"""Validation tools for FreeCAD Robust MCP Server.

This module provides tools for validating FreeCAD objects and documents,
checking for errors, and providing automatic rollback capabilities.

These tools are essential for robust CAD workflows where operations
may fail or create invalid geometry.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from freecad_mcp.bridge._parametric_validation_runtime import (
    build_parametric_validation_code,
)


class SketchValidationTarget(BaseModel):
    """Restrict parametric validation to one Sketcher sketch."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["sketch"]
    name: str = Field(
        min_length=1,
        description="Internal FreeCAD Name of the Sketcher::SketchObject to validate.",
    )


_VALIDATION_TARGET_ADAPTER = TypeAdapter(SketchValidationTarget)


def _finding_page(
    findings: list[dict[str, Any]], offset: int, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = len(findings)
    page = findings[offset : offset + page_size]
    next_offset = offset + len(page) if offset + len(page) < total else None
    return page, {
        "offset": offset,
        "page_size": page_size,
        "returned": len(page),
        "total": total,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }


def _compact_dimension_inventory(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "provided": value.get("provided", False),
        "required_names": value.get("required_names", []),
        "all_used": value.get("all_used", False),
        "usage": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "sketch_match_count": len(item.get("sketch_constraints") or []),
                "spreadsheet_match_count": len(
                    item.get("spreadsheet_parameters") or []
                ),
            }
            for item in value.get("usage", [])
        ],
    }


def _parametric_response(
    report: dict[str, Any],
    detail_level: str,
    finding_offset: int,
    finding_limit: int,
) -> dict[str, Any]:
    """Project the full validator report into an agent-sized response."""
    findings = list(report.get("findings") or [])
    finding_page, pagination = _finding_page(findings, finding_offset, finding_limit)
    if detail_level == "full":
        result = dict(report)
        result["detail_level"] = "full"
        result["response_guidance"] = (
            "Full validation includes feature history, expressions, Spreadsheet "
            "cells, and optionally every sketch constraint. Request it only for "
            "a focused structural diagnosis after reviewing summary/structure."
        )
        return result

    severity_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity", "unknown"))
        category = str(finding.get("category", "unknown"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1

    result = {
        "informational": report.get("informational", True),
        "workflow": report.get("workflow", "native_parametric"),
        "assessment": report.get("assessment"),
        "summary": report.get("summary"),
        "detail_level": detail_level,
        "validation_target": report.get("validation_target", {"kind": "model"}),
        "target_sketch": report.get("target_sketch"),
        "document": report.get("document"),
        "counts": report.get("counts", {}),
        "sketch_solver_status_counts": report.get("sketch_solver_status_counts", {}),
        "dimension_inventory": _compact_dimension_inventory(
            report.get("dimension_inventory") or {}
        ),
        "finding_counts": {
            "by_severity": severity_counts,
            "by_category": category_counts,
        },
        "findings": finding_page,
        "finding_pagination": pagination,
        "completion_guidance": report.get("completion_guidance", {}),
        "limitations": report.get("limitations", []),
    }
    if detail_level == "structure":
        result.update(
            {
                "bodies": report.get("bodies", []),
                "standalone_sketches": report.get("standalone_sketches", []),
                "uncontained_shape_objects": report.get(
                    "uncontained_shape_objects", []
                ),
                "spreadsheets": report.get("spreadsheets", []),
            }
        )
    return result


def register_validation_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register validation-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    shape_checkpoints: dict[str, dict[str, Any]] = {}

    @mcp.tool()
    async def capture_shape_checkpoint(
        checkpoint_name: str,
        object_name: str,
        doc_name: str | None = None,
        recompute: bool = True,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Capture an in-memory B-rep baseline; example: checkpoint_name="before_holes", object_name="Body". Use compare_shape_checkpoint after the edit.

        The checkpoint is server-session-local and does not modify the FreeCAD
        document. It records validity, bounds, volume, area, topology counts,
        and the exact serialized Shape used by the later comparison.
        """
        normalized_name = checkpoint_name.strip()
        if not normalized_name:
            raise ValueError("checkpoint_name must not be empty")
        if len(normalized_name) > 80:
            raise ValueError("checkpoint_name must not exceed 80 characters")
        if not object_name.strip():
            raise ValueError("object_name must not be empty")
        if normalized_name in shape_checkpoints and not overwrite:
            raise ValueError(
                f"Shape checkpoint already exists: {normalized_name!r}; "
                "set overwrite=true to replace it"
            )
        if normalized_name not in shape_checkpoints and len(shape_checkpoints) >= 32:
            raise ValueError(
                "Shape checkpoint limit (32) reached; overwrite an existing "
                "checkpoint or restart the server session"
            )

        bridge = await get_bridge()
        code = f"""
import FreeCAD
import Part

def _shape_metrics(shape):
    box = shape.BoundBox
    return {{
        "valid": bool(shape.isValid()),
        "shape_type": str(shape.ShapeType),
        "solid_count": len(shape.Solids),
        "shell_count": len(shape.Shells),
        "face_count": len(shape.Faces),
        "edge_count": len(shape.Edges),
        "vertex_count": len(shape.Vertexes),
        "volume": float(shape.Volume),
        "area": float(shape.Area),
        "bounding_box": {{
            "min": [float(box.XMin), float(box.YMin), float(box.ZMin)],
            "max": [float(box.XMax), float(box.YMax), float(box.ZMax)],
            "size": [float(box.XLength), float(box.YLength), float(box.ZLength)],
        }},
    }}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
if {recompute!r}:
    doc.recompute()
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
shape = getattr(obj, "Shape", None)
if shape is None or shape.isNull():
    raise ValueError(f"Object has no usable Shape: {object_name!r}")
source_metrics = _shape_metrics(shape)
shape_placement = shape.Placement
brep = shape.exportBrepToString()
baseline = Part.Shape()
baseline.importBrepFromString(brep)
if baseline.isNull():
    raise ValueError("Serialized checkpoint Shape could not be restored")
baseline_metrics = _shape_metrics(baseline)

def _close(first, second, absolute=1e-7, relative=1e-11):
    return abs(first - second) <= max(
        absolute,
        relative * max(abs(first), abs(second)),
    )

round_trip_errors = []
for name in ("shape_type", "solid_count", "shell_count", "face_count", "edge_count", "vertex_count", "valid"):
    if source_metrics[name] != baseline_metrics[name]:
        round_trip_errors.append(
            "%s: source=%r restored=%r" % (
                name,
                source_metrics[name],
                baseline_metrics[name],
            )
        )
for name in ("volume", "area"):
    if not _close(source_metrics[name], baseline_metrics[name]):
        round_trip_errors.append(
            "%s: source=%r restored=%r" % (
                name,
                source_metrics[name],
                baseline_metrics[name],
            )
        )
placement_probes = (
    FreeCAD.Vector(0.0, 0.0, 0.0),
    FreeCAD.Vector(1.0, 0.0, 0.0),
    FreeCAD.Vector(0.0, 1.0, 0.0),
    FreeCAD.Vector(0.0, 0.0, 1.0),
)
placement_max_error = max(
    (
        shape.Placement.multVec(point)
        - baseline.Placement.multVec(point)
    ).Length
    for point in placement_probes
)
if placement_max_error > 1e-9:
    round_trip_errors.append(
        "placement_transform: max_probe_error=%r" % placement_max_error
    )
bbox_errors = [
    abs(source_metrics["bounding_box"][key][index] - baseline_metrics["bounding_box"][key][index])
    for key in ("min", "max", "size")
    for index in range(3)
]
if round_trip_errors:
    raise ValueError(
        "Checkpoint BREP round-trip changed Shape metrics: "
        + "; ".join(round_trip_errors)
    )
_result_ = {{
    "success": True,
    "document": doc.Name,
    "object_name": obj.Name,
    "metrics": source_metrics,
    "shape_placement": {{
        "base": [
            float(shape_placement.Base.x),
            float(shape_placement.Base.y),
            float(shape_placement.Base.z),
        ],
        "rotation_quaternion": [float(value) for value in shape_placement.Rotation.Q],
    }},
    "round_trip_verified": True,
    "round_trip_max_bbox_error": max(bbox_errors),
    "round_trip_max_placement_error": placement_max_error,
    "_brep": brep,
}}
"""
        execution = await bridge.execute_python(code)
        if not execution.success or not isinstance(execution.result, dict):
            raise ValueError(
                execution.error_traceback or "Failed to capture shape checkpoint"
            )
        payload = dict(execution.result)
        brep = payload.pop("_brep", None)
        if not isinstance(brep, str) or not brep:
            raise ValueError("FreeCAD did not return a serialized checkpoint Shape")
        shape_checkpoints[normalized_name] = {
            "brep": brep,
            "document": payload.get("document"),
            "object_name": payload.get("object_name"),
            "metrics": payload.get("metrics"),
            "shape_placement": payload.get("shape_placement"),
        }
        payload["checkpoint_name"] = normalized_name
        payload["storage"] = "server_session_memory"
        payload["checkpoint_count"] = len(shape_checkpoints)
        return payload

    @mcp.tool()
    async def compare_shape_checkpoint(
        checkpoint_name: str,
        object_name: str | None = None,
        doc_name: str | None = None,
        recompute: bool = True,
        volume_tolerance: float = 1e-7,
        linear_tolerance: float = 1e-7,
        difference_mode: Literal["auto", "exact", "metrics"] = "auto",
        exact_face_product_limit: int = 10000,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """Compare current geometry with a captured B-rep; example: checkpoint_name="before_holes", object_name="Body". Reports added/removed regions and metric deltas.

        This is a read-only invariant check for direct edits. ``auto`` avoids
        whole-shape OCCT cuts when the product of before/after face counts exceeds
        ``exact_face_product_limit``. Use ``exact`` to force localized symmetric
        Shape differences or ``metrics`` to avoid booleans entirely.
        """
        normalized_name = checkpoint_name.strip()
        snapshot = shape_checkpoints.get(normalized_name)
        if snapshot is None:
            available = sorted(shape_checkpoints)
            raise ValueError(
                f"Shape checkpoint not found: {normalized_name!r}; "
                f"available={available}"
            )
        if volume_tolerance < 0 or linear_tolerance < 0:
            raise ValueError("comparison tolerances must be non-negative")
        if exact_face_product_limit < 0:
            raise ValueError("exact_face_product_limit must be non-negative")
        if not 1 <= timeout_ms <= 600000:
            raise ValueError("timeout_ms must be between 1 and 600000")
        target_object = object_name or str(snapshot["object_name"])
        target_doc = doc_name or str(snapshot["document"])
        bridge = await get_bridge()
        code = f"""
import FreeCAD
import Part

def _bbox(shape):
    box = shape.BoundBox
    return {{
        "min": [float(box.XMin), float(box.YMin), float(box.ZMin)],
        "max": [float(box.XMax), float(box.YMax), float(box.ZMax)],
        "size": [float(box.XLength), float(box.YLength), float(box.ZLength)],
    }}

def _metrics(shape):
    return {{
        "valid": bool(shape.isValid()),
        "shape_type": str(shape.ShapeType),
        "solid_count": len(shape.Solids),
        "shell_count": len(shape.Shells),
        "face_count": len(shape.Faces),
        "edge_count": len(shape.Edges),
        "vertex_count": len(shape.Vertexes),
        "volume": float(shape.Volume),
        "area": float(shape.Area),
        "bounding_box": _bbox(shape),
    }}

def _difference_regions(shape):
    def _has_topology(candidate):
        return not candidate.isNull() and bool(
            len(candidate.Solids)
            or len(candidate.Faces)
            or len(candidate.Edges)
            or len(candidate.Vertexes)
        )

    if not _has_topology(shape):
        return []
    regions = [solid for solid in shape.Solids if _has_topology(solid)]
    if not regions:
        regions = [shape]
    return [
        {{
            "index": index,
            "shape_type": str(region.ShapeType),
            "valid": bool(region.isValid()),
            "volume": float(region.Volume),
            "area": float(region.Area),
            "face_count": len(region.Faces),
            "edge_count": len(region.Edges),
            "vertex_count": len(region.Vertexes),
            "surface_types": sorted({{
                type(face.Surface).__name__ for face in region.Faces
            }}),
            "bounding_box": _bbox(region),
        }}
        for index, region in enumerate(regions, 1)
    ]

doc = FreeCAD.ActiveDocument if {target_doc!r} is None else FreeCAD.getDocument({target_doc!r})
if doc is None:
    raise ValueError("No document found")
if {recompute!r}:
    doc.recompute()
obj = doc.getObject({target_object!r})
if obj is None:
    raise ValueError(f"Object not found: {target_object!r}")
after = getattr(obj, "Shape", None)
if after is None or after.isNull():
    raise ValueError(f"Object has no usable Shape: {target_object!r}")
before = Part.Shape()
before.importBrepFromString({snapshot["brep"]!r})
before_metrics = {snapshot["metrics"]!r}
after_metrics = _metrics(after)
face_product = before_metrics["face_count"] * after_metrics["face_count"]
requested_mode = {difference_mode!r}
run_exact = requested_mode == "exact" or (
    requested_mode == "auto" and face_product <= {exact_face_product_limit!r}
)

boolean_error = None
skip_reason = None
if run_exact:
    try:
        removed = before.cut(after)
        added = after.cut(before)
        try:
            removed = removed.removeSplitter()
            added = added.removeSplitter()
        except Exception:
            pass
        removed_regions = _difference_regions(removed)
        added_regions = _difference_regions(added)
    except Exception as exc:
        boolean_error = str(exc)
        removed_regions = []
        added_regions = []
else:
    removed_regions = []
    added_regions = []
    if requested_mode == "metrics":
        skip_reason = "difference_mode_metrics"
    else:
        skip_reason = "face_product %s exceeds exact_face_product_limit {exact_face_product_limit!r}" % face_product

metric_names = ("solid_count", "shell_count", "face_count", "edge_count", "vertex_count", "volume", "area")
deltas = {{name: after_metrics[name] - before_metrics[name] for name in metric_names}}
bbox_delta = {{
    key: [
        after_metrics["bounding_box"][key][index] - before_metrics["bounding_box"][key][index]
        for index in range(3)
    ]
    for key in ("min", "max", "size")
}}
removed_volume = sum(region["volume"] for region in removed_regions)
added_volume = sum(region["volume"] for region in added_regions)
bbox_changed = any(
    abs(value) > {linear_tolerance!r}
    for values in bbox_delta.values()
    for value in values
)
geometric_change = None if boolean_error or not run_exact else bool(
    removed_volume > {volume_tolerance!r}
    or added_volume > {volume_tolerance!r}
)
metric_change_detected = bool(
    bbox_changed
    or abs(deltas["volume"]) > {volume_tolerance!r}
    or before_metrics["valid"] != after_metrics["valid"]
    or any(deltas[name] != 0 for name in metric_names[:5])
)
_result_ = {{
    "success": True,
    "document": doc.Name,
    "object_name": obj.Name,
    "before": before_metrics,
    "after": after_metrics,
    "delta": {{**deltas, "bounding_box": bbox_delta}},
    "invariants": {{
        "valid_before": before_metrics["valid"],
        "valid_after": after_metrics["valid"],
        "solid_count_unchanged": deltas["solid_count"] == 0,
        "bounding_box_unchanged": not bbox_changed,
    }},
    "difference": {{
        "method": (
            "occt_before_cut_after_and_after_cut_before"
            if run_exact
            else "metrics_only"
        ),
        "requested_mode": requested_mode,
        "performed_mode": "exact" if run_exact else "metrics",
        "available": run_exact and boolean_error is None,
        "error": boolean_error,
        "skip_reason": skip_reason,
        "face_product": face_product,
        "exact_face_product_limit": {exact_face_product_limit!r},
        "metric_change_detected": metric_change_detected,
        "geometric_change": geometric_change,
        "removed_volume": removed_volume,
        "added_volume": added_volume,
        "removed_region_count": len(removed_regions),
        "added_region_count": len(added_regions),
        "removed_regions": removed_regions,
        "added_regions": added_regions,
    }},
}}
"""
        execution = await bridge.execute_python(code, timeout_ms=timeout_ms)
        if not execution.success or not isinstance(execution.result, dict):
            raise ValueError(
                execution.error_traceback or "Failed to compare shape checkpoint"
            )
        payload = dict(execution.result)
        payload["checkpoint_name"] = normalized_name
        payload["checkpoint_source"] = {
            "document": snapshot["document"],
            "object_name": snapshot["object_name"],
        }
        return payload

    @mcp.tool()
    async def validate_object(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Check the health and validity of a FreeCAD object.

        This tool inspects an object to determine if it is in a valid state,
        has any computation errors, or needs recomputation. Use this after
        performing operations to verify they succeeded.

        Args:
            object_name: Name of the object to validate.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary containing:
                - valid: Overall validity (True if shape is valid and no errors)
                - object_name: Name of the validated object
                - shape_valid: Whether the shape geometry is valid
                - has_errors: Whether the object has error states
                - state: List of state flags (e.g., ["Invalid", "Touched"])
                - recompute_needed: Whether recomputation is needed
                - volume: Shape volume if applicable (None otherwise)
                - area: Shape surface area if applicable (None otherwise)
                - error_messages: List of any error messages
                - warnings: List of any warnings

        Example:
            Validate an object after creating it::

                result = await validate_object("MyBox")
                if not result["valid"]:
                    print(f"Errors: {result['error_messages']}")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}
object_name = {object_name!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "valid": False,
        "object_name": object_name,
        "error_messages": ["No active document found"],
        "shape_valid": False,
        "has_errors": True,
        "state": [],
        "recompute_needed": False,
        "volume": None,
        "area": None,
        "warnings": []
    }}
else:
    obj = doc.getObject(object_name)
    if obj is None:
        _result_ = {{
            "valid": False,
            "object_name": object_name,
            "error_messages": [f"Object '{{object_name}}' not found in document '{{doc.Name}}'"],
            "shape_valid": False,
            "has_errors": True,
            "state": [],
            "recompute_needed": False,
            "volume": None,
            "area": None,
            "warnings": []
        }}
    else:
        # Check object state
        state = list(obj.State) if hasattr(obj, 'State') else []
        has_errors = "Invalid" in state or "Error" in state
        recompute_needed = "Touched" in state

        # Check shape validity
        shape_valid = False
        volume = None
        area = None
        warnings = []
        error_messages = []

        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                shape_valid = obj.Shape.isValid()
                if not shape_valid:
                    error_messages.append("Shape geometry is invalid")

                # Get volume if shape is a solid
                if hasattr(obj.Shape, 'Volume'):
                    volume = obj.Shape.Volume
                    if volume <= 0:
                        warnings.append(f"Shape has non-positive volume: {{volume}}")

                # Get surface area
                if hasattr(obj.Shape, 'Area'):
                    area = obj.Shape.Area

            except Exception as e:
                error_messages.append(f"Error checking shape: {{str(e)}}")
                shape_valid = False
        else:
            # Not all objects have shapes (e.g., Sketch, Body container)
            # This is not necessarily an error
            if obj.TypeId.startswith("Part::") or obj.TypeId.startswith("PartDesign::"):
                if not obj.TypeId.endswith("Body"):
                    warnings.append("Object has no shape")
            shape_valid = True  # Objects without shapes are considered valid

        # Check for PartDesign-specific issues
        if hasattr(obj, 'BaseFeature') and obj.BaseFeature is None:
            if obj.TypeId not in ["PartDesign::Body", "Sketcher::SketchObject"]:
                warnings.append("PartDesign feature has no base feature")

        # Overall validity
        valid = shape_valid and not has_errors

        _result_ = {{
            "valid": valid,
            "object_name": obj.Name,
            "shape_valid": shape_valid,
            "has_errors": has_errors,
            "state": state,
            "recompute_needed": recompute_needed,
            "volume": volume,
            "area": area,
            "error_messages": error_messages,
            "warnings": warnings
        }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "valid": False,
            "object_name": object_name,
            "error_messages": [result.error_traceback or "Validation failed"],
            "shape_valid": False,
            "has_errors": True,
            "state": [],
            "recompute_needed": False,
            "volume": None,
            "area": None,
            "warnings": [],
        }

    @mcp.tool()
    async def validate_document(
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Check the health of all objects in a FreeCAD document.

        This tool validates every object in the document and provides
        a summary of the document's overall health. Use this after
        complex operations or before saving/exporting.

        Args:
            doc_name: Name of document to validate. Uses active document if None.

        Returns:
            Dictionary containing:
                - valid: Overall document validity (True if all objects valid)
                - doc_name: Name of the validated document
                - total_objects: Total number of objects in document
                - valid_objects: Count of valid objects
                - invalid_objects: List of names of invalid objects
                - objects_with_errors: List of names with error states
                - objects_needing_recompute: List of objects that need recompute
                - recompute_needed: Whether document needs recomputation
                - summary: Human-readable summary of document health

        Example:
            Check document health before saving::

                result = await validate_document()
                if result["valid"]:
                    await save_document()
                else:
                    print(f"Issues: {result['invalid_objects']}")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "valid": False,
        "doc_name": None,
        "total_objects": 0,
        "valid_objects": 0,
        "invalid_objects": [],
        "objects_with_errors": [],
        "objects_needing_recompute": [],
        "recompute_needed": False,
        "summary": "No active document found"
    }}
else:
    total_objects = len(doc.Objects)
    valid_count = 0
    invalid_objects = []
    objects_with_errors = []
    objects_needing_recompute = []

    for obj in doc.Objects:
        is_valid = True

        # Check state
        state = list(obj.State) if hasattr(obj, 'State') else []

        if "Invalid" in state or "Error" in state:
            objects_with_errors.append(obj.Name)
            is_valid = False

        if "Touched" in state:
            objects_needing_recompute.append(obj.Name)

        # Check shape validity for objects that should have shapes
        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                if not obj.Shape.isValid():
                    invalid_objects.append(obj.Name)
                    is_valid = False
            except Exception:
                invalid_objects.append(obj.Name)
                is_valid = False

        if is_valid:
            valid_count += 1

    # Build summary
    if valid_count == total_objects and not objects_with_errors:
        summary = f"Document '{{doc.Name}}' is healthy: all {{total_objects}} objects are valid"
    else:
        issues = []
        if invalid_objects:
            issues.append(f"{{len(invalid_objects)}} invalid objects")
        if objects_with_errors:
            issues.append(f"{{len(objects_with_errors)}} objects with errors")
        if objects_needing_recompute:
            issues.append(f"{{len(objects_needing_recompute)}} objects need recompute")
        summary = f"Document '{{doc.Name}}' has issues: " + ", ".join(issues)

    overall_valid = (valid_count == total_objects) and not objects_with_errors

    _result_ = {{
        "valid": overall_valid,
        "doc_name": doc.Name,
        "total_objects": total_objects,
        "valid_objects": valid_count,
        "invalid_objects": invalid_objects,
        "objects_with_errors": objects_with_errors,
        "objects_needing_recompute": objects_needing_recompute,
        "recompute_needed": len(objects_needing_recompute) > 0,
        "summary": summary
    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "valid": False,
            "doc_name": doc_name,
            "total_objects": 0,
            "valid_objects": 0,
            "invalid_objects": [],
            "objects_with_errors": [],
            "objects_needing_recompute": [],
            "recompute_needed": False,
            "summary": result.error_traceback or "Validation failed",
        }

    @mcp.tool()
    async def validate_parametric_model(
        doc_name: str | None = None,
        recompute: bool = True,
        include_sketch_constraints: bool = False,
        required_dimension_names: list[str] | None = None,
        target: SketchValidationTarget | None = None,
        workflow: Literal["native_parametric", "imported_brep_edit"] = (
            "native_parametric"
        ),
        detail_level: Literal["summary", "structure", "full"] = "summary",
        finding_offset: int = 0,
        finding_limit: int = 20,
    ) -> dict[str, Any]:
        """Validate parametric health with a compact default response.

        This is the mandatory final diagnostic for tasks that create or modify a
        FreeCAD model. It is intentionally informative rather than a rigid gate:
        it reports Bodies and Tips, ordered Body history, shape validity, sketch
        solver/profile state, expressions, direct solid objects outside Bodies,
        Spreadsheet parameter connectivity, required drawing-dimension usage,
        and actionable findings. Set ``target={"kind":"sketch","name":"..."}``
        to validate a sketch deliverable without treating the absence or state of
        a Body, solid, or Tip as an error. Set
        ``workflow="imported_brep_edit"`` when intentionally editing imported
        STEP/BRep geometry so provenance-marked sources and direct edits are
        informational while invalid shapes remain errors. Call it before the
        final user-facing response and summarize significant findings instead of
        merely saying "done".

        The tool does not verify that the model matches a drawing or that the
        chosen manufacturing process is correct. Those remain separate visual,
        dimensional, and engineering checks. Do not bulk-delete or recreate an
        accepted sketch constraint graph solely to improve this diagnostic;
        inspect the existing dependency path or report a tracing limitation.

        Dynamic/custom properties remain non-driving metadata by default. The
        narrow exception is the known geometry-property set on recognized native
        SheetMetal FeaturePython proxies.

        Args:
            doc_name: Document to inspect. Uses the active document when omitted.
            recompute: Recompute the document before inspection. Defaults to True.
            include_sketch_constraints: Include every individual sketch constraint
                with name, type, datum, driving/reference state, and index. Defaults
                to False because large sketches can make the response very long.
            required_dimension_names: Stable identifiers for all source dimensions
                classified as driving in the pre-model evidence manifest. Each name
                must appear as a named driving sketch constraint or as a Spreadsheet
                alias connected directly or transitively to an expression in the
                active final-solid dependency graph. With a sketch target, each name
                must instead influence non-construction geometry of that exact
                sketch. Check/reference dimensions belong in separate deterministic
                measurement evidence. Construction-only geometry and inactive/helper
                objects do not count as usage.
            target: Optional sketch validation target. Omit it for the existing
                whole-model/final-solid diagnostic. For a sketch-only deliverable,
                pass ``{"kind":"sketch","name":"Sketch_FlatPattern"}``.
            workflow: ``native_parametric`` keeps static BRep snapshots as
                warnings. ``imported_brep_edit`` recognizes import provenance and
                ``DirectEditOperation``/``SourceObject`` results as intentional.
            detail_level: ``summary`` (default) returns completion-critical counts,
                dimension influence, and a page of findings. ``structure`` adds
                Bodies, sketches, and Spreadsheet structure. ``full`` returns the
                complete diagnostic and may be very large.
            finding_offset: Zero-based findings-page offset.
            finding_limit: Findings-page size, from 1 to 100.

        Returns:
            Informative report containing:
                - assessment and human-readable summary
                - document metadata and counts
                - each PartDesign Body, its validity, shape, Tip, and ordered history
                - each sketch with solver state, remaining DoF, profile state,
                  support, expressions, and constraint type counts
                - required dimension identifiers and whether they drive geometry
                - Spreadsheet cells, aliases, expression bindings, and unused parameters
                - standalone sketches and solid objects outside Bodies
                - findings with error/warning severity
                - explicit limitations of the diagnostic
        """
        if finding_offset < 0:
            raise ValueError("finding_offset must be non-negative")
        if not 1 <= finding_limit <= 100:
            raise ValueError("finding_limit must be between 1 and 100")
        if include_sketch_constraints and detail_level != "full":
            raise ValueError(
                "include_sketch_constraints=True requires detail_level='full' "
                "because individual constraints can make the response very large"
            )

        normalized_required_dimensions = []
        seen_required_dimensions = set()
        for raw_name in required_dimension_names or []:
            name = str(raw_name).strip()
            if not name:
                raise ValueError(
                    "required_dimension_names must not contain empty values"
                )
            if name in seen_required_dimensions:
                raise ValueError(
                    f"required_dimension_names contains duplicate identifier: {name!r}"
                )
            seen_required_dimensions.add(name)
            normalized_required_dimensions.append(name)

        normalized_target = None
        if target is not None:
            normalized_target = _VALIDATION_TARGET_ADAPTER.validate_python(
                target
            ).model_dump()
            normalized_target["name"] = normalized_target["name"].strip()
            if not normalized_target["name"]:
                raise ValueError("target sketch name must not be empty")

        bridge = await get_bridge()
        code = build_parametric_validation_code(
            doc_name=doc_name,
            recompute=recompute,
            include_sketch_constraints=include_sketch_constraints,
            required_dimension_names=normalized_required_dimensions,
            validation_target=normalized_target,
            workflow=workflow,
        )
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return _parametric_response(
                result.result,
                detail_level,
                finding_offset,
                finding_limit,
            )
        error = result.error_traceback or "Parametric model validation failed"
        return {
            "informational": True,
            "workflow": workflow,
            "assessment": "unavailable",
            "summary": error,
            "validation_target": normalized_target or {"kind": "model"},
            "target_sketch": None,
            "document": None,
            "counts": {
                "bodies": 0,
                "body_history_items": 0,
                "sketches": 0,
                "standalone_sketches": 0,
                "spreadsheets": 0,
                "spreadsheet_parameters": 0,
                "required_dimensions": len(normalized_required_dimensions),
                "uncontained_shape_objects": 0,
            },
            "sketch_solver_status_counts": {},
            "expression_bindings": [],
            "dimension_inventory": {
                "provided": bool(normalized_required_dimensions),
                "required_names": normalized_required_dimensions,
                "usage": [],
                "all_used": False,
                "named_dimension_constraints": [],
                "spreadsheet_parameters": [],
            },
            "bodies": [],
            "standalone_sketches": [],
            "uncontained_shape_objects": [],
            "spreadsheets": [],
            "findings": [
                {
                    "severity": "error",
                    "category": "validation_execution_failed",
                    "object": doc_name,
                    "message": error,
                }
            ],
            "completion_guidance": {
                "required_before_user_response": True,
                "report": ["validation execution failure"],
            },
            "limitations": [
                "The FreeCAD-side diagnostic did not execute successfully."
            ],
        }

    @mcp.tool()
    async def undo_if_invalid(
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Check document health and undo the last operation if invalid objects exist.

        This tool first validates all objects in the document. If any objects
        are invalid or have errors, it automatically performs an undo operation.
        Use this after risky operations to ensure the model stays in a valid state.

        Args:
            doc_name: Name of document to check. Uses active document if None.

        Returns:
            Dictionary containing:
                - was_valid: Whether the document was valid before any undo
                - undone: Whether an undo operation was performed
                - invalid_objects: List of invalid objects found (before undo)
                - objects_with_errors: List of objects with errors (before undo)
                - message: Human-readable description of what happened
                - validation_after: Validation result after undo (if performed)

        Example:
            Auto-recover from a failed boolean operation::

                await boolean_operation("cut", "Box", "InvalidShape")
                result = await undo_if_invalid()
                if result["undone"]:
                    print("Recovered from invalid operation")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "was_valid": False,
        "undone": False,
        "invalid_objects": [],
        "objects_with_errors": [],
        "message": "No active document found",
        "validation_after": None
    }}
else:
    # First, check current state
    invalid_objects = []
    objects_with_errors = []

    for obj in doc.Objects:
        state = list(obj.State) if hasattr(obj, 'State') else []

        if "Invalid" in state or "Error" in state:
            objects_with_errors.append(obj.Name)

        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                if not obj.Shape.isValid():
                    invalid_objects.append(obj.Name)
            except Exception:
                invalid_objects.append(obj.Name)

    was_valid = len(invalid_objects) == 0 and len(objects_with_errors) == 0

    if was_valid:
        _result_ = {{
            "was_valid": True,
            "undone": False,
            "invalid_objects": [],
            "objects_with_errors": [],
            "message": "Document is valid, no undo needed",
            "validation_after": None
        }}
    else:
        # Perform undo
        try:
            doc.undo()
            doc.recompute()
            undone = True

            # Re-validate after undo
            invalid_after = []
            errors_after = []

            for obj in doc.Objects:
                state = list(obj.State) if hasattr(obj, 'State') else []

                if "Invalid" in state or "Error" in state:
                    errors_after.append(obj.Name)

                if hasattr(obj, 'Shape') and obj.Shape:
                    try:
                        if not obj.Shape.isValid():
                            invalid_after.append(obj.Name)
                    except Exception:
                        invalid_after.append(obj.Name)

            valid_after = len(invalid_after) == 0 and len(errors_after) == 0

            if valid_after:
                message = f"Undid last operation. Document is now valid."
            else:
                message = f"Undid last operation, but document still has issues."

            validation_after = {{
                "valid": valid_after,
                "invalid_objects": invalid_after,
                "objects_with_errors": errors_after
            }}

        except Exception as e:
            undone = False
            message = f"Failed to undo: {{str(e)}}"
            validation_after = None

        _result_ = {{
            "was_valid": False,
            "undone": undone,
            "invalid_objects": invalid_objects,
            "objects_with_errors": objects_with_errors,
            "message": message,
            "validation_after": validation_after
        }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "was_valid": False,
            "undone": False,
            "invalid_objects": [],
            "objects_with_errors": [],
            "message": result.error_traceback or "Operation failed",
            "validation_after": None,
        }

    @mcp.tool()
    async def safe_execute(
        code: str,
        doc_name: str | None = None,
        validate_after: bool = True,
        auto_undo_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Execute Python code with automatic validation and rollback on failure.

        This tool provides transactional semantics for FreeCAD operations:
        1. Opens an undo transaction
        2. Executes the provided code
        3. Validates all objects
        4. Automatically rolls back if validation fails (optional)

        Use this for complex operations where you want automatic error recovery.

        Args:
            code: Python code to execute. Use _result_ = value to return data.
            doc_name: Target document. Uses active document if None.
            validate_after: Whether to validate objects after execution.
            auto_undo_on_failure: Whether to automatically undo if validation fails.

        Returns:
            Dictionary containing:
                - success: Whether the operation succeeded (execution + validation)
                - result: The value assigned to _result_ in the code (if any)
                - rolled_back: Whether a rollback was performed
                - execution_success: Whether the code executed without exceptions
                - execution_error: Any execution error message
                - validation: Validation results (if validate_after is True)
                - message: Human-readable summary

        Example:
            Execute code with automatic rollback on failure::

                result = await safe_execute('''
                box = doc.addObject("Part::Box", "MyBox")
                box.Length = 100
                _result_ = {"created": box.Name}
                ''')
                if result["success"]:
                    print(f"Created: {result['result']['created']}")
        """
        bridge = await get_bridge()

        # Escape the user code for embedding in the wrapper
        escaped_code = code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

        wrapper_code = f"""
import FreeCAD

doc_name = {doc_name!r}
validate_after = {validate_after!r}
auto_undo_on_failure = {auto_undo_on_failure!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "success": False,
        "result": None,
        "rolled_back": False,
        "execution_success": False,
        "execution_error": "No active document found",
        "validation": None,
        "message": "No active document found"
    }}
else:
    # Start transaction
    doc.openTransaction("SafeExecute")

    execution_success = False
    execution_error = None
    user_result = None

    # Execute user code
    try:
        user_code = \"\"\"{escaped_code}\"\"\"
        exec_globals = {{"FreeCAD": FreeCAD, "App": FreeCAD, "doc": doc}}

        # Try to import common modules
        try:
            import Part
            exec_globals["Part"] = Part
        except ImportError:
            pass
        try:
            import PartDesign
            exec_globals["PartDesign"] = PartDesign
        except ImportError:
            pass
        try:
            import Sketcher
            exec_globals["Sketcher"] = Sketcher
        except ImportError:
            pass

        exec(user_code, exec_globals)

        if "_result_" in exec_globals:
            user_result = exec_globals["_result_"]

        execution_success = True
        doc.recompute()

    except Exception as e:
        execution_error = str(e)
        execution_success = False

    # Validate if requested
    validation = None
    validation_passed = True

    if validate_after and execution_success:
        invalid_objects = []
        objects_with_errors = []

        for obj in doc.Objects:
            state = list(obj.State) if hasattr(obj, 'State') else []

            if "Invalid" in state or "Error" in state:
                objects_with_errors.append(obj.Name)

            if hasattr(obj, 'Shape') and obj.Shape:
                try:
                    if not obj.Shape.isValid():
                        invalid_objects.append(obj.Name)
                except Exception:
                    invalid_objects.append(obj.Name)

        validation_passed = len(invalid_objects) == 0 and len(objects_with_errors) == 0
        validation = {{
            "valid": validation_passed,
            "invalid_objects": invalid_objects,
            "objects_with_errors": objects_with_errors
        }}

    # Determine if we need to rollback
    rolled_back = False
    if not execution_success or (validate_after and not validation_passed and auto_undo_on_failure):
        doc.abortTransaction()
        doc.recompute()
        rolled_back = True
    else:
        doc.commitTransaction()

    # Build message
    if execution_success and validation_passed:
        message = "Operation completed successfully"
    elif not execution_success:
        message = f"Execution failed: {{execution_error}}"
        if rolled_back:
            message += " (rolled back)"
    else:
        message = f"Validation failed: {{len(validation.get('invalid_objects', []))}} invalid objects"
        if rolled_back:
            message += " (rolled back)"

    overall_success = execution_success and (not validate_after or validation_passed)

    _result_ = {{
        "success": overall_success,
        "result": user_result,
        "rolled_back": rolled_back,
        "execution_success": execution_success,
        "execution_error": execution_error,
        "validation": validation,
        "message": message
    }}
"""
        result = await bridge.execute_python(wrapper_code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "result": None,
            "rolled_back": False,
            "execution_success": False,
            "execution_error": result.error_traceback or "Safe execute failed",
            "validation": None,
            "message": result.error_traceback or "Safe execute failed",
        }
