"""Tests for deterministic model checkpoint decisions."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def registered_tools():
    """Register checkpoint tools on a mock MCP server."""
    from freecad_mcp.tools.checkpoints import register_checkpoint_tools

    mcp = MagicMock()
    mcp._registered_tools = {}

    def tool_decorator():
        def wrapper(func):
            mcp._registered_tools[func.__name__] = func
            return func

        return wrapper

    mcp.tool = tool_decorator
    register_checkpoint_tools(mcp)
    return mcp._registered_tools


@pytest.mark.asyncio
async def test_checkpoint_allows_continue_when_all_gates_pass(registered_tools):
    result = await registered_tools["evaluate_model_checkpoint"](
        checkpoint_name="Pad_Base",
        geometry_valid=True,
        solid_count=1,
        expected_solid_count=1,
        dimension_checks_passed=True,
        visual_comparison_performed=True,
        view_match_confirmed=True,
        discrepancies=[
            {
                "category": "rendering_difference",
                "severity": "minor",
                "expected": "black edges",
                "observed": "gray antialiasing",
                "evidence": "comparison.png",
                "proposed_reaction": "ignore rendering-only difference",
            }
        ],
    )

    assert result["decision"] == "continue"
    assert result["can_continue"] is True
    assert result["warnings"]


@pytest.mark.asyncio
async def test_checkpoint_requires_rework_for_blocking_discrepancy(registered_tools):
    result = await registered_tools["evaluate_model_checkpoint"](
        checkpoint_name="MountingHoles",
        geometry_valid=True,
        solid_count=1,
        visual_comparison_performed=True,
        discrepancies=[
            {
                "category": "wrong_count",
                "severity": "minor",
                "expected": "4 holes",
                "observed": "3 holes",
                "evidence": "front_compare.png",
                "proposed_reaction": "recreate pattern",
            }
        ],
    )

    assert result["decision"] == "rework"
    assert result["can_continue"] is False
    assert "wrong_count" in " ".join(result["rework_reasons"])


@pytest.mark.asyncio
async def test_checkpoint_asks_user_for_unresolved_dimension(registered_tools):
    result = await registered_tools["evaluate_model_checkpoint"](
        checkpoint_name="WallThickness",
        geometry_valid=True,
        visual_comparison_performed=True,
        unresolved_dimensions=["wall thickness near Detail C"],
    )

    assert result["decision"] == "rework"
    assert result["can_continue"] is False
    assert result["unresolved_reasons"]


@pytest.mark.asyncio
async def test_rework_has_priority_over_user_question(registered_tools):
    result = await registered_tools["evaluate_model_checkpoint"](
        checkpoint_name="Pocket",
        geometry_valid=False,
        unresolved_dimensions=["pocket depth"],
    )

    assert result["decision"] == "rework"
    assert result["rework_reasons"]
    assert result["unresolved_reasons"]


@pytest.mark.asyncio
async def test_checkpoint_rejects_missing_visual_observation(registered_tools):
    result = await registered_tools["evaluate_model_checkpoint"](
        checkpoint_name="Pad",
        geometry_valid=True,
    )

    assert result["decision"] == "rework"
    assert "visual checkpoint" in " ".join(result["rework_reasons"])
