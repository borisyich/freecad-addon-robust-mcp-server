"""Tests for native SheetMetal Workbench tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.tools.sheetmetal import (
    _SHEET_METAL_OPERATION_ADAPTER,
    SheetMetalMaterialRule,
    register_sheetmetal_tools,
)


@pytest.fixture
def mock_bridge():
    """Return a bridge whose Python execution can be inspected."""
    return AsyncMock()


@pytest.fixture
def registered_tools(mock_bridge):
    """Register SheetMetal tools against a minimal FastMCP double."""
    mcp = MagicMock()
    captured = {}

    def tool_decorator():
        def wrapper(func):
            captured[func.__name__] = func
            return func

        return wrapper

    mcp.tool = tool_decorator

    async def get_bridge():
        return mock_bridge

    register_sheetmetal_tools(mcp, get_bridge)
    return captured


def _success(payload=None):
    """Build a successful bridge response."""
    return ExecutionResult(
        success=True,
        result=payload or {"validated": True, "solid_count": 1},
        stdout="",
        stderr="",
        execution_time_ms=1.0,
    )


def test_registers_compact_sheet_metal_surface(registered_tools):
    """The workbench should add five lifecycle tools, not toolbar-button sprawl."""
    assert set(registered_tools) == {
        "sheet_metal_capabilities",
        "create_sheet_metal_base",
        "create_sheet_metal_feature",
        "unfold_sheet_metal",
        "inspect_sheet_metal",
    }


def test_feature_operation_schema_is_strict_and_discriminated():
    """Agents must discover operation-specific fields from the public schema."""
    schema = _SHEET_METAL_OPERATION_ADAPTER.json_schema()

    assert schema["discriminator"]["propertyName"] == "op"
    assert set(schema["discriminator"]["mapping"]) == {
        "flange",
        "fold",
        "junction",
        "relief",
        "corner_relief",
        "extend",
        "hem",
        "solid_bend",
        "from_solid",
    }
    flange_definition = schema["$defs"]["FlangeOperation"]
    assert flange_definition["additionalProperties"] is False
    assert flange_definition["properties"]["length"]["exclusiveMinimum"] == 0


def test_operation_validation_rejects_bad_topology_and_unknown_fields():
    """Malformed topology and misspelled options must fail before FreeCAD."""
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        _SHEET_METAL_OPERATION_ADAPTER.validate_python(
            {
                "op": "flange",
                "base_feature": "BaseBend",
                "edges": ["Face1"],
                "length": 20,
                "radius": 2,
            }
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _SHEET_METAL_OPERATION_ADAPTER.validate_python(
            {
                "op": "junction",
                "base_feature": "Bend",
                "edges": ["Edge1"],
                "gap": 1,
                "silent_default": True,
            }
        )


def test_unfold_material_rule_requires_one_explicit_source():
    """An unfold must never inherit an invisible workbench K-factor default."""
    assert SheetMetalMaterialRule(k_factor=0.38).standard == "ansi"
    assert SheetMetalMaterialRule(material_sheet="material_DC01").k_factor is None

    with pytest.raises(ValidationError, match="exactly one"):
        SheetMetalMaterialRule()
    with pytest.raises(ValidationError, match="exactly one"):
        SheetMetalMaterialRule(k_factor=0.38, material_sheet="material_DC01")


@pytest.mark.asyncio
async def test_capabilities_reports_classes_without_gui_selection(
    registered_tools, mock_bridge
):
    """Capability discovery should import exact proxies and parse package metadata."""
    mock_bridge.execute_python.return_value = _success(
        {"installed": True, "version": "0.8.21", "operations": {"fold": True}}
    )

    result = await registered_tools["sheet_metal_capabilities"]()
    code = mock_bridge.execute_python.await_args.args[0]

    assert result["version"] == "0.8.21"
    assert '"flange": ("SheetMetalCmd", "SMBendWall")' in code
    assert '"unfold": ("SheetMetalUnfoldCmd", "SMUnfold")' in code
    assert "Gui.Selection" not in code


@pytest.mark.asyncio
async def test_create_base_is_native_transactional_and_validated(
    registered_tools, mock_bridge
):
    """Base creation should configure SMBaseBend and commit only valid solids."""
    mock_bridge.execute_python.return_value = _success(
        {"validated": True, "proxy_type": "SMBaseBend", "tip_matches": True}
    )

    result = await registered_tools["create_sheet_metal_base"](
        sketch_name="BlankSketch",
        thickness=1.5,
        radius=2,
        wall_length=80,
        bend_side="middle",
        name="BaseBend",
        doc_name="Enclosure",
    )
    code = mock_bridge.execute_python.await_args.args[0]

    assert result["proxy_type"] == "SMBaseBend"
    assert 'doc.openTransaction("Create Sheet Metal Base")' in code
    assert "from SheetMetalBaseCmd import SMBaseBend" in code
    assert "feature.Thickness = 1.5" in code
    assert "feature.BendSide = 'Middle'" in code
    assert "doc.abortTransaction()" in code
    assert "solid_count != 1" in code
    assert "except NameError:" in code


@pytest.mark.asyncio
async def test_create_base_rejects_invalid_dimensions_before_bridge(
    registered_tools, mock_bridge
):
    """Non-physical base parameters should not start a FreeCAD transaction."""
    with pytest.raises(ValueError, match="must be positive"):
        await registered_tools["create_sheet_metal_base"](
            sketch_name="Blank", thickness=0, radius=1
        )
    mock_bridge.execute_python.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "native_import", "property_evidence"),
    [
        (
            {
                "op": "flange",
                "base_feature": "Base",
                "edges": ["Edge1"],
                "length": 20,
                "radius": 2,
            },
            "from SheetMetalCmd import SMBendWall",
            "feature.LengthSpec = {",
        ),
        (
            {
                "op": "fold",
                "base_feature": "Base",
                "face": "Face1",
                "bend_line_sketch": "B1",
                "radius": 2,
                "k_factor": 0.38,
            },
            "from SheetMetalFoldCmd import SMFoldWall",
            'feature.Position = operation["position"].replace("_", " ")',
        ),
        (
            {
                "op": "junction",
                "base_feature": "Base",
                "edges": ["Edge2"],
                "gap": 1,
            },
            "from SheetMetalJunction import SMJunction",
            'feature.gap = operation["gap"]',
        ),
        (
            {
                "op": "relief",
                "base_feature": "Base",
                "vertices": ["Vertex1"],
                "size": 2,
            },
            "from SheetMetalRelief import SMRelief",
            'feature.relief = operation["size"]',
        ),
        (
            {
                "op": "corner_relief",
                "base_feature": "Base",
                "edges": ["Edge1", "Edge2"],
                "size": 3,
                "k_factor": 0.38,
            },
            "from SheetMetalCornerReliefCmd import SMCornerRelief",
            'feature.SizeRatio = operation["size_ratio"]',
        ),
        (
            {
                "op": "extend",
                "base_feature": "Base",
                "subelements": ["Edge1"],
                "length": 10,
            },
            "from SheetMetalExtendCmd import SMExtrudeWall",
            'feature.UseSubtraction = operation["use_subtraction"]',
        ),
        (
            {
                "op": "hem",
                "base_feature": "Base",
                "edges": ["Edge1"],
                "hem_type": "open",
            },
            "from SheetMetalHem import SMHem",
            'feature.HemType = operation["hem_type"].title()',
        ),
        (
            {
                "op": "solid_bend",
                "base_feature": "Base",
                "edges": ["Edge1"],
                "radius": 2,
            },
            "from SheetMetalBend import SMSolidBend",
            'feature.radius = operation["radius"]',
        ),
        (
            {
                "op": "from_solid",
                "base_feature": "ThinSolid",
                "remove_faces_and_rip_edges": ["Face1", "Edge2"],
                "thickness": 1.5,
                "radius": 2,
            },
            "from SheetMetalFromSolid import SMFromSolid",
            'feature.Thickness = operation["thickness"]',
        ),
    ],
)
async def test_every_feature_variant_dispatches_to_native_proxy(
    registered_tools, mock_bridge, operation, native_import, property_evidence
):
    """Every public variant should build one native editable feature."""
    mock_bridge.execute_python.return_value = _success()

    await registered_tools["create_sheet_metal_feature"](
        operation=operation, doc_name="SheetPart"
    )
    code = mock_bridge.execute_python.await_args.args[0]

    assert native_import in code
    assert property_evidence in code
    assert "_sm_validate_refs" in code
    assert 'doc.openTransaction("Create Sheet Metal Feature")' in code
    assert "doc.abortTransaction()" in code
    assert "tip is not base" in code


@pytest.mark.asyncio
async def test_invalid_feature_payload_never_reaches_bridge(
    registered_tools, mock_bridge
):
    """Discriminated validation should happen before generated code execution."""
    with pytest.raises(ValidationError):
        await registered_tools["create_sheet_metal_feature"](
            operation={
                "op": "corner_relief",
                "base_feature": "Base",
                "edges": ["Edge1"],
                "size": 3,
                "k_factor": 0.38,
            }
        )
    mock_bridge.execute_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_unfold_keeps_formed_body_and_uses_explicit_manual_rule(
    registered_tools, mock_bridge
):
    """Unfold should be outside the Body and retain explicit allowance evidence."""
    mock_bridge.execute_python.return_value = _success(
        {"validated": True, "material_source": "manual_k_factor"}
    )

    result = await registered_tools["unfold_sheet_metal"](
        feature_name="Hem",
        stationary_face="Face6",
        material={"k_factor": 0.38, "standard": "ansi"},
        doc_name="Enclosure",
    )
    code = mock_bridge.execute_python.await_args.args[0]

    assert result["material_source"] == "manual_k_factor"
    assert "from SheetMetalUnfoldCmd import SMUnfold" in code
    assert "feature, _unused_body = _sm_new_feature" in code
    assert "False)" in code
    assert 'feature.MaterialSheet = "_manual"' in code
    assert 'feature.KFactor = material["k_factor"]' in code
    assert "base.Visibility = True" in code
    assert '"Plane" not in surface_name' in code


@pytest.mark.asyncio
async def test_unfold_material_sheet_is_resolved_and_type_checked(
    registered_tools, mock_bridge
):
    """A material-table unfold must link a real Spreadsheet object."""
    mock_bridge.execute_python.return_value = _success()

    await registered_tools["unfold_sheet_metal"](
        feature_name="Bend",
        stationary_face="Face1",
        material={"material_sheet": "material_DC01"},
    )
    code = mock_bridge.execute_python.await_args.args[0]

    assert '"Material sheet"' in code
    assert '!= "Spreadsheet::Sheet"' in code
    assert "feature.MaterialSheet = sheet.Name" in code


@pytest.mark.asyncio
async def test_inspector_reports_manufacturing_evidence(registered_tools, mock_bridge):
    """Inspection should expose thickness, bends, root faces, history, and warnings."""
    expected = {
        "object": "Bend",
        "estimated_thickness": 1.5,
        "cylindrical_bend_face_count": 1,
        "unfold_ready": True,
    }
    mock_bridge.execute_python.return_value = _success(expected)

    result = await registered_tools["inspect_sheet_metal"](
        object_name="Bend", doc_name="Enclosure"
    )
    code = mock_bridge.execute_python.await_args.args[0]

    assert result == expected
    for evidence in (
        "smGetThickness",
        "stationary_face_candidates",
        "cylindrical_bend_face_count",
        "sheet_metal_history",
        "unfold_ready",
        "warnings",
    ):
        assert evidence in code


@pytest.mark.asyncio
async def test_bridge_failure_is_actionable(registered_tools, mock_bridge):
    """FreeCAD tracebacks should propagate instead of returning false success."""
    mock_bridge.execute_python.return_value = ExecutionResult(
        success=False,
        result=None,
        stdout="",
        stderr="",
        error_type="ImportError",
        error_traceback="ImportError: SheetMetalTools",
        execution_time_ms=1.0,
    )

    with pytest.raises(ValueError, match="ImportError: SheetMetalTools"):
        await registered_tools["inspect_sheet_metal"]("Part")
