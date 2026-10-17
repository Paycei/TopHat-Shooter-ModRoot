#!/usr/bin/env python3
"""Check the mod registry.

Every entry is checked on its own (format, fields, duplicates). Entries named
on the command line, or changed since a commit, are also checked against
GitHub with --online: the mod's archive at the pinned commit is downloaded and
its mod.json read, and the commit must be on the repository's default branch.

    python tools/validate_registry.py
    python tools/validate_registry.py --online mods/my_mod.json
    python tools/validate_registry.py --online --changed-since <commit>

The game reads entries with the same rules (src/modding/mod_market.nim in
github.com/Paycei/TopHat-Shooter), so an entry that passes here is one the
game lists. Only the Python standard library is used.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMAT = 1
FIELDS = {"id", "title", "description", "repo", "commit", "version", "path"}
OPTIONAL = {"path"}
MAX_TITLE = 48
MAX_DESCRIPTION = 240
LARGE_ARCHIVE = 50 * 1024 * 1024
# The example mods the game ships (Install Examples writes these folders).
EXAMPLE_IDS = {"arena_3d", "chaos_engine", "content_pack", "cosmetics", "critical_section", "hello_hud",
               "house_rules", "media", "mixins", "necromancer", "overclock", "story_mode"}

ID_RE = re.compile(r"[a-z0-9_]{1,40}\Z")
REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
VERSION_RE = re.compile(r"[0-9][A-Za-z0-9.+-]{0,31}\Z")
PATH_RE = re.compile(r"[A-Za-z0-9._/-]{1,200}\Z")
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"


def font_text(s, max_chars):
    """One line the game's font draws: U+0020..U+007E and U+00A0..U+00FF."""
    if not s or len(s) > max_chars or s.strip() != s:
        return False
    return all(0x20 <= ord(c) <= 0x7E or 0xA0 <= ord(c) <= 0xFF for c in s)


def repo_parts(repo):
    m = REPO_RE.match(repo)
    if not m or m.group(2) in (".", "..") or m.group(2).lower().endswith(".git"):
        return None
    return m.group(1), m.group(2)


def valid_path(p):
    if p == "":
        return True
    if not PATH_RE.match(p) or p.startswith("/") or p.endswith("/") or "//" in p:
        return False
    return all(part not in (".", "..") for part in p.split("/"))


def check_entry(name, text):
    """Errors in one registry file (its name and contents)."""
    errors = []
    if not name.endswith(".json"):
        return ["registry entries are .json files"]
    try:
        e = json.loads(text)
    except ValueError as err:
        return ["not valid JSON: %s" % err]
    if not isinstance(e, dict):
        return ["must be a JSON object"]
    unknown = set(e) - FIELDS
    if unknown:
        errors.append("unknown field(s): %s" % ", ".join(sorted(unknown)))
    for key in sorted(FIELDS - OPTIONAL):
        if key not in e:
            errors.append('missing "%s"' % key)
    for key, value in e.items():
        if key in FIELDS and not isinstance(value, str):
            errors.append('"%s" must be a string' % key)
    if errors:
        return errors
    eid = e["id"]
    if not ID_RE.match(eid):
        errors.append('"id" must be 1-40 characters of a-z, 0-9 and _')
    elif name[:-5] != eid:
        errors.append("the file must be named %s.json" % eid)
    if eid in EXAMPLE_IDS:
        errors.append('"%s" is the id of an example mod the game ships' % eid)
    if not font_text(e["title"], MAX_TITLE):
        errors.append('"title" must be 1-%d characters (Latin-1, no line breaks)' % MAX_TITLE)
    if not font_text(e["description"], MAX_DESCRIPTION):
        errors.append('"description" must be one line of 1-%d characters (Latin-1)' % MAX_DESCRIPTION)
    if not repo_parts(e["repo"]):
        errors.append('"repo" must be https://github.com/<owner>/<name> (no .git, no trailing slash)')
    if not COMMIT_RE.match(e["commit"]):
        errors.append('"commit" must be the full 40-character commit id, in lowercase')
    if not VERSION_RE.match(e["version"]):
        errors.append('"version" must be a version like 1.2.0')
    if not valid_path(e.get("path", "")):
        errors.append('"path" must be a folder of the repository, like "mods/my_mod" (or "")')
    return errors


def http_get(url, accept=None):
    headers = {"User-Agent": "TopHat-Shooter-ModRoot-validator"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return r.read()


def check_online(e, notes):
    """Errors found by fetching the mod from GitHub (warnings go to notes)."""
    owner, name = repo_parts(e["repo"])
    commit, path = e["commit"], e.get("path", "")
    errors = []
    # The commit must be on the default branch: GitHub also serves commits that
    # only exist in a fork through the parent's URL.
    try:
        info = json.loads(http_get("https://api.github.com/repos/%s/%s" % (owner, name)))
        if info.get("private"):
            return ["the repository is private"]
        if info.get("fork"):
            notes.append("the repository is a fork of %s" % info.get("parent", {}).get("full_name", "?"))
        branch = info["default_branch"]
        cmp = json.loads(http_get("https://api.github.com/repos/%s/%s/compare/%s...%s"
                                  % (owner, name, branch, commit)))
        if cmp.get("status") not in ("identical", "behind"):
            errors.append("commit %s is not on the default branch (%s) of %s/%s"
                          % (commit[:12], branch, owner, name))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return ["repository or commit not found (is it public, and is the commit pushed?)"]
        errors.append("GitHub API: HTTP %d" % err.code)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as err:
        errors.append("GitHub API: %s" % err)
    # What the game downloads: the archive at the pinned commit.
    try:
        data = http_get("https://codeload.github.com/%s/%s/zip/%s" % (owner, name, commit))
    except (urllib.error.URLError, OSError) as err:
        return errors + ["the archive could not be downloaded: %s" % err]
    if len(data) > LARGE_ARCHIVE:
        notes.append("the archive is %.1f MB: players download all of it" % (len(data) / 1048576))
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return errors + ["the download is not a zip archive"]
    if z.comment.decode("ascii", "replace").strip() != commit:
        errors.append("the archive is not commit %s" % commit)
    names = z.namelist()
    top = names[0].split("/")[0] + "/" if names else ""
    prefix = top + (path + "/" if path else "")
    if prefix + "mod.json" not in names:
        return errors + ["no mod.json in %s" % (path or "the repository's root")]
    try:
        manifest = json.loads(z.read(prefix + "mod.json").decode("utf-8-sig"))
    except ValueError as err:
        return errors + ["mod.json is not valid JSON: %s" % err]
    if not isinstance(manifest, dict):
        return errors + ["mod.json must be a JSON object"]
    if manifest.get("id") != e["id"]:
        errors.append('mod.json says id "%s", the entry says "%s"' % (manifest.get("id"), e["id"]))
    if "version" not in manifest:
        errors.append('mod.json must set "version" (the entry says "%s")' % e["version"])
    elif manifest["version"] != e["version"]:
        errors.append('mod.json says version "%s", the entry says "%s"' % (manifest["version"], e["version"]))
    main = manifest.get("main", "main.lua")
    if not isinstance(main, str) or main.startswith("/") or ":" in main:
        errors.append('"main" in mod.json must be a path inside the mod')
    elif prefix + main not in names and not ("main" not in manifest and
                                             any(n.startswith(prefix + "content/") for n in names)):
        errors.append("the main script %s is not in the archive" % main)
    if "disableAchievements" in manifest and not isinstance(manifest["disableAchievements"], bool):
        errors.append('"disableAchievements" in mod.json must be true or false')
    if "game" in manifest and not (isinstance(manifest["game"], str) and manifest["game"][:1].isdigit()):
        errors.append('"game" in mod.json must be a version string')
    for info in z.infolist():
        if not info.filename.startswith(prefix) or info.is_dir():
            continue
        if (info.external_attr >> 16) & 0xF000 == 0xA000:
            notes.append("%s is a symbolic link: the game skips it" % info.filename[len(prefix):])
        elif info.file_size < 200 and z.read(info).startswith(LFS_POINTER):
            errors.append("%s is a Git LFS pointer: LFS files are not in GitHub's archives"
                          % info.filename[len(prefix):])
    return errors


def changed_entries(since):
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", since, "HEAD", "--", "mods/"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.endswith(".json")]


def changed_outside_mods(since):
    out = subprocess.run(["git", "diff", "--name-only", since, "HEAD"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if not line.startswith("mods/")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--online", action="store_true", help="also check the named entries on GitHub")
    ap.add_argument("--changed-since", metavar="COMMIT", help="check the entries added or changed since COMMIT")
    ap.add_argument("files", nargs="*", help="entries to check online (mods/<id>.json)")
    args = ap.parse_args()

    report = []      # (file, errors, notes)
    failed = False

    try:
        reg = json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))
        if reg.get("format") != FORMAT:
            report.append(("registry.json", ['"format" must be %d' % FORMAT], []))
    except (OSError, ValueError) as err:
        report.append(("registry.json", ["cannot be read: %s" % err], []))

    entries = {}
    mods_dir = os.path.join(ROOT, "mods")
    for fname in sorted(os.listdir(mods_dir)) if os.path.isdir(mods_dir) else []:
        if fname == ".gitkeep":
            continue
        rel = "mods/" + fname
        if os.path.isdir(os.path.join(mods_dir, fname)):
            report.append((rel, ["mods/ holds entry files only, no folders"], []))
            continue
        text = open(os.path.join(mods_dir, fname), encoding="utf-8").read()
        errors = check_entry(fname, text)
        if not errors:
            entries[rel] = json.loads(text)
        report.append((rel, errors, []))

    seen = {}
    for rel, e in entries.items():
        key = (e["repo"], e.get("path", ""))
        if key in seen:
            report.append((rel, ["lists the same mod as %s" % seen[key]], []))
        seen.setdefault(key, rel)

    online = list(args.files)
    author_notes = []
    if args.changed_since:
        online += changed_entries(args.changed_since)
        outside = changed_outside_mods(args.changed_since)
        if outside:
            author_notes.append("this change also edits the registry's own files (%s): maintainers only"
                                % ", ".join(outside[:5]))
    if args.online:
        author = os.environ.get("PR_AUTHOR", "")
        for rel in sorted(set(f.replace("\\", "/") for f in online)):
            if rel not in entries:
                if not any(r == rel and errs for r, errs, _ in report):
                    report.append((rel, ["not a valid entry of this registry"], []))
                continue
            notes = []
            errors = check_online(entries[rel], notes)
            owner = repo_parts(entries[rel]["repo"])[0]
            if author and author.lower() != owner.lower():
                notes.append("submitted by %s, the repository belongs to %s" % (author, owner))
            report.append((rel + " (online)", errors, notes))

    lines = []
    for rel, errors, notes in report:
        if errors:
            failed = True
            for err in errors:
                lines.append("ERROR %s: %s" % (rel, err))
        for note in notes:
            lines.append("NOTE  %s: %s" % (rel, note))
    for note in author_notes:
        lines.append("NOTE  %s" % note)
    checked = sum(1 for rel, _, _ in report if rel.startswith("mods/") and not rel.endswith("(online)"))
    online_count = sum(1 for rel, _, _ in report if rel.endswith("(online)"))
    lines.append("%s: %d entries checked, %d online" % ("FAILED" if failed else "OK", checked, online_count))
    print("\n".join(lines))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Registry check\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
