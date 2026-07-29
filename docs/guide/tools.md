# Tools Reference

The server currently registers **122 MCP tools**. This page is generated from the actual `@mcp.tool()` definitions in `src/freecad_mcp/tools` and is the exact inventory.

Geometry-changing operations are transaction-backed where applicable. Use `history(action="undo")` for explicit recovery, `get_console_output` for console diagnostics, and `recompute_document` for document recomputation.

## Category summary

| Category | Source | Count |
|---|---|---:|
| [Execution](#execution) | `src/freecad_mcp/tools/execution.py` | 5 |
| [Documents](#documents) | `src/freecad_mcp/tools/documents.py` | 7 |
| [Objects / Part](#objects-part) | `src/freecad_mcp/tools/objects.py` | 38 |
| [PartDesign / Sketcher](#partdesign-sketcher) | `src/freecad_mcp/tools/partdesign.py` | 25 |
| [Spreadsheet](#spreadsheet) | `src/freecad_mcp/tools/spreadsheet.py` | 10 |
| [Draft](#draft) | `src/freecad_mcp/tools/draft.py` | 6 |
| [Images](#images) | `src/freecad_mcp/tools/images.py` | 3 |
| [Checkpoints](#checkpoints) | `src/freecad_mcp/tools/checkpoints.py` | 1 |
| [View / GUI / History](#view-gui-history) | `src/freecad_mcp/tools/view.py` | 9 |
| [Validation](#validation) | `src/freecad_mcp/tools/validation.py` | 5 |
| [Export / Import](#export-import) | `src/freecad_mcp/tools/export.py` | 7 |
| [Macros](#macros) | `src/freecad_mcp/tools/macros.py` | 6 |
| **Total** |  | **122** |

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
| `inspect_object` | Get detailed information about a FreeCAD object. |
| `create_object` | Create a new FreeCAD object. |
| `create_box` | Create a Part Box primitive. |
| `create_cylinder` | Create a Part Cylinder primitive. |
| `create_sphere` | Create a Part Sphere primitive. |
| `create_cone` | Create a Part Cone primitive. |
| `create_torus` | Create a Part Torus (donut shape) primitive. |
| `create_wedge` | Create a Part Wedge primitive. |
| `create_helix` | Create a Part Helix curve. |
| `edit_object` | Edit properties of an existing FreeCAD object. |
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

## PartDesign / Sketcher

| Tool | Description |
|---|---|
| `create_partdesign_body` | Create a new PartDesign Body. |
| `create_sketch` | Create a new Sketch attached to an origin plane, datum plane, or face. |
| `edit_sketch_geometry` | Apply geometry edits to one sketch in a single transaction. |
| `edit_sketch_constraints` | Apply constraint edits to one sketch in a single transaction. |
| `pad_sketch` | Create a Pad (extrusion) from a sketch. |
| `pocket_sketch` | Create a Pocket (cut extrusion) from a sketch. |
| `fillet_edges` | Add fillet (rounded edges) to an object. |
| `chamfer_edges` | Add chamfer (beveled edges) to an object. |
| `revolution_sketch` | Create a Revolution (rotational extrusion) from a sketch. |
| `groove_sketch` | Create a Groove (subtractive revolution) from a sketch. |
| `create_hole` | Create a validated Hole feature from a face- or origin-plane sketch. |
| `create_cylindrical_cut` | Create a validated cylindrical cut with an explicit world-space axis. |
| `linear_pattern` | Create a Linear Pattern from a PartDesign feature. |
| `polar_pattern` | Create a Polar (circular) Pattern from a PartDesign feature. |
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
| `get_sketch_info` | Get detailed information about a sketch. |

## Spreadsheet

| Tool | Description |
|---|---|
| `spreadsheet_create` | Create a new Spreadsheet object. |
| `spreadsheet_set_cell` | Set the value of a cell in a spreadsheet. |
| `spreadsheet_get_cell` | Get the value of a cell in a spreadsheet. |
| `spreadsheet_set_alias` | Set an alias for a cell in a spreadsheet. |
| `spreadsheet_get_aliases` | Get all aliases defined in a spreadsheet. |
| `spreadsheet_clear_cell` | Clear a cell in a spreadsheet. |
| `spreadsheet_bind_property` | Bind an object property to a spreadsheet cell using expressions. |
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
| `compare_images` | Return a labelled side-by-side comparison as one MCP image. |

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
| `list_parts_library` | List available parts from the FreeCAD parts library. |
| `insert_part_from_library` | Insert a part from the parts library into the document. |

## Validation

| Tool | Description |
|---|---|
| `validate_object` | Check the health and validity of a FreeCAD object. |
| `validate_document` | Check the health of all objects in a FreeCAD document. |
| `validate_parametric_model` | Inspect the document's editable parametric structure before completion. |
| `undo_if_invalid` | Check document health and undo the last operation if invalid objects exist. |
| `safe_execute` | Execute Python code with automatic validation and rollback on failure. |

## Export / Import

| Tool | Description |
|---|---|
| `export_step` | Export objects to STEP format. |
| `export_stl` | Export objects to STL format. |
| `export_3mf` | Export objects to 3MF format. |
| `export_obj` | Export objects to OBJ format. |
| `export_iges` | Export objects to IGES format. |
| `import_step` | Import a STEP file into FreeCAD. |
| `import_stl` | Import an STL file into FreeCAD. |

## Macros

| Tool | Description |
|---|---|
| `list_macros` | List all available FreeCAD macros. |
| `run_macro` | Run a FreeCAD macro by name. |
| `create_macro` | Create a new FreeCAD macro. |
| `read_macro` | Read the contents of a FreeCAD macro. |
| `delete_macro` | Delete a user macro. |
| `create_macro_from_template` | Create a new macro from a predefined template. |
