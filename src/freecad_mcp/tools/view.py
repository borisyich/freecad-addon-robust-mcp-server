"""View and screenshot tools for FreeCAD Robust MCP Server.

This module provides tools for controlling the 3D view and
capturing screenshots. Based on learnings from neka-nat which
has excellent screenshot handling with view type detection.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.types import CallToolResult


VIEW_PROJECTION_CONTEXT: dict[str, dict[str, str | None]] = {
    "Front": {"projection_plane": "XZ", "normal_axis": "Y"},
    "Back": {"projection_plane": "XZ", "normal_axis": "Y"},
    "Top": {"projection_plane": "XY", "normal_axis": "Z"},
    "Bottom": {"projection_plane": "XY", "normal_axis": "Z"},
    "Left": {"projection_plane": "YZ", "normal_axis": "X"},
    "Right": {"projection_plane": "YZ", "normal_axis": "X"},
    "Isometric": {"projection_plane": None, "normal_axis": None},
    "FitAll": {"projection_plane": None, "normal_axis": None},
}


def register_view_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register view-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def get_screenshot(
        view_angle: Literal[
            "Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right", "FitAll"
        ] = "Isometric",
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
        fit_all: bool = True,
        background: Literal["White", "Current"] = "White",
        show_corner_cross: bool = True,
        corner_cross_size: int = 10,
        settle_time_seconds: float = 2.0,
        save_to_disk: bool = False,
        output_path: str | None = None,
        return_image: bool = True,
        return_data: bool = False,
    ) -> CallToolResult:
        """Capture a FreeCAD view and optionally return real MCP image content.

        ``return_image=True`` is the normal choice for an autonomous multimodal
        agent: the screenshot is returned as MCP ``ImageContent`` and can be
        interpreted directly. A filesystem path or base64 text alone is not
        visual context. ``return_data`` is retained only for legacy callers that
        explicitly need the base64 string in metadata.

        Args:
            view_angle: Isometric, Front, Back, Top, Bottom, Left, Right, or FitAll.
            width: Image width in pixels.
            height: Image height in pixels.
            doc_name: Document to activate and capture. Uses active document if None.
            fit_all: Fit all visible objects after setting the view.
            background: FreeCAD saveImage mode: ``White`` or ``Current``.
            show_corner_cross: Show the global X/Y/Z orientation indicator in
                the lower-right corner. Defaults to True for engineering review.
            corner_cross_size: Approximate percentage of the 3D-view canvas used
                by the corner cross. Must be between 1 and 100.
            settle_time_seconds: Delay after setting the camera and fitting the
                model before ``saveImage``. FreeCAD GUI events and redraws are
                processed during the delay. Defaults to 2 seconds; use 0 only for
                controlled tests or when camera state is already stable.
            save_to_disk: Persist the PNG on disk.
            output_path: Optional PNG path. When omitted, FreeCAD creates a file
                under ``./screenshots`` when disk saving is enabled.
            return_image: Return pixels as MCP ``ImageContent``. Defaults to True.
            return_data: Also expose legacy base64 text in metadata. Avoid this for
                agent vision because it wastes context and is not interpreted as an image.

        Returns:
            A ``CallToolResult`` containing metadata and, when requested, an image.
        """
        from freecad_mcp.bridge.base import ViewAngle
        from freecad_mcp.tools.images import image_error, image_tool_result

        angle_map = {
            "Isometric": ViewAngle.ISOMETRIC,
            "Front": ViewAngle.FRONT,
            "Back": ViewAngle.BACK,
            "Top": ViewAngle.TOP,
            "Bottom": ViewAngle.BOTTOM,
            "Left": ViewAngle.LEFT,
            "Right": ViewAngle.RIGHT,
            "FitAll": ViewAngle.FIT_ALL,
        }

        if view_angle not in angle_map:
            return image_error(
                f"Invalid view_angle: {view_angle}. Options: {list(angle_map.keys())}"
            )
        if width <= 0 or height <= 0:
            return image_error("width and height must be positive")
        if background not in {"White", "Current"}:
            return image_error("background must be 'White' or 'Current'")
        if not 1 <= corner_cross_size <= 100:
            return image_error("corner_cross_size must be between 1 and 100")
        if not 0 <= settle_time_seconds <= 10:
            return image_error("settle_time_seconds must be between 0 and 10")
        if output_path is not None and not save_to_disk:
            return image_error("output_path requires save_to_disk=True")
        if not save_to_disk and not return_image and not return_data:
            return image_error("Enable return_image, return_data, or save_to_disk")

        bridge = await get_bridge()
        need_base64 = return_image or return_data
        result = await bridge.get_screenshot(
            view_angle=angle_map[view_angle],
            width=width,
            height=height,
            doc_name=doc_name,
            fit_all=fit_all,
            background=background,
            show_corner_cross=show_corner_cross,
            corner_cross_size=corner_cross_size,
            settle_time_seconds=settle_time_seconds,
            save_to_disk=save_to_disk,
            output_path=output_path,
            return_data=need_base64,
        )

        metadata = {
            "success": result.success,
            "kind": "freecad_screenshot",
            "view_angle": view_angle,
            "projection_plane": VIEW_PROJECTION_CONTEXT[view_angle]["projection_plane"],
            "normal_axis": VIEW_PROJECTION_CONTEXT[view_angle]["normal_axis"],
            "format": result.format,
            "width": result.width,
            "height": result.height,
            "path": result.path,
            "saved_to_disk": result.saved_to_disk,
            "file_size": result.file_size,
            "settle_time_seconds": settle_time_seconds,
            "error": result.error,
        }
        if return_data:
            metadata["data"] = result.data

        if not result.success:
            return image_tool_result(metadata, is_error=True)
        if return_image and not result.data:
            return image_error(
                "FreeCAD screenshot succeeded but returned no image data",
                **metadata,
            )

        return image_tool_result(
            metadata,
            image_base64=result.data if return_image else None,
            mime_type=f"image/{result.format}",
        )

    @mcp.tool()
    async def set_view_angle(
        view_angle: Literal[
            "Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right", "FitAll"
        ],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the 3D view angle.

        Args:
            view_angle: View angle to set. Options:
                - "Isometric" - 3D isometric view
                - "Front" - Front projection on XZ; camera normal is Y
                - "Back" - Rear projection on XZ; camera normal is Y
                - "Top" - Top projection on XY; camera normal is Z
                - "Bottom" - Bottom projection on XY; camera normal is Z
                - "Left" - Left-side projection on YZ (ZOY); camera normal is X
                - "Right" - Right-side projection on YZ (ZOY); camera normal is X
                - "FitAll" - Fit all objects in view
            doc_name: Document to set view for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        from freecad_mcp.bridge.base import ViewAngle

        angle_map = {
            "Isometric": ViewAngle.ISOMETRIC,
            "Front": ViewAngle.FRONT,
            "Back": ViewAngle.BACK,
            "Top": ViewAngle.TOP,
            "Bottom": ViewAngle.BOTTOM,
            "Left": ViewAngle.LEFT,
            "Right": ViewAngle.RIGHT,
            "FitAll": ViewAngle.FIT_ALL,
        }

        if view_angle not in angle_map:
            return {
                "success": False,
                "error": f"Invalid view_angle: {view_angle}. Options: {list(angle_map.keys())}",
            }

        bridge = await get_bridge()
        await bridge.set_view(angle_map[view_angle], doc_name)
        return {
            "success": True,
            "view_angle": view_angle,
            "projection_plane": VIEW_PROJECTION_CONTEXT[view_angle]["projection_plane"],
            "normal_axis": VIEW_PROJECTION_CONTEXT[view_angle]["normal_axis"],
        }

    @mcp.tool()
    async def workbench(
        action: Literal["list", "activate"],
        workbench_name: str | None = None,
    ) -> dict[str, Any]:
        """List FreeCAD workbenches or activate one workbench.

        Args:
            action: ``list`` to inspect available workbenches or ``activate`` to
                switch the active workbench.
            workbench_name: Internal workbench name required for ``activate``.

        Returns:
            The available workbenches or activation result.
        """
        bridge = await get_bridge()
        if action == "list":
            workbenches = await bridge.get_workbenches()
            return {
                "action": action,
                "workbenches": [
                    {
                        "name": item.name,
                        "label": item.label,
                        "is_active": item.is_active,
                    }
                    for item in workbenches
                ],
            }
        if not workbench_name:
            raise ValueError("workbench_name is required for action='activate'")
        await bridge.activate_workbench(workbench_name)
        return {
            "success": True,
            "action": action,
            "workbench_name": workbench_name,
        }

    @mcp.tool()
    async def set_visual_properties(
        object_name: str,
        visible: bool | None = None,
        color: list[float] | None = None,
        display_mode: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set one or more GUI display properties for a FreeCAD object.

        Args:
            object_name: Name of the object.
            visible: Optional visibility state.
            color: Optional RGB values in the inclusive range 0.0 to 1.0.
            display_mode: Optional FreeCAD display mode such as ``Flat Lines``.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Applied visual properties.
        """
        if visible is None and color is None and display_mode is None:
            raise ValueError("Provide visible, color, or display_mode")
        if color is not None:
            if len(color) != 3 or any(
                component < 0 or component > 1 for component in color
            ):
                raise ValueError("color must contain three values between 0.0 and 1.0")

        bridge = await get_bridge()
        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - visual properties require GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        obj = doc.getObject({object_name!r})
        if obj is None:
            _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
        elif not hasattr(obj, "ViewObject") or not obj.ViewObject:
            _result_ = {{"success": False, "error": "Object has no ViewObject"}}
        else:
            applied = {{}}
            if {visible!r} is not None:
                obj.ViewObject.Visibility = {visible!r}
                applied["visible"] = bool(obj.ViewObject.Visibility)
            if {color!r} is not None:
                obj.ViewObject.ShapeColor = tuple({color!r})
                applied["color"] = list(obj.ViewObject.ShapeColor)
            if {display_mode!r} is not None:
                obj.ViewObject.DisplayMode = {display_mode!r}
                applied["display_mode"] = obj.ViewObject.DisplayMode
            _result_ = {{"success": True, "object_name": obj.Name, "applied": applied}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set visual properties failed",
        }

    @mcp.tool()
    async def history(
        action: Literal["undo", "redo", "status"],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Undo, redo, or inspect document history.

        Args:
            action: History operation to perform.
            doc_name: Document to operate on. Uses active document if None.

        Returns:
            Action result plus current undo and redo counts.
        """
        bridge = await get_bridge()
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    _result_ = {{
        "success": False,
        "action": {action!r},
        "error": "No document found",
        "undo_count": 0,
        "redo_count": 0,
        "undo_names": [],
        "redo_names": [],
    }}
else:
    action = {action!r}
    success = True
    error = None
    if action == "undo":
        if doc.UndoCount > 0:
            doc.undo()
        else:
            success = False
            error = "Nothing to undo"
    elif action == "redo":
        if doc.RedoCount > 0:
            doc.redo()
        else:
            success = False
            error = "Nothing to redo"
    _result_ = {{
        "success": success,
        "action": action,
        "error": error,
        "undo_count": doc.UndoCount,
        "redo_count": doc.RedoCount,
        "undo_names": list(doc.UndoNames) if hasattr(doc, "UndoNames") else [],
        "redo_names": list(doc.RedoNames) if hasattr(doc, "RedoNames") else [],
    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "action": action,
            "error": result.error_traceback or "History operation failed",
            "undo_count": 0,
            "redo_count": 0,
            "undo_names": [],
            "redo_names": [],
        }

    @mcp.tool()
    async def fit_all(doc_name: str | None = None) -> dict[str, Any]:
        """Fit all objects in the current view.

        Adjusts the camera to show all visible objects in the document.

        Args:
            doc_name: Document to fit view for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        from freecad_mcp.bridge.base import ViewAngle

        bridge = await get_bridge()
        await bridge.set_view(ViewAngle.FIT_ALL, doc_name)
        return {"success": True}

    @mcp.tool()
    async def set_camera_position(
        position: list[float],
        look_at: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the camera position and orientation.

        Requires GUI mode.

        Args:
            position: Camera position as [x, y, z].
            look_at: Point to look at as [x, y, z]. Uses origin if None.
            doc_name: Document to set camera for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        bridge = await get_bridge()

        look_str = (
            f"FreeCAD.Vector({look_at[0]}, {look_at[1]}, {look_at[2]})"
            if look_at
            else "FreeCAD.Vector(0, 0, 0)"
        )

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - camera position requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    elif FreeCADGui.ActiveDocument is None or FreeCADGui.ActiveDocument.ActiveView is None:
        _result_ = {{"success": False, "error": "No active view"}}
    else:
        view = FreeCADGui.ActiveDocument.ActiveView
        pos = FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})
        look_at = {look_str}

        # Calculate direction
        direction = look_at - pos
        direction.normalize()

        # Set camera
        view.setCameraOrientation(FreeCAD.Rotation(FreeCAD.Vector(0, 0, -1), direction))
        cam = view.getCameraNode()
        cam.position.setValue(pos.x, pos.y, pos.z)

        _result_ = {{"success": True}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set camera position failed",
        }

    @mcp.tool()
    async def list_parts_library() -> list[dict[str, Any]]:
        """List available parts from the FreeCAD parts library.

        Returns:
            List of parts with:
                - name: Part filename
                - path: Full path to part file
                - category: Part category/folder
        """
        bridge = await get_bridge()

        code = """
import os

parts = []

# Get parts library paths
try:
    # Standard library path
    lib_path = FreeCAD.getResourceDir() + "Mod/Parts_Library"
    if not os.path.exists(lib_path):
        lib_path = os.path.expanduser("~/.FreeCAD/Mod/PartsLibrary")

    if os.path.exists(lib_path):
        for root, dirs, files in os.walk(lib_path):
            category = os.path.relpath(root, lib_path)
            if category == ".":
                category = "Root"

            for f in files:
                if f.endswith((".FCStd", ".step", ".stp", ".iges", ".igs")):
                    parts.append({
                        "name": f,
                        "path": os.path.join(root, f),
                        "category": category,
                    })
except Exception as e:
    pass

_result_ = parts
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        return []

    @mcp.tool()
    async def insert_part_from_library(
        part_path: str,
        name: str | None = None,
        position: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Insert a part from the parts library into the document.

        Args:
            part_path: Path to the part file.
            name: Name for the inserted part. Auto-generated if None.
            position: Initial position [x, y, z]. Origin if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with inserted part information:
                - name: Part name
                - label: Part label
                - type_id: Part type
        """
        bridge = await get_bridge()

        pos_str = (
            f"FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})"
            if position
            else "FreeCAD.Vector(0, 0, 0)"
        )

        code = f"""
import os
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

part_path = {part_path!r}
if not os.path.exists(part_path):
    raise FileNotFoundError(f"Part file not found: {{part_path}}")

ext = os.path.splitext(part_path)[1].lower()
part_name = {name!r} or os.path.splitext(os.path.basename(part_path))[0]

# Wrap in transaction for undo support
doc.openTransaction("Insert Part from Library")
try:
    new_obj = None
    if ext == ".fcstd":
        # Import FreeCAD document
        src_doc = FreeCAD.openDocument(part_path)
        for obj in src_doc.Objects:
            if hasattr(obj, "Shape"):
                new_obj = doc.addObject("Part::Feature", part_name)
                new_obj.Shape = obj.Shape.copy()
                break
        FreeCAD.closeDocument(src_doc.Name)
    else:
        # Import STEP/IGES
        shape = Part.read(part_path)
        new_obj = doc.addObject("Part::Feature", part_name)
        new_obj.Shape = shape

    if new_obj is None:
        raise ValueError(f"No importable shape found in {{part_path}}")

    # Set position
    new_obj.Placement.Base = {pos_str}

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": new_obj.Name,
        "label": new_obj.Label,
        "type_id": new_obj.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Insert part from library failed",
        }
