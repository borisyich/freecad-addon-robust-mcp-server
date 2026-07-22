"""Deterministic checkpoint gates for agentic CAD workflows."""

from __future__ import annotations

from typing import Any

from freecad_mcp.guidance import (
    BLOCKING_DISCREPANCY_CATEGORIES,
    DISCREPANCY_LEDGER_FIELDS,
    UNCERTAINTY_CATEGORIES,
)

_VALID_SEVERITIES = {"info", "minor", "major", "critical"}


def _normalize_discrepancy(item: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize one model-authored discrepancy ledger entry."""
    category = str(item.get("category", "unspecified")).strip().lower()
    severity = str(item.get("severity", "major")).strip().lower()
    if severity not in _VALID_SEVERITIES:
        severity = "major"

    normalized = {
        "index": index,
        "category": category,
        "severity": severity,
        "expected": item.get("expected"),
        "observed": item.get("observed"),
        "evidence": item.get("evidence"),
        "proposed_reaction": item.get("proposed_reaction"),
    }
    normalized["missing_fields"] = [
        field
        for field in DISCREPANCY_LEDGER_FIELDS
        if normalized.get(field) is None or str(normalized.get(field)).strip() == ""
    ]
    return normalized


def register_checkpoint_tools(mcp: Any) -> None:
    """Register workflow checkpoint tools that do not require a FreeCAD bridge."""

    @mcp.tool()
    async def evaluate_model_checkpoint(
        checkpoint_name: str,
        geometry_valid: bool,
        solid_count: int | None = None,
        expected_solid_count: int | None = 1,
        dimension_checks_passed: bool = True,
        visual_comparison_performed: bool = False,
        view_match_confirmed: bool = True,
        unresolved_dimensions: list[str] | None = None,
        discrepancies: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Convert observation evidence into a mandatory workflow decision.

        Call this after a major modeling feature, after geometric validation and
        visual comparison. The tool does not inspect pixels itself; it applies a
        deterministic stop policy to the agent-authored discrepancy ledger.

        Args:
            checkpoint_name: Human-readable feature/checkpoint identifier.
            geometry_valid: Whether FreeCAD geometry validation passed.
            solid_count: Current number of solids when known.
            expected_solid_count: Intended number of solids; usually one.
            dimension_checks_passed: Whether measured dimensions/volume effects pass.
            visual_comparison_performed: Whether screenshot/open/compare was completed.
            view_match_confirmed: Whether reference and candidate use equivalent views.
            unresolved_dimensions: Required values that remain unreadable or ambiguous.
            discrepancies: Ledger entries containing category, severity, expected,
                observed, evidence, and proposed_reaction.

        Returns:
            A deterministic decision: ``continue`` or ``rework``.
            ``can_continue`` is true only for ``continue``.
        """
        unresolved = [str(value).strip() for value in (unresolved_dimensions or [])]
        unresolved = [value for value in unresolved if value]
        normalized = [
            _normalize_discrepancy(item, index)
            for index, item in enumerate(discrepancies or [], start=1)
        ]

        rework_reasons: list[str] = []
        unresolved_reasons: list[str] = []
        warnings: list[str] = []

        if not geometry_valid:
            rework_reasons.append("FreeCAD geometry validation failed")

        if (
            solid_count is not None
            and expected_solid_count is not None
            and solid_count != expected_solid_count
        ):
            rework_reasons.append(
                f"solid count is {solid_count}; expected {expected_solid_count}"
            )

        if not dimension_checks_passed:
            rework_reasons.append("one or more dimensional or volume checks failed")

        if not visual_comparison_performed:
            rework_reasons.append(
                "visual checkpoint was not completed with saved/opened pixels and comparison"
            )

        if not view_match_confirmed:
            rework_reasons.append("reference and candidate views are not equivalent")

        if unresolved:
            unresolved_reasons.append(
                "required dimensions or interpretations remain unresolved: "
                + ", ".join(unresolved)
            )

        for item in normalized:
            category = item["category"]
            severity = item["severity"]
            if item["missing_fields"]:
                rework_reasons.append(
                    f"discrepancy #{item['index']} has incomplete ledger fields: "
                    + ", ".join(item["missing_fields"])
                )
            if category in UNCERTAINTY_CATEGORIES:
                unresolved_reasons.append(
                    f"discrepancy #{item['index']} requires user clarification: {category}"
                )
            elif category in BLOCKING_DISCREPANCY_CATEGORIES:
                rework_reasons.append(
                    f"blocking discrepancy #{item['index']}: {category}"
                )
            elif severity in {"major", "critical"}:
                rework_reasons.append(
                    f"{severity} discrepancy #{item['index']}: {category}"
                )
            elif severity == "minor":
                warnings.append(f"minor discrepancy #{item['index']}: {category}")

        if rework_reasons:
            decision = "rework"
            required_action = (
                "Do not create the next feature. Undo or remove only the failed "
                "feature, confirm the previous valid Body Tip/state is restored, "
                "correct the cause, and repeat this checkpoint."
            )
        elif unresolved_reasons:
            decision = "rework"
            required_action = (
                "Stop modeling and ask the user for the unresolved dimensions or "
                "interpretation before changing the model further."
            )
        else:
            decision = "continue"
            required_action = "Checkpoint accepted; proceed to the next planned feature."

        return {
            "checkpoint_name": checkpoint_name,
            "decision": decision,
            "can_continue": decision == "continue",
            "required_action": required_action,
            "rework_reasons": rework_reasons,
            "unresolved_reasons": unresolved_reasons,
            "warnings": warnings,
            "unresolved_dimensions": unresolved,
            "discrepancies": normalized,
            "required_ledger_fields": list(DISCREPANCY_LEDGER_FIELDS),
            "policy": {
                "blocking_categories": sorted(BLOCKING_DISCREPANCY_CATEGORIES),
                "uncertainty_categories": sorted(UNCERTAINTY_CATEGORIES),
            },
        }
