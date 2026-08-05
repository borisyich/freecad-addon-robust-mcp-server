"""Complex live workflow for semantic inspection and Spreadsheet-driven sketches.

Run with a FreeCAD instance whose Robust MCP XML-RPC bridge is listening on
localhost:9875.  The scenario deliberately changes the parameter table after
Fillet and Chamfer have been created, so it exercises the complete editable
PartDesign history rather than only checking one-shot tool responses.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.slow]


_PARAMETERS: tuple[tuple[str, str, str], ...] = (
    ("A1", "BaseCenterX", "2 mm"),
    ("A2", "BaseCenterY", "3 mm"),
    ("A3", "BaseRadius", "20 mm"),
    ("A4", "Height", "30 mm"),
    ("A5", "HoleOffsetX", "8 mm"),
    ("A6", "HoleOffsetY", "4 mm"),
    ("A7", "HoleRadius", "5 mm"),
    ("A8", "FilletRadius", "2 mm"),
    ("A9", "ChamferSize", "1 mm"),
)


def _constraint_expressions(info: dict[str, Any]) -> dict[str, str]:
    """Return named driving expressions from a detailed sketch response."""
    return {
        item["name"]: item["expression"]
        for item in info["constraints"]
        if item.get("name") and item.get("expression")
    }


def _quantity_property(info: dict[str, Any], name: str) -> float:
    """Extract the numeric value of a quantity property from inspect_object."""
    return float(info["properties"][name]["value"]["value"])


async def _assert_parametric_model_valid(
    tools: dict[str, Any], doc_name: str
) -> dict[str, Any]:
    """Require a recomputable model with every declared drawing parameter used."""
    required_names = [alias for _cell, alias, _value in _PARAMETERS]
    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        recompute=True,
        include_sketch_constraints=True,
        required_dimension_names=required_names,
    )

    errors = [
        finding
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    ]
    assert report.get("document", {}).get("recompute_error") is None, report
    assert report.get("assessment") != "invalid_or_broken", report
    assert not errors, errors

    usage = {
        item["name"]: item["status"]
        for item in report["dimension_inventory"]["usage"]
    }
    assert usage == {name: "used" for name in required_names}, usage

    dimensions_sheet = next(
        item for item in report["spreadsheets"] if item["name"] == "Dimensions"
    )
    assert dimensions_sheet["unused_parameters"] == []
    return report


@pytest.mark.asyncio
async def test_semantic_selector_and_sketch_expressions_survive_parameter_update(
    live_tools: dict[str, Any],
) -> None:
    """Build and resize a dressed, through-holed cylinder using only semantic refs.

    Workflow covered:
    Spreadsheet aliases -> named sketch-constraint expressions -> Pad property
    binding -> semantic top-face selection -> face-supported hole sketch ->
    semantic edge selection -> Fillet and Chamfer -> semantic topology inspection
    -> Spreadsheet resize -> final parametric validation.
    """
    tools = live_tools
    doc_name = "McpAuditSemanticParametricWorkflow"
    await _fresh(tools, doc_name)

    sheet = await _call(
        tools,
        "spreadsheet_create",
        name="Dimensions",
        doc_name=doc_name,
    )
    assert sheet["name"] == "Dimensions"
    batch = await _call(
        tools,
        "spreadsheet_apply_batch",
        spreadsheet_name="Dimensions",
        cells=[{"cell": cell, "value": value} for cell, _alias, value in _PARAMETERS],
        aliases=[{"cell": cell, "alias": alias} for cell, alias, _value in _PARAMETERS],
        doc_name=doc_name,
    )
    assert batch["cells_applied"] == len(_PARAMETERS)
    assert batch["aliases_applied"] == len(_PARAMETERS)

    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc_name)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="BaseSketch",
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BaseSketch",
        operations=[
            {
                "op": "add_circle",
                "center_x": 2.0,
                "center_y": 3.0,
                "radius": 20.0,
            }
        ],
        doc_name=doc_name,
    )
    base_sketch = await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="BaseSketch",
        operations=[
            {
                "op": "distance_x",
                "geometry1": 0,
                "point1": 3,
                "value": 2.0,
                "constraint_name": "BaseCenterX",
                "expression": "Dimensions.BaseCenterX",
            },
            {
                "op": "distance_y",
                "geometry1": 0,
                "point1": 3,
                "value": 3.0,
                "constraint_name": "BaseCenterY",
                "expression": "Dimensions.BaseCenterY",
            },
            {
                "op": "radius",
                "geometry1": 0,
                "value": 20.0,
                "constraint_name": "BaseRadius",
                "expression": "Dimensions.BaseRadius",
            },
        ],
        doc_name=doc_name,
    )
    assert base_sketch["sketch_status"]["solver"]["status"] == "fully_constrained"
    assert base_sketch["geometry"][0]["geometry"]["radius"] == pytest.approx(20.0)
    assert _constraint_expressions(base_sketch) == {
        "BaseCenterX": "Dimensions.BaseCenterX",
        "BaseCenterY": "Dimensions.BaseCenterY",
        "BaseRadius": "Dimensions.BaseRadius",
    }
    assert all(
        expression["path"].startswith("Constraints[")
        for expression in base_sketch["expressions"]
    )

    pad = await _call(
        tools,
        "pad_sketch",
        sketch_name="BaseSketch",
        length=30.0,
        direction=[0, 0, 1],
        name="Pad",
        doc_name=doc_name,
    )
    assert pad["validated"] is True
    height_binding = await _call(
        tools,
        "spreadsheet_bind_property",
        spreadsheet_name="Dimensions",
        alias="Height",
        target_object="Pad",
        target_property="Length",
        doc_name=doc_name,
    )
    assert height_binding["expression"] == "Dimensions.Height"

    pad_info = await _call(
        tools,
        "inspect_object",
        object_name="Pad",
        doc_name=doc_name,
        include_properties=True,
    )
    assert pad_info["shape_info"]["is_valid"] is True
    assert pad_info["shape_info"]["solid_count"] == 1
    assert pad_info["shape_info"]["volume"] == pytest.approx(
        3.141592653589793 * 20.0**2 * 30.0, rel=1e-6
    )
    assert _quantity_property(pad_info, "Length") == pytest.approx(30.0)

    top_face = await _call(
        tools,
        "select_subshapes",
        object_name="Pad",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["planar"],
            "normal": [0, 0, 1],
            "normal_tolerance_deg": 1,
            "sort_by": "center_z",
            "sort_order": "desc",
            "limit": 1,
        },
    )
    assert top_face["match_count"] == 1, top_face
    assert top_face["matches"][0]["surface_type"] == "Plane"
    assert top_face["matches"][0]["normal"]["z"] == pytest.approx(1.0)
    top_face_ref = top_face["references"][0]

    hole_support = await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={
            "kind": "feature_face",
            "feature": "Pad",
            "face": top_face_ref,
        },
        name="HoleSketch",
        doc_name=doc_name,
    )
    assert hole_support["support"] == f"Pad.{top_face_ref}"
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="HoleSketch",
        operations=[
            {
                "op": "add_circle",
                "center_x": 8.0,
                "center_y": 4.0,
                "radius": 5.0,
            }
        ],
        doc_name=doc_name,
    )
    hole_sketch = await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="HoleSketch",
        operations=[
            {
                "op": "distance_x",
                "geometry1": 0,
                "point1": 3,
                "value": 8.0,
                "constraint_name": "HoleOffsetX",
                "expression": "Dimensions.HoleOffsetX",
            },
            {
                "op": "distance_y",
                "geometry1": 0,
                "point1": 3,
                "value": 4.0,
                "constraint_name": "HoleOffsetY",
                "expression": "Dimensions.HoleOffsetY",
            },
            {
                "op": "radius",
                "geometry1": 0,
                "value": 5.0,
                "constraint_name": "HoleRadius",
                "expression": "Dimensions.HoleRadius",
            },
        ],
        doc_name=doc_name,
    )
    assert hole_sketch["sketch_status"]["solver"]["status"] == "fully_constrained"
    assert "start_point" in hole_sketch["geometry"][0]
    assert "end_point" in hole_sketch["geometry"][0]
    assert _constraint_expressions(hole_sketch) == {
        "HoleOffsetX": "Dimensions.HoleOffsetX",
        "HoleOffsetY": "Dimensions.HoleOffsetY",
        "HoleRadius": "Dimensions.HoleRadius",
    }

    detailed_hole_sketch = await _call(
        tools,
        "get_sketch_info",
        sketch_name="HoleSketch",
        doc_name=doc_name,
    )
    assert detailed_hole_sketch["geometry"][0]["geometry_type"] == "Circle"
    assert detailed_hole_sketch["geometry"][0]["geometry"]["center"] == {
        "x": pytest.approx(8.0),
        "y": pytest.approx(4.0),
        "z": pytest.approx(0.0),
    }
    assert {
        item["path"] for item in detailed_hole_sketch["expressions"]
    } == {"Constraints[0]", "Constraints[1]", "Constraints[2]"}

    pocket = await _call(
        tools,
        "pocket_sketch",
        sketch_name="HoleSketch",
        length=30.0,
        type="ThroughAll",
        base_feature_name="Pad",
        name="Pocket",
        doc_name=doc_name,
    )
    assert pocket["validated"] is True
    assert pocket["removed_volume"] > 0

    top_outer_edge = await _call(
        tools,
        "select_subshapes",
        object_name="Pocket",
        doc_name=doc_name,
        criteria={
            "kind": "edge",
            "curve_types": ["circular"],
            "radius_min": 19.9,
            "radius_max": 20.1,
            "center": {"z_min": 29.9},
            "adjacent_surface_types": ["Plane", "Cylinder"],
            "sort_by": "center_z",
            "sort_order": "desc",
            "limit": 1,
        },
    )
    assert top_outer_edge["match_count"] == 1, top_outer_edge
    assert len(top_outer_edge["matches"][0]["adjacent_faces"]) == 2

    fillet = await _call(
        tools,
        "fillet_edges",
        object_name="Pocket",
        radius=2.0,
        edges=top_outer_edge["references"],
        name="Fillet",
        doc_name=doc_name,
    )
    assert fillet["validated"] is True
    assert fillet["tip_matches"] is True
    fillet_binding = await _call(
        tools,
        "spreadsheet_bind_property",
        spreadsheet_name="Dimensions",
        alias="FilletRadius",
        target_object="Fillet",
        target_property="Radius",
        doc_name=doc_name,
    )
    assert fillet_binding["expression"] == "Dimensions.FilletRadius"

    bottom_outer_edge = await _call(
        tools,
        "select_subshapes",
        object_name="Fillet",
        doc_name=doc_name,
        criteria={
            "kind": "edge",
            "curve_types": ["Circle"],
            "radius_min": 19.9,
            "radius_max": 20.1,
            "center": {"z_max": 0.1},
            "adjacent_surface_types": ["Plane", "Cylinder"],
            "sort_by": "center_z",
            "sort_order": "asc",
            "limit": 1,
        },
    )
    assert bottom_outer_edge["match_count"] == 1, bottom_outer_edge

    chamfer = await _call(
        tools,
        "chamfer_edges",
        object_name="Fillet",
        size=1.0,
        edges=bottom_outer_edge["references"],
        name="Chamfer",
        doc_name=doc_name,
    )
    assert chamfer["validated"] is True
    assert chamfer["tip_matches"] is True
    chamfer_binding = await _call(
        tools,
        "spreadsheet_bind_property",
        spreadsheet_name="Dimensions",
        alias="ChamferSize",
        target_object="Chamfer",
        target_property="Size",
        doc_name=doc_name,
    )
    assert chamfer_binding["expression"] == "Dimensions.ChamferSize"

    initial_final = await _call(
        tools,
        "inspect_object",
        object_name="Chamfer",
        doc_name=doc_name,
        include_properties=True,
    )
    initial_shape = initial_final["shape_info"]
    assert initial_shape["is_valid"] is True
    assert initial_shape["solid_count"] == 1
    assert initial_shape["volume"] < pad_info["shape_info"]["volume"]
    assert all("surface_type" in face for face in initial_shape["faces"])
    assert all("adjacent_faces" in face for face in initial_shape["faces"])
    assert all("curve_type" in edge for edge in initial_shape["edges"])
    assert all(
        "start_point" in edge and "end_point" in edge
        for edge in initial_shape["edges"]
    )
    assert all("adjacent_faces" in edge for edge in initial_shape["edges"])

    concave_hole_face = await _call(
        tools,
        "select_subshapes",
        object_name="Chamfer",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["cylindrical"],
            "convexity": "concave",
            "sort_by": "area",
            "sort_order": "asc",
            "limit": 1,
        },
    )
    assert concave_hole_face["match_count"] == 1, concave_hole_face
    assert concave_hole_face["matches"][0]["convexity"] == "concave"
    assert concave_hole_face["matches"][0]["adjacent_faces"]

    await _assert_parametric_model_valid(tools, doc_name)

    resized = await _call(
        tools,
        "spreadsheet_apply_batch",
        spreadsheet_name="Dimensions",
        cells=[
            {"cell": "A3", "value": "24 mm"},
            {"cell": "A4", "value": "36 mm"},
            {"cell": "A5", "value": "10 mm"},
            {"cell": "A7", "value": "6 mm"},
            {"cell": "A8", "value": "3 mm"},
            {"cell": "A9", "value": "1.5 mm"},
        ],
        doc_name=doc_name,
    )
    assert resized["cells_applied"] == 6

    resized_base = await _call(
        tools,
        "get_sketch_info",
        sketch_name="BaseSketch",
        doc_name=doc_name,
    )
    resized_hole = await _call(
        tools,
        "get_sketch_info",
        sketch_name="HoleSketch",
        doc_name=doc_name,
    )
    assert resized_base["geometry"][0]["geometry"]["radius"] == pytest.approx(24.0)
    assert resized_hole["geometry"][0]["geometry"]["center"]["x"] == pytest.approx(10.0)
    assert resized_hole["geometry"][0]["geometry"]["radius"] == pytest.approx(6.0)
    assert (
        _constraint_expressions(resized_base)["BaseRadius"]
        == "Dimensions.BaseRadius"
    )
    assert (
        _constraint_expressions(resized_hole)["HoleRadius"]
        == "Dimensions.HoleRadius"
    )

    resized_pad = await _call(
        tools,
        "inspect_object",
        object_name="Pad",
        doc_name=doc_name,
        include_properties=True,
    )
    resized_fillet = await _call(
        tools,
        "inspect_object",
        object_name="Fillet",
        doc_name=doc_name,
        include_properties=True,
    )
    resized_final = await _call(
        tools,
        "inspect_object",
        object_name="Chamfer",
        doc_name=doc_name,
        include_properties=True,
    )
    assert _quantity_property(resized_pad, "Length") == pytest.approx(36.0)
    assert _quantity_property(resized_fillet, "Radius") == pytest.approx(3.0)
    assert _quantity_property(resized_final, "Size") == pytest.approx(1.5)

    resized_shape = resized_final["shape_info"]
    assert resized_shape["is_valid"] is True
    assert resized_shape["solid_count"] == 1
    assert resized_shape["volume"] > initial_shape["volume"]
    assert resized_shape["bounding_box"]["size"] == {
        "x": pytest.approx(48.0),
        "y": pytest.approx(48.0),
        "z": pytest.approx(36.0),
    }

    resized_top_face = await _call(
        tools,
        "select_subshapes",
        object_name="Chamfer",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "normal_tolerance_deg": 1,
            "center": {"z_min": 35.9},
            "sort_by": "area",
            "sort_order": "desc",
            "limit": 1,
        },
    )
    assert resized_top_face["match_count"] == 1, resized_top_face
    assert resized_top_face["matches"][0]["center"]["z"] == pytest.approx(36.0)

    await _assert_parametric_model_valid(tools, doc_name)
