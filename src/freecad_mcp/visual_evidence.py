"""Server-session evidence that a document state was visually compared."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

_MAX_RECORDS_PER_DOCUMENT = 32
_COMPARISONS: dict[str, list[dict[str, Any]]] = defaultdict(list)


def record_visual_comparison(
    signature: dict[str, Any],
    *,
    reference_path: str,
    candidate_path: str,
    view_context: str,
) -> dict[str, Any]:
    """Record one successful comparison against the current document signature."""
    document = str(signature.get("document") or "")
    geometry_signature = str(signature.get("geometry_signature") or "")
    if not document or not geometry_signature:
        raise ValueError("Document signature is incomplete")
    record = {
        "document": document,
        "geometry_signature": geometry_signature,
        "reference_path": reference_path,
        "candidate_path": candidate_path,
        "view_context": view_context,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    records = _COMPARISONS[document]
    records.append(record)
    del records[:-_MAX_RECORDS_PER_DOCUMENT]
    return dict(record)


def visual_comparison_status(signature: dict[str, Any] | None) -> dict[str, Any]:
    """Return current/missing/stale comparison evidence for a document state."""
    if not signature:
        return {
            "status": "unavailable",
            "current_comparison_count": 0,
            "recorded_comparison_count": 0,
            "comparisons": [],
        }
    document = str(signature.get("document") or "")
    geometry_signature = str(signature.get("geometry_signature") or "")
    records = list(_COMPARISONS.get(document, []))
    current = [
        dict(record)
        for record in records
        if record.get("geometry_signature") == geometry_signature
    ]
    if current:
        status = "current"
    elif records:
        status = "stale"
    else:
        status = "missing"
    return {
        "status": status,
        "document": document or None,
        "geometry_signature": geometry_signature or None,
        "current_comparison_count": len(current),
        "recorded_comparison_count": len(records),
        "comparisons": current,
    }


def clear_visual_comparisons() -> None:
    """Clear session evidence (used by isolated tests)."""
    _COMPARISONS.clear()
