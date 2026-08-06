"""Live audit of the complete public freecad-mcp tool surface.

This suite is deliberately registry-driven.  Every public tool must occur in
``TOOL_SCENARIOS`` so adding or removing a tool makes the suite fail until the
live coverage plan is updated.  The tests use the real registered wrappers and
the real XML-RPC bridge, not mocked bridge responses.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from PIL import Image

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.server import mcp as production_mcp
from freecad_mcp.tools import register_all_tools

pytestmark = [pytest.mark.integration, pytest.mark.slow]


TOOL_SCENARIOS: dict[str, str] = {
    # Checkpoint/execution/document lifecycle.
    "evaluate_model_checkpoint": "contracts",
    "execute_python": "contracts",
    "get_freecad_version": "contracts",
    "get_connection_status": "contracts",
    "get_console_output": "contracts",
    "get_mcp_server_environment": "contracts",
    "list_documents": "contracts",
    "get_active_document": "contracts",
    "create_document": "contracts",
    "open_document": "contracts",
    "save_document": "contracts",
    "close_document": "contracts",
    "recompute_document": "contracts",
    # Generic objects and Part operations.
    "list_objects": "objects",
    "inspect_object": "objects",
    "select_subshapes": "objects",
    "create_object": "objects",
    "create_primitive": "objects",
    "edit_object": "objects",
    "delete_object": "objects",
    "boolean_operation": "objects",
    "set_placement": "objects",
    "scale_object": "objects",
    "rotate_object": "objects",
    "copy_object": "objects",
    "mirror_object": "objects",
    "selection": "objects",
    "create_line": "objects",
    "create_plane": "objects",
    "create_ellipse": "objects",
    "create_prism": "objects",
    "create_regular_polygon": "objects",
    "shell_object": "objects",
    "offset_3d": "objects",
    "slice_shape": "objects",
    "section_shape": "objects",
    "make_compound": "objects",
    "explode_compound": "objects",
    "fuse_all": "objects",
    "common_all": "objects",
    "make_wire": "objects",
    "make_face": "objects",
    "extrude_shape": "objects",
    "revolve_shape": "objects",
    "part_loft": "objects",
    "part_sweep": "objects",
    # PartDesign and Sketcher.
    "create_partdesign_body": "partdesign",
    "set_body_tip": "partdesign",
    "create_sketch": "partdesign",
    "edit_sketch_geometry": "partdesign",
    "edit_sketch_constraints": "partdesign",
    "pad_sketch": "partdesign",
    "pocket_sketch": "partdesign",
    "fillet_edges": "partdesign",
    "chamfer_edges": "partdesign",
    "revolution_sketch": "partdesign",
    "groove_sketch": "partdesign",
    "thread_helix": "partdesign",
    "create_hole": "partdesign",
    "create_cylindrical_cut": "partdesign",
    "linear_pattern": "partdesign",
    "polar_pattern": "partdesign",
    "multi_transform_pattern": "partdesign",
    "mirrored_feature": "partdesign",
    "loft_sketches": "partdesign",
    "sweep_sketch": "partdesign",
    "create_datum_plane": "partdesign",
    "create_datum_line": "partdesign",
    "create_datum_point": "partdesign",
    "draft_feature": "partdesign",
    "thickness_feature": "partdesign",
    "subtractive_loft": "partdesign",
    "subtractive_pipe": "partdesign",
    "get_sketch_info": "partdesign",
    # Spreadsheet, Draft, files, macros and GUI.
    "spreadsheet_create": "io_gui",
    "spreadsheet_set_cell": "io_gui",
    "spreadsheet_apply_batch": "io_gui",
    "spreadsheet_get_cell": "io_gui",
    "spreadsheet_set_alias": "io_gui",
    "spreadsheet_get_aliases": "io_gui",
    "spreadsheet_clear_cell": "io_gui",
    "spreadsheet_bind_property": "io_gui",
    "spreadsheet_get_cell_range": "io_gui",
    "spreadsheet_import_csv": "io_gui",
    "spreadsheet_export_csv": "io_gui",
    "draft_shapestring": "io_gui",
    "draft_list_fonts": "io_gui",
    "draft_shapestring_to_sketch": "io_gui",
    "draft_shapestring_to_face": "io_gui",
    "draft_text_on_surface": "io_gui",
    "draft_extrude_shapestring": "io_gui",
    "export": "io_gui",
    "import": "io_gui",
    "list_macros": "io_gui",
    "run_macro": "io_gui",
    "create_macro": "io_gui",
    "read_macro": "io_gui",
    "delete_macro": "io_gui",
    "create_macro_from_template": "io_gui",
    "open_image": "io_gui",
    "open_image_tiles": "io_gui",
    "compare_images": "io_gui",
    "get_screenshot": "io_gui",
    "set_view_angle": "io_gui",
    "workbench": "io_gui",
    "set_visual_properties": "io_gui",
    "history": "io_gui",
    "fit_all": "io_gui",
    "set_camera_position": "io_gui",
    "list_parts_library": "io_gui",
    "insert_part_from_library": "io_gui",
    "validate_object": "validation",
    "validate_document": "validation",
    "validate_parametric_model": "validation",
    "undo_if_invalid": "validation",
    "safe_execute": "validation",
}


DOCUMENTED_CHOICES: dict[tuple[str, str], tuple[str, ...]] = {
    ("create_primitive", "primitive.kind"): (
        "box", "cylinder", "sphere", "cone", "torus", "wedge", "helix",
    ),
    ("boolean_operation", "operation"): ("fuse", "cut", "common"),
    ("mirror_object", "plane"): ("XY", "XZ", "YZ"),
    ("selection", "action"): ("get", "set", "clear"),
    ("section_shape", "plane"): ("XY", "XZ", "YZ"),
    ("create_sketch", "support.kind"): (
        "origin_plane",
        "body_tip_face",
        "feature_face",
        "datum_plane",
    ),
    ("edit_sketch_geometry", "operations[].op"): (
        "add_rectangle", "add_circle", "add_line", "add_arc", "add_point",
        "add_ellipse", "add_regular_polygon", "add_polyline", "add_slot", "add_bspline",
        "add_external_geometry", "delete_geometry", "toggle_construction",
    ),
    ("edit_sketch_constraints", "operations[].op"): (
        "add_constraint", "horizontal", "vertical", "coincident", "parallel",
        "perpendicular", "tangent", "equal", "distance", "distance_x",
        "distance_y", "radius", "angle", "fix", "delete_constraint",
        "set_expression", "clear_expression",
    ),
    ("pocket_sketch", "type"): ("Length", "ThroughAll", "UpToFirst", "UpToFace"),
    ("pocket_sketch", "direction"): ("normal", "reversed"),
    ("revolution_sketch", "axis"): (
        "Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H",
    ),
    ("thread_helix", "operation"): ("additive", "subtractive"),
    ("thread_helix", "axis"): (
        "Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H",
    ),
    ("groove_sketch", "axis"): (
        "Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H",
    ),
    ("create_hole", "hole_type"): ("Dimension", "ThroughAll"),
    ("create_hole", "thread_type"): ("ISO", "ISO_FINE", "UNC", "UNF"),
    ("create_hole", "drill_point"): ("Flat", "Angled"),
    ("linear_pattern", "direction"): ("X", "Y", "Z"),
    ("polar_pattern", "axis"): ("X", "Y", "Z"),
    ("mirrored_feature", "plane"): ("XY", "XZ", "YZ"),
    ("sweep_sketch", "transition"): ("Transformed", "Right", "Round"),
    ("create_datum_plane", "base_plane"): ("XY_Plane", "XZ_Plane", "YZ_Plane"),
    ("create_datum_line", "base_axis"): ("X_Axis", "Y_Axis", "Z_Axis"),
    ("draft_feature", "plane"): ("XY", "XZ", "YZ"),
    ("subtractive_pipe", "transition"): ("Transformed", "Right", "Round"),
    ("draft_shapestring_to_sketch", "plane"): ("XY_Plane", "XZ_Plane", "YZ_Plane"),
    ("draft_text_on_surface", "operation"): ("emboss", "engrave"),
    ("export", "file_format"): ("step", "iges", "stl", "3mf", "obj"),
    ("import", "file_format"): ("step", "stl"),
    ("create_macro_from_template", "template"): ("basic", "part", "sketch", "gui"),
    ("get_screenshot", "view_angle"): (
        "Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right", "FitAll",
    ),
    ("get_screenshot", "background"): ("White", "Current"),
    ("set_view_angle", "view_angle"): (
        "Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right", "FitAll",
    ),
    ("workbench", "action"): ("list", "activate"),
    ("history", "action"): ("undo", "redo", "status"),
}


class ToolCollector:
    """Small FastMCP-compatible collector preserving MCP name aliases."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        name = kwargs.get("name")

        def decorator(function: Any) -> Any:
            self.tools[name or function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_tools() -> Any:
    bridge = XmlRpcBridge()
    await bridge.connect()
    collector = ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return bridge

    register_all_tools(collector, get_bridge)
    try:
        yield collector.tools
    finally:
        await bridge.execute_python(
            """
for name in list(FreeCAD.listDocuments()):
    if name.startswith("McpAudit"):
        FreeCAD.closeDocument(name)
_result_ = True
"""
        )
        await bridge.disconnect()


async def _call(tools: dict[str, Any], tool_name: str, **kwargs: Any) -> Any:
    result = await tools[tool_name](**kwargs)
    if isinstance(result, dict) and result.get("success") is False:
        raise AssertionError(f"{tool_name} returned unsuccessful result: {result!r}")
    return result


async def _fresh(tools: dict[str, Any], name: str) -> None:
    await _call(
        tools,
        "execute_python",
        code=f"""
if {name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({name!r})
FreeCAD.newDocument({name!r})
_result_ = True
""",
    )


def test_runtime_registry_has_explicit_116_tool_coverage() -> None:
    async def registered() -> set[str]:
        return {tool.name for tool in await production_mcp.list_tools()}

    actual = asyncio.run(registered())
    assert len(actual) == 116
    assert set(TOOL_SCENARIOS) == actual


def test_create_sketch_runtime_schema_has_only_typed_support() -> None:
    async def schema() -> dict[str, Any]:
        tool = next(
            tool
            for tool in await production_mcp.list_tools()
            if tool.name == "create_sketch"
        )
        return tool.inputSchema

    input_schema = asyncio.run(schema())
    assert "plane" not in input_schema["properties"]
    support_schema = input_schema["properties"]["support"]["anyOf"][0]
    assert support_schema["discriminator"]["propertyName"] == "kind"
    assert set(support_schema["discriminator"]["mapping"]) == {
        "origin_plane",
        "body_tip_face",
        "feature_face",
        "datum_plane",
    }


def test_sketch_batch_runtime_schemas_expose_discriminated_operations() -> None:
    """FastMCP tools/list must not degrade sketch operation items to unknown."""
    async def schemas() -> dict[str, dict[str, Any]]:
        return {
            tool.name: tool.inputSchema
            for tool in await production_mcp.list_tools()
            if tool.name in {"edit_sketch_geometry", "edit_sketch_constraints"}
        }

    input_schemas = asyncio.run(schemas())
    expected = {
        "edit_sketch_geometry": set(
            DOCUMENTED_CHOICES[("edit_sketch_geometry", "operations[].op")]
        ),
        "edit_sketch_constraints": set(
            DOCUMENTED_CHOICES[("edit_sketch_constraints", "operations[].op")]
        ),
    }
    for tool_name, operation_names in expected.items():
        items = input_schemas[tool_name]["properties"]["operations"]["items"]
        assert items["discriminator"]["propertyName"] == "op"
        assert set(items["discriminator"]["mapping"]) == operation_names
        assert len(items["oneOf"]) > 1


def test_documented_choice_catalog_is_nonempty_and_unique() -> None:
    assert len(DOCUMENTED_CHOICES) >= 25
    for key, values in DOCUMENTED_CHOICES.items():
        assert key[0] in TOOL_SCENARIOS
        assert values
        assert len(values) == len(set(values))


@pytest.mark.asyncio
async def test_contracts_and_document_lifecycle(live_tools: dict[str, Any], tmp_path: Path) -> None:
    tools = live_tools
    await _call(tools, "get_freecad_version")
    status = await _call(tools, "get_connection_status")
    assert status["connected"] is True
    await _call(tools, "get_mcp_server_environment")
    await _call(tools, "get_console_output", lines=5)
    await _call(tools, "list_documents")
    await _call(tools, "create_document", name="McpAuditLifecycle", label="MCP audit")
    active = await _call(tools, "get_active_document")
    assert active["name"] == "McpAuditLifecycle"
    await _call(tools, "recompute_document", doc_name="McpAuditLifecycle")
    await _call(
        tools,
        "evaluate_model_checkpoint",
        checkpoint_name="healthy",
        geometry_valid=True,
        solid_count=1,
        visual_comparison_performed=True,
    )
    await _call(
        tools,
        "evaluate_model_checkpoint",
        checkpoint_name="rework",
        geometry_valid=False,
        discrepancies=[{"severity": "critical", "category": "shape"}],
    )
    saved = tmp_path / "lifecycle.FCStd"
    await _call(
        tools, "save_document", doc_name="McpAuditLifecycle", path=str(saved),
    )
    await _call(tools, "close_document", doc_name="McpAuditLifecycle")
    await _call(tools, "open_document", path=str(saved))
    await _call(tools, "close_document", doc_name="lifecycle")


@pytest.mark.asyncio
async def test_generic_part_object_workflow(live_tools: dict[str, Any]) -> None:
    tools = live_tools
    doc = "McpAuditObjects"
    await _fresh(tools, doc)
    await _call(tools, "create_object", type_id="Part::Box", name="RawBox",
                properties={"Length": 20.0, "Width": 16.0, "Height": 12.0}, doc_name=doc)
    for kind, dimensions in {
        "box": {"length": 12.0, "width": 10.0, "height": 8.0},
        "cylinder": {"radius": 4.0, "height": 10.0, "angle": 270.0},
        "sphere": {"radius": 5.0},
        "cone": {"radius1": 5.0, "radius2": 2.0, "height": 9.0, "angle": 300.0},
        "torus": {"radius1": 8.0, "radius2": 2.0, "angle3": 270.0},
        "wedge": {},
        "helix": {"pitch": 3.0, "height": 12.0, "radius": 4.0, "left_handed": True},
    }.items():
        await _call(tools, "create_primitive", primitive={"kind": kind, **dimensions},
                    name=f"P_{kind}", doc_name=doc)
    await _call(tools, "edit_object", object_name="RawBox",
                properties={"Length": 22.0}, doc_name=doc)
    await _call(tools, "set_placement", object_name="P_cylinder",
                position=[8, 3, 0], rotation=[0, 0, 10], doc_name=doc)
    await _call(tools, "rotate_object", object_name="P_cone",
                axis=[0, 0, 1], angle=15, center=[0, 0, 0], doc_name=doc)
    await _call(tools, "copy_object", object_name="P_box", new_name="P_box_copy",
                offset=[5, 0, 0], doc_name=doc)
    await _call(tools, "scale_object", object_name="P_sphere", scale=1.2,
                result_name="SphereScaled", doc_name=doc)
    for plane in ("XY", "XZ", "YZ"):
        await _call(tools, "mirror_object", object_name="P_cone", plane=plane,
                    result_name=f"ConeMirror{plane}", doc_name=doc)
    await _call(tools, "boolean_operation", operation="fuse",
                object1_name="RawBox", object2_name="P_box", result_name="BoolFuse", doc_name=doc)
    await _call(tools, "boolean_operation", operation="cut",
                object1_name="P_box_copy", object2_name="P_cylinder", result_name="BoolCut", doc_name=doc)
    await _call(tools, "boolean_operation", operation="common",
                object1_name="P_sphere", object2_name="P_cone", result_name="BoolCommon", doc_name=doc)
    await _call(tools, "create_line", point1=[0, 0, 0], point2=[10, 0, 0],
                name="Line", doc_name=doc)
    await _call(tools, "create_plane", length=20, width=15, name="Plane", doc_name=doc)
    await _call(tools, "create_ellipse", major_radius=9, minor_radius=4,
                name="Ellipse", doc_name=doc)
    await _call(tools, "create_prism", polygon_sides=5, circumradius=6, height=8,
                name="Prism", doc_name=doc)
    await _call(tools, "create_regular_polygon", polygon_sides=7, circumradius=6,
                name="Polygon", doc_name=doc)
    await _call(tools, "make_wire", points=[[0, 0, 0], [12, 0, 0], [12, 8, 0], [0, 8, 0]],
                closed=True, name="Wire", doc_name=doc)
    await _call(tools, "make_face", object_name="Wire", result_name="Face", doc_name=doc)
    await _call(tools, "extrude_shape", object_name="Face", direction=[0, 0, 6],
                result_name="Extrusion", doc_name=doc)
    await _call(tools, "revolve_shape", object_name="Face", axis_point=[0, 0, 0],
                axis_direction=[0, 1, 0], angle=90, result_name="Revolve", doc_name=doc)
    await _call(tools, "slice_shape", object_name="Extrusion", plane_point=[0, 0, 3],
                plane_normal=[0, 0, 1], result_name="Slice", doc_name=doc)
    for plane, offset in (("XY", 3), ("XZ", 4), ("YZ", 6)):
        await _call(tools, "section_shape", object_name="Extrusion", plane=plane,
                    offset=offset, result_name=f"Section{plane}", doc_name=doc)
    await _call(tools, "offset_3d", object_name="P_box", offset=0.5,
                result_name="Offset", doc_name=doc)
    await _call(tools, "shell_object", object_name="RawBox", thickness=-1.0,
                faces_to_remove=["Face6"], result_name="Shell", doc_name=doc)
    await _call(tools, "make_compound", object_names=["P_cone", "P_sphere"],
                result_name="Compound", doc_name=doc)
    await _call(tools, "explode_compound", object_name="Compound", doc_name=doc)
    await _call(tools, "fuse_all", object_names=["P_box", "P_box_copy"],
                result_name="FuseAll", doc_name=doc)
    await _call(tools, "common_all", object_names=["P_sphere", "SphereScaled"],
                result_name="CommonAll", doc_name=doc)
    await _call(
        tools, "execute_python",
        code=f"""
doc = FreeCAD.getDocument({doc!r})
import Part
for name, z, size in [("LoftA", 0, 10), ("LoftB", 15, 6)]:
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.Wire(Part.makePolygon([
        FreeCAD.Vector(-size, -size, z), FreeCAD.Vector(size, -size, z),
        FreeCAD.Vector(size, size, z), FreeCAD.Vector(-size, size, z),
        FreeCAD.Vector(-size, -size, z)
    ]).Edges)
profile = doc.addObject("Part::Feature", "SweepProfile")
profile.Shape = Part.Wire([Part.makeCircle(2, FreeCAD.Vector(0,0,0),
    FreeCAD.Vector(0,1,0))])
spine = doc.addObject("Part::Feature", "SweepSpine")
spine.Shape = Part.Wire([Part.makeLine(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,20,0))])
doc.recompute()
_result_ = True
""",
    )
    await _call(tools, "part_loft", profile_names=["LoftA", "LoftB"],
                result_name="PartLoft", doc_name=doc)
    await _call(tools, "part_sweep", profile_name="SweepProfile", spine_name="SweepSpine",
                result_name="PartSweep", doc_name=doc)
    await _call(tools, "list_objects", doc_name=doc)
    await _call(tools, "inspect_object", object_name="Extrusion", doc_name=doc)
    selected = await _call(
        tools,
        "select_subshapes",
        object_name="Extrusion",
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "sort_by": "center_z",
            "sort_order": "desc",
            "limit": 1,
        },
        doc_name=doc,
    )
    assert selected["match_count"] == 1
    for action in ("set", "get", "clear"):
        kwargs = {"object_names": ["Extrusion"]} if action == "set" else {}
        await _call(tools, "selection", action=action, doc_name=doc, **kwargs)
    await _call(tools, "delete_object", object_name="Line", doc_name=doc)


@pytest.mark.asyncio
async def test_spreadsheet_macro_export_image_gui_and_validation_workflow(
    live_tools: dict[str, Any], tmp_path: Path,
) -> None:
    tools = live_tools
    doc = "McpAuditIoGui"
    await _fresh(tools, doc)
    await _call(tools, "create_primitive",
                primitive={"kind": "box", "length": 30, "width": 20, "height": 10},
                name="Box", doc_name=doc)
    await _call(tools, "spreadsheet_create", name="Params", doc_name=doc)
    await _call(tools, "spreadsheet_set_cell", spreadsheet_name="Params", cell="A1",
                value=42, doc_name=doc)
    await _call(tools, "spreadsheet_set_alias", spreadsheet_name="Params", cell="A1",
                alias="BoxLength", doc_name=doc)
    await _call(tools, "spreadsheet_get_cell", spreadsheet_name="Params", cell="A1", doc_name=doc)
    await _call(tools, "spreadsheet_get_aliases", spreadsheet_name="Params", doc_name=doc)
    await _call(tools, "spreadsheet_bind_property", spreadsheet_name="Params",
                alias="BoxLength", target_object="Box", target_property="Length", doc_name=doc)
    csv_in = tmp_path / "params.csv"
    csv_in.write_text("11;12\n13;14\n", encoding="utf-8")
    await _call(tools, "spreadsheet_import_csv", spreadsheet_name="Params",
                file_path=str(csv_in), delimiter=";", start_cell="C1", doc_name=doc)
    await _call(tools, "spreadsheet_get_cell_range", spreadsheet_name="Params",
                start_cell="A1", end_cell="D2", doc_name=doc)
    csv_out = tmp_path / "params_out.csv"
    await _call(tools, "spreadsheet_export_csv", spreadsheet_name="Params",
                file_path=str(csv_out), delimiter=";", doc_name=doc)
    await _call(tools, "spreadsheet_clear_cell", spreadsheet_name="Params",
                cell="D2", doc_name=doc)
    macro = "McpAuditMacro"
    await _call(tools, "create_macro", name=macro,
                code="_result_ = {'value': audit_value}", description="audit")
    await _call(tools, "read_macro", macro_name=macro)
    await _call(tools, "run_macro", macro_name=macro, args={"audit_value": 7})
    await _call(tools, "list_macros")
    for template in ("basic", "part", "sketch", "gui"):
        name = f"McpAuditTemplate_{template}"
        await _call(tools, "create_macro_from_template", name=name, template=template)
        await _call(tools, "delete_macro", macro_name=name)
    await _call(tools, "delete_macro", macro_name=macro)
    for fmt in ("step", "iges", "stl", "3mf", "obj"):
        await _call(tools, "export", file_format=fmt, file_path=str(tmp_path / f"box.{fmt}"),
                    object_names=["Box"], doc_name=doc)
    for fmt in ("step", "stl"):
        await _call(tools, "import", file_format=fmt, file_path=str(tmp_path / f"box.{fmt}"),
                    doc_name=doc)
    image_a = tmp_path / "reference.png"
    image_b = tmp_path / "candidate.png"
    Image.new("RGB", (160, 100), "white").save(image_a)
    Image.new("RGB", (160, 100), "lightgray").save(image_b)
    await _call(tools, "open_image", path=str(image_a), max_dimension=128)
    await _call(tools, "open_image_tiles", path=str(image_a), rows=2, columns=2,
                overlap_percent=10, output_dir=str(tmp_path / "tiles"))
    await _call(tools, "compare_images", reference_path=str(image_a),
                candidate_path=str(image_b), output_path=str(tmp_path / "comparison.png"),
                view_context="Front / XZ / normal Y")
    fonts = await _call(tools, "draft_list_fonts")
    font_path = fonts["fonts"][0]["path"] if isinstance(fonts, dict) and fonts.get("fonts") else None
    shape = await _call(tools, "draft_shapestring", text="MCP", font_path=font_path,
                        size=5, position=[0, 0, 10], name="Text", doc_name=doc)
    await _call(tools, "list_objects", doc_name=doc)
    shape_name = shape["name"]
    await _call(tools, "draft_shapestring_to_face", shapestring_name=shape_name,
                name="TextFace", doc_name=doc)
    await _call(tools, "draft_extrude_shapestring", shapestring_name=shape_name,
                height=1, direction=[0, 0, 1], name="TextSolid", doc_name=doc)
    for plane in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        await _call(tools, "draft_shapestring_to_sketch", shapestring_name=shape_name,
                    plane=plane, sketch_name=f"TextSketch{plane[:2]}", doc_name=doc)
    for operation in ("engrave", "emboss"):
        await _call(tools, "draft_text_on_surface", text="A", target_face="Face6",
                    target_object="Box", depth=0.5, font_path=font_path, size=3,
                    position=[3, 3], operation=operation,
                    name=f"SurfaceText{operation}", doc_name=doc)
    for view in ("Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right", "FitAll"):
        await _call(tools, "set_view_angle", view_angle=view, doc_name=doc)
        await _call(tools, "get_screenshot", view_angle=view, width=320, height=240,
                    doc_name=doc, background="White", settle_time_seconds=0,
                    save_to_disk=False, return_image=False)
    await _call(tools, "get_screenshot", view_angle="Isometric", width=320, height=240,
                doc_name=doc, background="Current", settle_time_seconds=0,
                save_to_disk=False, return_image=False)
    benches = await _call(tools, "workbench", action="list")
    bench_names = list(benches.get("workbenches", benches)) if isinstance(benches, dict) else list(benches)
    if bench_names:
        first = bench_names[0]
        if isinstance(first, dict):
            first = first.get("name") or first.get("internal_name")
        await _call(tools, "workbench", action="activate", workbench_name=str(first))
    await _call(tools, "set_visual_properties", object_name="Box", visible=True,
                color=[0.2, 0.4, 0.8], display_mode="Flat Lines", doc_name=doc)
    await _call(tools, "fit_all", doc_name=doc)
    await _call(tools, "set_camera_position", position=[80, 60, 50],
                look_at=[15, 10, 5], doc_name=doc)
    for action in ("status", "undo", "redo"):
        await _call(tools, "history", action=action, doc_name=doc)
    await _call(tools, "list_parts_library")
    part_path = tmp_path / "library_part.FCStd"
    await _call(tools, "save_document", doc_name=doc, path=str(part_path))
    await _call(tools, "insert_part_from_library", part_path=str(part_path),
                name="InsertedPart", position=[50, 0, 0], doc_name=doc)
    await _call(tools, "safe_execute", doc_name=doc,
                code='obj = doc.getObject("Box"); _result_ = {"volume": obj.Shape.Volume}')
    await _call(tools, "validate_object", object_name="Box", doc_name=doc)
    await _call(tools, "validate_document", doc_name=doc)
    await _call(tools, "validate_parametric_model", doc_name=doc,
                recompute=True, include_sketch_constraints=True)
    await _call(tools, "undo_if_invalid", doc_name=doc)


@pytest.mark.asyncio
async def test_draft_shapestring_honors_explicit_doc_name(
    live_tools: dict[str, Any],
) -> None:
    """Regression: Draft.make_shapestring must not leak into ActiveDocument."""
    tools = live_tools
    await _fresh(tools, "McpAuditDraftTarget")
    await _call(tools, "create_document", name="McpAuditDraftOther")
    fonts = await _call(tools, "draft_list_fonts")
    font_path = fonts["fonts"][0]["path"]
    result = await _call(
        tools,
        "draft_shapestring",
        text="A",
        font_path=font_path,
        name="ExplicitTargetText",
        doc_name="McpAuditDraftTarget",
    )
    target_objects = await _call(tools, "list_objects", doc_name="McpAuditDraftTarget")
    target_identifiers = {
        value
        for item in target_objects
        for value in (item["name"], item["label"])
    }
    assert result["name"] in target_identifiers


@pytest.mark.asyncio
async def test_draft_shapestring_returned_name_is_chainable(
    live_tools: dict[str, Any],
) -> None:
    tools = live_tools
    await _fresh(tools, "McpAuditDraftChain")
    fonts = await _call(tools, "draft_list_fonts")
    result = await _call(
        tools, "draft_shapestring", text="A", font_path=fonts["fonts"][0]["path"],
        name="FriendlyLabel", doc_name="McpAuditDraftChain",
    )
    await _call(
        tools, "draft_shapestring_to_face", shapestring_name=result["name"],
        doc_name="McpAuditDraftChain",
    )
