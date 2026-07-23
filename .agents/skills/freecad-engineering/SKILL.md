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
- a valid Body Tip and no accidental visible helper solids.

`execute_python`, `safe_execute`, and `run_macro` are always available. They may
create or edit the model, but they do not waive the requirements above. Python
used for production geometry should create native FreeCAD document objects and
editable history rather than only assigning a final `Shape` to `Part::Feature`.

## Mandatory final inspection

After any task that creates or changes model geometry, call:

```text
validate_parametric_model(doc_name=<intended document>)
```

Do this immediately before the final user-facing response. Summarize:

1. document and Body names;
2. Body and Tip validity;
3. ordered feature history;
4. sketch solver/profile status, especially under-, over-, redundant, or
   conflicting constraints;
5. solids outside Bodies and other significant findings;
6. limitations that still require visual or dimensional verification.

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
- Avoid broad `Fix` constraints as a substitute for design intent.
- Driving sketches should normally be fully constrained before completion.
  Intermediate under-constrained sketches are acceptable only while actively
  being developed. Over-constrained, conflicting, redundant, or solver-error
  states must be corrected.

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
- Add connected flanges/tabs and bends while preserving one continuous body and
  constant nominal thickness. Verify overlap, gaps, and bend direction after
  every major flange.
- A bend deforms material around a neutral axis; do **not** generically simulate
  it by adding volume on one side and subtracting an equal volume on the other.
  Use sheet-metal/bend features when available. If they are unavailable, use a
  documented constant-thickness approximation and do not claim a reliable flat
  pattern.
- Bend allowance, bend deduction, K-factor, inside radius, and thickness control
  the developed blank. Use explicit drawing/manufacturing data when supplied;
  do not invent production values.
- Beads, dimples, louvers, embossed ribs, and other formed details require local
  thickness continuity. Simple additive/subtractive approximations are allowed
  only when they preserve the intended outer/inner surfaces sufficiently for the
  task and are clearly reported as approximations.

## 5. Reconstruct from drawings or images

- Open the whole sheet first to identify views, sections, details, dimensions,
  notes, and scale relationships.
- Use `open_image_tiles` or focused crops when dimensions/features are too small
  in the full sheet. Upscaling improves presentation to the VLM but does not
  restore detail absent from the source pixels.
- Build an evidence table: feature, value/count, source view, explicit/derived/
  assumed status, and confidence.
- Compare equivalent views: front-to-front, top-to-top, section-to-section.
- Resolve ambiguity autonomously by choosing the interpretation most consistent
  across all views. Record assumptions and alternatives; revise them when later
  evidence conflicts.
- Use screenshots and `compare_images` at high-risk transitions or after major
  features. The comparison tool is visual assistance, not a numerical proof.

Read [references/drawing-reconstruction.md](references/drawing-reconstruction.md).

## 6. Modify existing models

- Inspect the current document, Body history, Tip, sketches, constraints,
  expressions, dependencies, visibility, and baseline dimensions before editing.
- Change the earliest parameter, constraint, sketch, or feature that semantically
  owns the requested change.
- Avoid appending compensating geometry or creating a replacement Body merely to
  hide a failed edit.
- Recompute and inspect downstream features after every upstream change.
- Preserve unrelated dimensions and functional interfaces.

## 7. Validate during work without over-constraining the workflow

After a major feature or any suspicious result, use the smallest relevant check:

- `get_sketch_info` for solver/profile state;
- `validate_object` for one feature;
- `validate_document` for overall geometric health;
- `inspect_object` for placement, bounds, volume, expressions, and dependencies;
- screenshots/crops for visual correspondence;
- `evaluate_model_checkpoint` only when a formal discrepancy ledger is useful.

Do not continue blindly after an invalid shape, ineffective cut, wrong Body Tip,
unexpected solid count, disconnected additive feature, or clearly wrong view.
Undo or repair the most recent causal feature rather than rebuilding in a new
hidden document.

## 8. Completion criteria

Before reporting completion:

- recompute the intended document;
- save it to the requested path;
- confirm the intended Body Tip and solid count;
- confirm no over-constrained, conflicting, redundant, or solver-error sketches;
- explain any remaining under-constrained sketches and why they are acceptable;
- hide or remove temporary construction solids;
- inspect the final model from the required views;
- call `validate_parametric_model` and report its findings accurately.

See [references/validation-and-editability.md](references/validation-and-editability.md)
for interpretation details and [references/source-notes.md](references/source-notes.md)
for the engineering/documentation basis used by this skill.
