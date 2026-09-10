# Evidence basis and limits

This bundle separates tested tool behavior, engineering reasoning, and empirical
agent-performance claims. No finite test suite proves that a language/vision model
has acquired the complete competence of a design or manufacturing engineer.

## Reproducible repository experiments

The repository test module
`tests/integration/test_engineering_policy_experiments.py` runs disposable
FreeCAD documents against the local bridge. Its ablations hold candidate geometry
fixed while removing one check:

| Check/decision | Counterexample or control |
|---|---|
| Local interface evidence beyond global metrics | Relocated symmetric voids retain volume, area, bounds, center of mass, and solid count |
| Parameter response and recovery | Linked and frozen placements agree at nominal size; only the linked one follows two changed sizes |
| Toleranced interfaces | Nominal non-interference becomes interference at dimensional limits |
| Diagnose redundancy before reinterpreting geometry | Duplicate Tangent fails; removing the duplicate preserves the original relationship |
| Purpose-based Fix/Block | A single intentionally fixed reference circle is valid in FreeCAD |
| Independent fit validation | An interpolating curve matches all fit points but misses a held-out source point |
| Explicit angle convention | Non-right-angle panel rotations distinguish sweep from included angle |

These are mechanism tests and counterexamples to universal rules. They do not
score a VLM's reading or execution of prose. The accompanying repository audit,
`docs/engineering-skill-audit.md`, records results, virtual task walkthroughs,
and the protocol for a separate blinded agent evaluation.

Existing integration tests cover B-rep component population/ties, checkpoint
differences, native sketches, sheet metal, and parametric dependencies. Run the
relevant suites when their contracts change; passing only text assertions does
not validate engineering behavior.

## Documentation used as bounded support

- [FreeCAD Sketcher Workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_Workbench.md):
  distinguishes sketch uses and constraints; profile closure/nesting rules apply
  to appropriate solid profiles, and a constrained sketch can have different
  geometric solutions.
- [Constraint practices](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_Micro_Tutorial_-_Constraint_Practices.md):
  geometric relationships can express intent more directly than redundant
  dimensions; this is not a universal ban on ordinate dimensions.
- [Sketcher fillet](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_CreateFillet.md):
  parent-edge fillet construction is conditional on the intended transition.
- [Sketcher B-spline](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_CreateBSpline.md):
  free-form curves have explicit control/degree/knot semantics. The tool's existence
  does not restrict legitimate source intent to supplied point tables.
- [Basic Part Design](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Basic_Part_Design_Tutorial.md)
  and [attachment](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Basic_Attachment_Tutorial.md):
  native feature dependencies and attachment are model structures to preserve,
  not a demand that every deliverable be one manufactured solid.
- [Fusion turning](https://help.autodesk.com/view/fusion360/ENU/?contextId=MFG-TURNING-OVERVIEW):
  rotating workpiece/axis and explicit radius-versus-diameter semantics.
- [Fusion modeling modes](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES):
  parametric history and direct modeling provide different forms of editability.
- [Onshape sketching guidance](https://www.onshape.com/en/resource-center/tech-tips/how-to-avoid-3-common-cad-sketching-mistakes):
  sketch size and construction relationships affect maintainability.

The FreeCAD documentation repository is an archived reference; installed
FreeCAD/tool behavior must be checked for version-specific claims. During this
audit several old SOLIDWORKS links returned only help-shell content, the Inventor
link returned no readable body, and the old Fusion stock link returned Page Not
Found. They are not retained as verified support for strong requirements.

Clearance interval bounds follow subtraction of endpoint intervals. Bend
allowance in the stated K convention follows arc length at the neutral radius;
that geometric relation does not identify a physical K-factor. No numeric
allowable, fit, tool-access limit, or material rule is supplied as universal truth.
Fetch an applicable authoritative source and establish conditions for a production
decision.

## Scope of practical evidence

The experiments establish failure modes and necessary distinctions on the
tested FreeCAD build. They do not establish production manufacturability,
load-bearing capacity, universal rollback reliability, or superiority across
VLMs. CAD guidance remains conditional on requested fidelity, source evidence,
and actual tool capabilities. Preserve this distinction when extending the skill.

A subsequent before/after audit is recorded in the repository at
`docs/engineering-skill-session-comparison.md`. It exposed excessive fallback
freedom, weak edit routing, guard bypass, equivalent retries, and inconsistent
acceptance reporting. It motivates the bounded control rules; the attempt budget
is a work/risk default, not an experimentally optimal value. Neither that pair
nor the mechanism tests isolates policy effects from tool-version changes or
proves improved agent performance.
