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
            if _is_valid_single_solid_feature(candidate):
                return candidate
        return None


    def _is_valid_single_solid_feature(candidate):
        """Return whether ``candidate`` owns one valid positive-volume solid."""
        shape = getattr(candidate, "Shape", None)
        if shape is None:
            return False
        try:
            return bool(
                not shape.isNull()
                and shape.isValid()
                and len(shape.Solids) == 1
                and float(shape.Volume) > 0
            )
        except Exception:
            return False


    def _resolve_partdesign_base_feature(
        doc,
        body,
        target,
        explicit_name=None,
    ):
        """Resolve an explicit or nearby single-solid base feature.

        Explicit selection is authoritative.  Without it, prefer the current
        Body Tip when it is a valid predecessor of ``target``; otherwise use
        the nearest valid single-solid feature before ``target`` in Body.Group.
        """
        group = list(getattr(body, "Group", []) or [])
        try:
            target_index = group.index(target)
        except ValueError as exc:
            raise ValueError(
                f"Object {getattr(target, 'Name', '<unknown>')!r} is not "
                f"present in Body {getattr(body, 'Name', '<unknown>')!r}"
            ) from exc

        if explicit_name:
            candidate = doc.getObject(explicit_name)
            if candidate is None:
                raise ValueError(f"Base feature not found: {explicit_name!r}")
            if candidate not in group:
                raise ValueError(
                    f"Base feature {explicit_name!r} is not in Body "
                    f"{getattr(body, 'Name', '<unknown>')!r}"
                )
            if group.index(candidate) >= target_index:
                raise ValueError(
                    f"Base feature {explicit_name!r} must precede "
                    f"{getattr(target, 'Name', '<unknown>')!r} in Body history"
                )
            if not _is_valid_single_solid_feature(candidate):
                raise ValueError(
                    f"Base feature {explicit_name!r} is not one valid solid"
                )
            return candidate, "explicit"

        current_tip = getattr(body, "Tip", None)
        if (
            current_tip in group
            and group.index(current_tip) < target_index
            and _is_valid_single_solid_feature(current_tip)
        ):
            return current_tip, "body_tip"

        candidate = _find_preceding_single_solid_feature(body, target)
        if candidate is None:
            raise ValueError(
                "No valid single-solid base feature exists before "
                f"{getattr(target, 'Name', '<unknown>')!r}"
            )
        return candidate, "nearest_predecessor"


    def _require_current_body_tip(body, feature, operation_name):
        """Reject dress-up operations on stale Body-history branches.

        PartDesign dress-up and one-off transform features are expected to extend
        the current Body Tip.  Creating them from an older feature can produce a
        branched dependency graph and later ``The graph must be a DAG`` errors.
        """
        current_tip = getattr(body, "Tip", None)
        if current_tip is feature:
            return
        raise ValueError(
            f"{operation_name} must target the current Body Tip "
            f"{getattr(current_tip, 'Name', None)!r}, not "
            f"{getattr(feature, 'Name', '<unknown>')!r}. Finish or remove the "
            "downstream branch first instead of inserting a dress-up feature "
            "into older Body history."
        )


    def _validated_shape_subelement_names(obj, requested, prefix):
        """Return validated ``EdgeN`` or ``FaceN`` names for ``obj.Shape``."""
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull() or not shape.isValid():
            raise ValueError(
                f"Object {getattr(obj, 'Name', '<unknown>')!r} has no valid shape"
            )
        collection_name = "Edges" if prefix == "Edge" else "Faces"
        available = len(getattr(shape, collection_name))
        names = list(requested or [f"{prefix}{index}" for index in range(1, available + 1)])
        if not names:
            raise ValueError(f"Object has no {collection_name.lower()} to select")
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate {prefix.lower()} references are not allowed: {names}")
        for name in names:
            if not isinstance(name, str) or not name.startswith(prefix):
                raise ValueError(f"Expected {prefix}N reference, got {name!r}")
            suffix = name[len(prefix):]
            if not suffix.isdigit() or int(suffix) < 1 or int(suffix) > available:
                raise ValueError(
                    f"{name!r} is outside the available {prefix} range "
                    f"1..{available}"
                )
        return names


    def _reject_nested_partdesign_pattern(feature):
        """Route chained pattern requests through a native MultiTransform."""
        pattern_types = {
            "PartDesign::LinearPattern",
            "PartDesign::PolarPattern",
            "PartDesign::Mirrored",
            "PartDesign::MultiTransform",
            "PartDesign::Scaled",
        }
        if getattr(feature, "TypeId", "") in pattern_types:
            raise ValueError(
                "Direct pattern-on-pattern input is intentionally rejected by "
                "this tool. Use multi_transform_pattern with the original seed "
                "feature so FreeCAD stores the chained transformations in one "
                "PartDesign::MultiTransform."
            )
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
            values = feature.getStatusString()
        except Exception:
            try:
                values = feature.State
            except Exception:
                return []
        if values is None:
            return []
        if isinstance(values, str):
            return [values] if values else []
        try:
            return [str(item) for item in values]
        except TypeError:
            return [str(values)]


    def _configure_feature_transform_mode(feature):
        """Keep a transformed feature in FreeCAD's feature-transform mode.

        ``TransformMode`` is an ``App::PropertyEnumeration``.  Its displayed
        labels differ between FreeCAD versions and downstream builds, so a
        hard-coded string such as ``"Features"`` is not portable.  FreeCAD
        stores feature-transform mode as the first enumeration entry and uses
        it as the constructor default.  Preserve that default, or restore the
        first advertised entry when a caller changed it.
        """
        diagnostics = {
            "available": False,
            "value": None,
            "options": [],
            "changed": False,
        }
        if not hasattr(feature, "TransformMode"):
            return diagnostics

        diagnostics["available"] = True
        try:
            options = list(feature.getEnumerationsOfProperty("TransformMode"))
        except Exception:
            options = []
        diagnostics["options"] = [str(item) for item in options]

        try:
            current = str(feature.TransformMode)
        except Exception:
            current = None

        if options and current != str(options[0]):
            feature.TransformMode = options[0]
            diagnostics["changed"] = True
            current = str(feature.TransformMode)

        diagnostics["value"] = current
        return diagnostics


    def _volume_diagnostics(base_volume, result_volume):
        """Return neutral before/after diagnostics without judging intent."""
        change = None
        change_ratio = None
        retained_ratio = None
        if base_volume is not None and result_volume is not None:
            change = float(result_volume) - float(base_volume)
            if abs(float(base_volume)) > 1e-12:
                change_ratio = change / float(base_volume)
                retained_ratio = float(result_volume) / float(base_volume)
        return {
            "base_volume": base_volume,
            "result_volume": result_volume,
            "volume_change": change,
            "volume_change_ratio": change_ratio,
            "retained_volume_ratio": retained_ratio,
            "note": (
                "Shape/Tip validity proves topological health, not that the "
                "operation changed the intended amount of material. Compare "
                "the before/after volume diagnostics with the expected feature."
            ),
        }


    def _pattern_material_change_diagnostics(
        pattern,
        base_shape,
        result_volume,
        relative_tolerance=1e-3,
    ):
        """Compare a pattern result with its effective transformed tool shape.

        ``Shape.isValid()`` and a matching Body Tip only prove topological
        health.  A transformed PartDesign feature also exposes ``AddSubShape``;
        intersecting that tool with the pre-pattern Body provides causal
        evidence for the amount of material that should be added or removed.

        If FreeCAD does not expose a usable tool shape, compare the result B-rep
        with the base B-rep. Report unavailable only when neither geometry can
        support a causal set-difference check.
        """
        diagnostics = {
            "available": False,
            "consistent": None,
            "method": None,
            "operation": None,
            "expected_material_change": None,
            "actual_material_change": None,
            "absolute_error": None,
            "tolerance": None,
            "reason": None,
        }

        try:
            base_volume = float(base_shape.Volume)
            result_volume = float(result_volume)
        except Exception as exc:
            diagnostics["reason"] = f"volume data unavailable: {exc}"
            return diagnostics

        tool_shape = getattr(pattern, "AddSubShape", None)
        use_tool_shape = True
        try:
            if tool_shape is None or tool_shape.isNull():
                use_tool_shape = False
            elif not tool_shape.isValid():
                use_tool_shape = False
        except Exception as exc:
            use_tool_shape = False
            diagnostics["reason"] = f"could not inspect AddSubShape: {exc}"

        actual_signed = result_volume - base_volume
        try:
            if use_tool_shape:
                method = "add_subshape"
                if actual_signed < 0.0:
                    operation = "subtractive"
                    expected = float(base_shape.common(tool_shape).Volume)
                    actual = -actual_signed
                elif actual_signed > 0.0:
                    operation = "additive"
                    expected = float(tool_shape.cut(base_shape).Volume)
                    actual = actual_signed
                else:
                    removed = float(base_shape.common(tool_shape).Volume)
                    added = float(tool_shape.cut(base_shape).Volume)
                    if removed >= added:
                        operation = "subtractive"
                        expected = removed
                    else:
                        operation = "additive"
                        expected = added
                    actual = 0.0
            else:
                # Some valid PartDesign patterns (notably PolarPattern in
                # several FreeCAD builds) do not publish AddSubShape. Compare
                # the result B-rep with the pre-pattern B-rep instead.
                result_shape = getattr(pattern, "Shape", None)
                if result_shape is None or result_shape.isNull():
                    diagnostics["reason"] = (
                        "pattern AddSubShape and result Shape are unavailable"
                    )
                    return diagnostics
                if not result_shape.isValid():
                    diagnostics["reason"] = "pattern result Shape is invalid"
                    return diagnostics
                method = "result_shape_difference"
                removed = float(base_shape.cut(result_shape).Volume)
                added = float(result_shape.cut(base_shape).Volume)
                if actual_signed < 0.0:
                    operation = "subtractive"
                    expected = removed
                    actual = -actual_signed
                elif actual_signed > 0.0:
                    operation = "additive"
                    expected = added
                    actual = actual_signed
                elif removed >= added:
                    operation = "subtractive"
                    expected = removed
                    actual = 0.0
                else:
                    operation = "additive"
                    expected = added
                    actual = 0.0
        except Exception as exc:
            diagnostics["reason"] = (
                f"could not evaluate pattern material change: {exc}"
            )
            return diagnostics

        body_scale = max(abs(base_volume), abs(result_volume), 1.0)
        tolerance = max(
            1e-7,
            body_scale * 1e-12,
            abs(expected) * float(relative_tolerance),
        )
        absolute_error = abs(actual - expected)
        consistent = absolute_error <= tolerance

        diagnostics.update({
            "available": True,
            "consistent": consistent,
            "method": method,
            "operation": operation,
            "expected_material_change": expected,
            "actual_material_change": actual,
            "absolute_error": absolute_error,
            "tolerance": tolerance,
            "reason": (
                None
                if consistent
                else (
                    "Pattern result volume is inconsistent with the effective "
                    f"material change measured by {method}"
                )
            ),
        })
        return diagnostics


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

        tip_matches = bool(body is None or body.Tip is feature)
        if require_body_tip and not tip_matches:
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
            "tip_matches": tip_matches,
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


    def _cleanup_failed_partdesign_features(
        doc,
        body,
        feature_names,
        original_tip_name=None,
    ):
        """Remove several transaction leftovers in reverse dependency order."""
        for feature_name in reversed(list(feature_names or [])):
            if not feature_name:
                continue
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
        constraint_indices = {}
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
                indices = sorted({int(value) for value in (getter() or [])})
            except Exception:
                continue
            if indices:
                constraint_indices[key] = {
                    "indices": indices,
                    "numbers": [index + 1 for index in indices],
                }
        if constraint_indices:
            result["constraint_references"] = constraint_indices
            result["indexing"] = {
                "constraint_index": "zero_based",
                "constraint_number": "one_based_gui",
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


    def _sketch_vector_value(value):
        if value is None:
            return None
        try:
            return {
                "x": float(value.x),
                "y": float(value.y),
                "z": float(value.z),
            }
        except Exception:
            return None


    def _sketch_expression_entries(sketch):
        entries = []
        try:
            raw_entries = list(sketch.ExpressionEngine or [])
        except Exception:
            raw_entries = []
        try:
            constraints = list(sketch.Constraints or [])
        except Exception:
            constraints = []

        for item in raw_entries:
            try:
                raw_path, expression = item[0], item[1]
            except Exception:
                continue

            source_path = str(raw_path)
            canonical_path = source_path
            constraint_index = _sketch_constraint_expression_index(
                sketch,
                source_path,
                constraints,
            )
            if constraint_index is not None:
                canonical_path = f"Constraints[{constraint_index}]"

            entry = {
                "path": canonical_path,
                "expression": str(expression),
            }
            if source_path != canonical_path:
                entry["source_path"] = source_path
            entries.append(entry)
        return entries


    def _sketch_geometry_details(sketch):
        values = []
        try:
            geometry_values = list(sketch.Geometry or [])
        except Exception:
            geometry_values = []
        construction_getter = getattr(sketch, "getConstruction", None)

        for index, geometry in enumerate(geometry_values):
            start = _sketch_vector_value(getattr(geometry, "StartPoint", None))
            end = _sketch_vector_value(getattr(geometry, "EndPoint", None))
            detail = {
                "index": index,
                "geometry_type": type(geometry).__name__,
                "start_point": start,
                "end_point": end,
                "geometry": {},
            }
            if callable(construction_getter):
                try:
                    detail["construction"] = bool(construction_getter(index))
                except Exception:
                    pass

            nested = detail["geometry"]
            for output_name, attribute in (
                ("center", "Center"),
                ("focus1", "Focus1"),
                ("focus2", "Focus2"),
            ):
                value = _sketch_vector_value(getattr(geometry, attribute, None))
                if value is not None:
                    nested[output_name] = value
            for output_name, attribute in (
                ("radius", "Radius"),
                ("major_radius", "MajorRadius"),
                ("minor_radius", "MinorRadius"),
                ("degree", "Degree"),
            ):
                try:
                    value = getattr(geometry, attribute)
                except Exception:
                    continue
                try:
                    nested[output_name] = float(value)
                except Exception:
                    nested[output_name] = str(value)
            for output_name, attribute in (
                ("is_closed", "isClosed"),
                ("is_periodic", "isPeriodic"),
            ):
                method = getattr(geometry, attribute, None)
                if callable(method):
                    try:
                        nested[output_name] = bool(method())
                    except Exception:
                        pass
            values.append(detail)
        return values


    def _sketch_constraint_expression_index(sketch, path, constraints):
        """Resolve a canonical ExpressionEngine path to a constraint index."""
        normalized = str(path).strip().lstrip(".")
        marker = "Constraints"
        marker_index = normalized.rfind(marker)
        if marker_index < 0:
            return None

        suffix = normalized[marker_index + len(marker):]
        constraint_name = None
        if suffix.startswith("["):
            closing = suffix.find("]")
            if closing < 0:
                return None
            token = suffix[1:closing].strip()
            if token.isdigit():
                index = int(token)
                return index if 0 <= index < len(constraints) else None
            if (
                len(token) >= 2
                and token[0] == token[-1]
                and token[0] in ("'", '"')
            ):
                constraint_name = token[1:-1]
        elif suffix.startswith("."):
            constraint_name = suffix[1:]

        if not constraint_name:
            return None

        index_getter = getattr(sketch, "getIndexByName", None)
        if callable(index_getter):
            try:
                index = int(index_getter(constraint_name))
                if 0 <= index < len(constraints):
                    return index
            except Exception:
                pass

        for index, constraint in enumerate(constraints):
            try:
                name = str(getattr(constraint, "Name", "") or "")
            except Exception:
                name = ""
            if name == constraint_name:
                return index
        return None


    def _sketch_constraint_details(sketch, expressions):
        expression_by_path = {
            item["path"]: item["expression"] for item in expressions
        }
        values = []
        try:
            constraints = list(sketch.Constraints or [])
        except Exception:
            constraints = []

        expression_by_index = {}
        for item in expressions:
            expression_index = _sketch_constraint_expression_index(
                sketch,
                item["path"],
                constraints,
            )
            if expression_index is not None:
                expression_by_index[expression_index] = item["expression"]

        for index, constraint in enumerate(constraints):
            path = f"Constraints[{index}]"
            detail = {
                "index": index,
                "number": index + 1,
                "constraint_type": getattr(
                    constraint, "Type", type(constraint).__name__
                ),
                "expression_path": path,
            }
            for output_name, attribute in (
                ("first_geometry", "First"),
                ("first_point", "FirstPos"),
                ("second_geometry", "Second"),
                ("second_point", "SecondPos"),
                ("third_geometry", "Third"),
                ("third_point", "ThirdPos"),
                ("value", "Value"),
                ("name", "Name"),
                ("label", "Label"),
            ):
                try:
                    item = getattr(constraint, attribute)
                except Exception:
                    continue
                if item is None or (isinstance(item, str) and not item):
                    continue
                if output_name == "value":
                    try:
                        item = float(item)
                    except Exception:
                        item = str(item)
                detail[output_name] = item

            driving_getter = getattr(sketch, "isDriving", None)
            if callable(driving_getter):
                try:
                    detail["driving"] = bool(driving_getter(index))
                except Exception:
                    pass

            datum_getter = getattr(sketch, "getDatum", None)
            if callable(datum_getter):
                try:
                    datum = datum_getter(index)
                    detail["datum"] = {
                        "value": float(datum.Value),
                        "unit": str(datum.Unit),
                        "display": str(datum),
                    }
                except Exception:
                    pass

            expression = expression_by_index.get(index)
            if expression is None:
                expression = expression_by_path.get(path)
            if expression is None and detail.get("name"):
                expression = expression_by_path.get(
                    f"Constraints.{detail['name']}"
                )
            if expression is not None:
                detail["expression"] = expression
            values.append(detail)
        return values


    def _sketch_detailed_info(sketch):
        expressions = _sketch_expression_entries(sketch)
        return {
            "geometry": _sketch_geometry_details(sketch),
            "constraints": _sketch_constraint_details(sketch, expressions),
            "expressions": expressions,
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
