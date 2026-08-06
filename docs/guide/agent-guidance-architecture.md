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

Protocol-level `MCP_INSTRUCTIONS` is delivered once as server instructions; it
must not be copied into every tool description. Tool descriptions contain only
the first concise purpose paragraph. Exact typed arguments remain in JSON
Schema, while cosmetic schema `title` fields are removed to keep `tools/list`
within a practical context budget. Full workflows and large-response warnings
belong in documentation, resources, prompts, and the Skill.

## Selective client discovery

Client-side discovery must not print every entry matching broad terms such as
`resource`, `prompt`, or `mcp` from a global `ALL_TOOLS` registry. Such a query
includes unrelated platform tools and can be much larger than FreeCAD's own
`tools/list` response.

Use the canonical server ID `freecad-mcp`, list prompt/resource names first,
then read or invoke only the item required for the current workflow. Start with
`freecad://skills/freecad-engineering`; use a workflow resource or
`freecad_guidance(task_type=...)` only when the task needs that narrower
guidance. When inspecting tools in a client registry, filter by an exact tool
name or the `mcp__freecad_mcp__` namespace and output a compact count/size
summary instead of complete schemas.

## Regression budgets

The server does not truncate tool descriptions at runtime. Instead, tests guard
the actual protocol and compact-response sizes:

- complete compact `tools/list` payload: less than 90 KB;
- aggregate tool descriptions: less than 10 KB;
- largest single serialized tool definition: less than 8 KB;
- representative compact `inspect_object` and `get_sketch_info` responses: less
  than 4 KB;
- representative compact `validate_parametric_model` and
  `edit_sketch_constraints` responses: less than 8 KB.

These are regression budgets for compact/default modes, not clipping rules.
Explicit topology, full validation, and paged sketch detail may be larger.

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
