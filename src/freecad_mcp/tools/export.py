"""Import and export tools for FreeCAD Robust MCP Server.

The public MCP surface intentionally exposes one ``export`` tool and one
``import`` tool. The selected file format determines the FreeCAD operation.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from freecad_mcp.bridge._document_runtime import DOCUMENT_RESOLUTION_RUNTIME

ExportFormat = Literal["step", "stl", "3mf", "obj", "iges"]
ImportFormat = Literal["step", "stl"]

_EXPORT_FORMATS = {"step", "stl", "3mf", "obj", "iges"}
_IMPORT_FORMATS = {"step", "stl"}
_MESH_EXPORT_FORMATS = {"stl", "3mf", "obj"}


def _normalise_format(file_format: str, supported: set[str], operation: str) -> str:
    """Normalize and validate an import or export format."""
    normalized = file_format.lower().lstrip(".")
    if normalized not in supported:
        supported_text = ", ".join(sorted(supported))
        raise ValueError(
            f"Unsupported {operation} format '{file_format}'. "
            f"Supported formats: {supported_text}"
        )
    return normalized


def _build_object_selection_code(object_names: list[str] | None) -> str:
    """Generate Python code for GUI-aware object selection."""
    return f"""
# Get objects to export
requested_object_names = {object_names!r}
if requested_object_names is not None:
    objects = [doc.getObject(n) for n in requested_object_names]
elif FreeCAD.GuiUp:
    objects = [
        obj for obj in doc.Objects
        if hasattr(obj, 'Shape') and obj.ViewObject and obj.ViewObject.Visibility
    ]
else:
    objects = [obj for obj in doc.Objects if hasattr(obj, 'Shape')]
objects = [obj for obj in objects if obj is not None and hasattr(obj, 'Shape')]

if not objects:
    raise ValueError("No exportable objects found")
"""


def _build_brep_export_code(
    file_format: str,
    file_path: str,
    object_names: list[str] | None,
    doc_name: str | None,
    verify_round_trip: bool,
    round_trip_linear_tolerance: float,
) -> str:
    """Build STEP or IGES export code."""
    export_method = "exportStep" if file_format == "step" else "exportIges"
    return f"""
import Part
import os

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
if len(objects) == 1:
    shape = objects[0].Shape
else:
    shape = Part.makeCompound([obj.Shape for obj in objects])

output_path = os.path.abspath({file_path!r})
output_directory = os.path.dirname(output_path)
if not os.path.isdir(output_directory):
    raise FileNotFoundError(
        f"Output directory does not exist: {{output_directory}}"
    )
shape.{export_method}(output_path)
if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
    raise ValueError("BREP export did not create a non-empty output file")

verification = {{"requested": {verify_round_trip!r}, "passed": None}}
if {verify_round_trip!r}:
    source_solid_count = len(shape.Solids)
    source_volume = float(shape.Volume)
    source_box = shape.BoundBox
    volume_tolerance = max(1e-7, abs(source_volume) * 1e-9)
    bbox_tolerance = max(
        {round_trip_linear_tolerance!r},
        max(source_box.XLength, source_box.YLength, source_box.ZLength, 1.0) * 1e-9,
    )
    canonical_source = Part.Shape()
    canonical_source.importBrepFromString(shape.exportBrepToString())
    if canonical_source.isNull() or not canonical_source.isValid():
        raise ValueError("Source Shape could not be canonicalized through BREP")
    canonical_volume_error = abs(float(canonical_source.Volume) - source_volume)
    canonical_box = canonical_source.BoundBox
    canonical_bbox_error = max(
        abs(float(left) - float(right))
        for left, right in zip(
            (
                source_box.XMin, source_box.YMin, source_box.ZMin,
                source_box.XMax, source_box.YMax, source_box.ZMax,
            ),
            (
                canonical_box.XMin, canonical_box.YMin, canonical_box.ZMin,
                canonical_box.XMax, canonical_box.YMax, canonical_box.ZMax,
            ),
        )
    )
    if len(canonical_source.Solids) != source_solid_count:
        raise ValueError("Source BREP normalization changed solid count")
    if canonical_volume_error > volume_tolerance:
        raise ValueError(
            f"Source BREP normalization changed volume by {{canonical_volume_error}} "
            f"(tolerance {{volume_tolerance}})"
        )
    if canonical_bbox_error > bbox_tolerance:
        raise ValueError(
            f"Source BREP normalization changed bounds by {{canonical_bbox_error}} "
            f"(tolerance {{bbox_tolerance}})"
        )
    round_trip = Part.read(output_path)
    if round_trip is None or round_trip.isNull():
        raise ValueError("Export round-trip produced a null Shape")
    if not round_trip.isValid():
        raise ValueError(
            "Export round-trip produced an invalid Shape; preserve upstream face "
            "boundaries (for example, retry the Boolean with refine=False)"
        )
    restored_solid_count = len(round_trip.Solids)
    if {file_format!r} == "step" and restored_solid_count != source_solid_count:
        raise ValueError(
            f"STEP round-trip changed solid count from {{source_solid_count}} "
            f"to {{restored_solid_count}}"
        )
    restored_volume = float(round_trip.Volume)
    volume_error = abs(restored_volume - source_volume)
    restored_box = round_trip.BoundBox
    bbox_error = max(
        abs(float(left) - float(right))
        for left, right in zip(
            (
                source_box.XMin, source_box.YMin, source_box.ZMin,
                source_box.XMax, source_box.YMax, source_box.ZMax,
            ),
            (
                restored_box.XMin, restored_box.YMin, restored_box.ZMin,
                restored_box.XMax, restored_box.YMax, restored_box.ZMax,
            ),
        )
    )
    if {file_format!r} == "step" and volume_error > volume_tolerance:
        raise ValueError(
            f"STEP round-trip changed volume by {{volume_error}} "
            f"(tolerance {{volume_tolerance}})"
        )
    if {file_format!r} == "step" and bbox_error > bbox_tolerance:
        raise ValueError(
            f"STEP round-trip changed bounds by {{bbox_error}} "
            f"(tolerance {{bbox_tolerance}})"
        )
    verification = {{
        "requested": True,
        "passed": True,
        "shape_valid": True,
        "source_solid_count": source_solid_count,
        "restored_solid_count": restored_solid_count,
        "volume_error": volume_error,
        "bounding_box_error": bbox_error,
        "baseline": "original_source_shape",
        "canonicalization_volume_error": canonical_volume_error,
        "canonicalization_bounding_box_error": canonical_bbox_error,
    }}

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "path": output_path,
    "object_count": len(objects),
    "file_size": os.path.getsize(output_path),
    "round_trip_verification": verification,
}}
"""


def _build_mesh_export_code(
    file_format: str,
    file_path: str,
    object_names: list[str] | None,
    doc_name: str | None,
    mesh_tolerance: float,
) -> str:
    """Build STL, 3MF, or OBJ export code."""
    return f"""
import Mesh
import MeshPart
import os

requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
meshes = [
    MeshPart.meshFromShape(obj.Shape, LinearDeflection={mesh_tolerance!r})
    for obj in objects
]

if len(meshes) == 1:
    final_mesh = meshes[0]
else:
    final_mesh = Mesh.Mesh()
    for mesh in meshes:
        final_mesh.addMesh(mesh)

output_path = os.path.abspath({file_path!r})
output_directory = os.path.dirname(output_path)
if not os.path.isdir(output_directory):
    raise FileNotFoundError(
        f"Output directory does not exist: {{output_directory}}"
    )
final_mesh.write(output_path)
if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
    raise ValueError("Mesh export did not create a non-empty output file")

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "path": output_path,
    "object_count": len(objects),
    "file_size": os.path.getsize(output_path),
}}
"""


def _build_import_code(
    file_format: str,
    file_path: str,
    doc_name: str | None,
) -> str:
    """Build STEP or STL import code with a consistent result shape."""
    module_name = "Part" if file_format == "step" else "Mesh"
    return f"""
import {module_name}
import os

if not os.path.exists({file_path!r}):
    raise FileNotFoundError(f"File not found: {file_path!r}")

requested_doc_name = {doc_name!r}
existing_doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.listDocuments().get(requested_doc_name)
)
document_created = existing_doc is None
{DOCUMENT_RESOLUTION_RUNTIME}
doc = _resolve_document(
    requested_doc_name,
    create_if_missing=True,
    default_name="Imported",
)

before_count = len(doc.Objects)
{module_name}.insert({file_path!r}, doc.Name)
doc.recompute()
new_object_refs = list(doc.Objects[before_count:])
for obj in new_object_refs:
    if not hasattr(obj, "addProperty"):
        continue
    try:
        if "ImportSourcePath" not in getattr(obj, "PropertiesList", []):
            obj.addProperty("App::PropertyString", "ImportSourcePath", "MCP Import")
        obj.ImportSourcePath = os.path.abspath({file_path!r})
        if "ImportSourceFormat" not in getattr(obj, "PropertiesList", []):
            obj.addProperty("App::PropertyString", "ImportSourceFormat", "MCP Import")
        obj.ImportSourceFormat = {file_format!r}
    except Exception:
        # Import success must not depend on optional provenance metadata.
        pass
new_objects = [obj.Name for obj in new_object_refs]

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "document": doc.Name,
    "document_created": document_created,
    "objects": new_objects,
}}
"""


def register_export_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register the consolidated import and export tools."""

    @mcp.tool()
    async def export(
        file_format: ExportFormat,
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
        mesh_tolerance: float = 0.1,
        verify_round_trip: bool = True,
        round_trip_linear_tolerance: float = 0.01,
    ) -> dict[str, Any]:
        """Export FreeCAD objects to STEP, IGES, STL, 3MF, or OBJ.

        Args:
            file_format: Target format: ``step``, ``iges``, ``stl``, ``3mf``, or
                ``obj``.
            file_path: Output file path.
            object_names: Specific objects to export. When omitted, exports visible
                shape objects in GUI mode or all shape objects in headless mode.
            doc_name: Source document. Uses the active document when omitted.
            mesh_tolerance: Linear deflection for mesh formats. Lower values create
                finer meshes. Ignored for STEP and IGES.
            verify_round_trip: Re-read STEP/IGES output and reject null or invalid
                exchange geometry. STEP also verifies solid count, volume, and bounds.
            round_trip_linear_tolerance: Allowed absolute bounding-box noise in
                millimetres during BREP canonicalization and STEP round-trip.

        Returns:
            Export status, normalized format, output path, and object count.
        """
        normalized_format = _normalise_format(file_format, _EXPORT_FORMATS, "export")
        if normalized_format in _MESH_EXPORT_FORMATS and mesh_tolerance <= 0:
            raise ValueError("mesh_tolerance must be positive for mesh exports")
        if round_trip_linear_tolerance < 0:
            raise ValueError("round_trip_linear_tolerance must be non-negative")

        if normalized_format in _MESH_EXPORT_FORMATS:
            code = _build_mesh_export_code(
                normalized_format,
                file_path,
                object_names,
                doc_name,
                mesh_tolerance,
            )
        else:
            code = _build_brep_export_code(
                normalized_format,
                file_path,
                object_names,
                doc_name,
                verify_round_trip,
                round_trip_linear_tolerance,
            )

        bridge = await get_bridge()
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(
            result.failure_details(f"{normalized_format.upper()} export failed")
        )

    @mcp.tool(name="import")
    async def import_file(
        file_format: ImportFormat,
        file_path: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import STEP/STL, creating the named target document when missing.

        The MCP tool name is ``import``. The Python implementation uses the name
        ``import_file`` because ``import`` is a Python keyword.

        Args:
            file_format: Source format: ``step`` or ``stl``.
            file_path: Input file path.
            doc_name: Target document. Reuses it when open and creates it when
                missing. If omitted and no document is active, creates ``Imported``.

        Returns:
            Import status, normalized format, target document, whether it was
            created, and names of all imported objects.
        """
        normalized_format = _normalise_format(file_format, _IMPORT_FORMATS, "import")
        code = _build_import_code(normalized_format, file_path, doc_name)

        bridge = await get_bridge()
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(
            result.failure_details(f"{normalized_format.upper()} import failed")
        )
