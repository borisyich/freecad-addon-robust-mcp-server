"""Image tools that return real MCP image content to multimodal agents."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

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


def multi_image_tool_result(
    metadata: dict[str, Any],
    labelled_images: list[tuple[str, str]],
    *,
    mime_type: str = "image/png",
) -> CallToolResult:
    """Build one result containing ordered text/image pairs.

    Each text block tells the model exactly which source region the following
    image represents. This is more reliable than returning anonymous crops.
    """
    content: list[TextContent | ImageContent] = [_json_text(metadata)]
    for label, image_base64 in labelled_images:
        content.append(TextContent(type="text", text=label))
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
        isError=False,
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


def _normalize_path_for_metadata(path: Path) -> str:
    """Return a stable absolute path string for tool metadata."""
    return str(path.resolve())


def _tile_boxes(
    width: int,
    height: int,
    rows: int,
    columns: int,
    overlap_percent: float,
) -> list[tuple[int, int, int, int, int, int]]:
    """Create row-major overlapping crop boxes.

    The overlap is applied on every internal side so dimensions or feature edges
    close to a grid boundary remain visible in at least one complete tile.
    """
    boxes: list[tuple[int, int, int, int, int, int]] = []
    base_width = width / columns
    base_height = height / rows
    expand_x = base_width * overlap_percent / 200.0
    expand_y = base_height * overlap_percent / 200.0
    for row in range(rows):
        for column in range(columns):
            left = max(0, round(column * base_width - expand_x))
            top = max(0, round(row * base_height - expand_y))
            right = min(width, round((column + 1) * base_width + expand_x))
            bottom = min(height, round((row + 1) * base_height + expand_y))
            boxes.append((row, column, left, top, right, bottom))
    return boxes


def _resize_tile(image: PILImage.Image, target_long_side: int) -> tuple[PILImage.Image, float]:
    """Resize a crop so its long side receives a predictable visual budget."""
    current = max(image.size)
    if current <= 0:
        raise ValueError("Tile has invalid dimensions")
    scale = target_long_side / current
    new_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    if new_size == image.size:
        return image.copy(), 1.0
    return image.resize(new_size, PILImage.Resampling.LANCZOS), scale


def _label_tile(
    image: PILImage.Image,
    *,
    index: int,
    total: int,
    row: int,
    column: int,
    rows: int,
    columns: int,
    box: tuple[int, int, int, int],
) -> PILImage.Image:
    """Add an explicit source-region header to one delivered tile."""
    source = image.convert("RGB")
    header_height = max(88, round(min(source.size) * 0.11))
    canvas = PILImage.new("RGB", (source.width, source.height + header_height), "white")
    canvas.paste(source, (0, header_height))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, header_height), fill=(242, 242, 242))
    left, top, right, bottom = box
    text = (
        f"DETAIL {index}/{total} | R{row + 1}/{rows} C{column + 1}/{columns} | "
        f"src [{left},{top}]-[{right},{bottom}]"
    )
    info_font = ImageFont.load_default(
        size=max(16, round(min(source.size) * 0.022))
    )
    draw.text((14, max(12, (header_height - 18) // 2)), text, fill="black", font=info_font)
    draw.rectangle((0, 0, canvas.width - 1, canvas.height - 1), outline=(90, 90, 90))
    return canvas


def _make_grid_overview(
    image: PILImage.Image,
    boxes: list[tuple[int, int, int, int, int, int]],
    *,
    rows: int,
    columns: int,
    max_dimension: int = 1600,
) -> PILImage.Image:
    """Create an overview showing the numbered source regions."""
    overview = image.convert("RGB").copy()
    scale = min(1.0, max_dimension / max(overview.size))
    if scale < 1.0:
        overview = overview.resize(
            (round(overview.width * scale), round(overview.height * scale)),
            PILImage.Resampling.LANCZOS,
        )
    draw = ImageDraw.Draw(overview)
    line_width = max(2, round(min(overview.size) / 360))
    for index, (row, column, left, top, right, bottom) in enumerate(boxes, start=1):
        scaled = tuple(round(value * scale) for value in (left, top, right, bottom))
        draw.rectangle(scaled, outline=(220, 35, 35), width=line_width)
        x1, y1, _x2, _y2 = scaled
        badge_size = max(26, round(min(overview.size) * 0.035))
        draw.rectangle(
            (x1, y1, x1 + badge_size, y1 + badge_size),
            fill=(255, 255, 255),
            outline=(220, 35, 35),
            width=line_width,
        )
        draw.text((x1 + 7, y1 + 5), str(index), fill=(180, 0, 0))
    header = 46
    canvas = PILImage.new("RGB", (overview.width, overview.height + header), "white")
    canvas.paste(overview, (0, header))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, header), fill=(242, 242, 242))
    draw.text(
        (14, 14),
        f"REFERENCE OVERVIEW | {rows}×{columns} overlapping regions, row-major order",
        fill="black",
    )
    return canvas


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
    async def open_image_tiles(
        path: str,
        rows: int = 2,
        columns: int = 3,
        overlap_percent: float = 12.0,
        tile_max_dimension: int = 1600,
        include_overview: bool = True,
        save_to_disk: bool = True,
        output_dir: str | None = None,
    ) -> CallToolResult:
        """Deliver a drawing overview plus enlarged, labelled, overlapping tiles.

        Use this before reconstructing a part from a dense drawing. Whole-sheet
        images are often downscaled by a VLM, making dimensions and small features
        occupy too few visual tokens. Cropping does not invent information, but it
        gives each source region a much larger share of the model's visual budget.

        The result contains an optional numbered overview followed by ordered
        text/image pairs. Every text block identifies the tile number, grid
        position, source pixel rectangle, overlap, and resize scale. This gives the
        model both global context and higher-resolution local evidence without
        imposing a separate workflow or acknowledgement protocol.

        Args:
            path: Source drawing or reference image.
            rows: Grid rows, from 1 to 4.
            columns: Grid columns, from 1 to 4. Total tiles may not exceed 9.
            overlap_percent: Shared context around adjacent cells, from 0 to 25.
            tile_max_dimension: Long-side pixel size delivered for every tile,
                from 512 to 2048. Smaller crops are upscaled; larger crops downscaled.
            include_overview: Include a numbered whole-image overview first.
            save_to_disk: Save overview and tiles so later `compare_images` calls
                can use an exact reference fragment. Defaults to True.
            output_dir: Optional output directory. When omitted and saving is
                enabled, files are written under `./image_tiles/<source>_<grid>`.

        Returns:
            Metadata and multiple labelled MCP ImageContent blocks in row-major order.
        """
        if not 1 <= rows <= 4 or not 1 <= columns <= 4:
            return image_error("rows and columns must each be between 1 and 4", path=path)
        if rows * columns > 9:
            return image_error("rows * columns must not exceed 9", path=path)
        if not 0 <= overlap_percent <= 25:
            return image_error("overlap_percent must be between 0 and 25", path=path)
        if not 512 <= tile_max_dimension <= 2048:
            return image_error(
                "tile_max_dimension must be between 512 and 2048", path=path
            )

        try:
            resolved = _resolve_image_path(path)
            source, source_meta = _load_normalized_image(resolved, max_dimension=10000)
            boxes = _tile_boxes(
                source.width,
                source.height,
                rows,
                columns,
                overlap_percent,
            )

            target_dir: Path | None = None
            if save_to_disk:
                if output_dir is None:
                    target_dir = (
                        Path.cwd()
                        / "image_tiles"
                        / f"{resolved.stem}_{rows}x{columns}"
                    )
                else:
                    target_dir = Path(output_dir).expanduser()
                    if not target_dir.is_absolute():
                        target_dir = Path.cwd() / target_dir
                target_dir = target_dir.resolve()
                target_dir.mkdir(parents=True, exist_ok=True)
            elif output_dir is not None:
                raise ValueError("output_dir requires save_to_disk=True")

            labelled_images: list[tuple[str, str]] = []
            tile_metadata: list[dict[str, Any]] = []
            if include_overview:
                overview = _make_grid_overview(
                    source, boxes, rows=rows, columns=columns
                )
                overview_path: str | None = None
                if target_dir is not None:
                    target = target_dir / "00_overview.png"
                    overview.save(target, format="PNG", optimize=True)
                    overview_path = _normalize_path_for_metadata(target)
                labelled_images.append(
                    (
                        "REFERENCE OVERVIEW. Red numbered rectangles identify the "
                        f"{len(boxes)} enlarged fragments that follow. Inspect the "
                        "overview for global layout only; read dimensions and local "
                        "features from the detail images.",
                        _encode_png(overview),
                    )
                )
            else:
                overview_path = None

            for index, (row, column, left, top, right, bottom) in enumerate(
                boxes, start=1
            ):
                crop = source.crop((left, top, right, bottom))
                resized, scale = _resize_tile(crop, tile_max_dimension)
                labelled = _label_tile(
                    resized,
                    index=index,
                    total=len(boxes),
                    row=row,
                    column=column,
                    rows=rows,
                    columns=columns,
                    box=(left, top, right, bottom),
                )
                saved_path: str | None = None
                if target_dir is not None:
                    target = target_dir / f"{index:02d}_r{row + 1}_c{column + 1}.png"
                    labelled.save(target, format="PNG", optimize=True)
                    saved_path = _normalize_path_for_metadata(target)

                instruction = (
                    f"ENLARGED FRAGMENT {index}/{len(boxes)} from "
                    f"{resolved.name}; grid row {row + 1}/{rows}, column "
                    f"{column + 1}/{columns}; source rectangle "
                    f"x={left}:{right}, y={top}:{bottom}; overlap="
                    f"{overlap_percent:.1f}%; resize scale={scale:.3f}. "
                    "Inspect all visible dimensions, feature boundaries, hole counts, "
                    "radii, hidden "
                    "lines, section marks, and continuations into "
                    "overlapping neighbour fragments. Do not treat this crop as an "
                    "independent drawing or infer symmetry from the crop alone."
                )
                labelled_images.append((instruction, _encode_png(labelled)))
                tile_metadata.append(
                    {
                        "index": index,
                        "row": row + 1,
                        "column": column + 1,
                        "source_box": {
                            "left": left,
                            "top": top,
                            "right": right,
                            "bottom": bottom,
                        },
                        "source_width": right - left,
                        "source_height": bottom - top,
                        "delivered_width": labelled.width,
                        "delivered_height": labelled.height,
                        "resize_scale": scale,
                        "saved_path": saved_path,
                    }
                )

            payload = {
                "success": True,
                "kind": "opened_image_tiles",
                "source": source_meta,
                "grid": {
                    "rows": rows,
                    "columns": columns,
                    "tile_count": len(boxes),
                    "order": "row_major",
                    "overlap_percent": overlap_percent,
                },
                "tile_max_dimension": tile_max_dimension,
                "overview_included": include_overview,
                "saved_to_disk": save_to_disk,
                "output_dir": str(target_dir) if target_dir is not None else None,
                "overview_saved_path": overview_path,
                "tiles": tile_metadata,
                "recommended_review": (
                    "Inspect every returned fragment, reconcile overlaps with the "
                    "overview, and record dimensions/features with their fragment "
                    "indices before choosing the modeling strategy."
                ),
                "limitations": [
                    "Upscaling does not recover detail absent from the source pixels.",
                    "Grid crops improve visual allocation but do not provide OCR or CAD semantics.",
                    "Features crossing tile boundaries must be reconciled using overlap and overview.",
                ],
            }
            return multi_image_tool_result(payload, labelled_images)
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
        When the comparison exposes a meaningful mismatch, describe the concrete
        discrepancy and rework the causal feature. ``evaluate_model_checkpoint``
        remains available when a formal ledger is useful, but is not mandatory.

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
                "recommended_review": {
                    "action": "describe_concrete_discrepancies_and_rework_if_needed",
                    "optional_ledger_fields": list(DISCREPANCY_LEDGER_FIELDS),
                    "optional_decision_values": ["continue", "rework"],
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
