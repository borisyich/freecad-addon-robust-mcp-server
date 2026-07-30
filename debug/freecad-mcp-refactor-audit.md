# freecad-mcp refactor audit — 2026-07-30

## Scope and environment

- Runtime registry: **111 public tools** in 12 tool modules.
- FreeCAD: 1.0.2, GUI mode, XML-RPC bridge on port 9875.
- Python server environment: 3.11.5 on Windows 10.
- Source under test: `D:\freecad-addon-robust-mcp-server`.
- Existing unit suite: **507 passed** (100% of collected unit tests).
- New registry snapshot gate: passed, exactly 111/111 tools represented.
- New documented-choice catalog: 30 argument catalogs, including all primitive
  kinds, sketch operations, constraint operations, formats, planes, axes,
  transitions, hole modes, views, macro templates, history and selection
  actions.

## Confirmed defects

### FC-MCP-001 — `draft_shapestring` result is not chainable

Severity: high.

`draft_shapestring(name="Text")` returns `{"name": "Text"}` where `Text` is the
object Label. Downstream tools (`draft_shapestring_to_face`,
`draft_shapestring_to_sketch`, `draft_extrude_shapestring`) call
`doc.getObject(shapestring_name)`, which requires the internal object Name
(normally `ShapeString`). Passing the documented result of the first tool into
the next therefore fails with:

`ValueError: ShapeString not found: 'Text'`

Regression:
`test_draft_shapestring_returned_name_is_chainable`.

Recommended fix: always return internal `Name` in `name`, return Label only in
`label`, and retain both fields consistently across all creation tools.

### FC-MCP-002 — `draft_shapestring(doc_name=...)` depends on ActiveDocument

Severity: high.

The implementation resolves `doc = FreeCAD.getDocument(doc_name)` but calls
`Draft.make_shapestring(...)` without activating that document. Draft creates
the object in `FreeCAD.ActiveDocument`. When another document became active
(reproduced after import/document lifecycle operations), the returned object
was absent from the explicitly requested document.

Regression:
`test_draft_shapestring_honors_explicit_doc_name`.

Recommended fix: activate `doc_name` for the Draft creation call and restore the
previous active document in `finally`, or use a creation API that takes the
document explicitly.

### FC-MCP-003 — most documented finite choices are absent from MCP schemas

Severity: medium.

Only 8 tools currently expose JSON-schema `enum`/discriminator constraints:
`create_primitive`, `selection`, `edit_sketch_geometry`,
`edit_sketch_constraints`, `export`, `import`, `workbench`, and `history`.

Many other arguments documented as finite lists remain unconstrained strings,
including boolean operation, mirror/section planes, pocket type,
revolution/groove axes, hole type/thread/drill point, pattern axes, transition
modes, datum planes/axes, Draft operation, view angles/background and macro
templates. Invalid values reach runtime code and produce inconsistent
ValueError/KeyError/tool-specific responses instead of protocol-level
validation.

Recommended fix: use `Literal[...]` (or equivalent Pydantic enums) for every
finite public choice and add one invalid-value schema test per argument.

## Verified live scenarios

- Document create/list/activate/recompute/save/close/open lifecycle.
- Connection/version/environment/console and checkpoint decisions.
- All seven primitive kinds.
- Generic object create/edit/delete/inspect/list.
- placement, rotation, copy, uniform scale and all mirror planes.
- fuse/cut/common plus multi-fuse/multi-common and compound/explode.
- line, plane, ellipse, prism, regular polygon, wire, face, extrusion,
  revolution, offset, shell, slicing and all standard section planes.
- Part loft and Part sweep.
- Spreadsheet create/set/get/alias/bind/range/import/export/clear.
- Macro create/read/run/list/delete and all four templates.
- STEP/IGES/STL/3MF/OBJ export and STEP/STL import.
- Image open/tile/compare.

## Test-infrastructure observations

- `section_shape` correctly rejects a plane that only touches a boundary and
  produces no section. The integration case now uses interior offsets for XY,
  XZ and YZ; all passed.
- `add_external_geometry` correctly rejected a standalone `Part::Line` as an
  invalid external-geometry provider for a sketch. This was a bad fixture, not
  classified as a product defect; the test remains to be adjusted to reference
  an allowed Body feature.
- Pytest cannot update `.pytest_cache` in this environment (`WinError 5`).
  Test execution is unaffected, but cache warnings are emitted.

## Added integration tests

- `tests/integration/test_all_tools_refactor_audit.py`
  - exact 111-tool registry coverage gate;
  - finite-choice catalog;
  - document/contracts workflow;
  - generic Part/object workflow;
  - Spreadsheet/Draft/macro/export/image/GUI/validation workflow;
  - focused Draft regressions.
- `tests/integration/test_partdesign_choice_workflows.py`
  - every Sketch geometry and constraint operation;
  - prismatic Pad/Pocket/cut/pattern/mirror/datum/fillet/chamfer chain;
  - turned Revolution/Groove workflow;
  - additive loft and additive/subtractive sweep/loft/thickness/draft families.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_all_tools_refactor_audit.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_partdesign_choice_workflows.py -q
```

The two focused Draft regressions are expected to fail until FC-MCP-001 and
FC-MCP-002 are fixed. Other failures should not be blanket-xfailed: inspect
whether they are a geometry precondition error or a tool regression.
