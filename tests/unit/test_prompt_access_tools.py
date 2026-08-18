"""Tests for the prompt fallback exposed through the MCP tool surface."""

from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.tools.prompt_access import register_prompt_access_tools


class _RenderedPrompt:
    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {"mode": "json", "by_alias": True, "exclude_none": True}
        return {"description": "Rendered", "messages": [{"role": "user"}]}


class _PromptMcp:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.get_calls: list[tuple[str, dict[str, str]]] = []

    def tool(self) -> Any:
        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator

    async def list_prompts(self) -> list[Any]:
        return [
            SimpleNamespace(
                name="modify_existing_model",
                description="Modify a model",
                arguments=[
                    SimpleNamespace(
                        name="model_path",
                        description="Model path",
                        required=False,
                    )
                ],
            )
        ]

    async def get_prompt(self, name: str, arguments: dict[str, str]) -> _RenderedPrompt:
        self.get_calls.append((name, arguments))
        return _RenderedPrompt()


@pytest.mark.asyncio
async def test_get_freecad_prompt_lists_and_renders_native_prompts() -> None:
    mcp = _PromptMcp()
    register_prompt_access_tools(mcp)
    tool = mcp.tools["get_freecad_prompt"]

    catalog = await tool()
    rendered = await tool(
        "modify_existing_model",
        {"model_path": "part.FCStd"},
    )

    assert catalog["mode"] == "list"
    assert catalog["native_mcp_method"] == "prompts/list"
    assert catalog["prompts"][0]["name"] == "modify_existing_model"
    assert rendered == {
        "success": True,
        "mode": "render",
        "native_mcp_method": "prompts/get",
        "name": "modify_existing_model",
        "prompt": {
            "description": "Rendered",
            "messages": [{"role": "user"}],
        },
    }
    assert mcp.get_calls == [("modify_existing_model", {"model_path": "part.FCStd"})]


@pytest.mark.asyncio
async def test_get_freecad_prompt_rejects_unknown_name_with_catalog() -> None:
    mcp = _PromptMcp()
    register_prompt_access_tools(mcp)

    with pytest.raises(ValueError, match="available=.*modify_existing_model"):
        await mcp.tools["get_freecad_prompt"]("missing")
