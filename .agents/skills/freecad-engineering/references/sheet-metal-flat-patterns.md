# Sheet-metal flat and formed representations

## Establish the deformation model

Separate blank-domain dimensions, formed-domain dimensions, and bend/process
parameters. A dimensioned flat blank defines its own cut perimeter and features;
do not apply bend compensation a second time. Curved blank edges are profile
geometry, not evidence of curved bend axes.

Planar panels with developable bends can use ordinary sheet-metal models.
Stretch forming, deep drawing, embossing, and nondevelopable regions may alter
surface length and thickness. Their production blank depends on material,
tooling, and process data; a constant-thickness visual approximation does not
establish an accurate blank.

## Panel and bend graph

For each panel record flat boundary, thickness, owned holes/cutouts, functional
datum, and expected final pose. For each bend record axis, fixed/moving panels,
signed rotation, inside radius, angle convention, bend-zone limits, and neutral
rule. Up/down is relative to the viewed blank face. Choose its normal explicitly.

Differentiate the **rotation from the flat state** from the **included angle
between flanges**. In a simple bend these can be supplementary. Do not feed
an included angle into a sweep/allowance formula without conversion.
Check the actual tool's angle and flange-length conventions.

Use dependency traversal from a functional anchor; largest area is not itself a
datum requirement. A simple flange chain is a tree. Cycles may represent seams,
closures, or constrained panel systems: resolve their closure and manufacturing
interpretation instead of silently discarding a connection.

Finite-radius bending includes bend-zone allowance and tangent offsets as well
as rigid-panel rotations. Simply rotating a panel around a drawn line can place
its tangent boundaries incorrectly. Verify panel poses, bend tangent locations,
and owned feature positions after the native operation.

## Neutral axis and process limits

For K measured as neutral-axis offset divided by thickness from the inside face:

```text
Rn = Ri + K * t
BA = theta * Rn
```

Here theta is sweep from flat in radians. For a compatible simple outside
flange-length convention, away from a folded hem singularity:

```text
SB = (Ri + t) * tan(theta / 2)
BD = 2 * SB - BA
```

Use the actual dimension convention and supported range. These formulas are not
general hem or stretch-forming models. Bend tables or explicit allowances take
precedence. Confirm the K convention (including ANSI/DIN interpretation) at the
tool boundary. Calibrated material/thickness/tooling data determine production
values; a guessed K-factor is only a declared modeling assumption.

## FreeCAD workflow

Check `sheet_metal_capabilities`. Choose `create_sheet_metal_base` and native
`create_sheet_metal_feature` operations matching the intended base, fold,
flange, relief, or other supported feature. Resolve topology through
`select_subshapes`; use the current intended Tip as the next base in a linear
Body workflow.

Put blank-owned cutouts in the flat profile when they must move with panels.
Post-form machined features belong in the appropriate later dependency stage.
Neither all-holes-first nor all-holes-last is universal. Preserve panel ownership,
tool access, and the representation that supplies each dimension.

After meaningful bends inspect thickness, continuity, overlap, local relief,
normals, placement, and expected solids. A direction check without tangent-offset
and feature-location checks is incomplete. CAD dependency order does not establish
a feasible press-brake sequence or collision-free tooling.

Use compact `inspect_sheet_metal`, then `detail_level="candidates"` for a
stationary face. Unfold the current intended shape with `unfold_sheet_metal`
and an explicit supported neutral-axis source. Compare the blank outline, bend
locations, holes, and dimensions against the supplied flat representation.
`verification_only=True` avoids persisting temporary unfold helpers; keep
an exportable/editable Unfold when it is a requested deliverable.

If required native capability is absent, a scoped script may construct supported
native objects. Otherwise an explicitly limited formed approximation can use
tangent constant-thickness bend sectors and panel geometry with correctly
allocated bend zones. It does not acquire native unfolding or calibrated
manufacturability merely because fusion is valid.

## Acceptance

Verify supplied formed views and flat views in their own domains. Check
thickness where relevant, bend count/radii/signed sweeps, tangent locations,
panel connectivity, local clearances, reliefs, and panel-owned feature poses.
A numerical unfold round trip verifies the chosen geometric rule; physical
bend accuracy still needs process calibration. Report those evidence levels
separately.
