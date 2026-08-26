"""Tests for compact FreeCAD MCP prompt routers."""

import inspect
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestFreecadPrompts:
    @pytest.fixture
    def mock_mcp(self) -> MagicMock:
        mcp = MagicMock()
        mcp._registered_prompts = {}

        def prompt_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
                mcp._registered_prompts[func.__name__] = func
                return func

            return wrapper

        mcp.prompt = prompt_decorator
        return mcp

    @pytest.fixture
    def register_prompts(self, mock_mcp: MagicMock) -> dict[str, Callable[..., Any]]:
        from freecad_mcp.prompts.freecad import register_prompts

        async def get_bridge() -> AsyncMock:
            return AsyncMock()

        register_prompts(mock_mcp, get_bridge)
        return mock_mcp._registered_prompts

    def test_all_compatibility_prompt_names_are_registered(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        assert set(register_prompts) == {
            "freecad_startup",
            "reproduce_from_drawing",
            "modify_existing_model",
            "freecad_guidance",
            "design_part",
            "create_sketch_guide",
            "boolean_operations_guide",
            "export_guide",
            "import_guide",
            "analyze_shape",
            "debug_model",
            "macro_development",
            "python_api_reference",
            "troubleshooting",
        }

    @pytest.mark.asyncio
    async def test_startup_is_minimal_skill_router(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        result = await register_prompts["freecad_startup"]()
        assert "freecad://skills/freecad-engineering" in result
        assert "ACT → OBSERVE → REACT" in result
        assert "validate_parametric_model" in result
        assert len(result.encode("utf-8")) < 1_000

    @pytest.mark.asyncio
    async def test_drawing_prompt_routes_to_new_reference(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        result = await register_prompts["reproduce_from_drawing"](
            reference_path="drawing.png", target_document="Part"
        )
        assert "drawing.png" in result
        assert "model-from-drawing.md" in result
        assert "manufacturing reference" in result

    @pytest.mark.asyncio
    async def test_modification_prompt_routes_by_history(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        result = await register_prompts["modify_existing_model"](
            model_path="part.step", change_request="move wall"
        )
        assert "edit-with-history.md" in result
        assert "edit-without-history.md" in result
        assert "part.step" in result

    @pytest.mark.asyncio
    async def test_guidance_routes_task_categories(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        guidance = register_prompts["freecad_guidance"]
        assert "model-from-text.md" in await guidance("text_modeling")
        assert "sheet-metal-parts.md" in await guidance("sheet_metal")
        assert "edit-without-history.md" in await guidance("edit_without_history")
        assert await guidance("unknown") == await guidance("general")

    @pytest.mark.asyncio
    async def test_create_sketch_guide_keeps_typed_origin_support(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        prompt = register_prompts["create_sketch_guide"]
        parameters = inspect.signature(prompt).parameters
        assert "plane" not in parameters
        assert "origin_plane" in parameters
        result = await prompt(origin_plane="XZ_Plane")
        assert '"kind": "origin_plane"' in result
        assert '"plane": "XZ_Plane"' in result

    @pytest.mark.asyncio
    async def test_legacy_guides_are_compact_operation_pointers(
        self, register_prompts: dict[str, Callable[..., Any]]
    ) -> None:
        boolean = await register_prompts["boolean_operations_guide"]()
        export = await register_prompts["export_guide"]("STEP")
        debug = await register_prompts["debug_model"]()
        assert "boolean_operation" in boolean
        assert "`export` tool schema" in export
        assert "get_console_output" in debug
        assert all(len(text.encode("utf-8")) < 1_000 for text in (boolean, export, debug))
