"""Tests for the shared PartDesign sketch-feature end-condition contract."""

from typing import Literal

import pytest

from freecad_mcp.tools._partdesign_end_conditions import (
    PARTDESIGN_END_CONDITION_RUNTIME,
    prepare_partdesign_end_condition,
)


def test_additive_through_all_maps_to_native_up_to_last() -> None:
    condition = prepare_partdesign_end_condition(
        "ThroughAll",
        bounded_type="Length",
        operation="additive",
        up_to_face=None,
    )

    assert condition.requested_type == "ThroughAll"
    assert condition.native_type == "UpToLast"
    assert condition.up_to_face is None


def test_subtractive_through_all_preserves_native_name() -> None:
    condition = prepare_partdesign_end_condition(
        "ThroughAll",
        bounded_type="Angle",
        operation="subtractive",
        up_to_face=None,
    )

    assert condition.native_type == "ThroughAll"


@pytest.mark.parametrize("bounded_type", ["Length", "Angle"])
def test_up_to_face_requires_strict_feature_face_reference(
    bounded_type: Literal["Length", "Angle"],
) -> None:
    with pytest.raises(ValueError, match="requires up_to_face"):
        prepare_partdesign_end_condition(
            "UpToFace",
            bounded_type=bounded_type,
            operation="additive",
            up_to_face=None,
        )
    with pytest.raises(ValueError, match=r"Feature\.FaceN"):
        prepare_partdesign_end_condition(
            "UpToFace",
            bounded_type=bounded_type,
            operation="additive",
            up_to_face="Target.Edge1",
        )


def test_up_to_face_is_rejected_for_other_modes() -> None:
    with pytest.raises(ValueError, match="valid only"):
        prepare_partdesign_end_condition(
            "Length",
            bounded_type="Length",
            operation="additive",
            up_to_face="Target.Face1",
        )


def test_runtime_validates_native_enum_and_face_existence() -> None:
    assert "getEnumerationsOfProperty" in PARTDESIGN_END_CONDITION_RUNTIME
    assert "does not support end condition" in PARTDESIGN_END_CONDITION_RUNTIME
    assert "Available faces: Face1..Face{available}" in (
        PARTDESIGN_END_CONDITION_RUNTIME
    )
    compile(PARTDESIGN_END_CONDITION_RUNTIME, "<end-condition-runtime>", "exec")
