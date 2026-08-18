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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
        """Remove selected faces with OCCT defeaturing and store the healed Shape."""
        if not face_names:
            raise ValueError("face_names must not be empty")
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
    healed = source_shape.defeaturing(faces)
    if {refine!r}:
        healed = healed.removeSplitter()
    if healed.isNull() or not healed.isValid():
        raise ValueError("OCCT defeaturing produced a null or invalid Shape")
    solid_count = len(healed.Solids)
    if {expected_solid_count!r} is not None and solid_count != {expected_solid_count!r}:
        raise ValueError(
            f"Expected {expected_solid_count!r} solid(s), got {{solid_count}}"
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
        "base_volume": float(source_shape.Volume),
        "result_volume": float(healed.Volume),
        "volume_delta": float(healed.Volume - source_shape.Volume),
        "refined": {refine!r},
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
        result_prefix: str = "RecoveredFeature",
        refine: bool = True,
        doc_name: str | None = None,
        timeout_ms: PositiveTimeout = 120000,
    ) -> dict[str, Any]:
        """Extract exact material/void regions from source and defeatured Shapes."""
        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
    recovered = (
        source_shape.cut(healed)
        if {mode!r} == "removed_material"
        else healed.cut(source_shape)
    )
    if {refine!r}:
        recovered = recovered.removeSplitter()
    if recovered.isNull() or not recovered.isValid():
        raise ValueError("Shape difference produced a null or invalid feature region")
    solids = list(recovered.Solids)
    if not solids:
        raise ValueError("Shape difference contains no solid feature components")
    requested = {component_indices!r} or list(range(1, len(solids) + 1))
    if len(set(requested)) != len(requested):
        raise ValueError("component_indices contains duplicates")
    if any(index < 1 or index > len(solids) for index in requested):
        raise ValueError(f"component_indices must be between 1 and {{len(solids)}}")
    components = []
    for component_index in requested:
        component_shape = solids[component_index - 1]
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
        }})
    doc.recompute()
    doc.commitTransaction()
    _result_ = {{
        "mode": {mode!r},
        "available_component_count": len(solids),
        "created_component_count": len(components),
        "components": components,
        "total_recovered_volume": float(recovered.Volume),
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
    if {refine!r}:
        healed = healed.removeSplitter()
    if healed.isNull() or not healed.isValid():
        raise ValueError("Healing produced a null or invalid Shape")
    solid_count = len(healed.Solids)
    if {expected_solid_count!r} is not None and solid_count != {expected_solid_count!r}:
        raise ValueError(
            f"Expected {expected_solid_count!r} solid(s), got {{solid_count}}"
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
        "refined": {refine!r},
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
    if {expected_solid_count!r} is not None and solid_count != {expected_solid_count!r}:
        raise ValueError(
            f"Expected {expected_solid_count!r} solid(s), got {{solid_count}}"
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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
        result_shape = copies[0]
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
    if {refine!r}:
        result_shape = result_shape.removeSplitter()
    if result_shape.isNull() or not result_shape.isValid():
        raise ValueError("Polar pattern produced a null or invalid Shape")
    solid_count = len(result_shape.Solids)
    if {expected_solid_count!r} is not None and solid_count != {expected_solid_count!r}:
        raise ValueError(
            f"Expected {expected_solid_count!r} solid(s), got {{solid_count}}"
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
