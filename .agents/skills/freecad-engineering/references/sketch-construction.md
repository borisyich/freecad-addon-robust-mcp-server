# Engineering sketch construction

## Purpose

Use this workflow when a drawing, flat pattern, marked-up image, or verbal
specification must become an editable Sketcher sketch. Treat solver status as
one diagnostic only: a fully constrained sketch can still have the wrong
topology, dimensions, datum interpretation, or design intent.

## Contents

- [Build a source-dimension manifest](#1-build-a-source-dimension-manifest)
- [Keep interpretation mutable](#2-keep-interpretation-mutable)
- [Gate flat-pattern feature groups](#3-gate-flat-pattern-feature-groups)
- [Express design intent with relationships](#4-express-design-intent-with-relationships)
- [Classify coordinate constraints](#5-classify-coordinate-constraints)
- [Treat tangency conflicts as interpretation failures](#6-treat-tangency-conflicts-as-interpretation-failures)
- [Construct arcs and fillets from source evidence](#7-construct-arcs-and-fillets-from-source-evidence)
- [Gate B-splines](#8-gate-b-splines)
- [Accept profile topology explicitly](#9-accept-profile-topology-explicitly)
- [Protect validation integrity](#10-protect-validation-integrity)
- [Finish with sketch-target validation](#11-finish-with-sketch-target-validation)

## 1. Build a source-dimension manifest

Before creating geometry, save every explicit source dimension. Preserve and
interpret drafting markers such as an asterisk, parentheses, `REF`, or `TYP`;
they do not make the dimension optional. Never omit a value because it appears
redundant or is inconvenient for the current hypothesis. Give each item a
stable ID, raw annotation, value, unit, source view/crop, and source location.

Classify its modeling role from drafting evidence and the dimension-chain plan:

- `driving`: an independent source dimension that should control geometry;
- `verification`: an explicit overall, repeated, reference, or check dimension
  that should verify the solved model without over-defining it;
- `source_issue`: exceptional terminal classification for a demonstrably
  defective source annotation, with concrete evidence and attempted
  interpretations recorded.

Do not use `unresolved`, `unknown`, or a similar terminal bucket. If the role or
semantic target is initially ambiguous, reinspect every applicable view/detail,
trace the dimension references, reconcile the dimension chain, and choose the
best-supported interpretation with confidence and rejected alternatives. Use
`source_issue` only when the source remains illegible at the best useful
resolution, has no identifiable extension/leader targets, is irreconcilably
contradictory with independent source dimensions beyond drafting tolerance, or
is demonstrably malformed/orphaned. A solver or CAD conflict is not enough.

Do not classify a dimension as `verification` merely because adding it creates a
solver conflict. A conflict makes the current interpretation suspect, not the
source requirement disposable. Reinspect the drawing and reconcile the
dimension chain first.

Use records similar to:

```json
{
  "id": "X_OVERALL_70",
  "value": 70.0,
  "unit": "mm",
  "role": "verification",
  "source_view_id": "V2",
  "source_references": ["LEFT_OUTER_EDGE", "RIGHT_OUTER_EDGE"],
  "target_elements": ["BODY.LEFT_OUTER_FACE", "BODY.RIGHT_OUTER_FACE"],
  "measurement_semantics": "projected_distance_x",
  "validation_view_id": "V2",
  "status": "pending"
}
```

```json
{
  "id": "HOLE_BOTTOM_Y_5_3",
  "value": 5.3,
  "unit": "mm",
  "role": "driving",
  "datum": "BOTTOM_EDGE",
  "target": "HOLE_BOTTOM.CENTER",
  "axis": "Y",
  "direction": "+Y",
  "source_view_id": "V2",
  "source_references": ["BOTTOM_EDGE", "HOLE_BOTTOM.CENTER"],
  "target_elements": ["BODY.BOTTOM_EDGE", "HOLE_BOTTOM.CENTER"],
  "measurement_semantics": "projected_distance_y",
  "validation_view_id": "V2"
}
```

For every ordinate or baseline dimension, preserve its datum/reference,
controlled axis, signed direction, target point/center/edge, and explicit or
derived status. A bare ordinate value is incomplete evidence. Do not translate
`35 mm from DATUM A` to global `X = 35 mm` unless the view map proves the datum,
origin, axis, and sign coincide.

Before translating an ordinate/baseline set, close at least one control chain
independently before using global coordinates:

```text
datum -> intermediate baseline/feature -> target -> overall/check dimension
```

If the signed chain does not close within the documented tolerance or drawing
precision, record `dimension_chain_mismatch`, reinspect the crop/view mapping,
and revise the interpretation. Do not average conflicting values.

Pass only all `driving` IDs to `required_dimension_names`. Independently check
every non-`source_issue` item, including driving items, by reproducing its
recorded source-view/section context and measuring between the same semantic
model elements with the same distance/radius/diameter/angle/thickness semantics.
Save observed value, tolerance, pass/fail, and tool evidence in the manifest or
discrepancy ledger. A FreeCAD reference constraint may display a solved value
but must not silently become a second driving constraint, and a driving
expression does not replace geometric measurement.

## 2. Keep interpretation mutable

Treat the evidence manifest and CAD model as two editable outputs of REACT:

```text
drawing -> interpretation/evidence manifest -> CAD -> observations
                ^                              |
                +---------- REACT -------------+
```

When an observation conflicts with the hypothesis, update the source-view map,
datum, sign, endpoint identity, radius, arc side, dimension role, or feature
mapping when evidence supports the change. Record the rejected interpretation
and reason. Do not preserve a weak interpretation by deleting source-backed CAD
relationships.

## 3. Gate flat-pattern feature groups

For a flat-pattern sketch, build and accept these groups in order:

1. coarse external contour using its straight parent segments;
2. stated radius transitions and trimmed corners;
3. holes and internal cutouts;
4. bend lines, normally as construction geometry unless the deliverable says
   they are cut/profile geometry;
5. final parameterization and remaining DoF removal.

Run a complete ACT -> OBSERVE -> REACT loop for each group. Do not create the
next group until the current checkpoint is accepted.

After each ACT, OBSERVE in this order:

1. recompute the FreeCAD document;
2. check solver health and the topology expected at this stage;
3. run deterministic dimension checks against the manifest;
4. perform same-view visual comparison with the source crop;
5. write or update the discrepancy ledger.

Use numerical evidence before visual judgment. After the coarse external
contour, call `measure_bounding_box` on the sketch and compare its X/Y extents
with overall verification dimensions. After holes, call
`get_sketch_info(detail_level="geometry")` and compare every circle center and
radius/diameter with its manifest records. Page through all geometry when
needed; do not verify only the first response page.

REACT with one of these outcomes:

- accept the group and continue;
- modify the CAD implementation;
- revise the interpretation/evidence manifest, then modify CAD;
- return to the relevant source crop because evidence conflicts or is
  incomplete.

Do not use 0 DoF as a group acceptance criterion. Apply final dimensional
constraints only after topology, deterministic dimensions, and visual
correspondence have passed. Reach 0 DoF near the end, then repeat all checks.

## 4. Express design intent with relationships

Prefer a compact graph that explains why geometry has its shape:

- endpoints meet through `Coincident`;
- edges remain axis-aligned through `Horizontal`/`Vertical`;
- a radius transition remains smooth through `Tangent`;
- repeated radii or lengths use `Equal` or one shared expression;
- circular size uses `Radius`/`Diameter`;
- location is measured from the correct datum with baseline/ordinate dimensions.

Place straight segments first and keep them approximate. Apply geometric relationships
before the smallest sufficient set of driving dimensions. Prefer horizontal or
vertical distances to a general distance when they express the same fact.

`fully_constrained` proves only that the solver reports no remaining motion. It
does not prove source correspondence, valid loop nesting, absence of contour
intersections, correct datums, or meaningful parameterization. When practical,
vary one major driving dimension reversibly and confirm the expected motion
without flips or topology failure.

## 5. Classify coordinate constraints

Absolute coordinates are legitimate for an ordinate drawing when they preserve
the drawing's datum. They are not legitimate merely because they eliminate DoF.
Classify every point-to-origin X/Y coordinate as:

- `source_backed`: directly maps to an explicit ordinate/baseline dimension;
- `derived`: follows from a recorded, checked dimension chain;
- `solver_lock`: has no independent source or derivation and exists only to
  remove motion.

For `source_backed`, record the source dimension ID and datum. For `derived`,
record the derivation and the control-chain check. For `solver_lock`, record why
the remaining motion could not be expressed by geometry, symmetry, or a
meaningful datum dimension. Minimize solver-lock coordinates; never multiply
them across most endpoints to chase 0 DoF.

Treat `coordinate_review_recommended` from `get_sketch_info` or final validation
as a mandatory provenance audit, not an automatic failure. The runtime can count
point-to-origin constraints but cannot infer their source classification.

## 6. Treat tangency conflicts as interpretation failures

Apply this blocking rule whenever a source-backed radius transition is expected:

```text
Tangent + current geometry conflicts
  -> stop the current feature group
  -> restore the last accepted checkpoint if needed
  -> reinspect the exact drawing crop and dimension chain
  -> revise endpoints, radius, arc side, datum, or feature identity
  -> rebuild and reapply Tangent
```

Do not delete or relax the Tangent constraint merely to keep the current arc
hypothesis. Do not continue to holes, bend lines, or final parameterization.
Remove tangency only when source evidence proves the transition is not tangent,
or when the tangency was explicitly an unsupported assumption; record that
decision in the discrepancy ledger.

## 7. Construct arcs and fillets from source evidence

`add_arc` `center_angles.start_angle` and `end_angle` are degrees. Use that mode
only when center and angular limits are the actual source definition.

For ordinary manufactured profiles:

1. create the straight parent segments;
2. use `arc_mode="tangent_fillet"` when radius and adjoining lines are known;
3. use `arc_mode="endpoints_radius"` when endpoints and radius are known;
4. retain `Tangent` and `Radius` constraints;
5. verify endpoints, material side, numerical extents, and source crop before
   continuing.

Never approximate a stated circular radius with a free curve or short segments.

## 8. Gate B-splines

Call `add_bspline` only when the source explicitly defines a free-form curve by
control/interpolation points, knots, or an equivalent point table. A visually
curved or unreadable boundary is insufficient evidence.

Never use a B-spline for a line, circular arc, stated fillet, native conic, or to
hide uncertainty. Preserve source point IDs and determine whether listed points
are control or interpolation points before constructing a justified B-spline.

## 9. Accept profile topology explicitly

For a closed manufacturing profile, inspect:

- expected disjoint outer loops and nested holes;
- parent and nesting depth of every closed wire;
- no intersections, tangencies, overlaps, shared edges, or T-connections;
- no self-intersection or zero-length regular geometry;
- construction geometry excluded from profile topology.

For `one outer loop + N holes`, require `outer_wire_count == 1`,
`hole_wire_count == N`, no intersecting pairs, and `profile_ready == true`.
Closed-wire count alone does not prove hole semantics.

## 10. Protect validation integrity

Never add fake geometry, construction points, dummy constraints,
zero-multiplied expressions, metadata properties, inactive helper sketches, or
no-op features to make a validator report green. Every required driving
dimension must affect requested non-construction geometry in sketch scope or a
real shape-producing feature in model scope.

If a genuine requirement cannot be represented or traced, preserve the honest
model, keep the dimension in the manifest, and report the limitation.

## 11. Finish with sketch-target validation

Call:

```text
validate_parametric_model(
    doc_name=<document>,
    target={"kind":"sketch", "name":<sketch name>},
    required_dimension_names=[<all driving source dimension IDs>],
)
```

Confirm that every required item is `sketch_driving` for non-construction
geometry of that sketch. Separately confirm that every driving and verification
dimension has deterministic same-view semantic measurement evidence, and audit
any exceptional `source_issue` record against its retained source evidence.
Body, Tip, and solid findings are outside sketch scope. The validator cannot
infer omitted source dimensions, visual correspondence, or coordinate provenance
from pixels.
