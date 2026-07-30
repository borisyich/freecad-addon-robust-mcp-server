# Sheet-metal flat-pattern reconstruction

## 1. What a flat pattern is

A **flat pattern** (developed blank, development, or unfolding) is the planar
shape of a sheet-metal part before bending. It normally contains:

- the cut perimeter of the blank;
- holes, slots, and cutouts made in the flat state;
- bend lines separating adjacent rigid panels;
- bend direction, angle, and inside-radius annotations;
- thickness and a neutral-axis rule such as K-factor, bend allowance, bend
  deduction, or a bend table.

A flat pattern is a manufacturing representation, not an orthographic camera
view of the formed part. Its overall width and height are blank dimensions and
must not be treated as the final 3D bounding box.

Curved edges in the blank contour are not automatically bends. Distinguish:

- **profile radii**, which shape the planar edge of a panel and remain panel
  boundaries after folding;
- **bend radii**, which belong to a bend line and define the cylindrical
  transition between panels.

## 2. Bend-dominated versus stretch-formed stamping

A flat pattern can be reconstructed directly only when the sheet remains
approximately developable: planar panels connected by cylindrical bend zones.
Simple flanges and press-brake bends normally satisfy this assumption.

Deep drawing, stretch forming, complex embossing, and some stamped ribs change
surface length and thickness over an area. Their production blank depends on
material behavior, tooling, draw beads, trimming, and forming simulation. Do not
apply ordinary K-factor bend equations to those regions or claim an exact
manufacturing blank without explicit process data.

## 3. Recognizing flat-pattern evidence

Treat a drawing region as a probable flat pattern when several of these are
present:

- one continuous constant-thickness blank shown face-on;
- all holes shown as true circles in the same plane, even though isometric views
  place their final panel normals in different directions;
- straight lines crossing the blank and labelled `BEND UP`, `BEND DOWN`, bend
  angle, or bend radius;
- notes for sheet thickness, bend radius, K-factor/neutral factor, bend
  allowance, or bend deduction;
- a second drawing of the same planar contour used only for ordinate/baseline
  dimensions.

Do not classify repeated drawings of the same flat contour as different formed
orthographic views merely because they occupy different regions of the sheet.
Reconcile contour shape, hole count, hole centers, and bend-line positions
first.

## 4. Separate flat and formed dimension domains

Before modeling, classify every dimension as one of:

1. **flat-domain**: blank perimeter, hole/cutout coordinates, bend-line
   coordinates, or developed lengths;
2. **formed-domain**: final flange height, angle, spacing, or overall envelope
   after bending;
3. **bend/process**: thickness, inside radius, angle, K-factor, allowance,
   deduction, relief, or tooling rule.

Do not mix these domains. In particular:

- do not use a flat overall dimension as a final formed extent;
- do not apply bend allowance a second time when the drawing already provides a
  fully dimensioned flat pattern;
- do not place a hole at the same world coordinates after folding. A hole belongs
  to a panel and its center and axis transform with that panel.

## 5. Build a panel-and-bend graph

Convert the flat pattern into a topological plan before creating 3D geometry.

### Panel table

For each region between bend lines record:

| Field | Meaning |
|---|---|
| panel ID | stable name such as `Base`, `Web`, `Flange_A` |
| flat boundary | contour segments and adjacent bend lines |
| thickness | nominal sheet thickness |
| attached features | holes, slots, cutouts, reliefs |
| final normal | expected panel normal from formed views |
| evidence | flat-pattern region and formed/isometric view |

### Bend table

For every bend record:

| Field | Meaning |
|---|---|
| bend ID | stable name such as `B1` |
| bend axis | line endpoints/direction in flat coordinates |
| adjacent panels | fixed/parent panel and moving/child panel |
| direction | up/down relative to the chosen flat-pattern face normal |
| angle | included bend angle, normally explicit |
| inside radius | local value or drawing default |
| neutral rule | K-factor, allowance, deduction, or table |
| expected result | child-panel final normal and position |

`BEND UP` and `BEND DOWN` are relative to the viewed face of the flat pattern,
not inherently to global FreeCAD `+Z` and `-Z`. Explicitly choose a flat-pattern
plane and a positive face normal, then map every callout to a signed rotation.
Also state which side of each bend is fixed; rotating the opposite side produces
a different model even with the same sign and angle.

The graph should be connected and acyclic for a simple flange chain. If a panel
can be reached through conflicting bend paths, stop and resolve the
interpretation before modeling.

## 6. Neutral-axis and developed-length reasoning

For the common K-factor convention measured from the inside surface:

```text
neutral radius Rn = Ri + K * t
bend allowance BA = theta * (Ri + K * t)
```

where `Ri` is inside bend radius, `t` is sheet thickness, `K` is the neutral
factor, and `theta` is bend angle in radians.

When deriving a flat length from formed outside dimensions, a common geometric
relation is:

```text
setback SB = (Ri + t) * tan(theta / 2)
bend deduction BD = 2 * SB - BA
```

Use these equations only when their dimension convention matches the drawing.
Bend tables or explicit drawing values override generic formulas. Different CAD
systems and shops may define flange dimensions and K-factor conventions
differently.

When an explicit, dimensioned flat pattern is supplied, use its perimeter,
hole locations, and bend-line locations directly. Use `t`, `Ri`, angle, and `K`
to create/validate the bend region—not to re-shorten or re-length the already
defined blank.

## 7. Preferred FreeCAD construction strategy

### Dedicated sheet-metal capability available

1. Use `workbench(action="list")` to determine whether an appropriate
   sheet-metal workbench is installed.
2. Prefer a base-wall/fold workflow that preserves sheet-metal semantics and can
   produce both formed and unfolded states.
3. For a drawing whose flat blank is explicit, prefer folding that blank along
   its bend lines rather than independently guessing flange lengths from the
   isometric view.
4. The current MCP surface may not expose dedicated sheet-metal operations. Use
   `execute_python`, `safe_execute`, or a tested macro only because the required
   semantic operation is unavailable as a standard MCP tool.

### Dedicated capability unavailable

For simple straight bends, construct a documented constant-thickness formed
state:

- create each planar panel from its flat region transformed by the accumulated
  parent bends;
- connect adjacent panels with a tangent cylindrical bend zone using the stated
  inside radius and thickness;
- fuse the regions into one valid solid;
- transform each panel's holes/cutouts with the panel and cut them normal to the
  final panel surface;
- keep bend parameters and panel transforms explicit and named.

A useful 90-degree bend fallback is a constant-thickness quarter-annular
cross-section extruded along the bend axis and tangent to both panel solids.
This is superior to intersecting unrelated rectangular prisms, but it is still
not a native unfoldable sheet-metal feature. Report that limitation.

Never claim a manufacturing-correct flat pattern from a formed-state fallback
unless an actual unfold operation reproduces the supplied blank.

## 8. Fold planning and verification

Choose the largest functional mounting panel as the usual anchor. Traverse the
panel graph outward from it. For each bend:

1. preserve the parent panel;
2. rotate the child panel about the recorded bend axis by the signed angle;
3. create or update the bend zone;
4. recompute and inspect continuity, thickness, and solid count;
5. verify the child-panel normal and silhouette against the formed/isometric
   evidence before continuing.

The reconstruction order is a dependency order, not necessarily the press-brake
manufacturing sequence. Determine an actual shop-floor bend sequence only when
requested, because tool access and collision avoidance may impose another order.

## 9. Required sheet-metal checks

Before completion verify:

- one continuous solid with nominal constant thickness;
- correct number of panels and bends;
- each bend axis, direction, angle, and inside radius;
- correct distinction between profile radii and bend radii;
- holes/cutouts remain attached to the correct panels and their axes match final
  panel normals;
- no panel overlap, self-intersection, gap, or missing bend relief;
- formed views agree with the reference isometrics/orthographic views;
- when native unfolding is available, the unfolded result agrees with the
  supplied flat contour, bend lines, and feature locations.

If only a formed-state approximation was produced, report that flat-pattern
manufacturability and bend allowance were not independently validated.
