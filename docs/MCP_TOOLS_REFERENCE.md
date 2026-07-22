# FreeCAD Robust MCP Server Tools Reference

This document provides a comprehensive reference for all MCP tools available in the FreeCAD Robust MCP Server.

---

## Overview

The FreeCAD Robust MCP Server exposes tools organized into the following categories:

| Category                        | Description                      | Tool Count |
| ------------------------------- | -------------------------------- | ---------- |
| [Execution](#execution-tools)   | Python execution and system info | 5          |
| [Documents](#document-tools)    | Document management              | 7          |
| [Objects](#object-tools)        | Object creation and manipulation | 22         |
| [PartDesign](#partdesign-tools) | Parametric solid modeling        | 20         |
| [Export](#export-tools)         | Import/export operations         | 7          |
| [View](#view-tools)             | View control and screenshots     | 18         |
| [Macros](#macro-tools)          | Macro management                 | 6          |
| **Total**                       |                                  | **85**     |

---

## Execution Tools

Tools for executing Python code and getting system information.

### execute_python

Execute arbitrary Python code in FreeCAD's context.

```python
execute_python(
    code: str,
    timeout_ms: int = 30000
) -> dict
```

**Parameters:**

- `code`: Python code to execute. Use `_result_ = value` to return data.
- `timeout_ms`: Maximum execution time in milliseconds.

**Returns:** Execution result with stdout, stderr, and any assigned `_result_`.

**Example:**

```python
await execute_python('''
import Part
box = Part.makeBox(10, 20, 30)
_result_ = {"volume": box.Volume}
''')
```

### get_freecad_version

Get FreeCAD version and build information.

```python
get_freecad_version() -> dict
```

**Returns:** Version string, build date, Python version, GUI availability.

### get_connection_status

Get the current bridge connection status.

```python
get_connection_status() -> dict
```

**Returns:** Connection state, mode (xmlrpc/socket/embedded), latency.

### get_console_output

Get recent FreeCAD console output.

```python
get_console_output(lines: int = 100) -> list[str]
```

### get_mcp_server_environment

Get environment information about the Robust MCP Server process. Useful for identifying the Robust MCP Server instance via the unique `instance_id`.

```python
get_mcp_server_environment() -> dict
```

**Returns:** Dictionary containing:

- `instance_id`: Unique UUID for this server instance (generated at startup)
- `hostname`: Server hostname
- `os_name`: Operating system name (e.g., "Linux", "Darwin", "Windows")
- `os_version`: OS version/release
- `platform`: Full platform string
- `python_version`: Python version
- `freecad`: FreeCAD connection information (connected, mode, version, gui_available, is_headless)
- `env_vars`: Selected environment variables (FREECAD_MODE, ports, host)

---

## Document Tools

Tools for managing FreeCAD documents.

### list_documents

List all open documents.

```python
list_documents() -> list[dict]
```

### get_active_document

Get the currently active document.

```python
get_active_document() -> dict | None
```

### create_document

Create a new document.

```python
create_document(
    name: str = "Unnamed",
    label: str | None = None
) -> dict
```

### open_document

Open an existing FreeCAD file.

```python
open_document(path: str) -> dict
```

### save_document

Save a document.

```python
save_document(
    doc_name: str | None = None,
    path: str | None = None
) -> dict
```

### close_document

Close a document.

```python
close_document(
    doc_name: str | None = None,
    save_changes: bool = False
) -> dict
```

### recompute_document

Recompute all objects in a document.

```python
recompute_document(doc_name: str | None = None) -> dict
```

---

## Object Tools

Tools for creating and manipulating FreeCAD objects.

### Primitive Creation

#### create_box

Create a parametric box.

```python
create_box(
    length: float = 10.0,
    width: float = 10.0,
    height: float = 10.0,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_cylinder

Create a parametric cylinder.

```python
create_cylinder(
    radius: float = 5.0,
    height: float = 10.0,
    angle: float = 360.0,  # For partial cylinders
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_sphere

Create a parametric sphere.

```python
create_sphere(
    radius: float = 5.0,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_cone

Create a parametric cone.

```python
create_cone(
    radius1: float = 5.0,   # Bottom radius
    radius2: float = 0.0,   # Top radius (0 = pointed)
    height: float = 10.0,
    angle: float = 360.0,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_torus

Create a torus (donut shape).

```python
create_torus(
    radius1: float = 10.0,  # Major radius
    radius2: float = 2.0,   # Minor radius
    angle1: float = -180.0,
    angle2: float = 180.0,
    angle3: float = 360.0,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_wedge

Create a tapered wedge shape.

```python
create_wedge(
    xmin: float = 0.0, ymin: float = 0.0, zmin: float = 0.0,
    x2min: float = 2.0, z2min: float = 2.0,
    xmax: float = 10.0, ymax: float = 10.0, zmax: float = 10.0,
    x2max: float = 8.0, z2max: float = 8.0,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_helix

Create a helix curve (for threads, springs).

```python
create_helix(
    pitch: float = 5.0,
    height: float = 20.0,
    radius: float = 5.0,
    angle: float = 0.0,
    left_handed: bool = False,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Object Management

#### list_objects

List all objects in a document.

```python
list_objects(doc_name: str | None = None) -> list[dict]
```

#### inspect_object

Get detailed information about an object.

```python
inspect_object(
    object_name: str,
    doc_name: str | None = None,
    include_properties: bool = True,
    include_shape: bool = True
) -> dict
```

#### create_object

Create a generic FreeCAD object by type ID.

```python
create_object(
    type_id: str,  # e.g., "Part::Box", "Sketcher::SketchObject"
    name: str | None = None,
    properties: dict[str, Any] | None = None,
    doc_name: str | None = None
) -> dict
```

#### edit_object

Modify object properties.

```python
edit_object(
    object_name: str,
    properties: dict[str, Any],
    doc_name: str | None = None
) -> dict
```

#### delete_object

Delete an object.

```python
delete_object(
    object_name: str,
    doc_name: str | None = None
) -> dict
```

### Boolean Operations

#### boolean_operation

Perform boolean operations (union, subtract, intersect).

```python
boolean_operation(
    operation: str,      # "fuse", "cut", or "common"
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
    doc_name: str | None = None
) -> dict
```

**Operations:**

- `fuse` - Union/combine shapes
- `cut` - Subtract object2 from object1
- `common` - Intersection of shapes

### Transformations

#### set_placement

Set object position and rotation.

```python
set_placement(
    object_name: str,
    position: list[float] | None = None,  # [x, y, z]
    rotation: list[float] | None = None,  # [yaw, pitch, roll] in degrees
    doc_name: str | None = None
) -> dict
```

#### rotate_object

Rotate object around an axis.

```python
rotate_object(
    object_name: str,
    axis: list[float],      # [x, y, z] rotation axis
    angle: float,           # Degrees
    center: list[float] | None = None,
    doc_name: str | None = None
) -> dict
```

#### scale_object

Scale an object (creates new copy).

```python
scale_object(
    object_name: str,
    scale: float | list[float],  # Uniform or [sx, sy, sz]
    result_name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### copy_object

Create a copy of an object.

```python
copy_object(
    object_name: str,
    new_name: str | None = None,
    offset: list[float] | None = None,  # [x, y, z]
    doc_name: str | None = None
) -> dict
```

#### mirror_object

Mirror object across a plane.

```python
mirror_object(
    object_name: str,
    plane: str = "XY",  # "XY", "XZ", or "YZ"
    result_name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Selection (GUI Mode)

#### get_selection

Get currently selected objects.

```python
get_selection(doc_name: str | None = None) -> list[dict]
```

#### set_selection

Select objects programmatically.

```python
set_selection(
    object_names: list[str],
    clear_existing: bool = True,
    doc_name: str | None = None
) -> dict
```

#### clear_selection

Clear the current selection.

```python
clear_selection() -> dict
```

---

## PartDesign Tools

Tools for parametric solid modeling using the PartDesign workbench.

### Bodies and Sketches

#### create_partdesign_body

Create a PartDesign Body container.

```python
create_partdesign_body(
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_sketch

Create a sketch attached to a Body origin plane, explicit face, or datum plane.

```python
create_sketch(
    body_name: str | None = None,
    plane: str = "XY_Plane",  # origin plane, "FaceN", "Object.FaceN", or datum name
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Sketch Geometry

#### add_sketch_rectangle

Add a rectangle to a sketch.

```python
add_sketch_rectangle(
    sketch_name: str,
    x: float, y: float,       # Bottom-left corner
    width: float, height: float,
    doc_name: str | None = None
) -> dict
```

#### add_sketch_circle

Add a circle to a sketch.

```python
add_sketch_circle(
    sketch_name: str,
    center_x: float, center_y: float,
    radius: float,
    doc_name: str | None = None
) -> dict
```

#### add_sketch_line

Add a line to a sketch.

```python
add_sketch_line(
    sketch_name: str,
    x1: float, y1: float,  # Start point
    x2: float, y2: float,  # End point
    construction: bool = False,
    doc_name: str | None = None
) -> dict
```

#### add_sketch_arc

Add an arc to a sketch.

```python
add_sketch_arc(
    sketch_name: str,
    center_x: float, center_y: float,
    radius: float,
    start_angle: float,  # Degrees
    end_angle: float,    # Degrees
    doc_name: str | None = None
) -> dict
```

#### add_sketch_point

Add a reference point to a sketch. For `create_hole`, use circles instead.

```python
add_sketch_point(
    sketch_name: str,
    x: float, y: float,
    doc_name: str | None = None
) -> dict
```

### Additive Features

All four additive tools return `validated`, `base_volume`, `result_volume`,
`added_volume`, and `solid_count`. They roll back if the result is not one valid
solid or the Body volume fails to increase.

#### pad_sketch

Extrude a sketch to create material. For direction-sensitive pads, prefer `direction=[x, y, z]`; the tool resolves `Reversed` from the sketch global normal and reports the effective world-space direction.

```python
pad_sketch(
    sketch_name: str,
    length: float,
    symmetric: bool = False,
    reversed: bool = False,
    direction: list[float] | None = None,  # desired world-space direction
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### revolution_sketch

Revolve a sketch around an axis.

```python
revolution_sketch(
    sketch_name: str,
    angle: float = 360.0,
    axis: str = "Base_X",  # "Base_X/Y/Z" or "Sketch_V/H"
    symmetric: bool = False,
    reversed: bool = False,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### loft_sketches

Loft through multiple sketches.

```python
loft_sketches(
    sketch_names: list[str],
    ruled: bool = False,
    closed: bool = False,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### sweep_sketch

Sweep a profile along a path.

```python
sweep_sketch(
    profile_sketch: str,
    spine_sketch: str,
    transition: str = "Transformed",  # "Transformed", "Right", "Round"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Subtractive Features

#### pocket_sketch

Cut material by extruding a sketch.

```python
pocket_sketch(
    sketch_name: str,
    length: float,
    type: str = "Length",  # "Length", "ThroughAll", "UpToFirst", "UpToFace"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### groove_sketch

Cut material by revolving a sketch.

```python
groove_sketch(
    sketch_name: str,
    angle: float = 360.0,
    axis: str = "Base_X",
    symmetric: bool = False,
    reversed: bool = False,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_hole

Create parametric holes with optional threading and strict post-validation. Use a new sketch containing only non-construction circles. Prefer attachment to an actual planar solid face such as `Pad_Base.Face8`; origin planes are allowed but may be ambiguous in a complex Body. Datum-plane sketches are rejected because `PartDesign::Hole` can become a geometrically ineffective no-op in FreeCAD 1.0.x. Use `create_cylindrical_cut` for radial or off-face holes.

The call rolls back unless the result is one valid solid, body volume decreases,
and geometric probes confirm that material was removed at every profile-circle
location. A sketch can be consumed only once.

```python
create_hole(
    sketch_name: str,        # Unused sketch with non-construction circles
    diameter: float = 6.0,
    depth: float = 10.0,
    hole_type: str = "Dimension",  # "Dimension" or "ThroughAll"
    threaded: bool = False,
    thread_type: str = "ISO",  # "ISO", "ISO_FINE", "UNC", "UNF"
    thread_size: str = "M6",
    drill_point: str = "Flat",  # "Flat" or "Angled" for blind holes
    reversed: bool | None = None,  # None = try both directions automatically
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### create_cylindrical_cut

Create a cylindrical cut from an explicit world-space start point and axis.
This is the preferred tool for radial oil holes, tangent-plane holes, and other
cuts that do not start from an actual planar face. A datum plane is not needed.

```python
create_cylindrical_cut(
    body_name: str,
    axis_origin: list[float],      # [x, y, z], cylinder starts here
    axis_direction: list[float],   # [dx, dy, dz], normalized internally
    diameter: float,
    depth: float,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Edge Operations

#### fillet_edges

Add rounded edges.

```python
fillet_edges(
    object_name: str,
    radius: float,
    edges: list[str] | None = None,  # ["Edge1", "Edge2"] or None for all
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### chamfer_edges

Add beveled edges.

```python
chamfer_edges(
    object_name: str,
    size: float,
    edges: list[str] | None = None,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

### Patterns

#### linear_pattern

Repeat a feature in a linear direction.

```python
linear_pattern(
    feature_name: str,
    direction: str = "X",  # "X", "Y", "Z"
    length: float = 50.0,
    occurrences: int = 3,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### polar_pattern

Repeat a feature around an axis.

```python
polar_pattern(
    feature_name: str,
    axis: str = "Z",  # "X", "Y", "Z"
    angle: float = 360.0,
    occurrences: int = 6,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### mirrored_feature

Mirror a feature across a plane.

```python
mirrored_feature(
    feature_name: str,
    plane: str = "XY",  # "XY", "XZ", "YZ"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

---

## Export Tools

Tools for importing and exporting CAD files.

### export_step

Export objects to STEP format.

```python
export_step(
    file_path: str,
    object_names: list[str] | None = None,  # None = all visible
    doc_name: str | None = None
) -> dict
```

### export_stl

Export objects to STL format (for 3D printing).

```python
export_stl(
    file_path: str,
    object_names: list[str] | None = None,
    doc_name: str | None = None,
    mesh_tolerance: float = 0.1
) -> dict
```

### export_3mf

Export objects to 3MF format (modern 3D printing format).

3MF (3D Manufacturing Format) supports richer data than STL, including colors, materials, and print settings. It is increasingly preferred over STL for 3D printing.

```python
export_3mf(
    file_path: str,
    object_names: list[str] | None = None,
    doc_name: str | None = None,
    mesh_tolerance: float = 0.1
) -> dict
```

### export_obj

Export objects to OBJ format.

```python
export_obj(
    file_path: str,
    object_names: list[str] | None = None,
    doc_name: str | None = None
) -> dict
```

### export_iges

Export objects to IGES format.

```python
export_iges(
    file_path: str,
    object_names: list[str] | None = None,
    doc_name: str | None = None
) -> dict
```

### import_step

Import a STEP file.

```python
import_step(
    file_path: str,
    doc_name: str | None = None
) -> dict
```

### import_stl

Import an STL file.

```python
import_stl(
    file_path: str,
    doc_name: str | None = None
) -> dict
```

---

## View Tools

Tools for controlling the 3D view and capturing screenshots.

### Screenshots

#### get_screenshot

Capture a screenshot of the 3D view.

**Requires GUI mode.**

```python
get_screenshot(
    view_angle: str = "Isometric",
    width: int = 800,
    height: int = 600,
    doc_name: str | None = None,
    fit_all: bool = True,
    background: str = "White",
    show_corner_cross: bool = True,
    corner_cross_size: int = 10,
    save_to_disk: bool = False,
    output_path: str | None = None,
    return_image: bool = True,
    return_data: bool = False,  # Legacy base64 metadata only
) -> CallToolResult
```

With `return_image=True`, the result contains real MCP `ImageContent`, so a
multimodal agent can inspect the pixels. A path or base64 string shown as text
is not equivalent to visual context.

`show_corner_cross=True` is the default. It adds the global X/Y/Z orientation
indicator to the lower-right corner of the PNG. FreeCAD's native corner cross is
a screen-space feedback decoration and is not reliably included by
`View3DInventorPy.saveImage`; the MCP screenshot pipeline therefore derives the
axis directions from the active camera orientation and composites the triad into
the saved PNG with Qt `QImage`/`QPainter`.

`corner_cross_size` is an approximate percentage of the canvas and accepts
values from 1 to 100. Set `show_corner_cross=False` only for clean presentation
images. Any native interactive-view setting is restored after capture.

**View angles:** `Isometric`, `Front`, `Back`, `Top`, `Bottom`, `Left`, `Right`, `FitAll`

#### open_image

Open a local drawing or saved screenshot and return its pixels to the agent.

```python
open_image(path: str, max_dimension: int = 4096) -> CallToolResult
```

Supported formats: PNG, JPEG, WebP. Relative paths are resolved from the MCP
server working directory. Local file access must be enabled.

#### compare_images

Create a labelled side-by-side image with `REFERENCE` on the left and
`CANDIDATE` on the right, then return it as MCP `ImageContent`.

```python
compare_images(
    reference_path: str,
    candidate_path: str,
    panel_width: int = 1200,
    panel_height: int = 900,
    output_path: str | None = None,
) -> CallToolResult
```

This is a visual comparison aid; it does not claim automatic geometric
alignment or a correctness score.

### View Control

#### set_view_angle

Set the 3D view angle.

```python
set_view_angle(
    view_angle: str,  # Same options as get_screenshot
    doc_name: str | None = None
) -> dict
```

#### fit_all

Fit all objects in the view.

```python
fit_all(doc_name: str | None = None) -> dict
```

#### zoom_in / zoom_out

Zoom the view.

**Requires GUI mode.**

```python
zoom_in(factor: float = 1.5, doc_name: str | None = None) -> dict
zoom_out(factor: float = 1.5, doc_name: str | None = None) -> dict
```

#### set_camera_position

Set custom camera position.

**Requires GUI mode.**

```python
set_camera_position(
    position: list[float],     # [x, y, z]
    look_at: list[float] | None = None,  # Default: origin
    doc_name: str | None = None
) -> dict
```

### Object Appearance

#### set_object_visibility

Show or hide an object.

**Requires GUI mode.**

```python
set_object_visibility(
    object_name: str,
    visible: bool,
    doc_name: str | None = None
) -> dict
```

#### set_display_mode

Set object display mode.

**Requires GUI mode.**

```python
set_display_mode(
    object_name: str,
    mode: str,  # "Flat Lines", "Shaded", "Wireframe", "Points"
    doc_name: str | None = None
) -> dict
```

#### set_object_color

Set object color.

**Requires GUI mode.**

```python
set_object_color(
    object_name: str,
    color: list[float],  # [r, g, b] where values are 0.0-1.0
    doc_name: str | None = None
) -> dict
```

### Workbenches

#### list_workbenches

List available workbenches.

```python
list_workbenches() -> list[dict]
```

#### activate_workbench

Activate a workbench.

```python
activate_workbench(workbench_name: str) -> dict
```

**Common workbenches:**

- `PartWorkbench` - Part modeling
- `PartDesignWorkbench` - Parametric design
- `SketcherWorkbench` - 2D sketching
- `DraftWorkbench` - 2D drafting
- `MeshWorkbench` - Mesh operations

### Undo/Redo

#### undo / redo

Undo or redo operations.

```python
undo(doc_name: str | None = None) -> dict
redo(doc_name: str | None = None) -> dict
```

#### get_undo_redo_status

Get undo/redo availability.

```python
get_undo_redo_status(doc_name: str | None = None) -> dict
```

### Parts Library

#### list_parts_library

List available library parts.

```python
list_parts_library() -> list[dict]
```

#### insert_part_from_library

Insert a part from the library.

```python
insert_part_from_library(
    part_path: str,
    name: str | None = None,
    position: list[float] | None = None,
    doc_name: str | None = None
) -> dict
```

### Utility

#### get_console_log

Get FreeCAD console output.

```python
get_console_log(lines: int = 50) -> dict
```

#### recompute

Force recompute of all objects.

```python
recompute(doc_name: str | None = None) -> dict
```

---

## Macro Tools

Tools for managing FreeCAD macros.

### list_macros

List available macros.

```python
list_macros() -> list[dict]
```

### run_macro

Execute a macro by name.

```python
run_macro(
    macro_name: str,
    args: dict[str, Any] | None = None
) -> dict
```

### create_macro

Create a new macro.

```python
create_macro(
    name: str,
    code: str,
    description: str = ""
) -> dict
```

### read_macro

Read macro contents.

```python
read_macro(macro_name: str) -> dict
```

### delete_macro

Delete a user macro.

```python
delete_macro(macro_name: str) -> dict
```

### create_macro_from_template

Create macro from a predefined template.

```python
create_macro_from_template(
    name: str,
    template: str = "basic",  # "basic", "part", "sketch", "gui", "selection"
    description: str = ""
) -> dict
```

---

## GUI vs Headless Mode

Some tools require FreeCAD to be running in GUI mode. When running in headless mode, these tools will return an error instead of crashing.

**GUI-only tools:**

- `get_screenshot`
- `set_object_visibility`
- `set_display_mode`
- `set_object_color`
- `zoom_in` / `zoom_out`
- `set_camera_position`
- `get_selection` / `set_selection` / `clear_selection`

**To check mode programmatically:**

```python
result = await execute_python("_result_ = FreeCAD.GuiUp")
is_gui_mode = result["result"]
```

---

## Error Handling

All tools return dictionaries with consistent error handling:

**Success:**

```python
{
    "success": True,
    "name": "Box",
    "volume": 6000.0,
    # ... other fields
}
```

**Failure:**

```python
{
    "success": False,
    "error": "Object not found: MissingBox"
}
```

For tools that raise exceptions, wrap calls in try/except or check the returned error field.
