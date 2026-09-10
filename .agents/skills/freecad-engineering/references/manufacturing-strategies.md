# Manufacturing strategies and CAD dependencies

Use function, material, quantity, tolerances, available equipment, and source
notes to select plausible processes. Geometry is evidence, not a unique process
identifier. Separate finished geometry from stock and process allowances.

## Compare viable process routes

| Geometry/process evidence | Candidate representation | Manufacturing questions |
|---|---|---|
| Prismatic envelope and accessible removals | Sketch-based additive/subtractive features | Cutter and holder reach, internal radii, workholding, setups, remaining walls |
| Common-axis dimensions | Constrained axial section and Revolution/Groove | Radius versus diameter, axial datum, tool access, chucking, relief and finish |
| Developable panels and bends | Native SheetMetal base/folds/flanges | Thickness, bend definition, neutral rule, tooling/collision, flat/formed domains |
| Drafted or near-net preform | Supplied/parameterized blank and finishing features | Parting direction, cores, draft, shrinkage and machining allowance |
| Welded or assembled members | Separate parts and joining interfaces | Access, locating sequence, distortion, inspection, intended gaps |
| Additive or free-form part | Suitable native solids/surfaces and process metadata | Build direction, support removal, anisotropy, minimum detail, postprocessing |

Unknown or hybrid is a valid classification. Do not turn a visually plausible
route into a production claim. Investigate only manufacturing questions that
affect the requested decision; use actual shop data for numeric process limits.

## Plan from dependencies

Choose datums from functional locating surfaces, symmetry, interfaces, and
inspection needs. A stock-like envelope with removals is useful for subtractive
design, while additive features can express the same finished intent more
clearly in other cases. Keep actual stock allowances separate from nominal size.

Order the feature tree by required parents and stability. Supporting geometry
precedes its dependent sketch; an accepted seed precedes its repetition;
a functional radius can precede a mating or tangent feature. Cosmetic edge
treatments are often late. There is no universal ribs → holes → pockets order.
CAD dependency order need not reproduce machining or press-brake sequence.

For each material addition/removal predict the affected region and topology.
Check intended intersection, remaining thickness and ligament, islands/slivers,
termination, and supported interfaces. A successful cut of the wrong wall is
still a rejected operation.

## Process-specific decisions

**Milling:** group accessible directions and datum relationships into meaningful
features. Check cutter envelope and holder clearance, pocket reach, minimum
inside radius relative to the chosen tool, and clamping access. A sharp inside
corner may require another process or a design relief; do not silently change
source geometry. A B-rep cannot establish chatter or achievable tolerance.

**Turning:** establish spindle axis and axial datum; keep diameter/radius
semantics explicit. Use revolved sections where appropriate, with later
non-axisymmetric features driven by stable datums. Account for internal tool
access and undercuts. Model helical thread geometry only when fidelity requires
it; preserve any existing functional thread unless the edit targets it.

**Sheet metal:** separate flat blank, formed state, and process data. Prefer native
SheetMetal operations when supported; check capabilities before choosing a tool.
Read [sheet-metal-flat-patterns.md](sheet-metal-flat-patterns.md).
A sheet-like envelope does not prove developability or a calibrated bend rule.

**Other processes:** model the requested fidelity, document limitations, and use
verified process data for production decisions. Do not force a casting, welded
assembly, or additive structure into a single machined-block narrative.

## Inspection and handoff

Connect each critical tolerance to an accessible measurement and datum scheme.
Check whether finishing, coating, heat treatment, or assembly changes the relevant
interface. Keep nominal dimensions, allowable variation, and allowances distinct.
Report tool access, sequence, and process assumptions separately from geometric
validity and editability.
