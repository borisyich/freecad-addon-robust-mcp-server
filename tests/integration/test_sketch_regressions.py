"""Live regressions for sketch topology, angle units, and sketch-only validation."""

from __future__ import annotations

import math
from typing import Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_sketch_profile_rejects_hole_intersecting_outer_contour(
    live_tools: dict[str, Any],
) -> None:
    """A closed circle crossing the outer loop must not be profile-ready."""
    tools = live_tools
    doc_name = "McpAuditSketchIntersectingHole"
    await _fresh(tools, doc_name)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc_name)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="Profile",
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="Profile",
        operations=[
            {"op": "add_rectangle", "x": 0, "y": 0, "width": 50, "height": 30},
            {"op": "add_circle", "center_x": 48, "center_y": 15, "radius": 5},
        ],
        doc_name=doc_name,
    )

    info = await _call(
        tools,
        "get_sketch_info",
        sketch_name="Profile",
        doc_name=doc_name,
    )
    profile = info["sketch_status"]["profile"]

    assert profile["closed_wire_count"] == 2
    assert profile["state"] == "intersecting"
    assert profile["topology_valid"] is False
    assert profile["intersecting_wire_pairs"], profile
    assert info["sketch_status"]["profile_ready"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        {"op": "angle", "geometry1": 0, "value": 45.0},
        {
            "op": "add_constraint",
            "constraint_type": "Angle",
            "geometry1": 0,
            "value": 45.0,
        },
    ],
    ids=["named-angle-operation", "generic-angle-constraint"],
)
async def test_sketch_angle_constraint_uses_degrees_at_mcp_boundary(
    live_tools: dict[str, Any], operation: dict[str, Any]
) -> None:
    """Both public angle-constraint paths accept degrees, not Sketcher radians."""
    tools = live_tools
    suffix = "Named" if operation["op"] == "angle" else "Generic"
    doc_name = f"McpAuditSketchAngleDegrees{suffix}"
    await _fresh(tools, doc_name)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc_name)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="AngleSketch",
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="AngleSketch",
        operations=[{"op": "add_line", "x1": 0, "y1": 0, "x2": 10, "y2": 1}],
        doc_name=doc_name,
    )

    result = await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="AngleSketch",
        operations=[operation],
        doc_name=doc_name,
        detail_level="full",
    )

    constraint = result["constraints"][0]
    assert constraint["constraint_type"] == "Angle"
    assert constraint["value"] == pytest.approx(45.0, abs=1e-6)
    assert constraint["value_unit"] == "deg"

    line = result["geometry"][0]
    dx = line["end_point"]["x"] - line["start_point"]["x"]
    dy = line["end_point"]["y"] - line["start_point"]["y"]
    line_angle_deg = math.degrees(math.atan2(dy, dx))
    assert line_angle_deg == pytest.approx(45.0, abs=1e-5)


@pytest.mark.asyncio
async def test_sketch_target_validation_accepts_spreadsheet_driven_sketch_without_solid(
    live_tools: dict[str, Any],
) -> None:
    """A required alias driving regular sketch geometry needs no Pad or Body Tip."""
    tools = live_tools
    doc_name = "McpAuditSketchTargetValidation"
    await _fresh(tools, doc_name)
    await _call(tools, "spreadsheet_create", name="Dimensions", doc_name=doc_name)
    await _call(
        tools,
        "spreadsheet_apply_batch",
        spreadsheet_name="Dimensions",
        cells=[{"cell": "A1", "value": "40 mm"}],
        aliases=[{"cell": "A1", "alias": "Width"}],
        doc_name=doc_name,
    )
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc_name)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="FlatPattern",
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="FlatPattern",
        operations=[
            {"op": "add_rectangle", "x": 0, "y": 0, "width": 40, "height": 20}
        ],
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="FlatPattern",
        operations=[
            {
                "op": "distance",
                "geometry1": 0,
                "value": 40.0,
                "constraint_name": "Width",
                "expression": "Dimensions.Width",
            }
        ],
        doc_name=doc_name,
    )

    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        recompute=True,
        required_dimension_names=["Width"],
        target={"kind": "sketch", "name": "FlatPattern"},
        detail_level="full",
    )

    usage = {
        item["name"]: item["status"]
        for item in report["dimension_inventory"]["usage"]
    }
    errors = [
        finding
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    ]

    assert usage == {"Width": "sketch_driving"}
    assert report["assessment"] != "invalid_or_broken", report
    assert not errors, errors
    assert all(
        finding.get("category") not in {"body_tip_missing", "body_tip_invalid"}
        for finding in report.get("findings", [])
    )


@pytest.mark.asyncio
async def test_sketch_target_validation_rejects_construction_only_required_dimension(
    live_tools: dict[str, Any],
) -> None:
    """A Spreadsheet alias used only by construction geometry is not sketch-driving."""
    tools = live_tools
    doc_name = "McpAuditSketchConstructionOnlyDimension"
    await _fresh(tools, doc_name)
    await _call(tools, "spreadsheet_create", name="Dimensions", doc_name=doc_name)
    await _call(
        tools,
        "spreadsheet_apply_batch",
        spreadsheet_name="Dimensions",
        cells=[{"cell": "A1", "value": "12 mm"}],
        aliases=[{"cell": "A1", "alias": "HelperLength"}],
        doc_name=doc_name,
    )
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc_name)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="FlatPattern",
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="FlatPattern",
        operations=[
            {"op": "add_rectangle", "x": 0, "y": 0, "width": 40, "height": 20},
            {
                "op": "add_line",
                "x1": 5,
                "y1": 5,
                "x2": 17,
                "y2": 5,
                "construction": True,
            },
        ],
        doc_name=doc_name,
    )
    await _call(
        tools,
        "edit_sketch_constraints",
        sketch_name="FlatPattern",
        operations=[
            {
                "op": "distance",
                "geometry1": 4,
                "value": 12.0,
                "constraint_name": "HelperLength",
                "expression": "Dimensions.HelperLength",
            }
        ],
        doc_name=doc_name,
    )

    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        recompute=True,
        required_dimension_names=["HelperLength"],
        target={"kind": "sketch", "name": "FlatPattern"},
        detail_level="full",
    )

    usage = {
        item["name"]: item["status"]
        for item in report["dimension_inventory"]["usage"]
    }
    matching_findings = [
        finding
        for finding in report.get("findings", [])
        if finding.get("category") == "required_dimension_unlinked"
    ]

    assert usage == {"HelperLength": "defined_but_not_sketch_driving"}
    assert matching_findings, report
    assert report["assessment"] == "invalid_or_broken", report
