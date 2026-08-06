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

Fix/Block constraints are not a substitute for design intent. Their count may
not exceed 50% of sketch geometry; use geometric or dimensional constraints, or
remove existing fixes.

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

## Valid Shape is not sufficient evidence

A feature can expose one valid OpenCASCADE solid and still remove or add the wrong amount of material. For Pocket and helix operations, compare the reported `base_volume`, `result_volume`, absolute change, and retained/change ratios with the expected feature. Pattern tools additionally return `material_change_diagnostics`. It compares the transformed `AddSubShape` with the actual Body delta when available, and otherwise uses the B-rep set difference between base and result (`method=result_shape_difference`). This fallback is required for valid FreeCAD patterns that do not publish `AddSubShape`. An inconsistent result is rolled back. The remaining ratios are diagnostic evidence, not a universal numeric threshold.

Datum planes, lines, points, and coordinate systems are reference geometry. Their synthetic or infinite Shape bounds/volume are not meaningful solid metrics and must not be interpreted as model dimensions.

## Repeated and combined transformations

Use `linear_pattern` or `polar_pattern` only for one transformation of a non-pattern seed. Do not apply one pattern directly to another. Use `multi_transform_pattern` with the original seed and ordered linear/polar stages, then verify Shape, Body Tip, solid count, volume change, and the expected instance layout.

For drawing reconstruction, accept the single seed with `compare_images` before
creating the pattern.

## Source dimensions and Spreadsheet cleanliness

For drawing/sketch input, call the final validator with the complete saved list
of non-starred source-dimension identifiers. Each identifier must be used by a
named driving sketch constraint or by a Spreadsheet alias that connects directly
or transitively to an expression that influences the active final solid. A link
to construction-only geometry, an inactive sketch, a datum/helper object, or
metadata is not sufficient.

Do not add construction points or other non-profile geometry solely to bind
otherwise unused aliases. Such a model may look structurally connected while
the final B-rep is invariant under those parameters. The validator reports this
case as `defined_but_not_solid_driving`; treat it as an error in requirement
correspondence.

Use the validator's compact default first. Request `structure` only for a
reported structural problem and `full` only for a focused history/expression or
constraint diagnosis. Full reports can be extremely large.

Review every unused Spreadsheet alias before completion. Determine why it was
created; connect it to the tree when it represents required design intent, or
delete it when it is redundant. A final model is not clean while required
dimensions are missing/unlinked or Spreadsheet parameters remain orphaned.

For a sketch dimension, the dependency is attached to the constraint expression
path accepted by the tool as `Constraints[index]`; FreeCAD may later report a
canonical named path. Create the dimensional constraint with an
initial numeric value, then set its expression to `SpreadsheetName.Alias`; use
`get_sketch_info` to verify that the same path appears in `expressions` and on
the corresponding constraint record. Constraint names improve readability but
are not the linkage mechanism.

## Final report pattern

Report the validator output in engineering terms:

```text
Document: Bracket.FCStd
Body: BracketBody — valid; Tip=Fillet002 — valid
History: BaseSketch → Pad → Pocket → HolePattern → Fillet002
Sketches: 4 total; 3 fully constrained; 1 under-constrained (2 DoF)
Source dimensions: 18/18 used
Spreadsheet: 7 aliases; all connected to feature history
Outside solids: none
Action: model is geometrically healthy; constrain SK_HolePattern before treating
it as fully production-ready.
```
