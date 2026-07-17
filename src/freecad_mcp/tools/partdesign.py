"""PartDesign tools for FreeCAD Robust MCP Server.

This module provides tools for the PartDesign workbench, enabling
parametric solid modeling operations like Pad, Pocket, Fillet, etc.

Based on learnings from contextform/freecad-mcp which has the most
comprehensive PartDesign coverage.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from freecad_mcp.tools._freecad_runtime_helpers import (
    BODY_RUNTIME_HELPERS,
    FEATURE_VALIDATION_RUNTIME_HELPERS,
    REVOLUTION_AXIS_RUNTIME_HELPERS,
    SKETCH_ANALYSIS_RUNTIME_HELPERS,
)


def register_partdesign_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register PartDesign-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    def require_additive_result(payload: Any, operation: str) -> dict[str, Any]:
        """Enforce the host-side contract for additive feature tools."""
        if not isinstance(payload, dict):
            raise ValueError(f"{operation} returned an invalid response payload")
        try:
            added_volume = float(payload.get("added_volume", 0.0))
            solid_count = int(payload.get("solid_count", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{operation} returned non-numeric validation evidence: {payload!r}"
            ) from exc
        if (
            payload.get("validated") is not True
            or added_volume <= 0.0
            or solid_count != 1
        ):
            raise ValueError(
                f"{operation} additive validation contract was not satisfied: "
                + repr(payload)
            )
        return payload

    def require_subtractive_result(payload: Any, operation: str) -> dict[str, Any]:
        """Enforce the host-side contract for subtractive feature tools."""
        if not isinstance(payload, dict):
            raise ValueError(f"{operation} returned an invalid response payload")
        try:
            removed_volume = float(payload.get("removed_volume", 0.0))
            solid_count = int(payload.get("solid_count", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{operation} returned non-numeric validation evidence: {payload!r}"
            ) from exc
        if (
            payload.get("validated") is not True
            or removed_volume <= 0.0
            or solid_count != 1
        ):
            raise ValueError(
                f"{operation} subtractive validation contract was not satisfied: "
                + repr(payload)
            )
        return payload

    @mcp.tool()
    async def create_partdesign_body(
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new PartDesign Body.

        A PartDesign Body is a container for feature-based modeling that
        maintains a single solid shape through a sequence of operations.

        Args:
            name: Body name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created body information:
                - name: Body name
                - label: Body label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object("PartDesign::Body", name, None, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_sketch(
        body_name: str | None = None,
        plane: str = "XY_Plane",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Sketch attached to an origin plane, datum plane, or face.

        Args:
            body_name: Name of PartDesign Body to attach to. Creates standalone if None.
            plane: Support to attach the sketch to. Options:
                - "XY_Plane" - Horizontal plane
                - "XZ_Plane" - Front vertical plane
                - "YZ_Plane" - Side vertical plane
                - Face name like "Face1" to attach to the current Body Tip
                - Explicit face like "Pad_Base.Face8"
                - Datum plane object name like "DP_OilHole"
            name: Sketch name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created sketch information:
                - name: Sketch name
                - label: Sketch label
                - type_id: Object type
                - support: What the sketch is attached to
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

# Wrap in transaction for undo support
doc.openTransaction("Create Sketch")
try:
    sketch_name = {name!r} or "Sketch"

    if {body_name!r}:
        body = doc.getObject({body_name!r})
        if body is None:
            raise ValueError(f"Body not found: {body_name!r}")

        # Add sketch to body
        sketch = body.newObject("Sketcher::SketchObject", sketch_name)

        # Set support plane - FreeCAD 1.x uses AttachmentSupport, older versions use Support
        # Check which property exists and use the appropriate one
        plane = {plane!r}
        if plane in ["XY_Plane", "XZ_Plane", "YZ_Plane"]:
            plane_obj = _resolve_body_origin_feature(body, plane)
            
            if hasattr(sketch, "AttachmentSupport"):
                sketch.AttachmentSupport = [(plane_obj, [""])]
            else:
                sketch.Support = (plane_obj, [""])
            sketch.MapMode = "FlatFace"
        elif plane.startswith("Face"):
            # A face belongs to the current solid feature, not to the Body
            # container. Attaching to Body produces a sketch object that exists
            # but is not mapped to a real face, causing downstream null shapes.
            support_feature = body.Tip
            if support_feature is None or not hasattr(support_feature, "Shape"):
                raise ValueError(
                    f"Body {{body.Name!r}} has no solid Tip to provide {{plane}}"
                )
            try:
                face_index = int(plane[4:])
            except Exception as exc:
                raise ValueError(f"Invalid face reference: {plane!r}") from exc
            if face_index < 1 or face_index > len(support_feature.Shape.Faces):
                raise ValueError(
                    f"Face not found: {{support_feature.Name}}.{{plane}}. "
                    f"Available faces: Face1..Face{{len(support_feature.Shape.Faces)}}"
                )
            if hasattr(sketch, "AttachmentSupport"):
                sketch.AttachmentSupport = [(support_feature, [plane])]
            else:
                sketch.Support = (support_feature, [plane])
            sketch.MapMode = "FlatFace"
        elif "." in plane:
            support_name, sub_element = plane.rsplit(".", 1)
            support_object = doc.getObject(support_name)
            if support_object is None:
                raise ValueError(f"Sketch support object not found: {{support_name!r}}")
            if not sub_element.startswith("Face"):
                raise ValueError(
                    f"Unsupported sketch sub-element: {{sub_element!r}}. "
                    "Use an explicit planar FaceN reference."
                )
            shape = getattr(support_object, "Shape", None)
            try:
                face_index = int(sub_element[4:])
            except Exception as exc:
                raise ValueError(
                    f"Invalid face reference: {{support_name}}.{{sub_element}}"
                ) from exc
            if (
                shape is None
                or shape.isNull()
                or face_index < 1
                or face_index > len(shape.Faces)
            ):
                available = 0 if shape is None or shape.isNull() else len(shape.Faces)
                raise ValueError(
                    f"Face not found: {{support_name}}.{{sub_element}}. "
                    f"Available faces: Face1..Face{{available}}"
                )
            if hasattr(sketch, "AttachmentSupport"):
                sketch.AttachmentSupport = [(support_object, [sub_element])]
            else:
                sketch.Support = (support_object, [sub_element])
            sketch.MapMode = "FlatFace"
        else:
            support_object = doc.getObject(plane)
            if support_object is None:
                raise ValueError(
                    f"Unsupported sketch support: {{plane!r}}. Use a Body origin "
                    "plane, an explicit Object.FaceN, or an existing datum plane."
                )
            if getattr(support_object, "TypeId", "") != "PartDesign::Plane":
                raise ValueError(
                    f"Object {{plane!r}} is not a PartDesign datum plane: "
                    f"{{getattr(support_object, 'TypeId', '<unknown>')}}"
                )
            if hasattr(sketch, "AttachmentSupport"):
                sketch.AttachmentSupport = [(support_object, [""])]
            else:
                sketch.Support = (support_object, [""])
            sketch.MapMode = "FlatFace"
    else:
        # Standalone sketch
        sketch = doc.addObject("Sketcher::SketchObject", sketch_name)

        plane = {plane!r}
        if plane == "XY_Plane":
            sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(0,0,0,1))
        elif plane == "XZ_Plane":
            sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(1,0,0), 90))
        elif plane == "YZ_Plane":
            sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(0,1,0), 90))

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

# Extract support name
support_info = None
if hasattr(sketch, "AttachmentSupport") and sketch.AttachmentSupport:
    # Structure: [(Object, ('SubElement', ...))]
    supp_obj, sub_elems = sketch.AttachmentSupport[0]
    support_info = f"{{supp_obj.Name}}.{{sub_elems[0]}}" if sub_elems and sub_elems[0] else supp_obj.Name
elif hasattr(sketch, "Support") and sketch.Support:
    # Structure: (Object, ['SubElement'])
    supp_obj, sub_elems = sketch.Support
    support_info = f"{{supp_obj.Name}}.{{sub_elems[0]}}" if sub_elems and sub_elems[0] else supp_obj.Name

_result_ = {{
    "name": sketch.Name,
    "label": sketch.Label,
    "type_id": sketch.TypeId,
    "support": support_info,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create sketch failed")

    @mcp.tool()
    async def add_sketch_rectangle(
        sketch_name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a rectangle to a sketch.

        Args:
            sketch_name: Name of the sketch to add rectangle to.
            x: X coordinate of bottom-left corner.
            y: Y coordinate of bottom-left corner.
            width: Rectangle width.
            height: Rectangle height.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - geometry_indices: Indices of the four added lines
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Rectangle")
try:
    # Add rectangle
    import Part
    import Sketcher

    x, y, w, h = {x}, {y}, {width}, {height}

    # Add lines
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y, 0), FreeCAD.Vector(x+w, y, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x+w, y, 0), FreeCAD.Vector(x+w, y+h, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x+w, y+h, 0), FreeCAD.Vector(x, y+h, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y+h, 0), FreeCAD.Vector(x, y, 0)), False)

    # Add coincident constraints to close the rectangle
    n = sketch.GeometryCount - 4
    sketch.addConstraint(Sketcher.Constraint("Coincident", n, 2, n+1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", n+1, 2, n+2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", n+2, 2, n+3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", n+3, 2, n, 1))

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "geometry_indices": list(range(n, n + 4)),
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add rectangle failed")

    @mcp.tool()
    async def add_sketch_circle(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a circle to a sketch.

        Args:
            sketch_name: Name of the sketch to add circle to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            radius: Circle radius.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - geometry_index: Index of the added circle
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Circle")
try:
    import Part

    idx = sketch.addGeometry(Part.Circle(FreeCAD.Vector({center_x}, {center_y}, 0), FreeCAD.Vector(0,0,1), {radius}), False)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "geometry_index": idx,
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add circle failed")

    @mcp.tool()
    async def pad_sketch(
        sketch_name: str,
        length: float,
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Pad (extrusion) from a sketch.

        Args:
            sketch_name: Name of the sketch to pad.
            length: Pad length (extrusion distance).
            symmetric: Whether to extrude symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Pad feature name. Auto-generated if None.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created pad information:
                - name: Pad name
                - label: Pad label
                - type_id: Object type
                - validated: Whether the additive result passed validation
                - added_volume: Effective volume added to the Body
                - base_volume: Volume before the operation, or None for first feature
                - result_volume: Volume after the operation
                - solid_count: Number of solids in the result (must be one)
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = _find_body_containing_object(doc, sketch)

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pad operation")

base_feature = _find_preceding_single_solid_feature(body, sketch)
base_shape = base_feature.Shape.copy() if base_feature is not None else None

original_tip_name = getattr(body.Tip, "Name", None)
created_pad_name = None
# Wrap in transaction for undo support
doc.openTransaction("Pad Sketch")
try:
    pad_name = {name!r} or "Pad"
    pad = body.newObject("PartDesign::Pad", pad_name)
    created_pad_name = pad.Name
    pad.Profile = sketch
    pad.Length = {length}
    # FreeCAD 1.0 uses Midplane instead of Symmetric
    if {symmetric}:
        pad.Midplane = True
    pad.Reversed = {reversed}

    doc.recompute()
    validation = _validate_additive_feature(pad, body, base_shape)
    if not validation["ok"]:
        raise ValueError("Pad failed: " + "; ".join(validation["reasons"]))
    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        _cleanup_failed_partdesign_feature(
            doc, body, created_pad_name, original_tip_name
        )
    raise

_result_ = {{
    "name": pad.Name,
    "label": pad.Label,
    "type_id": pad.TypeId,
    "validated": validation["ok"],
    "base_volume": validation["base_volume"],
    "result_volume": validation["result_volume"],
    "added_volume": validation["added_volume"],
    "solid_count": validation["solid_count"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return require_additive_result(result.result, 'Pad')
        raise ValueError(result.error_traceback or "Pad failed")

    @mcp.tool()
    async def pocket_sketch(
        sketch_name: str,
        length: float,
        type: str = "Length",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Pocket (cut extrusion) from a sketch.

        Args:
            sketch_name: Name of the sketch to pocket.
            length: Pocket depth.
            type: Pocket type: "Length", "ThroughAll", "UpToFirst", "UpToFace".
            name: Pocket feature name. Auto-generated if None.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created pocket information:
                - name: Pocket name
                - label: Pocket label
                - type_id: Object type
                - validated: Check if the result has a valid shape
                - removed_volume: Removed volume of the body
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = _find_body_containing_object(doc, sketch)

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pocket operation")

base_feature = _find_preceding_single_solid_feature(body, sketch)
if base_feature is None:
    raise ValueError("Pocket requires a valid single-solid feature before the sketch")
base_shape = base_feature.Shape.copy()

# Wrap in transaction for undo support
doc.openTransaction("Pocket Sketch")
try:
    pocket_name = {name!r} or "Pocket"
    pocket = body.newObject("PartDesign::Pocket", pocket_name)
    pocket.Profile = sketch
    pocket.Length = {length}
    pocket.Type = {type!r}

    doc.recompute()
    validation = _validate_subtractive_feature(pocket, body, base_shape)
    if not validation["ok"]:
        raise ValueError("Pocket failed: " + "; ".join(validation["reasons"]))
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": pocket.Name,
    "label": pocket.Label,
    "type_id": pocket.TypeId,
    "validated": validation["ok"],
    "removed_volume": validation["removed_volume"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Pocket failed")

    @mcp.tool()
    async def fillet_edges(
        object_name: str,
        radius: float,
        edges: list[str] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add fillet (rounded edges) to an object.

        Args:
            object_name: Name of the object to fillet.
            radius: Fillet radius.
            edges: List of edge names to fillet (e.g., ["Edge1", "Edge2"]).
                   Fillets all edges if None.
            name: Fillet feature name. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created fillet information:
                - name: Fillet name
                - label: Fillet label
                - type_id: Object type
        """
        bridge = await get_bridge()

        # Use actual None or list, not string "None"
        edges_param = edges if edges else None

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

# Get selected edges (None means all edges)
selected_edges = {edges_param!r}

# Wrap in transaction for undo support
doc.openTransaction("Fillet Edges")
try:
    fillet_name = {name!r} or "Fillet"

    if body:
        # PartDesign Fillet
        fillet = body.newObject("PartDesign::Fillet", fillet_name)
        fillet.Base = (obj, selected_edges if selected_edges else obj.Shape.Edges)
        fillet.Radius = {radius}
    else:
        # Part Fillet
        fillet = doc.addObject("Part::Fillet", fillet_name)
        fillet.Base = obj

        if selected_edges:
            edge_list = [(int(e.replace("Edge", "")), {radius}, {radius}) for e in selected_edges]
        else:
            edge_list = [(i+1, {radius}, {radius}) for i in range(len(obj.Shape.Edges))]

        fillet.Edges = edge_list

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": fillet.Name,
    "label": fillet.Label,
    "type_id": fillet.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Fillet failed")

    @mcp.tool()
    async def chamfer_edges(
        object_name: str,
        size: float,
        edges: list[str] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add chamfer (beveled edges) to an object.

        Args:
            object_name: Name of the object to chamfer.
            size: Chamfer size.
            edges: List of edge names to chamfer (e.g., ["Edge1", "Edge2"]).
                   Chamfers all edges if None.
            name: Chamfer feature name. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created chamfer information:
                - name: Chamfer name
                - label: Chamfer label
                - type_id: Object type
        """
        bridge = await get_bridge()

        # Use actual None or list, not string "None"
        edges_param = edges if edges else None

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

# Get selected edges (None means all edges)
selected_edges = {edges_param!r}

# Wrap in transaction for undo support
doc.openTransaction("Chamfer Edges")
try:
    chamfer_name = {name!r} or "Chamfer"

    if body:
        # PartDesign Chamfer
        chamfer = body.newObject("PartDesign::Chamfer", chamfer_name)
        chamfer.Base = (obj, selected_edges if selected_edges else obj.Shape.Edges)
        chamfer.Size = {size}
    else:
        # Part Chamfer
        chamfer = doc.addObject("Part::Chamfer", chamfer_name)
        chamfer.Base = obj

        if selected_edges:
            edge_list = [(int(e.replace("Edge", "")), {size}, {size}) for e in selected_edges]
        else:
            edge_list = [(i+1, {size}, {size}) for i in range(len(obj.Shape.Edges))]

        chamfer.Edges = edge_list

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": chamfer.Name,
    "label": chamfer.Label,
    "type_id": chamfer.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Chamfer failed")

    @mcp.tool()
    async def revolution_sketch(
        sketch_name: str,
        angle: float = 360.0,
        axis: str = "Base_X",
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Revolution (rotational extrusion) from a sketch.

        Revolves the sketch profile around an axis to create a solid of revolution.

        Args:
            sketch_name: Name of the sketch to revolve.
            angle: Revolution angle in degrees. Defaults to 360.
            axis: Axis to revolve around. Options:
                - "Base_X" - X axis
                - "Base_Y" - Y axis
                - "Base_Z" - Z axis
                - "Sketch_V" - Sketch vertical axis
                - "Sketch_H" - Sketch horizontal axis
            symmetric: Whether to revolve symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Revolution feature name. Auto-generated if None.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created revolution information:
                - name: Revolution name
                - label: Revolution label
                - type_id: Object type
                - validated: Check if the result has a valid shape
        """
        bridge = await get_bridge()

        code = f"""
{REVOLUTION_AXIS_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = _find_body_containing_object(doc, sketch)

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Revolution operation")

base_feature = _find_preceding_single_solid_feature(body, sketch)
base_shape = base_feature.Shape.copy() if base_feature is not None else None

original_tip_name = getattr(body.Tip, "Name", None)
created_revolution_name = None
# Wrap in transaction for undo support
doc.openTransaction("Revolution Sketch")
try:
    rev_name = {name!r} or "Revolution"
    rev = body.newObject("PartDesign::Revolution", rev_name)
    created_revolution_name = rev.Name
    rev.Profile = sketch
    rev.Angle = {angle}
    # FreeCAD 1.0 uses Midplane instead of Symmetric
    if {symmetric}:
        rev.Midplane = True
    rev.Reversed = {reversed}

    # Resolve the requested Body or sketch axis.
    axis_name = {axis!r}
    rev.ReferenceAxis, resolved_axis_name = _resolve_revolution_axis(
        body, sketch, axis_name, 'Revolution'
    )

    doc.recompute()

    validation = _validate_additive_feature(rev, body, base_shape)
    if not validation["ok"]:
        details = "; ".join(validation["reasons"])
        raise ValueError(
            'Revolution' + " failed: " + details +
            ". Common causes: open profile, profile crossing the axis, "
            "or an axis that does not produce a valid solid."
        )

    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        _cleanup_failed_partdesign_feature(
            doc, body, created_revolution_name, original_tip_name
        )
    raise

_result_ = {{
    "name": rev.Name,
    "label": rev.Label,
    "type_id": rev.TypeId,
    "validated": validation["ok"],
    "base_volume": validation["base_volume"],
    "result_volume": validation["result_volume"],
    "added_volume": validation["added_volume"],
    "solid_count": validation["solid_count"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return require_additive_result(result.result, 'Revolution')
        raise ValueError(result.error_traceback or "Revolution failed")

    @mcp.tool()
    async def groove_sketch(
        sketch_name: str,
        angle: float = 360.0,
        axis: str = "Base_X",
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Groove (subtractive revolution) from a sketch.

        Revolves a sketch profile and subtracts it from existing material.

        Args:
            sketch_name: Name of the sketch to revolve.
            angle: Groove angle in degrees. Defaults to 360.
            axis: Axis to revolve around. Options:
                - "Base_X" - X axis
                - "Base_Y" - Y axis
                - "Base_Z" - Z axis
                - "Sketch_V" - Sketch vertical axis
                - "Sketch_H" - Sketch horizontal axis
            symmetric: Whether to revolve symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Groove feature name. Auto-generated if None.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created groove information:
                - name: Groove name
                - label: Groove label
                - type_id: Object type
                - validated: Check if the result has a valid shape
                - removed_volume: Removed volume of the body
        """
        bridge = await get_bridge()

        code = f"""
{REVOLUTION_AXIS_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = _find_body_containing_object(doc, sketch)

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Groove operation")

base_feature = _find_preceding_single_solid_feature(body, sketch)
if base_feature is None:
    raise ValueError("Groove requires a valid single-solid feature before the sketch")
base_shape = base_feature.Shape.copy()

# Wrap in transaction for undo support
doc.openTransaction("Groove Sketch")
try:
    groove_name = {name!r} or "Groove"
    groove = body.newObject("PartDesign::Groove", groove_name)
    groove.Profile = sketch
    groove.Angle = {angle}
    # FreeCAD 1.0 uses Midplane instead of Symmetric
    if {symmetric}:
        groove.Midplane = True
    groove.Reversed = {reversed}

    # Resolve the requested Body or sketch axis.
    axis_name = {axis!r}
    groove.ReferenceAxis, resolved_axis_name = _resolve_revolution_axis(
        body, sketch, axis_name, 'Groove'
    )

    doc.recompute()

    validation = _validate_subtractive_feature(groove, body, base_shape)
    if not validation["ok"]:
        details = "; ".join(validation["reasons"])
        raise ValueError(
            'Groove' + " failed: " + details +
            ". Common causes: the groove profile does not intersect the base "
            "solid, the profile is open, or the selected axis is incorrect."
        )

    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": groove.Name,
    "label": groove.Label,
    "type_id": groove.TypeId,
    "validated": validation["ok"],
    "removed_volume": validation["removed_volume"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Groove failed")

    @mcp.tool()
    async def create_hole(
        sketch_name: str,
        diameter: float = 6.0,
        depth: float = 10.0,
        hole_type: str = "Dimension",
        threaded: bool = False,
        thread_type: str = "ISO",
        thread_size: str = "M6",
        drill_point: str = "Flat",
        reversed: bool | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a validated Hole feature from a face- or origin-plane sketch.

        The sketch must contain one or more non-construction circles. One sketch
        may be consumed by only one PartDesign feature. The operation succeeds
        only when FreeCAD produces one valid solid and the body's volume is
        measurably reduced. If the default direction does not cut the body, the
        opposite direction is tried automatically unless ``reversed`` is set.

        Prefer a sketch attached to an actual planar face of the solid. Origin
        planes are allowed, but can be ambiguous in a complex Body. Sketches on
        ``PartDesign::Plane`` datum planes are rejected deliberately: FreeCAD
        1.0.x can create a syntactically valid but geometrically ineffective
        Hole in that configuration. Use ``create_cylindrical_cut`` for radial,
        tangent-plane, or otherwise off-face cylindrical cuts.

        Args:
            sketch_name: Name of an unused sketch with hole-location circles.
                Prefer attachment to ``Object.FaceN`` of the solid being cut.
            diameter: Hole diameter for non-threaded holes. Defaults to 6.0.
            depth: Hole depth for ``Dimension`` holes. Defaults to 10.0.
            hole_type: Depth type: ``Dimension`` or ``ThroughAll``.
            threaded: Whether to create a threaded hole definition.
            thread_type: Thread profile: ``ISO``, ``ISO_FINE``, ``UNC``, or ``UNF``.
            thread_size: Thread designation, for example ``M6`` or ``1/4``.
            drill_point: Blind-hole bottom shape: ``Flat`` (default) or
                ``Angled``. ``Angled`` adds the drill-tip cone.
            reversed: Explicit cutting direction. If None, both directions are
                tried and the first valid subtractive result is retained.
            name: Hole feature name. Auto-generated if None.
            doc_name: Existing document containing the sketch. Uses the active
                document if None. A missing document is never created silently.

        Returns:
            Dictionary with created hole information:
                - name: Hole name
                - label: Hole label
                - type_id: Object type
                - validated: Check if the result has a valid shape
                - removed_volume: Removed volume of the body
                - support_kind: ``planar_face`` or ``body_origin_plane``
        """
        if diameter <= 0:
            raise ValueError("Hole diameter must be greater than zero")
        if depth <= 0:
            raise ValueError("Hole depth must be greater than zero")

        normalized_hole_type = hole_type.strip().lower().replace("_", "")
        hole_type_map = {
            "dimension": "Dimension",
            "throughall": "ThroughAll",
        }
        if normalized_hole_type not in hole_type_map:
            raise ValueError(
                "Unsupported hole_type. Use 'Dimension' or 'ThroughAll'. "
                "FreeCAD 1.0 does not expose UpToFirst for PartDesign::Hole."
            )
        depth_type = hole_type_map[normalized_hole_type]

        normalized_thread_type = (
            thread_type.strip().upper().replace(" ", "").replace("-", "")
        )
        thread_type_map = {
            "ISO": "ISOMetricProfile",
            "ISOMETRICPROFILE": "ISOMetricProfile",
            "ISOFINE": "ISOMetricFineProfile",
            "ISOMETRICFINEPROFILE": "ISOMetricFineProfile",
            "UNC": "UNC",
            "UNF": "UNF",
        }
        if threaded and normalized_thread_type not in thread_type_map:
            raise ValueError(
                "Unsupported thread_type. Use ISO, ISO_FINE, UNC, or UNF."
            )
        resolved_thread_type = thread_type_map.get(
            normalized_thread_type, "ISOMetricProfile"
        )

        normalized_drill_point = drill_point.strip().lower()
        drill_point_map = {"flat": "Flat", "angled": "Angled"}
        if normalized_drill_point not in drill_point_map:
            raise ValueError("Unsupported drill_point. Use 'Flat' or 'Angled'.")
        resolved_drill_point = drill_point_map[normalized_drill_point]

        bridge = await get_bridge()

        code = f"""
import Part

{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.listDocuments().get(requested_doc_name)
    if requested_doc_name is not None
    else FreeCAD.ActiveDocument
)
if doc is None:
    raise ValueError(
        "Document not found. create_hole requires an existing document; "
        "it will not create one implicitly."
    )

sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
if sketch.TypeId != "Sketcher::SketchObject":
    raise ValueError(
        f"Object {sketch_name!r} is not a Sketcher::SketchObject: {{sketch.TypeId}}"
    )

# Find the unique PartDesign Body containing the sketch.
body = _find_body_containing_object(doc, sketch)
if body is None:
    raise ValueError("Sketch must belong to a PartDesign Body")

# A profile sketch is single-use in a PartDesign history. Reusing it creates
# ambiguous dependencies and frequently leaves invalid/no-op Hole features.
consumers = []
for obj in doc.Objects:
    if obj is sketch or obj is body or not hasattr(obj, "Profile"):
        continue
    try:
        profile = obj.Profile
        profile_obj = profile[0] if isinstance(profile, (tuple, list)) else profile
        if profile_obj is sketch:
            consumers.append(obj.Name)
    except Exception:
        pass
if consumers:
    raise ValueError(
        "Sketch is already consumed by PartDesign feature(s): "
        + ", ".join(consumers)
        + ". Create a new sketch for another hole operation."
    )

# FreeCAD 1.0 Hole uses circle/arc centers. This MCP tool deliberately accepts
# only full circles: they are deterministic and do not require contour analysis.
profile_circle_count = 0
unsupported_geometry = []
for index, geometry in enumerate(sketch.Geometry):
    try:
        if sketch.getConstruction(index):
            continue
    except Exception:
        pass
    geometry_type = getattr(geometry, "TypeId", type(geometry).__name__)
    if geometry_type == "Part::GeomCircle":
        profile_circle_count += 1
    else:
        unsupported_geometry.append(f"{{index}}:{{geometry_type}}")
if profile_circle_count == 0:
    raise ValueError(
        "Hole sketch contains no non-construction circles. "
        "Use add_sketch_circle for each hole location; sketch points are not "
        "a reliable PartDesign::Hole profile in FreeCAD 1.0.x."
    )
if unsupported_geometry:
    raise ValueError(
        "Hole sketch must contain only non-construction circles. Unsupported "
        "geometry: " + ", ".join(unsupported_geometry)
    )

# Locate the most recent valid solid feature preceding the sketch in the Body.
base_feature = _find_preceding_single_solid_feature(body, sketch)
if base_feature is None:
    raise ValueError(
        "No valid single-solid feature exists before the hole sketch. "
        "Create a Pad or another solid feature first."
    )

base_shape = base_feature.Shape.copy()
base_volume = float(base_shape.Volume)
if base_volume <= 0:
    raise ValueError("Base feature has zero volume")
volume_tolerance = max(1e-7, abs(base_volume) * 1e-9)

# Classify sketch support before creating the Hole. Datum planes look valid at
# the object/property level but repeatedly produce no-op Hole features in
# FreeCAD 1.0.x. Fail early with the correct alternative instead of making the
# agent try Reversed, Face1, and other attachment permutations blindly.
support_object = None
support_sub_elements = []
attachment = getattr(sketch, "AttachmentSupport", None)
if attachment:
    try:
        support_object, support_sub_elements = attachment[0]
    except Exception:
        pass
elif hasattr(sketch, "Support") and sketch.Support:
    try:
        support_object, support_sub_elements = sketch.Support
    except Exception:
        pass

support_name = getattr(support_object, "Name", None)
support_type = getattr(support_object, "TypeId", None)
support_sub_element = None
try:
    if support_sub_elements:
        support_sub_element = str(support_sub_elements[0])
except Exception:
    support_sub_element = None

if support_type == "PartDesign::Plane":
    raise ValueError(
        "create_hole does not support a sketch attached to a PartDesign datum "
        f"plane reliably in FreeCAD 1.0.x (support={{support_name!r}}). "
        "Use create_cylindrical_cut with an explicit axis_origin, "
        "axis_direction, diameter, and depth. A datum plane may still be used "
        "to derive that origin and direction."
    )

support_kind = "unknown"
if support_sub_element and support_sub_element.startswith("Face"):
    support_kind = "planar_face"
    shape = getattr(support_object, "Shape", None)
    try:
        support_face = shape.getElement(support_sub_element)
    except Exception as exc:
        raise ValueError(
            f"Hole sketch support face is unavailable: "
            f"{{support_name}}.{{support_sub_element}}"
        ) from exc
    surface_name = type(getattr(support_face, "Surface", None)).__name__
    surface_type = getattr(getattr(support_face, "Surface", None), "TypeId", "")
    if "Plane" not in surface_name and surface_type != "Part::GeomPlane":
        raise ValueError(
            "create_hole requires a planar support face. "
            f"Received {{support_name}}.{{support_sub_element}} "
            f"with surface type {{surface_type or surface_name!r}}. "
            "Use create_cylindrical_cut for an arbitrary cylindrical cut."
        )
elif support_name and any(
    token in support_name for token in ("XY_Plane", "XZ_Plane", "YZ_Plane")
):
    support_kind = "body_origin_plane"
elif support_object is None:
    raise ValueError(
        "Hole sketch is not attached to a support. Attach it to a planar face "
        "of the solid, or use create_cylindrical_cut for an off-face cut."
    )

try:
    sketch_global_placement = sketch.getGlobalPlacement()
except Exception:
    sketch_global_placement = sketch.Placement
sketch_normal = sketch_global_placement.Rotation.multVec(
    FreeCAD.Vector(0, 0, 1)
)
if sketch_normal.Length <= 1e-12:
    raise ValueError("Hole sketch has an invalid zero-length normal")
sketch_normal.normalize()
circle_world_centers = []
for index, geometry in enumerate(sketch.Geometry):
    try:
        if sketch.getConstruction(index):
            continue
    except Exception:
        pass
    if getattr(geometry, "TypeId", "") != "Part::GeomCircle":
        continue
    circle_world_centers.append(
        sketch_global_placement.multVec(geometry.Center)
    )



hole = None
created_hole_name = None
original_tip_name = getattr(body.Tip, "Name", None)
doc.openTransaction("Create validated Hole")
try:
    hole_name = {name!r} or "Hole"
    hole = body.newObject("PartDesign::Hole", hole_name)
    created_hole_name = hole.Name
    hole.Profile = sketch
    hole.DepthType = {depth_type!r}
    if {depth_type!r} == "Dimension":
        hole.Depth = {depth}
        # FreeCAD defaults to an angled drill point, which adds a conical tip
        # beyond the cylindrical depth. Use a flat bottom by default so MCP
        # dimensions and volume comparisons are deterministic.
        if hasattr(hole, "DrillPoint"):
            hole.DrillPoint = {resolved_drill_point!r}
        if hasattr(hole, "DrillForDepth"):
            hole.DrillForDepth = False

    if {threaded}:
        resolved_thread_profile = {resolved_thread_type!r}
        hole.ThreadType = resolved_thread_profile
        requested_size = {thread_size!r}.strip()
        available_sizes = []
        try:
            available_sizes = list(hole.getEnumerationsOfProperty("ThreadSize"))
        except Exception:
            pass

        resolved_size = requested_size
        if available_sizes and requested_size not in available_sizes:
            request_lower = requested_size.lower()
            candidates = [
                option for option in available_sizes
                if option.lower() == request_lower
                or option.lower().startswith(request_lower + "x")
            ]
            if len(candidates) == 1:
                resolved_size = candidates[0]
            else:
                raise ValueError(
                    f"Unsupported thread_size {{requested_size!r}} for "
                    f"{{resolved_thread_profile}}. Available examples: "
                    + ", ".join(available_sizes[:12])
                )
        hole.ThreadSize = resolved_size
        hole.Threaded = True
    else:
        hole.ThreadType = "None"
        hole.Threaded = False
        hole.Diameter = {diameter}

    requested_reversed = {reversed!r}
    directions_to_try = (
        [requested_reversed] if requested_reversed is not None else [False, True]
    )
    attempts = []
    selected = None
    for direction in directions_to_try:
        hole.Reversed = bool(direction)
        doc.recompute()
        validation = _validate_subtractive_feature(
            hole,
            body,
            base_shape,
            volume_tolerance=volume_tolerance,
        )

        # Validate each intended hole location geometrically. Counting solids in
        # base_shape.cut(result) is brittle: one valid through-hole can be split
        # into multiple BRep solids at the sketch plane. A probe around every
        # circle axis directly proves that each requested location removed
        # material without requiring a topology-specific solid count.
        circle_probe_volumes = []
        if validation["ok"]:
            removed_shape = base_shape.cut(hole.Shape)
            bounds = base_shape.BoundBox
            diagonal = (
                bounds.XLength ** 2
                + bounds.YLength ** 2
                + bounds.ZLength ** 2
            ) ** 0.5
            probe_half_length = max(float({depth}), diagonal + float({depth}))
            probe_radius = float({diameter}) / 2.0 * 1.000001
            for center in circle_world_centers:
                probe_start = center - sketch_normal * probe_half_length
                probe = Part.makeCylinder(
                    probe_radius,
                    probe_half_length * 2.0,
                    probe_start,
                    sketch_normal,
                )
                probe_volume = float(removed_shape.common(probe).Volume)
                circle_probe_volumes.append(probe_volume)
            missing_locations = [
                index
                for index, probe_volume in enumerate(circle_probe_volumes)
                if probe_volume <= volume_tolerance
            ]
            if missing_locations:
                validation["ok"] = False
                validation["reasons"].append(
                    "no material was removed at circle index(es): "
                    + ", ".join(str(index) for index in missing_locations)
                )
        attempts.append({{
            "reversed": bool(direction),
            "ok": validation["ok"],
            "reasons": validation["reasons"],
            "status": validation["status"],
            "circle_probe_volumes": circle_probe_volumes,
        }})
        if validation["ok"]:
            selected = {{
                "reversed": bool(direction),
                "result_volume": validation["result_volume"],
                "solid_count": validation["solid_count"],
                "removed_solid_count": validation["removed_solid_count"],
                "shape_valid": validation["shape_valid"],
                "circle_probe_volumes": circle_probe_volumes,
            }}
            break

    if selected is None:
        details = "; ".join(
            f"reversed={{attempt['reversed']}}: "
            + (", ".join(attempt["reasons"]) or "unknown failure")
            for attempt in attempts
        )
        raise ValueError(
            "Hole produced no valid subtractive result in the tested direction(s). "
            f"Support={{support_name!r}}; sub-element={{support_sub_element!r}}; "
            f"support kind={{support_kind}}. Attach the sketch to an actual "
            "planar face of the solid when possible. For radial or off-face "
            "cuts, use create_cylindrical_cut instead of moving the Hole sketch "
            "between origin and datum planes. " + details
        )

    removed_volume = base_volume - selected["result_volume"]
    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        # Some FreeCAD builds can leave a failed feature after abortTransaction.
        # Remove only the object created by this call and restore a clean history.
        if created_hole_name:
            leftover = doc.getObject(created_hole_name)
            if leftover is not None:
                try:
                    doc.removeObject(created_hole_name)
                    if original_tip_name:
                        original_tip = doc.getObject(original_tip_name)
                        if original_tip is not None:
                            body.Tip = original_tip
                    doc.recompute()
                except Exception:
                    pass
    raise

_result_ = {{
    "name": hole.Name,
    "label": hole.Label,
    "type_id": hole.TypeId,
    "validated": True,
    "profile_circle_count": profile_circle_count,
    "base_feature": base_feature.Name,
    "base_volume": base_volume,
    "result_volume": selected["result_volume"],
    "removed_volume": removed_volume,
    "solid_count": selected["solid_count"],
    "reversed": selected["reversed"],
    "depth_type": str(hole.DepthType),
    "depth": float(hole.Depth) if {depth_type!r} == "Dimension" else None,
    "effective_diameter": float(getattr(hole, "Diameter", {diameter})),
    "drill_point": str(getattr(hole, "DrillPoint", "")),
    "threaded": bool(hole.Threaded),
    "support_kind": support_kind,
    "support_object": support_name,
    "support_sub_element": support_sub_element,
    "circle_probe_volumes": selected["circle_probe_volumes"],
}}
"""
        result = await bridge.execute_python(code)
        if not result.success:
            raise ValueError(result.error_traceback or "Hole creation failed")

        return require_subtractive_result(result.result, "Hole")

    @mcp.tool()
    async def create_cylindrical_cut(
        body_name: str,
        axis_origin: list[float],
        axis_direction: list[float],
        diameter: float,
        depth: float,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a validated cylindrical cut with an explicit world-space axis.

        Use this tool for radial holes, tangent-plane holes, oil passages, and
        other cylindrical cuts that do not start from an actual planar face.
        Unlike ``create_hole``, it does not require a sketch or datum-plane
        attachment. The cylinder starts at ``axis_origin`` and extends by
        ``depth`` along the normalized ``axis_direction``.

        Args:
            body_name: Existing PartDesign Body to cut.
            axis_origin: World-space start point ``[x, y, z]`` in millimetres.
            axis_direction: World-space cutting direction ``[dx, dy, dz]``.
            diameter: Cylinder diameter in millimetres.
            depth: Cut depth in millimetres.
            name: Feature name. Defaults to ``CylindricalCut``.
            doc_name: Existing document containing the Body. Uses the active
                document if None. A missing document is never created silently.

        Returns:
            Validation evidence including removed volume, final solid count,
            normalized axis direction, origin, diameter, and depth.
        """
        if len(axis_origin) != 3:
            raise ValueError("axis_origin must contain exactly three coordinates")
        if len(axis_direction) != 3:
            raise ValueError("axis_direction must contain exactly three components")
        if diameter <= 0:
            raise ValueError("Cylindrical cut diameter must be greater than zero")
        if depth <= 0:
            raise ValueError("Cylindrical cut depth must be greater than zero")

        try:
            resolved_origin = [float(value) for value in axis_origin]
            resolved_direction = [float(value) for value in axis_direction]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "axis_origin and axis_direction must contain numeric values"
            ) from exc
        direction_norm = sum(value * value for value in resolved_direction) ** 0.5
        if direction_norm <= 1e-12:
            raise ValueError("axis_direction must be non-zero")

        bridge = await get_bridge()
        code = f"""
import Part

{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.listDocuments().get(requested_doc_name)
    if requested_doc_name is not None
    else FreeCAD.ActiveDocument
)
if doc is None:
    raise ValueError(
        "Document not found. create_cylindrical_cut requires an existing "
        "document; it will not create one implicitly."
    )

body = doc.getObject({body_name!r})
if body is None:
    raise ValueError(f"Body not found: {body_name!r}")
if body.TypeId != "PartDesign::Body":
    raise ValueError(
        f"Object {body_name!r} is not a PartDesign Body: {{body.TypeId}}"
    )

base_feature = body.Tip
base_shape = getattr(base_feature, "Shape", None)
if (
    base_feature is None
    or base_shape is None
    or base_shape.isNull()
    or not base_shape.isValid()
    or len(base_shape.Solids) != 1
    or float(base_shape.Volume) <= 0
):
    raise ValueError(
        "create_cylindrical_cut requires a valid single-solid Body Tip"
    )
base_shape = base_shape.copy()
base_volume = float(base_shape.Volume)
volume_tolerance = max(1e-7, abs(base_volume) * 1e-9)

origin = FreeCAD.Vector(*{resolved_origin!r})
direction = FreeCAD.Vector(*{resolved_direction!r})
if direction.Length <= 1e-12:
    raise ValueError("axis_direction must be non-zero")
direction.normalize()

original_tip_name = getattr(body.Tip, "Name", None)
created_name = None
doc.openTransaction("Create validated cylindrical cut")
try:
    cut_name = {name!r} or "CylindricalCut"
    cut = body.newObject("PartDesign::SubtractiveCylinder", cut_name)
    created_name = cut.Name
    cut.Radius = float({diameter}) / 2.0
    cut.Height = float({depth})
    if hasattr(cut, "Angle"):
        cut.Angle = 360.0
    cut.Placement = FreeCAD.Placement(
        origin,
        FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), direction),
    )
    doc.recompute()

    validation = _validate_subtractive_feature(
        cut,
        body,
        base_shape,
        volume_tolerance=volume_tolerance,
    )
    if not validation["ok"]:
        details = "; ".join(validation["reasons"])
        raise ValueError(
            "Cylindrical cut failed: " + details + ". Check that the axis "
            "starts at or outside the material, points through the Body, and "
            "uses sufficient depth."
        )

    # Confirm that material was removed specifically along the requested axis.
    requested_tool = Part.makeCylinder(
        float({diameter}) / 2.0,
        float({depth}),
        origin,
        direction,
    )
    removed_shape = base_shape.cut(cut.Shape)
    axis_removed_volume = float(removed_shape.common(requested_tool).Volume)
    if axis_removed_volume <= volume_tolerance:
        raise ValueError(
            "Cylindrical cut changed the Body but removed no material along "
            "the requested axis"
        )

    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        _cleanup_failed_partdesign_feature(
            doc,
            body,
            created_name,
            original_tip_name,
        )
    raise

_result_ = {{
    "name": cut.Name,
    "label": cut.Label,
    "type_id": cut.TypeId,
    "validated": True,
    "base_volume": base_volume,
    "result_volume": validation["result_volume"],
    "removed_volume": validation["removed_volume"],
    "axis_removed_volume": axis_removed_volume,
    "solid_count": validation["solid_count"],
    "axis_origin": [origin.x, origin.y, origin.z],
    "axis_direction": [direction.x, direction.y, direction.z],
    "diameter": float({diameter}),
    "depth": float({depth}),
}}
"""
        result = await bridge.execute_python(code)
        if not result.success:
            raise ValueError(
                result.error_traceback or "Cylindrical cut creation failed"
            )
        return require_subtractive_result(result.result, "Cylindrical cut")

    @mcp.tool()
    async def linear_pattern(
        feature_name: str,
        direction: str = "X",
        length: float = 50.0,
        occurrences: int = 3,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Linear Pattern from a PartDesign feature.

        Repeats a feature in a linear direction.

        Args:
            feature_name: Name of the feature to pattern.
            direction: Pattern direction. Options: "X", "Y", "Z".
            length: Total pattern length. Defaults to 50.0.
            occurrences: Number of pattern instances. Defaults to 3.
            name: Pattern feature name. Auto-generated if None.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created pattern information:
                - name: Pattern name
                - label: Pattern label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = _find_body_containing_object(doc, feature)

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

# Wrap in transaction for undo support
doc.openTransaction("Linear Pattern")
try:
    pattern_name = {name!r} or "LinearPattern"
    pattern = body.newObject("PartDesign::LinearPattern", pattern_name)
    pattern.Originals = [feature]
    pattern.Length = {length}
    pattern.Occurrences = {occurrences}

    # Set direction
    dir_name = {direction!r}
    if dir_name not in {{"X", "Y", "Z"}}:
        raise ValueError(f"Invalid pattern direction: {{dir_name!r}}")
    axis_obj = _resolve_body_origin_feature(body, f"{{dir_name}}_Axis")
    pattern.Direction = (axis_obj, [""])

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": pattern.Name,
    "label": pattern.Label,
    "type_id": pattern.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Linear pattern failed")

    @mcp.tool()
    async def polar_pattern(
        feature_name: str,
        axis: str = "Z",
        angle: float = 360.0,
        occurrences: int = 6,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Polar (circular) Pattern from a PartDesign feature.

        Repeats a feature around an axis.

        Args:
            feature_name: Name of the feature to pattern.
            axis: Pattern axis. Options: "X", "Y", "Z".
            angle: Total pattern angle. Defaults to 360.0.
            occurrences: Number of pattern instances. Defaults to 6.
            name: Pattern feature name. Auto-generated if None.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created pattern information:
                - name: Pattern name
                - label: Pattern label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = _find_body_containing_object(doc, feature)

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

# Wrap in transaction for undo support
doc.openTransaction("Polar Pattern")
try:
    pattern_name = {name!r} or "PolarPattern"
    pattern = body.newObject("PartDesign::PolarPattern", pattern_name)
    pattern.Originals = [feature]
    pattern.Angle = {angle}
    pattern.Occurrences = {occurrences}

    # Set axis
    axis_name = {axis!r}
    if axis_name not in {{"X", "Y", "Z"}}:
        raise ValueError(f"Invalid pattern axis: {{axis_name!r}}")
    axis_obj = _resolve_body_origin_feature(body, f"{{axis_name}}_Axis")
    pattern.Axis = (axis_obj, [""])

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": pattern.Name,
    "label": pattern.Label,
    "type_id": pattern.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Polar pattern failed")

    @mcp.tool()
    async def mirrored_feature(
        feature_name: str,
        plane: str = "XY",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Mirrored feature from a PartDesign feature.

        Mirrors a feature across a plane.

        Args:
            feature_name: Name of the feature to mirror.
            plane: Mirror plane. Options: "XY", "XZ", "YZ".
            name: Mirrored feature name. Auto-generated if None.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created mirror information:
                - name: Mirror name
                - label: Mirror label
                - type_id: Object type
        """
        bridge = await get_bridge()

        plane_map = {
            "XY": "XY_Plane",
            "XZ": "XZ_Plane",
            "YZ": "YZ_Plane",
        }

        if plane not in plane_map:
            raise ValueError(f"Invalid plane: {plane}. Use: XY, XZ, YZ")

        plane_ref = plane_map[plane]

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = _find_body_containing_object(doc, feature)

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

# Wrap in transaction for undo support
doc.openTransaction("Mirrored Feature")
try:
    mirror_name = {name!r} or "Mirrored"
    mirror = body.newObject("PartDesign::Mirrored", mirror_name)
    mirror.Originals = [feature]
    plane_obj = _resolve_body_origin_feature(body, {plane_ref!r})
    mirror.MirrorPlane = (plane_obj, [""])

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": mirror.Name,
    "label": mirror.Label,
    "type_id": mirror.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Mirrored feature failed")

    @mcp.tool()
    async def add_sketch_line(
        sketch_name: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        construction: bool = False,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a line to a sketch.

        Args:
            sketch_name: Name of the sketch to add line to.
            x1: X coordinate of start point.
            y1: Y coordinate of start point.
            x2: X coordinate of end point.
            y2: Y coordinate of end point.
            construction: Whether this is a construction line. Defaults to False.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Index of the added line
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Line")
try:
    import Part

    idx = sketch.addGeometry(
        Part.LineSegment(
            FreeCAD.Vector({x1}, {y1}, 0),
            FreeCAD.Vector({x2}, {y2}, 0)
        ),
        {construction}
    )
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "sketch_name": sketch.Name,
    "geometry_index": idx,
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add line failed")

    @mcp.tool()
    async def add_sketch_arc(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add an arc to a sketch.

        Args:
            sketch_name: Name of the sketch to add arc to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            radius: Arc radius.
            start_angle: Start angle in degrees.
            end_angle: End angle in degrees.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Index of the added arc
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Arc")
try:
    import Part
    import math

    center = FreeCAD.Vector({center_x}, {center_y}, 0)
    start_rad = math.radians({start_angle})
    end_rad = math.radians({end_angle})

    arc = Part.ArcOfCircle(
        Part.Circle(center, FreeCAD.Vector(0, 0, 1), {radius}),
        start_rad,
        end_rad
    )
    idx = sketch.addGeometry(arc, False)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": sketch.Name,
    "geometry_index": idx,
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add arc failed")

    @mcp.tool()
    async def add_sketch_point(
        sketch_name: str,
        x: float,
        y: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a point to a sketch.

        Points are useful as reference locations. For create_hole on FreeCAD 1.0.x, use non-construction circles instead.

        Args:
            sketch_name: Name of the sketch to add point to.
            x: X coordinate.
            y: Y coordinate.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Index of the added point
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Point")
try:
    import Part

    idx = sketch.addGeometry(Part.Point(FreeCAD.Vector({x}, {y}, 0)), False)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": sketch.Name,
    "geometry_index": idx,
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add point failed")

    @mcp.tool()
    async def loft_sketches(
        sketch_names: list[str],
        ruled: bool = False,
        closed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Loft (additive) through multiple sketches.

        A loft creates a solid by connecting multiple profile sketches.

        Args:
            sketch_names: List of sketch names to loft through (in order).
            ruled: Whether to create ruled surfaces. Defaults to False.
            closed: Whether to close the loft. Defaults to False.
            name: Loft feature name. Auto-generated if None.
            doc_name: Document containing the sketches. Uses active document if None.

        Returns:
            Dictionary with created loft information:
                - name: Loft name
                - label: Loft label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

sketches = []
for sname in {sketch_names!r}:
    sketch = doc.getObject(sname)
    if sketch is None:
        raise ValueError(f"Sketch not found: {{sname}}")
    sketches.append(sketch)

if len(sketches) < 2:
    raise ValueError("Loft requires at least 2 sketches")

# Find the body containing the first sketch
body = _find_body_containing_object(doc, sketches[0])

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body for Loft operation")

base_feature = _find_preceding_single_solid_feature(body, sketches[0])
base_shape = base_feature.Shape.copy() if base_feature is not None else None

original_tip_name = getattr(body.Tip, "Name", None)
created_loft_name = None
# Wrap in transaction for undo support
doc.openTransaction("Loft Sketches")
try:
    loft_name = {name!r} or "Loft"
    loft = body.newObject("PartDesign::AdditiveLoft", loft_name)
    created_loft_name = loft.Name
    loft.Profile = sketches[0]
    loft.Sections = sketches[1:]
    loft.Ruled = {ruled}
    loft.Closed = {closed}

    doc.recompute()
    validation = _validate_additive_feature(loft, body, base_shape)
    if not validation["ok"]:
        raise ValueError("Loft failed: " + "; ".join(validation["reasons"]))
    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        _cleanup_failed_partdesign_feature(
            doc, body, created_loft_name, original_tip_name
        )
    raise

_result_ = {{
    "name": loft.Name,
    "label": loft.Label,
    "type_id": loft.TypeId,
    "validated": validation["ok"],
    "base_volume": validation["base_volume"],
    "result_volume": validation["result_volume"],
    "added_volume": validation["added_volume"],
    "solid_count": validation["solid_count"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return require_additive_result(result.result, 'Loft')
        raise ValueError(result.error_traceback or "Loft failed")

    @mcp.tool()
    async def sweep_sketch(
        profile_sketch: str,
        spine_sketch: str,
        transition: str = "Transformed",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Sweep (additive) along a spine path.

        A sweep extrudes a profile sketch along a path defined by another sketch.

        Args:
            profile_sketch: Name of the profile sketch to sweep.
            spine_sketch: Name of the spine (path) sketch.
            transition: Transition mode. Options:
                - "Transformed" - Smooth transitions
                - "Right" - Sharp corners
                - "Round" - Rounded corners
            name: Sweep feature name. Auto-generated if None.
            doc_name: Document containing the sketches. Uses active document if None.

        Returns:
            Dictionary with created sweep information:
                - name: Sweep name
                - label: Sweep label
                - type_id: Object type
        """
        bridge = await get_bridge()

        transition_map = {
            "Transformed": 0,
            "Right": 1,
            "Round": 2,
        }

        if transition not in transition_map:
            raise ValueError(
                f"Invalid transition: {transition}. Use: Transformed, Right, Round"
            )

        code = f"""
{BODY_RUNTIME_HELPERS}

{FEATURE_VALIDATION_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

profile = doc.getObject({profile_sketch!r})
if profile is None:
    raise ValueError(f"Profile sketch not found: {profile_sketch!r}")

spine = doc.getObject({spine_sketch!r})
if spine is None:
    raise ValueError(f"Spine sketch not found: {spine_sketch!r}")

# Find the body containing the profile sketch
body = _find_body_containing_object(doc, profile)

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body for Sweep operation")

base_feature = _find_preceding_single_solid_feature(body, profile)
base_shape = base_feature.Shape.copy() if base_feature is not None else None

original_tip_name = getattr(body.Tip, "Name", None)
created_sweep_name = None
# Wrap in transaction for undo support
doc.openTransaction("Sweep Sketch")
try:
    sweep_name = {name!r} or "Sweep"
    sweep = body.newObject("PartDesign::AdditivePipe", sweep_name)
    created_sweep_name = sweep.Name
    sweep.Profile = profile
    sweep.Spine = (spine, ["Edge1"])
    sweep.Transition = {transition_map[transition]}

    doc.recompute()
    validation = _validate_additive_feature(sweep, body, base_shape)
    if not validation["ok"]:
        raise ValueError("Sweep failed: " + "; ".join(validation["reasons"]))
    doc.commitTransaction()
except Exception:
    try:
        doc.abortTransaction()
    finally:
        _cleanup_failed_partdesign_feature(
            doc, body, created_sweep_name, original_tip_name
        )
    raise

_result_ = {{
    "name": sweep.Name,
    "label": sweep.Label,
    "type_id": sweep.TypeId,
    "validated": validation["ok"],
    "base_volume": validation["base_volume"],
    "result_volume": validation["result_volume"],
    "added_volume": validation["added_volume"],
    "solid_count": validation["solid_count"],
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return require_additive_result(result.result, 'Sweep')
        raise ValueError(result.error_traceback or "Sweep failed")

    # =========================================================================
    # PartDesign Datum Features
    # =========================================================================

    @mcp.tool()
    async def create_datum_plane(
        body_name: str,
        offset: float = 0.0,
        base_plane: str = "XY_Plane",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a datum plane in a PartDesign body.

        Datum planes are reference planes used for sketching or measurements.

        Args:
            body_name: Name of the PartDesign body.
            offset: Offset distance from base plane. Defaults to 0.
            base_plane: Base plane to offset from. Options:
                - "XY_Plane" - Horizontal plane
                - "XZ_Plane" - Front vertical plane
                - "YZ_Plane" - Side vertical plane
            name: Datum plane name. Auto-generated if None.
            doc_name: Document containing the body. Uses active document if None.

        Returns:
            Dictionary with created datum information:
                - name: Datum name
                - label: Datum label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

body = doc.getObject({body_name!r})
if body is None:
    raise ValueError(f"Body not found: {body_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Create Datum Plane")
try:
    datum_name = {name!r} or "DatumPlane"
    datum = body.newObject("PartDesign::Plane", datum_name)

    # Set reference plane
    plane = {base_plane!r}
    if plane not in {{"XY_Plane", "XZ_Plane", "YZ_Plane"}}:
        raise ValueError(f"Invalid base plane: {{plane!r}}")
    plane_obj = _resolve_body_origin_feature(body, plane)
    datum.AttachmentSupport = [(plane_obj, "")]
    datum.MapMode = "FlatFace"
    datum.MapPathParameter = 0
    datum.MapReversed = False
    datum.AttachmentOffset = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, {offset}),
        FreeCAD.Rotation(0, 0, 0, 1)
    )

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": datum.Name,
        "label": datum.Label,
        "type_id": datum.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create datum plane failed")

    @mcp.tool()
    async def create_datum_line(
        body_name: str,
        base_axis: str = "X_Axis",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a datum line (axis) in a PartDesign body.

        Datum lines are reference axes used for patterns or measurements.

        Args:
            body_name: Name of the PartDesign body.
            base_axis: Base axis. Options: "X_Axis", "Y_Axis", "Z_Axis".
            name: Datum line name. Auto-generated if None.
            doc_name: Document containing the body. Uses active document if None.

        Returns:
            Dictionary with created datum information:
                - name: Datum name
                - label: Datum label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

body = doc.getObject({body_name!r})
if body is None:
    raise ValueError(f"Body not found: {body_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Create Datum Line")
try:
    datum_name = {name!r} or "DatumLine"
    datum = body.newObject("PartDesign::Line", datum_name)

    # Set reference axis
    axis = {base_axis!r}
    if axis not in {{"X_Axis", "Y_Axis", "Z_Axis"}}:
        raise ValueError(f"Invalid base axis: {{axis!r}}")
    axis_obj = _resolve_body_origin_feature(body, axis)
    datum.AttachmentSupport = [(axis_obj, "")]
    datum.MapMode = "ObjectXY"

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": datum.Name,
        "label": datum.Label,
        "type_id": datum.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create datum line failed")

    @mcp.tool()
    async def create_datum_point(
        body_name: str,
        position: list[float] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a datum point in a PartDesign body.

        Datum points are reference points used for measurements or construction.

        Args:
            body_name: Name of the PartDesign body.
            position: Point position [x, y, z]. Uses origin if None.
            name: Datum point name. Auto-generated if None.
            doc_name: Document containing the body. Uses active document if None.

        Returns:
            Dictionary with created datum information:
                - name: Datum name
                - label: Datum label
                - type_id: Object type
        """
        bridge = await get_bridge()

        pos = position if position else [0, 0, 0]

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

body = doc.getObject({body_name!r})
if body is None:
    raise ValueError(f"Body not found: {body_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Create Datum Point")
try:
    datum_name = {name!r} or "DatumPoint"
    datum = body.newObject("PartDesign::Point", datum_name)

    # Set offset from the origin point that belongs to this Body.
    origin_point = _resolve_body_origin_feature(body, "Point")
    datum.AttachmentSupport = [(origin_point, "")]
    datum.MapMode = "ObjectOrigin"
    datum.AttachmentOffset = FreeCAD.Placement(
        FreeCAD.Vector({pos[0]}, {pos[1]}, {pos[2]}),
        FreeCAD.Rotation(0, 0, 0, 1)
    )

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": datum.Name,
        "label": datum.Label,
        "type_id": datum.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create datum point failed")

    # =========================================================================
    # PartDesign Dress-up Features
    # =========================================================================

    @mcp.tool()
    async def draft_feature(
        object_name: str,
        angle: float,
        plane: str = "XY",
        faces: list[str] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add draft angle to faces of an object.

        Draft angles are used in manufacturing to allow parts to be
        released from molds.

        Args:
            object_name: Name of the object to draft.
            angle: Draft angle in degrees.
            plane: Neutral plane for draft direction: "XY", "XZ", "YZ".
            faces: List of face names to draft (e.g., ["Face1", "Face2"]).
                   Drafts all suitable faces if None.
            name: Draft feature name. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created draft information:
                - name: Draft name
                - label: Draft label
                - type_id: Object type
        """
        bridge = await get_bridge()

        # Use actual None or list, not string "None"
        faces_param = faces if faces else None

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

if body is None:
    raise ValueError("Object must be inside a PartDesign Body for Draft operation")

# Get selected faces (None means all suitable faces)
selected_faces = {faces_param!r}

# Wrap in transaction for undo support
doc.openTransaction("Draft Feature")
try:
    draft_name = {name!r} or "Draft"
    draft = body.newObject("PartDesign::Draft", draft_name)

    draft.Angle = {angle}
    draft.Base = (obj, selected_faces if selected_faces else [])

    # Set neutral plane
    plane_name = {plane!r}
    plane_map = {{"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}}
    if plane_name in plane_map:
        plane_obj = _resolve_body_origin_feature(body, plane_map[plane_name])
        draft.NeutralPlane = (plane_obj, "")

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": draft.Name,
        "label": draft.Label,
        "type_id": draft.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Draft feature failed")

    @mcp.tool()
    async def thickness_feature(
        object_name: str,
        thickness: float,
        faces_to_remove: list[str],
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a thickness (shell) feature in PartDesign.

        Hollows out a solid by removing specified faces and offsetting
        the remaining faces.

        Args:
            object_name: Name of the solid feature to shell.
            thickness: Wall thickness (positive = inward).
            faces_to_remove: List of face names to remove (e.g., ["Face1"]).
            name: Thickness feature name. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created thickness information:
                - name: Thickness name
                - label: Thickness label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

if body is None:
    raise ValueError("Object must be inside a PartDesign Body for Thickness operation")

# Wrap in transaction for undo support
doc.openTransaction("Thickness Feature")
try:
    thickness_name = {name!r} or "Thickness"
    thick = body.newObject("PartDesign::Thickness", thickness_name)

    thick.Value = {thickness}
    thick.Base = (obj, {faces_to_remove!r})
    thick.Mode = 0  # Skin mode
    thick.Join = 0  # Arc join

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": thick.Name,
        "label": thick.Label,
        "type_id": thick.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Thickness feature failed")

    # =========================================================================
    # PartDesign Subtractive Features
    # =========================================================================

    @mcp.tool()
    async def subtractive_loft(
        sketch_names: list[str],
        ruled: bool = False,
        closed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a subtractive loft (cut) through multiple sketches.

        Args:
            sketch_names: List of sketch names to loft through (in order).
            ruled: Whether to create ruled surfaces. Defaults to False.
            closed: Whether to close the loft. Defaults to False.
            name: Loft feature name. Auto-generated if None.
            doc_name: Document containing the sketches. Uses active document if None.

        Returns:
            Dictionary with created loft information:
                - name: Loft name
                - label: Loft label
                - type_id: Object type
        """
        bridge = await get_bridge()

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

sketches = []
for sname in {sketch_names!r}:
    sketch = doc.getObject(sname)
    if sketch is None:
        raise ValueError(f"Sketch not found: {{sname}}")
    sketches.append(sketch)

if len(sketches) < 2:
    raise ValueError("Loft requires at least 2 sketches")

# Find the body containing the first sketch
body = _find_body_containing_object(doc, sketches[0])

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body")

# Wrap in transaction for undo support
doc.openTransaction("Subtractive Loft")
try:
    loft_name = {name!r} or "SubtractiveLoft"
    loft = body.newObject("PartDesign::SubtractiveLoft", loft_name)
    loft.Profile = sketches[0]
    loft.Sections = sketches[1:]
    loft.Ruled = {ruled}
    loft.Closed = {closed}

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": loft.Name,
        "label": loft.Label,
        "type_id": loft.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Subtractive loft failed")

    @mcp.tool()
    async def subtractive_pipe(
        profile_sketch: str,
        spine_sketch: str,
        transition: str = "Transformed",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a subtractive pipe (sweep cut) along a spine path.

        Args:
            profile_sketch: Name of the profile sketch to sweep.
            spine_sketch: Name of the spine (path) sketch.
            transition: Transition mode. Options:
                - "Transformed" - Smooth transitions
                - "Right" - Sharp corners
                - "Round" - Rounded corners
            name: Pipe feature name. Auto-generated if None.
            doc_name: Document containing the sketches. Uses active document if None.

        Returns:
            Dictionary with created pipe information:
                - name: Pipe name
                - label: Pipe label
                - type_id: Object type
        """
        bridge = await get_bridge()

        transition_map = {
            "Transformed": 0,
            "Right": 1,
            "Round": 2,
        }

        if transition not in transition_map:
            raise ValueError(f"Invalid transition: {transition}")

        code = f"""
{BODY_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")

profile = doc.getObject({profile_sketch!r})
if profile is None:
    raise ValueError(f"Profile sketch not found: {profile_sketch!r}")

spine = doc.getObject({spine_sketch!r})
if spine is None:
    raise ValueError(f"Spine sketch not found: {spine_sketch!r}")

# Find the body containing the profile sketch
body = _find_body_containing_object(doc, profile)

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body")

# Wrap in transaction for undo support
doc.openTransaction("Subtractive Pipe")
try:
    pipe_name = {name!r} or "SubtractivePipe"
    pipe = body.newObject("PartDesign::SubtractivePipe", pipe_name)
    pipe.Profile = profile
    pipe.Spine = (spine, ["Edge1"])
    pipe.Transition = {transition_map[transition]}

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": pipe.Name,
        "label": pipe.Label,
        "type_id": pipe.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Subtractive pipe failed")

    # =========================================================================
    # Sketcher Geometry - Additional shapes
    # =========================================================================

    @mcp.tool()
    async def add_sketch_ellipse(
        sketch_name: str,
        center_x: float,
        center_y: float,
        major_radius: float,
        minor_radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add an ellipse to a sketch.

        Args:
            sketch_name: Name of the sketch to add ellipse to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            major_radius: Semi-major axis radius.
            minor_radius: Semi-minor axis radius.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Index of the added ellipse
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Ellipse")
try:
    import Part

    center = FreeCAD.Vector({center_x}, {center_y}, 0)
    ellipse = Part.Ellipse(center, {major_radius}, {minor_radius})
    idx = sketch.addGeometry(ellipse, False)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "geometry_index": idx,
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add sketch ellipse failed")

    @mcp.tool()
    async def add_sketch_polygon(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        sides: int = 6,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a regular polygon to a sketch.

        Args:
            sketch_name: Name of the sketch to add polygon to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            radius: Circumscribed circle radius.
            sides: Number of sides (3 for triangle, 6 for hexagon, etc.).
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_indices: Indices of the added polygon edges
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import math
import Part
import Sketcher

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Polygon")
try:
    center = FreeCAD.Vector({center_x}, {center_y}, 0)
    radius = {radius}
    sides = {sides}

    # Calculate vertices
    vertices = []
    for i in range(sides):
        angle = 2 * math.pi * i / sides - math.pi / 2  # Start from top
        x = center.x + radius * math.cos(angle)
        y = center.y + radius * math.sin(angle)
        vertices.append(FreeCAD.Vector(x, y, 0))

    # Add edges
    first_idx = sketch.GeometryCount
    for i in range(sides):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % sides]
        sketch.addGeometry(Part.LineSegment(p1, p2), False)

    # Add coincident constraints to close the polygon
    for i in range(sides):
        idx1 = first_idx + i
        idx2 = first_idx + ((i + 1) % sides)
        sketch.addConstraint(Sketcher.Constraint("Coincident", idx1, 2, idx2, 1))

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "geometry_indices": list(range(first_idx, sketch.GeometryCount)),
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add sketch polygon failed")

    @mcp.tool()
    async def add_sketch_slot(
        sketch_name: str,
        center1_x: float,
        center1_y: float,
        center2_x: float,
        center2_y: float,
        radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a slot (obround/stadium shape) to a sketch.

        A slot is two semicircles connected by parallel lines.

        Args:
            sketch_name: Name of the sketch to add slot to.
            center1_x: X coordinate of first arc center.
            center1_y: Y coordinate of first arc center.
            center2_x: X coordinate of second arc center.
            center2_y: Y coordinate of second arc center.
            radius: Radius of the semicircular ends.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_indices: Indices of the added slot geometry
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import math
import Part
import Sketcher

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Slot")
try:
    c1 = FreeCAD.Vector({center1_x}, {center1_y}, 0)
    c2 = FreeCAD.Vector({center2_x}, {center2_y}, 0)
    radius = {radius}

    # Calculate direction and perpendicular
    direction = c2 - c1
    length = direction.Length
    if length < 1e-6:
        raise ValueError("Centers must be different")

    direction.normalize()
    perp = FreeCAD.Vector(-direction.y, direction.x, 0)

    # Calculate the four corner points
    p1 = c1 + perp * radius
    p2 = c1 - perp * radius
    p3 = c2 - perp * radius
    p4 = c2 + perp * radius

    first_idx = sketch.GeometryCount

    # Add first arc (at c1)
    angle1 = math.atan2(perp.y, perp.x)
    arc1 = Part.ArcOfCircle(
        Part.Circle(c1, FreeCAD.Vector(0, 0, 1), radius),
        angle1,
        angle1 + math.pi
    )
    sketch.addGeometry(arc1, False)

    # Add line from p2 to p3
    sketch.addGeometry(Part.LineSegment(p2, p3), False)

    # Add second arc (at c2)
    arc2 = Part.ArcOfCircle(
        Part.Circle(c2, FreeCAD.Vector(0, 0, 1), radius),
        angle1 + math.pi,
        angle1 + 2 * math.pi
    )
    sketch.addGeometry(arc2, False)

    # Add line from p4 to p1
    sketch.addGeometry(Part.LineSegment(p4, p1), False)

    # Add coincident constraints to connect the geometry
    sketch.addConstraint(Sketcher.Constraint("Coincident", first_idx, 2, first_idx + 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", first_idx + 1, 2, first_idx + 2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", first_idx + 2, 2, first_idx + 3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", first_idx + 3, 2, first_idx, 1))

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "geometry_indices": list(range(first_idx, sketch.GeometryCount)),
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add sketch slot failed")

    @mcp.tool()
    async def add_sketch_bspline(
        sketch_name: str,
        points: list[list[float]],
        closed: bool = False,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a B-spline curve to a sketch.

        Args:
            sketch_name: Name of the sketch to add B-spline to.
            points: List of control points, each as [x, y].
            closed: Whether to close the spline. Defaults to False.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Index of the added B-spline
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import Part

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

points = {points!r}
if len(points) < 2:
    raise ValueError("Need at least 2 control points")

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch BSpline")
try:
    vectors = [FreeCAD.Vector(p[0], p[1], 0) for p in points]

    if {closed}:
        bspline = Part.BSplineCurve()
        bspline.interpolate(vectors, PeriodicFlag=True)
    else:
        bspline = Part.BSplineCurve()
        bspline.interpolate(vectors)

    idx = sketch.addGeometry(bspline, False)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "geometry_index": idx,
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add sketch B-spline failed")

    # =========================================================================
    # Sketcher Constraints
    # =========================================================================

    @mcp.tool()
    async def add_sketch_constraint(
        sketch_name: str,
        constraint_type: str,
        geometry1: int,
        point1: int = -1,
        geometry2: int = -2,
        point2: int = -1,
        value: float | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a constraint to a sketch.

        This is a general-purpose constraint tool. For common constraints,
        use the specific constraint tools (constrain_horizontal, etc.).

        Args:
            sketch_name: Name of the sketch.
            constraint_type: Type of constraint. Options:
                - Geometric: "Coincident", "Horizontal", "Vertical", "Parallel",
                  "Perpendicular", "Tangent", "Equal", "Symmetric", "Block"
                - Dimensional: "Distance", "DistanceX", "DistanceY", "Radius",
                  "Diameter", "Angle"
            geometry1: Index of first geometry element.
            point1: Point index on first geometry (1=start, 2=end, 3=center).
                    Use -1 for edge itself.
            geometry2: Index of second geometry element. Use -2 for external.
            point2: Point index on second geometry.
            value: Value for dimensional constraints (distance, angle, etc.).
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import Sketcher

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Untitled")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(
        f"Sketch not found: {sketch_name!r}",
        "Firstly you need to create sketch by tool `create_sketch`"
    )

# Wrap in transaction for undo support
doc.openTransaction("Add Sketch Constraint")
try:
    ctype = {constraint_type!r}
    g1, p1, g2, p2 = {geometry1}, {point1}, {geometry2}, {point2}
    value = {value!r}

    # Build constraint based on type and parameters
    if ctype in ["Horizontal", "Vertical", "Block"]:
        if p1 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, p1)
        else:
            constraint = Sketcher.Constraint(ctype, g1)
    elif ctype in ["Coincident", "Perpendicular", "Parallel", "Tangent", "Equal"]:
        if p1 >= 0 and p2 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2)
        else:
            constraint = Sketcher.Constraint(ctype, g1, g2)
    elif ctype == "Symmetric":
        # Symmetric requires geometry2 to be the symmetry line index
        # Points g1,p1 and g2,p2 are symmetric about line geometry2
        if g2 < 0:
            raise ValueError("Symmetric constraint requires geometry2 as the symmetry line index")
        constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, geometry2)
    elif ctype in ["Distance", "DistanceX", "DistanceY"]:
        if value is None:
            raise ValueError(f"{{ctype}} constraint requires a value")
        if g2 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, value)
        elif p1 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, p1, value)
        else:
            constraint = Sketcher.Constraint(ctype, g1, value)
    elif ctype in ["Radius", "Diameter"]:
        if value is None:
            raise ValueError(f"{{ctype}} constraint requires a value")
        constraint = Sketcher.Constraint(ctype, g1, value)
    elif ctype == "Angle":
        if value is None:
            raise ValueError("Angle constraint requires a value")
        if g2 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, g2, value)
        else:
            constraint = Sketcher.Constraint(ctype, g1, value)
    else:
        raise ValueError(f"Unknown constraint type: {{ctype}}")

    idx = sketch.addConstraint(constraint)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "constraint_index": idx,
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add constraint failed")

    @mcp.tool()
    async def constrain_horizontal(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain a line to be horizontal.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the line geometry.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "Horizontal", geometry_index, doc_name=doc_name
        )

    @mcp.tool()
    async def constrain_vertical(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain a line to be vertical.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the line geometry.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "Vertical", geometry_index, doc_name=doc_name
        )

    @mcp.tool()
    async def constrain_coincident(
        sketch_name: str,
        geometry1: int,
        point1: int,
        geometry2: int,
        point2: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain two points to be coincident (same location).

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first geometry element.
            point1: Point on first geometry (1=start, 2=end, 3=center).
            geometry2: Index of second geometry element.
            point2: Point on second geometry.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name,
            "Coincident",
            geometry1,
            point1,
            geometry2,
            point2,
            doc_name=doc_name,
        )

    @mcp.tool()
    async def constrain_parallel(
        sketch_name: str,
        geometry1: int,
        geometry2: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain two lines to be parallel.

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first line.
            geometry2: Index of second line.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "Parallel", geometry1, -1, geometry2, -1, doc_name=doc_name
        )

    @mcp.tool()
    async def constrain_perpendicular(
        sketch_name: str,
        geometry1: int,
        geometry2: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain two lines to be perpendicular.

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first line.
            geometry2: Index of second line.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name,
            "Perpendicular",
            geometry1,
            -1,
            geometry2,
            -1,
            doc_name=doc_name,
        )

    @mcp.tool()
    async def constrain_tangent(
        sketch_name: str,
        geometry1: int,
        geometry2: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain two curves to be tangent.

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first curve.
            geometry2: Index of second curve.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "Tangent", geometry1, -1, geometry2, -1, doc_name=doc_name
        )

    @mcp.tool()
    async def constrain_equal(
        sketch_name: str,
        geometry1: int,
        geometry2: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain two elements to have equal size (length or radius).

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first element.
            geometry2: Index of second element.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "Equal", geometry1, -1, geometry2, -1, doc_name=doc_name
        )

    @mcp.tool()
    async def constrain_distance(
        sketch_name: str,
        geometry1: int,
        distance: float,
        point1: int = -1,
        geometry2: int = -2,
        point2: int = -1,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a distance constraint.

        Can constrain:
        - Line length (geometry1 only)
        - Point to point distance (geometry1+point1, geometry2+point2)
        - Point to line distance (geometry1+point1, geometry2 as line)

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first geometry element.
            distance: The distance value.
            point1: Point on first geometry (1=start, 2=end). -1 for line length.
            geometry2: Index of second geometry element. -2 if not used.
            point2: Point on second geometry.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name,
            "Distance",
            geometry1,
            point1,
            geometry2,
            point2,
            distance,
            doc_name,
        )

    @mcp.tool()
    async def constrain_distance_x(
        sketch_name: str,
        geometry: int,
        point: int,
        distance: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain horizontal distance from origin or between points.

        Args:
            sketch_name: Name of the sketch.
            geometry: Index of geometry element.
            point: Point index (1=start, 2=end, 3=center).
            distance: The horizontal distance value.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        return await add_sketch_constraint(
            sketch_name, "DistanceX", geometry, point, -2, -1, distance, doc_name
        )

    @mcp.tool()
    async def constrain_distance_y(
        sketch_name: str,
        geometry: int,
        point: int,
        distance: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain vertical distance from origin or between points.

        Args:
            sketch_name: Name of the sketch.
            geometry: Index of geometry element.
            point: Point index (1=start, 2=end, 3=center).
            distance: The vertical distance value.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics        """
        return await add_sketch_constraint(
            sketch_name, "DistanceY", geometry, point, -2, -1, distance, doc_name
        )

    @mcp.tool()
    async def constrain_radius(
        sketch_name: str,
        geometry_index: int,
        radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain the radius of a circle or arc.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the circle/arc geometry.
            radius: The radius value.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics        """
        return await add_sketch_constraint(
            sketch_name, "Radius", geometry_index, -1, -2, -1, radius, doc_name
        )

    @mcp.tool()
    async def constrain_angle(
        sketch_name: str,
        geometry1: int,
        angle: float,
        geometry2: int = -2,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Constrain angle of a line or between two lines.

        Args:
            sketch_name: Name of the sketch.
            geometry1: Index of first line.
            angle: Angle in degrees.
            geometry2: Index of second line (-2 for angle from horizontal).
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics        """
        return await add_sketch_constraint(
            sketch_name, "Angle", geometry1, -1, geometry2, -1, angle, doc_name
        )

    @mcp.tool()
    async def constrain_fix(
        sketch_name: str,
        geometry_index: int,
        point_index: int = -1,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Fix (lock) a point or geometry in place.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the geometry element.
            point_index: Point to fix (1=start, 2=end, 3=center).
                        -1 to fix the entire element.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with constraint info:
                - name: Sketch name
                - constraint_index: Index of the added constraint
                - sketch_status: Solver, constraint, and profile diagnostics        """
        return await add_sketch_constraint(
            sketch_name, "Block", geometry_index, point_index, doc_name=doc_name
        )

    # =========================================================================
    # Sketcher Operations
    # =========================================================================

    @mcp.tool()
    async def add_external_geometry(
        sketch_name: str,
        object_name: str,
        element: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add external geometry reference to a sketch.

        External geometry allows referencing edges/faces from other
        objects for construction and constraints.

        Args:
            sketch_name: Name of the sketch.
            object_name: Name of the object to reference.
            element: Element to reference (e.g., "Edge1", "Face1").
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - external_geometry_count: Number of external geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Untitled")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(Sketch not found
        f"Sketch not found: {sketch_name!r}",
        "Firstly you need to create sketch by tool `create_sketch`"
    )

ref_obj = doc.getObject({object_name!r})
if ref_obj is None:
    raise ValueError(
        f"Object not found: {object_name!r}",
        "Firstly you need to create object by tool `create_object` or another object creation tool"
    )

# Wrap in transaction for undo support
doc.openTransaction("Add External Geometry")
try:
    sketch.addExternal({object_name!r}, {element!r})
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "external_geometry_count": len(sketch.ExternalGeometry),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add external geometry failed")

    @mcp.tool()
    async def delete_sketch_geometry(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete a geometry element from a sketch.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the geometry to delete.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - deleted_geometry_index: Index that was deleted
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Delete Sketch Geometry")
try:
    sketch.delGeometry({geometry_index})
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "deleted_geometry_index": {geometry_index},
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Delete sketch geometry failed")

    @mcp.tool()
    async def delete_sketch_constraint(
        sketch_name: str,
        constraint_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete a constraint from a sketch.

        Args:
            sketch_name: Name of the sketch.
            constraint_index: Index of the constraint to delete.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - deleted_constraint_index: Index that was deleted
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Delete Sketch Constraint")
try:
    sketch.delConstraint({constraint_index})
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "deleted_constraint_index": {constraint_index},
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Delete sketch constraint failed")

    @mcp.tool()
    async def get_sketch_info(
        sketch_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed information about a sketch.

        Args:
            sketch_name: Name of the sketch.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with sketch information:
                - name: Sketch name
                - sketch_status: Structured dict containing:
                    - geometry and constraint counts
                    - solver status, solve code, and remaining DoF
                    - closed/open profile state and open endpoints
                    - unconstrained geometry plus actionable hints
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

_result_ = {{
    "name": sketch.Name,
    "label": sketch.Label,
    "sketch_status": _analyze_sketch(sketch),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Get sketch info failed")

    @mcp.tool()
    async def toggle_construction(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Toggle construction mode for a sketch geometry.

        Construction geometry is used for reference but not included
        in the final sketch profile.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the geometry to toggle.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Compact edit result:
                - name: Sketch name
                - geometry_index: Modified geometry index
                - is_construction: New construction state
                - sketch_status: Solver, constraint, and profile diagnostics
        """
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Toggle Construction")
try:
    sketch.toggleConstruction({geometry_index})
    doc.recompute()
    doc.commitTransaction()

    # Query construction state from SketchObject, not the geometry wrapper.
    is_construction = bool(sketch.getConstruction({geometry_index}))

    _result_ = {{
        "name": sketch.Name,
        "geometry_index": {geometry_index},
        "is_construction": is_construction,
        "sketch_status": _analyze_sketch(sketch),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Toggle construction failed")
