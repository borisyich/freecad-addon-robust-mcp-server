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

For clients that do not implement Codex Skills, read the same file directly. A
repository-launched MCP server also exposes it through:

```text
freecad://skills/freecad-engineering
```

## Contents

The Skill covers:

- selective MCP prompt/resource discovery without dumping the global client
  tool registry;
- stock and dominant-process classification;
- milling, turning, and sheet-metal modeling strategies, including flat-pattern/developed-blank reconstruction;
- editable Body/Sketch/PartDesign structure;
- feature dependency/order guidance;
- drawing-view identification, FreeCAD plane/axis mapping, and dimension-axis evidence;
- saved inventories of every explicit non-starred source dimension;
- mandatory same-view `compare_images` checkpoints after major features and
  before patterning a seed;
- sketch arc construction by endpoints/radius and by tangent fillet between lines;
- the 50% ceiling for Fix/Block constraints;
- existing-model modification;
- lightweight intermediate validation;
- mandatory final `validate_parametric_model` reporting, including source-
  dimension usage and Spreadsheet connectivity/cleanliness.

Detailed content is intentionally not copied into this documentation page.
