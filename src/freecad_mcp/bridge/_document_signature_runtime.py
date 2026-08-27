"""Build a compact FreeCAD-side geometry signature for workflow evidence."""

from __future__ import annotations

from textwrap import dedent

DOCUMENT_SIGNATURE_RUNTIME_HELPERS = r'''
def _document_geometry_signature(doc):
    """Fingerprint visible/model shape state without modifying the document."""
    import hashlib
    import json

    shape_objects = []
    body_tips = []
    for obj in getattr(doc, "Objects", []):
        type_id = str(getattr(obj, "TypeId", "") or "")
        if type_id == "PartDesign::Body":
            tip = getattr(obj, "Tip", None)
            body_tips.append(
                {
                    "body": getattr(obj, "Name", None),
                    "tip": getattr(tip, "Name", None) if tip is not None else None,
                }
            )

        shape = getattr(obj, "Shape", None)
        try:
            if shape is None or shape.isNull():
                continue
        except Exception:
            continue

        try:
            shape_hash = int(shape.hashCode())
        except TypeError:
            try:
                shape_hash = int(shape.hashCode(1e-7))
            except Exception:
                shape_hash = None
        except Exception:
            shape_hash = None

        try:
            placement = obj.Placement
            placement_key = [
                round(float(placement.Base.x), 9),
                round(float(placement.Base.y), 9),
                round(float(placement.Base.z), 9),
                *[
                    round(float(value), 12)
                    for value in placement.Rotation.Q
                ],
            ]
        except Exception:
            placement_key = None

        try:
            bounds = shape.BoundBox
            bounds_key = [
                round(float(bounds.XMin), 9),
                round(float(bounds.YMin), 9),
                round(float(bounds.ZMin), 9),
                round(float(bounds.XMax), 9),
                round(float(bounds.YMax), 9),
                round(float(bounds.ZMax), 9),
            ]
        except Exception:
            bounds_key = None

        shape_objects.append(
            {
                "name": getattr(obj, "Name", None),
                "type_id": type_id,
                "shape_hash": shape_hash,
                "shape_type": str(getattr(shape, "ShapeType", "")),
                "solid_count": len(getattr(shape, "Solids", []) or []),
                "face_count": len(getattr(shape, "Faces", []) or []),
                "edge_count": len(getattr(shape, "Edges", []) or []),
                "volume": round(float(getattr(shape, "Volume", 0.0)), 9),
                "area": round(float(getattr(shape, "Area", 0.0)), 9),
                "bounds": bounds_key,
                "placement": placement_key,
            }
        )

    payload = {
        "body_tips": sorted(body_tips, key=lambda item: str(item["body"])),
        "shape_objects": sorted(shape_objects, key=lambda item: str(item["name"])),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "document": getattr(doc, "Name", None),
        "geometry_signature": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "shape_object_count": len(shape_objects),
        "body_tips": payload["body_tips"],
    }
'''


def build_document_signature_code(doc_name: str | None) -> str:
    """Build a read-only script that fingerprints the active or named document."""
    template = r"""
import FreeCAD

__DOCUMENT_SIGNATURE_HELPERS__

doc = FreeCAD.getDocument(__DOC_NAME__) if __DOC_NAME__ else FreeCAD.ActiveDocument
if doc is None:
    raise ValueError("No active document")
_result_ = _document_geometry_signature(doc)
"""
    return (
        dedent(template)
        .replace("__DOCUMENT_SIGNATURE_HELPERS__", DOCUMENT_SIGNATURE_RUNTIME_HELPERS)
        .replace("__DOC_NAME__", repr(doc_name))
    )
