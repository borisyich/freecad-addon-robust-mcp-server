# Modeling patterns for engineering agents

The canonical client rule file is the root [`AGENTS.md`](../../AGENTS.md). It is mirrored in [`.clinerules/freecad-modeling.md`](../../.clinerules/freecad-modeling.md) and [`.agents/AGENT.md`](../../.agents/AGENT.md).

For an explanation of what each client receives automatically and what must be invoked explicitly, see [Agent guidance architecture](agent-guidance-architecture.md).

## Task-specific workflow entry points

| Task | MCP prompt | MCP resource |
|---|---|---|
| New model from drawing/image | `reproduce_from_drawing` | `freecad://workflows/drawing-reconstruction` |
| Modify existing model | `modify_existing_model` | `freecad://workflows/model-modification` |
| General PartDesign work | `freecad_guidance(task_type="partdesign")` | `freecad://best-practices` |

## Why feature validity is not enough

FreeCAD may create a valid feature that does not implement the intended design—for example, a Pad extruded away from the Body, a valid cut in the wrong position, or the wrong number of patterned holes. Every major feature therefore has two independent gates:

1. FreeCAD geometric validity and measurable effect;
2. correspondence to the drawing or change request.

## Mandatory checkpoint

```text
one feature
→ recompute and validate
→ same-view screenshot
→ open saved pixels
→ compare with a reference crop
→ discrepancy ledger
→ evaluate_model_checkpoint
→ continue / rework
```

A call to `compare_images` alone is not acceptance.

### Required discrepancy ledger

```json
{
  "category": "wrong_count",
  "severity": "major",
  "expected": "4 mounting holes",
  "observed": "3 mounting holes",
  "evidence": "screenshots/front_holes_compare.png",
  "proposed_reaction": "undo the pattern and recreate four occurrences"
}
```

### Reaction gate example

```python
evaluate_model_checkpoint(
    checkpoint_name="MountingHolePattern",
    geometry_valid=True,
    solid_count=1,
    expected_solid_count=1,
    dimension_checks_passed=True,
    visual_comparison_performed=True,
    view_match_confirmed=True,
    unresolved_dimensions=[],
    discrepancies=[...],
)
```

Proceed only when `decision == "continue"`.

## Drawing preparation

Use `open_image` for the overview, inspect individual views, sections, details, and dimension clusters. Compare a candidate only with the equivalent reference view. Do not compare an isometric model view with an orthographic drawing or a small candidate against an entire sheet. Also you may rotate candidate, and the get screenshot.

## Recommended screenshot call

```python
get_screenshot(
    return_image=True,
    view_angle="Front",
    doc_name="PartDocument",
    fit_all=True,
    background="White",
    show_corner_cross=True,
    corner_cross_size=10,
    save_to_disk=True,
    output_path="screenshots/front_after_pad.png",
    return_data=False,
)
```

Open the saved PNG with `open_image` before comparison. The corner cross is orientation evidence, not proof of the part's placement relative to the global origin.

## Existing-model modification

Inspect the history, aliases, constraints, expressions, dependencies, Tip, bounds, and baseline screenshots before changing anything. Modify the earliest feature or parameter that semantically owns the request. Avoid appending compensating geometry that merely hides an incorrect upstream model.

## Fallback code policy

Use standard MCP tools first. `safe_execute` and `execute_python` are allowed only for a missing or demonstrably invalid standard operation. State the reason, keep the code local to one feature, and run the full checkpoint immediately afterward.
