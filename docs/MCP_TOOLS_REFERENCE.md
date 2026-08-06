# FreeCAD Robust MCP Server Tools Reference

This document provides detailed signatures and examples for core MCP tools. It is not the exact inventory of all registered tools. Use [Tools Overview](guide/tools.md) or the MCP client's discovered tool list for the authoritative 116-tool inventory.

---

## Overview

The FreeCAD Robust MCP Server exposes tools organized into the following categories:

The exact generated inventory is grouped as follows:

| Category | Tool Count |
| --- | ---: |
| Execution | 5 |
| Documents | 7 |
| Objects / Part | 33 |
| PartDesign / Sketcher | 28 |
| Spreadsheet | 11 |
| Draft | 6 |
| Images | 3 |
| Checkpoints | 1 |
| View / GUI / History | 9 |
| Validation | 5 |
| Export / Import | 2 |
| Macros | 6 |
| **Total** | **116** |

The sections below retain deeper examples for commonly used tools; they do not repeat every generated entry.

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

#### create_primitive

Create one supported Part primitive through a single typed entry point.

```python
create_primitive(
    primitive: PrimitiveSpec,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

`PrimitiveSpec.kind` accepts `box`, `cylinder`, `sphere`, `cone`, `torus`,
`wedge`, or `helix`. Each kind has its own strict parameter schema; dimensions
from another primitive kind are rejected instead of being silently ignored.

```python
create_primitive(
    primitive={
        "kind": "box",
        "length": 20.0,
        "width": 10.0,
        "height": 5.0
    },
    name="Base"
)
```

The tool validates relevant dimensions before creating the FreeCAD object.

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
    include_properties: bool = False,
    include_shape: bool = True
) -> dict
```

For routine structure, dependency, bounds, or shape inspection, explicitly use
`include_properties=False`. Set it to `True` only when exact property values are
needed for a specific diagnosis or edit; the complete property map can be large.

With `include_shape=True`, `shape_info.faces` includes `surface_type`, an
oriented normal sampled at a representative point, `area`, `center`, adjacent
`FaceN` references, local `convexity`, and
participating edges. `shape_info.edges` includes `curve_type`, start/end points,
length, radius when available, direction, and adjacent faces. `convexity` describes
the local surface curvature at a representative point (`flat`, `convex`,
`concave`, `saddle`, or `unknown`); it is not an assertion about manufacturability.

#### select_subshapes

Select topology without writing manual loops over `Shape.Faces` or `Shape.Edges`.
The result contains semantic records plus ready-to-use `FaceN`/`EdgeN` references.
Use it before face-supported sketches, Fillet, Chamfer, Draft, or Thickness.

```python
select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "face",
        "surface_types": ["Plane"],
        "normal": [0, 0, 1],
        "normal_tolerance_deg": 2,
        "sort_by": "center_z",
        "sort_order": "desc",
        "limit": 1,
    },
)

select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "edge",
        "curve_types": ["Line"],
        "direction": [1, 0, 0],
        "length_min": 20,
        "adjacent_surface_types": ["Plane"],
        "sort_by": "length",
        "sort_order": "desc",
        "limit": 4,
    },
)
```

Line direction is treated as undirected, so `[1, 0, 0]` also matches an edge
stored from right to left. Type names are case-insensitive and accept common
forms such as `planar`/`Plane`, `circular`/`Circle`, and
`LineSegment`/`Line`. When `adjacent_surface_types` contains several entries,
every listed type must occur among the edge's adjacent faces.

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

Modify object properties. For `App::PropertyLink`, `LinkList`, `LinkSub`, and `LinkSubList` properties, string object names such as `"Pad"` or `"Pad.Face3"` are resolved through the selected document before assignment. Non-link string properties remain unchanged.

```python
edit_object(
    object_name: str,
    properties: dict[str, Any],
    doc_name: str | None = None
) -> dict
```

For `Body.Tip`, prefer `set_body_tip`: it verifies Body membership, one valid solid, positive volume, recompute state, and the final Tip link. `edit_object` provides flexible type-aware assignment but does not replace feature-specific validation.

When changing `PartDesign::Hole.ThreadType`, include `ThreadSize` in the same
call. FreeCAD resets `ThreadSize` when the profile enumeration changes, so the
tool applies these dependent properties in safe order and rejects a profile-only
edit. Friendly values such as `ISO_FINE` are accepted:

```python
edit_object(
    object_name="Hole",
    properties={"ThreadType": "ISO_FINE", "ThreadSize": "M12x1.25"},
)
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

#### selection

Get, set, or clear the FreeCAD GUI selection through one entry point.

```python
selection(
    action: Literal["get", "set", "clear"],
    object_names: list[str] | None = None,
    clear_existing: bool = True,
    doc_name: str | None = None,
) -> dict
```

For `action="set"`, provide at least one object name. The result reports selected
and missing object names rather than silently ignoring unresolved references.

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
    support: SketchSupport | None = None,
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

Use the discriminated `support` object:

```python
{"kind": "origin_plane", "plane": "XY_Plane"}
{"kind": "body_tip_face", "face": "Face6"}
{"kind": "feature_face", "feature": "Pad", "face": "Face6"}
{"kind": "datum_plane", "name": "DP_OilHole"}
```

If `support` is omitted, the sketch defaults to the `XY_Plane` origin support.
The result includes the resolved FreeCAD `support` reference and
`support_kind`.

#### set_body_tip

Set the active result of a Body to an existing single-solid feature. The tool validates Body membership, Shape validity, one-solid topology, and the final Tip assignment; it restores the previous Tip on failure.

```python
set_body_tip(
    body_name: str,
    feature_name: str,
    doc_name: str | None = None,
) -> dict
```

### Sketch Geometry and Constraints

#### edit_sketch_geometry

Apply an ordered batch of sketch geometry edits in one FreeCAD transaction and
one recompute. Supported `op` values are:

- `add_rectangle`, `add_circle`, `add_line`, `add_arc`, `add_point`;
- `add_ellipse`, `add_regular_polygon`, `add_polyline`, `add_slot`, `add_bspline`;
- `add_external_geometry`, `delete_geometry`, `toggle_construction`.

```python
edit_sketch_geometry(
    sketch_name: str,
    operations: list[SketchGeometryOperation],
    doc_name: str | None = None,
) -> dict
```

Example:

```python
edit_sketch_geometry(
    sketch_name="BaseSketch",
    operations=[
        {"op": "add_rectangle", "x": 0, "y": 0, "width": 80, "height": 60},
        {"op": "add_circle", "center_x": 15, "center_y": 30, "radius": 3},
        {"op": "add_circle", "center_x": 65, "center_y": 30, "radius": 3},
        {"op": "add_regular_polygon", "center_x": 40, "center_y": 30, "radius": 8, "sides": 6},
        {"op": "add_polyline", "points": [[0, 0], [10, 0], [10, 5]], "closed": False},
    ],
)
```

`add_regular_polygon` creates a center/radius-based regular polygon inside an existing Sketcher sketch. `add_polyline` creates an explicit open or closed chain of Sketcher line segments. They are intentionally separate operations; the former does not accept arbitrary vertices.

`add_arc` supports three modes. `center_angles` remains the default legacy form.
The two radius-driven forms are:

```python
# Arc through two endpoints with known radius. arc_side chooses the side of the
# directed chord (x1, y1) -> (x2, y2) that contains the minor arc.
edit_sketch_geometry(
    sketch_name="Sketch",
    operations=[{
        "op": "add_arc",
        "arc_mode": "endpoints_radius",
        "x1": 0,
        "y1": 0,
        "x2": 20,
        "y2": 0,
        "radius": 15,
        "arc_side": "left",  # or "right"
    }],
)

# Tangent arc between two existing line segments with known radius. The native
# Sketcher fillet operation trims both lines and inserts the connecting arc.
edit_sketch_geometry(
    sketch_name="Sketch",
    operations=[{
        "op": "add_arc",
        "arc_mode": "tangent_fillet",
        "line1_index": 0,
        "line2_index": 1,
        "radius": 4,
    }],
)
```

For `endpoints_radius`, the chord may not exceed the diameter. For
`tangent_fillet`, create or identify both line segments first and pass their
current geometry indices; an impossible radius is rejected rather than silently
approximated.

These do not duplicate the standalone Part tools: `create_regular_polygon` creates a `Part::RegularPolygon` document object, while `make_wire` creates a 3D `Part::Feature` wire from `[x, y, z]` points. Use the sketch operations for PartDesign profiles and the standalone tools for Part workbench geometry.

The result contains one entry per operation and the final sketch solver/profile
status. Invalid operation payloads are rejected before FreeCAD is modified.
`operations` is a discriminated union keyed by `op`, so MCP clients receive the
required fields for each variant. Every operation that creates local sketch
geometry accepts `construction=true`; compound operations apply it to every
created segment. `add_arc` returns `point_indices` mapping the requested
`start`, `end`, and `center` roles to Sketcher's point positions, avoiding
assumptions when a FreeCAD build canonicalizes arc orientation.

#### edit_sketch_constraints

Apply an ordered batch of constraint additions or deletions in one transaction
and one recompute. Supported `op` values are:

- `horizontal`, `vertical`, `coincident`, `parallel`, `perpendicular`;
- `tangent`, `equal`, `distance`, `distance_x`, `distance_y`;
- `radius`, `angle`, `fix`, `delete_constraint`;
- `set_expression` and `clear_expression` for existing constraints;
- `add_constraint` for a Sketcher constraint type not covered above.

```python
edit_sketch_constraints(
    sketch_name: str,
    operations: list[SketchConstraintOperation],
    doc_name: str | None = None,
) -> dict
```

The total number of `fix`/generic `Block` constraints may not exceed 50% of
`sketch.GeometryCount`. If the next Fix would exceed the limit, use geometric or
dimensional constraints, or delete existing Fix/Block constraints first.

Example:

```python
edit_sketch_constraints(
    sketch_name="BaseSketch",
    operations=[
        {"op": "horizontal", "geometry1": 0},
        {"op": "vertical", "geometry1": 1},
        {
            "op": "distance",
            "geometry1": 0,
            "value": 80,
            "constraint_name": "PlateWidth",
            "expression": "Dimensions.PlateWidth",
        },
    ],
)
```

The Spreadsheet cell must have an alias before it can be referenced. Bind a
constraint by its generated path, not by assigning the Spreadsheet to geometry:

```text
Spreadsheet cell A1 = 80 mm; alias = PlateWidth
Sketch expression path = Constraints[2]
Expression = Dimensions.PlateWidth
```

`constraint_name` improves readability, while the tool attaches the expression
through `Constraints[index]`. FreeCAD may later report the same binding through
a canonical named path in `ExpressionEngine`. To edit an existing binding:

```python
edit_sketch_constraints(
    sketch_name="BaseSketch",
    operations=[
        {"op": "set_expression", "constraint_index": 2,
         "expression": "Dimensions.PlateWidth - 2 mm"},
        {"op": "clear_expression", "constraint_index": 5},
    ],
)
```

Use explicit units in constants inside expressions (`2 mm`, `15 deg`). The
Spreadsheet alias itself may already carry units.

All MCP fields named `constraint_index` are **zero-based**, matching
`SketchObject.Constraints` and `Constraints[index]`. FreeCAD's GUI and solver
messages often display one-based constraint numbers. Results therefore include
both `constraint_index` and `constraint_number`; solver diagnostics expose
`indices` (zero-based MCP values) and `numbers` (one-based GUI values). For
example, GUI constraint 16 is deleted with `constraint_index=15`.

#### get_sketch_info

```python
get_sketch_info(sketch_name="BaseSketch", doc_name="Model")
```

The result includes:

- `geometry`: indexed geometry with `geometry_type`, `start_point`, `end_point`,
  construction state, and type-specific data such as center/radius;
- `constraints`: indexed constraint type, referenced geometry/points, datum,
  name, driving state, and attached expression;
- `expressions`: stable path/expression pairs; constraint bindings use
  `Constraints[index]`, with FreeCAD's original path preserved as optional
  `source_path` when it differs;
- `sketch_status`: solver, remaining degrees of freedom, and profile closure.

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

Sweep a profile along a path. Profile and spine must be different sketches in
the same Body; the profile must contain a closed wire and the spine at least one
edge. The result is committed only after additive-volume and solid validation.

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
    direction: str = "normal",  # "normal" or "reversed"
    base_feature_name: str | None = None,
    up_to_face: str | None = None,  # required for UpToFace: "Pad.Face3"
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

`direction` is relative to the sketch normal and does not depend on GUI
selection: `normal` cuts along the positive global sketch normal and `reversed`
along the negative normal. The tool translates this to Pocket's inverted
internal `Reversed` convention and reports the actual global
`effective_direction`. `base_feature_name` is authoritative when supplied.
Without it, the tool uses a valid preceding Body Tip when possible, then the
nearest valid preceding single-solid feature. `type="UpToFace"` requires an
explicit and prevalidated `up_to_face="Feature.FaceN"`; supplying that parameter
for another type is rejected. The response reports `base_feature`,
`base_selection`, Shape/Tip evidence, and before/after volume diagnostics.

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

#### subtractive_loft

Cut material through at least two distinct closed profile sketches in the same
Body. An existing valid solid must precede the profiles. The tool validates a
real positive volume decrease and rolls the feature back on failure.

```python
subtractive_loft(
    sketch_names: list[str],
    ruled: bool = False,
    closed: bool = False,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### subtractive_pipe

Sweep a closed profile along a different path sketch in the same Body. The path
must contain at least one edge and an existing solid must precede both sketches.
The operation is accepted only when it removes measurable material and leaves
one valid solid as the Body Tip.

```python
subtractive_pipe(
    profile_sketch: str,
    spine_sketch: str,
    transition: str = "Transformed",  # "Transformed", "Right", "Round"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

#### thread_helix

Create native editable helical thread geometry from a closed profile sketch. Use `additive` for an external thread and `subtractive` for an internal thread or groove. This tool creates geometry; it does not infer a standard thread profile or tolerance class.

```python
thread_helix(
    sketch_name: str,
    pitch: float,
    height: float,
    operation: str = "additive",  # "additive" or "subtractive"
    axis: str = "Sketch_H",       # Base_X/Y/Z or Sketch_V/H
    left_handed: bool = False,
    reversed: bool = False,
    base_feature_name: str | None = None,
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

The response includes the resolved base, axis, turn count, Shape/Tip status, and volume diagnostics.

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

`ISO_FINE` is normalized to FreeCAD's `ISOMetricFineProfile` enumeration before
the requested `thread_size` is selected. The size is validated against the
enumeration advertised by the running FreeCAD build.

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

Add rounded edges. For a PartDesign object, the source must be the current
Body Tip. `EdgeN` references are validated before mutation; after recompute the
result must be one valid solid and the new Body Tip, otherwise the feature is
removed and the previous Tip is restored.

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

Add beveled edges. The same current-Tip, `EdgeN`, post-recompute, and rollback
contract used by `fillet_edges` applies.

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

Repeat one non-pattern feature in a linear direction. The result is rolled back when Shape is null/invalid, does not contain exactly one solid, or is not the Body Tip.

When reconstructing from a drawing/image, first compare the single seed feature
with the corresponding reference view using `compare_images`. Do not multiply a
seed whose profile, placement, orientation, or dimensions have not been visually
accepted.

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

Repeat one non-pattern feature around an axis. The result is rolled back when Shape is null/invalid, does not contain exactly one solid, or is not the Body Tip.

The same mandatory seed comparison applies before polar, mirrored, and combined
multi-transform patterns.

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

Both single-pattern tools use the first `TransformMode` enumeration entry advertised by the running FreeCAD build. This is the feature-transform mode, but its displayed label differs between FreeCAD versions (for example, `Features` or `Transform tool shapes`). The API contract still treats `feature_name` as an additive/subtractive seed rather than the whole Body. Responses keep `transform_mode` as the selected string and add `transform_mode_options` for diagnostics. They return `base_volume`, `result_volume`, and `volume_diagnostics`. They also compare the actual volume delta with the effective transformed `AddSubShape` and return `material_change_diagnostics`. When that causal check is available and inconsistent, the feature is rolled back even if OpenCASCADE reports a formally valid solid. The neutral retained/change ratios remain evidence for the agent rather than a general proof of design intent. Applying a pattern directly to another pattern is rejected with guidance to use `multi_transform_pattern`.

#### multi_transform_pattern

Combine two or more linear/polar stages in one native `PartDesign::MultiTransform`. This is the supported replacement for `linear_pattern(polar_pattern(...))` or the reverse chain.

```python
multi_transform_pattern(
    feature_name: str,
    transformations: list[dict],
    name: str | None = None,
    doc_name: str | None = None,
) -> dict

# Example stages
[
    {"kind": "linear", "direction": "X", "length": 52, "occurrences": 3},
    {"kind": "polar", "axis": "X", "angle": 360, "occurrences": 12},
]
```

Internal transformation stages are owned by the MultiTransform and intentionally have no separate `Originals`; the original seed is assigned once to the parent feature. The final MultiTransform receives the same Shape, Body Tip, volume-ratio, and causal `AddSubShape` checks as the single-pattern tools.

#### mirrored_feature

Mirror the current Body Tip across a plane. The source must be one valid solid;
the mirrored feature is rolled back when recompute reports an error, an invalid
Shape, multiple/no solids, or a Body-Tip mismatch.

```python
mirrored_feature(
    feature_name: str,
    plane: str = "XY",  # "XY", "XZ", "YZ"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

---

## Spreadsheet Tools

### spreadsheet_apply_batch

Apply cell values, aliases, and object-property bindings to an existing Spreadsheet in one transaction and one final recompute. Use this instead of dozens of independent setter calls when creating a parameter table. Binding targets, properties, aliases, duplicate entries, and alias collisions are validated before mutation. Because FreeCAD 1.0 does not roll Spreadsheet mutations back on `abortTransaction()`, the tool snapshots and explicitly restores affected cells, aliases, and expressions if any operation fails.

```python
spreadsheet_apply_batch(
    spreadsheet_name: str,
    cells: list[dict] | None = None,       # {"cell": "B2", "value": "42 mm"}
    aliases: list[dict] | None = None,     # {"cell": "B2", "alias": "Length"}
    bindings: list[dict] | None = None,    # {"alias": "Length", "target_object": "Pad", "target_property": "Length"}
    doc_name: str | None = None,
) -> dict
```

At least one non-empty list is required. Aliases created in the same batch may immediately be used by bindings.
Retries are idempotent, including aliases that already point to the requested
cell. When a unitless Spreadsheet value is bound to an `App::PropertyAngle`
such as `PartDesign::PolarPattern.Angle`, the generated expression multiplies
the value by `1 deg`; a cell that already has an angle unit is bound directly.
After recompute the batch verifies every updated formula. Encoded values such as
`ERR:`, `#ERR`, `#REF!`, or an invalid-expression diagnostic cause rollback
rather than a successful response. In GUI mode the bridge flushes posted Qt
events before reading the per-request Report View delta; high-confidence Spreadsheet errors
are returned as `FreeCADReportError` even when FreeCAD's Python API did not
raise an exception.

`spreadsheet_get_aliases` enumerates actual Spreadsheet cells (not ordinary
FreeCAD object properties). `spreadsheet_clear_cell` is idempotent and reports
the removed alias. By default it refuses to clear a cell referenced by any
expression; pass `clear_bindings=True` to detach those expressions explicitly
in the same transaction. The tool verifies that content, alias, and dependent
bindings are gone before returning success.

---

## Export / Import Tools

Two tools cover all supported exchange formats.

### export

Export objects to STEP, IGES, STL, 3MF, or OBJ.

```python
export(
    file_format: Literal["step", "iges", "stl", "3mf", "obj"],
    file_path: str,
    object_names: list[str] | None = None,
    doc_name: str | None = None,
    mesh_tolerance: float = 0.1
) -> dict
```

`mesh_tolerance` is used only for STL, 3MF, and OBJ. STEP and IGES preserve
BREP geometry.

### import

Import STEP or STL. `import` is the MCP tool name; it is not a Python function
identifier.

```text
Tool: import
Arguments:
  file_format: "step" | "stl"
  file_path: string
  doc_name: string | null
```

Both formats return a consistent `objects` list containing every newly imported
object.

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
    settle_time_seconds: float = 2.0,
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

`settle_time_seconds=2.0` is the default. After setting the camera and running
`fitAll`, the generated FreeCAD-side code processes GUI events and redraws the
view during this interval before calling `saveImage`. This prevents a screenshot
from capturing a stale orientation or incomplete fit. Values from 0 to 10 are
accepted; use 0 only when the view is already stable or in controlled tests.

**View/plane correspondence:**

| View | Projection plane | Normal/depth axis |
|---|---|---|
| Front / Back | XZ | Y |
| Top / Bottom | XY | Z |
| Left / Right | YZ (ZOY) | X |
| Isometric | no true-shape plane | verification only |

**View angles:** `Isometric`, `Front`, `Back`, `Top`, `Bottom`, `Left`, `Right`, `FitAll`

#### open_image

Open a local drawing or saved screenshot and return its pixels to the agent.

```python
open_image(path: str, max_dimension: int = 4096) -> CallToolResult
```

Supported formats: PNG, JPEG, WebP. Relative paths are resolved from the MCP
server working directory. Local file access must be enabled.

#### open_image_tiles

Return a numbered overview and ordered, enlarged, overlapping fragments.

```python
open_image_tiles(
    path: str,
    rows: int = 2,
    columns: int = 3,
    overlap_percent: float = 12.0,
    tile_max_dimension: int = 1600,
    include_overview: bool = True,
    save_to_disk: bool = True,
    output_dir: str | None = None,
) -> CallToolResult
```

The result contains one text block before every image, identifying the fragment
number, grid position, source pixel rectangle, overlap, and resize scale. The
overview preserves global context while every fragment is delivered as a separate
MCP image block with an explicit prompt describing what region it represents.
Cropping gives small drawing details a larger visual budget; upscaling does not
recover information absent from the source. A maximum of nine tiles is allowed.
Tiles are saved by default under
`./image_tiles/<source>_<grid>` so `compare_images` can use an exact reference
fragment instead of the whole sheet.

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
    view_context: str | None = None,
) -> CallToolResult
```

This is a visual comparison aid; it does not perform geometric alignment or
calculate a correctness score. For drawing/image reconstruction it is mandatory
after every major feature; saving or opening a screenshot alone is not a complete
visual checkpoint. Reference and candidate must show equivalent views. Crop a
complete drawing sheet to the matching target view before comparison; a full
sheet versus one model screenshot is weak evidence. Use
`view_context`, for example `"Left / YZ plane / normal X"`, so the panel labels
carry the active view/plane contract.

A match in one projection does not prove depth or feature-axis orientation. If
similarity is uncertain, repeat same-view comparisons for every principal target
view available: front, matching left/right side, top, then isometric. A formal
discrepancy ledger and `evaluate_model_checkpoint` remain optional.

Before `linear_pattern`, `polar_pattern`, `mirrored_feature`, or
`multi_transform_pattern`, compare the single seed element first. A pattern
multiplies any error in the seed and must not be used as a substitute for
verifying that element.

#### evaluate_model_checkpoint

Apply a deterministic reaction policy after geometric validation and visual comparison.

```python
evaluate_model_checkpoint(
    checkpoint_name: str,
    geometry_valid: bool,
    solid_count: int | None = None,
    expected_solid_count: int | None = 1,
    visual_comparison_performed: bool = False,
    unresolved_dimensions: list[str] | None = None,
    discrepancies: list[dict] | None = None,
) -> dict
```

The decision is `continue`, `rework`. The tool does not inspect pixels; it enforces stop criteria against the agent-authored evidence. Do not create the next feature unless `can_continue=true`.

### View Control

#### set_view_angle

Set a standard camera view.

```python
set_view_angle(view_angle: str, doc_name: str | None = None) -> dict
```

#### fit_all

Fit all visible objects in the active view.

```python
fit_all(doc_name: str | None = None) -> dict
```

#### set_camera_position

Set an explicit camera position and look-at point.

```python
set_camera_position(
    position: list[float],
    look_at: list[float] | None = None,
    doc_name: str | None = None,
) -> dict
```

### Object Appearance

#### set_visual_properties

Set any combination of visibility, RGB color, and display mode in one call.

```python
set_visual_properties(
    object_name: str,
    visible: bool | None = None,
    color: list[float] | None = None,
    display_mode: str | None = None,
    doc_name: str | None = None,
) -> dict
```

At least one visual property must be provided. RGB components must be between
`0.0` and `1.0`.

### Workbenches

#### workbench

List available workbenches or activate one.

```python
workbench(
    action: Literal["list", "activate"],
    workbench_name: str | None = None,
) -> dict
```

`workbench_name` is required for `action="activate"`.

### History

#### history

Undo, redo, or inspect current document history.

```python
history(
    action: Literal["undo", "redo", "status"],
    doc_name: str | None = None,
) -> dict
```

The result always includes current undo/redo counts and available transaction
names.

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

For FCStd sources, an already open document with the same normalized file path is
reused and is never closed by the tool. This also supports copying a Shape from
the target document's own saved FCStd file without invalidating the live document.

### Utility

Console diagnostics and document recomputation use the canonical tools documented
under Execution and Document Tools:

- `get_console_output(lines=100)`;
- `recompute_document(doc_name=None)`.

### validate_parametric_model

Inspect the active or named document's editable parametric structure. This is an
informative diagnostic, not a hard pass/fail gate. After creating or changing
model geometry, call it immediately before the final user-facing response.

```python
validate_parametric_model(
    doc_name: str | None = None,
    recompute: bool = True,
    include_sketch_constraints: bool = False,
    required_dimension_names: list[str] | None = None,
) -> dict
```

When the input is a drawing or sketch, first extract and save every explicit
source dimension except dimensions marked with an asterisk. Assign stable unique
identifiers, implement them as named driving sketch constraints or connected
Spreadsheet aliases, and pass the complete identifier list through
`required_dimension_names`. The validator can verify only identifiers supplied
by the caller; it cannot discover a dimension omitted from the source-image
inventory.

The report includes:

- document metadata and counts;
- each `PartDesign::Body`, shape validity, current Tip, and ordered history;
- status strings serialized as complete entries (for example `["Valid"]`, not one character per entry);
- datum planes/lines/points marked as reference geometry, with non-applicable volume and bounding-box metrics omitted;
- sketches with solver state (`fully_constrained`, `under_constrained`,
  `over_constrained`, `conflicting`, `redundant`, or `solver_error`), remaining
  degrees of freedom, solver-reported conflicting/redundant constraint indices,
  profile state, supports, expressions, and constraint counts;
- standalone sketches, Spreadsheets, and solid objects outside Bodies;
- required-dimension usage, including `missing` and `defined_but_unlinked`
  identifiers;
- each Spreadsheet alias, its direct and transitive dependencies, whether it is
  connected to a feature-tree expression, and an error finding for aliases that
  remain unused;
- findings with `error` or `warning` severity;
- limitations: it does not prove drawing correspondence, manufacturing process,
  tolerances, design intent, or that a valid feature changed the expected amount
  of material. Use feature-level before/after volume diagnostics and visual checks.

Set `include_sketch_constraints=True` only when individual constraint details are
needed; it can make the response large.

Before final completion, investigate every unused Spreadsheet alias: connect it
to the tree if it was intended to drive geometry, or remove it if it is
redundant. A clean final report must not contain missing/unlinked required
dimensions or unused Spreadsheet parameters.

### Other validation tools

```python
validate_object(object_name: str, doc_name: str | None = None) -> dict
validate_document(doc_name: str | None = None) -> dict
undo_if_invalid(doc_name: str | None = None) -> dict
safe_execute(
    code: str,
    doc_name: str | None = None,
    validate_after: bool = True,
    auto_undo_on_failure: bool = True,
) -> dict
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
- `set_visual_properties`
- `set_camera_position`
- `selection`

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
