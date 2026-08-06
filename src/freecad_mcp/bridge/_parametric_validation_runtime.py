"""Generate FreeCAD-side code for parametric document diagnostics."""

from __future__ import annotations

from textwrap import dedent

from freecad_mcp.tools._freecad_runtime_helpers import SKETCH_ANALYSIS_RUNTIME_HELPERS


def build_parametric_validation_code(
    *,
    doc_name: str | None,
    recompute: bool,
    include_sketch_constraints: bool,
    required_dimension_names: list[str] | None = None,
) -> str:
    """Build a self-contained script executed inside the FreeCAD process.

    The result is intentionally diagnostic rather than a hard pass/fail gate. It
    reports document structure, PartDesign Bodies and Tips, ordered history,
    sketch solver/profile state, direct shape objects, and actionable findings.
    """
    template = r'''
import math
import re
import FreeCAD

__SKETCH_HELPERS__

required_dimension_names = __REQUIRED_DIMENSION_NAMES__


def _finite_number(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _text_uses_token(text, token):
    return re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
        str(text or ""),
    ) is not None


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
                if isinstance(values, str):
                    return [values]
                return [str(item) for item in values]
        except Exception:
            pass
    try:
        values = obj.State
        if isinstance(values, str):
            return [values] if values else []
        return [str(item) for item in values]
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
    type_id = getattr(obj, "TypeId", "")
    is_reference_geometry = type_id in {
        "PartDesign::Plane",
        "PartDesign::Line",
        "PartDesign::Point",
        "PartDesign::CoordinateSystem",
    }
    result = {
        "present": shape is not None,
        "metrics_applicable": not is_reference_geometry,
        "reference_geometry": is_reference_geometry,
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
    if is_reference_geometry:
        return result
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


def _constraint_geometry_indices(constraint):
    indices = []
    for attribute in ("First", "Second", "Third"):
        try:
            value = int(getattr(constraint, attribute))
        except Exception:
            continue
        if value >= 0 and value not in indices:
            indices.append(value)
    return indices


def _constraint_solid_influence(sketch, constraint_index, active_object_names):
    result = {
        "in_tip_dependency": getattr(sketch, "Name", None) in active_object_names,
        "geometry_indices": [],
        "construction_geometry_indices": [],
        "construction_only": False,
        "solid_driving": False,
        "reason": None,
    }
    try:
        constraint = list(sketch.Constraints or [])[constraint_index]
    except Exception:
        result["reason"] = "constraint is unavailable"
        return result

    indices = _constraint_geometry_indices(constraint)
    result["geometry_indices"] = indices
    construction = []
    getter = getattr(sketch, "getConstruction", None)
    for index in indices:
        try:
            if callable(getter) and bool(getter(index)):
                construction.append(index)
        except Exception:
            pass
    result["construction_geometry_indices"] = construction
    result["construction_only"] = bool(indices) and len(construction) == len(indices)

    driving_getter = getattr(sketch, "isDriving", None)
    try:
        driving = bool(driving_getter(constraint_index)) if callable(driving_getter) else True
    except Exception:
        driving = True
    if not driving:
        result["reason"] = "constraint is reference/non-driving"
    elif not result["in_tip_dependency"]:
        result["reason"] = "sketch is not in the active Body Tip dependency graph"
    elif not indices:
        result["reason"] = "constraint has no verifiable profile geometry reference"
    elif result["construction_only"]:
        result["reason"] = "constraint references construction geometry only"
    else:
        result["solid_driving"] = True
    return result


def _active_solid_dependency_names(doc):
    """Return objects reachable backwards from each active Body Tip."""
    names = set()
    for body in getattr(doc, "Objects", []) or []:
        if getattr(body, "TypeId", None) != "PartDesign::Body":
            continue
        tip = getattr(body, "Tip", None)
        stack = [tip] if tip is not None else []
        visited = set()
        while stack:
            current = stack.pop()
            marker = id(current)
            if marker in visited:
                continue
            visited.add(marker)
            name = getattr(current, "Name", None)
            if name:
                names.add(name)
            stack.extend(
                item for item in (getattr(current, "OutList", []) or [])
                if item is not None
            )
    return names


def _expression_binding_solid_influence(obj, property_name, active_object_names):
    type_id = getattr(obj, "TypeId", "")
    name = getattr(obj, "Name", None)
    if name not in active_object_names:
        return False, "object is not in the active Body Tip dependency graph"
    if type_id == "Sketcher::SketchObject":
        match = re.search(r"Constraints\[(\d+)\]", str(property_name))
        if match is None:
            constraint_name = str(property_name).split("Constraints.", 1)
            index = None
            if len(constraint_name) == 2:
                getter = getattr(obj, "getConstraintName", None)
                if callable(getter):
                    for candidate in range(int(getattr(obj, "ConstraintCount", 0))):
                        try:
                            if getter(candidate) == constraint_name[1]:
                                index = candidate
                                break
                        except Exception:
                            pass
            if index is None:
                return False, "sketch expression is not bound to a verifiable constraint"
        else:
            index = int(match.group(1))
        influence = _constraint_solid_influence(obj, index, active_object_names)
        return influence["solid_driving"], influence["reason"]
    if type_id.startswith("PartDesign::") and not any(
        token in type_id for token in ("Plane", "Line", "Point", "CoordinateSystem", "Body")
    ):
        status_getter = getattr(obj, "getPropertyStatus", None)
        if callable(status_getter):
            try:
                raw_status = list(status_getter(property_name) or [])
            except Exception:
                raw_status = []
            # FreeCAD Python may expose the Dynamic enum as its numeric index
            # (21) instead of the label, depending on the bridge serializer.
            if any(item == 21 or str(item) == "Dynamic" for item in raw_status):
                return False, "expression is attached to a dynamic/custom metadata property"
        return True, None
    return False, "expression endpoint is not a shape-producing active feature"


def _spreadsheet_cells(sheet):
    cells = set()
    try:
        cells.update(sheet.getNonEmptyCells())
    except Exception:
        pass
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(sheet.getPropertyByName("cells").Content)
        for node in root.iter("Cell"):
            address = node.attrib.get("address")
            if address:
                cells.add(address)
    except Exception:
        pass
    return sorted(cells)


def _spreadsheet_summary(sheet, expression_bindings):
    parameters = []
    cells = []
    for cell in _spreadsheet_cells(sheet):
        try:
            content = sheet.getContents(cell) or ""
        except Exception:
            content = ""
        try:
            alias = sheet.getAlias(cell) or None
        except Exception:
            alias = None
        try:
            computed = str(sheet.get(cell))
        except Exception:
            computed = None

        references = []
        tokens = [f"{sheet.Name}.{cell}"]
        if alias:
            tokens.extend(
                [
                    f"{sheet.Name}.{alias}",
                    f"<<{getattr(sheet, 'Label', sheet.Name)}>>.{alias}",
                ]
            )
        for binding in expression_bindings:
            expression = binding.get("expression", "")
            if (
                not str(binding.get("object_type", "")).startswith("Spreadsheet::")
                and any(_text_uses_token(expression, token) for token in tokens)
            ):
                references.append(binding)

        cell_summary = {
            "cell": cell,
            "alias": alias,
            "content": content,
            "computed": computed,
            "references": references,
            "reference_count": len(references),
            "dependencies": [],
            "dependent_cells": [],
            "connected_to_tree": any(
                reference.get("solid_driving") for reference in references
            ),
        }
        cells.append(cell_summary)
        if alias:
            parameters.append(cell_summary)

    return {
        "name": getattr(sheet, "Name", None),
        "label": getattr(sheet, "Label", None),
        "type_id": getattr(sheet, "TypeId", None),
        "visibility": _visibility(sheet),
        "cell_count": len(cells),
        "parameter_count": len(parameters),
        "cells": cells,
        "parameters": parameters,
        "unused_parameters": [],
    }


def _resolve_spreadsheet_connectivity(spreadsheets):
    """Mark aliases that directly or transitively drive non-Spreadsheet objects."""
    node_by_id = {}
    token_to_node_ids = {}
    for spreadsheet in spreadsheets:
        sheet_name = spreadsheet["name"]
        sheet_label = spreadsheet["label"] or sheet_name
        for cell in spreadsheet["cells"]:
            node_id = f"{sheet_name}.{cell['cell']}"
            cell["node_id"] = node_id
            node_by_id[node_id] = cell
            tokens = [f"{sheet_name}.{cell['cell']}"]
            if cell["alias"]:
                tokens.extend(
                    [
                        f"{sheet_name}.{cell['alias']}",
                        f"<<{sheet_label}>>.{cell['alias']}",
                    ]
                )
            for token in tokens:
                token_to_node_ids.setdefault(token, set()).add(node_id)

    for spreadsheet in spreadsheets:
        local_aliases = {
            cell["alias"]: cell["node_id"]
            for cell in spreadsheet["cells"]
            if cell["alias"]
        }
        local_cells = {
            cell["cell"]: cell["node_id"] for cell in spreadsheet["cells"]
        }
        for source in spreadsheet["cells"]:
            content = source["content"] or ""
            dependencies = set()
            for token, node_ids in token_to_node_ids.items():
                if _text_uses_token(content, token):
                    dependencies.update(node_ids)
            for token, node_id in {**local_cells, **local_aliases}.items():
                if _text_uses_token(content, token):
                    dependencies.add(node_id)
            dependencies.discard(source["node_id"])
            source["dependencies"] = sorted(dependencies)
            for dependency in dependencies:
                node_by_id[dependency]["dependent_cells"].append(source["node_id"])

    connected = {
        node_id
        for node_id, node in node_by_id.items()
        if node["connected_to_tree"]
    }
    changed = True
    while changed:
        changed = False
        for node_id in list(connected):
            for dependency in node_by_id[node_id]["dependencies"]:
                if dependency not in connected:
                    connected.add(dependency)
                    changed = True

    for spreadsheet in spreadsheets:
        for cell in spreadsheet["cells"]:
            cell["connected_to_tree"] = cell["node_id"] in connected
            cell["connected_to_final_solid"] = cell["connected_to_tree"]
            cell["dependent_cells"] = sorted(set(cell["dependent_cells"]))
        spreadsheet["unused_parameters"] = [
            parameter
            for parameter in spreadsheet["parameters"]
            if not parameter["connected_to_tree"]
        ]
    return spreadsheets


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
    """Return zero-based constraint indices reported by the last solve."""
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
        "number": index + 1,
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
    named_constraints = []
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
            named_constraints.append(
                {
                    "index": detail["index"],
                    "name": detail["name"],
                    "type": detail["type"],
                    "driving": detail["driving"],
                    "datum": detail["datum"],
                }
            )
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
        "named_constraints": named_constraints,
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
    invalid_history_items = [item for item in history if not item.get("valid")]
    tip_valid = tip_summary is not None and bool(tip_summary.get("valid"))
    reference_only = last_shape_feature is None
    tip_requirement_satisfied = bool(
        tip_valid or (tip is None and reference_only)
    )
    body_valid = bool(
        not _state_has_error(body_states)
        and body_shape["valid"] is not False
        and not invalid_history_items
        and tip_requirement_satisfied
    )

    issues = []
    warnings = []
    if tip is None:
        if reference_only:
            warnings.append(
                "Body has no Tip because no shape-bearing feature has been created yet."
            )
        else:
            issues.append("Body has no Tip despite shape-bearing feature history.")
    elif tip not in history_objects:
        issues.append("Body Tip is not present in Body history.")
    elif tip_summary is not None and not tip_summary.get("has_solid"):
        warnings.append("Body Tip does not currently expose a solid result.")
    for item in invalid_history_items:
        issues.append(
            f"Body history item {item.get('name')!r} ({item.get('type_id')}) is invalid."
        )
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
        "reference_only": reference_only,
        "invalid_history_item_count": len(invalid_history_items),
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
        "dimension_inventory": {
            "provided": bool(required_dimension_names),
            "required_names": required_dimension_names,
            "usage": [],
            "all_used": False,
            "named_dimension_constraints": [],
            "spreadsheet_parameters": [],
        },
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

    active_solid_dependency_names = _active_solid_dependency_names(doc)
    expression_bindings = []
    for obj in doc.Objects:
        for expression in _expression_summary(obj):
            solid_driving, influence_reason = _expression_binding_solid_influence(
                obj,
                expression["property"],
                active_solid_dependency_names,
            )
            expression_bindings.append(
                {
                    "object": getattr(obj, "Name", None),
                    "label": getattr(obj, "Label", None),
                    "object_type": getattr(obj, "TypeId", None),
                    "property": expression["property"],
                    "expression": expression["expression"],
                    "solid_driving": solid_driving,
                    "influence_reason": influence_reason,
                }
            )

    spreadsheets = [
        _spreadsheet_summary(obj, expression_bindings)
        for obj in doc.Objects
        if getattr(obj, "TypeId", "").startswith("Spreadsheet::")
    ]
    spreadsheets = _resolve_spreadsheet_connectivity(spreadsheets)

    all_sketches = []
    for body in bodies:
        all_sketches.extend(body["sketches"])
    all_sketches.extend(standalone_sketches)

    named_dimension_constraints = []
    for sketch in all_sketches:
        getter = getattr(doc, "getObject", None)
        live_sketch = getter(sketch["name"]) if callable(getter) else next(
            (
                item
                for item in doc.Objects
                if getattr(item, "Name", None) == sketch["name"]
            ),
            None,
        )
        for constraint in sketch.get("named_constraints", []):
            # A geometric constraint may have a name, but it is not a drawing
            # dimension. Only constraints with a readable datum satisfy the
            # required-dimension inventory.
            if constraint.get("datum") is None:
                continue
            influence = _constraint_solid_influence(
                live_sketch,
                constraint["index"],
                active_solid_dependency_names,
            )
            named_dimension_constraints.append(
                {
                    "name": constraint["name"],
                    "sketch": sketch["name"],
                    "index": constraint["index"],
                    "type": constraint["type"],
                    "driving": constraint["driving"],
                    "datum": constraint["datum"],
                    **influence,
                }
            )

    spreadsheet_parameters = []
    for spreadsheet in spreadsheets:
        for parameter in spreadsheet["parameters"]:
            spreadsheet_parameters.append(
                {
                    "name": parameter["alias"],
                    "spreadsheet": spreadsheet["name"],
                    "cell": parameter["cell"],
                    "content": parameter["content"],
                    "computed": parameter["computed"],
                    "references": parameter["references"],
                    "reference_count": parameter["reference_count"],
                    "dependencies": parameter["dependencies"],
                    "dependent_cells": parameter["dependent_cells"],
                    "connected_to_tree": parameter["connected_to_tree"],
                    "connected_to_final_solid": parameter[
                        "connected_to_final_solid"
                    ],
                }
            )

    dimension_usage = []
    for required_name in required_dimension_names:
        sketch_matches = [
            item
            for item in named_dimension_constraints
            if item["name"] == required_name
        ]
        spreadsheet_matches = [
            item for item in spreadsheet_parameters if item["name"] == required_name
        ]
        driving_sketch_matches = [
            item for item in sketch_matches if item.get("solid_driving") is True
        ]
        linked_spreadsheet_matches = [
            item
            for item in spreadsheet_matches
            if item["connected_to_final_solid"]
        ]
        if driving_sketch_matches or linked_spreadsheet_matches:
            status = "solid_driving"
        elif sketch_matches or spreadsheet_matches:
            status = "defined_but_not_solid_driving"
        else:
            status = "missing"
        dimension_usage.append(
            {
                "name": required_name,
                "status": status,
                "sketch_constraints": sketch_matches,
                "spreadsheet_parameters": spreadsheet_matches,
            }
        )

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

    for item in dimension_usage:
        if item["status"] == "missing":
            findings.append(
                {
                    "severity": "error",
                    "category": "required_dimension_missing",
                    "object": None,
                    "message": (
                        f"Required drawing dimension {item['name']!r} is not present "
                        "as a named driving sketch constraint or Spreadsheet alias."
                    ),
                }
            )
        elif item["status"] == "defined_but_not_solid_driving":
            findings.append(
                {
                    "severity": "error",
                    "category": "required_dimension_unlinked",
                    "object": None,
                    "message": (
                        f"Required drawing dimension {item['name']!r} exists but does "
                        "not have a verified influence on the active final solid. "
                        "Construction-only constraints, inactive sketches, datum "
                        "objects, and metadata links do not satisfy this check."
                    ),
                }
            )

    for spreadsheet in spreadsheets:
        for parameter in spreadsheet["unused_parameters"]:
            findings.append(
                {
                    "severity": "error",
                    "category": "unused_spreadsheet_parameter",
                    "object": spreadsheet["name"],
                    "message": (
                        f"Spreadsheet parameter {parameter['alias']!r} in "
                        f"{parameter['cell']} has no expression binding. Determine "
                        "why it was created; connect it to the feature tree if it is "
                        "required, otherwise remove it."
                    ),
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
                    "message": (
                        f"Sketch solver reported {key} zero-based MCP constraint "
                        f"indices: {indices}; GUI numbers: "
                        f"{[index + 1 for index in indices]}."
                    ),
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
            "spreadsheet_parameters": len(spreadsheet_parameters),
            "required_dimensions": len(required_dimension_names),
            "uncontained_shape_objects": len(uncontained_shape_objects),
        },
        "sketch_solver_status_counts": sketch_status_counts,
        "expression_bindings": expression_bindings,
        "dimension_inventory": {
            "provided": bool(required_dimension_names),
            "required_names": required_dimension_names,
            "usage": dimension_usage,
            "all_used": bool(required_dimension_names) and all(
                item["status"] == "solid_driving" for item in dimension_usage
            ),
            "named_dimension_constraints": named_dimension_constraints,
            "spreadsheet_parameters": spreadsheet_parameters,
        },
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
                "required drawing-dimension usage",
                "Spreadsheet parameter connectivity and unused aliases",
                "significant findings and unresolved warnings",
            ],
        },
        "limitations": [
            "This is an informative structural and geometric diagnostic, "
            "not a hard acceptance gate.",
            "It can verify only required dimension identifiers supplied by the "
            "caller; it cannot discover omitted drawing dimensions from pixels.",
            "It does not prove correspondence to a drawing, manufacturability, "
            "or design intent.",
            "Shape validity uses FreeCAD/OpenCASCADE isValid checks and does not "
            "run every expensive BOPCheck mode.",
        ],
    }
'''
    return (
        dedent(template)
        .replace("__SKETCH_HELPERS__", SKETCH_ANALYSIS_RUNTIME_HELPERS)
        .replace("__DOC_NAME__", repr(doc_name))
        .replace("__RECOMPUTE__", repr(recompute))
        .replace("__INCLUDE_CONSTRAINTS__", repr(include_sketch_constraints))
        .replace("__REQUIRED_DIMENSION_NAMES__", repr(required_dimension_names or []))
    )
