# Model bent and formed sheet-metal parts

Use this workflow for parts dominated by approximately constant sheet thickness,
planar panels, bends, flanges, hems, tabs, reliefs, beads, dimples, louvers, or a
flat/developed blank.

## 1. Confirm that the part is actually sheet metal

Strong evidence:

- near-constant thickness;
- panels connected by bend radii;
- bend angle/radius notes;
- flat pattern/developed blank;
- bend lines or bend-direction symbols;
- sheet gauge/material and formed dimensions.

Do not force deep-drawn or heavily stretched stampings into a pure bend model.
If thickness remains roughly constant but surface area changes materially through
stretch forming, record that the simple panel+bend abstraction may be
insufficient.

## 2. Separate flat and formed geometry

A flat pattern and the final part are related but are not interchangeable views.
Maintain two domains:

- **flat domain:** blank outline, cutouts, bend lines, developed distances;
- **formed domain:** panel positions, bend angles, flange heights, final envelope.

Never treat a dimension across a bend in the formed part as though it were a
straight flat-pattern distance without accounting for bend development.

## 3. Build a panel-and-bend plan

Before modeling, identify:

- base/fixed panel;
- connected moving panels/flanges;
- bend axes;
- bend direction;
- bend angle;
- inside radius when known;
- thickness;
- relief/corner treatment;
- formed features that are not simple bends.

Choose the fixed panel so the largest and most dimensionally stable portion of
the part remains stationary while other panels fold from it.

## 4. Prefer dedicated sheet-metal features

Call `sheet_metal_capabilities` before choosing a native SheetMetal construction
when the installed workbench/version is not already known. Use
`create_sheet_metal_base`, `create_sheet_metal_feature`,
`inspect_sheet_metal`, and `unfold_sheet_metal` when they express the required
geometry.

Model the sheet as sheet metal rather than a thick block with pockets when the
part is clearly bend dominated. Use ordinary PartDesign only for features the
sheet-metal workflow cannot represent reliably.

## 5. Bend-development reasoning

When a flat pattern must be reconstructed or validated, relate developed length
to thickness, inside radius, bend angle, and neutral-axis/K-factor assumptions.
Do not invent a K-factor when the drawing already provides the developed blank;
the blank itself is stronger evidence.

For the common K-factor convention measured from the inside surface:

```text
neutral radius Rn = Ri + K * t
bend allowance BA = theta * (Ri + K * t)
```

where `Ri` is inside radius, `t` is thickness, and `theta` is the bend angle in
radians. Use the drawing/shop convention when it differs; an explicit developed
blank or bend table is stronger evidence than a generic K-factor formula.

If both flat and formed dimensions are given, use them to cross-check bend
interpretation. A systematic mismatch usually indicates wrong fixed panel, bend
direction, inside/outside radius interpretation, or bend allowance—not a reason
to distort unrelated panel dimensions.

## 6. Feature order

A robust modeling order is:

1. base sheet/blank or fixed panel;
2. primary bends/flanges;
3. secondary bends/hems;
4. formed features such as beads/dimples/louvers when supported;
5. cutouts/holes according to which state defines their location most clearly;
6. corner reliefs and finishing details;
7. unfold and inspect.

If the drawing defines a hole in the flat pattern, it may be most naturally
created before folding. If its functional location is dimensioned on the formed
part, creating/verifying it after the bend can be safer. The final geometry and
flat/formed correspondence matter more than a universal holes-first/last rule.

## 7. Verification

After every important bend:

- recompute;
- inspect sheet thickness and sheet-metal state;
- verify panel orientation and bend direction;
- compare the equivalent drawing view when modeling from a drawing.

At the end:

- unfold the part when supported;
- compare the unfolded outline and bend layout to any supplied flat pattern;
- check that thickness is consistent and that the result is one intended sheet
  body;
- verify holes/cutouts near bends for unexpected deformation or relocation.

## Completion checks

- The part is represented as a sheet with bends/forming, not as an arbitrary
  block approximation.
- Flat and formed dimensions have not been mixed without bend reasoning.
- Bend direction, angle, radius, fixed panel, and flange orientation are
  consistent with the source.
- Unfolded geometry is checked when the workflow supports it.
- Limitations for deep-drawn/stretch-formed geometry are explicitly reported.
