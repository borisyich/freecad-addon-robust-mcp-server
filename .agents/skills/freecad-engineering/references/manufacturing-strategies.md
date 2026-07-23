# Manufacturing-oriented modeling strategies

This reference guides the choice of stock-like base geometry and feature order.
It does not replace a process plan, tolerance analysis, tooling review, or
manufacturing approval.

## Classification evidence

Use drawing and geometry evidence rather than the part name alone.

| Evidence | Likely stock/process | Modeling consequence |
|---|---|---|
| Large planar faces, orthogonal steps, pockets, slots | Plate/block; milling | Stock-like pad or block, then subtractive features |
| Dominant common axis, multiple diameters and axial lengths | Round/hex bar or tube; turning | Constrained half-profile and Revolution |
| Constant thickness, panels, bend radii/angles, flanges | Sheet; bending/forming | Base panel plus connected flanges/bends |
| Axial body plus flats/cross-holes | Turn-mill hybrid | Revolved base first, then non-axisymmetric features |
| Rough organic envelope, draft, machining allowances | Casting/forging/preform | Represent/import blank, then machining features |

## Milling strategy

### Simple prismatic design

Use a base sketch and Pad when the part's design intent is naturally expressed as
one profile with a small number of added/removed features. Examples include a
mounting plate, simple bracket, spacer, or prismatic support.

1. Choose the principal datum plane.
2. Create a constrained base profile.
3. Pad symmetrically when the center plane is a useful design datum.
4. Add structural bosses/walls/ribs that belong to the main envelope.
5. Add primary pockets/slots/bores.
6. Add repeated holes/patterns.
7. Finish with fillets/chamfers.

### Complex machined design

For a geometry dominated by removed material, a stock-like model is easier to
reason about and validate.

1. Create the smallest credible rectangular/plate/profile stock envelope that
   contains the final part.
2. Align stock axes with likely setups and principal drawing datums.
3. Remove large accessible volumes first.
4. Create secondary pockets/slots and side features by setup direction.
5. Add holes after their supporting faces and datums are stable.
6. Add edge treatments last.

Check after each large cut:

- the cut intersects the intended stock;
- removed volume is positive;
- one contiguous solid remains;
- the silhouette changes in the expected view;
- no thin accidental sliver or disconnected island is created.

Do not equate CAD-tree order with exact machine operation order. A stable design
history may group features differently from the CAM setup sequence.

## Turning strategy

### Stock selection

- round bar for solid axisymmetric parts;
- tube for parts dominated by a through bore and approximately constant wall;
- hex bar when flats are supplied by stock or wrenching geometry dominates;
- forging/casting/preform when the drawing or supplied model indicates it.

### Base feature

Use one constrained half-section around a clearly defined centerline. Include
major outer diameters, shoulders, tapers, and axial lengths. Revolve it into the
main body.

For complex parts, use the maximum useful revolved envelope and remove material
with:

- Groove for annular recesses and reliefs;
- revolved subtractive profiles for internal bores/stepped cavities;
- Pocket/Hole for axial or local non-revolved features;
- later milling features for flats, keyways, cross-holes, and bolt patterns.

Validation points:

- all diameter dimensions are interpreted consistently as diameter versus radius;
- the profile does not cross the axis unintentionally;
- the revolution angle and axis are correct;
- internal and external profiles do not self-intersect;
- cross-holes and flats are added only after the rotational base is stable.

Threads should be modeled geometrically only when the task requires thread
geometry. Otherwise preserve nominal thread parameters/annotations without an
expensive helical solid.

## Sheet-metal bending and forming

### Base panel and thickness

Start with the largest functional panel or the panel that best defines the datum
scheme. Establish nominal thickness once and preserve it through connected
features.

### Bends and flanges

A bend is a deformation with an inside radius and a neutral axis. Flat length is
controlled by bend allowance/deduction or K-factor. Therefore:

- do not represent every bend as unrelated intersecting prisms;
- do not use a generic equal-volume add/subtract rule;
- do not claim a manufacturing flat pattern from a crude solid approximation;
- keep adjacent panels connected through a valid bend region;
- check inside radius, bend angle, flange length, reliefs, and bend direction;
- verify there are no overlaps or gaps after multiple bends.

When a dedicated SheetMetal workbench/tool is unavailable, approximate the
formed state with a single constant-thickness solid. State explicitly that bend
allowance and flat-pattern correctness were not validated.

### Formed details

Beads, stiffening ribs, dimples, louvers, joggles, embosses, and local flanges
move material rather than create it. A high-fidelity model should preserve local
thickness and use formed surfaces/thickening or sheet-metal features. An
additive/subtractive approximation is acceptable for visual or envelope purposes
only when:

- it remains one valid solid;
- nominal thickness is not obviously violated;
- the outer and inner surfaces correspond to the drawing;
- the approximation is disclosed.

### Feature order

A useful design-history order is:

1. base panel and thickness;
2. main flanges and bends;
3. structural formed features such as beads/ribs/dimples;
4. cutouts and holes whose final formed positions are known;
5. repeated patterns;
6. corner/bend relief refinements;
7. fillets/chamfers not inherent to the bend definition.

Actual manufacturing may punch holes before bending. The model should preserve
final design intent and, when flat-pattern accuracy matters, use proper sheet
metal parameters rather than imitate shop-floor order with arbitrary booleans.

## General additions often missed

- Distinguish nominal geometry from tolerances, allowances, coatings, and surface
  treatments; do not silently bake all of them into nominal solids.
- Preserve functional datums and interfaces so later dimensional changes do not
  move mating features unexpectedly.
- Use patterns only after verifying the seed feature, count, direction, and
  spacing from explicit evidence.
- Prefer stable origin/datum references to fragile generated-face references,
  subject to current FreeCAD tool limitations.
- Keep helper geometry named, hidden, and clearly separated from the delivered
  part.

## Datum, setup, and stock considerations

The starting envelope should reflect how the part is likely located and held, not
only the final bounding box.

- Separate **nominal finished geometry** from machining allowance. Do not enlarge
  final dimensions merely because stock is larger; represent stock as planning
  context or a named hidden reference when useful.
- Choose primary, secondary, and tertiary datums from functional interfaces and
  stable manufacturing surfaces. Avoid dimension chains that unnecessarily move
  hole patterns or mating faces when one upstream size changes.
- For milling, group major removal directions by plausible setups and tool
  accessibility. Features hidden from every plausible direction are a signal to
  reconsider the interpretation, setup count, or manufacturing classification.
- For turning, keep the spindle axis and axial datum explicit. Distinguish
  diameter dimensions from radius values and preserve chuck-side/front-side
  orientation where it affects shoulders or axial lengths.
- For hybrid parts, stabilize the turned or bent base before adding secondary
  milling features. Cross-holes, flats, and keyways should reference stable axes
  or datum planes, not incidental transient edges.

## Late-detail ordering

For secondary details that do not define the primary envelope, use this default
late order unless dependencies require another sequence:

1. stiffening ribs or formed reinforcements;
2. holes and repeated hole patterns;
3. secondary pockets, local cutouts, and reliefs;
4. fillets and chamfers.

Major pockets that create the principal machined form are not "late details" and
may need to be modeled earlier. Similarly, a functional radius that controls a
later feature may precede it. The objective is a robust dependency tree, not a
blind universal sequence.

## Checks often omitted in drawing reconstruction

- Identify whether dimensions are baseline, ordinate, chain, symmetric, or from
  a common datum before choosing sketch constraints.
- Distinguish through holes, blind holes, counterbores, countersinks, spotfaces,
  threads, and simple cylindrical cuts.
- Preserve hole-axis orientation and termination condition, not only diameter.
- Check wall thickness and minimum remaining material after intersecting pockets,
  bores, and side cuts.
- Treat tolerances, fits, surface finish, coatings, heat treatment, and material
  notes as engineering metadata unless the task explicitly requires geometric
  representation.
- Model standard thread geometry only when explicitly required; otherwise retain
  nominal thread designation and controlling dimensions.
- Verify that patterns use explicit count, pitch/angle, and seed location rather
  than inferred visual regularity.
- Delay topology-sensitive fillets/chamfers until parent geometry is stable, and
  select edges by geometric criteria where tools allow it rather than memorized
  `EdgeN` indices.
