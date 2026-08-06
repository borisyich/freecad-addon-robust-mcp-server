"""Spreadsheet tools for FreeCAD Robust MCP Server.

This module provides tools for the Spreadsheet workbench, enabling
parametric design through cell values that can drive model dimensions.
"""

from collections.abc import Awaitable, Callable
from textwrap import dedent
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SPREADSHEET_RUNTIME_HELPERS = dedent(
    r'''
    def _spreadsheet_cell_content(sheet, cell):
        try:
            return sheet.getContents(cell) or ""
        except Exception:
            return ""


    def _spreadsheet_cell_alias(sheet, cell):
        try:
            return sheet.getAlias(cell) or None
        except Exception:
            return None


    def _spreadsheet_nonempty_cells(sheet):
        cells = set()
        try:
            cells.update(sheet.getNonEmptyCells())
        except Exception:
            pass

        # ``getNonEmptyCells`` is the public API, but include addresses from
        # the serialized cell store as a compatibility fallback for older
        # FreeCAD builds and alias-only cells.
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(sheet.getPropertyByName("cells").Content)
            for node in root.iter("Cell"):
                address = node.attrib.get("address")
                if address:
                    cells.add(address)
        except Exception:
            pass

        return sorted(cells)


    def _spreadsheet_aliases(sheet):
        cells = _spreadsheet_nonempty_cells(sheet)

        aliases = {}
        for cell in cells:
            alias = _spreadsheet_cell_alias(sheet, cell)
            if alias:
                aliases[alias] = cell
        return aliases


    def _spreadsheet_restore_content(sheet, cell, content):
        if not content:
            return
        # Spreadsheet.getContents prefixes literal strings with one quote,
        # while Spreadsheet.set expects the original unquoted text.
        restored = content[1:] if content.startswith("'") else content
        sheet.set(cell, restored)


    def _spreadsheet_serializable_value(value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        # FreeCAD.Units.Quantity and other wrapped cell values are not
        # marshalable by XML-RPC. Their string form preserves value and unit.
        return str(value)


    def _spreadsheet_formula_error(cell, content, computed):
        """Return a diagnostic when FreeCAD encoded a formula failure as text."""
        if not str(content or "").lstrip().startswith("="):
            return None
        text = str(computed or "").strip()
        lowered = text.lower()
        error_tokens = (
            "#err",
            "err:",
            "#ref",
            "#value",
            "#name",
            "#div/0",
            "#div0",
            "division by zero",
            "divide by zero",
            "invalid expression",
            "expression error",
            "parse error",
            "cyclic dependency",
        )
        if any(token in lowered for token in error_tokens):
            return f"Spreadsheet formula failed in {cell}: {text}"
        return None


    def _spreadsheet_expression_dependencies(doc, sheet, cell, alias):
        import re

        references = [f"{sheet.Name}.{cell}"]
        if alias:
            references.append(f"{sheet.Name}.{alias}")
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])(?:"
            + "|".join(re.escape(reference) for reference in references)
            + r")(?![A-Za-z0-9_])"
        )

        dependencies = []
        for obj in doc.Objects:
            for property_path, expression in getattr(obj, "ExpressionEngine", []):
                expression_text = str(expression)
                if pattern.search(expression_text):
                    dependencies.append({
                        "object": obj.Name,
                        "property": str(property_path),
                        "expression": expression_text,
                    })
        return dependencies


    def _spreadsheet_binding_expression(sheet, alias, target, property_name):
        cell = sheet.getCellFromAlias(alias)
        if not cell:
            raise ValueError(f"Alias not found: {alias!r}")

        expression = f"{sheet.Name}.{alias}"
        try:
            source_value = sheet.get(cell)
        except Exception:
            # A cell changed earlier in the same batch is not available via
            # get() until recompute, while getContents() is immediately valid.
            source_value = _spreadsheet_cell_content(sheet, cell)
        source_unit = ""
        try:
            source_unit = FreeCAD.Units.Quantity(source_value).Unit.Type
        except Exception:
            pass

        try:
            target_type = target.getTypeIdOfProperty(property_name)
        except Exception:
            target_type = ""

        unit_coercion = None
        if target_type == "App::PropertyAngle" and not source_unit:
            expression = f"({expression}) * 1 deg"
            unit_coercion = "deg"

        return expression, {
            "source_cell": cell,
            "source_unit": source_unit or None,
            "target_property_type": target_type or None,
            "unit_coercion": unit_coercion,
        }
    '''
).strip()


class SpreadsheetCellUpdate(BaseModel):
    """One cell value update for ``spreadsheet_apply_batch``."""

    model_config = ConfigDict(extra="forbid")
    cell: str = Field(pattern=r"^[A-Za-z]+[1-9]\d*$")
    value: str | int | float


class SpreadsheetAliasUpdate(BaseModel):
    """One cell alias update for ``spreadsheet_apply_batch``."""

    model_config = ConfigDict(extra="forbid")
    cell: str = Field(pattern=r"^[A-Za-z]+[1-9]\d*$")
    alias: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_alias(self) -> "SpreadsheetAliasUpdate":
        """Reject aliases that FreeCAD cannot expose as identifiers."""
        if not self.alias.isidentifier():
            raise ValueError("alias must be a valid Python identifier")
        return self


class SpreadsheetPropertyBinding(BaseModel):
    """One property expression binding for ``spreadsheet_apply_batch``."""

    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1)
    target_object: str = Field(min_length=1)
    target_property: str = Field(min_length=1)


def register_spreadsheet_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register Spreadsheet-related tools with the Robust MCP Server.

    Registers tools for creating and manipulating FreeCAD spreadsheets,
    enabling parametric design through cell values that can drive model
    dimensions via expressions.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.

    Returns:
        None. Tools are registered as side effect on the mcp instance.

    Raises:
        TypeError: If mcp does not have a tool() decorator method.
        TypeError: If get_bridge is not callable.

    Example:
        Register spreadsheet tools with an MCP server::

            from freecad_mcp.tools.spreadsheet import register_spreadsheet_tools

            register_spreadsheet_tools(mcp, get_bridge)
            # Now spreadsheet_create, spreadsheet_set_cell, etc. are available
    """

    @mcp.tool()
    async def spreadsheet_create(
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Spreadsheet object.

        Spreadsheets allow storing values and formulas that can be
        referenced by other objects in the document for parametric design.

        Args:
            name: Spreadsheet name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created spreadsheet information:
                - name: Spreadsheet object name
                - label: Spreadsheet label
                - type_id: Object type

        Raises:
            ValueError: If the bridge fails to create the spreadsheet.
            ValueError: If a spreadsheet with the same name already exists
                (FreeCAD will auto-rename).

        Example:
            Create a spreadsheet for parameters::

                result = await spreadsheet_create(name="Parameters")
                # Returns {"name": "Parameters", "label": "Parameters", ...}
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

# Wrap in transaction for undo support
doc.openTransaction("Create Spreadsheet")
try:
    sheet_name = {name!r} or "Spreadsheet"
    sheet = doc.addObject("Spreadsheet::Sheet", sheet_name)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sheet.Name,
        "label": sheet.Label,
        "type_id": sheet.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to create spreadsheet")

    @mcp.tool()
    async def spreadsheet_set_cell(
        spreadsheet_name: str,
        cell: str,
        value: str | int | float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the value of a cell in a spreadsheet.

        Values can be numbers, strings, or formulas. Formulas start with '='.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1", "B2", "C10").
            value: Value to set. Can be:
                - Number (int or float)
                - String (text)
                - Formula starting with '=' (e.g., "=A1+B1", "=2*pi")
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address that was set
                - value: Value that was set
                - computed: Computed value (for formulas)

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the object is not a spreadsheet.
            ValueError: If setting the cell value fails.

        Example:
            Set numeric values and formulas::

                await spreadsheet_set_cell("Params", "A1", 100)  # Number
                await spreadsheet_set_cell("Params", "A2", "=A1*2")  # Formula
                await spreadsheet_set_cell("Params", "B1", "Length")  # String
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

if not hasattr(sheet, "set"):
    raise ValueError(f"Object is not a spreadsheet: {spreadsheet_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Spreadsheet Cell")
try:
    cell = {cell!r}
    value = {value!r}

    # Set the cell value
    sheet.set(cell, str(value))
    doc.recompute()

    # Get the computed value
    try:
        computed = sheet.get(cell)
    except Exception:
        computed = value

    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
        "value": value,
        "computed": computed,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to set cell")

    @mcp.tool()
    async def spreadsheet_get_cell(
        spreadsheet_name: str,
        cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get the value of a cell in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1", "B2").
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with cell information:
                - cell: Cell address
                - value: Raw value (formula if it's a formula)
                - computed: Computed/displayed value
                - alias: Cell alias if set, None otherwise

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If retrieving cell data fails.

        Example:
            Get a cell value::

                result = await spreadsheet_get_cell("Params", "A1")
                print(f"Value: {result['computed']}")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

cell = {cell!r}

# Get computed value
try:
    computed = sheet.get(cell)
except Exception:
    computed = None

# Get raw content (formula or value)
try:
    content = sheet.getContents(cell)
except Exception:
    content = None

# Check for alias
alias = None
try:
    # Get all aliases and check if this cell has one
    aliases = sheet.getPropertyByName("cells").Content
    # Parse XML to find alias - simplified approach
    for prop_name in dir(sheet):
        if not prop_name.startswith("_"):
            try:
                cell_prop = sheet.getCellFromAlias(prop_name)
                if cell_prop == cell:
                    alias = prop_name
                    break
            except Exception:
                pass
except Exception:
    pass

_result_ = {{
    "cell": cell,
    "value": content,
    "computed": computed,
    "alias": alias,
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get cell")

    @mcp.tool()
    async def spreadsheet_set_alias(
        spreadsheet_name: str,
        cell: str,
        alias: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set an alias for a cell in a spreadsheet.

        Aliases allow referencing cell values by name instead of cell address.
        This is the key to parametric design - set an alias like "Length"
        and then reference it in object properties as "Spreadsheet.Length".

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1").
            alias: Alias name (e.g., "Length", "Width"). Must be a valid
                Python identifier (no spaces, starts with letter).
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address
                - alias: Alias that was set

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the alias is not a valid Python identifier.
            ValueError: If setting the alias fails.

        Example:
            Set aliases for parametric dimensions::

                await spreadsheet_set_alias("Params", "A1", "BoxLength")
                await spreadsheet_set_alias("Params", "A2", "BoxWidth")
                # Now use Params.BoxLength in expressions
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Cell Alias")
try:
    cell = {cell!r}
    alias = {alias!r}

    # Validate alias is a valid identifier
    if not alias.isidentifier():
        raise ValueError(f"Invalid alias: {alias!r}. Must be a valid Python identifier.")

    sheet.setAlias(cell, alias)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
        "alias": alias,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to set alias")

    @mcp.tool()
    async def spreadsheet_get_aliases(
        spreadsheet_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get all aliases defined in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with aliases:
                - spreadsheet: Spreadsheet name
                - aliases: Dictionary mapping alias names to cell addresses
                - count: Number of aliases

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If retrieving aliases fails.

        Example:
            List all parameter aliases::

                result = await spreadsheet_get_aliases("Params")
                for alias, cell in result["aliases"].items():
                    print(f"{alias} -> {cell}")
        """
        bridge = await get_bridge()

        code = f"""
{SPREADSHEET_RUNTIME_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

aliases = _spreadsheet_aliases(sheet)

_result_ = {{
    "spreadsheet": sheet.Name,
    "aliases": aliases,
    "count": len(aliases),
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get aliases")

    @mcp.tool()
    async def spreadsheet_clear_cell(
        spreadsheet_name: str,
        cell: str,
        doc_name: str | None = None,
        clear_bindings: bool = False,
    ) -> dict[str, Any]:
        """Clear a cell in a spreadsheet.

        This removes the cell's content and any alias.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address to clear (e.g., "A1").
            clear_bindings: Detach expressions that reference this cell or its
                alias before clearing. Defaults to False so a parameter cannot
                silently disconnect downstream model dimensions.
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address that was cleared
                - cleared_bindings: Expressions detached from the cell

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If clearing the cell fails.

        Example:
            Clear a cell::

                await spreadsheet_clear_cell(
                    "Params", "A1", clear_bindings=True
                )
        """
        bridge = await get_bridge()

        code = f"""
{SPREADSHEET_RUNTIME_HELPERS}

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

cell = {cell!r}
clear_bindings = {clear_bindings!r}
previous_alias = _spreadsheet_cell_alias(sheet, cell)
previous_content = _spreadsheet_cell_content(sheet, cell)
dependent_bindings = _spreadsheet_expression_dependencies(
    doc, sheet, cell, previous_alias
)
if dependent_bindings and not clear_bindings:
    targets = ", ".join(
        f"{{item['object']}}.{{item['property']}}"
        for item in dependent_bindings
    )
    raise ValueError(
        f"Spreadsheet cell {{sheet.Name}}.{{cell}} is referenced by: "
        f"{{targets}}. Pass clear_bindings=True to detach these "
        "expressions explicitly before clearing the cell."
    )

# Resolve all targets before starting a transaction so preflight failures do
# not mutate the document or trigger a rollback.
expression_snapshot = []
for item in dependent_bindings:
    target = doc.getObject(item["object"])
    if target is None:
        raise ValueError(
            f"Expression target not found: {{item['object']!r}}"
        )
    expression_snapshot.append(
        (target, item["property"], item["expression"])
    )

# Wrap the actual mutation in one transaction for undo support.
doc.openTransaction("Clear Spreadsheet Cell")
try:
    for target, property_path, _expression in expression_snapshot:
        target.setExpression(property_path, None)

    # Clearing is idempotent. Do not suppress alias-removal failures: returning
    # success while an alias survives makes the cell impossible to reuse.
    if previous_alias:
        sheet.setAlias(cell, "")
    if previous_content:
        sheet.clear(cell)
    doc.recompute()

    remaining_alias = _spreadsheet_cell_alias(sheet, cell)
    remaining_content = _spreadsheet_cell_content(sheet, cell)
    remaining_dependencies = _spreadsheet_expression_dependencies(
        doc, sheet, cell, previous_alias
    )
    if remaining_dependencies:
        raise RuntimeError(
            f"Cell {{cell}} still has dependent expressions after clearing: "
            f"{{remaining_dependencies!r}}"
        )
    if remaining_alias or remaining_content:
        raise RuntimeError(
            f"Cell {{cell}} was not fully cleared: "
            f"alias={{remaining_alias!r}}, content={{remaining_content!r}}"
        )
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
        "removed_alias": previous_alias,
        "had_content": bool(previous_content),
        "cleared_bindings": dependent_bindings,
    }}
except Exception:
    doc.abortTransaction()
    rollback_errors = []
    try:
        # The transaction normally restores everything. Detach the snapshot
        # expressions again before any manual cell repair, so an alias is never
        # removed while a property still references it.
        for target, property_path, _expression in expression_snapshot:
            target.setExpression(property_path, None)

        current_alias = _spreadsheet_cell_alias(sheet, cell)
        if current_alias:
            sheet.setAlias(cell, "")
        current_content = _spreadsheet_cell_content(sheet, cell)
        if current_content:
            sheet.clear(cell)
        _spreadsheet_restore_content(sheet, cell, previous_content)
        if previous_alias:
            sheet.setAlias(cell, previous_alias)
    except Exception as exc:
        rollback_errors.append(f"restore cell: {{exc}}")

    for target, property_path, expression in expression_snapshot:
        try:
            target.setExpression(property_path, expression)
        except Exception as exc:
            rollback_errors.append(
                f"restore {{target.Name}}.{{property_path}}: {{exc}}"
            )
    try:
        doc.recompute()
    except Exception as exc:
        rollback_errors.append(f"recompute: {{exc}}")

    if rollback_errors:
        raise RuntimeError(
            "Spreadsheet cell clear failed and rollback was incomplete: "
            + "; ".join(rollback_errors)
        )
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to clear cell")

    @mcp.tool()
    async def spreadsheet_bind_property(
        spreadsheet_name: str,
        alias: str,
        target_object: str,
        target_property: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Bind an object property to a spreadsheet cell using expressions.

        This creates a parametric link where the object property is
        driven by the spreadsheet cell value. When the spreadsheet
        value changes, the object updates automatically.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            alias: Cell alias to bind (the cell must have an alias set).
            target_object: Name of the object to modify.
            target_property: Property name to bind (e.g., "Length", "Width").
            doc_name: Document containing the objects. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - expression: The expression that was set
                - target_object: Object that was modified
                - target_property: Property that was bound

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the target object is not found.
            ValueError: If the alias does not exist on the spreadsheet.
            ValueError: If the target property does not exist.
            ValueError: If binding the expression fails.

        Example:
            Bind a box's length to a spreadsheet parameter::

                await spreadsheet_set_cell("Params", "A1", 50)
                await spreadsheet_set_alias("Params", "A1", "BoxLength")
                await spreadsheet_bind_property("Params", "BoxLength", "Box", "Length")
                # Now Box.Length = 50 and updates when A1 changes
        """
        bridge = await get_bridge()

        code = f"""
{SPREADSHEET_RUNTIME_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

target = doc.getObject({target_object!r})
if target is None:
    raise ValueError(f"Target object not found: {target_object!r}")

alias = {alias!r}
prop = {target_property!r}

# Verify the alias exists
try:
    cell = sheet.getCellFromAlias(alias)
    if not cell:
        raise ValueError(f"Alias not found: {{alias!r}}")
except Exception as e:
    raise ValueError(f"Alias not found: {{alias!r}}") from e

# Verify the property exists on target
if not hasattr(target, prop):
    raise ValueError(f"Property not found on target: {{prop!r}}")

# Wrap in transaction for undo support
doc.openTransaction("Bind Property to Spreadsheet")
try:
    expression, binding_metadata = _spreadsheet_binding_expression(
        sheet, alias, target, prop
    )
    target.setExpression(prop, expression)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "expression": expression,
        "target_object": target.Name,
        "target_property": prop,
        **binding_metadata,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to bind property")

    @mcp.tool()
    async def spreadsheet_apply_batch(
        spreadsheet_name: str,
        cells: list[SpreadsheetCellUpdate] | None = None,
        aliases: list[SpreadsheetAliasUpdate] | None = None,
        bindings: list[SpreadsheetPropertyBinding] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Apply cell values, aliases and property bindings atomically.

        All changes use one FreeCAD transaction and one final recompute. After
        recompute, every non-empty formula cell on the sheet is evaluated, not
        only cells changed by the batch. Any encoded formula failure rolls back
        the affected cells, aliases, and expressions. This is the preferred tool
        when building a parameter table because it avoids one MCP round trip and
        one recompute per individual operation.

        Args:
            spreadsheet_name: Existing Spreadsheet object.
            cells: Cell/value updates.
            aliases: Cell/alias assignments.
            bindings: Object-property bindings to spreadsheet aliases.
            doc_name: Document containing the objects. Uses active if None.

        Returns:
            Applied counts, number of validated formula cells, computed values,
            and created expressions.
        """
        normalized_cells = [
            (
                item
                if isinstance(item, SpreadsheetCellUpdate)
                else SpreadsheetCellUpdate.model_validate(item)
            ).model_dump()
            for item in (cells or [])
        ]
        normalized_aliases = [
            (
                item
                if isinstance(item, SpreadsheetAliasUpdate)
                else SpreadsheetAliasUpdate.model_validate(item)
            ).model_dump()
            for item in (aliases or [])
        ]
        normalized_bindings = [
            (
                item
                if isinstance(item, SpreadsheetPropertyBinding)
                else SpreadsheetPropertyBinding.model_validate(item)
            ).model_dump()
            for item in (bindings or [])
        ]
        if not (normalized_cells or normalized_aliases or normalized_bindings):
            raise ValueError("Batch must contain cells, aliases, or bindings")

        def reject_duplicates(
            items: list[dict[str, Any]], field: str, description: str
        ) -> None:
            values = [item[field] for item in items]
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                joined = ", ".join(repr(value) for value in duplicates)
                raise ValueError(f"Duplicate {description} in batch: {joined}")

        reject_duplicates(normalized_cells, "cell", "cell updates")
        reject_duplicates(normalized_aliases, "cell", "alias target cells")
        reject_duplicates(normalized_aliases, "alias", "aliases")
        binding_targets = [
            {
                "target": (item["target_object"], item["target_property"]),
            }
            for item in normalized_bindings
        ]
        reject_duplicates(binding_targets, "target", "binding targets")

        bridge = await get_bridge()
        code = f"""
{SPREADSHEET_RUNTIME_HELPERS}

cells = {normalized_cells!r}
aliases = {normalized_aliases!r}
bindings = {normalized_bindings!r}
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
sheet = doc.getObject({spreadsheet_name!r})
if sheet is None or not hasattr(sheet, "set") or not hasattr(sheet, "setAlias"):
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

# Resolve the final alias map before mutating the document. This permits an
# intentional alias swap while rejecting collisions and makes retries
# idempotent after an interrupted/failed client call.
existing_aliases = _spreadsheet_aliases(sheet)
final_alias_by_cell = {{cell: alias for alias, cell in existing_aliases.items()}}
for item in aliases:
    final_alias_by_cell[item["cell"]] = item["alias"]
final_aliases = {{}}
for cell, alias in final_alias_by_cell.items():
    other_cell = final_aliases.get(alias)
    if other_cell is not None and other_cell != cell:
        raise ValueError(
            f"Alias {{alias!r}} would be assigned to both "
            f"{{other_cell}} and {{cell}}"
        )
    final_aliases[alias] = cell

# Validate binding targets and aliases before mutating the document.
resolved_bindings = []
for item in bindings:
    target = doc.getObject(item["target_object"])
    if target is None:
        raise ValueError(f"Target object not found: {{item['target_object']!r}}")
    if not hasattr(target, item["target_property"]):
        raise ValueError(
            f"Property not found on target {{target.Name!r}}: "
            f"{{item['target_property']!r}}"
        )
    if item["alias"] not in final_aliases:
        raise ValueError(f"Alias not found: {{item['alias']!r}}")
    resolved_bindings.append((item, target))

touched_cells = sorted(
    {{item["cell"] for item in cells}} | {{item["cell"] for item in aliases}}
)
cell_snapshot = {{
    cell: {{
        "content": _spreadsheet_cell_content(sheet, cell),
        "alias": _spreadsheet_cell_alias(sheet, cell),
    }}
    for cell in touched_cells
}}
expression_snapshot = []
for item, target in resolved_bindings:
    old_expression = dict(getattr(target, "ExpressionEngine", [])).get(
        item["target_property"]
    )
    expression_snapshot.append((target, item["target_property"], old_expression))

doc.openTransaction("Apply Spreadsheet Batch")
try:
    # Detach bindings being replaced before a source cell changes units. This
    # avoids a transient invalid expression such as (360 deg) * 1 deg when an
    # existing unitless angle parameter is upgraded to an explicit angle.
    for target, property_name, _old_expression in expression_snapshot:
        target.setExpression(property_name, None)

    for item in cells:
        sheet.set(item["cell"], str(item["value"]))

    # Remove aliases from every affected cell first so swaps and idempotent
    # retries cannot fail with "Alias already defined".
    for item in aliases:
        if _spreadsheet_cell_alias(sheet, item["cell"]):
            sheet.setAlias(item["cell"], "")
    for item in aliases:
        sheet.setAlias(item["cell"], item["alias"])

    # Make values (including formula units) queryable without recomputing the
    # whole document. The final doc.recompute() below still occurs exactly once.
    if bindings:
        sheet.recompute()

    expression_results = []
    for item, target in resolved_bindings:
        expression, binding_metadata = _spreadsheet_binding_expression(
            sheet, item["alias"], target, item["target_property"]
        )
        target.setExpression(item["target_property"], expression)
        expression_results.append({{
            "target_object": target.Name,
            "target_property": item["target_property"],
            "expression": expression,
            **binding_metadata,
        }})

    doc.recompute()
    formula_cells_validated = 0
    for formula_cell in _spreadsheet_nonempty_cells(sheet):
        formula_content = _spreadsheet_cell_content(sheet, formula_cell)
        if not str(formula_content or "").lstrip().startswith("="):
            continue
        try:
            formula_computed = sheet.get(formula_cell)
        except Exception as exc:
            raise ValueError(
                f"Failed to evaluate spreadsheet cell {{formula_cell}}: {{exc}}"
            ) from exc
        formula_error = _spreadsheet_formula_error(
            formula_cell,
            formula_content,
            formula_computed,
        )
        if formula_error:
            raise ValueError(formula_error)
        formula_cells_validated += 1

    computed_cells = []
    for item in cells:
        try:
            computed = sheet.get(item["cell"])
        except Exception as exc:
            raise ValueError(
                f"Failed to evaluate spreadsheet cell {{item['cell']}}: {{exc}}"
            ) from exc
        computed_cells.append({{
            "cell": item["cell"],
            "value": item["value"],
            "computed": _spreadsheet_serializable_value(computed),
        }})
    doc.commitTransaction()
except Exception as batch_error:
    rollback_errors = []

    # Do not call abortTransaction() before restoring Spreadsheet cells.
    # FreeCAD 1.0 can emit ``Bad dynamic_cast!`` while its transaction engine
    # tries to restore a cell whose internal value type changed (for example,
    # a numeric literal replaced by an invalid formula). Restore the explicit
    # snapshots while the transaction remains open, recompute the valid state,
    # then commit that restored no-op state to close the transaction cleanly.
    for cell, previous in cell_snapshot.items():
        try:
            if _spreadsheet_cell_alias(sheet, cell):
                sheet.setAlias(cell, "")

            # Overwrite an existing cell directly when it had previous
            # content. Clearing and recreating a Spreadsheet cell inside the
            # same transaction can leave its dynamic property registration in
            # an invalid state in FreeCAD 1.0 (later get/getContents calls then
            # fail with "Invalid cell address or property"). Only clear cells
            # that were genuinely absent before the batch.
            if previous["content"]:
                _spreadsheet_restore_content(sheet, cell, previous["content"])
            elif _spreadsheet_cell_content(sheet, cell):
                sheet.clear(cell)

            if previous["alias"]:
                sheet.setAlias(cell, previous["alias"])
        except Exception as exc:
            rollback_errors.append(f"restore {{cell}}: {{exc}}")
    for target, property_name, old_expression in expression_snapshot:
        try:
            target.setExpression(property_name, old_expression)
        except Exception as exc:
            rollback_errors.append(
                f"restore {{target.Name}}.{{property_name}}: {{exc}}"
            )
    try:
        doc.recompute()
    except Exception as exc:
        rollback_errors.append(f"recompute: {{exc}}")

    if not rollback_errors:
        try:
            doc.commitTransaction()
        except Exception as exc:
            rollback_errors.append(f"finalize restored transaction: {{exc}}")

    if rollback_errors:
        # Emergency fallback only. It may still produce a FreeCAD diagnostic,
        # but is preferable to leaving an open transaction after an incomplete
        # explicit rollback.
        try:
            doc.abortTransaction()
        except Exception as exc:
            rollback_errors.append(f"abort failed transaction: {{exc}}")
        raise RuntimeError(
            "Spreadsheet batch failed and rollback was incomplete: "
            + "; ".join(rollback_errors)
        ) from batch_error
    raise

_result_ = {{
    "success": True,
    "spreadsheet": sheet.Name,
    "cells_applied": len(cells),
    "aliases_applied": len(aliases),
    "bindings_applied": len(bindings),
    "formula_cells_validated": formula_cells_validated,
    "cells": computed_cells,
    "bindings": expression_results,
}}
"""
        result = await bridge.execute_python(code)
        if (
            result.success
            and isinstance(result.result, dict)
            and result.result.get("success") is True
        ):
            return result.result
        raise ValueError(result.error_traceback or "Failed to apply spreadsheet batch")

    @mcp.tool()
    async def spreadsheet_get_cell_range(
        spreadsheet_name: str,
        start_cell: str,
        end_cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get values from a range of cells in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            start_cell: Starting cell address (e.g., "A1").
            end_cell: Ending cell address (e.g., "C5").
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with range data:
                - spreadsheet: Spreadsheet name
                - start: Start cell
                - end: End cell
                - cells: Dictionary mapping cell addresses to their values

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If start_cell or end_cell has an invalid format.
            ValueError: If retrieving the cell range fails.

        Example:
            Get a range of values::

                result = await spreadsheet_get_cell_range("Params", "A1", "B3")
                for cell, value in result["cells"].items():
                    print(f"{cell}: {value}")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

import re

start_cell = {start_cell!r}.upper()
end_cell = {end_cell!r}.upper()

# Parse cell addresses
def parse_cell(cell_str):
    match = re.match(r'^([A-Z]+)([0-9]+)$', cell_str)
    if not match:
        raise ValueError(f"Invalid cell address: {{cell_str}}")
    col_str, row_str = match.groups()
    # Convert column letters to number (A=0, Z=25, AA=26, etc.)
    # Use 1-based indexing per position, then convert to 0-based
    col = 0
    for c in col_str:
        col = col * 26 + (ord(c) - ord('A') + 1)
    col = col - 1  # Convert to 0-based index
    row = int(row_str)
    return col, row

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

start_col, start_row = parse_cell(start_cell)
end_col, end_row = parse_cell(end_cell)

# Ensure start <= end
if start_col > end_col:
    start_col, end_col = end_col, start_col
if start_row > end_row:
    start_row, end_row = end_row, start_row

cells = {{}}
for col in range(start_col, end_col + 1):
    for row in range(start_row, end_row + 1):
        cell_addr = col_to_str(col) + str(row)
        try:
            value = sheet.get(cell_addr)
            cells[cell_addr] = value
        except Exception:
            # Cell might be empty
            cells[cell_addr] = None

_result_ = {{
    "spreadsheet": sheet.Name,
    "start": start_cell,
    "end": end_cell,
    "cells": cells,
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get cell range")

    @mcp.tool()
    async def spreadsheet_import_csv(
        spreadsheet_name: str,
        file_path: str,
        delimiter: str = ",",
        start_cell: str = "A1",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import data from a CSV file into a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            file_path: Path to the CSV file to import.
            delimiter: CSV delimiter character. Defaults to ",".
            start_cell: Cell to start importing at. Defaults to "A1".
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with import result:
                - success: Whether the operation succeeded
                - rows_imported: Number of rows imported
                - cols_imported: Number of columns imported
                - start_cell: Starting cell

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If start_cell has an invalid format.
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If importing the CSV data fails.

        Example:
            Import parameters from CSV::

                await spreadsheet_import_csv("Params", "/path/to/data.csv")
        """
        bridge = await get_bridge()

        code = f"""
import csv
import re

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

file_path = {file_path!r}
delimiter = {delimiter!r}
start_cell = {start_cell!r}.upper()

# Parse start cell
match = re.match(r'^([A-Z]+)([0-9]+)$', start_cell)
if not match:
    raise ValueError(f"Invalid cell address: {{start_cell}}")
col_str, row_str = match.groups()
# Convert column letters to number (A=0, Z=25, AA=26, etc.)
# Use 1-based indexing per position, then convert to 0-based
start_col = 0
for c in col_str:
    start_col = start_col * 26 + (ord(c) - ord('A') + 1)
start_col = start_col - 1  # Convert to 0-based index
start_row = int(row_str)

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

# Wrap in transaction for undo support
doc.openTransaction("Import CSV to Spreadsheet")
try:
    rows_imported = 0
    max_cols = 0

    with open(file_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row_idx, row in enumerate(reader):
            for col_idx, value in enumerate(row):
                cell_addr = col_to_str(start_col + col_idx) + str(start_row + row_idx)
                # Try to convert to number if possible
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
                sheet.set(cell_addr, str(value))
            rows_imported += 1
            max_cols = max(max_cols, len(row))

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "rows_imported": rows_imported,
        "cols_imported": max_cols,
        "start_cell": start_cell,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to import CSV")

    @mcp.tool()
    async def spreadsheet_export_csv(
        spreadsheet_name: str,
        file_path: str,
        delimiter: str = ",",
        max_row_limit: int = 1000,
        max_col_limit: int = 52,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Export spreadsheet data to a CSV file.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            file_path: Path to write the CSV file.
            delimiter: CSV delimiter character. Defaults to ",".
            max_row_limit: Maximum rows to scan for data. Defaults to 1000.
            max_col_limit: Maximum columns to scan for data. Defaults to 52 (AZ).
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with export result:
                - success: Whether the operation succeeded
                - file_path: Path where file was written
                - rows_exported: Number of rows exported
                - cols_exported: Number of columns exported
                - truncated: True if data exists beyond the scan limits

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If export fails.

        Example:
            Export spreadsheet to CSV::

                await spreadsheet_export_csv("Params", "/path/to/output.csv")
        """
        bridge = await get_bridge()

        code = f"""
import csv

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

file_path = {file_path!r}
delimiter = {delimiter!r}
max_row_limit = {max_row_limit!r}
max_col_limit = {max_col_limit!r}

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

# Get used range - find max row and column with data within limits
max_row = 0
max_col = 0
truncated = False

# Scan within the configured limits
for col in range(max_col_limit):
    for row in range(1, max_row_limit + 1):
        cell_addr = col_to_str(col) + str(row)
        try:
            val = sheet.get(cell_addr)
            if val is not None:
                max_row = max(max_row, row)
                max_col = max(max_col, col)
        except Exception:
            pass

# Check if data exists beyond limits (probe one row/column past)
# Always probe, even if sheet appears empty within scan limits - data may exist beyond

# Check row beyond limit (probe first row past max_row_limit across all columns scanned)
probe_cols = max(max_col + 1, 1)  # At least probe column A
for col in range(probe_cols):
    cell_addr = col_to_str(col) + str(max_row_limit + 1)
    try:
        val = sheet.get(cell_addr)
        if val is not None:
            truncated = True
            break
    except Exception:
        pass

# Check column beyond limit (probe column at max_col_limit across rows)
if not truncated:
    probe_rows = max(max_row, 1)  # At least probe row 1
    for row in range(1, probe_rows + 1):
        cell_addr = col_to_str(max_col_limit) + str(row)
        try:
            val = sheet.get(cell_addr)
            if val is not None:
                truncated = True
                break
        except Exception:
            pass

# Also probe a cell beyond both limits if sheet appears empty
if not truncated and max_row == 0 and max_col == 0:
    # Probe one cell beyond both row and column limits
    cell_addr = col_to_str(max_col_limit) + str(max_row_limit + 1)
    try:
        val = sheet.get(cell_addr)
        if val is not None:
            truncated = True
    except Exception:
        pass

if max_row == 0:
    # Empty spreadsheet (within scan limits)
    _result_ = {{
        "success": True,
        "file_path": file_path,
        "rows_exported": 0,
        "cols_exported": 0,
        "truncated": truncated,
    }}
else:
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=delimiter)
        for row in range(1, max_row + 1):
            row_data = []
            for col in range(max_col + 1):
                cell_addr = col_to_str(col) + str(row)
                try:
                    val = sheet.get(cell_addr)
                    row_data.append(val if val is not None else "")
                except Exception:
                    row_data.append("")
            writer.writerow(row_data)

    _result_ = {{
        "success": True,
        "file_path": file_path,
        "rows_exported": max_row,
        "cols_exported": max_col + 1,
        "truncated": truncated,
    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to export CSV")
