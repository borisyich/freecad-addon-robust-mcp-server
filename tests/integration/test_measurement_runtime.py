"""Live FreeCAD/OCCT tests for measurement runtime evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools import register_all_tools
from freecad_mcp.tools.measurements import _measurement_code

if TYPE_CHECKING:
    import xmlrpc.client

pytestmark = pytest.mark.integration


class _ToolCollector:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        name = kwargs.get("name")

        def decorator(function: Any) -> Any:
            self.tools[name or function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def measurement_tools():
    bridge = XmlRpcBridge()
    await bridge.connect()
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return bridge

    register_all_tools(collector, get_bridge)
    try:
        yield collector.tools
    finally:
        await bridge.disconnect()


async def _call(tools: dict[str, Any], tool_name: str, **kwargs: Any) -> Any:
    result = await tools[tool_name](**kwargs)
    if isinstance(result, dict) and result.get("success") is False:
        raise AssertionError(f"{tool_name} returned unsuccessful result: {result!r}")
    return result


def _execute(proxy: xmlrpc.client.ServerProxy, code: str) -> dict[str, Any]:
    result: dict[str, Any] = proxy.execute(code)  # type: ignore[assignment]
    assert result.get("success"), result.get("error_traceback")
    return result["result"]


@pytest.fixture
def measurement_document(xmlrpc_proxy: xmlrpc.client.ServerProxy):
    doc_name = "MCPMeasurementRuntime"
    _execute(
        xmlrpc_proxy,
        f"""
import FreeCAD
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
box_a = doc.addObject("Part::Feature", "BoxA")
box_a.Shape = Part.makeBox(10, 20, 30)
box_a.Placement.Base = FreeCAD.Vector(100, 0, 0)
box_b = doc.addObject("Part::Feature", "BoxB")
box_b.Shape = Part.makeBox(10, 20, 30)
box_b.Placement.Base = FreeCAD.Vector(115, 0, 0)
cylinder = doc.addObject("Part::Feature", "Cylinder")
cylinder.Shape = Part.makeCylinder(4, 12)
cylinder.Placement.Base = FreeCAD.Vector(0, 50, 0)
doc.recompute()
_result_ = {{"document": doc.Name}}
""",
    )
    try:
        yield doc_name
    finally:
        _execute(
            xmlrpc_proxy,
            f"""
import FreeCAD
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = {{"closed": True}}
""",
        )


def _measure(
    proxy: xmlrpc.client.ServerProxy,
    doc_name: str,
    names: list[str],
    expression: str,
) -> dict[str, Any]:
    return _execute(proxy, _measurement_code(doc_name, names, True, expression))


def test_bbox_fast_optimal_local_world_and_tolerance_evidence(
    xmlrpc_proxy: xmlrpc.client.ServerProxy, measurement_document: str
) -> None:
    world = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA"],
        "_m_bbox(doc, 'BoxA', 'optimal', 'world', False, False, True, _recompute_evidence)",
    )
    local = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA"],
        "_m_bbox(doc, 'BoxA', 'fast', 'local', False, False, True, _recompute_evidence)",
    )

    assert world["bounds_mm"]["min"]["x"] == pytest.approx(100.0)
    assert world["bounds_mm"]["size"] == pytest.approx(
        {"x": 10.0, "y": 20.0, "z": 30.0}
    )
    assert local["bounds_mm"]["min"]["x"] == pytest.approx(0.0)
    assert local["coordinate_transform"]["method"] == "inverse_global_placement"
    assert world["recompute"]["forced"] is True
    assert world["tolerance_report"]["maximum_mm"] == pytest.approx(1e-7)
    assert "maximum_absolute_difference_mm" in world["gap_report"]


def test_distance_clearance_angle_radius_and_minimum_gap_runtime(
    xmlrpc_proxy: xmlrpc.client.ServerProxy, measurement_document: str
) -> None:
    first = {"object_name": "BoxA"}
    second = {"object_name": "BoxB"}
    distance = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA", "BoxB"],
        f"_m_public_distance(_m_distance(doc, {first!r}, {second!r}, 1e-7))",
    )
    clearance = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA", "BoxB"],
        f"(lambda _d: {{'distance': _m_public_distance(_d), "
        f"'interference': _m_interference(_d, 1e-7)}})"
        f"(_m_distance(doc, {first!r}, {second!r}, 1e-7))",
    )
    angle = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA"],
        "_m_angle(doc, {'object_name':'BoxA','subshape':'Face1'}, "
        "{'object_name':'BoxA','subshape':'Face3'}, 'undirected')",
    )
    radius = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["Cylinder"],
        "_m_radius(doc, {'object_name':'Cylinder','subshape':'Face1'}, 'auto')",
    )

    assert distance["distance_mm"] == pytest.approx(5.0)
    assert distance["solutions"][0]["point_on_first"]["x"] == pytest.approx(110.0)
    assert clearance["interference"]["volume_mm3"] == 0.0
    assert angle["angle_deg"] == pytest.approx(90.0)
    assert radius["radius_mm"] == pytest.approx(4.0)
    assert radius["diameter_mm"] == pytest.approx(8.0)


def test_wall_thickness_and_point_to_face_reject_topology_guessing(
    xmlrpc_proxy: xmlrpc.client.ServerProxy, measurement_document: str
) -> None:
    thickness = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA"],
        "_m_wall_thickness(doc, "
        "{'object_name':'BoxA','subshape':'Face1'}, "
        "{'object_name':'BoxA','subshape':'Face2'}, 1e-7, True)",
    )
    point_distance = _measure(
        xmlrpc_proxy,
        measurement_document,
        ["BoxA"],
        "_m_point_to_face(doc, {'object_name':'BoxA','subshape':'Face6'}, "
        "[105, 5, 40], None, 1e-7)",
    )

    assert thickness["validated_opposing_surfaces"] is True
    assert thickness["thickness_mm"] == pytest.approx(10.0)
    assert point_distance["distance_mm"] == pytest.approx(10.0)
    assert point_distance["nearest_point_on_face"] == pytest.approx(
        {"x": 105.0, "y": 5.0, "z": 30.0}
    )


@pytest.mark.asyncio
async def test_registered_measurement_tools_run_end_to_end(
    measurement_tools: dict[str, Any], measurement_document: str
) -> None:
    """Exercise every kind through the compact public measurement wrapper."""
    bbox = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "bbox",
            "object_name": "BoxA",
            "mode": "fast",
            "report_gap": False,
        },
        doc_name=measurement_document,
    )
    distance = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "distance",
            "first": {"object_name": "BoxA"},
            "second": {"object_name": "BoxB"},
        },
        doc_name=measurement_document,
    )
    angle = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "angle",
            "first": {"object_name": "BoxA", "subshape": "Face1"},
            "second": {"object_name": "BoxA", "subshape": "Face3"},
        },
        doc_name=measurement_document,
    )
    radius = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "radius",
            "reference": {"object_name": "Cylinder", "subshape": "Face1"},
        },
        doc_name=measurement_document,
    )
    thickness = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "wall_thickness",
            "first_face": {"object_name": "BoxA", "subshape": "Face1"},
            "second_face": {"object_name": "BoxA", "subshape": "Face2"},
        },
        doc_name=measurement_document,
    )
    clearance = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "clearance",
            "first": {"object_name": "BoxA"},
            "second": {"object_name": "BoxB"},
            "required_clearance_mm": 4.0,
        },
        doc_name=measurement_document,
    )
    minimum_gap = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "minimum_gap",
            "references": [
                {"object_name": "BoxA"},
                {"object_name": "BoxB"},
                {"object_name": "Cylinder"},
            ],
        },
        doc_name=measurement_document,
    )
    point_to_face = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "point_to_face",
            "face": {"object_name": "BoxA", "subshape": "Face6"},
            "point": [105.0, 5.0, 40.0],
        },
        doc_name=measurement_document,
    )
    selected_vertex = await _call(
        measurement_tools,
        "select_subshapes",
        object_name="BoxA",
        criteria={
            "kind": "vertex",
            "point_bounds": {
                "x_min": 109.99,
                "x_max": 110.01,
                "y_min": -0.01,
                "y_max": 0.01,
                "z_min": 29.99,
                "z_max": 30.01,
            },
            "limit": 1,
        },
        detail_level="summary",
        doc_name=measurement_document,
    )
    selected_vertex_distance = await _call(
        measurement_tools,
        "measure_geometry",
        measurement={
            "kind": "point_to_face",
            "face": {"object_name": "BoxB", "subshape": "Face1"},
            "vertex": {
                "object_name": "BoxA",
                "subshape": selected_vertex["references"][0],
            },
        },
        doc_name=measurement_document,
    )
    with pytest.raises(ValueError, match="overlapping parallel planar faces"):
        await _call(
            measurement_tools,
            "measure_geometry",
            measurement={
                "kind": "wall_thickness",
                "first_face": {"object_name": "BoxA", "subshape": "Face6"},
                "second_face": {"object_name": "BoxB", "subshape": "Face6"},
            },
            doc_name=measurement_document,
        )

    assert bbox["gap_report"]["reported"] is False
    assert distance["distance_mm"] == pytest.approx(5.0)
    assert angle["angle_deg"] == pytest.approx(90.0)
    assert radius["diameter_mm"] == pytest.approx(8.0)
    assert thickness["thickness_mm"] == pytest.approx(10.0)
    assert clearance["passes"] is True
    assert minimum_gap["pair_count"] == 3
    assert minimum_gap["minimum_gap_mm"] == pytest.approx(5.0)
    assert point_to_face["distance_mm"] == pytest.approx(10.0)
    assert selected_vertex["references"]
    assert selected_vertex_distance["distance_mm"] == pytest.approx(5.0)
