"""Shared MCP guidance identifiers and checkpoint vocabulary.

Detailed engineering policy lives in the repository skill at
``.agents/skills/freecad-engineering/SKILL.md``. This module intentionally keeps
only short routing text and machine-consumed checkpoint constants so prompts,
resources, and client instruction files do not maintain duplicate workflows.
"""

from __future__ import annotations

from typing import Final

ENGINEERING_SKILL_NAME: Final[str] = "freecad-engineering"
ENGINEERING_SKILL_RELATIVE_PATH: Final[str] = (
    ".agents/skills/freecad-engineering/SKILL.md"
)
ENGINEERING_SKILL_RESOURCE_URI: Final[str] = "freecad://skills/freecad-engineering"
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

_SKILL_ROUTER = f"""# Canonical FreeCAD engineering policy

Use the `${ENGINEERING_SKILL_NAME}` repository skill before operating FreeCAD on
a mechanical model. Its canonical file is `{ENGINEERING_SKILL_RELATIVE_PATH}`;
the same text is available through `{ENGINEERING_SKILL_RESOURCE_URI}`.

The skill covers stock/process classification, native editable parametric
structure, milling/turning/sheet-metal strategies, drawing reconstruction,
model modification, lightweight verification, and completion criteria.

After any model creation or geometry change, call
`{FINAL_PARAMETRIC_VALIDATION_TOOL}` immediately before the final user-facing
response and summarize its significant findings. The report is informative, not
a rigid pass/fail workflow. For drawing/sketch reconstruction, first save every
explicit non-starred source dimension under a stable identifier and pass the
complete identifier list as `required_dimension_names`.

`execute_python`, `safe_execute`, and `run_macro` remain available. Their use
does not waive editable/parametric model expectations.
"""

DRAWING_RECONSTRUCTION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER
    + "\nFor drawing reconstruction, also read the skill section "
    "'Reconstruct from drawings or images' and its referenced guidance. "
    "Use `compare_images` after every major feature and before patterning a "
    "single seed element.\n"
)

MODEL_MODIFICATION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER
    + "\nFor an existing model, also read the skill section "
    "'Modify existing models' and inspect the current history before editing.\n"
)

VISUAL_CHECKPOINT_PROTOCOL: Final[str] = (
    _SKILL_ROUTER
    + "\nFollow the Skill's ACT → OBSERVE → REACT loop. Before modeling from a "
    "drawing, establish the front/top/side view map and its FreeCAD XZ/XY/YZ "
    "plane and normal-axis correspondence. After every major feature, compare "
    "the equivalent source and candidate views with `compare_images`; creating "
    "a screenshot alone is not a completed visual checkpoint. Compare a single "
    "seed feature before applying any pattern. If one pair is uncertain, compare "
    "every principal target view available before continuing; a formal checkpoint "
    "ledger remains optional.\n"
)
