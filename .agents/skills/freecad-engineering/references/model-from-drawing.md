# Model or reconstruct a part from a technical drawing

Use this workflow when geometry must be inferred from orthographic, sectional,
isometric, detail, auxiliary, or flat-pattern views.

## Goal

Reconstruct one coherent 3D part from source evidence. A valid solid and a
plausible isometric render are not enough: dimensions, view relationships,
sections, feature counts, interfaces, and topology must agree with the drawing.

## 1. Build drawing memory before geometry

Do not model while informally reading the sheet. Create a compact drawing record
that remains available throughout the task. It has four linked parts:

1. **source-region index** — whole sheet, each view/detail/section, and the exact
   crop or tile where evidence was read;
2. **view map** — identified view, projection plane, viewing normal, orientation,
   and what that view can and cannot prove;
3. **dimension/requirement ledger** — every explicit source value or count with a
   stable ID, role, datum, target, and status;
4. **feature plan** — dominant form, positive masses, negative volumes,
   interfaces, repeated features, and finishing details in dependency order.

Keep an assumption/discrepancy list beside the record. After every accepted
checkpoint, mark which feature and dimension IDs are satisfied and what remains.
This record is the agent's memory; do not rely on a remembered visual impression.

## 2. Inspect the source at two resolutions

Start with `open_image` on the whole sheet to identify:

- units, scale, projection symbol, notes, and tolerances;
- principal/front, top/plan, left/right side, section, detail, auxiliary,
  isometric, and flat-pattern views;
- centerlines, hidden lines, section hatching, symmetry, datums, and repeated
  feature notes;
- all regions that need higher-resolution inspection.

Then use `open_image_tiles` or focused crops for dense dimensions and small
features. Record the source path plus tile/crop identifier for every ledger item.
Inspect overlapping neighbor tiles for features crossing a crop boundary. Reopen
the whole-sheet overview whenever local crops make the global view relationship
unclear.

Printed dimension values are authoritative. Do not infer a real dimension from
pixel length when a callout exists, and do not multiply a printed value by the
drawing scale. Pixels can support topology and relative layout, not replace a
missing dimension with false precision.

## 3. Establish the view ↔ model-axis contract

Determine the projection convention from the symbol and cross-view evidence.
Do not classify a view only by its page position: benchmark and non-standard
drawings may deliberately depart from normal layout.

Default FreeCAD orthographic contract used by this project:

| Drawing/FreeCAD view | Screen plane | Viewing normal | Typical sketch plane |
|---|---|---|---|
| Front/Rear | XZ | +Y / -Y | `XZ_Plane` |
| Top/Bottom | XY | +Z / -Z | `XY_Plane` |
| Left/Right | YZ | +X / -X | `YZ_Plane` |
| Isometric | none | none | verification only |

The exact sign depends on camera direction. Record it once and keep it consistent.
Use `get_camera_state` when a custom view is needed. With
`set_camera_position`, use orthographic projection and record `look_at`,
`up_direction`, and view direction; do not silently accept a tilted candidate.

### Circle/axis rule

A circular feature appears circular only when viewed approximately along its
axis. Therefore:

- circle in Front/Rear → profile in XZ, axis along Y;
- circle in Top/Bottom → profile in XY, axis along Z;
- circle in Left/Right → profile in YZ, axis along X.

Cross-check the inferred axis with hidden lines, a section, or another view.
This prevents a visually plausible cylinder rotated by 90 degrees.

For each source region, record a view-map row such as:

| Region | View | Plane/normal | Proves | Does not prove |
|---|---|---|---|---|
| V1 | front | XZ / Y | height, X location, profile | Y depth |
| V2 | side | YZ / X | depth, Z profile, circular true shape | X thickness |
| S-A | section | stated cut plane | material/void and wall sequence | uncut exterior detail |

## 4. Decompose the part before choosing operations

Describe the drawing as a feature graph rather than one silhouette:

- **dominant form:** prismatic, revolved, cored housing, spoked/ribbed,
  thin-walled, sheet metal, lofted/freeform, or hybrid;
- **positive masses:** base, hub, rim, flange, boss, rib, spoke, lug, foot, pad;
- **negative volumes:** bore, through hole, blind pocket, slot, window, groove,
  relief, counterbore/countersink;
- **functional interfaces:** mounting faces, bores, seats, hole patterns, mating
  outlines, datums;
- **repetition:** seed identity, count, pitch/angle, center/axis, symmetry;
- **finishing:** fillets, chamfers, rounds, draft, and small reliefs.

For every major feature, cross-check at least two independent sources when they
exist: silhouette plus depth view, circle plus hidden lines, section plus exterior
view, or pattern note plus visible count. A section overrides a tempting exterior
interpretation: hatching means retained material; an unhatched cavity/void is not
material merely because the outer silhouette is closed.

Record each planned feature with:

- stable feature ID and semantic name;
- parent/base feature and additive/subtractive/forming operation;
- source regions and dimension IDs;
- sketch/datum plane and operation axis/sign;
- expected envelope, volume/topology, and view changes;
- deterministic and visual checks required for acceptance.

Do not start a feature whose profile plane, depth source, or material/void role is
still implicit.

## 5. Build a source-dimension ledger

Record every explicit non-reference drawing dimension with a stable identifier.
Do not silently omit a value because it looks redundant or conflicts with the
current hypothesis.

Classify each item as:

- **driving** — implemented by a named constraint, property, or connected
  Spreadsheet expression that affects final geometry;
- **verification** — deliberately not a driver, but measured on the solved model;
- **unresolved** — evidence cannot yet be reconciled;
- **out-of-scope** — only when the user explicitly excludes that requirement.

A useful row contains: ID, value/unit, symbol type (diameter/radius/angle/etc.),
source region, datum/reference, target feature, controlled axis/plane, signed
direction, role, tolerance, implementation path, observed value, and pass/fail.

For ordinate/baseline dimensions, a value without datum, axis, sign, and target
is incomplete. Before converting ordinates to world coordinates, close at least
one signed chain from datum through an intermediate feature to an overall/check
dimension. If it does not close within drawing precision, record a
`dimension_chain_mismatch` and revisit the view/datum interpretation; do not
average conflicting values.

Do not satisfy the validator by adding disconnected Spreadsheet values,
construction-only geometry, dummy constraints, or zero-multiplied expressions.

## 6. Construct source-derived sketches deliberately

For a manufactured profile, build and accept feature groups in this order when
applicable: straight parent segments, stated radius transitions, holes/internal
cutouts, construction/bend lines, then final parameterization.

- Apply `Horizontal`, `Vertical`, `Coincident`, `Tangent`, `Equal`, symmetry,
  and datum relationships before adding the smallest sufficient driving
  dimension set.
- Classify each point-to-origin coordinate as `source_backed`, `derived` from a
  closed dimension chain, or `solver_lock`. Minimize solver locks; 0 DoF obtained
  from arbitrary endpoint coordinates does not encode design intent.
- Construct a specified fillet from its straight parents using tangent/radius
  semantics. If adding Tangent conflicts, treat the current endpoint/radius/arc
  side/datum interpretation as suspect; do not delete tangency merely to keep a
  visually convenient arc.
- Use a B-spline only when the source explicitly defines a free-form curve by
  points/knots or equivalent data. Never substitute one for a line, circular arc,
  conic, stated radius, or unreadable boundary.
- For a closed profile, verify outer/hole nesting, expected wire counts, no
  intersections/overlaps/T-connections, and construction geometry exclusion.
  `fully_constrained` and `closed_wire_count` alone do not prove profile validity.

After each sketch feature group, run deterministic dimensions and same-view
comparison before adding the next group. Reach final constraint completeness only
after topology and source correspondence are accepted.

## 7. Model and check the dominant form first

Choose the manufacturing/body strategy from the feature plan and the applicable
manufacturing reference. Build only enough to establish the principal material
distribution, outer envelope, main cavity, and axis system.

At the first valid dominant-form candidate:

1. measure the overall X/Y/Z envelope and major section-defining dimensions;
2. inspect solid count, volume plausibility, Body Tip, and main sketch/profile;
3. render the principal orthographic views and one isometric view;
4. name the largest semantic mismatch against the drawing;
5. rebuild the base strategy if the mismatch is body-family level.

Do not repair a solid slab that should be a cored housing, a filled disk that
should be spoked, or a wrong-axis revolve with cosmetic pockets and fillets.

## 8. Drawing reconstruction feedback loop

Use checkpoints after the dominant form and after each major feature or coherent
feature group. Before every ACT:

1. reopen the exact source crop/tile for the current feature;
2. reread its feature-plan row and dimension IDs;
3. state the expected numerical, topological, and visible change.

After recompute, OBSERVE in this order:

1. tool result and FreeCAD errors;
2. shape validity, solid count, Body Tip, and sketch solver/profile state;
3. direct measurements: envelope, center/axis, radius/diameter, depth, thickness,
   angle, count, spacing, or volume delta appropriate to the feature;
4. section evidence for internal geometry (`section_shape`, targeted inspection,
   or a reproducible section screenshot) when an exterior view cannot prove it;
5. same-view visual comparison.

For the visual check:

- isolate the intended result and hide helpers that are not part of the source;
- set the candidate to the matching orthographic/custom view explicitly;
- crop the drawing to the corresponding view; never compare a full sheet with
  one model screenshot;
- call `compare_images` with an explicit `view_context` and `doc_name` so the
  evidence is tied to the current document geometry signature;
- inspect silhouette/aspect ratio, feature count, centers/spacing, visible depth,
  axis direction, openings, and material/void boundaries.

`compare_images` only presents two images together. It does not register them,
read dimensions, segment features, or compute CAD correctness. Treat it as one
qualitative observation beside deterministic evidence, not as a score.

Write the checkpoint result: expected, observed, evidence, discrepancies, and
decision `continue` or `rework`. Rework the causal feature before proceeding.

### Multi-view escalation

A match in one projection does not prove depth, hidden geometry, or feature-axis
orientation. When the current pair is ambiguous or the feature affects several
views, compare every available relevant projection:

1. principal/front;
2. matching left or right side;
3. top;
4. section/detail for internal geometry;
5. isometric as a spatial sanity check.

Do not accept a feature until those views are mutually consistent.

## 9. Patterns and repeated features

Build and accept one seed first. Verify its size, axis, attachment, and source
position using direct measurements and the relevant drawing view. Only then
create the pattern/mirror/multi-transform.

After patterning, verify count, spacing/angle, center or pitch circle, one-solid
topology, material-change evidence, and the complete layout. A correct count with
merged, missing, or wrongly oriented instances is not success.

## 10. Flat patterns

A developed blank is manufacturing evidence, not another orthographic view. If
the drawing contains one, also read `sheet-metal-parts.md`. Keep flat-domain and
formed-domain dimensions separate and reconcile them through the bend model.

## 11. Ambiguity and revision policy

Resolve low-risk ambiguity with the interpretation that best satisfies all
views, dimensions, sections, symmetry, and manufacturing logic. Record the
assumption and make it reversible.

When a later observation conflicts, revise the evidence record as well as the
CAD: view identity, datum, sign, endpoints, radius side, feature type, or
dimension role may be wrong. Preserve the rejected interpretation and reason so
it is not rediscovered. Request clarification only when conflicting or missing
critical evidence prevents a meaningful reconstruction.

## Completion checks

- Every source view has a consistent plane/normal mapping.
- Every major visible or sectioned feature appears in the feature plan and final
  model, or is explicitly unresolved/out-of-scope.
- Every explicit source dimension is driving, verification, unresolved, or
  explicitly out-of-scope; none is silently omitted.
- Every driving ID truly influences final geometry.
- Every verification dimension has measured pass/fail evidence.
- Major silhouettes, sections, feature counts, axes, openings, and interfaces
  agree across all relevant views.
- The final discrepancy list contains no unresolved blocking mismatch.
- A final same-view comparison was recorded after the last geometry change;
  earlier comparison evidence is repeated if the validator reports it stale.
- `validate_parametric_model(required_dimension_names=[...])` is run with the
  complete driving-ID list and its findings are reconciled with the drawing
  record.
