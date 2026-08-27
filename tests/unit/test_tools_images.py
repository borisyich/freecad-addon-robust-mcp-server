"""Tests for local image MCP tools."""

from __future__ import annotations

import base64
import os
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


def _write_noisy_image(path, size=(900, 900)):
    """Create a PNG that remains large after lossless compression."""
    image = PILImage.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    image.save(path, format="PNG")


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
async def test_open_image_has_no_delivery_byte_cap_by_default(
    registered_tools, tmp_path, monkeypatch
):
    """Local/default image delivery should remain unlimited."""
    monkeypatch.setenv("FREECAD_IMAGE_DELIVERY_MAX_BYTES", "0")
    image_path = tmp_path / "noisy.png"
    _write_noisy_image(image_path)

    result = await registered_tools["open_image"](str(image_path))

    image = next(item for item in result.content if isinstance(item, ImageContent))
    assert len(base64.b64decode(image.data)) > 1_000_000
    assert "image_delivery" not in result.structuredContent


@pytest.mark.asyncio
async def test_open_image_applies_configured_delivery_byte_cap(
    registered_tools, tmp_path, monkeypatch
):
    """Opt-in remote profile should keep each returned image within its cap."""
    monkeypatch.setenv("FREECAD_IMAGE_DELIVERY_MAX_BYTES", "1000000")
    image_path = tmp_path / "noisy.png"
    _write_noisy_image(image_path)

    result = await registered_tools["open_image"](str(image_path))

    image = next(item for item in result.content if isinstance(item, ImageContent))
    delivered_bytes = len(base64.b64decode(image.data))
    delivery = result.structuredContent["image_delivery"]
    assert delivered_bytes <= 1_000_000
    assert delivery["max_bytes"] == 1_000_000
    assert delivery["original_bytes"] > 1_000_000
    assert delivery["delivered_bytes"] == delivered_bytes
    assert delivery["resized"] is True


def test_image_result_caps_legacy_base64_metadata(monkeypatch):
    """Remote delivery must not leave an oversized duplicate in metadata."""
    from freecad_mcp.tools.images import _encode_png, image_tool_result

    monkeypatch.setenv("FREECAD_IMAGE_DELIVERY_MAX_BYTES", "1000000")
    image = PILImage.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3))
    image_base64 = _encode_png(image)

    result = image_tool_result(
        {"success": True, "data": image_base64},
        image_base64=image_base64,
    )

    assert len(base64.b64decode(result.structuredContent["data"])) <= 1_000_000


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
        view_context="Left / YZ plane / normal X",
    )

    assert result.isError is False
    metadata = result.structuredContent
    assert metadata["layout"] == "reference_left_candidate_right"
    assert metadata["width"] == 1008
    assert metadata["height"] == 400
    assert metadata["saved_path"] == str(output.resolve())
    assert metadata["view_context"] == "Left / YZ plane / normal X"
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
async def test_compare_images_returns_optional_review_guidance(
    registered_tools, tmp_path
):
    """compare_images should suggest review without imposing a rigid gate."""
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    _write_image(reference)
    _write_image(candidate)

    result = await registered_tools["compare_images"](
        str(reference),
        str(candidate),
    )

    metadata = result.structuredContent
    assert "assessment_status" not in metadata
    assert metadata["view_context"] == "VIEW NOT SPECIFIED"
    assert "whole drawing sheet" in metadata["comparison_preconditions"][0]
    review = metadata["recommended_review"]
    assert review["action"] == "describe_concrete_discrepancies_and_rework_if_needed"
    assert "observed" in review["optional_ledger_fields"]
    assert review["optional_decision_values"] == ["continue", "rework"]
    assert "every source-view manifest record" in review["when_uncertain"]
    assert "profile_plane_and_axis_direction" in review["inspect"]
    contract = metadata["visual_review_contract"]
    assert contract["image_content_returned"] is True
    assert contract["image_content_review_required"] is True
    assert contract["metadata_or_saved_file_alone_is_not_review"] is True
    assert "Forward the returned MCP ImageContent" in contract["wrapper_requirement"]


@pytest.mark.asyncio
async def test_open_image_tiles_returns_overview_and_labelled_fragments(
    registered_tools, tmp_path
):
    """Dense drawings should be delivered as overview plus overlapping tiles."""
    drawing = tmp_path / "drawing.png"
    output_dir = tmp_path / "tiles"
    image = PILImage.new("RGB", (900, 600), "white")
    image.save(drawing, format="PNG")

    result = await registered_tools["open_image_tiles"](
        str(drawing),
        rows=2,
        columns=3,
        overlap_percent=10,
        tile_max_dimension=800,
        output_dir=str(output_dir),
    )

    assert result.isError is False
    metadata = result.structuredContent
    assert metadata["kind"] == "opened_image_tiles"
    assert metadata["grid"]["tile_count"] == 6
    assert metadata["grid"]["order"] == "row_major"
    assert len(metadata["tiles"]) == 6
    assert sum(isinstance(item, ImageContent) for item in result.content) == 7
    assert (output_dir / "00_overview.png").is_file()
    assert (output_dir / "01_r1_c1.png").is_file()

    assert "visual_ack_required" not in metadata
    assert "submit_modeling_plan" not in str(metadata)
    assert "Inspect every returned fragment" in metadata["recommended_review"]
    assert "minimum tile grid" in metadata["recommended_review"]


@pytest.mark.asyncio
async def test_open_image_tiles_never_upscales_source_crops(registered_tools, tmp_path):
    """Small source crops should keep native resolution instead of being enlarged."""
    drawing = tmp_path / "small.png"
    PILImage.new("RGB", (600, 400), "white").save(drawing, format="PNG")

    result = await registered_tools["open_image_tiles"](
        str(drawing),
        rows=2,
        columns=2,
        overlap_percent=0,
        tile_max_dimension=1600,
        include_overview=False,
        save_to_disk=False,
    )

    assert result.isError is False
    for tile in result.structuredContent["tiles"]:
        assert tile["resize_scale"] == 1.0
        # delivered_height includes the label header, but image content itself
        # must not have been enlarged. Width is unchanged by the header.
        assert tile["delivered_width"] == tile["source_width"]


@pytest.mark.asyncio
async def test_open_image_tiles_caps_every_returned_image(
    registered_tools, tmp_path, monkeypatch
):
    """The same remote cap must cover overview and every tile."""
    monkeypatch.setenv("FREECAD_IMAGE_DELIVERY_MAX_BYTES", "200000")
    drawing = tmp_path / "noisy.png"
    _write_noisy_image(drawing, size=(1200, 800))

    result = await registered_tools["open_image_tiles"](
        str(drawing),
        rows=2,
        columns=2,
        tile_max_dimension=1200,
        save_to_disk=False,
    )

    images = [item for item in result.content if isinstance(item, ImageContent)]
    assert len(images) == 5
    assert all(len(base64.b64decode(item.data)) <= 200_000 for item in images)
    assert len(result.structuredContent["image_delivery"]["images"]) == 5


@pytest.mark.asyncio
async def test_open_image_tiles_rejects_excessive_grid(registered_tools, tmp_path):
    drawing = tmp_path / "drawing.png"
    _write_image(drawing)

    result = await registered_tools["open_image_tiles"](str(drawing), rows=4, columns=4)

    assert result.isError is True
    assert "must not exceed 9" in result.structuredContent["error"]
