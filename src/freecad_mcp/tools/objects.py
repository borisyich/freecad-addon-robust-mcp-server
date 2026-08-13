"""Object management tools for FreeCAD Robust MCP Server.

This module provides tools for managing FreeCAD objects:
creating, editing, deleting, and inspecting objects.
"""

import math
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from freecad_mcp.bridge._document_runtime import DOCUMENT_RESOLUTION_RUNTIME


class _PrimitiveBase(BaseModel):
    """Strict base model for one concrete primitive contract."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


FiniteVector3 = Annotated[
    list[Annotated[float, Field(allow_inf_nan=False)]],
    Field(min_length=3, max_length=3),
]


class BoxPrimitive(_PrimitiveBase):
    kind: Literal["box"]
    length: float = Field(default=10.0, gt=0)
    width: float = Field(default=10.0, gt=0)
    height: float = Field(default=10.0, gt=0)


class CylinderPrimitive(_PrimitiveBase):
    kind: Literal["cylinder"]
    radius: float = Field(default=5.0, gt=0)
    height: float = Field(default=10.0, gt=0)
    angle: float = Field(
        default=360.0, gt=0, le=360, description="Sweep angle in degrees."
    )


class SpherePrimitive(_PrimitiveBase):
    kind: Literal["sphere"]
    radius: float = Field(default=5.0, gt=0)


class ConePrimitive(_PrimitiveBase):
    kind: Literal["cone"]
    radius1: float = Field(default=5.0, ge=0)
    radius2: float = Field(default=0.0, ge=0)
    height: float = Field(default=10.0, gt=0)
    angle: float = Field(
        default=360.0, gt=0, le=360, description="Sweep angle in degrees."
    )

    @model_validator(mode="after")
    def validate_radii(self) -> "ConePrimitive":
        if self.radius1 == 0 and self.radius2 == 0:
            raise ValueError("cone requires at least one positive radius")
        return self


class TorusPrimitive(_PrimitiveBase):
    kind: Literal["torus"]
    radius1: float = Field(default=10.0, gt=0)
    radius2: float = Field(default=2.0, gt=0)
    angle1: float = Field(default=-180.0, description="First torus angle in degrees.")
    angle2: float = Field(default=180.0, description="Second torus angle in degrees.")
    angle3: float = Field(
        default=360.0, gt=0, le=360, description="Torus sweep angle in degrees."
    )


class WedgePrimitive(_PrimitiveBase):
    kind: Literal["wedge"]
    xmin: float = 0.0
    ymin: float = 0.0
    zmin: float = 0.0
    x2min: float = 2.0
    z2min: float = 2.0
    xmax: float = 10.0
    ymax: float = 10.0
    zmax: float = 10.0
    x2max: float = 8.0
    z2max: float = 8.0

    @model_validator(mode="after")
    def validate_extents(self) -> "WedgePrimitive":
        if self.xmax <= self.xmin:
            raise ValueError("xmax must be greater than xmin for wedge")
        if self.ymax <= self.ymin:
            raise ValueError("ymax must be greater than ymin for wedge")
        if self.zmax <= self.zmin:
            raise ValueError("zmax must be greater than zmin for wedge")
        return self


class HelixPrimitive(_PrimitiveBase):
    kind: Literal["helix"]
    pitch: float = Field(default=5.0, gt=0)
    height: float = Field(default=20.0, gt=0)
    radius: float = Field(default=5.0, gt=0)
    angle: float = Field(default=0.0, description="Helix cone angle in degrees.")
    left_handed: bool = False


PrimitiveSpec = Annotated[
    BoxPrimitive
    | CylinderPrimitive
    | SpherePrimitive
    | ConePrimitive
    | TorusPrimitive
    | WedgePrimitive
    | HelixPrimitive,
    Field(discriminator="kind"),
]
_PRIMITIVE_ADAPTER: TypeAdapter[PrimitiveSpec] = TypeAdapter(PrimitiveSpec)


class CoordinateRange(_PrimitiveBase):
    """Bounds for a face-area or edge-length centroid in global coordinates."""

    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    z_min: float | None = None
    z_max: float | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "CoordinateRange":
        for axis in ("x", "y", "z"):
            minimum = getattr(self, f"{axis}_min")
            maximum = getattr(self, f"{axis}_max")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{axis}_min must not exceed {axis}_max")
        return self


class FaceSelectionCriteria(_PrimitiveBase):
    """Semantic criteria for selecting faces from an object's Shape."""

    kind: Literal["face"]
    surface_types: list[str] | None = None
    normal: list[float] | None = Field(default=None, min_length=3, max_length=3)
    normal_tolerance_deg: float = Field(default=10.0, ge=0, le=180)
    area_min: float | None = Field(default=None, ge=0)
    area_max: float | None = Field(default=None, ge=0)
    radius_min: float | None = Field(default=None, ge=0)
    radius_max: float | None = Field(default=None, ge=0)
    axis_direction: list[float] | None = Field(default=None, min_length=3, max_length=3)
    axis_direction_tolerance_deg: float = Field(default=10.0, ge=0, le=90)
    axis_point: list[float] | None = Field(default=None, min_length=3, max_length=3)
    axis_point_tolerance: float = Field(default=1e-6, ge=0)
    convexity: Literal["flat", "convex", "concave", "saddle", "unknown"] | None = None
    adjacent_face_count_min: int | None = Field(default=None, ge=0)
    adjacent_face_count_max: int | None = Field(default=None, ge=0)
    centroid_bounds: CoordinateRange | None = Field(
        default=None,
        validation_alias=AliasChoices("centroid_bounds", "center"),
        description=(
            "Global-coordinate bounds for the face surface-area centroid. "
            "The legacy input name 'center' is accepted for compatibility."
        ),
    )
    sort_by: Literal[
        "index",
        "area",
        "radius",
        "centroid_x",
        "centroid_y",
        "centroid_z",
        "center_x",
        "center_y",
        "center_z",
        "axis_point_x",
        "axis_point_y",
        "axis_point_z",
    ] = "index"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_ranges(self) -> "FaceSelectionCriteria":
        if (
            self.area_min is not None
            and self.area_max is not None
            and self.area_min > self.area_max
        ):
            raise ValueError("area_min must not exceed area_max")
        if (
            self.adjacent_face_count_min is not None
            and self.adjacent_face_count_max is not None
            and self.adjacent_face_count_min > self.adjacent_face_count_max
        ):
            raise ValueError(
                "adjacent_face_count_min must not exceed adjacent_face_count_max"
            )
        if (
            self.radius_min is not None
            and self.radius_max is not None
            and self.radius_min > self.radius_max
        ):
            raise ValueError("radius_min must not exceed radius_max")
        _validate_direction(self.normal, "normal")
        _validate_direction(self.axis_direction, "axis_direction")
        return self


class EdgeSelectionCriteria(_PrimitiveBase):
    """Semantic criteria for selecting edges from an object's Shape."""

    kind: Literal["edge"]
    curve_types: list[str] | None = None
    direction: list[float] | None = Field(default=None, min_length=3, max_length=3)
    direction_tolerance_deg: float = Field(default=10.0, ge=0, le=90)
    length_min: float | None = Field(default=None, ge=0)
    length_max: float | None = Field(default=None, ge=0)
    radius_min: float | None = Field(default=None, ge=0)
    radius_max: float | None = Field(default=None, ge=0)
    adjacent_face_count_min: int | None = Field(default=None, ge=0)
    adjacent_face_count_max: int | None = Field(default=None, ge=0)
    adjacent_surface_types: list[str] | None = None
    centroid_bounds: CoordinateRange | None = Field(
        default=None,
        validation_alias=AliasChoices("centroid_bounds", "center"),
        description=(
            "Global-coordinate bounds for the edge curve-length centroid. "
            "The legacy input name 'center' is accepted for compatibility."
        ),
    )
    sort_by: Literal[
        "index",
        "length",
        "radius",
        "centroid_x",
        "centroid_y",
        "centroid_z",
        "center_x",
        "center_y",
        "center_z",
    ] = "index"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_ranges(self) -> "EdgeSelectionCriteria":
        for name in ("length", "radius", "adjacent_face_count"):
            minimum = getattr(self, f"{name}_min")
            maximum = getattr(self, f"{name}_max")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{name}_min must not exceed {name}_max")
        _validate_direction(self.direction, "direction")
        return self


class VertexSelectionCriteria(_PrimitiveBase):
    """Semantic criteria for selecting vertices from an object's Shape."""

    kind: Literal["vertex"]
    point_bounds: CoordinateRange | None = Field(
        default=None,
        validation_alias=AliasChoices("point_bounds", "point", "center"),
        description="Global-coordinate bounds for the vertex point.",
    )
    adjacent_edge_count_min: int | None = Field(default=None, ge=0)
    adjacent_edge_count_max: int | None = Field(default=None, ge=0)
    adjacent_face_count_min: int | None = Field(default=None, ge=0)
    adjacent_face_count_max: int | None = Field(default=None, ge=0)
    sort_by: Literal["index", "point_x", "point_y", "point_z"] = "index"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_ranges(self) -> "VertexSelectionCriteria":
        """Reject inverted vertex-adjacency ranges."""
        for name in ("adjacent_edge_count", "adjacent_face_count"):
            minimum = getattr(self, f"{name}_min")
            maximum = getattr(self, f"{name}_max")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{name}_min must not exceed {name}_max")
        return self


SubshapeSelectionCriteria = Annotated[
    FaceSelectionCriteria | EdgeSelectionCriteria | VertexSelectionCriteria,
    Field(discriminator="kind"),
]
_SUBSHAPE_CRITERIA_ADAPTER: TypeAdapter[SubshapeSelectionCriteria] = TypeAdapter(
    SubshapeSelectionCriteria
)


class SubshapeSelectionCriteriaInput(_PrimitiveBase):
    """Flat MCP input contract for semantic face, edge, or vertex selection.

    Some MCP clients render a discriminated union whose branches are local
    ``$ref`` values as ``unknown | unknown | unknown``.  Keeping one flat input
    object makes every selector field visible in generated tool declarations;
    the existing discriminated models still perform the kind-specific runtime
    validation below.
    """

    kind: Literal["face", "edge", "vertex"] = Field(
        description="Topology kind to select: face, edge, or vertex."
    )
    surface_types: list[str] | None = Field(
        default=None,
        description="Face only: accepted surface types, such as Plane or Cylinder.",
    )
    normal: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Face only: oriented representative normal [x, y, z].",
    )
    normal_tolerance_deg: float = Field(
        default=10.0,
        ge=0,
        le=180,
        description="Face only: maximum angular difference from normal, in degrees.",
    )
    area_min: float | None = Field(
        default=None, ge=0, description="Face only: minimum surface area."
    )
    area_max: float | None = Field(
        default=None, ge=0, description="Face only: maximum surface area."
    )
    radius_min: float | None = Field(
        default=None,
        ge=0,
        description="Face/edge: minimum cylindrical or circular radius.",
    )
    radius_max: float | None = Field(
        default=None,
        ge=0,
        description="Face/edge: maximum cylindrical or circular radius.",
    )
    axis_direction: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Face only: undirected cylinder/cone axis [x, y, z].",
    )
    axis_direction_tolerance_deg: float = Field(
        default=10.0,
        ge=0,
        le=90,
        description="Face only: maximum axis angular difference, in degrees.",
    )
    axis_point: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Face only: any point on the expected infinite axis.",
    )
    axis_point_tolerance: float = Field(
        default=1e-6,
        ge=0,
        description="Face only: maximum perpendicular distance to axis_point.",
    )
    convexity: Literal["flat", "convex", "concave", "saddle", "unknown"] | None = Field(
        default=None, description="Face only: local surface convexity."
    )
    curve_types: list[str] | None = Field(
        default=None,
        description="Edge only: accepted curve types, such as Line or Circle.",
    )
    direction: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Edge only: undirected straight-edge direction [x, y, z].",
    )
    direction_tolerance_deg: float = Field(
        default=10.0,
        ge=0,
        le=90,
        description="Edge only: maximum direction angular difference, in degrees.",
    )
    length_min: float | None = Field(
        default=None, ge=0, description="Edge only: minimum curve length."
    )
    length_max: float | None = Field(
        default=None, ge=0, description="Edge only: maximum curve length."
    )
    adjacent_surface_types: list[str] | None = Field(
        default=None,
        description="Edge only: every listed adjacent face surface type must occur.",
    )
    adjacent_edge_count_min: int | None = Field(
        default=None, ge=0, description="Vertex only: minimum adjacent edge count."
    )
    adjacent_edge_count_max: int | None = Field(
        default=None, ge=0, description="Vertex only: maximum adjacent edge count."
    )
    adjacent_face_count_min: int | None = Field(
        default=None,
        ge=0,
        description="Face/edge/vertex: minimum adjacent face count.",
    )
    adjacent_face_count_max: int | None = Field(
        default=None,
        ge=0,
        description="Face/edge/vertex: maximum adjacent face count.",
    )
    centroid_bounds: CoordinateRange | None = Field(
        default=None,
        validation_alias=AliasChoices("centroid_bounds", "center"),
        description="Face/edge: global centroid coordinate bounds.",
    )
    point_bounds: CoordinateRange | None = Field(
        default=None,
        validation_alias=AliasChoices("point_bounds", "point"),
        description="Vertex only: global point coordinate bounds.",
    )
    sort_by: Literal[
        "index",
        "area",
        "length",
        "radius",
        "centroid_x",
        "centroid_y",
        "centroid_z",
        "center_x",
        "center_y",
        "center_z",
        "axis_point_x",
        "axis_point_y",
        "axis_point_z",
        "point_x",
        "point_y",
        "point_z",
    ] = Field(default="index", description="Sort key supported by the selected kind.")
    sort_order: Literal["asc", "desc"] = Field(
        default="asc", description="Ascending or descending result order."
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Maximum total matches before output pagination.",
    )

    @model_validator(mode="before")
    @classmethod
    def route_legacy_center_alias(cls, value: Any) -> Any:
        """Keep legacy ``center`` bounds unambiguous for vertex criteria."""
        if (
            isinstance(value, dict)
            and value.get("kind") == "vertex"
            and "center" in value
            and "point_bounds" not in value
            and "point" not in value
        ):
            value = dict(value)
            value["point_bounds"] = value.pop("center")
        return value

    def to_internal(self) -> SubshapeSelectionCriteria:
        """Validate and convert the flat wire contract to a kind-specific model."""
        common = {
            "kind",
            "adjacent_face_count_min",
            "adjacent_face_count_max",
            "sort_by",
            "sort_order",
            "limit",
        }
        allowed = {
            "face": common
            | {
                "surface_types",
                "normal",
                "normal_tolerance_deg",
                "area_min",
                "area_max",
                "radius_min",
                "radius_max",
                "axis_direction",
                "axis_direction_tolerance_deg",
                "axis_point",
                "axis_point_tolerance",
                "convexity",
                "centroid_bounds",
            },
            "edge": common
            | {
                "curve_types",
                "direction",
                "direction_tolerance_deg",
                "length_min",
                "length_max",
                "radius_min",
                "radius_max",
                "adjacent_surface_types",
                "centroid_bounds",
            },
            "vertex": common
            | {
                "point_bounds",
                "adjacent_edge_count_min",
                "adjacent_edge_count_max",
            },
        }[self.kind]
        supplied = set(self.model_fields_set)
        unsupported = sorted(supplied - allowed)
        if unsupported:
            raise ValueError(
                f"criteria.kind={self.kind!r} does not support fields: {unsupported}"
            )
        payload = self.model_dump(include=allowed, exclude_none=True)
        return _SUBSHAPE_CRITERIA_ADAPTER.validate_python(payload)


def _validate_direction(value: list[float] | None, field_name: str) -> None:
    """Reject zero vectors before semantic selection reaches FreeCAD."""
    if value is None:
        return
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if not math.isfinite(length) or length <= 1e-12:
        raise ValueError(f"{field_name} must be a non-zero vector")


def _normalized_type_name(value: Any) -> str:
    """Normalize FreeCAD/Python type labels for case-insensitive matching."""
    text = str(value or "").strip().lower().replace(" ", "")
    text = text.rsplit(".", 1)[-1]
    for suffix in ("surface", "curve"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    aliases = {
        "planar": "plane",
        "cylindrical": "cylinder",
        "conical": "cone",
        "spherical": "sphere",
        "toroidal": "torus",
        "linear": "line",
        "linesegment": "line",
        "circular": "circle",
        "elliptical": "ellipse",
        "bspline": "bspline",
        "bezier": "bezier",
    }
    return aliases.get(text, text)


def _matches_requested_type(value: Any, requested: list[str] | None) -> bool:
    if not requested:
        return True
    candidate = _normalized_type_name(value)
    return any(candidate == _normalized_type_name(item) for item in requested)


def _vector_angle_deg(
    actual: dict[str, Any] | None,
    expected: list[float],
    *,
    undirected: bool,
) -> float | None:
    if not actual:
        return None
    try:
        actual_values = [float(actual[axis]) for axis in ("x", "y", "z")]
        expected_values = [float(item) for item in expected]
        actual_length = math.sqrt(sum(item * item for item in actual_values))
        expected_length = math.sqrt(sum(item * item for item in expected_values))
        dot = sum(
            left * right
            for left, right in zip(actual_values, expected_values, strict=True)
        ) / (actual_length * expected_length)
    except Exception:
        return None
    dot = max(-1.0, min(1.0, abs(dot) if undirected else dot))
    return math.degrees(math.acos(dot))


def _inside_range(value: Any, minimum: Any, maximum: Any) -> bool:
    if value is None:
        return minimum is None and maximum is None
    try:
        number = float(value)
    except Exception:
        return False
    return (minimum is None or number >= minimum) and (
        maximum is None or number <= maximum
    )


def _point_to_axis_distance(
    point: dict[str, Any] | None,
    axis_point: list[float],
    axis_direction: dict[str, Any] | None,
) -> float | None:
    """Measure a point to an infinite axis, ignoring the axis anchor choice."""
    if not point or not axis_direction:
        return None
    try:
        offset = [
            float(axis_point[index]) - float(point[axis])
            for index, axis in enumerate(("x", "y", "z"))
        ]
        direction = [float(axis_direction[axis]) for axis in ("x", "y", "z")]
        direction_length = math.sqrt(sum(value * value for value in direction))
        unit = [value / direction_length for value in direction]
        projection = sum(left * right for left, right in zip(offset, unit, strict=True))
        residual = [
            left - projection * right for left, right in zip(offset, unit, strict=True)
        ]
        return math.sqrt(sum(value * value for value in residual))
    except Exception:
        return None


def _centroid_matches(
    centroid: dict[str, Any] | None, bounds: CoordinateRange | None
) -> bool:
    if bounds is None:
        return True
    if centroid is None:
        return False
    for axis in ("x", "y", "z"):
        if not _inside_range(
            centroid.get(axis),
            getattr(bounds, f"{axis}_min"),
            getattr(bounds, f"{axis}_max"),
        ):
            return False
    return True


def _selection_topology_request(  # noqa: PLR0912, PLR0915
    criteria: SubshapeSelectionCriteria,
    detail_level: Literal["references", "summary", "full"],
) -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    """Request only the topology records and evidence needed by a selector."""
    kind = "vertices" if criteria.kind == "vertex" else f"{criteria.kind}s"
    if detail_level == "full":
        return (kind,), None

    fields: set[str] = set()
    if isinstance(criteria, FaceSelectionCriteria):
        if detail_level == "summary":
            fields.update(
                {
                    "surface_type",
                    "normal",
                    "area",
                    "centroid",
                    "convexity",
                    "adjacent_faces",
                    "radius",
                    "axis_direction",
                    "axis_point",
                }
            )
        if criteria.surface_types:
            fields.add("surface_type")
        if (
            criteria.radius_min is not None
            or criteria.radius_max is not None
            or criteria.sort_by == "radius"
        ):
            fields.add("radius")
        if criteria.axis_direction is not None:
            fields.add("axis_direction")
        if criteria.axis_point is not None or criteria.sort_by.startswith(
            "axis_point_"
        ):
            fields.update({"axis_direction", "axis_point"})
        if criteria.normal is not None:
            fields.add("normal")
        if (
            criteria.area_min is not None
            or criteria.area_max is not None
            or criteria.sort_by == "area"
        ):
            fields.add("area")
        if criteria.convexity is not None:
            fields.add("convexity")
        if criteria.centroid_bounds is not None or criteria.sort_by.startswith(
            ("center_", "centroid_")
        ):
            fields.add("centroid")
        if (
            criteria.adjacent_face_count_min is not None
            or criteria.adjacent_face_count_max is not None
        ):
            fields.add("adjacent_faces")
    elif isinstance(criteria, EdgeSelectionCriteria):
        if detail_level == "summary":
            fields.update(
                {
                    "curve_type",
                    "direction",
                    "length",
                    "radius",
                    "centroid",
                    "adjacent_faces",
                }
            )
        if criteria.curve_types:
            fields.add("curve_type")
        if criteria.direction is not None:
            fields.add("direction")
        if (
            criteria.length_min is not None
            or criteria.length_max is not None
            or criteria.sort_by == "length"
        ):
            fields.add("length")
        if (
            criteria.radius_min is not None
            or criteria.radius_max is not None
            or criteria.sort_by == "radius"
        ):
            fields.add("radius")
        if criteria.centroid_bounds is not None or criteria.sort_by.startswith(
            ("center_", "centroid_")
        ):
            fields.add("centroid")
        if (
            criteria.adjacent_face_count_min is not None
            or criteria.adjacent_face_count_max is not None
        ):
            fields.add("adjacent_faces")
        if criteria.adjacent_surface_types:
            fields.update({"adjacent_faces", "adjacent_surface_types"})
    else:
        if detail_level == "summary":
            fields.update({"point", "adjacent_edges", "adjacent_faces", "tolerance"})
        if criteria.point_bounds is not None or criteria.sort_by.startswith("point_"):
            fields.add("point")
        if (
            criteria.adjacent_edge_count_min is not None
            or criteria.adjacent_edge_count_max is not None
        ):
            fields.add("adjacent_edges")
        if (
            criteria.adjacent_face_count_min is not None
            or criteria.adjacent_face_count_max is not None
        ):
            fields.add("adjacent_faces")
    return (kind,), tuple(sorted(fields))


def _semantic_matches(  # noqa: PLR0912, PLR0915
    shape_info: dict[str, Any], criteria: SubshapeSelectionCriteria
) -> list[dict[str, Any]]:
    """Filter enriched ``shape_info`` using typed semantic criteria."""
    faces = list(shape_info.get("faces") or [])
    face_by_name = {face.get("name"): face for face in faces}
    if isinstance(criteria, FaceSelectionCriteria):
        source = faces
    elif isinstance(criteria, EdgeSelectionCriteria):
        source = list(shape_info.get("edges") or [])
    else:
        source = list(shape_info.get("vertices") or [])
    matches: list[dict[str, Any]] = []

    for item in source:
        adjacent_count = len(item.get("adjacent_faces") or [])
        if isinstance(criteria, VertexSelectionCriteria):
            adjacent_edge_count = len(item.get("adjacent_edges") or [])
            if not _inside_range(
                adjacent_edge_count,
                criteria.adjacent_edge_count_min,
                criteria.adjacent_edge_count_max,
            ):
                continue
            if not _inside_range(
                adjacent_count,
                criteria.adjacent_face_count_min,
                criteria.adjacent_face_count_max,
            ):
                continue
            if not _centroid_matches(item.get("point"), criteria.point_bounds):
                continue
            matches.append(item)
            continue
        if isinstance(criteria, FaceSelectionCriteria):
            if not _matches_requested_type(
                item.get("surface_type"), criteria.surface_types
            ):
                continue
            if criteria.normal is not None:
                angle = _vector_angle_deg(
                    item.get("normal"), criteria.normal, undirected=False
                )
                if angle is None or angle > criteria.normal_tolerance_deg:
                    continue
            if not _inside_range(
                item.get("area"), criteria.area_min, criteria.area_max
            ):
                continue
            if not _inside_range(
                item.get("radius"), criteria.radius_min, criteria.radius_max
            ):
                continue
            if criteria.axis_direction is not None:
                angle = _vector_angle_deg(
                    item.get("axis_direction"), criteria.axis_direction, undirected=True
                )
                if angle is None or angle > criteria.axis_direction_tolerance_deg:
                    continue
            if criteria.axis_point is not None:
                distance = _point_to_axis_distance(
                    item.get("axis_point"),
                    criteria.axis_point,
                    item.get("axis_direction"),
                )
                if distance is None or distance > criteria.axis_point_tolerance:
                    continue
            if (
                criteria.convexity is not None
                and item.get("convexity") != criteria.convexity
            ):
                continue
        else:
            if not _matches_requested_type(
                item.get("curve_type"), criteria.curve_types
            ):
                continue
            if criteria.direction is not None:
                angle = _vector_angle_deg(
                    item.get("direction"), criteria.direction, undirected=True
                )
                if angle is None or angle > criteria.direction_tolerance_deg:
                    continue
            if not _inside_range(
                item.get("length"), criteria.length_min, criteria.length_max
            ):
                continue
            if not _inside_range(
                item.get("radius"), criteria.radius_min, criteria.radius_max
            ):
                continue
            if criteria.adjacent_surface_types:
                adjacent_types = {
                    _normalized_type_name(value)
                    for value in item.get("adjacent_surface_types") or []
                } or {
                    _normalized_type_name(
                        face_by_name.get(name, {}).get("surface_type")
                    )
                    for name in item.get("adjacent_faces") or []
                }
                requested_types = {
                    _normalized_type_name(value)
                    for value in criteria.adjacent_surface_types
                }
                if not requested_types.issubset(adjacent_types):
                    continue

        if not _inside_range(
            adjacent_count,
            criteria.adjacent_face_count_min,
            criteria.adjacent_face_count_max,
        ):
            continue
        centroid = item.get("centroid") or item.get("center")
        if not _centroid_matches(centroid, criteria.centroid_bounds):
            continue
        matches.append(item)

    def sort_value(item: dict[str, Any]) -> tuple[bool, float]:
        if criteria.sort_by == "index":
            value = item.get("index")
        elif criteria.sort_by.startswith(
            ("center_", "centroid_", "point_", "axis_point_")
        ):
            axis = criteria.sort_by[-1]
            value = (
                item.get("axis_point")
                if criteria.sort_by.startswith("axis_point_")
                else item.get("point")
                or item.get("centroid")
                or item.get("center")
                or {}
            ) or {}
            value = value.get(axis)
        else:
            value = item.get(criteria.sort_by)
        if value is None:
            return True, 0.0
        try:
            return False, float(value)
        except Exception:
            return True, 0.0

    present: list[tuple[float, dict[str, Any]]] = []
    missing: list[tuple[float, dict[str, Any]]] = []
    for item in matches:
        is_missing, value = sort_value(item)
        (missing if is_missing else present).append((value, item))
    present.sort(key=lambda pair: pair[0], reverse=criteria.sort_order == "desc")
    ordered = [item for _, item in present] + [item for _, item in missing]
    return ordered


def _page(
    items: list[dict[str, Any]], offset: int, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one deterministic page plus navigation metadata."""
    total = len(items)
    page = items[offset : offset + page_size]
    next_offset = offset + len(page) if offset + len(page) < total else None
    return page, {
        "offset": offset,
        "page_size": page_size,
        "returned": len(page),
        "total": total,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }


def _compact_subshape(item: dict[str, Any]) -> dict[str, Any]:
    """Keep selection evidence useful without returning diagnostic topology."""
    keys = (
        "name",
        "index",
        "surface_type",
        "curve_type",
        "normal",
        "direction",
        "area",
        "length",
        "radius",
        "axis_direction",
        "axis_point",
        "centroid",
        "centroid_kind",
        "convexity",
        "adjacent_faces",
        "point",
        "adjacent_edges",
        "tolerance",
    )
    result = {key: item[key] for key in keys if key in item}
    if "centroid" not in result and item.get("center") is not None:
        result["centroid"] = item["center"]
    return result


def _primitive_definition(spec: PrimitiveSpec) -> tuple[str, dict[str, Any]]:
    """Map a validated primitive specification to a FreeCAD type and properties."""
    if isinstance(spec, BoxPrimitive):
        return "Part::Box", {
            "Length": spec.length,
            "Width": spec.width,
            "Height": spec.height,
        }
    if isinstance(spec, CylinderPrimitive):
        return "Part::Cylinder", {
            "Radius": spec.radius,
            "Height": spec.height,
            "Angle": spec.angle,
        }
    if isinstance(spec, SpherePrimitive):
        return "Part::Sphere", {"Radius": spec.radius}
    if isinstance(spec, ConePrimitive):
        return "Part::Cone", {
            "Radius1": spec.radius1,
            "Radius2": spec.radius2,
            "Height": spec.height,
            "Angle": spec.angle,
        }
    if isinstance(spec, TorusPrimitive):
        return "Part::Torus", {
            "Radius1": spec.radius1,
            "Radius2": spec.radius2,
            "Angle1": spec.angle1,
            "Angle2": spec.angle2,
            "Angle3": spec.angle3,
        }
    if isinstance(spec, WedgePrimitive):
        return "Part::Wedge", {
            "Xmin": spec.xmin,
            "Ymin": spec.ymin,
            "Zmin": spec.zmin,
            "X2min": spec.x2min,
            "Z2min": spec.z2min,
            "Xmax": spec.xmax,
            "Ymax": spec.ymax,
            "Zmax": spec.zmax,
            "X2max": spec.x2max,
            "Z2max": spec.z2max,
        }
    if isinstance(spec, HelixPrimitive):
        return "Part::Helix", {
            "Pitch": spec.pitch,
            "Height": spec.height,
            "Radius": spec.radius,
            "Angle": spec.angle,
            "LocalCoord": 1 if spec.left_handed else 0,
        }
    raise TypeError(f"Unsupported primitive specification: {type(spec).__name__}")


def _primitive_axis_placement(
    axis_origin: list[float] | None,
    axis_direction: list[float] | None,
) -> tuple[list[float], list[float]] | None:
    """Return an explicit normalized world-axis placement when requested."""
    if axis_origin is None and axis_direction is None:
        return None
    origin = [float(value) for value in (axis_origin or [0.0, 0.0, 0.0])]
    direction = [float(value) for value in (axis_direction or [0.0, 0.0, 1.0])]
    length = math.sqrt(sum(value * value for value in direction))
    return origin, [value / length for value in direction]


def _oriented_primitive_creation_code(
    type_id: str,
    name: str | None,
    properties: dict[str, Any],
    doc_name: str | None,
    axis_origin: list[float],
    axis_direction: list[float],
) -> str:
    """Build one transactional primitive creation with an axis-based placement."""
    return f"""
{DOCUMENT_RESOLUTION_RUNTIME}

doc = _resolve_document({doc_name!r})
doc.openTransaction("Create Oriented Primitive")
try:
    obj = doc.addObject({type_id!r}, {name!r} or "")
    for prop_name, prop_val in {properties!r}.items():
        if hasattr(obj, prop_name):
            setattr(obj, prop_name, prop_val)
    axis_origin = FreeCAD.Vector(*{axis_origin!r})
    axis_direction = FreeCAD.Vector(*{axis_direction!r})
    obj.Placement = FreeCAD.Placement(
        axis_origin,
        FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), axis_direction),
    )
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
}}
"""


def register_object_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register object-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def list_objects(doc_name: str | None = None) -> list[dict[str, Any]]:
        """List all objects in a FreeCAD document.

        Args:
            doc_name: Name of document. Uses active document if None.

        Returns:
            List of dictionaries, each containing:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier (e.g., "Part::Box")
                - visibility: Whether object is visible
        """
        bridge = await get_bridge()
        objects = await bridge.get_objects(doc_name)
        return [
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "visibility": obj.visibility,
            }
            for obj in objects
        ]

    @mcp.tool()
    async def inspect_object(
        object_name: str,
        doc_name: str | None = None,
        detail_level: Literal["summary", "shape", "topology", "full"] = "summary",
        face_offset: int = 0,
        face_limit: int = 20,
        edge_offset: int = 0,
        edge_limit: int = 20,
        vertex_offset: int = 0,
        vertex_limit: int = 20,
        include_properties: bool | None = None,
        include_shape: bool | None = None,
    ) -> dict[str, Any]:
        """Inspect an object with compact defaults and paged topology on demand.

        Args:
            object_name: Name of the object to inspect.
            doc_name: Document containing the object. Uses active document if None.
            detail_level: ``summary`` returns identity, links, and compact shape
                metrics; ``shape`` returns only bounds, volume, area, validity,
                and topology counts; ``topology`` adds paged face/edge records;
                ``full`` also serializes every property. Request ``full`` only
                after compact modes show that exact properties are necessary.
            face_offset: Zero-based face-page offset for topology/full.
            face_limit: Face-page size, from 0 to 100; zero omits faces.
            edge_offset: Zero-based edge-page offset for topology/full.
            edge_limit: Edge-page size, from 0 to 100; zero omits edges.
            vertex_offset: Zero-based vertex-page offset for topology/full.
            vertex_limit: Vertex-page size, from 0 to 100; zero omits vertices.
            include_properties: Deprecated switch that selects full detail.
            include_shape: Deprecated switch that can omit shape metrics.

        Returns:
            A compact report by default. Topology/full include independent face,
            edge, and vertex page metadata with
            ``has_more`` and ``next_offset``. Large objects can still produce a
            large response in ``full`` mode; keep page limits small.
        """
        if min(face_offset, edge_offset, vertex_offset) < 0:
            raise ValueError("topology offsets must be non-negative")
        if not all(
            0 <= value <= 100 for value in (face_limit, edge_limit, vertex_limit)
        ):
            raise ValueError("topology page limits must be between 0 and 100")

        effective_detail = detail_level
        if include_properties is True:
            effective_detail = "full"
        include_shape_value = include_shape is not False
        include_topology = effective_detail in {"topology", "full"}
        try:
            bridge = await get_bridge()
            topology_options: dict[str, Any] = {}
            if include_topology and 0 in (face_limit, edge_limit, vertex_limit):
                topology_options["topology_kinds"] = tuple(
                    kind
                    for kind, limit in (
                        ("faces", face_limit),
                        ("edges", edge_limit),
                        ("vertices", vertex_limit),
                    )
                    if limit > 0
                )
            obj = await bridge.get_object(
                object_name,
                doc_name,
                include_properties=effective_detail == "full",
                include_shape=include_shape_value,
                include_topology=include_topology,
                face_offset=face_offset,
                face_limit=face_limit,
                edge_offset=edge_offset,
                edge_limit=edge_limit,
                vertex_offset=vertex_offset,
                vertex_limit=vertex_limit,
                **topology_options,
            )
        except Exception as e:
            return {
                "error": f"Failed to retrieve object '{object_name}' from FreeCAD: {e!s}",
                "success": False,
            }

        if not obj:
            return {"error": f"Object '{object_name}' not found", "success": False}

        # obj is an ObjectInfo dataclass returned by the bridge
        if effective_detail == "shape":
            return {
                "object_name": obj.name,
                "detail_level": "shape",
                "shape_metrics": obj.shape_info,
            }

        result: dict[str, Any] = {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
            "children": obj.children,
            "parents": obj.parents,
            "visibility": obj.visibility,
            "detail_level": effective_detail,
        }

        if effective_detail == "full":
            properties = dict(obj.properties)
            if (
                include_shape_value
                and obj.shape_info is not None
                and "Shape" in properties
            ):
                shape_property = dict(properties["Shape"])
                shape_property["value"] = {"summary_ref": "shape_info"}
                properties["Shape"] = shape_property
            result["properties"] = properties

        if include_shape_value:
            result["shape_info"] = obj.shape_info

        if effective_detail in {"topology", "full"}:
            result["response_guidance"] = (
                "Use topology_pages.next_offset to request another page; use full "
                "only for a specific property-level diagnosis."
            )

        return result

    @mcp.tool()
    async def select_subshapes(
        object_name: str,
        criteria: SubshapeSelectionCriteriaInput,
        doc_name: str | None = None,
        detail_level: Literal["references", "summary", "full"] = "references",
        offset: int = 0,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Select topology semantically; example: object_name="Body", criteria={"kind":"face","surface_types":["Cylinder"],"radius_min":2.49,"radius_max":2.51}.

        Use this tool before creating a face-supported sketch or choosing edges
        for Fillet/Chamfer. It avoids brittle manual loops over ``Shape.Faces``
        ``Shape.Edges``, and ``Shape.Vertexes`` and returns the same
        ``FaceN``/``EdgeN``/``VertexN`` references consumed by modeling and
        measurement tools.

        Face criteria can filter by surface type, representative oriented
        normal, area, cylindrical radius/axis, local convexity, adjacency count,
        and centroid position.
        Edge criteria can filter by curve type, undirected line direction,
        length, radius, required adjacent surface types, adjacency count, and
        centroid position. Vertex criteria filter the world point and adjacent
        edge/face counts. Face centroids are surface-area centroids; edge
        centroids are curve-length centroids. Every listed adjacent surface type
        must occur. Results can be sorted by size or location.

        Args:
            object_name: Object whose Shape contains the target subshapes.
            criteria: Flat typed criteria. Set ``kind`` to ``face``, ``edge``, or
                ``vertex``; the schema exposes every supported filter and marks
                its applicable topology kind in each field description.
            doc_name: Document containing the object. Uses active document if None.
            detail_level: ``references`` (default) returns only FaceN/EdgeN names;
                ``summary`` adds compact evidence; ``full`` adds complete topology
                records and should be used only for a focused diagnosis.
            offset: Zero-based output-page offset.
            page_size: Output-page size, from 1 to 200.

        Returns:
            Object identity, total match count, page metadata, and references.
        """
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        normalized_input = (
            criteria
            if isinstance(criteria, SubshapeSelectionCriteriaInput)
            else SubshapeSelectionCriteriaInput.model_validate(criteria)
        )
        normalized = normalized_input.to_internal()
        bridge = await get_bridge()
        topology_kinds, topology_fields = _selection_topology_request(
            normalized, detail_level
        )
        obj = await bridge.get_object(
            object_name,
            doc_name,
            include_properties=False,
            include_shape=True,
            include_topology=True,
            face_limit=None if normalized.kind == "face" else 0,
            edge_limit=None if normalized.kind == "edge" else 0,
            vertex_limit=None if normalized.kind == "vertex" else 0,
            topology_kinds=topology_kinds,
            topology_fields=topology_fields,
        )
        if not obj:
            raise ValueError(f"Object not found: {object_name!r}")
        shape_info = obj.shape_info
        if not isinstance(shape_info, dict) or shape_info.get("is_null") is True:
            raise ValueError(f"Object {object_name!r} has no usable Shape")

        all_matches = _semantic_matches(shape_info, normalized)
        if normalized.limit is not None:
            all_matches = all_matches[: normalized.limit]
        matches, pagination = _page(all_matches, offset, page_size)
        response = {
            "object_name": obj.name,
            "object_label": obj.label,
            "kind": normalized.kind,
            "criteria": normalized.model_dump(exclude_none=True),
            "detail_level": detail_level,
            "match_count": len(all_matches),
            "pagination": pagination,
            "references": [item["name"] for item in matches],
        }
        if detail_level == "summary":
            response["matches"] = [_compact_subshape(item) for item in matches]
        elif detail_level == "full":
            response["matches"] = matches
            response["response_guidance"] = (
                "Full topology records are verbose; keep page_size small and page "
                "only while resolving a specific ambiguous selection."
            )
        return response

    @mcp.tool()
    async def create_object(
        type_id: str,
        name: str | None = None,
        properties: dict[str, Any] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new FreeCAD object.

        Args:
            type_id: FreeCAD type ID for the object. Common types include:
                - "Part::Box" - Parametric box
                - "Part::Cylinder" - Parametric cylinder
                - "Part::Sphere" - Parametric sphere
                - "Part::Cone" - Parametric cone
                - "Part::Torus" - Parametric torus
                - "Part::Feature" - Generic Part feature
                - "Sketcher::SketchObject" - Sketch
                - "PartDesign::Body" - PartDesign body
            name: Object name. Auto-generated if None.
            properties: Initial property values to set.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(type_id, name, properties, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_primitive(
        primitive: PrimitiveSpec,
        name: str | None = None,
        doc_name: str | None = None,
        axis_origin: FiniteVector3 | None = None,
        axis_direction: FiniteVector3 | None = None,
    ) -> dict[str, Any]:
        """Create a Box, Cylinder, Sphere, Cone, Torus, Wedge, or Helix.

        Args:
            primitive: Primitive kind and its dimensions. The selected kind uses
                its own strict schema; unrelated fields and invalid dimensions are
                rejected.
            name: Object name. Auto-generated if omitted.
            doc_name: Target document. Uses the active document if omitted.
            axis_origin: Optional world-space axis start/center ``[x, y, z]``.
                Supported by cylinder, cone, torus, and helix.
            axis_direction: Optional world-space axis direction ``[dx, dy, dz]``.
                It is normalized internally and supported by the same axial kinds.

        Returns:
            Created object identity, selected primitive kind, and box volume when
            the selected kind is ``box``.
        """
        if isinstance(primitive, dict):
            primitive = _PRIMITIVE_ADAPTER.validate_python(primitive)
        if (
            axis_origin is not None or axis_direction is not None
        ) and primitive.kind not in {
            "cylinder",
            "cone",
            "torus",
            "helix",
        }:
            raise ValueError(
                "axis_origin and axis_direction are supported only for cylinder, "
                "cone, torus, and helix"
            )
        _validate_direction(axis_direction, "axis_direction")
        type_id, properties = _primitive_definition(primitive)
        axis_placement = _primitive_axis_placement(axis_origin, axis_direction)

        bridge = await get_bridge()
        if axis_placement is None:
            obj = await bridge.create_object(type_id, name, properties, doc_name)
            object_name = obj.name
            object_label = obj.label
            object_type_id = obj.type_id
        else:
            axis_origin, axis_direction = axis_placement
            execution = await bridge.execute_python(
                _oriented_primitive_creation_code(
                    type_id,
                    name,
                    properties,
                    doc_name,
                    axis_origin,
                    axis_direction,
                )
            )
            if not execution.success or not isinstance(execution.result, dict):
                raise ValueError(
                    execution.error_traceback or "Failed to create oriented primitive"
                )
            object_name = str(execution.result["name"])
            object_label = str(execution.result["label"])
            object_type_id = str(execution.result["type_id"])
        result: dict[str, Any] = {
            "name": object_name,
            "label": object_label,
            "type_id": object_type_id,
            "kind": primitive.kind,
        }
        if axis_placement is not None:
            result["axis_origin"] = axis_placement[0]
            result["axis_direction"] = axis_placement[1]
        if primitive.kind == "box":
            result["volume"] = primitive.length * primitive.width * primitive.height
        return result

    @mcp.tool()
    async def edit_object(
        object_name: str,
        properties: dict[str, Any],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Edit properties of an existing FreeCAD object.

        Args:
            object_name: Name of the object to edit.
            properties: Dictionary of property names and new values. For
                ``App::PropertyLink`` properties, a string object name is
                resolved with ``doc.getObject``. Link lists and simple
                ``Object.SubElement`` references are resolved likewise.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with updated object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.edit_object(object_name, properties, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def delete_object(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete an object from a FreeCAD document.

        Args:
            object_name: Name of the object to delete.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with delete result:
                - success: Whether delete was successful
        """
        bridge = await get_bridge()
        await bridge.delete_object(object_name, doc_name)
        return {"success": True}

    @mcp.tool()
    async def boolean_operation(
        operation: Literal["fuse", "cut", "common"],
        object1_name: str,
        object2_name: str,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Perform a boolean operation on two FreeCAD objects.

        Args:
            operation: Boolean operation type: "fuse" (union), "cut" (subtract),
                      or "common" (intersection).
            object1_name: Name of the first object.
            object2_name: Name of the second object.
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
                - shape_valid: Whether the result Shape is valid
                - shape_type: OCCT ShapeType (or ``Null``)
                - solid_count: Number of result solids
                - volume: Result volume (alias of ``result_volume``)
                - base_volume: Volume of the first operand
                - result_volume: Volume after the Boolean
                - volume_delta: ``result_volume - base_volume``
        """
        bridge = await get_bridge()

        operation_map = {
            "fuse": "Part::MultiFuse",
            "cut": "Part::Cut",
            "common": "Part::MultiCommon",
        }

        if operation not in operation_map:
            raise ValueError(f"Invalid operation: {operation}. Use: fuse, cut, common")

        op_type = operation_map[operation]
        result_name = result_name or f"{operation.capitalize()}"

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj1 = doc.getObject({object1_name!r})
obj2 = doc.getObject({object2_name!r})

if obj1 is None:
    raise ValueError(f"Object not found: {object1_name!r}")
if obj2 is None:
    raise ValueError(f"Object not found: {object2_name!r}")

base_shape = getattr(obj1, "Shape", None)
tool_shape = getattr(obj2, "Shape", None)
base_volume = float(base_shape.Volume) if base_shape is not None and not base_shape.isNull() else 0.0
tool_volume = float(tool_shape.Volume) if tool_shape is not None and not tool_shape.isNull() else 0.0

# Wrap in transaction for undo support
doc.openTransaction("Boolean {operation.capitalize()}")
try:
    if {op_type!r} == "Part::Cut":
        result = doc.addObject({op_type!r}, {result_name!r})
        result.Base = obj1
        result.Tool = obj2
    else:
        result = doc.addObject({op_type!r}, {result_name!r})
        result.Shapes = [obj1, obj2]

    doc.recompute()
    shape = getattr(result, "Shape", None)
    shape_is_null = shape is None or shape.isNull()
    shape_valid = bool(not shape_is_null and shape.isValid())
    shape_type = "Null" if shape_is_null else str(shape.ShapeType)
    solid_count = 0 if shape_is_null else len(shape.Solids)
    result_volume = 0.0 if shape_is_null else float(shape.Volume)
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
    "operation": {operation!r},
    "shape_valid": shape_valid,
    "shape_type": shape_type,
    "solid_count": solid_count,
    "volume": result_volume,
    "base_volume": base_volume,
    "tool_volume": tool_volume,
    "result_volume": result_volume,
    "volume_delta": result_volume - base_volume,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Boolean operation failed")

    @mcp.tool()
    async def set_placement(
        object_name: str,
        position: list[float] | None = None,
        rotation: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the placement (position and rotation) of a FreeCAD object.

        Args:
            object_name: Name of the object to move.
            position: Position as [x, y, z]. Keeps current if None.
            rotation: Rotation as [yaw, pitch, roll] in degrees. Keeps current if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with new placement:
                - position: New position [x, y, z]
                - rotation: New rotation angles
        """
        bridge = await get_bridge()

        pos_str = (
            f"FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})"
            if position
            else "obj.Placement.Base"
        )
        rot_str = (
            f"FreeCAD.Rotation({rotation[0]}, {rotation[1]}, {rotation[2]})"
            if rotation
            else "obj.Placement.Rotation"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Placement")
try:
    pos = {pos_str}
    rot = {rot_str}

    obj.Placement = FreeCAD.Placement(pos, rot)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "position": [obj.Placement.Base.x, obj.Placement.Base.y, obj.Placement.Base.z],
    "rotation": list(obj.Placement.Rotation.toEuler()),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Set placement failed")

    @mcp.tool()
    async def scale_object(
        object_name: str,
        scale: float | list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Scale an object uniformly or non-uniformly.

        Creates a new scaled copy using Part.Scale.

        Args:
            object_name: Name of the object to scale.
            scale: Scale factor. Can be:
                - A single float for uniform scaling
                - A list [sx, sy, sz] for non-uniform scaling
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        if isinstance(scale, int | float):
            scale_vec = f"FreeCAD.Vector({scale}, {scale}, {scale})"
        else:
            scale_vec = f"FreeCAD.Vector({scale[0]}, {scale[1]}, {scale[2]})"

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape to scale")

import Part

# Wrap in transaction for undo support
doc.openTransaction("Scale Object")
try:
    scale_vec = {scale_vec}
    center = obj.Shape.BoundBox.Center

    # Create scaled shape
    mat = FreeCAD.Matrix()
    mat.scale(scale_vec)
    scaled_shape = obj.Shape.transformGeometry(mat)

    # Create result object
    result_name = {result_name!r} or f"{{obj.Name}}_scaled"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = scaled_shape

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Scale operation failed")

    @mcp.tool()
    async def rotate_object(
        object_name: str,
        axis: list[float],
        angle: float,
        center: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Rotate an object around an axis.

        Modifies the object's placement in-place.

        Args:
            object_name: Name of the object to rotate.
            axis: Rotation axis as [x, y, z] vector.
            angle: Rotation angle in degrees.
            center: Center point for rotation [x, y, z].
                    Uses object center if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with new placement:
                - position: New position [x, y, z]
                - rotation: New rotation angles
        """
        bridge = await get_bridge()

        center_str = (
            f"FreeCAD.Vector({center[0]}, {center[1]}, {center[2]})"
            if center
            else "obj.Shape.BoundBox.Center if hasattr(obj, 'Shape') else FreeCAD.Vector(0,0,0)"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Rotate Object")
try:
    axis = FreeCAD.Vector({axis[0]}, {axis[1]}, {axis[2]})
    center = {center_str}

    # Create rotation
    rot = FreeCAD.Rotation(axis, {angle})

    # Apply rotation around center
    old_placement = obj.Placement
    new_rot = rot.multiply(old_placement.Rotation)

    # Adjust position for rotation around center
    pos_vec = old_placement.Base - center
    rotated_pos = rot.multVec(pos_vec) + center

    obj.Placement = FreeCAD.Placement(rotated_pos, new_rot)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "position": [obj.Placement.Base.x, obj.Placement.Base.y, obj.Placement.Base.z],
    "rotation": list(obj.Placement.Rotation.toEuler()),
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Rotate operation failed")

    @mcp.tool()
    async def copy_object(
        object_name: str,
        new_name: str | None = None,
        offset: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a copy of an object.

        Args:
            object_name: Name of the object to copy.
            new_name: Name for the copy. Auto-generated if None.
            offset: Position offset [x, y, z] for the copy. [0,0,0] if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with copy object information:
                - name: Copy object name
                - label: Copy object label
                - type_id: Copy object type
        """
        bridge = await get_bridge()

        offset_str = (
            f"[{offset[0]}, {offset[1]}, {offset[2]}]" if offset else "[0, 0, 0]"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Copy Object")
try:
    # Create copy
    new_name = {new_name!r} or f"{{obj.Name}}_copy"

    if hasattr(obj, "Shape"):
        copy_obj = doc.addObject("Part::Feature", new_name)
        copy_obj.Shape = obj.Shape.copy()
    else:
        # For non-shape objects, create simple copy
        copy_obj = doc.copyObject(obj, False)
        copy_obj.Label = new_name

    # Apply offset
    offset = {offset_str}
    copy_obj.Placement.Base = FreeCAD.Vector(
        obj.Placement.Base.x + offset[0],
        obj.Placement.Base.y + offset[1],
        obj.Placement.Base.z + offset[2]
    )

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": copy_obj.Name,
    "label": copy_obj.Label,
    "type_id": copy_obj.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Copy operation failed")

    @mcp.tool()
    async def mirror_object(
        object_name: str,
        plane: Literal["XY", "XZ", "YZ"] = "XY",
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Mirror an object across a plane.

        Creates a new mirrored copy of the object.

        Args:
            object_name: Name of the object to mirror.
            plane: Mirror plane. Options: "XY", "XZ", "YZ".
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        plane_map = {
            "XY": "(0, 0, 1)",
            "XZ": "(0, 1, 0)",
            "YZ": "(1, 0, 0)",
        }

        if plane not in plane_map:
            raise ValueError(f"Invalid plane: {plane}. Use: XY, XZ, YZ")

        normal = plane_map[plane]

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape to mirror")

import Part

# Wrap in transaction for undo support
doc.openTransaction("Mirror Object")
try:
    # Create mirror matrix
    normal = FreeCAD.Vector{normal}
    center = obj.Shape.BoundBox.Center

    # Mirror the shape
    mirrored = obj.Shape.mirror(center, normal)

    # Create result object
    result_name = {result_name!r} or f"{{obj.Name}}_mirror"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = mirrored

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
}}
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Mirror operation failed")

    @mcp.tool()
    async def selection(
        action: Literal["get", "set", "clear"],
        object_names: list[str] | None = None,
        clear_existing: bool = True,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get, set, or clear the FreeCAD GUI selection.

        ``set`` accepts both object names and qualified subelements such as
        ``Body.Face12``, ``Pad.Edge7``, or ``Sketch.Vertex3``.

        Args:
            action: Selection operation.
            object_names: Object names or ``Object.FaceN``/``Object.EdgeN``/
                ``Object.VertexN`` references required for ``set``.
            clear_existing: Clear the previous selection before ``set``.
            doc_name: Document used for ``get`` or ``set``. Uses active document if None.

        Returns:
            Selected objects for ``get`` or the mutation result for ``set``/``clear``.
        """
        if action == "set" and not object_names:
            raise ValueError("object_names is required for action='set'")

        bridge = await get_bridge()
        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "action": {action!r}, "error": "GUI not available"}}
else:
    action = {action!r}
    if action == "get":
        selected = (
            FreeCADGui.Selection.getSelectionEx()
            if {doc_name!r} is None
            else FreeCADGui.Selection.getSelectionEx({doc_name!r})
        )
        items = []
        for selection_item in selected:
            items.append({{
                "name": selection_item.Object.Name,
                "label": selection_item.Object.Label,
                "type_id": selection_item.Object.TypeId,
                "sub_elements": list(selection_item.SubElementNames) if selection_item.SubElementNames else [],
            }})
        _result_ = {{"success": True, "action": action, "selected": items}}
    elif action == "clear":
        FreeCADGui.Selection.clearSelection()
        _result_ = {{"success": True, "action": action, "selected_count": 0}}
    else:
        import re

        doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
        if doc is None:
            raise ValueError("No document found")
        if {clear_existing!r}:
            FreeCADGui.Selection.clearSelection()
        selected_names = []
        selected_references = []
        missing_names = []
        for selection_reference in {object_names!r}:
            object_name = selection_reference
            subelement = None
            owner_name, separator, candidate = selection_reference.rpartition(".")
            if separator and re.fullmatch(r"(?:Face|Edge|Vertex)\\d+", candidate):
                object_name = owner_name
                subelement = candidate
            obj = doc.getObject(object_name)
            if obj is None:
                missing_names.append(selection_reference)
            else:
                if subelement is None:
                    FreeCADGui.Selection.addSelection(obj)
                else:
                    try:
                        obj.Shape.getElement(subelement)
                    except Exception:
                        missing_names.append(selection_reference)
                        continue
                    FreeCADGui.Selection.addSelection(obj, subelement)
                if obj.Name not in selected_names:
                    selected_names.append(obj.Name)
                selected_references.append(
                    f"{{obj.Name}}.{{subelement}}" if subelement else obj.Name
                )
        _result_ = {{
            "success": not missing_names,
            "action": action,
            "selected_count": len(selected_references),
            "selected_names": selected_names,
            "selected_references": selected_references,
            "missing_names": missing_names,
        }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "action": action,
            "error": result.error_traceback or "Selection operation failed",
        }

    # =========================================================================
    # Part Primitives - Additional shapes
    # =========================================================================

    @mcp.tool()
    async def create_line(
        point1: list[float],
        point2: list[float],
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Line (edge) between two points.

        Args:
            point1: Start point as [x, y, z].
            point2: End point as [x, y, z].
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - length: Line length
        """
        bridge = await get_bridge()

        code = f"""
import Part

{DOCUMENT_RESOLUTION_RUNTIME}

doc = _resolve_document({doc_name!r})

# Wrap in transaction for undo support
doc.openTransaction("Create Line")
try:
    p1 = FreeCAD.Vector({point1[0]}, {point1[1]}, {point1[2]})
    p2 = FreeCAD.Vector({point2[0]}, {point2[1]}, {point2[2]})

    line = Part.makeLine(p1, p2)
    obj_name = {name!r} or "Line"
    obj = doc.addObject("Part::Feature", obj_name)
    obj.Shape = line

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "length": line.Length,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create line failed")

    @mcp.tool()
    async def create_plane(
        length: float = 10.0,
        width: float = 10.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Plane (flat rectangular face).

        Args:
            length: Plane length (X direction). Defaults to 10.0.
            width: Plane width (Y direction). Defaults to 10.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Plane",
            name,
            {"Length": length, "Width": width},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_ellipse(
        major_radius: float = 10.0,
        minor_radius: float = 5.0,
        angle1: float = 0.0,
        angle2: float = 360.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Ellipse curve.

        Args:
            major_radius: Semi-major axis radius. Defaults to 10.0.
            minor_radius: Semi-minor axis radius. Defaults to 5.0.
            angle1: Start angle in degrees. Defaults to 0.
            angle2: End angle in degrees. Defaults to 360.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Ellipse",
            name,
            {
                "MajorRadius": major_radius,
                "MinorRadius": minor_radius,
                "Angle1": angle1,
                "Angle2": angle2,
            },
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_prism(
        polygon_sides: int = 6,
        circumradius: float = 5.0,
        height: float = 10.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Prism (extruded regular polygon).

        Args:
            polygon_sides: Number of sides (3 for triangle, 6 for hexagon, etc.).
                           Defaults to 6.
            circumradius: Radius of circumscribed circle. Defaults to 5.0.
            height: Prism height. Defaults to 10.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Prism",
            name,
            {"Polygon": polygon_sides, "Circumradius": circumradius, "Height": height},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_regular_polygon(
        polygon_sides: int = 6,
        circumradius: float = 5.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Regular Polygon (2D wire).

        Args:
            polygon_sides: Number of sides (3 for triangle, 6 for hexagon, etc.).
                           Defaults to 6.
            circumradius: Radius of circumscribed circle. Defaults to 5.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::RegularPolygon",
            name,
            {"Polygon": polygon_sides, "Circumradius": circumradius},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    # =========================================================================
    # Part Shape Operations
    # =========================================================================

    @mcp.tool()
    async def shell_object(
        object_name: str,
        thickness: float,
        faces_to_remove: list[str] | None = None,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a shell (hollow) version of a solid by removing faces.

        Also known as "thickness" operation. Removes specified faces and
        offsets the remaining faces to create a hollow shell.

        Args:
            object_name: Name of the solid object to shell.
            thickness: Wall thickness (positive = outward, negative = inward).
            faces_to_remove: List of face names to remove (e.g., ["Face1", "Face6"]).
                            If None, tries to remove the largest face.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        # Use actual None or list, not string "None"
        faces_param = faces_to_remove if faces_to_remove else None

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Get faces to remove (None means find largest face)
faces_to_remove = {faces_param!r}

# Wrap in transaction for undo support
doc.openTransaction("Shell Object")
try:
    if faces_to_remove is None:
        # Find and remove the largest face
        faces = obj.Shape.Faces
        largest = max(faces, key=lambda f: f.Area)
        faces_to_remove_objs = [largest]
    else:
        # Get faces by name
        faces_to_remove_objs = []
        for fname in faces_to_remove:
            idx = int(fname.replace("Face", "")) - 1
            if 0 <= idx < len(obj.Shape.Faces):
                faces_to_remove_objs.append(obj.Shape.Faces[idx])

    shell = obj.Shape.makeThickness(faces_to_remove_objs, {thickness}, 1e-3)

    result_name = {result_name!r} or f"{{obj.Name}}_shell"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = shell

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Shell operation failed")

    @mcp.tool()
    async def move_faces(
        object_name: str,
        face_names: list[str],
        distance: float,
        operation: Literal["auto", "add", "remove"] = "auto",
        result_name: str | None = None,
        hide_source: bool = True,
        doc_name: str | None = None,
        method: Literal["auto", "feature_rebuild", "prism"] = "auto",
        feature_face_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Move selected planar boundaries by a signed normal distance.

        ``feature_rebuild`` performs topology-aware local B-rep surgery for an
        imported/static solid. It discovers the local feature from the selected
        planar cap or floor, carries adjacent wall/blend/chamfer faces up to a
        parallel support boundary, heals the source with OCCT defeaturing, and
        rebuilds the recovered material or void at the moved boundary. This
        preserves fixed attachment transitions and moves terminal transitions
        instead of merely extruding the selected trimmed face.

        ``auto`` first tries that algorithm and reports any fallback reason. It
        uses the legacy face-prism Boolean only when feature reconstruction is
        unavailable. ``prism`` requests that limited compatibility algorithm
        explicitly. Use strict ``feature_rebuild`` when silent degradation is
        unacceptable. ``operation`` controls only the prism compatibility path;
        a boundary move itself adds material for positive distance and removes
        material for negative distance.

        The result is an auditable static shape feature with links to the source,
        selected and propagated faces, distance, performed method, validity, and
        before/after volume evidence. It does not pretend to be a native
        parametric PartDesign feature.

        Args:
            object_name: Shape-bearing source object.
            face_names: One or more ``FaceN`` references from ``select_subshapes``.
            distance: Signed offset distance along each oriented face normal.
            operation: ``auto`` (add for positive, remove for negative), ``add``,
                or ``remove``.
            result_name: Optional result object name.
            hide_source: Hide the source after a successful operation.
            doc_name: Document containing the source object.
            method: ``auto``, strict ``feature_rebuild``, or compatibility
                ``prism``.
            feature_face_names: Optional explicit complete local feature region.
                Include the selected boundary, walls, fillets, chamfers, and
                blends, but not the parallel support face. When omitted, the
                region is discovered automatically.

        Returns:
            Result identity, operation evidence, and static/direct-edit status.
        """
        if not face_names:
            raise ValueError("face_names must contain at least one FaceN reference")
        if not math.isfinite(distance) or abs(distance) <= 1e-12:
            raise ValueError("distance must be a finite non-zero value")
        for face_name in face_names:
            if not (
                face_name.startswith("Face")
                and face_name[4:].isdigit()
                and int(face_name[4:]) > 0
            ):
                raise ValueError(f"Invalid face reference: {face_name!r}")
        if method not in {"auto", "feature_rebuild", "prism"}:
            raise ValueError("method must be auto, feature_rebuild, or prism")
        for feature_face_name in feature_face_names or []:
            if not (
                feature_face_name.startswith("Face")
                and feature_face_name[4:].isdigit()
                and int(feature_face_name[4:]) > 0
            ):
                raise ValueError(
                    f"Invalid feature face reference: {feature_face_name!r}"
                )

        bridge = await get_bridge()
        code = f"""
import math
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, "Shape") or obj.Shape.isNull():
    raise ValueError("Object has no usable shape")

source_shape = obj.Shape
face_count = len(source_shape.Faces)
face_names = {face_names!r}
selected_indexes = []
for face_name in face_names:
    index = int(face_name[4:]) - 1
    if index < 0 or index >= face_count:
        raise ValueError(f"Subelement not found: {{obj.Name}}.{{face_name}}")
    selected_indexes.append(index)

explicit_feature_names = {feature_face_names!r} or []
explicit_feature_indexes = []
for face_name in explicit_feature_names:
    index = int(face_name[4:]) - 1
    if index < 0 or index >= face_count:
        raise ValueError(f"Subelement not found: {{obj.Name}}.{{face_name}}")
    explicit_feature_indexes.append(index)

def _surface_type(face):
    return type(getattr(face, "Surface", None)).__name__

def _face_normal(face):
    center = face.CenterOfMass
    try:
        u, v = face.Surface.parameter(center)
    except Exception:
        u_min, u_max, v_min, v_max = face.ParameterRange
        u, v = (u_min + u_max) * 0.5, (v_min + v_max) * 0.5
    normal = face.normalAt(u, v)
    if normal.Length <= 1e-12:
        raise ValueError("Could not determine an oriented face normal")
    normal.normalize()
    return normal

def _same_shape(first, second):
    try:
        return bool(first.isSame(second))
    except Exception:
        return first.isEqual(second)

def _shared_edges(first, second):
    return [
        edge
        for edge in first.Edges
        if any(_same_shape(edge, other) for other in second.Edges)
    ]

def _faces_are_tangent(first, second, shared_edges, angle_tolerance_degrees=5.0):
    if not shared_edges:
        return False
    shared_edge = shared_edges[0]
    point = shared_edge.valueAt(
        (shared_edge.FirstParameter + shared_edge.LastParameter) * 0.5
    )
    try:
        first_uv = first.Surface.parameter(point)
        second_uv = second.Surface.parameter(point)
        first_normal = first.normalAt(*first_uv)
        second_normal = second.normalAt(*second_uv)
        if first_normal.Length <= 1e-12 or second_normal.Length <= 1e-12:
            return False
        first_normal.normalize()
        second_normal.normalize()
        threshold = math.cos(math.radians(angle_tolerance_degrees))
        return abs(first_normal.dot(second_normal)) >= threshold
    except Exception:
        return False

selected_faces = [source_shape.Faces[index] for index in selected_indexes]
reference_normal = _face_normal(selected_faces[0])
for face_name, face in zip(face_names, selected_faces, strict=True):
    surface_type = type(getattr(face, "Surface", None)).__name__.lower()
    if "plane" not in surface_type:
        raise ValueError(
            f"move_faces currently supports planar faces; {{face_name}} is {{surface_type or 'unknown'}}"
        )
    normal = _face_normal(face)
    if normal.dot(reference_normal) < 1.0 - 1e-6:
        raise ValueError(
            "feature-rebuild face groups must have aligned oriented normals"
        )

adjacency = {{index: [] for index in range(face_count)}}
shared_edge_map = {{}}
for first_index in range(face_count):
    first = source_shape.Faces[first_index]
    for second_index in range(first_index + 1, face_count):
        second = source_shape.Faces[second_index]
        shared = _shared_edges(first, second)
        if shared:
            adjacency[first_index].append(second_index)
            adjacency[second_index].append(first_index)
            shared_edge_map[(first_index, second_index)] = shared

def _discover_feature_region():
    if explicit_feature_indexes:
        indexes = set(explicit_feature_indexes) | set(selected_indexes)
        return indexes, set()

    indexes = set(selected_indexes)
    support_indexes = set()
    queue = list(selected_indexes)
    while queue:
        current = queue.pop(0)
        for candidate in adjacency[current]:
            if candidate in indexes or candidate in support_indexes:
                continue
            face = source_shape.Faces[candidate]
            surface_type = _surface_type(face).lower()
            candidate_normal = _face_normal(face)
            parallel = abs(candidate_normal.dot(reference_normal)) >= 1.0 - 1e-6
            if "plane" in surface_type and parallel:
                support_indexes.add(candidate)
                continue
            indexes.add(candidate)
            queue.append(candidate)
    return indexes, support_indexes

def _discover_selected_tangent_chain():
    tangent_indexes = set()
    visited = set(selected_indexes)
    queue = list(selected_indexes)
    while queue:
        current = queue.pop(0)
        for candidate in adjacency[current]:
            if candidate in visited:
                continue
            candidate_face = source_shape.Faces[candidate]
            candidate_surface = _surface_type(candidate_face).lower()
            candidate_normal = _face_normal(candidate_face)
            if (
                candidate not in selected_indexes
                and "plane" in candidate_surface
                and abs(candidate_normal.dot(reference_normal)) >= 1.0 - 1e-6
            ):
                continue
            pair = tuple(sorted((current, candidate)))
            if not _faces_are_tangent(
                source_shape.Faces[current],
                candidate_face,
                shared_edge_map.get(pair, []),
            ):
                continue
            visited.add(candidate)
            tangent_indexes.add(candidate)
            queue.append(candidate)
    return tangent_indexes

def _selected_non_tangent_transitions():
    transitions = set()
    for selected_index in selected_indexes:
        for candidate in adjacency[selected_index]:
            pair = tuple(sorted((selected_index, candidate)))
            candidate_face = source_shape.Faces[candidate]
            if _faces_are_tangent(
                source_shape.Faces[selected_index],
                candidate_face,
                shared_edge_map.get(pair, []),
            ):
                continue
            candidate_normal = _face_normal(candidate_face)
            normal_component = abs(candidate_normal.dot(reference_normal))
            if 1e-3 < normal_component < 1.0 - 1e-6:
                transitions.add(candidate)
    return transitions

feature_indexes, support_indexes = _discover_feature_region()
tangent_indexes = _discover_selected_tangent_chain()
terminal_transition_indexes = _selected_non_tangent_transitions()
feature_names = [f"Face{{index + 1}}" for index in sorted(feature_indexes)]
support_names = [f"Face{{index + 1}}" for index in sorted(support_indexes)]
tangent_names = [f"Face{{index + 1}}" for index in sorted(tangent_indexes)]
terminal_transition_names = [
    f"Face{{index + 1}}" for index in sorted(terminal_transition_indexes)
]

mode = {operation!r}
if mode == "auto":
    mode = "add" if {distance!r} > 0 else "remove"

requested_method = {method!r}
performed_method = None
fallback_reason = None
feature_kind = None
rebuild_variant = None
base_volume = float(source_shape.Volume)
volume_tolerance = max(1e-7, abs(base_volume) * 1e-10)

def _feature_rebuild():
    if not hasattr(source_shape, "defeaturing"):
        raise ValueError("FreeCAD Shape.defeaturing is unavailable")
    if not support_indexes and not explicit_feature_indexes:
        raise ValueError(
            "automatic feature region has no parallel support boundary; "
            "supply feature_face_names or use method='prism' explicitly"
        )
    if terminal_transition_indexes:
        raise ValueError(
            "selected boundary meets a non-tangent terminal transition "
            f"{{terminal_transition_names}}; automatic translation would leave "
            "the transition behind, so controlled local B-rep surgery is required"
        )
    feature_faces = [source_shape.Faces[index] for index in sorted(feature_indexes)]
    healed = source_shape.defeaturing(feature_faces)
    if healed.isNull() or not healed.isValid():
        raise ValueError("OCCT defeaturing did not produce a valid healed support")
    if len(healed.Solids) != len(source_shape.Solids):
        raise ValueError(
            "OCCT defeaturing changed the source solid count "
            f"from {{len(source_shape.Solids)}} to {{len(healed.Solids)}}"
        )

    healed_volume = float(healed.Volume)
    feature_volume_delta = healed_volume - base_volume
    if abs(feature_volume_delta) <= volume_tolerance:
        raise ValueError("defeaturing did not isolate a material or void feature")
    if feature_volume_delta < 0.0:
        local_feature_kind = "additive_material"
        recovered_tool = source_shape.cut(healed)
    else:
        local_feature_kind = "subtractive_void"
        recovered_tool = healed.cut(source_shape)
    if recovered_tool.isNull() or float(recovered_tool.Volume) <= volume_tolerance:
        raise ValueError("could not recover the defeatured material/void region")

    if not tangent_indexes:
        return _prism_boolean(), local_feature_kind, "sharp_boundary_sweep"

    moved_tool = recovered_tool.copy()
    moved_tool.translate(reference_normal * {distance!r})
    grows_recovered_tool = (
        ({distance!r} > 0 and local_feature_kind == "additive_material")
        or ({distance!r} < 0 and local_feature_kind == "subtractive_void")
    )
    updated_tool = (
        recovered_tool.fuse(moved_tool)
        if grows_recovered_tool
        else recovered_tool.common(moved_tool)
    )
    if updated_tool.isNull() or float(updated_tool.Volume) <= volume_tolerance:
        raise ValueError(
            "requested distance collapses or disconnects the recovered feature"
        )
    candidate = (
        healed.fuse(updated_tool)
        if local_feature_kind == "additive_material"
        else healed.cut(updated_tool)
    )
    try:
        candidate = candidate.removeSplitter()
    except Exception:
        pass
    return candidate, local_feature_kind, "translated_tangent_feature"

def _prism_boolean():
    candidate = source_shape
    for face_name, face in zip(face_names, selected_faces, strict=True):
        normal = _face_normal(face)
        prism = face.extrude(normal * {distance!r})
        candidate = candidate.fuse(prism) if mode == "add" else candidate.cut(prism)
    try:
        candidate = candidate.removeSplitter()
    except Exception:
        pass
    return candidate

doc.openTransaction("Move Faces")
try:
    if requested_method in ("auto", "feature_rebuild"):
        try:
            result_shape, feature_kind, rebuild_variant = _feature_rebuild()
            performed_method = "feature_rebuild"
        except Exception as exc:
            if requested_method == "feature_rebuild":
                raise
            fallback_reason = str(exc)
            result_shape = _prism_boolean()
            performed_method = "prism_boolean_fallback"
    else:
        result_shape = _prism_boolean()
        performed_method = "prism_boolean"

    if str(source_shape.ShapeType) == "Solid" and len(result_shape.Solids) == 1:
        result_shape = result_shape.Solids[0]
    if result_shape.isNull() or not result_shape.isValid():
        raise ValueError("Local face move produced an invalid shape")
    if len(result_shape.Solids) != len(source_shape.Solids):
        raise ValueError(
            "Local face move changed solid count from "
            f"{{len(source_shape.Solids)}} to {{len(result_shape.Solids)}}"
        )
    result_volume = float(result_shape.Volume)
    volume_delta = result_volume - base_volume
    if abs(volume_delta) <= volume_tolerance:
        raise ValueError("Local face move produced no measurable material change")

    body = next(
        (
            parent for parent in (getattr(obj, "InList", []) or [])
            if getattr(parent, "TypeId", "") == "PartDesign::Body"
        ),
        None,
    )
    requested_name = {result_name!r} or f"{{obj.Name}}_move_faces"
    result = (
        body.newObject("PartDesign::Feature", requested_name)
        if body is not None
        else doc.addObject("Part::Feature", requested_name)
    )
    result.Shape = result_shape
    result.addProperty("App::PropertyLink", "SourceObject", "Direct Edit")
    result.SourceObject = obj
    result.addProperty("App::PropertyStringList", "SourceFaces", "Direct Edit")
    result.SourceFaces = face_names
    result.addProperty("App::PropertyStringList", "FeatureFaces", "Direct Edit")
    result.FeatureFaces = feature_names
    result.addProperty("App::PropertyStringList", "TangentChainFaces", "Direct Edit")
    result.TangentChainFaces = tangent_names
    result.addProperty("App::PropertyLength", "OffsetDistance", "Direct Edit")
    result.OffsetDistance = {distance!r}
    result.addProperty("App::PropertyString", "DirectEditOperation", "Direct Edit")
    result.DirectEditOperation = f"move_faces:{{mode}}:{{performed_method}}"
    result.addProperty("App::PropertyString", "DirectEditMethod", "Direct Edit")
    result.DirectEditMethod = performed_method
    if {hide_source!r} and hasattr(obj, "ViewObject"):
        obj.ViewObject.Visibility = False

    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
        "source_object": obj.Name,
        "face_names": face_names,
        "feature_face_names": feature_names,
        "support_face_names": support_names,
        "tangent_chain_face_names": tangent_names,
        "terminal_transition_face_names": terminal_transition_names,
        "distance": float({distance!r}),
        "operation": mode,
        "requested_method": requested_method,
        "performed_method": performed_method,
        "fallback_reason": fallback_reason,
        "feature_kind": feature_kind,
        "rebuild_variant": rebuild_variant,
        "shape_valid": bool(result_shape.isValid()),
        "shape_type": str(result_shape.ShapeType),
        "solid_count": len(result_shape.Solids),
        "base_volume": base_volume,
        "result_volume": result_volume,
        "volume_delta": volume_delta,
        "static_snapshot": True,
        "direct_edit": True,
        "response_guidance": (
            "This local direct edit stores a static Shape snapshot. Inspect performed_method and "
            "fallback_reason, compare a shape checkpoint, and use native Sketcher/PartDesign "
            "features when editable history exists."
        ),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Move faces failed")

    @mcp.tool()
    async def offset_3d(
        object_name: str,
        offset: float,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a 3D offset of a shape.

        Offsets all faces of the shape by the specified distance.

        Args:
            object_name: Name of the object to offset.
            offset: Offset distance (positive = outward, negative = inward).
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("3D Offset")
try:
    offset_shape = obj.Shape.makeOffsetShape({offset}, 1e-3)

    result_name = {result_name!r} or f"{{obj.Name}}_offset"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = offset_shape

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "3D offset failed")

    @mcp.tool()
    async def slice_shape(
        object_name: str,
        plane_point: list[float],
        plane_normal: list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Slice a shape with a plane, returning the cross-section.

        Args:
            object_name: Name of the object to slice.
            plane_point: A point on the cutting plane [x, y, z].
            plane_normal: Normal vector of the cutting plane [x, y, z].
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Slice Shape")
try:
    point = FreeCAD.Vector({plane_point[0]}, {plane_point[1]}, {plane_point[2]})
    normal = FreeCAD.Vector({plane_normal[0]}, {plane_normal[1]}, {plane_normal[2]})

    # Create section
    wires = obj.Shape.slice(normal, point.dot(normal))

    if not wires:
        raise ValueError("Slice produced no result - plane may not intersect shape")

    # Make a compound of the wires
    if len(wires) == 1:
        section_shape = wires[0]
    else:
        section_shape = Part.makeCompound(wires)

    result_name = {result_name!r} or f"{{obj.Name}}_slice"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = section_shape

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Slice operation failed")

    @mcp.tool()
    async def section_shape(
        object_name: str,
        plane: Literal["XY", "XZ", "YZ"] = "XY",
        offset: float = 0.0,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a cross-section of a shape at a standard plane.

        Args:
            object_name: Name of the object to section.
            plane: Section plane: "XY", "XZ", or "YZ". Defaults to "XY".
            offset: Offset from origin along the plane normal. Defaults to 0.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        plane_normals = {
            "XY": [0, 0, 1],
            "XZ": [0, 1, 0],
            "YZ": [1, 0, 0],
        }

        if plane not in plane_normals:
            raise ValueError(f"Invalid plane: {plane}. Use: XY, XZ, YZ")

        normal = plane_normals[plane]
        point = [n * offset for n in normal]

        return await slice_shape(object_name, point, normal, result_name, doc_name)

    # =========================================================================
    # Part Compound Operations
    # =========================================================================

    @mcp.tool()
    async def make_compound(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Combine multiple shapes into a single compound.

        A compound is a collection of shapes that can be manipulated together
        but are not fused (each shape remains separate).

        Args:
            object_names: List of object names to combine.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
                - shape_count: Number of shapes in compound
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

# Wrap in transaction for undo support
doc.openTransaction("Make Compound")
try:
    compound = Part.makeCompound(shapes)

    result_name = {result_name!r} or "Compound"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = compound

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
        "shape_count": len(shapes),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make compound failed")

    @mcp.tool()
    async def explode_compound(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Separate a compound into individual shape objects.

        Args:
            object_name: Name of the compound object to explode.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation succeeded
                - created_objects: List of created object names
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Explode Compound")
try:
    created = []

    # Get solids, shells, or other sub-shapes
    solids = obj.Shape.Solids
    if solids:
        shapes = solids
    else:
        shapes = obj.Shape.Shells if obj.Shape.Shells else obj.Shape.Faces

    for i, shape in enumerate(shapes):
        new_obj = doc.addObject("Part::Feature", f"{{obj.Name}}_{{i+1}}")
        new_obj.Shape = shape
        created.append(new_obj.Name)

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "created_objects": created,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Explode compound failed")

    @mcp.tool()
    async def fuse_all(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Fuse (union) multiple shapes into a single solid.

        Unlike boolean_operation which works on two objects at a time,
        this fuses all specified objects at once.

        Args:
            object_names: List of object names to fuse.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

if len(shapes) < 2:
    raise ValueError("Need at least 2 objects to fuse")

# Wrap in transaction for undo support
doc.openTransaction("Fuse All")
try:
    # Fuse all shapes
    fused = shapes[0]
    for s in shapes[1:]:
        fused = fused.fuse(s)

    result_name = {result_name!r} or "Fusion"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = fused

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Fuse all failed")

    @mcp.tool()
    async def common_all(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Find the common (intersection) of multiple shapes.

        Args:
            object_names: List of object names to intersect.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

if len(shapes) < 2:
    raise ValueError("Need at least 2 objects for common operation")

# Wrap in transaction for undo support
doc.openTransaction("Common All")
try:
    # Find common of all shapes
    common = shapes[0]
    for s in shapes[1:]:
        common = common.common(s)

    result_name = {result_name!r} or "Common"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = common

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Common all failed")

    # =========================================================================
    # Part Wire/Face Operations
    # =========================================================================

    @mcp.tool()
    async def make_wire(
        points: list[list[float]],
        closed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a wire (polyline) from a list of points.

        Args:
            points: List of points, each as [x, y, z].
            closed: Whether to close the wire. Defaults to False.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - length: Wire length
        """
        bridge = await get_bridge()

        code = f"""
import Part

{DOCUMENT_RESOLUTION_RUNTIME}

doc = _resolve_document({doc_name!r})

points = {points!r}
if len(points) < 2:
    raise ValueError("Need at least 2 points to make a wire")

# Wrap in transaction for undo support
doc.openTransaction("Make Wire")
try:
    vectors = [FreeCAD.Vector(p[0], p[1], p[2]) for p in points]

    # Create edges between consecutive points
    edges = []
    for i in range(len(vectors) - 1):
        edges.append(Part.makeLine(vectors[i], vectors[i+1]))

    # Close the wire if requested
    if {closed} and len(vectors) > 2:
        edges.append(Part.makeLine(vectors[-1], vectors[0]))

    wire = Part.Wire(edges)

    obj_name = {name!r} or "Wire"
    obj = doc.addObject("Part::Feature", obj_name)
    obj.Shape = wire

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "length": wire.Length,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make wire failed")

    @mcp.tool()
    async def make_face(
        object_name: str,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a face from a closed wire.

        Args:
            object_name: Name of the wire object.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
                - area: Face area
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Make Face")
try:
    # Get wire from shape
    wires = obj.Shape.Wires
    if not wires:
        raise ValueError("Object has no wires to make face from")

    face = Part.Face(wires[0])

    result_name = {result_name!r} or f"{{obj.Name}}_face"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = face

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
        "area": face.Area,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make face failed")

    @mcp.tool()
    async def extrude_shape(
        object_name: str,
        direction: list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Extrude a wire or face along a direction vector.

        Args:
            object_name: Name of the wire or face object to extrude.
            direction: Extrusion direction and length as [x, y, z].
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Extrude Shape")
try:
    direction = FreeCAD.Vector({direction[0]}, {direction[1]}, {direction[2]})
    extruded = obj.Shape.extrude(direction)

    result_name = {result_name!r} or f"{{obj.Name}}_extruded"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = extruded

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Extrude shape failed")

    @mcp.tool()
    async def revolve_shape(
        object_name: str,
        axis_point: list[float],
        axis_direction: list[float],
        angle: float = 360.0,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Revolve a wire or face around an axis.

        Args:
            object_name: Name of the wire or face object to revolve.
            axis_point: A point on the rotation axis [x, y, z].
            axis_direction: Direction of the rotation axis [x, y, z].
            angle: Revolution angle in degrees. Defaults to 360.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Revolve Shape")
try:
    axis_point = FreeCAD.Vector({axis_point[0]}, {axis_point[1]}, {axis_point[2]})
    axis_dir = FreeCAD.Vector({axis_direction[0]}, {axis_direction[1]}, {axis_direction[2]})

    revolved = obj.Shape.revolve(axis_point, axis_dir, {angle})

    result_name = {result_name!r} or f"{{obj.Name}}_revolved"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = revolved

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Revolve shape failed")

    # =========================================================================
    # Part Loft and Sweep
    # =========================================================================

    @mcp.tool()
    async def part_loft(
        profile_names: list[str],
        solid: bool = True,
        ruled: bool = False,
        closed: bool = False,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a loft (transition shape) between multiple profiles.

        This is the Part workbench version of loft, working directly on
        wires/faces rather than PartDesign sketches.

        Args:
            profile_names: List of wire/face object names to loft through (in order).
            solid: Whether to create a solid (True) or shell (False). Defaults to True.
            ruled: Whether to create ruled surfaces. Defaults to False.
            closed: Whether to close the loft (connect last to first). Defaults to False.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the profiles. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

profiles = []
for name in {profile_names!r}:
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError(f"Object not found: {{name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{name}}")

    # Get wire from shape
    if obj.Shape.Wires:
        profiles.append(obj.Shape.Wires[0])
    else:
        raise ValueError(f"Object has no wires: {{name}}")

if len(profiles) < 2:
    raise ValueError("Need at least 2 profiles for loft")

# Wrap in transaction for undo support
doc.openTransaction("Part Loft")
try:
    loft = Part.makeLoft(profiles, {solid}, {ruled}, {closed})

    result_name = {result_name!r} or "Loft"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = loft

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Part loft failed")

    @mcp.tool()
    async def part_sweep(
        profile_name: str,
        spine_name: str,
        solid: bool = True,
        frenet: bool = True,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Sweep a profile along a spine path.

        This is the Part workbench version of sweep, working directly on
        wires/faces rather than PartDesign sketches.

        Args:
            profile_name: Name of the profile wire/face object.
            spine_name: Name of the spine (path) wire object.
            solid: Whether to create a solid. Defaults to True.
            frenet: Whether to use Frenet mode for orientation. Defaults to True.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

profile_obj = doc.getObject({profile_name!r})
if profile_obj is None:
    raise ValueError(f"Profile object not found: {profile_name!r}")

spine_obj = doc.getObject({spine_name!r})
if spine_obj is None:
    raise ValueError(f"Spine object not found: {spine_name!r}")

if not hasattr(profile_obj, "Shape") or not hasattr(spine_obj, "Shape"):
    raise ValueError("Objects must have shapes")

# Wrap in transaction for undo support
doc.openTransaction("Part Sweep")
try:
    # Get profile wire
    if profile_obj.Shape.Wires:
        profile = profile_obj.Shape.Wires[0]
    else:
        raise ValueError("Profile has no wires")

    # Get spine wire
    if spine_obj.Shape.Wires:
        spine = spine_obj.Shape.Wires[0]
    else:
        raise ValueError("Spine has no wires")

    sweep = Part.Wire(spine).makePipeShell([profile], {solid}, {frenet})

    result_name = {result_name!r} or "Sweep"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = sweep

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Part sweep failed")
