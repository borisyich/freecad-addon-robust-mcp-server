# Drawing reconstruction guidance

## 1. Identify the view system before interpreting dimensions

Start from the whole sheet. Identify the principal/front view first, then every
available top, left/right side, section, detail, and isometric view. A view may
be unlabeled or placed non-standardly, so do not infer its identity from page
position alone.

Use geometry and annotation evidence:

- shared centerlines and repeated hole centers;
- matching outer silhouettes and feature counts;
- dimensions that must be shared between adjacent projections;
- section arrows, detail callouts, hidden lines, and symmetry marks;
- isometric views only as supporting spatial evidence.

Determine whether the sheet follows first-angle, third-angle, or a deliberately
non-standard arrangement. When the convention is unclear, classify views from
feature correspondence rather than layout.

## 2. Treat flat patterns as manufacturing views

A flat pattern/developed blank does not belong to the front/top/side camera
system. Identify it before constructing the orthographic view map.

Evidence includes a single planar blank contour, all holes shown in one plane,
straight bend lines, `BEND UP`/`BEND DOWN` callouts, and notes for thickness,
bend radius, or neutral factor. Two regions of a drawing may repeat the same
flat contour—one for bend/radius callouts and another for ordinate dimensions.
Do not classify those duplicates as different formed views.

Use the flat pattern for blank geometry, bend-line coordinates, panel adjacency,
and pre-bend feature locations. Use formed orthographic/isometric views for final
panel normals, bend signs, and spatial envelope. Build the panel-and-bend graph
described in
[sheet-metal-flat-patterns.md](sheet-metal-flat-patterns.md)
before choosing sketch planes or transforms.

## 3. FreeCAD view, plane, and normal-axis contract

Unless the model has an explicitly different global coordinate system, use:

| Drawing / camera view | True-shape projection plane | Normal / feature depth axis | FreeCAD sketch plane |
|---|---|---|---|
| Front / Rear | XZ | ±Y | `XZ_Plane` |
| Top / Bottom | XY | ±Z | `XY_Plane` |
| Left / Right side | YZ (ZOY) | ±X | `YZ_Plane` |
| Isometric | no single true-shape plane | none | verification only |

The sketch plane is selected from the view that shows the feature's true
profile, not from the camera angle that merely looks visually convenient.

### Circle/axis rule

If a boss, bore, or cylindrical ear appears as a true circle:

- circle in Front/Rear → profile lies in XZ, cylinder axis is Y;
- circle in Top/Bottom → profile lies in XY, cylinder axis is Z;
- circle in Left/Right → profile lies in YZ, cylinder axis is X.

This rule prevents a common failure: reproducing the correct circular outline on
the wrong plane, producing a plausible isometric model whose axis is rotated by
90 degrees.

## 4. Build a view map before the feature plan

Create a compact table such as:

| Source region | Identified view | FreeCAD camera | Projection plane | Normal axis | Proves | Does not prove |
|---|---|---|---|---|---|---|
| crop A | principal/front | Front | XZ | Y | height, X position, front profile | Y depth |
| crop B | side | Left/Right | YZ | X | depth, Z profile, cylindrical true shape | X thickness |
| crop C | top | Top | XY | Z | width, depth, planform | Z height |
| iso | isometric | Isometric | — | — | spatial arrangement | exact dimensions |

For every planned feature state:

- source view/crop;
- sketch or datum plane;
- normal/extrusion axis and sign;
- controlling in-plane dimensions;
- depth/offset source from another view;
- FreeCAD view used for the checkpoint screenshot.

Do not proceed with a feature whose profile plane and normal axis are still
implicit.

## 5. Assign dimensions to model axes

Create an axis-aware evidence table:

- feature or requirement;
- dimension/value/count;
- source view/detail;
- controlled axis or plane;
- explicit, derived, or assumed status;
- confidence and alternatives.

Before any modeling, also create and save a complete dimension inventory. It
must include every explicit source dimension except dimensions marked with an
asterisk. Give each item a stable unique identifier that can become a named
driving sketch constraint or Spreadsheet alias. Do not discard apparently
redundant values silently; use them as cross-checks or record a real conflict.

Rules:

1. A dimension shown in a projection plane usually controls one of the two axes
   visible in that plane.
2. Feature depth normal to the plane must come from another orthographic view,
   section/detail, or explicit depth/thickness callout.
3. Never turn a remembered 2D silhouette into an extrusion with an arbitrary
   length.
4. A centerline-to-datum dimension plus the relevant **outer** radius may define
   an outer extent. Cross-check any explicit overall dimension and do not use an
   inner diameter to derive an outer envelope.
5. Shared coordinates and overall dimensions must reconcile across all views
   before they become driving constraints.

## 6. Evidence extraction

1. Inspect the full sheet to identify views, sections, details, notes, units, and
   scale relationships.
2. Use `open_image_tiles` or focused crops for local dimensions and small
   geometry.
3. Record features, counts, radii/diameters, center locations, thicknesses,
   offsets, hidden boundaries, section evidence, and every non-starred dimension
   in the saved inventory.
4. Reconcile every feature across all applicable views before committing it to
   the feature plan.
5. Treat isometric views as a spatial cross-check, not the source of exact
   orthographic dimensions unless explicitly annotated.

## 7. Planning

Choose the stock/process classification first. Then plan a parametric sequence
with:

- Body and sketch names;
- sketch plane or datum;
- controlling dimensions and model axes;
- additive/subtractive/revolved operation;
- expected change in silhouette, volume, or bounds;
- reference view and candidate camera for verification.

A feature plan that says only “draw this outline and extrude” is incomplete. It
must also say **which view supplied the outline** and **which view supplied the
extrusion depth**.

## 8. Visual checking and multi-view fallback

Use same-view comparisons. A whole drawing sheet compared with an isometric
screenshot is weak evidence. Crop the relevant drawing view and orient FreeCAD
to the same projection.

`compare_images` only presents images. It does not align them, read dimensions,
or compute correctness. Explicitly inspect:

- outer silhouette and aspect ratio;
- feature count and symmetry evidence;
- center positions and spacing;
- cylindrical axis direction and profile plane;
- visible thickness/depth;
- openings, pockets, bends, and local radii;
- whether a match in one view hides a mismatch in another.

Despite being qualitative, this comparison is mandatory after every major
feature in drawing reconstruction. A screenshot that was merely captured or
opened is not a completed visual checkpoint. Before any linear, polar, mirrored,
or multi-transform pattern, compare the single seed element first; repeating an
unverified seed multiplies its error.

When one pair is inconclusive or suspicious, compare every principal target view
that exists:

1. front/principal;
2. matching left or right side;
3. top;
4. isometric.

Do not accept a model because its isometric image merely “looks similar.” The
orthographic set must agree on width, height, depth, axis orientation, and
feature placement.

## 9. ACT → OBSERVE → REACT with a view contract

### ACT

Create one reviewable feature or feature group with an explicit profile plane,
normal axis, and reference view.

### OBSERVE

- recompute and validate geometry;
- inspect Body Tip, solid count, volume/bounds, and sketch status;
- capture a settled screenshot in the matching candidate view, passing that
  view explicitly to `get_screenshot` rather than relying on a previous camera
  command or the default isometric view;
- compare against the corresponding target crop;
- state expected versus observed changes;
- broaden to the full available view set when similarity is uncertain.

### REACT

- continue only when the current feature is consistent with all relevant views;
- otherwise correct or undo the causal feature before adding downstream detail.

## 10. Autonomous ambiguity handling

When a value is unreadable or ambiguous:

1. inspect all views/details and nearby dimensions;
2. derive constraints from overall dimensions and repeated geometry;
3. choose the interpretation with the fewest unsupported assumptions;
4. record the assumption and confidence;
5. model it parametrically so it can be revised;
6. revisit the assumption when later evidence conflicts.

Do not silently invent a convenient dimension. Do not stop the entire task merely
because one noncritical value is uncertain; use the best-supported interpretation
and report it.
