"""Keep generated/discovery documentation aligned with registered MCP APIs."""

from __future__ import annotations

import ast
import re
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
            _registered_tool_name(node) for node in _decorated_functions(path, "tool")
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
        node.name
        for node in _decorated_functions(source, "prompt")  # type: ignore[attr-defined]
    ]
    text = (ROOT / "docs/guide/prompts.md").read_text(encoding="utf-8")
    assert f"**{len(prompt_names)} MCP prompts**" in text
    missing = [name for name in prompt_names if f"`{name}`" not in text]
    assert missing == []


def test_every_sheet_metal_reference_example_is_live_tested() -> None:
    """The public Sheet Metal recipes must not drift into unexecuted pseudocode."""
    reference = (ROOT / "docs/MCP_TOOLS_REFERENCE.md").read_text(encoding="utf-8")
    section = reference.split("## Sheet Metal Tools", 1)[1].split(
        "## Spreadsheet Tools", 1
    )[0]
    examples = re.findall(r"```python\n(.*?)```", section, flags=re.DOTALL)
    marker = re.compile(
        r"^# Verified by: "
        r"(tests/integration/test_sheetmetal_workflow\.py)::([a-zA-Z0-9_]+)$",
        flags=re.MULTILINE,
    )

    assert len(examples) == 2
    targets: set[str] = set()
    test_source = (ROOT / "tests/integration/test_sheetmetal_workflow.py").read_text(
        encoding="utf-8"
    )
    for example in examples:
        match = marker.search(example)
        assert match is not None, (
            "Every Sheet Metal Python example needs a live-test marker"
        )
        test_name = match.group(2)
        assert f"async def {test_name}(" in test_source
        targets.add(test_name)

        indented = "\n".join(f"    {line}" for line in example.splitlines())
        ast.parse(f"async def _documented_example():\n{indented}\n")

    assert targets == {
        "test_upstream_reference_l_profile_unfolds_to_100_mm_blank",
        "test_semantic_edge_flange_and_unfold_workflow",
    }


def test_freecad_engineering_skill_routes_target_task_files() -> None:
    skill_path = ROOT / ".agents/skills/freecad-engineering/SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    reference_dir = skill_path.parent / "references"
    expected = {
        "model-from-text.md",
        "model-from-drawing.md",
        "machined-and-additive-parts.md",
        "sheet-metal-parts.md",
        "edit-without-history.md",
        "edit-with-history.md",
        "engineering-drawings.md",
    }

    assert {path.name for path in reference_dir.glob("*.md")} == expected
    for filename in expected:
        assert f"references/{filename}" in skill
    assert "Creation routes are composable" in skill
    assert "model-from-drawing.md` and" in skill
    assert "sheet-metal-parts.md" in skill


def test_freecad_engineering_skill_has_codex_routing_metadata() -> None:
    skill = (ROOT / ".agents/skills/freecad-engineering/SKILL.md").read_text(
        encoding="utf-8"
    )
    metadata = (
        ROOT / ".agents/skills/freecad-engineering/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    assert skill.startswith("---\nname: freecad-engineering\n")
    assert "ACT → OBSERVE → REACT" in skill
    assert "validate_parametric_model" in skill
    assert "allow_implicit_invocation: true" in metadata
    assert 'value: "freecad"' in metadata


def test_historyless_edit_reference_requires_local_delta_verification() -> None:
    reference = (
        ROOT
        / ".agents/skills/freecad-engineering/references/edit-without-history.md"
    ).read_text(encoding="utf-8")

    for concept in (
        "capture_shape_checkpoint",
        "compare_shape_checkpoint",
        "select_subshapes",
        "inspect_subshape_neighborhood",
        "defeature_faces",
        "move_faces",
        "Do not reconstruct fake history",
        "smallest local geometric change",
    ):
        assert concept in reference


def test_drawing_and_sheet_metal_references_preserve_key_reasoning() -> None:
    drawing = (
        ROOT / ".agents/skills/freecad-engineering/references/model-from-drawing.md"
    ).read_text(encoding="utf-8")
    sheet = (
        ROOT / ".agents/skills/freecad-engineering/references/sheet-metal-parts.md"
    ).read_text(encoding="utf-8")

    for concept in (
        "view ↔ model-axis contract",
        "Front/Rear | XZ",
        "Top/Bottom | XY",
        "Left/Right | YZ",
        "driving",
        "verification",
        "compare_images",
        "first valid dominant-form candidate",
    ):
        assert concept in drawing

    for concept in (
        "flat domain",
        "formed domain",
        "panel-and-bend plan",
        "K-factor",
        "create_sheet_metal_base",
        "unfold_sheet_metal",
        "deep-drawn",
    ):
        assert concept in sheet

