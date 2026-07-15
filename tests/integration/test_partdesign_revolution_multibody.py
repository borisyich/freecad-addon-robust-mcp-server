"""Integration coverage for Revolution in documents with multiple Bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.partdesign import register_partdesign_tools

pytestmark = pytest.mark.integration


class _ToolCollector:
    """Minimal FastMCP-compatible collector used to access registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        """Return a decorator that stores the tool by function name."""

        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    """Connect an actual bridge client to the running FreeCAD instance."""
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def revolution_tool(live_bridge: XmlRpcBridge) -> Any:
    """Return the real registered Revolution implementation."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_partdesign_tools(collector, get_bridge)
    return collector.tools["revolution_sketch"]


async def _close_document(bridge: XmlRpcBridge, doc_name: str) -> None:
    """Close the test document when the test finishes."""
    await bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = True
"""
    )


@pytest.mark.asyncio
async def test_base_z_resolves_to_second_body_axis(
    live_bridge: XmlRpcBridge,
    revolution_tool: Any,
) -> None:
    """Base_Z must resolve to Z_Axis001 for a sketch in Body001."""
    doc_name = "MCPRevolutionSecondBody"
    setup = await live_bridge.execute_python(
        f"""
import FreeCAD
import Part
import Sketcher

if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})

# Consume the unsuffixed origin feature names.
doc.addObject("PartDesign::Body", "Body")
body = doc.addObject("PartDesign::Body", "Body001")

sketch = body.newObject("Sketcher::SketchObject", "RevolutionSketch")
xz_plane = next(
    feature for feature in body.Origin.OriginFeatures
    if feature.Name.startswith("XZ_Plane")
)
if hasattr(sketch, "AttachmentSupport"):
    sketch.AttachmentSupport = [(xz_plane, [""])]
else:
    sketch.Support = (xz_plane, [""])
sketch.MapMode = "FlatFace"

# Closed profile offset from the Body Z-axis.
points = [(5.0, -5.0), (10.0, -5.0), (10.0, 5.0), (5.0, 5.0)]
for index, start in enumerate(points):
    end = points[(index + 1) % len(points)]
    sketch.addGeometry(
        Part.LineSegment(
            FreeCAD.Vector(start[0], start[1], 0.0),
            FreeCAD.Vector(end[0], end[1], 0.0),
        ),
        False,
    )

doc.recompute()
_result_ = {{
    "body": body.Name,
    "axis_names": [
        feature.Name for feature in body.Origin.OriginFeatures
        if "Axis" in feature.Name
    ],
}}
"""
    )
    assert setup.success, setup.error_traceback
    assert "Z_Axis001" in setup.result["axis_names"]

    try:
        result = await revolution_tool(
            sketch_name="RevolutionSketch",
            angle=360.0,
            axis="Base_Z",
            doc_name=doc_name,
        )

        state = await live_bridge.execute_python(
            f"""
doc = FreeCAD.listDocuments()[{doc_name!r}]
rev = doc.getObject({result['name']!r})
_result_ = {{
    "shape_valid": bool(
        rev is not None
        and not rev.Shape.isNull()
        and rev.Shape.isValid()
    ),
    "solid_count": len(rev.Shape.Solids) if rev is not None else 0,
    "volume": float(rev.Shape.Volume) if rev is not None else 0.0,
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result["shape_valid"] is True
        assert state.result["solid_count"] == 1
        assert state.result["volume"] > 0.0
    finally:
        await _close_document(live_bridge, doc_name)
