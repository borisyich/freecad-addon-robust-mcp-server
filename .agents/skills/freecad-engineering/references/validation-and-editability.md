# Validation and editability

## Three separate questions

Do not conflate these checks:

1. **Geometric health:** Is the OpenCASCADE shape valid, recomputed, and the
   expected number of solids?
2. **Parametric/editable structure:** Are Bodies, Tips, sketches, constraints,
   expressions, and semantic features present and coherent?
3. **Requirement correspondence:** Does the model match the drawing/request?

`validate_parametric_model` addresses mainly the first two. It does not prove the
third.

## Interpreting sketch status

- `fully_constrained`: preferred final state for driving sketches;
- `under_constrained`: structurally valid but still movable; inspect remaining
  DoF and unconstrained geometry;
- `redundant`: remove unnecessary constraint before adding more;
- `conflicting` or `over_constrained`: repair before relying on downstream
  features;
- `solver_error`: undo/rework the latest sketch change;
- `profile=open`: acceptable for paths, but not for Pad/Pocket profile operations;
- `profile=closed`: suitable for profile operations when solver state is healthy;
- `profile=invalid`: inspect self-intersections, duplicate/zero-length geometry,
  and overlapping edges.

## Interpreting Body and Tip findings

Review when:

- a Body has no Tip;
- Tip is outside Body history;
- Tip is not the latest intended shape-bearing feature;
- Body shape is invalid or contains an unexpected number of solids;
- a valid solid exists outside all Bodies and may be replacing editable history;
- a Body contains no sketches even though the requested result was parametric.

Not every warning is an error. Imported references, master geometry, or deliberate
construction solids may exist outside the main Body. They should be named,
hidden when appropriate, and explained.

## Final report pattern

Report the validator output in engineering terms:

```text
Document: Bracket.FCStd
Body: BracketBody — valid; Tip=Fillet002 — valid
History: BaseSketch → Pad → Pocket → HolePattern → Fillet002
Sketches: 4 total; 3 fully constrained; 1 under-constrained (2 DoF)
Outside solids: none
Action: model is geometrically healthy; constrain SK_HolePattern before treating
it as fully production-ready.
```
