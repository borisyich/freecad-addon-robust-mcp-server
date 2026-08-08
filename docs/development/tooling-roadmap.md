# Tooling roadmap

This is the prioritized TODO list for making FreeCAD MCP reliable for autonomous mechanical modeling.

Status was re-audited against the 123-tool registry and live FreeCAD 1.0 tests
on 2026-08-08. A partially implemented umbrella item remains unchecked until
every capability named by that item has a public, tested contract.

## Sketch authoring

- [ ] Add atomic `edit_sketch` to replace most `add_sketch_*` and one-by-one constraint tools.
- [ ] Give sketch geometry stable semantic IDs so constraints reference `left_wall` or `mount_hole_1`, not numeric indexes.
- [x] Support named constraints and Spreadsheet expressions in atomic constraint batches.
- [ ] Support grouped geometry/constraints, dry-run solver diagnostics, and full rollback on conflicts.
- [ ] Add profile intent checks: expected contour count, closed/open wires, self-intersections, construction geometry, and regions suitable for Pad/Pocket.
- [ ] Add higher-level primitives: centered rectangle, rounded rectangle, bolt-circle pattern, slot, symmetric trapezoid, and constrained hole layout.

## Topology and attachment

- [x] Add semantic face selectors using surface type, normal, centroid, area, bounds, local convexity, and adjacency.
- [x] Add semantic edge selectors using curve type, endpoints/direction, length/radius, adjacent faces/surface types, and location.
- [x] Add semantic vertex selectors using world point bounds, adjacency counts,
  deterministic sorting, pagination, and ready-to-use `VertexN` references.
- [ ] Return selector confidence and ambiguity instead of silently choosing the first match.
- [ ] Add persistent selection recipes that are re-evaluated after recompute to reduce dependence on transient `FaceN`/`EdgeN` names.
- [ ] Add robust `attach_sketch` for origin planes, datum planes, planar faces, offsets, rotations, and support verification.
- [ ] Add ShapeBinder/SubShapeBinder helpers for stable cross-feature and cross-body references where appropriate.

FreeCAD documents the topological naming problem and recommends modeling practices that reduce fragile face/edge dependencies. Attachment and binder tools should therefore be first-class agent operations rather than Python-console workarounds.

## Feature operations and validation

- [x] Validate positive volume increase for Pad, Revolution, Additive Loft, and Additive Pipe.
- [ ] Extend postcondition contracts to additive primitives, patterns, mirrors, boolean unions, fillets, and chamfers.
- [ ] Add `preview_feature` / `dry_run_feature` that reports direction, expected bounds, intersection volume, and resulting solid count before committing.
- [x] Add validated `direction="auto"` fallback for directional subtractive
  tools, including Pocket, Groove, Hole, cylindrical cuts, and subtractive
  helical cuts; explicit directions never silently fall back.
- [ ] Extend world-space direction/preflight support to additive Pad/Revolution
  and datum offsets where automatic side selection has a clear design meaning.
- [ ] Add `create_simple_holes` for one or many circle centers and automatic support/direction selection.
- [x] Add `create_cylindrical_cut` for radial or datum-plane holes where PartDesign Hole is unnecessarily fragile.
- [x] Reject datum-plane `create_hole` calls early with an actionable alternative, validate each circle location by probe volume, and prefer actual planar-face support.
- [ ] Add feature suppression, safe reordering, replace-feature, and checkpoint/restore operations.
- [ ] Add design-history rules such as “all additive features before all holes” with configurable exceptions.
- [ ] Add parameter sensitivity validation for required drawing dimensions. In
  an isolated transaction, perturb each parameter by a small native-unit delta
  (initially `+0.1`), recompute, record the geometric response, then restore the
  exact original value. A zero volume change or a volume change above 10% of the
  baseline should trigger review rather than automatic acceptance. Treat this
  volume threshold only as triage: hole pitch, location, and angular parameters
  can change the shape while preserving volume, while a legitimate thickness or
  length change can exceed 10%. The durable implementation should therefore
  compare volume together with bounds, center of mass, topology/section evidence,
  and eventually a shape-difference metric before classifying a parameter as
  solid-driving or suspicious.
- [ ] Add structured failure diagnostics for fillet, chamfer, thickness, draft,
  and similar dress-up operations. Return selected subshape evidence, adjacent
  face/surface types, requested radius or distance, Shape/Body-Tip failure mode,
  and rollback status. Add an optional non-committing diagnostic search for a
  feasible fillet/chamfer size; never silently substitute a smaller value.

## Measurement and geometric evidence

- [x] Add `measure_geometry(measurement={"kind": "bbox", ...})` with fast and
  optimal OCCT modes, forced recompute, gap/tolerance reporting, and local/world
  coordinates. Fast mode can skip the optimal comparison with
  `report_gap=False`; every response
  identifies the actual OCCT path and recompute/tolerance evidence.
- [x] Add distance, angle, radius/diameter, wall-thickness, clearance,
  minimum-gap, and point-to-face measurements. These share strict
  `FaceN`/`EdgeN`/`VertexN` references with `select_subshapes`, return closest
  points/support evidence, and distinguish separation from solid interference.
  All eight operations use one discriminated public tool so the registry stays
  compact without weakening per-kind validation.
- [ ] Add mass properties: volume, area, center of mass, inertia tensor, principal axes, and material-based mass.
- [ ] Add section and probe tools: plane section, ray intersections, cylinder/box probe volume, and void continuity checks.
- [ ] Add shape-diff metrics before/after an operation: added/removed volume, changed bounds, face/edge count, and affected regions.
- [ ] Add tolerance-aware assertions usable directly in integration tests and agent plans.

OCCT exposes both ordinary and optimal bounding-box algorithms; the tool should report which method was used instead of treating a cached approximate box as exact design evidence.

## Visual verification

- [x] Make screenshots explicitly activate the document, select the view, fit geometry, flush GUI events, save through `saveImage`, and verify the file.
- [x] Support optional disk output and base64-free responses.
- [ ] Add `capture_views` for Front/Back/Top/Bottom/Left/Right/Isometric in one call.
- [ ] Add deterministic camera, projection, background, object visibility, line style, and image metadata.
- [ ] Add before/after image pairs and overlays for changed geometry.
- [ ] Add screenshot resources rather than embedding large base64 strings in normal JSON responses.

## Inspection and agent feedback

- [ ] Require an existing explicit `doc_name` for every non-document operation; never create `Unnamed` as a side effect.
- [ ] Add `create_document(on_exists="error|reuse|replace|suffix")` so duplicate-document behavior is intentional.
- [ ] Add a compact model audit: document count, active Body, Tip, feature order, errors, suppressed objects, solids, bounds, and parameter expressions.
- [ ] Add feature provenance: source sketch, support selector, parameter aliases, direction, validation evidence, and screenshots.
- [ ] Add actionable failures that distinguish execution, recompute, topology, feature effect, design-rule, and dimensional errors.
- [ ] Add local validation scopes so Spreadsheet or metadata edits are not rejected because an unrelated empty Body exists.
- [ ] Add a machine-readable operation journal suitable for replay, regression tests, and SFT/RL trajectory generation.

## Sheet metal design

Sheet-metal modeling is a distinct manufacturing domain, not a PartDesign
variant. The primary design object is a constant-thickness, developable sheet:
planar panels are connected by cylindrical bend zones, flat-domain features
remain attached to their panels, and bend allowance connects the formed and
unfolded representations. Deep drawing and stretch forming are intentionally
outside this first architecture because their blanks require material and
tooling simulation rather than ordinary K-factor equations.

### Architecture and invariants

The MCP layer wraps the native, installed
[FreeCAD SheetMetal Workbench](https://github.com/shaise/FreeCAD_SheetMetal)
`FeaturePython` proxies. It must not replace them with final `Part::Feature`
B-reps: native proxies preserve parameters, feature history, recomputation, and
unfold capability.

```text
engineering intent / flat-pattern panel graph
                    |
                    v
typed MCP contract + semantic topology references
                    |
                    v
native SheetMetal FeaturePython proxy in a linear Body history
                    |
          +---------+----------+
          |                    |
          v                    v
formed-state inspection   parametric Unfold outside Body
          |                    |
          +---------+----------+
                    v
     dimensional + visual manufacturing checks
```

Every geometry-changing operation is one transaction and must either commit a
valid, non-empty, single solid or roll back. A PartDesign operation accepts only
the current Body Tip as its base; this prevents hidden branches. Agent-supplied
topology references are checked for the expected subshape type, and agents must
derive them with `select_subshapes`. All responses return proxy type, Body/Tip,
solid count, shape validity, volume before/after, and the resolved references.

Neutral-axis data is safety-critical. `unfold_sheet_metal` therefore requires
exactly one explicit source: a manual K-factor with its ANSI/DIN convention, or
a SheetMetal material-definition Spreadsheet. It never silently uses the GUI
default. The flat pattern is a separate manufacturing representation and stays
outside the formed PartDesign Body so unfolding cannot replace its Tip.

### Compact tool surface

- [x] Add `sheet_metal_capabilities` to report installed version and availability
  of every wrapped native proxy. Missing workbench and missing operation are
  separate actionable states.
- [x] Add `create_sheet_metal_base` for a closed flat blank or open wall profile
  from a Sketcher sketch, with explicit thickness, inside radius, wall length,
  material side, midplane, and direction.
- [x] Add one discriminated `create_sheet_metal_feature` tool instead of one MCP
  tool per toolbar button. Its strict operation variants cover `flange`, `fold`,
  `junction`, `relief`, `corner_relief`, `extend`, `hem`, `solid_bend`, and
  `from_solid`; each variant exposes only meaningful parameters.
- [x] Add `unfold_sheet_metal` for a planar stationary face, explicit neutral
  rule, optional separated outline/internal/bend-line sketches, and bend-angle
  labels.
- [x] Add `inspect_sheet_metal` for native proxy history, nominal/estimated
  thickness, planar stationary-face candidates, cylindrical bend-face count,
  one-solid validity, Body Tip, and unfold readiness.
- [ ] Add batch flange/fold creation from a validated panel-and-bend graph after
  persistent semantic topology recipes exist. A batch must stop at the first
  failed bend and return the last valid graph checkpoint.
- [ ] Add formed-vs-unfolded correspondence diagnostics: panel area, transformed
  hole centers, bend-line length/count, blank bounds, and shape-difference
  evidence.
- [ ] Add material-library authoring and validation for radius/thickness K-factor
  tables, including monotonic lookup checks and explicit ANSI/DIN conversion.
- [ ] Add manufacturing checks for minimum bend radius, bend-to-hole distance,
  relief sufficiency, flange collision, self-intersection, grain direction, and
  press-brake tooling access.
- [ ] Add formed-feature APIs for wrapped cutouts and local forming only after
  thickness-continuity postconditions are available. Beads, dimples, louvers,
  embosses, and deep draws must be labelled as formed/stamped operations and
  must not claim an exact developed blank without process data.

### Testing strategy

- [x] Unit-test discriminated schemas, forbidden extra fields, positive
  dimensions, K-factor/material-sheet exclusivity, module/class dispatch,
  transaction rollback, semantic reference type checks, and result evidence.
- [x] Keep the registered-tool/documentation catalog test authoritative so the
  five tools cannot be added without agent-facing documentation.
- [ ] Add live canonical parts when SheetMetal is installed in CI: an L-bracket
  (base + flange), a sketch-line fold reconstructed from a flat blank, a hemmed
  enclosure corner with relief/junction, and solid-to-sheet conversion.
- [ ] For each live part, mutate thickness, radius, angle, and K-factor and prove
  downstream recomputation. Validate formed volume/solid count and compare the
  unfold outline, bend lines, and flat-domain holes against stored invariants.
- [ ] Add negative regressions for stale Body bases, wrong Face/Edge/Vertex
  references, non-planar unfold roots, missing material rules, multi-solid
  results, self-intersection, disconnected flanges, and unavailable workbench
  modules. Every failure must leave no new feature and preserve the prior Tip.

The engineering workflow and panel/bend graph are documented in
`.agents/skills/freecad-engineering/references/sheet-metal-flat-patterns.md`.
Upstream command semantics are tracked against the
[SheetMetal repository](https://github.com/shaise/FreeCAD_SheetMetal),
[FreeCAD SheetMetal wiki](https://wiki.freecad.org/SheetMetal_Workbench), and
[workbench discussion thread](https://forum.freecad.org/viewtopic.php?f=3&t=60818).

## Testing

- [x] Add a complete bracket regression with wrong-direction rollback, additive-volume validation, final-hole ordering, parameter bindings, dimensional checks, void probes, and optional screenshot output.
- [ ] Add canonical integration parts for revolution, loft, sweep, patterns, mirrors, fillets, chamfers, datum attachments, and multi-body references.
- [ ] Store expected feature graphs and geometric invariants rather than relying only on screenshots or object existence.
- [ ] Add mutation tests: change Spreadsheet values and prove that geometry, selectors, and downstream features update correctly.
- [ ] Add negative sensitivity regressions for non-construction points, isolated
  open helper geometry, volume-preserving location parameters, and genuinely
  profile-driving constraints.

## Research references

- [FreeCAD: Topological naming problem](https://wiki.freecad.org/Topological_naming_problem)
- [FreeCAD: Basic Attachment Tutorial](https://wiki.freecad.org/Basic_Attachment_Tutorial)
- [OCCT: BRepBndLib bounding-box algorithms](https://dev.opencascade.org/doc/refman/html/class_b_rep_bnd_lib.html)
- [FreeCAD source repository](https://github.com/FreeCAD/FreeCAD)
