"""Keep generated/discovery documentation aligned with registered MCP APIs."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _decorated_functions(path: Path, decorator_name: str) -> list[ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == decorator_name
            for decorator in node.decorator_list
        ):
            result.append(node)
    return result


def _registered_tool_name(node: ast.AST) -> str:
    """Return the MCP name, honoring ``@mcp.tool(name=...)`` aliases."""
    for decorator in node.decorator_list:  # type: ignore[attr-defined]
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
        ):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "name":
                assert isinstance(keyword.value, ast.Constant)
                assert isinstance(keyword.value.value, str)
                return keyword.value.value
    return node.name  # type: ignore[attr-defined]


def test_tools_overview_contains_every_registered_tool() -> None:
    tool_names: list[str] = []
    for path in sorted((ROOT / "src/freecad_mcp/tools").glob("*.py")):
        tool_names.extend(
            _registered_tool_name(node)
            for node in _decorated_functions(path, "tool")
        )

    text = (ROOT / "docs/guide/tools.md").read_text(encoding="utf-8")
    assert f"**{len(tool_names)} MCP tools**" in text
    assert len(tool_names) == len(set(tool_names))
    missing = [name for name in tool_names if f"`{name}`" not in text]
    assert missing == []


def test_resources_page_contains_every_registered_resource_uri() -> None:
    source = ROOT / "src/freecad_mcp/resources/freecad.py"
    resource_uris: list[str] = []
    for node in _decorated_functions(source, "resource"):
        decorator = next(
            decorator
            for decorator in node.decorator_list  # type: ignore[attr-defined]
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "resource"
        )
        value = decorator.args[0]
        assert isinstance(value, ast.Constant) and isinstance(value.value, str)
        resource_uris.append(value.value)

    text = (ROOT / "docs/guide/resources.md").read_text(encoding="utf-8")
    missing = [uri for uri in resource_uris if f"`{uri}`" not in text]
    assert missing == []


def test_prompts_page_contains_every_registered_prompt() -> None:
    source = ROOT / "src/freecad_mcp/prompts/freecad.py"
    prompt_names = [
        node.name for node in _decorated_functions(source, "prompt")  # type: ignore[attr-defined]
    ]
    text = (ROOT / "docs/guide/prompts.md").read_text(encoding="utf-8")
    assert f"**{len(prompt_names)} MCP prompts**" in text
    missing = [name for name in prompt_names if f"`{name}`" not in text]
    assert missing == []


def test_freecad_engineering_skill_covers_flat_pattern_reconstruction() -> None:
    skill_path = ROOT / ".agents/skills/freecad-engineering/SKILL.md"
    reference_path = (
        ROOT
        / ".agents/skills/freecad-engineering/references"
        / "sheet-metal-flat-patterns.md"
    )

    skill = skill_path.read_text(encoding="utf-8")
    reference = reference_path.read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    normalized_reference = " ".join(reference.split())

    assert reference_path.exists()
    assert "references/sheet-metal-flat-patterns.md" in skill

    # The main Skill must route the agent through the essential reconstruction
    # decisions, not merely mention sheet metal as a supported process.
    for concept in (
        "manufacturing representation rather than an orthographic view",
        "panel regions",
        "fixed/moving panels",
        "relative to the viewed blank face",
        "profile radii",
        "rotate with those panels",
        "apply bend compensation twice",
        "formed state",
        "unfolded state",
    ):
        assert concept in normalized_skill

    # The detailed reference must provide enough information to derive a formed
    # model from a blank without conflating flat and world coordinates.
    for concept in (
        "Separate flat and formed dimension domains",
        "Build a panel-and-bend graph",
        "neutral radius Rn = Ri + K * t",
        "bend allowance BA = theta * (Ri + K * t)",
        "A hole belongs to a panel",
        "constant-thickness quarter-annular",
        "Deep drawing, stretch forming",
        "Never claim a manufacturing-correct flat pattern",
    ):
        assert concept in normalized_reference


def test_freecad_engineering_skill_has_codex_routing_metadata() -> None:
    skill = (
        ROOT / ".agents/skills/freecad-engineering/SKILL.md"
    ).read_text(encoding="utf-8")
    metadata = (
        ROOT / ".agents/skills/freecad-engineering/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: freecad-engineering\n")
    assert "validate_parametric_model" in skill
    assert 'allow_implicit_invocation: true' in metadata
    assert 'value: "freecad"' in metadata
