# Skullgirls Sprite Workshop

A Windows desktop tool to export Skullgirls character sprites, match frames between game versions, and import custom PNG artwork into the game.

## Download and run

Download the Windows ZIP from this repository's Releases page, extract it, and open **Skullgirls Sprite Workshop.exe**. No Python installation is needed for the portable build. The executable is unsigned.

You supply your installed game or an older depot. Game archives, sprites, and the Digital Art Compendium are not included. This is an unofficial tool; the MIT license applies to this project's code, not Skullgirls assets.

## Workflow

1. **Export project:** choose the game folder, a project destination outside the game installation, and characters. Create Output + empty Input exports PNGs and matching empty replacement folders.
2. **Import replacements:** use **Import animation sequence** to select numbered PNGs, choose an animation/layer and the first destination frame, and review the mapping. Any filename prefix works; originals stay unchanged. Select one PNG and its destination to fix a single frame. Optional replacement backs up existing Input frames into Sequence Imports. Alternatively, place edited PNGs in Input at the same relative paths as Output. Check Input, prepare previews, and inspect fitting notes. Close the game before applying. The app backs up affected art archives and verifies the installed changes.
3. **Sort between projects:** match an old source project to a new target project, then copy ready PNGs into target Input. Original Output files and existing edited Input files are preserved. Pixel-identical frames are skipped.

Matching supports projects with different character selections. Removed Output character folders and missing PNGs are skipped and recorded in the match report; later characters continue matching. Incomplete layered frames are skipped as a whole.

After preparing and reviewing replacements, **Save mod ZIPs…** beside Apply exports one ZIP per character with ready changes. Import these ZIPs into Skullgirls Mod Manager. The ZIPs contain patched character art assets and `mod.json`; exporting leaves the game and Input files unchanged. Use the same game version used for preparation. Mods that replace the same character art asset can override each other according to manager load order.

```text
Skullgirls Project .../
  Output/character/character/data/.../frames/frame.png
  Input/character/character/data/.../frames/
  project.json
  Prepared/       # reviewable previews and import plans
  Backups/        # verified restore copies after applying
  Matches/        # cross-version pairing and copy reports
```

**Generate full empty Input tree** builds the complete replacement folder layout without extracting every animation. Digital Art Compendium references provide animation names when available; otherwise exports use internal frame numbers. Frames without reliable Compendium matches remain importable in unmapped folders.

Imports preserve frame metadata, animation timing, origins, hitboxes, tile masks, palettes, archive lengths, and lighting normals. Artwork must fit the original tile coverage and compressed storage slots. Some frames need color or shading approximation, and stronger fitting can produce visible bands. Preview notes identify these changes. Material substitutions can look different with alternate palettes. Future game updates can require a new export or decoder changes.

Current FOIT v9, older v3, and legacy archives without version headers are supported, including older `temp` archive paths. Characters without a default palette in the selected game version are excluded from the character list. Native CPU compression is used when available; GPU acceleration is not required. The first native compilation in an app session takes additional time.

Legacy exports use the character metadata's embedded palette gradients. Re-export older projects created before v0.2.7 to replace incorrectly colored reference PNGs before editing or importing replacements.

## Documentation

- [Making custom sprites](docs/CUSTOM_SPRITES.md)
- [Matching, fitting, and restoring imports](docs/WORKFLOW.md)
- [Building and preparing a GitHub release](docs/RELEASING.md)
- [Release notes](CHANGELOG.md)

## Run from source

Use 64-bit Python 3.12 on Windows with Tkinter installed:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Pinned dependency versions match the validated release environment. The source may work elsewhere, but the supported release target is Windows x64.

## Test and build

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python test_workshop.py
.venv\Scripts\python scripts/build_release.py
```

Tests generate isolated synthetic archives and hidden UI fixtures; they do not change the installed game. The build script checks the packaged app and produces Windows/source ZIPs plus SHA-256 checksums in `release/`. See [Contributing](CONTRIBUTING.md) for the code layout.

## License

[MIT](LICENSE). Portable builds also include the bundled dependencies' license notices.
