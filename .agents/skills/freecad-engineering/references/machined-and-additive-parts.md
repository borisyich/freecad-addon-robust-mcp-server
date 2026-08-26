# Model machined/material-removal and additive parts

Use this reference for volumetric parts whose dominant manufacturing logic is
material removal, turning/milling/drilling, or additive manufacturing. It is the
manufacturing-strategy layer and should be combined with the appropriate input
reference (`model-from-text.md` or `model-from-drawing.md`).

## 1. Classify the dominant process

### Material removal / machining

Evidence includes planar faces, pockets, slots, drilled/reamed holes, steps,
turned diameters, grooves, keyways, and a plausible stock form.

Typical stock candidates:

- rectangular block/plate/flat bar;
- round bar/tube;
- hex bar;
- extrusion/profile;
- casting/forging/preform when clearly implied.

### Additive

Evidence includes topology that is not naturally stock-driven, internal or
organic geometry, lattice-like features, topology-optimized forms, or an
explicit additive requirement.

### Hybrid

Treat turned+milled, cast+machined, printed+finish-machined, and similar parts
as hybrid rather than forcing them into one strategy.

## 2. Machined prismatic parts

Prefer a stock/primary-envelope-first mental model:

1. create the main stock-like or near-net base mass;
2. remove large pockets/steps/through regions;
3. add or preserve bosses/ribs/pads that belong to the near-net form;
4. machine slots and local details;
5. create and verify one repeated seed, then pattern;
6. add holes and bores after the surrounding mass is stable when practical;
7. add final chamfers/fillets.

This order is about robust CAD dependencies, not literal shop routing.

Use pockets/cuts that express the intended removal. Avoid building a complicated
union of small positive blocks when a simple stock minus a few cuts represents
the part more clearly.

## 3. Turned / axisymmetric parts

When most dimensions are diameters and axial lengths:

- choose the rotational axis first;
- build the half-section profile and revolve it when that clearly captures the
  design;
- keep diameters, shoulders, tapers, grooves, and axial lengths in the revolved
  base as long as practical;
- add cross holes, flats, keyways, off-axis pockets, and bolt patterns afterward.

If the revolve is valid but produces the wrong section/envelope because the axis
or profile interpretation was wrong, replace the base strategy. Do not keep a
wrong revolved body and compensate with many patches.

## 4. Cored/cast near-net bodies followed by machining

For housings, flanges, impeller-like bases, webs, or cast/forged shapes:

- construct the main near-net body and primary cavities/webs first;
- fuse bosses/ribs with intentional overlap rather than tangent contact;
- cut shared bores and holes only after the masses they pass through exist;
- keep open windows and air gaps as real topology, not engraved lines on a slab;
- reserve finishing radii for the end and re-check interfaces afterward.

## 5. Additive parts

Do not invent subtractive stock merely because PartDesign is feature based.
Start from the intended final material distribution:

- keep the result watertight when a solid part is required;
- use shells/lofts/sweeps/ribs/booleans according to design intent;
- parameterize repeated geometry and wall thickness when they are meaningful;
- do not add manufacturing supports to the engineering model unless requested;
- treat minimum wall, overhang, trapped powder, machining allowance, and build
  orientation as manufacturability checks only when the task or design requires
  them.

## 6. Geometry robustness

- Avoid exactly tangent/coincident positive solids when they are intended to
  fuse; use deliberate overlap where design permits.
- Verify one boolean before stacking many later operations on it.
- After a cut/fuse, check solid count and whether volume/topology changed in the
  expected direction.
- For holes or cylinders, verify axis, diameter/radius, depth, and location from
  semantic geometry rather than face-center guesses.
- After fillets/chamfers, re-check critical bores, mating faces, and repeated
  feature counts.

## Completion checks

- The dominant body construction matches the likely manufacturing family.
- Stock logic is used where it clarifies machining intent, not where it creates
  unnecessary geometry.
- Axisymmetric parts have a stable, correctly oriented rotational base.
- Additive parts are modeled as intended material, not as a fake machining
  sequence.
- Interfaces, bores, pockets, pattern counts, and one-solid expectations are
  verified before finishing.
