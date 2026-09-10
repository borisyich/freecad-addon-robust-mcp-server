# Editing and recovery

## Modify existing models

Select native-history or static-B-rep editing from the actual document evidence.

## Choose the edit route before constructing cutting tools

| Observed representation and requested change | First route | Required evidence before escalation |
|---|---|---|
| Native constraint/feature owns the change | Edit that owner; inspect its dependents | Actual dependency and supported parameter range, not an imagined owner |
| Separate components/instances | Edit placements, count or component geometry with typed tools | Whole-population inventory, attachment and intended variants |
| Static solid, supported local boundary motion | Semantic selection and `move_faces` with appropriate feature boundary | Neighborhood, performed method and preserved transitions |
| Static fused repeated features | `group_feature_faces` / `detect_rotational_pattern`; test supported removal/isolation, then `extract_feature_material` where applicable | An independently supported invariant base and complete repeat unit, not only a plausible volume filter |
| Static geometry without a usable direct route | Reconstruct only the necessary local region from measured/source-defined geometry | Interface agreement and unchanged-region checks; no implied permission to approximate the whole part |
| No route satisfies invariants or guards | Preserve the last accepted state and report the specific blocker | Evidence or user decision needed to proceed; do not expand a mask/Boolean search indefinitely |

These are branches, not a list of operations to exhaust. Select the branch from
observed geometry and revisit it only when new evidence changes applicability.
Do not infer a native Pattern feature from visual repetition in an imported solid.
Primitive envelopes are valid isolation tools only when they represent the
measured separation boundary; intersecting some material does not prove the
assumed invariant base is correct.

## Bound failed attempts by causal family

Before a risky operation, record a compact attempt entry: semantic objective and
region, invariant, method family, expected result, acceptance limits, and recovery.
On failure record the actual result and one discriminating observation needed
next. By default allow the initial attempt and **one evidence-led corrective
retry per failure family**. Stop that family after its second failure; after the
first, do not retry without a specific cause and predicted distinguishing result.
This is a conservative work/risk budget, not a geometric theorem or measured
optimal count. A larger experiment needs an explicit bounded plan and justified
evidence before running; a user's stricter limit controls.

Changing mask extent/shape, angle, fuzzy tolerance, Boolean order, object name,
seam orientation, refinement mode, or API does not create a new family when it
tests the same unsupported decomposition or unresolved failure. Count each
kernel candidate inside loops and scripts, including diagnostic candidates.
Do not hide an unbounded search inside one tool call. A new family requires a
different supported mechanism and independent evidence; self-renaming a hypothesis
does not reset the budget. Renew an exhausted family only after new evidence
changes its preconditions and a revised bounded plan is recorded.

Pure schema/argument errors before execution can be corrected without consuming
a geometry attempt. Polling retained running status is waiting, not a candidate
retry. Unresolved execution state forbids another mutation regardless of budget.
On exhaustion, preserve the baseline, summarize eliminated hypotheses, and
continue only independent in-scope work or ask for the missing decision.

## Define the influence region

Inspect the target and nearby geometry before mutation. Use semantic selection,
then walk face adjacency until the primary feature, transitions, support,
attachments, and neighboring functional regions are explicit. Expand along
dependencies as well as geometric adjacency: a remote feature can depend on the
same parameter. Page complete evidence for the chosen region.

Record changes and invariants separately. Boundaries may move while interface
axes, termination conditions, transition radii, continuity, attachment, or
unaffected material remain constrained. Expected split/merge of faces does not
necessarily violate those physical invariants. Never reuse FaceN/EdgeN references
after recompute without resolving their semantics again.

Choose the semantic owner with the smallest correct dependency scope. In native
history inspect downstream features after parameter changes. In static B-reps
retain a source baseline and use supported direct surgery. For local planar
rebuilding, inspect the actual `move_faces` method performed and its limitations;
a fallback extrusion does not prove preservation of a curved transition.

## Checkpoints are evidence, not restoration commands

For imported/static B-rep mutation call `capture_shape_checkpoint` before and
`compare_shape_checkpoint` after the edit. Preserve the original location and
reference through every refine, healing, serialization, and export stage.
Repeatedly exporting/importing a changed shape does not establish fidelity to
the original.

A shape checkpoint records geometry; it is not a full document-history backup.
Provide a document transaction, saved copy, or verified reversible owner edit for
recovery. Confirm undo support before depending on it. On rejection restore
geometry, expressions, Tip, placement, and relevant document state, then repeat
baseline checks. File writes and external effects need their own recovery.

Whole-model validity, volume, bounds, area, and center of mass are screening
metrics. Even all of them can agree for different local geometry. Compare semantic
measurements and neighborhoods; use exact localized added/removed material when
needed and computationally feasible. An unavailable exact result is unknown,
not zero difference. Never treat metric-only acceptance as proof of locality.

For cleanup such as refine/heal, predict geometry preservation rather than an
intended dimensional change. Inspect guard diagnostics and use the valid original
when cleanup drifts. The core rejection rule also covers cleanup and export:
an agent-authored explanation alone cannot justify an override. Keep planned
engineering tolerances distinct from suspected estimator error; validate a
replacement estimator on the original and candidate without relaxing the
engineering invariant. Intermediate agreement does not reset cumulative error.

## Repeated features

Inventory the complete valid population before filters, sorting, or limits.
Group topology and compare local geometry, placements, attachment, and transition
structure. Frequency is evidence of repetition, not correctness or a statistical
majority. Tied largest groups remain ambiguous. A unique largest group can be a
plurality or contain systematic damage; outliers may be intentional variants.
Do not infer the seed from names, indices, order, or a zero spread in one sample.

Establish the intended repeat unit from source/function and inspect candidate
members against it. If evidence cannot identify an intact member, preserve the
uncertainty and reconstruct only when the common design is independently defined.
Do not multiply a guessed instance.

Before changing population, test the decomposition against the original state:
recompose the measured base and recovered repeat units at the original placements
or independently verify equivalent source boundaries and interfaces. Compare
local material/geometry, not just the bounding box. A few plausible components
from a failed whole-population extraction do not establish a correct seed/base.
If exact control is unavailable, disclose the missing evidence; do not label
the reconstruction exact because the kernel returned a valid solid.

Check transforms, handedness, seed inclusion, count, pitch, termination, overlap,
and attachment. For an unfused compound of identical copies, component-volume
sum should equal seed volume times total copies. For a fused pattern, overlap
means that equality generally does not hold; for subtractive patterns compare
actual removed regions, accounting for intersection with the base.

Use `multi_transform_pattern` for composed PartDesign transforms instead of
chaining Pattern features. Inspect `material_change_diagnostics`, final Tip,
expected solid count, local interfaces, and layout. Use source-image comparison
when supplied; otherwise use the functional and geometric contract.

## Execution uncertainty

Track long operations with jobs and inspect actual execution state. A running
or unknown request may still mutate FreeCAD: do not duplicate it, undo it, or
issue dependent edits while its outcome is unresolved. If the bridge cannot
recover retained status, inspect after execution is known to have stopped and
reconcile the document with the last accepted baseline.

A guaranteed queue timeout is cancellation before execution; a stopped operation
with an actual error is failure; `unknown_after_timeout` and
`unknown_after_transport_error` do not prove either rollback or completion.
Recovery must follow observed state, including any partial side effects.
