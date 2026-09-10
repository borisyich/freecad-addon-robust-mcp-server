# Engineering sketch construction

A sketch expresses geometric relationships and admissible change. Solver health,
profile topology, source correspondence, and edit response are separate checks.
Use [drawing-reconstruction.md](drawing-reconstruction.md) for source evidence
and [validation-and-editability.md](validation-and-editability.md) for acceptance.

## Select geometry from its definition

Use the simplest representation faithful to the source and function: lines,
circles, circular arcs, conics, or free-form geometry as appropriate. Straight
parent segments are useful for line-to-line fillets; circular, conic, or
free-form profiles need no artificial straight-line stage.

For `edit_sketch_geometry`, choose arc mode by known quantities:
`center_angles` for center and angular limits; `endpoints_radius` for chord,
radius, and side; `tangent_fillet` for adjoining line segments and radius.
The first mode takes degrees. Recheck current geometry indices after trimming.
A chord longer than twice the specified radius has no circular solution.
A major arc, material side, or sweep sign must be established from evidence.

Use `add_bspline` for genuinely free-form design, measured/reconstructed curves,
or supported fitted data. Record whether points interpolate or control the curve,
end conditions, continuity, and fitting tolerance. Verify residuals with
independent samples, not only the points used to fit it. A sparse image may
support an approximate contour, with explicit uncertainty; it cannot define an
exact production profile. Preserve stated analytic geometry exactly instead of
substituting a spline to conceal an interpretation failure.

## Build and constrain by dependency

Choose sketch support, local frame, and datums before assigning coordinates.
Use geometric relations for intended incidence, direction, tangency, equality,
and symmetry, then the independent dimensions needed to control them.
Apply dimensions during construction when they stabilize subsequent geometry;
there is no requirement to postpone all dimensions until the final stage.

Separate feature groups when that isolates design intent or eases diagnosis.
The order follows dependency: a parent edge precedes its fillet, a bend axis may
precede a panel-dependent cutout, a datum may precede the outside contour.
A closed-loop stage and an open construction stage have different acceptance.

Classify absolute coordinates as source-backed, derived from a dimension chain,
or temporary solver locks. Ordinate dimensions are legitimate design intent.
Inspect `coordinate_review_recommended` as a diagnostic; a coordinate count
alone cannot determine whether a constraint is wrong.

Fix/Block is appropriate for intentionally immutable reference geometry or a
specified frozen profile. It is inappropriate when it suppresses an intended
driving relationship. Judge by purpose and a reversible edit-response test, not
by percentage of geometry. Do not delete accepted constraints merely to satisfy
a score. A deliberately free path or mechanism can also retain meaningful DoF.

## Diagnose constraint conflicts before changing interpretation

Sketch geometry/constraint batches reject an unhealthy or unverified final
solver state and abort their transaction. Apply coupled repairs in one batch;
temporary intermediate conflicts are allowed only if resolved by its end.
Healthy under-constrained sketches remain valid construction stages.

Inspect the actual conflict/redundancy indices, geometry, existing relationships,
driving/reference state, and expression units. A failed Tangent addition can be
a duplicate of a correct existing relationship, a redundant dimension, wrong
indices after trimming, an incorrect solver branch, or a source-interpretation
error. Remove a demonstrated redundant constraint while preserving the intended
tangency; revise the source interpretation only when evidence calls for it.

Do not remove an intended relationship simply to suppress the error. A radius
does not by itself prove tangency to every adjacent edge. Record the supported
relation and recheck endpoints, branch, material side, and dimensions.

Spreadsheet-driven sketch dimensions bind through actual constraint expressions.
Use `expression`, `set_expression`, or `clear_expression` on
`Constraints[index]` and verify with `get_sketch_info`. A name does not create
a dependency. Numeric angle constraints are degrees at the MCP boundary;
expressions need compatible angular quantities.

## Verify topology and behavior

For a closed material profile, inspect self-intersections, zero-length/duplicate
edges, touching or intersecting loops, nesting, and excluded construction
geometry. Match outer/hole counts to the intended region; closed-wire count
alone cannot identify holes. For a path or open profile validate its intended
connectivity and downstream operation instead of demanding `profile_ready`
for a solid.

Check actual dimensions and equivalent source views when supplied. Then
perturb meaningful parameters within the intended range, predict and measure the
response, and restore. Zero DoF proves only solver constraint, not geometry
correctness or robust editing. Scope final sketch validation with
`target={"kind":"sketch","name":...}`.
