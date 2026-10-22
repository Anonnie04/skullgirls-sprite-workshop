# Changelog

## 0.2.17 — 2026-10-23

- Add a 50–100% minimum shape-overlap slider to project matching, defaulting to 94%.
- Apply the chosen minimum to sequence and recovered pairings; retain ambiguity, layer and shared-target review checks.
- Save the threshold in matching reports and restore it when loading them. Slider changes take effect on the next match.

## 0.2.16 — 2026-10-23

- Edit each character mod’s name, version and multiline description in a window before exporting ZIPs.
- Retain metadata drafts per project while Workshop is open; validate required fields before export.

## 0.2.15 — 2026-10-22

- Add Approve selected and Return to review controls, with persistent decisions and loading of existing matching reports.
- Double-click pairings for a side-by-side preview with composite and editable-layer views.
- Require an explicit source-variant choice for conflicting targets. Back up unchanged staged copies when switching variants, and preserve later user edits.
- Keep approvals separate from copying, preparation and game changes; validate layers, hashes and report revisions before saving decisions.

## 0.2.14 — 2026-10-22

- Recover reordered and reused frames after sequence alignment using native-size, translation-tolerant alpha overlap.
- Recognize faint effects using relative opacity instead of dropping frames below a fixed alpha cutoff.
- Reuse identical old artwork across shared targets, deduplicate Input copies, and keep conflicting source variants in review.
- Show aligned shape overlap for recovered pairings. Fully transparent matches need no copy.

## 0.2.13 — 2026-10-22

- Compare softly normalized outlines when matching exported projects across game versions, avoiding false mismatches from small emblem, outline and alpha-edge changes.
- Keep frame order, aspect-ratio penalties, editable-layer checks and ambiguous-neighbor review. Compendium animation naming is unchanged.

## 0.2.12 — 2026-10-20

- Update Filia and Valentine character-select idle previews from edited standing idle sprites in Apply and mod ZIP exports.
- Verify source artwork, preserve menu timing, origins and animation metadata, and rebuild the RGB565 atlas with deduplicated tiles.
- Back up, verify, roll back and restore the menu archive alongside character art; leave unrelated textures and palettes intact.

## 0.2.11 — 2026-10-19

- Preserve the runtime's 0xBB completion marker after each relocated streamed-art payload. Missing markers caused movement and attack sprites to be skipped despite decoding in previews.
- Cover markers in original fixtures, exported ZIPs, and direct Apply/Restore checks.

## 0.2.10 — 2026-10-19

- Grow VRSN 9 art-memory sizes when relocated replacement streams expand either character art bank.
- Use the corrected metadata for both direct Apply and exported mod ZIPs, including existing prepared imports.
- Preserve larger reservations and all unrelated metadata; verify export, direct apply, rollback and restore with art-size regression fixtures.

## 0.2.9 — 2026-10-19

- Remove fixed compressed-slot limits from new imports by relocating replacement streams and updating only their art pointers, channel lengths, and brightness encoding flags.
- Stop storage-driven color, material, and shading approximations; support translucent palette materials during preparation.
- Include matching character metadata with exported mod ZIPs, and back up and restore all affected archives together.
- Verify exact-color oversized translucent replacements, untouched assets, rollback, restore, and legacy archive compatibility.

## 0.2.8 — 2026-10-19

- Add Save mod ZIPs beside Apply to export one verified mod-manager ZIP per character with ready replacements, without modifying the game.
- Continue frame matching when exported PNGs or whole character folders are missing, and report skipped frames instead of aborting the remaining characters.
- Preserve internal frame numbers and skip incomplete layered frames so missing exports cannot create invalid copy plans.

## 0.2.7 — 2026-10-18

- Correct legacy sprite colors using embedded character palette gradients and material ranges instead of DDS row indices.
- Use the same legacy palette interpretation for exports, silhouette matching, replacement previews, and imports.
- Validate both older palette layouts and add color, transparency, and verified import/restore regressions.

## 0.2.6 — 2026-10-18

- Support legacy FOIT metadata without version headers, including omitted storage fields on empty images and empty initial frames.
- Exclude characters lacking a default palette in the selected depot so unavailable boss assets cannot stop a playable-character export.
- Add regression coverage for pre-version-header exports and import preparation while retaining v3 and v9 checks.

## 0.2.5 — 2026-10-16

- Give the workshop an original Skullgirls-inspired art-deco theme with burgundy panels, gold accents, cream text, and coordinated tabs, tables, dialogs, and keyboard-focus states.

- Smooth the decorative diamond edges with antialiasing.

## 0.2.4 — 2026-10-15

- Resume interrupted restores safely using verified, atomic archive replacement.
- Stage and verify matched PNG copies before publishing them; failed copies remain retryable.
- Cancel preparation correctly even during the final reference-matching pass.
- Rebuild damaged catalog caches and publish caches and JSON receipts atomically.
- Validate replacement payloads without copying whole art banks; batch matching distances to reduce peak memory and improve cancellation.
- Add failure-injection regression checks for restore, copy, cache and cancellation recovery.

## 0.2.3 — 2026-10-15

- Recognize Parasoul troop Input names with or without the Compendium Misc_ prefix, while refusing ambiguous aliases.
- Map four translucent troop muzzle flashes with a narrowly scoped confidence check; refresh stored route caches.
- Explain that Compendium-only poses and parts require an existing stored game art slot for import.

## 0.2.2 — 2026-10-15

- Recognize single/double character folder prefixes and alternate Compendium frames-directory placement without moving PNGs.
- Resolve additional installed Compendium references lazily in exported projects.
- Keep actual Input paths in import integrity checks and refuse ambiguous normalized routes.

## 0.2.1 — 2026-10-15

- Try the closest palette colors with lossless compression before visible fitting.
- Prefer original materials only for equal-distance ties in the first passes.
- Retain the stronger original-material preference as an explicitly reported fallback.

## 0.2.0 — 2026-10-15

- Import numbered animation PNGs without requiring game-style filenames.
- Preview mappings and choose the destination animation/layer and first frame.
- Update individual frames with verified backups of existing Input edits.
- Refuse overflow and invalid PNGs; roll back staged changes on failure.

## 0.1.0 — 2026-10-12

First public release preparation.

- Export character PNGs into Compendium-style or numbered folders, with separate Output and Input branches.
- Generate the full empty Input tree without exporting every frame.
- Match old/new projects while accounting for inserted and removed frames; copy differing editable layers while preserving existing edits.
- Prepare full-resolution previews, fit colors and shading to fixed art slots, apply verified imports, and restore verified backups.
- Support FOIT v3/v9 and legacy depot archive paths.
- Accelerate exact RLE planning on the CPU, including extended literal packets, equivalent material indices, and ignored brightness bits.
- Offer bounded shading fitting with decoded opacity checks, interpolation safeguards, median shade selection, and explicit fitting notes.
- Validate shared-art conflicts, stale inputs, payload integrity, archive boundaries, and game-running restrictions.

Local validation: 37 isolated source/package checks, including median shade selection, passed. An entire 239-frame Filia input batch prepared without errors and was confirmed working in-game by the user. Wider fitting can still introduce visible color bands; review previews.
