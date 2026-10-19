# Making custom sprites

1. Export the character and find the desired animation in Output. Keep Output as a reference.
2. Copy the selected PNG into Input using exactly the same relative directory and filename. For layered frames, edit the individual `frames/layers` PNGs; the composite is a reference.
3. Edit in an image editor that preserves RGBA transparency. Export a PNG with the original canvas dimensions whenever possible. Keep the pose aligned with the exported reference and avoid adding visible pixels outside its original tile coverage.
4. Check Input and prepare previews. Inspect the full-resolution prepared replacement, fitting notes, and any shared-art references before applying.
5. Close Skullgirls, apply ready replacements, then inspect the animation in-game. Keep the verified backup.

## Color and shape constraints

Game colors are palette material indices plus brightness and outline values. A PNG is converted to the installed default palette with neutral lighting. Matching that palette closely reduces approximation. Large edits, scattered colors, and fine texture can need more compressed bytes than the original slot.

Preparation keeps all brightness choices and supports translucent palette materials. It does not consolidate materials, quantize shades, or approximate whites to fit the old byte budget. Streams can grow and their storage references are updated. Exact colors available in the installed palette are preferred; colors absent from it still require the closest representable sample.

The importer keeps the original lighting normals, tile masks, hitboxes and timing. Only art pointers, compressed channel lengths, and brightness encoding flags change in frame metadata. It does not add animation frames. Whole-frame fitting may scale and align a different-sized PNG, and pixels outside original tiles can be clipped; preview notes report this.

Fully transparent replacements are supported. For shared art, editing one stored image can affect several frame references. Conflicting replacements for the same slot are refused.

## Import a numbered animation export

Use **Import animation sequence** in the Import replacements tab. Select one or more PNGs (for example `Timeline 1_0000.png`); filenames are sorted numerically. Choose the destination animation/layer and first destination frame, and inspect the source-to-destination mapping. Files map consecutively; no `_1p` suffix or manual renaming is required. Too many PNGs are refused instead of truncating the sequence.

To fix one frame, select only that PNG and choose its destination frame. Enable **Replace existing Input frames (back up first)** to update an existing edit. Previous Input copies and a filename mapping are retained in the project’s Sequence Imports folder. Source exports, Output and game archives are unchanged. Prepare previews after staging.

If your editor exports directly inside Input, staging registers those original export filenames so unchanged source copies do not cause path errors. If you edit them again, import the sequence again to refresh the mapped replacements.

The importer uses the closest available palette colors and keeps unchanged pixels intact. Original materials win equal-distance ties. Review the resulting preview with the palettes you intend to use; the same rendered color can have more than one material representation.
