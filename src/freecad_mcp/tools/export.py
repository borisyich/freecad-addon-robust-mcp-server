"""Import and export tools for FreeCAD Robust MCP Server.

The public MCP surface intentionally exposes one ``export`` tool and one
``import`` tool. The selected file format determines the FreeCAD operation.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

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
if {object_names!r} is not None:
    objects = [doc.getObject(n) for n in {object_names!r}]
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
) -> str:
    """Build STEP or IGES export code."""
    export_method = "exportStep" if file_format == "step" else "exportIges"
    return f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
if len(objects) == 1:
    shape = objects[0].Shape
else:
    shape = Part.makeCompound([obj.Shape for obj in objects])

shape.{export_method}({file_path!r})

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "path": {file_path!r},
    "object_count": len(objects),
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
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

final_mesh.write({file_path!r})

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "path": {file_path!r},
    "object_count": len(objects),
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

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Imported")

before_count = len(doc.Objects)
{module_name}.insert({file_path!r}, doc.Name)
doc.recompute()
new_objects = [obj.Name for obj in doc.Objects[before_count:]]

_result_ = {{
    "success": True,
    "format": {file_format!r},
    "document": doc.Name,
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

        Returns:
            Export status, normalized format, output path, and object count.
        """
        normalized_format = _normalise_format(
            file_format, _EXPORT_FORMATS, "export"
        )
        if normalized_format in _MESH_EXPORT_FORMATS and mesh_tolerance <= 0:
            raise ValueError("mesh_tolerance must be positive for mesh exports")

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
            )

        bridge = await get_bridge()
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(
            result.error_traceback or f"{normalized_format.upper()} export failed"
        )

    @mcp.tool(name="import")
    async def import_file(
        file_format: ImportFormat,
        file_path: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import a STEP or STL file into FreeCAD.

        The MCP tool name is ``import``. The Python implementation uses the name
        ``import_file`` because ``import`` is a Python keyword.

        Args:
            file_format: Source format: ``step`` or ``stl``.
            file_path: Input file path.
            doc_name: Existing target document. If omitted and no document is active,
                creates a document named ``Imported``.

        Returns:
            Import status, normalized format, target document, and names of all
            imported objects.
        """
        normalized_format = _normalise_format(
            file_format, _IMPORT_FORMATS, "import"
        )
        code = _build_import_code(normalized_format, file_path, doc_name)

        bridge = await get_bridge()
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        raise ValueError(
            result.error_traceback or f"{normalized_format.upper()} import failed"
        )
