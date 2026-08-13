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


    def _cylindrical_surface_value(surface):
        # Return stable cylinder geometry without probing unrelated surfaces.
        if surface is None or "cylinder" not in type(surface).__name__.lower():
            return None
        axis = _safe_attr(surface, "Axis")
        center = _safe_attr(surface, "Center")
        return {
            "radius": _finite_number(_safe_attr(surface, "Radius")),
            "axis_direction": _vector_value(axis) if axis is not None else None,
            "axis_point": _vector_value(center) if center is not None else None,
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


    def _shape_hash(value):
        method = getattr(value, "hashCode", None)
        if not callable(method):
            return None
        try:
            return int(method())
        except TypeError:
            try:
                return int(method(2147483647))
            except Exception:
                return None
        except Exception:
            return None


    def _shape_index(values, target, index_by_hash):
        # Resolve wrapped TopoShapes without an O(N) scan in the normal case.
        key = _shape_hash(target)
        if key is not None:
            for index in index_by_hash.get(key, []):
                if _shape_is_same(values[index], target):
                    return index
        for index, value in enumerate(values or []):
            if _shape_is_same(value, target):
                return index
        return None


    def _shape_index_map(values):
        result = {}
        for index, value in enumerate(values or []):
            key = _shape_hash(value)
            if key is not None:
                result.setdefault(key, []).append(index)
        return result


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


    def _page_value(values, offset, limit):
        total = len(values)
        start = max(0, int(offset or 0))
        if limit is None:
            page = values[start:]
        else:
            page = values[start:start + max(0, int(limit))]
        returned = len(page)
        next_offset = start + returned if start + returned < total else None
        return page, {
            "offset": start,
            "limit": limit,
            "returned": returned,
            "total": total,
            "has_more": next_offset is not None,
            "next_offset": next_offset,
        }


    def _shape_topology_value(
        shape,
        face_offset=0,
        face_limit=20,
        edge_offset=0,
        edge_limit=20,
        vertex_offset=0,
        vertex_limit=20,
        topology_kinds=None,
        topology_fields=None,
    ):
        faces = list(_safe_attr(shape, "Faces", []) or [])
        edges = list(_safe_attr(shape, "Edges", []) or [])
        vertexes = list(_safe_attr(shape, "Vertexes", []) or [])

        requested_kinds = set(
            ("faces", "edges", "vertices")
            if topology_kinds is None
            else topology_kinds
        )
        requested_fields = (
            None if topology_fields is None else set(topology_fields)
        )

        def wants(field):
            return requested_fields is None or field in requested_fields

        needs_edge_faces = any(
            wants(field)
            for field in ("adjacent_faces", "adjacent_surface_types")
        ) and bool(requested_kinds & {"faces", "edges"})
        needs_face_edges = "faces" in requested_kinds and wants("edges")
        needs_vertex_edges = "vertices" in requested_kinds and wants("adjacent_edges")
        needs_vertex_faces = "vertices" in requested_kinds and wants("adjacent_faces")

        edge_faces = {index: [] for index in range(len(edges))}
        face_edges = {index: [] for index in range(len(faces))}
        if needs_edge_faces or needs_face_edges:
            edge_index_by_hash = _shape_index_map(edges)
            for face_index, face in enumerate(faces):
                for face_edge in list(_safe_attr(face, "Edges", []) or []):
                    edge_index = _shape_index(edges, face_edge, edge_index_by_hash)
                    if edge_index is None:
                        continue
                    edge_name = f"Edge{edge_index + 1}"
                    if edge_name not in face_edges[face_index]:
                        face_edges[face_index].append(edge_name)
                    face_name = f"Face{face_index + 1}"
                    if face_name not in edge_faces[edge_index]:
                        edge_faces[edge_index].append(face_name)

        vertex_edges = {index: [] for index in range(len(vertexes))}
        if needs_vertex_edges:
            vertex_index_by_hash = _shape_index_map(vertexes)
            for edge_index, edge in enumerate(edges):
                for edge_vertex in list(_safe_attr(edge, "Vertexes", []) or []):
                    vertex_index = _shape_index(
                        vertexes, edge_vertex, vertex_index_by_hash
                    )
                    if vertex_index is not None:
                        vertex_edges[vertex_index].append(f"Edge{edge_index + 1}")

        vertex_faces = {index: [] for index in range(len(vertexes))}
        if needs_vertex_faces:
            vertex_index_by_hash = _shape_index_map(vertexes)
            for face_index, face in enumerate(faces):
                for face_vertex in list(_safe_attr(face, "Vertexes", []) or []):
                    vertex_index = _shape_index(
                        vertexes, face_vertex, vertex_index_by_hash
                    )
                    if vertex_index is not None:
                        vertex_faces[vertex_index].append(f"Face{face_index + 1}")

        face_page, face_paging = _page_value(faces, face_offset, face_limit)
        edge_page, edge_paging = _page_value(edges, edge_offset, edge_limit)
        vertex_page, vertex_paging = _page_value(
            vertexes, vertex_offset, vertex_limit
        )

        face_values = []
        for page_index, face in enumerate(face_page):
            face_index = face_paging["offset"] + page_index
            u, v = _representative_face_parameters(face)
            normal = None
            if wants("normal"):
                try:
                    normal = _vector_value(face.normalAt(u, v))
                except Exception:
                    pass
            surface = _safe_attr(face, "Surface")
            value = {"name": f"Face{face_index + 1}", "index": face_index + 1}
            if wants("surface_type"):
                value["surface_type"] = (
                    type(surface).__name__ if surface is not None else None
                )
            if any(wants(field) for field in ("radius", "axis_direction", "axis_point")):
                cylinder = _cylindrical_surface_value(surface)
                if cylinder is not None:
                    for field in ("radius", "axis_direction", "axis_point"):
                        if wants(field):
                            value[field] = cylinder[field]
            if wants("normal"):
                value["normal"] = normal
            if wants("area"):
                value["area"] = _finite_number(_safe_attr(face, "Area"))
            if wants("centroid"):
                center = _safe_attr(face, "CenterOfMass")
                value["centroid"] = _vector_value(center) if center is not None else None
                value["centroid_kind"] = "surface_area_centroid"
            if wants("adjacent_faces"):
                adjacent = set()
                for edge_name in face_edges.get(face_index, []):
                    adjacent.update(edge_faces.get(int(edge_name[4:]) - 1, []))
                adjacent.discard(value["name"])
                value["adjacent_faces"] = sorted(adjacent)
            if wants("edges"):
                value["edges"] = face_edges.get(face_index, [])
            if wants("convexity") or wants("curvature"):
                curvature = _face_curvature_value(face, u, v)
                if wants("convexity"):
                    value["convexity"] = curvature["classification"]
                if wants("curvature"):
                    value["curvature"] = curvature
            if wants("bounding_box"):
                value["bounding_box"] = _bounding_box_value(
                    _safe_attr(face, "BoundBox")
                )
            face_values.append(value)

        edge_values = []
        for page_index, edge in enumerate(edge_page):
            edge_index = edge_paging["offset"] + page_index
            start = end = None
            if wants("start_point") or wants("end_point") or wants("direction"):
                start, end = _edge_endpoints(edge)
            curve = _safe_attr(edge, "Curve")
            value = {"name": f"Edge{edge_index + 1}", "index": edge_index + 1}
            if wants("curve_type"):
                value["curve_type"] = type(curve).__name__ if curve is not None else None
            if wants("start_point"):
                value["start_point"] = _vector_value(start) if start is not None else None
            if wants("end_point"):
                value["end_point"] = _vector_value(end) if end is not None else None
            if wants("direction"):
                value["direction"] = _normalized_vector_between(start, end)
            if wants("length"):
                value["length"] = _finite_number(_safe_attr(edge, "Length"))
            if wants("radius"):
                value["radius"] = _finite_number(_safe_attr(curve, "Radius"))
            if wants("centroid"):
                center = _safe_attr(edge, "CenterOfMass")
                value["centroid"] = _vector_value(center) if center is not None else None
                value["centroid_kind"] = "curve_length_centroid"
            if wants("adjacent_faces"):
                value["adjacent_faces"] = edge_faces.get(edge_index, [])
            if wants("adjacent_surface_types"):
                value["adjacent_surface_types"] = [
                    type(_safe_attr(faces[int(name[4:]) - 1], "Surface")).__name__
                    for name in edge_faces.get(edge_index, [])
                    if _safe_attr(faces[int(name[4:]) - 1], "Surface") is not None
                ]
            if wants("bounding_box"):
                value["bounding_box"] = _bounding_box_value(
                    _safe_attr(edge, "BoundBox")
                )
            edge_values.append(value)

        vertex_values = []
        for page_index, vertex in enumerate(vertex_page):
            vertex_index = vertex_paging["offset"] + page_index
            point = _safe_attr(vertex, "Point")
            value = {"name": f"Vertex{vertex_index + 1}", "index": vertex_index + 1}
            if wants("point"):
                value["point"] = _vector_value(point) if point is not None else None
            if wants("adjacent_edges"):
                value["adjacent_edges"] = vertex_edges.get(vertex_index, [])
            if wants("adjacent_faces"):
                value["adjacent_faces"] = vertex_faces.get(vertex_index, [])
            if wants("tolerance"):
                value["tolerance"] = _finite_number(_safe_attr(vertex, "Tolerance"))
            vertex_values.append(value)

        result = {"topology_pages": {}}
        for kind, values, paging in (
            ("faces", face_values, face_paging),
            ("edges", edge_values, edge_paging),
            ("vertices", vertex_values, vertex_paging),
        ):
            if kind in requested_kinds:
                result[kind] = values
                result["topology_pages"][kind] = paging
        return result


    def _shape_value(
        shape,
        include_topology=False,
        face_offset=0,
        face_limit=20,
        edge_offset=0,
        edge_limit=20,
        vertex_offset=0,
        vertex_limit=20,
        topology_kinds=None,
        topology_fields=None,
    ):
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
            summary.update(
                _shape_topology_value(
                    shape,
                    face_offset=face_offset,
                    face_limit=face_limit,
                    edge_offset=edge_offset,
                    edge_limit=edge_limit,
                    vertex_offset=vertex_offset,
                    vertex_limit=vertex_limit,
                    topology_kinds=topology_kinds,
                    topology_fields=topology_fields,
                )
            )
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
                if item is not None and result["constraint_type"] == "Angle":
                    item = math.degrees(item)
                    result["value_unit"] = "deg"
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


    def _inspect_object_value(
        obj,
        include_properties=False,
        include_shape=True,
        include_topology=False,
        face_offset=0,
        face_limit=20,
        edge_offset=0,
        edge_limit=20,
        vertex_offset=0,
        vertex_limit=20,
        topology_kinds=None,
        topology_fields=None,
    ):
        properties = {}
        if include_properties:
            properties = {
                property_name: _property_entry(obj, property_name)
                for property_name in getattr(obj, "PropertiesList", [])
            }
        shape_info = None
        if include_shape and hasattr(obj, "Shape"):
            try:
                shape_info = _shape_value(
                    obj.Shape,
                    include_topology=include_topology,
                    face_offset=face_offset,
                    face_limit=face_limit,
                    edge_offset=edge_offset,
                    edge_limit=edge_limit,
                    vertex_offset=vertex_offset,
                    vertex_limit=vertex_limit,
                    topology_kinds=topology_kinds,
                    topology_fields=topology_fields,
                )
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


def build_object_inspection_code(
    obj_name: str,
    doc_name: str | None,
    *,
    include_properties: bool = False,
    include_shape: bool = True,
    include_topology: bool = False,
    face_offset: int = 0,
    face_limit: int | None = 20,
    edge_offset: int = 0,
    edge_limit: int | None = 20,
    vertex_offset: int = 0,
    vertex_limit: int | None = 20,
    topology_kinds: tuple[str, ...] | None = None,
    topology_fields: tuple[str, ...] | None = None,
) -> str:
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

_result_ = _inspect_object_value(
    obj,
    include_properties={include_properties!r},
    include_shape={include_shape!r},
    include_topology={include_topology!r},
    face_offset={face_offset!r},
    face_limit={face_limit!r},
    edge_offset={edge_offset!r},
    edge_limit={edge_limit!r},
    vertex_offset={vertex_offset!r},
    vertex_limit={vertex_limit!r},
    topology_kinds={topology_kinds!r},
    topology_fields={topology_fields!r},
)
"""
