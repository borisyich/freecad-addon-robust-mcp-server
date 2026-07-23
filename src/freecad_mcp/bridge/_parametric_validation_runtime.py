"""Generate FreeCAD-side code for parametric document diagnostics."""

from __future__ import annotations

from textwrap import dedent

from freecad_mcp.tools._freecad_runtime_helpers import SKETCH_ANALYSIS_RUNTIME_HELPERS


def build_parametric_validation_code(
    *,
    doc_name: str | None,
    recompute: bool,
    include_sketch_constraints: bool,
) -> str:
    """Build a self-contained script executed inside the FreeCAD process.

    The result is intentionally diagnostic rather than a hard pass/fail gate. It
    reports document structure, PartDesign Bodies and Tips, ordered history,
    sketch solver/profile state, direct shape objects, and actionable findings.
    """
    template = r'''
import math
import FreeCAD

__SKETCH_HELPERS__


def _finite_number(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _object_ref(obj):
    if obj is None:
        return None
    return {
        "name": getattr(obj, "Name", None),
        "label": getattr(obj, "Label", None),
        "type_id": getattr(obj, "TypeId", None),
    }


def _state_values(obj):
    getter = getattr(obj, "getStatusString", None)
    if callable(getter):
        try:
            values = getter()
            if values:
                return [str(item) for item in values]
        except Exception:
            pass
    try:
        return [str(item) for item in obj.State]
    except Exception:
        return []


def _state_has_error(values):
    return any(
        "error" in value.lower() or "invalid" in value.lower()
        for value in values
    )


def _visibility(obj):
    try:
        return bool(obj.ViewObject.Visibility)
    except Exception:
        return None


def _shape_summary(obj):
    shape = getattr(obj, "Shape", None)
    result = {
        "present": shape is not None,
        "is_null": None,
        "valid": None,
        "shape_type": None,
        "solid_count": None,
        "shell_count": None,
        "face_count": None,
        "edge_count": None,
        "vertex_count": None,
        "volume": None,
        "area": None,
        "bounding_box": None,
    }
    if shape is None:
        return result

    try:
        result["is_null"] = bool(shape.isNull())
    except Exception:
        result["is_null"] = None
    if result["is_null"] is True:
        return result

    result["shape_type"] = getattr(shape, "ShapeType", type(shape).__name__)
    try:
        result["valid"] = bool(shape.isValid())
    except Exception:
        result["valid"] = None

    for key, attr in (
        ("solid_count", "Solids"),
        ("shell_count", "Shells"),
        ("face_count", "Faces"),
        ("edge_count", "Edges"),
        ("vertex_count", "Vertexes"),
    ):
        try:
            result[key] = len(getattr(shape, attr))
        except Exception:
            result[key] = None

    result["volume"] = _finite_number(getattr(shape, "Volume", None))
    result["area"] = _finite_number(getattr(shape, "Area", None))
    try:
        box = shape.BoundBox
        result["bounding_box"] = {
            "min": {
                "x": _finite_number(box.XMin),
                "y": _finite_number(box.YMin),
                "z": _finite_number(box.ZMin),
            },
            "max": {
                "x": _finite_number(box.XMax),
                "y": _finite_number(box.YMax),
                "z": _finite_number(box.ZMax),
            },
            "size": {
                "x": _finite_number(box.XLength),
                "y": _finite_number(box.YLength),
                "z": _finite_number(box.ZLength),
            },
        }
    except Exception:
        pass
    return result


def _expression_summary(obj):
    output = []
    try:
        engine = list(obj.ExpressionEngine or [])
    except Exception:
        engine = []
    for item in engine:
        try:
            property_name, expression = item[0], item[1]
        except Exception:
            continue
        output.append(
            {
                "property": str(property_name),
                "expression": str(expression),
            }
        )
    return output


def _placement_summary(obj):
    try:
        placement = obj.Placement
        axis = placement.Rotation.Axis
        return {
            "position": {
                "x": _finite_number(placement.Base.x),
                "y": _finite_number(placement.Base.y),
                "z": _finite_number(placement.Base.z),
            },
            "rotation": {
                "axis": {
                    "x": _finite_number(axis.x),
                    "y": _finite_number(axis.y),
                    "z": _finite_number(axis.z),
                },
                "angle_deg": math.degrees(float(placement.Rotation.Angle)),
            },
        }
    except Exception:
        return None


def _support_summary(sketch):
    result = {
        "map_mode": getattr(sketch, "MapMode", None),
        "support": [],
        "attachment_support": [],
    }
    for output_key, attr in (
        ("support", "Support"),
        ("attachment_support", "AttachmentSupport"),
    ):
        try:
            raw = getattr(sketch, attr)
        except Exception:
            continue
        if raw is None:
            continue
        if isinstance(raw, tuple) and raw and hasattr(raw[0], "Name"):
            # FreeCAD commonly exposes Support as (Object, ["FaceN"]).
            values = [raw]
        elif isinstance(raw, (list, tuple)):
            values = list(raw)
        else:
            values = [raw]
        for value in values:
            if isinstance(value, (list, tuple)) and value:
                obj = value[0]
                subelements = []
                if len(value) > 1:
                    try:
                        subelements = [str(item) for item in (value[1] or [])]
                    except Exception:
                        subelements = [str(value[1])]
                item = _object_ref(obj)
                if item:
                    item["subelements"] = subelements
                    result[output_key].append(item)
            elif hasattr(value, "Name"):
                item = _object_ref(value)
                if item:
                    result[output_key].append(item)
    return result


def _solver_constraint_indices(sketch):
    """Return constraint indices reported by the last Sketcher solve."""
    result = {
        "conflicting": [],
        "redundant": [],
        "partially_redundant": [],
        "malformed": [],
    }
    for key, getter_name in (
        ("conflicting", "getLastConflicting"),
        ("redundant", "getLastRedundant"),
        ("partially_redundant", "getLastPartiallyRedundant"),
        ("malformed", "getLastMalformedConstraints"),
    ):
        getter = getattr(sketch, getter_name, None)
        if not callable(getter):
            continue
        try:
            result[key] = sorted({int(value) for value in (getter() or [])})
        except Exception:
            pass
    return result


def _constraint_detail(sketch, index, constraint):
    item = {
        "index": index,
        "type": str(getattr(constraint, "Type", type(constraint).__name__)),
        "name": None,
        "driving": None,
        "virtual": None,
        "datum": None,
    }
    name_getter = getattr(sketch, "getConstraintName", None)
    if callable(name_getter):
        try:
            item["name"] = name_getter(index) or None
        except Exception:
            pass
    if not item["name"]:
        value = getattr(constraint, "Name", None)
        if value:
            item["name"] = str(value)

    driving_getter = getattr(sketch, "isDriving", None)
    if callable(driving_getter):
        try:
            item["driving"] = bool(driving_getter(index))
        except Exception:
            pass
    virtual_getter = getattr(sketch, "isInVirtualSpace", None)
    if callable(virtual_getter):
        try:
            item["virtual"] = bool(virtual_getter(index))
        except Exception:
            pass

    datum_getter = getattr(sketch, "getDatum", None)
    if callable(datum_getter):
        try:
            datum = datum_getter(index)
            item["datum"] = {
                "value": _finite_number(getattr(datum, "Value", None)),
                "unit": str(getattr(datum, "Unit", "")) or None,
                "display": str(datum),
            }
        except Exception:
            pass
    return item


def _sketch_summary(sketch, body_name=None):
    analysis = _analyze_sketch(sketch)
    states = _state_values(sketch)
    constraint_type_counts = {}
    named_constraint_count = 0
    constraints = []
    try:
        raw_constraints = list(sketch.Constraints or [])
    except Exception:
        raw_constraints = []
    for index, constraint in enumerate(raw_constraints):
        detail = _constraint_detail(sketch, index, constraint)
        constraint_type = detail["type"]
        constraint_type_counts[constraint_type] = (
            constraint_type_counts.get(constraint_type, 0) + 1
        )
        if detail["name"]:
            named_constraint_count += 1
        if __INCLUDE_CONSTRAINTS__:
            constraints.append(detail)

    solver_status = analysis.get("solver", {}).get("status", "unknown")
    solver_constraint_indices = _solver_constraint_indices(sketch)
    solver_valid = solver_status not in {
        "over_constrained",
        "conflicting",
        "redundant",
        "solver_error",
    } and not any(
        solver_constraint_indices.get(key)
        for key in ("conflicting", "redundant", "malformed")
    )
    profile_state = analysis.get("profile", {}).get("state", "unknown")
    geometry_valid = profile_state != "invalid"

    result = {
        "name": getattr(sketch, "Name", None),
        "label": getattr(sketch, "Label", None),
        "type_id": getattr(sketch, "TypeId", None),
        "body": body_name,
        "valid": bool(not _state_has_error(states) and solver_valid and geometry_valid),
        "state": states,
        "visibility": _visibility(sketch),
        "placement": _placement_summary(sketch),
        "support": _support_summary(sketch),
        "expressions": _expression_summary(sketch),
        "constraint_type_counts": constraint_type_counts,
        "named_constraint_count": named_constraint_count,
        "solver_constraint_indices": solver_constraint_indices,
        "analysis": analysis,
    }
    if __INCLUDE_CONSTRAINTS__:
        result["constraints"] = constraints
    return result


def _history_role(obj):
    type_id = getattr(obj, "TypeId", "")
    if type_id == "Sketcher::SketchObject":
        return "sketch"
    if type_id.startswith("PartDesign::") and any(
        token in type_id for token in ("Plane", "Line", "Point", "CoordinateSystem")
    ):
        return "datum"
    if type_id.startswith("PartDesign::"):
        return "feature"
    return "other"


def _history_item(obj, index):
    states = _state_values(obj)
    shape = _shape_summary(obj)
    shape_is_problem = shape["present"] and (
        shape["valid"] is False or shape["is_null"] is True
    )
    return {
        "index": index,
        "name": getattr(obj, "Name", None),
        "label": getattr(obj, "Label", None),
        "type_id": getattr(obj, "TypeId", None),
        "role": _history_role(obj),
        "valid": bool(not _state_has_error(states) and not shape_is_problem),
        "state": states,
        "visibility": _visibility(obj),
        "shape": shape,
        "expressions": _expression_summary(obj),
        "in_list": [
            _object_ref(value)
            for value in (getattr(obj, "InList", []) or [])
            if value is not None
        ],
        "out_list": [
            _object_ref(value)
            for value in (getattr(obj, "OutList", []) or [])
            if value is not None
        ],
    }


def _body_summary(body):
    history_objects = list(getattr(body, "Group", []) or [])
    history = [_history_item(obj, index) for index, obj in enumerate(history_objects)]
    sketches = [
        _sketch_summary(obj, getattr(body, "Name", None))
        for obj in history_objects
        if getattr(obj, "TypeId", None) == "Sketcher::SketchObject"
    ]
    history_type_counts = {}
    history_role_counts = {}
    for item in history:
        type_id = item.get("type_id") or "<unknown>"
        role = item.get("role") or "other"
        history_type_counts[type_id] = history_type_counts.get(type_id, 0) + 1
        history_role_counts[role] = history_role_counts.get(role, 0) + 1

    tip = getattr(body, "Tip", None)
    tip_summary = _history_item(tip, -1) if tip is not None else None
    if tip_summary is not None:
        tip_summary["in_body_history"] = tip in history_objects
        tip_shape = tip_summary.get("shape", {})
        tip_summary["has_solid"] = bool((tip_shape.get("solid_count") or 0) > 0)

    last_shape_feature = None
    for obj in reversed(history_objects):
        shape = _shape_summary(obj)
        if (
            shape["present"]
            and shape["is_null"] is not True
            and (shape["solid_count"] or 0) > 0
        ):
            last_shape_feature = obj
            break

    body_states = _state_values(body)
    body_shape = _shape_summary(body)
    tip_valid = tip_summary is not None and bool(tip_summary.get("valid"))
    body_valid = bool(
        not _state_has_error(body_states)
        and body_shape["valid"] is not False
        and tip_valid
    )

    issues = []
    warnings = []
    if tip is None:
        issues.append("Body has no Tip.")
    elif tip not in history_objects:
        issues.append("Body Tip is not present in Body history.")
    elif tip_summary is not None and not tip_summary.get("has_solid"):
        warnings.append("Body Tip does not currently expose a solid result.")
    if tip is not None and last_shape_feature is not None and tip is not last_shape_feature:
        warnings.append(
            "Body Tip is not the latest shape-bearing item in the recorded history."
        )
    if body_shape["solid_count"] not in (None, 1):
        issues.append(
            f"Body contains {body_shape['solid_count']} solids; PartDesign normally expects one contiguous solid."
        )
    if body_shape["valid"] is False:
        issues.append("Body shape is invalid.")
    if not sketches:
        warnings.append("Body contains no Sketcher sketches.")

    return {
        "name": getattr(body, "Name", None),
        "label": getattr(body, "Label", None),
        "type_id": getattr(body, "TypeId", None),
        "valid": body_valid,
        "state": body_states,
        "visibility": _visibility(body),
        "placement": _placement_summary(body),
        "shape": body_shape,
        "tip": tip_summary,
        "tip_is_latest_shape_feature": bool(
            tip is not None and last_shape_feature is not None and tip is last_shape_feature
        ),
        "history_count": len(history),
        "history_type_counts": history_type_counts,
        "history_role_counts": history_role_counts,
        "history": history,
        "sketch_count": len(sketches),
        "sketches": sketches,
        "issues": issues,
        "warnings": warnings,
    }


requested_doc_name = __DOC_NAME__
if requested_doc_name is None:
    doc = FreeCAD.ActiveDocument
else:
    try:
        doc = FreeCAD.listDocuments().get(requested_doc_name)
    except Exception:
        doc = None

if doc is None:
    _result_ = {
        "informational": True,
        "document": None,
        "assessment": "unavailable",
        "summary": "No active document found.",
        "bodies": [],
        "standalone_sketches": [],
        "uncontained_shape_objects": [],
        "spreadsheets": [],
        "findings": [
            {
                "severity": "error",
                "category": "document_missing",
                "object": None,
                "message": "No active document found.",
            }
        ],
        "completion_guidance": {
            "required_before_user_response": True,
            "report": ["validation unavailable because no document was found"],
        },
        "limitations": [
            "This diagnostic does not verify correspondence to a drawing or manufacturing intent."
        ],
    }
else:
    recompute_error = None
    if __RECOMPUTE__:
        try:
            doc.recompute()
        except Exception as exc:
            recompute_error = str(exc)

    bodies = [
        _body_summary(obj)
        for obj in doc.Objects
        if getattr(obj, "TypeId", None) == "PartDesign::Body"
    ]
    body_member_names = set()
    for body in doc.Objects:
        if getattr(body, "TypeId", None) != "PartDesign::Body":
            continue
        for member in (getattr(body, "Group", []) or []):
            body_member_names.add(getattr(member, "Name", ""))

    standalone_sketches = [
        _sketch_summary(obj, None)
        for obj in doc.Objects
        if getattr(obj, "TypeId", None) == "Sketcher::SketchObject"
        and getattr(obj, "Name", "") not in body_member_names
    ]

    uncontained_shape_objects = []
    for obj in doc.Objects:
        type_id = getattr(obj, "TypeId", "")
        if type_id == "PartDesign::Body" or getattr(obj, "Name", "") in body_member_names:
            continue
        shape = _shape_summary(obj)
        if not shape["present"] or shape["is_null"] is True:
            continue
        if (shape["solid_count"] or 0) <= 0:
            continue
        uncontained_shape_objects.append(
            {
                "name": getattr(obj, "Name", None),
                "label": getattr(obj, "Label", None),
                "type_id": type_id,
                "visibility": _visibility(obj),
                "state": _state_values(obj),
                "shape": shape,
                "expressions": _expression_summary(obj),
                "classification": (
                    "direct_shape_feature"
                    if type_id in {"Part::Feature", "Part::FeaturePython"}
                    else "uncontained_solid"
                ),
            }
        )

    spreadsheets = [
        {
            "name": getattr(obj, "Name", None),
            "label": getattr(obj, "Label", None),
            "type_id": getattr(obj, "TypeId", None),
            "visibility": _visibility(obj),
        }
        for obj in doc.Objects
        if getattr(obj, "TypeId", "").startswith("Spreadsheet::")
    ]

    all_sketches = []
    for body in bodies:
        all_sketches.extend(body["sketches"])
    all_sketches.extend(standalone_sketches)

    sketch_status_counts = {}
    for sketch in all_sketches:
        status = sketch.get("analysis", {}).get("solver", {}).get("status", "unknown")
        sketch_status_counts[status] = sketch_status_counts.get(status, 0) + 1

    object_type_counts = {}
    for obj in doc.Objects:
        type_id = getattr(obj, "TypeId", None) or "<unknown>"
        object_type_counts[type_id] = object_type_counts.get(type_id, 0) + 1

    findings = []
    if recompute_error:
        findings.append(
            {
                "severity": "error",
                "category": "recompute_failed",
                "object": getattr(doc, "Name", None),
                "message": f"Document recompute failed: {recompute_error}",
            }
        )
    if not bodies:
        findings.append(
            {
                "severity": "warning",
                "category": "no_partdesign_body",
                "object": getattr(doc, "Name", None),
                "message": "No PartDesign Body was found. The document may be imported, direct-shape, or non-parametric.",
            }
        )

    for body in bodies:
        if not body["valid"]:
            findings.append(
                {
                    "severity": "error",
                    "category": "body_invalid",
                    "object": body["name"],
                    "message": "Body or its Tip requires review; inspect body issues and Tip diagnostics.",
                }
            )
        for issue in body["issues"]:
            findings.append(
                {
                    "severity": "error",
                    "category": "body_issue",
                    "object": body["name"],
                    "message": issue,
                }
            )
        for warning in body["warnings"]:
            findings.append(
                {
                    "severity": "warning",
                    "category": "body_warning",
                    "object": body["name"],
                    "message": warning,
                }
            )

    for sketch in all_sketches:
        solver = sketch.get("analysis", {}).get("solver", {})
        status = solver.get("status", "unknown")
        index_data = sketch.get("solver_constraint_indices", {})
        if status in {"over_constrained", "conflicting", "redundant", "solver_error"}:
            if status == "over_constrained":
                relevant_indices = sorted(
                    {
                        index
                        for key in (
                            "conflicting",
                            "redundant",
                            "partially_redundant",
                            "malformed",
                        )
                        for index in index_data.get(key, [])
                    }
                )
            else:
                relevant_indices = index_data.get(status, [])
            suffix = f" Constraint indices: {relevant_indices}." if relevant_indices else ""
            findings.append(
                {
                    "severity": "error",
                    "category": "sketch_solver_issue",
                    "object": sketch["name"],
                    "message": f"Sketch solver status is {status}.{suffix}",
                }
            )
        elif status == "under_constrained":
            remaining_dof = solver.get("remaining_dof")
            suffix = (
                f" ({remaining_dof} remaining DoF)"
                if remaining_dof is not None
                else ""
            )
            findings.append(
                {
                    "severity": "warning",
                    "category": "sketch_under_constrained",
                    "object": sketch["name"],
                    "message": f"Sketch is under-constrained{suffix}.",
                }
            )

        for key, severity in (
            ("conflicting", "error"),
            ("redundant", "error"),
            ("partially_redundant", "warning"),
            ("malformed", "error"),
        ):
            indices = index_data.get(key, [])
            if not indices:
                continue
            # Avoid duplicating the normal status finding when it already names
            # exactly the same diagnostic class.
            if key == status:
                continue
            findings.append(
                {
                    "severity": severity,
                    "category": f"sketch_{key}_constraints",
                    "object": sketch["name"],
                    "message": f"Sketch solver reported {key} constraint indices: {indices}.",
                }
            )

        profile_state = sketch.get("analysis", {}).get("profile", {}).get("state")
        if profile_state == "invalid":
            findings.append(
                {
                    "severity": "error",
                    "category": "sketch_profile_invalid",
                    "object": sketch["name"],
                    "message": "Sketch profile geometry is invalid.",
                }
            )

    for obj in uncontained_shape_objects:
        findings.append(
            {
                "severity": "warning",
                "category": obj["classification"],
                "object": obj["name"],
                "message": "Solid exists outside a PartDesign Body; confirm that it is intentional and not a replacement for editable feature history.",
            }
        )

    severities = {item["severity"] for item in findings}
    if "error" in severities:
        assessment = "invalid_or_broken"
    elif "warning" in severities:
        assessment = "review_recommended"
    else:
        assessment = "healthy"

    summary = (
        f"Document '{doc.Name}': {len(bodies)} PartDesign Body/Bodies, "
        f"{len(all_sketches)} sketch(es), "
        f"{len(uncontained_shape_objects)} solid object(s) outside Bodies; "
        f"assessment={assessment}."
    )

    _result_ = {
        "informational": True,
        "assessment": assessment,
        "summary": summary,
        "document": {
            "name": getattr(doc, "Name", None),
            "label": getattr(doc, "Label", None),
            "path": getattr(doc, "FileName", None) or None,
            "object_count": len(doc.Objects),
            "object_type_counts": object_type_counts,
            "recomputed": bool(__RECOMPUTE__ and recompute_error is None),
            "recompute_error": recompute_error,
        },
        "counts": {
            "bodies": len(bodies),
            "body_history_items": sum(body["history_count"] for body in bodies),
            "sketches": len(all_sketches),
            "standalone_sketches": len(standalone_sketches),
            "spreadsheets": len(spreadsheets),
            "uncontained_shape_objects": len(uncontained_shape_objects),
        },
        "sketch_solver_status_counts": sketch_status_counts,
        "bodies": bodies,
        "standalone_sketches": standalone_sketches,
        "uncontained_shape_objects": uncontained_shape_objects,
        "spreadsheets": spreadsheets,
        "findings": findings,
        "completion_guidance": {
            "required_before_user_response": True,
            "report": [
                "document and Body names",
                "Body and Tip validity",
                "ordered feature history",
                "sketch solver/profile status",
                "significant findings and unresolved warnings",
            ],
        },
        "limitations": [
            "This is an informative structural and geometric diagnostic, not a hard acceptance gate.",
            "It does not prove correspondence to a drawing, dimensions not represented in the model, manufacturability, or design intent.",
            "Shape validity uses FreeCAD/OpenCASCADE isValid checks and does not run every expensive BOPCheck mode.",
        ],
    }
'''
    return (
        dedent(template)
        .replace("__SKETCH_HELPERS__", SKETCH_ANALYSIS_RUNTIME_HELPERS)
        .replace("__DOC_NAME__", repr(doc_name))
        .replace("__RECOMPUTE__", repr(recompute))
        .replace("__INCLUDE_CONSTRAINTS__", repr(include_sketch_constraints))
    )
