"""Tests for structured object inspection executed inside FreeCAD."""

from freecad_mcp.bridge._object_inspection_runtime import (
    OBJECT_INSPECTION_RUNTIME,
    build_object_inspection_code,
)


def _load_runtime() -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(OBJECT_INSPECTION_RUNTIME, namespace)  # noqa: S102
    return namespace


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

    result = inspect_value(_InspectedObject())

    shape = result["properties"]["Shape"]
    assert shape["type"] == "Part::PropertyPartShape"
    assert shape["value"]["shape_type"] == "Solid"
    assert shape["value"]["volume"] == 6000.0
    assert shape["value"]["bounding_box"]["size"] == {
        "x": 10.0,
        "y": 20.0,
        "z": 30.0,
    }

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

    assert "_inspect_object_value(obj)" in code
    assert "getTypeIdOfProperty" in code
    assert "FreeCAD.getDocument('Model')" in code
    assert "doc.getObject('Pad')" in code
