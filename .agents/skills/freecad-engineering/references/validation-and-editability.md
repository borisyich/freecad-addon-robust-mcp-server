# Validation and editability

## Match the claim to the evidence

| Claim | Evidence required | What it does not establish |
|---|---|---|
| Shape healthy | Recompute, validity, expected topology/solid count | Requirement correspondence |
| Editable as intended | Semantic dependencies, solver diagnostics, reversible perturbation | Correct loads/material or fit |
| Dimension satisfied | Independent measurement of the specified semantic elements and tolerance | Hidden features or other requirements |
| Source view matches | Equivalent projection/section and inspected image content | Numeric accuracy beyond source resolution |
| Function/manufacture acceptable | Applicable calculations, interface limits, process/access evidence | Anything outside the analyzed conditions |

Datum shapes can have synthetic/infinite bounds; exclude them from part metrics.
Surface, sketch, mesh, assembly, imported-B-rep, and Body targets have different
validity expectations. Separate intentional components from accidental helpers.

## Use the validator accurately

After geometry changes, run `validate_parametric_model` immediately before the
final user-facing response. Start compact; request `structure` or paged/full
evidence only for a specific diagnostic. Check the intended document, active
target, Tip, dependency graph, sketch solver, and significant outside objects.

For an intentional imported/static-B-rep edit use `workflow="imported_brep_edit"`.
Validate geometry, preserved interfaces and deliverable fidelity; missing native
history is not a request to manufacture a parametric tree. Native features that
do exist still need dependency checks. A STEP deliverable cannot preserve native
feature history; do not imply otherwise in the report.

For sketch output pass `target={"kind":"sketch","name":...}`; Body/solid/Tip
requirements do not apply to the sketch target. An under-constrained result may
be deliberate motion or an unfinished driving sketch: inspect which DoF remain.
A redundant relation calls for diagnosis, not wholesale reconstruction.

For drawings use the complete `acceptance_manifest`. It supplies every driving
identifier; `required_dimension_names` alone is legacy incomplete acceptance.
Retain every explicit dimension with source location, semantic targets, units,
role, and measurement evidence. `source_issue` documents an actual source defect,
not merely a hard-to-interpret requirement. Keep other dimensions pending if
unverified; do not declare accepted completion while a requirement is open.

The validator checks the records supplied. It cannot discover annotations omitted
from that manifest or independently validate caller-authored tool evidence,
`review_attestation`, or image-content review. Preserve actual observations and
artifacts; report correspondence as caller-attested unless an independent verifier
really checked it. No-image work needs no fabricated visual records.
Non-dimensional requirements belong in `requirements`; empty `dimensions`
are legitimate when the source has none.

Maintain three independent outcomes: model health, source/requirement evidence,
and final artifact verification. The model validator does not replay export or
healing guards. An incomplete manifest does not itself mean broken geometry;
`review_recommended` with `machine_verified=false` does not mean all requirements
were independently verified. Report both the aggregate and scoped assessments.

Record view recipes, candidate identity/revision, actual comparison observation,
and measurement method when the check is performed. Correcting a missing recipe
or attestation afterward is legitimate only if it describes an already performed,
traceable check of the same final candidate. Otherwise do the missing observation;
do not write a success statement merely because validation asks for a field.
Invalidate affected evidence after geometry/export changes. Keep failed checks
in the task record even when a later check succeeds, explaining what changed.

For conflicting measurements record both actual outputs, their methods, frames,
units and uncertainties. Do not cite an optimal-bounds measurement while copying
fast-bound values, or claim exact equality from rounded numbers. If independent
evidence cannot resolve a discrepancy, acceptance of that invariant stays open.
Changing schema completeness never establishes numeric or visual truth.

## Dependency integrity

Trace required drivers to the requested geometry and verify their actual effect.
A useful construction datum can drive production geometry indirectly even when
a structural tracer cannot prove it. Conversely, a named parameter can exist
without meaningful influence. Use perturbation and observation to resolve
uncertainty rather than adding dummy geometry or zero-effect expressions.

Review unused Spreadsheet aliases by purpose. Preserve legitimate inspection
values, manufacturing data, archived user inputs, and reference calculations.
Connect missing design drivers; remove only confirmed redundant task-created
items. Unused count alone is not permission to delete user information.

Never rebuild an accepted sketch or modify geometry just to turn a report green.
Record unsupported tracing or a validator limitation with independent evidence.

## Numerical, visual, and artifact checks

Use declared dimension-specific tolerances with units. Distinguish physical
acceptance limits, raster/source uncertainty, and numerical kernel noise.
For cleanup/export compare to the original baseline, including location. For
intended edits compare allowed changed regions and preserved interfaces.
Volume/bounds agreement is insufficient; exact Boolean differences can themselves
fail and must be reported as unavailable rather than zero.

A saved comparison image is not reviewed until its ImageContent is inspected.
Compare corresponding physical sides and section recipes. For exports validate
the candidate before accepting the destination. For an FCStd deliverable,
reopen a saved copy when persistence of history, expressions, or proxies matters;
recompute and check the intended target. Record unavailable verification.

Final reporting should state the deliverable, measured changes, preserved
interfaces, significant validator findings, and remaining assumptions. Do not
equate a geometry-health report or a fully constrained sketch with production
readiness.
