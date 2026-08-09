"""Typed tools for the external FreeCAD SheetMetal Workbench.

The tools in this module create native SheetMetal ``FeaturePython`` objects.
They deliberately wrap the workbench proxy classes instead of returning a
disposable B-rep, so the resulting model remains editable and unfoldable.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

EdgeReference = Annotated[str, Field(pattern=r"^Edge[1-9]\d*$")]
FaceReference = Annotated[str, Field(pattern=r"^Face[1-9]\d*$")]
VertexReference = Annotated[str, Field(pattern=r"^Vertex[1-9]\d*$")]
SheetSubshapeReference = Annotated[str, Field(pattern=r"^(?:Face|Edge)[1-9]\d*$")]


class _SheetMetalOperation(BaseModel):
    """Strict base for discriminated SheetMetal operations."""

    model_config = ConfigDict(extra="forbid")


class FlangeOperation(_SheetMetalOperation):
    """Edge-flange operation."""

    op: Literal["flange"]
    base_feature: str = Field(min_length=1)
    edges: list[EdgeReference] = Field(min_length=1)
    length: float = Field(gt=0)
    radius: float = Field(gt=0)
    angle: float = Field(default=90.0, gt=0, le=180)
    invert: bool = False
    bend_type: Literal[
        "material_outside", "material_inside", "thickness_outside", "offset"
    ] = "material_outside"
    length_spec: Literal["leg", "outer_sharp", "inner_sharp", "tangential"] = "leg"
    gap_left: float = Field(default=0.0, ge=0)
    gap_right: float = Field(default=0.0, ge=0)
    relief_type: Literal["rectangle", "round"] = "rectangle"
    relief_width: float = Field(default=0.8, gt=0)
    relief_depth: float = Field(default=1.0, gt=0)
    auto_miter: bool = True


class FoldOperation(_SheetMetalOperation):
    """Sketch-line fold operation."""

    op: Literal["fold"]
    base_feature: str = Field(min_length=1)
    face: FaceReference
    bend_line_sketch: str = Field(min_length=1)
    radius: float = Field(gt=0)
    angle: float = Field(default=90.0, gt=0, le=180)
    k_factor: float = Field(ge=0, le=1)
    invert: bool = False
    invert_solid: bool = False
    position: Literal["intersection_of_planes", "middle", "backward", "forward"] = (
        "intersection_of_planes"
    )


class JunctionOperation(_SheetMetalOperation):
    """Junction rip operation."""

    op: Literal["junction"]
    base_feature: str = Field(min_length=1)
    edges: list[EdgeReference] = Field(min_length=1)
    gap: float = Field(gt=0)


class ReliefOperation(_SheetMetalOperation):
    """Vertex-relief operation."""

    op: Literal["relief"]
    base_feature: str = Field(min_length=1)
    vertices: list[VertexReference] = Field(min_length=1)
    size: float = Field(gt=0)


class CornerReliefOperation(_SheetMetalOperation):
    """Corner-relief operation."""

    op: Literal["corner_relief"]
    base_feature: str = Field(min_length=1)
    edges: list[EdgeReference] = Field(min_length=2, max_length=2)
    relief_shape: Literal["circle", "circle_scaled", "square", "square_scaled"] = (
        "circle"
    )
    size: float = Field(gt=0)
    size_ratio: float = Field(default=1.5, gt=0)
    k_factor: float = Field(ge=0, le=1)
    offset_x: float = Field(default=0.0, ge=0)
    offset_y: float = Field(default=0.0, ge=0)


class ExtendOperation(_SheetMetalOperation):
    """Wall-extend operation."""

    op: Literal["extend"]
    base_feature: str = Field(min_length=1)
    subelements: list[SheetSubshapeReference] = Field(min_length=1)
    length: float = Field(gt=0)
    gap_left: float = Field(default=0.0, ge=0)
    gap_right: float = Field(default=0.0, ge=0)
    reverse: bool = False
    sketch: str | None = None
    use_subtraction: bool = True
    clearance: float = Field(default=0.2, ge=0)
    refine: bool = True


class HemOperation(_SheetMetalOperation):
    """Edge-hem operation."""

    op: Literal["hem"]
    base_feature: str = Field(min_length=1)
    edges: list[EdgeReference] = Field(min_length=1)
    hem_type: Literal["flat", "open", "teardrop", "rolled"]
    width: float = Field(default=10.0, gt=0)
    radius: float = Field(default=1.0, gt=0)
    opening: float = Field(default=1.0, ge=0)
    roll_angle: float = Field(default=225.0, gt=180, lt=360)
    include_bend: bool = True
    opened: bool = False
    invert: bool = False
    gap_left: float = Field(default=0.0, ge=0)
    gap_right: float = Field(default=0.0, ge=0)
    bend_type: Literal["material_outside", "material_inside", "thickness_outside"] = (
        "material_outside"
    )
    relief_type: Literal["rectangle", "round"] = "rectangle"
    relief_width: float = Field(default=0.8, gt=0)
    relief_depth: float = Field(default=1.0, gt=0)


class SolidBendOperation(_SheetMetalOperation):
    """Solid-bend operation."""

    op: Literal["solid_bend"]
    base_feature: str = Field(min_length=1)
    edges: list[EdgeReference] = Field(min_length=1)
    radius: float = Field(gt=0)


class FromSolidOperation(_SheetMetalOperation):
    """Solid-to-sheet operation."""

    op: Literal["from_solid"]
    base_feature: str = Field(min_length=1)
    remove_faces_and_rip_edges: list[SheetSubshapeReference] = Field(min_length=1)
    thickness: float = Field(gt=0)
    radius: float = Field(gt=0)
    invert: bool = False


SheetMetalFeatureOperation = Annotated[
    FlangeOperation
    | FoldOperation
    | JunctionOperation
    | ReliefOperation
    | CornerReliefOperation
    | ExtendOperation
    | HemOperation
    | SolidBendOperation
    | FromSolidOperation,
    Field(discriminator="op"),
]
_SHEET_METAL_OPERATION_ADAPTER: TypeAdapter[SheetMetalFeatureOperation] = TypeAdapter(
    SheetMetalFeatureOperation
)


class SheetMetalMaterialRule(BaseModel):
    """Explicit neutral-axis rule used by an unfold operation."""

    model_config = ConfigDict(extra="forbid")
    k_factor: float | None = Field(default=None, ge=0, le=2)
    standard: Literal["ansi", "din"] = "ansi"
    material_sheet: str | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "SheetMetalMaterialRule":
        """Require exactly one explicit source for bend allowance data."""
        if (self.k_factor is None) == (self.material_sheet is None):
            raise ValueError(
                "Provide exactly one of k_factor or material_sheet; production "
                "bend allowance must not come from an implicit default"
            )
        if self.material_sheet is not None and not self.material_sheet.strip():
            raise ValueError("material_sheet must not be empty")
        return self


_SHEET_METAL_RUNTIME_HELPERS = r"""
def _sm_document(requested_name):
    try:
        doc = FreeCAD.getDocument(requested_name) if requested_name else FreeCAD.ActiveDocument
    except NameError:
        doc = None
    if doc is None:
        raise ValueError("No target document. Create or activate a document first.")
    return doc


def _sm_object(doc, name, role):
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError(f"{role} object {name!r} does not exist in document {doc.Name!r}")
    return obj


def _sm_body_for(obj):
    parent_getter = getattr(obj, "getParentGeoFeatureGroup", None)
    if callable(parent_getter):
        parent = parent_getter()
        if parent is not None and getattr(parent, "TypeId", "") == "PartDesign::Body":
            return parent
    for parent in getattr(obj, "InList", []):
        if getattr(parent, "TypeId", "") == "PartDesign::Body":
            return parent
    return None


def _sm_require_current_tip(base):
    body = _sm_body_for(base)
    if body is not None:
        tip = getattr(body, "Tip", None)
        if tip is not None and tip is not base:
            raise ValueError(
                f"Base feature {base.Name!r} is not the current Body Tip {tip.Name!r}; "
                "inspect and continue the linear sheet-metal history from the Tip"
            )
    return body


def _sm_require_workbench():
    import importlib
    try:
        tools_module = importlib.import_module("SheetMetalTools")
    except Exception as exc:
        raise RuntimeError(
            "SheetMetal Workbench is not importable. Install it with FreeCAD Addon "
            "Manager and restart FreeCAD. Original error: " + str(exc)
        ) from exc
    return tools_module


def _sm_validate_refs(base, refs, allowed_types):
    if not refs:
        raise ValueError("At least one topology reference is required")
    resolved = []
    for ref in refs:
        try:
            subshape = base.getSubObject(ref)
            if subshape is None or bool(getattr(subshape, "isNull", lambda: False)()):
                raise ValueError(f"Cannot resolve {base.Name}.{ref}")
            shape_type = getattr(subshape, "ShapeType", "")
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("Cannot resolve "):
                raise
            raise ValueError(f"Cannot resolve {base.Name}.{ref}: {exc}") from exc
        if shape_type not in allowed_types:
            raise ValueError(
                f"{base.Name}.{ref} is {shape_type or 'unknown'}, expected "
                + "/".join(sorted(allowed_types))
            )
        resolved.append(ref)
    return resolved


def _sm_new_feature(doc, base, name, allow_body=True):
    if doc.getObject(name) is not None:
        raise ValueError(f"Object {name!r} already exists in document {doc.Name!r}")
    body = _sm_require_current_tip(base) if allow_body else None
    if body is not None:
        feature = body.newObject("PartDesign::FeaturePython", name)
    else:
        feature = doc.addObject("Part::FeaturePython", name)
    return feature, body


def _sm_attach_view_provider(feature, module_name, tree_class, flat_class=None, body=None):
    # Attach the same GUI provider as the SheetMetal command implementation.
    if not bool(getattr(FreeCAD, "GuiUp", False)):
        return None
    import importlib
    module = importlib.import_module(module_name)
    class_name = flat_class if body is not None and flat_class else tree_class
    provider = getattr(module, class_name)
    provider(feature.ViewObject)
    return class_name


def _sm_set_visibility(obj, visible):
    try:
        obj.ViewObject.Visibility = bool(visible)
        return True
    except Exception:
        try:
            obj.Visibility = bool(visible)
            return True
        except Exception:
            return False


def _sm_view_evidence(feature, body=None):
    if not bool(getattr(FreeCAD, "GuiUp", False)):
        return {"gui_available": False}
    view = feature.ViewObject
    modes = list(view.listDisplayModes())
    display_mode = str(getattr(view, "DisplayMode", ""))
    if (not display_mode or display_mode == "None") and modes:
        try:
            view.DisplayMode = modes[0]
            display_mode = str(view.DisplayMode)
        except Exception:
            pass
    view.Visibility = True
    if body is not None:
        _sm_set_visibility(body, True)
    if not display_mode or display_mode == "None":
        raise ValueError(
            f"Sheet-metal feature {feature.Name!r} has no usable GUI display mode; "
            "its SheetMetal ViewProvider was not initialized"
        )
    return {
        "gui_available": True,
        "view_provider_type": type(getattr(view, "Proxy", None)).__name__,
        "display_mode": display_mode,
        "available_display_modes": modes,
        "visible": bool(view.Visibility),
        "body_visible": None if body is None else bool(body.ViewObject.Visibility),
    }


def _sm_unfold_history_evidence(base):
    # Audit the complete active history from the first native SheetMetal feature
    # through ``base``. A later SM proxy must never erase evidence that the
    # history left native sheet-metal semantics and then re-entered them.
    body = _sm_body_for(base)
    if body is None:
        proxy_type = type(getattr(base, "Proxy", None)).__name__
        native = proxy_type.startswith("SM")
        return {
            "native_history": native,
            "native_linear_history": native,
            "classification": "native_standalone" if native else "no_native",
            "native_feature_names": [base.Name] if native else [],
            "active_history": [{
                "name": base.Name,
                "type_id": str(getattr(base, "TypeId", "")),
                "proxy_type": proxy_type,
            }],
            "supported_subtractive_features": [],
            "unsupported_shape_features": [],
            "unsupported_post_sheet_features": [],
            "reentered_after_unsupported": False,
            "supported": native,
        }
    items = list(getattr(body, "Group", []))
    try:
        endpoint_index = next(
            index for index, item in enumerate(items) if item is base
        )
    except StopIteration:
        endpoint_index = len(items) - 1
    active_items = items[:endpoint_index + 1]
    native_indexes = [
        index for index, item in enumerate(items)
        if index <= endpoint_index
        and type(getattr(item, "Proxy", None)).__name__.startswith("SM")
    ]
    unsupported = []
    supported_subtractive = []
    if native_indexes:
        first_native = min(native_indexes)
        last_native = max(native_indexes)
        for index, item in enumerate(items[first_native:endpoint_index + 1], first_native):
            type_id = str(getattr(item, "TypeId", ""))
            if type(getattr(item, "Proxy", None)).__name__.startswith("SM"):
                continue
            if type_id.startswith("Sketcher::") or type_id in {
                "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
                "PartDesign::CoordinateSystem",
            }:
                continue
            subtractive = type_id.startswith("PartDesign::") and any(
                token in type_id for token in ("Pocket", "Hole", "Subtractive", "Groove")
            )
            shape = getattr(item, "Shape", None)
            if shape is not None and not shape.isNull():
                evidence = {
                    "name": item.Name,
                    "type_id": type_id,
                    "index": index,
                    "position": (
                        "interleaved_before_later_native"
                        if index < last_native
                        else "after_last_native"
                    ),
                    "reason": "unsupported_shape_producing_feature",
                }
                if subtractive and index > last_native:
                    evidence["reason"] = "supported_post_native_subtractive_tail"
                    supported_subtractive.append(evidence)
                else:
                    unsupported.append(evidence)
    if not native_indexes:
        classification = "no_native"
    elif any(item["position"] == "interleaved_before_later_native" for item in unsupported):
        classification = "mixed_interleaved_history"
    elif unsupported:
        classification = "unsupported_post_native_history"
    elif supported_subtractive:
        classification = "native_with_supported_subtractive_tail"
    else:
        classification = "native_linear_history"
    active_history = []
    for item in active_items:
        proxy = getattr(item, "Proxy", None)
        active_history.append({
            "name": item.Name,
            "type_id": str(getattr(item, "TypeId", "")),
            "proxy_type": type(proxy).__name__ if proxy is not None else None,
        })
    reentered = any(
        item["position"] == "interleaved_before_later_native"
        for item in unsupported
    )
    return {
        "native_history": bool(native_indexes),
        "native_linear_history": bool(native_indexes) and not unsupported,
        "classification": classification,
        "native_feature_names": [items[index].Name for index in native_indexes],
        "active_history": active_history,
        "supported_subtractive_features": supported_subtractive,
        "unsupported_shape_features": unsupported,
        # Backwards-compatible alias. Unlike the old implementation this now
        # includes unsupported interleaved features, not only the final tail.
        "unsupported_post_sheet_features": unsupported,
        "reentered_after_unsupported": reentered,
        "supported": bool(native_indexes) and not unsupported,
    }


def _sm_shape_evidence(feature, base=None, body=None):
    shape = getattr(feature, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError(f"Sheet-metal feature {feature.Name!r} produced a null shape")
    shape_valid = bool(shape.isValid())
    solid_count = len(shape.Solids)
    volume = float(shape.Volume)
    if not shape_valid:
        raise ValueError(f"Sheet-metal feature {feature.Name!r} produced an invalid shape")
    if solid_count != 1 or volume <= 1e-9:
        raise ValueError(
            f"Sheet-metal feature {feature.Name!r} must produce one non-empty solid; "
            f"got solids={solid_count}, volume={volume}"
        )
    if body is not None:
        body.Tip = feature
    base_volume = None
    if base is not None and hasattr(base, "Shape") and not base.Shape.isNull():
        base_volume = float(base.Shape.Volume)
    delta = None if base_volume is None else volume - base_volume
    ratio = None
    if base_volume not in (None, 0.0):
        ratio = delta / base_volume
    return {
        "name": feature.Name,
        "label": feature.Label,
        "type_id": feature.TypeId,
        "proxy_type": type(feature.Proxy).__name__,
        "validated": True,
        "shape_valid": shape_valid,
        "solid_count": solid_count,
        "volume": volume,
        "base_volume": base_volume,
        "volume_change": delta,
        "volume_change_ratio": ratio,
        "body": getattr(body, "Name", None),
        "tip": getattr(getattr(body, "Tip", None), "Name", None),
        "tip_matches": body is None or getattr(body, "Tip", None) is feature,
    }


def _sm_finish(doc, feature, base=None, body=None):
    feature.touch()
    doc.recompute()
    evidence = _sm_shape_evidence(feature, base, body)
    evidence["view"] = _sm_view_evidence(feature, body)
    if base is not None:
        _sm_set_visibility(base, False)
    return evidence
"""


def _normalize_operation(
    operation: SheetMetalFeatureOperation | dict[str, Any],
) -> SheetMetalFeatureOperation:
    """Return one validated discriminated operation model."""
    if isinstance(operation, BaseModel):
        return operation
    return _SHEET_METAL_OPERATION_ADAPTER.validate_python(operation)


def register_sheetmetal_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register native SheetMetal Workbench tools."""

    @mcp.tool()
    async def sheet_metal_capabilities() -> dict[str, Any]:
        """Report installed SheetMetal version and native operation availability.

        Use this once before a sheet-metal workflow. It distinguishes a missing
        workbench from an unsupported feature and returns the exact compact
        operation vocabulary accepted by ``create_sheet_metal_feature``. If a
        drawing includes an explicit flat pattern, inventory its entire outline,
        panel regions, and bend table before creating the first feature.
        """
        bridge = await get_bridge()
        code = r"""
import importlib
import os
import xml.etree.ElementTree as ET

modules = {
    "base": ("SheetMetalBaseCmd", "SMBaseBend"),
    "flange": ("SheetMetalCmd", "SMBendWall"),
    "fold": ("SheetMetalFoldCmd", "SMFoldWall"),
    "junction": ("SheetMetalJunction", "SMJunction"),
    "relief": ("SheetMetalRelief", "SMRelief"),
    "corner_relief": ("SheetMetalCornerReliefCmd", "SMCornerRelief"),
    "extend": ("SheetMetalExtendCmd", "SMExtrudeWall"),
    "hem": ("SheetMetalHem", "SMHem"),
    "solid_bend": ("SheetMetalBend", "SMSolidBend"),
    "from_solid": ("SheetMetalFromSolid", "SMFromSolid"),
    "unfold": ("SheetMetalUnfoldCmd", "SMUnfold"),
}
available = {}
errors = {}
tools_module = None
try:
    tools_module = importlib.import_module("SheetMetalTools")
except Exception as exc:
    errors["SheetMetalTools"] = str(exc)
for operation, (module_name, class_name) in modules.items():
    try:
        module = importlib.import_module(module_name)
        available[operation] = hasattr(module, class_name)
        if not available[operation]:
            errors[operation] = f"{module_name}.{class_name} is missing"
    except Exception as exc:
        available[operation] = False
        errors[operation] = str(exc)
version = None
install_path = None
if tools_module is not None:
    install_path = os.path.dirname(os.path.abspath(tools_module.__file__))
    package_xml = os.path.join(install_path, "package.xml")
    if os.path.isfile(package_xml):
        try:
            root = ET.parse(package_xml).getroot()
            version_node = next(
                (node for node in root.iter() if node.tag.split("}")[-1] == "version"),
                None,
            )
            version = version_node.text if version_node is not None else None
        except Exception as exc:
            errors["package_xml"] = str(exc)
_result_ = {
    "installed": tools_module is not None,
    "version": version,
    "install_path": install_path,
    "operations": available,
    "errors": errors,
    "engineering_mode_note": (
        "MCP unfold requires an explicit K-factor or material sheet even when "
        "the workbench GUI engineering mode is disabled."
    ),
}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result is not None:
            return result.result
        raise ValueError(result.error_traceback or "Failed to inspect SheetMetal")

    @mcp.tool()
    async def create_sheet_metal_base(
        sketch_name: str,
        thickness: float,
        radius: float,
        wall_length: float = 100.0,
        bend_side: Literal["outside", "inside", "middle"] = "outside",
        midplane: bool = False,
        reverse: bool = False,
        name: str = "BaseBend",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a native sheet-metal base from a closed or open sketch.

        A closed sketch creates a flat wall/blank with nominal ``thickness``.
        An open wire creates connected walls using ``wall_length`` and
        ``radius``. Put the sketch in a PartDesign Body to keep one editable
        manufactured-part history. The operation is transactional and rejects
        null, invalid, empty, or multi-solid results. For a drawing with an
        explicit flat pattern, prefer a fully constrained sketch of the complete
        blank followed by native ``fold`` operations along recorded bend lines;
        do not silently reduce the source to its largest panel.
        """
        if thickness <= 0 or radius <= 0 or wall_length <= 0:
            raise ValueError("thickness, radius, and wall_length must be positive")
        bridge = await get_bridge()
        side = {"outside": "Outside", "inside": "Inside", "middle": "Middle"}[bend_side]
        code = f"""
import FreeCAD
{_SHEET_METAL_RUNTIME_HELPERS}
doc = _sm_document({doc_name!r})
doc.openTransaction("Create Sheet Metal Base")
try:
    _sm_require_workbench()
    from SheetMetalBaseCmd import SMBaseBend
    sketch = _sm_object(doc, {sketch_name!r}, "Sketch")
    if not getattr(sketch, "TypeId", "").startswith("Sketcher::"):
        raise ValueError(f"{{sketch.Name!r}} is not a Sketcher object")
    feature, body = _sm_new_feature(doc, sketch, {name!r}, True)
    SMBaseBend(feature, sketch)
    _result_view_provider = _sm_attach_view_provider(
        feature, "SheetMetalBaseCmd", "SMBaseViewProvider", body=body
    )
    feature.Thickness = {float(thickness)!r}
    feature.Radius = {float(radius)!r}
    feature.Length = {float(wall_length)!r}
    feature.BendSide = {side!r}
    feature.MidPlane = {bool(midplane)!r}
    feature.Reverse = {bool(reverse)!r}
    _result_ = _sm_finish(doc, feature, sketch, body)
    _result_["operation"] = "base"
    _result_["view_provider"] = _result_view_provider
    _result_["thickness"] = float(feature.Thickness.Value)
    _result_["radius"] = float(feature.Radius.Value)
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result is not None:
            return result.result
        raise ValueError(result.error_traceback or "Failed to create sheet-metal base")

    @mcp.tool()
    async def create_sheet_metal_feature(
        operation: SheetMetalFeatureOperation,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create one native parametric SheetMetal feature.

        ``operation.op`` selects ``flange``, ``fold``, ``junction``, ``relief``,
        ``corner_relief``, ``extend``, ``hem``, ``solid_bend``, or
        ``from_solid`` and exposes only that operation's valid fields. Resolve
        topology with ``select_subshapes`` first; do not guess ``EdgeN`` or
        ``FaceN``. A PartDesign base must be the current Body Tip, keeping the
        history linear and the final result one valid solid. Use ``fold`` for a
        source-defined bend line in a complete flat blank; use ``flange`` when
        constructing from a formed-only drawing's base panel.
        """
        normalized = _normalize_operation(operation)
        payload = normalized.model_dump()
        feature_name = (
            name
            or {
                "flange": "Bend",
                "fold": "Fold",
                "junction": "Junction",
                "relief": "Relief",
                "corner_relief": "CornerRelief",
                "extend": "Extend",
                "hem": "Hem",
                "solid_bend": "SolidBend",
                "from_solid": "SolidToSheet",
            }[payload["op"]]
        )
        bridge = await get_bridge()
        code = f"""
import FreeCAD
{_SHEET_METAL_RUNTIME_HELPERS}
doc = _sm_document({doc_name!r})
operation = {payload!r}
doc.openTransaction("Create Sheet Metal Feature")
try:
    _sm_require_workbench()
    base = _sm_object(doc, operation["base_feature"], "Base feature")
    op = operation["op"]
    _sm_require_current_tip(base)
    bend_line = None
    extend_sketch = None
    if op in {{"flange", "junction", "hem", "solid_bend"}}:
        refs = _sm_validate_refs(base, operation["edges"], {{"Edge"}})
    elif op == "fold":
        refs = _sm_validate_refs(base, [operation["face"]], {{"Face"}})
        bend_line = _sm_object(doc, operation["bend_line_sketch"], "Bend-line sketch")
        if not getattr(bend_line, "TypeId", "").startswith("Sketcher::"):
            raise ValueError(f"{{bend_line.Name!r}} is not a Sketcher object")
    elif op == "relief":
        refs = _sm_validate_refs(base, operation["vertices"], {{"Vertex"}})
    elif op == "corner_relief":
        refs = _sm_validate_refs(base, operation["edges"], {{"Edge"}})
    elif op == "extend":
        refs = _sm_validate_refs(base, operation["subelements"], {{"Face", "Edge"}})
        if operation["sketch"] is not None:
            extend_sketch = _sm_object(doc, operation["sketch"], "Extend sketch")
    elif op == "from_solid":
        refs = _sm_validate_refs(
            base, operation["remove_faces_and_rip_edges"], {{"Face", "Edge"}}
        )
    else:
        raise ValueError(f"Unsupported sheet-metal operation: {{op}}")
    feature, body = _sm_new_feature(doc, base, {feature_name!r}, True)
    if op == "flange":
        from SheetMetalCmd import SMBendWall
        SMBendWall(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalCmd", "SMViewProviderTree", "SMViewProviderFlat", body
        )
        feature.length = operation["length"]
        feature.radius = operation["radius"]
        feature.angle = operation["angle"]
        feature.invert = operation["invert"]
        feature.BendType = {{
            "material_outside": "Material Outside",
            "material_inside": "Material Inside",
            "thickness_outside": "Thickness Outside",
            "offset": "Offset",
        }}[operation["bend_type"]]
        feature.LengthSpec = {{
            "leg": "Leg", "outer_sharp": "Outer Sharp",
            "inner_sharp": "Inner Sharp", "tangential": "Tangential",
        }}[operation["length_spec"]]
        feature.gap1 = operation["gap_left"]
        feature.gap2 = operation["gap_right"]
        feature.reliefType = operation["relief_type"].title()
        feature.reliefw = operation["relief_width"]
        feature.reliefd = operation["relief_depth"]
        feature.AutoMiter = operation["auto_miter"]
    elif op == "fold":
        from SheetMetalFoldCmd import SMFoldWall
        SMFoldWall(feature, base, refs, bend_line)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalFoldCmd", "SMFoldViewProvider", body=body
        )
        feature.radius = operation["radius"]
        feature.angle = operation["angle"]
        feature.kfactor = operation["k_factor"]
        feature.invert = operation["invert"]
        feature.invertbend = operation["invert_solid"]
        feature.Position = operation["position"].replace("_", " ")
    elif op == "junction":
        from SheetMetalJunction import SMJunction
        SMJunction(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalJunction", "SMJViewProviderTree", body=body
        )
        feature.gap = operation["gap"]
    elif op == "relief":
        from SheetMetalRelief import SMRelief
        SMRelief(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalRelief", "SMReliefViewProviderTree", body=body
        )
        feature.relief = operation["size"]
    elif op == "corner_relief":
        from SheetMetalCornerReliefCmd import SMCornerRelief
        SMCornerRelief(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalCornerReliefCmd", "SMCornerReliefVP", body=body
        )
        feature.ReliefSketch = {{
            "circle": "Circle", "circle_scaled": "Circle-Scaled",
            "square": "Square", "square_scaled": "Square-Scaled",
        }}[operation["relief_shape"]]
        feature.Size = operation["size"]
        feature.SizeRatio = operation["size_ratio"]
        feature.kfactor = operation["k_factor"]
        feature.XOffset = operation["offset_x"]
        feature.YOffset = operation["offset_y"]
    elif op == "extend":
        from SheetMetalExtendCmd import SMExtrudeWall
        SMExtrudeWall(feature, base, refs, extend_sketch)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalExtendCmd", "SMViewProviderTree", body=body
        )
        feature.length = operation["length"]
        feature.gap1 = operation["gap_left"]
        feature.gap2 = operation["gap_right"]
        feature.reversed = operation["reverse"]
        feature.UseSubtraction = operation["use_subtraction"]
        feature.Offset = operation["clearance"]
        feature.Refine = operation["refine"]
    elif op == "hem":
        from SheetMetalHem import SMHem
        SMHem(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalHem", "SMViewProviderTree", "SMViewProviderFlat", body
        )
        feature.HemType = operation["hem_type"].title()
        feature.width = operation["width"]
        feature.radius = operation["radius"]
        feature.opening = operation["opening"]
        feature.RollAngle = operation["roll_angle"]
        feature.IncludeBend = operation["include_bend"]
        feature.opened = operation["opened"]
        feature.invert = operation["invert"]
        feature.gap1 = operation["gap_left"]
        feature.gap2 = operation["gap_right"]
        feature.BendType = {{
            "material_outside": "Material Outside",
            "material_inside": "Material Inside",
            "thickness_outside": "Thickness Outside",
        }}[operation["bend_type"]]
        feature.reliefType = operation["relief_type"].title()
        feature.reliefw = operation["relief_width"]
        feature.reliefd = operation["relief_depth"]
    elif op == "solid_bend":
        from SheetMetalBend import SMSolidBend
        SMSolidBend(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalBend", "SMBendViewProviderFlat", body=body
        )
        feature.radius = operation["radius"]
    elif op == "from_solid":
        from SheetMetalFromSolid import SMFromSolid
        SMFromSolid(feature, base, refs)
        _result_view_provider = _sm_attach_view_provider(
            feature, "SheetMetalFromSolid", "SMFromSolidViewProvider", body=body
        )
        feature.Thickness = operation["thickness"]
        feature.Radius = operation["radius"]
        feature.Invert = operation["invert"]
    _result_ = _sm_finish(doc, feature, base, body)
    _result_["operation"] = op
    _result_["references"] = refs
    _result_["view_provider"] = _result_view_provider
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result is not None:
            return result.result
        raise ValueError(
            result.error_traceback or "Failed to create SheetMetal feature"
        )

    @mcp.tool()
    async def unfold_sheet_metal(
        feature_name: str,
        stationary_face: str,
        material: SheetMetalMaterialRule,
        generate_sketch: bool = True,
        separate_layers: bool = True,
        show_bend_angles: bool = True,
        verification_only: bool = False,
        name: str = "Unfold",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a native parametric flat pattern from a formed sheet.

        ``stationary_face`` must be a planar face selected semantically on the
        formed feature. ``material`` requires exactly one explicit source:
        manual K-factor plus ANSI/DIN convention, or a workbench material
        Spreadsheet. A persistent unfold is intentionally outside the
        PartDesign Body, preserving the formed Body Tip as the manufactured-part
        history. With ``verification_only=True`` the tool captures flat-shape
        and generated-sketch evidence, then rolls back every generated object.
        """
        normalized_material = (
            material
            if isinstance(material, SheetMetalMaterialRule)
            else SheetMetalMaterialRule.model_validate(material)
        )
        payload = normalized_material.model_dump()
        bridge = await get_bridge()
        code = f"""
import FreeCAD
{_SHEET_METAL_RUNTIME_HELPERS}
doc = _sm_document({doc_name!r})
material = {payload!r}
verification_only = {bool(verification_only)!r}
preexisting_names = {{obj.Name for obj in doc.Objects}}
doc.openTransaction("Unfold Sheet Metal")
transaction_open = True
try:
    _sm_require_workbench()
    base = _sm_object(doc, {feature_name!r}, "Formed feature")
    body = _sm_require_current_tip(base)
    history_evidence = _sm_unfold_history_evidence(base)
    if not history_evidence["supported"]:
        if not history_evidence["native_history"]:
            raise ValueError(
                "Unfold requires a native SheetMetal feature history; use "
                "create_sheet_metal_base or the from_solid operation first"
            )
        raise ValueError(
            "Unfold rejected unsupported shape-producing features in the active "
            "history from the first native SheetMetal feature: "
            + str(history_evidence["unsupported_shape_features"])
        )
    refs = _sm_validate_refs(base, [{stationary_face!r}], {{"Face"}})
    selected_face = base.getSubObject(refs[0])
    surface_name = type(selected_face.Surface).__name__
    if "Plane" not in surface_name:
        raise ValueError(
            f"Stationary face {{base.Name}}.{{refs[0]}} is {{surface_name}}, not planar"
        )
    feature, _unused_body = _sm_new_feature(doc, base, {name!r}, False)
    from SheetMetalUnfoldCmd import SMUnfold
    SMUnfold(feature, base, refs)
    _result_view_provider = _sm_attach_view_provider(
        feature, "SheetMetalUnfoldCmd", "SMUnfoldViewProvider"
    )
    if material["material_sheet"] is not None:
        sheet = _sm_object(doc, material["material_sheet"], "Material sheet")
        if getattr(sheet, "TypeId", "") != "Spreadsheet::Sheet":
            raise ValueError(f"{{sheet.Name!r}} is not a Spreadsheet::Sheet")
        feature.MaterialSheet = sheet.Name
    else:
        feature.MaterialSheet = "_manual"
        feature.KFactor = material["k_factor"]
        feature.KFactorStandard = material["standard"]
    feature.GenerateSketch = {bool(generate_sketch)!r}
    feature.SeparateSketchLayers = {bool(separate_layers)!r}
    feature.ShowBendAngles = {bool(show_bend_angles)!r}
    _result_ = _sm_finish(doc, feature, None, None)
    _result_["operation"] = "unfold"
    _result_["formed_feature"] = base.Name
    _result_["stationary_face"] = refs[0]
    _result_["material_source"] = (
        "spreadsheet" if material["material_sheet"] is not None else "manual_k_factor"
    )
    _result_["k_factor_standard"] = str(feature.KFactorStandard)
    generated_sketch_names = [str(name) for name in list(feature.UnfoldSketches)]
    generated_sketch_evidence = []
    for sketch_name in generated_sketch_names:
        sketch = doc.getObject(sketch_name)
        if sketch is None:
            continue
        sketch_shape = getattr(sketch, "Shape", None)
        geometry = list(getattr(sketch, "Geometry", []) or [])
        generated_sketch_evidence.append({{
            "name": sketch.Name,
            "type_id": sketch.TypeId,
            "geometry_count": len(geometry),
            "geometry_types": [type(item).__name__ for item in geometry],
            "circle_count": sum(
                1 for item in geometry if "Circle" in type(item).__name__
            ),
            "wire_count": len(getattr(sketch_shape, "Wires", []) or []),
            "visible": bool(getattr(getattr(sketch, "ViewObject", None), "Visibility", False)),
        }})
    flat_box = feature.Shape.BoundBox
    _result_["verification_evidence"] = {{
        "flat_shape": {{
            "valid": bool(feature.Shape.isValid()),
            "solid_count": len(feature.Shape.Solids),
            "volume": float(feature.Shape.Volume),
            "face_count": len(feature.Shape.Faces),
            "bounds": {{
                "min": [float(flat_box.XMin), float(flat_box.YMin), float(flat_box.ZMin)],
                "max": [float(flat_box.XMax), float(flat_box.YMax), float(flat_box.ZMax)],
                "size": [float(flat_box.XLength), float(flat_box.YLength), float(flat_box.ZLength)],
            }},
        }},
        "generated_sketches": generated_sketch_evidence,
    }}
    _result_["generated_sketches"] = generated_sketch_names
    _result_["view_provider"] = _result_view_provider
    _result_["history_evidence"] = history_evidence
    _result_["verification_only"] = verification_only
    _result_["persisted"] = not verification_only
    _sm_set_visibility(base, True)
    if verification_only:
        created_unfold_name = feature.Name
        created_names = [
            obj.Name for obj in doc.Objects if obj.Name not in preexisting_names
        ]
        doc.abortTransaction()
        transaction_open = False
        doc.recompute()
        remaining = [name for name in created_names if doc.getObject(name) is not None]
        if remaining:
            # Some FreeCAD/Workbench combinations create recompute-side helper
            # objects outside the original transaction. Remove only objects
            # proven new relative to the pre-verification document snapshot.
            doc.openTransaction("Clean verification-only Sheet Metal Unfold")
            try:
                ordered_cleanup = []
                if created_unfold_name in remaining:
                    ordered_cleanup.append(created_unfold_name)
                ordered_cleanup.extend(
                    name for name in reversed(remaining) if name != created_unfold_name
                )
                for object_name in ordered_cleanup:
                    if doc.getObject(object_name) is not None:
                        doc.removeObject(object_name)
                doc.recompute()
                remaining = [
                    name for name in created_names if doc.getObject(name) is not None
                ]
                if remaining:
                    raise RuntimeError(
                        "Verification-only unfold cleanup left objects: "
                        + ", ".join(remaining)
                    )
                doc.commitTransaction()
            except Exception:
                doc.abortTransaction()
                raise
        _sm_set_visibility(base, True)
        _result_["rolled_back"] = True
        _result_["rolled_back_objects"] = created_names
        _result_["remaining_generated_objects"] = []
    else:
        doc.commitTransaction()
        transaction_open = False
        _result_["rolled_back"] = False
except Exception:
    if transaction_open:
        doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result is not None:
            return result.result
        raise ValueError(result.error_traceback or "Failed to unfold sheet metal")

    @mcp.tool()
    async def inspect_sheet_metal(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Inspect sheet thickness, bend surfaces, history, and unfold readiness.

        The report is compact: shape validity, solid count, declared/estimated
        thickness, planar stationary-face candidates, cylindrical bend-face
        count, native SheetMetal proxy history, Body Tip, and warnings. Use the
        returned face candidates as evidence, then resolve the final choice with
        ``select_subshapes`` before folding or unfolding.
        """
        bridge = await get_bridge()
        code = f"""
import FreeCAD
import math
{_SHEET_METAL_RUNTIME_HELPERS}
tools_module = _sm_require_workbench()
doc = _sm_document({doc_name!r})
obj = _sm_object(doc, {object_name!r}, "Sheet-metal")
shape = getattr(obj, "Shape", None)
if shape is None or shape.isNull():
    raise ValueError(f"{{obj.Name!r}} has no inspectable shape")
body = _sm_body_for(obj)
if body is not None:
    body_items = list(getattr(body, "Group", []))
    try:
        object_index = next(
            index for index, item in enumerate(body_items) if item is obj
        )
    except StopIteration:
        object_index = len(body_items) - 1
    history_objects = body_items[:object_index + 1]
else:
    history_objects = [obj]
history_evidence = _sm_unfold_history_evidence(obj)
history = []
declared_thicknesses = []
declared_bend_radii = []
for item in history_objects:
    proxy = getattr(item, "Proxy", None)
    proxy_type = type(proxy).__name__ if proxy is not None else None
    if proxy_type and proxy_type.startswith("SM"):
        history.append({{
            "name": item.Name,
            "proxy_type": proxy_type,
            "visible": bool(getattr(getattr(item, "ViewObject", None), "Visibility", False)),
            "display_mode": str(
                getattr(getattr(item, "ViewObject", None), "DisplayMode", "")
            ),
        }})
        for prop_name in ("radius", "Radius"):
            if hasattr(item, prop_name):
                prop = getattr(item, prop_name)
                value = float(getattr(prop, "Value", prop))
                if value > 0:
                    declared_bend_radii.append({{
                        "object": item.Name,
                        "property": prop_name,
                        "value": value,
                    }})
    for prop_name in ("Thickness", "thickness"):
        if hasattr(item, prop_name):
            prop = getattr(item, prop_name)
            value = float(getattr(prop, "Value", prop))
            if value > 0:
                declared_thicknesses.append({{"object": item.Name, "value": value}})
planar = []
cylindrical_faces = []
for index, face in enumerate(shape.Faces, start=1):
    surface_name = type(face.Surface).__name__
    if "Plane" in surface_name:
        normal = face.normalAt(0, 0)
        planar.append({{
            "face": f"Face{{index}}",
            "area": float(face.Area),
            "normal": [float(normal.x), float(normal.y), float(normal.z)],
            "centroid": [
                float(face.CenterOfMass.x), float(face.CenterOfMass.y),
                float(face.CenterOfMass.z),
            ],
        }})
    elif "Cylinder" in surface_name:
        surface = face.Surface
        parameter_range = list(face.ParameterRange)
        u_span = abs(float(parameter_range[1]) - float(parameter_range[0]))
        axis = surface.Axis
        center = surface.Center
        cylindrical_faces.append({{
            "face": f"Face{{index}}",
            "radius": float(surface.Radius),
            "axis": [float(axis.x), float(axis.y), float(axis.z)],
            "center": [float(center.x), float(center.y), float(center.z)],
            "u_span_radians": u_span,
            "full_sweep": bool(u_span >= 2.0 * math.pi - 1e-5),
            "area": float(face.Area),
            "classification": "unclassified",
        }})

# A real constant-thickness bend contributes coaxial inner/outer cylindrical
# faces whose radii differ by nominal thickness. Full 360-degree cylinders are
# hole/tube walls, while an unpaired partial cylinder is more likely a fillet or
# unrelated curved surface. Matching the declared native bend radius prevents
# arbitrary cylindrical geometry from being promoted to bend evidence.
thickness_values = [item["value"] for item in declared_thicknesses]
radius_values = [item["value"] for item in declared_bend_radii]
bend_face_names = set()
bend_pairs = []
for left_index, left in enumerate(cylindrical_faces):
    if left["full_sweep"] or left["face"] in bend_face_names:
        continue
    left_axis = FreeCAD.Vector(*left["axis"])
    left_center = FreeCAD.Vector(*left["center"])
    for right in cylindrical_faces[left_index + 1:]:
        if right["full_sweep"] or right["face"] in bend_face_names:
            continue
        right_axis = FreeCAD.Vector(*right["axis"])
        right_center = FreeCAD.Vector(*right["center"])
        axis_parallel = abs(left_axis.dot(right_axis)) >= 1.0 - 1e-6
        coaxial_offset = (right_center - left_center).cross(left_axis).Length
        radii = sorted([left["radius"], right["radius"]])
        radius_delta = radii[1] - radii[0]
        thickness_match = next((
            value for value in thickness_values
            if abs(radius_delta - value) <= max(1e-5, abs(value) * 1e-4)
        ), None)
        declared_radius_match = next((
            value for value in radius_values
            if any(
                abs(radius - value) <= max(1e-5, abs(value) * 1e-4)
                for radius in radii
            )
        ), None)
        same_sweep = abs(left["u_span_radians"] - right["u_span_radians"]) <= 1e-5
        if (
            axis_parallel and coaxial_offset <= 1e-5 and same_sweep
            and thickness_match is not None and declared_radius_match is not None
        ):
            bend_face_names.update((left["face"], right["face"]))
            bend_pairs.append({{
                "inner_face": left["face"] if left["radius"] <= right["radius"] else right["face"],
                "outer_face": right["face"] if left["radius"] <= right["radius"] else left["face"],
                "inside_radius": radii[0],
                "outside_radius": radii[1],
                "thickness": thickness_match,
                "sweep_degrees": math.degrees(left["u_span_radians"]),
            }})
            break
for item in cylindrical_faces:
    if item["face"] in bend_face_names:
        item["classification"] = "sheet_bend_pair"
    elif item["full_sweep"]:
        item["classification"] = "full_cylinder_non_bend"
    else:
        item["classification"] = "partial_unpaired_or_unmatched"
planar.sort(key=lambda item: item["area"], reverse=True)
estimated_thickness = None
thickness_warning = None
if planar:
    try:
        root_face = shape.getElement(planar[0]["face"])
        estimate = float(tools_module.smGetThickness(shape, root_face))
        if estimate > 1e-9:
            estimated_thickness = estimate
    except Exception as exc:
        thickness_warning = str(exc)
warnings = []
if len(shape.Solids) != 1:
    warnings.append("Expected exactly one continuous solid")
if not shape.isValid():
    warnings.append("Shape is invalid")
if not planar:
    warnings.append("No planar stationary face is available for native unfold")
if not declared_thicknesses and estimated_thickness is None:
    warnings.append("Nominal thickness could not be established")
if thickness_warning:
    warnings.append("Thickness estimate failed: " + thickness_warning)
if len(cylindrical_faces) > len(bend_face_names):
    warnings.append(
        f"{{len(cylindrical_faces) - len(bend_face_names)}} cylindrical face(s) "
        "were not classified as constant-thickness bends; they may be holes, "
        "fillets, tubes, or other curved surfaces"
    )
if body is not None and getattr(body, "Tip", None) is not obj:
    warnings.append("Object is not the current Body Tip; continue from the Tip before unfold")
if not history_evidence["native_history"]:
    warnings.append("No native SheetMetal feature exists in the active history")
if history_evidence["unsupported_shape_features"]:
    warnings.append(
        "Unsupported shape-producing features occur in the active history from "
        "the first native SheetMetal feature: "
        + str(history_evidence["unsupported_shape_features"])
    )
view = getattr(obj, "ViewObject", None)
display_mode = str(getattr(view, "DisplayMode", ""))
visible = bool(getattr(view, "Visibility", False))
if bool(getattr(FreeCAD, "GuiUp", False)) and (not display_mode or display_mode == "None"):
    warnings.append("Object has no usable GUI display mode (missing SheetMetal ViewProvider)")
_result_ = {{
    "object": obj.Name,
    "type_id": obj.TypeId,
    "proxy_type": type(getattr(obj, "Proxy", None)).__name__,
    "body": getattr(body, "Name", None),
    "tip": getattr(getattr(body, "Tip", None), "Name", None),
    "is_body_tip": body is None or getattr(body, "Tip", None) is obj,
    "shape_valid": bool(shape.isValid()),
    "solid_count": len(shape.Solids),
    "volume": float(shape.Volume),
    "declared_thicknesses": declared_thicknesses,
    "estimated_thickness": estimated_thickness,
    "planar_face_count": len(planar),
    "cylindrical_face_count": len(cylindrical_faces),
    "classified_bend_face_count": len(bend_face_names),
    # Backwards-compatible alias with strengthened semantics.
    "cylindrical_bend_face_count": len(bend_face_names),
    "bend_zone_count": len(bend_pairs),
    "declared_bend_radii": declared_bend_radii,
    "cylindrical_faces": cylindrical_faces,
    "bend_pairs": bend_pairs,
    "stationary_face_candidates": planar[:8],
    "sheet_metal_history": history,
    "has_native_sheet_metal_features": bool(history),
    "native_sheet_metal_history": history_evidence["native_linear_history"],
    "sheet_metal_history_classification": history_evidence["classification"],
    "history_evidence": history_evidence,
    "display_mode": display_mode,
    "visible": visible,
    "unfold_ready": bool(
        shape.isValid()
        and len(shape.Solids) == 1
        and planar
        and (body is None or getattr(body, "Tip", None) is obj)
        and history_evidence["supported"]
        and (not bool(getattr(FreeCAD, "GuiUp", False)) or bool(display_mode and display_mode != "None"))
    ),
    "warnings": warnings,
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result is not None:
            return result.result
        raise ValueError(result.error_traceback or "Failed to inspect sheet metal")
