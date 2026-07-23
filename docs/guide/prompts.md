# MCP Prompts

The server currently registers **14 MCP prompts**. Prompts are reusable context
templates; discovery does not guarantee that a client automatically invokes or
inserts them. Durable repository routing therefore remains in `AGENTS.md` for
Codex and `.clinerules/` for Cline, while detailed modeling policy lives in the
`$freecad-engineering` Skill.

## Engineering routes

| Prompt | Parameters | Purpose |
| --- | --- | --- |
| `freecad_startup` | none | Session bootstrap; routes mechanical modeling tasks to `$freecad-engineering` and requires final `validate_parametric_model` reporting. |
| `reproduce_from_drawing` | `reference_path`, `target_document` | Adds drawing-task context and routes to the canonical Skill. |
| `modify_existing_model` | `model_path`, `change_request`, `reference_path` | Adds existing-model context and routes to the canonical Skill. |
| `freecad_guidance` | `task_type` | Returns compact guidance for general, PartDesign, sketching, boolean, export, debugging, validation, drawing, modification, or visual-check tasks. |

## Task guides

| Prompt | Parameters | Purpose |
| --- | --- | --- |
| `design_part` | `description`, `units` | Produces a concise PartDesign-oriented plan for a requested part. |
| `create_sketch_guide` | `shape_type`, `plane` | Guides creation and constraint of a sketch. |
| `boolean_operations_guide` | none | Guides validation and execution of boolean operations. |
| `export_guide` | `target_format` | Guides pre-export validation and format selection. |
| `import_guide` | `source_format` | Guides import and post-import inspection. |
| `analyze_shape` | none | Guides geometry/property analysis without treating it as drawing verification. |
| `debug_model` | none | Provides a diagnostic sequence for broken or unexpected geometry. |
| `macro_development` | none | Guides FreeCAD macro creation; macros remain available for model tasks. |
| `python_api_reference` | none | Provides a focused FreeCAD Python API reminder. |
| `troubleshooting` | none | Provides structured troubleshooting for connection, GUI, geometry, or API failures. |

## Source of truth

- Exact prompt definitions: `src/freecad_mcp/prompts/freecad.py`
- Canonical engineering policy: `.agents/skills/freecad-engineering/SKILL.md`
- Same Skill through MCP when running from a repository checkout:
  `freecad://skills/freecad-engineering`

Prompts intentionally do not duplicate the full Skill. If a prompt and the Skill
appear to differ on mechanical-modeling policy, use the Skill and report the
document with `validate_parametric_model` before the final response.
