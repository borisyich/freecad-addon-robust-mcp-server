# Engineering sketch construction

## Purpose

Use this workflow when a drawing, flat pattern, marked-up image, or verbal
specification must become an editable Sketcher sketch. Solver status is only one
piece of evidence: a fully constrained sketch can still have the wrong topology,
the wrong dimensional datum, or a constraint graph that hides design intent.

## Contents

- [Preserve dimensional datums before coordinates](#1-preserve-dimensional-datums-before-coordinates)
- [Build geometry in engineering order](#2-build-geometry-in-engineering-order)
- [Express design intent with relationships](#3-express-design-intent-with-relationships)
- [Arc and fillet rules](#4-arc-and-fillet-rules)
- [B-spline gate](#5-b-spline-gate)
- [Profile topology acceptance](#6-profile-topology-acceptance)
- [Validation integrity](#7-validation-integrity)
- [Sketch-target validation](#8-sketch-target-validation)

## 1. Preserve dimensional datums before coordinates

For every ordinate or baseline dimension, record all of these fields before
creating geometry:

- stable dimension identifier;
- value and unit;
- controlled axis;
- datum/reference feature named on the drawing;
- signed direction from that datum;
- target point, centerline, edge, or feature;
- source view/detail and explicit/derived/assumed status.

Do not store an ordinate as a bare value. `35 mm from DATUM A` is not equivalent
to global `X = 35 mm` unless the view map proves that DATUM A coincides with the
sketch origin and has the same positive axis direction.

Before translating any ordinate/baseline set into global sketch coordinates,
close at least one control chain:

```text
datum -> intermediate baseline/feature -> target feature -> overall/check dimension
```

Compute the signed chain independently, verify that it closes within the drawing
precision, and cross-check it in another view or against an overall dimension
when available. If it does not close, revisit the datum, sign, projection, and
feature identity; do not average conflicting values or silently choose the
global origin.

## 2. Build geometry in engineering order

1. Count and identify the intended outer loops, holes, open paths, centerlines,
   and construction references.
2. Place the primary straight segments first. Start approximate; do not lock
   every endpoint with absolute X/Y dimensions.
3. Join true connections with `Coincident`; apply `Horizontal`, `Vertical`,
   `Parallel`, `Perpendicular`, `Equal`, and symmetry relationships that are
   explicit in, or safely implied by, the drawing.
4. Add circular arcs and fillets only after their adjoining straight geometry is
   stable. When a radius and two adjoining lines are known, prefer
   `add_arc(arc_mode="tangent_fillet")`. When two endpoints and a radius are
   known, prefer `arc_mode="endpoints_radius"`.
5. Add the smallest set of datum-based driving dimensions that expresses size
   and placement. Prefer horizontal/vertical dimensions over general distance
   dimensions when they express the same requirement.
6. Recompute, inspect solver diagnostics and contour topology, then compare the
   sketch with the same drawing view. Repeat after each major contour group.
7. Reach 0 DoF only after topology and dimensional interpretation are accepted.

Use the sketch origin or axes as a datum only when the drawing or a deliberate
functional symmetry scheme supports that choice. Otherwise create or reference
the actual engineering datum.

## 3. Express design intent with relationships

Prefer a compact constraint graph that answers why geometry has its shape:

- endpoints meet because they are `Coincident`;
- edges remain axis-aligned through `Horizontal`/`Vertical`;
- a transition is smooth through `Tangent`;
- repeated radii or lengths use `Equal` or one shared expression;
- circular size uses `Radius`/`Diameter`;
- location is measured from the correct datum with baseline/ordinate dimensions.

Do not reproduce the solved coordinates of every point with a separate X and Y
dimension. A large point-to-origin coordinate grid can produce 0 DoF while
making edits brittle and obscuring the functional relationships.

`fully_constrained` means that the solver reports no remaining motion. It does
not prove any of the following:

- correspondence to the source drawing;
- valid outer-loop/hole nesting;
- absence of intersecting contours;
- correct datum interpretation;
- stable behavior when a driving dimension changes;
- economical or meaningful parameterization.

Vary at least one major driving dimension by a small reversible amount when
practical, recompute, and confirm that the sketch changes in the intended
direction without flipping or breaking topology.

## 4. Arc and fillet rules

`add_arc` `center_angles.start_angle` and `end_angle` are degrees. Use that mode
only when the center and angular limits are the actual source definition.

For ordinary manufactured profiles:

- draw the straight parents first;
- insert a tangent fillet at the stated radius;
- retain or add `Tangent` and `Radius` constraints;
- verify which side of the corner is material;
- compare the resulting transition against the drawing before continuing.

Do not approximate a stated circular radius with a free curve or a chain of
short segments.

## 5. B-spline gate

Call `add_bspline` only when the source explicitly defines a free-form curve by
control/interpolation points, knots, or an equivalent point table. A visually
curved boundary is not sufficient evidence.

Never use a B-spline for:

- a straight edge;
- a circular arc or fillet with a stated radius;
- a conic that has a native Sketcher representation;
- hiding uncertainty in unreadable geometry.

When a point-defined B-spline is required, preserve the source point identifiers
and determine whether the listed points are interpolation points or control
points before constructing it.

## 6. Profile topology acceptance

For a closed manufacturing profile, inspect more than `closed_wire_count` and
`Shape.isValid()`:

- expected number of disjoint outer loops;
- expected number of nested holes;
- parent and nesting depth of every closed wire;
- no intersection, tangency, overlap, shared edge, or T-connection between
  contours;
- no self-intersection or zero-length regular geometry;
- construction geometry excluded from profile topology.

For the common `one outer loop + N holes` case, require
`outer_wire_count == 1`, `hole_wire_count == N`, no intersecting pairs, and
`profile_ready == true`. Multiple closed wires alone do not prove hole semantics.

## 7. Validation integrity

Never add fake geometry, construction points, dummy constraints, zero-multiplied
expressions, metadata properties, inactive helper sketches, or no-op features to
make a validator report green. Every required dimension must affect genuine
requested non-construction geometry in the selected sketch, or a genuine
shape-producing feature in model scope.

If a real requirement cannot be represented or traced, preserve the honest
model, report the limitation, and fix the semantic dependency. Do not feed the
validator an artificial dependency.

## 8. Sketch-target validation

When the deliverable is a sketch rather than a final solid, call:

```text
validate_parametric_model(
    doc_name=<document>,
    target={"kind":"sketch", "name":<sketch name>},
    required_dimension_names=[<all applicable source identifiers>],
)
```

Confirm that required dimensions are `sketch_driving`, meaning that they affect
non-construction geometry of that exact sketch. Body, Tip, and solid findings
are outside sketch scope. Still compare the sketch to the source: the validator
cannot infer the intended silhouette or dimensional datum from pixels.
