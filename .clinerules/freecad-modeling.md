# FreeCAD modeling rules for the engineering agent

1. Inspect available documents first. Reuse the intended document; never create duplicate `Unnamed` or suffixed documents silently. Pass `doc_name` explicitly.
2. Create one `PartDesign::Body` per part and keep one contiguous solid. Name every sketch and feature by function, not by sequence.
3. Put key dimensions in a Spreadsheet and bind feature properties or named sketch constraints to aliases. Do not replace design intent with `Fix` constraints.
4. Build the complete additive blank first: base, walls, bosses, ribs. **Create bosses as solid material. Perform every bore, pocket and hole only after all additive features.**
5. After each additive operation require: valid shape, one solid, and positive added volume. After each subtractive operation require positive removed volume.
6. Prefer standard MCP tools. Use `safe_execute` only for a missing or demonstrably invalid tool, keep the code local to one operation, and validate immediately afterward.
7. Do not guess `FaceN` or `EdgeN`. Inspect geometry and select by plane/normal/location/adjacency. Treat numeric topology names as temporary. Use `FaceN` or `EdgeN` only if there are no no other ways to make a goal.
8. After every major feature: recompute, inspect dimensions and volume, capture Isometric view, and compare against expected bounds.
9. On failure, undo or remove only the failed feature, confirm the previous Tip and solid are restored, then correct the cause. Do not start a new Body or document to hide an error.
10. Before completion, verify feature order, parameter expressions, one valid solid, overall dimensions.
