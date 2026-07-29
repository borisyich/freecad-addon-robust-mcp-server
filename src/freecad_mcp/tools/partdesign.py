"""PartDesign tools for FreeCAD Robust MCP Server.

This module provides tools for the PartDesign workbench, enabling
parametric solid modeling operations like Pad, Pocket, Fillet, etc.

Based on learnings from contextform/freecad-mcp which has the most
comprehensive PartDesign coverage.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from freecad_mcp.tools._freecad_runtime_helpers import (
    BODY_RUNTIME_HELPERS,
    FEATURE_VALIDATION_RUNTIME_HELPERS,
    REVOLUTION_AXIS_RUNTIME_HELPERS,
    SKETCH_ANALYSIS_RUNTIME_HELPERS,
)


class SketchGeometryOperation(BaseModel):
    """One atomic geometry edit for :func:`edit_sketch_geometry`."""

    model_config = ConfigDict(extra="forbid")

    op: Literal[
        "add_rectangle",
        "add_circle",
        "add_line",
        "add_arc",
        "add_point",
        "add_ellipse",
        "add_polygon",
        "add_slot",
        "add_bspline",
        "add_external_geometry",
        "delete_geometry",
        "toggle_construction",
    ]
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    center_x: float | None = None
    center_y: float | None = None
    radius: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None
    start_angle: float | None = None
    end_angle: float | None = None
    major_radius: float | None = None
    minor_radius: float | None = None
    sides: int = 6
    center1_x: float | None = None
    center1_y: float | None = None
    center2_x: float | None = None
    center2_y: float | None = None
    points: list[list[float]] | None = None
    closed: bool = False
    construction: bool = False
    object_name: str | None = None
    element: str | None = None
    geometry_index: int | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "SketchGeometryOperation":
        """Reject incomplete or nonsensical operation payloads."""
        required_by_op = {
            "add_rectangle": ("x", "y", "width", "height"),
            "add_circle": ("center_x", "center_y", "radius"),
            "add_line": ("x1", "y1", "x2", "y2"),
            "add_arc": (
                "center_x",
                "center_y",
                "radius",
                "start_angle",
                "end_angle",
            ),
            "add_point": ("x", "y"),
            "add_ellipse": (
                "center_x",
                "center_y",
                "major_radius",
                "minor_radius",
            ),
            "add_polygon": ("center_x", "center_y", "radius"),
            "add_slot": (
                "center1_x",
                "center1_y",
                "center2_x",
                "center2_y",
                "radius",
            ),
            "add_bspline": ("points",),
            "add_external_geometry": ("object_name", "element"),
            "delete_geometry": ("geometry_index",),
            "toggle_construction": ("geometry_index",),
        }
        missing = [
            field
            for field in required_by_op[self.op]
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(f"{self.op} requires: {', '.join(missing)}")

        positive_fields = {
            "add_rectangle": ("width", "height"),
            "add_circle": ("radius",),
            "add_arc": ("radius",),
            "add_ellipse": ("major_radius", "minor_radius"),
            "add_polygon": ("radius",),
            "add_slot": ("radius",),
        }
        for field in positive_fields.get(self.op, ()):
            value = getattr(self, field)
            if value is not None and value <= 0:
                raise ValueError(f"{field} must be positive")

        if self.op == "add_polygon" and self.sides < 3:
            raise ValueError("add_polygon requires sides >= 3")
        if self.op == "add_bspline":
            points = self.points or []
            if len(points) < 2 or any(len(point) != 2 for point in points):
                raise ValueError("add_bspline requires at least two [x, y] points")
        if self.geometry_index is not None and self.geometry_index < 0:
            raise ValueError("geometry_index must be non-negative")
        return self


class SketchConstraintOperation(BaseModel):
    """One atomic constraint edit for :func:`edit_sketch_constraints`."""

    model_config = ConfigDict(extra="forbid")

    op: Literal[
        "add_constraint",
        "horizontal",
        "vertical",
        "coincident",
        "parallel",
        "perpendicular",
        "tangent",
        "equal",
        "distance",
        "distance_x",
        "distance_y",
        "radius",
        "angle",
        "fix",
        "delete_constraint",
    ]
    constraint_type: str | None = None
    geometry1: int | None = None
    point1: int = -1
    geometry2: int = -2
    point2: int = -1
    value: float | None = None
    constraint_index: int | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "SketchConstraintOperation":
        """Reject incomplete constraint operations before touching FreeCAD."""
        if self.op == "delete_constraint":
            if self.constraint_index is None or self.constraint_index < 0:
                raise ValueError(
                    "delete_constraint requires a non-negative constraint_index"
                )
            return self

        if self.geometry1 is None:
            raise ValueError(f"{self.op} requires geometry1")
        if self.op == "add_constraint" and not self.constraint_type:
            raise ValueError("add_constraint requires constraint_type")
        if self.op in {
            "coincident",
            "parallel",
            "perpendicular",
            "tangent",
            "equal",
        } and self.geometry2 < 0:
            raise ValueError(f"{self.op} requires geometry2")
        if self.op in {"distance", "distance_x", "distance_y", "radius", "angle"}:
            if self.value is None:
                raise ValueError(f"{self.op} requires value")
        return self


def register_partdesign_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register PartDesign-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    def _validation_payload(payload: Any, operation: str) -> dict[str, Any]:
        """Normalize bridge results without coupling to optional API fields.

        Current bridge and FastMCP versions may expose only the public evidence
        fields (``validated`` plus the volume delta). Older bridge versions also
        return diagnostic fields such as ``solid_count`` and volume snapshots.
        The strict geometric checks still run inside FreeCAD before ``validated``
        can become true; host-side validation must not reject a successful result
        merely because optional diagnostics were omitted during transport.
        """
        if isinstance(payload, Mapping):
            return dict(payload)

        model_dump = getattr(payload, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)

        raise ValueError(f"{operation} returned an invalid response payload")

    def _optional_numeric_field(
        payload: dict[str, Any], field: str, operation: str
    ) -> float | None:
        """Read an optional numeric validation field without inventing evidence."""
        if field not in payload or payload[field] is None:
            return None
        try:
            return float(payload[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{operation} returned non-numeric {field}: {payload!r}"
            ) from exc

    def _validate_optional_common_evidence(
        payload: dict[str, Any], operation: str
    ) -> None:
        """Validate diagnostics when the active API version includes them."""
        if payload.get("shape_valid") is False:
            raise ValueError(
                f"{operation} validation reported an invalid shape: {payload!r}"
            )

        if "solid_count" in payload and payload["solid_count"] is not None:
            try:
                solid_count = int(payload["solid_count"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{operation} returned non-numeric solid_count: {payload!r}"
                ) from exc
            if solid_count != 1:
                raise ValueError(
                    f"{operation} validation expected one solid: {payload!r}"
                )

    def require_additive_result(payload: Any, operation: str) -> dict[str, Any]:
        """Enforce the public host-side contract for additive feature tools."""
        normalized = _validation_payload(payload, operation)
        added_volume = _optional_numeric_field(
            normalized, "added_volume", operation
        )
        _validate_optional_common_evidence(normalized, operation)

        if normalized.get("validated") is not True or not (
            added_volume is not None and added_volume > 0.0
        ):
            raise ValueError(
                f"{operation} additive validation contract was not satisfied: "
                + repr(normalized)
            )

        base_volume = _optional_numeric_field(normalized, "base_volume", operation)
        result_volume = _optional_numeric_field(
            normalized, "result_volume", operation
        )
        if base_volume is not None and result_volume is not None:
            measured_delta = result_volume - base_volume
            tolerance = max(1e-7, abs(added_volume) * 1e-9)
            if abs(measured_delta - added_volume) > tolerance:
                raise ValueError(
                    f"{operation} returned inconsistent additive volume evidence: "
                    + repr(normalized)
                )
        return normalized

    def require_subtractive_result(payload: Any, operation: str) -> dict[str, Any]:
        """Enforce the public host-side contract for subtractive feature tools."""
        normalized = _validation_payload(payload, operation)
        removed_volume = _optional_numeric_field(
            normalized, "removed_volume", operation
        )
        _validate_optional_common_evidence(normalized, operation)

        if normalized.get("validated") is not True or not (
            removed_volume is not None and removed_volume > 0.0
        ):
            raise ValueError(
                f"{operation} subtractive validation contract was not satisfied: "
                + repr(normalized)
            )

        base_volume = _optional_numeric_field(normalized, "base_volume", operation)
        result_volume = _optional_numeric_field(
            normalized, "result_volume", operation
        )
        if base_volume is not None and result_volume is not None:
            measured_delta = base_volume - result_volume
            tolerance = max(1e-7, abs(removed_volume) * 1e-9)
            if abs(measured_delta - removed_volume) > tolerance:
                raise ValueError(
                    f"{operation} returned inconsistent subtractive volume evidence: "
                    + repr(normalized)
                )
        return normalized

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
    async def edit_sketch_geometry(
        sketch_name: str,
        operations: list[SketchGeometryOperation],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Apply geometry edits to one sketch in a single transaction.

        Supported operations are ``add_rectangle``, ``add_circle``, ``add_line``,
        ``add_arc``, ``add_point``, ``add_ellipse``, ``add_polygon``, ``add_slot``,
        ``add_bspline``, ``add_external_geometry``, ``delete_geometry``, and
        ``toggle_construction``. Operations are applied sequentially, so later
        operations may reference geometry created earlier in the same request.

        Args:
            sketch_name: Name of the sketch to edit.
            operations: Ordered geometry operations.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Batch result with one entry per operation and final sketch diagnostics.
        """
        if not operations:
            raise ValueError("operations must contain at least one geometry edit")
        normalized_operations = [
            (
                operation
                if isinstance(operation, SketchGeometryOperation)
                else SketchGeometryOperation.model_validate(operation)
            ).model_dump()
            for operation in operations
        ]
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import math
import Part
import Sketcher

operations = {normalized_operations!r}
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

operation_results = []
doc.openTransaction("Edit Sketch Geometry")
try:
    for operation in operations:
        op = operation["op"]

        if op == "add_rectangle":
            x = operation["x"]
            y = operation["y"]
            width = operation["width"]
            height = operation["height"]
            first_idx = sketch.GeometryCount
            sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y, 0), FreeCAD.Vector(x + width, y, 0)), False)
            sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x + width, y, 0), FreeCAD.Vector(x + width, y + height, 0)), False)
            sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x + width, y + height, 0), FreeCAD.Vector(x, y + height, 0)), False)
            sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y + height, 0), FreeCAD.Vector(x, y, 0)), False)
            for offset in range(4):
                next_offset = (offset + 1) % 4
                sketch.addConstraint(Sketcher.Constraint("Coincident", first_idx + offset, 2, first_idx + next_offset, 1))
            operation_results.append({{"op": op, "geometry_indices": list(range(first_idx, first_idx + 4))}})

        elif op == "add_circle":
            idx = sketch.addGeometry(
                Part.Circle(
                    FreeCAD.Vector(operation["center_x"], operation["center_y"], 0),
                    FreeCAD.Vector(0, 0, 1),
                    operation["radius"],
                ),
                False,
            )
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_line":
            idx = sketch.addGeometry(
                Part.LineSegment(
                    FreeCAD.Vector(operation["x1"], operation["y1"], 0),
                    FreeCAD.Vector(operation["x2"], operation["y2"], 0),
                ),
                bool(operation["construction"]),
            )
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_arc":
            circle = Part.Circle(
                FreeCAD.Vector(operation["center_x"], operation["center_y"], 0),
                FreeCAD.Vector(0, 0, 1),
                operation["radius"],
            )
            arc = Part.ArcOfCircle(
                circle,
                math.radians(operation["start_angle"]),
                math.radians(operation["end_angle"]),
            )
            idx = sketch.addGeometry(arc, False)
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_point":
            idx = sketch.addGeometry(
                Part.Point(FreeCAD.Vector(operation["x"], operation["y"], 0)),
                False,
            )
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_ellipse":
            ellipse = Part.Ellipse(
                FreeCAD.Vector(operation["center_x"], operation["center_y"], 0),
                operation["major_radius"],
                operation["minor_radius"],
            )
            idx = sketch.addGeometry(ellipse, False)
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_polygon":
            first_idx = sketch.GeometryCount
            center = FreeCAD.Vector(operation["center_x"], operation["center_y"], 0)
            sides = operation["sides"]
            vertices = []
            for index in range(sides):
                angle = 2 * math.pi * index / sides - math.pi / 2
                vertices.append(
                    FreeCAD.Vector(
                        center.x + operation["radius"] * math.cos(angle),
                        center.y + operation["radius"] * math.sin(angle),
                        0,
                    )
                )
            for index in range(sides):
                sketch.addGeometry(
                    Part.LineSegment(vertices[index], vertices[(index + 1) % sides]),
                    False,
                )
            for index in range(sides):
                sketch.addConstraint(
                    Sketcher.Constraint(
                        "Coincident",
                        first_idx + index,
                        2,
                        first_idx + ((index + 1) % sides),
                        1,
                    )
                )
            operation_results.append({{"op": op, "geometry_indices": list(range(first_idx, first_idx + sides))}})

        elif op == "add_slot":
            center1 = FreeCAD.Vector(operation["center1_x"], operation["center1_y"], 0)
            center2 = FreeCAD.Vector(operation["center2_x"], operation["center2_y"], 0)
            radius = operation["radius"]
            direction = center2 - center1
            if direction.Length < 1e-6:
                raise ValueError("add_slot centers must be different")
            direction.normalize()
            perpendicular = FreeCAD.Vector(-direction.y, direction.x, 0)
            point1 = center1 + perpendicular * radius
            point2 = center1 - perpendicular * radius
            point3 = center2 - perpendicular * radius
            point4 = center2 + perpendicular * radius
            angle = math.atan2(perpendicular.y, perpendicular.x)
            first_idx = sketch.GeometryCount
            sketch.addGeometry(
                Part.ArcOfCircle(
                    Part.Circle(center1, FreeCAD.Vector(0, 0, 1), radius),
                    angle,
                    angle + math.pi,
                ),
                False,
            )
            sketch.addGeometry(Part.LineSegment(point2, point3), False)
            sketch.addGeometry(
                Part.ArcOfCircle(
                    Part.Circle(center2, FreeCAD.Vector(0, 0, 1), radius),
                    angle + math.pi,
                    angle + 2 * math.pi,
                ),
                False,
            )
            sketch.addGeometry(Part.LineSegment(point4, point1), False)
            for offset in range(4):
                sketch.addConstraint(
                    Sketcher.Constraint(
                        "Coincident",
                        first_idx + offset,
                        2,
                        first_idx + ((offset + 1) % 4),
                        1,
                    )
                )
            operation_results.append({{"op": op, "geometry_indices": list(range(first_idx, first_idx + 4))}})

        elif op == "add_bspline":
            vectors = [FreeCAD.Vector(point[0], point[1], 0) for point in operation["points"]]
            bspline = Part.BSplineCurve()
            if operation["closed"]:
                bspline.interpolate(vectors, PeriodicFlag=True)
            else:
                bspline.interpolate(vectors)
            idx = sketch.addGeometry(bspline, False)
            operation_results.append({{"op": op, "geometry_index": idx}})

        elif op == "add_external_geometry":
            referenced_object = doc.getObject(operation["object_name"])
            if referenced_object is None:
                raise ValueError(f"Object not found: {{operation['object_name']}}")
            idx = sketch.addExternal(operation["object_name"], operation["element"])
            operation_results.append({{
                "op": op,
                "external_geometry_index": idx,
                "external_geometry_count": len(sketch.ExternalGeometry),
            }})

        elif op == "delete_geometry":
            sketch.delGeometry(operation["geometry_index"])
            operation_results.append({{
                "op": op,
                "deleted_geometry_index": operation["geometry_index"],
            }})

        elif op == "toggle_construction":
            geometry_index = operation["geometry_index"]
            sketch.toggleConstruction(geometry_index)
            operation_results.append({{
                "op": op,
                "geometry_index": geometry_index,
                "is_construction": bool(sketch.getConstruction(geometry_index)),
            }})

        else:
            raise ValueError(f"Unsupported sketch geometry operation: {{op}}")

    doc.recompute()
    sketch_status = _analyze_sketch(sketch)
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": sketch.Name,
    "operations_applied": len(operation_results),
    "operation_results": operation_results,
    "sketch_status": sketch_status,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Edit sketch geometry failed")

    @mcp.tool()
    async def edit_sketch_constraints(
        sketch_name: str,
        operations: list[SketchConstraintOperation],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Apply constraint edits to one sketch in a single transaction.

        Named operations cover the former constraint tools. ``add_constraint``
        retains the generic interface for less common Sketcher constraint types,
        while ``delete_constraint`` removes an existing constraint by index.

        Args:
            sketch_name: Name of the sketch to edit.
            operations: Ordered constraint operations.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Batch result with one entry per operation and final sketch diagnostics.
        """
        if not operations:
            raise ValueError("operations must contain at least one constraint edit")
        normalized_operations = [
            (
                operation
                if isinstance(operation, SketchConstraintOperation)
                else SketchConstraintOperation.model_validate(operation)
            ).model_dump()
            for operation in operations
        ]
        bridge = await get_bridge()

        code = f"""
{SKETCH_ANALYSIS_RUNTIME_HELPERS}

import Sketcher

operations = {normalized_operations!r}
doc = (
    FreeCAD.listDocuments().get({doc_name!r}) if {doc_name!r} is not None
    else FreeCAD.ActiveDocument
) or FreeCAD.newDocument({doc_name!r} or "Unnamed")
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

operation_results = []
doc.openTransaction("Edit Sketch Constraints")
try:
    for operation in operations:
        op = operation["op"]
        if op == "delete_constraint":
            sketch.delConstraint(operation["constraint_index"])
            operation_results.append({{
                "op": op,
                "deleted_constraint_index": operation["constraint_index"],
            }})
            continue

        constraint_types = {{
            "horizontal": "Horizontal",
            "vertical": "Vertical",
            "coincident": "Coincident",
            "parallel": "Parallel",
            "perpendicular": "Perpendicular",
            "tangent": "Tangent",
            "equal": "Equal",
            "distance": "Distance",
            "distance_x": "DistanceX",
            "distance_y": "DistanceY",
            "radius": "Radius",
            "angle": "Angle",
            "fix": "Block",
        }}
        constraint_type = (
            operation["constraint_type"]
            if op == "add_constraint"
            else constraint_types[op]
        )
        geometry1 = operation["geometry1"]
        point1 = operation["point1"]
        geometry2 = operation["geometry2"]
        point2 = operation["point2"]
        value = operation["value"]

        if constraint_type in ["Horizontal", "Vertical", "Block"]:
            constraint = (
                Sketcher.Constraint(constraint_type, geometry1, point1)
                if point1 >= 0
                else Sketcher.Constraint(constraint_type, geometry1)
            )
        elif constraint_type in ["Coincident", "Perpendicular", "Parallel", "Tangent", "Equal"]:
            constraint = (
                Sketcher.Constraint(constraint_type, geometry1, point1, geometry2, point2)
                if point1 >= 0 and point2 >= 0
                else Sketcher.Constraint(constraint_type, geometry1, geometry2)
            )
        elif constraint_type == "Symmetric":
            if geometry2 < 0:
                raise ValueError("Symmetric constraint requires geometry2")
            constraint = Sketcher.Constraint(
                constraint_type,
                geometry1,
                point1,
                geometry2,
                point2,
                geometry2,
            )
        elif constraint_type in ["Distance", "DistanceX", "DistanceY"]:
            if value is None:
                raise ValueError(f"{{constraint_type}} constraint requires a value")
            if geometry2 >= 0:
                constraint = Sketcher.Constraint(
                    constraint_type,
                    geometry1,
                    point1,
                    geometry2,
                    point2,
                    value,
                )
            elif point1 >= 0:
                constraint = Sketcher.Constraint(constraint_type, geometry1, point1, value)
            else:
                constraint = Sketcher.Constraint(constraint_type, geometry1, value)
        elif constraint_type in ["Radius", "Diameter"]:
            if value is None:
                raise ValueError(f"{{constraint_type}} constraint requires a value")
            constraint = Sketcher.Constraint(constraint_type, geometry1, value)
        elif constraint_type == "Angle":
            if value is None:
                raise ValueError("Angle constraint requires a value")
            constraint = (
                Sketcher.Constraint(constraint_type, geometry1, geometry2, value)
                if geometry2 >= 0
                else Sketcher.Constraint(constraint_type, geometry1, value)
            )
        else:
            raise ValueError(f"Unknown constraint type: {{constraint_type}}")

        constraint_index = sketch.addConstraint(constraint)
        operation_results.append({{
            "op": op,
            "constraint_type": constraint_type,
            "constraint_index": constraint_index,
        }})

    doc.recompute()
    sketch_status = _analyze_sketch(sketch)
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": sketch.Name,
    "operations_applied": len(operation_results),
    "operation_results": operation_results,
    "sketch_status": sketch_status,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Edit sketch constraints failed")


    @mcp.tool()
    async def pad_sketch(
        sketch_name: str,
        length: float,
        symmetric: bool = False,
        reversed: bool = False,
        direction: list[float] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Pad (extrusion) from a sketch.

        Args:
            sketch_name: Name of the sketch to pad.
            length: Pad length (extrusion distance).
            symmetric: Whether to extrude symmetrically. Defaults to False.
            reversed: Whether to reverse direction when ``direction`` is not supplied.
            direction: Optional desired world-space extrusion direction ``[x, y, z]``.
                The tool resolves ``Reversed`` from the sketch global normal and rejects
                directions perpendicular to the sketch. Prefer this for direction-sensitive
                features instead of guessing ``reversed``.
            name: Pad feature name. Auto-generated if None.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created pad information:
                - name: Pad name
                - label: Pad label
                - type_id: Object type
                - validated: Whether the additive result passed validation
                - added_volume: Effective volume added to the Body
                - effective_direction: Actual extrusion direction in world coordinates
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
    # Resolve the direction from the sketch global normal. Plane orientation can
    # differ between support types and FreeCAD builds, so callers may supply an
    # explicit world-space direction instead of guessing Reversed.
    sketch_normal_vec = sketch.getGlobalPlacement().Rotation.multVec(
        FreeCAD.Vector(0, 0, 1)
    )
    if sketch_normal_vec.Length <= 1e-12:
        raise ValueError("Could not resolve sketch global normal")
    sketch_normal_vec.normalize()
    requested_direction = {direction!r}
    resolved_reversed = bool({reversed})
    if requested_direction is not None:
        if len(requested_direction) != 3:
            raise ValueError("direction must contain exactly three numbers")
        desired_vec = FreeCAD.Vector(*[float(v) for v in requested_direction])
        if desired_vec.Length <= 1e-12:
            raise ValueError("direction must be a non-zero vector")
        desired_vec.normalize()
        alignment = sketch_normal_vec.dot(desired_vec)
        if abs(alignment) < 1.0 - 1e-3:
            raise ValueError(
                "direction must be parallel to the sketch normal; "
                f"sketch_normal=({{sketch_normal_vec.x:.3g}}, "
                f"{{sketch_normal_vec.y:.3g}}, {{sketch_normal_vec.z:.3g}}), "
                f"requested=({{desired_vec.x:.3g}}, {{desired_vec.y:.3g}}, "
                f"{{desired_vec.z:.3g}})"
            )
        resolved_reversed = alignment < 0
    # FreeCAD 1.0 uses Midplane instead of Symmetric. Direction is immaterial
    # for a midplane pad, but we still report the resolved normal consistently.
    if {symmetric}:
        pad.Midplane = True
    pad.Reversed = resolved_reversed
    effective_direction_vec = (
        sketch_normal_vec * -1.0 if resolved_reversed else sketch_normal_vec
    )

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
    "added_volume": validation["added_volume"],
    "effective_direction": [
        float(effective_direction_vec.x),
        float(effective_direction_vec.y),
        float(effective_direction_vec.z),
    ],
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
                - added_volume: Effective volume added to the Body
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
    "added_volume": validation["added_volume"],
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
        "Use edit_sketch_geometry with add_circle for each hole location; "
        "sketch points are not a reliable PartDesign::Hole profile in FreeCAD 1.0.x."
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
    "removed_volume": removed_volume,
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
            Dictionary with created cylindrical cut information:
                - name: Cylindrical cut name
                - label: Cylindrical cut label
                - type_id: Object type
                - validated: Check if the result has a valid shape
                - removed_volume: Removed volume of the body
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
    "removed_volume": validation["removed_volume"],
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
                - validated: Check if the result has a valid shape
                - added_volume: Effective volume added to the Body
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
    "added_volume": validation["added_volume"],
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
                - validated: Check if the result has a valid shape
                - added_volume: Effective volume added to the Body
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
    "added_volume": validation["added_volume"],
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
    # Sketcher inspection
    # =========================================================================

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

