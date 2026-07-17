# Tooling roadmap

This is the prioritized TODO list for making FreeCAD MCP reliable for autonomous mechanical modeling.

## Sketch authoring

- [ ] Add atomic `edit_sketch` to replace most `add_sketch_*` and one-by-one constraint tools.
- [ ] Give sketch geometry stable semantic IDs so constraints reference `left_wall` or `mount_hole_1`, not numeric indexes.
- [ ] Support grouped geometry, grouped constraints, named constraints, Spreadsheet expressions, dry-run solver diagnostics, and full rollback on conflicts.
- [ ] Add profile intent checks: expected contour count, closed/open wires, self-intersections, construction geometry, and regions suitable for Pad/Pocket.
- [ ] Add higher-level primitives: centered rectangle, rounded rectangle, bolt-circle pattern, slot, symmetric trapezoid, and constrained hole layout.

## Topology and attachment

- [ ] Add semantic face selectors using surface type, normal, centroid, area, bounds, orientation, and adjacency.
- [ ] Add semantic edge selectors using curve type, endpoints, tangent, length/radius, adjacent faces, convexity, and location.
- [ ] Return selector confidence and ambiguity instead of silently choosing the first match.
- [ ] Add persistent selection recipes that are re-evaluated after recompute to reduce dependence on transient `FaceN`/`EdgeN` names.
- [ ] Add robust `attach_sketch` for origin planes, datum planes, planar faces, offsets, rotations, and support verification.
- [ ] Add ShapeBinder/SubShapeBinder helpers for stable cross-feature and cross-body references where appropriate.

FreeCAD documents the topological naming problem and recommends modeling practices that reduce fragile face/edge dependencies. Attachment and binder tools should therefore be first-class agent operations rather than Python-console workarounds.

## Feature operations and validation

- [x] Validate positive volume increase for Pad, Revolution, Additive Loft, and Additive Pipe.
- [ ] Extend postcondition contracts to additive primitives, patterns, mirrors, boolean unions, fillets, and chamfers.
- [ ] Add `preview_feature` / `dry_run_feature` that reports direction, expected bounds, intersection volume, and resulting solid count before committing.
- [ ] Add explicit world-space direction vectors and `direction="auto"` for Pad, Pocket, Revolution, Hole, and datum offsets.
- [ ] Add `create_simple_holes` for one or many circle centers and automatic support/direction selection.
- [x] Add `create_cylindrical_cut` for radial or datum-plane holes where PartDesign Hole is unnecessarily fragile.
- [x] Reject datum-plane `create_hole` calls early with an actionable alternative, validate each circle location by probe volume, and prefer actual planar-face support.
- [ ] Add feature suppression, safe reordering, replace-feature, and checkpoint/restore operations.
- [ ] Add design-history rules such as “all additive features before all holes” with configurable exceptions.

## Measurement and geometric evidence

- [ ] Add `measure_bbox` with fast and optimal OCCT modes, forced recompute, gap/tolerance reporting, and local/world coordinates.
- [ ] Add distance, angle, radius/diameter, wall-thickness, clearance, minimum-gap, and point-to-face measurements.
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

## Testing

- [x] Add a complete bracket regression with wrong-direction rollback, additive-volume validation, final-hole ordering, parameter bindings, dimensional checks, void probes, and optional screenshot output.
- [ ] Add canonical integration parts for revolution, loft, sweep, patterns, mirrors, fillets, chamfers, datum attachments, and multi-body references.
- [ ] Store expected feature graphs and geometric invariants rather than relying only on screenshots or object existence.
- [ ] Add mutation tests: change Spreadsheet values and prove that geometry, selectors, and downstream features update correctly.

## Research references

- [FreeCAD: Topological naming problem](https://wiki.freecad.org/Topological_naming_problem)
- [FreeCAD: Basic Attachment Tutorial](https://wiki.freecad.org/Basic_Attachment_Tutorial)
- [OCCT: BRepBndLib bounding-box algorithms](https://dev.opencascade.org/doc/refman/html/class_b_rep_bnd_lib.html)
- [FreeCAD source repository](https://github.com/FreeCAD/FreeCAD)
