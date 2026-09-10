"""Replay evidence-state transitions without claiming to verify image semantics."""

from copy import deepcopy

import pytest

from freecad_mcp.tools.validation import (
    _SOURCE_ACCEPTANCE_ADAPTER,
    _assess_source_acceptance,
    _merge_source_acceptance,
    _parametric_response,
)


def _manifest():
    return {
        "dimensions": [],
        "requirements": [
            {
                "id": "component_population",
                "kind": "count",
                "status": "verified",
                "expected": 4,
                "observed": 4,
                "passed": True,
                "evidence_references": ["inspection result"],
            }
        ],
        "views": [
            {
                "view_id": "overview",
                "drawing_role": "reference rendering",
                "source_reference": "source.png",
                "candidate_reference": "candidate.png",
                "comparison_image_path": "comparison.png",
                "status": "verified",
                "decision": "accept",
                "image_content_reviewed": True,
                "visual_observation": "The intended interfaces remain visible.",
            }
        ],
    }


def _assess(manifest):
    normalized = _SOURCE_ACCEPTANCE_ADAPTER.validate_python(manifest).model_dump()
    return _assess_source_acceptance(normalized, source_evidence_expected=True)


@pytest.mark.parametrize("review_flag", [False, True])
def test_metadata_repair_changes_completeness_not_machine_verification(review_flag):
    manifest = _manifest()
    manifest["views"][0]["image_content_reviewed"] = review_flag
    original = deepcopy(manifest)
    report = {
        "workflow": "imported_brep_edit",
        "assessment": "healthy",
        "summary": "Imported model; workflow=imported_brep_edit; assessment=healthy.",
        "findings": [],
    }
    before = _merge_source_acceptance(report, _assess(manifest))
    assert before["model_assessment"] == "healthy"
    assert before["assessment"] == "invalid_or_broken"
    assert before["source_acceptance"]["view_records"][0]["missing_or_failed"] == [
        "candidate_recipe",
        "review_attestation",
    ]

    manifest["views"][0].update(
        candidate_recipe={"view_angle": "Isometric"},
        review_attestation="Recorded observation from the existing comparison.",
    )
    after = _merge_source_acceptance(report, _assess(manifest))
    assert after["model_assessment"] == "healthy"
    assert after["assessment"] == "review_recommended"
    assert after["source_acceptance"]["complete"] is True
    for result in [before, after]:
        assert result["source_acceptance"]["verification_scope"] == "caller_attested"
        assert result["source_acceptance"]["machine_verified"] is False
        assert f"Overall assessment={result['assessment']}" in result["summary"]
        assert "model_assessment=healthy" in result["summary"]
        assert "machine_verified=False" in result["summary"]
    assert report["assessment"] == "healthy"  # Merge does not alter baseline data.
    assert original["requirements"] == manifest["requirements"]


@pytest.mark.parametrize(
    "severity,assessment",
    [
        ("error", "invalid_or_broken"),
        ("warning", "review_recommended"),
    ],
)
def test_complete_manifest_cannot_clear_existing_model_findings(severity, assessment):
    manifest = _manifest()
    manifest["views"][0].update(
        candidate_recipe={"view_angle": "Top"},
        review_attestation="Reviewed.",
    )
    finding = {
        "severity": severity,
        "category": "model_diagnostic",
        "message": "Existing finding",
    }
    report = {"assessment": assessment, "findings": [finding]}
    result = _merge_source_acceptance(report, _assess(manifest))
    assert result["assessment"] == assessment
    assert result["model_assessment"] == assessment
    assert finding in result["findings"]
    assert result["source_acceptance"]["machine_verified"] is False


@pytest.mark.parametrize("field,value", [("status", "failed"), ("passed", False)])
def test_view_metadata_does_not_clear_failed_requirement(field, value):
    manifest = _manifest()
    manifest["views"][0].update(
        candidate_recipe={"view_angle": "Top"},
        review_attestation="Reviewed.",
    )
    manifest["requirements"][0][field] = value
    result = _merge_source_acceptance({"assessment": "healthy"}, _assess(manifest))
    assert result["model_assessment"] == "healthy"
    assert result["assessment"] == "invalid_or_broken"
    assert result["source_acceptance"]["requirement_records"][0]["complete"] is False


@pytest.mark.parametrize("level", ["summary", "structure", "full"])
def test_response_preserves_scoped_assessment_at_every_detail_level(level):
    report = _merge_source_acceptance(
        {"assessment": "healthy", "summary": "assessment=healthy."},
        _assess(_manifest()),
    )
    result = _parametric_response(report, level, 0, 1)
    assert result["model_assessment"] == "healthy"
    assert result["assessment"] == "invalid_or_broken"
    assert "Overall assessment=invalid_or_broken" in result["summary"]
    assert result["source_acceptance"]["machine_verified"] is False
