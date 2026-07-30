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

## Resolution — 2026-07-30

- **FC-MCP-001 fixed:** `draft_shapestring.name` now always contains the
  internal FreeCAD `Name`; the user-facing `Label` remains in `label`.
- **FC-MCP-002 fixed:** the requested document is activated around
  `Draft.make_shapestring`, and the previous active document is restored in
  `finally`.
- **FC-MCP-003 fixed for closed-choice arguments:** public annotations now use
  `Literal[...]`; runtime MCP schemas expose enums for 27 tools instead of 8.
  `create_sketch.plane` intentionally remains a string because it also accepts
  face references and datum-plane object names.
- The invalid external-geometry fixture is isolated in a standalone Sketch and
  uses a real box edge instead of an empty `Part::Line`; PartDesign correctly
  rejects unrelated solids as external geometry for a Body-owned first sketch.

Verification:

- 507 unit tests passed.
- Both live Draft regressions passed using FreeCAD 1.0.2 in GUI/XML-RPC mode.
- Registry, documented-choice and schema introspection checks passed.
- Ruff formatting check passed for all modified source modules.

Remaining environment issue: pytest still reports `WinError 5` when attempting
to update `.pytest_cache`; this does not affect test results and is not a
freecad-mcp behavior defect.

## Typed sketch support follow-up

`create_sketch` now provides a discriminated `support` union with four variants:
`origin_plane`, `body_tip_face`, `feature_face`, and `datum_plane`. Face
identifiers are schema-validated with `^Face[1-9]\d*$`, origin planes use an
enum, and extra fields are forbidden. The overloaded `plane` string has been
removed from the public tool schema.

All four variants passed live FreeCAD 1.0.2 GUI/XML-RPC tests. A repository-wide
AST/docstring audit found no remaining finite documented choices exposed as
unconstrained tool parameters. Dynamic identifiers such as object names,
workbench names, display modes, and thread sizes remain
strings intentionally because their valid values depend on document or runtime
state.

The removal follow-up also found two previously masked live-test defects:

- an unescaped inner `f"{plane!r}"` in the generated sketch code depended on
  the removed outer argument and now correctly remains inside the FreeCAD code;
- `create_datum_point` attempted to attach to a nonexistent Body origin
  `Point`. FreeCAD 1.0 exposes origin axes and planes but no point object, so a
  free datum point now uses `MapMode = "Deactivated"` and a direct `Placement`.

Verification after removing the argument:

- the production MCP schema has no top-level `create_sketch.plane` property;
- its `support` schema has a `kind` discriminator with all four variants;
- 514 unit tests passed;
- all four PartDesign choice-workflow integration scenarios and the full
  bracket workflow passed against FreeCAD 1.0.2 GUI/XML-RPC;
- the prompt catalog exposes `origin_plane`, not `plane`, for
  `create_sketch_guide`.

The repository-wide Ruff check is not currently clean because of existing lint
debt in touched large modules/tests (unused guidance imports, fixture-import
redefinition warnings, commented test code, and older whitespace). Ruff must be
run with `--no-cache` in this checkout because `.ruff_cache` has the same
`WinError 5` permission issue as `.pytest_cache`.
