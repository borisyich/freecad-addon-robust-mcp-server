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


    def _shape_is_same(left, right):
        for method_name in ("isSame", "isEqual"):
            method = getattr(left, method_name, None)
            if callable(method):
                try:
                    return bool(method(right))
                except Exception:
                    pass
        return left is right


    def _shape_name(values, target, prefix):
        for index, value in enumerate(values or []):
            if _shape_is_same(value, target):
                return f"{prefix}{index + 1}"
        return None


    def _normalized_vector_between(start, end):
        if start is None or end is None:
            return None
        try:
            dx = float(end.x) - float(start.x)
            dy = float(end.y) - float(start.y)
            dz = float(end.z) - float(start.z)
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
        except Exception:
            return None
        if length <= 1e-12:
            return None
        return {"x": dx / length, "y": dy / length, "z": dz / length}


    def _representative_face_parameters(face):
        center = _safe_attr(face, "CenterOfMass")
        surface = _safe_attr(face, "Surface")
        parameter = getattr(surface, "parameter", None)
        if center is not None and callable(parameter):
            try:
                uv = parameter(center)
                return float(uv[0]), float(uv[1])
            except Exception:
                pass

        parameter_range = _safe_attr(face, "ParameterRange")
        try:
            u_min, u_max, v_min, v_max = parameter_range
            return (
                (float(u_min) + float(u_max)) * 0.5,
                (float(v_min) + float(v_max)) * 0.5,
            )
        except Exception:
            return 0.0, 0.0


    def _face_curvature_value(face, u, v):
        try:
            minimum, maximum = face.curvatureAt(u, v)
            minimum = float(minimum)
            maximum = float(maximum)
        except Exception:
            return {
                "classification": "unknown",
                "principal_curvatures": None,
                "method": "oriented_principal_curvature",
            }

        orientation = str(_safe_attr(face, "Orientation", "")).lower()
        if "reversed" in orientation:
            minimum, maximum = -maximum, -minimum
        minimum, maximum = sorted((minimum, maximum))

        tolerance = 1e-9
        if abs(minimum) <= tolerance and abs(maximum) <= tolerance:
            classification = "flat"
        elif minimum < -tolerance and maximum > tolerance:
            classification = "saddle"
        elif minimum >= -tolerance and maximum > tolerance:
            classification = "convex"
        elif maximum <= tolerance and minimum < -tolerance:
            classification = "concave"
        else:
            classification = "unknown"

        return {
            "classification": classification,
            "principal_curvatures": {
                "minimum": _finite_number(minimum),
                "maximum": _finite_number(maximum),
            },
            "method": "oriented_principal_curvature",
        }


    def _edge_endpoints(edge):
        vertexes = list(_safe_attr(edge, "Vertexes", []) or [])
        start = _safe_attr(vertexes[0], "Point") if vertexes else None
        end = _safe_attr(vertexes[-1], "Point") if len(vertexes) > 1 else None

        if start is None:
            value_at = getattr(edge, "valueAt", None)
            if callable(value_at):
                try:
                    start = value_at(float(edge.FirstParameter))
                except Exception:
                    pass
        if end is None:
            value_at = getattr(edge, "valueAt", None)
            if callable(value_at):
                try:
                    end = value_at(float(edge.LastParameter))
                except Exception:
                    pass
        return start, end


    def _shape_topology_value(shape):
        faces = list(_safe_attr(shape, "Faces", []) or [])
        edges = list(_safe_attr(shape, "Edges", []) or [])

        edge_faces = {}
        for edge_index, edge in enumerate(edges):
            names = []
            for face_index, face in enumerate(faces):
                if any(
                    _shape_is_same(edge, face_edge)
                    for face_edge in list(_safe_attr(face, "Edges", []) or [])
                ):
                    names.append(f"Face{face_index + 1}")
            edge_faces[edge_index] = names

        face_values = []
        for face_index, face in enumerate(faces):
            u, v = _representative_face_parameters(face)
            normal = None
            try:
                normal = _vector_value(face.normalAt(u, v))
            except Exception:
                pass

            face_edge_names = []
            adjacent_faces = set()
            for face_edge in list(_safe_attr(face, "Edges", []) or []):
                edge_name = _shape_name(edges, face_edge, "Edge")
                if edge_name is None:
                    continue
                if edge_name not in face_edge_names:
                    face_edge_names.append(edge_name)
                edge_index = int(edge_name[4:]) - 1
                adjacent_faces.update(edge_faces.get(edge_index, []))
            adjacent_faces.discard(f"Face{face_index + 1}")

            surface = _safe_attr(face, "Surface")
            curvature = _face_curvature_value(face, u, v)
            face_values.append(
                {
                    "name": f"Face{face_index + 1}",
                    "index": face_index + 1,
                    "surface_type": (
                        type(surface).__name__ if surface is not None else None
                    ),
                    "normal": normal,
                    "area": _finite_number(_safe_attr(face, "Area")),
                    "center": (
                        _vector_value(_safe_attr(face, "CenterOfMass"))
                        if _safe_attr(face, "CenterOfMass") is not None
                        else None
                    ),
                    "adjacent_faces": sorted(adjacent_faces),
                    "edges": face_edge_names,
                    "convexity": curvature["classification"],
                    "curvature": curvature,
                    "bounding_box": _bounding_box_value(_safe_attr(face, "BoundBox")),
                }
            )

        edge_values = []
        for edge_index, edge in enumerate(edges):
            start, end = _edge_endpoints(edge)
            curve = _safe_attr(edge, "Curve")
            radius = _finite_number(_safe_attr(curve, "Radius"))
            edge_values.append(
                {
                    "name": f"Edge{edge_index + 1}",
                    "index": edge_index + 1,
                    "curve_type": type(curve).__name__ if curve is not None else None,
                    "start_point": _vector_value(start) if start is not None else None,
                    "end_point": _vector_value(end) if end is not None else None,
                    "direction": _normalized_vector_between(start, end),
                    "length": _finite_number(_safe_attr(edge, "Length")),
                    "radius": radius,
                    "center": (
                        _vector_value(_safe_attr(edge, "CenterOfMass"))
                        if _safe_attr(edge, "CenterOfMass") is not None
                        else None
                    ),
                    "adjacent_faces": edge_faces.get(edge_index, []),
                    "bounding_box": _bounding_box_value(_safe_attr(edge, "BoundBox")),
                }
            )

        return {"faces": face_values, "edges": edge_values}


    def _shape_value(shape, include_topology=True):
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
        if include_topology:
            summary.update(_shape_topology_value(shape))
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
            return _shape_value(value, include_topology=False)
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
