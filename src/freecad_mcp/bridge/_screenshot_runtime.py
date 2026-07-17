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
    save_to_disk: bool,
    output_path: str | None,
    return_data: bool,
) -> str:
    """Build code that activates the target GUI document and saves its view.

    The code intentionally mirrors the reliable workflow used interactively in
    FreeCAD: activate document, select a standard view, fit the model, flush GUI
    events, call ``saveImage``, and verify the produced file.
    """
    return f'''
import base64
import os
import tempfile
import time

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
FreeCADGui.updateGui()

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

view.saveImage(image_path, {width}, {height}, {background!r})
FreeCADGui.updateGui()

if not os.path.isfile(image_path):
    raise RuntimeError(f"FreeCAD did not create screenshot: {{image_path}}")
file_size = int(os.path.getsize(image_path))
if file_size <= 0:
    raise RuntimeError(f"FreeCAD created an empty screenshot: {{image_path}}")

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
}}

if is_temporary:
    try:
        os.unlink(image_path)
    except OSError:
        pass
'''
