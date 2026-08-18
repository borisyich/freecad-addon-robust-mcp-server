# FreeCAD Robust MCP User Guide

This guide explains how to use AI assistants with FreeCAD via the MCP (Model Context Protocol) server to create and manipulate 3D CAD models.

---

## Table of Contents

1. [Getting Started](#getting-started)
1. [Running Modes](#running-modes)
1. [Basic Workflows](#basic-workflows)
1. [Object Creation Examples](#object-creation-examples)
1. [PartDesign Workflow](#partdesign-workflow)
1. [Complete Example: Mounting Bracket](#complete-example-mounting-bracket)
1. [Tips and Best Practices](#tips-and-best-practices)

---

## Getting Started

### Prerequisites

1. **FreeCAD installed** - Version 1.0.x or later
1. **An MCP client** (Claude Code, or other MCP-compatible AI assistant) configured
1. **Python 3.11** - Must match FreeCAD's bundled Python version

### Starting FreeCAD with MCP Bridge

You have two options depending on your workflow:

#### Headless Mode (Command-line only)

Best for automated workflows, batch processing, or when you don't need visual feedback.

```bash
just freecad::run-headless
```

**Capabilities:** All modeling operations, export, scripting.
**Limitations:** No screenshots, no visual feedback, no color/visibility control.

#### GUI Mode (Full graphical interface)

Best for interactive design work where you want to see results visually.

```bash
just freecad::run-gui
```

**Capabilities:** Everything headless mode can do, plus screenshots, colors, view control.

### Verifying Connection

Once FreeCAD is running with the MCP bridge, you can verify the connection:

```text
"Check the FreeCAD connection status"
```

Claude will use the `get_connection_status` tool to confirm the bridge is working.

---

## Running Modes

### Headless vs GUI Mode

| Feature                  | Headless Mode | GUI Mode |
| ------------------------ | ------------- | -------- |
| Object creation          | Yes           | Yes      |
| Boolean operations       | Yes           | Yes      |
| Export (STEP, STL, etc.) | Yes           | Yes      |
| Save documents           | Yes           | Yes      |
| Screenshots              | No            | Yes      |
| Object colors            | No            | Yes      |
| Object visibility        | No            | Yes      |
| Camera control           | No            | Yes      |
| Interactive selection    | No            | Yes      |

### Detecting the Current Mode

When working with Claude, it will automatically detect whether FreeCAD is in GUI or headless mode and adapt accordingly. GUI-only operations will return informative errors in headless mode rather than crashing.

---

## Basic Workflows

### Creating a Document

Every FreeCAD project needs a document. You can ask Claude:

```text
"Create a new FreeCAD document called 'MyProject'"
```

Claude will use the `create_document` tool.

### Creating Simple Shapes

Ask Claude to create primitive shapes:

```text
"Create a box that's 50mm long, 30mm wide, and 10mm tall"
"Add a cylinder with radius 5mm and height 20mm"
"Create a sphere with 15mm radius"
```

### Positioning Objects

Move and rotate objects:

```text
"Move the box to position (100, 50, 0)"
"Rotate the cylinder 45 degrees around the Z axis"
```

### Boolean Operations

Combine shapes:

```text
"Fuse the box and cylinder together"
"Cut a hole through the box using the cylinder"
"Find the intersection of the two shapes"
```

### Saving and Exporting

```text
"Save the document as MyProject.FCStd"
"Export the model to STEP format"
"Export for 3D printing as STL"
```

---

## Object Creation Examples

### Example 1: Simple Box with Hole

**Request:**

```text
Create a 50x50x20mm box with a 10mm diameter hole through the center.
```

**What Claude does:**

1. Creates a document
1. Creates a box (50x50x20)
1. Creates a cylinder (radius 5, height 30) positioned at center
1. Performs boolean cut operation
1. Returns the result

### Example 2: Pipe/Tube Shape

**Request:**

```text
Create a pipe with outer diameter 40mm, inner diameter 30mm, and length 100mm.
```

**What Claude does:**

1. Creates outer cylinder (radius 20, height 100)
1. Creates inner cylinder (radius 15, height 100)
1. Cuts inner from outer to create hollow tube

### Example 3: L-Bracket

**Request:**

```text
Create an L-shaped bracket:
- Horizontal part: 100mm x 50mm x 5mm
- Vertical part: 5mm x 50mm x 80mm standing on the horizontal part
```

**What Claude does:**

1. Creates horizontal box
1. Creates vertical box positioned at correct location
1. Fuses them together

---

## PartDesign Workflow

For parametric modeling that maintains design history, use the PartDesign workflow.

### Understanding PartDesign Concepts

**Body**: A container for a single solid model built from features.

**Sketch**: A 2D drawing that defines profiles for 3D operations.

**Features**: Operations like Pad (extrude), Pocket (cut), Fillet, etc.

### Basic PartDesign Example

**Request:**

```text
Create a parametric mounting plate:
1. Start with a PartDesign body
2. Create a sketch on the XY plane with a 100x60mm rectangle
3. Pad it 8mm thick
4. Add four 5mm holes near each corner for mounting screws
5. Fillet all edges with 2mm radius
```

**What Claude does:**

1. `create_partdesign_body()` - Creates the Body container
1. `create_sketch(body_name="Body", support={"kind": "origin_plane", "plane": "XY_Plane"})` - Creates attached sketch
1. `edit_sketch_geometry(...)` - Adds the profile geometry as a batch
1. `pad_sketch(sketch_name="Sketch", length=8)` - Extrudes to solid
1. Identifies the planar top face geometrically
1. Creates a new face-attached sketch with circles at the hole locations
1. Calls one validated `create_hole(...)` for the circle group
1. `fillet_edges(...)` - Rounds the edges

### Revolving Profiles

**Request:**

```text
Create a turned part:
- Draw a profile on the XZ plane
- Revolve it 360 degrees around the X axis
```

**What Claude does:**

1. Creates body and sketch on XZ plane
1. Draws the profile using lines and arcs
1. Uses `revolution_sketch()` to create the solid

Two common radius-defined sketch arcs are available:

```python
# Arc through two endpoints with a known radius.
edit_sketch_geometry(
    sketch_name="TurnProfile",
    operations=[{
        "op": "add_arc",
        "arc_mode": "endpoints_radius",
        "x1": 0,
        "y1": 0,
        "x2": 20,
        "y2": 0,
        "radius": 15,
        "arc_side": "left",
    }],
)

# Tangent radius joining two existing line segments; the lines are trimmed.
edit_sketch_geometry(
    sketch_name="TurnProfile",
    operations=[{
        "op": "add_arc",
        "arc_mode": "tangent_fillet",
        "line1_index": 0,
        "line2_index": 1,
        "radius": 4,
    }],
)
```

Fix/Block constraints are deliberately limited: they may constrain at most 50%
of sketch geometry. Use geometric and dimensional constraints for design intent.

### Pattern Operations

**Request:**

```text
Create a plate with a row of 6 holes spaced 15mm apart.
```

**What Claude does:**

1. Creates the base plate
1. Creates one hole feature
1. For drawing reconstruction, compares that single hole against the matching
   source view with `compare_images`.
1. Uses `linear_pattern()` to repeat the accepted hole. For combined linear and circular repetition, uses `multi_transform_pattern()` instead of chaining one Pattern onto another.

---

## Complete Example: Mounting Bracket

This detailed example shows a complete workflow for creating a practical part.

### Design Requirements

Create a mounting bracket with:

- Base plate: 80mm x 60mm x 5mm
- Vertical support: 5mm thick, 50mm tall, 60mm wide
- Two mounting holes (6mm diameter) on the base
- One slot (10mm x 20mm) on the vertical support
- 3mm fillets on external corners

### Step-by-Step Workflow

#### Step 1: Ask Claude to create the bracket

```text
Create a mounting bracket with the following specifications:

Base plate:
- Size: 80mm x 60mm x 5mm
- Two 6mm diameter mounting holes, centered 15mm from each short edge

Vertical support:
- Attached to one end of the base
- 5mm thick, 60mm wide, 50mm tall
- One slot: 10mm wide x 20mm tall, centered

Finish:
- 3mm fillet on all outer edges
- Export as STEP file when done
```

#### Step 2: Claude's approach

Claude will break this down into manageable operations:

```python
# 1. Create document and PartDesign body
create_document(name="MountingBracket")
create_partdesign_body(name="Body")

# 2. Create base plate sketch and pad
create_sketch(body_name="Body", support={"kind": "origin_plane", "plane": "XY_Plane"}, name="BaseSketch")
edit_sketch_geometry(sketch_name="BaseSketch", operations=[{"op": "add_rectangle", "x": 0, "y": 0, "width": 80, "height": 60}])
pad_sketch(sketch_name="BaseSketch", length=5)

# 3. Add vertical support
create_sketch(body_name="Body", support={"kind": "origin_plane", "plane": "XZ_Plane"}, name="SupportSketch")
# ... add geometry
pad_sketch(sketch_name="SupportSketch", length=60)

# 4. Add mounting holes after all additive features.
# Determine the actual planar top face first; do not guess FaceN.
create_sketch(body_name="Body", support={"kind": "feature_face", "feature": "Pad", "face": "Face6"}, name="HoleSketch")
edit_sketch_geometry(
    sketch_name="HoleSketch",
    operations=[
        {"op": "add_circle", "center_x": 15, "center_y": 30, "radius": 3},
        {"op": "add_circle", "center_x": 65, "center_y": 30, "radius": 3},
    ],
)
hole = create_hole(sketch_name="HoleSketch", diameter=6, hole_type="ThroughAll")
# Continue only when hole["validated"] is true and hole["removed_volume"] > 0.

# A radial/off-face hole is not a create_hole + datum-plane workflow.
oil_hole = create_cylindrical_cut(
    body_name="Body",
    axis_origin=[0, 20, 40],
    axis_direction=[0, 0, -1],
    diameter=5,
    depth=8,
    name="OilHole",
)

# 5. Add slot (as pocket)
create_sketch(body_name="Body", support={"kind": "body_tip_face", "face": "Face1"}, name="SlotSketch")
edit_sketch_geometry(sketch_name="SlotSketch", operations=[{"op": "add_rectangle", "x": 0, "y": 0, "width": 10, "height": 20}])
pocket_sketch(
    sketch_name="SlotSketch",
    length=5,
    type="ThroughAll",
    direction="auto",
    base_feature_name="Pad",
)

# For an up-to-face pocket, name the target explicitly:
# pocket_sketch(
#     sketch_name="SlotSketch",
#     length=5,
#     type="UpToFace",
#     up_to_face="Pad.Face6",
# )

# 6. Add fillets
fillet_edges(object_name="...", radius=3)

# 7. Export
export(file_format="step", file_path="/path/to/bracket.step")
```

#### Step 3: View the result (GUI mode)

```text
Take a screenshot of the bracket from an isometric view
```

The agent should use `get_screenshot(view_angle="Isometric", return_image=True)` so the pixels are returned as MCP image content. The global X/Y/Z corner cross is included by default (`show_corner_cross=True`, `corner_cross_size=10`) so the agent can verify camera and model orientation. The screenshot pipeline paints this triad into the PNG after `saveImage`, because FreeCAD's native screen-space corner cross is not guaranteed to survive off-screen rendering. Check `corner_cross_embedded=true` and `corner_cross_render_mode="qimage_overlay"` in the metadata. Set `show_corner_cross=False` only for a clean presentation image.

`get_screenshot` also waits `settle_time_seconds=2.0` by default after camera
alignment and `fitAll`, while processing GUI events and redraws. This is
important when an agent sets a standard view and immediately captures it.

For drawing reconstruction, identify the view-to-plane map before modeling:
Front/Rear → XZ with depth along Y; Top/Bottom → XY with depth along Z;
Left/Right → YZ (ZOY) with depth along X. Select a sketch plane from the view
that shows the feature's true profile, and obtain extrusion depth from another
view or an explicit callout.

Call `open_image(path)` for the overview and use `open_image_tiles` when local
dimensions/features are too small. Before creating geometry, save every explicit
dimension except dimensions marked with an asterisk and assign each a stable
identifier. Compare only equivalent views and pass a short `view_context` to
`compare_images`. During drawing reconstruction, run it after every major
feature; a screenshot alone is not a completed visual checkpoint. Compare the
single seed before any pattern. If one pair is uncertain, compare all principal
target views that exist—front, matching side, top, then isometric.
`compare_images` is visual assistance rather than an automatic correctness
metric; use formal checkpoints only when the task benefits from them.

---

## Reliable PartDesign Feature Selection

- Directional subtractive tools default to `direction="auto"` and retain only a Shape/Tip-valid result with a measurable volume decrease. `pocket_sketch` and `create_hole` use `normal`/`reversed` relative to the global sketch normal; `create_cylindrical_cut`, `groove_sketch`, and `thread_helix` use `forward`/`reversed`. Explicit directions never fall back. For `pocket_sketch`, an optional `base_feature_name` selects the authoritative base; otherwise it prefers a valid preceding Body Tip, then the nearest valid preceding solid.
- Sketch-based Pad, Pocket, Revolution, and Groove share `type` end conditions. Linear features accept `Length`; rotational features accept `Angle`; all four also accept `ThroughAll`, `UpToFirst`, and `UpToFace`. Supply `up_to_face="Feature.FaceN"` only with `UpToFace`. Additive `ThroughAll` is translated to FreeCAD's native `UpToLast` mode. Generic `extrude_shape` remains a fixed-vector B-rep operation; use `pad_sketch` when termination depends on Body material or a target face.
- `set_body_tip` changes the active Body result without using `edit_object` or GUI selection and validates the resulting Shape/Tip contract.
- `linear_pattern` and `polar_pattern` are for one transformation of a non-pattern seed. Use `multi_transform_pattern` for combined linear and polar stages. For drawing reconstruction, accept the single seed through `compare_images` before repeating it.
- Pattern, Pocket, and thread responses include before/after volume diagnostics. A valid Shape is not proof that the intended amount of material changed.
- `boolean_operation` aborts its transaction for a null/invalid Shape or a solid
  count different from `expected_solid_count` (default `1`). Successful results
  return Shape/type/count plus base, tool, result, and delta volumes. Set the
  expectation to `None` only for an intentional multi-solid result.
- A failed `fillet_edges` rolls back and returns structured source/selection,
  adjacent-face, radius, result-state, and per-edge trial evidence. When every
  edge succeeds individually but the group fails, inspect `failing_edge_groups`.
- `thread_helix` creates native additive or subtractive helical geometry from an editable profile sketch.
- `spreadsheet_apply_batch` stages numeric/structured-Quantity values, aliases, alias-dependent formulas, and property bindings in one transaction. Use `{"value":40,"unit":"mm"}` for a Quantity, `formula="=..."` for a formula, and `text="..."` for literal text; ambiguous raw string values such as `"40 mm"` are rejected. After recompute it evaluates every non-empty formula cell on the sheet, including unchanged formulas that depend on a modified cell or alias. Any formula failure restores affected cells, aliases, and expressions. Report View formula errors are surfaced as `FreeCADReportError` rather than success.
- A unitless spreadsheet number bound to an angle property is interpreted in degrees, so `360` can safely drive `PolarPattern.Angle`. Supply an explicit angle to batch as `{"value":360,"unit":"deg"}`.
- Around direct edits, call `capture_shape_checkpoint` before mutation and `compare_shape_checkpoint` after it. The comparison always reports solid/topology counts, validity, and bounding-box/volume/area deltas. Its default `difference_mode="auto"` localizes added/removed regions with OCCT only below the configured face-product complexity limit; use `metrics` for imported B-reps when no booleans are wanted, or `exact` with an explicit timeout when localization is essential.
- Shape checkpoints serialize the original Shape directly so OCCT preserves the
  full native location graph. Capture verifies topology, mass properties, and the
  placement transform after BREP import; metric comparison reuses the captured
  bbox because OCCT may tighten a restored bbox slightly for identical geometry.
- For imported/static B-reps, `move_faces(method="feature_rebuild")` is the
  topology-aware path for recognized local planar boundaries and transition
  chains. Inspect `performed_method`; `prism_boolean_fallback` is only a sharp
  prismatic compatibility result, not general push-pull.
- When an exact checkpoint difference is performed, `volume_tolerance` governs the summary `geometric_change` flag. Smaller OCCT sliver regions are still returned for diagnosis but do not override the threshold. Metric-only comparisons leave `geometric_change=None` and report the cheaper `metric_change_detected` signal instead.
- Exact checkpoint results discard non-null but topologically empty OCCT
  Compounds, so zero-face/zero-edge regions with sentinel infinite bounds are not
  counted as added or removed.
- Change a Hole thread profile and size together, for example `edit_object("Hole", {"ThreadType": "ISO_FINE", "ThreadSize": "M12x1.25"})`; this prevents FreeCAD from silently resetting the size.

## Tips and Best Practices

The canonical engineering policy is `.agents/skills/freecad-engineering/SKILL.md`
(or MCP resource `freecad://skills/freecad-engineering`). It classifies stock and
process, covers milling/turning/sheet-metal strategies, and requires
`validate_parametric_model` before the final response after geometry changes.
For intentional edits of imported STEP/BRep geometry, pass
`workflow="imported_brep_edit"`; import sources and results carrying
`DirectEditOperation` plus `SourceObject` are then informational, while broken
shapes remain errors. Keep the default `native_parametric` workflow for models
expected to have native editable history.
For drawing/sketch input, save every non-starred dimension but classify it as
driving, verification, or unresolved. Pass the complete driving list as
`required_dimension_names`; retain deterministic measured evidence for every
verification item. The final report also flags Spreadsheet aliases that
do not drive the feature tree directly or through other cells; connect intended
parameters or delete redundant ones.

For a sketch-only deliverable, call
`validate_parametric_model(target={"kind":"sketch","name":"SketchName"}, ...)`.
This checks required-dimension influence on non-construction geometry of that
sketch without treating Body, solid, or Tip state as an error. Profile readiness
includes outer/hole nesting and contour-intersection checks; five closed wires no
longer imply one outer loop and four holes.

Build drawing-derived sketches from straight segments and semantic relationships
first, then insert stated tangent fillets/radii. Use a B-spline only for a source
curve explicitly defined by points or knots. Preserve the datum/reference of
every ordinate/baseline dimension and close one control dimension chain before
converting it to global coordinates. A 0-DoF sketch can still be geometrically or
dimensionally wrong.

### 1. Be Specific with Dimensions

**Good:** "Create a box 50mm x 30mm x 10mm"

**Vague:** "Create a small box"

### 2. Specify Units

FreeCAD uses millimeters by default. Always include units to avoid confusion:

```text
"Create a cylinder with 25.4mm (1 inch) diameter"
```

### 3. Use Meaningful Names

```text
"Create a box named 'BasePlate' and a cylinder named 'MountingHole'"
```

This makes it easier to reference objects later.

### 4. Work Incrementally

For complex parts, build step by step:

1. Create one logically reviewable feature.
1. Recompute and inspect topology, then deterministic dimensions and volume effect.
1. For drawing reconstruction, compare the equivalent reference and candidate
   views with `compare_images` only after the numerical checks.
1. Update the discrepancy ledger and revise source interpretation as well as CAD
   when observations invalidate the current hypothesis.
1. Rework invalid or clearly incorrect geometry before adding dependent features.
1. Use compact `inspect_object()` or `detail_level="shape"` for routine checks.
   Request paged `topology` only for face/edge/vertex evidence and `full` only for a
   specific property diagnosis. Use `select_subshapes` instead of iterating every
   face or edge when choosing sketch support, Fillet, Chamfer, Draft, or Thickness.
1. Immediately before the final response, call `validate_parametric_model`. For
   drawing/sketch input include all driving dimension identifiers and verify all
   check dimensions, then resolve missing/unlinked dimensions or unused
   Spreadsheet aliases before completion.

### Semantic face, edge, and vertex selection

`inspect_object(detail_level="topology")` returns a paged topology catalogue. Faces include
surface type, a representative oriented normal, area, adjacent faces, and local
  convexity; cylindrical and conical faces additionally include radius, axis direction,
  and a point on the axis. Faces and edges can expose adjacent surface types.
  Edges include curve type, endpoints, length, direction/radius, and
adjacent faces. Vertices include a world point, tolerance, and adjacent
edges/faces. Use `select_subshapes` to convert engineering intent into `FaceN`,
`EdgeN`, or `VertexN`:

```python
# Highest upward planar face for sketch support.
select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "face", "surface_types": ["Plane"],
        "normal": [0, 0, 1], "sort_by": "center_z",
        "sort_order": "desc", "limit": 1,
    },
    detail_level="summary",
)

# Cylindrical bosses/holes near a known axis, without one measure_radius call per face.
select_subshapes(
    object_name="Imported",
    criteria={
        "kind": "face", "surface_types": ["Cylinder"],
        "radius_min": 4.99, "radius_max": 5.01,
        "axis_direction": [0, 0, 1],
        "axis_point": [20, 10, 0], "axis_point_tolerance": 0.01,
        "adjacent_surface_types": ["Cone"],
    },
    detail_level="summary", page_size=200,
)

# Four longest X-parallel straight edges for a fillet/chamfer candidate set.
select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "edge", "curve_types": ["Line"],
        "direction": [1, 0, 0], "sort_by": "length",
        "sort_order": "desc", "limit": 4,
    },
)

# Highest vertex in a narrow world-X band for point-to-face measurement.
select_subshapes(
    object_name="Pad",
    criteria={
        "kind": "vertex", "point_bounds": {"x_min": 19.9, "x_max": 20.1},
        "sort_by": "point_z", "sort_order": "desc", "limit": 1,
    },
)
```

The selector narrows candidates but does not replace geometric verification.
Its wire schema is a single flat `criteria` object so clients can display every
filter instead of a ref-only `unknown` union; fields that do not apply to the
selected `kind` are rejected before FreeCAD execution.
`criteria.limit` and `page_size` both accept up to 200 results. Cylinder/cone-axis
direction is undirected, and `axis_point` may be any point on the expected
infinite axis.
Inspect the returned records and confirm the selected references on the current
Body Tip before creating topology-sensitive downstream features.

Before every local edit—hole, boss, pocket wall, rib, flange, thickness change,
or direct face move—inspect the target's topology neighborhood:

```python
inspect_subshape_neighborhood(
    object_name="Imported",
    reference="Face3",
    hops=1,
)
```

The compact target/neighbor records make transitions, attachments, functional
interfaces, and nearby invariant faces visible without manually following each
face name. Treat the selected face as an edit handle, not as the whole feature.
After recompute, reselect transient references and repeat the same neighborhood,
measurement, section/view, validity, and solid-count checks. If any non-target
face, transition, attachment, continuity, interface, or nearby invariant is
damaged, undo the causal edit or reconstruct the original design intent before
continuing. For imported STEP/static B-reps, bracket this loop with
`capture_shape_checkpoint` and `compare_shape_checkpoint`.

### Measurement evidence

Use the dedicated `measure_*` tools instead of deriving dimensions from a
screenshot or cached `inspect_object` bounds. They force recompute by default,
accept references returned by `select_subshapes`, and expose only the fields
needed by the selected operation. `measure_geometry` remains for compatibility.

```python
bounds = await measure_bounding_box(
    object_name="Body", mode="optimal", coordinate_system="world",
    use_triangulation=False, use_shape_tolerance=False,
)

clearance = await measure_clearance(
    first={"object_name": "PartA"}, second={"object_name": "PartB"},
    required_clearance_mm=0.25,
)

point_gap = await measure_point_to_face(
    face={"object_name": "PartA", "subshape": "Face3"},
    vertex={"object_name": "PartB", "subshape": "Vertex7"},
)
```

Use `measure_distance` for a scalar minimum with closest-point evidence;
`measure_clearance` when a pass/fail requirement and solid interference matter;
and `measure_minimum_gap` to find the closest pair within a bounded reference
set. `kind="wall_thickness"` validates opposing planar/cylindrical faces before
accepting their distance as thickness.
Distance responses call the threshold flag `within_distance_threshold`.

### Spreadsheet expressions for sketch constraints

Create the Spreadsheet cell and alias first, then bind the dimensional
constraint through its expression path:

```python
edit_sketch_constraints(
    sketch_name="BaseSketch",
    operations=[{
        "op": "distance", "geometry1": 0, "value": 80,
        "constraint_name": "PlateWidth",
        "expression": "Dimensions.PlateWidth",
    }],
)
```

The tool binds through `Constraints[index]`; the readable constraint name does
not choose the target. FreeCAD may report the same binding using a canonical
named path after the constraint is renamed. Existing links can be changed or
removed atomically:

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

Use compact `get_sketch_info()` for status and counts. Request
`detail_level="geometry"`, `"constraints"`, or paged `"full"` only to inspect
geometry endpoints and type-specific data,
constraint references/datums/names, and expression bindings. Constraint
expression entries expose a stable `Constraints[index]` path; when FreeCAD
reports a different canonical source path, it is preserved as `source_path`.
Use explicit units for literal constants inside expressions. Constraint indices
in MCP requests are zero-based. The GUI/solver commonly shows one-based
numbers, so subtract one when copying a displayed number (GUI 16 becomes
`constraint_index=15`). Sketch responses include both forms.

### 5. Save Frequently

```text
"Save the document"
```

FreeCAD can crash, and you don't want to lose work.

### 6. Use PartDesign for Parametric Parts

If you might need to modify dimensions later, use the PartDesign workflow with sketches rather than direct Part operations.

### 7. Export to Multiple Formats

For manufacturing or 3D printing:

```text
"Export as STEP for CNC machining and STL for 3D printing"
```

### 8. Python and macros remain available

`execute_python`, `safe_execute`, and `run_macro` may be used whenever they are the clearest reliable method. When producing a parametric part, they should still create native Bodies, sketches, constraints, and semantic features rather than only a final direct Shape:

```text
"Calculate the volume and center of mass of the part"
```

Claude will use `execute_python()` to run the necessary FreeCAD Python commands.

### 9. Check GUI Mode for Visual Features

Before asking for screenshots or colors:

```text
"Is FreeCAD running in GUI mode?"
```

### 10. Use Patterns for Repetitive Features

Instead of creating many individual features:

```text
"Create one hole and pattern it in a 4x3 grid with 20mm spacing"
```

---

## Common Operations Quick Reference

| Task             | How to Ask                                              |
| ---------------- | ------------------------------------------------------- |
| Create box       | "Create a box 50x30x10mm"                               |
| Create cylinder  | "Create a cylinder with 10mm radius and 20mm height"    |
| Move object      | "Move MyBox to position (100, 50, 0)"                   |
| Rotate object    | "Rotate MyCylinder 45 degrees around Z axis"            |
| Boolean union    | "Fuse Box and Cylinder together"                        |
| Boolean subtract | "Cut Cylinder from Box"                                 |
| Create hole      | "Add a 6mm through hole at (25, 15)"                    |
| Fillet edges     | "Add 3mm fillet to all edges"                           |
| Chamfer edges    | "Add 2mm chamfer to selected edges"                     |
| Export STEP      | "Export to STEP format"                                 |
| Export STL       | "Export for 3D printing"                                |
| Save document    | "Save the document as MyPart.FCStd"                     |
| Screenshot       | "Take a screenshot from the front view" (GUI mode only) |
| Change color     | "Make the box red" (GUI mode only)                      |

---

## Troubleshooting

### "GUI not available" Error

You're running in headless mode and trying to use a GUI-only feature. Either:

- Switch to GUI mode: `just freecad::run-gui`
- Use an alternative approach (e.g., skip visual operations)

### Objects Not Appearing

Make sure to recompute the document:

```text
"Recompute the document"
```

### Boolean Operations Failing

Ensure:

1. Both objects have valid shapes
1. The objects actually intersect
1. Objects are in the same document

### Sketch Errors

Sketches need to be fully constrained for PartDesign operations. Ask Claude to:

```text
"Check if the sketch is fully constrained"
```

### Connection Issues

If the MCP bridge isn't responding:

1. Check FreeCAD is running with the bridge started
1. Verify ports 9875 (XML-RPC) and 9876 (socket) are available
1. Restart FreeCAD with `just freecad::run-gui` or `just freecad::run-headless`

---

## Next Steps

- See [MCP_TOOLS_REFERENCE.md](MCP_TOOLS_REFERENCE.md) for detailed API documentation
- Explore the FreeCAD wiki for advanced techniques
- Practice with simple parts before attempting complex assemblies

## Examples of user prompts

### drawing from https://huggingface.co/spaces/HuggingAI4Engineering/CADGenBench № 128
The target drawing of the part is located at "path\to\image.png".
Task: Act as a designer and lay out the part in a plan of action for constructing a 3D model of the part.
Next, use freecad-mcp and 3D model the part.
IMPORTANT:
1. The 3D model must be parametric for easy editing.
2. Use the "act-observe-reaction" engineering cycle.
For a full description of the work and available skills, please refer to the file path\to\freecad-addon-robust-mcp-server\AGENTS.md.
Also, use the MCP resources and prompts – they describe many useful and important things for a design engineer.
3. Verify every step of your work.
4. The default safe_execute and execute_python tools are not required. Use them only in cases where you cannot complete the task using other standard mcp tools.
