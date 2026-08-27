# FreeCAD engineering Skill

The repository includes a Codex Skill at:

```text
.agents/skills/freecad-engineering/SKILL.md
```

It is the single source of detailed engineering guidance for creating,
reconstructing, modifying, repairing, and validating mechanical models in
FreeCAD.

## Activation

For Codex, open the repository root and start a new session after changing the
Skill or `AGENTS.md`. The root `AGENTS.md` requires `$freecad-engineering` for
FreeCAD model tasks. The Skill's front-matter description also supports implicit
routing.

For clients that do not implement Codex Skills, read the same file directly.
The MCP server exposes the complete Skill bundle even when installed from a
wheel, with the entrypoint at:

```text
freecad://skills/freecad-engineering
```

The bundle manifest is available at:

```text
freecad://skills/freecad-engineering/bundle
```

All relative Skill files preserve their repository paths beneath that URI, for
example:

```text
freecad://skills/freecad-engineering/references/drawing-reconstruction.md
freecad://skills/freecad-engineering/references/sketch-construction.md
freecad://skills/freecad-engineering/agents/openai.yaml
```

## Contents

The Skill covers:

- selective MCP prompt/resource discovery without dumping the global client
  tool registry;
- stock and dominant-process classification;
- milling, turning, and sheet-metal modeling strategies, including flat-pattern/developed-blank reconstruction;
- editable Body/Sketch/PartDesign structure;
- feature dependency/order guidance;
- complete source-view inventory, including opposite-side views, sections,
  details, auxiliary/non-standard views, and their FreeCAD camera/section recipes;
- saved inventories of every explicit source dimension, including annotations
  with drafting markers such as an asterisk, parentheses, `REF`, or `TYP`, mapped
  to source view and semantic geometry, classified as driving/verification or the
  exceptional evidence-backed `source_issue` role; `unresolved` is not a terminal
  manifest classification;
- ordinate/baseline datum preservation and a mandatory control dimension-chain
  check before global-coordinate conversion;
- same-view `compare_images` checkpoints for feature-relevant views during
  modeling, plus exhaustive one-to-one comparison of every source-view manifest
  record before final acceptance;
- sketch arc construction by endpoints/radius and by tangent fillet between lines;
- straight-lines-first sketch construction, semantic constraint selection,
  explicit B-spline gating, and outer/hole/intersection topology checks;
- flat-pattern feature-group gates with numerical checks before visual checks,
  a mutable interpretation manifest, and a blocking tangency-conflict rule;
- coordinate provenance audits separating source-backed, derived, and
  solver-lock point coordinates;
- the 50% ceiling for Fix/Block constraints;
- existing-model modification;
- lightweight intermediate validation;
- mandatory final `validate_parametric_model` reporting for driving dimensions,
  plus same-view semantic measured evidence for every driving/verification
  dimension, source-issue auditing, sketch-target scope, and Spreadsheet
  connectivity/cleanliness.

Detailed content is intentionally not copied into this documentation page.
