# `create_hole` reliability contract

## Why the previous implementation was unsafe

The old tool treated successful creation of a `PartDesign::Hole` document object as successful geometry. FreeCAD can create the feature object and complete `doc.recompute()` without raising a Python exception even when the operation is invalid or removes no material.

The main failure modes were:

1. The tool accepted point-only sketches. For the targeted FreeCAD 1.0.x workflow, use full non-construction circles as the Hole profile.
2. A sketch on the base XY plane may cut away from a Pad unless `Reversed` is enabled.
3. The same profile sketch could be consumed repeatedly, creating ambiguous PartDesign history dependencies.
4. The tool did not verify `Shape.isValid()`, solid count, Body Tip, volume reduction, or the number of actual cuts.
5. Failed features remained in the document and looked successful to an agent because `name`, `label`, and `type_id` existed.

## New success contract

`create_hole` now returns success only when all conditions are true:

- the document already exists;
- the object is a `Sketcher::SketchObject` inside exactly one Body;
- the sketch is not already consumed by another profile-based feature;
- the sketch contains only non-construction circles;
- a valid single-solid feature exists before the sketch;
- the resulting Hole shape is non-null and valid;
- the Body Tip is the new Hole;
- the result contains exactly one solid;
- body volume decreases by more than numerical tolerance;
- removed material contains one independent solid per profile circle.

When `reversed` is omitted, the tool tries both directions and retains the first valid subtractive result. If neither direction passes validation, the transaction is aborted and any leftover Hole object is removed.

## Correct workflow

```text
create_sketch {
  "body_name": "Body",
  "plane": "XY_Plane",
  "name": "HoleCirclesSketch",
  "doc_name": "HoleTest"
}

add_sketch_circle {
  "sketch_name": "HoleCirclesSketch",
  "center_x": -20,
  "center_y": 0,
  "radius": 2.5,
  "doc_name": "HoleTest"
}

add_sketch_circle {
  "sketch_name": "HoleCirclesSketch",
  "center_x": 0,
  "center_y": 0,
  "radius": 2.5,
  "doc_name": "HoleTest"
}

add_sketch_circle {
  "sketch_name": "HoleCirclesSketch",
  "center_x": 20,
  "center_y": 0,
  "radius": 2.5,
  "doc_name": "HoleTest"
}

create_hole {
  "sketch_name": "HoleCirclesSketch",
  "diameter": 5,
  "depth": 15,
  "doc_name": "HoleTest"
}
```

A successful response must include:

```json
{
  "validated": true,
  "shape_valid": true,
  "solid_count": 1,
  "profile_circle_count": 3,
  "removed_solid_count": 3,
  "removed_volume": 1.0,
  "reversed": true
}
```

`removed_volume` must be positive.

## Required regression scenarios

1. **Point-only sketch:** call must fail before creating a Hole feature.
2. **Base-plane direction:** a Pad above XY must normally succeed with automatic `reversed: true`.
3. **Explicit wrong direction:** call with the wrong explicit `reversed` value must fail and leave no Hole object.
4. **Circle outside the solid:** call must fail because the expected removed cut count is not reached.
5. **Three valid circles:** response must report `profile_circle_count == 3` and `removed_solid_count == 3`.
6. **Sketch reuse:** the second call with the same successfully consumed sketch must fail.
7. **Threaded ISO hole:** `thread_type="ISO"` must map to `ISOMetricProfile`; a short size such as `M6` may resolve to the available exact designation.
8. **Unsupported depth mode:** `UpToFirst` must be rejected before bridge execution for FreeCAD 1.0.x.

## Cleaning an already corrupted test document

Delete failed features in reverse history order (`Hole002`, `Hole001`, `Hole`) or undo them until the original hole sketch is unused. Then replace point geometry with circles or create a fresh circle sketch. Do not build another feature on top of the failed history.

## Running the live regression tests

With FreeCAD and the Robust MCP XML-RPC bridge running:

```bash
pytest -q tests/integration/test_partdesign_hole.py
```

These tests call the actual registered MCP tool and verify the resulting FreeCAD geometry and rollback behavior. They are not mock-only tests.
