# MCP Prompts

The server registers **14 MCP prompts** for compatibility, but prompt bodies are
intentionally small. Prompts are task routers or operation pointers; detailed
engineering policy lives only in `$freecad-engineering`.

Clients do not receive prompt bodies during MCP initialization. Use native
`prompts/list` / `prompts/get` when available, or `get_freecad_prompt()` as the
tool-surface fallback.

## Engineering routes

| Prompt | Parameters | Purpose |
| --- | --- | --- |
| `freecad_startup` | none | Minimal session bootstrap. |
| `reproduce_from_drawing` | `reference_path`, `target_document` | Route to drawing reconstruction + manufacturing reference. |
| `modify_existing_model` | `model_path`, `change_request`, `reference_path` | Route to edit-with-history or edit-without-history after inspection. |
| `freecad_guidance` | `task_type` | Return a compact Skill/reference route. |

## Compatibility prompt names

`design_part`, `create_sketch_guide`, `boolean_operations_guide`, `export_guide`,
`import_guide`, `analyze_shape`, `debug_model`, `macro_development`,
`python_api_reference`, and `troubleshooting` remain callable. They point to the
relevant tool schema or Skill route rather than maintaining separate workflow
prose.

## Source of truth

- Prompt definitions: `src/freecad_mcp/prompts/freecad.py`
- Engineering router: `.agents/skills/freecad-engineering/SKILL.md`
- MCP Skill URI: `freecad://skills/freecad-engineering`
