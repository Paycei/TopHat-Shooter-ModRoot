#!/usr/bin/env python3
"""Pin the example mods' registry entries to the commit that holds them.

The example mods live in this repository (examples/<id>/), and each is listed
like any other mod, by mods/<id>.json pointing at this repository and a commit.
After committing a change to an example, run this to point its entry at that
commit (and copy its new version), then commit the entries:

    git commit -m "Update the Media example" examples/media
    python tools/pin_examples.py            # HEAD, or name another commit
    git commit -m "Pin the Media example" mods

Only an example whose files changed since its pinned commit is re-pinned, so the
others don't show as updates in players' Marketplace. A changed example must
raise "version" in its mod.json. Only the Python standard library is used.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "https://github.com/Paycei/TopHat-Shooter-ModRoot"
FIELDS = ["id", "title", "description", "repo", "commit", "version", "path"]


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r


def main():
    commit = git("rev-parse", sys.argv[1] if len(sys.argv) > 1 else "HEAD").stdout.strip()
    examples = sorted(e for e in os.listdir(os.path.join(ROOT, "examples"))
                      if os.path.isdir(os.path.join(ROOT, "examples", e)))
    errors, pinned = [], []
    for eid in examples:
        path = "examples/" + eid
        entry_file = os.path.join(ROOT, "mods", eid + ".json")
        if git("cat-file", "-e", "%s:%s/mod.json" % (commit, path), check=False).returncode != 0:
            errors.append("%s is not in commit %s: commit it first" % (path, commit[:12]))
            continue
        if not os.path.exists(entry_file):
            errors.append("mods/%s.json is missing: write it (title and description) first" % eid)
            continue
        entry = json.load(open(entry_file, encoding="utf-8"))
        manifest = json.loads(git("show", "%s:%s/mod.json" % (commit, path)).stdout.lstrip("﻿"))
        if manifest.get("id") != eid:
            errors.append('%s/mod.json says id "%s"' % (path, manifest.get("id")))
            continue
        old = entry.get("commit", "")
        known = git("cat-file", "-e", old + "^{commit}", check=False).returncode == 0 if old else False
        if known and git("diff", "--quiet", old, commit, "--", path, check=False).returncode == 0 \
                and entry.get("repo") == REPO and entry.get("path") == path:
            continue   # unchanged since its pinned commit
        if known and manifest.get("version") == entry.get("version"):
            errors.append('%s changed since %s: raise "version" in its mod.json' % (path, old[:12]))
            continue
        entry.update({"id": eid, "repo": REPO, "commit": commit,
                      "version": manifest.get("version", ""), "path": path})
        ordered = {k: entry[k] for k in FIELDS if k in entry}
        with open(entry_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")
        pinned.append("%s %s" % (eid, ordered["version"]))
    for e in errors:
        print("ERROR " + e)
    print("pinned to %s: %s" % (commit[:12], ", ".join(pinned) if pinned else "nothing changed"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
