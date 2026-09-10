"""Shared MCP guidance identifiers and checkpoint vocabulary.

Detailed engineering policy lives in the repository skill at
``.agents/skills/freecad-engineering/SKILL.md``. This module intentionally keeps
only short routing text and machine-consumed checkpoint constants so prompts,
resources, and client instruction files do not maintain duplicate workflows.
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
    "design-and-verification.md",
    "drawing-reconstruction.md",
    "manufacturing-strategies.md",
    "model-editing.md",
    "sheet-metal-flat-patterns.md",
    "sketch-construction.md",
    "source-notes.md",
    "validation-and-editability.md",
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

_SKILL_ROUTER = f"""# Canonical FreeCAD engineering policy

Use the `${ENGINEERING_SKILL_NAME}` repository skill before operating FreeCAD on
a mechanical model. Its canonical file is `{ENGINEERING_SKILL_RELATIVE_PATH}`;
the same text is available through `{ENGINEERING_SKILL_RESOURCE_URI}`.

The skill connects functional requirements, interfaces, datums, manufacturing
assumptions, editable dependencies, and measurable acceptance. Select the
representation and checks for the actual deliverable.

After any model creation or geometry change, call
`{FINAL_PARAMETRIC_VALIDATION_TOOL}` immediately before the final user-facing
response and summarize its significant findings. The report is informative, not
a rigid pass/fail workflow. For any task that uses a drawing/sketch as geometry
evidence, including reconstruction or an edit, first inventory every source
view/detail/section that depicts part geometry, including apparently
redundant/corroborative views, and save every explicit source dimension under
a stable identifier. Preserve and interpret drafting markers such as an
asterisk, parentheses, REF, or TYP; they never make an annotation optional. Each
dimension must map to its source view and semantic geometric references and be
classified as driving or verification; `source_issue` is exceptional and
requires concrete source evidence. Never use `unresolved` as a terminal manifest
role. Pass the complete `acceptance_manifest` to the final validator; it
derives every driving ID and checks final evidence for every driving,
verification, and source-view record. Legacy `required_dimension_names` alone is
not complete drawing acceptance.

When the deliverable is a sketch rather than a final solid, pass
`target={{"kind":"sketch","name":"..."}}` so required dimensions are traced to
that sketch's non-construction geometry and Body/solid/Tip state is out of scope.

`execute_python`, `safe_execute`, and `run_macro` remain available. Their use
does not waive editable/parametric model expectations.
"""

DRAWING_RECONSTRUCTION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER + "\nFor drawing reconstruction, also read the skill section "
    "'Reconstruct from drawings or images' and its referenced guidance. Before "
    "modeling, inventory every source view and dimension. Use `compare_images` "
    "after every major feature against the source views that expose that feature, "
    "and before patterning a single seed element. Surface and inspect every "
    "returned comparison ImageContent block; text metadata or a saved file alone "
    "is not visual review. Before final acceptance, "
    "reproduce and compare every source-view manifest record one-to-one, including "
    "sections/details/opposite-side views when present.\n"
)

MODEL_MODIFICATION_WORKFLOW: Final[str] = (
    _SKILL_ROUTER + "\nFor an existing model, also read the skill section "
    "'Modify existing models' in references/model-editing.md and inspect the "
    "current history, local neighborhood, and invariants before editing. "
    "When a drawing/image supplies geometry evidence for the edit, also apply the "
    "complete source-view/dimension manifest and final one-to-one view validation "
    "rules from 'Reconstruct from drawings or images' to the edited model.\n"
)

VISUAL_CHECKPOINT_PROTOCOL: Final[str] = (
    _SKILL_ROUTER
    + "\nUse the Skill's observe/predict/edit/verify/recover loop; ACT → OBSERVE → REACT "
    "is only its abbreviated feedback pattern. Before modeling from a "
    "drawing, establish a complete manifest for every source view, including its "
    "FreeCAD camera/section recipe and plane/normal correspondence when applicable. "
    "After every major feature, compare the equivalent source/candidate views that "
    "can expose that feature; creating a screenshot alone is not a completed visual "
    "checkpoint. Compare a single seed feature before applying any pattern. Before "
    "final acceptance, reproduce and compare every source-view manifest record "
    "one-to-one. A formal checkpoint ledger remains optional.\n"
)
