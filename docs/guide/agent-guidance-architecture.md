# Agent guidance architecture

The project uses one detailed engineering policy and small client-specific
routers. This prevents the same workflow from drifting across prompts,
resources, and instruction files.

## Source of truth

```text
.agents/skills/freecad-engineering/
├── SKILL.md
├── references/
└── agents/openai.yaml
```

`SKILL.md` contains the modeling policy: stock/process classification,
parametric structure, milling, turning, sheet-metal strategy, drawing
reconstruction, model modification, validation, and completion criteria.

## Delivery layers

1. **`AGENTS.md`** — short Codex router. Codex reads it before work and it tells
   the agent to activate `$freecad-engineering` for FreeCAD model tasks.
2. **`.clinerules/freecad-modeling.md`** — short Cline router to the same Skill.
3. **Skill metadata** — the `name` and `description` route relevant tasks into
   the full Skill without loading the full policy for unrelated repository work.
4. **`freecad://skills/freecad-engineering`** — MCP resource that reads the same
   repository `SKILL.md` when that file is available; it is not a copied second policy.
5. **Prompts** — lightweight task context plus a route to the Skill.
6. **Tools** — perform deterministic operations and diagnostics. In particular,
   `validate_parametric_model` reports the actual FreeCAD document structure.

## What is mandatory

For any task that creates or changes FreeCAD geometry:

- activate/read the Skill before modeling;
- follow the first rule for every engineer: feedback loop (ACT → OBSERVE → REACT);
- use any appropriate tool, including `execute_python`, `safe_execute`, or
  `run_macro`, while preserving the Skill's editable/parametric expectations;
- call `validate_parametric_model` immediately before the final user-facing
  response and summarize its significant findings.

This is an instruction-level requirement. MCP cannot prevent a client from
emitting a premature final text response, so the server also makes the final
validator easy to discover through tool descriptions, prompts, resources, and
capabilities.

## Avoiding duplication

Detailed policy belongs only in the Skill. Other files may contain:

- a path/URI to the Skill;
- a one-sentence activation rule;
- tool-specific contracts;
- factual diagnostics or API documentation.

Do not copy complete process descriptions into `AGENTS.md`, prompts, resources,
or general documentation.
