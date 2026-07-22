"""Generate FreeCAD-side code for reliable 3D view screenshots."""

from __future__ import annotations


def build_screenshot_code(
    *,
    view_angle: str,
    width: int,
    height: int,
    doc_name: str | None,
    fit_all: bool,
    background: str,
    show_corner_cross: bool,
    corner_cross_size: int,
    save_to_disk: bool,
    output_path: str | None,
    return_data: bool,
) -> str:
    """Build code that activates the target GUI document and saves its view.

    ``View3DInventorPy.saveImage`` renders the 3D scene through FreeCAD's
    off-screen renderer. Screen-space feedback decorations such as the corner
    coordinate cross are not guaranteed to be part of that scene image. The
    generated code therefore composites a deterministic X/Y/Z orientation
    indicator into the saved PNG with Qt after ``saveImage`` completes.
    """
    return f'''
import base64
import math
import os
import tempfile
import time


def _qt_modules():
    try:
        from PySide import QtCore, QtGui
        return QtCore, QtGui
    except ImportError:
        try:
            from PySide2 import QtCore, QtGui
            return QtCore, QtGui
        except ImportError:
            from PySide6 import QtCore, QtGui
            return QtCore, QtGui


def _embed_global_corner_cross(image_path, active_view, requested_size):
    """Paint a camera-aware global X/Y/Z triad into ``image_path``.

    FreeCAD's native corner cross is a screen-space viewer decoration and may
    be omitted by ``saveImage``. This software overlay derives the projected
    global-axis directions from the active camera orientation, then paints the
    result directly into the PNG using Qt's QImage/QPainter APIs bundled with
    FreeCAD.
    """
    QtCore, QtGui = _qt_modules()
    image = QtGui.QImage(image_path)
    if image.isNull():
        raise RuntimeError(
            f"Cannot load screenshot for corner-cross compositing: {{image_path}}"
        )

    camera_rotation = active_view.getCameraOrientation()
    if not hasattr(camera_rotation, "multVec"):
        try:
            camera_rotation = FreeCAD.Rotation(*camera_rotation)
        except Exception as exc:
            raise RuntimeError(
                "FreeCAD returned an unsupported camera orientation"
            ) from exc

    # Coin/FreeCAD camera orientation maps the camera-local basis into world
    # space. Dotting a world axis with the camera's right/up basis gives its
    # screen projection without depending on model position or zoom.
    camera_right = camera_rotation.multVec(FreeCAD.Vector(1.0, 0.0, 0.0))
    camera_up = camera_rotation.multVec(FreeCAD.Vector(0.0, 1.0, 0.0))
    camera_forward = camera_rotation.multVec(FreeCAD.Vector(0.0, 0.0, -1.0))

    axes = [
        ("X", QtGui.QColor(220, 55, 55), FreeCAD.Vector(1.0, 0.0, 0.0)),
        ("Y", QtGui.QColor(45, 175, 75), FreeCAD.Vector(0.0, 1.0, 0.0)),
        ("Z", QtGui.QColor(55, 105, 225), FreeCAD.Vector(0.0, 0.0, 1.0)),
    ]

    min_dimension = float(max(1, min(image.width(), image.height())))
    axis_length = max(
        24.0,
        min(min_dimension * float(requested_size) / 100.0, min_dimension * 0.30),
    )
    margin = max(12.0, min_dimension * 0.025)
    origin = QtCore.QPointF(
        float(image.width()) - margin - axis_length,
        float(image.height()) - margin - axis_length,
    )

    line_width = max(2, int(round(min_dimension / 420.0)))
    font_pixels = max(12, int(round(axis_length * 0.24)))
    font = QtGui.QFont()
    font.setBold(True)
    font.setPixelSize(font_pixels)

    painter = QtGui.QPainter(image)
    try:
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
        except AttributeError:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        painter.setFont(font)

        projected = []
        for label, color, world_axis in axes:
            screen_x = float(world_axis.dot(camera_right))
            screen_y = -float(world_axis.dot(camera_up))
            depth = float(world_axis.dot(camera_forward))
            magnitude = math.hypot(screen_x, screen_y)
            projected.append(
                (depth, label, color, screen_x, screen_y, magnitude)
            )

        # Draw axes pointing farther into the scene first, then foreground axes.
        projected.sort(key=lambda item: item[0], reverse=True)

        tiny_label_offsets = {{
            "X": QtCore.QPointF(font_pixels * 0.65, -font_pixels * 0.25),
            "Y": QtCore.QPointF(-font_pixels * 1.10, -font_pixels * 0.25),
            "Z": QtCore.QPointF(font_pixels * 0.15, font_pixels * 1.00),
        }}

        for _depth, label, color, screen_x, screen_y, magnitude in projected:
            if magnitude < 0.075:
                # An axis parallel to the line of sight projects to a point.
                radius = max(4.0, axis_length * 0.055)
                halo_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 220))
                halo_pen.setWidth(line_width + 2)
                painter.setPen(halo_pen)
                painter.setBrush(QtGui.QBrush(color))
                painter.drawEllipse(origin, radius, radius)
                label_point = origin + tiny_label_offsets[label]
            else:
                end = QtCore.QPointF(
                    origin.x() + axis_length * screen_x,
                    origin.y() + axis_length * screen_y,
                )

                halo_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 210))
                halo_pen.setWidth(line_width + 3)
                painter.setPen(halo_pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawLine(origin, end)

                axis_pen = QtGui.QPen(color)
                axis_pen.setWidth(line_width)
                painter.setPen(axis_pen)
                painter.drawLine(origin, end)

                unit_x = screen_x / magnitude
                unit_y = screen_y / magnitude
                perp_x = -unit_y
                perp_y = unit_x
                head_length = max(7.0, axis_length * 0.14)
                head_half_width = head_length * 0.48
                back_x = end.x() - unit_x * head_length
                back_y = end.y() - unit_y * head_length
                arrow = QtGui.QPolygonF(
                    [
                        end,
                        QtCore.QPointF(
                            back_x + perp_x * head_half_width,
                            back_y + perp_y * head_half_width,
                        ),
                        QtCore.QPointF(
                            back_x - perp_x * head_half_width,
                            back_y - perp_y * head_half_width,
                        ),
                    ]
                )
                painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 210), 1))
                painter.setBrush(QtGui.QBrush(color))
                painter.drawPolygon(arrow)

                label_point = QtCore.QPointF(
                    end.x() + unit_x * font_pixels * 0.35 - font_pixels * 0.20,
                    end.y() + unit_y * font_pixels * 0.35 + font_pixels * 0.35,
                )

            shadow_point = QtCore.QPointF(
                label_point.x() + 1.5,
                label_point.y() + 1.5,
            )
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 235)))
            painter.drawText(shadow_point, label)
            painter.setPen(QtGui.QPen(color))
            painter.drawText(label_point, label)

        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 230), max(1, line_width)))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(245, 245, 245)))
        origin_radius = max(2.5, axis_length * 0.025)
        painter.drawEllipse(origin, origin_radius, origin_radius)
    finally:
        painter.end()

    if not image.save(image_path, "PNG"):
        raise RuntimeError(
            f"Failed to save screenshot after corner-cross compositing: {{image_path}}"
        )

    return {{
        "render_mode": "qimage_overlay",
        "axis_length_px": float(axis_length),
        "camera_right": [
            float(camera_right.x),
            float(camera_right.y),
            float(camera_right.z),
        ],
        "camera_up": [
            float(camera_up.x),
            float(camera_up.y),
            float(camera_up.z),
        ],
    }}


requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("No document found")
if not FreeCAD.GuiUp:
    raise RuntimeError("GUI not available")

# A different tab (Spreadsheet, TechDraw, another document) may currently be
# active. Explicit activation is required before accessing ActiveView.
FreeCAD.setActiveDocument(doc.Name)
try:
    FreeCADGui.activeDocument().activeView()
except Exception:
    pass
FreeCADGui.updateGui()

gui_doc = FreeCADGui.getDocument(doc.Name)
if gui_doc is None:
    raise ValueError(f"GUI document is not available: {{doc.Name}}")
try:
    view = gui_doc.activeView()
except Exception:
    view = FreeCADGui.ActiveDocument.ActiveView
if view is None:
    raise ValueError("No active 3D view")

view_class = type(view).__name__
if view_class not in ("View3DInventor", "View3DInventorPy"):
    raise ValueError(f"Cannot capture screenshot from {{view_class}} view")

view_type = {view_angle!r}
if view_type == "Isometric":
    view.viewIsometric()
elif view_type == "Front":
    view.viewFront()
elif view_type == "Back":
    view.viewRear()
elif view_type == "Top":
    view.viewTop()
elif view_type == "Bottom":
    view.viewBottom()
elif view_type == "Left":
    view.viewLeft()
elif view_type == "Right":
    view.viewRight()
elif view_type != "FitAll":
    raise ValueError(f"Unsupported screenshot view: {{view_type}}")

if {fit_all!r} or view_type == "FitAll":
    view.fitAll()

show_corner_cross = {show_corner_cross!r}
corner_cross_size = {corner_cross_size!r}
native_corner_cross_supported = all(
    hasattr(view, method_name)
    for method_name in (
        "isCornerCrossVisible",
        "getCornerCrossSize",
        "setCornerCrossVisible",
        "setCornerCrossSize",
    )
)

# Keep the interactive view consistent while capturing, but do not rely on the
# native feedback decoration being included by saveImage's off-screen render.
previous_corner_cross_visible = None
previous_corner_cross_size = None
if native_corner_cross_supported:
    previous_corner_cross_visible = bool(view.isCornerCrossVisible())
    previous_corner_cross_size = int(view.getCornerCrossSize())
    view.setCornerCrossVisible(show_corner_cross)
    if show_corner_cross:
        view.setCornerCrossSize(corner_cross_size)

FreeCADGui.updateGui()
try:
    view.redraw()
except Exception:
    pass

save_to_disk = {save_to_disk!r}
requested_output_path = {output_path!r}
return_data = {return_data!r}
if not save_to_disk and not return_data:
    raise ValueError("Screenshot must be returned or saved to disk")

is_temporary = not save_to_disk
if save_to_disk:
    if requested_output_path:
        image_path = os.path.abspath(os.path.expanduser(requested_output_path))
    else:
        output_dir = os.path.abspath(os.path.join(os.getcwd(), "screenshots"))
        os.makedirs(output_dir, exist_ok=True)
        safe_doc_name = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in doc.Name
        )
        safe_view_name = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in view_type
        )
        image_path = os.path.join(
            output_dir,
            f"{{safe_doc_name}}_{{safe_view_name}}_{{int(time.time() * 1000)}}.png",
        )
    parent_dir = os.path.dirname(image_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
else:
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image_path = handle.name
    handle.close()

try:
    view.saveImage(image_path, {width}, {height}, {background!r})
    FreeCADGui.updateGui()

    if not os.path.isfile(image_path):
        raise RuntimeError(f"FreeCAD did not create screenshot: {{image_path}}")
    if int(os.path.getsize(image_path)) <= 0:
        raise RuntimeError(f"FreeCAD created an empty screenshot: {{image_path}}")

    corner_cross_embedded = False
    corner_cross_render_mode = None
    corner_cross_overlay = None
    if show_corner_cross:
        corner_cross_overlay = _embed_global_corner_cross(
            image_path,
            view,
            corner_cross_size,
        )
        corner_cross_embedded = True
        corner_cross_render_mode = corner_cross_overlay["render_mode"]

    file_size = int(os.path.getsize(image_path))
    if file_size <= 0:
        raise RuntimeError(
            f"FreeCAD created an empty screenshot after compositing: {{image_path}}"
        )

    image_data = None
    if return_data:
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("ascii")

    _result_ = {{
        "success": True,
        "data": image_data,
        "format": "png",
        "width": {width},
        "height": {height},
        "path": image_path if save_to_disk else None,
        "saved_to_disk": bool(save_to_disk),
        "file_size": file_size,
        "corner_cross_visible": bool(show_corner_cross and corner_cross_embedded),
        "corner_cross_size": corner_cross_size if show_corner_cross else None,
        "corner_cross_supported": True,
        "corner_cross_native_supported": bool(native_corner_cross_supported),
        "corner_cross_embedded": bool(corner_cross_embedded),
        "corner_cross_render_mode": corner_cross_render_mode,
        "corner_cross_overlay": corner_cross_overlay,
    }}
finally:
    if native_corner_cross_supported:
        try:
            view.setCornerCrossSize(previous_corner_cross_size)
            view.setCornerCrossVisible(previous_corner_cross_visible)
            FreeCADGui.updateGui()
        except Exception:
            pass
    if is_temporary:
        try:
            os.unlink(image_path)
        except OSError:
            pass
'''
