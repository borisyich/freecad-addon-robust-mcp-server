"""Compact MCP prompts that route tasks to the canonical engineering Skill.

Prompts intentionally do not contain a second copy of modeling policy. Tool
schemas define operation contracts; the Skill bundle defines engineering
workflow.
"""

from typing import Any, Literal

from freecad_mcp.guidance import (
    DRAWING_RECONSTRUCTION_WORKFLOW,
    ENGINEERING_SKILL_RESOURCE_URI,
    FINAL_PARAMETRIC_VALIDATION_TOOL,
    MODEL_MODIFICATION_WORKFLOW,
    VISUAL_CHECKPOINT_PROTOCOL,
)


def _reference(filename: str) -> str:
    return f"{ENGINEERING_SKILL_RESOURCE_URI}/references/{filename}"


def _route(*references: str) -> str:
    lines = [
        "Use `$freecad-engineering`.",
        f"Router: `{ENGINEERING_SKILL_RESOURCE_URI}`.",
    ]
    if references:
        lines.append("Read only these task references:")
        lines.extend(f"- `{_reference(name)}`" for name in references)
    lines.append(
        f"After geometry changes, verify the requested result and run "
        f"`{FINAL_PARAMETRIC_VALIDATION_TOOL}` before the final response."
    )
    return "\n".join(lines)


def register_prompts(mcp: Any, get_bridge: Any) -> None:  # noqa: ARG001
    """Register compact task routers and compatibility prompt names."""

    @mcp.prompt()
    async def freecad_startup() -> str:
        """Return the minimal FreeCAD engineering-session bootstrap."""
        return """# FreeCAD engineering session

1. Inspect the current FreeCAD connection/document before creating anything.
2. Read `freecad://skills/freecad-engineering` and route the task there.
3. Load only the reference file(s) selected by that router.
4. Use tool schemas for operation arguments; do not load generic guides first.
5. Work in ACT → OBSERVE → REACT steps and verify the requested result.
6. Run `validate_parametric_model` before the final response after geometry changes.
"""

    @mcp.prompt()
    async def reproduce_from_drawing(
        reference_path: str = "",
        target_document: str = "",
    ) -> str:
        """Route drawing reconstruction to the drawing and manufacturing skills."""
        context = (
            f"Reference: {reference_path or '(provided by client)'}\n"
            f"Target document: {target_document or '(inspect/reuse intended document)'}\n\n"
        )
        return context + DRAWING_RECONSTRUCTION_WORKFLOW

    @mcp.prompt()
    async def modify_existing_model(
        model_path: str = "",
        change_request: str = "",
        reference_path: str = "",
    ) -> str:
        """Route model edits according to whether construction history exists."""
        context = (
            f"Model: {model_path or '(current/imported model)'}\n"
            f"Requested change: {change_request or '(user request)'}\n"
            f"Reference: {reference_path or '(none)'}\n\n"
        )
        return context + MODEL_MODIFICATION_WORKFLOW

    @mcp.prompt()
    async def freecad_guidance(task_type: str = "general") -> str:
        """Return a compact route for a task type; use tool schemas for syntax."""
        routes = {
            "general": _route(),
            "text_modeling": _route("model-from-text.md"),
            "drawing_reconstruction": _route("model-from-drawing.md"),
            "machining": _route("machined-and-additive-parts.md"),
            "additive": _route("machined-and-additive-parts.md"),
            "sheet_metal": _route("sheet-metal-parts.md"),
            "edit_with_history": _route("edit-with-history.md"),
            "edit_without_history": _route("edit-without-history.md"),
            "engineering_drawing": _route("engineering-drawings.md"),
            "model_modification": MODEL_MODIFICATION_WORKFLOW,
            "visual_validation": VISUAL_CHECKPOINT_PROTOCOL,
            # Compatibility categories: exact operation syntax belongs to tools/list.
            "partdesign": _route(),
            "sketching": _route(),
            "boolean": _route(),
            "export": _route(),
            "debugging": _route(),
            "validation": _route(),
        }
        return routes.get(task_type, routes["general"])

    # Compatibility prompt names are intentionally thin. Existing clients can keep
    # calling them without carrying duplicate workflow prose in this module.

    @mcp.prompt()
    async def design_part(description: str, units: str = "mm") -> str:
        """Route creation of a new part from textual requirements."""
        return (
            f"Part request ({units}): {description}\n\n"
            + _route("model-from-text.md")
            + "\nAlso load the manufacturing reference selected by the Skill router."
        )

    @mcp.prompt()
    async def create_sketch_guide(
        shape_type: str = "rectangle",
        origin_plane: Literal["XY_Plane", "XZ_Plane", "YZ_Plane"] = "XY_Plane",
    ) -> str:
        """Point sketch creation to native tool schemas and the engineering router."""
        return (
            f"Create a {shape_type} sketch on "
            f'{{"kind": "origin_plane", "plane": "{origin_plane}"}}.\n'
            "Use `create_sketch`, `edit_sketch_geometry`, "
            "`edit_sketch_constraints`, and `get_sketch_info` schemas directly.\n\n"
            + _route()
        )

    @mcp.prompt()
    async def boolean_operations_guide() -> str:
        """Point boolean work to the boolean tool contract."""
        return "Use the `boolean_operation` tool schema for fuse/cut/common.\n\n" + _route()

    @mcp.prompt()
    async def export_guide(target_format: str = "STEP") -> str:
        """Point export work to the export tool contract."""
        return f"Export target: {target_format}. Use the `export` tool schema."

    @mcp.prompt()
    async def import_guide(source_format: str = "STEP") -> str:
        """Point import work to the import tool contract."""
        return (
            f"Import source: {source_format}. Use the `import_file` tool schema. "
            "If geometry will be edited without history, read "
            f"`{_reference('edit-without-history.md')}`."
        )

    @mcp.prompt()
    async def analyze_shape() -> str:
        """Point shape analysis to inspection and measurement tools."""
        return (
            "Use `inspect_object`, `select_subshapes`, `measure_geometry`, and the "
            "specific measurement tools. Request expanded detail only when needed."
        )

    @mcp.prompt()
    async def debug_model() -> str:
        """Point model debugging to console, inspection and validation tools."""
        return (
            "Inspect the first failing object/feature with `get_console_output`, "
            "`inspect_object`, `validate_object`, and `validate_document`; rework the "
            "causal operation instead of layering fixes."
        )

    @mcp.prompt()
    async def macro_development() -> str:
        """Point macro work to the macro tool family."""
        return (
            "Use `create_macro`, `read_macro`, `run_macro`, and `delete_macro`. "
            "Macro code is an implementation mechanism, not a substitute for the "
            "engineering workflow selected by `$freecad-engineering`."
        )

    @mcp.prompt()
    async def python_api_reference() -> str:
        """Return a minimal pointer for Python fallback work."""
        return (
            "Prefer native MCP tools. When Python is required, use `execute_python` "
            "or `safe_execute`, inspect existing FreeCAD object types/properties first, "
            "and create native document objects when editability is required."
        )

    @mcp.prompt()
    async def troubleshooting() -> str:
        """Return the minimal troubleshooting sequence."""
        return (
            "Check connection → console errors → active document/object → recompute → "
            "first invalid feature → undo/rework causal step. Use `validate_document` "
            "for geometry health and `validate_parametric_model` for final structure."
        )
