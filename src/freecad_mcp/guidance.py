"""Shared identifiers and compact routing text for FreeCAD engineering guidance.

Detailed engineering policy lives only in the canonical repository skill bundle
under ``.agents/skills/freecad-engineering``. MCP instructions, prompts and
resources should route to that bundle rather than duplicate its workflows.
"""

from __future__ import annotations

from typing import Final

ENGINEERING_SKILL_NAME: Final[str] = "freecad-engineering"
ENGINEERING_SKILL_BUNDLE_RELATIVE_PATH: Final[str] = (
    ".agents/skills/freecad-engineering"
)
ENGINEERING_SKILL_RELATIVE_PATH: Final[str] = (
    ".agents/skills/freecad-engineering/SKILL.md"
)
ENGINEERING_SKILL_RESOURCE_URI: Final[str] = "freecad://skills/freecad-engineering"
ENGINEERING_SKILL_BUNDLE_RESOURCE_URI: Final[str] = (
    f"{ENGINEERING_SKILL_RESOURCE_URI}/bundle"
)
ENGINEERING_SKILL_AGENT_METADATA_FILE: Final[str] = "agents/openai.yaml"
ENGINEERING_SKILL_REFERENCE_FILES: Final[tuple[str, ...]] = (
    "model-from-text.md",
    "model-from-drawing.md",
    "machined-and-additive-parts.md",
    "sheet-metal-parts.md",
    "edit-without-history.md",
    "edit-with-history.md",
    "engineering-drawings.md",
)
FINAL_PARAMETRIC_VALIDATION_TOOL: Final[str] = "validate_parametric_model"

CHECKPOINT_DECISIONS: Final[tuple[str, ...]] = (
    "continue",
    "rework",
)

BLOCKING_DISCREPANCY_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "geometry_invalid",
        "missing_element",
        "extra_element",
        "wrong_count",
        "wrong_dimension",
        "wrong_position",
        "wrong_orientation",
        "wrong_profile",
        "wrong_bend",
        "silhouette_mismatch",
        "view_mismatch",
        "topology_mismatch",
        "tangent_constraint_conflict",
        "dimension_chain_mismatch",
    }
)

UNCERTAINTY_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "unreadable_dimension",
        "ambiguous_geometry",
        "insufficient_evidence",
        "conflicting_views",
    }
)

DISCREPANCY_LEDGER_FIELDS: Final[tuple[str, ...]] = (
    "category",
    "severity",
    "expected",
    "observed",
    "evidence",
    "proposed_reaction",
)

_SKILL_ROUTER: Final[str] = f"""Use `${ENGINEERING_SKILL_NAME}` for FreeCAD
engineering work. Read `{ENGINEERING_SKILL_RESOURCE_URI}` first, then only the
reference file(s) selected by its task router. Detailed workflow policy belongs
in the Skill bundle, not in MCP prompts.

After geometry changes, verify the requested result and run
`{FINAL_PARAMETRIC_VALIDATION_TOOL}` before the final response. For imported or
direct B-rep edits, use shape checkpoints as specified by the selected reference.
"""

DRAWING_RECONSTRUCTION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER
    + "\nFor drawing reconstruction read "
    f"`{ENGINEERING_SKILL_RESOURCE_URI}/references/model-from-drawing.md` and "
    "the applicable manufacturing reference.\n"
)

MODEL_MODIFICATION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER
    + "\nFor model modification, inspect whether editable history exists, then read "
    f"`{ENGINEERING_SKILL_RESOURCE_URI}/references/edit-with-history.md` or "
    f"`{ENGINEERING_SKILL_RESOURCE_URI}/references/edit-without-history.md`.\n"
)

VISUAL_CHECKPOINT_PROTOCOL: Final[str] = (
    _SKILL_ROUTER
    + "\nUse visual comparison only where geometry/orientation/source correspondence "
    "cannot be established deterministically. Drawing reconstruction has its own "
    "mandatory view-comparison rules in `model-from-drawing.md`.\n"
)
