# FreeCAD Robust MCP Server Tools Reference

This document provides detailed signatures and examples for core MCP tools. It is not the exact inventory of all registered tools. Use [Tools Overview](guide/tools.md) or the MCP client's discovered tool list for the authoritative 148-tool inventory.

---

## Overview

The FreeCAD Robust MCP Server exposes tools organized into the following categories:

The exact generated inventory is grouped as follows:

| Category | Tool Count |
| --- | ---: |
| Execution | 5 |
| Prompt access | 1 |
| Background jobs | 3 |
| Documents | 7 |
| Objects / Part and BREP surgery | 43 |
| Measurements | 9 |
| PartDesign / Sketcher | 28 |
| Sheet Metal | 5 |
| Spreadsheet | 11 |
| Draft | 6 |
| Images | 3 |
| Checkpoints | 1 |
| View / GUI / History | 11 |
| Validation | 7 |
| Export / Import | 2 |
| Macros | 6 |
| **Total** | **148** |

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

All root tool contracts advertise `additionalProperties: false`, and the server
rejects unknown root arguments before dispatch. For example,
`create_document({"doc_name": "Part"})` fails with the allowed argument list;
use its declared `name` field. Nested discriminated models also forbid unknown
fields where their contract is closed.

Treat the live `tools/list` response as the source of truth. A copied source
archive can legitimately describe another commit than a still-running FreeCAD
bridge/MCP process. Restart both components after upgrades and keep the server
commit/version with task logs. CI pins the complete registered tool inventory
and asserts critical fields such as `boolean_operation.expected_solid_count`
and `boolean_operation.fuzzy_tolerance`, so
an implementation/schema mismatch fails before release.

### Primitive Creation

#### create_primitive

Create one supported Part primitive through a single typed entry point.

```python
create_primitive(
    primitive: PrimitiveSpec,
    name: str | None = None,
    doc_name: str | None = None,
    axis_origin: list[float] | None = None,
    axis_direction: list[float] | None = None,
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
For axial primitives (`cylinder`, `cone`, `torus`, and `helix`), optional
`axis_origin=[x,y,z]` and `axis_direction=[dx,dy,dz]` place the native +Z axis
directly in world coordinates. The direction is normalized internally, avoiding
an additional Euler-angle `set_placement` call. For cylinder, cone, and helix the
origin is the axis start; for torus it is the center.

### Object Management

#### list_objects

List all objects in a document.

```python
list_objects(doc_name: str | None = None) -> list[dict]
```

#### inspect_object

Inspect an object. The default response is deliberately compact.

```python
inspect_object(
    object_name: str,
    doc_name: str | None = None,
    detail_level: str = "summary",  # summary | shape | topology | full
    face_offset: int = 0,
    face_limit: int = 20,
    edge_offset: int = 0,
    edge_limit: int = 20,
    vertex_offset: int = 0,
    vertex_limit: int = 20,
) -> dict
```

Use `summary` for identity, relationships, and compact shape metrics. Use `shape`
when only bounds, volume, area, validity, and topology counts are needed. The
`topology` and `full` modes return independently paged face, edge, and vertex records;
`full` additionally serializes every property and can still be very large. Use
it only after a compact response identifies a specific property-level question.
The legacy `include_properties`/`include_shape` arguments remain accepted.

With `detail_level="topology"`, `shape_info.faces` includes `surface_type`, an
oriented normal sampled at a representative point, `area`, `centroid`, adjacent
`FaceN` references, local `convexity`, and participating edges. Cylindrical faces
also include `radius`, `axis_direction`, and `axis_point` (the OCCT cylinder
center used as a stable point on the infinite axis). `shape_info.edges` includes
`curve_type`, start/end points,
length, radius when available, direction, and adjacent faces. `convexity` describes
the local surface curvature at a representative point (`flat`, `convex`,
`concave`, `saddle`, or `unknown`); it is not an assertion about manufacturability.
The location field is named `centroid`: for faces it is the surface-area
centroid and for edges it is the curve-length centroid, in global coordinates.
`shape_info.vertices` contains the exact point, adjacent edges/faces, and vertex
tolerance. Each topology kind has its own page metadata under `topology_pages`.
Set a page limit to `0` to omit that topology kind entirely, for example
`edge_limit=0, vertex_limit=0` when only face records are needed. Positive limits
remain capped at 100.

#### select_subshapes

Select topology without writing manual loops over `Shape.Faces`, `Shape.Edges`,
or `Shape.Vertexes`. The result contains semantic records plus ready-to-use
`FaceN`/`EdgeN`/`VertexN` references.
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
    detail_level="summary",
    offset=0,
    page_size=20,
)

select_subshapes(
    object_name="Imported",
    criteria={
        "kind": "face",
        "surface_types": ["Cylinder"],
        "radius_min": 4.99,
        "radius_max": 5.01,
        "axis_direction": [0, 0, 1],
        "axis_direction_tolerance_deg": 1,
        "axis_point": [20, 10, 0],
        "axis_point_tolerance": 0.01,
        "adjacent_surface_types": ["Cone"],
    },
    detail_level="summary",
    page_size=200,
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

select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "vertex",
        "point_bounds": {"x_min": 19.99, "x_max": 20.01},
        "adjacent_edge_count_min": 3,
        "sort_by": "point_z",
        "sort_order": "desc",
        "limit": 1,
    },
    detail_level="summary",
)
```

The default `detail_level="references"` returns only `FaceN`/`EdgeN`/`VertexN` references
plus pagination metadata. Use `summary` for compact selection evidence and
`full` only to resolve a specific ambiguity. Location filters use
`centroid_bounds`; the old input key `center` and `center_x/y/z` sort names are
accepted for compatibility.

The MCP input schema deliberately exposes `criteria` as one flat object rather
than a `$ref`-only union. Every face, edge, and vertex filter is therefore visible
in generated tool declarations; each field description identifies the applicable
topology kind. Supplying a field that is not valid for the selected `kind` is
rejected before FreeCAD is called.

Face radius uses `radius_min`/`radius_max`. Cylinder and cone axes are
geometrically undirected, so either sign of `axis_direction` matches.
`axis_point` may be any
point on the expected infinite axis: comparison uses perpendicular distance and
`axis_point_tolerance`, not the arbitrary longitudinal position of the serialized
surface center. `page_size` and `criteria.limit` both accept values from 1 to 200.

The implementation is selective and lazy: it requests only the selected
topology kind, and `references` computes only fields used by the supplied
criteria. Expensive adjacency, curvature, normals, and bounding boxes are not
built unless filtering or the requested detail level needs them. This keeps
semantic selection usable on large imported STEP topology.

Line direction is treated as undirected, so `[1, 0, 0]` also matches an edge
stored from right to left. Type names are case-insensitive and accept common
forms such as `planar`/`Plane`, `conical`/`Cone`, `circular`/`Circle`, and
`LineSegment`/`Line`. When `adjacent_surface_types` contains several entries,
every listed type must occur among the selected face's or edge's adjacent faces.

Vertex location uses `point_bounds` in world coordinates. Vertex filters also
accept minimum/maximum adjacent edge and face counts. Use the returned
`VertexN` directly with the relevant dedicated `measure_*` tool; do not
infer the vertex index from an edge endpoint.

#### inspect_subshape_neighborhood

Inspect the local face topology without manually following each returned
`adjacent_faces` name:

```python
inspect_subshape_neighborhood(
    object_name="hf_217",
    reference="Face3",
    hops=1,
    doc_name=None,
)
```

Use the tool before and after every local geometry edit, not only for holes.
Treat the selected face as an edit handle for a larger local feature; compare
transitions, attachments, interfaces, and nearby invariant faces after
recompute, and rollback/rework collateral changes.

The target and neighbors contain compact surface evidence (`type`, radius/axis
when applicable, normal, area, centroid, and convexity). Neighbors are ordered
by hop distance and face index. At most 50 neighbors are returned;
`neighbor_count`, `returned_neighbor_count`, and `truncated` expose that bound.
The tool currently accepts exact `FaceN`
references; reselect the face after any geometry-changing recompute.

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
    doc_name: str | None = None,
    expected_solid_count: int | None = 1,
    fuzzy_tolerance: float = 0.0,
    refine: bool = True,
    timeout_ms: int = 30000,
) -> dict
```

**Operations:**

- `fuse` - Union/combine shapes
- `cut` - Subtract object2 from object1
- `common` - Intersection of shapes

The operation commits only after the result is non-null, valid, and has exactly
`expected_solid_count` solids. The default requires one continuous solid. A
rejected result aborts the FreeCAD transaction and returns an MCP error; set
`expected_solid_count=None` only for an intentional multi-solid result.

With `fuzzy_tolerance=0`, the tool keeps FreeCAD's native parametric `Part::Cut`,
`Part::MultiFuse`, or `Part::MultiCommon` feature. A positive tolerance routes
`fuse`, `cut`, and `common` through the corresponding direct `Shape` Boolean in
the same transaction and stores a static `Part::Feature` with `BaseSource` and
`ToolSource` provenance links plus the operation and tolerance. This is the
generic tolerant path for imported/static B-reps. Use the smallest defensible
tolerance. Optional refinement falls back to the valid unrefined result when
possible.

The successful response includes `shape_valid`, `shape_type`, `solid_count`,
`volume`, `base_volume`, `tool_volume`, `result_volume`, and `volume_delta`.
It also reports `execution_mode`, `fuzzy_tolerance`, and actual refinement state.
These fields verify material change without a routine follow-up inspection call.

#### fuse_all and common_all

```python
fuse_all(
    object_names: list[str],
    result_name: str | None = None,
    doc_name: str | None = None,
    fuzzy_tolerance: float = 0.0,
    refine: bool = True,
    expected_solid_count: int | None = 1,
    timeout_ms: int = 30000,
) -> dict
common_all(  # same arguments
    object_names: list[str],
    result_name: str | None = None,
    doc_name: str | None = None,
    fuzzy_tolerance: float = 0.0,
    refine: bool = True,
    expected_solid_count: int | None = 1,
    timeout_ms: int = 30000,
) -> dict
```

Both tools validate every intermediate Boolean and abort before commit when a
Shape is null/invalid, has non-positive volume, or has the wrong final solid
count. `steps` reports intermediate solid counts and volumes. `fuse_all` is the
general controlled fuse entry point: use `fuzzy_tolerance` only when exact
topology is insufficient, and keep the smallest defensible value.

### General BREP Surgery

These tools expose the imported/static-shape workflow that was previously only
available inside specialized edits:

```python
group_feature_faces(object_name, face_names, doc_name=None) -> dict
detect_rotational_pattern(
    object_name, face_groups, axis_origin=None, axis_direction=None,
    angular_tolerance_deg=0.5, radial_tolerance=1e-4, doc_name=None,
) -> dict
defeature_faces(
    object_name, face_names, result_name=None, refine=True,
    max_volume_drift_absolute=1e-4, max_volume_drift_relative=1e-7,
    max_linear_drift=1e-6, allow_geometry_drift=False,
    expected_solid_count=1, hide_source=True, doc_name=None,
) -> dict
extract_feature_material(
    source_name, healed_name, mode="removed_material",
    component_indices=None, component_volume_min=None,
    component_volume_max=None, component_sort_by="index",
    component_sort_order="asc", component_limit=None,
    result_prefix="RecoveredFeature", refine=True, fuzzy_tolerance=0.0,
    max_volume_drift_absolute=1e-4, max_volume_drift_relative=1e-7,
    max_linear_drift=1e-6, allow_geometry_drift=False,
    doc_name=None,
) -> dict
sew_shell(object_names, result_name=None, tolerance=1e-7, doc_name=None) -> dict
heal_shape(
    object_name, result_name=None, tolerance=1e-7, refine=True,
    max_volume_drift_absolute=1e-4, max_volume_drift_relative=1e-7,
    max_linear_drift=1e-6, allow_geometry_drift=False,
    expected_solid_count=None, doc_name=None,
) -> dict
make_solid(
    object_name, result_name=None, refine=True, expected_solid_count=1,
    max_volume_drift_absolute=1e-4, max_volume_drift_relative=1e-7,
    max_linear_drift=1e-6, allow_geometry_drift=False,
    doc_name=None,
) -> dict
polar_pattern_shape(
    object_name, occurrences, total_angle_deg=360.0,
    axis_origin=None, axis_direction=None, result_name=None, fuse=False,
    fuzzy_tolerance=0.0, refine=True, expected_solid_count=None,
    max_volume_drift_absolute=1e-4, max_volume_drift_relative=1e-7,
    max_linear_drift=1e-6, allow_geometry_drift=False,
    hide_source=True, doc_name=None,
) -> dict
```

A typical impeller repair is: group the known feature faces; confirm equal
rotational spacing; defeature all blade faces to recover the support; subtract
that support from the original with `extract_feature_material`; select one exact
solid component; then create the required count with `polar_pattern_shape`.
Every geometry-producing tool opens a FreeCAD transaction, validates before
commit, and reports `transaction_state`.

`defeature_faces` rejects an OCCT no-op when the raw result of `defeaturing`
leaves volume, area, and topology unchanged. The check happens before
`removeSplitter`, so refinement-only topology cleanup cannot masquerade as face
removal. Every optional refinement compares volume, bounding box, center of mass,
and solid count before accepting the result. Excess drift keeps the valid
unrefined Shape and is reported; `heal_shape` aborts its transaction when the
healing step itself exceeds the guard. `allow_geometry_drift=True` is an explicit
auditable override, not the default. Small floating-point noise is handled by
combined absolute/relative tolerances.

`extract_feature_material` accepts the same narrowly controlled fuzzy tolerance
used by Boolean tools. OCCT can report an invalid compound from a Boolean even
when some contained solids are valid. The tool therefore decomposes the result,
reports `container_valid` and `invalid_component_indices`, and creates only valid
solids. Use `component_volume_min`/`component_volume_max`, sorting, and a limit
to select a component in the same Boolean call; raw `component_indices` remain
available when topology order is known. Refinement is applied per selected solid
and falls back independently, with diagnostics in each component record.
The response groups equal topology signatures in `representative_analysis` and
reports per-candidate volume, area, centre, plus absolute/relative spreads. It
never auto-selects a seed. That group is candidate evidence only: compare local
neighborhood, attachment, geometry, and source views before choosing a repeated
feature; generated names and component order are not proof that an instance is
intact.
`polar_pattern_shape(fuse=True)` uses a single OCCT multi-fuse when no fuzzy
tolerance is requested and reports the chosen `fuse_strategy`. An unfused
pattern must preserve `source volume × occurrences` before refinement; its
response includes expected, observed, delta, and tolerance.

`select_subshapes(detail_level="summary"|"full")` and
`inspect_subshape_neighborhood` expose `major_radius`, `minor_radius`, axis, and
center (`axis_point`) for toroidal faces. This permits reconstruction of
analytic support geometry without arbitrary Python inspection.

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

### Section and Slice Operations

#### slice_shape

Create either an ordinary planar cross-section or an offset/aligned section whose
cutting line consists of multiple straight segments.

```python
# Arbitrary planar section
slice_shape(
    object_name="Part",
    plane_point=[0, 0, 12],
    plane_normal=[0, 0, 1],
    result_name="Section",
)

# Broken/aligned cutting line, for example A-A on an engineering drawing
slice_shape(
    object_name="Part",
    section_path=[[0, 20, 0], [35, 20, 0], [35, 45, 0]],
    section_depth_direction=[0, 0, 1],
    align_segments=True,
    result_name="Section_AA",
)
```

Exactly one mode is accepted. In path mode, `section_path` contains the ordered
3D points of the cutting line in the source drawing-view plane.
`section_depth_direction` is the axis normal to that drawing view and must be
perpendicular to every path segment. Each segment creates a finite cutting face
spanning the source Shape bounding box. With `align_segments=True`, the segment
sections are rigidly unfolded in path order into one XY plane, preserving lengths
and curve geometry while making the result directly inspectable as an aligned
engineering-drawing section. Set `align_segments=False` only when the original
3D placement of the segment sections is required.

The response reports `mode`, total `edge_count`, `segment_count`, `path_length`,
and per-segment start/end, length, edge count, and cutting-plane normal. Empty
sections and invalid/degenerate paths fail without leaving a result object.

#### section_shape

Convenience wrapper for standard XY/XZ/YZ sections. For an arbitrary plane or a
broken/aligned cutting line, use `slice_shape`.

```python
section_shape(
    object_name="Part",
    plane="XZ",
    offset=15.0,
    result_name="SectionXZ",
)
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

For `action="set"`, provide at least one object name or qualified subelement such
as `"hf_201.Face357"`. Qualified `FaceN`, `EdgeN`, and `VertexN` references are
validated against the owning Shape and passed to FreeCAD's subelement selection
API. The result reports selected references and missing names rather than
silently ignoring unresolved references.

#### move_faces

Move a recognized planar feature boundary along its oriented normal, with an
explicitly reported fallback for legacy prism Booleans.

```python
move_faces(
    object_name="ImportedHousing",
    face_names=["Face12"],
    distance=2.0,
    operation="auto",             # prism compatibility path only
    result_name=None,
    hide_source=True,
    doc_name=None,
    method="feature_rebuild",     # auto | feature_rebuild | prism
    feature_face_names=None,       # optional explicit local feature region
) -> dict
```

`feature_rebuild` is intended for imported/static solids. Starting from the
selected planar cap or pocket floor, it discovers adjacent wall, fillet,
chamfer, blend, and tangent-chain faces up to a parallel support boundary. OCCT
defeaturing heals that local feature; the recovered material/void region is
then moved and rebuilt so fixed attachment transitions and moved terminal
transitions are retained. If discovery is ambiguous, pass the complete feature
region explicitly in `feature_face_names`, excluding the parallel support face.

`auto` attempts that path first but may use the old selected-face extrusion plus
Boolean. The response exposes `performed_method` and `fallback_reason`; a
`prism_boolean_fallback` is not equivalent to Move Face and should not be
reported as one. Use strict `feature_rebuild` when blend-aware reconstruction is
required, or explicit `prism` only for sharp prismatic geometry. The response
also includes propagated/support/tangent faces, Shape validity/type/solid count,
and `base_volume`, `result_volume`, and `volume_delta`.
`rebuild_variant="sharp_boundary_sweep"` means the selected boundary was sharp
and its attachment transitions stayed fixed. `translated_tangent_feature` means
the selected boundary began a tangent chain that was carried with the recovered
material/void feature.

A non-tangent terminal transition such as a chamfer directly adjoining the
selected cap is not silently left behind by strict `feature_rebuild`: the tool
reports `terminal_transition_face_names` and refuses the edit. `auto` may still
produce an explicitly labelled prism fallback; use controlled local B-rep
surgery when that fallback would violate the required transition geometry.

All modes create an auditable static snapshot rather than a native dimensional
PartDesign feature. Prefer the semantic owner whenever editable history exists.

---

## Measurement Tools

Measurements are read-only geometric evidence. They operate in FreeCAD native
units (millimetres, square/cubic millimetres, and degrees), touch and recompute
referenced objects by default, and never create document geometry. A topology
reference has this common shape:

```python
{"object_name": "Body", "subshape": "Face3"}
```

Omit `subshape` to measure the complete object Shape. When a tool needs a
specific topology kind it rejects the wrong kind early. Resolve references with
`select_subshapes`; `FaceN`, `EdgeN`, and `VertexN` remain transient topology
names and must be selected again after geometry-changing recomputes.

There are eight dedicated tools: `measure_bounding_box`, `measure_distance`,
`measure_angle`, `measure_radius`, `measure_wall_thickness`,
`measure_clearance`, `measure_minimum_gap`, and `measure_point_to_face`. Their
schemas expose only the relevant fields, which makes incorrect agent calls
fail early and keeps tool discovery readable. All accept optional `doc_name`
and `force_recompute` arguments. The older `measure_geometry` discriminated
dispatcher remains available for compatibility.

### measure_bounding_box

`fast` uses cached `TopoShape.BoundBox`/OCCT `BRepBndLib::Add`; `optimal` uses
`TopoShape.optimalBoundingBox`/OCCT `BRepBndLib::AddOptimal`. The response names
the actual algorithm. `coordinate_system="world"` includes object placement;
`local` removes the global placement before measuring.

With `report_gap=True`, both algorithms are evaluated and `gap_report` gives
the lower/upper expansion and size excess of the fast box on every axis. Set it
to `False` with `mode="fast"` when latency matters more than comparison
evidence. `tolerance_report` always contains maximum vertex, edge, and face
tolerances. `use_shape_tolerance=True` asks the optimal algorithm to enlarge
bounds by topology tolerances; triangulation use is explicit and reported.

```python
bounds = await measure_bounding_box(
    object_name="ImportedHousing", mode="optimal", coordinate_system="world",
    use_triangulation=False, use_shape_tolerance=False,
    force_recompute=True,
)
assert bounds["mode"] == "optimal"
```

### measure_distance

Measure the OCCT minimum distance between complete Shapes or any supported
subshape pair. The response includes all closest-point solutions up to a safe
limit, OCCT support tuples, the method, tolerance, and contact classification.
`within_distance_threshold` is true when `distance_mm <= tolerance_mm`; the
longer name distinguishes this distance threshold from general model tolerance.

```python
distance = await measure_distance(
    first={"object_name": "Shaft", "subshape": "Face2"},
    second={"object_name": "Housing", "subshape": "Face7"},
    tolerance_mm=1e-6,
    doc_name="Assembly",
)
```

### measure_angle

Measure between explicit `EdgeN` or `FaceN` references. Stable directions come
from line/circle axes, planar normals, or axial surfaces. Undirected mode treats
an axis and its reverse as equivalent (0–90 degrees); directed mode retains
orientation (0–180 degrees).

```python
angle = await measure_angle(
    first={"object_name": "Bracket", "subshape": "Face1"},
    second={"object_name": "Bracket", "subshape": "Face4"},
    orientation="undirected",
)
```

### measure_radius

Returns both `radius_mm` and `diameter_mm` for circular edges, cylinders, and
spheres. A toroid requires `radius_kind="major"` or `"minor"`. A conical face is
rejected because it has no constant radius; select its circular boundary edge.

```python
diameter = await measure_radius(
    reference={"object_name": "Bore", "subshape": "Face1"},
    radius_kind="auto",
)
```

### measure_wall_thickness

Requires two explicit `FaceN` references. Strict mode (the default) validates
parallel planar faces or coaxial cylindrical faces. Planar thickness is the
minimum distance between overlapping patches. Cylindrical thickness is the
nominal absolute radius difference; the minimum physical distance between the
finite face patches is reported separately as
`evidence.minimum_patch_distance_mm`. This remains reliable for axially split or
trimmed cylindrical faces whose closest points are not radially aligned.

```python
outer = await select_subshapes(
    object_name="Tube",
    criteria={"kind": "face", "surface_types": ["Cylinder"],
              "sort_by": "area", "sort_order": "desc", "limit": 2},
)
thickness = await measure_wall_thickness(
    first_face={"object_name": "Tube", "subshape": outer["references"][0]},
    second_face={"object_name": "Tube", "subshape": outer["references"][1]},
    strict=True,
)
```

### measure_clearance

Compares actual minimum distance with `required_clearance_mm`. For complete
object Shapes at contact distance, it also computes OCCT boolean-common volume
so interfering solids cannot pass merely because their minimum distance is
zero. Subshape clearance reports contact/distance evidence but not interference
volume.

```python
clearance = await measure_clearance(
    first={"object_name": "MovingJaw"},
    second={"object_name": "Guard"},
    required_clearance_mm=0.5,
    tolerance_mm=1e-6,
)
if not clearance["passes"]:
    raise ValueError(clearance)
```

### measure_minimum_gap

Evaluates every pair among 2–30 complete Shapes or subshape references and
returns `minimum_gap_mm`, `closest_pair`, and `pair_count`. Use it for a bounded
set of semantically selected candidates, not an unfiltered assembly with
thousands of components.

```python
gap = await measure_minimum_gap(
    references=[
        {"object_name": "Gear"}, {"object_name": "Cover"},
        {"object_name": "Shaft", "subshape": "Face3"}],
    tolerance_mm=1e-6,
)
```

### measure_point_to_face

Supply exactly one point source: a world-coordinate `[x, y, z]`, or a selected
`VertexN`. The target must be an explicit `FaceN`. The response includes the
nearest point on the face and OCCT support evidence.

```python
vertex = await select_subshapes(
    object_name="Probe",
    criteria={"kind": "vertex", "point_bounds": {"z_min": 99.9},
              "sort_by": "point_z", "sort_order": "desc", "limit": 1},
)
result = await measure_point_to_face(
    face={"object_name": "DatumPlate", "subshape": "Face1"},
    vertex={"object_name": "Probe", "subshape": vertex["references"][0]},
)

# Or use an explicit world point:
result = await measure_point_to_face(
    face={"object_name": "DatumPlate", "subshape": "Face1"},
    point=[25.0, 10.0, 100.0],
)
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

`add_arc` supports three modes. `center_angles` remains the default legacy form;
its `start_angle` and `end_angle` values are degrees. For engineering drawings,
prefer the two radius-driven forms when the source defines endpoints or adjoining
edges rather than center angles:

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

Use `add_bspline` only when the source explicitly defines a free-form curve by
interpolation/control points or knots. Do not use it to approximate a line,
circular arc, conic, unreadable boundary, or stated fillet radius.

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
get_sketch_info(
    sketch_name="BaseSketch",
    doc_name="Model",
    detail_level="summary",  # summary | geometry | constraints | full
)
```

The compact default contains solver/profile status and record counts. Geometry,
constraints, and expressions are independently paged when requested. Use
`detail_level="full"` only when exact indices or expression bindings are needed.
The detailed result includes:

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

Extrude a sketch to create material. For direction-sensitive pads, prefer
`direction=[x, y, z]`; the tool resolves `Reversed` from the sketch global
normal and reports the effective world-space direction. Pad supports the same
public end conditions as Pocket. For additive features, public `ThroughAll`
maps to FreeCAD's equivalent native `UpToLast` enumeration.

```python
pad_sketch(
    sketch_name: str,
    length: float,
    type: str = "Length",  # "Length", "ThroughAll", "UpToFirst", "UpToFace"
    symmetric: bool = False,
    reversed: bool = False,
    direction: list[float] | None = None,  # desired world-space direction
    up_to_face: str | None = None,  # required for UpToFace: "Feature.FaceN"
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
    type: str = "Angle",  # "Angle", "ThroughAll", "UpToFirst", "UpToFace"
    axis: str = "Base_X",  # "Base_X/Y/Z" or "Sketch_V/H"
    symmetric: bool = False,
    reversed: bool = False,
    up_to_face: str | None = None,
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
    direction: str = "auto",  # "auto", "normal", or "reversed"
    base_feature_name: str | None = None,
    up_to_face: str | None = None,  # required for UpToFace: "Pad.Face3"
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

`direction` is relative to the sketch normal and does not depend on GUI
selection. The default `auto` tries the negative normal first and then the
positive normal, retaining the first result that passes Shape/Tip checks and
measurably decreases Body volume. This makes a face-supported pocket cut into
the solid even when the face normal points outward. `normal` cuts along the
positive global sketch normal and `reversed` along the negative normal; explicit
directions never fall back. The response reports `requested_direction`, the
selected `direction`, `effective_direction`, and compact `direction_attempts`.
`base_feature_name` is authoritative when supplied.
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
    type: str = "Angle",  # "Angle", "ThroughAll", "UpToFirst", "UpToFace"
    axis: str = "Base_X",
    symmetric: bool = False,
    reversed: bool | None = None,  # deprecated compatibility override
    direction: str = "auto",  # "auto", "forward", or "reversed"
    up_to_face: str | None = None,
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

For a partial groove, `auto` tries both revolution directions and retains the
first measurable subtraction. Use an explicit direction when both sides of an
embedded profile intersect material and design intent requires one side.

`pad_sketch`, `pocket_sketch`, `revolution_sketch`, and `groove_sketch` share
one end-condition implementation. `UpToFace` always requires a validated
`Feature.FaceN` reference. The response exposes both the requested public
`type` and FreeCAD's `native_type`; additive `ThroughAll` is reported as native
`UpToLast`. Runtime enum validation produces an explicit compatibility error if
the connected FreeCAD build does not expose a requested native mode.

The standalone `extrude_shape` tool deliberately remains vector-length based.
It calls `TopoShape.extrude` and has no PartDesign support solid, so “first face”
and “through all material” are undefined. Use `pad_sketch` when an extrusion
must terminate at body material or an explicit face.

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
    reversed: bool | None = None,  # deprecated compatibility override
    direction: str = "auto",  # "auto", "forward", or "reversed"
    base_feature_name: str | None = None,
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

The response includes the resolved base, axis, selected direction, attempted
directions, turn count, Shape/Tip status, and volume diagnostics. `auto` validates
an actual volume increase for additive helices and an actual decrease for
subtractive helices.

#### create_hole

Create parametric holes with optional threading and strict post-validation. Use a new sketch containing only non-construction circles. Prefer attachment to an actual planar solid face such as `Pad_Base.Face8`; origin planes are allowed but may be ambiguous in a complex Body. Datum-plane sketches are rejected because `PartDesign::Hole` can become a geometrically ineffective no-op in FreeCAD 1.0.x. Use `create_cylindrical_cut` for radial or off-face holes. For native SheetMetal parts, prefer holes/cutouts in the source flat blank so panel ownership is explicit, but a validated Hole is also allowed as a linear subtractive tail after the last native SheetMetal feature.

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
    reversed: bool | None = None,  # deprecated compatibility override
    direction: str = "auto",  # "auto", "normal", or "reversed"
    name: str | None = None,
    doc_name: str | None = None
) -> dict
```

`ISO_FINE` is normalized to FreeCAD's `ISOMetricFineProfile` enumeration before
the requested `thread_size` is selected. The size is validated against the
enumeration advertised by the running FreeCAD build. `auto` tries both sides
and validates material removal at every profile circle. `normal` and `reversed`
are relative to the global sketch normal and do not fall back. Do not supply an
explicit `direction` together with the legacy `reversed` flag.

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
    doc_name: str | None = None,
    direction: str = "auto",  # "auto", "forward", or "reversed"
) -> dict
```

`auto` first tests `axis_direction` and then its negative, retaining the first
validated material removal. `forward` uses the supplied vector exactly;
`reversed` uses its negative. The selected world-space vector is returned as
`effective_axis_direction` together with compact attempt diagnostics.

The Boolean `boolean_operation(operation="cut")`, `subtractive_loft`, and
`subtractive_pipe` have no two-sided direction property: their subtracting
geometry or path already defines the operation, so `auto` is not applicable.

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

An OCCT build/validation failure returns `success=false` after rollback instead
of only a generic exception string. The diagnostic includes source Shape type
and solid count, selected `EdgeN` values, adjacent face names/surface types,
requested radius, result validation state, and individual-edge trials.
`failing_edges` identifies edges that fail alone. If all edges work alone but
the combined selection fails, `failing_edge_groups` records that group-level
interaction.

#### chamfer_edges

Add beveled edges. The same current-Tip, `EdgeN`, post-recompute, rollback, and
structured-failure contract used by `fillet_edges` applies. On failure the tool
returns source Shape/solid evidence, adjacent face surface types, requested size,
per-edge trials, `failing_edges`, and a group-level diagnostic when edges succeed
individually but fail together.

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

Both single-pattern tools use the first `TransformMode` enumeration entry advertised by the running FreeCAD build. This is the feature-transform mode, but its displayed label differs between FreeCAD versions (for example, `Features` or `Transform tool shapes`). The API contract still treats `feature_name` as an additive/subtractive seed rather than the whole Body. Responses keep `transform_mode` as the selected string and add `transform_mode_options` for diagnostics. They return `base_volume`, `result_volume`, and `volume_diagnostics`. `material_change_diagnostics.method` is `add_subshape` when FreeCAD exposes the transformed tool shape. Valid patterns in builds that omit `AddSubShape` are checked with a B-rep before/after set difference (`result_shape_difference`) instead of being reported unavailable. An inconsistent causal check rolls the feature back even if OpenCASCADE reports a formally valid solid. The neutral retained/change ratios remain evidence for the agent rather than a general proof of design intent. Applying a pattern directly to another pattern is rejected with guidance to use `multi_transform_pattern`.

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

## Sheet Metal Tools

These five tools wrap the installed
[FreeCAD SheetMetal Workbench](https://github.com/shaise/FreeCAD_SheetMetal)
as native, editable `FeaturePython` history. They are intended for one
constant-thickness part per `PartDesign::Body`; an unfold is generated outside
the Body so it cannot replace the formed part's Tip.

A reliable agent workflow is:

1. call `sheet_metal_capabilities` once and check the exact installed operations;
2. when the source includes a flat pattern, inventory its entire perimeter,
   cutouts, panel regions, bend lines, bend directions, thickness, radius, and
   neutral-axis rule before creating 3D geometry;
3. create and fully constrain a closed blank or open wall-path sketch;
4. create a native base, inspect its visibility/display evidence, and keep the
   Body history linear;
5. resolve every `FaceN`/`EdgeN` with `select_subshapes` or inspection evidence;
6. add native manufacturing features, inspecting after each major bend;
7. unfold with an explicit K-factor convention or a material Spreadsheet and
   compare the generated blank/bend lines with the source flat pattern;
8. finish with `validate_parametric_model`.

Do not model a bent part as unrelated Pads, boxes, or fused solids. Such a
shape may look correct but has no trustworthy neutral axis, bend allowance, or
flat pattern.

### sheet_metal_capabilities

Report whether the external workbench is importable, its package version, and
which native proxy classes are available.

```text
sheet_metal_capabilities() -> dict
```

The `operations` mapping contains `base`, `flange`, `fold`, `junction`,
`relief`, `corner_relief`, `extend`, `hem`, `solid_bend`, `from_solid`, and
`unfold`. Check the operations needed by the planned workflow rather than
assuming that every SheetMetal release has the same Python API.

### create_sheet_metal_base

Create a native `SMBaseBend` from a Sketcher object.

```text
create_sheet_metal_base(
    sketch_name: str,
    thickness: float,
    radius: float,
    wall_length: float = 100.0,
    bend_side: "outside" | "inside" | "middle" = "outside",
    midplane: bool = False,
    reverse: bool = False,
    name: str = "BaseBend",
    doc_name: str | None = None,
) -> dict
```

- A closed sketch creates a flat base wall. `wall_length` is then immaterial to
  its footprint.
- An open polyline creates connected walls whose extrusion width is
  `wall_length`.
- For an open sketch, each segment dimension is the full flange length used by
  SheetMetal, not the mold-line leg. For a 90-degree bend, the upstream
  calculator expresses this as `flange_length = radius + thickness + leg_length`.
- Put the sketch in the intended Body. The tool rejects a null, invalid,
  multi-solid result and reports the native proxy, volume, Body, Tip, GUI
  ViewProvider, visibility, and display mode.

### create_sheet_metal_feature

Create one native manufacturing feature. One discriminated `operation`
argument keeps the public surface compact while exposing only fields valid for
the chosen operation.

```text
create_sheet_metal_feature(
    operation: SheetMetalFeatureOperation,
    name: str | None = None,
    doc_name: str | None = None,
) -> dict
```

| `operation.op` | Purpose | Required topology / primary inputs |
| --- | --- | --- |
| `flange` | Bend one or more boundary edges into a wall | `base_feature`, `edges`, `length`, `radius`; optional angle, bend and length conventions, gaps and relief |
| `fold` | Bend a sheet along a sketch line | `base_feature`, planar `face`, `bend_line_sketch`, `radius`, `k_factor` |
| `junction` | Open a seam/rip | `base_feature`, `edges`, `gap` |
| `relief` | Add relief at selected vertices | `base_feature`, `vertices`, `size` |
| `corner_relief` | Relieve the intersection of two bends | exactly two `edges`, `size`, `k_factor` |
| `extend` | Extend a wall or merge a sketched extension | `base_feature`, face/edge `subelements`, `length` |
| `hem` | Create flat, open, teardrop, or rolled hems | `base_feature`, `edges`, `hem_type`; optional width, radius and opening |
| `solid_bend` | Bend a suitable thin solid along edges | `base_feature`, `edges`, `radius` |
| `from_solid` | Convert a thin solid to SheetMetal history | `base_feature`, faces/edges to remove or rip, `thickness`, `radius` |

All topology strings are validated before the native proxy is constructed.
For a Body feature, `base_feature` must be the current Tip. The tool then
requires one valid non-empty solid and advances the Tip transactionally.
For `fold`, a Body-owned bend-line sketch is a helper: `create_sketch`
explicitly preserves an existing solid Tip, so the sketch may reference the
base face without becoming the next modeling base. Invalid or missing
subshapes are normalized to an actionable `Cannot resolve Object.FaceN/EdgeN`
error before proxy construction.

### inspect_sheet_metal

Inspect whether an object is a usable constant-thickness sheet-metal part.

```text
inspect_sheet_metal(
    object_name: str,
    doc_name: str | None = None,
    detail_level: "summary" | "candidates" | "full" = "summary",
) -> dict
```

The default `summary` report includes scalar validity, thickness, topology,
history, Body/Tip, display, readiness, and warning evidence without face lists.
Use `candidates` to add up to eight planar `stationary_face_candidates`,
classified `bend_pairs`, and compact native-history records. Use `full` only to
add every `cylindrical_faces` record and complete `history_evidence`.

`has_native_sheet_metal_features` means that at
least one native proxy exists. The stronger `native_sheet_metal_history` means
the complete active history from the first native proxy through the inspected
object is supported; `sheet_metal_history_classification` distinguishes a
native linear history, a supported post-native subtractive tail, unsupported
post-native geometry, and an unsupported interleaved history that later
re-enters a native proxy. Hole, Pocket, Groove, and cylindrical-cut features
after the final native proxy are reported in `supported_subtractive_features`.
Holes and contour cutouts are still best placed in the source flat blank when
that matches design intent, because their panel ownership is then explicit.
`unfold_ready` is false when the object is not the current Body Tip, lacks a
supported native history, has a missing ViewProvider, or contains unsupported
shape-producing features anywhere in that active interval. Use a
candidate as evidence for unfold; use `select_subshapes` when the design intent
requires a particular normal, location, or area.

`cylindrical_face_count` remains the raw count of all cylindrical surfaces.
`classified_bend_face_count` and the compatibility field
`cylindrical_bend_face_count` include only coaxial partial-cylinder pairs whose
radius difference matches nominal thickness and whose radius matches declared
native bend data; `bend_zone_count` counts those pairs. Hole walls (full
cylinders), fillets, tubes, and unmatched curved surfaces are retained in the
`full` response's `cylindrical_faces` with a non-bend classification rather than
inflating the bend count.
Candidate status does not guarantee that the installed upstream workbench can
unfold the complete history. Native unfold errors, including the SheetMetal
0.8.21 `SMFromSolid` open-box `Wire is not closed` case, remain transactional:
no flat feature is retained and the formed Body Tip is unchanged.

### unfold_sheet_metal

Create a native `SMUnfold` flat pattern while preserving the formed Body Tip.

```text
unfold_sheet_metal(
    feature_name: str,
    stationary_face: str,
    material: {
        "k_factor": float,
        "standard": "ansi" | "din",
    } | {"material_sheet": str},
    generate_sketch: bool = True,
    separate_layers: bool = True,
    show_bend_angles: bool = True,
    verification_only: bool = False,
    name: str = "Unfold",
    doc_name: str | None = None,
) -> dict
```

Exactly one bend-allowance source is mandatory. Manual values require an
explicit ANSI or DIN convention; production workflows may instead name a real
`Spreadsheet::Sheet` material table. The stationary face must resolve to a
planar face. The input must be the current Body Tip and retain a native
sheet-metal history; ad-hoc additive PartDesign reconstruction is rejected.
The result reports its material source, generated sketch objects, and geometric
validation evidence. With `verification_only=True`, the native Unfold is fully
computed first, then the response captures flat validity/solids/volume/bounds
and generated-sketch geometry types, circle count, and wire count. The tool
rolls back the Unfold plus every newly generated helper object and verifies that
none remain. Use this mode before final `validate_parametric_model`; leave the
default persistent mode only when the saved document must retain an editable or
exportable flat pattern.

### Example: upstream 100 mm L-profile flat pattern

The upstream
[`calc-unfold.py`](https://github.com/shaise/FreeCAD_SheetMetal/blob/master/tools/calc-unfold.py)
uses `t=2 mm`, inside `R=1.64 mm`, ANSI `K=0.38`, and a 90-degree bend.
It calculates a 48.12 mm mold-line leg and a 51.76 mm full flange. The fully
constrained open `ProfileSketch` therefore uses the full flange length on both
segments; unfolding must recover a 100 mm developed strip.

```python
# Verified by: tests/integration/test_sheetmetal_workflow.py::test_upstream_reference_l_profile_unfolds_to_100_mm_blank
base = await create_sheet_metal_base(
    sketch_name="ProfileSketch",
    thickness=2.0,
    radius=1.64,
    wall_length=30.0,
    bend_side="inside",
    name="ReferenceLProfile",
    doc_name="McpAuditSheetMetalReference",
)
inspection = await inspect_sheet_metal(
    object_name="ReferenceLProfile",
    doc_name="McpAuditSheetMetalReference",
    detail_level="candidates",
)
flat = await unfold_sheet_metal(
    feature_name="ReferenceLProfile",
    stationary_face=inspection["stationary_face_candidates"][0]["face"],
    material={"k_factor": 0.38, "standard": "ansi"},
    verification_only=True,
    generate_sketch=True,
    separate_layers=True,
    show_bend_angles=True,
    name="ReferenceFlatPattern",
    doc_name="McpAuditSheetMetalReference",
)
```

The linked live test constructs and fully constrains the sketch, verifies the
native `SMBaseBend`, checks the bend surface and thickness evidence, unfolds it,
measures the resulting B-rep as `100.00 +/- 0.05 mm`, and runs final parametric
validation with both named flange dimensions.

### Example: semantic edge flange

Never guess that the desired boundary is `Edge1`. This example selects the
80 mm top boundary of an 80 x 50 x 2 mm closed base by geometry and location,
then creates and unfolds a 20 mm flange.

```python
# Verified by: tests/integration/test_sheetmetal_workflow.py::test_semantic_edge_flange_and_unfold_workflow
edge = await select_subshapes(
    object_name="BaseBlank",
    criteria={
        "kind": "edge",
        "curve_types": ["Line"],
        "direction": [1.0, 0.0, 0.0],
        "length_min": 79.99,
        "length_max": 80.01,
        "centroid_bounds": {
            "y_min": 49.99, "y_max": 50.01,
            "z_min": 1.99, "z_max": 2.01,
        },
        "limit": 1,
    },
    detail_level="summary",
    doc_name="McpAuditSheetMetalFlange",
)
flange = await create_sheet_metal_feature(
    operation={
        "op": "flange",
        "base_feature": "BaseBlank",
        "edges": edge["references"],
        "length": 20.0,
        "radius": 2.0,
        "angle": 90.0,
        "bend_type": "material_outside",
        "length_spec": "leg",
    },
    name="EdgeFlange",
    doc_name="McpAuditSheetMetalFlange",
)
inspection = await inspect_sheet_metal(
    object_name="EdgeFlange",
    doc_name="McpAuditSheetMetalFlange",
    detail_level="candidates",
)
flat = await unfold_sheet_metal(
    feature_name="EdgeFlange",
    stationary_face=inspection["stationary_face_candidates"][0]["face"],
    material={"k_factor": 0.38, "standard": "ansi"},
    name="FlangeFlatPattern",
    doc_name="McpAuditSheetMetalFlange",
)
```

The linked live test also proves that the selector returns exactly one edge,
the feature is an `SMBendWall` and the Body Tip, the model has a cylindrical
bend face and no inspection warnings, the unfold is one valid solid with
generated sketches, and both named blank dimensions still drive the result.

Unit tests additionally dispatch every operation in the table to its native
proxy and reject misspelled fields, wrong topology kinds, invalid dimensions,
and ambiguous unfold material rules. The registry-driven integration audit
requires all five Sheet Metal tools and all nine feature variants to remain in
the public schema.

---

## Spreadsheet Tools

`spreadsheet_set_cell` and `spreadsheet_get_cell` normalize FreeCAD wrapped cell
values (for example `Quantity` objects and method/proxy wrappers) to bridge-safe
primitive/string values before returning them. This prevents XML-RPC marshalling
failures such as `cannot marshal <class 'builtin_function_or_method'> objects`.


### spreadsheet_apply_batch

Apply literals/quantities, aliases, dependent formulas, and object-property bindings to an existing Spreadsheet in that order, inside one transaction with one final document recompute. Use this instead of dozens of independent setter calls when creating a parameter table. Binding targets accept FreeCAD expression paths such as `Length`, `Placement.Base.x`, and `AttachmentOffset.Base.z`; FreeCAD validates the leaf path through `setExpression`. Aliases, duplicate entries, and alias collisions are validated before mutation. Because FreeCAD 1.0 does not roll Spreadsheet mutations back on `abortTransaction()`, the tool snapshots and explicitly restores affected cells, aliases, and expressions if any operation fails.

```python
spreadsheet_apply_batch(
    spreadsheet_name: str,
    cells: list[dict] | None = None,       # numeric {"cell":"B2","value":42}
                                           # Quantity {"cell":"B3","value":{"value":40,"unit":"mm"}}
                                           # formula {"cell":"B4","formula":"=Length/2"}
                                           # text {"cell":"C1","text":"Parameters"}
    aliases: list[dict] | None = None,     # {"cell": "B2", "alias": "Length"}
    bindings: list[dict] | None = None,    # {"alias": "Length", "target_object": "Pad", "target_property": "Length"}
    doc_name: str | None = None,
) -> dict
```

At least one non-empty list is required. The `value` field accepts only a number
or structured Quantity; raw strings such as `"40 mm"` are rejected because they
are ambiguous with Spreadsheet text. Use `formula` and `text` explicitly for
those content kinds. Aliases created in the same batch may immediately be used
by later formulas and bindings.
Retries are idempotent, including aliases that already point to the requested
cell. When a unitless Spreadsheet value is bound to an `App::PropertyAngle`
such as `PartDesign::PolarPattern.Angle`, the generated expression multiplies
the value by `1 deg`; a cell that already has an angle unit is bound directly.
After recompute the batch verifies every non-empty formula cell on the sheet,
including unchanged formulas that depend on a modified cell or alias. Encoded
values such as `ERR:`, `#ERR`, `#REF!`, or an invalid-expression diagnostic
cause rollback rather than a successful response. The result reports
`formula_cells_validated`. In GUI mode the bridge flushes posted Qt
events before reading the per-request Report View delta; high-confidence Spreadsheet errors
are returned as `FreeCADReportError` even when FreeCAD's Python API did not
raise an exception.

`spreadsheet_bind_property` uses the same expression-path contract for a single
binding. Both tools normalize the leading dot that FreeCAD uses when reporting
nested `ExpressionEngine` paths, verify that the requested binding was retained,
and preserve existing expressions when an invalid path causes rollback.

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
    mesh_tolerance: float = 0.1,
    verify_round_trip: bool = True,
    round_trip_linear_tolerance: float = 0.01,
) -> dict
```

`mesh_tolerance` is used only for STL, 3MF, and OBJ. STEP and IGES preserve
BREP geometry. The destination directory must already exist; a missing directory
is reported explicitly before the writer is called. BREP exports are re-read by
default and rejected when the exchange file is null or invalid. STEP verification
checks solid count, volume, and bounds against the original in-document Shape,
not against a BREP-normalized copy of that same export. The diagnostic
canonicalization is also checked against the original and fails if it changes
those invariants, so repeated exchange cannot silently rebase the reference.
Measurements and the explicit `baseline="original_source_shape"` marker are
returned in `round_trip_verification`. `round_trip_linear_tolerance` admits only
small bounding-box noise from FreeCAD/OCC serialization (0.01 mm by default);
it does not rebase the comparison or relax volume/solid-count checks. Set
`verify_round_trip=False` only when a downstream application must receive a file
that FreeCAD cannot read back.

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
object. If `doc_name` names an open document it is reused; otherwise that named
document is created automatically. With no `doc_name`, the active document is
used or a new `Imported` document is created. The result includes
`document_created`, and imported objects receive best-effort
`ImportSourcePath`/`ImportSourceFormat` provenance properties.

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
Supplying `output_path` automatically enables `save_to_disk`; callers do not
need to repeat both arguments.

**View/plane correspondence:**

| View | Projection plane | Normal/depth axis |
|---|---|---|
| Front / Back | XZ | Y |
| Top / Bottom | XY | Z |
| Left / Right | YZ (ZOY) | X |
| Isometric | no true-shape plane | verification only |

**View angles:** `Isometric`, `Front`, `Back`, `Top`, `Bottom`, `Left`, `Right`, `Current`, `FitAll`

`Current` preserves both orientation and framing. `FitAll` preserves the current
orientation and changes only framing. With `get_screenshot`, combine
`view_angle="Current"` and `fit_all=False` to capture an existing custom camera
exactly; use `fit_all=True` only when reframing is intended.

#### open_image

Open a local drawing or saved screenshot and return its pixels to the agent.

```python
open_image(path: str, max_dimension: int = 4096) -> CallToolResult
```

Supported formats: PNG, JPEG, WebP. Relative paths are resolved from the MCP
server working directory. Local file access must be enabled.

#### open_image_tiles

Return a numbered overview and ordered, labelled, overlapping fragments without
upscaling source crops.

```python
open_image_tiles(
    path: str,
    rows: int = 2,
    columns: int = 3,
    overlap_percent: float = 12.0,
    tile_max_dimension: int = 1600,  # maximum; smaller crops keep native size
    include_overview: bool = True,
    save_to_disk: bool = True,
    output_dir: str | None = None,
) -> CallToolResult
```

The result contains one text block before every image, identifying the fragment
number, grid position, source pixel rectangle, overlap, and resize scale. The
overview preserves global context while every fragment is delivered as a separate
MCP image block with an explicit prompt describing what region it represents.
Cropping gives small drawing details a larger visual budget without synthesizing
pixels: crops smaller than `tile_max_dimension` stay at native size, while larger
crops are downscaled. A maximum of nine tiles is allowed.
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

A match in one projection does not prove depth, opposite-face geometry, or
feature-axis orientation. During modeling, compare the source view(s) that can
expose the current feature. Before final acceptance, reproduce and compare every
source-view manifest record one-to-one, including opposite-side views,
sections/details/auxiliary views, and isometric/axonometric views when present.
A formal discrepancy ledger and `evaluate_model_checkpoint` remain optional.

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

The decision is `continue`, `rework`. The tool does not inspect pixels; it enforces stop criteria against the agent-authored evidence. `unresolved_dimensions` is only transient checkpoint state while the agent is still interpreting evidence; it is not a permitted terminal role in the saved source-dimension manifest. Do not create the next feature unless `can_continue=true`.

### View Control

#### set_view_angle

Set a standard camera view, preserve the `Current` view, or apply framing-only
`FitAll`.

```python
set_view_angle(view_angle: str, doc_name: str | None = None) -> dict
```

#### fit_all

Fit all visible objects in the active view.

```python
fit_all(doc_name: str | None = None) -> dict
```

#### set_camera_position

Set a reproducible engineering camera for drawing comparison.

```python
set_camera_position(
    position: list[float],
    look_at: list[float] | None = None,
    doc_name: str | None = None,
    up_direction: list[float] | None = None,
    projection: str = "orthographic",
    orthographic_height: float | None = None,
    roll_degrees: float = 0,
    fit_all: bool = False,
) -> dict
```

Orthographic projection, explicit screen-up, and `orthographic_height` make
candidate screenshots repeatable at the same orientation and scale. Use
`get_camera_state()` to record the current projection, position, quaternion,
height, and focal distance. `fit_all` and `orthographic_height` are mutually
exclusive.

### Object Appearance

#### highlight_faces

Temporarily color and optionally select individual faces without adding objects
to the document tree.

```python
highlight_faces(
    action="show",  # show or clear
    object_name="Pad",
    face_names=["Face12", "Face13"],
    color=[1.0, 0.75, 0.0],
    select_faces=True,
    clear_existing_selection=True,
    doc_name=None,
) -> dict
```

`show` saves the current per-face `DiffuseColor`; `clear` restores it (omit
`object_name` to clear all MCP highlights in the document). Highlight state is
session-only and creates no temporary `Part::Feature` geometry.

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

At least one visual property must be provided. RGB accepts either normalized
components from `0.0` to `1.0` or integer byte components from `0` to `255`;
byte input such as `[255, 0, 0]` is normalized to `[1.0, 0.0, 0.0]`. The JSON
Schema exposes exactly three items and component bounds `0..255`.

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

### Shape checkpoints for direct edits

Use a session-local B-rep checkpoint to prove both what changed and what stayed
invariant across an edit. Capturing and comparing are read-only and add no
objects or properties to the FreeCAD document.

```python
capture_shape_checkpoint(
    checkpoint_name="before_holes",
    object_name="Body",
    doc_name="Bracket",
    round_trip_linear_tolerance=0.01,
)

compare_shape_checkpoint(
    checkpoint_name="before_holes",
    object_name="Body",  # optional; defaults to captured object
    doc_name="Bracket",  # optional; defaults to captured document
    volume_tolerance=1e-7,
    linear_tolerance=1e-7,
    round_trip_linear_tolerance=0.01,
    difference_mode="auto",       # auto | exact | metrics
    exact_face_product_limit=10000,
    timeout_ms=30000,
)
```

The report always includes before/after validity, solid/shell/face/edge/vertex
counts, volume, surface area, bounding boxes and their deltas. Capture serializes
the original Shape directly, preserving the complete native BREP location graph;
it does not make a shallow copy, clear Placement, or reconstruct a quaternion.
Capture verifies restored topology, mass properties, placement, and every
bounding-box component. Any mismatch rejects capture; a changed bound can no
longer be labelled as a successful normalization. The separate default
round-trip bound tolerance is 0.01 mm to accommodate observed OCCT compound
serialization noise; it is returned in the report and can be tightened. Checkpoint metrics retain the
original in-document Shape as the immutable comparison origin. Comparison uses
the current in-document metrics for deltas and permits the restored BREP only
for exact booleans after another round-trip invariant check. Empty,
non-null OCCT Compounds with no topology are discarded rather than reported as
added or removed regions with infinite bounds. In `auto` mode,
OCCT computes both `before.cut(after)` and `after.cut(before)` only when the
product of the two face counts does not exceed `exact_face_product_limit`.
Larger imported B-reps automatically use metric-only comparison, avoiding two
unbounded whole-shape booleans; `difference.skip_reason` makes this explicit.
Use `difference_mode="exact"` (and raise `timeout_ms` if appropriate) when exact
localized regions are required, or `metrics` to prohibit boolean work. Exact
mode reports each added/removed connected solid with bounds and topology. If a
Boolean throws, produces a nonempty invalid Shape or region, or reports
negative/non-finite volume or area or non-finite bounds, then
`difference.available` is false and the exact error is explicit. Diagnostic
region records may remain present, but aggregate
added/removed volumes and `geometric_change` are then `None`;
metric deltas remain available. `volume_tolerance` controls exact
`geometric_change`; `metric_change_detected` is a cheaper summary and is not a
substitute for exact localization. Checkpoints live only for the current MCP
server session (up to 32 named baselines) and may be replaced with
`overwrite=True`.

### Background tool jobs

Use `start_tool_job(tool_name, arguments)` for FreeCAD operations that may
outlive a client request timeout, then poll `get_tool_job(job_id)`. The job and
its final MCP result are retained only in the current server session. This
wrapper applies to every ordinary registered tool, including
`defeature_faces`; job-control tools cannot recursively submit themselves.

`cancel_tool_job(job_id)` can cancel work only while it is still queued. Once
FreeCAD/OCCT has entered a main-thread operation, safe hard interruption is not
available: cancellation is recorded, the response explicitly sets
`cancellable=false`, and the caller must keep polling. This preserves MCP
responsiveness without pretending that an in-process OCCT call was stopped.

### Prompt access fallback

The server registers prompts through native MCP `prompts/list` and `prompts/get`.
When a client does not expose those protocol methods to the agent, use the
ordinary `get_freecad_prompt` tool. With no `name` it lists prompt metadata; with
`name` and an optional string `arguments` mapping it renders the same registered
prompt. This is preferable to reading prompt source files from the repository.

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
    acceptance_manifest: dict | None = None,
    target: dict | None = None,  # {"kind":"sketch", "name":"SketchName"}
    workflow: str = "native_parametric",  # or imported_brep_edit
    detail_level: str = "summary",  # summary | structure | full
    finding_offset: int = 0,
    finding_limit: int = 20,
) -> dict
```

When the input is a drawing or sketch, first inventory every source
view/detail/section and extract every explicit source dimension. Preserve and
interpret drafting markers such as an asterisk, parentheses, `REF`, or `TYP`;
they do not make a dimension optional. Assign each dimension a stable identifier,
source view, semantic source references, corresponding model elements, and validation
measurement recipe. Classify it as `driving` or `verification`; exceptional
`source_issue` requires concrete source evidence plus attempted interpretations,
and `unresolved` is not a permitted terminal manifest role. Implement driving
dimensions as named sketch constraints or connected Spreadsheet aliases and pass
the complete driving list through `required_dimension_names`. Separately check
every driving and verification dimension by reproducing its source-view context
and measuring between the same semantic elements with matching dimension
semantics. Retain expected, observed, tolerance, pass/fail, and tool evidence.
Store counts, topology, feature presence, material/process constraints, and
other non-dimensional acceptance criteria in `requirements`; `dimensions` may
legitimately be empty. The validator can verify only structure and identifiers
supplied by the caller. Evidence strings, `review_attestation`, and the legacy
`image_content_reviewed` boolean are not proof of tool execution or image
semantics. Consequently a structurally complete manifest is reported with
`verification_scope="caller_attested"`, `machine_verified=false`, and a review
finding rather than upgrading the model assessment to `healthy`.

Omit `target` for the existing whole-model/final-solid diagnostic. When the
deliverable is a sketch, pass for example
`target={"kind":"sketch","name":"Sketch_FlatPattern"}`. The assessment then
uses only that sketch: Body, solid, Tip, standalone-solid, and unused global
Spreadsheet findings are outside scope. Required dimensions must influence
non-construction geometry of the named sketch.

For an intentional STEP/BRep editing task, set
`workflow="imported_brep_edit"`. A source marked by the import tool, a source
referenced through `SourceObject`, and a result marked by
`DirectEditOperation` become `info` findings rather than generic static-shape
warnings, including `PartDesign::Feature` results stored inside a Body.
Unrelated snapshots still warn, and an invalid Shape or object error
state remains an `error`. The default `native_parametric` workflow preserves the
strict warning behavior used for models expected to have native editable history.

The report includes:

- document metadata and counts;
- each `PartDesign::Body`, shape validity, current Tip, and ordered history;
- every exact `PartDesign::Feature` solid inside a Body classified as a static
  Shape snapshot (including an explicit direct-edit marker when present), so a
  chain of generic snapshots cannot be mistaken for native parametric history;
- status strings serialized as complete entries (for example `["Valid"]`, not one character per entry);
- datum planes/lines/points marked as reference geometry, with non-applicable volume and bounding-box metrics omitted;
- sketches with solver state (`fully_constrained`, `under_constrained`,
  `over_constrained`, `conflicting`, `redundant`, or `solver_error`), remaining
  degrees of freedom, solver-reported conflicting/redundant constraint indices,
  profile state, outer/hole counts, per-wire nesting roles, intersecting wire
  pairs, supports, expressions, and constraint counts;
- standalone sketches, Spreadsheets, and solid objects outside Bodies; native
  parametric `Part::*` primitives and boolean chains are classified as editable
  Part history and do not cause a warning merely because they are outside a
  `PartDesign::Body`, while static/imported `Part::Feature` shapes still do;
- required-dimension usage, including `missing`,
  `defined_but_not_solid_driving`, and `solid_driving`
  identifiers in model scope, or `defined_but_not_sketch_driving` and
  `sketch_driving` in sketch scope;
- each Spreadsheet alias, its direct and transitive dependencies, whether it is
  connected to a feature-tree expression, and an error finding for aliases that
  remain unused;
- findings with `error`, `warning`, or workflow-context `info` severity;
- limitations: it does not prove drawing correspondence, manufacturing process,
  tolerances, design intent, or that a valid feature changed the expected amount
  of material. Use feature-level before/after volume diagnostics and visual checks.

The default response is a completion-oriented summary with paged findings.
`structure` adds Bodies, sketches, and Spreadsheet structure. `full` can be very
large because it contains complete feature history, expression bindings,
Spreadsheet cells, and optional individual constraints. Set
`include_sketch_constraints=True` only together with `detail_level="full"`, and
only when a compact response has identified a specific constraint-level problem.

`profile_ready` now requires verified closed-contour topology, not just a positive
closed-wire count. Pairwise contour intersection/tangency/overlap fails the
profile, while strict containment produces explicit `outer` and `hole` roles.
Multiple disjoint outer loops are reported separately so an agent cannot infer
hole semantics from `closed_wire_count`. The report can also warn about a sketch
dominated by point-to-origin X/Y constraints; 0 DoF is not proof of correct
geometry, datum interpretation, or design intent. The warning triggers when
there are at least eight such constraints and at least one per sketch geometry,
even when geometric relations are also numerous. Treat it as a provenance audit:
classify coordinates as source-backed, derived from a checked chain, or
solver-lock, and minimize the last category rather than banning ordinate data.

A source dimension counts only when the server can trace it to the active
validation target: the final solid in model scope or non-construction geometry
of the named sketch in sketch scope. A named constraint on construction-only
geometry, an inactive sketch, datum/helper object, or metadata-only property is
reported as not driving.
References that are structurally neutralized by multiplication by zero (for
example `0 * (Parameters.Width + Parameters.Height)`) are also reported as
non-driving; they cannot be used as an audit-only expression bridge. This is a
targeted structural guard, not a complete symbolic algebra proof.

FreeCAD marks custom properties as `Dynamic`, which normally remains a reason
to reject metadata-only expression endpoints. Native SheetMetal proxies are a
narrow exception: each known `SMBaseBend`, `SMBendWall`, `SMFoldWall`, relief,
hem, bend, extend, and from-solid proxy has its own geometry-property contract
matching the fields assigned by `create_sheet_metal_base` and
`create_sheet_metal_feature`. This includes flange `length`, gaps, relief and
miter settings; fold angle/radius/K-factor; hem dimensions; corner-relief size
and offsets; and base/from-solid thickness and radius. Those endpoints count as
solid-driving only when the feature is in the active Tip dependency graph.
Arbitrary Dynamic properties—even on the same object—remain untrusted.

For Sketcher expressions, both indexed paths such as `Constraints[12]` and
named paths such as `.Constraints.HoleCenterX` are resolved to the underlying
constraint. FreeCAD 1.0.x exposes the latter name on `Constraint.Name` rather
than through a `SketchObject.getConstraintName()` method, so the validator uses
the native constraint records and retains the same profile-versus-construction
geometry check. A named constraint on construction geometry therefore remains
non-driving even when the sketch feeds a native SheetMetal feature.

Before final completion, investigate every unused Spreadsheet alias: connect it
to the tree if it was intended to drive geometry, or remove it if it is
redundant. A clean final report must not contain missing/unlinked required
dimensions or unused Spreadsheet parameters.
Do not bulk-delete or recreate an accepted sketch constraint graph solely to
change this diagnostic. Inspect the existing dependency path, bind the semantic
feature property when appropriate, or preserve the accepted geometry and report
a tracing limitation. The compact response repeats this non-destructive policy
in `completion_guidance.non_destructive_remediation`.

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
    timeout_ms: int = 30000,
) -> dict
```

The failure response preserves `error_type`, `stderr`, duration,
`operation_state`, `transaction_state`, `continues_running`, and `request_id`.
A request cancelled while queued has `rolled_back=false` because it never opened
a transaction. A timeout after execution starts has `rolled_back=null` and an
unknown transaction state: CPython/OCCT work already running on FreeCAD's thread
cannot be interrupted safely and may still be modifying the document.

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
