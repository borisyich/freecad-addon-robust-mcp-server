---
name: freecad-engineering
description: >
  Use for every task that operates FreeCAD to create, reconstruct from a
  drawing or image, modify, repair, or validate a mechanical 3D model. Covers
  stock and manufacturing-process classification, milling, turning, sheet-metal
  bending, native parametric Body/Sketch/PartDesign structure, feature ordering,
  visual checks, and the mandatory final validate_parametric_model report. Do
  not use for ordinary MCP-server code or documentation work unless the task
  also changes a CAD model.
---

# FreeCAD engineering

Use this skill as the engineering policy for model creation and modification.
It is guidance, not a rigid state machine: choose the smallest reliable sequence
for the actual part, but preserve editable design intent and verify the result.

## Load MCP guidance selectively

Do not dump the global client tool registry with a broad search such as:

```javascript
const names = ALL_TOOLS.filter(
  x => /freecad|resource|prompt|mcp/i.test(x.name + " " + x.description)
);
text(names);
```

That query also matches unrelated platform tools and prints their complete
descriptions and schemas, which can consume a large part of the model context.

Discover only the guidance needed for the current step:

1. Use the exact MCP server ID `freecad-mcp` when listing prompts or resources.
2. List names/URIs first; do not print every description or schema.
3. Read one targeted resource, starting with
   `freecad://skills/freecad-engineering` for modeling policy. Use
   `freecad://capabilities`, `freecad://best-practices`, or one workflow resource
   only when the current task needs it.
4. If this Skill was loaded through MCP rather than from the repository, resolve
   its relative `references/...` links under
   `freecad://skills/freecad-engineering/`; the complete bundle URI index is
   `freecad://skills/freecad-engineering/bundle`.
5. Invoke one relevant prompt such as `freecad_startup`,
   `reproduce_from_drawing`, `modify_existing_model`, or
   `freecad_guidance(task_type=...)`; do not load the entire prompt catalogue.
6. Inspect an exact tool definition only when its typed arguments remain
   unclear. In clients exposing `ALL_TOOLS`, filter by the exact name or the
   `mcp__freecad_mcp__` prefix and print a compact name/size summary rather than
   complete definitions.

Stop discovery as soon as the current operation has enough guidance. Re-read a
resource or prompt later only when the task enters a different workflow or a
specific tool contract is unclear.

## First rule for every engineer: feedback loop (ACT → OBSERVE → REACT)

Use an ACT → OBSERVE → REACT loop throughout model creation and modification.

### ACT

Create or modify one logically reviewable feature or closely related feature
group. Recompute the document.

### OBSERVE

Check the result using evidence appropriate to the operation:

- sketch solver and profile state;
- Body Tip, validity, solid count, volume and bounds;
- screenshot from a relevant view;
- comparison with the corresponding drawing view when reconstructing from an
  image.

Observation is not complete merely because a screenshot was created. State what
changed, what was expected, and whether a discrepancy exists.

### REACT

Choose one response:

- continue when the result matches the intended geometry and design plan;
- rework when the operation is invalid, ineffective, disconnected, incorrectly
  oriented, dimensionally inconsistent, or visually inconsistent with the
  reference.

When rework is required, correct or undo the causal feature before adding later
features.

Apply the loop after every major feature and whenever a result is uncertain or
suspicious. Trivial operations may be grouped when they form one reviewable
engineering step.

## Required outcome

Unless the user explicitly requests a disposable direct B-rep or imported-shape
workflow, deliver a native editable FreeCAD model:

- one intended `PartDesign::Body` per manufactured part;
- one contiguous solid in each Body unless the design is intentionally multi-solid;
- `Sketcher::SketchObject` sketches with geometric and dimensional constraints;
- semantic PartDesign features such as Pad, Revolution, Pocket, Groove, Hole,
  Pattern, Rib, Fillet, or Chamfer where they express the design intent;
- key dimensions controlled by named constraints, expressions, or Spreadsheet
  aliases when reuse or editing benefits from them;
- for drawing/sketch reconstruction, a saved view manifest containing every
  graphical source view/detail/section that carries geometric evidence and the
  candidate camera/section recipe used to reproduce it from the model;
- a saved dimension manifest containing every explicit source
  dimension, a stable identifier, its source view, the same semantic elements it
  spans or controls, and a justified `driving` or `verification` role. Use the
  exceptional `source_issue` role only with concrete source evidence as defined
  below; never use `unresolved` as a terminal dimension classification;
- a valid Body Tip and no accidental visible helper solids.

`execute_python`, `safe_execute`, and `run_macro` are always available. They may
create or edit the model, but they do not waive the requirements above. Python
used for production geometry should create native FreeCAD document objects and
editable history rather than only assigning a final `Shape` to `Part::Feature`.

## Mandatory final inspection

After any task that creates or changes model geometry, call:

For a drawing/sketch reconstruction, pass the complete saved source acceptance
manifest to the validator. The validator derives every `driving` identifier from
that manifest, traces it to the target geometry, and checks that every
`driving`/`verification` record has final same-view measurement evidence and
every source-view record has reviewed visual-comparison evidence:

```text
validate_parametric_model(
    doc_name=<intended document>,
    acceptance_manifest={"dimensions":[...], "views":[...]},
)
```

`required_dimension_names` remains a legacy compatibility input. Supplying it
without `acceptance_manifest` is not complete drawing acceptance and must not be
reported as such. If both are supplied, the list must exactly match every
manifest item whose role is `driving`.

When the requested deliverable is a sketch rather than a final solid, scope the
same diagnostic to that sketch:

```text
validate_parametric_model(
    doc_name=<intended document>,
    target={"kind":"sketch", "name":<intended sketch>},
    acceptance_manifest={"dimensions":[...], "views":[...]},
)
```

In sketch scope, required dimensions must influence non-construction geometry of
that exact sketch. Body, solid, and Tip state are not acceptance criteria.

For other geometry-changing tasks, `required_dimension_names` may be omitted.

Do this immediately before the final user-facing response. Summarize:

1. document and Body names;
2. Body and Tip validity;
3. ordered feature history;
4. sketch solver/profile status, especially under-, over-, redundant, or
   conflicting constraints;
5. solids outside Bodies and other significant findings;
6. whether every identified source view was reproduced from the final model
   with an equivalent camera/section/detail context and compared one-to-one;
7. whether every driving source dimension drives the model and every driving
   and verification dimension has a same-view semantic measurement with
   expected/observed/pass-fail evidence;
8. whether every exceptional `source_issue` dimension has concrete source
   evidence, attempted interpretations, and a disclosed reason;
9. whether every Spreadsheet alias is connected directly or transitively to
   the feature tree, or has been removed as redundant;
10. limitations that still require visual or dimensional verification.

The validator is informative. Do not convert every warning into failure, but do
not hide warnings or claim a clean parametric result when the report contradicts
that claim.

## 1. Classify the part before modeling

Determine the likely starting stock and dominant manufacturing process from the
drawing, existing model, or geometry.

### Stock-form candidates

- plate, slab, or rectangular block;
- sheet;
- round bar or tube;
- hexagonal bar;
- flat bar, angle, channel, or extrusion/profile;
- preform, casting, forging, or imported blank when clearly indicated;
- unknown or hybrid when evidence is insufficient.

### Dominant process candidates

- **milling**: mostly prismatic faces, pockets, slots, planar steps, drilled
  holes, and features reachable from a finite set of setups;
- **turning**: dominant rotational symmetry around one axis, diameters,
  shoulders, bores, tapers, grooves, and axial lengths;
- **sheet-metal bending/forming**: near-constant thickness, planar panels,
  bend radii/angles, flanges, hems, tabs, beads, dimples, or a flat pattern;
- **hybrid**: for example turned blank plus milled flats/cross-holes, or bent
  sheet plus machined holes.

Record the classification and evidence before selecting the base feature. Do
not force a part into one process when the drawing clearly implies a hybrid.

Read the detailed strategy in
[references/manufacturing-strategies.md](references/manufacturing-strategies.md).

## 2. Choose a stable parametric skeleton

- Select origin planes and datums from functional symmetry, primary dimensions,
  and manufacturing setup—not from the current camera view.
- Prefer sketches on origin/datum planes for stable dependencies. Attach to a
  generated face only when the feature logically belongs to that face or the
  available MCP tool requires it.
- Center symmetric geometry about an origin plane when that simplifies later
  mirroring, patterns, and dimension changes.
- Use the fewest sketches that still express independent design intent. Avoid a
  single enormous sketch for unrelated features and avoid one sketch per trivial
  line when features belong together.
- Prefer geometric constraints (`Horizontal`, `Vertical`, `Coincident`,
  `Tangent`, `Equal`, symmetry) plus a minimal set of driving dimensions.
- Do not constrain nearly every endpoint with absolute X/Y coordinates. That can
  produce 0 DoF while obscuring datum relationships, tangency, equality, and
  feature intent. `fully_constrained` is solver evidence, not proof of correct
  geometry or parameterization.
- For ordinate drawings, classify every absolute coordinate as `source_backed`,
  `derived` from a closed dimension chain, or `solver_lock`. Preserve justified
  source/derived coordinates and minimize only solver-lock coordinates. Treat a
  `coordinate_review_recommended` diagnostic as a mandatory audit, not a ban.
- For Spreadsheet-driven dimensions, create a cell alias first and attach the
  expression to the dimensional constraint path (`Constraints[index]`). In
  `edit_sketch_constraints`, supply `expression` when creating the constraint,
  or use `set_expression`/`clear_expression` for an existing index. A readable
  `constraint_name` documents intent but does not replace the expression path.
  Numeric sketch `angle` constraint values are degrees at the MCP boundary. An
  angle expression must evaluate to an angular quantity: store `45 deg` in the
  Spreadsheet or multiply a unitless alias by `1 deg`; do not pass radians.
- After constraint edits, use compact `get_sketch_info()` first. Request
  `detail_level="constraints"` or paged `"full"` only when exact indices,
  referenced elements, datum/name/driving state, or expression bindings are
  needed for a specific diagnosis.
- Avoid broad `Fix`/`Block` constraints as a substitute for design intent.
  They may constrain at most 50% of the sketch geometry. When the next Fix
  would exceed that limit, use geometric/dimensional constraints or delete
  existing Fix/Block constraints before continuing.
- Driving sketches should normally be fully constrained before completion.
  Intermediate under-constrained sketches are acceptable only while actively
  being developed. Over-constrained, conflicting, redundant, or solver-error
  states must be corrected.

For drawing-derived sketch construction, follow
[references/sketch-construction.md](references/sketch-construction.md). It gives
the required straight-lines-first workflow, fillet/radius selection, datum-chain
check, B-spline gate, profile-topology acceptance, and validation-integrity rule.
For a flat pattern, accept external contour, radius transitions, holes, bend
lines, and final parameterization as separate feature-group checkpoints.

## 3. Plan features by dependency and design intent

Use this default order, then adjust when dependencies require another order:

1. primary datum/origin strategy and stock or base envelope;
2. major additive/revolved form and structural flanges, walls, bosses, or ribs;
3. major material-removal features that establish the principal shape;
4. secondary pockets, slots, grooves, bores, and local formed features;
5. repeated holes and patterns after the seed feature is verified;
6. small details, reliefs, and manufacturing clearances;
7. fillets and chamfers last, unless an earlier radius is a functional parent
   for later geometry.

This is a robust CAD-history order, not necessarily the literal shop-floor
operation sequence. Preserve design dependencies first; document manufacturing
assumptions separately.

For **late detail features**, use this default sequence when dependencies allow:
local stiffening ribs or formed reinforcements → holes and repeated hole patterns
→ secondary pockets/local cutouts/reliefs → fillets and chamfers. A rib or major
pocket that defines the primary load path or principal envelope is not a late
detail and should be created earlier.

## 4. Model according to the dominant process

### Milling

- For a simple part whose design intent is naturally additive, use constrained
  sketches and additive PartDesign features, followed by pockets and holes.
- For a complex machined part, start from a stock-like rectangular, plate, or
  profile envelope and remove material progressively. Verify that every removal
  intersects the intended stock and leaves one valid solid.
- Prefer a small number of meaningful setup-aligned sketches over many arbitrary
  booleans.

### Turning

- Establish the axis once and model the main axial half-profile with a constrained
  sketch and Revolution.
- For a complex turned part, begin with the maximum revolved envelope or stock
  profile, then add bores, grooves, shoulders, tapers, axial holes, and local
  features with revolved or subtractive operations.
- Keep diameter/radius semantics explicit and place cross-holes, flats, keyways,
  or milled features after the axisymmetric form is stable.

### Sheet-metal bending/forming

- Start with the largest functional planar panel or the panel that best controls
  the coordinate system, then establish the nominal thickness.
- Before calling dedicated operations, use `sheet_metal_capabilities()` once.
  Create the first native wall with `create_sheet_metal_base`; add flanges,
  sketch-line folds, hems, junctions, and reliefs with the discriminated
  `create_sheet_metal_feature` tool. Do not substitute PartDesign Pad/Fillet
  chains when a SheetMetal proxy expresses the manufacturing intent.
- When a **flat pattern/developed blank** is present, treat it as a manufacturing
  representation rather than an orthographic view of the formed part. It defines
  the planar blank perimeter, flat-domain hole/cutout locations, bend lines, and
  panel adjacency. Do not use its overall extents as the final 3D bounding box.
- For SheetMetal-designed parts, prefer holes and contour cutouts in the source
  flat blank sketch before `create_sheet_metal_base`: that records their panel
  ownership directly and lets them bend with the panel. A later subtractive
  Hole, Pocket, Groove, or cylindrical cut is still valid when the design intent
  requires it; keep it as a linear tail after the last native SheetMetal feature
  and inspect/unfold that current Tip. Generated Unfold sketches are
  verification output, not a second production feature history.
- Before modeling, split the flat pattern into named panel regions and build a
  bend table containing each bend axis, adjacent fixed/moving panels, signed
  up/down direction, angle, inside radius, neutral rule, and expected final panel
  normal. `BEND UP`/`BEND DOWN` are relative to the viewed blank face, not
  automatically to global FreeCAD `+Z`/`-Z`.
- Distinguish planar **profile radii** on the cut perimeter from **bend radii** at
  bend lines. Curved blank edges remain panel boundaries; they are not evidence
  of a curved bend axis.
- Add connected flanges/tabs and bends while preserving one continuous body and
  constant nominal thickness. Holes and cutouts belong to their panels and must
  rotate with those panels during folding. Verify overlap, gaps, and bend
  direction after every major flange.
- Resolve every topology input with `select_subshapes`; pass its references to
  the sheet-metal tool instead of guessing `EdgeN`, `FaceN`, or `VertexN`.
  Keep the history linear: the base of the next native operation is the current
  Body Tip.
- A bend deforms material around a neutral axis; do **not** generically simulate
  it by adding volume on one side and subtracting an equal volume on the other.
  Use sheet-metal/bend features when available. If they are unavailable, use a
  documented constant-thickness approximation with tangent bend zones and do not
  claim a reliable native unfold.
- Bend allowance, bend deduction, K-factor, inside radius, and thickness control
  the developed blank. Use explicit drawing/manufacturing data when supplied;
  do not invent production values or apply bend compensation twice to an already
  dimensioned flat pattern.
- Verify both representations when possible: the formed state against formed or
  isometric views, and the unfolded state against the supplied flat contour,
  bend lines, and feature locations.
- After the formed state is stable, call
  `inspect_sheet_metal(detail_level="candidates")` and use one of its planar
  candidates as evidence for the stationary face. Request `full` only when
  individual cylindrical faces or complete history evidence must be diagnosed.
  Create the flat pattern
  with `unfold_sheet_metal`, supplying either an explicit K-factor plus ANSI/DIN
  convention or a named material-definition Spreadsheet. Never rely on an
  implicit workbench K-factor default.
- Prefer `unfold_sheet_metal(..., verification_only=True)` for final validation.
  It returns flat-shape, outline, bend-line, and hole evidence and then removes
  the temporary Unfold/helper sketches, so the final structural validator sees
  only the manufactured-part history. Persist an Unfold only when the user needs
  an editable/exportable flat-pattern object in the saved document.
- Separate bend-dominated stamped parts from stretch-formed or deep-drawn
  parts. Ordinary bend allowance/K-factor reasoning applies to developable bend
  zones, not to material stretched over dies. Do not claim an exact blank for a
  deep draw, emboss, or complex stamping without explicit tooling/forming data.
- Beads, dimples, louvers, embossed ribs, and other formed details require local
  thickness continuity. Simple additive/subtractive approximations are allowed
  only when they preserve the intended outer/inner surfaces sufficiently for the
  task and are clearly reported as approximations.

Read the detailed flat-pattern workflow in
[references/sheet-metal-flat-patterns.md](references/sheet-metal-flat-patterns.md).

## 5. Reconstruct from drawings or images

### 5.1 Establish the drawing view-to-axis map before modeling

Do not begin feature planning from a remembered silhouette or from one assumed
anchor view. First inventory **every graphical source view that carries geometric
evidence**: any orthographic direction, opposite-side view, section, aligned or
offset section, detail, auxiliary view, isometric/axonometric view, and any
formed/unfolded manufacturing view that applies to the task. Assign each one a
stable `view_id`. Every drawing view that depicts any part geometry must be
inventoried, even if it appears redundant, corroborative, or less useful for
construction. A view may be absent, duplicated, unlabeled, or intentionally
placed non-standardly; none may be skipped merely because another view appears
more conventional or more informative.

Do not classify a view only from its page position. Determine the projection
convention and confirm view identity from shared centerlines, repeated feature
centers/counts, dimensions, section arrows, matching silhouettes, and which
geometry is visible or hidden. Explicitly test the opposite-side hypothesis when
two views share the same projected envelope and through-features but show
different face-local geometry. Some evaluation drawings deliberately depart
from drafting standards.

Use this FreeCAD coordinate contract unless the task explicitly establishes a
different global frame:

| Drawing / FreeCAD camera | Projection plane seen without foreshortening | Normal / feature depth axis | Typical sketch plane |
|---|---|---|---|
| Front / Rear | XZ | ±Y | `XZ_Plane` |
| Top / Bottom | XY | ±Z | `XY_Plane` |
| Left / Right side | YZ (ZOY) | ±X | `YZ_Plane` |
| Isometric | none; verification only | none | do not choose a sketch plane from isometry alone |

This table is only a coordinate mapping contract for standard cameras. It is
**not** a whitelist of drawing views to inspect or validate; every source-view
manifest record remains mandatory even when it needs a custom camera or section
recipe.

A feature profile belongs to the plane in which its true shape is shown. Its
Pad/Pocket/Hole direction is normally perpendicular to that plane. Therefore:

- a circular boss shown as a circle in a side view is planned on `YZ_Plane`,
  with its axis along X;
- a circular boss shown as a circle in the front view is planned on `XZ_Plane`,
  with its axis along Y;
- a circular boss shown as a circle in the top view is planned on `XY_Plane`,
  with its axis along Z.

Before creating the first feature, write a compact **complete view map** with
one record for every identified source view. Each record must contain:

- stable `view_id`, source region/crop, and identified drawing role/type;
- physical side/look direction when applicable, FreeCAD camera/projection plane,
  or the exact `section_shape`/`slice_shape` recipe for a section;
- viewing/normal axis and any non-standard camera state needed to reproduce it;
- dimensions, features, and visibility relationships that this view proves;
- the candidate screenshot/section/detail recipe that will reproduce the same
  evidence from the final model.

For every planned feature, state the source `view_id`, sketch/datum plane,
normal/extrusion axis, and which other source evidence supplies depth or offset.
Never copy a 2D outline from one view and invent its normal depth from visual
appearance. Every view record remains a required final validation target even if
it was not needed to create a feature.

### 5.2 Assign dimensions to axes, not merely to views

Build an axis-aware evidence table. For every source dimension record at least:
`dimension_id`, raw annotation/value/unit, `source_view_id`, the source extension
lines/leaders or other semantic references, the model elements the dimension
controls or spans, controlled axis/plane, role, validation measurement recipe,
and confidence/alternatives.

A dimension is not understood merely because its numeric value was read. The
agent must determine **what geometric relationship that value constrains or
checks**. During validation, reproduce the dimension's source view/section and
measure the candidate between the same semantic elements using the matching
distance/radius/diameter/angle/thickness semantics. Do not substitute a bounding
box or a different projection unless that is what the source dimension actually
represents. A named driving expression proves parameter linkage, but it does not
replace this same-view geometric measurement.

- Dimensions measured in a projection plane control the two axes visible in that
  plane.
- Feature depth along the plane normal must come from another orthographic view,
  a section/detail, or an explicit depth/thickness callout.
- A centerline location plus an outer radius may define an overall extent, but
  use the radius of the boundary being dimensioned and cross-check any explicit
  overall dimension. Do not mix an inner diameter from one boundary with the
  outer envelope of another.
- Shared dimensions must reconcile across views before they drive a sketch or
  feature.

### 5.3 Inspect local evidence and plan the model

- Open the whole sheet first to identify views, sections, details, dimensions,
  notes, and scale relationships.
- Use `open_image_tiles` when dimensions/features are too small in the full
  sheet. Tiles preserve native crop resolution unless they exceed the configured
  long-side cap; they are not upscaled. Start with the default 2 x 3 grid or the
  smallest grid likely to make annotations readable. Increase the grid only
  after naming evidence that remains unreadable; do not select the maximum tile
  count pre-emptively.
- Treat every drawing section as geometric evidence, not merely annotation. If a
  section view exists, reproduce the candidate section before completion and
  compare section-to-section. Use `section_shape` for an origin-aligned XY/XZ/YZ
  section, or `slice_shape` for an arbitrary plane. For an offset/aligned section
  whose cutting line bends, call `slice_shape(section_path=[...],
  section_depth_direction=[...], align_segments=True)`: `section_path` is the
  ordered 3D cutting line from the drawing view and `section_depth_direction` is
  the axis normal to that drawing view. The returned aligned-path section is
  unfolded into one XY plane for inspection. Record `section_type`, the source
  cutting path, and this exact mode in the view manifest. When the source cutting
  line changes direction, `section_shape` and planar `slice_shape` are not
  equivalent substitutes. Do not infer internal steps,
  chamfers, fillets, wall thicknesses, or axial offsets from external views when
  the section provides explicit evidence.
- Before creating geometry, extract and save every explicit dimension from every
  source view. Preserve drafting markers such as an asterisk, parentheses,
  `REF`, or `TYP` in the raw annotation and determine what they mean; a marker is
  not a reason to omit the dimension. Give each dimension a stable identifier,
  attach it to its `source_view_id` and semantic target elements, and classify it
  as `driving` or `verification`. A redundant/check/reference dimension is
  `verification`, not disposable evidence.
- Do **not** use `unresolved`, `unknown`, or an equivalent bucket as a terminal
  structured role merely because interpretation is difficult. Continue reading
  the drawing, inspect the applicable views/details/sections, reconcile the
  dimension chain, then choose the best-supported semantic interpretation and
  record its confidence and alternatives.
- The only exceptional terminal role is `source_issue`. Use it only after
  targeted reinspection produces concrete evidence that the source itself is
  defective for that dimension: for example the annotation remains illegible at
  the best useful source resolution; extension/leader targets cannot be
  identified; independent source dimensions are mutually contradictory beyond
  stated/drafting tolerance under every plausible interpretation; or the
  annotation is geometrically malformed/orphaned. Record the raw source token,
  source view/location, attempted interpretations, conflict/evidence, and exact
  reason. A conflict with the current CAD model is never sufficient evidence of
  a `source_issue`.
- For every ordinate/baseline dimension, also save its datum/reference,
  controlled axis, signed direction, and target feature. A value without its
  datum is incomplete evidence. Before converting such dimensions to global
  coordinates, independently close at least one control dimension chain from
  datum to target and reconcile it with an overall/check dimension or another
  view.
- Build the complete view manifest, axis-aware dimension manifest, and feature
  plan before modeling. Every driving item must later be a named constraint or
  connected Spreadsheet parameter. Every non-`source_issue` dimension, including
  every driving item, must also retain deterministic same-view observed value,
  tolerance, pass/fail, semantic measurement targets, and tool evidence.
- Resolve ambiguity autonomously by choosing the interpretation most consistent
  across all views. Keep interpretation mutable after modeling starts: record
  assumptions and rejected alternatives, and revise datum, endpoints, radii,
  signs, dimension roles, and feature mapping when observations conflict.

### 5.4 Compare the current feature against the correct references

At each ACT → OBSERVE → REACT checkpoint, keep the current feature's view/plane
contract explicit. Set the candidate camera to the same projection as the
reference crop before taking the screenshot. Prefer a single explicit call such
as `get_screenshot(view_angle="Left", settle_time_seconds=2.0, ...)`; do not rely
only on a preceding `set_view_angle` call or on the default isometric view.

Run numerical checks before visual comparison. For sketches, compare bounding
box extents, hole centers/radii, and other deterministic manifest values first.
Then compare only equivalent source/candidate view records: the same physical
side and projection, the same section cutting recipe, the same detail region, or
the same non-standard camera. A good match in one projection does not prove
correct depth, axis direction, opposite-face geometry, or hidden geometry.

During modeling, use `compare_images` after every major feature against the
smallest set of source views that directly exposes that feature; do **not**
re-render every view after every feature when it adds no evidence. A screenshot
without comparison is not a completed visual checkpoint. Broaden the checkpoint
to any additional source views that can expose an uncertainty or contradiction.

The comparison is incomplete until its returned MCP `ImageContent` has been
surfaced to and inspected by the vision model. When orchestrating multiple calls,
forward image blocks; never retain only text/metadata. Saving a comparison file
or receiving its structured metadata is not visual review. Record the comparison
path, `image_content_reviewed=true`, a concrete visual observation, and the
accept/rework decision in the view manifest.

Before final acceptance, however, the rule is exhaustive: iterate through
**every record in the source view manifest**, reproduce its candidate
camera/section/detail from the finished model, and perform a one-to-one
comparison. This includes opposite-side views, all sections/details/auxiliary
views, and isometric/axonometric or manufacturing views when present and
applicable. No view may be omitted because another projection already looked
correct. Only finish when the complete source-view set is mutually consistent or
a concrete source defect is documented. The comparison tool is visual assistance,
not a numerical proof.

Read [references/drawing-reconstruction.md](references/drawing-reconstruction.md).

## 6. Modify existing models

First classify the model from evidence; do not assume that an imported/static
B-rep has a semantic owner merely because it is open in FreeCAD.

### Local edit feedback pattern (OBSERVE → EDIT → RE-OBSERVE → RESTORE/REWORK)

Apply this pattern to every local geometry edit: holes and bores, bosses, pocket
or slot walls, pads, ribs, lugs, flanges, nozzles, local thickness changes, and
direct face moves. A selected face is only the edit handle, not the complete
feature.

1. **OBSERVE before editing.** Resolve the target face(s) with
   `select_subshapes`, then call `inspect_subshape_neighborhood` for at least one
   face-adjacency hop. Continue outward until the feature boundary, attachment
   to the parent body, and transition chain are explicit. Record affected and
   invariant faces, dimensions, surface/curve types, continuity, connectivity,
   solid count, validity, and local section/screenshot evidence when useful.
2. **EDIT the semantic owner.** For native history, change the earliest
   parameter, constraint, sketch, or feature that owns the intent. For static
   B-reps, apply the smallest supported local surgery that preserves the
   observed attachment and transition chain.
3. **RE-OBSERVE after recompute.** Reselect transient `FaceN` references and
   repeat the same neighborhood walk, measurements, local section/view, and
   validity checks. Compare the new neighborhood with the baseline: the
   requested boundary may change; unaffected faces, functional interfaces,
   attachment, continuity, transitions, and solid topology must not.
4. **RESTORE or REWORK on collateral damage.** If a chamfer, fillet, blend,
   tangent face, wall, support, interface, or unrelated local region disappears,
   disconnects, changes unintentionally, or becomes sharp/invalid, do not accept
   the edit. Undo/abort the causal operation or reconstruct the original design
   intent, then repeat the loop before continuing.

For imported STEP/static B-reps this pattern is mandatory and stricter: capture
a shape checkpoint immediately before mutation and compare it afterwards.
Whole-model volume and bounds do not replace neighborhood comparison; verify
both the changed region and nearby regions expected to remain unchanged.

### Native editable history

1. Inspect the current document, Body history, Tip, sketches, constraints,
   expressions, dependencies, visibility, and baseline dimensions.
2. Change the earliest parameter, constraint, sketch, or feature that
   semantically owns the requested change.
3. Avoid appending compensating geometry or creating a replacement Body merely
   to hide a failed edit.
4. Recompute and inspect downstream features after every upstream change.

### Imported or static B-rep

1. Identify the target feature and the boundary whose motion expresses the
   requested change. Inspect adjacent walls, fillets, chamfers, blends, tangent
   faces, and the attachment to the parent solid.
2. Record invariants: functional/interface geometry, solid count, validity,
   volume expectations, bounds that must stay fixed, and unaffected local regions.
3. Call `capture_shape_checkpoint` before mutation. Placement is part of the
   checkpoint; do not substitute a visually similar origin-normalized shape.
4. Use a supported direct edit. For planar push-pull on a recognized local
   feature, prefer `move_faces(method="feature_rebuild")` and supply
   `feature_face_names` when automatic boundary discovery is ambiguous. Inspect
   `performed_method`; do not describe `prism_boolean_fallback` as Move Face.
5. If no supported direct edit preserves the feature, use controlled local B-rep
   surgery: isolate the feature/material or void, preserve or reconstruct its
   transition chain, apply the smallest edit, and validate one solid. Do not
   silently replace a blend-bearing feature with a sharp prism.
6. Call `compare_shape_checkpoint`, using exact localization when complexity and
   timeout allow. Verify both the changed region and unchanged local/invariant
   regions; whole-model volume and bounds alone are insufficient.

For both branches, treat existing functional features and interfaces as
invariants unless the change request explicitly targets them.

### Preserve functional geometry when choosing what to move

When a requested dimension can be achieved by modifying either of two
boundaries, do not choose the boundary only from geometric convenience.

1. Identify the surfaces/features that define the current dimension.
2. Classify each side as a functional/interface feature or as ordinary
   structural/envelope geometry.
3. Preserve functional geometry unless the request explicitly requires changing
   it. Functional geometry includes threads, fits, bearing or seal seats, mating
   faces, hole axes/diameters, splines/teeth, and other interfaces to another
   component.
4. Prefer changing the less functionally constrained boundary and make the
   smallest semantic change to the existing model.
5. Do not destroy and reconstruct a complex accepted feature merely because
   rebuilding it makes the requested numeric dimension easier to obtain.

Example: if the wall around an existing threaded bore must increase from
10 mm to 15 mm and the thread itself is not requested to change, preserve the
thread geometry and increase the outer boss diameter/radius. Do not fill the
existing thread and cut a smaller replacement thread.

### Preserve feature attachment and transition geometry

When modifying an existing local feature such as a boss, lug, rib, flange,
pad, pocket, or nozzle, do not treat the bounds of one selected face as the
bounds of the whole feature.

Before editing:

1. Inspect the faces adjacent to the primary target face and follow the
   attachment side at least one topology hop toward the parent body.

2. Identify transition geometry connecting the feature to its parent,
   including fillets, chamfers, blends, lofted/BSpline transitions, tangent
   faces, and intersecting support surfaces.

3. Treat those transition faces as part of the feature's design intent.
   If the primary feature dimension changes, preserve or reconstruct the
   original transition type and dimensions unless the request explicitly
   changes them.

4. For an additive enlargement, do not stop new material at the trimmed
   boundary of the original analytical face when that face terminates in a
   blend or other transition. Extend the primary geometry until it intersects
   the parent/support geometry, then recreate the required transition.

5. Do not introduce a new sharp junction where the original feature joined
   its parent through a fillet, chamfer, tangent blend, or smooth transition.

6. Verify the edited attachment with local topology and a section through the
   feature axis. Check that the feature reaches the parent body and that the
   expected transition/continuity is present.

## 7. Validate during work without over-constraining the workflow

After a major feature or any suspicious result, use the smallest relevant check:

- compact `get_sketch_info()` for solver/profile state and counts;
- `validate_object` for one feature;
- `validate_document` for overall geometric health;
- compact `inspect_object()` for identity, relationships, bounds, volume, and
  topology counts; use `detail_level="shape"` when only shape metrics are
  needed, paged `"topology"` only for face/edge evidence, and `"full"` only for
  an identified property-level diagnosis;
- `select_subshapes` before face-supported sketches and topology-sensitive
  Fillet, Chamfer, Draft, or Thickness operations. Express intent through
  surface/curve type, normal/direction, size, adjacency, convexity, and location;
  do not manually enumerate every `FaceN`/`EdgeN` unless the selector cannot
  represent a genuinely necessary criterion. Its default returns references;
  request paged `summary` evidence for ambiguous candidates and `full` only for
  a focused diagnosis. `centroid_bounds` is a surface-area centroid for faces
  and curve-length centroid for edges, in global coordinates;
- feature responses for `base_volume`, `result_volume`, retained/change ratios, and resolved Body Tip/base;
- screenshots/crops for visual correspondence;
- `evaluate_model_checkpoint` only when a formal discrepancy ledger is useful.

Do not continue blindly after an invalid shape, implausible before/after volume ratio, ineffective cut, wrong Body Tip, unexpected solid count, disconnected additive feature, or clearly wrong view.
Undo or repair the most recent causal feature rather than rebuilding in a new
hidden document.

### Pattern reliability

Use `linear_pattern` and `polar_pattern` only on a non-pattern seed. Before any
linear, polar, mirrored, or multi-transform pattern, compare the single seed
feature against the corresponding source view with `compare_images`. Do not
pattern a seed that is merely plausible: patterning multiplies its dimensional,
placement, and orientation errors. For combined linear and polar repetition,
use `multi_transform_pattern`; do not chain a Pattern feature directly into
another Pattern. After every pattern, require successful
`material_change_diagnostics`, then verify Shape, Body Tip, one-solid topology,
before/after volume evidence, and instance layout in an equivalent view.
The diagnostic may use `add_subshape` or the `result_shape_difference` fallback
when a valid FreeCAD pattern does not expose `AddSubShape`.

### Sketch arc construction

Construct manufactured profiles from their straight parents first, then insert
the stated tangent fillets/radii. `center_angles.start_angle` and `end_angle` are
degrees, but prefer a radius-defined mode when the drawing specifies endpoints
or adjoining elements rather than center angles.

Use `edit_sketch_geometry(..., operations=[...])` for both of these supported
radius-defined cases:

```text
# Arc through two endpoints with a known radius. arc_side selects which side
# of the directed chord x1,y1 -> x2,y2 contains the minor arc.
{"op":"add_arc", "arc_mode":"endpoints_radius",
 "x1":0, "y1":0, "x2":20, "y2":0, "radius":15,
 "arc_side":"left"}

# Tangent arc joining two existing line segments. The lines are trimmed by the
# native Sketcher fillet operation.
{"op":"add_arc", "arc_mode":"tangent_fillet",
 "line1_index":0, "line2_index":1, "radius":4}
```

For the second form, create/identify the two lines first and use their current
geometry indices. A radius that cannot fit the line geometry must be corrected,
not approximated with an unrelated free arc.

If a source-backed radius transition conflicts when `Tangent` is added, stop the
current feature group. Do not delete tangency to preserve the current arc
hypothesis. Reinspect the exact crop and revise endpoints, radius, arc side,
datum, or dimension-chain interpretation; rebuild the transition and repeat the
checkpoint before adding later geometry.

Call `add_bspline` only when the source explicitly defines the curve by points,
knots, or equivalent tabulated free-form data. Never substitute a B-spline for a
line, circular arc, conic, unreadable boundary, or stated fillet radius.

## 8. Completion criteria

Before reporting completion:

- recompute the intended document;
- save it to the requested path;
- confirm the intended Body Tip and solid count;
- confirm no over-constrained, conflicting, redundant, or solver-error sketches;
- explain any remaining under-constrained sketches and why they are acceptable;
- hide or remove temporary construction solids;
- for drawing/image input, reproduce and compare every source-view manifest
  record one-to-one against the final model, including sections/details and
  opposite-side views;
- confirm that the dimension manifest contains every source dimension. Pass
  the complete source acceptance manifest to
  `validate_parametric_model(acceptance_manifest={...})`; require every driving
  and verification record to be verified with same-view semantic measured
  evidence, every source-view comparison image to be inspected, and every
  exceptional `source_issue` to contain concrete evidence; for a
  sketch-only
  deliverable also pass `target={"kind":"sketch","name":...}`;
- inspect each Spreadsheet alias: determine why it exists, connect it to the
  feature tree if required, or delete it if redundant;
- treat 0 DoF as necessary solver evidence only: also verify outer/hole nesting,
  contour intersections, drawing correspondence, datum chains, and the semantic
  constraint pattern;
- call `validate_parametric_model` and report its findings accurately. Do not
  finish while it reports missing/unlinked required dimensions or unused
  Spreadsheet parameters.
- Never bulk-delete or recreate an already accepted sketch constraint graph
  solely to turn a validator status green. Diagnose the existing dependency
  path and change the semantic owner only when the model itself is wrong. If
  geometry is accepted but tracing remains uncertain, preserve it and report the
  validator limitation instead of optimizing the model for the metric.

Call the validator with its compact default first. Use `detail_level="structure"`
only for a reported Body/sketch/Spreadsheet problem. Use `detail_level="full"`
(and `include_sketch_constraints=True`, if needed) only after a compact result
identifies a specific history, dependency, expression, or solver-index question.
Full reports contain entire feature history, expressions, cells, and constraint
records and can consume tens of thousands of tokens on complex documents.

A required dimension is satisfied only when it has a verified path to the
active validation target. In model scope that target is the final solid; in
sketch scope it is non-construction geometry of the named sketch. Never add fake geometry,
construction points, dummy constraints, inactive helper sketches,
zero-multiplied expressions, metadata-only links, or no-op features merely to
make an identifier appear used. Fix the real semantic dependency or report the
limitation honestly.

See [references/validation-and-editability.md](references/validation-and-editability.md)
for interpretation details and [references/source-notes.md](references/source-notes.md)
for the engineering/documentation basis used by this skill.
