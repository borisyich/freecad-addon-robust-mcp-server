# Changelog
## AFTER FORK ORIGINAL REPO (consistent history of changes)

- Debugged tools
- Added effective-volume validation and rollback for Pad, Revolution, Additive Loft, and Additive Pipe.
- Reworked screenshots to activate the target 3D view, fit and refresh the GUI, verify image output, and optionally save without returning base64.
- Added engineering-agent modeling rules, a tooling roadmap, and a full bracket integration regression.
- Added `create_cylindrical_cut` for validated radial and off-face holes with an explicit world-space axis.
- Added typed `create_sketch.support` variants for origin planes, Body Tip
  faces, explicit feature faces, and datum planes. The former overloaded
  `plane` argument has been removed.
- Fixed `create_datum_point` on FreeCAD 1.0 by positioning a deactivated datum
  directly; Bodies do not expose the previously assumed attachable origin
  `Point` feature.
- Added an optional world-space `direction` argument to `pad_sketch`. This avoids relying on plane-specific `Reversed` semantics, which can differ with sketch support orientation. The tool now reports `sketch_normal`, `effective_direction`, and the resolved `reversed` value.
- Added multimodal image delivery: `get_screenshot(return_image=True)`, `open_image(path)`, and `compare_images(reference_path, candidate_path)` now return real MCP `ImageContent` instead of relying on paths or base64 text.
- Fixed the global X/Y/Z corner indicator in screenshots. FreeCAD's native corner cross is a screen-space feedback decoration and can be omitted by `saveImage`; `get_screenshot(show_corner_cross=True)` now derives the projected axes from the active camera and composites the triad into the PNG using Qt `QImage`/`QPainter`.
- Added root `AGENTS.md` and synchronized Codex/Cline/repository engineering rules.
- Added `reproduce_from_drawing` and `modify_existing_model` MCP prompts.
- Added `freecad://workflows/drawing-reconstruction` and `freecad://workflows/model-modification` resources.
- Reworked `freecad_startup` into a compact task router and clarified that MCP prompts/resources are discoverable but not guaranteed to be auto-injected by every client.
- Added deterministic `evaluate_model_checkpoint` decisions (`continue`, `rework`) from geometry evidence, visual-checkpoint status, unresolved dimensions, and a structured discrepancy ledger.
- Reworked best practices, documentation, and tests around ACT → OBSERVE → REACT, same-view comparison, stop criteria, design-intent-preserving model edits, and standard-tool-first execution.
- Added `open_image_tiles`, which returns a numbered overview and up to nine enlarged overlapping drawing fragments as labelled MCP image blocks. The current implementation uses explicit fragment metadata and prompts without a separate visual-acknowledgement gate.
- Added the repository Skill `.agents/skills/freecad-engineering/SKILL.md` as the
  single source of detailed CAD-engineering guidance. Root `AGENTS.md`, Cline
  rules, MCP prompts, and MCP resources now route to it instead of copying the
  same workflow.
- Added informative `validate_parametric_model`, reporting documents, Bodies,
  Tips, ordered Body history, sketches, solver/profile state, constraint
  diagnostics, expressions, and solid objects outside Bodies. Project guidance
  requires calling it immediately before the final response after geometry
  changes, but the report is not a rigid server-side pass/fail gate.
- Expanded process-oriented guidance for plate/block milling, turning from
  round/tube/hex stock, sheet-metal bending/forming, hybrid parts, datum strategy,
  feature ordering, and autonomous drawing interpretation.
- Hardened remote XML-RPC startup: transport `ping()` no longer depends on the
  FreeCAD GUI queue, startup now verifies that the Qt/main-thread execution
  queue is responsive, and version lookup is removed from the MCP session's
  critical initialization path.
- Added `execute_with_timeout` and lightweight `get_health` XML-RPC methods while
  retaining compatibility with legacy `execute(code)` clients.
- Cancelled queue requests are now skipped after timeout so stalled operations
  cannot execute unexpectedly after the FreeCAD GUI timer recovers.
- Added mandatory remote-start preflight, duplicate HTTP-listener detection,
  finite XML-RPC socket timeouts, serialized XML-RPC calls, and start/completion
  audit logs with MCP method, target, status, and duration.
- Fixed remote Streamable HTTP request completion: the audit middleware now
  forwards the real ASGI `http.disconnect` event instead of synthesizing an
  endless stream of empty request messages.
- Remote HTTP mode now defaults to ordinary JSON POST responses and
  backwards-compatible unstructured tool results. This guarantees a populated
  MCP `content` field for SaaS clients that mishandle `outputSchema` or
  `structuredContent`. Local stdio mode retains automatic structured output.
- Added protocol-level `tools/list` and `tools/call` start/completion logs so it
  is possible to distinguish a SaaS client-side failure from a call that
  actually reached FreeCAD.
- Added `scripts/update_freecad_bridge.ps1` to install the matching updated
  FreeCAD-side workbench on Windows with backup of the previous installation.
- Added opt-in sanitized logging of parsed MCP tool arguments via
  `FREECAD_LOG_TOOL_ARGUMENTS`, compact summaries via `FREECAD_LOG_TOOL_RESULTS`.
- Added final ASGI-boundary logging of the exact JSON-RPC response entity body
  sent to remote MCP clients.
- Added per-request raw request/response artifacts with byte counts and SHA-256
  hashes under `logs/mcp-wire`.
- Added console-safe full response logging that redacts only binary base64.
- Added separate client-request and server-response MCP validation results.
- Added stable revision profiles for 2024-11-05, 2025-03-26, 2025-06-18,
  and 2025-11-25.
- Added live Streamable HTTP verification for 2025-03-26, 2025-06-18, and
  2025-11-25.
- Added outputSchema/structuredContent, image, audio, version-header, JSON-RPC
  correlation, and missing-content regression tests.
- Added protocol-level FastMCP `instructions` with the required FreeCAD engineering workflow.
- Consolidated sketch geometry and constraint editing into atomic batch tools: `edit_sketch_geometry` and `edit_sketch_constraints`.
- Consolidated GUI/view utility entry points into `set_visual_properties`, `workbench`, `history`, and `selection`; removed zoom and duplicate console/recompute tools.
- Consolidated file exchange into `export` and `import`, with explicit format routing and consistent import results.
- Consolidated Box, Cylinder, Sphere, Cone, Torus, Wedge, and Helix creation into the typed `create_primitive` tool.
- Expanded the engineering Skill with flat-pattern recognition, panel-and-bend graphs, neutral-axis/developed-length rules, formed/unfolded validation, and a FreeCAD fallback strategy for stamped and bent sheet-metal parts.
- Split the ambiguous sketch `add_polygon` operation into `add_regular_polygon` and `add_polyline`.
- Hardened PartDesign pattern tools with Shape/Body Tip checks, rollback, before/after volume diagnostics, causal `AddSubShape` material-change checks, and a native `multi_transform_pattern` for combined linear/polar repetition.
- Added explicit Pocket direction/base selection, validated `Feature.FaceN` support for `UpToFace`, `set_body_tip`, and additive/subtractive `thread_helix`.
- Added link-property name resolution to `edit_object` and atomic `spreadsheet_apply_batch`.
- Fixed parametric-validator State serialization and excluded datum reference geometry from solid volume/bounds metrics.
- Fixed Spreadsheet alias discovery, idempotent cell clearing, and real rollback
  for failed `spreadsheet_apply_batch` calls. Unitless values bound to angle
  properties are now explicitly interpreted as degrees.
- Fixed the documented `create_hole(thread_type="ISO_FINE")` spelling and made
  `edit_object` require/apply `ThreadSize` together with a Hole thread-profile
  change so FreeCAD cannot silently reset the size to its first enumeration.
- Made `compare_images` mandatory in drawing-reconstruction guidance after every
  major feature and before any pattern multiplies a seed.
- Added a hard 50% ceiling for Sketcher Fix/Block constraints.
- Added drawing-dimension inventories to `validate_parametric_model`, including
  missing/unlinked required dimensions and direct/transitive Spreadsheet
  connectivity with unused-alias findings.
- Extended `edit_sketch_geometry(add_arc)` with endpoint/radius arcs and native
  tangent fillets between two existing lines.
- Reworked live PartDesign choice workflows to use separate linear Body histories and genuinely valid geometry for every draft plane and additive/subtractive pipe transition; positive scenarios now fail on `validate_parametric_model` errors instead of swallowing FreeCAD exceptions.
- Added post-recompute Shape/State/Body-Tip validation with rollback for fillet, chamfer, mirror, draft, thickness, subtractive loft, and subtractive pipe. Dress-up operations now reject stale Body-history branches and invalid `EdgeN`/`FaceN` references before mutation.
- Replaced the unsupported datum-line `ObjectXY` attachment with a deactivated datum aligned by Placement to the selected Body-local X/Y/Z axis, including direction/status validation.
- Refined Body validation so datum-only/reference-only construction states without a Tip are reported as incomplete warnings, while a missing Tip after shape-bearing history remains an error; invalid non-Tip history items are now surfaced.
- Added post-recompute validation, rollback, and Body Tip preservation to datum plane and datum point creation, and made the live datum workflow operate on a real padded Body.
- Normalized sketch-constraint expression paths to stable `Constraints[index]` values while preserving FreeCAD's original named or prefixed path as `source_path`.
- Fixed sketch-expression serialization for real FreeCAD canonical paths by resolving named `Constraints.<name>` bindings through `SketchObject.getIndexByName()`; prefixed and numeric paths are also supported.
- Made the MCP instruction regression test verify required workflow clauses instead of duplicating the entire instruction block.
- Expanded `get_sketch_info` and sketch-edit responses with indexed geometry,
  start/end points, type-specific geometry data, constraint references/datums,
  names/driving state, and stable ExpressionEngine bindings.
- Expanded `inspect_object` Shape topology with semantic face and edge records:
  surface/curve types, normals/directions, areas/lengths, endpoints, adjacency,
  local surface convexity, centers, radii, and bounds, while keeping the Shape
  property itself compact to avoid duplicate topology serialization.
- Added `select_subshapes`, a typed semantic face/edge selector for sketch
  support and topology-sensitive Fillet, Chamfer, Draft, and Thickness inputs.
- Added named sketch constraints plus create/update/clear support for Spreadsheet
  expressions through `edit_sketch_constraints`, with early rejection of
  expressions on non-dimensional constraints.
- Made FreeCAD GUI bridge execution fail with `FreeCADReportError` when Report View records high-confidence errors such as `<Exception>`, dangling property bindings, invalid topology links, missing Hole profiles, or invalid boolean tools despite Python `exec()` returning normally. Per-request delta extraction excludes old messages, and executed code cannot bypass the check.
- Hardened `spreadsheet_clear_cell`: referenced parameter cells are preserved by default, `clear_bindings=True` detaches dependent expressions atomically, and rollback restores cell content, alias, and expressions.
- Replaced ambiguous sketch batch item schemas with discriminated `op` unions,
  implemented consistent construction geometry handling and explicit arc point
  mappings, and documented zero-based MCP versus one-based GUI constraint
  references.
- Corrected `pocket_sketch` direction translation for FreeCAD's inverted Pocket
  `Reversed` convention.
- Prevented false `spreadsheet_apply_batch` success by validating computed
  formulas and flushing GUI events before translating new Report View formula
  diagnostics into `FreeCADReportError`.
- Added validated `direction="auto"` defaults to directional Pocket, Hole,
  cylindrical cut, Groove, and Helix operations. Explicit directions remain
  strict, legacy `reversed` inputs remain compatible, and responses report the
  selected direction plus compact per-direction diagnostics.
- Removed arbitrary runtime clipping of MCP tool descriptions; tools expose the
  complete concise purpose paragraph while tests enforce aggregate protocol
  budgets.
- Added selective prompt/resource discovery guidance so agents do not dump broad
  global `ALL_TOOLS` matches into context.
- Hardened `spreadsheet_apply_batch` to validate every non-empty formula cell
  after recompute, including unchanged dependent formulas, with rollback on any
  encoded formula error.
- Added live Spreadsheet regressions for dependent-formula rollback and the
  rectangular `A1:B2` range, plus numeric response-size budgets for compact tool
  modes.
- Added a compact native SheetMetal toolset for capability discovery, base-wall
  creation, nine typed manufacturing-feature variants, inspection, and
  explicit-material/K-factor unfolding with transactional shape and Body-Tip
  validation.
- Added Sheet Metal architecture and tool documentation plus live FreeCAD
  integration regressions for the upstream 100 mm L-profile calculation and a
  semantically selected edge flange. The registry audit now covers all 122 MCP
  tools and preserves the nine-variant public Sheet Metal schema.
- Added the compact `measure_geometry` tool with eight strict kinds: fast/optimal
  local/world bounding boxes, distance, angle, radius/diameter, validated wall
  thickness, clearance/interference, minimum gap, and point-to-face evidence.
- Extended `inspect_object` and `select_subshapes` with paged semantic
  `VertexN` records so point measurements no longer require guessed indices.
  - Added eight dedicated measurement tools for fast/optimal local/world bounding
  boxes, distance, angle, radius/diameter, validated wall thickness,
  clearance/interference, minimum gap, and point-to-face evidence. The strict
  `measure_geometry` dispatcher remains available for compatibility.
- Fixed invisible native SheetMetal results by attaching the same operation-
  specific GUI ViewProvider classes used by the SheetMetal Workbench. Creation
  and inspection responses now report visibility, display mode, available modes,
  and ViewProvider evidence, and reject `DisplayMode = None` in GUI sessions.
- Hardened SheetMetal inspection and unfolding: the formed input must be the
  current Body Tip with native SheetMetal history, while unsupported additive or
  copied PartDesign features after the final native SheetMetal feature make the
  model explicitly not unfold-ready. Valid subtractive hole/cut features remain
  supported.
- Prevented parametric-validation bypasses through audit-only expressions such
  as `0 * (Parameters.Width + Parameters.Height)` and `0 mm * (...)`; structurally
  neutralized references are now reported but do not count as solid-driving.
- Added protocol-level sheet-metal planning instructions: when a source drawing
  includes a flat pattern, agents must inventory the complete blank, panel
  regions, bend lines/directions, thickness, radius, and neutral-axis rule before
  modeling, use native SheetMetal bends, then unfold and compare against the
  source instead of substituting PartDesign construction.
- Hardened SheetMetal Fold/helper-sketch history: live FreeCAD 1.0.2 evidence
  confirms Body-owned bend-line sketches preserve the prior solid Tip, and
  `create_sketch` now enforces that contract across supported releases.
- Moved SheetMetal stale-Tip, topology, and helper-object validation ahead of
  native proxy creation; invalid null subshapes now return actionable
  `Cannot resolve` errors while every recompute failure still rolls back.
- Added live canonical/mutation coverage for edge flanges, sketch-line folds
  with flat-domain holes, relief-configured hemmed corners, and solid-to-sheet
  conversion, plus atomic negative regressions. Documented the upstream
  SheetMetal 0.8.21 open-box `SMFromSolid` unfold limitation.
- Made SheetMetal history evidence audit the complete active interval from the
  first native feature, so a later native proxy cannot hide an interleaved Pad
  or copied PartDesign feature. Inspection now separates native-feature presence
  from a supported linear native history.
- Split raw cylindrical-face evidence from classified constant-thickness bend
  pairs. Hole walls, tubes, and unmatched fillet-like cylinders no longer
  inflate `cylindrical_bend_face_count`.
- Extended Spreadsheet bindings to native FreeCAD expression paths such as
  `Placement.Base.x` and `AttachmentOffset.Base.z`, including atomic batch
  snapshot/verification and live recomputation regressions.
- Sheet-metal holes/cutouts now belong in the source flat blank sketch; 
  post-native PartDesign Hole/Pocket tails are rejected.
- Recognized known Dynamic SheetMetal proxy properties (`Thickness`, `Radius`,
  `radius`, `angle`, and `kfactor`) as geometry-driving validator endpoints
  without trusting arbitrary custom metadata.
- Added `unfold_sheet_metal(verification_only=True)`: it returns native flat
  shape and generated-sketch evidence, then transactionally removes the Unfold
  and all newly generated helpers while preserving the formed Body Tip.
- Added non-destructive validator guidance so an accepted sketch constraint
  graph is not bulk-rebuilt merely to optimize a final diagnostic.
- Documented the flat blank as the preferred place for sheet-metal holes and
  contour cutouts, while keeping validated post-native Hole/Pocket/Groove and
  cylindrical-cut features as explicitly supported subtractive tails.
- Replaced the incomplete shared Dynamic-property allowlist with a
  proxy-specific SheetMetal geometry contract covering every property assigned
  by the public feature dispatcher, including flange length/gaps/relief, hem,
  corner-relief offsets, and conversion parameters, without trusting arbitrary
  custom metadata.
- Fixed false-negative Spreadsheet/Sketcher dependency validation for named
  expression paths such as `.Constraints.HoleCenterX` on FreeCAD 1.0.x, where
  names are exposed through `Constraint.Name` instead of
  `SketchObject.getConstraintName()`. Profile constraints feeding native
  SheetMetal features now count as solid-driving, while construction-only
  constraints remain rejected.
- Added sketch-scoped `validate_parametric_model(target={"kind":"sketch",...})`
  so required dimensions are traced to non-construction geometry of the named
  sketch without Body/solid/Tip findings affecting the assessment.
- Hardened sketch profile readiness with pairwise contour intersection checks,
  FaceMaker topology validation, and explicit outer/hole nesting roles; closed
  wire count alone no longer implies a valid hole arrangement.
- Added coordinate-heavy constraint diagnostics and expanded the engineering
  Skill with straight-lines-first construction, datum-chain verification,
  B-spline gating, validation-integrity rules, and the explicit warning that
  0 DoF does not prove geometric correctness or design intent.
- Clarified in the public `add_arc` schema that center angles use degrees and
  documented radius-defined endpoint/fillet modes as the preferred engineering
  forms.
- Added flat-pattern sketch feature-group gates with numerical checks before
  visual comparison, mutable interpretation/evidence manifests, driving versus
  verification dimension roles, and a blocking response to source-backed
  tangency conflicts.
- Expanded coordinate-heavy sketch diagnostics to flag at least one absolute
  X/Y constraint per geometry and require source-backed/derived/solver-lock
  provenance review without rejecting legitimate ordinate drawings.
- Made `select_subshapes` request only the selected topology kind and required
  semantic fields; topology adjacency now uses indexed incidence traversal
  instead of full edge-by-face and vertex-by-edge/face scans.
- Added qualified subelement GUI selection, transient `highlight_faces`, planar
  local `move_faces` direct edits, explicit `Current` camera semantics, and
  validation warnings for static generic `PartDesign::Feature` snapshots.
- Added cylindrical-face `radius`, `axis_direction`, and `axis_point` to object
  topology and semantic selection, with matching radius/axis filters.
- Made `validate_parametric_model` accept native `Part::*` primitive/boolean
  chains as editable parametric history while retaining warnings for static or
  imported `Part::Feature` shapes.
- Aligned `select_subshapes.page_size` with `criteria.limit`; both now allow up
  to 200 matches.
- Flattened the public `select_subshapes.criteria` schema so MCP clients expose
  all face/edge/vertex filters instead of rendering ref-only union branches as
  `unknown`.
- Added `validate_parametric_model(workflow="imported_brep_edit")`, import/direct-
  edit provenance findings, and error-level invalid standalone-shape detection.
- Made `import` and root object-creation tools create a missing explicitly named
  target document, and added best-effort import provenance metadata.
- Accepted both normalized and integer-byte RGB triplets with schema-level length
  and range bounds.
- Reworked `spreadsheet_apply_batch` into dependency-safe stages (typed
  numbers/quantities, aliases, formulas, bindings, final recompute and
  validation). Structured quantities use `{"value": 40, "unit": "mm"}`;
  ambiguous string values are replaced by explicit `formula` and `text` fields.
- Added session-local `capture_shape_checkpoint` and `compare_shape_checkpoint`
  validation tools with before/after validity, bounds, volume, area, topology
  deltas, and localized OCCT added/removed B-rep regions.
- Added short working examples to the public schemas/descriptions of nested and
  commonly miscalled tools so clients need not inspect Python source to form
  requests.
- Kept missing-target document creation only for `import`; object, Spreadsheet,
  Draft, PartDesign, and library tools now use one strict centralized resolver
  so a misspelled `doc_name` cannot create a side-effect document.
- Made Shape checkpoint tolerance authoritative even when OCCT returns
  sub-threshold sliver regions, and added exact two-added/two-removed-cylinder
  integration coverage.
- Treated provenance-marked direct edits inside PartDesign Bodies as
  `intentional_direct_edit` information under `imported_brep_edit`.
- Preserved shared `$defs` after direct schema-property inlining, added drift
  coverage for the flattened subshape criteria contract, and renamed distance
  evidence to `within_distance_threshold`.
- Made shape-checkpoint comparison complexity-aware, separated nominal coaxial
  cylinder thickness from finite-patch distance, added world-axis placement for
  axial primitives, and allowed zero topology page limits in `inspect_object`.
- Expanded Modify existing models paragraph in Skill.md.
- Added one shared native end-condition contract to Pad, Pocket, Revolution,
  and Groove: bounded length/angle, ThroughAll, UpToFirst, and UpToFace.
- Added cone-axis serialization to semantic face selection and allowed
  `adjacent_surface_types` for face criteria as well as edges.
- Added `inspect_subshape_neighborhood` for compact bounded face-adjacency walks.
- Made `boolean_operation` abort null, invalid, or unexpected-solid results
  before transaction commit; one result solid is required by default.
- Added `summary`, `candidates`, and `full` detail levels to
  `inspect_sheet_metal`; the complete cylindrical-face list is now opt-in.
- Strengthened the FreeCAD engineering Skill with a universal local-edit
  feedback pattern: observe the face neighborhood, edit, re-observe, and
  restore/rework any collateral damage, with stricter checkpoints for STEP/B-rep.
- Reduced protocol-level server instructions to a sub-800-byte router so clients
  that repeat them beside selected tools do not multiply the full engineering
  policy, and added `get_freecad_prompt` as a prompt-list/render fallback for
  clients without native prompt controls.
- Fixed Shape checkpoints for placed/nested Compounds by serializing the native
  BREP location graph, retaining capture-time metric baselines, verifying the
  round-trip transform, and filtering topologically empty OCCT difference
  Compounds with sentinel infinite bounds.
- Added general BREP surgery tools for face grouping, rotational-pattern
  detection, defeaturing, feature extraction, sewing, healing, solid creation,
  and exact-Shape polar patterns.
- Preserved execution error type, stderr, duration, transaction state, and
  continuation status across legacy and new tools.
- Added bounded `safe_execute` queue cancellation and explicit running/unknown
  state when timed-out FreeCAD code cannot be interrupted safely.
- Hardened Boolean operations with intermediate/final validity, positive-volume,
  solid-count, fuzzy-tolerance, refine, and rollback checks.
- Rejected unknown root tool arguments, advertised strict schemas, and added
  registry-contract coverage for API drift.
- Hardened drawing reconstruction around a complete source-view manifest: every
  drawing view/detail/section is read before modeling, feature checkpoints compare
  only relevant equivalent views, and final acceptance reproduces and compares
  every source view one-to-one. Source dimensions now map to source view plus
  semantic geometry and end as driving/verification; exceptional `source_issue`
  requires concrete source evidence, while `unresolved` is not a terminal manifest
  role. Every explicit dimension is inventoried, including annotations carrying
  drafting markers such as an asterisk/REF/TYP; those markers are interpreted, not
  used as exclusion rules. Final dimension evidence measures the same semantic
  elements in the reproduced source-view context.
- `open_image_tiles`: tiles are never upscaled beyond their source crop resolution.
- Hardened imported-BREP editing after a real impeller workflow: defeaturing now
  rejects unchanged geometry and safely falls back from invalid refinement;
  feature extraction decomposes imperfect Boolean containers, validates solids
  independently, supports semantic volume/sort/limit selection, fuzzy cuts, and
  per-component refinement fallback; toroidal face inspection exposes analytic
  radii/axis/center; and non-fuzzy polar patterns use one multi-fuse operation.
- STEP/IGES export now preflights the destination and performs a default
  round-trip validity check; STEP also verifies solid count, volume, and bounds.
  Shape checkpoints use canonical BREP-round-trip metrics so stale imported
  bounds are normalized instead of producing false comparisons.
- An explicit screenshot `output_path` now implies disk saving.
- Hardened BREP follow-up checks: `defeature_faces` now detects no-op behavior
  from the raw defeaturing result before refinement; `boolean_operation` accepts
  fuzzy tolerance for generic fuse/cut/common operations through an auditable
  direct-Shape branch; exact shape-checkpoint differences reject invalid or
  nonphysical result regions; and compact capability metadata matches the full
  tool contracts.
- Fixed STEP/checkpoint validation so export and shape checkpoint metrics retain the
  original in-document Shape as the reference. BREP normalization now fails on
  volume, topology, placement, or bounding-box drift instead of silently rebasing
  the baseline and reporting a zero round-trip error.
- Added geometry-preservation guards to BREP healing and `removeSplitter`
  refinement. Volume, bounds, center of mass, and solid count are checked with
  explicit absolute/relative tolerances; unsafe refinement falls back and unsafe
  healing aborts unless the caller explicitly allows drift. Unfused polar patterns
  also verify `seed volume × occurrence count` before refinement.
- Added representative-candidate diagnostics (topology groups, volume/area
  spreads, placement evidence, and no automatic winner) to extracted repeated
  features, plus engineering guidance that forbids choosing a seed by generated
  name/order.
- Added session-local `start_tool_job`, `get_tool_job`, and `cancel_tool_job` for
  long-running FreeCAD operations. Running in-process OCCT work is explicitly
  reported as non-interruptible instead of pretending cancellation succeeded.
- Split non-dimensional source requirements from physical dimensions in the
  acceptance manifest. Empty dimension lists are valid; counts belong in
  `requirements`. Caller-authored evidence and image-review attestations no longer
  promote a structurally healthy model to machine-verified acceptance.

This project uses **component-specific versioning**. Each component has its own
release notes and version history.

## Component Release Notes

| Component              | Release Notes                                                        | Description                                           |
| ---------------------- | -------------------------------------------------------------------- | ----------------------------------------------------- |
| **Robust MCP Server**  | [RELEASE_NOTES.md](src/freecad_mcp/RELEASE_NOTES.md)                 | MCP server for AI assistant integration (PyPI/Docker) |
| **Robust MCP Bridge**  | [RELEASE_NOTES.md](freecad/RobustMCPBridge/RELEASE_NOTES.md)         | FreeCAD workbench addon                               |

## Versioning Scheme

Each component follows [Semantic Versioning](https://semver.org/) independently:

- **Robust MCP Server**: Released via git tags `robust-mcp-server-vX.Y.Z`
- **Robust MCP Bridge**: Released via git tags `robust-mcp-workbench-vX.Y.Z`

## Latest Versions

To see the current latest versions of each component:

```bash
just release::latest-versions
```

## Full Documentation

For detailed release process and contribution guidelines, see:

- [Release Process](https://spkane.github.io/freecad-robust-mcp-and-more/development/releasing/)
- [Contributing Guide](https://spkane.github.io/freecad-robust-mcp-and-more/development/contributing/)
