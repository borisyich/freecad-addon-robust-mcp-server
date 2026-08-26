# Model or reconstruct a part from a technical drawing

Use this workflow when geometry must be inferred from orthographic, sectional,
isometric, detail, or flat-pattern views.

## Goal

Reconstruct one coherent 3D part from drawing evidence. A valid solid is not
enough; the model must agree with dimensions, view relationships, sections, and
feature counts.

## 1. Read the drawing before modeling

Identify:

- units and scale;
- projection convention when shown;
- front, top/plan, left/right side, section, detail, isometric, and flat-pattern
  views;
- centerlines, hidden lines, section hatching, symmetry, and repeated-feature
  notes;
- all explicit dimensions that affect the requested geometry.

Printed dimension values are authoritative. Do not infer a real dimension from
pixel length when a dimension callout exists, and do not multiply a printed
value by the drawing scale.

## 2. Establish the view ↔ model-axis contract

Before building, write down which model axes each drawing view represents.

Default FreeCAD orthographic contract used by this project:

| Drawing/FreeCAD view | Screen plane | Viewing normal |
|---|---|---|
| Front/Rear | XZ | +Y / -Y |
| Top/Bottom | XY | +Z / -Z |
| Left/Right | YZ | +X / -X |

The exact sign depends on the chosen camera direction; the important point is to
keep one consistent world-axis mapping for the entire reconstruction.

Use this map to choose sketch planes and feature directions. Never choose a
sketch plane merely because the current screenshot looks similar to a drawing
view.

### Circle/axis rule

A circular feature appears circular only when viewed approximately along its
axis. Use that fact with the matching side view/hidden lines to infer bore or
boss direction.

## 3. Build a source-dimension ledger

Give every explicit non-reference drawing dimension a stable identifier. Mark it
as:

- **driving** — implemented by a constraint/property/expression that controls
  final geometry;
- **verification** — not a convenient driver, but must be measured on the final
  model;
- **unresolved** — cannot yet be reconciled with the available views.

Do not satisfy the validator by adding disconnected Spreadsheet values. A
source dimension is driving only when it actually influences final geometry.

## 4. Reconcile views before choosing the base strategy

For each major feature, cross-check at least two independent sources when
available:

- silhouette in one view + depth in another;
- circular callout + hidden lines/section;
- section hatching + exterior view;
- repeated-feature note + visible instance count.

Section views override tempting but incorrect silhouette interpretations. If a
section shows material remaining, do not create a through void merely because an
external view looks open.

## 5. Model the dominant form first

Classify the body family before details: prismatic, revolved, cored housing,
spoked/ribbed, thin-walled, sheet metal, lofted/freeform, or hybrid.

After the first valid dominant-form candidate:

1. render the principal views that correspond to the drawing;
2. identify the largest semantic mismatch;
3. if the mismatch is body-family level, rebuild the base strategy from the
   dimension ledger;
4. do not repair a wrong primary representation with cosmetic cuts/fillets.

## 6. Drawing reconstruction feedback loop

After each major feature or coherent feature group:

1. recompute and inspect deterministic geometry evidence;
2. set the corresponding FreeCAD view;
3. capture/open the model image;
4. use `compare_images` against the relevant source view when a direct visual
   comparison is possible;
5. if one view is ambiguous, compare the other available principal views before
   accepting the feature.

A generated screenshot without comparison is not a completed visual checkpoint.

For patterns, compare one seed feature before patterning. Then verify final
count, spacing/angle, and that instances did not merge unintentionally.

## 7. Flat patterns

A flat pattern is manufacturing evidence, not another orthographic projection.
If the drawing contains a developed blank, route additionally to
`sheet-metal-parts.md`. Keep flat dimensions and formed dimensions in separate
reasoning domains and reconcile them through the bend model.

## 8. Ambiguity policy

Resolve low-risk ambiguity by the interpretation that best satisfies all views,
dimensions, symmetry, and manufacturing logic. Record the assumption.

If the drawing remains materially underdetermined after cross-view checking,
use the best-supported reversible assumption and record confidence when useful work
can continue. Request clarification only for conflicting/unknown critical dimensions
that prevent a meaningful reconstruction.

## Completion checks

- Every principal view is mapped to consistent model axes.
- Every explicit source dimension is driving, verification, or unresolved.
- Every driving ID truly influences the model.
- Every verification dimension has measured pass/fail evidence.
- Major silhouettes, sections, feature counts, and orientations agree with the
  source.
- `validate_parametric_model(required_dimension_names=[...])` is run with the
  complete driving-ID list.
