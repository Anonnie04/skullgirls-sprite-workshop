# Projects, matching and imports

## Export and empty trees

Output contains images decoded from the selected game's archives. Input mirrors its directories and starts empty. Digital Art Compendium artwork supplies names through silhouette matching; it is not copied into Output. Duplicate names have internal-frame suffixes. Unmapped frames remain editable through `project.json`.

Generate full empty Input tree creates the directory layout without decoding every sprite. When Compendium references exist, matching is resolved lazily for characters with added Input files. Layered edits require an export of the individual layers.

Caches in `.skullgirls-cache` are reused only when the art, metadata, palette and reference signatures still match. They do not replace the integrity checks before applying.

## Match old and new projects

Choose the old exported source and the new exported target. Match frames produces a report; it does not stage any replacements. Sequence alignment permits inserted or removed frames. Low-confidence pairings require review and are not automatically copied.

Copy matched to target Input stages only confident, pixel-different editable PNGs. An existing edited Input file is preserved. An unchanged reference copy may be replaced by the matched source. Source and target Output exports remain intact. If the report says identical, no Input copy is created. Different folder names or different game metadata do not necessarily mean different rendered artwork.

Project matching compares softly normalized outlines so small emblem, edge and alpha-boundary revisions across game versions do not overwhelm pose similarity. Frame order, aspect ratio, editable layers and ambiguous neighboring poses still constrain matches. This does not change Compendium animation naming. Rerun Match projects to regenerate older matching reports; exporting the projects again is not required.

After sequence alignment, Workshop searches for reordered or reused artwork among the remaining frames. It aligns alpha images at their native scale, with small scale tolerance, so an altered emblem changing the bounding box does not distort the entire comparison. Relative opacity includes faint effects. The table shows aligned shape overlap for recovered candidates. Strong, distinct matches and identical repeated source images can be copied; uncertain candidates and different old images sharing one current target stay in review. Identical duplicates are copied to each destination once. Fully transparent pairs need no copy. Frame/layer compatibility and export integrity checks still apply.

Double-click a pairing to inspect source and target images side by side; layered frames have a composite/layer selector. Select review rows (Ctrl/Shift for multiple) and click **Approve selected**, or approve from the preview. Approved pairings join **Copy ready PNGs to target Input**. Approval only saves a report decision; it does not copy files or change the game. **Return to review** removes a ready pairing from the copy plan. Use **Load report…** to reopen `matches.json` with its saved decisions; rerunning matching creates a fresh report.

Choose only one different source variant per target. If a selected variant conflicts with ready or previously staged art, Workshop asks which one to keep and returns other ready choices to review. On the next Copy, an unchanged staged copy of an explicitly replaced variant is backed up under the report's `Input backups` folder before replacement. Later edits remain protected. Returning a pairing to review does not remove files that were already copied to Input. Incomplete or incompatible editable layers cannot be approved as a whole.

## Prepare, apply and restore

Prepare previews reads the game and added Input PNGs, resolves frames, fits artwork, and creates a plan and payloads. Unchanged references, unknown paths, layered composites, shared-slot conflicts, and art that cannot fit are reported rather than silently imported.

New preparations encode all brightness levels and all palette materials, including translucent effects. They do not alter colors or materials to satisfy the original compressed size. Replacement art is appended to the character asset; all shared frame references receive the new pointer, channel lengths, and explicit per-row brightness encoding. VRSN 9 art-memory sizes also grow to cover the resulting art banks, preserving any larger reservations. Both direct Apply and Save mod ZIPs use these sizes, including when opening an existing prepared import. Other character metadata stays byte-identical. Existing ZIPs need to be exported again to include this correction. The installed palette still determines which PNG colors can be represented.

Apply rechecks the game files, Input PNGs, metadata-derived slots and payload hashes. It stages rebuilt art and metadata archives, verifies every replacement and untouched asset, and creates verified backups before installation. It rolls back installed archives if a write fails. Palettes remain unchanged. Close the game before applying or restoring. Existing fixed-slot preparations remain supported; prepare again to use the new behavior.

Relocated streamed art includes the runtime's `0xBB` completion marker immediately after its compressed channels. This marker is outside the channel lengths; previews can decode the pixels without it, but the game skips the sprite when it is missing. Version 0.2.11 adds the marker for both Apply and Save mod ZIPs. Re-export ZIPs made by earlier relocation builds before using them in a mod manager.

Version 0.2.12 also synchronizes the separate character-select idle animation for Filia and Valentine. Both Apply and Save mod ZIPs rebuild `sprites/character_select_NAME.dds` and its `.spr.msb` frame table from changed standing idle layers. The original preview must match the expected idle artwork before conversion. RGB565 menu storage retains palette selection and outline at the menu resolution; timing, origins and animation metadata are preserved. Other characters are not yet synchronized. Direct Apply backs up and stages `sprites.gfs` in the same transaction, verifies all unrelated textures and palette bytes, and includes it in rollback and Restore. Existing fixed-slot preparations must be prepared again to use this feature.

Restore an import backup returns the affected archives to their verified original contents. Each archive is copied and verified before replacing the installed file. If restoration is interrupted, select the same backup again to resume; already restored archives are skipped. Keep the game closed until restoration finishes. Restore refuses when newer changes would be overwritten. Keep `project.json`, Prepared plans, and Backups together.

Input recognition accepts one or two repeated character folders before `data`, and Compendium layouts with `frames` at different directory depths. Only unique normalized routes are accepted; filenames still identify the frame unless the animation sequence importer is used. Additional installed Compendium references are resolved lazily. A recognized reference can still be refused during preparation if no reliable stored game frame exists or individual layers are required. Input files are not moved, and integrity checks use their actual paths.

Parasoul troop filenames accept the Compendium `Misc_` prefix as optional. The Compendium also contains unused troop poses and standalone bikes that have no corresponding standalone art slot in the game; these cannot be added through an art-only replacement. Use exported rider/bike frames or bike-part frames for edits to the assets the game actually stores.

### Mod ZIP details

After preparing replacements, choose **Save mod ZIPs…**. The Mod details window lets you edit the name, version and description written to `mod.json` for each character. Switch characters to edit separate details without losing drafts. Name and version must contain text; descriptions may be empty or span multiple lines. **Choose folder and export…** validates all characters before asking for a destination. Cancelling the folder picker keeps the window open. Drafts remain available per project during this Workshop session. Metadata edits affect exported ZIPs only.

### Shape-overlap tolerance

Set **Minimum shape overlap** in Sort between projects before matching. The slider runs from 50% to 100% in whole percentage points, with a 94% default. Both sequence matches and recovered poses must meet this minimum for automatic acceptance. Registration allows position shifts and small size differences. Lowering the minimum does not bypass editable-layer compatibility, competing poses or source-variant conflicts. Below-threshold pairings remain available for manual review when a pairing exists. Changing the slider leaves existing decisions unchanged; run **Match frames** to generate a new report with that value. Reports retain their selected threshold; older reports without a setting display 94%.
