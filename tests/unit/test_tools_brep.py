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
            {"object_name": "Impeller", "face_names": ["Face1", "Face2"]},
            "edge_to_faces",
        ),
        (
            "detect_rotational_pattern",
            {"object_name": "Impeller", "face_groups": [["Face1"], ["Face2"]]},
            "expected_pitch = 360.0 / count",
        ),
        (
            "defeature_faces",
            {"object_name": "Impeller", "face_names": ["Face1"]},
            "source_shape.defeaturing(faces)",
        ),
        (
            "extract_feature_material",
            {"source_name": "Impeller", "healed_name": "Core"},
            "source_shape.cut(healed)",
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
            {"object_name": "Blade", "occurrences": 5},
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
            object_name="Impeller",
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
            object_name="Blade",
            occurrences=5,
            axis_direction=[0.0, 1.0],
        )

    bridge.execute_python.assert_not_awaited()
