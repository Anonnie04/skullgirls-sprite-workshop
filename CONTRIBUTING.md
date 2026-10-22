# Contributing

Use Windows x64 and Python 3.12. Install `requirements-dev.txt` and run `python test_workshop.py` before proposing changes. Run `python scripts/build_release.py` when changing packaging or native compression imports.

## Code layout

| File | Responsibility |
| --- | --- |
| `app.py`, `workshop_app.py` | Tkinter entry point and three-tab UI |
| `decoder.py` | GFS archive reading, FOIT parsing, tile decoding and color rendering |
| `layout.py` | Digital Art Compendium naming and silhouette descriptors |
| `animation_sequence.py` | Numbered PNG mapping, staging and Input backups |
| `project_match.py` | Cross-version sequence alignment and guarded Input copies |
| `pose_recovery.py` | Reused/reordered artwork recovery and opacity-aware image registration |
| `match_review.py` | Validated approval decisions, shared-target choices and preview routes |
| `workshop.py` | Projects, previews, fitting, verified apply and restore |
| `compression.py` | Exact-length RLE and constrained value planning |
| `compression_fast.py` | Optional Numba acceleration |
| `test_workshop.py` | Synthetic archive and UI integration checks |
| `scripts/build_release.py` | Portable and source release packaging |

Keep game archives, user projects, previews, backups, and extracted artwork outside the repository. Tests should use generated fixtures. Preserve byte-identical palettes, animation metadata, normals, input integrity checks, and rollback behavior. Relocated imports may change art storage pointers, channel lengths, brightness encoding flags, and VRSN 9 art-memory size fields only; verify every other metadata byte and all untouched assets. Character-select synchronization may also replace the supported character's menu atlas and tile references, preserving durations, origins and animation metadata. Include sprites.gfs in backup, rollback and restore whenever it changes; all unrelated textures and palette assets must stay byte-identical. Never shrink existing art-memory reservations. Keep validation for older fixed-slot plans. Add focused regression tests for changes to these guarantees.

Bug reports should identify the app version, game/depot version, selected character, steps, expected result, actual result, and the error text. An animation name and frame/layer identifier help diagnose matching issues.
