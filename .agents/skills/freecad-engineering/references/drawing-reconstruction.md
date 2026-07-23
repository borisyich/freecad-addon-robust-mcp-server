# Drawing reconstruction guidance

## Evidence extraction

1. Inspect the full sheet to identify projection convention, views, sections,
   details, notes, units, and repeated feature callouts.
2. Use enlarged tiles/crops for local dimensions and small geometry.
3. Create an evidence table with:
   - feature or requirement;
   - dimension/value/count;
   - source view or detail;
   - status: explicit, derived, or assumed;
   - confidence;
   - alternative interpretation when relevant.
4. Reconcile every feature across all applicable views before committing it to
   the feature plan.

## Planning

Choose the stock/process classification first. Then plan a parametric sequence
with:

- Body and sketch names;
- sketch plane or datum;
- controlling dimensions;
- additive/subtractive/revolved operation;
- expected change in silhouette, volume, or bounds;
- a view suitable for visual verification.

## Visual checking

Use same-view comparisons. A whole drawing sheet compared with an isometric
screenshot is usually weak evidence. Crop the relevant drawing view and orient
FreeCAD to the same projection.

`compare_images` only presents images. It does not align them, read dimensions,
or compute correctness. Use it to write concrete observations such as missing
hole, wrong count, wrong profile, wrong bend direction, or inconsistent scale.

## Autonomous ambiguity handling

When a value is unreadable or ambiguous:

1. inspect all views/details and nearby dimensions;
2. derive constraints from overall dimensions and repeated geometry;
3. choose the interpretation with the fewest unsupported assumptions;
4. record the assumption and confidence;
5. model it parametrically so it can be revised;
6. revisit the assumption when later evidence conflicts.

Do not silently invent a convenient dimension. Do not stop the entire task merely
because one noncritical value is uncertain; use the best-supported interpretation
and report it.
