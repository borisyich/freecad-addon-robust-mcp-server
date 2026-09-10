"""Counterexamples and check ablations; these are not VLM performance scores."""

import json
import uuid
from typing import Any

import pytest

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.partdesign import register_partdesign_tools

pytestmark = pytest.mark.integration


def _experiment(xmlrpc_proxy, body: str) -> dict[str, Any]:
    """Run only in a fresh disposable document, preserving the active document."""
    name = "PolicyExperiment_" + uuid.uuid4().hex
    code = f"""
import FreeCAD, Part, Sketcher, math
previous = FreeCAD.ActiveDocument
previous_name = previous.Name if previous else None
doc = FreeCAD.newDocument({name!r})
doc.UndoMode = 1
def run_experiment(doc=doc):
    import FreeCAD, Part, Sketcher, math
{chr(10).join("    " + line for line in body.splitlines())}
    return _result_
try:
    _result_ = run_experiment()
finally:
    FreeCAD.closeDocument(doc.Name)
    if previous_name and previous_name in FreeCAD.listDocuments():
        FreeCAD.setActiveDocument(previous_name)
"""
    result = xmlrpc_proxy.execute_with_timeout(code, 20000)
    assert result.get("success"), json.dumps(result)
    payload = result["result"]
    print(json.dumps(payload, sort_keys=True))
    return payload


@pytest.mark.parametrize("radius,offset", [(1.0, 4.0), (1.7, 6.0), (2.1, 7.0)])
def test_global_metrics_ablation_misses_relocated_interfaces(
    xmlrpc_proxy, radius, offset
):
    result = _experiment(
        xmlrpc_proxy,
        f"""
base = Part.makeBox(24, 24, 6, FreeCAD.Vector(-12, -12, 0))
def perforated(axis):
    shape = base
    for sign in [-1, 1]:
        point = FreeCAD.Vector(sign * {offset} if axis == "x" else 0,
                               sign * {offset} if axis == "y" else 0, 0)
        shape = shape.cut(Part.makeCylinder({radius}, 6, point))
    assert len(shape.Solids) == 1
    return shape.Solids[0]
before, wrong = perforated("x"), perforated("y")
metric_only_accepts = (
    before.isValid() and wrong.isValid()
    and len(before.Solids) == len(wrong.Solids)
    and abs(before.Volume - wrong.Volume) < 1e-7
    and abs(before.Area - wrong.Area) < 1e-7
    and (before.CenterOfMass - wrong.CenterOfMass).Length < 1e-7
    and all(abs(getattr(before.BoundBox, k) - getattr(wrong.BoundBox, k)) < 1e-7
            for k in ["XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"])
)
removed = before.cut(wrong).Volume
added = wrong.cut(before).Volume
probe = FreeCAD.Vector({offset}, 0, 3)
_result_ = {{"metric_only_accepts": metric_only_accepts,
            "removed": removed, "added": added,
            "interface_changed": before.isInside(probe, 1e-7, True)
                                 != wrong.isInside(probe, 1e-7, True)}}
""",
    )
    assert result["metric_only_accepts"] is True
    assert result["removed"] > 0 and result["added"] > 0
    assert result["interface_changed"] is True


@pytest.mark.parametrize("delta", [-4.0, 6.0])
def test_parameter_perturbation_ablation_exposes_frozen_design_relation(
    xmlrpc_proxy, delta
):
    result = _experiment(
        xmlrpc_proxy,
        f"""
base = doc.addObject("Part::Box", "Envelope")
base.Length, base.Width, base.Height = 20, 12, 5
linked = doc.addObject("Part::Cylinder", "LinkedInterface")
frozen = doc.addObject("Part::Cylinder", "FrozenInterface")
for tool in [linked, frozen]:
    tool.Radius, tool.Height = 1, 5
    tool.Placement.Base = FreeCAD.Vector(10, 6, 0)
linked.setExpression("Placement.Base.x", "Envelope.Length / 2")
doc.recompute()
initial_error = (linked.Shape.CenterOfMass - frozen.Shape.CenterOfMass).Length
doc.openTransaction("Perturb design parameter")
base.Length = 20 + {delta}
doc.recompute()
expected_x = float(base.Length) / 2
linked_error = abs(linked.Shape.CenterOfMass.x - expected_x)
frozen_error = abs(frozen.Shape.CenterOfMass.x - expected_x)
doc.abortTransaction()
doc.recompute()
_result_ = {{"initial_error": initial_error, "linked_error": linked_error,
            "frozen_error": frozen_error, "restored_length": float(base.Length),
            "restored_x": linked.Shape.CenterOfMass.x}}
""",
    )
    assert result["initial_error"] == pytest.approx(0, abs=1e-7)
    assert result["linked_error"] == pytest.approx(0, abs=1e-7)
    assert result["frozen_error"] == pytest.approx(abs(delta) / 2)
    assert result["restored_length"] == pytest.approx(20)
    assert result["restored_x"] == pytest.approx(10)


@pytest.mark.parametrize("radial_tolerance", [0.04, 0.08])
def test_nominal_clearance_ablation_misses_limit_interference(
    xmlrpc_proxy, radial_tolerance
):
    result = _experiment(
        xmlrpc_proxy,
        f"""
def interference(bore_radius, shaft_radius):
    sleeve = Part.makeCylinder(8, 5).cut(Part.makeCylinder(bore_radius, 5))
    shaft = Part.makeCylinder(shaft_radius, 5)
    return sleeve.common(shaft).Volume
_result_ = {{"nominal_interference": interference(5.03, 5.0),
            "limit_interference": interference(5.03 - {radial_tolerance},
                                                5.0 + {radial_tolerance})}}
""",
    )
    assert result["nominal_interference"] == pytest.approx(0, abs=1e-7)
    assert result["limit_interference"] > 0


def test_redundant_tangency_does_not_require_reinterpreting_source(xmlrpc_proxy):
    result = _experiment(
        xmlrpc_proxy,
        """
sketch = doc.addObject("Sketcher::SketchObject", "TangentProfile")
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(-4, 0, 0), FreeCAD.Vector(4, 0, 0)), False)
sketch.addGeometry(Part.Circle(FreeCAD.Vector(0, 2, 0), FreeCAD.Vector(0, 0, 1), 2), False)
first = sketch.addConstraint(Sketcher.Constraint("Tangent", 0, 1))
healthy = sketch.solve()
duplicate = sketch.addConstraint(Sketcher.Constraint("Tangent", 0, 1))
redundant = sketch.solve()
sketch.delConstraint(duplicate)
repaired = sketch.solve()
_result_ = {"healthy_solver": healthy, "duplicate_solver": redundant,
            "repaired_solver": repaired,
            "tangent_count": sum(c.Type == "Tangent" for c in sketch.Constraints)}
""",
    )
    assert result["healthy_solver"] == 0
    assert result["duplicate_solver"] != 0
    assert result["repaired_solver"] == 0
    assert result["tangent_count"] == 1


def test_single_fixed_reference_curve_is_valid_in_freecad(xmlrpc_proxy):
    result = _experiment(
        xmlrpc_proxy,
        """
sketch = doc.addObject("Sketcher::SketchObject", "ReferenceCurve")
sketch.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 3), False)
sketch.addConstraint(Sketcher.Constraint("Block", 0))
doc.recompute()
_result_ = {"solver": sketch.solve(), "dof": sketch.FullyConstrained,
            "geometry_count": sketch.GeometryCount, "constraint_count": sketch.ConstraintCount}
""",
    )
    assert result["solver"] == 0
    assert result["dof"] is True
    assert result["geometry_count"] == result["constraint_count"] == 1


@pytest.mark.asyncio
async def test_constraint_tool_allows_complete_intentional_reference_fix():
    """Exercise the public batch against FreeCAD, including rollback on conflict."""

    class Collector:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function

            return register

    name = "PolicyConstraintTool_" + uuid.uuid4().hex
    bridge = XmlRpcBridge()
    await bridge.connect()
    collector = Collector()

    async def get_bridge():
        return bridge

    register_partdesign_tools(collector, get_bridge)
    setup = await bridge.execute_python(f"""
import Part
previous_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
doc = FreeCAD.newDocument({name!r})
doc.UndoMode = 1
sketch = doc.addObject("Sketcher::SketchObject", "Reference")
sketch.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 3), False)
doc.recompute()
_result_ = previous_name
""")
    try:
        assert setup.success, setup.failure_details("setup")
        result = await collector.tools["edit_sketch_constraints"](
            "Reference", [{"op": "fix", "geometry1": 0}], doc_name=name
        )
        assert result["operations_applied"] == 1
        with pytest.raises(ValueError):
            await collector.tools["edit_sketch_constraints"](
                "Reference",
                [
                    {"op": "delete_constraint", "constraint_index": 0},
                    {"op": "radius", "geometry1": 0, "value": 3},
                    {"op": "radius", "geometry1": 0, "value": 4},
                ],
                doc_name=name,
            )
        state = await bridge.execute_python(f"""
sketch = FreeCAD.getDocument({name!r}).getObject("Reference")
_result_ = {{"count": sketch.ConstraintCount, "radius": sketch.Geometry[0].Radius,
            "solver": sketch.solve()}}
""")
        assert state.success, state.failure_details("inspect")
        assert state.result["count"] == 1
        assert state.result["radius"] == pytest.approx(3)
        assert state.result["solver"] == 0
        repaired = await collector.tools["edit_sketch_constraints"](
            "Reference",
            [
                {"op": "delete_constraint", "constraint_index": 0},
                {"op": "radius", "geometry1": 0, "value": 3},
                {"op": "radius", "geometry1": 0, "value": 4},
                {"op": "delete_constraint", "constraint_index": 1},
            ],
            doc_name=name,
        )
        assert repaired["operations_applied"] == 4
        assert repaired["sketch_status"]["solver"]["solve_code"] == 0
        print(json.dumps({"rollback_state": state.result, "repair_batch_applied": 4}))
        # A previously damaged sketch must not acquire unrelated geometry while
        # its solver remains broken; a subsequent constraint repair is allowed.
        damaged = await bridge.execute_python(f"""
import Sketcher
sketch = FreeCAD.getDocument({name!r}).getObject("Reference")
sketch.addConstraint(Sketcher.Constraint("Radius", 0, 4))
_result_ = sketch.solve()
""")
        assert damaged.success and damaged.result != 0
        circle = {"op": "add_circle", "center_x": 8, "center_y": 0, "radius": 1}
        with pytest.raises(ValueError, match="Sketch edit rejected"):
            await collector.tools["edit_sketch_geometry"](
                "Reference", [circle], doc_name=name
            )
        rejected = await bridge.execute_python(f"""
sketch = FreeCAD.getDocument({name!r}).getObject("Reference")
_result_ = {{"geometry": sketch.GeometryCount, "constraints": sketch.ConstraintCount}}
""")
        assert rejected.success and rejected.result == {"geometry": 1, "constraints": 2}
        await collector.tools["edit_sketch_constraints"](
            "Reference",
            [{"op": "delete_constraint", "constraint_index": 1}],
            doc_name=name,
        )
        continued = await collector.tools["edit_sketch_geometry"](
            "Reference", [circle], doc_name=name
        )
        assert continued["sketch_status"]["geometry_count"] == 2
        assert continued["sketch_status"]["solver"]["solve_code"] == 0
        print(
            json.dumps(
                {
                    "rejected_geometry_state": rejected.result,
                    "repaired_geometry_count": 2,
                }
            )
        )
    finally:
        cleanup = await bridge.execute_python(f"""
if {name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({name!r})
if {setup.result!r} and {setup.result!r} in FreeCAD.listDocuments():
    FreeCAD.setActiveDocument({setup.result!r})
_result_ = True
""")
        await bridge.disconnect()
        assert cleanup.success, cleanup.failure_details("cleanup")


def test_fitted_curve_needs_independent_samples_not_only_fit_points(xmlrpc_proxy):
    result = _experiment(
        xmlrpc_proxy,
        """
# The requirement defines a smooth function, not a supplied point table.
def target(x):
    return FreeCAD.Vector(x, math.sin(x), 0)
sample_x = [0, math.pi, 2 * math.pi]
curve = Part.BSplineCurve()
curve.interpolate([target(x) for x in sample_x])
edge = curve.toShape()
training_error = max(Part.Vertex(target(x)).distToShape(edge)[0] for x in sample_x)
held_out_error = Part.Vertex(target(math.pi / 2)).distToShape(edge)[0]
_result_ = {"valid_curve": edge.isValid(), "training_error": training_error,
            "held_out_error": held_out_error}
""",
    )
    assert result["valid_curve"] is True
    assert result["training_error"] < 1e-7
    assert result["held_out_error"] > 0.9


@pytest.mark.parametrize("sweep_deg", [35.0, 110.0])
def test_bend_sweep_is_not_included_angle(xmlrpc_proxy, sweep_deg):
    result = _experiment(
        xmlrpc_proxy,
        f"""
normal = FreeCAD.Vector(0, 0, 1)
axis = FreeCAD.Vector(1, 0, 0)
correct = FreeCAD.Rotation(axis, {sweep_deg}).multVec(normal)
wrong = FreeCAD.Rotation(axis, 180 - {sweep_deg}).multVec(normal)
_result_ = {{"sweep": math.degrees(normal.getAngle(correct)),
            "angle_confusion_error": math.degrees(correct.getAngle(wrong))}}
""",
    )
    assert result["sweep"] == pytest.approx(sweep_deg)
    assert result["angle_confusion_error"] > 1
