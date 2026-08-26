---
name: freecad-engineering
description: >
  Route FreeCAD engineering work to the correct workflow for creating parts
  from text or drawings, modeling machined/additive or sheet-metal parts,
  editing models with or without history, with a reserved engineering-drawing route.
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

## 2. Common engineering loop

Use **ACT → OBSERVE → REACT** throughout geometry work.

### ACT

Make one logically reviewable change: a base feature, one cut, one bend, one
pattern seed, one history edit, or one local B-rep edit. Recompute the document.

### OBSERVE

Verify the result with the cheapest deterministic evidence first:

1. operation/tool result and FreeCAD errors;
2. recompute and shape validity;
3. dimensions, topology, solid count, Body Tip, sketch state, or before/after
   shape delta appropriate to the operation;
4. visual evidence when shape, orientation, topology, or correspondence to a
   drawing cannot be established numerically.

A screenshot by itself is not verification. State what was expected and what
was observed.

### REACT

- **continue** when the result satisfies the current requirement;
- **rework** when the result is invalid, ineffective, disconnected, wrongly
  oriented, dimensionally wrong, topologically wrong, or inconsistent with the
  source.

Correct or undo the causal feature. Do not hide a wrong dominant form under
later fillets, cuts, helper solids, or cosmetic patches.

## 3. Modeling principles shared by all routes

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
- Build and verify one repeated-feature seed before patterning it.
- Apply finishing features such as small fillets/chamfers after the dominant
  mass, cavities, interfaces, and repeated features are correct unless an
  earlier radius is required by construction.
- When source evidence is incomplete but the missing value is not critical,
  choose the most consistent, reversible engineering assumption and record it.
  Request clarification only when no meaningful implementation can proceed without
  choosing among materially different functional outcomes.

## 4. Editability depends on the task

Do not impose one representation on every workflow.

- **Create from scratch / edit with history:** preserve editable design intent
  whenever practical.
- **Edit without history:** a local direct B-rep edit is often the correct
  representation. Do not rebuild an imported STEP into fake parametric history
  unless the user explicitly asks for reconstruction.
- **Disposable/interchange geometry:** direct solids are acceptable when the
  user explicitly requests them and editability is not a requirement.

## 5. Final gate

Immediately before the final response after any geometry change:

1. recompute the intended document;
2. run the task-specific checks from the selected reference file(s);
3. call `validate_parametric_model` for native/parametric model structure;
4. for direct/imported B-rep edits, also compare the final object against the
   pre-edit shape checkpoint when one was captured;
5. save the intended document when the task requires a persistent result.

For drawing reconstruction, pass all implemented driving source-dimension IDs
as `required_dimension_names`; verification-only dimensions must be measured
separately against the solved model.

Report significant warnings and unresolved assumptions. Do not claim success
from shape validity alone.
