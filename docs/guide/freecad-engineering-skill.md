# FreeCAD engineering Skill

The canonical bundle is `.agents/skills/freecad-engineering/SKILL.md`.
It supports new mechanical design, drawing reconstruction, local edits,
repair, and validation with an explicit engineering contract and feedback loop.

## Loading

Native clients discover the repository Skill. Clients using MCP can read:

- `freecad://skills/freecad-engineering` — entrypoint;
- `freecad://skills/freecad-engineering/bundle` — complete URI index;
- `freecad://skills/freecad-engineering/references/<filename>` — routed detail.

The wheel contains the same bundle. Discover the actual server alias from the
client; no particular alias or tool-name prefix is an engineering requirement.
Load the entrypoint and relevant references rather than every file on every task.

## Coverage

The core loop is observe, predict, edit, verify, and restore or accept. It links
requirements, functional interfaces, datums, dependencies, manufacturing
assumptions, tolerances, and measurable evidence.

The model-editing reference supplies an edit-route table and bounded failure-family
protocol. Standard tools come first; diagnostic scripting does not authorize
mutation or guard bypass. A rejection blocks acceptance until its invariant is
resolved. Imported edits use `workflow="imported_brep_edit"` without requiring
reconstruction of native history.

| Reference | Use |
|---|---|
| `design-and-verification.md` | New-design requirements, function, load/fit assumptions, alternatives, evidence and tolerances |
| `model-editing.md` | Local influence regions, native/static geometry, repeat populations, rollback and execution uncertainty |
| `drawing-reconstruction.md` | Source inventory, frames, semantic dimensions, ambiguity, sections and VLM comparison |
| `sketch-construction.md` | Geometry choice, dependencies, solver diagnosis, parameter response |
| `manufacturing-strategies.md` | Stock/process alternatives, access, datums and feature dependencies |
| `sheet-metal-flat-patterns.md` | Panel graph, angle conventions, finite bend zones, flat/formed domains and process limits |
| `validation-and-editability.md` | Claim/evidence boundaries, actual targets, manifests and artifact checks |
| `source-notes.md` | Tested mechanisms, documentation sources and limitations |

New editable parts normally retain native parametric history. Existing imported
models, sketches, surfaces, and assemblies have their own target contracts.
Feature order follows dependencies; constraint quality follows intended behavior,
not a fixed ratio or one mandatory sequence.

After geometry-changing work, `validate_parametric_model` remains the final
diagnostic. Drawing reconstruction also uses the complete acceptance manifest
and equivalent source-view comparisons. The validator cannot establish source
inventory completeness, image semantics, functional performance, or production
readiness by itself.

## Evidence and maintenance

The [audit and experiment report](../engineering-skill-audit.md) records
counterexamples, ablations of checks, virtual use cases, reproducible commands,
and what the results do and do not prove. Tests check real FreeCAD behavior and
bundle/resource integrity; they do not require every procedure's wording to
remain in the entrypoint.

When changing a rule, state the failing behavior, its applicability, the proposed
decision criterion, and a counterexample or relevant test. Keep evaluation
fixtures out of the runtime instructions so a known case does not become the
definition of engineering practice.

The [before/after session audit](../engineering-skill-session-comparison.md)
records subsequent operational regressions, counterevidence and corrections.
Metadata completeness, model health and artifact verification are distinct;
validation reports both `model_assessment` and aggregate `assessment`.
