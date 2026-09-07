"""General-purpose, transactional BREP inspection and surgery tools."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from pydantic import Field

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveTimeout = Annotated[int, Field(ge=1, le=600000)]


def _vector3(value: list[float], name: str) -> None:
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values")


def register_brep_tools(
    mcp: Any,
    get_bridge: Callable[[], Awaitable[Any]],
) -> None:
    """Register imported/static-shape analysis, repair, and pattern tools."""

    async def _execute(code: str, fallback: str, timeout_ms: int) -> dict[str, Any]:
        bridge = await get_bridge()
        execution = await bridge.execute_python(code, timeout_ms=timeout_ms)
        if execution.success and isinstance(execution.result, dict):
            return execution.result
        raise ValueError(execution.failure_details(fallback))

    @mcp.tool()
    async def group_feature_faces(
        object_name: str,
        face_names: list[str],
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 30000,
    ) -> dict[str, Any]:
        """Group selected FaceN references into edge-connected feature regions."""
        if not face_names:
            raise ValueError("face_names must not be empty")
        code = f"""
import Part

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError("Object not found: {object_name}")
shape = getattr(obj, "Shape", None)
if shape is None or shape.isNull():
    raise ValueError("Object has a null Shape")

indices = []
for reference in {face_names!r}:
    if not reference.startswith("Face") or not reference[4:].isdigit():
        raise ValueError(f"Invalid face reference: {{reference}}")
    index = int(reference[4:])
    if index < 1 or index > len(shape.Faces):
        raise ValueError(f"Face reference out of range: {{reference}}")
    if index not in indices:
        indices.append(index)

edge_to_faces = {{}}
for index in indices:
    for edge in shape.Faces[index - 1].Edges:
        key = edge.hashCode()
        edge_to_faces.setdefault(key, []).append(index)
neighbors = {{index: set() for index in indices}}
for attached in edge_to_faces.values():
    for left in attached:
        neighbors[left].update(right for right in attached if right != left)

remaining = set(indices)
groups = []
while remaining:
    pending = [min(remaining)]
    component = []
    remaining.remove(pending[0])
    while pending:
        current = pending.pop()
        component.append(current)
        for adjacent in sorted(neighbors[current]):
            if adjacent in remaining:
                remaining.remove(adjacent)
                pending.append(adjacent)
    component.sort()
    faces = [shape.Faces[index - 1] for index in component]
    total_area = sum(float(face.Area) for face in faces)
    if total_area > 0.0:
        center = sum(
            (face.CenterOfMass * float(face.Area) for face in faces),
            FreeCAD.Vector(),
        ) / total_area
    else:
        center = FreeCAD.Vector()
    groups.append({{
        "face_names": [f"Face{{index}}" for index in component],
        "face_count": len(component),
        "area": total_area,
        "center": [float(center.x), float(center.y), float(center.z)],
    }})

groups.sort(key=lambda item: item["face_names"][0])
_result_ = {{
    "object_name": obj.Name,
    "selected_face_count": len(indices),
    "group_count": len(groups),
    "groups": groups,
}}
"""
        return await _execute(code, "Group feature faces failed", timeout_ms)

    @mcp.tool()
    async def detect_rotational_pattern(
        object_name: str,
        face_groups: list[list[str]],
        axis_origin: list[FiniteFloat] | None = None,
        axis_direction: list[FiniteFloat] | None = None,
        angular_tolerance_deg: NonNegativeFloat = 0.5,
        radial_tolerance: NonNegativeFloat = 1e-4,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 30000,
    ) -> dict[str, Any]:
        """Detect equal angular spacing of supplied face groups about an axis."""
        axis_origin = axis_origin or [0.0, 0.0, 0.0]
        axis_direction = axis_direction or [0.0, 0.0, 1.0]
        _vector3(axis_origin, "axis_origin")
        _vector3(axis_direction, "axis_direction")
        if len(face_groups) < 2 or any(not group for group in face_groups):
            raise ValueError("face_groups must contain at least two non-empty groups")
        code = f"""
import math

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError("Object not found: {object_name}")
shape = getattr(obj, "Shape", None)
if shape is None or shape.isNull():
    raise ValueError("Object has a null Shape")
origin = FreeCAD.Vector(*{axis_origin!r})
axis = FreeCAD.Vector(*{axis_direction!r})
if axis.Length <= 0.0:
    raise ValueError("axis_direction must be non-zero")
axis.normalize()
helper = FreeCAD.Vector(1, 0, 0) if abs(axis.x) < 0.9 else FreeCAD.Vector(0, 1, 0)
basis_x = axis.cross(helper)
basis_x.normalize()
basis_y = axis.cross(basis_x)
basis_y.normalize()

records = []
for group_index, references in enumerate({face_groups!r}):
    faces = []
    for reference in references:
        if not reference.startswith("Face") or not reference[4:].isdigit():
            raise ValueError(f"Invalid face reference: {{reference}}")
        index = int(reference[4:])
        if index < 1 or index > len(shape.Faces):
            raise ValueError(f"Face reference out of range: {{reference}}")
        faces.append(shape.Faces[index - 1])
    area = sum(float(face.Area) for face in faces)
    if area <= 0.0:
        raise ValueError(f"Face group {{group_index}} has zero area")
    center = sum(
        (face.CenterOfMass * float(face.Area) for face in faces),
        FreeCAD.Vector(),
    ) / area
    relative = center - origin
    radial = relative - axis * relative.dot(axis)
    radius = float(radial.Length)
    angle = math.degrees(math.atan2(radial.dot(basis_y), radial.dot(basis_x))) % 360.0
    records.append({{
        "group_index": group_index,
        "face_names": references,
        "center": [float(center.x), float(center.y), float(center.z)],
        "radius": radius,
        "angle_deg": angle,
        "area": area,
    }})

records.sort(key=lambda item: item["angle_deg"])
count = len(records)
expected_pitch = 360.0 / count
gaps = []
for index, record in enumerate(records):
    next_angle = records[(index + 1) % count]["angle_deg"]
    if index == count - 1:
        next_angle += 360.0
    gaps.append(next_angle - record["angle_deg"])
angular_deviations = [abs(gap - expected_pitch) for gap in gaps]
radii = [record["radius"] for record in records]
radial_spread = max(radii) - min(radii)
equal_spacing = (
    max(angular_deviations) <= {angular_tolerance_deg!r}
    and radial_spread <= {radial_tolerance!r}
)
_result_ = {{
    "pattern_detected": equal_spacing,
    "occurrence_count": count,
    "expected_pitch_deg": expected_pitch,
    "angular_gaps_deg": gaps,
    "max_angular_deviation_deg": max(angular_deviations),
    "radial_spread": radial_spread,
    "ordered_groups": records,
    "axis_origin": {axis_origin!r},
    "axis_direction": [float(axis.x), float(axis.y), float(axis.z)],
}}
"""
        return await _execute(code, "Detect rotational pattern failed", timeout_ms)

    @mcp.tool()
    async def defeature_faces(
        object_name: str,
        face_names: list[str],
        result_name: str | None = None,
        refine: bool = True,
        expected_solid_count: Annotated[int, Field(ge=1)] | None = 1,
        hide_source: bool = True,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Remove selected faces with OCCT defeaturing and reject no-op results."""
        if not face_names:
            raise ValueError("face_names must not be empty")
        code = f"""
requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
source = doc.getObject({object_name!r})
if source is None:
    raise ValueError("Object not found: {object_name}")
source_shape = getattr(source, "Shape", None)
if source_shape is None or source_shape.isNull() or not source_shape.isValid():
    raise ValueError("Source Shape must be non-null and valid")
faces = []
for reference in {face_names!r}:
    if not reference.startswith("Face") or not reference[4:].isdigit():
        raise ValueError(f"Invalid face reference: {{reference}}")
    index = int(reference[4:])
    if index < 1 or index > len(source_shape.Faces):
        raise ValueError(f"Face reference out of range: {{reference}}")
    faces.append(source_shape.Faces[index - 1])
if not hasattr(source_shape, "defeaturing"):
    raise ValueError("FreeCAD Shape.defeaturing is unavailable")

doc.openTransaction("Defeature Faces")
try:
    raw_healed = source_shape.defeaturing(faces)
    if raw_healed.isNull() or not raw_healed.isValid():
        raise ValueError("OCCT defeaturing produced a null or invalid Shape")
    base_volume = float(source_shape.Volume)
    defeatured_volume = float(raw_healed.Volume)
    base_area = float(source_shape.Area)
    defeatured_area = float(raw_healed.Area)
    base_counts = (len(source_shape.Faces), len(source_shape.Edges), len(source_shape.Vertexes))
    defeatured_counts = (len(raw_healed.Faces), len(raw_healed.Edges), len(raw_healed.Vertexes))
    volume_tolerance = max(1e-7, abs(base_volume) * 1e-10)
    area_tolerance = max(1e-7, abs(base_area) * 1e-10)
    measurable_change = bool(
        abs(defeatured_volume - base_volume) > volume_tolerance
        or abs(defeatured_area - base_area) > area_tolerance
        or defeatured_counts != base_counts
    )
    if not measurable_change:
        raise ValueError(
            "OCCT defeaturing completed without changing volume, area, or topology; "
            "the selected faces were not removed"
        )
    healed = raw_healed
    refine_applied = False
    refine_fallback_reason = None
    if {refine!r}:
        try:
            refined = raw_healed.removeSplitter()
            if refined.isNull() or not refined.isValid():
                raise ValueError("removeSplitter produced a null or invalid Shape")
            healed = refined
            refine_applied = True
        except Exception as exc:
            refine_fallback_reason = str(exc)
    result_volume = float(healed.Volume)
    result_area = float(healed.Area)
    result_counts = (len(healed.Faces), len(healed.Edges), len(healed.Vertexes))
    solid_count = len(healed.Solids)
    expected_count = {expected_solid_count!r}
    if expected_count is not None and solid_count != expected_count:
        raise ValueError(
            f"Expected {{expected_count}} solid(s), got {{solid_count}}"
        )
    result_obj = doc.addObject("Part::Feature", {result_name!r} or "Defeatured")
    result_obj.Shape = healed
    source.Visibility = not {hide_source!r}
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result_obj.Name,
        "source_name": source.Name,
        "removed_face_count": len(faces),
        "shape_valid": True,
        "shape_type": healed.ShapeType,
        "solid_count": solid_count,
        "base_volume": base_volume,
        "defeatured_volume": defeatured_volume,
        "result_volume": result_volume,
        "volume_delta": result_volume - base_volume,
        "base_area": base_area,
        "defeatured_area": defeatured_area,
        "result_area": result_area,
        "area_delta": result_area - base_area,
        "base_topology_counts": {{"faces": base_counts[0], "edges": base_counts[1], "vertices": base_counts[2]}},
        "defeatured_topology_counts": {{"faces": defeatured_counts[0], "edges": defeatured_counts[1], "vertices": defeatured_counts[2]}},
        "result_topology_counts": {{"faces": result_counts[0], "edges": result_counts[1], "vertices": result_counts[2]}},
        "measurable_change": measurable_change,
        "refined": refine_applied,
        "refine_requested": {refine!r},
        "refine_applied": refine_applied,
        "refine_fallback_reason": refine_fallback_reason,
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Defeature faces failed", timeout_ms)

    @mcp.tool()
    async def extract_feature_material(
        source_name: str,
        healed_name: str,
        mode: Literal["removed_material", "filled_void"] = "removed_material",
        component_indices: list[Annotated[int, Field(ge=1)]] | None = None,
        component_volume_min: NonNegativeFloat | None = None,
        component_volume_max: NonNegativeFloat | None = None,
        component_sort_by: Literal[
            "index", "volume", "center_x", "center_y", "center_z"
        ] = "index",
        component_sort_order: Literal["asc", "desc"] = "asc",
        component_limit: Annotated[int, Field(ge=1, le=1000)] | None = None,
        result_prefix: str = "RecoveredFeature",
        refine: bool = True,
        fuzzy_tolerance: NonNegativeFloat = 0.0,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Extract valid material/void solids using semantic component filters."""
        if (
            component_volume_min is not None
            and component_volume_max is not None
            and component_volume_min > component_volume_max
        ):
            raise ValueError(
                "component_volume_min must not exceed component_volume_max"
            )
        code = f"""
import Part

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
source = doc.getObject({source_name!r})
healed_obj = doc.getObject({healed_name!r})
if source is None or healed_obj is None:
    raise ValueError("Source or healed object was not found")
source_shape = getattr(source, "Shape", None)
healed = getattr(healed_obj, "Shape", None)
if any(shape is None or shape.isNull() or not shape.isValid() for shape in (source_shape, healed)):
    raise ValueError("Source and healed Shapes must be non-null and valid")

doc.openTransaction("Extract Feature Material")
try:
    left, right = (
        (source_shape, healed)
        if {mode!r} == "removed_material"
        else (healed, source_shape)
    )
    if {fuzzy_tolerance!r} > 0.0:
        try:
            raw_recovered = left.cut(right, {fuzzy_tolerance!r})
        except TypeError as exc:
            raise ValueError(
                "This FreeCAD build does not expose fuzzy tolerance for Shape.cut"
            ) from exc
    else:
        raw_recovered = left.cut(right)
    if raw_recovered.isNull():
        raise ValueError("Shape difference produced a null feature region")
    container_valid = bool(raw_recovered.isValid())
    solids = list(raw_recovered.Solids)
    if not solids:
        raise ValueError("Shape difference contains no solid feature components")
    requested_indices = {component_indices!r}
    requested = requested_indices or list(range(1, len(solids) + 1))
    if len(set(requested)) != len(requested):
        raise ValueError("component_indices contains duplicates")
    if any(index < 1 or index > len(solids) for index in requested):
        raise ValueError(f"component_indices must be between 1 and {{len(solids)}}")

    records = []
    invalid_component_indices = []
    for component_index, component_shape in enumerate(solids, start=1):
        component_valid = bool(component_shape.isValid())
        if not component_valid:
            invalid_component_indices.append(component_index)
        center = component_shape.CenterOfMass
        records.append({{
            "component_index": component_index,
            "shape": component_shape,
            "valid": component_valid,
            "volume": float(component_shape.Volume),
            "center": [float(center.x), float(center.y), float(center.z)],
        }})
    invalid_requested = sorted(set(requested).intersection(invalid_component_indices))
    if requested_indices is not None and invalid_requested:
        raise ValueError(
            f"Explicitly requested components are invalid: {{invalid_requested}}"
        )
    selected = [record for record in records if record["component_index"] in requested]
    selected = [record for record in selected if record["valid"]]
    if {component_volume_min!r} is not None:
        selected = [record for record in selected if record["volume"] >= {component_volume_min!r}]
    if {component_volume_max!r} is not None:
        selected = [record for record in selected if record["volume"] <= {component_volume_max!r}]
    sort_keys = {{
        "index": lambda record: record["component_index"],
        "volume": lambda record: record["volume"],
        "center_x": lambda record: record["center"][0],
        "center_y": lambda record: record["center"][1],
        "center_z": lambda record: record["center"][2],
    }}
    selected.sort(
        key=sort_keys[{component_sort_by!r}],
        reverse={component_sort_order!r} == "desc",
    )
    if {component_limit!r} is not None:
        selected = selected[:{component_limit!r}]
    if not selected:
        suffix = f"; invalid requested components: {{invalid_requested}}" if invalid_requested else ""
        raise ValueError(f"No valid solid feature components matched the selection{{suffix}}")

    components = []
    refine_fallbacks = []
    for record in selected:
        component_index = record["component_index"]
        component_shape = record["shape"]
        component_refined = False
        component_refine_fallback_reason = None
        if {refine!r}:
            try:
                refined = component_shape.removeSplitter()
                if refined.isNull() or not refined.isValid():
                    raise ValueError("removeSplitter produced a null or invalid Shape")
                component_shape = refined
                component_refined = True
            except Exception as exc:
                component_refine_fallback_reason = str(exc)
                refine_fallbacks.append(
                    f"component {{component_index}}: {{component_refine_fallback_reason}}"
                )
        result_obj = doc.addObject("Part::Feature", f"{result_prefix}{{component_index}}")
        result_obj.Shape = component_shape
        components.append({{
            "component_index": component_index,
            "name": result_obj.Name,
            "volume": float(component_shape.Volume),
            "center": [
                float(component_shape.CenterOfMass.x),
                float(component_shape.CenterOfMass.y),
                float(component_shape.CenterOfMass.z),
            ],
            "face_count": len(component_shape.Faces),
            "refined": component_refined,
            "refine_fallback_reason": component_refine_fallback_reason,
        }})
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "mode": {mode!r},
        "container_valid": container_valid,
        "available_component_count": len(solids),
        "valid_component_count": len(solids) - len(invalid_component_indices),
        "invalid_component_indices": invalid_component_indices,
        "created_component_count": len(components),
        "components": components,
        "total_recovered_volume": float(raw_recovered.Volume),
        "total_valid_component_volume": sum(
            record["volume"] for record in records if record["valid"]
        ),
        "selected_volume": sum(component["volume"] for component in components),
        "component_selection": {{
            "indices": requested_indices,
            "volume_min": {component_volume_min!r},
            "volume_max": {component_volume_max!r},
            "sort_by": {component_sort_by!r},
            "sort_order": {component_sort_order!r},
            "limit": {component_limit!r},
        }},
        "fuzzy_tolerance": {fuzzy_tolerance!r},
        "refine_requested": {refine!r},
        "refine_applied": all(component["refined"] for component in components),
        "refine_fallback_reason": "; ".join(refine_fallbacks) or None,
        "refined": all(component["refined"] for component in components),
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Extract feature material failed", timeout_ms)

    @mcp.tool()
    async def sew_shell(
        object_names: list[str],
        result_name: str | None = None,
        tolerance: NonNegativeFloat = 1e-7,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Sew all faces from supplied objects into one or more valid shells."""
        if not object_names:
            raise ValueError("object_names must not be empty")
        code = f"""
import Part

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
faces = []
for object_name in {object_names!r}:
    obj = doc.getObject(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {{object_name}}")
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError(f"Object has a null Shape: {{object_name}}")
    faces.extend(shape.Faces)
if not faces:
    raise ValueError("Input objects contain no faces")

doc.openTransaction("Sew Shell")
try:
    shell = Part.makeShell(faces)
    if {tolerance!r} > 0.0:
        shell.fixTolerance({tolerance!r})
    if shell.isNull() or not shell.isValid():
        raise ValueError("Sewing produced a null or invalid shell")
    result_obj = doc.addObject("Part::Feature", {result_name!r} or "SewnShell")
    result_obj.Shape = shell
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result_obj.Name,
        "shape_valid": True,
        "shape_type": shell.ShapeType,
        "shell_count": len(shell.Shells),
        "face_count": len(shell.Faces),
        "closed": bool(shell.isClosed()),
        "tolerance": {tolerance!r},
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Sew shell failed", timeout_ms)

    @mcp.tool()
    async def heal_shape(
        object_name: str,
        result_name: str | None = None,
        tolerance: NonNegativeFloat = 1e-7,
        refine: bool = True,
        expected_solid_count: Annotated[int, Field(ge=1)] | None = None,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Run OCCT shape fixing, optional tolerance limiting, and refinement."""
        code = f"""
requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
source = doc.getObject({object_name!r})
if source is None:
    raise ValueError("Object not found: {object_name}")
source_shape = getattr(source, "Shape", None)
if source_shape is None or source_shape.isNull():
    raise ValueError("Source has a null Shape")

doc.openTransaction("Heal Shape")
try:
    healed = source_shape.copy()
    healed.fix({tolerance!r}, {tolerance!r}, max({tolerance!r}, 1e-7))
    if {tolerance!r} > 0.0:
        healed.limitTolerance({tolerance!r})
    if healed.isNull() or not healed.isValid():
        raise ValueError("Shape fixing did not produce a valid Shape")
    refine_applied = False
    refine_fallback_reason = None
    if {refine!r}:
        try:
            refined = healed.removeSplitter()
            if refined.isNull() or not refined.isValid():
                raise ValueError("removeSplitter produced a null or invalid Shape")
            healed = refined
            refine_applied = True
        except Exception as exc:
            refine_fallback_reason = str(exc)
    solid_count = len(healed.Solids)
    expected_count = {expected_solid_count!r}
    if expected_count is not None and solid_count != expected_count:
        raise ValueError(
            f"Expected {{expected_count}} solid(s), got {{solid_count}}"
        )
    result_obj = doc.addObject("Part::Feature", {result_name!r} or "HealedShape")
    result_obj.Shape = healed
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result_obj.Name,
        "shape_valid": True,
        "shape_type": healed.ShapeType,
        "solid_count": solid_count,
        "volume": float(healed.Volume),
        "refine_requested": {refine!r},
        "refine_applied": refine_applied,
        "refine_fallback_reason": refine_fallback_reason,
        "refined": refine_applied,
        "tolerance": {tolerance!r},
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Heal shape failed", timeout_ms)

    @mcp.tool()
    async def make_solid(
        object_name: str,
        result_name: str | None = None,
        refine: bool = True,
        expected_solid_count: Annotated[int, Field(ge=1)] | None = 1,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Build solid(s) from closed shell(s) and validate positive volume."""
        code = f"""
import Part

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
source = doc.getObject({object_name!r})
if source is None:
    raise ValueError("Object not found: {object_name}")
shape = getattr(source, "Shape", None)
if shape is None or shape.isNull():
    raise ValueError("Source has a null Shape")
shells = list(shape.Shells)
if not shells:
    raise ValueError("Source Shape contains no shells")
if any(not shell.isClosed() for shell in shells):
    raise ValueError("Every source shell must be closed")

doc.openTransaction("Make Solid")
try:
    solids = [Part.makeSolid(shell) for shell in shells]
    result_shape = solids[0] if len(solids) == 1 else Part.makeCompound(solids)
    if {refine!r}:
        result_shape = result_shape.removeSplitter()
    if result_shape.isNull() or not result_shape.isValid():
        raise ValueError("Solid construction produced a null or invalid Shape")
    solid_count = len(result_shape.Solids)
    volume = float(result_shape.Volume)
    if volume <= 0.0:
        raise ValueError(f"Solid volume must be positive; got {{volume}}")
    expected_count = {expected_solid_count!r}
    if expected_count is not None and solid_count != expected_count:
        raise ValueError(
            f"Expected {{expected_count}} solid(s), got {{solid_count}}"
        )
    result_obj = doc.addObject("Part::Feature", {result_name!r} or "Solid")
    result_obj.Shape = result_shape
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result_obj.Name,
        "shape_valid": True,
        "shape_type": result_shape.ShapeType,
        "solid_count": solid_count,
        "volume": volume,
        "refined": {refine!r},
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Make solid failed", timeout_ms)

    @mcp.tool()
    async def polar_pattern_shape(
        object_name: str,
        occurrences: Annotated[int, Field(ge=2, le=1000)],
        total_angle_deg: FiniteFloat = 360.0,
        axis_origin: list[FiniteFloat] | None = None,
        axis_direction: list[FiniteFloat] | None = None,
        result_name: str | None = None,
        fuse: bool = False,
        fuzzy_tolerance: NonNegativeFloat = 0.0,
        refine: bool = True,
        expected_solid_count: Annotated[int, Field(ge=1)] | None = None,
        hide_source: bool = True,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Rotate exact Shape copies about an axis, optionally fuse and refine."""
        axis_origin = axis_origin or [0.0, 0.0, 0.0]
        axis_direction = axis_direction or [0.0, 0.0, 1.0]
        _vector3(axis_origin, "axis_origin")
        _vector3(axis_direction, "axis_direction")
        code = f"""
import Part

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
source = doc.getObject({object_name!r})
if source is None:
    raise ValueError("Object not found: {object_name}")
source_shape = getattr(source, "Shape", None)
if source_shape is None or source_shape.isNull() or not source_shape.isValid():
    raise ValueError("Source Shape must be non-null and valid")
origin = FreeCAD.Vector(*{axis_origin!r})
axis = FreeCAD.Vector(*{axis_direction!r})
if axis.Length <= 0.0:
    raise ValueError("axis_direction must be non-zero")
pitch = {total_angle_deg!r} / {occurrences!r}

doc.openTransaction("Polar Pattern Shape")
try:
    copies = []
    for index in range({occurrences!r}):
        copy_shape = source_shape.copy()
        if index:
            copy_shape.rotate(origin, axis, pitch * index)
        copies.append(copy_shape)
    if {fuse!r}:
        if {fuzzy_tolerance!r} <= 0.0 and hasattr(copies[0], "multiFuse"):
            result_shape = copies[0].multiFuse(copies[1:])
            fuse_strategy = "multi_fuse"
        else:
            result_shape = copies[0]
            fuse_strategy = "sequential_fuzzy" if {fuzzy_tolerance!r} > 0.0 else "sequential"
            for copy_shape in copies[1:]:
                if {fuzzy_tolerance!r} > 0.0:
                    try:
                        result_shape = result_shape.fuse(copy_shape, {fuzzy_tolerance!r})
                    except TypeError as exc:
                        raise ValueError(
                            "This FreeCAD build does not expose fuzzy tolerance for fuse"
                        ) from exc
                else:
                    result_shape = result_shape.fuse(copy_shape)
    else:
        result_shape = Part.makeCompound(copies)
        fuse_strategy = "compound"
    if {refine!r}:
        result_shape = result_shape.removeSplitter()
    if result_shape.isNull() or not result_shape.isValid():
        raise ValueError("Polar pattern produced a null or invalid Shape")
    solid_count = len(result_shape.Solids)
    expected_count = {expected_solid_count!r}
    if expected_count is not None and solid_count != expected_count:
        raise ValueError(
            f"Expected {{expected_count}} solid(s), got {{solid_count}}"
        )
    result_obj = doc.addObject("Part::Feature", {result_name!r} or "PolarPatternShape")
    result_obj.Shape = result_shape
    source.Visibility = not {hide_source!r}
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "name": result_obj.Name,
        "source_name": source.Name,
        "occurrences": {occurrences!r},
        "pitch_deg": pitch,
        "total_angle_deg": {total_angle_deg!r},
        "fused": {fuse!r},
        "fuzzy_tolerance": {fuzzy_tolerance!r},
        "fuse_strategy": fuse_strategy,
        "refined": {refine!r},
        "shape_valid": True,
        "shape_type": result_shape.ShapeType,
        "solid_count": solid_count,
        "volume": float(result_shape.Volume),
        "transaction_state": "committed",
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        return await _execute(code, "Polar pattern shape failed", timeout_ms)
