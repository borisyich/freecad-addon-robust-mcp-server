---
name: freecad-engineering
description: >
  Route FreeCAD engineering work to the correct workflow for creating parts
  from text or drawings, modeling machined/additive or sheet-metal parts,
  editing models with or without history, and validating drawing correspondence
  and editable design intent. Do not use for MCP-server code work that does not
  create, inspect, change, or document a mechanical model.
---

# FreeCAD engineering router

This file is the router and the common engineering contract. Do not load every
reference. Select only the reference files required by the task.

## 1. Route the task

Classify the requested work before changing the model.

| Task | Read |
|---|---|
| Create a model from textual requirements | `references/model-from-text.md` |
| Create/reconstruct a model from a drawing or reference image | `references/model-from-drawing.md` |
| Create a part made mainly by machining/material removal or additive manufacturing | `references/machined-and-additive-parts.md` |
| Create a bent/formed sheet-metal part | `references/sheet-metal-parts.md` |
| Modify an imported/static model without editable feature history | `references/edit-without-history.md` |
| Modify a model with native editable history | `references/edit-with-history.md` |
| Develop an engineering drawing from a 3D model | `references/engineering-drawings.md` |

Creation routes are composable, not mutually exclusive. For example:

- drawing + machined part → read `model-from-drawing.md` and
  `machined-and-additive-parts.md`;
- drawing + bent sheet part → read `model-from-drawing.md` and
  `sheet-metal-parts.md`;
- textual sheet-metal request → read `model-from-text.md` and
  `sheet-metal-parts.md`.

Do not load a manufacturing reference until the dominant manufacturing family
has been identified.

## 2. Keep an explicit task record

Do not use conversation memory as the only record of a drawing, specification,
or accepted model state. Before geometry work, create a compact task record in
the working notes and keep it current. Its exact format is flexible, but it must
make these items recoverable without reinterpreting the whole task:

- requirements or source dimensions, with stable IDs and their evidence;
- the view/datum/axis contract when images or drawings are involved;
- planned semantic features and their parent/operation order;
- assumptions, conflicts, and protected invariants;
- accepted checkpoints and the next unresolved item.

The selected reference defines the task-specific record. Update the record when
an observation changes the interpretation. Do not preserve a rejected hypothesis
by silently changing or dropping source evidence.

## 3. Common engineering loop

Use **ACT → OBSERVE → REACT** throughout geometry work.

### ACT

Make one logically reviewable change: a base feature, one cut, one bend, one
pattern seed, one history edit, or one local B-rep edit. Before the change, state
which requirement/feature IDs it implements and the expected observable result.
Recompute the document.

### OBSERVE

Verify the result with the cheapest deterministic evidence first:

1. operation/tool result and FreeCAD errors;
2. recompute and shape validity;
3. dimensions, topology, solid count, Body Tip, sketch state, or before/after
   shape delta appropriate to the operation;
4. visual evidence when shape, orientation, topology, or correspondence to a
   drawing cannot be established numerically.

A screenshot by itself is not verification. State what was expected, what was
observed, and which requirement/feature IDs the evidence covers. For drawing
work, reopen the relevant source crop at the checkpoint; do not compare the
candidate only with a remembered impression of the drawing.

### REACT

- **continue** when the result satisfies the current requirement;
- **rework** when the result is invalid, ineffective, disconnected, wrongly
  oriented, dimensionally wrong, topologically wrong, or inconsistent with the
  source.

Correct or undo the causal feature. Do not hide a wrong dominant form under
later fillets, cuts, helper solids, or cosmetic patches.

Record the checkpoint as accepted or rejected. Do not build downstream features
on an unresolved major discrepancy.

## 4. Use the tool surface selectively

The server has a large tool surface. Discover or inspect only the exact tool
needed for the next operation; do not load every schema or generic guide.

- source images: `open_image`, `open_image_tiles`, `compare_images`;
- reproducible views: `get_screenshot`, `set_view_angle`,
  `set_camera_position`, `get_camera_state`;
- geometry evidence: `inspect_object`, `select_subshapes`,
  `inspect_subshape_neighborhood`, and the specific measurement tools;
- local deltas: `capture_shape_checkpoint`, `compare_shape_checkpoint`;
- model gates: `validate_object`, `validate_document`,
  `validate_parametric_model`.

Use `execute_python`, `safe_execute`, or a macro when the typed tools cannot
express a necessary operation. The fallback changes the implementation method,
not the required model structure or verification evidence.

## 5. Modeling principles shared by all routes

- Reuse the intended document. Do not create duplicate documents to escape a
  failed step.
- Prefer standard MCP tools and native FreeCAD objects. `execute_python`,
  `safe_execute`, and macros remain valid escape hatches when the tool surface
  is insufficient; using them does not make a fragile final model acceptable.
- For new parametric parts, prefer one intended `PartDesign::Body` per physical
  part, native sketches/constraints, semantic PartDesign features, and a valid
  Tip. Multiple Bodies are appropriate only when there are genuinely separate
  parts or the construction requires them.
- Choose origin planes, datums, and symmetry from the part's functional geometry
  and manufacturing logic, not from the current camera angle.
- Express design intent with relationships and named dimensions. Avoid magic
  coordinates when a dimension, symmetry, equality, tangent relation, datum, or
  Spreadsheet expression can express the same intent.
- Do not confuse `fully constrained` with `correct`. Solver status proves only
  that the sketch has no remaining degrees of freedom.
- Use semantic subshape selection (`select_subshapes` and neighborhood
  inspection) for topology-sensitive work instead of guessing `FaceN`/`EdgeN`
  from visual order.
- Preserve exact CAD/B-rep geometry when it exists. Do not replace analytic or
  NURBS surfaces with tessellated/faceted approximations merely to make an
  operation easier; use mesh-like approximation only when the source itself is
  mesh-derived or the user explicitly accepts approximation.
- Separate the dominant form, functional interfaces, repeated features, and
  finishing details in the feature plan. Validate the dominant form before
  spending effort on small radii or cosmetic detail.
- Build and verify one repeated-feature seed before patterning it.
- Apply finishing features such as small fillets/chamfers after the dominant
  mass, cavities, interfaces, and repeated features are correct unless an
  earlier radius is required by construction.
- When source evidence is incomplete but the missing value is not critical,
  choose the most consistent, reversible engineering assumption and record it.
  Request clarification only when no meaningful implementation can proceed without
  choosing among materially different functional outcomes.

## 6. Editability depends on the task

Do not impose one representation on every workflow.

- **Create from scratch / edit with history:** preserve editable design intent
  whenever practical.
- **Edit without history:** a local direct B-rep edit is often the correct
  representation. Do not rebuild an imported STEP into fake parametric history
  unless the user explicitly asks for reconstruction.
- **Disposable/interchange geometry:** direct solids are acceptable when the
  user explicitly requests them and editability is not a requirement.

## 7. Keep three acceptance questions separate

Do not treat one successful check as proof of all three:

1. **Geometric health:** is the recomputed result a valid shape with the intended
   number of solids?
2. **Editable structure:** do Body, Tip, sketches, constraints, expressions, and
   semantic features represent the intended design where editability is required?
3. **Requirement correspondence:** do measured dimensions, feature counts,
   sections, interfaces, and drawing views match the actual request/source?

`validate_parametric_model` mainly addresses the first two. It cannot discover
an omitted source dimension or prove that a visually plausible model matches a
drawing.

## 8. Final gate

Immediately before the final response after any geometry change:

1. recompute the intended document;
2. run the task-specific checks from the selected reference file(s);
3. call `validate_parametric_model` for native/parametric model structure;
4. for direct/imported B-rep edits, also compare the final object against the
   pre-edit shape checkpoint when one was captured;
5. reconcile every task-record item as passed, unresolved, or explicitly
   out-of-scope; do not leave silent omissions;
6. save the intended document when the task requires a persistent result;
7. when STEP/BREP interchange is the deliverable, validate the written artifact
   (or re-import it into a separate verification document) rather than assuming
   an in-memory valid shape survived export unchanged.

For drawing reconstruction, pass all implemented driving source-dimension IDs
as `required_dimension_names`; verification-only dimensions must be measured
separately against the solved model. Run the final `compare_images` against the
current document state after the last geometry change and pass `doc_name` so the
comparison is bound to that geometry signature; a comparison made before a later
edit is stale evidence.

Report significant warnings and unresolved assumptions. Do not claim success
from shape validity alone.
