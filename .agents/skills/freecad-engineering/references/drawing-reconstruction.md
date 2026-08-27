# Drawing reconstruction guidance

## 1. Inventory every source view before interpreting dimensions

Start from the whole sheet and identify **every graphical region that carries
geometric evidence**, not only the view that appears principal. This includes
all present orthographic directions and opposite-side views, sections, aligned
or offset sections, details, auxiliary views, isometric/axonometric views, and
applicable formed/unfolded manufacturing views. Assign each one a stable
`view_id`. Even an apparently redundant or merely corroborative depiction remains
a source view and final validation target. A view may be unlabeled, duplicated,
or placed non-standardly, so do not infer its identity from page position alone
and do not skip it because another projection looks more informative.

Use geometry and annotation evidence:

- shared centerlines and repeated hole centers;
- matching outer silhouettes, through-features, and feature counts;
- dimensions that must reconcile between projections;
- section arrows, detail callouts, hidden lines, and symmetry marks;
- which local features are visible on one face but absent on the opposite face;
- isometric/axonometric views as spatial evidence and as final visual targets.

Explicitly test whether two similar projected outlines are opposite sides of the
same part when their through-features align but face-local geometry differs.
Determine whether the sheet follows first-angle, third-angle, or a deliberately
non-standard arrangement. When the convention is unclear, classify views from
feature correspondence rather than layout.

## 2. Treat flat patterns as manufacturing views

A flat pattern/developed blank does not belong to the ordinary orthographic
camera system. Identify it before constructing the orthographic view map.

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

This table only maps standard cameras to the global frame. It is not a whitelist
of source views: custom, auxiliary, opposite-side, detail, and section views must
still be inventoried and reproduced when present.

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

## 4. Build a complete view manifest before the feature plan

Create one record for **every identified source view**. A compact schema is:

| view_id | Source region | Drawing role/type | Physical side/look direction | Candidate camera/section recipe | Projection plane / normal | Proves |
|---|---|---|---|---|---|---|
| V1 | crop A | orthographic | identified from evidence | matching FreeCAD camera | mapped plane/axis | listed features/dimensions |
| V2 | crop B | opposite-side orthographic | identified from evidence | matching FreeCAD camera | mapped plane/axis | face-local geometry |
| S1 | section A-A | aligned section | cutting-line evidence | `slice_shape(...)` recipe | section-defined | internal steps/radii |
| I1 | isometric | isometric | spatial camera | matching camera state | — | spatial arrangement |

For non-standard cameras, preserve enough `get_camera_state` information to
reproduce the candidate view. For a section, preserve the exact
`section_shape`/`slice_shape` parameters. For a detail, preserve the parent
view, target region, and equivalent candidate framing.

For every planned feature state:

- source `view_id` that supplies the profile or placement evidence;
- sketch or datum plane;
- normal/extrusion axis and sign;
- controlling in-plane dimensions;
- depth/offset source from another view/detail/section;
- candidate view(s) that can expose an error in this feature.

Do not proceed with a feature whose profile plane and normal axis are still
implicit. Every view-manifest record remains a required final validation target,
even when it contributed no driving feature.

## 5. Assign every dimension to semantic geometry and model axes

Before any modeling, create a complete dimension inventory containing every
explicit source dimension. A numeric value alone is not a parsed dimension. An
asterisk, parentheses, `REF`, `TYP`, or another drafting marker is source
metadata to preserve and interpret; it is not a reason to omit the annotation
from the inventory. For each item record:

- stable `dimension_id`, raw annotation, value, and unit;
- `source_view_id` and source location;
- source extension lines/leaders/centerlines or other geometric references;
- the corresponding semantic model elements it spans or controls;
- controlled axis/plane and dimension semantics (distance, projected distance,
  radius, diameter, angle, thickness, etc.);
- `driving` or `verification` role;
- candidate validation view/section and measurement recipe;
- confidence and rejected alternatives when interpretation was ambiguous.

Do not discard apparently redundant values silently; use them as verification
checks. Do not use `unresolved`, `unknown`, or an equivalent terminal role just
because interpretation is difficult. Reinspect all applicable views/details and
the dimension chain, choose the best-supported semantic interpretation, and
record its confidence.

The only exceptional terminal role is `source_issue`, and it requires concrete
source evidence: the annotation remains illegible at the best useful source
resolution; its extension/leader targets cannot be identified; independent
source dimensions contradict each other beyond stated/drafting tolerance under
every plausible interpretation; or the annotation is demonstrably malformed or
orphaned. Record the raw source token, source view/location, attempted
interpretations, conflict evidence, and exact reason. A disagreement with the
current CAD hypothesis is never sufficient.

For every ordinate or baseline item, the inventory must preserve the
datum/reference, controlled axis, signed direction, and target feature in
addition to value and unit. Never reinterpret a local ordinate as a global
coordinate merely because its number is readable. Before converting an
ordinate/baseline set to global coordinates, close at least one signed control
chain from its datum through an intermediate feature to the target and reconcile
the result with an overall/check dimension or a second view. Resolve a failed
chain before constructing geometry.

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
6. During validation, reproduce the dimension's `source_view_id` (or its
   section/detail context) and measure between the same semantic model elements
   with the same dimension semantics. A different projection, bounding-box
   extent, or convenient surrogate is not equivalent unless the source dimension
   itself is defined that way. Driving-expression linkage does not replace this
   geometric measurement.

## 6. Evidence extraction

1. Inspect the full sheet and enumerate every geometric view/detail/section into
   the view manifest before modeling.
2. Use `open_image_tiles` for local dimensions and small geometry. Tiles are
   cropped at source resolution and only downscaled when they exceed the
   configured long-side limit. Start with the default 2 x 3 grid or the minimum
   grid that makes annotations readable. Increase it only after identifying
   specific evidence that remains unreadable; never choose nine tiles merely
   because the tool permits nine.
3. For every drawing section, save a matching candidate-section recipe before
   modeling is considered complete. Use `section_shape` for standard XY/XZ/YZ
   sections, `slice_shape(plane_point=..., plane_normal=...)` for arbitrary
   planar sections, and `slice_shape(section_path=...,
   section_depth_direction=..., align_segments=True)` for offset/aligned sections
   with a broken cutting line. In path mode, provide the ordered 3D cutting-line
   points in the drawing-view plane and the axis normal to that view; the tool
   unfolds the segment sections into one XY-plane result for section-to-section
   inspection. Record `section_type`, source cutting path, and exact candidate
   recipe in the view manifest. If the source cutting line changes direction,
   `section_shape` and planar `slice_shape` are not equivalent substitutes.
4. Extract every dimension from every view and assign its semantic
   references and role before geometry creation. No dimension may disappear from
   the manifest because it is redundant, inconvenient, or difficult to map.
5. Record features, counts, radii/diameters, center locations, thicknesses,
   offsets, hidden boundaries, and section/detail evidence per `view_id`.
6. Reconcile every feature across all applicable views before committing it to
   the feature plan.
7. Treat isometric views as spatial evidence and final visual comparison targets;
   use their dimensions as exact inputs only when explicitly annotated.

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

## 8. Visual checking and complete view-set validation

Use one-to-one equivalent-view comparisons. A whole drawing sheet compared with
one model screenshot is weak evidence. Use the source view record and orient or
section FreeCAD to reproduce the same projection, physical side, cutting recipe,
detail context, or non-standard camera.

For non-standard candidate views, use `set_camera_position` with explicit
`look_at`, `up_direction`, orthographic projection, and (when scale must remain
fixed) `orthographic_height`. Record the result with `get_camera_state`. Do not
combine `fit_all` with an explicit orthographic height.

`compare_images` only presents images. It does not align them, read dimensions,
or compute correctness. Explicitly inspect:

The comparison is not reviewed until the returned MCP `ImageContent` is surfaced
to and inspected by the vision model. A multi-call wrapper must forward image
blocks rather than retaining only text. A saved file or structured metadata by
itself is not visual evidence.

- outer silhouette and aspect ratio;
- feature count and symmetry evidence;
- center positions and spacing;
- cylindrical axis direction and profile plane;
- visible thickness/depth;
- openings, pockets, bends, and local radii;
- whether a match in one view hides a mismatch in another.

During modeling, comparison is mandatory after every major feature, but use the
smallest set of source views that directly exposes that feature; repeatedly
rendering unrelated views adds cost without evidence. A screenshot that was
merely captured or opened is not a completed visual checkpoint. Before any
linear, polar, mirrored, or multi-transform pattern, compare the single seed
element first; repeating an unverified seed multiplies its error.

For each completed view comparison, retain the comparison path,
`image_content_reviewed=true`, a concrete visual observation, and the
accept/rework decision. These records belong in the final
`acceptance_manifest`; creating comparison artifacts without reviewing their
image content leaves the view incomplete.

Before final acceptance, iterate through **every view-manifest record** and
reproduce its candidate view from the finished model. Compare every pair,
including opposite-side orthographic views, all sections/details/auxiliary
views, and isometric/axonometric or manufacturing views when present and
applicable. This exhaustive final pass is required even if earlier feature
checkpoints were conclusive. Do not accept a model because one projection or an
isometric image merely “looks similar.” The complete source-view set must agree
on the geometry each record is able to prove.

## 9. ACT → OBSERVE → REACT with a view contract

### ACT

Create one reviewable feature or feature group with an explicit profile plane,
normal axis, and reference view.

### OBSERVE

- recompute and validate geometry;
- inspect Body Tip, solid count, volume/bounds, and sketch status;
- reproduce the source view(s) that directly expose the current feature, passing
  the camera/section recipe explicitly rather than relying on prior GUI state;
- compare against the corresponding source record(s);
- measure any dimensions affected by the feature between the same semantic
  elements in their recorded source-view context;
- state expected versus observed changes;
- broaden to any additional source views that can expose an uncertainty.

### REACT

- continue only when the current feature is consistent with all relevant views;
- otherwise correct or undo the causal feature before adding downstream detail.

## 10. Autonomous ambiguity handling

When a value or its semantic target is initially unreadable or ambiguous:

1. inspect all views/details/sections and nearby dimensions;
2. trace extension lines, leaders, centerlines, datums, and repeated geometry;
3. derive and close applicable dimension chains;
4. choose the interpretation with the fewest unsupported assumptions and the
   strongest cross-view consistency;
5. record the interpretation, confidence, and rejected alternatives;
6. model it parametrically so it can be revised;
7. revisit the interpretation when later evidence conflicts.

Do not silently invent a convenient dimension and do not park it indefinitely as
`unresolved`. If the source itself is demonstrably defective, use `source_issue`
only with the evidence required in Section 5. Otherwise choose and document the
best-supported semantic interpretation and continue.
