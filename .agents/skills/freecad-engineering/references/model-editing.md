# Editing and recovery

## Modify existing models

Select native-history or static-B-rep editing from the actual document evidence.

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
when cleanup drifts. Any deliberate override needs an engineering tolerance and
reason, with original-to-final evidence; intermediate-to-intermediate agreement
does not reset the cumulative error.

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
