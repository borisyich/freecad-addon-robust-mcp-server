"""Live regressions for Spreadsheet aliases, angle bindings, and cell clearing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
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
body = doc.addObject("PartDesign::Body", "Body")
pattern = body.newObject("PartDesign::PolarPattern", "Pattern")
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

        cleared = await spreadsheet_tools["spreadsheet_clear_cell"](
            "Parameters", "A1", doc_name=doc_name
        )
        assert cleared["removed_alias"] == "PatternAngle"
        assert cleared["had_content"] is True
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
) -> None:
    """The generic bridge edit should not leave FreeCAD's reset M1x0.2 size."""
    doc_name = "MCPHoleEditFineRegression"
    setup = await live_bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
hole = body.newObject("PartDesign::Hole", "Hole")
hole.ThreadType = "ISOMetricProfile"
hole.ThreadSize = "M12"
_result_ = True
"""
    )
    assert setup.success, setup.error_traceback

    try:
        with pytest.raises(ValueError, match="requires ThreadSize"):
            await live_bridge.edit_object(
                "Hole", {"ThreadType": "ISO_FINE"}, doc_name
            )

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
}}
"""
        )
        assert state.success, state.error_traceback
        assert state.result == {
            "thread_type": "ISOMetricFineProfile",
            "thread_size": "M12x1.25",
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
