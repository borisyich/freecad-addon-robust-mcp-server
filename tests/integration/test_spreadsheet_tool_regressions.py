"""Live regressions for Spreadsheet aliases, angle bindings, and cell clearing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.partdesign import register_partdesign_tools
from freecad_mcp.tools.spreadsheet import register_spreadsheet_tools

pytestmark = pytest.mark.integration


class _ToolCollector:
    """Minimal FastMCP-compatible tool collector."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        """Return a decorator that records a tool by name."""

        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    """Connect to the running FreeCAD GUI bridge."""
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def spreadsheet_tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    """Return the real registered Spreadsheet tools."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_spreadsheet_tools(collector, get_bridge)
    return collector.tools


@pytest.fixture
def partdesign_tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    """Return the real registered PartDesign tools."""
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_partdesign_tools(collector, get_bridge)
    return collector.tools


@pytest.mark.asyncio
async def test_numeric_360_alias_retry_discovery_and_clear(
    live_bridge: XmlRpcBridge,
    spreadsheet_tools: dict[str, Any],
) -> None:
    """A unitless 360 should drive an angle and alias operations should retry."""
    doc_name = "MCPSpreadsheetAngleRegression"
    setup = await live_bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
pattern = doc.addObject("App::FeaturePython", "Pattern")
pattern.addProperty("App::PropertyAngle", "Angle")
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    batch_args = {
        "spreadsheet_name": "Parameters",
        "cells": [{"cell": "A1", "value": 360}],
        "aliases": [{"cell": "A1", "alias": "PatternAngle"}],
        "bindings": [
            {
                "alias": "PatternAngle",
                "target_object": "Pattern",
                "target_property": "Angle",
            }
        ],
        "doc_name": doc_name,
    }
    try:
        first = await spreadsheet_tools["spreadsheet_apply_batch"](**batch_args)
        second = await spreadsheet_tools["spreadsheet_apply_batch"](**batch_args)
        assert first["bindings"][0]["unit_coercion"] == "deg"
        assert second["bindings"][0]["unit_coercion"] == "deg"

        aliases = await spreadsheet_tools["spreadsheet_get_aliases"](
            "Parameters", doc_name=doc_name
        )
        assert aliases["aliases"] == {"PatternAngle": "A1"}

        state = await live_bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
pattern = doc.getObject("Pattern")
_result_ = {{
    "angle": float(pattern.Angle.Value),
    "expression": dict(pattern.ExpressionEngine).get("Angle"),
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result == {
            "angle": 360.0,
            "expression": "Parameters.PatternAngle * 1 deg",
        }

        unitful_args = dict(batch_args)
        unitful_args["cells"] = [{"cell": "A1", "value": "360 deg"}]
        unitful = await spreadsheet_tools["spreadsheet_apply_batch"](**unitful_args)
        assert unitful["bindings"][0]["source_unit"] == "Angle"
        assert unitful["bindings"][0]["unit_coercion"] is None

        unitful_state = await live_bridge.execute_python(
            f"""
pattern = FreeCAD.getDocument({doc_name!r}).getObject("Pattern")
_result_ = {{
    "angle": float(pattern.Angle.Value),
    "expression": dict(pattern.ExpressionEngine).get("Angle"),
}}
"""
        )
        assert unitful_state.success, unitful_state.error_traceback
        assert unitful_state.result == {
            "angle": 360.0,
            "expression": "Parameters.PatternAngle",
        }

        with pytest.raises(ValueError, match="clear_bindings=True"):
            await spreadsheet_tools["spreadsheet_clear_cell"](
                "Parameters", "A1", doc_name=doc_name
            )

        preserved = await live_bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
sheet = doc.getObject("Parameters")
pattern = doc.getObject("Pattern")
_result_ = {{
    "content": sheet.getContents("A1"),
    "alias": sheet.getAlias("A1"),
    "expression": dict(pattern.ExpressionEngine).get("Angle"),
}}
"""
        )
        assert preserved.success, preserved.error_traceback
        assert preserved.result["alias"] == "PatternAngle"
        assert preserved.result["expression"] == "Parameters.PatternAngle"

        cleared = await spreadsheet_tools["spreadsheet_clear_cell"](
            "Parameters",
            "A1",
            clear_bindings=True,
            doc_name=doc_name,
        )
        assert cleared["removed_alias"] == "PatternAngle"
        assert cleared["had_content"] is True
        assert cleared["cleared_bindings"] == [
            {
                "object": "Pattern",
                "property": "Angle",
                "expression": "Parameters.PatternAngle",
            }
        ]

        detached = await live_bridge.execute_python(
            f"""
pattern = FreeCAD.getDocument({doc_name!r}).getObject("Pattern")
_result_ = dict(pattern.ExpressionEngine).get("Angle")
"""
        )
        assert detached.success, detached.error_traceback
        assert detached.result is None

        cleared_again = await spreadsheet_tools["spreadsheet_clear_cell"](
            "Parameters", "A1", doc_name=doc_name
        )
        assert cleared_again["removed_alias"] is None
        assert cleared_again["had_content"] is False
        aliases_after = await spreadsheet_tools["spreadsheet_get_aliases"](
            "Parameters", doc_name=doc_name
        )
        assert aliases_after["aliases"] == {}
    finally:
        await live_bridge.execute_python(
            f"FreeCAD.closeDocument({doc_name!r}) if {doc_name!r} in FreeCAD.listDocuments() else None"
        )


@pytest.mark.asyncio
async def test_edit_object_switches_hole_profile_and_size_together(
    live_bridge: XmlRpcBridge,
    partdesign_tools: dict[str, Any],
) -> None:
    """The generic bridge edit should not leave FreeCAD's reset M1x0.2 size."""
    doc_name = "MCPHoleEditFineRegression"
    setup = await live_bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
import Part
import Sketcher

doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
base = body.newObject("PartDesign::Feature", "BaseSolid")
base.Shape = Part.makeBox(
    40.0,
    40.0,
    12.0,
    FreeCAD.Vector(-20.0, -20.0, 0.0),
)
body.Tip = base

sketch = body.newObject("Sketcher::SketchObject", "HoleSketch")
top_face_index = max(
    range(1, len(base.Shape.Faces) + 1),
    key=lambda index: base.Shape.Faces[index - 1].CenterOfMass.z,
)
top_face = f"Face{{top_face_index}}"
if hasattr(sketch, "AttachmentSupport"):
    sketch.AttachmentSupport = [(base, [top_face])]
else:
    sketch.Support = (base, [top_face])
sketch.MapMode = "FlatFace"
sketch.addGeometry(
    Part.Circle(
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(0.0, 0.0, 1.0),
        6.0,
    ),
    False,
)
doc.recompute()
_result_ = {{
    "base_volume": float(base.Shape.Volume),
    "sketch_geometry_count": int(sketch.GeometryCount),
}}
"""
    )
    assert setup.success, setup.error_traceback

    try:
        created = await partdesign_tools["create_hole"](
            sketch_name="HoleSketch",
            diameter=12.0,
            depth=12.0,
            hole_type="ThroughAll",
            threaded=True,
            thread_type="ISO",
            thread_size="M12",
            name="Hole",
            doc_name=doc_name,
        )
        assert created["validated"] is True
        assert created["removed_volume"] > 0.0

        with pytest.raises(ValueError, match="requires ThreadSize"):
            await live_bridge.edit_object("Hole", {"ThreadType": "ISO_FINE"}, doc_name)

        await live_bridge.edit_object(
            "Hole",
            {"ThreadType": "ISO_FINE", "ThreadSize": "M12x1.25"},
            doc_name,
        )
        state = await live_bridge.execute_python(
            f"""
hole = FreeCAD.getDocument({doc_name!r}).getObject("Hole")
_result_ = {{
    "thread_type": str(hole.ThreadType),
    "thread_size": str(hole.ThreadSize),
    "shape_valid": bool(not hole.Shape.isNull() and hole.Shape.isValid()),
    "solid_count": len(hole.Shape.Solids),
    "tip": getattr(FreeCAD.getDocument({doc_name!r}).getObject("Body").Tip, "Name", None),
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result == {
            "thread_type": "ISOMetricFineProfile",
            "thread_size": "M12x1.25",
            "shape_valid": True,
            "solid_count": 1,
            "tip": "Hole",
        }
    finally:
        await live_bridge.execute_python(
            f"FreeCAD.closeDocument({doc_name!r}) if {doc_name!r} in FreeCAD.listDocuments() else None"
        )


@pytest.mark.asyncio
async def test_failed_batch_restores_cell_alias_and_expression(
    live_bridge: XmlRpcBridge,
    spreadsheet_tools: dict[str, Any],
) -> None:
    """A late setExpression failure must restore all earlier mutations."""
    doc_name = "MCPSpreadsheetRollbackRegression"
    setup = await live_bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
sheet.set("A1", "10")
sheet.setAlias("A1", "Original")
target = doc.addObject("PartDesign::Feature", "Target")
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    try:
        with pytest.raises(ValueError, match="Property 'TypeId' not found"):
            await spreadsheet_tools["spreadsheet_apply_batch"](
                spreadsheet_name="Parameters",
                cells=[{"cell": "A1", "value": 20}],
                aliases=[{"cell": "A1", "alias": "Changed"}],
                bindings=[
                    {
                        "alias": "Changed",
                        "target_object": "Target",
                        "target_property": "TypeId",
                    }
                ],
                doc_name=doc_name,
            )

        state = await live_bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
sheet = doc.getObject("Parameters")
target = doc.getObject("Target")
_result_ = {{
    "content": sheet.getContents("A1"),
    "computed": sheet.get("A1"),
    "alias": sheet.getAlias("A1"),
    "expressions": list(target.ExpressionEngine),
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result == {
            "content": "10",
            "computed": 10,
            "alias": "Original",
            "expressions": [],
        }
    finally:
        await live_bridge.execute_python(
            f"FreeCAD.closeDocument({doc_name!r}) if {doc_name!r} in FreeCAD.listDocuments() else None"
        )


@pytest.mark.asyncio
async def test_formula_error_is_not_success_and_restores_previous_cell(
    live_bridge: XmlRpcBridge,
    spreadsheet_tools: dict[str, Any],
) -> None:
    """FreeCAD's textual ERR result must fail inside the batch transaction."""
    doc_name = "MCPSpreadsheetFormulaErrorRegression"
    setup = await live_bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
sheet.set("A1", "10")
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    try:
        with pytest.raises(ValueError, match="Spreadsheet formula failed in A1"):
            await spreadsheet_tools["spreadsheet_apply_batch"](
                spreadsheet_name="Parameters",
                cells=[{"cell": "A1", "value": "=MissingObject.MissingProperty"}],
                doc_name=doc_name,
            )

        state = await live_bridge.execute_python(
            f"""
sheet = FreeCAD.getDocument({doc_name!r}).getObject("Parameters")
_result_ = {{"content": sheet.getContents("A1"), "computed": sheet.get("A1")}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result == {"content": "10", "computed": 10}
    finally:
        await live_bridge.execute_python(
            f"FreeCAD.closeDocument({doc_name!r}) if {doc_name!r} in FreeCAD.listDocuments() else None"
        )
