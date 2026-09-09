"""Tests for the public general-purpose BREP surgery tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.tools.brep import register_brep_tools


@pytest.fixture
def brep_tools() -> tuple[dict[str, object], AsyncMock]:
    mcp = MagicMock()
    registered: dict[str, object] = {}

    def tool_decorator():
        def wrapper(func):
            registered[func.__name__] = func
            return func

        return wrapper

    mcp.tool = tool_decorator
    bridge = AsyncMock()

    async def get_bridge():
        return bridge

    register_brep_tools(mcp, get_bridge)
    return registered, bridge


def _success(payload: dict[str, object]) -> ExecutionResult:
    return ExecutionResult(True, payload, "", "", 12.5)


def test_all_brep_tools_are_registered(brep_tools):
    tools, _ = brep_tools
    assert set(tools) == {
        "group_feature_faces",
        "detect_rotational_pattern",
        "defeature_faces",
        "extract_feature_material",
        "sew_shell",
        "heal_shape",
        "make_solid",
        "polar_pattern_shape",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "kwargs", "code_fragment"),
    [
        (
            "group_feature_faces",
            {"object_name": "ImportedAssembly", "face_names": ["Face1", "Face2"]},
            "edge_to_faces",
        ),
        (
            "detect_rotational_pattern",
            {"object_name": "ImportedAssembly", "face_groups": [["Face1"], ["Face2"]]},
            "expected_pitch = 360.0 / count",
        ),
        (
            "defeature_faces",
            {"object_name": "ImportedAssembly", "face_names": ["Face1"]},
            "source_shape.defeaturing(faces)",
        ),
        (
            "extract_feature_material",
            {"source_name": "ImportedAssembly", "healed_name": "RecoveredSupport"},
            "raw_recovered = left.cut(right)",
        ),
        (
            "sew_shell",
            {"object_names": ["Faces"]},
            "Part.makeShell(faces)",
        ),
        (
            "heal_shape",
            {"object_name": "Broken"},
            "healed.fix(",
        ),
        (
            "make_solid",
            {"object_name": "Shell"},
            "Part.makeSolid(shell)",
        ),
        (
            "polar_pattern_shape",
            {"object_name": "PatternSeed", "occurrences": 4},
            "copy_shape.rotate(origin, axis, pitch * index)",
        ),
    ],
)
async def test_brep_tool_builds_expected_freecad_code(
    brep_tools,
    tool_name,
    kwargs,
    code_fragment,
):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = _success({"name": "Result"})

    result = await tools[tool_name](**kwargs)

    assert result == {"name": "Result"}
    code = bridge.execute_python.call_args.args[0]
    assert code_fragment in code
    assert bridge.execute_python.call_args.kwargs["timeout_ms"] > 0


@pytest.mark.asyncio
async def test_brep_failure_preserves_timeout_diagnostics(brep_tools):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = ExecutionResult(
        success=False,
        result=None,
        stdout="",
        stderr="Execution timed out after 2000ms",
        execution_time_ms=2000.0,
        error_type="TimeoutError",
        operation_state="running",
        continues_running=True,
        transaction_state="unknown",
        request_id="request-7",
    )

    with pytest.raises(ValueError) as error:
        await tools["defeature_faces"](
            object_name="ImportedAssembly",
            face_names=["Face1"],
            timeout_ms=2000,
        )

    message = str(error.value)
    assert "TimeoutError" in message
    assert "operation_state=running" in message
    assert "continues_running=true" in message
    assert "request_id=request-7" in message


@pytest.mark.asyncio
async def test_vector_contract_rejects_wrong_length(brep_tools):
    tools, bridge = brep_tools

    with pytest.raises(ValueError, match="exactly three"):
        await tools["polar_pattern_shape"](
            object_name="PatternSeed",
            occurrences=4,
            axis_direction=[0.0, 1.0],
        )

    bridge.execute_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_defeature_rejects_unchanged_geometry(brep_tools):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = _success({"name": "Result"})

    await tools["defeature_faces"](
        object_name="ImportedAssembly", face_names=["Face1"], doc_name="Model"
    )

    code = bridge.execute_python.call_args.args[0]
    assert "OCCT defeaturing completed without changing" in code
    assert "measurable_change" in code
    no_op_check = code.index("if not measurable_change:")
    refinement = code.index("raw_healed.removeSplitter()")
    assert no_op_check < refinement
    assert "defeatured_counts != base_counts" in code
    assert '"defeatured_topology_counts"' in code
    assert "raw_healed.removeSplitter()" in code
    assert "refine_fallback_reason" in code
    assert "expected_count is not None" in code
    assert "1 is not None" not in code
    assert "'Model' is None" not in code


@pytest.mark.asyncio
async def test_extract_feature_material_supports_fuzzy_cut_and_refine_fallback(
    brep_tools,
):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = _success({"components": []})

    await tools["extract_feature_material"](
        source_name="ImportedAssembly",
        healed_name="RecoveredSupport",
        fuzzy_tolerance=1e-5,
        component_volume_max=100000.0,
        component_sort_by="volume",
        component_limit=1,
    )

    code = bridge.execute_python.call_args.args[0]
    assert "raw_recovered = left.cut(right, 1e-05)" in code
    assert '"container_valid": container_valid' in code
    assert "invalid_component_indices" in code
    assert "Explicitly requested components are invalid" in code
    assert '"total_valid_component_volume"' in code
    assert '"representative_analysis"' in code
    assert '"scope": "all_valid_components_before_selection"' in code
    assert code.index("representative_analysis =") < code.index(
        "selected = selected[:1]"
    )
    assert '"candidate_metrics"' in code
    assert '"volume_spread_relative"' in code
    assert '"auto_selected": None' in code
    assert '"selection_required": True' in code
    assert '"equal_topology_group_inventory"' in code
    assert '"ambiguous_topology_group_tie"' in code
    assert '"largest_group_is_unique"' in code
    assert '"leading_groups"' in code
    assert '"largest_topology_signatures"' in code
    assert '"preferred_topology_signature"' not in code
    assert '"majority_topology_signature"' not in code
    assert "do not choose by signature value" in code
    assert "key=sort_keys['volume']" in code
    assert "selected = selected[:1]" in code
    assert "component_shape = refined" in code


@pytest.mark.asyncio
async def test_extract_feature_material_rejects_inverted_volume_range(brep_tools):
    tools, bridge = brep_tools

    with pytest.raises(ValueError, match="component_volume_min"):
        await tools["extract_feature_material"](
            source_name="ImportedAssembly",
            healed_name="RecoveredSupport",
            component_volume_min=20.0,
            component_volume_max=10.0,
        )

    bridge.execute_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_polar_pattern_uses_single_multi_fuse_when_no_fuzzy_tolerance(
    brep_tools,
):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = _success({"name": "Pattern"})

    await tools["polar_pattern_shape"](
        object_name="PatternSeed", occurrences=4, fuse=True
    )

    code = bridge.execute_python.call_args.args[0]
    assert 'hasattr(copies[0], "multiFuse")' in code
    assert "copies[0].multiFuse(copies[1:])" in code
    assert 'fuse_strategy = "multi_fuse"' in code


@pytest.mark.asyncio
async def test_pattern_and_healing_guard_geometry_before_commit(brep_tools):
    tools, bridge = brep_tools
    bridge.execute_python.return_value = _success({"name": "Guarded"})

    await tools["polar_pattern_shape"](
        object_name="PatternSeed", occurrences=4, refine=True
    )
    pattern_code = bridge.execute_python.call_args.args[0]
    assert "pattern_expected_volume = float(source_shape.Volume) * 4" in pattern_code
    assert "Unfused polar pattern changed the sum of copy volumes" in pattern_code
    assert "_geometry_preservation_check(" in pattern_code
    assert pattern_code.index("refine_geometry_guard") < pattern_code.index(
        "doc.commitTransaction()"
    )
    assert '"pattern_volume_delta"' in pattern_code

    await tools["heal_shape"](object_name="Imported", refine=True)
    heal_code = bridge.execute_python.call_args.args[0]
    assert "Shape healing rejected by geometry-preservation guard" in heal_code
    assert "healing_geometry_guard" in heal_code
    assert heal_code.index("healing_geometry_guard") < heal_code.index("doc.addObject")


def test_geometry_preservation_runtime_rejects_material_drift():
    from freecad_mcp.bridge._geometry_runtime import GEOMETRY_PRESERVATION_RUNTIME

    class Vector:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

        def __sub__(self, other):
            return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

        @property
        def Length(self):
            return (self.x**2 + self.y**2 + self.z**2) ** 0.5

    class Box:
        XMin = YMin = ZMin = 0.0
        XMax = YMax = ZMax = 10.0
        XLength = YLength = ZLength = 10.0

    class Shape:
        def __init__(self, volume):
            self.Volume = volume
            self.BoundBox = Box()
            self.CenterOfMass = Vector(5.0, 5.0, 5.0)
            self.Solids = [object()]

    namespace = {}
    exec(GEOMETRY_PRESERVATION_RUNTIME, namespace)  # noqa: S102
    report = namespace["_geometry_preservation_check"](
        Shape(1000.0), Shape(960.0), 1e-4, 1e-7, 1e-6
    )

    assert report["within_tolerance"] is False
    assert any("volume drift" in issue for issue in report["issues"])
