"""Shared FreeCAD-side geometry-preservation checks."""

GEOMETRY_PRESERVATION_RUNTIME = r'''
def _geometry_center(shape):
    """Return a stable mass/area center for solids, compounds, and shells."""
    try:
        center = shape.CenterOfMass
        return (float(center.x), float(center.y), float(center.z))
    except Exception:
        pass
    weighted_items = []
    for item in list(getattr(shape, "Solids", [])):
        try:
            center = item.CenterOfMass
            weight = abs(float(item.Volume))
            if weight > 0.0:
                weighted_items.append((weight, center))
        except Exception:
            continue
    if not weighted_items:
        for item in list(getattr(shape, "Faces", [])):
            try:
                center = item.CenterOfMass
                weight = abs(float(item.Area))
                if weight > 0.0:
                    weighted_items.append((weight, center))
            except Exception:
                continue
    if weighted_items:
        total = sum(weight for weight, center in weighted_items)
        return tuple(
            sum(
                weight * float(getattr(center, axis))
                for weight, center in weighted_items
            ) / total
            for axis in ("x", "y", "z")
        )
    box = shape.BoundBox
    return (
        (float(box.XMin) + float(box.XMax)) / 2.0,
        (float(box.YMin) + float(box.YMax)) / 2.0,
        (float(box.ZMin) + float(box.ZMax)) / 2.0,
    )


def _geometry_preservation_check(before, after, volume_abs, volume_rel, linear):
    """Compare invariants for an operation expected not to change geometry."""
    before_volume = float(before.Volume)
    after_volume = float(after.Volume)
    volume_delta = after_volume - before_volume
    volume_limit = max(
        float(volume_abs),
        float(volume_rel) * max(abs(before_volume), abs(after_volume)),
    )
    before_box = before.BoundBox
    after_box = after.BoundBox
    bbox_error = max(
        abs(float(first) - float(second))
        for first, second in zip(
            (
                before_box.XMin, before_box.YMin, before_box.ZMin,
                before_box.XMax, before_box.YMax, before_box.ZMax,
                before_box.XLength, before_box.YLength, before_box.ZLength,
            ),
            (
                after_box.XMin, after_box.YMin, after_box.ZMin,
                after_box.XMax, after_box.YMax, after_box.ZMax,
                after_box.XLength, after_box.YLength, after_box.ZLength,
            ),
        )
    )
    before_center = _geometry_center(before)
    after_center = _geometry_center(after)
    center_error = sum(
        (float(after_value) - float(before_value)) ** 2
        for before_value, after_value in zip(before_center, after_center)
    ) ** 0.5
    issues = []
    if abs(volume_delta) > volume_limit:
        issues.append(
            "volume drift %r exceeds limit %r" % (volume_delta, volume_limit)
        )
    if bbox_error > float(linear):
        issues.append(
            "bounding-box drift %r exceeds limit %r" % (bbox_error, linear)
        )
    if center_error > float(linear):
        issues.append(
            "center-of-mass drift %r exceeds limit %r" % (center_error, linear)
        )
    if len(before.Solids) != len(after.Solids):
        issues.append(
            "solid count changed from %d to %d"
            % (len(before.Solids), len(after.Solids))
        )
    return {
        "within_tolerance": not issues,
        "issues": issues,
        "before_volume": before_volume,
        "after_volume": after_volume,
        "volume_delta": volume_delta,
        "volume_limit": volume_limit,
        "max_bbox_error": bbox_error,
        "center_of_mass_error": center_error,
        "linear_limit": float(linear),
    }
'''.strip()
