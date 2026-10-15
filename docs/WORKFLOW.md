# Projects, matching and imports

## Export and empty trees

Output contains images decoded from the selected game's archives. Input mirrors its directories and starts empty. Digital Art Compendium artwork supplies names through silhouette matching; it is not copied into Output. Duplicate names have internal-frame suffixes. Unmapped frames remain editable through `project.json`.

Generate full empty Input tree creates the directory layout without decoding every sprite. When Compendium references exist, matching is resolved lazily for characters with added Input files. Layered edits require an export of the individual layers.

Caches in `.skullgirls-cache` are reused only when the art, metadata, palette and reference signatures still match. They do not replace the integrity checks before applying.

## Match old and new projects

Choose the old exported source and the new exported target. Match frames produces a report; it does not stage any replacements. Sequence alignment permits inserted or removed frames. Low-confidence pairings require review and are not automatically copied.

Copy matched to target Input stages only confident, pixel-different editable PNGs. An existing edited Input file is preserved. An unchanged reference copy may be replaced by the matched source. Source and target Output exports remain intact. If the report says identical, no Input copy is created. Different folder names or different game metadata do not necessarily mean different rendered artwork.

## Prepare, apply and restore

Prepare previews reads the game and added Input PNGs, resolves frames, fits artwork, and creates a plan and payloads. Unchanged references, unknown paths, layered composites, shared-slot conflicts, and art that cannot fit are reported rather than silently imported.

Storage optimizations first use equivalent palette values and decoder-ignored brightness bits. Remaining shading overflows may use small nearby shade adjustments. Interpolated palette transitions are checked and their contributing pixels frozen when needed. Final decoded opacity and visible color bounds are verified. Notes show affected pixel counts and measured RGB differences; stronger fitting is flagged for banding.

Apply rechecks the game files, Input PNGs, metadata-derived slots and payload hashes. It creates verified backups before writing art bytes, checks that other archive bytes and protected files remain unchanged, and rolls back if verification fails. Close the game before applying or restoring.

Restore an import backup returns the affected archives to their verified original contents. Each archive is copied and verified before replacing the installed file. If restoration is interrupted, select the same backup again to resume; already restored archives are skipped. Keep the game closed until restoration finishes. Restore refuses when newer changes would be overwritten. Keep `project.json`, Prepared plans, and Backups together.

Input recognition accepts one or two repeated character folders before `data`, and Compendium layouts with `frames` at different directory depths. Only unique normalized routes are accepted; filenames still identify the frame unless the animation sequence importer is used. Additional installed Compendium references are resolved lazily. A recognized reference can still be refused during preparation if no reliable stored game frame exists or individual layers are required. Input files are not moved, and integrity checks use their actual paths.

Parasoul troop filenames accept the Compendium `Misc_` prefix as optional. The Compendium also contains unused troop poses and standalone bikes that have no corresponding standalone art slot in the game; these cannot be added through an art-only replacement. Use exported rider/bike frames or bike-part frames for edits to the assets the game actually stores.
