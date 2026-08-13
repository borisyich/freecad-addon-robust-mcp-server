"""View and screenshot tools for FreeCAD Robust MCP Server.

This module provides tools for controlling the 3D view and
capturing screenshots. Based on learnings from neka-nat which
has excellent screenshot handling with view type detection.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from mcp.types import CallToolResult
from pydantic import Field

from freecad_mcp.bridge._document_runtime import DOCUMENT_RESOLUTION_RUNTIME

RGBColor = Annotated[
    list[Annotated[float, Field(ge=0, le=255)]],
    Field(
        min_length=3,
        max_length=3,
        description=(
            "RGB triplet. Use normalized 0.0..1.0 values or integer byte "
            "values 0..255; byte values are normalized automatically."
        ),
    ),
]

VIEW_PROJECTION_CONTEXT: dict[str, dict[str, str | None]] = {
    "Front": {"projection_plane": "XZ", "normal_axis": "Y"},
    "Back": {"projection_plane": "XZ", "normal_axis": "Y"},
    "Top": {"projection_plane": "XY", "normal_axis": "Z"},
    "Bottom": {"projection_plane": "XY", "normal_axis": "Z"},
    "Left": {"projection_plane": "YZ", "normal_axis": "X"},
    "Right": {"projection_plane": "YZ", "normal_axis": "X"},
    "Isometric": {"projection_plane": None, "normal_axis": None},
    "Current": {"projection_plane": None, "normal_axis": None},
    "FitAll": {"projection_plane": None, "normal_axis": None},
}


def _normalize_rgb_color(color: list[float]) -> list[float]:
    """Accept normalized RGB or integer byte RGB and return FreeCAD values."""
    if len(color) != 3:
        raise ValueError("color must contain exactly three RGB values")
    try:
        values = [float(component) for component in color]
    except (TypeError, ValueError) as exc:
        raise ValueError("color components must be numeric") from exc
    if any(component < 0 or component > 255 for component in values):
        raise ValueError("color components must be between 0 and 255")
    if all(component <= 1 for component in values):
        return values
    if any(not component.is_integer() for component in values):
        raise ValueError(
            "RGB values above 1 use byte form and must be integers from 0 to 255"
        )
    return [component / 255.0 for component in values]


def register_view_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register view-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def get_screenshot(
        view_angle: Literal[
            "Isometric",
            "Front",
            "Back",
            "Top",
            "Bottom",
            "Left",
            "Right",
            "Current",
            "FitAll",
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
            view_angle: Standard orientation, ``Current`` to preserve orientation,
                or ``FitAll`` to change framing only.
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
            "Current": ViewAngle.CURRENT,
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
            "Isometric",
            "Front",
            "Back",
            "Top",
            "Bottom",
            "Left",
            "Right",
            "Current",
            "FitAll",
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
                - "Current" - Preserve the current orientation and framing
                - "FitAll" - Preserve orientation and fit all visible objects
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
            "Current": ViewAngle.CURRENT,
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
    async def highlight_faces(
        action: Literal["show", "clear"],
        object_name: str | None = None,
        face_names: list[str] | None = None,
        color: RGBColor | None = None,
        select_faces: bool = True,
        clear_existing_selection: bool = True,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Temporarily highlight individual faces without creating document objects.

        ``show`` stores the object's current per-face colors, applies the requested
        highlight through ``DiffuseColor``, and optionally selects the same faces
        for a strong outline. ``clear`` restores the exact prior colors. Highlights
        are session-only and do not add geometry to the model tree.

        Args:
            action: ``show`` or ``clear``.
            object_name: Object to highlight; optional for ``clear`` to clear all.
            face_names: ``FaceN`` references required for ``show``.
            color: Highlight RGB as normalized 0.0..1.0 values or integer
                0..255 byte values, normalized automatically.
            select_faces: Also add the faces to GUI selection.
            clear_existing_selection: Clear selection before applying/clearing.
            doc_name: Document containing the object.

        Returns:
            Highlighted/restored references and session-only status.
        """
        if action == "show" and (not object_name or not face_names):
            raise ValueError(
                "object_name and face_names are required for action='show'"
            )
        highlight_color = _normalize_rgb_color(
            color if color is not None else [1.0, 0.75, 0.0]
        )
        for face_name in face_names or []:
            if not (
                face_name.startswith("Face")
                and face_name[4:].isdigit()
                and int(face_name[4:]) > 0
            ):
                raise ValueError(f"Invalid face reference: {face_name!r}")

        bridge = await get_bridge()
        code = f"""
import builtins

if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - face highlighting requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        registry_name = "_freecad_mcp_face_highlights"
        registry = getattr(builtins, registry_name, None)
        if not isinstance(registry, dict):
            registry = {{}}
            setattr(builtins, registry_name, registry)

        if {clear_existing_selection!r}:
            FreeCADGui.Selection.clearSelection()

        if {action!r} == "clear":
            restored = []
            target_name = {object_name!r}
            for key in list(registry):
                stored_doc_name, stored_object_name = key
                if stored_doc_name != doc.Name:
                    continue
                if target_name is not None and stored_object_name != target_name:
                    continue
                obj = doc.getObject(stored_object_name)
                if obj is not None and hasattr(obj, "ViewObject") and obj.ViewObject:
                    obj.ViewObject.DiffuseColor = registry[key]
                    restored.append(obj.Name)
                del registry[key]
            FreeCADGui.updateGui()
            _result_ = {{
                "success": True,
                "action": "clear",
                "restored_objects": restored,
                "transient": True,
            }}
        else:
            obj = doc.getObject({object_name!r})
            if obj is None:
                _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
            elif not hasattr(obj, "Shape") or not hasattr(obj, "ViewObject") or not obj.ViewObject:
                _result_ = {{"success": False, "error": "Object has no highlightable Shape/ViewObject"}}
            else:
                face_count = len(obj.Shape.Faces)
                indices = []
                missing = []
                for face_name in {face_names!r}:
                    index = int(face_name[4:]) - 1
                    if index < 0 or index >= face_count:
                        missing.append(face_name)
                    else:
                        indices.append(index)
                if missing:
                    _result_ = {{
                        "success": False,
                        "error": f"Subelements not found: {{missing}}",
                        "missing_faces": missing,
                    }}
                else:
                    key = (doc.Name, obj.Name)
                    current = [tuple(item) for item in list(obj.ViewObject.DiffuseColor)]
                    if key not in registry:
                        registry[key] = current
                    base = registry[key]
                    if len(base) == face_count:
                        display = list(base)
                    else:
                        fallback = base[0] if base else tuple(obj.ViewObject.ShapeColor)
                        display = [fallback for _ in range(face_count)]
                    highlight_color = tuple({highlight_color!r})
                    for index in indices:
                        display[index] = highlight_color
                    obj.ViewObject.DiffuseColor = display
                    if {select_faces!r}:
                        for face_name in {face_names!r}:
                            FreeCADGui.Selection.addSelection(obj, face_name)
                    FreeCADGui.updateGui()
                    _result_ = {{
                        "success": True,
                        "action": "show",
                        "object_name": obj.Name,
                        "highlighted_faces": list({face_names!r}),
                        "color": list(highlight_color),
                        "selected": bool({select_faces!r}),
                        "transient": True,
                    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "action": action,
            "error": result.error_traceback or "Face highlighting failed",
        }

    @mcp.tool()
    async def set_visual_properties(
        object_name: str,
        visible: bool | None = None,
        color: RGBColor | None = None,
        display_mode: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set one or more GUI display properties for a FreeCAD object.

        Args:
            object_name: Name of the object.
            visible: Optional visibility state.
            color: Optional RGB as normalized 0.0..1.0 values or integer
                0..255 byte values, normalized automatically.
            display_mode: Optional FreeCAD display mode such as ``Flat Lines``.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Applied visual properties.
        """
        if visible is None and color is None and display_mode is None:
            raise ValueError("Provide visible, color, or display_mode")
        normalized_color = _normalize_rgb_color(color) if color is not None else None

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
            if {normalized_color!r} is not None:
                obj.ViewObject.ShapeColor = tuple({normalized_color!r})
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
        up_direction: list[float] | None = None,
        projection: Literal["orthographic", "perspective"] = "orthographic",
        orthographic_height: float | None = None,
        roll_degrees: float = 0.0,
        fit_all: bool = False,
    ) -> dict[str, Any]:
        """Set a deterministic engineering camera for drawing comparison.

        Requires GUI mode.

        Args:
            position: Camera position as [x, y, z].
            look_at: Point to look at as [x, y, z]. Uses origin if None.
            doc_name: Document to set camera for. Uses active document if None.
            up_direction: Approximate screen-up vector. Defaults to global +Z,
                with a safe fallback when parallel to the viewing direction.
            projection: Orthographic by default for same-view drawing checks.
            orthographic_height: Visible world-space height for reproducible scale.
            roll_degrees: Additional roll around the viewing direction.
            fit_all: Fit visible geometry after orientation. Do not combine with
                orthographic_height because fit_all determines scale.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        for field_name, value in (
            ("position", position),
            ("look_at", look_at),
            ("up_direction", up_direction),
        ):
            if value is not None and len(value) != 3:
                raise ValueError(f"{field_name} must contain exactly three numbers")
        if orthographic_height is not None and orthographic_height <= 0:
            raise ValueError("orthographic_height must be positive")
        if projection != "orthographic" and orthographic_height is not None:
            raise ValueError(
                "orthographic_height is available only for orthographic projection"
            )
        if fit_all and orthographic_height is not None:
            raise ValueError("fit_all and orthographic_height are mutually exclusive")

        bridge = await get_bridge()

        look_str = (
            f"FreeCAD.Vector({look_at[0]}, {look_at[1]}, {look_at[2]})"
            if look_at
            else "FreeCAD.Vector(0, 0, 0)"
        )
        up = up_direction or [0.0, 0.0, 1.0]

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - camera position requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    elif FreeCADGui.getDocument(doc.Name) is None:
        _result_ = {{"success": False, "error": "Document has no GUI view"}}
    else:
        from pivy import coin

        FreeCAD.setActiveDocument(doc.Name)
        gui_doc = FreeCADGui.getDocument(doc.Name)
        view = gui_doc.activeView()
        pos = FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})
        look_at = {look_str}

        # Calculate direction
        direction = look_at - pos
        if direction.Length <= 1e-12:
            raise ValueError("position and look_at must be different points")
        focal_distance = float(direction.Length)
        direction.normalize()

        up = FreeCAD.Vector({up[0]}, {up[1]}, {up[2]})
        if up.Length <= 1e-12:
            raise ValueError("up_direction must be a non-zero vector")
        up.normalize()
        # Project the requested up vector into the camera plane. If it is
        # parallel to the view, choose a deterministic fallback axis.
        projection_component = up.dot(direction)
        up = up - FreeCAD.Vector(
            direction.x * projection_component,
            direction.y * projection_component,
            direction.z * projection_component,
        )
        if up.Length <= 1e-9:
            fallback = FreeCAD.Vector(0, 1, 0)
            if abs(direction.dot(fallback)) > 0.99:
                fallback = FreeCAD.Vector(1, 0, 0)
            projection_component = fallback.dot(direction)
            up = fallback - FreeCAD.Vector(
                direction.x * projection_component,
                direction.y * projection_component,
                direction.z * projection_component,
            )
        up.normalize()
        if {roll_degrees!r}:
            up = FreeCAD.Rotation(direction, {roll_degrees!r}).multVec(up)
        right = direction.cross(up)
        right.normalize()
        up = right.cross(direction)
        up.normalize()
        backward = FreeCAD.Vector(-direction.x, -direction.y, -direction.z)

        view.setCameraType({projection.title()!r})
        camera_rotation = FreeCAD.Rotation(right, up, backward, "ZXY")
        cam = view.getCameraNode()
        quaternion = camera_rotation.Q
        cam.orientation.setValue(coin.SbRotation(*quaternion))
        cam.position.setValue(pos.x, pos.y, pos.z)
        cam.focalDistance.setValue(focal_distance)
        if {fit_all!r}:
            view.fitAll()
        if {orthographic_height!r} is not None:
            cam.height.setValue(float({orthographic_height!r}))
        view.redraw()
        FreeCADGui.updateGui()
        # Some Coin/FreeCAD camera combinations apply a deferred focal update
        # during redraw. Reassert the requested position and scale afterwards.
        if not {fit_all!r}:
            cam.position.setValue(pos.x, pos.y, pos.z)
            cam.focalDistance.setValue(focal_distance)
        if {orthographic_height!r} is not None:
            cam.height.setValue(float({orthographic_height!r}))
        view.redraw()
        FreeCADGui.updateGui()

        _result_ = {{
            "success": True,
            "position": [float(cam.position.getValue()[i]) for i in range(3)],
            "look_at": [look_at.x, look_at.y, look_at.z],
            "view_direction": [direction.x, direction.y, direction.z],
            "up_direction": [up.x, up.y, up.z],
            "projection": {projection!r},
            "orthographic_height": (
                float(cam.height.getValue())
                if {projection!r} == "orthographic" and hasattr(cam, "height")
                else None
            ),
            "roll_degrees": {roll_degrees!r},
            "fit_all": {fit_all!r},
            "focal_distance": float(cam.focalDistance.getValue()),
        }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set camera position failed",
        }

    @mcp.tool()
    async def get_camera_state(doc_name: str | None = None) -> dict[str, Any]:
        """Return compact current camera state for reproducible view checks."""
        bridge = await get_bridge()
        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None or FreeCADGui.getDocument(doc.Name) is None:
        _result_ = {{"success": False, "error": "No active document/view"}}
    else:
        FreeCAD.setActiveDocument(doc.Name)
        gui_doc = FreeCADGui.getDocument(doc.Name)
        view = gui_doc.activeView()
        cam = view.getCameraNode()
        pos = cam.position.getValue()
        orientation = cam.orientation.getValue()
        _result_ = {{
            "success": True,
            "projection": str(view.getCameraType()).lower(),
            "position": [float(pos[i]) for i in range(3)],
            "orientation_quaternion": [
                float(orientation.getValue()[i]) for i in range(4)
            ],
            "orthographic_height": (
                float(cam.height.getValue()) if hasattr(cam, "height") else None
            ),
            "focal_distance": (
                float(cam.focalDistance.getValue())
                if hasattr(cam, "focalDistance") else None
            ),
        }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Get camera state failed",
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

requested_doc_name = {doc_name!r}
documents = FreeCAD.listDocuments()
{DOCUMENT_RESOLUTION_RUNTIME}
doc = _resolve_document(requested_doc_name)

target_doc_name = doc.Name
part_path = {part_path!r}
if not os.path.exists(part_path):
    raise FileNotFoundError(f"Part file not found: {{part_path}}")


def _normalized_path(value):
    if not value:
        return None
    return os.path.normcase(os.path.realpath(os.path.abspath(value)))


ext = os.path.splitext(part_path)[1].lower()
part_name = {name!r} or os.path.splitext(os.path.basename(part_path))[0]
source_path = _normalized_path(part_path)
target_path = _normalized_path(getattr(doc, "FileName", ""))
source_shape = None
source_object_name = None
opened_source_doc_name = None
source_document_name = None

try:
    if ext == ".fcstd":
        # Reuse an already open document. In particular, do not call
        # openDocument() for the target document's own FileName: FreeCAD may
        # replace the live document and invalidate both `doc` and its objects.
        src_doc = doc if target_path and source_path == target_path else None
        if src_doc is None:
            for candidate in FreeCAD.listDocuments().values():
                candidate_path = _normalized_path(getattr(candidate, "FileName", ""))
                if candidate_path and candidate_path == source_path:
                    src_doc = candidate
                    break

        if src_doc is None:
            src_doc = FreeCAD.openDocument(part_path)
            if src_doc.Name != target_doc_name:
                opened_source_doc_name = src_doc.Name

        source_document_name = src_doc.Name
        for obj in src_doc.Objects:
            shape = getattr(obj, "Shape", None)
            if shape is not None and not shape.isNull():
                source_shape = shape.copy()
                source_object_name = obj.Name
                break
    else:
        source_shape = Part.read(part_path)

    if source_shape is None or source_shape.isNull():
        raise ValueError(f"No importable shape found in {{part_path}}")
finally:
    # Only close a source document that this tool opened. Never close the
    # target document or another document that was already open.
    if (
        opened_source_doc_name is not None
        and opened_source_doc_name in FreeCAD.listDocuments()
    ):
        FreeCAD.closeDocument(opened_source_doc_name)
    if target_doc_name in FreeCAD.listDocuments():
        FreeCAD.setActiveDocument(target_doc_name)

# Reacquire the target after source loading. Opening an FCStd file can change
# the active document and some FreeCAD builds can replace document wrappers.
doc = FreeCAD.listDocuments().get(target_doc_name)
if doc is None:
    raise RuntimeError(
        f"Target document was closed while reading the source file: {{target_doc_name}}"
    )

transaction_open = False
try:
    doc.openTransaction("Insert Part from Library")
    transaction_open = True

    new_obj = doc.addObject("Part::Feature", part_name)
    new_obj.Shape = source_shape
    new_obj.Placement.Base = {pos_str}

    doc.recompute()
    doc.commitTransaction()
    transaction_open = False

    _result_ = {{
        "name": new_obj.Name,
        "label": new_obj.Label,
        "type_id": new_obj.TypeId,
        "source_document": source_document_name,
        "source_object": source_object_name,
    }}
except Exception:
    # Do not call methods through a stale document wrapper. Reacquire the live
    # target document first, and preserve the original exception if rollback
    # itself is no longer possible.
    rollback_doc = FreeCAD.listDocuments().get(target_doc_name)
    if transaction_open and rollback_doc is not None:
        try:
            rollback_doc.abortTransaction()
        except Exception:
            pass
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Insert part from library failed",
        }
