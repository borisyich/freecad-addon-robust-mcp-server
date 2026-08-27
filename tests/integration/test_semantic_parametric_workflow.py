"""Complex live workflow for semantic inspection and Spreadsheet-driven sketches.

Run with a FreeCAD instance whose Robust MCP XML-RPC bridge is listening on
localhost:9875.  The scenario deliberately changes the parameter table after
Fillet and Chamfer have been created, so it exercises the complete editable
PartDesign history rather than only checking one-shot tool responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from .test_all_tools_refactor_audit import _call, _fresh, live_tools  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.slow]


_PARAMETERS: tuple[tuple[str, str, float], ...] = (
    ("A1", "BaseCenterX", 2.0),
    ("A2", "BaseCenterY", 3.0),
    ("A3", "BaseRadius", 20.0),
    ("A4", "Height", 30.0),
    ("A5", "HoleOffsetX", 8.0),
    ("A6", "HoleOffsetY", 4.0),
    ("A7", "HoleRadius", 5.0),
    ("A8", "FilletRadius", 2.0),
    ("A9", "ChamferSize", 1.0),
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
        require_visual_comparison=False,
        detail_level="full",
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
        item["name"]: item["status"] for item in report["dimension_inventory"]["usage"]
    }
    assert usage == dict.fromkeys(required_names, "connected_to_final_solid"), usage

    dimensions_sheet = next(
        item for item in report["spreadsheets"] if item["name"] == "Dimensions"
    )
    assert dimensions_sheet["unused_parameters"] == []
    return report


@pytest.mark.asyncio
async def test_native_part_boolean_chain_does_not_require_partdesign_review(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """A healthy Part primitive/boolean history is valid outside a Body."""
    tools = live_tools
    doc_name = "McpAuditNativePartValidation"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument
base = doc.addObject("Part::Cylinder", "BaseCylinder")
base.Radius = 10.0
base.Height = 20.0
tool = doc.addObject("Part::Cylinder", "ToolCylinder")
tool.Radius = 3.0
tool.Height = 20.0
cut = doc.addObject("Part::Cut", "Cut")
cut.Base = base
cut.Tool = tool
doc.recompute()
_result_ = {"cut_valid": cut.Shape.isValid(), "volume": cut.Shape.Volume}
""",
    )

    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        recompute=True,
        detail_level="full",
    )

    assert report["assessment"] == "healthy", report
    assert report["findings"] == []
    assert report["counts"]["parametric_part_features"] == 3
    assert {item["classification"] for item in report["uncontained_shape_objects"]} == {
        "parametric_part_feature"
    }


@pytest.mark.asyncio
async def test_imported_brep_workflow_recognizes_move_faces_provenance(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """Expected import/direct-edit snapshots should be info, not review noise."""
    tools = live_tools
    doc_name = "McpAuditImportedBrepValidation"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument
source = doc.addObject("Part::Feature", "ImportedSource")
source.Shape = Part.makeBox(20, 10, 5)
source.addProperty("App::PropertyString", "ImportSourcePath", "MCP Import")
source.ImportSourcePath = "fixture.step"
source.addProperty("App::PropertyString", "ImportSourceFormat", "MCP Import")
source.ImportSourceFormat = "step"
doc.recompute()
_result_ = source.Shape.isValid()
""",
    )
    top = await _call(
        tools,
        "select_subshapes",
        object_name="ImportedSource",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "sort_by": "area",
            "sort_order": "desc",
            "limit": 1,
        },
    )
    edited = await _call(
        tools,
        "move_faces",
        object_name="ImportedSource",
        face_names=top["references"],
        distance=2.0,
        operation="add",
        result_name="MovedFaces",
        doc_name=doc_name,
    )
    assert edited["direct_edit"] is True

    native_report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        detail_level="full",
    )
    assert native_report["assessment"] == "review_recommended"

    imported_report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        workflow="imported_brep_edit",
        detail_level="full",
    )
    assert imported_report["assessment"] == "healthy", imported_report
    assert {
        (item["severity"], item["category"]) for item in imported_report["findings"]
    } == {
        ("info", "imported_brep_source"),
        ("info", "intentional_direct_edit"),
    }


@pytest.mark.asyncio
async def test_imported_brep_move_faces_rebuilds_boss_with_fillet_chain(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """Strict feature rebuild should move a boss cap without losing its blend."""
    tools = live_tools
    doc_name = "McpImportedBrepMoveFaceFillet"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import Part
doc = FreeCAD.ActiveDocument
base = Part.makeBox(40, 40, 10)
boss = Part.makeCylinder(7, 10, FreeCAD.Vector(20, 20, 10))
sharp = base.fuse(boss)
shape = sharp.makeFillet(2, [sharp.Edges[9]]).Solids[0]
source = doc.addObject("Part::Feature", "ImportedBoss")
source.Shape = shape
source.addProperty("App::PropertyString", "ImportSourcePath", "MCP Import")
source.ImportSourcePath = "boss-with-fillet.step"
source.addProperty("App::PropertyString", "ImportSourceFormat", "MCP Import")
source.ImportSourceFormat = "step"
doc.recompute()
_result_ = {
    "valid": shape.isValid(),
    "solid_count": len(shape.Solids),
    "max_z": shape.BoundBox.ZMax,
}
""",
    )
    cap = await _call(
        tools,
        "select_subshapes",
        object_name="ImportedBoss",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "sort_by": "area",
            "sort_order": "asc",
            "limit": 1,
        },
    )

    edited = await _call(
        tools,
        "move_faces",
        object_name="ImportedBoss",
        face_names=cap["references"],
        distance=3.0,
        method="feature_rebuild",
        result_name="MovedBoss",
        doc_name=doc_name,
    )

    assert edited["performed_method"] == "feature_rebuild", edited
    assert edited["rebuild_variant"] == "sharp_boundary_sweep"
    assert edited["fallback_reason"] is None
    assert edited["feature_kind"] == "additive_material"
    assert edited["shape_valid"] is True
    assert edited["shape_type"] == "Solid"
    assert edited["solid_count"] == 1
    assert edited["volume_delta"] > 0.0
    assert edited["tangent_chain_face_names"] == []
    assert len(edited["feature_face_names"]) == 3

    evidence = await _call(
        tools,
        "execute_python",
        code="""
obj = FreeCAD.ActiveDocument.getObject("MovedBoss")
shape = obj.Shape
surface_types = [type(face.Surface).__name__ for face in shape.Faces]
_result_ = {
    "valid": shape.isValid(),
    "solid_count": len(shape.Solids),
    "min_z": shape.BoundBox.ZMin,
    "max_z": shape.BoundBox.ZMax,
    "toroid_count": surface_types.count("Toroid"),
    "cylinder_count": surface_types.count("Cylinder"),
}
""",
    )
    evidence = evidence["result"]
    assert evidence == {
        "valid": True,
        "solid_count": 1,
        "min_z": pytest.approx(0.0, abs=1e-7),
        "max_z": pytest.approx(23.0, abs=1e-7),
        "toroid_count": 1,
        "cylinder_count": 1,
    }


@pytest.mark.asyncio
async def test_imported_brep_move_faces_moves_pocket_tangent_chain(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """A pocket floor move should carry its bottom fillet and extend the wall."""
    tools = live_tools
    doc_name = "McpImportedBrepMovePocketFillet"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import Part
doc = FreeCAD.ActiveDocument
base = Part.makeBox(40, 40, 10)
tool = Part.makeCylinder(7, 7, FreeCAD.Vector(20, 20, 4))
sharp = base.cut(tool)
shape = sharp.makeFillet(2, [sharp.Edges[14]]).Solids[0]
source = doc.addObject("Part::Feature", "ImportedPocket")
source.Shape = shape
doc.recompute()
_result_ = {"valid": shape.isValid(), "solid_count": len(shape.Solids)}
""",
    )
    floor = await _call(
        tools,
        "select_subshapes",
        object_name="ImportedPocket",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "sort_by": "area",
            "sort_order": "asc",
            "limit": 1,
        },
    )

    edited = await _call(
        tools,
        "move_faces",
        object_name="ImportedPocket",
        face_names=floor["references"],
        distance=-2.0,
        method="feature_rebuild",
        result_name="DeepPocket",
        doc_name=doc_name,
    )

    assert edited["performed_method"] == "feature_rebuild", edited
    assert edited["rebuild_variant"] == "translated_tangent_feature"
    assert edited["feature_kind"] == "subtractive_void"
    assert edited["shape_valid"] is True
    assert edited["shape_type"] == "Solid"
    assert edited["solid_count"] == 1
    assert edited["volume_delta"] < 0.0
    assert len(edited["tangent_chain_face_names"]) == 2

    evidence = await _call(
        tools,
        "execute_python",
        code="""
shape = FreeCAD.ActiveDocument.getObject("DeepPocket").Shape
surface_types = [type(face.Surface).__name__ for face in shape.Faces]
small_planes = [
    face for face in shape.Faces
    if type(face.Surface).__name__ == "Plane" and face.Area < 100.0
]
_result_ = {
    "valid": shape.isValid(),
    "solid_count": len(shape.Solids),
    "floor_z": small_planes[0].CenterOfMass.z,
    "toroid_count": surface_types.count("Toroid"),
    "cylinder_count": surface_types.count("Cylinder"),
}
""",
    )
    evidence = evidence["result"]
    assert evidence == {
        "valid": True,
        "solid_count": 1,
        "floor_z": pytest.approx(2.0, abs=1e-7),
        "toroid_count": 1,
        "cylinder_count": 1,
    }


@pytest.mark.asyncio
async def test_fillet_failure_returns_structured_edge_diagnostics_after_rollback(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """An impossible radius should identify the edge and leave no failed feature."""
    tools = live_tools
    doc_name = "McpFilletFailureDiagnostics"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import Part
doc = FreeCAD.ActiveDocument
source = doc.addObject("Part::Feature", "FilletSource")
source.Shape = Part.makeBox(10, 10, 10)
doc.recompute()
_result_ = source.Shape.isValid()
""",
    )

    failed = await tools["fillet_edges"](
        object_name="FilletSource",
        radius=100.0,
        edges=["Edge1"],
        name="ImpossibleFillet",
        doc_name=doc_name,
    )

    assert failed["success"] is False
    assert failed["rolled_back"] is True
    assert failed["source_shape_type"] == "Solid"
    assert failed["source_solid_count"] == 1
    assert failed["selected_edges"] == ["Edge1"]
    assert failed["adjacent_face_types"] == {"Edge1": ["Plane", "Plane"]}
    assert failed["requested_radius"] == 100.0
    assert failed["result_state"]["shape_valid"] is False
    assert failed["failing_edges"] == ["Edge1"]
    assert failed["edge_trials"][0]["ok"] is False

    state = await _call(
        tools,
        "execute_python",
        code="""
doc = FreeCAD.ActiveDocument
source = doc.getObject("FilletSource")
_result_ = {
    "failed_feature_present": doc.getObject("ImpossibleFillet") is not None,
    "source_valid": source is not None and source.Shape.isValid(),
}
""",
    )
    assert state["result"] == {
        "failed_feature_present": False,
        "source_valid": True,
    }


@pytest.mark.asyncio
async def test_imported_brep_direct_edit_inside_body_is_informational(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """A provenance-marked static result has the same meaning inside a Body."""
    tools = live_tools
    doc_name = "McpImportedBodyDirectEdit"
    await _fresh(tools, doc_name)
    await _call(
        tools,
        "execute_python",
        code="""
import Part
doc = FreeCAD.ActiveDocument
body = doc.addObject("PartDesign::Body", "Body")
source = body.newObject("PartDesign::Feature", "ImportedBodySource")
source.Shape = Part.makeBox(20, 10, 5)
source.addProperty("App::PropertyString", "ImportSourcePath", "MCP Import")
source.ImportSourcePath = "fixture.step"
source.addProperty("App::PropertyString", "ImportSourceFormat", "MCP Import")
source.ImportSourceFormat = "step"
body.Tip = source
doc.recompute()
_result_ = source.Shape.isValid()
""",
    )
    top = await _call(
        tools,
        "select_subshapes",
        object_name="ImportedBodySource",
        doc_name=doc_name,
        criteria={
            "kind": "face",
            "surface_types": ["Plane"],
            "normal": [0, 0, 1],
            "sort_by": "area",
            "sort_order": "desc",
            "limit": 1,
        },
    )
    edited = await _call(
        tools,
        "move_faces",
        object_name="ImportedBodySource",
        face_names=top["references"],
        distance=2.0,
        operation="add",
        result_name="MovedBodyFaces",
        doc_name=doc_name,
    )
    assert edited["type_id"] == "PartDesign::Feature"

    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=doc_name,
        workflow="imported_brep_edit",
        detail_level="full",
    )
    moved_findings = [
        item for item in report["findings"] if item.get("object") == "MovedBodyFaces"
    ]
    assert {(item["severity"], item["category"]) for item in moved_findings} == {
        ("info", "intentional_direct_edit")
    }
    assert moved_findings[0]["message"].endswith("of source 'ImportedBodySource'.")


@pytest.mark.asyncio
async def test_import_creates_missing_named_document(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
    tmp_path: Path,
) -> None:
    """An explicit import target name should not require create_document first."""
    tools = live_tools
    source_doc = "McpAuditImportSource"
    target_doc = "McpAuditImportTarget"
    step_path = tmp_path / "import_contract.step"
    await _fresh(tools, source_doc)
    await _call(
        tools,
        "execute_python",
        code="""
import FreeCAD
doc = FreeCAD.ActiveDocument
box = doc.addObject("Part::Box", "SourceBox")
box.Length = 12
box.Width = 8
box.Height = 4
doc.recompute()
_result_ = box.Shape.isValid()
""",
    )
    await _call(
        tools,
        "export",
        file_format="step",
        file_path=str(step_path),
        object_names=["SourceBox"],
        doc_name=source_doc,
    )
    await _call(tools, "close_document", doc_name=source_doc)
    await _call(
        tools,
        "execute_python",
        code=f"""
import FreeCAD
if {target_doc!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({target_doc!r})
_result_ = True
""",
    )

    imported = await _call(
        tools,
        "import",
        file_format="step",
        file_path=str(step_path),
        doc_name=target_doc,
    )

    assert imported["document"] == target_doc
    assert imported["document_created"] is True
    assert imported["objects"]
    report = await _call(
        tools,
        "validate_parametric_model",
        doc_name=target_doc,
        workflow="imported_brep_edit",
        detail_level="full",
    )
    assert report["assessment"] == "healthy", report
    assert any(
        item["category"] == "imported_brep_source" and item["severity"] == "info"
        for item in report["findings"]
    )


@pytest.mark.asyncio
async def test_non_import_creation_tools_reject_missing_document_names(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
) -> None:
    """A misspelled ordinary target must not create a side-effect document."""
    tools = live_tools
    cases = (
        (
            "create_primitive",
            {
                "primitive": {"kind": "box", "length": 1, "width": 1, "height": 1},
                "doc_name": "TypoObjectDocument",
            },
        ),
        (
            "spreadsheet_create",
            {"name": "Params", "doc_name": "TypoSpreadsheetDocument"},
        ),
        (
            "create_partdesign_body",
            {"name": "Body", "doc_name": "TypoPartDesignDocument"},
        ),
    )
    for tool_name, arguments in cases:
        with pytest.raises(ValueError, match="Document not found"):
            await tools[tool_name](**arguments)

    documents = await _call(tools, "list_documents")
    names = {
        item["name"] if isinstance(item, dict) else item.name for item in documents
    }
    assert not names.intersection(
        {
            "TypoObjectDocument",
            "TypoSpreadsheetDocument",
            "TypoPartDesignDocument",
        }
    )


@pytest.mark.asyncio
async def test_semantic_selector_and_sketch_expressions_survive_parameter_update(
    live_tools: dict[str, Any],  # noqa: F811 - imported pytest fixture
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
        cells=[
            {"cell": cell, "value": {"value": value, "unit": "mm"}}
            for cell, _alias, value in _PARAMETERS
        ],
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
        detail_level="full",
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
        detail_level="summary",
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
        detail_level="full",
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
        detail_level="full",
    )
    assert detailed_hole_sketch["geometry"][0]["geometry_type"] == "Circle"
    assert detailed_hole_sketch["geometry"][0]["geometry"]["center"] == {
        "x": pytest.approx(8.0),
        "y": pytest.approx(4.0),
        "z": pytest.approx(0.0),
    }
    assert {item["path"] for item in detailed_hole_sketch["expressions"]} == {
        "Constraints[0]",
        "Constraints[1]",
        "Constraints[2]",
    }

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
        detail_level="summary",
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
        detail_level="summary",
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
        "start_point" in edge and "end_point" in edge for edge in initial_shape["edges"]
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
        detail_level="summary",
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
            {"cell": "A3", "value": {"value": 24, "unit": "mm"}},
            {"cell": "A4", "value": {"value": 36, "unit": "mm"}},
            {"cell": "A5", "value": {"value": 10, "unit": "mm"}},
            {"cell": "A7", "value": {"value": 6, "unit": "mm"}},
            {"cell": "A8", "value": {"value": 3, "unit": "mm"}},
            {"cell": "A9", "value": {"value": 1.5, "unit": "mm"}},
        ],
        doc_name=doc_name,
    )
    assert resized["cells_applied"] == 6

    resized_base = await _call(
        tools,
        "get_sketch_info",
        sketch_name="BaseSketch",
        doc_name=doc_name,
        detail_level="full",
    )
    resized_hole = await _call(
        tools,
        "get_sketch_info",
        sketch_name="HoleSketch",
        doc_name=doc_name,
        detail_level="full",
    )
    assert resized_base["geometry"][0]["geometry"]["radius"] == pytest.approx(24.0)
    assert resized_hole["geometry"][0]["geometry"]["center"]["x"] == pytest.approx(10.0)
    assert resized_hole["geometry"][0]["geometry"]["radius"] == pytest.approx(6.0)
    assert (
        _constraint_expressions(resized_base)["BaseRadius"] == "Dimensions.BaseRadius"
    )
    assert (
        _constraint_expressions(resized_hole)["HoleRadius"] == "Dimensions.HoleRadius"
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
        detail_level="summary",
    )
    assert resized_top_face["match_count"] == 1, resized_top_face
    assert resized_top_face["matches"][0]["centroid"]["z"] == pytest.approx(36.0)

    await _assert_parametric_model_valid(tools, doc_name)
