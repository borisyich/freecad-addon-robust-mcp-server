"""Shared runtime code for structured FreeCAD object inspection.

The bridge implementations execute Python in a FreeCAD interpreter.  Keeping
this generated code here avoids three subtly different serializers in the
embedded, socket, and XML-RPC bridges.
"""

from textwrap import dedent

OBJECT_INSPECTION_RUNTIME = dedent(
    r"""
    import math
    import re


    def _safe_attr(value, attribute, default=None):
        try:
            return getattr(value, attribute)
        except Exception:
            return default


    def _finite_number(value):
        try:
            number = float(value)
        except Exception:
            return None
        return number if math.isfinite(number) else None


    def _vector_value(value):
        return {
            "x": _finite_number(_safe_attr(value, "x")),
            "y": _finite_number(_safe_attr(value, "y")),
            "z": _finite_number(_safe_attr(value, "z")),
        }


    def _rotation_value(value):
        axis = _safe_attr(value, "Axis")
        angle_rad = _finite_number(_safe_attr(value, "Angle"))
        quaternion = None
        try:
            quaternion = [_finite_number(item) for item in value.Q]
        except Exception:
            pass
        return {
            "axis": _vector_value(axis) if axis is not None else None,
            "angle_deg": math.degrees(angle_rad) if angle_rad is not None else None,
            "quaternion": quaternion,
        }


    def _placement_value(value):
        base = _safe_attr(value, "Base")
        rotation = _safe_attr(value, "Rotation")
        return {
            "position": _vector_value(base) if base is not None else None,
            "rotation": _rotation_value(rotation) if rotation is not None else None,
        }


    def _document_object_ref(value):
        return {
            "name": getattr(value, "Name", None),
            "label": getattr(value, "Label", None),
            "type_id": getattr(value, "TypeId", None),
        }


    def _bounding_box_value(bound_box):
        if bound_box is None:
            return None
        return {
            "min": {
                "x": _finite_number(_safe_attr(bound_box, "XMin")),
                "y": _finite_number(_safe_attr(bound_box, "YMin")),
                "z": _finite_number(_safe_attr(bound_box, "ZMin")),
            },
            "max": {
                "x": _finite_number(_safe_attr(bound_box, "XMax")),
                "y": _finite_number(_safe_attr(bound_box, "YMax")),
                "z": _finite_number(_safe_attr(bound_box, "ZMax")),
            },
            "size": {
                "x": _finite_number(_safe_attr(bound_box, "XLength")),
                "y": _finite_number(_safe_attr(bound_box, "YLength")),
                "z": _finite_number(_safe_attr(bound_box, "ZLength")),
            },
        }


    def _shape_value(shape):
        try:
            is_null = bool(shape.isNull())
        except Exception:
            is_null = True

        summary = {
            "shape_type": getattr(shape, "ShapeType", type(shape).__name__),
            "is_null": is_null,
        }
        if is_null:
            return summary

        for key, attribute in (
            ("solid_count", "Solids"),
            ("shell_count", "Shells"),
            ("face_count", "Faces"),
            ("edge_count", "Edges"),
            ("vertex_count", "Vertexes"),
        ):
            try:
                summary[key] = len(getattr(shape, attribute))
            except Exception:
                summary[key] = None

        try:
            summary["is_valid"] = bool(shape.isValid())
        except Exception:
            summary["is_valid"] = None
        try:
            summary["is_closed"] = bool(shape.isClosed())
        except Exception:
            summary["is_closed"] = None

        summary["volume"] = _finite_number(_safe_attr(shape, "Volume"))
        summary["area"] = _finite_number(_safe_attr(shape, "Area"))

        center = _safe_attr(shape, "CenterOfMass")
        summary["center_of_mass"] = _vector_value(center) if center is not None else None
        summary["bounding_box"] = _bounding_box_value(_safe_attr(shape, "BoundBox"))
        return summary


    def _quantity_value(value):
        numeric = _finite_number(_safe_attr(value, "Value"))
        unit = None
        try:
            unit = str(value.Unit)
        except Exception:
            pass
        return {
            "value": numeric,
            "unit": unit or None,
            "display": str(value),
        }


    def _constraint_value(value):
        result = {"constraint_type": getattr(value, "Type", type(value).__name__)}
        fields = (
            ("first_geometry", "First"),
            ("first_point", "FirstPos"),
            ("second_geometry", "Second"),
            ("second_point", "SecondPos"),
            ("third_geometry", "Third"),
            ("third_point", "ThirdPos"),
            ("value", "Value"),
            ("label", "Label"),
            ("name", "Name"),
        )
        for output_name, attribute in fields:
            if not hasattr(value, attribute):
                continue
            try:
                item = getattr(value, attribute)
            except Exception:
                continue
            if item in (None, ""):
                continue
            if output_name == "value":
                item = _finite_number(item)
            elif isinstance(item, (int, float, str, bool)):
                pass
            else:
                item = _serialize_value(item)
            result[output_name] = item
        return result


    def _geometry_value(value):
        result = {"geometry_type": type(value).__name__}
        vector_fields = (
            ("start", "StartPoint"),
            ("end", "EndPoint"),
            ("center", "Center"),
            ("focus1", "Focus1"),
            ("focus2", "Focus2"),
        )
        scalar_fields = (
            ("radius", "Radius"),
            ("major_radius", "MajorRadius"),
            ("minor_radius", "MinorRadius"),
            ("degree", "Degree"),
        )
        for output_name, attribute in vector_fields:
            if hasattr(value, attribute):
                try:
                    result[output_name] = _vector_value(getattr(value, attribute))
                except Exception:
                    pass
        for output_name, attribute in scalar_fields:
            if hasattr(value, attribute):
                try:
                    result[output_name] = _finite_number(getattr(value, attribute))
                except Exception:
                    pass
        for output_name, attribute in (("is_closed", "isClosed"), ("is_periodic", "isPeriodic")):
            method = getattr(value, attribute, None)
            if callable(method):
                try:
                    result[output_name] = bool(method())
                except Exception:
                    pass
        return result


    def _material_value(value):
        for attribute in ("Material", "CardName"):
            candidate = getattr(value, attribute, None)
            if isinstance(candidate, dict):
                return {str(key): _serialize_value(item) for key, item in candidate.items()}
        to_dict = getattr(value, "toDict", None)
        if callable(to_dict):
            try:
                candidate = to_dict()
                if isinstance(candidate, dict):
                    return {str(key): _serialize_value(item) for key, item in candidate.items()}
            except Exception:
                pass
        return None


    def _sanitized_fallback(value):
        text = str(value)
        text = re.sub(r"\s+at\s+(?:0x)?[0-9A-Fa-f]{8,}", "", text)
        text = re.sub(r"\s+object\s+at\s+(?:0x)?[0-9A-Fa-f]{8,}", " object", text)
        return {
            "python_type": f"{type(value).__module__}.{type(value).__name__}",
            "display": text,
        }


    def _serialize_value(value, property_type=None, depth=0):
        if depth > 8:
            return {"truncated": True, "reason": "maximum nesting depth reached"}
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return _finite_number(value)

        property_type = property_type or ""
        type_name = type(value).__name__
        module_name = type(value).__module__

        if hasattr(value, "Name") and hasattr(value, "TypeId"):
            return _document_object_ref(value)
        if hasattr(value, "ShapeType") and hasattr(value, "isNull"):
            return _shape_value(value)
        if "Placement" in property_type or type_name == "Placement":
            return _placement_value(value)
        if "Rotation" in property_type or type_name == "Rotation":
            return _rotation_value(value)
        if "Vector" in property_type or type_name == "Vector":
            return _vector_value(value)
        if hasattr(value, "Value") and (
            "PropertyLength" in property_type
            or "PropertyDistance" in property_type
            or "PropertyAngle" in property_type
            or "PropertyQuantity" in property_type
            or "Units.Quantity" in f"{module_name}.{type_name}"
        ):
            return _quantity_value(value)
        if "Constraint" in type_name or "Sketcher.Constraint" in f"{module_name}.{type_name}":
            return _constraint_value(value)
        if module_name.startswith("Part") and type_name not in ("TopoShape", "Shape"):
            return _geometry_value(value)
        if "Material" in property_type or "Material" in type_name:
            material = _material_value(value)
            if material is not None:
                return material
        if isinstance(value, dict):
            return {
                str(key): _serialize_value(item, depth=depth + 1)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [_serialize_value(item, depth=depth + 1) for item in value]
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            try:
                return [_serialize_value(item, depth=depth + 1) for item in value]
            except Exception:
                pass
        return _sanitized_fallback(value)


    def _property_entry(obj, property_name):
        property_type = None
        group = None
        status = None
        try:
            property_type = obj.getTypeIdOfProperty(property_name)
        except Exception:
            pass
        try:
            group = obj.getGroupOfProperty(property_name) or None
        except Exception:
            pass
        try:
            raw_status = obj.getPropertyStatus(property_name)
            if raw_status:
                status = [str(item) for item in raw_status]
        except Exception:
            pass

        try:
            value = _serialize_value(getattr(obj, property_name), property_type)
            readable = True
        except Exception as exc:
            value = {"error": str(exc)}
            readable = False

        entry = {
            "type": property_type,
            "group": group,
            "value": value,
        }
        if status:
            entry["status"] = status
        if not readable:
            entry["readable"] = False
        return entry


    def _inspect_object_value(obj):
        properties = {
            property_name: _property_entry(obj, property_name)
            for property_name in getattr(obj, "PropertiesList", [])
        }
        shape_info = None
        if hasattr(obj, "Shape"):
            try:
                shape_info = _shape_value(obj.Shape)
            except Exception as exc:
                shape_info = {"error": str(exc)}

        return {
            "name": obj.Name,
            "label": obj.Label,
            "type_id": obj.TypeId,
            "properties": properties,
            "shape_info": shape_info,
            "children": [child.Name for child in getattr(obj, "OutList", [])],
            "parents": [parent.Name for parent in getattr(obj, "InList", [])],
            "visibility": (
                bool(obj.ViewObject.Visibility)
                if hasattr(obj, "ViewObject") and obj.ViewObject
                else True
            ),
        }
    """
).strip()


def build_object_inspection_code(obj_name: str, doc_name: str | None) -> str:
    """Build the FreeCAD-side script used by all bridge implementations."""
    document_expression = (
        "FreeCAD.ActiveDocument"
        if doc_name is None
        else f"FreeCAD.getDocument({doc_name!r})"
    )
    return f"""\
doc = {document_expression}
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name}")

{OBJECT_INSPECTION_RUNTIME}

_result_ = _inspect_object_value(obj)
"""
