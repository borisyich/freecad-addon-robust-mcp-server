"""Tests for structured object inspection executed inside FreeCAD."""

from freecad_mcp.bridge._object_inspection_runtime import (
    OBJECT_INSPECTION_RUNTIME,
    build_object_inspection_code,
)


def _load_runtime() -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(OBJECT_INSPECTION_RUNTIME, namespace)  # noqa: S102
    return namespace


def test_constraint_serializer_reports_angle_values_in_degrees() -> None:
    """Structured object inspection should not expose raw Sketcher radians."""
    runtime = _load_runtime()

    class AngleConstraint:
        Type = "Angle"
        Value = 3.141592653589793 / 2

    result = runtime["_constraint_value"](AngleConstraint())

    assert result["value"] == 90.0
    assert result["value_unit"] == "deg"


class _Vector:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z


class _Rotation:
    Axis = _Vector(0, 0, 1)
    Angle = 1.5707963267948966
    Q = (0.0, 0.0, 0.70710678, 0.70710678)


class Placement:
    Base = _Vector(1, 2, 3)
    Rotation = _Rotation()


class _BoundBox:
    XMin = 0.0
    YMin = 1.0
    ZMin = 2.0
    XMax = 10.0
    YMax = 21.0
    ZMax = 32.0
    XLength = 10.0
    YLength = 20.0
    ZLength = 30.0


class _Shape:
    ShapeType = "Solid"
    Volume = 6000.0
    Area = 2200.0
    CenterOfMass = _Vector(5, 11, 17)
    BoundBox = _BoundBox()
    Solids = (object(),)
    Shells = (object(),)
    Faces = (object(),) * 6
    Edges = (object(),) * 12
    Vertexes = (object(),) * 8

    def isNull(self) -> bool:
        return False

    def isValid(self) -> bool:
        return True

    def isClosed(self) -> bool:
        return True

    def __str__(self) -> str:
        return "<Solid object at 000001B68E6ABD40>"


class _SameShape:
    def __init__(self, token: str) -> None:
        self.token = token

    def isSame(self, other) -> bool:
        return getattr(other, "token", None) == self.token


class Line:
    pass


class Plane:
    def parameter(self, _point):
        return 0.5, 0.5


class Cylinder:
    Radius = 4.25
    Axis = _Vector(0.0, 0.0, 1.0)
    Center = _Vector(10.0, 20.0, 0.0)

    def parameter(self, _point):
        return 0.5, 0.5


class Cone:
    Radius = 6.0
    Axis = _Vector(0.0, 1.0, 0.0)
    Center = _Vector(3.0, 4.0, 5.0)

    def parameter(self, _point):
        return 0.5, 0.5


class Toroid:
    MajorRadius = 171.5
    MinorRadius = 12.25
    Axis = _Vector(0.0, 0.0, 1.0)
    Center = _Vector(1.0, 2.0, 3.0)

    def parameter(self, _point):
        return 0.5, 0.5


class _Vertex:
    def __init__(self, point: _Vector) -> None:
        self.Point = point


class _Edge(_SameShape):
    def __init__(self, token: str, start: _Vector, end: _Vector) -> None:
        super().__init__(token)
        self.Curve = Line()
        self.Vertexes = (_Vertex(start), _Vertex(end))
        self.Length = 10.0
        self.CenterOfMass = _Vector(
            (start.x + end.x) / 2,
            (start.y + end.y) / 2,
            (start.z + end.z) / 2,
        )
        self.BoundBox = _BoundBox()


class _Face:
    Orientation = "Forward"

    def __init__(self, edges) -> None:
        self.Surface = Plane()
        self.Edges = edges
        self.Area = 100.0
        self.CenterOfMass = _Vector(5.0, 5.0, 0.0)
        self.BoundBox = _BoundBox()

    def normalAt(self, _u, _v):
        return _Vector(0.0, 0.0, 1.0)

    def curvatureAt(self, _u, _v):
        return 0.0, 0.0


class _CylindricalFace(_Face):
    def __init__(self, edges) -> None:
        super().__init__(edges)
        self.Surface = Cylinder()


class _ConicalFace(_Face):
    def __init__(self, edges) -> None:
        super().__init__(edges)
        self.Surface = Cone()


class _ToroidalFace(_Face):
    def __init__(self, edges) -> None:
        super().__init__(edges)
        self.Surface = Toroid()


class _TopologicalShape(_Shape):
    edge1 = _Edge("edge-1", _Vector(0, 0, 0), _Vector(10, 0, 0))
    edge2 = _Edge("edge-2", _Vector(10, 0, 0), _Vector(10, 10, 0))
    Faces = (_Face((edge1, edge2)), _Face((edge1,)))
    Edges = (edge1, edge2)


class _LinkedObject:
    Name = "Sketch001"
    Label = "Hole profile"
    TypeId = "Sketcher::SketchObject"


class _InspectedObject:
    Name = "Feature"
    Label = "Feature"
    TypeId = "PartDesign::Feature"
    PropertiesList = ("Shape", "Placement", "Profile", "Unknown")
    Shape = _Shape()
    Placement = Placement()
    Profile = (_LinkedObject(), [])
    Unknown = object()
    OutList = (_LinkedObject(),)
    InList = ()

    def getTypeIdOfProperty(self, name: str) -> str:
        return {
            "Shape": "Part::PropertyPartShape",
            "Placement": "App::PropertyPlacement",
            "Profile": "App::PropertyLinkSub",
            "Unknown": "App::PropertyPythonObject",
        }[name]

    def getGroupOfProperty(self, _name: str) -> str:
        return "Data"

    def getPropertyStatus(self, _name: str) -> list[str]:
        return []


def test_structured_serializer_replaces_pointer_reprs() -> None:
    runtime = _load_runtime()
    inspect_value = runtime["_inspect_object_value"]

    result = inspect_value(
        _InspectedObject(), include_properties=True, include_topology=True
    )

    shape = result["properties"]["Shape"]
    assert shape["type"] == "Part::PropertyPartShape"
    assert shape["value"]["shape_type"] == "Solid"
    assert shape["value"]["volume"] == 6000.0
    assert shape["value"]["bounding_box"]["size"] == {
        "x": 10.0,
        "y": 20.0,
        "z": 30.0,
    }
    assert "faces" not in shape["value"]
    assert "edges" not in shape["value"]
    assert "faces" in result["shape_info"]
    assert "edges" in result["shape_info"]
    assert "vertices" in result["shape_info"]

    placement = result["properties"]["Placement"]["value"]
    assert placement["position"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert round(placement["rotation"]["angle_deg"], 6) == 90.0

    profile = result["properties"]["Profile"]["value"]
    assert profile[0] == {
        "name": "Sketch001",
        "label": "Hole profile",
        "type_id": "Sketcher::SketchObject",
    }

    serialized = str(result)
    assert "000001B68E6ABD40" not in serialized
    assert "object at" not in serialized


def test_all_bridges_can_share_one_inspection_script() -> None:
    code = build_object_inspection_code("Pad", "Model")

    assert "_inspect_object_value(" in code
    assert "include_topology=False" in code
    assert "getTypeIdOfProperty" in code
    assert "FreeCAD.getDocument('Model')" in code
    assert "doc.getObject('Pad')" in code


def test_shape_topology_contains_semantic_faces_and_edges() -> None:
    runtime = _load_runtime()
    shape_value = runtime["_shape_value"]

    result = shape_value(_TopologicalShape(), include_topology=True)

    assert result["faces"][0]["surface_type"] == "Plane"
    assert result["faces"][0]["normal"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert result["faces"][0]["area"] == 100.0
    assert result["faces"][0]["centroid_kind"] == "surface_area_centroid"
    assert result["faces"][0]["adjacent_faces"] == ["Face2"]
    assert result["faces"][0]["adjacent_surface_types"] == ["Plane"]
    assert result["faces"][0]["convexity"] == "flat"
    assert result["edges"][0]["curve_type"] == "Line"
    assert result["edges"][0]["start_point"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert result["edges"][0]["end_point"] == {"x": 10.0, "y": 0.0, "z": 0.0}
    assert result["edges"][0]["length"] == 10.0
    assert result["edges"][0]["centroid_kind"] == "curve_length_centroid"
    assert result["edges"][0]["adjacent_faces"] == ["Face1", "Face2"]
    assert result["topology_pages"]["vertices"]["total"] == 8


def test_cylindrical_face_topology_contains_radius_and_axis() -> None:
    runtime = _load_runtime()
    shape = _TopologicalShape()
    shape.Faces = (_CylindricalFace((shape.edge1, shape.edge2)),)

    result = runtime["_shape_topology_value"](
        shape,
        face_limit=None,
        edge_limit=0,
        vertex_limit=0,
        topology_kinds=("faces",),
        topology_fields=(
            "surface_type",
            "radius",
            "axis_direction",
            "axis_point",
        ),
    )

    face = result["faces"][0]
    assert face["surface_type"] == "Cylinder"
    assert face["radius"] == 4.25
    assert face["axis_direction"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert face["axis_point"] == {"x": 10.0, "y": 20.0, "z": 0.0}


def test_conical_face_topology_contains_radius_and_axis() -> None:
    runtime = _load_runtime()
    shape = _TopologicalShape()
    shape.Faces = (_ConicalFace((shape.edge1, shape.edge2)),)

    result = runtime["_shape_topology_value"](
        shape,
        face_limit=None,
        edge_limit=0,
        vertex_limit=0,
        topology_kinds=("faces",),
        topology_fields=("surface_type", "radius", "axis_direction", "axis_point"),
    )

    face = result["faces"][0]
    assert face["surface_type"] == "Cone"
    assert face["radius"] == 6.0
    assert face["axis_direction"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    assert face["axis_point"] == {"x": 3.0, "y": 4.0, "z": 5.0}


def test_toroidal_face_topology_contains_major_minor_radius_and_axis() -> None:
    runtime = _load_runtime()
    shape = _TopologicalShape()
    shape.Faces = (_ToroidalFace((shape.edge1, shape.edge2)),)

    result = runtime["_shape_topology_value"](
        shape,
        face_limit=None,
        edge_limit=0,
        vertex_limit=0,
        topology_kinds=("faces",),
        topology_fields=(
            "surface_type",
            "major_radius",
            "minor_radius",
            "axis_direction",
            "axis_point",
        ),
    )

    face = result["faces"][0]
    assert face["surface_type"] == "Toroid"
    assert face["major_radius"] == 171.5
    assert face["minor_radius"] == 12.25
    assert face["axis_direction"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert face["axis_point"] == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_shape_topology_is_paged_and_omitted_by_default() -> None:
    runtime = _load_runtime()
    shape_value = runtime["_shape_value"]

    compact = shape_value(_TopologicalShape())
    assert "faces" not in compact
    assert compact["face_count"] == 2

    paged = shape_value(
        _TopologicalShape(),
        include_topology=True,
        face_offset=1,
        face_limit=1,
        edge_limit=1,
        vertex_offset=2,
        vertex_limit=2,
    )
    assert [item["name"] for item in paged["faces"]] == ["Face2"]
    assert paged["topology_pages"]["faces"] == {
        "offset": 1,
        "limit": 1,
        "returned": 1,
        "total": 2,
        "has_more": False,
        "next_offset": None,
    }
    assert paged["topology_pages"]["vertices"]["returned"] == 2
    assert paged["topology_pages"]["vertices"]["next_offset"] == 4


def test_shape_topology_can_skip_unrequested_kinds_and_expensive_fields() -> None:
    """Semantic selectors should not build unrelated topology payloads."""
    runtime = _load_runtime()
    result = runtime["_shape_topology_value"](
        _TopologicalShape(),
        face_limit=None,
        topology_kinds=("faces",),
        topology_fields=("surface_type", "area"),
    )

    assert set(result) == {"faces", "topology_pages"}
    assert set(result["topology_pages"]) == {"faces"}
    assert set(result["faces"][0]) == {"name", "index", "surface_type", "area"}
    assert "edges" not in result
    assert "vertices" not in result


def test_shape_topology_empty_kind_request_returns_no_topology_records() -> None:
    runtime = _load_runtime()
    result = runtime["_shape_topology_value"](
        _TopologicalShape(),
        face_limit=0,
        edge_limit=0,
        vertex_limit=0,
        topology_kinds=(),
    )

    assert result == {"topology_pages": {}}


def test_generated_inspection_code_carries_selective_topology_contract() -> None:
    code = build_object_inspection_code(
        "Imported",
        None,
        include_topology=True,
        face_limit=None,
        edge_limit=0,
        vertex_limit=0,
        topology_kinds=("faces",),
        topology_fields=("normal", "area"),
    )

    assert "topology_kinds=('faces',)" in code
    assert "topology_fields=('normal', 'area')" in code
