"""FreeCAD Robust MCP resources for exposing FreeCAD state.

This module provides MCP resources that expose FreeCAD's current state
as read-only data. Resources are URI-addressable data that Claude can
access to understand the current FreeCAD environment.

Resource URIs:
    - freecad://capabilities - Complete list of all available tools/resources
    - freecad://version - FreeCAD version information
    - freecad://status - Connection and runtime status
    - freecad://documents - List of open documents
    - freecad://documents/{name} - Single document details
    - freecad://documents/{name}/objects - Objects in a document
    - freecad://objects/{doc_name}/{obj_name} - Object details
    - freecad://active-document - Currently active document
    - freecad://best-practices - Canonical engineering guidance
    - freecad://workflows/drawing-reconstruction - Drawing reconstruction workflow
    - freecad://workflows/model-modification - Existing-model modification workflow
    - freecad://workbenches - Available workbenches
    - freecad://workbenches/active - Currently active workbench
    - freecad://macros - Available macros
    - freecad://console - Recent console output
"""

import json
from typing import Any

from freecad_mcp.guidance import (
    BLOCKING_DISCREPANCY_CATEGORIES,
    DISCREPANCY_LEDGER_FIELDS,
    DRAWING_RECONSTRUCTION_WORKFLOW,
    MODEL_MODIFICATION_WORKFLOW,
    UNCERTAINTY_CATEGORIES,
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

    @mcp.resource("freecad://best-practices")
    async def resource_best_practices() -> str:
        """Get FreeCAD best practices and AI guidance.

        This resource provides comprehensive guidance for AI assistants
        working with FreeCAD, covering API patterns, version compatibility,
        validation workflows, and common pitfalls.

        Use this resource at the start of a FreeCAD session to understand
        best practices for reliable CAD operations.

        Returns:
            JSON string containing best practices and guidance.

        Example:
            Read via MCP resource mechanism::

                # In an MCP client
                best_practices = await mcp.read_resource("freecad://best-practices")
                data = json.loads(best_practices)
                print(data["critical_patterns"])  # Shows validation_first, partdesign_workflow
        """
        best_practices = {
            "description": "FreeCAD Best Practices and AI Guidance",
            "purpose": (
                "Reference for reliable parametric modeling, drawing reconstruction, "
                "existing-model modification, validation, and rollback"
            ),
            "delivery_note": {
                "important": (
                    "MCP resources and prompts are exposed to the client but are not "
                    "guaranteed to be inserted automatically into every model turn."
                ),
                "client_bootstrap_files": {
                    "Codex": "AGENTS.md",
                    "Cline": ".clinerules/freecad-modeling.md",
                    "repository_agents": ".agents/AGENT.md",
                    "Claude/project development": "CLAUDE.md",
                },
                "task_prompts": [
                    "freecad_startup",
                    "reproduce_from_drawing",
                    "modify_existing_model",
                    "freecad_guidance",
                ],
            },
            "critical_patterns": {
                "validation_first": {
                    "description": (
                        "Validate geometry after every major feature, but do not confuse "
                        "shape validity with requirement correctness."
                    ),
                    "pattern": [
                        "recompute the document",
                        "validate the new feature and document",
                        "confirm Body Tip and solid count",
                        "confirm positive added/removed volume and expected bounds",
                        "run same-view visual correspondence checks",
                    ],
                    "tools": [
                        "validate_object",
                        "validate_document",
                        "inspect_object",
                        "get_screenshot",
                        "compare_images",
                        "evaluate_model_checkpoint",
                    ],
                },
                "partdesign_workflow": {
                    "description": "Proper parametric PartDesign workflow",
                    "rules": [
                        "reuse one explicit document",
                        "use one PartDesign Body per part and keep one contiguous solid",
                        "centralize key dimensions in Spreadsheet aliases or named constraints",
                        "build additive blank before cuts; fillets/chamfers last",
                        "pass explicit world-space directions for direction-sensitive features",
                        "do not guess FaceN/EdgeN; select by geometry",
                    ],
                    "sequence": [
                        "create_document or reuse intended document",
                        "create_partdesign_body",
                        "create and constrain sketch",
                        "create one feature",
                        "validate geometry",
                        "perform visual checkpoint",
                    ],
                    "tools": [
                        "create_partdesign_body",
                        "create_sketch",
                        "pad_sketch",
                        "pocket_sketch",
                    ],
                },
                "transaction_safety": {
                    "description": "Rollback the failed operation, not the entire design",
                    "rules": [
                        "all modifying tools are transactional and support undo",
                        "on failure undo/delete only the failed feature",
                        "confirm the previous valid Body Tip/state is restored",
                        "do not create duplicate documents or Bodies to hide errors",
                        "safe_execute/execute_python are fallback mechanisms only",
                    ],
                    "tools": [
                        "undo",
                        "redo",
                        "undo_if_invalid",
                        "get_undo_redo_status",
                        "safe_execute",
                    ],
                },
                "act_observe_react": {
                    "description": "Mandatory checkpoint after each major feature",
                    "act": "Create exactly one logically reviewable feature and recompute.",
                    "observe_geometry": [
                        "validate shape and document",
                        "check Body Tip and solid count",
                        "check dimensions, bounds, placement, and volume effect",
                    ],
                    "observe_visual": [
                        "use a reference crop, not the whole sheet",
                        "set an equivalent candidate view",
                        "save/open screenshot and call compare_images",
                        "write a discrepancy ledger",
                    ],
                    "react": (
                        "Call evaluate_model_checkpoint and obey continue/rework."
                    ),
                    "ledger_fields": list(DISCREPANCY_LEDGER_FIELDS),
                },
            },
            "drawing_reconstruction": {
                "resource": "freecad://workflows/drawing-reconstruction",
                "prompt": "reproduce_from_drawing",
                "blocking_discrepancy_categories": sorted(
                    BLOCKING_DISCREPANCY_CATEGORIES
                ),
                "uncertainty_categories": sorted(UNCERTAINTY_CATEGORIES),
                "requirements": [
                    "open the source pixels with open_image",
                    "create an evidence table before modeling",
                    "compare equivalent views only",
                    "stop rather than invent unreadable dimensions",
                    "accept feature by feature, not by overall resemblance",
                ],
            },
            "model_modification": {
                "resource": "freecad://workflows/model-modification",
                "prompt": "modify_existing_model",
                "requirements": [
                    "inspect history, constraints, expressions, dependencies, and Tip",
                    "modify the earliest semantic owner of the requested change",
                    "prefer parameter/constraint edits over appended workaround geometry",
                    "record baseline invariants before editing",
                    "verify requested change and absence of regressions",
                ],
            },
            "tool_selection_policy": {
                "priority": [
                    "standard domain-specific MCP tool",
                    "standard generic MCP tool",
                    "safe_execute for one missing/invalid operation",
                    "execute_python only as a last-resort diagnostic or unsupported operation",
                ],
                "fallback_requirements": [
                    "state why the standard tool is insufficient",
                    "limit code to one operation",
                    "validate immediately",
                    "preserve parametric design intent",
                ],
            },
            "version_compatibility": {
                "description": "FreeCAD API changes across versions",
                "critical_changes": {
                    "sketch_attachment": {
                        "versions_affected": "FreeCAD 1.0+ vs earlier",
                        "old_api": "sketch.Support = (plane_obj, [''])",
                        "new_api": "sketch.AttachmentSupport = [(plane_obj, '')]",
                        "note": "MCP tools handle this compatibility layer.",
                    },
                    "body_object_creation": {
                        "correct": (
                            "body.newObject('Sketcher::SketchObject', 'Sketch')"
                        ),
                        "incorrect": "doc.addObject(...); body.addObject(sketch)",
                    },
                },
            },
            "gui_vs_headless": {
                "description": "Visual checkpoints require a GUI-enabled FreeCAD session",
                "check_gui": "Use get_freecad_version() and inspect gui_available",
                "gui_only_features": [
                    "get_screenshot",
                    "view/camera controls",
                    "visibility/color/display controls",
                ],
                "headless_safe_features": [
                    "document and object operations",
                    "validation and inspection",
                    "import/export",
                ],
            },
            "common_pitfalls": {
                "standalone_features": {
                    "problem": "PartDesign features outside a Body",
                    "solution": "Create features inside one intended Body.",
                },
                "valid_but_wrong": {
                    "problem": "Shape is valid but differs from the drawing",
                    "solution": (
                        "Run geometric and visual/requirement validation as separate gates."
                    ),
                },
                "whole_sheet_comparison": {
                    "problem": "Candidate compared with an entire drawing sheet",
                    "solution": "Crop and compare one equivalent view at a time.",
                },
                "observation_without_reaction": {
                    "problem": "Screenshot is inspected but the plan continues unchanged",
                    "solution": (
                        "Write a discrepancy ledger and call evaluate_model_checkpoint."
                    ),
                },
                "unconstrained_sketches": {
                    "problem": "Sketches have unintended degrees of freedom",
                    "solution": "Inspect sketch status and constrain design intent.",
                },
                "document_state": {
                    "problem": "Wrong document or duplicate Body modified",
                    "solution": "Pass doc_name explicitly and reuse the intended state.",
                },
            },
            "recommended_workflows": {
                "creating_parts": {
                    "steps": [
                        "inspect/reuse document",
                        "create Body and parameter table",
                        "build additive blank",
                        "checkpoint each feature",
                        "perform cuts",
                        "apply finishing features",
                        "final feature-by-feature acceptance",
                    ],
                },
                "modifying_existing": {
                    "steps": [
                        "inspect current model and dependencies",
                        "record baseline invariants",
                        "edit semantic owner",
                        "validate and compare",
                        "rework or accept",
                        "save",
                    ],
                },
                "debugging_issues": {
                    "steps": [
                        "get_console_output",
                        "validate_document",
                        "inspect_object and dependencies",
                        "undo failed operation",
                        "confirm previous Tip/state",
                        "retry with corrected cause",
                    ],
                },
            },
            "error_recovery": {
                "invalid_geometry": [
                    "undo failed feature",
                    "confirm previous valid state",
                    "diagnose support/direction/parameters",
                    "retry one corrected feature",
                ],
                "visual_mismatch": [
                    "do not continue to the next feature",
                    "classify discrepancy",
                    "undo/rework current feature",
                    "repeat same-view checkpoint",
                ],
                "ambiguous_reference": [
                    "stop",
                    "identify exact unreadable or conflicting evidence",
                    "ask user",
                ],
            },
            "performance_tips": {
                "context": (
                    "Keep startup rules concise; load task-specific workflow only when needed."
                ),
                "images": (
                    "Use overview for layout and high-resolution crops for dimensions."
                ),
                "checkpoints": (
                    "One major feature per checkpoint limits rollback scope."
                ),
                "execution": (
                    "Do not batch unrelated operations in execute_python."
                ),
            },
        }
        return json.dumps(best_practices, indent=2)

    @mcp.resource("freecad://workflows/drawing-reconstruction")
    async def resource_drawing_reconstruction() -> str:
        """Get the canonical drawing-to-model workflow."""
        return json.dumps(
            {
                "description": "Mandatory workflow for reconstructing a model from drawings",
                "prompt": "reproduce_from_drawing",
                "workflow_markdown": DRAWING_RECONSTRUCTION_WORKFLOW,
                "blocking_categories": sorted(BLOCKING_DISCREPANCY_CATEGORIES),
                "uncertainty_categories": sorted(UNCERTAINTY_CATEGORIES),
                "ledger_fields": list(DISCREPANCY_LEDGER_FIELDS),
            },
            indent=2,
        )

    @mcp.resource("freecad://workflows/model-modification")
    async def resource_model_modification() -> str:
        """Get the canonical existing-model modification workflow."""
        return json.dumps(
            {
                "description": "Mandatory workflow for changing existing models",
                "prompt": "modify_existing_model",
                "workflow_markdown": MODEL_MODIFICATION_WORKFLOW,
            },
            indent=2,
        )

    @mcp.resource("freecad://capabilities")
    async def resource_capabilities() -> str:
        """Get comprehensive list of all MCP capabilities.

        This resource provides a complete catalog of all available tools,
        resources, and prompts. Use this to discover what functionality
        is available when working with the FreeCAD Robust MCP Server.

        Returns:
            JSON string containing:
                - tools: Dict of tool categories with tool definitions
                - resources: List of available resource URIs
                - prompts: List of available prompt names
                - examples: Common usage patterns
        """
        capabilities = {
            "description": "FreeCAD Robust MCP Server - Control FreeCAD via Model Context Protocol",
            "tools": {
                "execution": {
                    "description": "Execute Python code and access console",
                    "tools": [
                        {
                            "name": "execute_python",
                            "description": "Execute arbitrary Python code in FreeCAD's context. Use _result_ = value to return data.",
                            "key_params": ["code", "timeout_ms"],
                        },
                        {
                            "name": "get_console_output",
                            "description": "Get recent FreeCAD console output for debugging",
                            "key_params": ["lines"],
                        },
                        {
                            "name": "get_console_log",
                            "description": "Alternative console log access",
                            "key_params": ["lines"],
                        },
                        {
                            "name": "get_freecad_version",
                            "description": "Get FreeCAD version, build date, Python version",
                            "key_params": [],
                        },
                        {
                            "name": "get_connection_status",
                            "description": "Check MCP bridge connection status and latency",
                            "key_params": [],
                        },
                        {
                            "name": "get_mcp_server_environment",
                            "description": "Get Robust MCP Server environment info (instance_id, OS, hostname, FreeCAD connection)",
                            "key_params": [],
                        },
                    ],
                },
                "documents": {
                    "description": "Document management",
                    "tools": [
                        {
                            "name": "list_documents",
                            "description": "List all open FreeCAD documents",
                            "key_params": [],
                        },
                        {
                            "name": "get_active_document",
                            "description": "Get info about currently active document",
                            "key_params": [],
                        },
                        {
                            "name": "create_document",
                            "description": "Create a new FreeCAD document",
                            "key_params": ["name"],
                        },
                        {
                            "name": "open_document",
                            "description": "Open an existing .FCStd file",
                            "key_params": ["path"],
                        },
                        {
                            "name": "save_document",
                            "description": "Save document to disk",
                            "key_params": ["doc_name", "path"],
                        },
                        {
                            "name": "close_document",
                            "description": "Close a document",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "recompute_document",
                            "description": "Force recomputation of document features",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
                "objects": {
                    "description": "Object creation and manipulation",
                    "note": "All operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "list_objects",
                            "description": "List all objects in a document",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "inspect_object",
                            "description": "Get detailed info about an object",
                            "key_params": ["object_name", "doc_name"],
                        },
                        {
                            "name": "create_object",
                            "description": "Create generic FreeCAD object by type",
                            "key_params": ["type_id", "name", "properties"],
                        },
                        {
                            "name": "create_box",
                            "description": "Create Part::Box primitive",
                            "key_params": ["length", "width", "height"],
                        },
                        {
                            "name": "create_cylinder",
                            "description": "Create Part::Cylinder primitive",
                            "key_params": ["radius", "height"],
                        },
                        {
                            "name": "create_sphere",
                            "description": "Create Part::Sphere primitive",
                            "key_params": ["radius"],
                        },
                        {
                            "name": "create_cone",
                            "description": "Create Part::Cone primitive",
                            "key_params": ["radius1", "radius2", "height"],
                        },
                        {
                            "name": "create_torus",
                            "description": "Create Part::Torus primitive",
                            "key_params": ["radius1", "radius2"],
                        },
                        {
                            "name": "create_wedge",
                            "description": "Create Part::Wedge primitive",
                            "key_params": [
                                "xmin",
                                "xmax",
                                "ymin",
                                "ymax",
                                "zmin",
                                "zmax",
                            ],
                        },
                        {
                            "name": "create_helix",
                            "description": "Create Part::Helix primitive",
                            "key_params": ["pitch", "height", "radius"],
                        },
                        {
                            "name": "create_line",
                            "description": "Create Part::Line (edge between two points)",
                            "key_params": ["point1", "point2"],
                        },
                        {
                            "name": "create_plane",
                            "description": "Create Part::Plane (rectangular face)",
                            "key_params": ["length", "width"],
                        },
                        {
                            "name": "create_ellipse",
                            "description": "Create Part ellipse (2D shape)",
                            "key_params": ["major_radius", "minor_radius"],
                        },
                        {
                            "name": "create_prism",
                            "description": "Create Part::Prism (extruded polygon)",
                            "key_params": ["polygon", "height"],
                        },
                        {
                            "name": "create_regular_polygon",
                            "description": "Create regular polygon face",
                            "key_params": ["num_sides", "radius"],
                        },
                        {
                            "name": "boolean_operation",
                            "description": "Union, cut, or intersection of two shapes",
                            "key_params": ["operation", "object1", "object2"],
                        },
                        {
                            "name": "fuse_all",
                            "description": "Fuse multiple objects together",
                            "key_params": ["object_names"],
                        },
                        {
                            "name": "common_all",
                            "description": "Find intersection of multiple objects",
                            "key_params": ["object_names"],
                        },
                        {
                            "name": "shell_object",
                            "description": "Create hollow shell from solid",
                            "key_params": ["object_name", "thickness", "faces"],
                        },
                        {
                            "name": "offset_3d",
                            "description": "Offset object surface by distance",
                            "key_params": ["object_name", "offset"],
                        },
                        {
                            "name": "slice_shape",
                            "description": "Slice object with a plane",
                            "key_params": ["object_name", "plane"],
                        },
                        {
                            "name": "section_shape",
                            "description": "Get 2D section where plane intersects object",
                            "key_params": ["object_name", "plane"],
                        },
                        {
                            "name": "make_compound",
                            "description": "Group objects into a compound",
                            "key_params": ["object_names"],
                        },
                        {
                            "name": "explode_compound",
                            "description": "Split compound into individual objects",
                            "key_params": ["object_name"],
                        },
                        {
                            "name": "make_wire",
                            "description": "Create wire from edges/curves",
                            "key_params": ["object_names"],
                        },
                        {
                            "name": "make_face",
                            "description": "Create face from wire",
                            "key_params": ["wire_name"],
                        },
                        {
                            "name": "extrude_shape",
                            "description": "Extrude shape along vector",
                            "key_params": ["object_name", "direction", "length"],
                        },
                        {
                            "name": "revolve_shape",
                            "description": "Revolve shape around axis",
                            "key_params": ["object_name", "axis", "angle"],
                        },
                        {
                            "name": "part_loft",
                            "description": "Create Part loft between shapes",
                            "key_params": ["object_names", "solid"],
                        },
                        {
                            "name": "part_sweep",
                            "description": "Sweep profile along path",
                            "key_params": ["profile_name", "path_name"],
                        },
                        {
                            "name": "edit_object",
                            "description": "Modify object properties",
                            "key_params": ["object_name", "properties"],
                        },
                        {
                            "name": "delete_object",
                            "description": "Delete an object",
                            "key_params": ["object_name"],
                        },
                        {
                            "name": "set_placement",
                            "description": "Set object position and rotation",
                            "key_params": ["object_name", "x", "y", "z"],
                        },
                        {
                            "name": "scale_object",
                            "description": "Scale an object by a factor",
                            "key_params": ["object_name", "scale_factor"],
                        },
                        {
                            "name": "rotate_object",
                            "description": "Rotate object around an axis",
                            "key_params": ["object_name", "axis", "angle"],
                        },
                        {
                            "name": "copy_object",
                            "description": "Create a copy of an object",
                            "key_params": ["object_name"],
                        },
                        {
                            "name": "mirror_object",
                            "description": "Mirror object across a plane",
                            "key_params": ["object_name", "plane"],
                        },
                    ],
                },
                "selection": {
                    "description": "Selection management",
                    "tools": [
                        {
                            "name": "get_selection",
                            "description": "Get currently selected objects",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "set_selection",
                            "description": "Select specific objects",
                            "key_params": ["object_names"],
                        },
                        {
                            "name": "clear_selection",
                            "description": "Clear current selection",
                            "key_params": [],
                        },
                    ],
                },
                "partdesign": {
                    "description": "Parametric modeling with PartDesign workbench",
                    "note": "All operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "create_partdesign_body",
                            "description": "Create a PartDesign::Body container",
                            "key_params": ["name"],
                        },
                        {
                            "name": "create_sketch",
                            "description": "Create sketch on plane or face",
                            "key_params": ["body_name", "plane"],
                        },
                        {
                            "name": "add_sketch_rectangle",
                            "description": "Add rectangle to sketch",
                            "key_params": ["sketch_name", "x", "y", "width", "height"],
                        },
                        {
                            "name": "add_sketch_circle",
                            "description": "Add circle to sketch",
                            "key_params": ["sketch_name", "x", "y", "radius"],
                        },
                        {
                            "name": "add_sketch_line",
                            "description": "Add line to sketch",
                            "key_params": ["sketch_name", "x1", "y1", "x2", "y2"],
                        },
                        {
                            "name": "add_sketch_arc",
                            "description": "Add arc to sketch",
                            "key_params": [
                                "sketch_name",
                                "center_x",
                                "center_y",
                                "radius",
                            ],
                        },
                        {
                            "name": "add_sketch_point",
                            "description": "Add reference point to sketch",
                            "key_params": ["sketch_name", "x", "y"],
                        },
                        {
                            "name": "add_sketch_ellipse",
                            "description": "Add ellipse to sketch",
                            "key_params": [
                                "sketch_name",
                                "center_x",
                                "center_y",
                                "major_radius",
                                "minor_radius",
                            ],
                        },
                        {
                            "name": "add_sketch_polygon",
                            "description": "Add regular polygon to sketch",
                            "key_params": [
                                "sketch_name",
                                "center_x",
                                "center_y",
                                "sides",
                                "radius",
                            ],
                        },
                        {
                            "name": "add_sketch_slot",
                            "description": "Add slot (rounded rectangle) to sketch",
                            "key_params": [
                                "sketch_name",
                                "x1",
                                "y1",
                                "x2",
                                "y2",
                                "width",
                            ],
                        },
                        {
                            "name": "add_sketch_bspline",
                            "description": "Add B-spline curve to sketch",
                            "key_params": ["sketch_name", "points"],
                        },
                        {
                            "name": "pad_sketch",
                            "description": "Extrude sketch (additive)",
                            "key_params": ["sketch_name", "length"],
                        },
                        {
                            "name": "pocket_sketch",
                            "description": "Cut using sketch (subtractive)",
                            "key_params": ["sketch_name", "length"],
                        },
                        {
                            "name": "revolution_sketch",
                            "description": "Revolve sketch around axis",
                            "key_params": ["sketch_name", "axis", "angle"],
                        },
                        {
                            "name": "groove_sketch",
                            "description": "Cut by revolving sketch (subtractive revolve)",
                            "key_params": ["sketch_name", "axis", "angle"],
                        },
                        {
                            "name": "loft_sketches",
                            "description": "Create additive loft between sketches",
                            "key_params": ["sketch_names"],
                        },
                        {
                            "name": "subtractive_loft",
                            "description": "Create subtractive loft between sketches",
                            "key_params": ["sketch_names"],
                        },
                        {
                            "name": "sweep_sketch",
                            "description": "Additive sweep sketch along path",
                            "key_params": ["profile_sketch", "spine_sketch"],
                        },
                        {
                            "name": "subtractive_pipe",
                            "description": "Subtractive sweep sketch along path",
                            "key_params": ["profile_sketch", "spine_sketch"],
                        },
                        {
                            "name": "create_hole",
                            "description": (
                                "Create validated holes from a planar-face or "
                                "origin-plane circle sketch"
                            ),
                            "key_params": ["sketch_name", "diameter", "depth"],
                        },
                        {
                            "name": "create_cylindrical_cut",
                            "description": (
                                "Create a validated radial or off-face cylindrical "
                                "cut from an explicit axis"
                            ),
                            "key_params": [
                                "body_name",
                                "axis_origin",
                                "axis_direction",
                                "diameter",
                                "depth",
                            ],
                        },
                        {
                            "name": "fillet_edges",
                            "description": "Add fillets to edges",
                            "key_params": ["object_name", "radius", "edges"],
                        },
                        {
                            "name": "chamfer_edges",
                            "description": "Add chamfers to edges",
                            "key_params": ["object_name", "size", "edges"],
                        },
                        {
                            "name": "draft_feature",
                            "description": "Add draft angle to faces",
                            "key_params": ["object_name", "angle", "faces"],
                        },
                        {
                            "name": "thickness_feature",
                            "description": "Shell solid to hollow with thickness",
                            "key_params": [
                                "object_name",
                                "thickness",
                                "faces_to_remove",
                            ],
                        },
                        {
                            "name": "create_datum_plane",
                            "description": "Create reference plane for sketches",
                            "key_params": ["body_name", "offset", "plane"],
                        },
                        {
                            "name": "create_datum_line",
                            "description": "Create reference line/axis",
                            "key_params": ["body_name"],
                        },
                        {
                            "name": "create_datum_point",
                            "description": "Create reference point",
                            "key_params": ["body_name"],
                        },
                    ],
                },
                "patterns": {
                    "description": "Pattern and transform features",
                    "note": "All operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "linear_pattern",
                            "description": "Create linear pattern",
                            "key_params": [
                                "feature_name",
                                "direction",
                                "occurrences",
                                "length",
                            ],
                        },
                        {
                            "name": "polar_pattern",
                            "description": "Create circular/polar pattern",
                            "key_params": [
                                "feature_name",
                                "axis",
                                "occurrences",
                                "angle",
                            ],
                        },
                        {
                            "name": "mirrored_feature",
                            "description": "Mirror feature across plane",
                            "key_params": ["feature_name", "plane"],
                        },
                    ],
                },
                "spreadsheet": {
                    "description": "Spreadsheet workbench for parametric design",
                    "note": "All mutating operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "spreadsheet_create",
                            "description": "Create a new Spreadsheet object",
                            "key_params": ["name", "doc_name"],
                        },
                        {
                            "name": "spreadsheet_set_cell",
                            "description": "Set cell value (number, string, or formula)",
                            "key_params": ["spreadsheet_name", "cell", "value"],
                        },
                        {
                            "name": "spreadsheet_get_cell",
                            "description": "Get cell value and computed result",
                            "key_params": ["spreadsheet_name", "cell"],
                        },
                        {
                            "name": "spreadsheet_set_alias",
                            "description": "Set alias for parametric references",
                            "key_params": ["spreadsheet_name", "cell", "alias"],
                        },
                        {
                            "name": "spreadsheet_get_aliases",
                            "description": "Get all aliases in a spreadsheet",
                            "key_params": ["spreadsheet_name"],
                        },
                        {
                            "name": "spreadsheet_clear_cell",
                            "description": "Clear a cell and its alias",
                            "key_params": ["spreadsheet_name", "cell"],
                        },
                        {
                            "name": "spreadsheet_bind_property",
                            "description": "Bind object property to spreadsheet cell",
                            "key_params": [
                                "spreadsheet_name",
                                "alias",
                                "target_object",
                                "target_property",
                            ],
                        },
                        {
                            "name": "spreadsheet_get_cell_range",
                            "description": "Get values from a range of cells",
                            "key_params": [
                                "spreadsheet_name",
                                "start_cell",
                                "end_cell",
                            ],
                        },
                        {
                            "name": "spreadsheet_import_csv",
                            "description": "Import CSV data into spreadsheet",
                            "key_params": ["spreadsheet_name", "file_path"],
                        },
                        {
                            "name": "spreadsheet_export_csv",
                            "description": "Export spreadsheet to CSV file",
                            "key_params": ["spreadsheet_name", "file_path"],
                        },
                    ],
                },
                "draft": {
                    "description": "Draft workbench - ShapeString for 3D text",
                    "note": "All mutating operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "draft_shapestring",
                            "description": "Create 3D text geometry from string and font",
                            "key_params": ["text", "font_path", "size", "position"],
                        },
                        {
                            "name": "draft_list_fonts",
                            "description": "List available system fonts for ShapeString",
                            "key_params": [],
                        },
                        {
                            "name": "draft_shapestring_to_sketch",
                            "description": "Convert ShapeString to Sketch for PartDesign",
                            "key_params": ["shapestring_name", "body_name", "plane"],
                        },
                        {
                            "name": "draft_shapestring_to_face",
                            "description": "Convert ShapeString to Face for boolean ops",
                            "key_params": ["shapestring_name"],
                        },
                        {
                            "name": "draft_text_on_surface",
                            "description": "Emboss or engrave text on a surface",
                            "key_params": [
                                "text",
                                "target_face",
                                "target_object",
                                "depth",
                                "operation",
                            ],
                        },
                        {
                            "name": "draft_extrude_shapestring",
                            "description": "Extrude ShapeString to create 3D solid text",
                            "key_params": ["shapestring_name", "height", "direction"],
                        },
                    ],
                },
                "sketcher_constraints": {
                    "description": "Sketcher constraint tools for fully defining geometry",
                    "note": "All operations are wrapped in transactions for undo support",
                    "tools": [
                        {
                            "name": "add_sketch_constraint",
                            "description": "Add generic constraint (flexible API)",
                            "key_params": ["sketch_name", "constraint_type", "params"],
                        },
                        {
                            "name": "constrain_horizontal",
                            "description": "Make line horizontal",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                        {
                            "name": "constrain_vertical",
                            "description": "Make line vertical",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                        {
                            "name": "constrain_coincident",
                            "description": "Make two points coincident",
                            "key_params": [
                                "sketch_name",
                                "geo1",
                                "point1",
                                "geo2",
                                "point2",
                            ],
                        },
                        {
                            "name": "constrain_parallel",
                            "description": "Make lines parallel",
                            "key_params": ["sketch_name", "geo1", "geo2"],
                        },
                        {
                            "name": "constrain_perpendicular",
                            "description": "Make lines perpendicular",
                            "key_params": ["sketch_name", "geo1", "geo2"],
                        },
                        {
                            "name": "constrain_tangent",
                            "description": "Make curves tangent",
                            "key_params": ["sketch_name", "geo1", "geo2"],
                        },
                        {
                            "name": "constrain_equal",
                            "description": "Make lengths/radii equal",
                            "key_params": ["sketch_name", "geo1", "geo2"],
                        },
                        {
                            "name": "constrain_distance",
                            "description": "Set distance between elements",
                            "key_params": ["sketch_name", "value", "geo1", "point1"],
                        },
                        {
                            "name": "constrain_distance_x",
                            "description": "Set horizontal distance",
                            "key_params": ["sketch_name", "value", "geo1", "point1"],
                        },
                        {
                            "name": "constrain_distance_y",
                            "description": "Set vertical distance",
                            "key_params": ["sketch_name", "value", "geo1", "point1"],
                        },
                        {
                            "name": "constrain_radius",
                            "description": "Set circle/arc radius",
                            "key_params": ["sketch_name", "geometry_index", "value"],
                        },
                        {
                            "name": "constrain_angle",
                            "description": "Set angle between lines",
                            "key_params": ["sketch_name", "geo1", "geo2", "angle"],
                        },
                        {
                            "name": "constrain_fix",
                            "description": "Fix point at location",
                            "key_params": [
                                "sketch_name",
                                "geometry_index",
                                "point_index",
                            ],
                        },
                        {
                            "name": "add_external_geometry",
                            "description": "Reference external geometry in sketch",
                            "key_params": ["sketch_name", "object_name", "element"],
                        },
                        {
                            "name": "delete_sketch_geometry",
                            "description": "Delete geometry from sketch",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                        {
                            "name": "delete_sketch_constraint",
                            "description": "Delete constraint from sketch",
                            "key_params": ["sketch_name", "constraint_index"],
                        },
                        {
                            "name": "get_sketch_info",
                            "description": "Get sketch geometry and constraint info",
                            "key_params": ["sketch_name"],
                        },
                        {
                            "name": "toggle_construction",
                            "description": "Toggle geometry construction mode",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                    ],
                },
                "images_and_checkpoints": {
                    "description": "Drawing delivery, cropping, visual comparison, and deterministic reaction gates",
                    "tools": [
                        {
                            "name": "open_image",
                            "description": "Return local drawing/screenshot pixels as MCP ImageContent",
                            "key_params": ["path", "max_dimension"],
                        },
                        {
                            "name": "open_image_tiles",
                            "description": "Return indexed overview plus enlarged overlapping drawing fragments",
                            "key_params": ["path", "rows", "columns", "overlap_percent"],
                        },
                        {
                            "name": "compare_images",
                            "description": "Side-by-side reference/candidate image; requires discrepancy ledger",
                            "key_params": ["reference_path", "candidate_path"],
                        },
                        {
                            "name": "evaluate_model_checkpoint",
                            "description": "Return continue/rework/ask_user from checkpoint evidence",
                            "key_params": ["checkpoint_name", "geometry_valid", "discrepancies"],
                        },
                    ],
                },
                "view": {
                    "description": "View and GUI control (some require GUI mode)",
                    "tools": [
                        {
                            "name": "get_screenshot",
                            "description": "Capture 3D view screenshot (GUI only)",
                            "key_params": ["file_path", "width", "height"],
                        },
                        {
                            "name": "set_view_angle",
                            "description": "Set camera to standard views",
                            "key_params": ["angle"],
                        },
                        {
                            "name": "fit_all",
                            "description": "Zoom to fit all objects",
                            "key_params": [],
                        },
                        {
                            "name": "zoom_in",
                            "description": "Zoom in",
                            "key_params": ["factor"],
                        },
                        {
                            "name": "zoom_out",
                            "description": "Zoom out",
                            "key_params": ["factor"],
                        },
                        {
                            "name": "set_camera_position",
                            "description": "Set exact camera position and orientation",
                            "key_params": ["position", "direction", "up_vector"],
                        },
                        {
                            "name": "set_object_visibility",
                            "description": "Show/hide objects (GUI only)",
                            "key_params": ["object_name", "visible"],
                        },
                        {
                            "name": "set_display_mode",
                            "description": "Set display mode (wireframe, shaded)",
                            "key_params": ["object_name", "mode"],
                        },
                        {
                            "name": "set_object_color",
                            "description": "Change object color (GUI only)",
                            "key_params": ["object_name", "r", "g", "b"],
                        },
                        {
                            "name": "list_workbenches",
                            "description": "List available workbenches",
                            "key_params": [],
                        },
                        {
                            "name": "activate_workbench",
                            "description": "Switch workbench",
                            "key_params": ["workbench_name"],
                        },
                        {
                            "name": "recompute",
                            "description": "Recompute document",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
                "undo_redo": {
                    "description": "Undo/redo operations",
                    "tools": [
                        {
                            "name": "undo",
                            "description": "Undo last operation",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "redo",
                            "description": "Redo undone operation",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "get_undo_redo_status",
                            "description": "Get available undo/redo operations",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
                "export_import": {
                    "description": "File export and import",
                    "tools": [
                        {
                            "name": "export_step",
                            "description": "Export to STEP format",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "export_stl",
                            "description": "Export to STL format (3D printing)",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "export_3mf",
                            "description": "Export to 3MF format",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "export_obj",
                            "description": "Export to OBJ format",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "export_iges",
                            "description": "Export to IGES format",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "import_step",
                            "description": "Import STEP file",
                            "key_params": ["file_path"],
                        },
                        {
                            "name": "import_stl",
                            "description": "Import STL file",
                            "key_params": ["file_path"],
                        },
                    ],
                },
                "macros": {
                    "description": "Macro management",
                    "tools": [
                        {
                            "name": "list_macros",
                            "description": "List available macros",
                            "key_params": [],
                        },
                        {
                            "name": "run_macro",
                            "description": "Execute a macro",
                            "key_params": ["macro_name"],
                        },
                        {
                            "name": "create_macro",
                            "description": "Create new macro",
                            "key_params": ["macro_name", "code"],
                        },
                        {
                            "name": "read_macro",
                            "description": "Read macro source code",
                            "key_params": ["macro_name"],
                        },
                        {
                            "name": "delete_macro",
                            "description": "Delete a macro",
                            "key_params": ["macro_name"],
                        },
                        {
                            "name": "create_macro_from_template",
                            "description": "Create macro from predefined template",
                            "key_params": ["macro_name", "template_name"],
                        },
                    ],
                },
                "parts_library": {
                    "description": "Parts library access",
                    "tools": [
                        {
                            "name": "list_parts_library",
                            "description": "List parts in library",
                            "key_params": [],
                        },
                        {
                            "name": "insert_part_from_library",
                            "description": "Insert part from library",
                            "key_params": ["part_path"],
                        },
                    ],
                },
                "validation": {
                    "description": "Object and document validation for error detection",
                    "tools": [
                        {
                            "name": "validate_object",
                            "description": "Check object health (shape validity, errors, state)",
                            "key_params": ["object_name", "doc_name"],
                        },
                        {
                            "name": "validate_document",
                            "description": "Check health of all objects in document",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "undo_if_invalid",
                            "description": "Check last operation and undo if it created invalid geometry",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "safe_execute",
                            "description": "Execute Python code with automatic rollback on failure",
                            "key_params": ["code", "doc_name"],
                        },
                    ],
                },
            },
            "resources": [
                {
                    "uri": "freecad://capabilities",
                    "description": "This resource - lists all available capabilities",
                },
                {
                    "uri": "freecad://best-practices",
                    "description": "★ RECOMMENDED: Read first - AI guidance, best practices, version compatibility, common pitfalls",
                },
                {
                    "uri": "freecad://workflows/drawing-reconstruction",
                    "description": "Mandatory drawing-to-model ACT-OBSERVE-REACT workflow",
                },
                {
                    "uri": "freecad://workflows/model-modification",
                    "description": "Mandatory workflow for changing existing parametric models",
                },
                {
                    "uri": "freecad://version",
                    "description": "FreeCAD version and build information",
                },
                {
                    "uri": "freecad://status",
                    "description": "Connection status, mode, GUI availability",
                },
                {
                    "uri": "freecad://documents",
                    "description": "List of all open documents",
                },
                {
                    "uri": "freecad://documents/{name}",
                    "description": "Details of a specific document",
                },
                {
                    "uri": "freecad://documents/{name}/objects",
                    "description": "Objects in a specific document",
                },
                {
                    "uri": "freecad://objects/{doc_name}/{obj_name}",
                    "description": "Detailed object info with properties",
                },
                {
                    "uri": "freecad://active-document",
                    "description": "Currently active document",
                },
                {
                    "uri": "freecad://workbenches",
                    "description": "Available FreeCAD workbenches",
                },
                {
                    "uri": "freecad://workbenches/active",
                    "description": "Currently active workbench",
                },
                {
                    "uri": "freecad://macros",
                    "description": "Available FreeCAD macros",
                },
                {
                    "uri": "freecad://console",
                    "description": "Recent console output (debugging)",
                },
            ],
            "prompts": [
                {
                    "name": "freecad_startup",
                    "description": "Session bootstrap and task router; client invocation is not automatic",
                    "key_params": [],
                },
                {
                    "name": "reproduce_from_drawing",
                    "description": "Mandatory drawing reconstruction and reaction-gate workflow",
                    "key_params": ["reference_path", "target_document"],
                },
                {
                    "name": "modify_existing_model",
                    "description": "Workflow for preserving design intent while modifying a model",
                    "key_params": ["model_path", "change_request", "reference_path"],
                },
                {
                    "name": "freecad_guidance",
                    "description": "Task-specific guidance including drawing, modification, and visual validation",
                    "key_params": ["task_type"],
                },
                {
                    "name": "design-part",
                    "description": "Guided workflow for designing parametric parts",
                    "key_params": ["description", "units"],
                },
                {
                    "name": "create-sketch-guide",
                    "description": "Guide for creating 2D sketches",
                    "key_params": ["shape_type", "plane"],
                },
                {
                    "name": "boolean-operations-guide",
                    "description": "Guide for boolean operations (fuse, cut, common)",
                },
                {
                    "name": "export-guide",
                    "description": "Guide for exporting models (STEP, STL, OBJ, IGES)",
                    "key_params": ["target_format"],
                },
                {
                    "name": "import-guide",
                    "description": "Guide for importing files",
                    "key_params": ["source_format"],
                },
                {
                    "name": "analyze-shape",
                    "description": "Guide for shape analysis (volume, area, etc.)",
                },
                {
                    "name": "debug-model",
                    "description": "Troubleshooting guide for model issues",
                },
                {
                    "name": "macro-development",
                    "description": "Guide for developing FreeCAD macros",
                },
                {
                    "name": "python-api-reference",
                    "description": "Quick reference for FreeCAD Python API",
                },
                {
                    "name": "troubleshooting",
                    "description": "General troubleshooting for FreeCAD MCP",
                },
            ],
            "examples": {
                "debug_macro": {
                    "description": "Debug a macro by checking console output",
                    "steps": [
                        "Use get_console_output(lines=50) to see recent errors",
                        "Use list_objects, inspect_object, and validate_document to inspect state",
                        "Use execute_python to advanced inspect document state",
                    ],
                },
                "create_simple_part": {
                    "description": "Create a basic parametric part",
                    "steps": [
                        "create_document(name='MyPart')",
                        "create_partdesign_body(name='Body')",
                        "create_sketch(body_name='Body', plane='XY_Plane')",
                        "add_sketch_rectangle(...)",
                        "pad_sketch(...)",
                    ],
                },
                "export_for_printing": {
                    "description": "Export model for 3D printing",
                    "steps": [
                        "export_stl(object_names=['Body'], file_path='...')",
                        "Or export_3mf for color/material support",
                    ],
                },
            },
        }
        return json.dumps(capabilities, indent=2)


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
