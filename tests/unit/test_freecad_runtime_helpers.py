"""Tests for Python snippets executed inside the FreeCAD interpreter."""

from freecad_mcp.tools._freecad_runtime_helpers import (
    BODY_RUNTIME_HELPERS,
    FEATURE_VALIDATION_RUNTIME_HELPERS,
)


def _load_helpers(source: str) -> dict[str, object]:
    """Execute a runtime snippet in an isolated namespace for testing."""
    namespace: dict[str, object] = {}
    exec(source, namespace)  # noqa: S102
    return namespace


class _Feature:
    def __init__(self, name: str) -> None:
        self.Name = name


class _Origin:
    def __init__(self, names: list[str]) -> None:
        self.OriginFeatures = [_Feature(name) for name in names]
        self.OutList: list[object] = []


class _Body:
    TypeId = "PartDesign::Body"

    def __init__(self, name: str, group: list[object]) -> None:
        self.Name = name
        self.Group = group
        self.Origin = _Origin(
            [
                "X_Axis001",
                "Y_Axis001",
                "Z_Axis001",
                "XY_Plane001",
                "XZ_Plane001",
                "YZ_Plane001",
                "Point001",
            ]
        )
        self.Tip = None


class _Document:
    def __init__(self, objects: list[object]) -> None:
        self.Objects = objects


def test_body_helpers_find_body_and_resolve_suffixed_origin() -> None:
    """One helper block should cover Body membership and Origin resolution."""
    target = _Feature("Sketch001")
    body = _Body("Body001", [target])
    helpers = _load_helpers(BODY_RUNTIME_HELPERS)

    find_body = helpers["_find_body_containing_object"]
    resolve_origin = helpers["_resolve_body_origin_feature"]

    assert find_body(_Document([body]), target) is body
    assert resolve_origin(body, "Z_Axis").Name == "Z_Axis001"
    assert resolve_origin(body, "XY_Plane").Name == "XY_Plane001"


class _RemovedShape:
    def __init__(self, solid_count: int) -> None:
        self.Solids = [object()] * solid_count


class _Shape:
    def __init__(
        self,
        volume: float,
        *,
        valid: bool = True,
        null: bool = False,
        solid_count: int = 1,
        removed_solid_count: int = 1,
    ) -> None:
        self.Volume = volume
        self._valid = valid
        self._null = null
        self.Solids = [object()] * solid_count
        self._removed_solid_count = removed_solid_count

    def isNull(self) -> bool:
        return self._null

    def isValid(self) -> bool:
        return self._valid

    def cut(self, _other: object) -> _RemovedShape:
        return _RemovedShape(self._removed_solid_count)


class _ValidatedFeature:
    Name = "Hole001"

    def __init__(self, shape: _Shape) -> None:
        self.Shape = shape
        self.State: list[str] = []

    def getStatusString(self) -> list[str]:
        return []


def test_subtractive_validation_checks_volume_and_removed_solids() -> None:
    """Shared validator should prove that a cut changed one valid solid."""
    helpers = _load_helpers(FEATURE_VALIDATION_RUNTIME_HELPERS)
    validate = helpers["_validate_subtractive_feature"]

    base_shape = _Shape(100.0, removed_solid_count=3)
    feature = _ValidatedFeature(_Shape(70.0))
    body = _Body("Body001", [feature])
    body.Tip = feature

    result = validate(
        feature,
        body,
        base_shape,
    )

    assert result["ok"] is True
    assert result["shape_valid"] is True
    assert result["removed_volume"] == 30.0


def test_single_solid_validation_rejects_stale_body_tip() -> None:
    """A valid Shape is not enough when the feature did not become Body.Tip."""
    helpers = _load_helpers(FEATURE_VALIDATION_RUNTIME_HELPERS)
    validate = helpers["_validate_single_solid_feature"]

    feature = _ValidatedFeature(_Shape(10.0))
    body = _Body("Body001", [feature])
    body.Tip = _Feature("PreviousFeature")

    result = validate(feature, body)

    assert result["ok"] is False
    assert any("Body Tip" in reason for reason in result["reasons"])


class _Wire:
    def __init__(self, closed: bool) -> None:
        self._closed = closed

    def isClosed(self) -> bool:
        return self._closed


class _SketchShape:
    def __init__(self, wires: list[_Wire], valid: bool = True) -> None:
        self.Wires = wires
        self._valid = valid

    def isNull(self) -> bool:
        return False

    def isValid(self) -> bool:
        return self._valid


class _Sketch:
    GeometryCount = 1
    ConstraintCount = 0
    ExternalGeometry: tuple[object, ...] = ()
    FullyConstrained = False
    DoF = 3
    Shape = _SketchShape([_Wire(True)])

    def solve(self) -> int:
        return 0

    def getConstruction(self, _index: int) -> bool:
        return False

    def getOpenVertices(self) -> list[tuple[int, int]]:
        return []

    def getGeometryWithDependentParameters(self) -> list[tuple[int, int]]:
        return [(0, 3), (0, -1)]


def test_sketch_analysis_reports_closed_but_under_constrained_profile() -> None:
    from freecad_mcp.tools._freecad_runtime_helpers import (
        SKETCH_ANALYSIS_RUNTIME_HELPERS,
    )

    helpers = _load_helpers(SKETCH_ANALYSIS_RUNTIME_HELPERS)
    analyze = helpers["_analyze_sketch"]

    result = analyze(_Sketch())

    assert result["solver"] == {
        "status": "under_constrained",
        "solve_code": 0,
        "fully_constrained": False,
        "remaining_dof": 3,
    }
    assert result["profile"]["state"] == "closed"
    assert result["profile_ready"] is True
    assert result["unconstrained"] == [
        {"geometry_index": 0, "elements": ["center", "geometry"]}
    ]
    assert "3 remaining degree(s) of freedom" in result["issues"][0]


def test_sketch_analysis_distinguishes_redundant_constraints() -> None:
    from freecad_mcp.tools._freecad_runtime_helpers import (
        SKETCH_ANALYSIS_RUNTIME_HELPERS,
    )

    class _RedundantSketch(_Sketch):
        def solve(self) -> int:
            return -2

        def getStatusString(self) -> str:
            return "Redundant constraint: 4"

    helpers = _load_helpers(SKETCH_ANALYSIS_RUNTIME_HELPERS)
    result = helpers["_analyze_sketch"](_RedundantSketch())

    assert result["solver"]["status"] == "redundant"
    assert result["solver"]["message"] == "Redundant constraint: 4"
    assert result["profile_ready"] is False
    assert result["issues"] == ["Sketch contains a redundant constraint."]


def test_sketch_analysis_reports_open_endpoints() -> None:
    from freecad_mcp.tools._freecad_runtime_helpers import (
        SKETCH_ANALYSIS_RUNTIME_HELPERS,
    )

    class _OpenSketch(_Sketch):
        GeometryCount = 2
        DoF = 4
        Shape = _SketchShape([_Wire(False)])

        def getOpenVertices(self) -> list[object]:
            class _Point:
                def __init__(self, x: float, y: float) -> None:
                    self.x = x
                    self.y = y
                    self.z = 0.0

            return [_Point(0.0, 0.0), _Point(10.0, 5.0)]

    helpers = _load_helpers(SKETCH_ANALYSIS_RUNTIME_HELPERS)
    result = helpers["_analyze_sketch"](_OpenSketch())

    assert result["profile"]["state"] == "open"
    assert result["profile"]["open_vertices"] == [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"x": 10.0, "y": 5.0, "z": 0.0},
    ]
    assert result["profile_ready"] is False
    assert any("Coincident" in hint for hint in result["hints"])
