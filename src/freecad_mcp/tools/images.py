"""Image tools that return real MCP image content to multimodal agents."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image as PILImage
from PIL import ImageDraw, ImageOps, UnidentifiedImageError

from freecad_mcp.config import get_config
from freecad_mcp.guidance import DISCREPANCY_LEDGER_FIELDS

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
PILImage.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _json_text(payload: dict[str, Any]) -> TextContent:
    """Create compact, model-visible JSON metadata."""
    return TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def image_tool_result(
    metadata: dict[str, Any],
    *,
    image_base64: str | None = None,
    mime_type: str = "image/png",
    is_error: bool = False,
) -> CallToolResult:
    """Build a tool result with metadata and optional MCP ImageContent."""
    content: list[TextContent | ImageContent] = [_json_text(metadata)]
    if image_base64 is not None:
        content.append(
            ImageContent(
                type="image",
                data=image_base64,
                mimeType=mime_type,
            )
        )
    return CallToolResult(
        content=content,
        structuredContent=metadata,
        isError=is_error,
    )


def image_error(message: str, **details: Any) -> CallToolResult:
    """Return a standard MCP tool error."""
    metadata = {**details, "success": False, "error": message}
    return image_tool_result(metadata, is_error=True)


def _resolve_image_path(path: str) -> Path:
    """Resolve and validate a local image path."""
    config = get_config()
    if not config.allow_file_access:
        raise PermissionError("Local file access is disabled by FREECAD_ALLOW_FILE_ACCESS")

    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    resolved = resolved.resolve()

    if not resolved.is_file():
        raise FileNotFoundError(f"Image file not found: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported image format: {resolved.suffix}. Supported: {supported}")

    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError(f"Image file is empty: {resolved}")
    if size > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image file is too large: {size} bytes; limit is {MAX_IMAGE_BYTES} bytes"
        )
    return resolved


def _load_normalized_image(path: Path, max_dimension: int) -> tuple[PILImage.Image, dict[str, Any]]:
    """Load, orient, resize, and normalize an image for model consumption."""
    if max_dimension <= 0:
        raise ValueError("max_dimension must be positive")

    try:
        with PILImage.open(path) as source:
            source.load()
            original_format = (source.format or path.suffix.lstrip(".")).upper()
            original_size = source.size
            image = ImageOps.exif_transpose(source).copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Cannot decode image: {path}") from exc

    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError(
            f"Image has too many pixels: {image.width}x{image.height}; "
            f"limit is {MAX_IMAGE_PIXELS}"
        )

    resized = max(image.size) > max_dimension
    if resized:
        image.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)

    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    metadata = {
        "source_path": str(path),
        "source_format": original_format,
        "source_width": original_size[0],
        "source_height": original_size[1],
        "width": image.width,
        "height": image.height,
        "resized": resized,
        "file_size": path.stat().st_size,
    }
    return image, metadata


def _encode_png(image: PILImage.Image) -> str:
    """Encode an image as base64 PNG."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _fit_on_panel(
    image: PILImage.Image,
    *,
    panel_width: int,
    panel_height: int,
    label: str,
) -> PILImage.Image:
    """Place one image on a labelled white panel."""
    label_height = 44
    available_height = panel_height - label_height
    fitted = ImageOps.contain(
        image.convert("RGB"),
        (panel_width - 24, available_height - 24),
        method=PILImage.Resampling.LANCZOS,
    )
    panel = PILImage.new("RGB", (panel_width, panel_height), "white")
    x = (panel_width - fitted.width) // 2
    y = label_height + (available_height - fitted.height) // 2
    panel.paste(fitted, (x, y))

    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, panel_width, label_height), fill=(245, 245, 245))
    draw.text((16, 14), label, fill="black")
    draw.rectangle((0, 0, panel_width - 1, panel_height - 1), outline=(100, 100, 100))
    return panel


def register_image_tools(mcp: Any) -> None:
    """Register local image tools that do not require a FreeCAD bridge."""

    @mcp.tool()
    async def open_image(path: str, max_dimension: int = 4096) -> CallToolResult:
        """Open a local PNG/JPEG/WebP and return its pixels as MCP ImageContent.

        Use this tool whenever the agent has only a filesystem path to a drawing,
        reference image, or previously saved screenshot. A path by itself is not
        visual context; this tool makes the actual pixels available to the model.

        Args:
            path: Absolute path, or a path relative to the MCP server working directory.
            max_dimension: Downscale only when the longest side exceeds this value.

        Returns:
            MCP text metadata followed by real image content for multimodal analysis.
        """
        try:
            resolved = _resolve_image_path(path)
            image, metadata = _load_normalized_image(resolved, max_dimension)
            payload = {"success": True, "kind": "opened_image", **metadata}
            return image_tool_result(
                payload,
                image_base64=_encode_png(image),
                mime_type="image/png",
            )
        except Exception as exc:
            return image_error(str(exc), path=path)

    @mcp.tool()
    async def compare_images(
        reference_path: str,
        candidate_path: str,
        panel_width: int = 1200,
        panel_height: int = 900,
        output_path: str | None = None,
    ) -> CallToolResult:
        """Return a labelled side-by-side comparison as one MCP image.

        The left panel is always REFERENCE and the right panel is CANDIDATE.
        This does not claim pixel-perfect alignment or compute a correctness score;
        it gives the vision model both images in one unambiguous visual context.
        After this call, the agent must write a discrepancy ledger and call
        ``evaluate_model_checkpoint`` before continuing to the next feature.

        Args:
            reference_path: Drawing or expected reference image.
            candidate_path: Current FreeCAD screenshot or other candidate image.
            panel_width: Width of each panel in pixels.
            panel_height: Height of each panel in pixels.
            output_path: Optional PNG path for persisting the comparison.

        Returns:
            Metadata and one side-by-side MCP ImageContent block.
        """
        if panel_width < 200 or panel_height < 200:
            return image_error(
                "panel_width and panel_height must be at least 200 pixels",
                reference_path=reference_path,
                candidate_path=candidate_path,
            )
        try:
            reference = _resolve_image_path(reference_path)
            candidate = _resolve_image_path(candidate_path)
            reference_image, reference_meta = _load_normalized_image(
                reference, max(panel_width, panel_height) * 2
            )
            candidate_image, candidate_meta = _load_normalized_image(
                candidate, max(panel_width, panel_height) * 2
            )

            left = _fit_on_panel(
                reference_image,
                panel_width=panel_width,
                panel_height=panel_height,
                label="REFERENCE",
            )
            right = _fit_on_panel(
                candidate_image,
                panel_width=panel_width,
                panel_height=panel_height,
                label="CANDIDATE",
            )
            comparison = PILImage.new(
                "RGB",
                (panel_width * 2 + 8, panel_height),
                (40, 40, 40),
            )
            comparison.paste(left, (0, 0))
            comparison.paste(right, (panel_width + 8, 0))

            saved_path: str | None = None
            if output_path is not None:
                target = Path(output_path).expanduser()
                if not target.is_absolute():
                    target = Path.cwd() / target
                target = target.resolve()
                if target.suffix.lower() != ".png":
                    raise ValueError("output_path must have a .png extension")
                target.parent.mkdir(parents=True, exist_ok=True)
                comparison.save(target, format="PNG", optimize=True)
                saved_path = str(target)

            payload = {
                "success": True,
                "kind": "image_comparison",
                "layout": "reference_left_candidate_right",
                "reference": reference_meta,
                "candidate": candidate_meta,
                "width": comparison.width,
                "height": comparison.height,
                "saved_path": saved_path,
                "assessment_status": "not_evaluated",
                "comparison_limitations": [
                    "This tool only arranges images side by side.",
                    "It does not align geometry or compute CAD correctness.",
                    "Reference and candidate must show equivalent views.",
                ],
                "required_next_step": {
                    "action": "write_discrepancy_ledger_then_call_evaluate_model_checkpoint",
                    "ledger_fields": list(DISCREPANCY_LEDGER_FIELDS),
                    "decision_values": ["continue", "rework"],
                },
            }
            return image_tool_result(
                payload,
                image_base64=_encode_png(comparison),
                mime_type="image/png",
            )
        except Exception as exc:
            return image_error(
                str(exc),
                reference_path=reference_path,
                candidate_path=candidate_path,
            )
