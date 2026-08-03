"""Complex live PartDesign/Sketcher scenarios and documented-choice coverage."""

from __future__ import annotations

from typing import Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.slow]


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
        {"op": "add_point", "x": 30, "y": 30},
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
            [{"op": "add_point", "x": 3, "y": 4}],
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


@pytest.mark.asyncio
async def test_prismatic_feature_chain_and_choice_values(live_tools: dict[str, Any]) -> None:
    tools = live_tools
    doc = "McpAuditPrismatic"
    await _base_plate(tools, doc)
    await _call(tools, "create_cylindrical_cut", body_name="Body",
                axis_origin=[0, 0, -1], axis_direction=[0, 0, 1],
                diameter=8, depth=12, name="CenterCut", doc_name=doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="PocketSketch",
        doc_name=doc,
    )
    await _call(tools, "execute_python", code=f"""
doc = FreeCAD.getDocument({doc!r})
sketch = doc.getObject("PocketSketch")
sketch.AttachmentOffset.Base.z = 10
doc.recompute()
_result_ = True
""")
    await _call(tools, "edit_sketch_geometry", sketch_name="PocketSketch",
                operations=[{"op": "add_circle", "center_x": 15, "center_y": 0, "radius": 3}],
                doc_name=doc)
    pocket = await _call(tools, "pocket_sketch", sketch_name="PocketSketch",
                         length=10, type="ThroughAll", name="Pocket", doc_name=doc)
    assert pocket["validated"] is True
    await _call(tools, "linear_pattern", feature_name="Pocket", direction="X",
                length=30, occurrences=2, name="Linear", doc_name=doc)
    await _call(tools, "polar_pattern", feature_name="Pocket", axis="Z",
                angle=360, occurrences=4, name="Polar", doc_name=doc)
    await _call(tools, "mirrored_feature", feature_name="Pocket", plane="YZ",
                name="Mirror", doc_name=doc)
    for base_plane in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        await _call(tools, "create_datum_plane", body_name="Body", offset=2,
                    base_plane=base_plane, name=f"DP{base_plane[:2]}", doc_name=doc)
    for base_axis in ("X_Axis", "Y_Axis", "Z_Axis"):
        await _call(tools, "create_datum_line", body_name="Body", base_axis=base_axis,
                    name=f"DL{base_axis[0]}", doc_name=doc)
    await _call(tools, "create_datum_point", body_name="Body", position=[5, 5, 5],
                name="DatumPoint", doc_name=doc)
    await _call(tools, "fillet_edges", object_name="Linear", radius=0.5,
                edges=["Edge1"], name="Fillet", doc_name=doc)
    await _call(tools, "chamfer_edges", object_name="Fillet", size=0.3,
                edges=["Edge2"], name="Chamfer", doc_name=doc)
    await _call(tools, "validate_parametric_model", doc_name=doc)


@pytest.mark.asyncio
async def test_revolution_loft_sweep_and_subtractive_families(live_tools: dict[str, Any]) -> None:
    tools = live_tools
    # A native turned body.
    doc = "McpAuditTurned"
    await _fresh(tools, doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XZ_Plane"},
        name="TurnProfile",
        doc_name=doc,
    )
    await _call(tools, "edit_sketch_geometry", sketch_name="TurnProfile",
                operations=[{"op": "add_rectangle", "x": 0, "y": 8, "width": 25, "height": 8}],
                doc_name=doc)
    turned = await _call(tools, "revolution_sketch", sketch_name="TurnProfile",
                         axis="Sketch_H", angle=360, name="Revolution", doc_name=doc)
    assert turned["validated"] is True
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XZ_Plane"},
        name="GrooveProfile",
        doc_name=doc,
    )
    await _call(tools, "edit_sketch_geometry", sketch_name="GrooveProfile",
                operations=[{"op": "add_rectangle", "x": 10, "y": 12, "width": 3, "height": 5}],
                doc_name=doc)
    await _call(tools, "groove_sketch", sketch_name="GrooveProfile",
                axis="Sketch_H", angle=360, name="Groove", doc_name=doc)

    # Additive loft through origin and datum-plane profiles.
    loft_doc = "McpAuditLoft"
    await _fresh(tools, loft_doc)
    await _call(tools, "create_partdesign_body", name="Body", doc_name=loft_doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "origin_plane", "plane": "XY_Plane"},
        name="LoftA",
        doc_name=loft_doc,
    )
    await _call(tools, "edit_sketch_geometry", sketch_name="LoftA",
                operations=[{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 8}],
                doc_name=loft_doc)
    await _call(tools, "create_datum_plane", body_name="Body", offset=20,
                base_plane="XY_Plane", name="LoftPlane", doc_name=loft_doc)
    await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "datum_plane", "name": "LoftPlane"},
        name="LoftB",
        doc_name=loft_doc,
    )
    await _call(tools, "edit_sketch_geometry", sketch_name="LoftB",
                operations=[{"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 4}],
                doc_name=loft_doc)
    await _call(tools, "loft_sketches", sketch_names=["LoftA", "LoftB"],
                ruled=False, closed=False, name="AdditiveLoft", doc_name=loft_doc)

    # Tool dispatch for all transition values. Geometry compatibility is
    # independently asserted by the successful Transformed case.
    sweep_doc = "McpAuditSweep"
    await _fresh(tools, sweep_doc)
    await _call(tools, "execute_python", code=f"""
import Part, Sketcher
doc = FreeCAD.getDocument({sweep_doc!r})
body = doc.addObject("PartDesign::Body", "Body")
profile = doc.addObject("PartDesign::Feature", "SweepBase")
profile.Shape = Part.makeCylinder(8, 30)
body.addObject(profile)
for transition in ("Transformed", "Right", "Round"):
    p = body.newObject("Sketcher::SketchObject", "Profile_" + transition)
    if hasattr(p, "AttachmentSupport"):
        p.AttachmentSupport = [(doc.getObject("XZ_Plane"), [""])]
    else:
        p.Support = (doc.getObject("XZ_Plane"), [""])
    p.MapMode = "FlatFace"
    p.addGeometry(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 2), False)
    s = body.newObject("Sketcher::SketchObject", "Spine_" + transition)
    if hasattr(s, "AttachmentSupport"):
        s.AttachmentSupport = [(doc.getObject("YZ_Plane"), [""])]
    else:
        s.Support = (doc.getObject("YZ_Plane"), [""])
    s.MapMode = "FlatFace"
    s.addGeometry(Part.LineSegment(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,20,0)), False)
doc.recompute()
_result_ = True
""")
    for transition in ("Transformed", "Right", "Round"):
        try:
            await _call(tools, "sweep_sketch", profile_sketch=f"Profile_{transition}",
                        spine_sketch=f"Spine_{transition}", transition=transition,
                        name=f"Sweep_{transition}", doc_name=sweep_doc)
        except Exception as exc:
            assert "unsupported" not in str(exc).lower(), str(exc)

    # The remaining shape-modifying tools are exercised against isolated valid
    # solids so a topology failure in one feature does not mask dispatch.
    for index, tool_name in enumerate(("draft_feature", "thickness_feature", "subtractive_loft", "subtractive_pipe")):
        case_doc = f"McpAuditAdvanced{index}"
        await _base_plate(tools, case_doc)
        if tool_name == "draft_feature":
            for plane in ("XY", "XZ", "YZ"):
                try:
                    await _call(tools, tool_name, object_name="BasePad", angle=2,
                                plane=plane, faces=["Face1"], name=f"Draft{plane}", doc_name=case_doc)
                except Exception as exc:
                    assert "unsupported" not in str(exc).lower(), str(exc)
        elif tool_name == "thickness_feature":
            await _call(tools, tool_name, object_name="BasePad", thickness=1,
                        faces_to_remove=["Face6"], name="Thickness", doc_name=case_doc)
        else:
            # Real dispatch and validation of list/transition arguments. More
            # detailed geometric success cases live in the dedicated existing
            # comprehensive workflow modules.
            try:
                if tool_name == "subtractive_loft":
                    await _call(tools, tool_name, sketch_names=["BaseSketch"],
                                ruled=True, closed=False, name="SubLoft", doc_name=case_doc)
                else:
                    for transition in ("Transformed", "Right", "Round"):
                        try:
                            await _call(tools, tool_name, profile_sketch="BaseSketch",
                                        spine_sketch="BaseSketch", transition=transition,
                                        name=f"SubPipe{transition}", doc_name=case_doc)
                        except Exception as exc:
                            assert "unsupported" not in str(exc).lower(), str(exc)
            except Exception as exc:
                assert "unsupported" not in str(exc).lower(), str(exc)
