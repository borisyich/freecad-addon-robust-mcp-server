"""Shared end-condition contract for native sketch-based PartDesign features."""

from __future__ import annotations

import re
from dataclasses import dataclass
from textwrap import dedent
from typing import Literal, TypeAlias

LinearEndCondition: TypeAlias = Literal["Length", "ThroughAll", "UpToFirst", "UpToFace"]
AngularEndCondition: TypeAlias = Literal["Angle", "ThroughAll", "UpToFirst", "UpToFace"]

_FACE_REFERENCE = re.compile(r"^[^.]+\.Face[1-9]\d*$")


@dataclass(frozen=True, slots=True)
class PartDesignEndCondition:
    """Validated public and native representations of one end condition."""

    requested_type: str
    native_type: str
    up_to_face: str | None


def prepare_partdesign_end_condition(
    requested_type: str,
    *,
    bounded_type: Literal["Length", "Angle"],
    operation: Literal["additive", "subtractive"],
    up_to_face: str | None,
) -> PartDesignEndCondition:
    """Validate one public condition and map additive ThroughAll to UpToLast."""
    allowed = {bounded_type, "ThroughAll", "UpToFirst", "UpToFace"}
    if requested_type not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"Unsupported end condition {requested_type!r}; use {choices}")
    if requested_type == "UpToFace":
        if not up_to_face:
            raise ValueError('type="UpToFace" requires up_to_face="Feature.FaceN"')
        if _FACE_REFERENCE.fullmatch(up_to_face) is None:
            raise ValueError('up_to_face must use the form "Feature.FaceN"')
    elif up_to_face is not None:
        raise ValueError('up_to_face is valid only for type="UpToFace"')

    native_type = (
        "UpToLast"
        if operation == "additive" and requested_type == "ThroughAll"
        else requested_type
    )
    return PartDesignEndCondition(requested_type, native_type, up_to_face)


PARTDESIGN_END_CONDITION_RUNTIME = dedent(
    r"""
    def _resolve_partdesign_up_to_face(doc, reference):
        if reference is None:
            return None
        object_name, element_name = reference.rsplit(".", 1)
        target = doc.getObject(object_name)
        if target is None:
            raise ValueError(f"Up-to-face object not found: {object_name!r}")
        shape = getattr(target, "Shape", None)
        face_index = int(element_name[4:])
        if shape is None or shape.isNull() or face_index > len(shape.Faces):
            available = 0 if shape is None or shape.isNull() else len(shape.Faces)
            raise ValueError(
                f"Face not found: {object_name}.{element_name}. "
                f"Available faces: Face1..Face{available}"
            )
        return (target, [element_name])


    def _configure_partdesign_end_condition(
        doc,
        feature,
        requested_type,
        native_type,
        up_to_face,
    ):
        try:
            available_types = list(feature.getEnumerationsOfProperty("Type"))
        except Exception:
            available_types = []
        if available_types and native_type not in available_types:
            raise ValueError(
                f"{feature.TypeId} does not support end condition "
                f"{native_type!r} in this FreeCAD build; "
                f"available={available_types!r}"
            )
        feature.Type = native_type
        resolved_face = _resolve_partdesign_up_to_face(doc, up_to_face)
        if resolved_face is not None:
            feature.UpToFace = resolved_face
        return {
            "type": requested_type,
            "native_type": native_type,
            "up_to_face": up_to_face,
        }
    """
).strip()
