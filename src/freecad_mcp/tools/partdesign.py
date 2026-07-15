"""PartDesign tools for FreeCAD Robust MCP Server.

This module provides tools for the PartDesign workbench, enabling
parametric solid modeling operations like Pad, Pocket, Fillet, etc.

Based on learnings from contextform/freecad-mcp which has the most
comprehensive PartDesign coverage.
"""

from collections.abc import Awaitable, Callable
from typing import Any


_ORIGIN_FEATURE_RESOLVER_CODE = r'''
def _resolve_body_origin_feature(body, canonical_name):
    """Resolve a Body origin feature without depending on document suffixes.

    FreeCAD makes DocumentObject.Name unique across the whole document.  As a
    result, the second Body receives names such as ``Z_Axis001`` and
    ``XY_Plane001`` even though they still represent that Body's canonical
    Z-axis and XY-plane.  Tool arguments use canonical names, so resolution
    must be scoped to ``body.Origin`` and accept a numeric uniqueness suffix.
    """
    origin = getattr(body, "Origin", None)
    if origin is None:
        raise ValueError(f"Body has no Origin: {getattr(body, 'Name', '<unknown>')}")

    features = list(getattr(origin, "OriginFeatures", []) or [])
    if not features:
        features = list(getattr(origin, "OutList", []) or [])

    suffixed_matches = []
    for feature in features:
        feature_name = getattr(feature, "Name", "")
        if feature_name == canonical_name:
            return feature
        if feature_name.startswith(canonical_name):
            suffix = feature_name[len(canonical_name):]
            if suffix.isdigit():
                suffixed_matches.append(feature)

    if len(suffixed_matches) == 1:
        return suffixed_matches[0]
    if len(suffixed_matches) > 1:
        names = [getattr(feature, "Name", "") for feature in suffixed_matches]
        raise ValueError(
            f"Ambiguous origin feature {canonical_name!r} in Body "
            f"{getattr(body, 'Name', '<unknown>')!r}: {names}"
        )

    available = [getattr(feature, "Name", "") for feature in features]
    raise ValueError(
        f"Origin feature not found: {canonical_name}. "
        f"Body={getattr(body, 'Name', '<unknown>')!r}; available={available}"
    )
'''


def register_partdesign_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register PartDesign-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

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
        """Create a new Sketch attached to a plane or body.

        Args:
            body_name: Name of PartDesign Body to attach to. Creates standalone if None.
            plane: Plane to attach sketch to. Options:
                - "XY_Plane" - Horizontal plane
                - "XZ_Plane" - Front vertical plane
                - "YZ_Plane" - Side vertical plane
                - Face name like "Face1" to attach to body face
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
{_ORIGIN_FEATURE_RESOLVER_CODE}

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
            # Attach to face
            if hasattr(sketch, "AttachmentSupport"):
                sketch.AttachmentSupport = [(body, plane)]
            else:
                sketch.Support = (body, [plane])
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
            Dictionary with geometry info:
                - constraint_count: Number of constraints in sketch
                - geometry_count: Number of geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
    "constraint_count": sketch.ConstraintCount,
    "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - geometry_index: Index of the added circle
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
    "geometry_count": sketch.GeometryCount,
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
        """
        bridge = await get_bridge()

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pad operation")

# Wrap in transaction for undo support
doc.openTransaction("Pad Sketch")
try:
    pad_name = {name!r} or "Pad"
    pad = body.newObject("PartDesign::Pad", pad_name)
    pad.Profile = sketch
    pad.Length = {length}
    # FreeCAD 1.0 uses Midplane instead of Symmetric
    if {symmetric}:
        pad.Midplane = True
    pad.Reversed = {reversed}

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": pad.Name,
    "label": pad.Label,
    "type_id": pad.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
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
        """
        bridge = await get_bridge()

        code = f"""
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pocket operation")

# Wrap in transaction for undo support
doc.openTransaction("Pocket Sketch")
try:
    pocket_name = {name!r} or "Pocket"
    pocket = body.newObject("PartDesign::Pocket", pocket_name)
    pocket.Profile = sketch
    pocket.Length = {length}
    pocket.Type = {type!r}

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": pocket.Name,
    "label": pocket.Label,
    "type_id": pocket.TypeId,
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
        """
        bridge = await get_bridge()

        code = f"""
{_ORIGIN_FEATURE_RESOLVER_CODE}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Revolution operation")

# Wrap in transaction for undo support
doc.openTransaction("Revolution Sketch")
try:
    rev_name = {name!r} or "Revolution"
    rev = body.newObject("PartDesign::Revolution", rev_name)
    rev.Profile = sketch
    rev.Angle = {angle}
    # FreeCAD 1.0 uses Midplane instead of Symmetric
    if {symmetric}:
        rev.Midplane = True
    rev.Reversed = {reversed}

    # Set axis reference
    axis_name = {axis!r}
    allowed_axes = {{"Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H"}}
    if axis_name not in allowed_axes:
        raise ValueError(
            f"Unsupported revolution axis: {{axis_name!r}}. "
            f"Expected one of {{sorted(allowed_axes)}}"
        )

    resolved_axis_name = None
    if axis_name.startswith("Base_"):
        axis_ref = axis_name.removeprefix("Base_")
        axis_obj = _resolve_body_origin_feature(body, f"{{axis_ref}}_Axis")
        resolved_axis_name = axis_obj.Name

        # Validate axis is not perpendicular to the sketch plane
        try:
            sketch_rotation = sketch.getGlobalPlacement().Rotation
        except Exception:
            sketch_rotation = sketch.Placement.Rotation
        try:
            body_rotation = body.getGlobalPlacement().Rotation
        except Exception:
            body_rotation = body.Placement.Rotation

        sketch_normal = sketch_rotation.multVec(FreeCAD.Vector(0, 0, 1))
        axis_direction_map = {{
            "X": FreeCAD.Vector(1, 0, 0),
            "Y": FreeCAD.Vector(0, 1, 0),
            "Z": FreeCAD.Vector(0, 0, 1),
        }}
        axis_dir = body_rotation.multVec(axis_direction_map[axis_ref])
        dot = abs(sketch_normal.dot(axis_dir))
        if dot > 0.9999:
            raise ValueError(
                f"Axis '{{axis_name}}' is perpendicular to the sketch plane. "
                f"Revolution axis must lie in (be parallel to) the sketch plane. "
                f"For a sketch on XY plane, use Base_X or Base_Y (not Base_Z). "
                f"For a sketch on XZ plane, use Base_X or Base_Z (not Base_Y). "
                f"For a sketch on YZ plane, use Base_Y or Base_Z (not Base_X)."
            )

        rev.ReferenceAxis = (axis_obj, [""])
    else:
        if axis_name == "Sketch_V":
            rev.ReferenceAxis = (sketch, ["V_Axis"])
            resolved_axis_name = "V_Axis"
        else:
            rev.ReferenceAxis = (sketch, ["H_Axis"])
            resolved_axis_name = "H_Axis"

    doc.recompute()

    # Post-validation: check if the result has a valid shape
    # FreeCAD loggs errors to console but does not raise Python exceptions on recompute
    if not hasattr(rev, "Shape") or rev.Shape.isNull() or not rev.Shape.isValid():
        # Collect errors from FreeCAD console
        import PySide
        _errors = []
        if hasattr(FreeCAD, "Console") and hasattr(FreeCAD.Console, "GetError"):
            _err_text = FreeCAD.Console.GetError()
            if _err_text:
                _errors.append(_err_text.strip())
        if not _errors:
            # Fallback: check for common error patterns in log
            _errors.append(
                "Revolution result has invalid shape. Check FreeCAD console for details. "
                "Common causes: axis perpendicular to sketch plane, "
                "wire not closed, or profile crossing the axis."
            )
        raise ValueError("Revolution failed: " + " ".join(_errors))

    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": rev.Name,
    "label": rev.Label,
    "type_id": rev.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
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
        """
        bridge = await get_bridge()

        code = f"""
{_ORIGIN_FEATURE_RESOLVER_CODE}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Groove operation")

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

    # Set axis reference
    axis_name = {axis!r}
    allowed_axes = {{"Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H"}}
    if axis_name not in allowed_axes:
        raise ValueError(
            f"Unsupported groove axis: {{axis_name!r}}. "
            f"Expected one of {{sorted(allowed_axes)}}"
        )

    resolved_axis_name = None
    if axis_name.startswith("Base_"):
        axis_ref = axis_name.removeprefix("Base_")
        axis_obj = _resolve_body_origin_feature(body, f"{{axis_ref}}_Axis")
        resolved_axis_name = axis_obj.Name

        # Validate axis is not perpendicular to the sketch plane
        try:
            sketch_rotation = sketch.getGlobalPlacement().Rotation
        except Exception:
            sketch_rotation = sketch.Placement.Rotation
        try:
            body_rotation = body.getGlobalPlacement().Rotation
        except Exception:
            body_rotation = body.Placement.Rotation

        sketch_normal = sketch_rotation.multVec(FreeCAD.Vector(0, 0, 1))
        axis_direction_map = {{
            "X": FreeCAD.Vector(1, 0, 0),
            "Y": FreeCAD.Vector(0, 1, 0),
            "Z": FreeCAD.Vector(0, 0, 1),
        }}
        axis_dir = body_rotation.multVec(axis_direction_map[axis_ref])
        dot = abs(sketch_normal.dot(axis_dir))
        if dot > 0.9999:
            raise ValueError(
                f"Axis '{{axis_name}}' is perpendicular to the sketch plane. "
                f"Groove axis must lie in (be parallel to) the sketch plane. "
                f"For a sketch on XY plane, use Base_X or Base_Y (not Base_Z). "
                f"For a sketch on XZ plane, use Base_X or Base_Z (not Base_Y). "
                f"For a sketch on YZ plane, use Base_Y or Base_Z (not Base_X)."
            )

        groove.ReferenceAxis = (axis_obj, [""])
    else:
        if axis_name == "Sketch_V":
            groove.ReferenceAxis = (sketch, ["V_Axis"])
            resolved_axis_name = "V_Axis"
        else:
            groove.ReferenceAxis = (sketch, ["H_Axis"])
            resolved_axis_name = "H_Axis"

    doc.recompute()

    # Post-validation: check if the result has a valid shape
    # FreeCAD loggs errors to console but does not raise Python exceptions on recompute
    if not hasattr(groove, "Shape") or groove.Shape.isNull() or not groove.Shape.isValid():
        import PySide
        _errors = []
        if hasattr(FreeCAD, "Console") and hasattr(FreeCAD.Console, "GetError"):
            _err_text = FreeCAD.Console.GetError()
            if _err_text:
                _errors.append(_err_text.strip())
        if not _errors:
            _errors.append(
                "Groove result has invalid shape. Check FreeCAD console for details. "
                "Common causes: axis perpendicular to sketch plane, "
                "wire not closed, or profile crossing the axis."
            )
        raise ValueError("Groove failed: " + " ".join(_errors))

    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": groove.Name,
    "label": groove.Label,
    "type_id": groove.TypeId,
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
        reversed: bool | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a validated Hole feature from a sketch containing circles.

        The sketch must contain one or more non-construction circles. One sketch
        may be consumed by only one PartDesign feature. The operation succeeds
        only when FreeCAD produces one valid solid and the body's volume is
        measurably reduced. If the default direction does not cut the body, the
        opposite direction is tried automatically unless ``reversed`` is set.

        Args:
            sketch_name: Name of an unused sketch with hole-location circles.
            diameter: Hole diameter for non-threaded holes. Defaults to 6.0.
            depth: Hole depth for ``Dimension`` holes. Defaults to 10.0.
            hole_type: Depth type: ``Dimension`` or ``ThroughAll``.
            threaded: Whether to create a threaded hole definition.
            thread_type: Thread profile: ``ISO``, ``ISO_FINE``, ``UNC``, or ``UNF``.
            thread_size: Thread designation, for example ``M6`` or ``1/4``.
            reversed: Explicit cutting direction. If None, both directions are
                tried and the first valid subtractive result is retained.
            name: Hole feature name. Auto-generated if None.
            doc_name: Existing document containing the sketch. Uses the active
                document if None. A missing document is never created silently.

        Returns:
            Dictionary with created groove information:
                - name: Hole name
                - label: Hole label
                - type_id: Object type
                - validated: Bool result of valid check of the body after creating hole
                - removed_volume: Removed volume of the body
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

        bridge = await get_bridge()

        code = f"""
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
bodies = []
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body" and hasattr(obj, "Group"):
        if sketch in obj.Group:
            bodies.append(obj)
if len(bodies) != 1:
    raise ValueError(
        f"Sketch must belong to exactly one PartDesign Body; found {{len(bodies)}}"
    )
body = bodies[0]

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
group = list(body.Group)
try:
    sketch_index = group.index(sketch)
except ValueError as exc:
    raise ValueError("Sketch is not present in its Body history") from exc

base_feature = None
for candidate in reversed(group[:sketch_index]):
    if not hasattr(candidate, "Shape"):
        continue
    try:
        candidate_shape = candidate.Shape
        if (
            not candidate_shape.isNull()
            and candidate_shape.isValid()
            and len(candidate_shape.Solids) == 1
        ):
            base_feature = candidate
            break
    except Exception:
        pass
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


def _status_strings(feature):
    try:
        return [str(item) for item in feature.getStatusString()]
    except Exception:
        try:
            return [str(item) for item in feature.State]
        except Exception:
            return []


def _check_result(feature):
    reasons = []
    shape = getattr(feature, "Shape", None)
    result_volume = None
    solid_count = 0
    removed_solid_count = 0
    if shape is None or shape.isNull():
        reasons.append("result shape is null")
    else:
        if not shape.isValid():
            reasons.append("result shape is invalid")
        try:
            solid_count = len(shape.Solids)
        except Exception:
            solid_count = 0
        if solid_count != 1:
            reasons.append(f"expected one solid, got {{solid_count}}")
        result_volume = float(shape.Volume)
        removed_volume = base_volume - result_volume
        if removed_volume <= volume_tolerance:
            reasons.append(
                f"body volume did not decrease: base={{base_volume:.9g}}, "
                f"result={{result_volume:.9g}}"
            )
        else:
            try:
                removed_shape = base_shape.cut(shape)
                removed_solid_count = len(removed_shape.Solids)
                if removed_solid_count != profile_circle_count:
                    reasons.append(
                        f"expected {{profile_circle_count}} independent hole cut(s), "
                        f"got {{removed_solid_count}}. A circle may be outside the "
                        "solid or multiple hole cuts may overlap."
                    )
            except Exception as exc:
                reasons.append(f"could not validate removed material: {{exc}}")
    if body.Tip is not feature:
        reasons.append(
            f"Body Tip is {{getattr(body.Tip, 'Name', None)!r}}, not {{feature.Name!r}}"
        )
    status = _status_strings(feature)
    error_status = [
        item for item in status
        if "error" in item.lower() or "invalid" in item.lower()
    ]
    if error_status:
        reasons.append("feature status: " + ", ".join(error_status))
    return (
        not reasons, reasons, result_volume, solid_count,
        removed_solid_count, status
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
        (
            ok, reasons, result_volume, solid_count,
            removed_solid_count, status
        ) = _check_result(hole)
        attempts.append({{
            "reversed": bool(direction),
            "ok": ok,
            "reasons": reasons,
            "status": status,
        }})
        if ok:
            selected = {{
                "reversed": bool(direction),
                "result_volume": result_volume,
                "solid_count": solid_count,
                "removed_solid_count": removed_solid_count,
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
            "Check that every circle center lies over the existing solid and that "
            "the sketch plane intersects the body. " + details
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
    "removed_volume": removed_volume
}}
"""
        result = await bridge.execute_python(code)
        if not result.success:
            raise ValueError(result.error_traceback or "Hole creation failed")

        payload = result.result
        if not isinstance(payload, dict):
            raise ValueError("Hole validation returned an invalid response payload")
        if (
            payload.get("validated") is not True
            or float(payload.get("removed_volume", 0.0)) <= 0.0
        ):
            raise ValueError(
                "Hole validation contract was not satisfied: " + repr(payload)
            )
        return payload

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None 
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

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
            Dictionary with geometry info:
                - geometry_index: Index of the added line
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - geometry_index: Index of the added arc
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - geometry_index: Index of the added point
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
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
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketches[0] in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body for Loft operation")

# Wrap in transaction for undo support
doc.openTransaction("Loft Sketches")
try:
    loft_name = {name!r} or "Loft"
    loft = body.newObject("PartDesign::AdditiveLoft", loft_name)
    loft.Profile = sketches[0]
    loft.Sections = sketches[1:]
    loft.Ruled = {ruled}
    loft.Closed = {closed}

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": loft.Name,
    "label": loft.Label,
    "type_id": loft.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
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
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and profile in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body for Sweep operation")

# Wrap in transaction for undo support
doc.openTransaction("Sweep Sketch")
try:
    sweep_name = {name!r} or "Sweep"
    sweep = body.newObject("PartDesign::AdditivePipe", sweep_name)
    sweep.Profile = profile
    sweep.Spine = (spine, ["Edge1"])
    sweep.Transition = {transition_map[transition]}

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": sweep.Name,
    "label": sweep.Label,
    "type_id": sweep.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
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
{_ORIGIN_FEATURE_RESOLVER_CODE}

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

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
{_ORIGIN_FEATURE_RESOLVER_CODE}

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
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketches[0] in obj.Group:
            body = obj
            break

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
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and profile in obj.Group:
            body = obj
            break

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
            Dictionary with geometry info:
                - geometry_index: Index of the added ellipse
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
        "geometry_index": idx,
        "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - first_line_index: Index of the first line
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
        "first_line_index": first_idx,
        "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - first_geometry_index: Index of first geometry element
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
        "first_geometry_index": first_idx,
        "geometry_count": sketch.GeometryCount,
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
            Dictionary with geometry info:
                - geometry_index: Index of the added B-spline
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
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
        "geometry_index": idx,
        "geometry_count": sketch.GeometryCount,
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
            Dictionary with constraint info:
                - constraint_index: Index of the added constraint
                - constraint_count: Total constraint count
        """
        bridge = await get_bridge()

        code = f"""
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
        "constraint_index": idx,
        "constraint_count": sketch.ConstraintCount,
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
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
                - constraint_index: Index of the added constraint
        """
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
                - constraint_index: Index of the added constraint
        """
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
                - constraint_index: Index of the added constraint
        """
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
                - constraint_index: Index of the added constraint
        """
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
            Dictionary with result:
                - success: Whether the deletion succeeded
                - geometry_count: Remaining geometry count
        """
        bridge = await get_bridge()

        code = f"""
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
        "success": True,
        "geometry_count": sketch.GeometryCount,
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
            Dictionary with result:
                - success: Whether the deletion succeeded
                - constraint_count: Remaining constraint count
        """
        bridge = await get_bridge()

        code = f"""
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
        "success": True,
        "constraint_count": sketch.ConstraintCount,
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
                - geometry_count: Number of geometry elements
                - constraint_count: Number of constraints
                - external_geometry_count: Number of external geometry references
                - fully_constrained: Whether sketch is fully constrained
                - dof: Degrees of freedom remaining
        """
        bridge = await get_bridge()

        code = f"""
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
    "geometry_count": sketch.GeometryCount,
    "constraint_count": sketch.ConstraintCount,
    "external_geometry_count": len(sketch.ExternalGeometry),
    "fully_constrained": sketch.FullyConstrained if hasattr(sketch, "FullyConstrained") else None,
    "dof": sketch.solve() if hasattr(sketch, "solve") else None,
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
            Dictionary with result:
                - success: Whether the operation succeeded
                - is_construction: New construction state
        """
        bridge = await get_bridge()

        code = f"""
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

    # Check new state
    geo = sketch.Geometry[{geometry_index}]
    is_construction = geo.Construction if hasattr(geo, "Construction") else False

    _result_ = {{
        "success": True,
        "is_construction": is_construction,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Toggle construction failed")
