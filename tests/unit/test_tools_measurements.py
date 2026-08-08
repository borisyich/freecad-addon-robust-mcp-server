"""Tests for the compact measurement contract and generated OCCT code."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.tools.measurements import GeometryReference, PointToFaceMeasurement


@pytest.fixture
def registered_tools():
    mcp = MagicMock()
    tools = {}

    def tool_decorator():
        def wrapper(function):
            tools[function.__name__] = function
            return function

        return wrapper

    mcp.tool = tool_decorator
    bridge = AsyncMock()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={"measurement": "test", "value": 1.0},
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    async def get_bridge():
        return bridge

    from freecad_mcp.tools.measurements import register_measurement_tools

    register_measurement_tools(mcp, get_bridge)
    return tools, bridge


def test_only_compact_measurement_tool_is_registered(registered_tools):
    tools, _ = registered_tools
    assert set(tools) == {"measure_geometry"}


def test_geometry_reference_rejects_unsupported_or_zero_subshape_indices():
    for subshape in ("Wire1", "Vertex0", "Face-1", "Edge"):
        with pytest.raises(ValidationError):
            GeometryReference(object_name="Part", subshape=subshape)


@pytest.mark.asyncio
async def test_bbox_uses_both_occt_modes_and_forced_recompute(registered_tools):
    tools, bridge = registered_tools
    await tools["measure_geometry"](
        measurement={
            "kind": "bbox",
            "object_name": "Body",
            "mode": "optimal",
            "coordinate_system": "local",
            "use_shape_tolerance": True,
        },
        force_recompute=True,
        doc_name="Model",
    )
    code = bridge.execute_python.await_args.args[0]
    compile(code, "<measure-bbox>", "exec")
    assert "obj.touch()" in code
    assert "shape.BoundBox" in code
    assert "shape.optimalBoundingBox" in code
    assert "inverse_global_placement" in code
    assert "BRepBndLib::AddOptimal" in code
    assert "FreeCAD.getDocument('Model')" in code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("measurement", "expected_code"),
    [
        (
            {
                "kind": "distance",
                "first": {"object_name": "Body", "subshape": "Face2"},
                "second": {"object_name": "Tool", "subshape": "Edge3"},
            },
            "_m_public_distance(_m_distance",
        ),
        (
            {
                "kind": "angle",
                "first": {"object_name": "Body", "subshape": "Face2"},
                "second": {"object_name": "Tool", "subshape": "Edge3"},
            },
            "_m_angle(doc",
        ),
        (
            {
                "kind": "clearance",
                "first": {"object_name": "Body", "subshape": "Face2"},
                "second": {"object_name": "Tool", "subshape": "Edge3"},
                "required_clearance_mm": 0.5,
            },
            "_m_interference",
        ),
    ],
)
async def test_pair_measurements_accept_selector_references(
    registered_tools, measurement, expected_code
):
    tools, bridge = registered_tools
    await tools["measure_geometry"](measurement=measurement, doc_name="Model")
    code = bridge.execute_python.await_args.args[0]
    compile(code, f"<measure-{measurement['kind']}>", "exec")
    assert "'subshape': 'Face2'" in code
    assert "'subshape': 'Edge3'" in code
    assert expected_code in code


@pytest.mark.asyncio
async def test_specialized_measurements_keep_runtime_validation(registered_tools):
    tools, bridge = registered_tools
    measure = tools["measure_geometry"]

    await measure(
        measurement={
            "kind": "wall_thickness",
            "first_face": {"object_name": "Tube", "subshape": "Face1"},
            "second_face": {"object_name": "Tube", "subshape": "Face2"},
        }
    )
    wall_code = bridge.execute_python.await_args.args[0]
    assert '_m_resolve(doc, first_spec, "Face")' in wall_code
    assert "coaxial_cylinders" in wall_code

    await measure(
        measurement={
            "kind": "radius",
            "reference": {"object_name": "Cylinder", "subshape": "Face1"},
        }
    )
    radius_code = bridge.execute_python.await_args.args[0]
    assert "A conical face has no constant radius" in radius_code
    assert "MajorRadius" in radius_code

    await measure(
        measurement={
            "kind": "point_to_face",
            "face": {"object_name": "Box", "subshape": "Face6"},
            "vertex": {"object_name": "Cylinder", "subshape": "Vertex1"},
        }
    )
    point_code = bridge.execute_python.await_args.args[0]
    assert 'vertex_spec, "Vertex"' in point_code
    assert "Part.Vertex" in point_code
    compile(point_code, "<point-to-face>", "exec")


@pytest.mark.asyncio
async def test_minimum_gap_checks_every_pair(registered_tools):
    tools, bridge = registered_tools
    await tools["measure_geometry"](
        measurement={
            "kind": "minimum_gap",
            "references": [
                {"object_name": "A"},
                {"object_name": "B"},
                {"object_name": "C", "subshape": "Face1"},
            ],
        }
    )
    code = bridge.execute_python.await_args.args[0]
    assert "for _j in range(_i + 1" in code
    assert "'pair_count': len(_pairs)" in code
    compile(code, "<minimum-gap>", "exec")


def test_point_to_face_requires_exactly_one_point_source():
    face = {"object_name": "Box", "subshape": "Face1"}
    with pytest.raises(ValidationError, match="exactly one"):
        PointToFaceMeasurement(kind="point_to_face", face=face)
    with pytest.raises(ValidationError, match="exactly one"):
        PointToFaceMeasurement(
            kind="point_to_face",
            face=face,
            point=[0, 0, 0],
            vertex={"object_name": "Box", "subshape": "Vertex1"},
        )


@pytest.mark.asyncio
async def test_discriminator_rejects_unknown_kinds_and_cross_kind_fields(
    registered_tools,
):
    tools, bridge = registered_tools
    measure = tools["measure_geometry"]
    with pytest.raises(ValidationError):
        await measure(measurement={"kind": "volume", "object_name": "Body"})
    with pytest.raises(ValidationError, match="mode"):
        await measure(
            measurement={
                "kind": "distance",
                "first": {"object_name": "A"},
                "second": {"object_name": "B"},
                "mode": "optimal",
            }
        )
    bridge.execute_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_bridge_errors_are_not_hidden(registered_tools):
    tools, bridge = registered_tools
    bridge.execute_python.return_value = ExecutionResult(
        success=False,
        result=None,
        stdout="",
        stderr="OCCT failure",
        execution_time_ms=1.0,
        error_type="RuntimeError",
        error_traceback="Traceback: OCCT failure",
    )
    with pytest.raises(ValueError, match="OCCT failure"):
        await tools["measure_geometry"](
            measurement={
                "kind": "distance",
                "first": {"object_name": "A"},
                "second": {"object_name": "B"},
            }
        )
