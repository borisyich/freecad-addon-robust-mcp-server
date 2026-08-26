# Edit a part with construction history

Use this workflow when the FreeCAD document contains editable sketches,
PartDesign features, Spreadsheet expressions, datums, and a meaningful feature
tree.

## Goal

Change the design at the earliest correct source in its history and let FreeCAD
recompute downstream geometry. Preserve design intent and existing dependencies.

## 1. Inspect the feature tree first

Before changing geometry, identify:

- intended document and Body;
- current Body Tip;
- ordered feature history;
- sketches, supports, constraints, and expressions;
- Spreadsheet aliases used by the affected features;
- downstream features that depend on the candidate edit point.

The visible face is usually the result, not necessarily the correct place to
edit.

## 2. Find the causal parameter/feature

Prefer edits in this order:

1. existing named Spreadsheet parameter/expression;
2. existing sketch dimension/constraint;
3. existing semantic feature property (Pad length, Pocket depth, Hole diameter,
   pattern count/spacing, fillet radius, etc.);
4. sketch geometry when the profile itself must change;
5. feature replacement/reconstruction when the existing feature cannot express
   the request.

Use direct B-rep surgery only when native history cannot represent the requested
change or the history is already effectively broken. If you do, report the loss
of parametric design intent.

## 3. Make one source edit at a time

After each source edit:

- recompute;
- inspect FreeCAD errors;
- confirm the Body Tip and downstream features remain valid;
- check the affected sketch solver/profile state when a sketch changed;
- measure the requested result at final geometry, not only the parameter value.

A property accepting a new value does not prove the final shape changed as
intended.

## 4. Preserve dependency semantics

- Do not replace a driven dimension with a disconnected numeric copy.
- Keep existing expressions unless the change explicitly alters the dependency.
- When adding a new reusable dimension, bind it through a named sketch
  constraint or Spreadsheet alias and verify that the expression reaches the
  feature tree.
- Avoid attaching new sketches to unstable generated faces when an origin/datum
  plane can express the same intent.
- Do not change Body Tip manually unless history repair genuinely requires it.

## 5. Patterns and repeated features

Edit the seed or source dimensions first. Verify the seed, then the resulting
pattern count/spacing. If the requested change applies to every instance, do not
individually edit generated pattern faces unless history provides no alternative.

## 6. Recovery

If a source edit invalidates downstream history:

1. inspect the first failing downstream feature;
2. determine whether the failure is a dependency/topology-reference problem or
   a genuinely impossible geometry;
3. undo/rework the causal edit or repair the affected support/reference;
4. avoid deleting and recreating unrelated later features.

## Completion checks

- The requested change is encoded in the existing design history at the correct
  causal level.
- Downstream features recompute successfully.
- Sketches remain solvable and profiles remain valid.
- Spreadsheet aliases/expressions used by the edit are connected to final
  geometry.
- Final dimensions are measured on the resulting shape.
- `validate_parametric_model` confirms the intended Body/Tip/history state or
  its significant warnings are explained.
