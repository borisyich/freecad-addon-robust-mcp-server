"""Packaging checks for the canonical FreeCAD engineering Skill bundle."""

import re
import tomllib
from pathlib import Path


def test_engineering_skill_bundle_is_force_included_in_wheel() -> None:
    """The installed MCP package must retain the same canonical Skill bundle."""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    assert force_include[".agents/skills/freecad-engineering"] == (
        "freecad_mcp/skills/freecad-engineering"
    )


def test_every_local_skill_reference_resolves_and_is_exposed_over_mcp() -> None:
    """Follow bundle links; a relocated reference must remain discoverable."""
    from freecad_mcp.guidance import ENGINEERING_SKILL_REFERENCE_FILES

    root = Path(__file__).resolve().parents[2] / ".agents/skills/freecad-engineering"
    exposed = {root / "references" / name for name in ENGINEERING_SKILL_REFERENCE_FILES}
    assert exposed == set((root / "references").glob("*.md"))
    visited = set()
    pending = [root / "SKILL.md"]
    while pending:
        path = pending.pop().resolve()
        if path in visited:
            continue
        visited.add(path)
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("https:", "http:", "#")):
                continue
            linked = (path.parent / target.split("#")[0]).resolve()
            assert linked.is_relative_to(root.resolve()), target
            assert linked.is_file(), (path, target)
            assert linked in {item.resolve() for item in exposed}, target
            pending.append(linked)
    assert {item.resolve() for item in exposed} <= visited
