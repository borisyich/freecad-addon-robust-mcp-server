# FreeCAD engineering Skill

The canonical engineering workflow is the repository Skill bundle:

```text
.agents/skills/freecad-engineering/
├── SKILL.md
├── agents/openai.yaml
└── references/
    ├── model-from-text.md
    ├── model-from-drawing.md
    ├── machined-and-additive-parts.md
    ├── sheet-metal-parts.md
    ├── edit-without-history.md
    ├── edit-with-history.md
    └── engineering-drawings.md
```

`SKILL.md` is deliberately a router plus common engineering contract. Detailed
workflow guidance belongs in the task reference files.

## Activation

For repository-aware agents, activate `$freecad-engineering` for FreeCAD
engineering tasks. Clients without repository Skill support can read the same
entrypoint through MCP:

```text
freecad://skills/freecad-engineering
```

The complete URI manifest is available at:

```text
freecad://skills/freecad-engineering/bundle
```

## Routing model

The routes are composable. Input source and manufacturing family are separate
classification dimensions. For example, a bent part reconstructed from a
drawing uses both:

```text
references/model-from-drawing.md
references/sheet-metal-parts.md
```

Existing-model edits choose exactly one history route after inspecting the
model:

```text
references/edit-with-history.md
references/edit-without-history.md
```

Engineering-drawing development has a reserved route but remains explicitly
marked TODO until a dedicated drawing toolchain exists.

## Common contract

All geometry-changing workflows use ACT → OBSERVE → REACT, verify deterministic
geometry evidence before relying on screenshots, and call
`validate_parametric_model` before the final response. Imported/direct B-rep
edits additionally use shape checkpoints when required by their reference.

Detailed policy is not duplicated in prompts, resources, `AGENTS.md`, or this
documentation page.
