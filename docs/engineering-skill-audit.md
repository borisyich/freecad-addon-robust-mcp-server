# Engineering Skill audit and practical evidence

Audit date: 2026-09-09. Canonical policy:
`.agents/skills/freecad-engineering/SKILL.md` and its eight routed references.

## Scope and method

Read the previous entrypoint, all six previous reference files and client metadata,
then checked their claims against tool contracts, implementation, repository tests,
and the documentation sources recorded in `references/source-notes.md`.
The revised bundle adds separate design/verification and model-editing references.
The entrypoint routes decisions; details are not repeated in every document.

The practical experiment suite runs against the local FreeCAD XML-RPC bridge.
Each case creates a uniquely named disposable document, closes it in `finally`,
and restores the previously active document. No user model is edited. Tested
environment: Windows, FreeCAD **1.0.2**, build **39319 (Git)**, FreeCAD Python
**3.11.13**. This is one tested environment, not a cross-version guarantee.

## Deficiencies and general replacements

| Previous rule or gap | Replacement and basis |
|---|---|
| Shape-first workflow, little explicit function or acceptance reasoning | Contract linking function, interfaces, datums, requirements, unknowns, prediction and recovery; toleranced interface and edit-response experiments below |
| Fixed feature sequence and straight-segments-first sketch construction | Dependencies and defining geometry determine order; valid circle and fitted-curve experiments refute a universal straight-line prerequisite |
| Fix/Block forbidden above 50% of geometry | Purpose and intended parameter response; a completely fixed reference curve is valid, whereas a frozen intended driver fails perturbation |
| Tangent conflict necessarily means wrong source interpretation | Diagnose redundant constraints, indices, units and solution branch first; duplicate-tangency control preserves the correct relation |
| B-splines legitimate only with a supplied point table | Legitimate free-form design/reconstruction plus explicit fitting uncertainty and independent residual checks; supplied fit points alone are insufficient |
| Local target treated as an isolated face; global summaries taken as preservation proof | Walk geometric and dependency influence regions; test functional interfaces independently; symmetric relocation defeats all tested global metrics |
| Native Body/one-solid and source-image comparison effectively universal | Validate the requested representation: native features, Part dependencies, imported B-rep, sketch/path, surface or assembly; source comparison requires an actual source |
| Frequency of repeated geometry suggests a trustworthy seed | Full-population analysis is only evidence of repetition; ties, plurality, systematic damage and intentional variants need independent interpretation |
| Bend included angle confused with rotation sweep; rigid rotation treated as finite-radius construction | Explicit angle convention and flat/formed/process domains, tangent offsets and finite bend zones; non-right-angle rotation tests expose the convention error |
| Solver/manifest/image attestations treated too strongly | Distinguish structural health, caller claims, actual visual observation, semantic measurements and functional/manufacturing acceptance |
| Unreferenced parameter or construction geometry treated as disposable | Retain legitimate reference/calibration/design data; verify causal dependencies instead of optimizing a score |
| Timeouts/undo/checkpoints imply recovery | Retained execution state first; no retry or dependent edit while unknown; geometry checkpoint is not a document backup or file rollback |

These are scoped decision criteria, not claims that every possible deficiency is
eliminated. Production-specific material allowables, process settings, standards,
loading and inspection capabilities still require applicable evidence.

## Controlled check ablations in real FreeCAD

Run `tests/integration/test_engineering_policy_experiments.py`. The final run
passed **13 parameterized cases**. Values below are observed results, rounded
for readability; the tests compute them anew rather than reading this table.

| Experiment | Reduced check / control | Additional evidence and observed outcome |
|---|---|---|
| Symmetric interface relocation, three sizes | Both candidates are valid; solid count, volume, area, six bounding limits and center of mass agree within 1e-7 | Semantic occupancy changes. Exact added and removed volumes are each 37.6991, 108.9504 and 166.2531 mm³; the local error is detected |
| Intended centered placement, two driver changes | Linked and frozen coordinates coincide at nominal size | Length changes of -4 and +6 mm leave linked error 0, but frozen error 2 and 3 mm. Abort restores length 20 and interface x=10 mm |
| Toleranced fit, two radial tolerances | Nominal interference volume is 0 | Limit configurations interfere by 7.87754 and 20.48161 mm³; nominal assembly does not establish limit assembly |
| Duplicate tangency | Original Tangent solves with code 0 | Duplicate gives -2; removing only the duplicate restores 0 and retains one Tangent |
| Immutable reference curve | One circle, one Block: 100% fixed | Solver code 0, fully constrained. A geometry-percentage ceiling rejects a valid representation |
| Public constraint batch and recovery | Valid reference Fix accepted; two incompatible driving radii submitted in a later batch | Rejected batch restores one constraint, radius 3 mm, solver 0. A four-operation batch with a temporary conflict repaired before its end succeeds |
| Fitted curve | Valid interpolating B-spline passes all three supplied samples: maximum residual about 2.47e-32 mm | An independent point of the specified analytic curve has residual 1 mm; checking only training points misses the approximation error |
| Bend rotation, two non-right angles | Substitute included angle for sweep | Correct sweeps 35° and 110°; substituted conventions produce 110° and 40° normal-orientation errors |

The ablations remove evidence checks while holding candidate geometry fixed, or
compare a dependency-bearing representation with a frozen control. They are
**not** an old-skill/new-skill VLM A/B experiment and do not measure agent success
rates. The bend cases test angle conversion, not a physical K-factor or the
manufacturability of a complete unfolded part.

### Runtime discrepancy discovered during the experiments

`edit_sketch_constraints` previously analyzed the solver and committed regardless
of its unhealthy result. Both `edit_sketch_constraints` and
`edit_sketch_geometry` now apply the shared final-solver guard before commit.
Errors, conflicting/redundant constraints, over-constraint and unverified solver
results abort. Healthy under-constrained construction stages remain supported.
Related repairs can be submitted atomically; intermediate conflicts do not force
rejection when the final state is healthy. The arbitrary Block ratio gate is gone.

An additional public-API check starts from a deliberately damaged sketch:
`edit_sketch_geometry` rejects an added circle and restores the original one
geometry/two constraints. Repairing the conflicting constraint then permits the
same circle addition, ending with two geometries and solver code 0.

An initial negative fixture (Block followed by Radius) did **not** demonstrate a
solver failure on this build; it was not counted as evidence of rollback. The
final fixture deliberately supplies two incompatible driving radii. The old
code's unconditional commit and the new code's actual restore are the relevant
mechanisms. Tangency diagnostics now direct investigation before source
reinterpretation rather than declaring the interpretation wrong.

## Virtual use of the revised policy

These are same-author desk walkthroughs, not independent agent trials. Specific
fixtures belong here and in tests, not as mandatory workflows in the Skill.

| Task variation | Decisions reached through the revised policy | Acceptance or stop condition |
|---|---|---|
| Enlarge a parametric mounting boss without a drawing | Function/interface contract; inspect base transition and attached features; find the radius owner; predict fixed axis and mating face; edit driver and perturb in a reversible copy | Measure actual diameter and preserved interfaces at supported values, restore and remeasure; no invented image manifest |
| Move a wall of an imported rectangular pocket | Preserve original B-rep; inspect wall, floor, end transitions and nearby cavities; resolve local planar surgery capability | Measure moved boundary, floor/transition semantics and unchanged material; reject and restore if the method destroys a transition, even if global metrics pass |
| Construct an open free-form guide from an analytic requirement | Choose path representation, not a one-solid Body; define fitting tolerance and independent sample positions | Connectivity, downstream path behavior and held-out residuals; neither profile closure nor zero DoF alone is the contract |
| Rebuild a repeated mixed population with tied largest groups | Inventory all members before limits; inspect functional/attachment differences; frequency is not correctness | No seed selection until independent evidence identifies the intended unit; keep deliberate variants distinct |
| Interpret a non-right-angle folded panel from a blank | Separate blank/formed dimensions; resolve whether annotation is included angle or sweep, bend side, radius and allowance convention | Compare formed orientation and actual finite-radius/flat representation; unknown process parameters prevent a production-ready claim |
| Design a load-carrying support with missing loads/material | Establish supports, load path, service environment and acceptance criteria; continue independent envelope/layout work | No unsupported strength/safety claim; critical missing values remain open rather than being called a source defect |
| Diagnose a failed model without a request to repair | Read current state, dependency graph and relevant solver/geometry evidence | Explain causal findings without changing the user's geometry |

Additional boundary checks during the walkthrough: remote dependencies outside
face adjacency; valid face splitting/merging; reference spreadsheet data without
a direct consumer; no source images; non-solid deliverables; uncertain running
operations; and exported files outside document undo.

## Reproduction and regression checks

With development dependencies installed and a local FreeCAD bridge running:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_engineering_policy_experiments.py -s -o addopts='' -q
.\.venv\Scripts\python.exe -m pytest tests/unit -o addopts='' -q
.\.venv\Scripts\python.exe -m mkdocs build --strict --site-dir .tmp-mkdocs-engineering-skill
```

Unit tests cover final-solver status combinations, unknown/cached status,
incremental stages, canonical resource contents, reference traversal and bundle
packaging. Documentation tests validate routes and API identifiers; long exact
prose assertions were replaced because they enforced duplicated, over-specific
policy rather than engineering behavior. An existing MultiTransform test was
also updated to check the current structural validator call, not an assignment
of the default empty `Originals` value. No MultiTransform runtime was changed.

Final checks: **755 unit tests passed**; all **13 live cases passed**, with the
expanded public batch case rerun successfully afterward. Skill metadata validation
and strict documentation build passed. The documentation timestamp plugin emitted
a warning for this newly created, uncommitted report. Targeted Ruff checks found
no new diagnostics; the 24 diagnostics in two touched files also exist at HEAD
(16 in `partdesign.py`, eight in `test_freecad_runtime_helpers.py`).

## What remains unproven; next evaluation protocol

This audit establishes counterexamples and tested mechanics, not that a VLM
learns engineering competence from the text. For that claim, use a separate
blinded evaluation: freeze model/tool versions, initial documents, budgets and
task sets before runs; randomize old/new policy assignment; use multiple runs;
include held-out geometry/process/representation families and adverse inputs.

Ablate contract, neighborhood/dependency observation, independent measurements,
parameter perturbation, and recovery separately. Grade actual artifacts and tool
traces against externally prepared requirements, with an assessor unaware of the
assigned policy. Count silent collateral damage, unsafe retry, incorrect
acceptance, recovery failure, edit response and cost; do not score self-attested
`passed` or `image_content_reviewed` fields as truth. Report uncertainty and all
failed/aborted runs. That evaluation has **not** been performed in this audit.
