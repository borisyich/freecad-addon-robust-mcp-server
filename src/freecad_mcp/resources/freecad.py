"""FreeCAD Robust MCP resources for exposing FreeCAD state.

This module provides MCP resources that expose FreeCAD's current state
as read-only data. Resources are URI-addressable data that MCP-compatible
assistants can access to understand the current FreeCAD environment.

Resource URIs:
    - freecad://capabilities - Curated capability overview and usage patterns
    - freecad://version - FreeCAD version information
    - freecad://status - Connection and runtime status
    - freecad://documents - List of open documents
    - freecad://documents/{name} - Single document details
    - freecad://documents/{name}/objects - Objects in a document
    - freecad://objects/{doc_name}/{obj_name} - Object details
    - freecad://active-document - Currently active document
    - freecad://skills/freecad-engineering - Canonical engineering Skill
    - freecad://skills/freecad-engineering/bundle - Complete Skill bundle index
    - freecad://skills/freecad-engineering/agents/openai.yaml - Skill metadata
    - freecad://skills/freecad-engineering/references/*.md - Skill references
    - freecad://best-practices - Compact Skill/validator index
    - freecad://workflows/drawing-reconstruction - Drawing-task Skill route
    - freecad://workflows/model-modification - Existing-model Skill route
    - freecad://workbenches - Available workbenches
    - freecad://workbenches/active - Currently active workbench
    - freecad://macros - Available macros
    - freecad://console - Recent console output
"""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from freecad_mcp.guidance import (
    DRAWING_RECONSTRUCTION_WORKFLOW,
    ENGINEERING_SKILL_AGENT_METADATA_FILE,
    ENGINEERING_SKILL_BUNDLE_RELATIVE_PATH,
    ENGINEERING_SKILL_BUNDLE_RESOURCE_URI,
    ENGINEERING_SKILL_REFERENCE_FILES,
    ENGINEERING_SKILL_RELATIVE_PATH,
    ENGINEERING_SKILL_RESOURCE_URI,
    FINAL_PARAMETRIC_VALIDATION_TOOL,
    MODEL_MODIFICATION_WORKFLOW,
)


def register_resources(mcp: Any, get_bridge: Any) -> None:
    """Register FreeCAD resources with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.resource("freecad://version")
    async def resource_version() -> str:
        """Get FreeCAD version and build information.

        Returns:
            JSON string containing:
                - version: FreeCAD version string
                - build_date: Build timestamp
                - python_version: Python interpreter version
                - gui_available: Whether GUI mode is active
        """
        bridge = await get_bridge()
        version_info = await bridge.get_freecad_version()
        return json.dumps(version_info, indent=2)

    @mcp.resource("freecad://status")
    async def resource_status() -> str:
        """Get current FreeCAD connection and runtime status.

        Returns:
            JSON string containing:
                - connected: Connection state
                - mode: Bridge mode (embedded, xmlrpc, socket)
                - freecad_version: Version string
                - gui_available: GUI availability
                - last_ping_ms: Connection latency
                - error: Any error message
        """
        bridge = await get_bridge()
        status = await bridge.get_status()
        return json.dumps(
            {
                "connected": status.connected,
                "mode": status.mode,
                "freecad_version": status.freecad_version,
                "gui_available": status.gui_available,
                "last_ping_ms": status.last_ping_ms,
                "error": status.error,
            },
            indent=2,
        )

    @mcp.resource("freecad://documents")
    async def resource_documents() -> str:
        """Get list of all open FreeCAD documents.

        Returns:
            JSON string containing list of documents, each with:
                - name: Internal document name
                - label: Display label
                - path: File path (null if unsaved)
                - object_count: Number of objects
                - is_modified: Has unsaved changes
                - active_object: Currently selected object
        """
        bridge = await get_bridge()
        docs = await bridge.get_documents()
        doc_list = [
            {
                "name": doc.name,
                "label": doc.label,
                "path": doc.path,
                "object_count": len(doc.objects),
                "is_modified": doc.is_modified,
                "active_object": doc.active_object,
            }
            for doc in docs
        ]
        return json.dumps(doc_list, indent=2)

    @mcp.resource("freecad://documents/{name}")
    async def resource_document(name: str) -> str:
        """Get detailed information about a specific document.

        Args:
            name: Document name to query.

        Returns:
            JSON string containing:
                - name: Internal document name
                - label: Display label
                - path: File path (null if unsaved)
                - objects: List of object names
                - is_modified: Has unsaved changes
                - active_object: Currently selected object
        """
        bridge = await get_bridge()
        docs = await bridge.get_documents()

        for doc in docs:
            if doc.name == name:
                return json.dumps(
                    {
                        "name": doc.name,
                        "label": doc.label,
                        "path": doc.path,
                        "objects": doc.objects,
                        "is_modified": doc.is_modified,
                        "active_object": doc.active_object,
                    },
                    indent=2,
                )

        return json.dumps({"error": f"Document '{name}' not found"}, indent=2)

    @mcp.resource("freecad://documents/{name}/objects")
    async def resource_document_objects(name: str) -> str:
        """Get list of objects in a specific document.

        Args:
            name: Document name to query.

        Returns:
            JSON string containing list of objects, each with:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier
                - visibility: Whether object is visible
        """
        bridge = await get_bridge()
        objects = await bridge.get_objects(doc_name=name)
        obj_list = [
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "visibility": obj.visibility,
            }
            for obj in objects
        ]
        return json.dumps(obj_list, indent=2)

    @mcp.resource("freecad://objects/{doc_name}/{obj_name}")
    async def resource_object(doc_name: str, obj_name: str) -> str:
        """Get detailed information about a specific object.

        Args:
            doc_name: Document containing the object.
            obj_name: Object name to query.

        Returns:
            JSON string containing:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier
                - properties: Dictionary of property values
                - shape_info: Shape geometry (if applicable)
                - children: Dependent object names
                - parents: Parent object names
                - visibility: Display visibility
        """
        bridge = await get_bridge()
        obj = await bridge.get_object(obj_name, doc_name=doc_name)

        # Filter properties to only include serializable values
        safe_properties = _make_json_safe(obj.properties)

        return json.dumps(
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "properties": safe_properties,
                "shape_info": obj.shape_info,
                "children": obj.children,
                "parents": obj.parents,
                "visibility": obj.visibility,
            },
            indent=2,
        )

    @mcp.resource("freecad://workbenches")
    async def resource_workbenches() -> str:
        """Get list of available FreeCAD workbenches.

        Returns:
            JSON string containing list of workbenches, each with:
                - name: Workbench internal name
                - label: Display label
                - is_active: Whether currently active
        """
        bridge = await get_bridge()
        workbenches = await bridge.get_workbenches()
        wb_list = [
            {
                "name": wb.name,
                "label": wb.label,
                "is_active": wb.is_active,
            }
            for wb in workbenches
        ]
        return json.dumps(wb_list, indent=2)

    @mcp.resource("freecad://workbenches/active")
    async def resource_active_workbench() -> str:
        """Get the currently active workbench.

        Returns:
            JSON string containing active workbench info or null.
        """
        bridge = await get_bridge()
        workbenches = await bridge.get_workbenches()
        for wb in workbenches:
            if wb.is_active:
                return json.dumps(
                    {
                        "name": wb.name,
                        "label": wb.label,
                    },
                    indent=2,
                )
        return json.dumps(None)

    @mcp.resource("freecad://macros")
    async def resource_macros() -> str:
        """Get list of available FreeCAD macros.

        Returns:
            JSON string containing list of macros, each with:
                - name: Macro name (without extension)
                - path: Full file path
                - description: Macro description
                - is_system: Whether it's a system macro
        """
        bridge = await get_bridge()
        macros = await bridge.get_macros()
        macro_list = [
            {
                "name": macro.name,
                "path": macro.path,
                "description": macro.description,
                "is_system": macro.is_system,
            }
            for macro in macros
        ]
        return json.dumps(macro_list, indent=2)

    @mcp.resource("freecad://console")
    async def resource_console() -> str:
        """Get recent FreeCAD console output.

        Returns:
            JSON string containing:
                - lines: List of console output lines
                - count: Number of lines
        """
        bridge = await get_bridge()
        lines = await bridge.get_console_output(lines=100)
        return json.dumps(
            {
                "lines": lines,
                "count": len(lines),
            },
            indent=2,
        )

    @mcp.resource("freecad://active-document")
    async def resource_active_document() -> str:
        """Get the currently active document.

        Returns:
            JSON string containing active document info or null.
        """
        bridge = await get_bridge()
        doc = await bridge.get_active_document()
        if doc is None:
            return json.dumps(None)
        return json.dumps(
            {
                "name": doc.name,
                "label": doc.label,
                "path": doc.path,
                "objects": doc.objects,
                "is_modified": doc.is_modified,
                "active_object": doc.active_object,
            },
            indent=2,
        )

    def _engineering_skill_file_text(relative_path: str) -> str:
        """Read one canonical Skill-bundle file from package or checkout."""
        packaged_path = files("freecad_mcp").joinpath(
            "skills", "freecad-engineering", *Path(relative_path).parts
        )
        try:
            return packaged_path.read_text(encoding="utf-8")
        except OSError:
            repo_root = Path(__file__).resolve().parents[3]
            skill_path = (
                repo_root / ENGINEERING_SKILL_BUNDLE_RELATIVE_PATH / relative_path
            )
            try:
                return skill_path.read_text(encoding="utf-8")
            except OSError as exc:
                expected = f"{ENGINEERING_SKILL_BUNDLE_RELATIVE_PATH}/{relative_path}"
                return (
                    "# FreeCAD engineering skill resource unavailable\n\n"
                    f"Expected `{expected}` but it could not be read: {exc}"
                )

    def _engineering_skill_text() -> str:
        """Read the canonical engineering Skill entrypoint."""
        return _engineering_skill_file_text("SKILL.md")

    def _engineering_skill_bundle_manifest() -> dict[str, Any]:
        """Describe every canonical Skill-bundle file exposed through MCP."""
        files_manifest = [
            {
                "path": "SKILL.md",
                "uri": ENGINEERING_SKILL_RESOURCE_URI,
                "role": "skill",
            },
            {
                "path": ENGINEERING_SKILL_AGENT_METADATA_FILE,
                "uri": (
                    f"{ENGINEERING_SKILL_RESOURCE_URI}/"
                    f"{ENGINEERING_SKILL_AGENT_METADATA_FILE}"
                ),
                "role": "agent_metadata",
            },
        ]
        files_manifest.extend(
            {
                "path": f"references/{filename}",
                "uri": f"{ENGINEERING_SKILL_RESOURCE_URI}/references/{filename}",
                "role": "reference",
            }
            for filename in ENGINEERING_SKILL_REFERENCE_FILES
        )
        return {
            "name": "freecad-engineering",
            "canonical_path": ENGINEERING_SKILL_BUNDLE_RELATIVE_PATH,
            "entrypoint": ENGINEERING_SKILL_RESOURCE_URI,
            "files": files_manifest,
        }

    def _register_engineering_skill_file(
        uri: str, relative_path: str, description: str
    ) -> None:
        """Expose one static Skill-bundle file as an MCP resource."""

        async def resource_skill_file() -> str:
            return _engineering_skill_file_text(relative_path)

        resource_skill_file.__name__ = (
            "resource_engineering_skill_"
            + relative_path.replace("/", "_").replace(".", "_")
        )
        resource_skill_file.__doc__ = description
        mcp.resource(uri)(resource_skill_file)

    @mcp.resource("freecad://skills/freecad-engineering/bundle")
    async def resource_engineering_skill_bundle() -> str:
        """Return the MCP URI manifest for the complete engineering Skill bundle."""
        return json.dumps(_engineering_skill_bundle_manifest(), indent=2)

    @mcp.resource("freecad://skills/freecad-engineering")
    async def resource_engineering_skill() -> str:
        """Return the canonical FreeCAD engineering Skill text."""
        return _engineering_skill_text()

    _register_engineering_skill_file(
        f"{ENGINEERING_SKILL_RESOURCE_URI}/{ENGINEERING_SKILL_AGENT_METADATA_FILE}",
        ENGINEERING_SKILL_AGENT_METADATA_FILE,
        "OpenAI agent metadata for the canonical FreeCAD engineering Skill.",
    )
    for _reference_file in ENGINEERING_SKILL_REFERENCE_FILES:
        _register_engineering_skill_file(
            f"{ENGINEERING_SKILL_RESOURCE_URI}/references/{_reference_file}",
            f"references/{_reference_file}",
            f"Canonical FreeCAD engineering Skill reference: {_reference_file}.",
        )

    @mcp.resource("freecad://best-practices")
    async def resource_best_practices() -> str:
        """Return a compact index to the canonical engineering Skill."""
        return json.dumps(
            {
                "description": "FreeCAD engineering guidance index",
                "canonical_skill": ENGINEERING_SKILL_RELATIVE_PATH,
                "canonical_resource": ENGINEERING_SKILL_RESOURCE_URI,
                "mandatory_final_diagnostic": FINAL_PARAMETRIC_VALIDATION_TOOL,
                "notes": [
                    "The Skill is the single source of detailed modeling policy.",
                    "execute_python, safe_execute, and run_macro remain available.",
                    "The final validator is informative and does not prove drawing correspondence.",
                ],
            },
            indent=2,
        )

    @mcp.resource("freecad://workflows/drawing-reconstruction")
    async def resource_drawing_reconstruction() -> str:
        """Route drawing reconstruction tasks to the canonical Skill."""
        return DRAWING_RECONSTRUCTION_WORKFLOW

    @mcp.resource("freecad://workflows/model-modification")
    async def resource_model_modification() -> str:
        """Route existing-model changes to the canonical Skill."""
        return MODEL_MODIFICATION_WORKFLOW

    @mcp.resource("freecad://capabilities")
    async def resource_capabilities() -> str:
        """Return a compact discovery index; exact contracts come from tools/list."""
        resources = [
            {"uri": "freecad://capabilities", "description": "Compact discovery index"},
            {"uri": ENGINEERING_SKILL_RESOURCE_URI, "description": "Engineering task router"},
            {"uri": ENGINEERING_SKILL_BUNDLE_RESOURCE_URI, "description": "Skill bundle manifest"},
            {
                "uri": f"{ENGINEERING_SKILL_RESOURCE_URI}/{ENGINEERING_SKILL_AGENT_METADATA_FILE}",
                "description": "Skill agent metadata",
            },
            *[
                {
                    "uri": f"{ENGINEERING_SKILL_RESOURCE_URI}/references/{filename}",
                    "description": f"Engineering workflow: {filename}",
                }
                for filename in ENGINEERING_SKILL_REFERENCE_FILES
            ],
            {"uri": "freecad://best-practices", "description": "Compatibility pointer to the Skill"},
            {"uri": "freecad://workflows/drawing-reconstruction", "description": "Compatibility drawing route"},
            {"uri": "freecad://workflows/model-modification", "description": "Compatibility edit route"},
            {"uri": "freecad://version", "description": "FreeCAD version"},
            {"uri": "freecad://status", "description": "Connection/runtime status"},
            {"uri": "freecad://documents", "description": "Open documents"},
            {"uri": "freecad://documents/{name}", "description": "Document details"},
            {"uri": "freecad://documents/{name}/objects", "description": "Document objects"},
            {"uri": "freecad://objects/{doc_name}/{obj_name}", "description": "Object details"},
            {"uri": "freecad://active-document", "description": "Active document"},
            {"uri": "freecad://workbenches", "description": "Available workbenches"},
            {"uri": "freecad://workbenches/active", "description": "Active workbench"},
            {"uri": "freecad://macros", "description": "Available macros"},
            {"uri": "freecad://console", "description": "Recent FreeCAD console output"},
        ]
        prompt_names = [
            "freecad_startup",
            "reproduce_from_drawing",
            "modify_existing_model",
            "freecad_guidance",
            "design_part",
            "create_sketch_guide",
            "boolean_operations_guide",
            "export_guide",
            "import_guide",
            "analyze_shape",
            "debug_model",
            "macro_development",
            "python_api_reference",
            "troubleshooting",
        ]
        return json.dumps(
            {
                "description": (
                    "Compact discovery index. Use tools/list for exact tool schemas and "
                    "the engineering Skill for workflow policy."
                ),
                "tools": {
                    "documents": "Document lifecycle and history",
                    "modeling": "PartDesign, Part/B-rep, Draft and SheetMetal operations",
                    "inspection": "Object/subshape inspection and measurements",
                    "validation": "Geometry, parametric and shape-checkpoint diagnostics",
                    "images": "Screenshots, image inspection and comparison",
                    "execution": "Python/macro fallback and FreeCAD console diagnostics",
                    "io": "Import/export",
                },
                "resources": resources,
                "prompts": [{"name": name} for name in prompt_names],
            },
            indent=2,
        )


def _make_json_safe(obj: Any) -> Any:
    """Convert an object to be JSON serializable.

    Args:
        obj: Object to convert.

    Returns:
        JSON-safe representation of the object.
    """
    if obj is None:
        return None
    if isinstance(obj, str | int | float | bool):
        return obj
    if isinstance(obj, list | tuple):
        return [_make_json_safe(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    # Convert other types to string representation
    return str(obj)
