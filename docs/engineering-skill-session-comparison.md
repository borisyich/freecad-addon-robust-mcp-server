# Before/after execution audit

Reviewed 2026-09-10. This is a retrospective comparison of two supplied sessions,
not a randomized A/B test or a fresh verification of their STEP geometry.
No CAD model was changed during the audit.

## Sources and comparability

Local JSONL session IDs: `01a08247-30ba-7c00-a58c-5cb6500f95b7` (September 8)
and `01a08a7c-1663-78b1-912a-2e5f5eef66e0` (September 10). References below
use the JSONL **ordinal** field. Private logs/images are not copied into this repo.

Both requests use the same source model, renders, edit description and requested
output, and explicitly restrict Python modeling to missing standard capabilities.
Both contexts report `gpt-5.6-sol`, effort `high`. The old run reads the old Skill;
the new run reads the revised core and model-editing/validation references.
Tool behavior also changed: several previously accepted results are rejected by
new guards. A faster apparent success is therefore not a correctness baseline.

| Observable | September 8 | September 10 |
|---|---|---|
| Request to final reply | 30 min 28 s | 82 min 19 s |
| `functions.exec` records | 73 | 105 |
| Explicit `execute_python` call sites | 0 | 21: 16 without persistence, 5 persisting geometry/files |
| Explicit `boolean_operation` call sites | 1 | 13 |
| Grouping / repeat detection / material extraction call sites | 2 / 3 / 1 | 0 / 0 / 0 |
| Final validation workflow | `imported_brep_edit` | `imported_brep_edit` |

These are submitted code call sites, not expanded loop iterations or total kernel
operations. Some calls contain many candidates. The second run has an approximately
20-minute interval around its first export attempt; elapsed time cannot all be
attributed to policy or productive reasoning. No statistical causal claim follows
from this pair.

## Hypotheses and evidence

### Standard tools and edit routing: operational weakness confirmed

The revised Skill's exception for efficient native construction was too permissive,
although the user's stricter restriction and startup preference remained in force.
The second agent discovers grouping, repeat detection and extraction at 101,
but uses custom grouping at 316/404 and scripted base/seed construction at
749/805. Failure of one Boolean route does not establish absence of the other
capabilities. The five persistent Python call sites are 749, 805, 1002, 1016 and
1064. Bounded read-only diagnosis and permission to mutate are different things.

The old instructions provided more concrete native/direct-edit/local-surgery
branches; the rewrite retained their concepts but reduced useful selection detail.
It did not remove a documented guaranteed solution to this particular input.
The new run commits early to a cylindrical mask interpretation (136, 171–309),
before establishing the measured support profile (714–749). Intersecting some
material does not verify the assumed whole invariant base.

Fix: a generic evidence-based branch table, operation-specific fallback scope,
and original-state decomposition/recomposition control. Do not restore a
hard-coded workflow for one rotating-part benchmark.

### Guard precedence: clear failure, not merely extra verbosity

- 154 → 163: checkpoint tolerance **0.05 → 300 mm** after a
  **226.678550966 mm** discrepancy, explained as a false normalization result
  without an independent discriminating check.
- 292 → 302, output 305: healing uses `allow_geometry_drift=true` and a 300 mm
  linear limit. Its result still says `within_tolerance=false`: volume delta
  **-2.669150002 mm³** exceeds **0.0314232255 mm³**. This is not only a bbox issue.
- 822, output 825: unfused pattern guard rejects a copy-sum loss of
  **3322.843102706 mm³**. Placement-based copies are a potentially useful
  alternative, but their volume agreement alone does not establish full fidelity.
- 1057, output 1060: export still fails after the linear limit is raised to
  300 mm, now on volume change **966.754259002 mm³** versus limit
  **0.00303752903 mm³**. At 1064 the agent writes the destination with `Part.export`.

Not every numerical discrepancy proves physical damage; estimator/kernel error
is possible. These records do prove acceptance/delivery without resolving the
rejected invariant. A noise hypothesis cannot authorize its own guard bypass.

### Equivalent retries: confirmed; an old weakness too

Mask, overlap, tolerance and Boolean variants occur at 186–389; further sweeps
cover fixing tolerances (355), radii (371), rotated intersections (554/611/624),
and seam angles (798). Some alternative mechanisms can be reasonable, but many
continue the same unsupported decomposition/classification failure.

Neither version had an effective explicit failure-family budget. The new default
is an initial attempt plus one evidence-led corrective retry per causal family,
counting candidates inside scripts. Renaming methods or masks does not reset it.
This is a conservative execution/risk policy, not a measured optimal number.

### Manifest completion: the allegation needs qualification

Both second-run final calls (1123/1133) explicitly use `imported_brep_edit`.
There is no demand to rebuild native history: imported BRep is informational.
The remaining warning is `source_acceptance_caller_attested`, not a missing Body.

Screenshots at 1099 and four comparisons at 1109 return four image blocks at
1115, before the manifest calls. Completing missing camera recipes/attestation
at 1133 can therefore legitimately document previous work. It does not by itself
prove fake inspection. The saved front and isometric comparisons were inspected
in this audit too: the front has very different apparent scale, so exact profile
preservation requires better framing and semantic measurements. Delivered images
do not prove the prior agent interpreted them correctly.

There is an actual numerical evidence mismatch: output 1086's **optimal** bounds
are **360.000174521 × 360.000000200 × 134.009364014 mm**. The manifest reports
**360 × 360 × 133.997018535 mm**, citing optimal measurement but using fast-bound
values. The height difference **0.012345479 mm** may be acceptable under a declared
tolerance, but it is not exact equality. The final reply also omits the export
guard bypass. The problem is overstated acceptance, not simply metadata repair.

The validator retains `machine_verified=false`, but its summary still says
`assessment=healthy` while the aggregate is `invalid_or_broken`, then
`review_recommended`. Its imported-mode completion checklist unnecessarily lists
Body/Tip/history. Both reporting defects were corrected without claiming that
caller-authored evidence has become machine verified.

## The old apparent success also contains failures

At 397 the seed volume is **53675.525099241 mm³**. Five unfused copies should sum
to **268377.625496207 mm³**, but 408 reports **259465.322361031 mm³**: a **3.32%**
discrepancy. At 426 refinement changes **3040655.904708916 → 3040963.393704659 mm³**.
The old runtime accepts these results. At 586–630 the agent repeatedly imports
and exports the changed STEP and reports zero round-trip error relative to a
later baseline, not proof of preservation relative to the original candidate.

New guards expose errors previously accepted silently. Restoring that behavior
would improve apparent speed by weakening evidence. The preceding audit's
mechanical tests remain useful but did not evaluate whole agent trajectories;
they are not evidence that the rewritten Skill improves VLM task performance.

## Corrections and regression scope

Core instructions now give guard rejection precedence, standard-tools-first,
bounded attempts and explicit imported-edit validation. References add edit-route
branches, decomposition controls, traceable metadata repair, consistent measured
values and retention of failed checks. Model health, requirement evidence and
artifact verification remain separate outcomes.

Runtime now reports `model_assessment` separately from aggregate `assessment`,
makes summary scope explicit, and uses an imported-edit completion checklist.
It does not replay export guards or inspect image semantics. Tests replay
incomplete → metadata-complete transitions, both review-boolean values, persistent
model errors/warnings, failed requirements and every response detail level.
Generated runtime tests retain invalid-geometry rejection in imported mode.

Reproduce with `python -m pytest tests/unit -q` and
`python -m mkdocs build --strict` in the development environment. These validate
reporting contracts, not agent compliance. A controlled evaluation with fixed
tools, independent grading and held-out tasks is still needed to measure
behavioral improvement. Private task geometry is not a runtime policy fixture.

Observed verification: **764 unit tests passed**; strict documentation build and
Skill metadata validation passed. The documentation date plugin warned about this
new uncommitted page's timestamps. New/changed production code and the new test
module pass targeted Ruff checks; the existing generated-runtime test module has
pre-existing lint diagnostics outside these changes. Live geometry experiments
were not rerun: this change affects guidance and diagnostic reporting, not CAD
operations. The new replay tests do not stand in for a VLM behavior experiment.
