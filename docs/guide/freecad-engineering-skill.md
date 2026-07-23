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

- stock and dominant-process classification;
- milling, turning, and sheet-metal modeling strategies;
- editable Body/Sketch/PartDesign structure;
- feature dependency/order guidance;
- drawing-image inspection and assumptions;
- existing-model modification;
- lightweight intermediate validation;
- mandatory final `validate_parametric_model` reporting.

Detailed content is intentionally not copied into this documentation page.
