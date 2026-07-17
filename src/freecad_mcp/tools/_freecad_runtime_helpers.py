"""Reusable Python snippets executed inside the FreeCAD process.

The MCP server builds Python source strings and sends them to a separate
FreeCAD interpreter.  Helpers used by that generated code therefore cannot be
imported like normal host-side Python utilities unless the same package is
installed in FreeCAD's Python environment.  This module keeps the shared
runtime snippets in one place while preserving compatibility with every bridge
mode.
"""

from textwrap import dedent


def _runtime_code(source: str) -> str:
    """Normalize indentation for a generated FreeCAD runtime snippet."""
    return dedent(source).strip()


BODY_RUNTIME_HELPERS = _runtime_code(
    r'''
    def _find_body_containing_object(doc, target):
        """Return the unique PartDesign Body containing ``target``."""
        matches = []
        for candidate in doc.Objects:
            if candidate.TypeId != "PartDesign::Body":
                continue
            if target in (getattr(candidate, "Group", []) or []):
                matches.append(candidate)

        if len(matches) > 1:
            names = [getattr(candidate, "Name", "") for candidate in matches]
            raise ValueError(
                f"Object {getattr(target, 'Name', '<unknown>')!r} belongs to "
                f"multiple PartDesign Bodies: {names}"
            )
        return matches[0] if matches else None


    def _resolve_body_origin_feature(body, canonical_name):
        """Resolve a Body origin feature without document name suffixes.

        FreeCAD makes DocumentObject.Name unique across the document.  Origin
        objects in a second Body therefore receive names such as ``Z_Axis001``
        and ``XY_Plane001``.  Resolution must be scoped to the selected Body.
        """
        origin = getattr(body, "Origin", None)
        if origin is None:
            raise ValueError(
                f"Body has no Origin: {getattr(body, 'Name', '<unknown>')}"
            )

        features = list(getattr(origin, "OriginFeatures", []) or [])
        if not features:
            features = list(getattr(origin, "OutList", []) or [])

        suffixed_matches = []
        for feature in features:
            feature_name = getattr(feature, "Name", "")
            if feature_name == canonical_name:
                return feature
            if feature_name.startswith(canonical_name):
                suffix = feature_name[len(canonical_name):]
                if suffix.isdigit():
                    suffixed_matches.append(feature)

        if len(suffixed_matches) == 1:
            return suffixed_matches[0]
        if len(suffixed_matches) > 1:
            names = [
                getattr(feature, "Name", "") for feature in suffixed_matches
            ]
            raise ValueError(
                f"Ambiguous origin feature {canonical_name!r} in Body "
                f"{getattr(body, 'Name', '<unknown>')!r}: {names}"
            )

        available = [getattr(feature, "Name", "") for feature in features]
        raise ValueError(
            f"Origin feature not found: {canonical_name}. "
            f"Body={getattr(body, 'Name', '<unknown>')!r}; "
            f"available={available}"
        )


    def _find_preceding_single_solid_feature(body, target):
        """Return the nearest valid single-solid feature before target."""
        group = list(getattr(body, "Group", []) or [])
        try:
            target_index = group.index(target)
        except ValueError as exc:
            raise ValueError(
                f"Object {getattr(target, 'Name', '<unknown>')!r} is not "
                f"present in Body {getattr(body, 'Name', '<unknown>')!r}"
            ) from exc

        for candidate in reversed(group[:target_index]):
            shape = getattr(candidate, "Shape", None)
            if shape is None:
                continue
            try:
                if (
                    not shape.isNull()
                    and shape.isValid()
                    and len(shape.Solids) == 1
                    and float(shape.Volume) > 0
                ):
                    return candidate
            except Exception:
                continue
        return None
    '''
)


REVOLUTION_AXIS_RUNTIME_HELPERS = (
    BODY_RUNTIME_HELPERS
    + "\n\n"
    + _runtime_code(
        r'''
    def _resolve_revolution_axis(body, sketch, axis_name, operation_name):
        """Resolve and validate an axis for Revolution or Groove."""
        allowed_axes = {"Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H"}
        if axis_name not in allowed_axes:
            raise ValueError(
                f"Unsupported {operation_name.lower()} axis: {axis_name!r}. "
                f"Expected one of {sorted(allowed_axes)}"
            )

        if axis_name == "Sketch_V":
            return (sketch, ["V_Axis"]), "V_Axis"
        if axis_name == "Sketch_H":
            return (sketch, ["H_Axis"]), "H_Axis"

        axis_ref = axis_name.removeprefix("Base_")
        axis_obj = _resolve_body_origin_feature(body, f"{axis_ref}_Axis")

        try:
            sketch_rotation = sketch.getGlobalPlacement().Rotation
        except Exception:
            sketch_rotation = sketch.Placement.Rotation
        try:
            body_rotation = body.getGlobalPlacement().Rotation
        except Exception:
            body_rotation = body.Placement.Rotation

        sketch_normal = sketch_rotation.multVec(FreeCAD.Vector(0, 0, 1))
        axis_direction_map = {
            "X": FreeCAD.Vector(1, 0, 0),
            "Y": FreeCAD.Vector(0, 1, 0),
            "Z": FreeCAD.Vector(0, 0, 1),
        }
        axis_direction = body_rotation.multVec(axis_direction_map[axis_ref])
        if abs(sketch_normal.dot(axis_direction)) > 0.9999:
            raise ValueError(
                f"Axis {axis_name!r} is perpendicular to the sketch plane. "
                f"{operation_name} axis must lie in the sketch plane. "
                "For XY use Base_X or Base_Y; for XZ use Base_X or Base_Z; "
                "for YZ use Base_Y or Base_Z."
            )

        return (axis_obj, [""]), axis_obj.Name
    '''
    )
)


FEATURE_VALIDATION_RUNTIME_HELPERS = _runtime_code(
    r'''
    def _feature_status_strings(feature):
        """Return FreeCAD feature status entries as plain strings."""
        try:
            return [str(item) for item in feature.getStatusString()]
        except Exception:
            try:
                return [str(item) for item in feature.State]
            except Exception:
                return []


    def _validate_single_solid_feature(feature, body=None, require_body_tip=True):
        """Validate the common result contract of a PartDesign feature."""
        reasons = []
        status = _feature_status_strings(feature)
        shape = getattr(feature, "Shape", None)
        shape_valid = False
        solid_count = 0
        result_volume = None

        if shape is None:
            reasons.append("result shape is missing")
        else:
            try:
                if shape.isNull():
                    reasons.append("result shape is null")
                else:
                    shape_valid = bool(shape.isValid())
                    if not shape_valid:
                        reasons.append("result shape is invalid")
                    try:
                        solid_count = len(shape.Solids)
                    except Exception:
                        solid_count = 0
                    if solid_count != 1:
                        reasons.append(f"expected one solid, got {solid_count}")
                    try:
                        result_volume = float(shape.Volume)
                    except Exception:
                        result_volume = None
            except Exception as exc:
                reasons.append(f"could not inspect result shape: {exc}")

        if require_body_tip and body is not None and body.Tip is not feature:
            reasons.append(
                f"Body Tip is {getattr(body.Tip, 'Name', None)!r}, "
                f"not {getattr(feature, 'Name', '<unknown>')!r}"
            )

        error_status = [
            item
            for item in status
            if "error" in item.lower() or "invalid" in item.lower()
        ]
        if error_status:
            reasons.append("feature status: " + ", ".join(error_status))

        return {
            "ok": not reasons,
            "reasons": reasons,
            "status": status,
            "shape_valid": shape_valid,
            "solid_count": solid_count,
            "result_volume": result_volume,
        }


    def _cleanup_failed_partdesign_feature(
        doc,
        body,
        feature_name,
        original_tip_name=None,
    ):
        """Remove a feature left behind by an aborted FreeCAD transaction."""
        if feature_name:
            leftover = doc.getObject(feature_name)
            if leftover is not None:
                try:
                    doc.removeObject(feature_name)
                except Exception:
                    pass
        if original_tip_name:
            try:
                original_tip = doc.getObject(original_tip_name)
                if original_tip is not None:
                    body.Tip = original_tip
            except Exception:
                pass
        try:
            doc.recompute()
        except Exception:
            pass


    def _validate_additive_feature(
        feature,
        body,
        base_shape=None,
        volume_tolerance=None,
    ):
        """Validate that an additive feature creates effective solid volume.

        The common shape checks are not enough for PartDesign additive
        operations: FreeCAD can create a syntactically valid feature that is
        detached from the existing Body or leaves the Body unchanged.  This
        contract therefore requires one valid solid and a measurable positive
        volume delta.  For the first solid feature, a positive result volume is
        sufficient.
        """
        validation = _validate_single_solid_feature(feature, body)
        reasons = validation["reasons"]
        result_volume = validation["result_volume"]
        base_volume = None
        added_volume = None

        if base_shape is not None:
            try:
                base_volume = float(base_shape.Volume)
            except Exception:
                reasons.append("could not inspect base shape volume")

        reference_volume = abs(base_volume or result_volume or 0.0)
        tolerance = (
            max(1e-7, reference_volume * 1e-9)
            if volume_tolerance is None
            else float(volume_tolerance)
        )

        if result_volume is None:
            reasons.append("result volume is unavailable")
        elif base_volume is None:
            added_volume = result_volume
            if result_volume <= tolerance:
                reasons.append(
                    f"additive feature produced non-positive volume: "
                    f"result={result_volume:.9g}"
                )
        else:
            added_volume = result_volume - base_volume
            if added_volume <= tolerance:
                reasons.append(
                    f"body volume did not increase: base={base_volume:.9g}, "
                    f"result={result_volume:.9g}"
                )

        validation.update(
            {
                "ok": not reasons,
                "base_volume": base_volume,
                "added_volume": added_volume,
                "volume_tolerance": tolerance,
            }
        )
        return validation


    def _validate_subtractive_feature(
        feature,
        body,
        base_shape,
        expected_removed_solid_count=None,
        volume_tolerance=None,
    ):
        """Validate a subtractive feature against the solid before the cut."""
        validation = _validate_single_solid_feature(feature, body)
        reasons = validation["reasons"]
        result_volume = validation["result_volume"]
        base_volume = float(base_shape.Volume)
        tolerance = (
            max(1e-7, abs(base_volume) * 1e-9)
            if volume_tolerance is None
            else float(volume_tolerance)
        )
        removed_volume = None
        removed_solid_count = 0

        if result_volume is not None:
            removed_volume = base_volume - result_volume
            if removed_volume <= tolerance:
                reasons.append(
                    f"body volume did not decrease: base={base_volume:.9g}, "
                    f"result={result_volume:.9g}"
                )
            elif expected_removed_solid_count is not None:
                try:
                    removed_shape = base_shape.cut(feature.Shape)
                    removed_solid_count = len(removed_shape.Solids)
                    if removed_solid_count != expected_removed_solid_count:
                        reasons.append(
                            f"expected {expected_removed_solid_count} independent "
                            f"cut(s), got {removed_solid_count}. A profile may be "
                            "outside the solid or multiple cuts may overlap."
                        )
                except Exception as exc:
                    reasons.append(f"could not validate removed material: {exc}")

        validation.update(
            {
                "ok": not reasons,
                "removed_volume": removed_volume,
                "removed_solid_count": removed_solid_count,
            }
        )
        return validation
    '''
)


SKETCH_ANALYSIS_RUNTIME_HELPERS = _runtime_code(
    r'''
    def _sketch_point_name(position):
        try:
            position = int(position)
        except Exception:
            return str(position)
        return {
            1: "start",
            2: "end",
            3: "center",
        }.get(position, "geometry")


    def _sketch_index_pairs(values):
        """Normalize FreeCAD geometry/point pairs to compact dictionaries."""
        normalized = []
        for item in values or []:
            try:
                geometry_index = int(item[0])
                point_position = item[1] if len(item) > 1 else -1
            except Exception:
                continue
            normalized.append(
                {
                    "geometry_index": geometry_index,
                    "point": _sketch_point_name(point_position),
                }
            )
        return normalized


    def _group_unconstrained_geometry(values):
        grouped = {}
        for item in values:
            geometry_index = item["geometry_index"]
            point = item["point"]
            grouped.setdefault(geometry_index, [])
            if point not in grouped[geometry_index]:
                grouped[geometry_index].append(point)
        return [
            {
                "geometry_index": geometry_index,
                "elements": grouped[geometry_index],
            }
            for geometry_index in sorted(grouped)
        ]


    def _sketch_solver_state(sketch):
        solve_code = None
        try:
            solve_code = int(sketch.solve())
        except Exception:
            pass

        solver_message = None
        status_getter = getattr(sketch, "getStatusString", None)
        if callable(status_getter):
            try:
                raw_message = status_getter()
                if isinstance(raw_message, (list, tuple)):
                    raw_message = "; ".join(str(item) for item in raw_message if item)
                if raw_message:
                    solver_message = str(raw_message)
            except Exception:
                pass

        fully_constrained = None
        try:
            fully_constrained = bool(sketch.FullyConstrained)
        except Exception:
            pass

        remaining_dof = None
        try:
            remaining_dof = int(sketch.DoF)
        except Exception:
            pass

        status_by_code = {
            -4: "over_constrained",
            -3: "conflicting",
            -2: "redundant",
            -1: "solver_error",
        }
        if solve_code in status_by_code:
            status = status_by_code[solve_code]
            fully_constrained = False
        elif fully_constrained is True or remaining_dof == 0:
            status = "fully_constrained"
            fully_constrained = True
        elif solve_code == 0:
            status = "under_constrained"
            fully_constrained = False
        else:
            status = "unknown"

        result = {
            "status": status,
            "solve_code": solve_code,
            "fully_constrained": fully_constrained,
            "remaining_dof": remaining_dof,
        }
        if solver_message:
            result["message"] = solver_message
        return result


    def _sketch_open_vertex_value(value):
        try:
            return {
                "x": float(value.x),
                "y": float(value.y),
                "z": float(value.z),
            }
        except Exception:
            pass
        try:
            coordinates = list(value)
            return {
                "x": float(coordinates[0]),
                "y": float(coordinates[1]),
                "z": float(coordinates[2]) if len(coordinates) > 2 else 0.0,
            }
        except Exception:
            return None


    def _sketch_profile_state(sketch, construction_geometry_count):
        open_vertices = []
        getter = getattr(sketch, "getOpenVertices", None)
        if callable(getter):
            try:
                for value in getter() or []:
                    serialized = _sketch_open_vertex_value(value)
                    if serialized is not None:
                        open_vertices.append(serialized)
            except Exception:
                pass

        closed_wire_count = 0
        open_wire_count = 0
        shape_valid = None
        shape = getattr(sketch, "Shape", None)
        if shape is not None:
            try:
                if not shape.isNull():
                    try:
                        shape_valid = bool(shape.isValid())
                    except Exception:
                        pass
                    for wire in getattr(shape, "Wires", []) or []:
                        try:
                            is_closed = bool(wire.isClosed())
                        except Exception:
                            is_closed = False
                        if is_closed:
                            closed_wire_count += 1
                        else:
                            open_wire_count += 1
            except Exception:
                pass

        regular_geometry_count = max(
            0,
            int(getattr(sketch, "GeometryCount", 0)) - construction_geometry_count,
        )
        if regular_geometry_count == 0:
            state = "empty"
        elif shape_valid is False:
            state = "invalid"
        elif open_vertices or open_wire_count:
            state = "open"
        elif closed_wire_count > 0:
            state = "closed"
        else:
            state = "non_profile_geometry"

        return {
            "state": state,
            "closed": state == "closed",
            "closed_wire_count": closed_wire_count,
            "open_wire_count": open_wire_count,
            "open_vertices": open_vertices,
            "shape_valid": shape_valid,
        }


    def _analyze_sketch(sketch):
        geometry_count = int(getattr(sketch, "GeometryCount", 0))
        constraint_count = int(getattr(sketch, "ConstraintCount", 0))
        external_geometry_count = len(getattr(sketch, "ExternalGeometry", []) or [])

        construction_geometry_count = 0
        construction_getter = getattr(sketch, "getConstruction", None)
        if callable(construction_getter):
            for index in range(geometry_count):
                try:
                    construction_geometry_count += int(bool(construction_getter(index)))
                except Exception:
                    pass

        solver = _sketch_solver_state(sketch)
        profile = _sketch_profile_state(sketch, construction_geometry_count)

        dependent = []
        dependent_getter = getattr(sketch, "getGeometryWithDependentParameters", None)
        if callable(dependent_getter):
            try:
                dependent = _sketch_index_pairs(dependent_getter())
            except Exception:
                pass
        unconstrained = _group_unconstrained_geometry(dependent)

        issues = []
        hints = []
        solver_status = solver["status"]
        if solver_status == "over_constrained":
            issues.append("Sketch is over-constrained.")
            hints.append("Remove or revise the most recently added constraint.")
        elif solver_status == "conflicting":
            issues.append("Sketch contains conflicting constraints.")
            hints.append("Inspect the latest constraints and remove the conflicting one.")
        elif solver_status == "redundant":
            issues.append("Sketch contains a redundant constraint.")
            hints.append("Remove the redundant constraint before adding more dimensions.")
        elif solver_status == "solver_error":
            issues.append("Sketch solver failed.")
            hints.append("Undo the last edit and inspect the affected geometry and constraints.")
        elif solver_status == "under_constrained":
            remaining_dof = solver["remaining_dof"]
            if remaining_dof is not None:
                issues.append(f"Sketch has {remaining_dof} remaining degree(s) of freedom.")
            else:
                issues.append("Sketch is under-constrained.")
            if unconstrained:
                indices = [item["geometry_index"] for item in unconstrained]
                hints.append(f"Constrain geometry indices {indices}.")
            else:
                hints.append("Add positional or dimensional constraints to remove remaining motion.")

        if profile["state"] == "open":
            count = len(profile["open_vertices"])
            issues.append(
                f"Profile is open with {count} detected open endpoint(s)."
                if count
                else "Profile contains open wire(s)."
            )
            hints.append("Add Coincident constraints between matching open endpoints.")
        elif profile["state"] == "invalid":
            issues.append("Sketch shape is geometrically invalid.")
            hints.append("Check for self-intersections, overlapping edges, or zero-length geometry.")
        elif profile["state"] == "non_profile_geometry":
            issues.append("Sketch has no closed wire suitable for a profile operation.")
            hints.append("Connect the regular geometry into at least one closed contour.")

        solver_healthy = solver_status not in {
            "over_constrained",
            "conflicting",
            "redundant",
            "solver_error",
        }
        result = {
            "geometry_count": geometry_count,
            "constraint_count": constraint_count,
            "construction_geometry_count": construction_geometry_count,
            "external_geometry_count": external_geometry_count,
            "solver": solver,
            "profile": profile,
            "profile_ready": bool(profile["closed"] and solver_healthy),
        }
        if unconstrained:
            result["unconstrained"] = unconstrained
        if issues:
            result["issues"] = issues
        if hints:
            result["hints"] = hints
        return result
    '''
)
