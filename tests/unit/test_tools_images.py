"""Tests for local image MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mcp.types import CallToolResult, ImageContent
from PIL import Image as PILImage


@pytest.fixture
def registered_tools():
    """Register image tools on a lightweight mock MCP server."""
    from freecad_mcp.tools.images import register_image_tools

    mcp = MagicMock()
    mcp._registered_tools = {}

    def tool_decorator():
        def wrapper(func):
            mcp._registered_tools[func.__name__] = func
            return func

        return wrapper

    mcp.tool = tool_decorator
    register_image_tools(mcp)
    return mcp._registered_tools


def _write_image(path, size=(320, 240), color="white"):
    """Create a test PNG."""
    PILImage.new("RGB", size, color).save(path, format="PNG")


@pytest.mark.asyncio
async def test_open_image_returns_mcp_image_content(registered_tools, tmp_path):
    """open_image should expose pixels, not just a local path."""
    image_path = tmp_path / "drawing.png"
    _write_image(image_path, size=(640, 480))

    result = await registered_tools["open_image"](str(image_path))

    assert isinstance(result, CallToolResult)
    assert result.isError is False
    assert result.structuredContent["success"] is True
    assert result.structuredContent["width"] == 640
    assert result.structuredContent["height"] == 480
    images = [item for item in result.content if isinstance(item, ImageContent)]
    assert len(images) == 1
    assert images[0].mimeType == "image/png"
    assert images[0].data


@pytest.mark.asyncio
async def test_open_image_resizes_large_image(registered_tools, tmp_path):
    """open_image should limit oversized image dimensions."""
    image_path = tmp_path / "large.png"
    _write_image(image_path, size=(1200, 600))

    result = await registered_tools["open_image"](
        str(image_path),
        max_dimension=300,
    )

    assert result.structuredContent["width"] == 300
    assert result.structuredContent["height"] == 150
    assert result.structuredContent["resized"] is True


@pytest.mark.asyncio
async def test_open_image_rejects_missing_file(registered_tools, tmp_path):
    """Missing images should be returned as MCP tool errors."""
    result = await registered_tools["open_image"](str(tmp_path / "missing.png"))

    assert result.isError is True
    assert result.structuredContent["success"] is False
    assert "not found" in result.structuredContent["error"]
    assert not any(isinstance(item, ImageContent) for item in result.content)


@pytest.mark.asyncio
async def test_compare_images_returns_labelled_composite(registered_tools, tmp_path):
    """compare_images should return one side-by-side image and optional disk file."""
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    output = tmp_path / "comparison.png"
    _write_image(reference, size=(400, 300), color="white")
    _write_image(candidate, size=(300, 400), color="gray")

    result = await registered_tools["compare_images"](
        str(reference),
        str(candidate),
        panel_width=500,
        panel_height=400,
        output_path=str(output),
    )

    assert result.isError is False
    metadata = result.structuredContent
    assert metadata["layout"] == "reference_left_candidate_right"
    assert metadata["width"] == 1008
    assert metadata["height"] == 400
    assert metadata["saved_path"] == str(output.resolve())
    assert output.is_file()
    assert sum(isinstance(item, ImageContent) for item in result.content) == 1


@pytest.mark.asyncio
async def test_compare_images_rejects_tiny_panels(registered_tools, tmp_path):
    """Comparison panels must remain large enough for visual inspection."""
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    _write_image(reference)
    _write_image(candidate)

    result = await registered_tools["compare_images"](
        str(reference),
        str(candidate),
        panel_width=100,
    )

    assert result.isError is True
    assert "at least 200" in result.structuredContent["error"]

@pytest.mark.asyncio
async def test_fastmcp_serializes_open_image_as_image_content(tmp_path):
    """FastMCP must preserve ImageContent through its result conversion layer."""
    from mcp.server.fastmcp import FastMCP

    from freecad_mcp.tools.images import register_image_tools

    image_path = tmp_path / "drawing.png"
    _write_image(image_path)
    mcp = FastMCP("image-test")
    register_image_tools(mcp)

    result = await mcp.call_tool("open_image", {"path": str(image_path)})

    assert isinstance(result, CallToolResult)
    assert result.isError is False
    assert any(isinstance(item, ImageContent) for item in result.content)


@pytest.mark.asyncio
async def test_compare_images_requires_reaction_gate(registered_tools, tmp_path):
    """compare_images metadata should make the next reaction step explicit."""
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    _write_image(reference)
    _write_image(candidate)

    result = await registered_tools["compare_images"](
        str(reference),
        str(candidate),
    )

    metadata = result.structuredContent
    assert metadata["assessment_status"] == "not_evaluated"
    assert "evaluate_model_checkpoint" in metadata["required_next_step"]["action"]
    assert "observed" in metadata["required_next_step"]["ledger_fields"]
