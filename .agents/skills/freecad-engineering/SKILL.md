---
name: freecad-engineering
description: >
  Design, reconstruct, edit, and verify mechanical geometry in FreeCAD from
  requirements, drawings, images, or existing models. Connect function, datums,
  parameter dependencies, manufacturing assumptions, and measurable acceptance.
  Use for CAD work; not ordinary MCP-server code or documentation maintenance.
---

# FreeCAD engineering

Treat the model as a testable engineering hypothesis. A successful command, a
valid solid, and a plausible picture answer different questions. Deliver the
requested geometry and editability with evidence tied to its intended function.

## Establish the engineering contract

Before geometry changes, identify the task: reconstruct supplied geometry,
design new geometry, edit an existing design, or diagnose without mutation.
Identify the intended document, parts, units, coordinate frames, deliverables,
and required fidelity. Preserve the user's process, material, and interface
choices. An imported model is a legitimate direct-edit starting point; it does
not implicitly require reconstruction of its entire history.

Record a compact contract in the task notes or existing project artifact:

- **Requirements:** what must work or change, with source and acceptance method.
- **Invariants:** interfaces, datums, unaffected regions, assembly relationships,
  topology, and parameter relationships that must survive.
- **Unknowns:** distinguish observed facts, derived values, and assumptions;
  identify which uncertainty could change the design decision.
- **Prediction:** expected changed region, dimensional response, and relevant
  failure modes; set tolerances before observing the candidate.
- **Recovery:** last accepted state and an actual way to restore it.

For new design, load
[design-and-verification.md](references/design-and-verification.md).
Determine load path, supports, motions, environment, fit, access, and production
constraints as relevant to the request. Geometry alone supplies none of these.
Use calculations or experiments whose assumptions match the intended use.
For reconstruction, preserve source intent rather than silently redesigning it.
For a diagnosis request, perform read-only checks and explain the cause.

Resolve noncritical ambiguity from available evidence and record an editable
assumption. If alternatives change a required interface, function, material, or
production decision and evidence cannot distinguish them, keep that requirement
open and report the missing decision; continue independent work. Do not turn
uncertainty into a claimed verification or a fabricated source defect.

## Observe → predict → edit → verify → restore or accept

1. **Observe the baseline.** Inspect current geometry and dependencies before
   choosing an operation. For a local edit, resolve targets with
   `select_subshapes` and inspect adjacent faces with
   `inspect_subshape_neighborhood`. Expand until the functional boundary,
   attachment, transitions, and affected neighboring regions are understood.
   A face identifier is an edit handle, not the complete feature.
2. **Predict and select the semantic owner.** Choose the parameter, constraint,
   sketch, feature, or local B-rep region that owns the requested change.
   Follow dependencies; an earlier feature is not automatically the right owner.
   Specify which measurements should change and which should remain fixed.
3. **Edit a reviewable feature or related group.** Recompute. Use native editable
   history where it expresses the requested design; retain existing history on
   an edit. Keep any direct modeling or approximation explicit.
4. **Verify independently.** Measure the resulting geometry, not just the input
   parameter. Reselect transient topology. Check local attachments, transitions,
   functional dimensions, solver state, Body Tip, expected solids, and downstream
   dependencies. Select views or sections that expose likely errors.
   A changed face count may be harmless splitting/merging; compare physical
   boundaries and relationships, not FaceN identity or counts alone.
5. **React.** Accept only when the contract is met. On collateral damage,
   restore the causal operation or rework its design intent, then remeasure.
   Verify restoration against the baseline; issuing undo is not proof of recovery.

Read [model-editing.md](references/model-editing.md) for existing models,
repeat populations, checkpoint limits, and recovery. Apply the same loop during
creation, with proportional checks after each meaningful change.

### Rejection takes precedence over the proposed explanation

A failed geometry, material-change, checkpoint, or export guard blocks accepting
that candidate and operations depending on it. "Kernel noise", "bad seam", and
"normalization bug" are hypotheses until independently tested. Do not widen
tolerances, enable drift, change the baseline, or repeat the operation through
Python to turn rejection into acceptance. Diagnose on an isolated copy with a
bounded discriminating test. If a verifier defect is demonstrated, record the
defect and independent checks of the same invariant; repair the verification
path within authorized scope or use a justified scoped replacement preserving
the other guards and atomic file acceptance. Do not change server code without
authorization. If no reliable verification path exists, report blocked delivery.
A requested relaxation of actual fidelity
requires the user's decision, not the agent's explanation.

Apply the bounded-attempt protocol in
[model-editing.md](references/model-editing.md) to failed CAD operations during
creation as well as edits. Renaming objects or switching APIs does not reset it.

## Choose representation and dependencies

Default for a new editable manufactured part: native Body, constrained sketches,
semantic features, and named parameters where later edits benefit. Use one Body
per intended contiguous part in the supported PartDesign workflow. For an
assembly, preserve separate parts and placements; for sketch, surface, mesh, or
static-B-rep deliverables, validate that representation rather than forcing a
one-solid Body. State expected solid count before operations.

Native parametric Part primitives and Boolean dependencies can also express
editable intent; a Body is not the only legitimate native representation.

Choose functional datums independently of the camera. Prefer stable origin or
datum references when they express the relationship. Build a dependency graph:
a feature follows its required supports and driving geometry. Edge treatments
may be late details or early functional parents. CAD history and shop-floor
operation order are different plans.

Read [sketch-construction.md](references/sketch-construction.md) when creating or
editing sketch geometry and constraints. Read
[manufacturing-strategies.md](references/manufacturing-strategies.md) when
selecting stock, process, setups, or manufacturing representation; it covers
milling, turning, sheet metal, and other processes without inferring a unique
process from shape alone. For sheet metal also load
[sheet-metal-flat-patterns.md](references/sheet-metal-flat-patterns.md).

## Reconstruct from drawings or images

Load [drawing-reconstruction.md](references/drawing-reconstruction.md) before
interpreting drawing geometry. Inventory every source view/detail/section and
explicit dimension relevant to the supplied part, including corroborative views
and marked reference dimensions. Preserve raw annotations and semantic targets.
Reproduce every source-view manifest record one-to-one before final acceptance.
Use `compare_images` only when a source image exists; surface and inspect its
ImageContent. Images support correspondence but do not establish numeric
tolerances, hidden geometry, or structural capacity.

Use the actual acceptance-manifest schema. Physical dimensions use `driving`
or `verification`; `source_issue` requires concrete source evidence.
Do not use `unresolved` as a terminal accepted dimension role. Unverified
requirements remain pending and prevent an unqualified acceptance claim.
Counts, material, process, and other non-dimensional criteria belong in
`requirements`. No-image tasks need no invented view or image attestation.

## Use tools with explicit scope

Discover the available FreeCAD server and exact tools in the current client;
server aliases and tool prefixes vary. Read compact capability metadata, then
only the schema needed. If loaded over MCP, resolve relative links beneath
`freecad://skills/freecad-engineering/`; its `bundle` resource indexes files.
Do not reload the same policy through several prompts or dump the global registry.

Use compact inspections first and page relevant topology or constraints.
An incomplete page is not a complete population. Use standard typed tools first
when their contract covers the operation. Before scripting, identify the exact
missing capability or reproducible implementation defect and the smallest scoped
fallback. A rejected candidate is not evidence that the standard tool is broken.
There is no requirement to try every equivalent formulation before stopping.
Do not reimplement available selection, grouping, extraction, transforms, or
export merely for convenience. `execute_python`, `safe_execute`, and `run_macro`
remain available for genuinely missing capabilities and bounded diagnosis;
read-only diagnosis is not permission to write its candidate into the model.
Fallback permission is operation-specific, not inherited by later operations.
Return to typed tools afterward and preserve their acceptance checks. A user's
stricter standard-tools-only constraint takes precedence over these exceptions.

For long operations use `start_tool_job` and `get_tool_job`. A timeout describes
waiting, not necessarily execution failure. Running OCCT work is not safely
interruptible through `cancel_tool_job`. Confirm retained execution state before
retrying, undoing, or starting dependent work. Unknown state remains unknown;
queue cancellation is valid only when execution was guaranteed not to start.
Do not assume document transactions undo files, external effects, or all macros.

## Completion and evidence limits

Read [validation-and-editability.md](references/validation-and-editability.md).
Recompute and inspect the intended deliverable; confirm its saved/exported
artifact when requested. Report significant unresolved assumptions and which
requirements were measured, visually reviewed, analytically checked, or untested.

After geometry-changing work, call `validate_parametric_model` immediately
before the final response. For intentional imported/static-B-rep editing pass
`workflow="imported_brep_edit"`; this does not require reconstructing history.
For drawing/sketch reconstruction pass the complete
`acceptance_manifest`; for sketch output also pass
`target={"kind":"sketch","name":...}`. `required_dimension_names` alone is
legacy input, not complete source acceptance. Interpret warnings against the
requested representation. Caller attestations do not prove image semantics,
source-inventory completeness, or tool provenance.

Keep modeling health, requirement evidence, and artifact/export verification as
separate conclusions. `review_recommended` is not machine-verified acceptance;
a complete manifest cannot clear a previous guard rejection. Record evidence
when observed. Repair omitted metadata only from existing traceable observations;
otherwise perform the missing check. Do not replace a failed measurement with a
more convenient estimator, remove a failed requirement, or relabel it to obtain
a better report. Preserve method, frame, units, tolerance, and actual values.

Never modify accepted geometry merely to improve a validation score. Diagnose
the actual dependency; preserve legitimate reference parameters and construction
geometry. A model-health report is not proof of strength, toleranced assembly,
tool accessibility, or production readiness.

The evidence basis and its limits are recorded in
[source-notes.md](references/source-notes.md).
