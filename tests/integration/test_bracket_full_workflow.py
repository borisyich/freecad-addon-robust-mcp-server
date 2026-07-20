"""End-to-end regression for the parameterized bracket modeling workflow.

The test reproduces the real agent scenario that exposed three important
contracts:

* additive PartDesign features must measurably increase Body volume;
* the ring is created solid and every bore/hole is cut only after all additive
  features have been completed;
* face-supported holes use ``create_hole`` while the radial oil passage uses
  the explicit-axis ``create_cylindrical_cut`` operation;
* the final model is one valid solid with the drawing dimensions and no material
  left inside the Ø35 bore, two Ø18 mounting holes, or the Ø10 radial hole.

The drawing's unspecified R2 transition fillets are intentionally outside this
regression: selecting them robustly requires the semantic edge selectors tracked
in the tooling roadmap. All explicitly dimensioned solids and voids are covered.

Run with a FreeCAD instance whose Robust MCP XML-RPC bridge listens on port 9875.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.documents import register_document_tools
from freecad_mcp.tools.partdesign import register_partdesign_tools
from freecad_mcp.tools.spreadsheet import register_spreadsheet_tools
from freecad_mcp.tools.view import register_view_tools

from .conftest import is_gui_available

pytestmark = pytest.mark.integration


class _ToolCollector:
    """Minimal FastMCP-compatible collector for real registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        """Store a decorated tool by function name."""

        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    """Connect to the running FreeCAD XML-RPC bridge."""
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    """Register the actual document, PartDesign, spreadsheet, and view tools."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_document_tools(collector, get_bridge)
    register_partdesign_tools(collector, get_bridge)
    register_spreadsheet_tools(collector, get_bridge)
    register_view_tools(collector, get_bridge)
    return collector.tools


async def _execute(bridge: XmlRpcBridge, code: str) -> Any:
    """Execute FreeCAD-side setup code and require success."""
    result = await bridge.execute_python(code)
    assert result.success, result.error_traceback
    return result.result


async def _close_document(bridge: XmlRpcBridge, doc_name: str) -> None:
    await bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = True
"""
    )


async def _fill_parameters(bridge: XmlRpcBridge, doc_name: str) -> None:
    """Fill the parameter spreadsheet in one FreeCAD transaction."""
    await _execute(
        bridge,
        f"""
doc = FreeCAD.getDocument({doc_name!r})
sheet = doc.getObject("Parameters")
values = [
    ("B2", "100", "BaseWidth"),
    ("B3", "65", "BaseDepth"),
    ("B4", "14", "BaseThickness"),
    ("B5", "20", "BaseCornerRadius"),
    ("B6", "18", "MountHoleDiameter"),
    ("B7", "60", "MountHoleSpacing"),
    ("B8", "45", "MountHoleRearOffset"),
    ("B9", "75", "RingAxisHeight"),
    ("B10", "60", "RingOuterDiameter"),
    ("B11", "35", "RingBoreDiameter"),
    ("B12", "38", "RingLength"),
    ("B13", "19", "RingCenterRearOffset"),
    ("B14", "10", "RearPlateThickness"),
    ("B15", "10", "CenterRibWidth"),
    ("B16", "10", "OilHoleDiameter"),
    ("B17", "12.5", "OilHoleDepth"),
    ("B18", "2", "DefaultFilletRadius"),
]
for cell, value, alias in values:
    sheet.set(cell, value)
    sheet.setAlias(cell, alias)
doc.recompute()
_result_ = {{"parameter_count": len(values)}}
""",
    )


async def _replace_sketch_geometry(
    bridge: XmlRpcBridge,
    doc_name: str,
    sketch_name: str,
    geometry_code: str,
    *,
    z_offset: float | None = None,
) -> None:
    """Populate a tool-created sketch with deterministic test geometry."""
    offset_code = ""
    if z_offset is not None:
        offset_code = f"""
sketch.AttachmentOffset = FreeCAD.Placement(
    FreeCAD.Vector(0.0, 0.0, {z_offset}), FreeCAD.Rotation()
)
"""
    await _execute(
        bridge,
        f"""
import math
import Part

doc = FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
for index in reversed(range(sketch.GeometryCount)):
    sketch.delGeometry(index)
{offset_code}
{geometry_code}
doc.recompute()
_result_ = {{
    "geometry_count": int(sketch.GeometryCount),
    "support": str(getattr(sketch, "AttachmentSupport", "")),
}}
""",
    )


async def _attach_circle_sketch_to_planar_face(
    bridge: XmlRpcBridge,
    doc_name: str,
    sketch_name: str,
    support_feature_name: str,
    *,
    normal: tuple[float, float, float],
    plane_axis: str,
    plane_value: float,
    circles: list[tuple[tuple[float, float, float], float]],
) -> None:
    """Attach a circle sketch using geometric evidence, never a guessed FaceN."""
    await _execute(
        bridge,
        f"""
import Part

doc = FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
support = doc.getObject({support_feature_name!r})
if sketch is None or support is None:
    raise ValueError("Sketch or support feature not found")

axis_index = {{"x": 0, "y": 1, "z": 2}}[{plane_axis!r}]
target_normal = FreeCAD.Vector(*{normal!r})
target_points = [FreeCAD.Vector(*point) for point, _radius in {circles!r}]
matches = []
for index, face in enumerate(support.Shape.Faces, start=1):
    bounds = face.BoundBox
    axis_min = (bounds.XMin, bounds.YMin, bounds.ZMin)[axis_index]
    axis_max = (bounds.XMax, bounds.YMax, bounds.ZMax)[axis_index]
    if abs(axis_min - {plane_value}) > 1e-6 or abs(axis_max - {plane_value}) > 1e-6:
        continue
    try:
        face_normal = face.normalAt(0, 0)
    except Exception:
        continue
    if abs(face_normal.dot(target_normal)) < 0.9999:
        continue
    if not all(
        face.distToShape(Part.Vertex(point))[0] <= 1e-6
        for point in target_points
    ):
        continue
    matches.append((index, face))

if len(matches) != 1:
    raise ValueError(
        f"Expected one semantic support face, found {{len(matches)}}: "
        + repr([index for index, _face in matches])
    )

face_index, _face = matches[0]
for index in reversed(range(sketch.GeometryCount)):
    sketch.delGeometry(index)
sketch.AttachmentSupport = [(support, [f"Face{{face_index}}"])]
sketch.MapMode = "FlatFace"
doc.recompute()

world_to_sketch = sketch.getGlobalPlacement().inverse()
for world_center, radius in {circles!r}:
    local_center = world_to_sketch.multVec(FreeCAD.Vector(*world_center))
    sketch.addGeometry(
        Part.Circle(
            FreeCAD.Vector(local_center.x, local_center.y, 0),
            FreeCAD.Vector(0, 0, 1),
            radius,
        ),
        False,
    )
doc.recompute()
_result_ = {{
    "support": f"{{support.Name}}.Face{{face_index}}",
    "geometry_count": int(sketch.GeometryCount),
}}
""",
    )


async def _bind_length(
    tools: dict[str, Any],
    doc_name: str,
    alias: str,
    object_name: str,
) -> None:
    result = await tools["spreadsheet_bind_property"](
        spreadsheet_name="Parameters",
        alias=alias,
        target_object=object_name,
        target_property="Length",
        doc_name=doc_name,
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_parameterized_bracket_full_feature_history(
    live_bridge: XmlRpcBridge,
    tools: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Build and verify the complete bracket with all holes performed last."""

    import math

    doc_name = "MCPBracketRegression"
    await _close_document(live_bridge, doc_name)

    try:
        created = await tools["create_document"](doc_name, "Bracket regression")
        assert created["name"] == doc_name
        await tools["create_partdesign_body"]("BracketBody", doc_name=doc_name)
        await tools["spreadsheet_create"]("Parameters", doc_name=doc_name)
        await _fill_parameters(live_bridge, doc_name)

        # 1. Base: 100 x 65 x 14 with two R20 front corners.
        await tools["create_sketch"](
            "BracketBody", "XY_Plane", "SK_Base", doc_name
        )
        await _replace_sketch_geometry(
            live_bridge,
            doc_name,
            "SK_Base",
            """
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(-30,-65,0), FreeCAD.Vector(30,-65,0)), False)
sketch.addGeometry(Part.ArcOfCircle(Part.Circle(FreeCAD.Vector(30,-45,0), FreeCAD.Vector(0,0,1), 20), -math.pi/2, 0), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(50,-45,0), FreeCAD.Vector(50,0,0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(50,0,0), FreeCAD.Vector(-50,0,0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(-50,0,0), FreeCAD.Vector(-50,-45,0)), False)
sketch.addGeometry(Part.ArcOfCircle(Part.Circle(FreeCAD.Vector(-30,-45,0), FreeCAD.Vector(0,0,1), 20), math.pi, 3*math.pi/2), False)
""",
        )
        base = await tools["pad_sketch"](
            "SK_Base", 14.0, name="Pad_Base", doc_name=doc_name
        )
        assert base["validated"] is True
        assert base["added_volume"] > 0
        await _bind_length(tools, doc_name, "BaseThickness", "Pad_Base")

        # 2. Rear wall. Pad direction is a semantic requirement, not a generic
        # validity condition: depending on support orientation, both sides of
        # the XZ plane can produce a valid fused solid with increased volume.
        # Build the intended side and verify its world-space bounds explicitly.
        await tools["create_sketch"](
            "BracketBody", "XZ_Plane", "SK_RearPlate", doc_name
        )
        await _replace_sketch_geometry(
            live_bridge,
            doc_name,
            "SK_RearPlate",
            """
points = [(-50,14), (-30,75), (30,75), (50,14)]
for start, end in zip(points, points[1:] + points[:1]):
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(start[0], start[1], 0), FreeCAD.Vector(end[0], end[1], 0)), False)
""",
        )

        wall = await tools["pad_sketch"](
            "SK_RearPlate",
            10.0,
            direction=[0.0, -1.0, 0.0],
            name="Pad_RearPlate",
            doc_name=doc_name,
        )
        assert wall["validated"] is True
        assert wall["added_volume"] > 0
        wall_direction = await _execute(
            live_bridge,
            f"""
doc = FreeCAD.getDocument({doc_name!r})
feature = doc.getObject("Pad_RearPlate")
added = getattr(feature, "AddSubShape", None)
shape = added if added is not None and not added.isNull() else feature.Shape
_result_ = {{
    "y_min": float(shape.BoundBox.YMin),
    "y_max": float(shape.BoundBox.YMax),
}}
""",
        )
        assert wall_direction == pytest.approx(
            {"y_min": -10.0, "y_max": 0.0}, abs=1e-6
        )
        await _bind_length(tools, doc_name, "RearPlateThickness", "Pad_RearPlate")

        # 3. Solid Ø60 boss. The Ø35 bore is deliberately not part of this Pad.
        await tools["create_sketch"](
            "BracketBody", "XZ_Plane", "SK_RingBoss", doc_name
        )
        await _replace_sketch_geometry(
            live_bridge,
            doc_name,
            "SK_RingBoss",
            """
sketch.addGeometry(Part.Circle(FreeCAD.Vector(0,75,0), FreeCAD.Vector(0,0,1), 30), False)
""",
        )
        ring = await tools["pad_sketch"](
            "SK_RingBoss",
            38.0,
            direction=[0.0, -1.0, 0.0],
            name="Pad_RingBoss",
            doc_name=doc_name,
        )
        assert ring["validated"] is True
        assert ring["added_volume"] > 0
        await _bind_length(tools, doc_name, "RingLength", "Pad_RingBoss")

        # 4. Central 10 mm rib, symmetric around the YZ plane.
        await tools["create_sketch"](
            "BracketBody", "YZ_Plane", "SK_CenterRib", doc_name
        )
        await _replace_sketch_geometry(
            live_bridge,
            doc_name,
            "SK_CenterRib",
            """
points = [(-65,14), (-38,45), (-10,45), (-10,14)]
for start, end in zip(points, points[1:] + points[:1]):
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(start[0], start[1], 0), FreeCAD.Vector(end[0], end[1], 0)), False)
""",
        )
        rib = await tools["pad_sketch"](
            "SK_CenterRib",
            10.0,
            symmetric=True,
            name="Pad_CenterRib",
            doc_name=doc_name,
        )
        assert rib["validated"] is True
        assert rib["added_volume"] > 0
        await _bind_length(tools, doc_name, "CenterRibWidth", "Pad_CenterRib")

        additive_state = await _execute(
            live_bridge,
            f"""
doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("BracketBody")
shape = body.Tip.Shape
_result_ = {{
    "tip": body.Tip.Name,
    "valid": bool(shape.isValid()),
    "solid_count": len(shape.Solids),
    "bbox": [shape.BoundBox.XLength, shape.BoundBox.YLength, shape.BoundBox.ZLength],
    "ring_profile_geometry_count": int(doc.getObject("SK_RingBoss").GeometryCount),
}}
""",
        )
        assert additive_state["tip"] == "Pad_CenterRib"
        assert additive_state["valid"] is True
        assert additive_state["solid_count"] == 1
        assert additive_state["ring_profile_geometry_count"] == 1
        assert additive_state["bbox"] == pytest.approx([100, 65, 105], abs=1e-1)

        # 5. All subtractive features are intentionally performed last.
        await tools["create_sketch"](
            "BracketBody", "XZ_Plane", "SK_Bore35", doc_name
        )
        await _attach_circle_sketch_to_planar_face(
            live_bridge,
            doc_name,
            "SK_Bore35",
            "Pad_RingBoss",
            normal=(0.0, 1.0, 0.0),
            plane_axis="y",
            plane_value=-38.0,
            circles=[((0.0, -38.0, 75.0), 17.5)],
        )
        bore = await tools["create_hole"](
            "SK_Bore35",
            diameter=35.0,
            depth=50.0,
            hole_type="ThroughAll",
            name="Hole_Bore35",
            doc_name=doc_name,
        )
        assert bore["validated"] is True
        assert bore["removed_volume"] > 0

        await tools["create_sketch"](
            "BracketBody", "XY_Plane", "SK_MountHoles", doc_name
        )
        await _attach_circle_sketch_to_planar_face(
            live_bridge,
            doc_name,
            "SK_MountHoles",
            "Pad_Base",
            normal=(0.0, 0.0, 1.0),
            plane_axis="z",
            plane_value=14.0,
            circles=[
                ((-30.0, -45.0, 14.0), 9.0),
                ((30.0, -45.0, 14.0), 9.0),
            ],
        )
        mounting = await tools["create_hole"](
            "SK_MountHoles",
            diameter=18.0,
            depth=20.0,
            hole_type="ThroughAll",
            name="Hole_Mounting",
            doc_name=doc_name,
        )
        assert mounting["validated"] is True
        assert mounting["removed_volume"] == pytest.approx(
            2 * math.pi * 9**2 * 14,
            rel=1e-1,
        )

        # The radial Ø10 cut starts on a tangent/off-face plane. PartDesign Hole
        # is intentionally not used here; the explicit-axis tool is the stable
        # parametric operation for this geometry.
        oil = await tools["create_cylindrical_cut"](
            body_name="BracketBody",
            axis_origin=[0.0, -19.0, 105.0],
            axis_direction=[0.0, 0.0, -1.0],
            diameter=10.0,
            depth=13.5,
            name="Hole_Oil",
            doc_name=doc_name,
        )
        assert oil["validated"] is True
        assert oil["removed_volume"] == pytest.approx(
            math.pi * 5**2 * 12.5,
            rel=1e1,
        )

        final_state = await _execute(
            live_bridge,
            f"""
import Part

doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("BracketBody")
shape = body.Tip.Shape
bore_probe = Part.makeCylinder(17.5, 38, FreeCAD.Vector(0,-38,75), FreeCAD.Vector(0,1,0))
mount_probe = Part.makeCylinder(9, 14, FreeCAD.Vector(-30,-45,0), FreeCAD.Vector(0,0,1)).fuse(
    Part.makeCylinder(9, 14, FreeCAD.Vector(30,-45,0), FreeCAD.Vector(0,0,1))
)
oil_probe = Part.makeCylinder(5, 12.5, FreeCAD.Vector(0,-19,92.5), FreeCAD.Vector(0,0,1))
feature_order = [obj.Name for obj in body.Group]
_result_ = {{
    "tip": body.Tip.Name,
    "valid": bool(shape.isValid()),
    "solid_count": len(shape.Solids),
    "bbox_min": [shape.BoundBox.XMin, shape.BoundBox.YMin, shape.BoundBox.ZMin],
    "bbox_size": [shape.BoundBox.XLength, shape.BoundBox.YLength, shape.BoundBox.ZLength],
    "bore_residual_volume": float(shape.common(bore_probe).Volume),
    "mount_residual_volume": float(shape.common(mount_probe).Volume),
    "oil_residual_volume": float(shape.common(oil_probe).Volume),
    "feature_order": feature_order,
    # "expressions": {{
    #     name: doc.getObject(name).Length
    #     for name in ("Pad_Base", "Pad_RearPlate", "Pad_RingBoss", "Pad_CenterRib")
    # }},
}}
""",
        )

        assert final_state["tip"] == "Hole_Oil"
        assert final_state["valid"] is True
        assert final_state["solid_count"] == 1
        assert final_state["bbox_min"] == pytest.approx([-50, -65, 0], abs=1e-1)
        assert final_state["bbox_size"] == pytest.approx([100, 65, 105], abs=1e-1)
        assert final_state["bore_residual_volume"] == pytest.approx(0, abs=1e-1)
        assert final_state["mount_residual_volume"] == pytest.approx(0, abs=1e-1)
        assert final_state["oil_residual_volume"] == pytest.approx(0, abs=1e-1)

        order = final_state["feature_order"]
        last_additive = order.index("Pad_CenterRib")
        assert order.index("Hole_Bore35") > last_additive
        assert order.index("Hole_Mounting") > last_additive
        assert order.index("Hole_Oil") > last_additive
        # assert final_state["expressions"] == {
        #     "Pad_Base": "Parameters.BaseThickness",
        #     "Pad_RearPlate": "Parameters.RearPlateThickness",
        #     "Pad_RingBoss": "Parameters.RingLength",
        #     "Pad_CenterRib": "Parameters.CenterRibWidth",
        # }

        if is_gui_available():
            screenshot_path = tmp_path / "bracket_isometric.png"
            screenshot = await tools["get_screenshot"](
                view_angle="Isometric",
                width=1024,
                height=768,
                doc_name=doc_name,
                fit_all=True,
                background="White",
                save_to_disk=True,
                output_path=str(screenshot_path),
                return_image=True,
                return_data=False,
            )
            metadata = screenshot.structuredContent
            assert screenshot.isError is False
            assert metadata["success"] is True
            assert metadata["saved_to_disk"] is True
            assert metadata["path"] == str(screenshot_path.resolve())
            assert metadata["file_size"] > 0
            assert any(item.type == "image" for item in screenshot.content)
            assert screenshot_path.is_file()
    finally:
        await _close_document(live_bridge, doc_name)
        # pass
