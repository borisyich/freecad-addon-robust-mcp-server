# `create_hole` reliability contract

## What failed in the bracket run

The agent exposed two different workflows that must not be conflated:

1. **Mounting holes from a real planar face.** A circle sketch on the Body origin
   plane repeatedly produced no subtractive result. After the agent identified
   the actual top face of the base and attached the sketch to
   `Pad_Base.Face8`, `create_hole` succeeded and removed the expected volume.
2. **Radial oil hole from a datum plane.** Attaching the sketch to
   `DP_OilHole`, and then to its formal `Face1`, still produced a no-op Hole.
   The operation that actually worked was a `PartDesign::SubtractiveCylinder`
   with an explicit origin, axis, diameter, and depth.

The datum plane was useful for deriving position and direction; it was **not**
what made the hole work.

## Supported workflows

### Parametric `PartDesign::Hole`

Use `create_hole` when the sketch starts from an actual planar face of the
solid. A Body origin plane is accepted for simple cases, but an actual face is
preferred.

Requirements:

- create a new sketch for this feature;
- attach it to an actual planar face when possible;
- use only non-construction circles;
- do not use sketch points;
- do not reuse a consumed profile sketch;
- omit `reversed` unless the direction is intentionally fixed.

The tool tries both directions when `reversed=None` and succeeds only when:

- the result is one valid solid;
- the new Hole is the Body Tip;
- Body volume decreases;
- a geometric probe confirms removed material at every profile-circle axis.

The response includes support diagnostics, selected direction, volume delta,
and per-circle probe volumes. A syntactically created Hole object is not a
successful result.

### Radial or off-face cylindrical cut

Do not force `PartDesign::Hole` through a datum plane. Use:

```text
create_cylindrical_cut(
    body_name="Body",
    axis_origin=[x, y, z],
    axis_direction=[dx, dy, dz],
    diameter=10,
    depth=12.5,
)
```

This tool creates a validated `PartDesign::SubtractiveCylinder` and rolls back
unless material is removed along the requested axis while the Body remains one
valid solid.

## Failure handling

A failed call must leave no Hole or cylindrical-cut feature behind. The prior
Body Tip must be restored. Do not retry by cycling blindly through origin
planes, datum planes, `Face1`, and `reversed`; choose the correct workflow from
the geometry.

## Live regression tests

With FreeCAD and the Robust MCP XML-RPC bridge running:

```bash
pytest -q tests/integration/test_partdesign_hole.py
```

The module covers circle profiles, point rejection, direction rollback, sketch
reuse, datum-plane rejection, and the explicit-axis cylindrical-cut fallback.
