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
