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
        getTypeIdOfProperty=lambda name: "App::PropertyLink"
    )
    sublink_obj = SimpleNamespace(
        getTypeIdOfProperty=lambda name: "App::PropertyLinkSub"
    )
    string_obj = SimpleNamespace(
        getTypeIdOfProperty=lambda name: "App::PropertyString"
    )

    assert coerce(doc, link_obj, "Tip", "Pad") is target
    assert coerce(doc, sublink_obj, "Support", "Pad.Face2") == (
        target,
        ["Face2"],
    )
    assert coerce(doc, string_obj, "Label", "Pad") == "Pad"


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
    assert "Property {prop_name!r} not found" in code
