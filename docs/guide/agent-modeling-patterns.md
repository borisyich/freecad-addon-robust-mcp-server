# Modeling patterns for engineering agents

The canonical agent rule file is [`.clinerules/freecad-modeling.md`](../../.clinerules/freecad-modeling.md). Its core workflow is:

1. Reuse one explicit document and one PartDesign Body.
2. Centralize key dimensions in a Spreadsheet.
3. Build the entire additive blank first.
4. Build bosses as solids; perform all bores, pockets, and holes after additive geometry.
5. Validate positive added or removed volume after every feature.
6. Keep one valid solid and verify the Body Tip.
7. Select faces and edges geometrically, not by guessed `FaceN` or `EdgeN` values.
8. Recompute, inspect, and capture standard views after each major step.
9. Roll back the failed operation instead of creating another document or Body.
10. Finish with dimensional, feature-order, expression, and void-probe checks.

## Why feature validity is not enough

FreeCAD may create a feature object whose shape is valid while the intended Body is unchanged—for example, a Pad extruded away from the existing solid. Additive tools therefore validate a measurable volume increase in addition to shape validity and single-solid topology.

## Recommended screenshot call

```python
get_screenshot(
    return_image=True,
    view_angle="Isometric",
    doc_name="PartDocument",
    fit_all=True,
    background="White",
    save_to_disk=True,
    output_path="screenshots/after_ring.png",
    return_data=False,
)
```

The image is returned as MCP `ImageContent` for actual visual inspection, while disk saving retains a reproducible checkpoint. Keep `return_data=False` so base64 is not duplicated as text metadata.

## Bracket regression

`tests/integration/test_bracket_full_workflow.py` reproduces the observed agent
trajectory: it proves wrong-direction Pad rollback, creates the boss as solid
Ø60 material, performs Ø35/Ø18/Ø10 cuts only after all additive features, checks
100×65×105 mm bounds, validates Spreadsheet bindings and void probe volumes,
and optionally saves an isometric screenshot.

Run it only while the FreeCAD Robust MCP bridge is active:

```bash
PYTHONPATH=src pytest tests/integration/test_bracket_full_workflow.py
```
