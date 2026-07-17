"""Integration tests for the strict ``create_hole`` geometry contract.

These tests invoke the registered MCP tool against a running FreeCAD XML-RPC
bridge. Start FreeCAD with the Robust MCP Bridge before running this module.
"""

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
def create_hole_tool(live_bridge: XmlRpcBridge) -> Any:
    """Return the real registered create_hole implementation."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_partdesign_tools(collector, get_bridge)
    return collector.tools["create_hole"]


@pytest.fixture
def create_cylindrical_cut_tool(live_bridge: XmlRpcBridge) -> Any:
    """Return the real registered explicit-axis cylindrical cut tool."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_partdesign_tools(collector, get_bridge)
    return collector.tools["create_cylindrical_cut"]


async def _create_test_body(
    bridge: XmlRpcBridge,
    doc_name: str,
    sketch_name: str,
    geometry: str,
) -> None:
    """Create a box feature followed by a supported XY-plane sketch."""
    code = f"""
import FreeCAD
import Part
import Sketcher

if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
base = body.newObject("PartDesign::Feature", "BaseSolid")
base.Shape = Part.makeBox(
    60.0,
    30.0,
    10.0,
    FreeCAD.Vector(-30.0, -15.0, 0.0),
)
body.Tip = base

sketch = body.newObject("Sketcher::SketchObject", {sketch_name!r})
xy_plane = next(
    item for item in body.Origin.OriginFeatures
    if item.Name.startswith("XY_Plane")
)
if hasattr(sketch, "AttachmentSupport"):
    sketch.AttachmentSupport = [(xy_plane, [""])]
else:
    sketch.Support = (xy_plane, [""])
sketch.MapMode = "FlatFace"
{geometry}
doc.recompute()
_result_ = {{
    "base_volume": float(base.Shape.Volume),
    "sketch_geometry_count": int(sketch.GeometryCount),
}}
"""
    result = await bridge.execute_python(code)
    assert result.success, result.error_traceback


async def _document_state(bridge: XmlRpcBridge, doc_name: str) -> dict[str, Any]:
    """Return Hole objects and current Body Tip for assertions."""
    result = await bridge.execute_python(
        f"""
doc = FreeCAD.listDocuments()[{doc_name!r}]
body = doc.getObject("Body")
_result_ = {{
    "holes": [
        obj.Name for obj in doc.Objects
        if obj.TypeId == "PartDesign::Hole"
    ],
    "tip": getattr(body.Tip, "Name", None),
}}
"""
    )
    assert result.success, result.error_traceback
    return result.result


async def _close_document(bridge: XmlRpcBridge, doc_name: str) -> None:
    """Close a test document, including after a failed assertion."""
    await bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = True
"""
    )


async def _create_datum_plane_hole_fixture(
    bridge: XmlRpcBridge,
    doc_name: str,
) -> None:
    """Create a solid followed by a circle sketch on a PartDesign datum plane."""
    result = await bridge.execute_python(
        f"""
import FreeCAD
import Part

if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
base = body.newObject("PartDesign::Feature", "BaseSolid")
base.Shape = Part.makeBox(
    30.0,
    30.0,
    10.0,
    FreeCAD.Vector(-15.0, -15.0, 0.0),
)
body.Tip = base

plane = body.newObject("PartDesign::Plane", "HoleDatum")
xy_plane = next(
    item for item in body.Origin.OriginFeatures
    if item.Name.startswith("XY_Plane")
)
if hasattr(plane, "AttachmentSupport"):
    plane.AttachmentSupport = [(xy_plane, [""])]
else:
    plane.Support = (xy_plane, [""])
plane.MapMode = "FlatFace"
plane.AttachmentOffset = FreeCAD.Placement(
    FreeCAD.Vector(0.0, 0.0, 10.0), FreeCAD.Rotation()
)

sketch = body.newObject("Sketcher::SketchObject", "DatumHoleSketch")
if hasattr(sketch, "AttachmentSupport"):
    sketch.AttachmentSupport = [(plane, [""])]
else:
    sketch.Support = (plane, [""])
sketch.MapMode = "FlatFace"
sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 2.5),
    False,
)
doc.recompute()
_result_ = {{
    "datum_type": plane.TypeId,
    "sketch_support": str(getattr(sketch, "AttachmentSupport", "")),
}}
"""
    )
    assert result.success, result.error_traceback


@pytest.mark.asyncio
async def test_three_circles_create_three_valid_holes_with_auto_direction(
    live_bridge: XmlRpcBridge,
    create_hole_tool: Any,
) -> None:
    """A box above XY should be cut and normally require reversed direction."""
    doc_name = "MCPHoleThreeCircles"
    geometry = """
for x in (-20.0, 0.0, 20.0):
    sketch.addGeometry(
        Part.Circle(FreeCAD.Vector(x, 0.0, 0.0), FreeCAD.Vector(0, 0, 1), 2.5),
        False,
    )
"""
    await _create_test_body(live_bridge, doc_name, "HoleCirclesSketch", geometry)
    try:
        result = await create_hole_tool(
            sketch_name="HoleCirclesSketch",
            diameter=5.0,
            depth=15.0,
            doc_name=doc_name,
        )

        assert result["validated"] is True
        assert result["removed_volume"] > 0.0
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_point_only_profile_fails_without_leaving_hole(
    live_bridge: XmlRpcBridge,
    create_hole_tool: Any,
) -> None:
    """Sketch points must not be reported as successful Hole geometry."""
    doc_name = "MCPHolePointOnly"
    geometry = """
for x in (-20.0, 0.0, 20.0):
    sketch.addGeometry(Part.Point(FreeCAD.Vector(x, 0.0, 0.0)), False)
"""
    await _create_test_body(live_bridge, doc_name, "HolePointsSketch", geometry)
    try:
        with pytest.raises(ValueError, match="no non-construction circles"):
            await create_hole_tool(
                sketch_name="HolePointsSketch",
                diameter=5.0,
                depth=15.0,
                doc_name=doc_name,
            )

        state = await _document_state(live_bridge, doc_name)
        assert state["holes"] == []
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_explicit_wrong_direction_rolls_back_feature(
    live_bridge: XmlRpcBridge,
    create_hole_tool: Any,
) -> None:
    """A no-op direction must fail and restore the original Body history."""
    doc_name = "MCPHoleWrongDirection"
    geometry = """
sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0, 0, 1), 2.5),
    False,
)
"""
    await _create_test_body(live_bridge, doc_name, "HoleCircleSketch", geometry)
    try:
        with pytest.raises(ValueError, match="no valid subtractive result"):
            await create_hole_tool(
                sketch_name="HoleCircleSketch",
                diameter=5.0,
                depth=15.0,
                reversed=False,
                doc_name=doc_name,
            )

        state = await _document_state(live_bridge, doc_name)
        assert state["holes"] == []
        assert state["tip"] in {"BaseSolid", "HoleCircleSketch"}
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_successful_profile_cannot_be_reused(
    live_bridge: XmlRpcBridge,
    create_hole_tool: Any,
) -> None:
    """The second operation on one consumed sketch must be rejected."""
    doc_name = "MCPHoleSketchReuse"
    geometry = """
sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0, 0, 1), 2.5),
    False,
)
"""
    await _create_test_body(live_bridge, doc_name, "HoleCircleSketch", geometry)
    try:
        first = await create_hole_tool(
            sketch_name="HoleCircleSketch",
            diameter=5.0,
            depth=15.0,
            doc_name=doc_name,
        )
        assert first["validated"] is True

        with pytest.raises(ValueError, match="already consumed"):
            await create_hole_tool(
                sketch_name="HoleCircleSketch",
                diameter=6.0,
                depth=10.0,
                doc_name=doc_name,
            )

        state = await _document_state(live_bridge, doc_name)
        assert state["holes"] == [first["name"]]
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_datum_plane_hole_is_rejected_with_cylindrical_cut_guidance(
    live_bridge: XmlRpcBridge,
    create_hole_tool: Any,
) -> None:
    """A datum-plane Hole must fail before leaving a no-op feature behind."""
    doc_name = "MCPHoleDatumPlaneRejected"
    await _create_datum_plane_hole_fixture(live_bridge, doc_name)
    try:
        with pytest.raises(ValueError, match="create_cylindrical_cut"):
            await create_hole_tool(
                sketch_name="DatumHoleSketch",
                diameter=5.0,
                depth=10.0,
                reversed=True,
                doc_name=doc_name,
            )

        state = await _document_state(live_bridge, doc_name)
        assert state["holes"] == []
    finally:
        await _close_document(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_explicit_axis_cylindrical_cut_handles_radial_style_hole(
    live_bridge: XmlRpcBridge,
    create_cylindrical_cut_tool: Any,
) -> None:
    """The explicit-axis tool should replace datum-plane Hole workarounds."""
    doc_name = "MCPCylindricalCutExplicitAxis"
    geometry = """
sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0, 0, 1), 1.0),
    True,
)
"""
    await _create_test_body(live_bridge, doc_name, "UnusedReferenceSketch", geometry)
    try:
        # Restore the solid Tip because the reference sketch is intentionally
        # not part of the cut operation.
        await live_bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("Body")
body.Tip = doc.getObject("BaseSolid")
doc.recompute()
_result_ = True
"""
        )
        result = await create_cylindrical_cut_tool(
            body_name="Body",
            axis_origin=[0.0, 0.0, 10.0],
            axis_direction=[0.0, 0.0, -1.0],
            diameter=5.0,
            depth=10.0,
            name="ExplicitAxisHole",
            doc_name=doc_name,
        )

        assert result["validated"] is True
        assert result["removed_volume"] == pytest.approx(
            3.141592653589793 * 2.5**2 * 10.0,
            rel=1e-5,
        )

        state = await live_bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("Body")
shape = body.Tip.Shape
_result_ = {{
    "solid_count": len(shape.Solids),
    "shape_valid": bool(not shape.isNull() and shape.isValid()),
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result["shape_valid"] is True
        assert state.result["solid_count"] == 1
    finally:
        await _close_document(live_bridge, doc_name)
