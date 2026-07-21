# FreeCAD modeling rules for the engineering agent

1. Inspect documents first. Reuse the intended document, pass `doc_name` explicitly, and never create duplicate `Unnamed` or suffixed documents silently.
2. Use one `PartDesign::Body` per part and keep one contiguous solid. Name sketches and features by function.
3. Put key dimensions in a Spreadsheet and bind feature properties or named constraints to aliases. Do not replace design intent with `Fix` constraints.
4. Build the complete additive blank first: base, walls, solid bosses, ribs. Perform every bore, pocket, and hole only after all additive features. Then make fillets, chamfers if need.
5. For direction-sensitive Pad operations pass an explicit world-space `direction=[x,y,z]`; do not guess `reversed`, because the positive sketch normal depends on support orientation and may differ between planes or FreeCAD builds. After an additive operation require a valid one-solid result, the new feature as Body Tip, positive `added_volume`, and verify `effective_direction` plus world-space bounds or orthographic views. After a cut require positive `removed_volume`.
6. Use `create_hole` only with a new sketch containing non-construction circles. Prefer attachment to an actual planar solid face such as `Pad_Base.Face8`; do not use sketch points and do not reuse a consumed sketch.
7. A datum plane only positions a sketch; it does not make `PartDesign::Hole` reliable. For radial, tangent-plane, or other off-face holes use `create_cylindrical_cut(axis_origin, axis_direction, diameter, depth)` instead of repeatedly changing Hole attachment or `reversed`.
8. Prefer standard MCP tools. Use `safe_execute` only for a missing or demonstrably invalid tool, keep it local to one operation, and validate immediately.
9. Do not guess `FaceN` or `EdgeN`. Inspect geometry and select by plane, normal, location, and adjacency; topology names are temporary. Use `FaceN` or `EdgeN` only if there are no no other ways to make a goal.
10. After every major feature: recompute, inspect dimensions and volume, then call `get_screenshot(return_image=True)` and actually inspect the returned pixels. For a drawing available only by path, call `open_image(path)` first. Use `compare_images(reference_path, candidate_path)` when both images are saved on disk.
11. On failure, undo or remove only the failed feature, confirm the previous Tip and solid are restored, then correct the cause. Do not start another Body or document to hide an error.
12. Before completion, verify feature order, expressions, one valid solid, overall dimensions.
13. If you add some additional auxiliary bodies (for example, for cutting internal cutouts or pockets) you should set their visibility to false.