# TopHat Shooter Mod Registry

The list of mods that **MODS.EXE's Marketplace** shows in
[TopHat-ShooterOS](https://github.com/Paycei/TopHat-Shooter). Each mod lives in
its author's own GitHub repository. This registry holds one small file per mod
that points to that repository at a **pinned commit**: the commit a maintainer
reviewed before merging. Updating a mod means pinning a newer commit, so the
code players install is always code that was reviewed.

## For players

Open **MODS.EXE → Marketplace**, pick a mod and press **Install**, then
**Apply & Reload**, as for any mod in your mods folder.
- When a newer reviewed version is listed, the mod shows **UPDATE**.
- Mods run with full access to the game and your files. The reason every
  listed mod is reviewed first is that only reviewed code reaches players.

## Publishing a mod

1. **Put the mod in a public GitHub repository.** `mod.json` goes at the
   repository's root, or in a subfolder (see `path` below). It must set `id`
   and `version`. [MODDING.md](https://github.com/Paycei/TopHat-Shooter/blob/main/mods-sdk/MODDING.md)
   explains how to write a mod.
2. **Push the commit you want to publish** to the repository's default branch.
   Copy its full id with `git rev-parse HEAD`.
3. **Fork this repository** and add `mods/<id>.json`, named after your mod's `id`:

   ```json
   {
     "id": "hello_hats",
     "title": "Hello Hats",
     "description": "Every enemy wears a tiny top hat. Purely cosmetic: rewards stay on.",
     "repo": "https://github.com/your-name/hello-hats",
     "commit": "4f1c2e8d0b6a5c3e9f7a1b2c4d6e8f0a1b3c5d7e",
     "version": "1.0.0"
   }
   ```

4. **Open a pull request.**
   - The `validate` check downloads your mod at that commit and checks the entry
     against its `mod.json`.
   - A maintainer then reviews the mod's code and merges it, and the mod appears
     in every player's Marketplace.

### The entry

| Field | Required | Rules |
|---|---|---|
| `id` | yes | The `id` in your `mod.json`: 1-40 characters of `a-z`, `0-9` and `_`. The file is named `<id>.json`. It must not be the id of one of the example mods the game ships. |
| `title` | yes | 1-48 characters, shown in the list. |
| `description` | yes | One line, 1-240 characters. |
| `repo` | yes | `https://github.com/<owner>/<name>`: no `.git`, no trailing slash. The owner is shown as the author. |
| `commit` | yes | The full 40-character commit id, in lowercase. The commit must be on the repository's default branch. |
| `version` | yes | The `version` in your `mod.json` at that commit, for example `1.2.0`. |
| `path` | no | The folder that holds `mod.json` when it is not the repository's root, for example `mods/hello_hats`. |

Titles and descriptions use characters the game's font can draw: the Latin-1
range (accents and `ñ` are fine, emoji are not). No other fields are accepted.

### Updating your mod

Push the new version, raising `version` in `mod.json`. Then open a pull request
that changes `commit` and `version` in your entry. Once it is merged, players
who installed the mod see **UPDATE**.

### Removing your mod

Open a pull request that deletes your entry, or ask a maintainer. Copies that
players already installed keep working. They just stop getting updates.

## Testing an entry before the pull request

- **Validator.** Check your entry with the same script the pull request runs
  (Python 3, nothing to install):

  ```
  python tools/validate_registry.py --online mods/<id>.json
  ```

- **In the game.** Point the game at your checkout of this repository. Its
  Marketplace then lists your branch's entries and installs them from GitHub as
  usual:

  ```
  TopHatShooterOS.exe --mod-registry C:\path\to\TopHat-Shooter-ModRoot
  ```

## What players download

The game downloads GitHub's archive of your repository at the pinned commit and
installs the folder that holds `mod.json`.
- **Size.** Players download the whole archive, so keep the repository small. A
  `.gitattributes` with `export-ignore` keeps files out of the archive, for
  example `screenshots/ export-ignore`.
- **Git LFS.** LFS files are not in GitHub's archives (it holds pointer files
  instead), so do not use LFS for the mod's files.
- **Symbolic links.** These are skipped.

## Review

A maintainer reads the mod's code at the pinned commit before merging. Mods run
with full access to the game and the player's files, so the registry does not
list a mod that:
- harms the player's computer or data;
- hides what it does;
- does something its title and description do not say.

## License

The registry itself is under the MIT license (see `LICENSE`). Each mod keeps its
own license. Adding one to your repository tells players and other modders what
they may do with your work.
