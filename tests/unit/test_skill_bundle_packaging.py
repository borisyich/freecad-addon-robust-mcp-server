"""Packaging checks for the canonical FreeCAD engineering Skill bundle."""

import tomllib
from pathlib import Path


def test_engineering_skill_bundle_is_force_included_in_wheel() -> None:
    """The installed MCP package must retain the same canonical Skill bundle."""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    assert force_include[".agents/skills/freecad-engineering"] == (
        "freecad_mcp/skills/freecad-engineering"
    )
