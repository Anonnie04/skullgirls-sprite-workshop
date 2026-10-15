# Making custom sprites

1. Export the character and find the desired animation in Output. Keep Output as a reference.
2. Copy the selected PNG into Input using exactly the same relative directory and filename. For layered frames, edit the individual `frames/layers` PNGs; the composite is a reference.
3. Edit in an image editor that preserves RGBA transparency. Export a PNG with the original canvas dimensions whenever possible. Keep the pose aligned with the exported reference and avoid adding visible pixels outside its original tile coverage.
4. Check Input and prepare previews. Inspect the full-resolution prepared replacement, fitting notes, and any shared-art references before applying.
5. Close Skullgirls, apply ready replacements, then inspect the animation in-game. Keep the verified backup.

## Color and shape constraints

Game colors are palette material indices plus brightness and outline values. A PNG is converted to the installed default palette with neutral lighting. Matching that palette closely reduces approximation. Large edits, scattered colors, and fine texture can need more compressed bytes than the original slot.

Fitting may reduce brightness choices, preserve tiny existing color differences, consolidate equivalent materials, or adjust nearby shading values. Notes report the measured shading difference from ordinary palette fitting. Higher tolerances may produce banding. Material substitutions can render differently in alternate costumes, so inspect the palettes you intend to use.

The importer keeps the original lighting normals and frame metadata. It does not enlarge tile masks or compressed slots, change hitboxes or timing, or add animation frames. Whole-frame fitting may scale and align a different-sized PNG, and pixels outside original tiles can be clipped; preview notes report this.

Fully transparent replacements are supported. For shared art, editing one stored image can affect several frame references. Conflicting replacements for the same slot are refused.

## Import a numbered animation export

Use **Import animation sequence** in the Import replacements tab. Select one or more PNGs (for example `Timeline 1_0000.png`); filenames are sorted numerically. Choose the destination animation/layer and first destination frame, and inspect the source-to-destination mapping. Files map consecutively; no `_1p` suffix or manual renaming is required. Too many PNGs are refused instead of truncating the sequence.

To fix one frame, select only that PNG and choose its destination frame. Enable **Replace existing Input frames (back up first)** to update an existing edit. Previous Input copies and a filename mapping are retained in the project’s Sequence Imports folder. Source exports, Output and game archives are unchanged. Prepare previews after staging.

If your editor exports directly inside Input, staging registers those original export filenames so unchanged source copies do not cause path errors. If you edit them again, import the sequence again to refresh the mapped replacements.

The importer first tries the closest available palette colors, keeping unchanged pixels intact and using lossless storage optimizations. Original materials win only equal-distance ties. Visible shading adjustments and stronger material preferences are attempted only after this pass fails to fit; preview notes identify stronger original-material substitutions.
