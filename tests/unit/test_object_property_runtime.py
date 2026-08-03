"""Tests for type-aware object-property assignment helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from freecad_mcp.bridge._object_property_runtime import (
    OBJECT_PROPERTY_COERCION_RUNTIME,
)
from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.bridge.embedded import EmbeddedBridge
from freecad_mcp.bridge.socket import SocketBridge
from freecad_mcp.bridge.xmlrpc import XmlRpcBridge


def test_object_property_runtime_resolves_links_and_sublinks() -> None:
    target = object()
    doc = SimpleNamespace(getObject=lambda name: target if name == "Pad" else None)

    namespace: dict[str, object] = {}
    exec(OBJECT_PROPERTY_COERCION_RUNTIME, namespace)
    coerce = namespace["_coerce_object_property_value"]

    link_obj = SimpleNamespace(
        getTypeIdOfProperty=lambda _name: "App::PropertyLink"
    )
    sublink_obj = SimpleNamespace(
        getTypeIdOfProperty=lambda _name: "App::PropertyLinkSub"
    )
    string_obj = SimpleNamespace(
        getTypeIdOfProperty=lambda _name: "App::PropertyString"
    )

    assert coerce(doc, link_obj, "Tip", "Pad") is target
    assert coerce(doc, sublink_obj, "Support", "Pad.Face2") == (
        target,
        ["Face2"],
    )
    assert coerce(doc, string_obj, "Label", "Pad") == "Pad"


def test_hole_thread_profile_change_requires_size_and_applies_it_after_type() -> None:
    """edit_object must prevent FreeCAD from silently resetting ThreadSize."""
    namespace: dict[str, object] = {}
    exec(OBJECT_PROPERTY_COERCION_RUNTIME, namespace)
    set_properties = namespace["_set_object_properties"]

    class Hole:
        TypeId = "PartDesign::Hole"
        Name = "Hole"

        def __init__(self) -> None:
            self._thread_type = "ISOMetricProfile"
            self.ThreadSize = "M12"

        @property
        def ThreadType(self):
            return self._thread_type

        @ThreadType.setter
        def ThreadType(self, value):
            self._thread_type = value
            self.ThreadSize = "M1x0.2" if "Fine" in value else "M1"

        @staticmethod
        def getTypeIdOfProperty(_name):
            return "App::PropertyEnumeration"

        def getEnumerationsOfProperty(self, _name):
            if "Fine" in self.ThreadType:
                return ["M1x0.2", "M12x1.0", "M12x1.25", "M12x1.5"]
            return ["M1", "M12"]

    hole = Hole()
    with pytest.raises(ValueError, match="requires ThreadSize"):
        set_properties(None, hole, {"ThreadType": "ISO_FINE"})
    assert hole.ThreadType == "ISOMetricProfile"
    assert hole.ThreadSize == "M12"

    set_properties(
        None,
        hole,
        {"ThreadSize": "M12x1.25", "ThreadType": "ISO_FINE"},
    )
    assert hole.ThreadType == "ISOMetricFineProfile"
    assert hole.ThreadSize == "M12x1.25"


@pytest.mark.asyncio
@pytest.mark.parametrize("bridge_class", [EmbeddedBridge, XmlRpcBridge, SocketBridge])
async def test_edit_object_embeds_type_aware_link_conversion(bridge_class) -> None:
    bridge = bridge_class()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={
                "name": "Body",
                "label": "Body",
                "type_id": "PartDesign::Body",
                "visibility": True,
                "children": [],
                "parents": [],
            },
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    await bridge.edit_object("Body", {"Tip": "Pad"})
    code = bridge.execute_python.await_args.args[0]
    assert "_coerce_object_property_value" in code
    assert "getTypeIdOfProperty" in code
    assert "Property {property_name!r} not found" in code
    assert "_set_object_properties" in code
