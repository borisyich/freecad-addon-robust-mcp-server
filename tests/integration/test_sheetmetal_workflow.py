"""Live native SheetMetal workflows derived from upstream reference geometry.

The L-profile constants and bend-allowance invariant come from the upstream
``tools/calc-unfold.py`` example:
https://github.com/shaise/FreeCAD_SheetMetal/blob/master/tools/calc-unfold.py
"""

# Importing a fixture intentionally gives pytest a module-global of the same
# name used by test parameters.
# ruff: noqa: F811

from __future__ import annotations

import math
from typing import Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.slow]


THICKNESS = 2.0
INSIDE_RADIUS = 1.64
K_FACTOR = 0.38
BEND_ANGLE_DEG = 90.0
MOLD_LINE_DISTANCE = 50.0
BEND_ALLOWANCE = math.radians(BEND_ANGLE_DEG) * (
    INSIDE_RADIUS + THICKNESS * K_FACTOR
)
LEG_LENGTH = MOLD_LINE_DISTANCE - BEND_ALLOWANCE / 2.0
FLANGE_LENGTH = INSIDE_RADIUS + THICKNESS + LEG_LENGTH


async def _require_sheetmetal(
    tools: dict[str, Any], *operations: str
) -> dict[str, Any]:
    capabilities = await _call(tools, "sheet_metal_capabilities")
    if not capabilities["installed"]:
        pytest.skip("FreeCAD SheetMetal Workbench is not installed")
    missing = [
        operation
        for operation in operations
        if not capabilities["operations"].get(operation)
    ]
    if missing:
        pytest.skip("Installed SheetMetal lacks: " + ", ".join(missing))
    return capabilities


async def _create_body_sketch(
    tools: dict[str, Any], doc: str, sketch: str
) -> None:
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name=sketch,
        doc_name=doc,
    )


async def _assert_valid_model(
    tools: dict[str, Any], doc: str, dimensions: list[str]
) -> dict[str, Any]:
    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc,
        recompute=True,
        required_dimension_names=dimensions,
        detail_level="structure",
    )
    errors = [
        finding
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    ]
    assert report["assessment"] != "invalid_or_broken", report
    assert report["document"]["recompute_error"] is None, report
    assert not errors, errors
    return report


@pytest.mark.asyncio
async def test_upstream_reference_l_profile_unfolds_to_100_mm_blank(
    live_tools: dict[str, Any],
) -> None:
    """The upstream 2 mm/K=.38 reference must preserve its developed length."""
    tools = live_tools
    doc = "McpAuditSheetMetalReference"
    await _require_sheetmetal(tools, "base", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "ProfileSketch")

    # Upstream rounded values are 48.12 mm legs and a 51.76 mm flange length.
    assert pytest.approx(48.12, abs=0.005) == LEG_LENGTH
    assert pytest.approx(51.76, abs=0.005) == FLANGE_LENGTH
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="ProfileSketch",
        operations=[
            {
                "op": "add_polyline",
                "points": [
                    [0.0, FLANGE_LENGTH],
                    [0.0, 0.0],
                    [FLANGE_LENGTH, 0.0],
                ],
                "closed": False,
            }
        ],
        doc_name=doc,
    )
    constrained = await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="ProfileSketch",
        operations=[
            {"op": "vertical", "geometry1": 0},
            {"op": "horizontal", "geometry1": 1},
            {
                "op": "coincident",
                "geometry1": 0,
                "point1": 2,
                "geometry2": -1,
                "point2": 1,
            },
            {
                "op": "distance",
                "geometry1": 0,
                "value": FLANGE_LENGTH,
                "constraint_name": "VerticalFlangeLength",
            },
            {
                "op": "distance",
                "geometry1": 1,
                "value": FLANGE_LENGTH,
                "constraint_name": "HorizontalFlangeLength",
            },
        ],
        doc_name=doc,
    )
    assert constrained["sketch_status"]["solver"]["status"] == "fully_constrained"

    base = await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="ProfileSketch",
        thickness=THICKNESS,
        radius=INSIDE_RADIUS,
        wall_length=30.0,
        bend_side="inside",
        name="ReferenceLProfile",
        doc_name=doc,
    )
    assert base["validated"] is True
    assert base["proxy_type"] == "SMBaseBend"

    inspection = await _call(
        tools,
        "inspect_sheet_metal",
        object_name="ReferenceLProfile",
        doc_name=doc,
    )
    assert inspection["shape_valid"] is True
    assert inspection["solid_count"] == 1
    assert inspection["unfold_ready"] is True
    assert inspection["cylindrical_bend_face_count"] >= 1
    stationary_face = inspection["stationary_face_candidates"][0]["face"]

    unfolded = await _call(
        tools,
        "unfold_sheet_metal",
        feature_name="ReferenceLProfile",
        stationary_face=stationary_face,
        material={"k_factor": K_FACTOR, "standard": "ansi"},
        generate_sketch=True,
        separate_layers=True,
        show_bend_angles=True,
        name="ReferenceFlatPattern",
        doc_name=doc,
    )
    assert unfolded["validated"] is True
    assert unfolded["material_source"] == "manual_k_factor"
    assert unfolded["generated_sketches"]

    bounds = await _call(
        tools,
        "execute_python",
        code=f"""
doc = FreeCAD.getDocument({doc!r})
shape = doc.getObject("ReferenceFlatPattern").Shape
_result_ = {{
    "valid": bool(shape.isValid()),
    "solids": len(shape.Solids),
    "dimensions": sorted([
        float(shape.BoundBox.XLength),
        float(shape.BoundBox.YLength),
        float(shape.BoundBox.ZLength),
    ]),
}}
""",
    )
    bounds = bounds["result"]
    assert bounds["valid"] is True
    assert bounds["solids"] == 1
    # Two 50 mm mold-line legs develop into one 100 mm blank (upstream invariant).
    assert bounds["dimensions"][-1] == pytest.approx(100.0, abs=0.05)

    validation = await _assert_valid_model(
        tools, doc, ["VerticalFlangeLength", "HorizontalFlangeLength"]
    )
    usage = {
        item["name"]: item["status"]
        for item in validation["dimension_inventory"]["usage"]
    }
    assert usage == {
        "VerticalFlangeLength": "solid_driving",
        "HorizontalFlangeLength": "solid_driving",
    }


@pytest.mark.asyncio
async def test_semantic_edge_flange_and_unfold_workflow(
    live_tools: dict[str, Any],
) -> None:
    """A constrained blank becomes a native edge flange without guessed EdgeN."""
    tools = live_tools
    doc = "McpAuditSheetMetalFlange"
    await _require_sheetmetal(tools, "base", "flange", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "BlankSketch")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BlankSketch",
        operations=[
            {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 80.0, "height": 50.0}
        ],
        doc_name=doc,
    )
    constrained = await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="BlankSketch",
        operations=[
            {"op": "horizontal", "geometry1": 0},
            {"op": "vertical", "geometry1": 1},
            {"op": "horizontal", "geometry1": 2},
            {"op": "vertical", "geometry1": 3},
            {
                "op": "coincident",
                "geometry1": 0,
                "point1": 1,
                "geometry2": -1,
                "point2": 1,
            },
            {
                "op": "distance",
                "geometry1": 0,
                "value": 80.0,
                "constraint_name": "BlankWidth",
            },
            {
                "op": "distance",
                "geometry1": 1,
                "value": 50.0,
                "constraint_name": "BlankDepth",
            },
        ],
        doc_name=doc,
    )
    assert constrained["sketch_status"]["solver"]["status"] == "fully_constrained"

    base = await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="BlankSketch",
        thickness=2.0,
        radius=2.0,
        name="BaseBlank",
        doc_name=doc,
    )
    assert base["validated"] is True

    selected = await _call(
        tools,
        "select_subshapes",
        object_name="BaseBlank",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [1.0, 0.0, 0.0],
            "length_min": 79.99,
            "length_max": 80.01,
            "centroid_bounds": {
                "y_min": 49.99,
                "y_max": 50.01,
                "z_min": 1.99,
                "z_max": 2.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    assert selected["match_count"] == 1, selected

    flange = await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "flange",
            "base_feature": "BaseBlank",
            "edges": selected["references"],
            "length": 20.0,
            "radius": 2.0,
            "angle": 90.0,
            "bend_type": "material_outside",
            "length_spec": "leg",
        },
        name="EdgeFlange",
        doc_name=doc,
    )
    assert flange["validated"] is True
    assert flange["proxy_type"] == "SMBendWall"
    assert flange["references"] == selected["references"]

    inspection = await _call(
        tools,
        "inspect_sheet_metal",
        object_name="EdgeFlange",
        doc_name=doc,
    )
    assert inspection["native_sheet_metal_history"] is True
    assert inspection["tip"] == "EdgeFlange"
    assert inspection["cylindrical_bend_face_count"] >= 1
    assert inspection["warnings"] == []

    unfolded = await _call(
        tools,
        "unfold_sheet_metal",
        feature_name="EdgeFlange",
        stationary_face=inspection["stationary_face_candidates"][0]["face"],
        material={"k_factor": 0.38, "standard": "ansi"},
        name="FlangeFlatPattern",
        doc_name=doc,
    )
    assert unfolded["shape_valid"] is True
    assert unfolded["solid_count"] == 1
    assert unfolded["generated_sketches"]

    validation = await _assert_valid_model(tools, doc, ["BlankWidth", "BlankDepth"])
    usage = {
        item["name"]: item["status"]
        for item in validation["dimension_inventory"]["usage"]
    }
    assert usage == {"BlankWidth": "solid_driving", "BlankDepth": "solid_driving"}
