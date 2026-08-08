"""Tolerance-aware geometric measurement tools backed by FreeCAD/OCCT."""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class GeometryReference(BaseModel):
    """An object or one of its stable-in-response topological references."""

    model_config = ConfigDict(extra="forbid")

    object_name: str = Field(min_length=1)
    subshape: str | None = Field(
        default=None,
        pattern=r"^(Face|Edge|Vertex)[1-9]\d*$",
        description=(
            "Optional FaceN, EdgeN, or VertexN returned by select_subshapes. "
            "Omit to measure the complete object Shape."
        ),
    )


class _MeasurementBase(BaseModel):
    """Strict base for the discriminated measurement request."""

    model_config = ConfigDict(extra="forbid")


class BoundingBoxMeasurement(_MeasurementBase):
    """Axis-aligned bounding-box request."""

    kind: Literal["bbox"]
    object_name: str = Field(min_length=1)
    mode: Literal["fast", "optimal"] = "fast"
    coordinate_system: Literal["world", "local"] = "world"
    use_triangulation: bool = False
    use_shape_tolerance: bool = False
    report_gap: bool = True


class DistanceMeasurement(_MeasurementBase):
    """Minimum distance request for two geometry references."""

    kind: Literal["distance"]
    first: GeometryReference
    second: GeometryReference
    tolerance_mm: float = Field(default=1e-7, ge=0, allow_inf_nan=False)


class AngleMeasurement(_MeasurementBase):
    """Angle request for two directional geometry references."""

    kind: Literal["angle"]
    first: GeometryReference
    second: GeometryReference
    orientation: Literal["undirected", "directed"] = "undirected"


class RadiusMeasurement(_MeasurementBase):
    """Radius and diameter request for constant-radius geometry."""

    kind: Literal["radius"]
    reference: GeometryReference
    radius_kind: Literal["auto", "primary", "major", "minor"] = "auto"


class WallThicknessMeasurement(_MeasurementBase):
    """Wall-thickness request for two opposing faces."""

    kind: Literal["wall_thickness"]
    first_face: GeometryReference
    second_face: GeometryReference
    tolerance_mm: float = Field(default=1e-7, ge=0, allow_inf_nan=False)
    strict: bool = True


class ClearanceMeasurement(_MeasurementBase):
    """Required-clearance check for two geometry references."""

    kind: Literal["clearance"]
    first: GeometryReference
    second: GeometryReference
    required_clearance_mm: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    tolerance_mm: float = Field(default=1e-7, ge=0, allow_inf_nan=False)


class MinimumGapMeasurement(_MeasurementBase):
    """Smallest pairwise gap request for a bounded reference set."""

    kind: Literal["minimum_gap"]
    references: Annotated[list[GeometryReference], Field(min_length=2, max_length=30)]
    tolerance_mm: float = Field(default=1e-7, ge=0, allow_inf_nan=False)


FinitePoint = Annotated[
    list[Annotated[float, Field(allow_inf_nan=False)]],
    Field(min_length=3, max_length=3),
]


class PointToFaceMeasurement(_MeasurementBase):
    """Distance request from a point or vertex to a face."""

    kind: Literal["point_to_face"]
    face: GeometryReference
    point: FinitePoint | None = None
    vertex: GeometryReference | None = None
    tolerance_mm: float = Field(default=1e-7, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _require_one_source(self) -> PointToFaceMeasurement:
        if (self.point is None) == (self.vertex is None):
            raise ValueError("Supply exactly one of point or vertex")
        return self


MeasurementRequest = Annotated[
    BoundingBoxMeasurement
    | DistanceMeasurement
    | AngleMeasurement
    | RadiusMeasurement
    | WallThicknessMeasurement
    | ClearanceMeasurement
    | MinimumGapMeasurement
    | PointToFaceMeasurement,
    Field(discriminator="kind"),
]

_MEASUREMENT_ADAPTER: TypeAdapter[MeasurementRequest] = TypeAdapter(MeasurementRequest)


def _measurement_request(value: MeasurementRequest | dict[str, Any]) -> MeasurementRequest:
    """Normalize direct Python calls as well as FastMCP-validated calls."""
    if isinstance(value, _MeasurementBase):
        return value
    return _MEASUREMENT_ADAPTER.validate_python(value)


def _reference_payload(value: GeometryReference) -> dict[str, Any]:
    return value.model_dump(exclude_none=True)


MEASUREMENT_RUNTIME = dedent(
    r"""
    import math
    import FreeCAD
    import Part


    def _m_finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("OCCT returned a non-finite measurement")
        return number


    def _m_vector(value):
        return {
            "x": _m_finite(value.x),
            "y": _m_finite(value.y),
            "z": _m_finite(value.z),
        }


    def _m_serialize(value):
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return _m_finite(value)
        if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
            return _m_vector(value)
        if isinstance(value, (list, tuple)):
            return [_m_serialize(item) for item in value]
        return str(value)


    def _m_get_object(doc, object_name):
        obj = doc.getObject(object_name)
        if obj is None:
            raise ValueError(f"Object not found: {object_name!r}")
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull():
            raise ValueError(f"Object {object_name!r} has no usable Shape")
        return obj


    def _m_resolve(doc, spec, expected_kind=None):
        obj = _m_get_object(doc, spec["object_name"])
        complete_shape = obj.Shape
        reference = spec.get("subshape")
        if reference is None:
            if expected_kind is not None:
                raise ValueError(
                    f"This measurement requires an explicit {expected_kind}N reference"
                )
            return {
                "object": obj,
                "shape": complete_shape,
                "object_name": obj.Name,
                "subshape": None,
                "kind": str(getattr(complete_shape, "ShapeType", "Shape")),
            }

        kind = "".join(character for character in reference if character.isalpha())
        index = int(reference[len(kind):])
        if expected_kind is not None and kind != expected_kind:
            raise ValueError(
                f"Expected {expected_kind}N reference, received {reference!r}"
            )
        collection_name = {"Face": "Faces", "Edge": "Edges", "Vertex": "Vertexes"}[kind]
        values = list(getattr(complete_shape, collection_name, []) or [])
        if index < 1 or index > len(values):
            raise ValueError(
                f"{reference!r} is out of range for {obj.Name!r}; "
                f"available {kind} count is {len(values)}"
            )
        return {
            "object": obj,
            "shape": values[index - 1],
            "object_name": obj.Name,
            "subshape": reference,
            "kind": kind,
        }


    def _m_reference_value(resolved):
        return {
            "object_name": resolved["object_name"],
            "subshape": resolved["subshape"],
            "kind": resolved["kind"],
        }


    def _m_force_recompute(doc, object_names, enabled):
        touched = []
        if enabled:
            for object_name in dict.fromkeys(object_names):
                obj = _m_get_object(doc, object_name)
                obj.touch()
                touched.append(obj.Name)
            recompute_result = doc.recompute()
        else:
            recompute_result = None
        return {
            "forced": bool(enabled),
            "touched_objects": touched,
            "recompute_result": _m_serialize(recompute_result),
        }


    def _m_bbox_value(bound_box):
        minimum = {
            "x": _m_finite(bound_box.XMin),
            "y": _m_finite(bound_box.YMin),
            "z": _m_finite(bound_box.ZMin),
        }
        maximum = {
            "x": _m_finite(bound_box.XMax),
            "y": _m_finite(bound_box.YMax),
            "z": _m_finite(bound_box.ZMax),
        }
        return {
            "min": minimum,
            "max": maximum,
            "size": {
                axis: maximum[axis] - minimum[axis] for axis in ("x", "y", "z")
            },
        }


    def _m_local_shape(obj):
        shape = obj.Shape.copy()
        placement = None
        try:
            placement = obj.getGlobalPlacement()
        except Exception:
            placement = getattr(obj, "Placement", None)
        if placement is None:
            raise ValueError(f"Object {obj.Name!r} has no usable Placement")
        shape.Placement = placement.inverse().multiply(shape.Placement)
        return shape, {
            "method": "inverse_global_placement",
            "global_position": _m_vector(placement.Base),
        }


    def _m_tolerance_report(shape):
        labels = ((0, "vertex"), (1, "edge"), (2, "face"))
        values = {}
        for mode, label in labels:
            try:
                values[label] = _m_finite(shape.getTolerance(mode))
            except Exception:
                values[label] = None
        finite_values = [value for value in values.values() if value is not None]
        return {
            "maximum_by_topology_mm": values,
            "maximum_mm": max(finite_values) if finite_values else None,
        }


    def _m_bbox(
        doc,
        object_name,
        mode,
        coordinate_system,
        use_triangulation,
        use_shape_tolerance,
        report_gap,
        recompute_evidence,
    ):
        obj = _m_get_object(doc, object_name)
        if coordinate_system == "local":
            shape, transform = _m_local_shape(obj)
        else:
            shape = obj.Shape
            transform = {"method": "document_world_shape"}

        fast_box = shape.BoundBox
        optimal_box = (
            shape.optimalBoundingBox(
                bool(use_triangulation), bool(use_shape_tolerance)
            )
            if mode == "optimal" or report_gap
            else None
        )
        selected_box = fast_box if mode == "fast" else optimal_box
        selected = _m_bbox_value(selected_box)
        fast = _m_bbox_value(fast_box)
        optimal = _m_bbox_value(optimal_box) if optimal_box is not None else None
        if optimal is not None:
            per_axis = {}
            for axis in ("x", "y", "z"):
                per_axis[axis] = {
                    "lower_expansion_mm": optimal["min"][axis] - fast["min"][axis],
                    "upper_expansion_mm": fast["max"][axis] - optimal["max"][axis],
                    "size_excess_mm": fast["size"][axis] - optimal["size"][axis],
                }
            maximum_expansion = max(
                abs(value)
                for axis_value in per_axis.values()
                for value in axis_value.values()
            )
            gap_report = {
                "reported": True,
                "basis": "fast minus optimal bounds using the requested OCCT options",
                "per_axis": per_axis,
                "maximum_absolute_difference_mm": maximum_expansion,
                "bound_box_gap_property_available": False,
            }
        else:
            gap_report = {
                "reported": False,
                "reason": "report_gap=False kept fast mode on the cached BoundBox path",
                "bound_box_gap_property_available": False,
            }
        return {
            "measurement": "bounding_box",
            "object_name": obj.Name,
            "mode": mode,
            "algorithm": (
                "TopoShape.BoundBox (OCCT BRepBndLib::Add, cached/fast)"
                if mode == "fast"
                else "TopoShape.optimalBoundingBox (OCCT BRepBndLib::AddOptimal)"
            ),
            "coordinate_system": coordinate_system,
            "coordinate_transform": transform,
            "bounds_mm": selected,
            "occt_options": {
                "use_triangulation": bool(use_triangulation),
                "use_shape_tolerance": bool(use_shape_tolerance),
            },
            "gap_report": gap_report,
            "tolerance_report": _m_tolerance_report(shape),
            "recompute": recompute_evidence,
        }


    def _m_distance(doc, first_spec, second_spec, tolerance_mm, max_solutions=8):
        first = _m_resolve(doc, first_spec)
        second = _m_resolve(doc, second_spec)
        value, point_pairs, support_info = first["shape"].distToShape(second["shape"])
        value = _m_finite(value)
        solutions = []
        for index, pair in enumerate(point_pairs[:max_solutions]):
            solutions.append(
                {
                    "point_on_first": _m_vector(pair[0]),
                    "point_on_second": _m_vector(pair[1]),
                    "support": (
                        _m_serialize(support_info[index])
                        if index < len(support_info)
                        else None
                    ),
                }
            )
        return {
            "first": _m_reference_value(first),
            "second": _m_reference_value(second),
            "distance_mm": value,
            "within_tolerance": value <= tolerance_mm,
            "tolerance_mm": tolerance_mm,
            "solution_count": len(point_pairs),
            "solutions": solutions,
            "solutions_truncated": len(point_pairs) > len(solutions),
            "method": "TopoShape.distToShape / OCCT BRepExtrema_DistShapeShape",
            "_first_resolved": first,
            "_second_resolved": second,
        }


    def _m_public_distance(result):
        return {key: value for key, value in result.items() if not key.startswith("_")}


    def _m_interference(distance_result, tolerance_mm):
        first = distance_result["_first_resolved"]
        second = distance_result["_second_resolved"]
        if first["subshape"] is not None or second["subshape"] is not None:
            return {
                "checked": False,
                "volume_mm3": None,
                "reason": "interference volume is evaluated only for complete object Shapes",
            }
        if distance_result["distance_mm"] > tolerance_mm:
            return {"checked": False, "volume_mm3": 0.0, "reason": "shapes are separated"}
        common = first["shape"].common(second["shape"])
        volume = _m_finite(getattr(common, "Volume", 0.0) or 0.0)
        return {
            "checked": True,
            "volume_mm3": volume,
            "interfering": volume > max(tolerance_mm ** 3, 1e-12),
            "method": "OCCT boolean common",
        }


    def _m_direction(resolved):
        shape = resolved["shape"]
        kind = resolved["kind"]
        geometry = None
        source = None
        origin = None
        if kind == "Edge":
            geometry = getattr(shape, "Curve", None)
            for attribute in ("Direction", "Axis"):
                vector = getattr(geometry, attribute, None)
                if vector is not None:
                    source = f"Curve.{attribute}"
                    break
            else:
                vertexes = list(getattr(shape, "Vertexes", []) or [])
                if len(vertexes) >= 2:
                    vector = vertexes[-1].Point - vertexes[0].Point
                    source = "edge endpoints"
                else:
                    vector = None
        elif kind == "Face":
            geometry = getattr(shape, "Surface", None)
            vector = getattr(geometry, "Axis", None)
            source = "Surface.Axis"
            if vector is None:
                center = shape.CenterOfMass
                u, v = geometry.parameter(center)
                vector = shape.normalAt(u, v)
                source = "Face.normalAt(surface centroid)"
        else:
            raise ValueError("Angle measurement requires EdgeN or FaceN references")
        if vector is None or vector.Length <= 1e-12:
            raise ValueError(
                f"Cannot derive a stable direction from {resolved['subshape']!r}"
            )
        for attribute in ("Center", "Location", "Position"):
            candidate = getattr(geometry, attribute, None)
            if candidate is not None:
                origin = candidate
                break
        return vector.normalize(), source, origin, type(geometry).__name__


    def _m_angle(doc, first_spec, second_spec, orientation):
        first = _m_resolve(doc, first_spec)
        second = _m_resolve(doc, second_spec)
        vector1, source1, _, geometry1 = _m_direction(first)
        vector2, source2, _, geometry2 = _m_direction(second)
        dot = max(-1.0, min(1.0, vector1.dot(vector2)))
        if orientation == "undirected":
            dot = abs(dot)
        angle = math.degrees(math.acos(dot))
        return {
            "measurement": "angle",
            "first": _m_reference_value(first),
            "second": _m_reference_value(second),
            "angle_deg": angle,
            "orientation": orientation,
            "first_direction": _m_vector(vector1),
            "second_direction": _m_vector(vector2),
            "first_geometry_type": geometry1,
            "second_geometry_type": geometry2,
            "direction_sources": [source1, source2],
        }


    def _m_radius(doc, spec, radius_kind):
        resolved = _m_resolve(doc, spec)
        if resolved["kind"] == "Edge":
            geometry = getattr(resolved["shape"], "Curve", None)
        elif resolved["kind"] == "Face":
            geometry = getattr(resolved["shape"], "Surface", None)
        else:
            raise ValueError("Radius measurement requires an EdgeN or FaceN reference")
        geometry_type = type(geometry).__name__
        if geometry_type == "Cone":
            raise ValueError(
                "A conical face has no constant radius; measure a circular edge instead"
            )
        available = {}
        for name, attribute in (
            ("primary", "Radius"),
            ("major", "MajorRadius"),
            ("minor", "MinorRadius"),
        ):
            try:
                available[name] = _m_finite(getattr(geometry, attribute))
            except Exception:
                pass
        selected_kind = radius_kind
        if selected_kind == "auto":
            if "primary" in available:
                selected_kind = "primary"
            elif len(available) == 1:
                selected_kind = next(iter(available))
            elif len(available) > 1:
                raise ValueError(
                    f"{geometry_type} has multiple radii; choose radius_kind='major' or 'minor'"
                )
        if selected_kind not in available:
            raise ValueError(
                f"{resolved['subshape']!r} ({geometry_type}) has no {selected_kind} radius"
            )
        radius = available[selected_kind]
        return {
            "measurement": "radius_diameter",
            "reference": _m_reference_value(resolved),
            "geometry_type": geometry_type,
            "radius_kind": selected_kind,
            "radius_mm": radius,
            "diameter_mm": radius * 2.0,
            "available_radii_mm": available,
        }


    def _m_wall_thickness(doc, first_spec, second_spec, tolerance_mm, strict):
        first = _m_resolve(doc, first_spec, "Face")
        second = _m_resolve(doc, second_spec, "Face")
        direction1, _, origin1, type1 = _m_direction(first)
        direction2, _, origin2, type2 = _m_direction(second)
        alignment = math.degrees(
            math.acos(max(-1.0, min(1.0, abs(direction1.dot(direction2)))))
        )
        supported = False
        evidence = {"direction_alignment_deg": alignment}
        if type1 == type2 == "Plane":
            supported = alignment <= 1e-5
            evidence["relationship"] = "parallel_planes"
        elif type1 == type2 == "Cylinder":
            center_offset = origin2 - origin1
            axis_offset = center_offset.cross(direction1).Length
            evidence.update(
                {"relationship": "coaxial_cylinders", "axis_offset_mm": axis_offset}
            )
            supported = alignment <= 1e-5 and axis_offset <= tolerance_mm
        else:
            evidence["relationship"] = "unsupported_surface_pair"
        distance = _m_distance(doc, first_spec, second_spec, tolerance_mm)
        if supported and distance["solutions"] and distance["distance_mm"] > tolerance_mm:
            first_point = distance["solutions"][0]["point_on_first"]
            second_point = distance["solutions"][0]["point_on_second"]
            separation = FreeCAD.Vector(
                second_point["x"] - first_point["x"],
                second_point["y"] - first_point["y"],
                second_point["z"] - first_point["z"],
            )
            separation.normalize()
            axial_component = abs(separation.dot(direction1))
            if type1 == type2 == "Plane":
                lateral_component = math.sqrt(max(0.0, 1.0 - axial_component ** 2))
                lateral_mm = lateral_component * distance["distance_mm"]
                evidence["lateral_separation_mm"] = lateral_mm
                supported = lateral_mm <= max(tolerance_mm, 1e-7)
            elif type1 == type2 == "Cylinder":
                axial_mm = axial_component * distance["distance_mm"]
                evidence["axial_separation_mm"] = axial_mm
                supported = axial_mm <= max(tolerance_mm, 1e-7)
        if strict and not supported:
            raise ValueError(
                "Wall thickness requires overlapping parallel planar faces or "
                "overlapping coaxial cylindrical faces; "
                f"received {type1}/{type2} with evidence {evidence!r}"
            )
        return {
            "measurement": "wall_thickness",
            "thickness_mm": distance["distance_mm"],
            "first": distance["first"],
            "second": distance["second"],
            "surface_types": [type1, type2],
            "strict_validation": bool(strict),
            "validated_opposing_surfaces": supported,
            "evidence": evidence,
            "solutions": distance["solutions"],
            "method": distance["method"],
        }


    def _m_point_to_face(doc, face_spec, point, vertex_spec, tolerance_mm):
        face = _m_resolve(doc, face_spec, "Face")
        if point is not None:
            point_shape = Part.Vertex(FreeCAD.Vector(*point))
            point_value = {"kind": "coordinate", "point": _m_vector(point_shape.Point)}
        else:
            vertex = _m_resolve(doc, vertex_spec, "Vertex")
            point_shape = vertex["shape"]
            point_value = {
                "kind": "vertex",
                "reference": _m_reference_value(vertex),
                "point": _m_vector(point_shape.Point),
            }
        value, pairs, support_info = point_shape.distToShape(face["shape"])
        value = _m_finite(value)
        nearest = pairs[0] if pairs else None
        return {
            "measurement": "point_to_face",
            "face": _m_reference_value(face),
            "point": point_value,
            "distance_mm": value,
            "within_tolerance": value <= tolerance_mm,
            "tolerance_mm": tolerance_mm,
            "nearest_point_on_face": _m_vector(nearest[1]) if nearest else None,
            "support": _m_serialize(support_info[0]) if support_info else None,
            "method": "TopoShape.distToShape / OCCT BRepExtrema_DistShapeShape",
        }
    """
).strip()


def _document_expression(doc_name: str | None) -> str:
    return "FreeCAD.ActiveDocument" if doc_name is None else f"FreeCAD.getDocument({doc_name!r})"


def _measurement_code(
    doc_name: str | None,
    object_names: list[str],
    force_recompute: bool,
    expression: str,
) -> str:
    """Build one read-only measurement script with explicit recompute evidence."""
    return f"""\
import FreeCAD
doc = {_document_expression(doc_name)}
if doc is None:
    raise ValueError("No document found")

{MEASUREMENT_RUNTIME}

_recompute_evidence = _m_force_recompute(doc, {object_names!r}, {force_recompute!r})
_result_ = {expression}
"""


async def _execute_measurement(get_bridge: Callable[[], Awaitable[Any]], code: str) -> dict[str, Any]:
    bridge = await get_bridge()
    result = await bridge.execute_python(code)
    if result.success and isinstance(result.result, dict):
        return result.result
    raise ValueError(result.error_traceback or result.stderr or "FreeCAD measurement failed")


def register_measurement_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register the compact, tolerance-aware geometric measurement API."""

    @mcp.tool()
    async def measure_geometry(
        measurement: MeasurementRequest,
        doc_name: str | None = None,
        force_recompute: bool = True,
    ) -> dict[str, Any]:
        """Measure geometry with one strict operation selected by ``kind``.

        Supported kinds are ``bbox``, ``distance``, ``angle``, ``radius``,
        ``wall_thickness``, ``clearance``, ``minimum_gap``, and
        ``point_to_face``. Each kind exposes only its relevant fields. Use
        ``select_subshapes`` references for FaceN, EdgeN, and VertexN inputs.
        Results include OCCT evidence and forced-recompute evidence.
        """
        request = _measurement_request(measurement)

        if isinstance(request, BoundingBoxMeasurement):
            names = [request.object_name]
            expression = (
                f"_m_bbox(doc, {request.object_name!r}, {request.mode!r}, "
                f"{request.coordinate_system!r}, {request.use_triangulation!r}, "
                f"{request.use_shape_tolerance!r}, {request.report_gap!r}, "
                "_recompute_evidence)"
            )
        elif isinstance(request, DistanceMeasurement):
            first = _reference_payload(request.first)
            second = _reference_payload(request.second)
            names = [first["object_name"], second["object_name"]]
            expression = (
                f"_m_public_distance(_m_distance(doc, {first!r}, {second!r}, "
                f"{request.tolerance_mm!r}))"
            )
        elif isinstance(request, AngleMeasurement):
            first = _reference_payload(request.first)
            second = _reference_payload(request.second)
            names = [first["object_name"], second["object_name"]]
            expression = f"_m_angle(doc, {first!r}, {second!r}, {request.orientation!r})"
        elif isinstance(request, RadiusMeasurement):
            reference = _reference_payload(request.reference)
            names = [reference["object_name"]]
            expression = (
                f"_m_radius(doc, {reference!r}, {request.radius_kind!r})"
            )
        elif isinstance(request, WallThicknessMeasurement):
            first = _reference_payload(request.first_face)
            second = _reference_payload(request.second_face)
            names = [first["object_name"], second["object_name"]]
            expression = (
                f"_m_wall_thickness(doc, {first!r}, {second!r}, "
                f"{request.tolerance_mm!r}, {request.strict!r})"
            )
        elif isinstance(request, ClearanceMeasurement):
            first = _reference_payload(request.first)
            second = _reference_payload(request.second)
            names = [first["object_name"], second["object_name"]]
            distance = (
                f"_m_distance(doc, {first!r}, {second!r}, {request.tolerance_mm!r})"
            )
            expression = (
                f"(lambda _d: (lambda _i: {{'measurement': 'clearance', "
                f"'actual_clearance_mm': _d['distance_mm'], "
                f"'required_clearance_mm': {request.required_clearance_mm!r}, "
                f"'tolerance_mm': {request.tolerance_mm!r}, 'passes': "
                f"_d['distance_mm'] + {request.tolerance_mm!r} >= "
                f"{request.required_clearance_mm!r} and not _i.get('interfering', False), "
                f"'distance': _m_public_distance(_d), 'interference': _i}})"
                f"(_m_interference(_d, {request.tolerance_mm!r})))({distance})"
            )
        elif isinstance(request, MinimumGapMeasurement):
            references = [_reference_payload(item) for item in request.references]
            names = [item["object_name"] for item in references]
            expression = (
                f"(lambda _specs: (lambda _pairs: {{'measurement': 'minimum_gap', "
                f"'minimum_gap_mm': _pairs[0]['distance_mm'], 'closest_pair': "
                f"_m_public_distance(_pairs[0]), 'pair_count': len(_pairs), "
                f"'tolerance_mm': {request.tolerance_mm!r}, 'within_tolerance': "
                f"_pairs[0]['distance_mm'] <= {request.tolerance_mm!r}}})(sorted("
                f"[_m_distance(doc, _specs[_i], _specs[_j], {request.tolerance_mm!r}) "
                "for _i in range(len(_specs)) for _j in range(_i + 1, len(_specs))], "
                f"key=lambda _item: _item['distance_mm'])))({references!r})"
            )
        else:
            face = _reference_payload(request.face)
            vertex = (
                _reference_payload(request.vertex) if request.vertex is not None else None
            )
            names = [face["object_name"]]
            if vertex is not None:
                names.append(vertex["object_name"])
            expression = (
                f"_m_point_to_face(doc, {face!r}, {request.point!r}, "
                f"{vertex!r}, {request.tolerance_mm!r})"
            )

        code = _measurement_code(doc_name, names, force_recompute, expression)
        return await _execute_measurement(get_bridge, code)
