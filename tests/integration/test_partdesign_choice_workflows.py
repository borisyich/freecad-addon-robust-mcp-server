"""Complex live PartDesign/Sketcher scenarios and documented-choice coverage."""

from __future__ import annotations

from typing import Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _execute_python_result(
    tools: dict[str, Any], *, code: str
) -> Any:
    """Execute bridge code and return only its user payload."""
    response = await _call(tools, "execute_python", code=code)
    assert isinstance(response, dict), response
    assert response.get("success") is True, response
    assert "result" in response, response
    return response["result"]


async def _base_plate(tools: dict[str, Any], doc: str, body: str = "Body") -> str:
    await _fresh(tools, doc)
    await _call(tools, "create_partdesign_body", name=body, doc_name=doc)
    await _call(
        tools,
        "create_sketch",
        body_name=body,
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="BaseSketch",
        doc_name=doc,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BaseSketch",
        operations=[{"op": "add_rectangle", "x": -30, "y": -20, "width": 60, "height": 40}],
        doc_name=doc,
    )
    info = await _call(tools, "get_sketch_info", sketch_name="BaseSketch", doc_name=doc)
    assert info["sketch_status"]["profile"]["state"] == "closed"
    result = await _call(tools, "pad_sketch", sketch_name="BaseSketch", length=10,
                         direction=[0, 0, 1], name="BasePad", doc_name=doc)
    assert result["validated"] is True
    return result["name"]


async def _assert_valid_model(tools: dict[str, Any], doc: str) -> dict[str, Any]:
    report = await _call(
        tools, "validate_parametric_model", doc_name=doc, recompute=True
    )
    errors = [
        finding
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    ]
    assert report.get("document", {}).get("recompute_error") is None, report
    assert report.get("assessment") != "invalid_or_broken", report
    assert not errors, errors
    return report


async def _plate_with_offset_pocket(
    tools: dict[str, Any], doc: str, *, x: float = -15.0
) -> str:
    await _base_plate(tools, doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="PocketSketch",
        doc_name=doc,
    )
    await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
sketch = doc.getObject("PocketSketch")
sketch.AttachmentOffset.Base.z = 10
doc.recompute()
_result_ = True
''',
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="PocketSketch",
        operations=[
            {"op": "add_circle", "center_x": x, "center_y": 0, "radius": 3}
        ],
        doc_name=doc,
    )
    pocket = await _call(
        tools,
        "pocket_sketch",
        sketch_name="PocketSketch",
        length=10,
        type="ThroughAll",
        direction="reversed",
        name="Pocket",
        doc_name=doc,
    )
    assert pocket["validated"] is True
    return pocket["name"]


@pytest.mark.asyncio
async def test_pocket_direction_follows_global_sketch_normal(
    live_tools: dict[str, Any],
) -> None:
    """A bottom-plane normal pocket must cut upward into a positive-Z pad."""
    tools = live_tools
    doc = "McpAuditPocketNormalDirection"
    await _base_plate(tools, doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="BottomPocketSketch",
        doc_name=doc,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BottomPocketSketch",
        operations=[
            {"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 3}
        ],
        doc_name=doc,
    )
    pocket = await _call(
        tools,
        "pocket_sketch",
        sketch_name="BottomPocketSketch",
        length=10,
        type="ThroughAll",
        direction="normal",
        name="BottomPocket",
        doc_name=doc,
    )
    assert pocket["validated"] is True
    assert pocket["removed_volume"] > 0
    assert pocket["effective_direction"] == [0.0, 0.0, 1.0]


async def _setup_pipe_sketches(
    tools: dict[str, Any], doc: str, *, subtractive: bool
) -> None:
    await _fresh(tools, doc)
    result = await _execute_python_result(
        tools,
        code=f'''
import Part
import Sketcher
doc = FreeCAD.getDocument({doc!r})
body = doc.addObject("PartDesign::Body", "Body")
if {subtractive!r}:
    base = body.newObject("PartDesign::Feature", "BaseSolid")
    base.Shape = Part.makeBox(60, 40, 20, FreeCAD.Vector(-30, -20, -10))
    body.Tip = base
profile = body.newObject("Sketcher::SketchObject", "Profile")
profile.MapMode = "Deactivated"
profile.Placement = FreeCAD.Placement(
    FreeCAD.Vector({-31 if subtractive else 0}, 0, 0),
    FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), FreeCAD.Vector(1, 0, 0)),
)
profile.addGeometry(
    Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 3),
    False,
)
spine = body.newObject("Sketcher::SketchObject", "Spine")
spine.MapMode = "Deactivated"
spine.addGeometry(
    Part.LineSegment(
        FreeCAD.Vector({-31 if subtractive else 0}, 0, 0),
        FreeCAD.Vector({31 if subtractive else 30}, 0, 0),
    ),
    False,
)
doc.recompute()
_result_ = {{
    "profile_wires": len(profile.Shape.Wires),
    "spine_edges": len(spine.Shape.Edges),
}}
''',
    )
    assert result == {"profile_wires": 1, "spine_edges": 1}


@pytest.mark.asyncio
async def test_create_sketch_typed_support_variants(live_tools: dict[str, Any]) -> None:
    """All four discriminated support variants must work in real FreeCAD."""
    tools = live_tools

    origin_doc = "McpAuditSupportOrigin"
    await _fresh(tools, origin_doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=origin_doc)
    origin = await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XZ_Plane"},
        name="OriginSketch",
        doc_name=origin_doc,
    )
    assert origin["support_kind"] == "origin_plane"

    for kind, support in (
        ("body_tip_face", {"kind": "body_tip_face", "face": "Face6"}),
        (
            "feature_face",
            {"kind": "feature_face", "feature": "BasePad", "face": "Face6"},
        ),
    ):
        doc = f"McpAuditSupport{kind.title().replace('_', '')}"
        await _base_plate(tools, doc)
        result = await _call(
            tools,
            "create_sketch",
            body_name="Body",
            support=support,
            name=f"{kind}Sketch",
            doc_name=doc,
        )
        assert result["support_kind"] == kind
        assert result["support"].endswith("Face6")

    datum_doc = "McpAuditSupportDatum"
    await _fresh(tools, datum_doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=datum_doc)
    await _call(
        tools,
        "create_datum_plane",
        body_name="Body",
        base_plane="XY_Plane",
        offset=12,
        name="SketchDatum",
        doc_name=datum_doc,
    )
    datum = await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "datum_plane", "name": "SketchDatum"},
        name="DatumSketch",
        doc_name=datum_doc,
    )
    assert datum["support_kind"] == "datum_plane"


@pytest.mark.asyncio
async def test_sketch_geometry_and_constraint_operation_catalog(live_tools: dict[str, Any]) -> None:
    tools = live_tools
    doc = "McpAuditSketchOps"
    await _fresh(tools, doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="Geometry",
        doc_name=doc,
    )
    operations = [
        {"op": "add_rectangle", "x": -20, "y": -10, "width": 15, "height": 10},
        {"op": "add_circle", "center_x": 5, "center_y": 5, "radius": 3},
        {"op": "add_line", "x1": 0, "y1": 20, "x2": 10, "y2": 20},
        {"op": "add_arc", "center_x": 20, "center_y": 20, "radius": 4,
         "start_angle": 0, "end_angle": 180},
        {"op": "add_point", "x": 30, "y": 30, "construction": True},
        {"op": "add_ellipse", "center_x": 40, "center_y": 0,
         "major_radius": 6, "minor_radius": 3},
        {"op": "add_regular_polygon", "center_x": 40, "center_y": 20,
         "radius": 5, "sides": 5},
        {"op": "add_slot", "center1_x": -5, "center1_y": 30,
         "center2_x": 10, "center2_y": 30, "radius": 3},
        {"op": "add_bspline", "points": [[20, 30], [25, 35], [30, 28], [35, 32]]},
        {"op": "toggle_construction", "geometry_index": 8},
        {"op": "delete_geometry", "geometry_index": 8},
        {"op": "add_polyline", "points": [[50, 30], [55, 35], [60, 30]],
         "closed": False},
    ]
    result = await _call(tools, "edit_sketch_geometry", sketch_name="Geometry",
                         operations=operations, doc_name=doc)
    assert result["operations_applied"] == len(operations)
    assert result["operation_results"][3]["point_indices"] == {
        "start": 1,
        "end": 2,
        "center": 3,
    }
    assert result["operation_results"][4]["construction"] is True
    assert result["sketch_status"]["construction_geometry_count"] >= 1
    external_doc = "McpAuditExternalGeometry"
    await _fresh(tools, external_doc)
    await _call(
        tools,
        "create_primitive",
        primitive={"kind": "box", "length": 10, "width": 10, "height": 10},
        name="ExternalBox",
        doc_name=external_doc,
    )
    await _call(
        tools,
        "create_sketch",
        body_name=None,
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="ExternalGeometrySketch",
        doc_name=external_doc,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="ExternalGeometrySketch",
        operations=[{"op": "add_external_geometry", "object_name": "ExternalBox",
                     "element": "Edge1"}],
        doc_name=external_doc,
    )

    # Each constraint operation is isolated so a deliberate solver interaction
    # cannot hide parser/dispatch defects in later operations.
    constraint_cases = {
        "horizontal": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 10, "y2": 1}],
            {"op": "horizontal", "geometry1": 0},
        ),
        "vertical": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 1, "y2": 10}],
            {"op": "vertical", "geometry1": 0},
        ),
        "coincident": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 10, "y2": 0},
             {"op": "add_line", "x1": 11, "y1": 0, "x2": 20, "y2": 0}],
            {"op": "coincident", "geometry1": 0, "point1": 2, "geometry2": 1, "point2": 1},
        ),
        "parallel": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 10, "y2": 1},
             {"op": "add_line", "x1": 0, "y1": 5, "x2": 10, "y2": 7}],
            {"op": "parallel", "geometry1": 0, "geometry2": 1},
        ),
        "perpendicular": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 10, "y2": 1},
             {"op": "add_line", "x1": 0, "y1": 0, "x2": 1, "y2": 10}],
            {"op": "perpendicular", "geometry1": 0, "geometry2": 1},
        ),
        "tangent": (
            [{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 5},
             {"op": "add_circle", "center_x": 11, "center_y": 0, "radius": 5}],
            {"op": "tangent", "geometry1": 0, "geometry2": 1},
        ),
        "equal": (
            [{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 5},
             {"op": "add_circle", "center_x": 20, "center_y": 0, "radius": 6}],
            {"op": "equal", "geometry1": 0, "geometry2": 1},
        ),
        "distance": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 9, "y2": 0}],
            {"op": "distance", "geometry1": 0, "value": 10},
        ),
        "distance_x": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 9, "y2": 3}],
            {"op": "distance_x", "geometry1": 0, "point1": 1,
             "geometry2": 0, "point2": 2, "value": 10},
        ),
        "distance_y": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 3, "y2": 9}],
            {"op": "distance_y", "geometry1": 0, "point1": 1,
             "geometry2": 0, "point2": 2, "value": 10},
        ),
        "radius": (
            [{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 4}],
            {"op": "radius", "geometry1": 0, "value": 5},
        ),
        "angle": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 9, "y2": 2}],
            {"op": "angle", "geometry1": 0, "value": 0.5},
        ),
        "fix": (
            [
                {"op": "add_line", "x1": 0, "y1": 0, "x2": 5, "y2": 0},
                {"op": "add_line", "x1": 5, "y1": 0, "x2": 5, "y2": 5},
            ],
            {"op": "fix", "geometry1": 0},
        ),
        "add_constraint": (
            [{"op": "add_line", "x1": 0, "y1": 0, "x2": 9, "y2": 1}],
            {"op": "add_constraint", "constraint_type": "Horizontal", "geometry1": 0},
        ),
    }
    for index, (case, (geometry, constraint)) in enumerate(constraint_cases.items()):
        sketch = f"C{index}_{case}"
        await _call(
            tools,
            "create_sketch",
            body_name="Body",
            support={"kind": "origin_plane", "plane": "XY_Plane"},
            name=sketch,
            doc_name=doc,
        )
        await _call(tools, "edit_sketch_geometry", sketch_name=sketch,
                    operations=geometry, doc_name=doc)
        result = await _call(tools, "edit_sketch_constraints", sketch_name=sketch,
                             operations=[constraint], doc_name=doc)
        assert result["operation_results"][0]["op"] == constraint["op"]
        if result["sketch_status"]["constraint_count"]:
            await _call(
                tools,
                "edit_sketch_constraints",
                sketch_name=sketch,
                operations=[{"op": "delete_constraint", "constraint_index": 0}],
                doc_name=doc,
            )

    limit_sketch = "FixLimit"
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name=limit_sketch,
        doc_name=doc,
    )
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name=limit_sketch,
        operations=[{"op": "add_line", "x1": 0, "y1": 0, "x2": 5, "y2": 0}],
        doc_name=doc,
    )
    with pytest.raises(ValueError, match="more than 50%"):
        await _call(
            tools,
            "edit_sketch_constraints",
            sketch_name=limit_sketch,
            operations=[{"op": "fix", "geometry1": 0}],
            doc_name=doc,
        )
    limit_info = await _call(
        tools, "get_sketch_info", sketch_name=limit_sketch, doc_name=doc
    )
    assert limit_info["sketch_status"]["constraint_count"] == 0


@pytest.mark.asyncio
async def test_prismatic_feature_chain_and_choice_values(live_tools: dict[str, Any]) -> None:
    tools = live_tools

    # Each transformation owns a fresh linear Body history. Parallel branches
    # in one Body are not a realistic PartDesign workflow.
    linear_doc = "McpAuditPrismaticLinear"
    await _plate_with_offset_pocket(tools, linear_doc)
    linear = await _call(
        tools, "linear_pattern", feature_name="Pocket", direction="X",
        length=30, occurrences=2, name="Linear", doc_name=linear_doc,
    )
    assert linear["validated"] is True
    await _assert_valid_model(tools, linear_doc)

    # A dress-up on BasePad would insert a branch behind the current Linear Tip.
    # The tool must reject it before creating a feature or corrupting the DAG.
    with pytest.raises(ValueError, match="current Body Tip"):
        await _call(
            tools, "fillet_edges", object_name="BasePad", radius=1.0,
            edges=["Edge1"], name="StaleFillet", doc_name=linear_doc,
        )
    unchanged = await _execute_python_result(
        tools,
        code=f'''
doc = FreeCAD.getDocument({linear_doc!r})
body = doc.getObject("Body")
_result_ = {{
    "tip": getattr(body.Tip, "Name", None),
    "stale_feature_absent": doc.getObject("StaleFillet") is None,
}}
''',
    )
    assert unchanged == {"tip": "Linear", "stale_feature_absent": True}
    await _assert_valid_model(tools, linear_doc)

    polar_doc = "McpAuditPrismaticPolar"
    await _plate_with_offset_pocket(tools, polar_doc)
    polar = await _call(
        tools, "polar_pattern", feature_name="Pocket", axis="Z",
        angle=360, occurrences=4, name="Polar", doc_name=polar_doc,
    )
    assert polar["validated"] is True
    await _assert_valid_model(tools, polar_doc)

    mirror_doc = "McpAuditPrismaticMirror"
    await _plate_with_offset_pocket(tools, mirror_doc)
    mirror = await _call(
        tools, "mirrored_feature", feature_name="Pocket", plane="YZ",
        name="Mirror", doc_name=mirror_doc,
    )
    assert mirror["validated"] is True
    assert mirror["tip"] == "Mirror"
    assert mirror["tip_matches"] is True
    await _assert_valid_model(tools, mirror_doc)

    # Dress-up features are independent terminal operations. Chaining them
    # through stale pattern branches caused the previous DAG warnings.
    fillet_doc = "McpAuditPrismaticFillet"
    await _base_plate(tools, fillet_doc)
    fillet = await _call(
        tools, "fillet_edges", object_name="BasePad", radius=1.0,
        edges=["Edge1"], name="Fillet", doc_name=fillet_doc,
    )
    assert fillet["validated"] is True
    await _assert_valid_model(tools, fillet_doc)

    chamfer_doc = "McpAuditPrismaticChamfer"
    await _base_plate(tools, chamfer_doc)
    chamfer = await _call(
        tools, "chamfer_edges", object_name="BasePad", size=1.0,
        edges=["Edge1"], name="Chamfer", doc_name=chamfer_doc,
    )
    assert chamfer["validated"] is True
    await _assert_valid_model(tools, chamfer_doc)

    datum_doc = "McpAuditPrismaticDatum"
    await _base_plate(tools, datum_doc)
    for base_plane in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        datum_plane = await _call(
            tools, "create_datum_plane", body_name="Body", offset=2,
            base_plane=base_plane, name=f"DP{base_plane[:2]}", doc_name=datum_doc,
        )
        assert datum_plane["validated"] is True
        assert datum_plane["tip"] == "BasePad"
        assert datum_plane["tip_preserved"] is True
    expected_directions = {
        "X_Axis": [1.0, 0.0, 0.0],
        "Y_Axis": [0.0, 1.0, 0.0],
        "Z_Axis": [0.0, 0.0, 1.0],
    }
    for base_axis, expected in expected_directions.items():
        datum = await _call(
            tools, "create_datum_line", body_name="Body", base_axis=base_axis,
            name=f"DL{base_axis[0]}", doc_name=datum_doc,
        )
        assert datum["validated"] is True
        assert datum["map_mode"] == "Deactivated"
        assert datum["direction"] == pytest.approx(expected, abs=1e-8)
    datum_point = await _call(
        tools, "create_datum_point", body_name="Body", position=[5, 5, 5],
        name="DatumPoint", doc_name=datum_doc,
    )
    assert datum_point["validated"] is True
    assert datum_point["tip"] == "BasePad"
    assert datum_point["tip_preserved"] is True
    assert datum_point["position"] == pytest.approx([5.0, 5.0, 5.0], abs=1e-8)
    datum_tree = await _execute_python_result(
        tools,
        code=f'''
body = FreeCAD.getDocument({datum_doc!r}).getObject("Body")
_result_ = {{
    "tip": getattr(body.Tip, "Name", None),
    "datum_names": sorted(
        obj.Name for obj in body.Group
        if getattr(obj, "TypeId", "").startswith((
            "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point"
        ))
    ),
}}
''',
    )
    assert datum_tree["tip"] == "BasePad"
    assert datum_tree["datum_names"] == sorted(
        ["DPXY", "DPXZ", "DPYZ", "DLX", "DLY", "DLZ", "DatumPoint"]
    )
    await _assert_valid_model(tools, datum_doc)


@pytest.mark.asyncio
async def test_revolution_loft_sweep_and_subtractive_families(live_tools: dict[str, Any]) -> None:
    tools = live_tools

    turned_doc = "McpAuditTurned"
    await _fresh(tools, turned_doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=turned_doc)
    await _call(
        tools, "create_sketch", body_name="Body",
        support={"kind": "origin_plane", "plane": "XZ_Plane"},
        name="TurnProfile", doc_name=turned_doc,
    )
    await _call(
        tools, "edit_sketch_geometry", sketch_name="TurnProfile",
        operations=[{"op": "add_rectangle", "x": 0, "y": 8, "width": 25, "height": 8}],
        doc_name=turned_doc,
    )
    turned = await _call(
        tools, "revolution_sketch", sketch_name="TurnProfile",
        axis="Sketch_H", angle=360, name="Revolution", doc_name=turned_doc,
    )
    assert turned["validated"] is True
    await _call(
        tools, "create_sketch", body_name="Body",
        support={"kind": "origin_plane", "plane": "XZ_Plane"},
        name="GrooveProfile", doc_name=turned_doc,
    )
    await _call(
        tools, "edit_sketch_geometry", sketch_name="GrooveProfile",
        operations=[{"op": "add_rectangle", "x": 10, "y": 12, "width": 3, "height": 5}],
        doc_name=turned_doc,
    )
    groove = await _call(
        tools, "groove_sketch", sketch_name="GrooveProfile",
        axis="Sketch_H", angle=360, name="Groove", doc_name=turned_doc,
    )
    assert groove["validated"] is True
    await _assert_valid_model(tools, turned_doc)

    loft_doc = "McpAuditLoft"
    await _fresh(tools, loft_doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=loft_doc)
    await _call(
        tools, "create_sketch", body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="LoftA", doc_name=loft_doc,
    )
    await _call(
        tools, "edit_sketch_geometry", sketch_name="LoftA",
        operations=[{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 8}],
        doc_name=loft_doc,
    )
    await _call(
        tools, "create_datum_plane", body_name="Body", offset=20,
        base_plane="XY_Plane", name="LoftPlane", doc_name=loft_doc,
    )
    await _call(
        tools, "create_sketch", body_name="Body",
        support={"kind": "datum_plane", "name": "LoftPlane"},
        name="LoftB", doc_name=loft_doc,
    )
    await _call(
        tools, "edit_sketch_geometry", sketch_name="LoftB",
        operations=[{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 4}],
        doc_name=loft_doc,
    )
    loft = await _call(
        tools, "loft_sketches", sketch_names=["LoftA", "LoftB"],
        ruled=False, closed=False, name="AdditiveLoft", doc_name=loft_doc,
    )
    assert loft["validated"] is True
    await _assert_valid_model(tools, loft_doc)

    # A straight path is intentionally used for all transition enum values:
    # each case is geometrically valid, not merely a dispatch probe.
    for transition in ("Transformed", "Right", "Round"):
        sweep_doc = f"McpAuditSweep{transition}"
        await _setup_pipe_sketches(tools, sweep_doc, subtractive=False)
        sweep = await _call(
            tools, "sweep_sketch", profile_sketch="Profile", spine_sketch="Spine",
            transition=transition, name=f"Sweep{transition}", doc_name=sweep_doc,
        )
        assert sweep["validated"] is True
        await _assert_valid_model(tools, sweep_doc)

    # Each neutral plane is a true boundary of the selected side face.
    draft_cases = {
        "XY": ([-20, -15, 0], [40, 30, 20], [1, 0, 0]),
        "XZ": ([-20, 0, -15], [40, 20, 30], [1, 0, 0]),
        "YZ": ([0, -20, -15], [20, 40, 30], [0, 1, 0]),
    }
    for plane, (origin, size, face_normal) in draft_cases.items():
        draft_doc = f"McpAuditDraft{plane}"
        await _fresh(tools, draft_doc)
        setup = await _execute_python_result(
            tools,
            code=f'''
import Part
doc = FreeCAD.getDocument({draft_doc!r})
body = doc.addObject("PartDesign::Body", "Body")
base = body.newObject("PartDesign::Feature", "BaseSolid")
base.Shape = Part.makeBox(
    {size[0]}, {size[1]}, {size[2]}, FreeCAD.Vector(*{origin!r})
)
body.Tip = base
doc.recompute()
target = FreeCAD.Vector(*{face_normal!r})
best = max(
    range(len(base.Shape.Faces)),
    key=lambda index: float(base.Shape.Faces[index].normalAt(0, 0).dot(target)),
)
_result_ = {{"face": f"Face{{best + 1}}"}}
''',
        )
        draft = await _call(
            tools, "draft_feature", object_name="BaseSolid", angle=2,
            plane=plane, faces=[setup["face"]], name=f"Draft{plane}",
            doc_name=draft_doc,
        )
        assert draft["validated"] is True
        await _assert_valid_model(tools, draft_doc)

    thickness_doc = "McpAuditThickness"
    await _base_plate(tools, thickness_doc)
    top = await _execute_python_result(
        tools,
        code=f'''
doc = FreeCAD.getDocument({thickness_doc!r})
obj = doc.getObject("BasePad")
best = max(
    range(len(obj.Shape.Faces)),
    key=lambda index: float(obj.Shape.Faces[index].CenterOfMass.z),
)
_result_ = {{"face": f"Face{{best + 1}}"}}
''',
    )
    thickness = await _call(
        tools, "thickness_feature", object_name="BasePad", thickness=1,
        faces_to_remove=[top["face"]], name="Thickness", doc_name=thickness_doc,
    )
    assert thickness["validated"] is True
    await _assert_valid_model(tools, thickness_doc)

    subloft_doc = "McpAuditSubtractiveLoft"
    await _fresh(tools, subloft_doc)
    setup = await _execute_python_result(
        tools,
        code=f'''
import Part
import Sketcher
doc = FreeCAD.getDocument({subloft_doc!r})
body = doc.addObject("PartDesign::Body", "Body")
base = body.newObject("PartDesign::Feature", "BaseSolid")
base.Shape = Part.makeBox(20, 20, 30, FreeCAD.Vector(-10, -10, 0))
body.Tip = base
for name, z, radius in (("LoftCutA", -1, 5), ("LoftCutB", 31, 3)):
    sketch = body.newObject("Sketcher::SketchObject", name)
    sketch.MapMode = "Deactivated"
    sketch.Placement.Base.z = z
    sketch.addGeometry(
        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), radius),
        False,
    )
doc.recompute()
_result_ = {{
    "a_wires": len(doc.getObject("LoftCutA").Shape.Wires),
    "b_wires": len(doc.getObject("LoftCutB").Shape.Wires),
}}
''',
    )
    assert setup == {"a_wires": 1, "b_wires": 1}
    subloft = await _call(
        tools, "subtractive_loft", sketch_names=["LoftCutA", "LoftCutB"],
        ruled=False, closed=False, name="SubtractiveLoft", doc_name=subloft_doc,
    )
    assert subloft["validated"] is True
    assert subloft["removed_volume"] > 0
    await _assert_valid_model(tools, subloft_doc)

    for transition in ("Transformed", "Right", "Round"):
        pipe_doc = f"McpAuditSubPipe{transition}"
        await _setup_pipe_sketches(tools, pipe_doc, subtractive=True)
        pipe = await _call(
            tools, "subtractive_pipe", profile_sketch="Profile", spine_sketch="Spine",
            transition=transition, name=f"SubPipe{transition}", doc_name=pipe_doc,
        )
        assert pipe["validated"] is True
        assert pipe["removed_volume"] > 0
        await _assert_valid_model(tools, pipe_doc)
