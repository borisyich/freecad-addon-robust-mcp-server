"""Live regressions for read-only before/after Shape checkpoints."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.validation import register_validation_tools

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration


class _ToolCollector:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def validation_tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_validation_tools(collector, get_bridge)
    return collector.tools


def _assert_bbox(
    region: dict[str, Any],
    *,
    center_x: float,
    center_y: float,
    radius: float,
    height: float,
) -> None:
    bounds = region["bounding_box"]
    assert bounds["min"] == pytest.approx(
        [center_x - radius, center_y - radius, 0.0], abs=1e-7
    )
    assert bounds["max"] == pytest.approx(
        [center_x + radius, center_y + radius, height], abs=1e-7
    )


@pytest.mark.asyncio
async def test_checkpoint_localizes_two_filled_and_two_new_cylinders(
    live_bridge: XmlRpcBridge,
    validation_tools: dict[str, Any],
) -> None:
    """Symmetric Shape difference should preserve exact disconnected regions."""
    doc_name = "MCPShapeCheckpointRegression"
    radius = 2.0
    height = 10.0
    old_centers = [(8.0, 8.0), (25.0, 8.0)]
    new_centers = [(8.0, 22.0), (25.0, 22.0)]
    setup = await live_bridge.execute_python(
        f"""
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
box = Part.makeBox(40, 30, {height!r})
old_holes = [
    Part.makeCylinder({radius!r}, {height!r}, FreeCAD.Vector(x, y, 0))
    for x, y in {old_centers!r}
]
shape = box.cut(old_holes[0].fuse(old_holes[1]))
obj = doc.addObject("Part::Feature", "EditedSolid")
obj.Shape = shape
doc.recompute()
_result_ = {{"valid": shape.isValid(), "solid_count": len(shape.Solids)}}
"""
    )
    assert setup.success, setup.error_traceback
    assert setup.result == {"valid": True, "solid_count": 1}

    try:
        await validation_tools["capture_shape_checkpoint"](
            checkpoint_name="before_hole_relocation",
            object_name="EditedSolid",
            doc_name=doc_name,
        )
        mutation = await live_bridge.execute_python(
            f"""
import Part
doc = FreeCAD.getDocument({doc_name!r})
box = Part.makeBox(40, 30, {height!r})
new_holes = [
    Part.makeCylinder({radius!r}, {height!r}, FreeCAD.Vector(x, y, 0))
    for x, y in {new_centers!r}
]
obj = doc.getObject("EditedSolid")
obj.Shape = box.cut(new_holes[0].fuse(new_holes[1]))
doc.recompute()
_result_ = obj.Shape.isValid()
"""
        )
        assert mutation.success and mutation.result is True, mutation.error_traceback

        report = await validation_tools["compare_shape_checkpoint"](
            checkpoint_name="before_hole_relocation"
        )
        difference = report["difference"]
        expected_volume = math.pi * radius * radius * height

        assert difference["added_region_count"] == 2
        assert difference["removed_region_count"] == 2
        assert [item["volume"] for item in difference["added_regions"]] == (
            pytest.approx([expected_volume, expected_volume], rel=1e-7)
        )
        assert [item["volume"] for item in difference["removed_regions"]] == (
            pytest.approx([expected_volume, expected_volume], rel=1e-7)
        )

        added = sorted(
            difference["added_regions"],
            key=lambda item: item["bounding_box"]["min"][0],
        )
        removed = sorted(
            difference["removed_regions"],
            key=lambda item: item["bounding_box"]["min"][0],
        )
        for region, center in zip(added, old_centers, strict=True):
            _assert_bbox(
                region,
                center_x=center[0],
                center_y=center[1],
                radius=radius,
                height=height,
            )
        for region, center in zip(removed, new_centers, strict=True):
            _assert_bbox(
                region,
                center_x=center[0],
                center_y=center[1],
                radius=radius,
                height=height,
            )

        assert report["invariants"]["solid_count_unchanged"] is True
        assert report["invariants"]["bounding_box_unchanged"] is True
    finally:
        await live_bridge.execute_python(
            f"FreeCAD.closeDocument({doc_name!r}) if {doc_name!r} in FreeCAD.listDocuments() else None"
        )
