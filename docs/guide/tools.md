# Tools Reference

The server currently registers **123 MCP tools**. This page is generated from the actual `@mcp.tool()` definitions in `src/freecad_mcp/tools` and is the exact inventory.

Geometry-changing operations are transaction-backed where applicable. Use `history(action="undo")` for explicit recovery, `get_console_output` for console diagnostics, and `recompute_document` for document recomputation.

## Category summary

| Category | Source | Count |
|---|---|---:|
| [Execution](#execution) | `src/freecad_mcp/tools/execution.py` | 5 |
| [Documents](#documents) | `src/freecad_mcp/tools/documents.py` | 7 |
| [Objects / Part](#objects-part) | `src/freecad_mcp/tools/objects.py` | 33 |
| [Measurements](#measurements) | `src/freecad_mcp/tools/measurements.py` | 1 |
| [PartDesign / Sketcher](#partdesign-sketcher) | `src/freecad_mcp/tools/partdesign.py` | 28 |
| [Sheet Metal](#sheet-metal) | `src/freecad_mcp/tools/sheetmetal.py` | 5 |
| [Spreadsheet](#spreadsheet) | `src/freecad_mcp/tools/spreadsheet.py` | 11 |
| [Draft](#draft) | `src/freecad_mcp/tools/draft.py` | 6 |
| [Images](#images) | `src/freecad_mcp/tools/images.py` | 3 |
| [Checkpoints](#checkpoints) | `src/freecad_mcp/tools/checkpoints.py` | 1 |
| [View / GUI / History](#view-gui-history) | `src/freecad_mcp/tools/view.py` | 10 |
| [Validation](#validation) | `src/freecad_mcp/tools/validation.py` | 5 |
| [Export / Import](#export-import) | `src/freecad_mcp/tools/export.py` | 2 |
| [Macros](#macros) | `src/freecad_mcp/tools/macros.py` | 6 |
| **Total** |  | **123** |

## Execution

| Tool | Description |
|---|---|
| `execute_python` | Execute Python code in FreeCAD's Python console context. |
| `get_freecad_version` | Get FreeCAD version and build information. |
| `get_connection_status` | Get the current FreeCAD connection status. |
| `get_console_output` | Get recent FreeCAD console output. |
| `get_mcp_server_environment` | Get environment info about the MCP Server and FreeCAD connection. |

## Documents

| Tool | Description |
|---|---|
| `list_documents` | List all open FreeCAD documents. |
| `get_active_document` | Get the currently active FreeCAD document. |
| `create_document` | Create a new FreeCAD document. |
| `open_document` | Open an existing FreeCAD document from file. |
| `save_document` | Save a FreeCAD document. |
| `close_document` | Close a FreeCAD document. |
| `recompute_document` | Recompute a FreeCAD document to update all dependent objects. |

## Objects / Part

| Tool | Description |
|---|---|
| `list_objects` | List all objects in a FreeCAD document. |
| `inspect_object` | Compact metrics by default; paged topology and full properties on request. |
| `select_subshapes` | Select paged face/edge/vertex references by semantic criteria and global location. |
| `create_object` | Create a new FreeCAD object. |
| `create_primitive` | Create a Box, Cylinder, Sphere, Cone, Torus, Wedge, or Helix. |
| `edit_object` | Edit object properties; string names are resolved for FreeCAD link properties. |
| `delete_object` | Delete an object from a FreeCAD document. |
| `boolean_operation` | Perform a boolean operation on two FreeCAD objects. |
| `set_placement` | Set the placement (position and rotation) of a FreeCAD object. |
| `scale_object` | Scale an object uniformly or non-uniformly. |
| `rotate_object` | Rotate an object around an axis. |
| `copy_object` | Create a copy of an object. |
| `mirror_object` | Mirror an object across a plane. |
| `selection` | Get, set, or clear the FreeCAD GUI selection. |
| `create_line` | Create a Part Line (edge) between two points. |
| `create_plane` | Create a Part Plane (flat rectangular face). |
| `create_ellipse` | Create a Part Ellipse curve. |
| `create_prism` | Create a Part Prism (extruded regular polygon). |
| `create_regular_polygon` | Create a Part Regular Polygon (2D wire). |
| `shell_object` | Create a shell (hollow) version of a solid by removing faces. |
| `offset_3d` | Create a 3D offset of a shape. |
| `slice_shape` | Slice a shape with a plane, returning the cross-section. |
| `section_shape` | Create a cross-section of a shape at a standard plane. |
| `make_compound` | Combine multiple shapes into a single compound. |
| `explode_compound` | Separate a compound into individual shape objects. |
| `fuse_all` | Fuse (union) multiple shapes into a single solid. |
| `common_all` | Find the common (intersection) of multiple shapes. |
| `make_wire` | Create a wire (polyline) from a list of points. |
| `make_face` | Create a face from a closed wire. |
| `extrude_shape` | Extrude a wire or face along a direction vector. |
| `revolve_shape` | Revolve a wire or face around an axis. |
| `part_loft` | Create a loft (transition shape) between multiple profiles. |
| `part_sweep` | Sweep a profile along a spine path. |

`create_regular_polygon` and `make_wire` create standalone Part objects. For geometry inside an existing Sketcher sketch, use `edit_sketch_geometry` with `add_regular_polygon` or `add_polyline`; these are sketch operations, not duplicate MCP tools.

## Measurements

`measure_geometry` is headless-safe, forces target-object recompute by default,
uses millimetres/degrees, and accepts `FaceN`, `EdgeN`, or `VertexN` references
returned by `select_subshapes`. Its required discriminator `measurement.kind`
selects one strict parameter variant, so unrelated fields cannot be mixed.

| Tool | Description |
|---|---|
| `measure_geometry` | Select `bbox`, `distance`, `angle`, `radius`, `wall_thickness`, `clearance`, `minimum_gap`, or `point_to_face` through `measurement.kind`; returns OCCT and recompute evidence. |

## PartDesign / Sketcher

| Tool | Description |
|---|---|
| `create_partdesign_body` | Create a new PartDesign Body. |
| `set_body_tip` | Set and validate the active Tip of a PartDesign Body. |
| `create_sketch` | Create a Sketch using a typed `support` selector for an origin plane, Body Tip face, explicit feature face, or datum plane. |
| `edit_sketch_geometry` | Apply geometry edits to one sketch in a single transaction, including endpoint/radius arcs and tangent line fillets. |
| `edit_sketch_constraints` | Apply constraint edits and Spreadsheet expressions in one transaction; Fix/Block may cover at most 50% of sketch geometry. |
| `pad_sketch` | Create a Pad (extrusion) from a sketch. |
| `pocket_sketch` | Create a validated Pocket; automatic direction is the default and an explicit base is optional. |
| `fillet_edges` | Add fillet (rounded edges) to an object. |
| `chamfer_edges` | Add chamfer (beveled edges) to an object. |
| `revolution_sketch` | Create a Revolution (rotational extrusion) from a sketch. |
| `groove_sketch` | Create a Groove with automatic or explicit revolution direction. |
| `thread_helix` | Create additive or subtractive editable helical geometry with validated automatic direction. |
| `create_hole` | Create a validated Hole with automatic or explicit sketch-normal direction. |
| `create_cylindrical_cut` | Create a validated cylindrical cut; automatically try the supplied world-space axis and its reverse. |
| `linear_pattern` | Create a Linear Pattern from a PartDesign feature. |
| `polar_pattern` | Create and validate a Polar Pattern from one non-pattern feature. |
| `multi_transform_pattern` | Combine linear and polar stages in one native PartDesign MultiTransform. |
| `mirrored_feature` | Create a Mirrored feature from a PartDesign feature. |
| `loft_sketches` | Create a Loft (additive) through multiple sketches. |
| `sweep_sketch` | Create a Sweep (additive) along a spine path. |
| `create_datum_plane` | Create a datum plane in a PartDesign body. |
| `create_datum_line` | Create a datum line (axis) in a PartDesign body. |
| `create_datum_point` | Create a datum point in a PartDesign body. |
| `draft_feature` | Add draft angle to faces of an object. |
| `thickness_feature` | Create a thickness (shell) feature in PartDesign. |
| `subtractive_loft` | Create a subtractive loft (cut) through multiple sketches. |
| `subtractive_pipe` | Create a subtractive pipe (sweep cut) along a spine path. |
| `get_sketch_info` | Get compact sketch status; page geometry, constraints, and expressions on request. |

## Sheet Metal

These tools require the external FreeCAD SheetMetal Workbench. They create its
native parametric `FeaturePython` objects, not final copied shapes. Keep one
linear PartDesign Body history for the formed part; the unfolded manufacturing
representation is created outside that Body.

| Tool | Description |
|---|---|
| `sheet_metal_capabilities` | Report installed SheetMetal version and availability of every wrapped native operation. |
| `create_sheet_metal_base` | Create a native flat blank or open base-wall profile from a Sketcher sketch with explicit thickness and bend radius. |
| `create_sheet_metal_feature` | Create a typed native flange, sketch-line fold, junction, relief, corner relief, extend, hem, solid bend, or solid-to-sheet conversion. |
| `unfold_sheet_metal` | Create a parametric flat pattern from a planar stationary face and an explicit K-factor/standard or material Spreadsheet. |
| `inspect_sheet_metal` | Report proxy history, thickness evidence, planar stationary-face candidates, bend-face count, Body Tip, and unfold readiness. |

Recommended sequence:

1. Call `sheet_metal_capabilities` once and create/constrain the base sketch.
2. Call `create_sheet_metal_base`. A closed sketch represents a flat blank; an
   open wire represents a wall profile.
3. Use `select_subshapes` to resolve the intended topology. Pass those exact
   references to `create_sheet_metal_feature`; never guess `EdgeN`, `FaceN`, or
   `VertexN`.
4. After each major flange or fold, inspect the formed feature and verify the
   expected panel normal and silhouette. The next operation must use the current
   Body Tip as `base_feature`.
5. Call `inspect_sheet_metal`, choose a planar stationary face from evidence,
   and create the manufacturing representation with `unfold_sheet_metal`.
6. Compare the unfold outline, bend lines, holes, and cutouts against the flat
   drawing. A successful unfold does not by itself prove shop-floor bend
   sequence, tooling access, or deep-draw manufacturability.

Example operation payloads:

```json
{
  "op": "flange",
  "base_feature": "BaseBend",
  "edges": ["Edge4"],
  "length": 25,
  "radius": 2,
  "angle": 90,
  "length_spec": "leg",
  "bend_type": "material_outside"
}
```

```json
{
  "op": "fold",
  "base_feature": "BaseBend",
  "face": "Face1",
  "bend_line_sketch": "BendLine_B1",
  "radius": 2,
  "angle": 90,
  "k_factor": 0.38,
  "position": "intersection_of_planes"
}
```

For unfolding, `material` is strict and mutually exclusive:

```json
{"k_factor": 0.38, "standard": "ansi"}
```

or:

```json
{"material_sheet": "material_DC01"}
```

Do not apply bend compensation twice to a fully dimensioned flat pattern.

## Spreadsheet

| Tool | Description |
|---|---|
| `spreadsheet_create` | Create a new Spreadsheet object. |
| `spreadsheet_set_cell` | Set the value of a cell in a spreadsheet. |
| `spreadsheet_apply_batch` | Atomically apply cells, aliases, and bindings with explicit rollback on failure. |
| `spreadsheet_get_cell` | Get the value of a cell in a spreadsheet. |
| `spreadsheet_set_alias` | Set an alias for a cell in a spreadsheet. |
| `spreadsheet_get_aliases` | Get aliases by enumerating actual spreadsheet cells. |
| `spreadsheet_clear_cell` | Safely clear a cell; preserve dependent expressions by default or detach them explicitly with `clear_bindings=True`. |
| `spreadsheet_bind_property` | Bind a property; unitless angle values are interpreted as degrees. |
| `spreadsheet_get_cell_range` | Get values from a range of cells in a spreadsheet. |
| `spreadsheet_import_csv` | Import data from a CSV file into a spreadsheet. |
| `spreadsheet_export_csv` | Export spreadsheet data to a CSV file. |

## Draft

| Tool | Description |
|---|---|
| `draft_shapestring` | Create a ShapeString (3D text geometry) using Draft workbench. |
| `draft_list_fonts` | List available font files on the system. |
| `draft_shapestring_to_sketch` | Convert a ShapeString to a Sketch for use with PartDesign. |
| `draft_shapestring_to_face` | Convert a ShapeString to a Face for direct use with Part operations. |
| `draft_text_on_surface` | Create embossed or engraved text on a surface. |
| `draft_extrude_shapestring` | Extrude a ShapeString to create a 3D solid text object. |

## Images

| Tool | Description |
|---|---|
| `open_image` | Open a local PNG/JPEG/WebP and return its pixels as MCP ImageContent. |
| `open_image_tiles` | Deliver a drawing overview plus enlarged, labelled, overlapping tiles. |
| `compare_images` | Return a labelled side-by-side comparison; mandatory after major drawing-reconstruction features and before patterning a seed. |

## Checkpoints

| Tool | Description |
|---|---|
| `evaluate_model_checkpoint` | Convert observation evidence into an optional continue/rework decision. |

## View / GUI / History

| Tool | Description |
|---|---|
| `get_screenshot` | Capture a FreeCAD view and optionally return real MCP image content. |
| `set_view_angle` | Set the 3D view angle. |
| `workbench` | List FreeCAD workbenches or activate one workbench. |
| `set_visual_properties` | Set one or more GUI display properties for a FreeCAD object. |
| `history` | Undo, redo, or inspect document history. |
| `fit_all` | Fit all objects in the current view. |
| `set_camera_position` | Set the camera position and orientation. |
| `get_camera_state` | Read camera projection, position, orientation, and scale. |
| `list_parts_library` | List available parts from the FreeCAD parts library. |
| `insert_part_from_library` | Insert a part from the parts library into the document. |

## Validation

| Tool | Description |
|---|---|
| `validate_object` | Check the health and validity of a FreeCAD object. |
| `validate_document` | Check the health of all objects in a FreeCAD document. |
| `validate_parametric_model` | Compact final diagnostic with expanded structure/full modes on request. |
| `undo_if_invalid` | Check document health and undo the last operation if invalid objects exist. |
| `safe_execute` | Execute Python code with automatic validation and rollback on failure. |

## Export / Import

| Tool | Description |
|---|---|
| `export` | Export objects to STEP, IGES, STL, 3MF, or OBJ. |
| `import` | Import a STEP or STL file into FreeCAD. |

## Macros

| Tool | Description |
|---|---|
| `list_macros` | List all available FreeCAD macros. |
| `run_macro` | Run a FreeCAD macro by name. |
| `create_macro` | Create a new FreeCAD macro. |
| `read_macro` | Read the contents of a FreeCAD macro. |
| `delete_macro` | Delete a user macro. |
| `create_macro_from_template` | Create a new macro from a predefined template. |
