"""Tests for generated FreeCAD parametric-validation code."""

from freecad_mcp.bridge._parametric_validation_runtime import (
    build_parametric_validation_code,
)


def test_generated_parametric_validation_code_compiles() -> None:
    code = build_parametric_validation_code(
        doc_name="Bracket",
        recompute=True,
        include_sketch_constraints=False,
    )

    compile(code, "<parametric-validation>", "exec")
    assert "Bracket" in code
    assert '"bodies"' in code
    assert '"sketch_solver_status_counts"' in code
    assert '"object_type_counts"' in code
    assert '"history_type_counts"' in code
    assert '"solver_constraint_indices"' in code
    assert '"has_solid"' in code
    assert "_analyze_sketch" in code


def test_generated_code_can_include_constraint_details() -> None:
    code = build_parametric_validation_code(
        doc_name=None,
        recompute=False,
        include_sketch_constraints=True,
    )

    compile(code, "<parametric-validation>", "exec")
    assert "__INCLUDE_CONSTRAINTS__" not in code
    assert "if True:" in code
    assert "FreeCAD.ActiveDocument" in code


def test_generated_code_uses_safe_named_document_lookup() -> None:
    code = build_parametric_validation_code(
        doc_name="MissingDoc",
        recompute=True,
        include_sketch_constraints=False,
    )

    assert "FreeCAD.listDocuments().get(requested_doc_name)" in code


def test_generated_report_describes_body_tip_history_and_sketch(monkeypatch) -> None:
    """Execute the generated runtime against a small FreeCAD-like object graph."""
    import sys
    from types import SimpleNamespace

    class FakeBoundBox:
        XMin = YMin = ZMin = 0.0
        XMax = 20.0
        YMax = 10.0
        ZMax = 5.0
        XLength = 20.0
        YLength = 10.0
        ZLength = 5.0

    class FakeWire:
        def isClosed(self) -> bool:  # noqa: N802 - mirrors FreeCAD API
            return True

    class FakeShape:
        ShapeType = "Solid"
        Solids = [object()]
        Shells = [object()]
        Faces = [object()] * 6
        Edges = [object()] * 12
        Vertexes = [object()] * 8
        Wires = [FakeWire()]
        Volume = 1000.0
        Area = 700.0
        BoundBox = FakeBoundBox()

        def isNull(self) -> bool:  # noqa: N802
            return False

        def isValid(self) -> bool:  # noqa: N802
            return True

    placement = SimpleNamespace(
        Base=SimpleNamespace(x=0.0, y=0.0, z=0.0),
        Rotation=SimpleNamespace(
            Axis=SimpleNamespace(x=0.0, y=0.0, z=1.0),
            Angle=0.0,
        ),
    )

    class FakeConstraint:
        Type = "DistanceX"
        Name = "Width"

    class FakeSketch:
        Name = "BaseSketch"
        Label = "Base Sketch"
        TypeId = "Sketcher::SketchObject"
        State = []
        ViewObject = SimpleNamespace(Visibility=False)
        Placement = placement
        MapMode = "FlatFace"
        Support = None
        AttachmentSupport = []
        ExpressionEngine = []
        Constraints = [FakeConstraint()]
        GeometryCount = 4
        ConstraintCount = 1
        ExternalGeometry = []
        FullyConstrained = False
        DoF = 2
        Shape = FakeShape()
        InList = []
        OutList = []

        def solve(self) -> int:
            return 0

        def getStatusString(self):  # noqa: N802
            return []

        def getConstruction(self, index):  # noqa: N802, ARG002
            return False

        def getOpenVertices(self):  # noqa: N802
            return []

        def getGeometryWithDependentParameters(self):  # noqa: N802
            return [(0, 1), (1, 2)]

        def getConstraintName(self, index):  # noqa: N802, ARG002
            return "Width"

        def isDriving(self, index):  # noqa: N802, ARG002
            return True

        def isInVirtualSpace(self, index):  # noqa: N802, ARG002
            return False

        def getDatum(self, index):  # noqa: N802, ARG002
            return SimpleNamespace(Value=20.0, Unit="mm", __str__=lambda _: "20 mm")

        def getLastConflicting(self):  # noqa: N802
            return []

        def getLastRedundant(self):  # noqa: N802
            return []

        def getLastPartiallyRedundant(self):  # noqa: N802
            return []

        def getLastMalformedConstraints(self):  # noqa: N802
            return []

    sketch = FakeSketch()
    pad = SimpleNamespace(
        Name="Pad",
        Label="Pad",
        TypeId="PartDesign::Pad",
        State=[],
        ViewObject=SimpleNamespace(Visibility=True),
        Placement=placement,
        Shape=FakeShape(),
        ExpressionEngine=[],
        InList=[sketch],
        OutList=[],
    )
    body = SimpleNamespace(
        Name="Body",
        Label="Body",
        TypeId="PartDesign::Body",
        State=[],
        ViewObject=SimpleNamespace(Visibility=True),
        Placement=placement,
        Shape=FakeShape(),
        Group=[sketch, pad],
        Tip=pad,
    )
    doc = SimpleNamespace(
        Name="Bracket",
        Label="Bracket",
        FileName="Bracket.FCStd",
        Objects=[body, sketch, pad],
        recompute=lambda: None,
    )
    fake_freecad = SimpleNamespace(
        ActiveDocument=doc,
        listDocuments=lambda: {"Bracket": doc},
    )
    monkeypatch.setitem(sys.modules, "FreeCAD", fake_freecad)

    code = build_parametric_validation_code(
        doc_name="Bracket",
        recompute=True,
        include_sketch_constraints=True,
    )
    namespace: dict[str, object] = {}
    exec(code, namespace)
    report = namespace["_result_"]

    assert report["document"]["name"] == "Bracket"
    assert report["counts"]["bodies"] == 1
    assert report["bodies"][0]["tip"]["name"] == "Pad"
    assert [item["name"] for item in report["bodies"][0]["history"]] == [
        "BaseSketch",
        "Pad",
    ]
    sketch_report = report["bodies"][0]["sketches"][0]
    assert sketch_report["analysis"]["solver"]["status"] == "under_constrained"
    assert sketch_report["analysis"]["solver"]["remaining_dof"] == 2
    assert sketch_report["named_constraint_count"] == 1
    assert sketch_report["constraints"][0]["name"] == "Width"
    assert any(
        item["category"] == "sketch_under_constrained"
        for item in report["findings"]
    )
