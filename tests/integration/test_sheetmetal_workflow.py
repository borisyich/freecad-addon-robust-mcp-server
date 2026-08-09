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
BEND_ALLOWANCE = math.radians(BEND_ANGLE_DEG) * (INSIDE_RADIUS + THICKNESS * K_FACTOR)
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


async def _create_body_sketch(tools: dict[str, Any], doc: str, sketch: str) -> None:
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


async def _sheet_state(
    tools: dict[str, Any], doc: str, formed: str, flat: str | None = None
) -> dict[str, Any]:
    """Return stable geometric invariants for formed and unfolded states."""
    result = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
def shape_state(name):
    obj = doc.getObject(name)
    shape = obj.Shape
    box = shape.BoundBox
    return {{
        "name": name,
        "valid": bool(shape.isValid()),
        "solids": len(shape.Solids),
        "volume": float(shape.Volume),
        "hash": int(shape.hashCode()),
        "bounds": [float(box.XLength), float(box.YLength), float(box.ZLength)],
        "cylindrical_faces": sum(
            1 for face in shape.Faces
            if "Cylinder" in type(face.Surface).__name__
        ),
    }}
state = {{"formed": shape_state({formed!r})}}
if {flat!r} is not None:
    flat_obj = doc.getObject({flat!r})
    state["flat"] = shape_state({flat!r})
    sketches = [doc.getObject(name) for name in list(flat_obj.UnfoldSketches)]
    state["unfold"] = {{
        "sketches": [obj.Name for obj in sketches],
        "outline_geometry": len(sketches[0].Geometry) if sketches else 0,
        "outline_wires": len(sketches[0].Shape.Wires) if sketches else 0,
        "outline_circles": sum(
            1 for geometry in sketches[0].Geometry
            if type(geometry).__name__ == "Circle"
        ) if sketches else 0,
        "outline_geometry_types": [
            type(geometry).__name__ for geometry in sketches[0].Geometry
        ] if sketches else [],
        "bend_line_geometry": next(
            (len(obj.Geometry) for obj in sketches if obj.Name.endswith("_Bends")), 0
        ),
    }}
body = doc.getObject("Body")
state["tip"] = body.Tip.Name if body and body.Tip else None
_result_ = state
''',
    )
    return result["result"]


async def _mutate_sheet_chain(
    tools: dict[str, Any],
    doc: str,
    formed: str,
    flat: str,
    mutations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mutate native properties one by one and capture downstream signatures."""
    result = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
mutations = {mutations!r}
formed = doc.getObject({formed!r})
flat = doc.getObject({flat!r})
def signature(obj):
    shape = obj.Shape
    box = shape.BoundBox
    return {{
        "valid": bool(shape.isValid()),
        "solids": len(shape.Solids),
        "volume": float(shape.Volume),
        "hash": int(shape.hashCode()),
        "bounds": [float(box.XLength), float(box.YLength), float(box.ZLength)],
    }}
trace = []
for mutation in mutations:
    target = doc.getObject(mutation["object"])
    setattr(target, mutation["property"], mutation["value"])
    doc.recompute()
    value = getattr(target, mutation["property"])
    if hasattr(value, "Value"):
        value = float(value.Value)
    else:
        value = float(value)
    trace.append({{
        "mutation": mutation,
        "stored_value": value,
        "formed": signature(formed),
        "flat": signature(flat),
    }})
_result_ = trace
''',
    )
    return result["result"]


async def _assert_tip_and_absence(
    tools: dict[str, Any], doc: str, expected_tip: str, absent: str
) -> None:
    """Assert the atomic-failure postcondition in the live document."""
    result = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
body = doc.getObject("Body")
_result_ = {{
    "tip": body.Tip.Name if body.Tip else None,
    "feature_exists": doc.getObject({absent!r}) is not None,
}}
''',
    )
    assert result["result"] == {"tip": expected_tip, "feature_exists": False}


async def _unfold_from_planar_candidates(
    tools: dict[str, Any],
    doc: str,
    formed: str,
    candidates: list[dict[str, Any]],
    name: str,
) -> dict[str, Any]:
    """Try inspected planar roots until the native workbench accepts one."""
    errors = []
    for candidate in candidates:
        try:
            return await _call(
                tools,
                "unfold_sheet_metal",
                feature_name=formed,
                stationary_face=candidate["face"],
                material={"k_factor": 0.38, "standard": "ansi"},
                name=name,
                doc_name=doc,
            )
        except ValueError as exc:
            errors.append(f"{candidate['face']}: {exc}")
            await _assert_tip_and_absence(tools, doc, formed, name)
    pytest.fail("No inspected planar stationary face unfolded:\n" + "\n".join(errors))


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
    assert base["view"]["visible"] is True
    assert base["view"]["display_mode"] != "None"
    assert base["view_provider"] == "SMBaseViewProvider"

    inspection = await _call(
        tools,
        "inspect_sheet_metal",
        object_name="ReferenceLProfile",
        doc_name=doc,
    )
    assert inspection["shape_valid"] is True
    assert inspection["solid_count"] == 1
    assert inspection["unfold_ready"] is True
    assert inspection["visible"] is True
    assert inspection["display_mode"] != "None"
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
    assert unfolded["view"]["visible"] is True
    assert unfolded["view"]["display_mode"] != "None"
    assert unfolded["view_provider"] == "SMUnfoldViewProvider"

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
    assert base["view"]["visible"] is True
    assert base["view"]["display_mode"] != "None"

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
    assert flange["view"]["visible"] is True
    assert flange["view"]["display_mode"] != "None"
    assert flange["view_provider"] == "SMViewProviderFlat"

    inspection = await _call(
        tools,
        "inspect_sheet_metal",
        object_name="EdgeFlange",
        doc_name=doc,
    )
    assert inspection["native_sheet_metal_history"] is True
    assert inspection["tip"] == "EdgeFlange"
    assert inspection["cylindrical_bend_face_count"] >= 1
    assert inspection["visible"] is True
    assert inspection["display_mode"] != "None"
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
    assert unfolded["view"]["visible"] is True
    assert unfolded["view"]["display_mode"] != "None"

    initial = await _sheet_state(tools, doc, "EdgeFlange", "FlangeFlatPattern")
    assert initial["formed"]["solids"] == 1
    assert initial["flat"]["solids"] == 1
    assert initial["unfold"]["bend_line_geometry"] >= 1
    trace = await _mutate_sheet_chain(
        tools,
        doc,
        "EdgeFlange",
        "FlangeFlatPattern",
        [
            {"object": "BaseBlank", "property": "Thickness", "value": 2.2},
            {"object": "EdgeFlange", "property": "radius", "value": 2.4},
            {"object": "EdgeFlange", "property": "angle", "value": 80.0},
            {"object": "FlangeFlatPattern", "property": "KFactor", "value": 0.42},
        ],
    )
    assert [item["stored_value"] for item in trace] == pytest.approx(
        [2.2, 2.4, 80.0, 0.42]
    )
    assert all(item["formed"]["valid"] for item in trace)
    assert all(item["formed"]["solids"] == 1 for item in trace)
    assert all(item["flat"]["valid"] for item in trace)
    assert all(item["flat"]["solids"] == 1 for item in trace)
    assert trace[-1]["formed"]["hash"] != initial["formed"]["hash"]
    assert trace[-1]["flat"]["hash"] != initial["flat"]["hash"]

    validation = await _assert_valid_model(tools, doc, ["BlankWidth", "BlankDepth"])
    usage = {
        item["name"]: item["status"]
        for item in validation["dimension_inventory"]["usage"]
    }
    assert usage == {"BlankWidth": "solid_driving", "BlankDepth": "solid_driving"}


@pytest.mark.asyncio
async def test_sketch_line_fold_preserves_tip_holes_and_recomputes(
    live_tools: dict[str, Any],
) -> None:
    """A helper bend sketch preserves Tip and flat-domain holes through Fold."""
    tools = live_tools
    doc = "McpAuditSheetMetalFold"
    await _require_sheetmetal(tools, "base", "fold", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "FoldBlank")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="FoldBlank",
        operations=[
            {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 80.0, "height": 40.0},
            {"op": "add_circle", "center_x": 15.0, "center_y": 20.0, "radius": 3.0},
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="FoldBlank",
        thickness=1.0,
        radius=2.0,
        name="FoldBase",
        doc_name=doc,
    )
    base_inspection = await _call(
        tools, "inspect_sheet_metal", object_name="FoldBase", doc_name=doc
    )
    assert base_inspection["cylindrical_face_count"] == 1
    assert base_inspection["classified_bend_face_count"] == 0
    assert base_inspection["cylindrical_bend_face_count"] == 0
    assert base_inspection["bend_zone_count"] == 0
    assert base_inspection["cylindrical_faces"][0]["classification"] == (
        "full_cylinder_non_bend"
    )
    bend_sketch = await _call(
        tools,
        "create_sketch",
        body_name="Body",
        support={"kind": "feature_face", "feature": "FoldBase", "face": "Face7"},
        name="BendLineSketch",
        doc_name=doc,
    )
    assert bend_sketch["body_tip"] == "FoldBase"
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BendLineSketch",
        operations=[{"op": "add_line", "x1": 40.0, "y1": 0.0, "x2": 40.0, "y2": 40.0}],
        doc_name=doc,
    )
    tip_state = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
body = doc.getObject("Body")
_result_ = {{"tip": body.Tip.Name, "is_base": body.Tip is doc.getObject("FoldBase")}}
''',
    )
    assert tip_state["result"] == {"tip": "FoldBase", "is_base": True}

    fold = await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "fold",
            "base_feature": "FoldBase",
            "face": "Face7",
            "bend_line_sketch": "BendLineSketch",
            "radius": 2.0,
            "angle": 90.0,
            "k_factor": 0.38,
        },
        name="SketchFold",
        doc_name=doc,
    )
    assert fold["proxy_type"] == "SMFoldWall"
    assert fold["solid_count"] == 1
    inspection = await _call(
        tools, "inspect_sheet_metal", object_name="SketchFold", doc_name=doc
    )
    assert inspection["tip"] == "SketchFold"
    assert inspection["classified_bend_face_count"] >= 2
    assert inspection["cylindrical_bend_face_count"] == inspection[
        "classified_bend_face_count"
    ]
    assert inspection["bend_zone_count"] >= 1
    assert inspection["cylindrical_face_count"] > inspection[
        "classified_bend_face_count"
    ]
    assert any(
        item["classification"] == "full_cylinder_non_bend"
        for item in inspection["cylindrical_faces"]
    )
    cylindrical = await _call(
        tools,
        "select_subshapes",
        object_name="SketchFold",
        criteria={"kind": "face", "surface_types": ["Cylinder"], "limit": 1},
        detail_level="summary",
        doc_name=doc,
    )
    with pytest.raises(ValueError, match="not planar"):
        await _call(
            tools,
            "unfold_sheet_metal",
            feature_name="SketchFold",
            stationary_face=cylindrical["references"][0],
            material={"k_factor": 0.38, "standard": "ansi"},
            name="RejectedNonPlanarUnfold",
            doc_name=doc,
        )
    await _assert_tip_and_absence(
        tools, doc, "SketchFold", "RejectedNonPlanarUnfold"
    )
    unfolded = await _call(
        tools,
        "unfold_sheet_metal",
        feature_name="SketchFold",
        stationary_face=inspection["stationary_face_candidates"][0]["face"],
        material={"k_factor": 0.38, "standard": "ansi"},
        name="FoldFlatPattern",
        doc_name=doc,
    )
    assert unfolded["solid_count"] == 1

    initial = await _sheet_state(tools, doc, "SketchFold", "FoldFlatPattern")
    assert initial["tip"] == "SketchFold"
    assert initial["flat"]["cylindrical_faces"] == 1
    assert initial["unfold"]["bend_line_geometry"] >= 1
    trace = await _mutate_sheet_chain(
        tools,
        doc,
        "SketchFold",
        "FoldFlatPattern",
        [
            {"object": "FoldBase", "property": "Thickness", "value": 1.2},
            {"object": "SketchFold", "property": "radius", "value": 2.5},
            {"object": "SketchFold", "property": "angle", "value": 75.0},
            {"object": "SketchFold", "property": "kfactor", "value": 0.42},
            {"object": "FoldFlatPattern", "property": "KFactor", "value": 0.42},
        ],
    )
    assert [item["stored_value"] for item in trace] == pytest.approx(
        [1.2, 2.5, 75.0, 0.42, 0.42]
    )
    assert all(item["formed"]["solids"] == 1 for item in trace)
    assert all(item["flat"]["solids"] == 1 for item in trace)
    assert trace[-1]["formed"]["hash"] != initial["formed"]["hash"]
    assert trace[-1]["flat"]["hash"] != initial["flat"]["hash"]

    with pytest.raises(ValueError, match="current Body Tip"):
        await _call(
            tools,
            "create_sheet_metal_feature",
            operation={
                "op": "flange",
                "base_feature": "FoldBase",
                "edges": ["Edge1"],
                "length": 10.0,
                "radius": 1.0,
            },
            name="RejectedStaleFoldBranch",
            doc_name=doc,
        )
    await _assert_tip_and_absence(tools, doc, "SketchFold", "RejectedStaleFoldBranch")

    with pytest.raises(ValueError, match=r"Cannot resolve SketchFold\.Face999"):
        await _call(
            tools,
            "create_sheet_metal_feature",
            operation={
                "op": "fold",
                "base_feature": "SketchFold",
                "face": "Face999",
                "bend_line_sketch": "BendLineSketch",
                "radius": 2.0,
                "k_factor": 0.38,
            },
            name="RejectedFoldReference",
            doc_name=doc,
        )
    await _assert_tip_and_absence(tools, doc, "SketchFold", "RejectedFoldReference")


@pytest.mark.asyncio
async def test_relief_configured_hemmed_enclosure_corner_recomputes(
    live_tools: dict[str, Any],
) -> None:
    """Two adjacent flanges and a relief-configured hem remain unfoldable."""
    tools = live_tools
    doc = "McpAuditHemmedCorner"
    await _require_sheetmetal(tools, "base", "flange", "hem", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "CornerBlank")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="CornerBlank",
        operations=[
            {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 60.0, "height": 40.0}
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="CornerBlank",
        thickness=1.0,
        radius=1.0,
        name="CornerBase",
        doc_name=doc,
    )
    first_edge = await _call(
        tools,
        "select_subshapes",
        object_name="CornerBase",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [1.0, 0.0, 0.0],
            "length_min": 59.99,
            "length_max": 60.01,
            "centroid_bounds": {
                "y_min": 39.99,
                "y_max": 40.01,
                "z_min": 0.99,
                "z_max": 1.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "flange",
            "base_feature": "CornerBase",
            "edges": first_edge["references"],
            "length": 15.0,
            "radius": 1.0,
            "angle": 90.0,
        },
        name="CornerFlangeY",
        doc_name=doc,
    )
    second_edge = await _call(
        tools,
        "select_subshapes",
        object_name="CornerFlangeY",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [0.0, 1.0, 0.0],
            "length_min": 39.99,
            "length_max": 40.01,
            "centroid_bounds": {
                "x_min": 59.99,
                "x_max": 60.01,
                "z_min": 0.99,
                "z_max": 1.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "flange",
            "base_feature": "CornerFlangeY",
            "edges": second_edge["references"],
            "length": 15.0,
            "radius": 1.0,
            "angle": 90.0,
            "auto_miter": True,
        },
        name="CornerFlangeX",
        doc_name=doc,
    )
    hem_edge = await _call(
        tools,
        "select_subshapes",
        object_name="CornerFlangeX",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [1.0, 0.0, 0.0],
            "length_min": 59.99,
            "length_max": 60.01,
            "centroid_bounds": {
                "y_min": 41.99,
                "y_max": 42.01,
                "z_min": 16.99,
                "z_max": 17.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    hem = await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "hem",
            "base_feature": "CornerFlangeX",
            "edges": hem_edge["references"],
            "hem_type": "open",
            "width": 8.0,
            "radius": 1.0,
            "opening": 1.0,
            "relief_type": "round",
            "relief_width": 1.2,
            "relief_depth": 1.5,
        },
        name="RelievedHem",
        doc_name=doc,
    )
    assert hem["proxy_type"] == "SMHem"
    assert hem["solid_count"] == 1
    inspection = await _call(
        tools, "inspect_sheet_metal", object_name="RelievedHem", doc_name=doc
    )
    unfolded = await _unfold_from_planar_candidates(
        tools,
        doc,
        "RelievedHem",
        inspection["stationary_face_candidates"],
        "HemFlatPattern",
    )
    assert unfolded["solid_count"] == 1
    initial = await _sheet_state(tools, doc, "RelievedHem", "HemFlatPattern")
    assert initial["unfold"]["bend_line_geometry"] >= 3
    relief_state = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
hem = doc.getObject("RelievedHem")
_result_ = {{
    "type": str(hem.reliefType),
    "width": float(hem.reliefw.Value),
    "depth": float(hem.reliefd.Value),
}}
''',
    )
    assert relief_state["result"] == {"type": "Round", "width": 1.2, "depth": 1.5}
    trace = await _mutate_sheet_chain(
        tools,
        doc,
        "RelievedHem",
        "HemFlatPattern",
        [
            {"object": "CornerBase", "property": "Thickness", "value": 1.1},
            {"object": "CornerFlangeY", "property": "radius", "value": 1.2},
            {"object": "CornerFlangeX", "property": "angle", "value": 80.0},
            {"object": "RelievedHem", "property": "kfactor", "value": 0.42},
            {"object": "HemFlatPattern", "property": "KFactor", "value": 0.42},
        ],
    )
    assert [item["stored_value"] for item in trace] == pytest.approx(
        [1.1, 1.2, 80.0, 0.42, 0.42]
    )
    assert all(item["formed"]["valid"] for item in trace)
    assert all(item["formed"]["solids"] == 1 for item in trace)
    assert all(item["flat"]["valid"] for item in trace)
    assert all(item["flat"]["solids"] == 1 for item in trace)
    assert trace[-1]["formed"]["hash"] != initial["formed"]["hash"]
    assert trace[-1]["flat"]["hash"] != initial["flat"]["hash"]


@pytest.mark.asyncio
async def test_solid_to_sheet_conversion_recomputes_and_audits_unfold(
    live_tools: dict[str, Any],
) -> None:
    """A padded solid converts natively and retains explicit unfold material data."""
    tools = live_tools
    doc = "McpAuditSolidToSheet"
    await _require_sheetmetal(tools, "from_solid", "junction", "relief", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "SolidSketch")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="SolidSketch",
        operations=[
            {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 60.0, "height": 40.0}
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "pad_sketch",
        sketch_name="SolidSketch",
        length=20.0,
        name="SourceSolid",
        doc_name=doc,
    )
    remove_face = await _call(
        tools,
        "select_subshapes",
        object_name="SourceSolid",
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0.0, 0.0, 1.0],
            "area_min": 2399.9,
            "area_max": 2400.1,
            "centroid_bounds": {"z_min": 19.99, "z_max": 20.01},
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    rip_edge = await _call(
        tools,
        "select_subshapes",
        object_name="SourceSolid",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [0.0, 0.0, 1.0],
            "length_min": 19.99,
            "length_max": 20.01,
            "centroid_bounds": {
                "x_min": -0.01,
                "x_max": 0.01,
                "y_min": -0.01,
                "y_max": 0.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=doc,
    )
    converted = await _call(
        tools,
        "create_sheet_metal_feature",
        operation={
            "op": "from_solid",
            "base_feature": "SourceSolid",
            "remove_faces_and_rip_edges": remove_face["references"]
            + rip_edge["references"],
            "thickness": 1.0,
            "radius": 1.0,
        },
        name="SolidToSheet",
        doc_name=doc,
    )
    assert converted["proxy_type"] == "SMFromSolid"
    assert converted["solid_count"] == 1
    inspection = await _call(
        tools, "inspect_sheet_metal", object_name="SolidToSheet", doc_name=doc
    )
    assert inspection["tip"] == "SolidToSheet"
    assert inspection["cylindrical_bend_face_count"] >= 1
    initial = await _sheet_state(tools, doc, "SolidToSheet")
    mutation_result = await _call(
        tools,
        "execute_python",
        code=f'''
doc = FreeCAD.getDocument({doc!r})
formed = doc.getObject("SolidToSheet")
steps = [
    ("SolidToSheet", "Thickness", 1.2),
    ("SolidToSheet", "Radius", 1.5),
]
trace = []
for object_name, property_name, value in steps:
    setattr(doc.getObject(object_name), property_name, value)
    doc.recompute()
    trace.append({{
        "valid": bool(formed.Shape.isValid()),
        "solids": len(formed.Shape.Solids),
        "volume": float(formed.Shape.Volume),
        "hash": int(formed.Shape.hashCode()),
    }})
_result_ = trace
''',
    )
    trace = mutation_result["result"]
    assert all(item["valid"] and item["solids"] == 1 for item in trace)
    assert trace[-1]["hash"] != initial["formed"]["hash"]

    # SheetMetal 0.8.21 can form this canonical open box but currently returns
    # a null shape for every planar unfold root (often "Wire is not closed").
    # Keep this as a compatibility audit: future versions may start succeeding,
    # while current versions must roll back every failed candidate atomically.
    inspection = await _call(
        tools, "inspect_sheet_metal", object_name="SolidToSheet", doc_name=doc
    )
    unfolded = None
    unfold_errors = []
    for candidate in inspection["stationary_face_candidates"]:
        try:
            unfolded = await _call(
                tools,
                "unfold_sheet_metal",
                feature_name="SolidToSheet",
                stationary_face=candidate["face"],
                material={"k_factor": 0.42, "standard": "ansi"},
                name="ConvertedFlatPattern",
                doc_name=doc,
            )
            break
        except ValueError as exc:
            unfold_errors.append(str(exc))
            await _assert_tip_and_absence(
                tools, doc, "SolidToSheet", "ConvertedFlatPattern"
            )
    if unfolded is not None:
        state = await _sheet_state(
            tools, doc, "SolidToSheet", "ConvertedFlatPattern"
        )
        assert state["flat"]["solids"] == 1
        assert state["unfold"]["bend_line_geometry"] >= 3
    else:
        assert unfold_errors
        assert any(
            "null shape" in error or "Wire is not closed" in error
            for error in unfold_errors
        )

    seam_edges = await _call(
        tools,
        "select_subshapes",
        object_name="SolidToSheet",
        criteria={
            "kind": "edge",
            "curve_types": ["Line"],
            "direction": [0.0, 0.0, 1.0],
            "length_min": 15.0,
            "length_max": 22.0,
            "centroid_bounds": {
                "x_min": -2.0,
                "x_max": 2.0,
                "y_min": -2.0,
                "y_max": 2.0,
            },
            "limit": 10,
        },
        detail_level="summary",
        doc_name=doc,
    )
    junction = None
    for edge in seam_edges["references"]:
        try:
            junction = await _call(
                tools,
                "create_sheet_metal_feature",
                operation={
                    "op": "junction",
                    "base_feature": "SolidToSheet",
                    "edges": [edge],
                    "gap": 0.5,
                },
                name="ConvertedJunction",
                doc_name=doc,
            )
            break
        except ValueError:
            await _assert_tip_and_absence(
                tools, doc, "SolidToSheet", "ConvertedJunction"
            )
    assert junction is not None
    assert junction["proxy_type"] == "SMJunction"
    seam_vertices = await _call(
        tools,
        "select_subshapes",
        object_name="ConvertedJunction",
        criteria={
            "kind": "vertex",
            "point_bounds": {
                "x_min": -2.0,
                "x_max": 2.0,
                "y_min": -2.0,
                "y_max": 2.0,
                "z_min": 0.0,
                "z_max": 4.0,
            },
            "limit": 30,
        },
        detail_level="summary",
        doc_name=doc,
    )
    relief = None
    for vertex in seam_vertices["references"]:
        try:
            relief = await _call(
                tools,
                "create_sheet_metal_feature",
                operation={
                    "op": "relief",
                    "base_feature": "ConvertedJunction",
                    "vertices": [vertex],
                    "size": 1.5,
                },
                name="ConvertedRelief",
                doc_name=doc,
            )
            break
        except ValueError:
            await _assert_tip_and_absence(
                tools, doc, "ConvertedJunction", "ConvertedRelief"
            )
    assert relief is not None
    assert relief["proxy_type"] == "SMRelief"
    assert relief["solid_count"] == 1


@pytest.mark.asyncio
async def test_sheet_metal_negative_failures_are_atomic(
    live_tools: dict[str, Any],
) -> None:
    """Topology, multi-solid, and self-crossing failures roll back."""
    tools = live_tools
    await _require_sheetmetal(tools, "base", "flange", "relief")

    doc = "McpAuditSheetMetalNegativeRefs"
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "NegativeBlank")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="NegativeBlank",
        operations=[
            {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 40.0, "height": 30.0}
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="NegativeBlank",
        thickness=1.0,
        radius=1.0,
        name="NegativeBase",
        doc_name=doc,
    )
    for operation, feature_name, expected in (
        (
            {
                "op": "flange",
                "base_feature": "NegativeBase",
                "edges": ["Edge999"],
                "length": 10.0,
                "radius": 1.0,
            },
            "RejectedWrongEdge",
            r"Cannot resolve NegativeBase\.Edge999",
        ),
        (
            {
                "op": "relief",
                "base_feature": "NegativeBase",
                "vertices": ["Vertex999"],
                "size": 2.0,
            },
            "RejectedWrongVertex",
            r"Cannot resolve NegativeBase\.Vertex999",
        ),
    ):
        with pytest.raises(ValueError, match=expected):
            await _call(
                tools,
                "create_sheet_metal_feature",
                operation=operation,
                name=feature_name,
                doc_name=doc,
            )
        await _assert_tip_and_absence(tools, doc, "NegativeBase", feature_name)

    for suffix, operations, error_pattern in (
        (
            "MultiSolid",
            [
                {"op": "add_rectangle", "x": 0.0, "y": 0.0, "width": 20.0, "height": 15.0},
                {"op": "add_rectangle", "x": 30.0, "y": 0.0, "width": 20.0, "height": 15.0},
            ],
            "null shape|one non-empty solid",
        ),
        (
            "SelfIntersection",
            [
                {
                    "op": "add_polyline",
                    "points": [[0.0, 0.0], [40.0, 30.0], [0.0, 30.0], [40.0, 0.0]],
                    "closed": True,
                }
            ],
            "null shape|invalid shape|one non-empty solid",
        ),
    ):
        failure_doc = f"McpAuditSheetMetal{suffix}"
        await _fresh(tools, failure_doc)
        await _create_body_sketch(tools, failure_doc, "FailureSketch")
        await _call(
            tools,
            "edit_sketch_geometry",
            sketch_name="FailureSketch",
            operations=operations,
            doc_name=failure_doc,
        )
        with pytest.raises(ValueError, match=error_pattern):
            await _call(
                tools,
                "create_sheet_metal_base",
                sketch_name="FailureSketch",
                thickness=1.0,
                radius=1.0,
                name="RejectedBase",
                doc_name=failure_doc,
            )
        state = await _call(
            tools,
            "execute_python",
            code=f'''
doc = FreeCAD.getDocument({failure_doc!r})
body = doc.getObject("Body")
_result_ = {{
    "tip": body.Tip.Name if body.Tip else None,
    "feature_exists": doc.getObject("RejectedBase") is not None,
}}
''',
        )
        assert state["result"] == {"tip": None, "feature_exists": False}


@pytest.mark.asyncio
async def test_inspection_and_unfold_reject_ad_hoc_post_sheet_reconstruction(
    live_tools: dict[str, Any],
) -> None:
    """A copied/additive PartDesign tail must not masquerade as unfold-ready."""
    tools = live_tools
    doc = "McpAuditSheetMetalBypass"
    await _require_sheetmetal(tools, "base", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "BlankSketch")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BlankSketch",
        operations=[
            {
                "op": "add_rectangle",
                "x": 0.0,
                "y": 0.0,
                "width": 40.0,
                "height": 25.0,
            }
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="BlankSketch",
        thickness=2.0,
        radius=2.0,
        name="NativeBase",
        doc_name=doc,
    )
    await _call(
        tools,
        "execute_python",
        code=f"""
doc = FreeCAD.getDocument({doc!r})
body = doc.getObject("Body")
base = doc.getObject("NativeBase")
bypass = body.newObject("PartDesign::Feature", "AdHocPadReconstruction")
bypass.Shape = base.Shape.copy()
body.Tip = bypass
base.ViewObject.Visibility = False
bypass.ViewObject.Visibility = True
doc.recompute()
_result_ = {{"tip": body.Tip.Name, "valid": bool(bypass.Shape.isValid())}}
""",
    )

    inspection = await _call(
        tools,
        "inspect_sheet_metal",
        object_name="AdHocPadReconstruction",
        doc_name=doc,
    )
    assert inspection["shape_valid"] is True
    assert inspection["has_native_sheet_metal_features"] is True
    assert inspection["native_sheet_metal_history"] is False
    assert inspection["sheet_metal_history_classification"] == (
        "unsupported_post_native_history"
    )
    assert inspection["unfold_ready"] is False
    unsupported = inspection["history_evidence"]["unsupported_shape_features"]
    assert [item["name"] for item in unsupported] == ["AdHocPadReconstruction"]
    assert unsupported[0]["type_id"] == "PartDesign::Feature"
    assert unsupported[0]["position"] == "after_last_native"
    assert any(
        "Unsupported shape-producing features" in item
        for item in inspection["warnings"]
    )

    with pytest.raises(ValueError, match="unsupported shape-producing features"):
        await _call(
            tools,
            "unfold_sheet_metal",
            feature_name="AdHocPadReconstruction",
            stationary_face=inspection["stationary_face_candidates"][0]["face"],
            material={"k_factor": 0.38, "standard": "ansi"},
            doc_name=doc,
        )
    await _assert_tip_and_absence(tools, doc, "AdHocPadReconstruction", "Unfold")


@pytest.mark.asyncio
async def test_interleaved_partdesign_history_cannot_be_hidden_by_later_sm_proxy(
    live_tools: dict[str, Any],
) -> None:
    """SMBase -> PartDesign shape -> SM proxy remains mixed and non-unfoldable."""
    tools = live_tools
    doc = "McpAuditSheetMetalInterleavedBypass"
    await _require_sheetmetal(tools, "base", "unfold")
    await _fresh(tools, doc)
    await _create_body_sketch(tools, doc, "BlankSketch")
    await _call(
        tools,
        "edit_sketch_geometry",
        sketch_name="BlankSketch",
        operations=[
            {
                "op": "add_rectangle",
                "x": 0.0,
                "y": 0.0,
                "width": 40.0,
                "height": 25.0,
            }
        ],
        doc_name=doc,
    )
    await _call(
        tools,
        "create_sheet_metal_base",
        sketch_name="BlankSketch",
        thickness=2.0,
        radius=2.0,
        name="NativeBase",
        doc_name=doc,
    )
    await _call(
        tools,
        "execute_python",
        code=f"""
doc = FreeCAD.getDocument({doc!r})
body = doc.getObject("Body")
base = doc.getObject("NativeBase")
interleaved = body.newObject("PartDesign::Feature", "InterleavedPad")
interleaved.Shape = base.Shape.copy()

class SMRecoveredProxy:
    pass

recovered = body.newObject("PartDesign::FeaturePython", "RecoveredSM")
recovered.Proxy = SMRecoveredProxy()
recovered.Shape = interleaved.Shape.copy()
body.Tip = recovered
base.ViewObject.Visibility = False
interleaved.ViewObject.Visibility = False
recovered.ViewObject.Visibility = True
doc.recompute()
_result_ = {{"tip": body.Tip.Name, "valid": bool(recovered.Shape.isValid())}}
""",
    )

    inspection = await _call(
        tools, "inspect_sheet_metal", object_name="RecoveredSM", doc_name=doc
    )
    assert inspection["has_native_sheet_metal_features"] is True
    assert inspection["native_sheet_metal_history"] is False
    assert inspection["sheet_metal_history_classification"] == (
        "mixed_interleaved_history"
    )
    assert inspection["history_evidence"]["reentered_after_unsupported"] is True
    unsupported = inspection["history_evidence"]["unsupported_shape_features"]
    assert [item["name"] for item in unsupported] == ["InterleavedPad"]
    assert unsupported[0]["position"] == "interleaved_before_later_native"
    assert inspection["unfold_ready"] is False

    with pytest.raises(ValueError, match="unsupported shape-producing features"):
        await _call(
            tools,
            "unfold_sheet_metal",
            feature_name="RecoveredSM",
            stationary_face=inspection["stationary_face_candidates"][0]["face"],
            material={"k_factor": 0.38, "standard": "ansi"},
            name="RejectedRecoveredUnfold",
            doc_name=doc,
        )
    await _assert_tip_and_absence(
        tools, doc, "RecoveredSM", "RejectedRecoveredUnfold"
    )
