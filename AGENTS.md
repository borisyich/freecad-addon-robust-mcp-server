# FreeCAD engineering-agent rules

These rules apply to model creation, reconstruction from drawings, and changes to existing FreeCAD models through `freecad-mcp`.

## 1. Task routing and startup

1. Verify the FreeCAD connection and GUI availability.
2. Inspect open documents first. Reuse the intended document, pass `doc_name` explicitly, and never create duplicate `Unnamed` or suffixed documents silently.
3. For drawing/image reconstruction, use the MCP prompt `reproduce_from_drawing` or read `freecad://workflows/drawing-reconstruction` before modeling.
4. For an existing-model change, use `modify_existing_model` or read `freecad://workflows/model-modification` before editing.
5. MCP prompts/resources may be available without being automatically inserted by the client; these repository rules remain authoritative.

## 2. Modeling policy

1. Use one `PartDesign::Body` per part and keep one intended contiguous solid. Name sketches and features by function.
2. Put key dimensions in a Spreadsheet or named sketch constraints and bind feature properties to aliases where practical. Do not replace design intent with broad `Fix` constraints.
3. Build the complete additive blank first: base, walls, solid bosses, ribs, flanges. Perform bores, pockets, holes, and cutouts after additive features. Apply fillets/chamfers last unless required earlier by design intent.
4. For direction-sensitive operations pass explicit world-space directions. Verify effective direction, bounds, and volume effect.
5. Use `create_hole` only with a new sketch containing non-construction circles on a supported planar face. For radial/off-face holes prefer `create_cylindrical_cut`.
6. Do not guess `FaceN` or `EdgeN`; identify geometry by plane, normal, position, dimensions, and adjacency whenever possible.
7. Prefer standard MCP tools. `safe_execute` and `execute_python` are fallback mechanisms only when a required standard tool is missing or demonstrably invalid. State why, limit fallback code to one operation, and validate immediately.
8. Auxiliary cutting/helper Bodies must be hidden and must not replace the intended parametric Body history.

## 3. Drawing evidence before modeling

1. Call `open_image` for any drawing supplied only as a path.
2. Create an evidence table containing feature, explicit value, source view/crop, status (`explicit`, `derived`, `assumed`), confidence, and unresolved questions.
3. Never infer symmetry, mirrored features, repeated counts, equal spacing, bend direction, or hidden geometry unless explicitly dimensioned or proven by the drawing.
4. If a required value is unreadable, conflicting, or missing, stop and ask the user instead of inventing it.

## 4. Mandatory ACT → OBSERVE → REACT checkpoint

After every major feature—Pad, Revolution, wall/thickness, boss, rib, bend, Pocket, Hole, cut, pattern, fillet, or chamfer—complete all steps below before creating the next feature.

### ACT

Create exactly one logically reviewable feature and recompute.

### OBSERVE: FreeCAD geometry

- Validate the feature and document.
- Confirm expected Body Tip and solid count.
- Confirm positive `added_volume` or `removed_volume` as applicable.
- Inspect dimensions, expressions, placement, world-space bounds/direction, and sketch status.

### OBSERVE: correspondence to requirement

- Set the candidate camera to the same view as the selected reference crop.
- Call `get_screenshot(save_to_disk=True, return_image=True, show_corner_cross=True)`.
- Open the saved screenshot with `open_image`.
- Call `compare_images` using equivalent reference and candidate views.
- Write a discrepancy ledger. Every entry must contain:
  - `category`;
  - `severity`;
  - `expected`;
  - `observed`;
  - `evidence`;
  - `proposed_reaction`.

`compare_images` only places images side by side. It does not approve geometry or calculate correctness.

### REACT

Call `evaluate_model_checkpoint` with geometric results, unresolved dimensions, and the discrepancy ledger.

- `continue`: accept checkpoint and proceed.
- `rework`: do not create the next feature. Undo/delete only the failed feature, verify the previous valid Tip/state is restored, correct the cause, and repeat the same checkpoint.

A screenshot without a ledger and an explicit reaction decision is not a completed observation.

## 5. Blocking conditions

Do not continue when any of these occurs:

- invalid shape, wrong Body Tip, or unexpected solid count;
- missing/extra major element or wrong feature quantity;
- wrong silhouette, profile, position, orientation, bend, radius, angle, or major dimension;
- candidate and reference views are not equivalent;
- a required drawing value is uncertain;
- geometric measurements and visual evidence conflict.

Rendering differences such as antialiasing, color, line thickness, and UI overlays are not geometric discrepancies by themselves.

## 6. Existing-model changes

1. Inspect history, constraints, expressions, dependencies, current Tip, visibility, placement, bounds, and volume before editing.
2. Record baseline invariants and screenshots.
3. Modify the earliest existing parameter/constraint/feature that semantically owns the requested change. Prefer this over appending compensating geometry.
4. Apply one change per checkpoint and verify that unrelated regions did not regress.
5. Do not create a replacement Body or duplicate document to hide a failed edit.

## 7. Completion

Before completion verify feature-by-feature acceptance, all explicit dimensions and quantities, one intended valid solid, correct Body Tip, parametric editability, sensible feature order, hidden helpers, matching required views/sections, no blocking discrepancies, and saved document path.
