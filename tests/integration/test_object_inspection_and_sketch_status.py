"""Live coverage for structured inspection and sketch diagnostics.

Run with a FreeCAD instance whose Robust MCP XML-RPC bridge is listening on
localhost:9875.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.objects import register_object_tools
from freecad_mcp.tools.partdesign import register_partdesign_tools

pytestmark = pytest.mark.integration


class _ToolCollector:
    """Minimal FastMCP-compatible collector."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        """Store decorated tools by function name."""

        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    """Connect to the running FreeCAD bridge."""
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    """Register the real tools against the live bridge."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_object_tools(collector, get_bridge)
    register_partdesign_tools(collector, get_bridge)
    return collector.tools


async def _close_document(bridge: XmlRpcBridge, doc_name: str) -> None:
    await bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = True
"""
    )


@pytest.mark.asyncio
async def test_inspect_object_returns_semantic_property_values(
    live_bridge: XmlRpcBridge,
    tools: dict[str, Any],
) -> None:
    """Shapes, placements, and quantities must not degrade to pointer reprs."""
    doc_name = "MCPStructuredInspection"
    setup = await live_bridge.execute_python(
        f"""
import FreeCAD
import Part

if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
box = doc.addObject("Part::Box", "Box")
box.Length = 10.0
box.Width = 20.0
box.Height = 30.0
box.Placement.Base = FreeCAD.Vector(1.0, 2.0, 3.0)
cylinder = doc.addObject("Part::Cylinder", "Cylinder")
cylinder.Radius = 5.0
cylinder.Height = 20.0
cylinder.Placement.Base = FreeCAD.Vector(30.0, 0.0, 0.0)
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    try:
        result = await tools["inspect_object"](
            "Box", doc_name=doc_name, include_properties=True
        )

        assert result["properties"]["Length"]["value"]["value"] == 10.0
        assert result["properties"]["Placement"]["value"]["position"] == {
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
        }
        assert result["properties"]["Shape"]["value"] == {"summary_ref": "shape_info"}
        assert result["shape_info"]["shape_type"] == "Solid"
        assert result["shape_info"]["volume"] == pytest.approx(6000.0)
        assert result["shape_info"]["bounding_box"]["size"] == {
            "x": 10.0,
            "y": 20.0,
            "z": 30.0,
        }
        assert len(result["shape_info"]["faces"]) == 6
        assert len(result["shape_info"]["edges"]) == 12
        assert all(
            face["surface_type"] == "Plane" for face in result["shape_info"]["faces"]
        )
        assert all(
            face["convexity"] == "flat" for face in result["shape_info"]["faces"]
        )
        assert all(
            edge["curve_type"] == "Line" for edge in result["shape_info"]["edges"]
        )
        assert all(
            len(edge["adjacent_faces"]) == 2 for edge in result["shape_info"]["edges"]
        )

        selected = await tools["select_subshapes"](
            object_name="Box",
            doc_name=doc_name,
            criteria={
                "kind": "face",
                "surface_types": ["Plane"],
                "normal": [0, 0, 1],
                "sort_by": "center_z",
                "sort_order": "desc",
                "limit": 1,
            },
            detail_level="summary",
        )
        assert selected["match_count"] == 1
        assert selected["references"][0].startswith("Face")
        assert selected["matches"][0]["normal"]["z"] == pytest.approx(1.0)

        x_edges = await tools["select_subshapes"](
            object_name="Box",
            doc_name=doc_name,
            criteria={
                "kind": "edge",
                "curve_types": ["LineSegment"],
                "direction": [1, 0, 0],
                "length_min": 9.9,
                "length_max": 10.1,
                "sort_by": "index",
            },
        )
        assert x_edges["match_count"] == 4
        assert all(item.startswith("Edge") for item in x_edges["references"])

        cylinder_info = await tools["inspect_object"](
            "Cylinder", doc_name=doc_name, detail_level="topology"
        )
        cylindrical_faces = [
            face
            for face in cylinder_info["shape_info"]["faces"]
            if face["surface_type"] == "Cylinder"
        ]
        assert len(cylindrical_faces) == 1
        assert cylindrical_faces[0]["convexity"] in {"convex", "concave"}
        assert cylindrical_faces[0]["normal"] is not None
        assert any(
            edge["curve_type"] == "Circle"
            for edge in cylinder_info["shape_info"]["edges"]
        )

        serialized = json.dumps(result)
        assert " object at " not in serialized
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_sketch_mutations_return_solver_and_profile_state(
    live_bridge: XmlRpcBridge,
    tools: dict[str, Any],
) -> None:
    """A circle should be closed immediately and become fully constrained later."""
    doc_name = "MCPSketchDiagnostics"
    setup = await live_bridge.execute_python(
        f"""
import FreeCAD
import Sketcher

if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
sheet.set("A1", "10 mm")
sheet.setAlias("A1", "CenterX")
sheet.set("A2", "5 mm")
sheet.setAlias("A2", "CenterY")
sheet.set("A3", "4 mm")
sheet.setAlias("A3", "Radius")
doc.addObject("Sketcher::SketchObject", "Sketch")
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    try:
        added = await tools["edit_sketch_geometry"](
            "Sketch",
            operations=[
                {
                    "op": "add_circle",
                    "center_x": 10.0,
                    "center_y": 5.0,
                    "radius": 4.0,
                }
            ],
            doc_name=doc_name,
        )
        status = added["sketch_status"]
        assert status["profile"]["state"] == "closed"
        assert status["profile_ready"] is True
        assert status["solver"]["status"] == "under_constrained"
        assert status["solver"]["remaining_dof"] == 3

        constrained = await tools["edit_sketch_constraints"](
            "Sketch",
            operations=[
                {
                    "op": "distance_x",
                    "geometry1": 0,
                    "point1": 3,
                    "value": 10.0,
                    "constraint_name": "CenterX",
                    "expression": "Dimensions.CenterX",
                },
                {
                    "op": "distance_y",
                    "geometry1": 0,
                    "point1": 3,
                    "value": 5.0,
                    "constraint_name": "CenterY",
                    "expression": "Dimensions.CenterY",
                },
                {
                    "op": "radius",
                    "geometry1": 0,
                    "value": 4.0,
                    "constraint_name": "Radius",
                    "expression": "Dimensions.Radius",
                },
            ],
            doc_name=doc_name,
            detail_level="full",
        )

        final_status = constrained["sketch_status"]
        assert final_status["solver"]["status"] == "fully_constrained"
        assert final_status["solver"]["remaining_dof"] == 0
        assert final_status["profile"]["state"] == "closed"
        assert "issues" not in final_status
        assert len(constrained["geometry"]) == 1
        assert constrained["geometry"][0]["geometry"]["radius"] == pytest.approx(4.0)
        assert constrained["constraints"][0]["expression"] == "Dimensions.CenterX"
        assert constrained["constraints"][2]["expression"] == "Dimensions.Radius"

        info = await tools["get_sketch_info"](
            "Sketch", doc_name=doc_name, detail_level="full"
        )
        assert "start_point" in info["geometry"][0]
        assert "end_point" in info["geometry"][0]
        assert len(info["constraints"]) == 3
        assert len(info["expressions"]) == 3
        assert {item["expression"] for item in info["expressions"]} == {
            "Dimensions.CenterX",
            "Dimensions.CenterY",
            "Dimensions.Radius",
        }
        assert all(
            item["path"].startswith("Constraints") for item in info["expressions"]
        )
    finally:
        await _close_document(live_bridge, doc_name)
