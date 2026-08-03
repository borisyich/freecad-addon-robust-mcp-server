"""FreeCAD Robust MCP prompts for common CAD tasks.

This module provides reusable prompt templates that help MCP-compatible AI
assistants understand FreeCAD concepts and work through complex tasks.

Prompt Categories:
    - Design Workflows: Part design, sketching, modeling
    - Export/Import: File format handling
    - Analysis: Shape inspection, validation
    - Macro Development: Scripting guidance
    - Troubleshooting: Common issues and solutions
"""

from typing import Any, Literal

from freecad_mcp.guidance import (
    DRAWING_RECONSTRUCTION_WORKFLOW,
    ENGINEERING_SKILL_RELATIVE_PATH,
    ENGINEERING_SKILL_RESOURCE_URI,
    FINAL_PARAMETRIC_VALIDATION_TOOL,
    MODEL_MODIFICATION_WORKFLOW,
    VISUAL_CHECKPOINT_PROTOCOL,
)


def register_prompts(mcp: Any, get_bridge: Any) -> None:  # noqa: ARG001
    """Register FreeCAD prompts with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge (unused but kept
            for interface consistency with other register functions).
    """
    # =========================================================================
    # Session bootstrap prompt (explicit invocation may be required)
    # =========================================================================

    @mcp.prompt()
    async def freecad_startup() -> str:
        """Essential startup guidance for AI assistants.

        Clients can discover this prompt, but invocation may require explicit
        user or client configuration. Repository instruction files remain the
        durable bootstrap layer.

        This prompt provides:
        - Session initialization checklist
        - Critical patterns to follow
        - Version compatibility notes
        - Quick reference for common operations

        Returns:
            Essential startup guidance for FreeCAD MCP sessions.

        Example:
            Invoke via MCP prompt mechanism::

                # In an MCP client
                guidance = await mcp.get_prompt("freecad_startup")
                print(guidance)  # Displays session initialization checklist
        """
        return f"""# FreeCAD MCP session bootstrap

For any task that creates, reconstructs, modifies, repairs, or validates a
mechanical model, activate `$freecad-engineering`. The canonical policy is
`{ENGINEERING_SKILL_RELATIVE_PATH}` and is also available through
`{ENGINEERING_SKILL_RESOURCE_URI}`.

## Session Checklist

1. Check connection and FreeCAD/GUI availability.
2. Inspect and reuse the intended document.
3. Read/activate the engineering Skill before modeling.
4. Choose the likely stock form and dominant process before selecting the base
   feature.

## Critical Rules

- Prefer standard MCP tools. `safe_execute` and `execute_python` are fallback
  mechanisms only when a required standard tool is missing or demonstrably
  invalid.
- Use one explicit document and one PartDesign Body per part; do not hide errors
  in duplicate documents or Bodies.
- Validate FreeCAD geometry and requirement correspondence separately. A valid
  solid can still be the wrong part.
- Follow the Skill's ACT → OBSERVE → REACT loop after each major feature.
  Establish the drawing-view/FreeCAD-plane contract before modeling, capture a
  settled screenshot in the equivalent view, and rework the causal feature when
  the available views disagree. A formal discrepancy ledger/checkpoint is
  optional rather than a universal gate.
- Preserve native editable design intent: Body, sketches, constraints, and
  semantic PartDesign history unless the user explicitly asks for direct B-rep.
- `execute_python`, `safe_execute`, and `run_macro` are always available. Using
  them does not waive the parametric/editability expectations in the Skill.
- Resolve drawing ambiguity autonomously using the most consistent evidence and
  disclose assumptions.
- Immediately before the final user-facing response after any geometry change,
  call `{FINAL_PARAMETRIC_VALIDATION_TOOL}` and summarize significant findings.

## Quick Reference

| Goal | Tools |
|---|---|
| Read a drawing | `open_image`, `open_image_tiles` |
| Parametric base | `create_partdesign_body` → `create_sketch` → PartDesign feature |
| Geometry health | `validate_object`, `validate_document` |
| Final structure report | `{FINAL_PARAMETRIC_VALIDATION_TOOL}` |
| Visual evidence | `set_view_angle`, `get_screenshot`, `open_image`, `compare_images` |
| Recovery | `history(action="undo")`, `safe_execute`, `execute_python`, `run_macro` |

GUI screenshot tools require `gui_available=true`.
"""

    # =========================================================================
    # Drawing and modification workflow prompts
    # =========================================================================

    @mcp.prompt()
    async def reproduce_from_drawing(
        reference_path: str = "",
        target_document: str = "",
    ) -> str:
        """Route a drawing-to-model task to the canonical engineering Skill.

        Args:
            reference_path: Optional path to the source drawing/image.
            target_document: Optional intended FreeCAD document name.
        """
        context = (
            "# Task context\n\n"
            f"- Reference path: `{reference_path or 'not supplied'}`\n"
            f"- Target document: `{target_document or 'not supplied'}`\n\n"
        )
        return context + DRAWING_RECONSTRUCTION_WORKFLOW

    @mcp.prompt()
    async def modify_existing_model(
        model_path: str = "",
        change_request: str = "",
        reference_path: str = "",
    ) -> str:
        """Route an existing-model task to the canonical engineering Skill.

        Args:
            model_path: Optional FCStd path or document identifier.
            change_request: Requested model change.
            reference_path: Optional drawing/image supporting the change.
        """
        context = (
            "# Task context\n\n"
            f"- Model: `{model_path or 'active document'}`\n"
            f"- Change request: {change_request or 'not supplied'}\n"
            f"- Reference path: `{reference_path or 'not supplied'}`\n\n"
        )
        return context + MODEL_MODIFICATION_WORKFLOW

    # =========================================================================
    # AI Guidance Prompts
    # =========================================================================

    @mcp.prompt()
    async def freecad_guidance(task_type: str = "general") -> str:
        """Get AI guidance for specific FreeCAD task types.

        This prompt provides targeted best practices and reminders
        for different types of FreeCAD operations. Use at the start
        of a task to get relevant guidance.

        Args:
            task_type: Type of task - one of:
                - "general": Overall best practices
                - "partdesign": Parametric part creation
                - "sketching": 2D sketch creation
                - "boolean": Boolean operations
                - "export": File export operations
                - "debugging": Troubleshooting issues
                - "validation": Checking model health
                - "drawing_reconstruction": Build a model from drawing views
                - "model_modification": Modify an existing parametric model
                - "visual_validation": ACT-OBSERVE-REACT checkpoint protocol

        Returns:
            Targeted guidance for the task type.

        Example:
            Get PartDesign workflow guidance::

                guidance = await freecad_guidance(task_type="partdesign")
        """
        guidance = {
            "general": """# FreeCAD AI Assistant Guidance

## Before Starting Any Task
1. **Check connection**: Use `get_connection_status()` to verify FreeCAD connection
2. **Check GUI**: Use `get_freecad_version()` - GUI features only work if gui_available=true
3. **Check document**: Use `get_active_document()` or create one with `create_document()`

## Key Principles
- **All Operations are Undoable**: Every tool operation is wrapped in a transaction
- **Validate Early**: After any geometry creation, use `validate_object()` to check validity
- **Prefer standard tools**: Use `safe_execute()` only when a standard tool is missing or demonstrably invalid
- **Check Version Compatibility**: FreeCAD 1.x changed some APIs (see best-practices resource)
- **Act-Observe-React**: visually inspect every major feature and do reaction therefore.

## History and Recovery
- `history(action="status")` reports available undo and redo steps.
- `history(action="undo")` reverts the last transaction.
- `history(action="redo")` reapplies an undone transaction.
- `undo_if_invalid()` remains available for legacy guarded workflows.

## GUI vs Headless
GUI-dependent tools include `get_screenshot()`, `set_visual_properties()`,
`selection()`, and `set_camera_position()`. Use `open_image_tiles()` to inspect
local drawings or screenshots without changing the FreeCAD camera.""",
            "partdesign": """# PartDesign Workflow Guidance

## Critical Rules
1. Create or select one explicit document.
2. Create or reuse one PartDesign Body.
3. Establish drawing-view to FreeCAD-plane correspondence before sketching.
4. Use one profile sketch per feature.

## Correct Workflow
```
create_document(name="MyPart")
create_partdesign_body(name="Body")
create_sketch(
    body_name="Body",
    support={"kind": "origin_plane", "plane": "XY_Plane"},
    name="BaseSketch",
)
edit_sketch_geometry(
    sketch_name="BaseSketch",
    operations=[{"op": "add_rectangle", "x": -10, "y": -10, "width": 20, "height": 20}],
)
pad_sketch(sketch_name="BaseSketch", length=15)
validate_object(object_name="Pad")
```

## Features
- Additive: `pad_sketch`, `revolution_sketch`, `thread_helix(operation="additive")`, `loft_sketches`, `sweep_sketch`.
- Subtractive: `pocket_sketch`, `groove_sketch`, `thread_helix(operation="subtractive")`, `create_hole`,
  `create_cylindrical_cut`, `subtractive_loft`, `subtractive_pipe`.
- Modifiers: `fillet_edges`, `chamfer_edges`, `draft_feature`, `thickness_feature`.
- Patterns: `linear_pattern`, `polar_pattern`, `multi_transform_pattern`, `mirrored_feature`.
  Do not chain one pattern directly onto another; use `multi_transform_pattern`.
- Datums: `create_datum_plane`, `create_datum_line`, `create_datum_point`.

## Sketch Editing
Use `edit_sketch_geometry` for ordered geometry edits and
`edit_sketch_constraints` for ordered constraint edits. Each batch is one
transaction and one recompute. Use `get_sketch_info` after editing.

## Common Mistakes
- Creating sketch without a body (will fail on pad).
- Guessing transient `FaceN` values instead of identifying the intended face.
- Not closing sketch contour (pad requires closed profile).
- Not constraining sketches (use get_sketch_info to check degrees of freedom).

## Completion
Before reporting completion, call `validate_parametric_model` and summarize
significant findings.""",
            "sketching": """# Sketch Creation Guidance

## Basic Workflow
1. Create the sketch on the intended origin plane, datum plane, or planar face.
2. Add ordered geometry with `edit_sketch_geometry`.
3. Add ordered constraints with `edit_sketch_constraints`.
4. Inspect solver and profile state with `get_sketch_info`.

## Geometry Operations
`edit_sketch_geometry(sketch_name, operations)` supports:
  `add_rectangle`, `add_circle`, `add_line`, `add_arc`, `add_point`,
  `add_ellipse`, `add_regular_polygon`, `add_polyline`, `add_slot`, `add_bspline`;
  `add_external_geometry`, `delete_geometry`, `toggle_construction`.

Example:
```
edit_sketch_geometry(
    sketch_name="Sketch",
    operations=[
        {"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 5},
        {"op": "toggle_construction", "geometry_index": 0},
    ],
)
```

## Constraint Operations
`edit_sketch_constraints(sketch_name, operations)` supports named operations
such as `horizontal`, `vertical`, `coincident`, `parallel`, `perpendicular`,
`tangent`, `equal`, `distance`, `distance_x`, `distance_y`, `radius`, `angle`,
`fix`, plus generic `add_constraint` and `delete_constraint`.

For `create_hole`, use non-construction circles in a dedicated sketch attached
to an actual planar solid face. Use `create_cylindrical_cut` for radial or
off-face cuts.""",
            "boolean": """# Boolean Operations Guidance

## Available Operations
- **fuse** (union): Combines shapes into one
- **cut** (difference): Removes second shape from first
- **common** (intersection): Keeps only overlapping region

## Tool Usage
```
boolean_operation(
    operation="fuse",  # or "cut" or "common"
    object1="Box",     # Base shape
    object2="Cylinder", # Tool shape
    result_name="FusedShape"  # Optional result name
)
```

## Prerequisites
- Both shapes must be **solids** (not curves, meshes, or compounds)
- Shapes should **overlap** for meaningful results
- Both objects must have **valid geometry**

## Validation Pattern
```
# Before boolean
validate_object(object_name="Box")
validate_object(object_name="Cylinder")

# Perform operation
boolean_operation(operation="fuse", object1="Box", object2="Cylinder")

# After boolean
validate_object(object_name="Fused")  # Check result is valid
```

## Common Issues
- **Empty result**: Shapes don't overlap - check positions
- **Invalid result**: Source shape has bad geometry
- **Fails completely**: Wrong shape type (mesh vs solid)

## Recovery
If boolean fails:
1. `history(action="undo")` to revert
2. Check source shapes with `validate_object()`
3. Ensure shapes actually intersect
4. Try simplifying geometry""",
            "export": """# Export Operations Guidance

## Available Formats
Use `export(file_format=..., file_path=...)` for every supported format.

| Format | `file_format` | Best For |
|--------|---------------|----------|
| STEP | `step` | CAD interchange, precise geometry |
| STL | `stl` | 3D printing (mesh format) |
| 3MF | `3mf` | 3D printing with color/material |
| OBJ | `obj` | Graphics, rendering, games |
| IGES | `iges` | Legacy CAD systems |

## Pre-Export Checklist
1. `validate_document()` - Ensure all objects are valid
2. `list_objects()` - Verify correct objects will export
3. `recompute_document()` - Force update before export

## Export Tips
- Specify `object_names` list to export specific objects
- Omit `object_names` to export all visible objects
- Use absolute paths for `file_path`

## Import Formats
- `import(file_format="step", ...)` - Preserves precise CAD geometry
- `import(file_format="stl", ...)` - Imports as mesh (may need conversion for CAD ops)

## Common Issues
- **Export fails**: Object has invalid shape
- **Missing objects**: Object not visible or wrong document
- **Wrong file**: Path error or permission issue""",
            "debugging": """# Debugging Guidance

## First Steps
1. `get_console_output(lines=50)` - Check for error messages
2. `validate_document()` - Find all invalid objects
3. `list_objects()` - See document structure

## Object Investigation
```
inspect_object(object_name="ProblemObject")
```
Check these fields:
- `state`: Should be empty; "Error" or "Invalid" indicates problems
- `is_valid` in shape_info: Geometry validity
- `type_id`: Ensure correct object type

## Common Problems

### "Object not found"
- Wrong name (case-sensitive)
- Wrong document (check `get_active_document()`)
- Object was deleted

### Invalid Shape
- Geometry computation failed
- Check parent objects (sketch, body)
- `history(action="undo")` and try simpler approach

### Recompute Errors
- Circular dependencies
- Invalid parent objects
- `recompute_document()` after fixing

## Recovery Steps
1. `history(action="undo")` - Revert last operation
2. `validate_document()` - Check what's broken
3. Fix or delete problem objects
4. `recompute_document()` - Refresh everything

## Using safe_execute
Use this only when standard MCP tools cannot perform the required operation:
```
safe_execute(
    code="... risky Python code ...",
    validate_after=True,
    auto_undo_on_failure=True
)
```
Automatically reverts if validation fails.""",
            "validation": """# Validation Guidance

## Transaction Support
**All MCP tool operations are wrapped in transactions** - this means:
- Every operation can be undone with `history(action="undo")`
- Use `history(action="status")` to see available undo steps
- Transaction names appear in FreeCAD's Edit > Undo menu

## Validation Tools

### validate_object(object_name, doc_name)
Checks a single object:
- `is_valid`: Shape geometry is valid
- `has_shape`: Object has geometry
- `state`: Error flags from FreeCAD
- `error_messages`: Human-readable errors

### validate_document(doc_name)
Checks all objects in document:
- `overall_valid`: True if ALL objects valid
- `invalid_count`: Number of problem objects
- `invalid_objects`: List of problem object names
- `objects`: Detailed status of each object

### undo_if_invalid(doc_name)
Checks document and auto-undoes if problems:
- Runs validation
- If invalid objects found, calls `history(action="undo")`
- Returns both validation and undo results

### safe_execute(code, validate_after, auto_undo_on_failure)
Fallback protected code execution; do not use it instead of available standard tools:
- Wraps code in transaction
- Validates result if validate_after=True
- Auto-reverts if validation fails and auto_undo_on_failure=True

## Validation Pattern
After any operation:
```
# Option 1: Simple undo if something goes wrong
create_primitive(primitive={"kind": "box", "length": 10, "width": 10, "height": 10})
# Oops, wrong size
history(action="undo")  # Reverts the box creation

# Option 2: Manual validation
result = validate_object(object_name="NewFeature")
if not result["is_valid"]:
    history(action="undo")
    # Try different approach

# Option 3: Automatic protection
safe_execute(
    code="...",
    validate_after=True,
    auto_undo_on_failure=True
)
```

## What Gets Checked
- Shape.isValid() - Geometry integrity
- Object.State - FreeCAD error flags
- Shape existence - Object has geometry
- Recompute state - Object up to date

### validate_parametric_model(doc_name, recompute, include_sketch_constraints)
Mandatory final informative scan after creating or changing geometry:
- reports Bodies, Tips, ordered history, and shape validity;
- reports sketches, solver/profile status, remaining DoF, supports, and expressions;
- reports standalone/direct solids and significant warnings;
- does not by itself prove drawing correspondence or manufacturability.

Call it immediately before the final user-facing response and summarize the findings.""",
            "drawing_reconstruction": DRAWING_RECONSTRUCTION_WORKFLOW,
            "model_modification": MODEL_MODIFICATION_WORKFLOW,
            "visual_validation": VISUAL_CHECKPOINT_PROTOCOL,
        }

        return guidance.get(task_type, guidance["general"])

    # =========================================================================
    # Design Workflow Prompts
    # =========================================================================

    @mcp.prompt()
    async def design_part(
        description: str,
        units: str = "mm",
    ) -> str:
        """Generate a guided workflow for designing a parametric part.

        Use this prompt when a user wants to create a new part from scratch.
        It provides step-by-step guidance for the PartDesign workflow.

        Args:
            description: Natural language description of the desired part.
            units: Unit system to use (mm, cm, m, in).

        Returns:
            Structured prompt guiding through part design.
        """
        return f"""# FreeCAD Part Design Workflow

## Part Description
{description}

## Recommended Approach

### 1. Create a New Document
First, create a new document for this part:
- Use `create_document` with a descriptive name

### 2. Set Up PartDesign Body
Create a PartDesign body to contain the parametric features:
- Use `create_partdesign_body` to create the body container
- This enables the parametric workflow with features

### 3. Create Base Sketch
Design the base profile:
- Use `create_sketch` with an `origin_plane`, face, or `datum_plane` typed support
- Add geometry with `edit_sketch_geometry`.
- Close the sketch when complete

### 4. Extrude the Base
Create the base 3D shape:
- Use `pad_sketch` to extrude the sketch
- Specify length in {units}

### 5. Add Features
Add additional features as needed:
- `pocket_sketch` for cuts/holes; 
  set `direction` explicitly, 
  use `base_feature_name` when Body history is ambiguous, 
  and pass `up_to_face="Feature.FaceN"` for `UpToFace`
- `fillet_edges` for rounded edges
- `chamfer_edges` for beveled edges

### 6. Verify and Export
When complete:
- Use `inspect_object` to verify dimensions
- Use `get_screenshot` to visualize the result
- Export with `export(file_format=...)` using the required target format

## Units
All dimensions should be specified in **{units}**.
"""

    @mcp.prompt()
    async def create_sketch_guide(
        shape_type: str = "rectangle",
        origin_plane: Literal["XY_Plane", "XZ_Plane", "YZ_Plane"] = "XY_Plane",
    ) -> str:
        """Guide for creating 2D sketches for part design.

        Args:
            shape_type: Type of shape (rectangle, circle, polygon).
            origin_plane: Origin plane used as the typed sketch support.

        Returns:
            Sketch creation guidance.
        """
        return f"""# FreeCAD Sketch Creation Guide

## Target Shape: {shape_type}
## Sketch Plane: {origin_plane}

### Step 1: Create Sketch
Use `create_sketch` with
`support={{"kind": "origin_plane", "plane": "{origin_plane}"}}` to start a new
sketch. For generated faces use `body_tip_face` or `feature_face`; for a datum
use `datum_plane`.

### Step 2: Add Geometry

{"#### Rectangle" if shape_type == "rectangle" else ""}
{"Use `edit_sketch_geometry` with one `add_rectangle` operation:" if shape_type == "rectangle" else ""}
{"- x, y: Starting corner position" if shape_type == "rectangle" else ""}
{"- width, height: Rectangle dimensions" if shape_type == "rectangle" else ""}

{"#### Circle" if shape_type == "circle" else ""}
{"Use `edit_sketch_geometry` with one `add_circle` operation:" if shape_type == "circle" else ""}
{"- x, y: Center position" if shape_type == "circle" else ""}
{"- radius: Circle radius" if shape_type == "circle" else ""}

{"#### Custom Polygon" if shape_type == "polygon" else ""}
{"Use `execute_python` with Part.makePolygon() for custom shapes." if shape_type == "polygon" else ""}

### Step 3: Constrain the Sketch
For a fully constrained sketch:
- All geometry should have defined positions
- No free degrees of freedom

### Step 4: Close and Use
The sketch can then be:
- Padded (extruded) with `pad_sketch`
- Pocketed (cut) with `pocket_sketch`
- Revolved with `revolution_sketch`
"""

    @mcp.prompt()
    async def boolean_operations_guide() -> str:
        """Guide for performing boolean operations on shapes.

        Returns:
            Boolean operations guidance.
        """
        return """# FreeCAD Boolean Operations Guide

Boolean operations combine two or more shapes into a new shape.

## Available Operations

### 1. Fuse (Union)
Combines two shapes into one:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="fuse",
    result_name="FusedShape"
)
```

### 2. Cut (Difference)
Removes the second shape from the first:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="cut",
    result_name="CutShape"
)
```

### 3. Common (Intersection)
Keeps only the overlapping region:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="common",
    result_name="CommonShape"
)
```

## Tips
- Shapes must overlap for meaningful results
- The original objects remain in the document
- Use `set_visual_properties(object_name, visible=False)` to hide originals after operation
- Recompute the document after boolean operations
"""

    # =========================================================================
    # Export/Import Prompts
    # =========================================================================

    @mcp.prompt()
    async def export_guide(target_format: str = "STEP") -> str:
        """Guide for exporting FreeCAD models to various formats.

        Args:
            target_format: Target export format (STEP, STL, OBJ, IGES).

        Returns:
            Export guidance for the specified format.
        """
        format_info = {
            "STEP": {
                "tool": "export",
                "extension": ".step",
                "description": "Standard for exchanging 3D CAD data between systems",
                "best_for": "CAD interchange, preserves geometry precisely",
                "params": "file_format, file_path, object_names (optional)",
            },
            "STL": {
                "tool": "export",
                "extension": ".stl",
                "description": "Triangulated mesh format",
                "best_for": "3D printing, mesh-based workflows",
                "params": "file_format, file_path, object_names (optional), mesh_tolerance (default 0.1)",
            },
            "OBJ": {
                "tool": "export",
                "extension": ".obj",
                "description": "Wavefront OBJ mesh format",
                "best_for": "3D graphics, rendering, game engines",
                "params": "file_format, file_path, object_names (optional)",
            },
            "IGES": {
                "tool": "export",
                "extension": ".iges",
                "description": "Initial Graphics Exchange Specification",
                "best_for": "Legacy CAD systems, surface data",
                "params": "file_format, file_path, object_names (optional)",
            },
        }

        info = format_info.get(target_format.upper(), format_info["STEP"])

        return f"""# FreeCAD Export Guide: {target_format.upper()}

## Format: {target_format.upper()} ({info["extension"]})
{info["description"]}

**Best for:** {info["best_for"]}

## Export Command
Use the `{info["tool"]}` tool with parameters:
- {info["params"]}

## Example
```python
{info["tool"]}(
    file_format="{target_format.lower()}",
    file_path="/path/to/output{info["extension"]}",
    object_names=["Part1", "Part2"]  # Optional: exports all if not specified
)
```

## Pre-Export Checklist
1. Verify all objects are visible with `list_objects`
2. Check object validity with `inspect_object`
3. Recompute document if needed: `recompute_document`
4. Consider using `fit_all` and `get_screenshot` to verify visually

## Post-Export
- Verify the exported file exists
- Check file size is reasonable
- Test import in target application if possible
"""

    @mcp.prompt()
    async def import_guide(source_format: str = "STEP") -> str:
        """Guide for importing models into FreeCAD.

        Args:
            source_format: Source file format (STEP, STL).

        Returns:
            Import guidance for the specified format.
        """
        format_info = {
            "STEP": {
                "tool": "import",
                "description": "Imports precise CAD geometry",
                "notes": "Preserves feature boundaries, faces, and edges",
            },
            "STL": {
                "tool": "import",
                "description": "Imports triangulated mesh",
                "notes": "Results in Mesh object, may need conversion for CAD operations",
            },
        }

        info = format_info.get(source_format.upper(), format_info["STEP"])

        return f"""# FreeCAD Import Guide: {source_format.upper()}

## Format: {source_format.upper()}
{info["description"]}

**Notes:** {info["notes"]}

## Import Command
Use the `{info["tool"]}` tool:
```python
{info["tool"]}(
    file_format="{source_format.lower()}",
    file_path="/path/to/file.{source_format.lower()}",
    doc_name="TargetDocument"  # Optional
)
```

## Post-Import Steps
1. List imported objects: `list_objects`
2. Inspect geometry: `inspect_object` on each object
3. Adjust view: `fit_all` to see all imported geometry
4. Take screenshot: `get_screenshot` to verify import

## Common Issues
- Large files may take time to process
- Complex geometry may create many objects
- STL meshes need conversion for boolean operations
"""

    # =========================================================================
    # Analysis Prompts
    # =========================================================================

    @mcp.prompt()
    async def analyze_shape() -> str:
        """Guide for analyzing shape geometry and properties.

        Returns:
            Shape analysis guidance.
        """
        return """# FreeCAD Shape Analysis Guide

## Quick Analysis
Use `inspect_object` with `include_shape=True` to get:
- Volume
- Surface area
- Bounding box
- Vertex/edge/face counts
- Validity status

## Detailed Analysis with Typed Tools

1. Call `inspect_object(object_name="ObjectName", include_shape=True)`.
2. Read the returned bounding box, volume, area, topology counts, placement,
   dependencies, and readable properties.
3. Call `validate_object(object_name="ObjectName")` for geometric validity.
4. Call `validate_document()` when downstream features or Body Tip state may be
   affected.
5. Use `get_screenshot` only after the geometric checks and compare an equivalent
   reference view.

Do not replace these typed inspections with direct Python. If a required physical
property is not exposed, report the missing field so a dedicated MCP tool can be
added.
"""

    @mcp.prompt()
    async def debug_model() -> str:
        """Guide for debugging FreeCAD model issues.

        Returns:
            Model debugging guidance.
        """
        return """# FreeCAD Model Debugging Guide

## Common Issues and Solutions

### 1. Recompute Errors
**Symptom:** Objects show error state, model doesn't update
**Solution:**
```python
recompute_document()  # Force full recompute
```

### 2. Invalid Shape
**Symptom:** Boolean operations fail, export errors
**Diagnosis:**
```text
validate_object(object_name="ObjectName")
inspect_object(object_name="ObjectName", include_shape=True)
```
If invalid, undo the failed feature and confirm the previous Body Tip is valid.

### 3. Sketch Not Fully Constrained
**Symptom:** Sketch geometry moves unexpectedly
**Check constraints:**
```text
get_sketch_info(sketch_name="SketchName")
```
Inspect degrees of freedom, conflicting/redundant constraints, open geometry,
and under-constrained elements before creating the 3D feature.

### 4. Object Dependencies
**Symptom:** Can't delete object, unexpected behavior
**Check dependencies:**
```python
inspect_object("ObjectName")  # Check children and parents
```

### 5. View Not Updating
**Symptom:** Display doesn't match model
**Solution:**
```python
fit_all()  # Reset view
get_screenshot()  # Force view update
```

## Diagnostic Workflow
1. `list_objects` - See all objects and their states
2. `inspect_object` on problematic objects
3. `get_console_output` - Check for error messages
4. `recompute_document` - Force update
5. `get_screenshot` - Visual verification
"""

    # =========================================================================
    # Macro Development Prompts
    # =========================================================================

    @mcp.prompt()
    async def macro_development() -> str:
        """Guide for developing FreeCAD macros.

        Returns:
            Macro development guidance.
        """
        return """# FreeCAD Macro Development Guide

## Macro Structure
A FreeCAD macro is a Python script that automates tasks.

### Basic Template
```python
# -*- coding: utf-8 -*-
# Macro: MacroName
# Description: What the macro does

import FreeCAD
import FreeCADGui

def main():
    # Get active document
    doc = FreeCAD.ActiveDocument
    if doc is None:
        FreeCAD.Console.PrintError("No active document\\n")
        return

    # Your code here

    doc.recompute()
    FreeCAD.Console.PrintMessage("Macro completed\\n")

if __name__ == "__main__":
    main()
```

## Creating a Macro
Use `create_macro` to save a macro:
```python
create_macro(
    name="MyMacro",
    code="... macro code ...",
    description="What it does"
)
```

Or use a template:
```python
create_macro_from_template(
    template_name="part",  # basic, part, sketch, gui, selection
    macro_name="MyPartMacro"
)
```

## Available Templates
- **basic**: Minimal template
- **part**: Part creation with primitives
- **sketch**: 2D sketch operations
- **gui**: GUI interaction with message boxes
- **selection**: Working with selected objects

## Running Macros
```python
run_macro("MacroName")
```

## Best Practices
1. Always check for active document
2. Use FreeCAD.Console for output
3. Call doc.recompute() after changes
4. Handle exceptions gracefully
5. Add descriptive comments
"""

    @mcp.prompt()
    async def python_api_reference() -> str:
        """Quick reference for common FreeCAD Python API operations.

        Returns:
            Python API reference.
        """
        return """# FreeCAD Python API Quick Reference

## Document Operations
```python
# Create/get documents
doc = FreeCAD.newDocument("Name")
doc = FreeCAD.ActiveDocument
doc = FreeCAD.getDocument("Name")

# Document methods
doc.recompute()
doc.save()
doc.saveAs("/path/to/file.FCStd")
```

## Object Operations
```python
# Create objects
box = doc.addObject("Part::Box", "MyBox")
cyl = doc.addObject("Part::Cylinder", "MyCyl")

# Get objects
obj = doc.getObject("ObjectName")
all_objs = doc.Objects

# Modify properties
obj.Length = 100
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector(x, y, z),
    FreeCAD.Rotation(axis, angle)
)

# Delete
doc.removeObject("ObjectName")
```

## Part Module
```python
import Part

# Primitives
box = Part.makeBox(l, w, h)
cyl = Part.makeCylinder(r, h)
sphere = Part.makeSphere(r)

# Boolean operations
fused = shape1.fuse(shape2)
cut = shape1.cut(shape2)
common = shape1.common(shape2)

# Create from shape
Part.show(shape, "Name")
```

## Sketcher Module
```python
import Sketcher

# Create sketch
sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
sketch.MapMode = "FlatFace"

# Add geometry
sketch.addGeometry(Part.LineSegment(p1, p2))
sketch.addGeometry(Part.Circle(center, normal, radius))

# Add constraints
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 2))
sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
```

## GUI Operations
```python
import FreeCADGui as Gui

# View control
view = Gui.ActiveDocument.ActiveView
view.viewIsometric()
view.fitAll()
view.saveImage("/path/to/image.png", 800, 600)

# Object visibility
obj.ViewObject.Visibility = True/False
obj.ViewObject.ShapeColor = (r, g, b)  # 0.0-1.0
```

## Vectors and Placement
```python
# Vector operations
v = FreeCAD.Vector(x, y, z)
v.Length
v.normalize()
v1.cross(v2)
v1.dot(v2)

# Placement
p = FreeCAD.Placement()
p.Base = FreeCAD.Vector(x, y, z)
p.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 45)
```
"""

    # =========================================================================
    # Troubleshooting Prompts
    # =========================================================================

    @mcp.prompt()
    async def troubleshooting() -> str:
        """General troubleshooting guide for FreeCAD Robust MCP.

        Returns:
            Troubleshooting guidance.
        """
        return """# FreeCAD Robust MCP Troubleshooting Guide

## Connection Issues

### Cannot Connect to FreeCAD
1. Verify FreeCAD is running (for socket/xmlrpc modes)
2. Check the MCP plugin is started in FreeCAD
3. Verify port numbers match (default: 9876 socket, 9875 xmlrpc)

**Check status:**
```python
get_connection_status()
```

### Connection Drops
- FreeCAD may be busy with long operations
- Try increasing timeout values
- Check FreeCAD console for errors

## Tool Execution Issues

### Operation Timeout
- increase the server timeout only after confirming the operation is valid;
- split the CAD change into one typed feature per call;
- inspect FreeCAD console output and document state;
- do not replace the failed typed operation with arbitrary Python.

### No Result Returned
- check `get_connection_status` and `get_console_output`;
- verify that the expected FreeCAD document is active;
- retry only the same typed operation after identifying the cause.

## GUI Issues

### Screenshots Fail
- Ensure GUI mode is available: `get_freecad_version()`
- Check for active document and view
- Verify view type supports screenshots

### View Not Updating
```python
recompute_document()
fit_all()
```

## Model Issues

### Boolean Operation Fails
- Check shapes are valid
- Ensure shapes overlap
- Try with simpler geometry first

### Export Fails
- Verify objects have valid shapes
- Check file path is writable
- Ensure correct format for geometry type

## Getting Help
1. Check console output: `get_console_output()`
2. Inspect problematic objects: `inspect_object()`
3. Verify document state: `list_documents()`, `list_objects()`
"""
