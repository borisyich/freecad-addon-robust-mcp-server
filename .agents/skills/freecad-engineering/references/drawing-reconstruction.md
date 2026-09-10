# Drawing and image reconstruction

## Inventory and interpret

Open the complete source first. Inventory every view/detail/section depicting
the supplied part, including corroborative, opposite-side, auxiliary, isometric,
flat, and formed views. Give records stable IDs and source regions. Preserve
every explicit dimension and note with raw annotation, units, location, and
geometric referents. Asterisk, parentheses, REF, and TYP modify interpretation;
they do not remove evidence. Keep counts and process/material requirements
separate from physical dimensions.

Use crops or `open_image_tiles` when needed, with enough native resolution for
the specific unreadable evidence. More tiles and upscaling do not create detail.
Do not infer geometric precision from printed decimal places alone or use
pixel measurements as exact drawing dimensions without calibration and uncertainty.

Determine view identity from projection symbols, arrows, centerlines,
silhouettes, hidden geometry, and dimensions. Page position alone is insufficient.
A circle is evidence of a circular section normal to view only under the
appropriate projection and feature interpretation; silhouettes alone do not
prove a cylinder. Keep alternative view hypotheses until evidence resolves them.

## Frames and measurements

For standard FreeCAD cameras the global projection planes are:

| Camera | Plane | Normal axis |
|---|---|---|
| Front / Rear | XZ | Y |
| Top / Bottom | XY | Z |
| Left / Right | YZ | X |

Determine the sign and screen axes from the actual camera; the table does not
define drawing placement or local model coordinates. Preserve an existing
coordinate system. Map source coordinates to the model with an explicit frame,
including handedness, origin, units, and scale. Choose sketch planes from true
profile geometry and datums, not simply from the camera name.

For every planned feature identify its semantic profile, normal/depth direction,
location, termination, and source of depth/offset. A single external view may
leave multiple valid 3D interpretations. Do not invent hidden dimensions.

Each dimension record retains its source view, extension/leader targets,
corresponding semantic model elements, datum, axis/direction where applicable,
measurement semantics, role, and acceptance tolerance. Independently close
available signed dimension chains. An aligned distance is not a projected
distance; a wall gap is not a whole-model bounding-box extent. A local ordinate
becomes a global coordinate only after applying the datum transformation.

## Acceptance manifest and uncertainty

Use the tool's real schema:
`acceptance_manifest={"dimensions":[...],"views":[...],"requirements":[...]}`.
Map independent inputs to `driving`, redundant/check/reference values to
`verification`; retain both. Use actual constraint expressions for drivers and
measure final geometry for both roles. Stable IDs identify source relationships;
their identity should survive changes of nominal value.

Do not demote a driving requirement merely to avoid a solver conflict. Diagnose
the constraint graph and source interpretation. `source_issue` is exceptional:
retain concrete source defects, reinspection, attempted interpretations, and
conflicts. CAD disagreement is not source-defect evidence.

Pending interpretation or measurement remains explicitly unverified. The schema
does not permit `unresolved` as a terminal accepted role; that does not authorize
inventing a value or claiming complete acceptance. Continue independent work and
record the missing evidence or decision. Choose a reversible noncritical
assumption only when it does not determine a required interface or function.

## Sections and manufacturing views

Record exact candidate section/detail recipes. Use `section_shape` or planar
`slice_shape` for planar cuts. Offset/aligned paths require the source cutting
path and projection convention. `slice_shape(section_path=...,
section_depth_direction=..., align_segments=True)` produces developed segment
sections; confirm this matches the source convention. Not every broken cutting
line is a single plane or uses the same unfolding convention.

A flat blank is a manufacturing representation, not a camera view of the formed
part. Use [sheet-metal-flat-patterns.md](sheet-metal-flat-patterns.md) for panel,
bend, and coordinate-domain reasoning. Blank overall size need not equal formed
bounds.

## Compare equivalent evidence

During construction check affected dimensions and the smallest relevant source
view set after meaningful features. Before patterning validate the seed's shape,
placement, and orientation using the supplied evidence. Reproduce every source
view manifest record against the finished model at final acceptance, including
sections, opposite sides, and applicable manufacturing representations.

Orient the candidate explicitly; preserve camera state, projection, section,
detail framing, and scale where relevant. Do not combine a fixed orthographic
height with fit-all. For `compare_images`, surface and inspect returned MCP
ImageContent. A saved path or metadata is not an observation. Record concrete
agreement/discrepancy and a decision with `review_attestation`.

If the candidate occupies only a small fraction of its panel, reframe or crop
before claiming detailed profile correspondence. Match orientation and useful
apparent scale; independently verify physical dimensions so image resizing does
not conceal size drift. Record the actual recipe rather than a guessed camera.

Compare visible geometry and annotation semantics, accounting for occlusion,
line conventions, and perspective. A matching projection cannot prove hidden
depth. Use geometric measurements for numeric claims. The validator cannot
discover omitted source annotations or independently inspect pixels; manifest
and review records are caller attestations.

For sketch implementation also use
[sketch-construction.md](sketch-construction.md).
