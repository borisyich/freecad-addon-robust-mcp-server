# From function to verified design

Use this reference for new design and changes whose consequences extend beyond
shape reconstruction. Keep the contract proportional to the deliverable.

## Define the problem before choosing geometry

Describe the component's function and its interfaces: what it locates, carries,
transmits, guides, seals, contains, or protects. Establish load cases and supports,
permitted motion, installation envelope, operating environment, and service life
when they determine the design. Material, process, production quantity, available
stock, assembly order, access for tools, and inspection constrain possible solutions.
Do not infer these values from a render. Keep unknowns explicit.

Separate hard acceptance requirements from preferences such as mass, cost, setup
count, or appearance. A reconstruction task is controlled by its source; a design
task may compare alternatives. Consider materially different concepts when the
tradeoff matters, and reject candidates against hard constraints before ranking
preferences. Do not assign invented weighted scores to missing engineering data.

For each consequential choice record:
source → assumption/model → prediction → measurement or calculation → decision.
An assumption has an impact and a revision trigger, not merely a confidence label.

## Datums, loads, tolerances, and manufacturing meet at interfaces

Choose datums from function and explain which degrees of freedom each interface
constrains. Model component placements and insertion/removal paths explicitly.
Static non-interference does not establish an assembly path or tool clearance.

Use nominal geometry for design and separate tolerances, stock allowances,
coatings, finish, and heat treatment in the specification. Evaluate interfaces at
relevant limits. For independent dimensional intervals with diametral clearance
C = D_bore - D_shaft:

- C_min = D_bore_min - D_shaft_max;
- C_max = D_bore_max - D_shaft_min.

Use the actual signs and correlations for a datum chain. Do not use statistical
root-sum-square tolerances unless distribution and independence assumptions are
supported. A positive nominal clearance can coexist with worst-case interference.
Choose inspection datums and measurable targets that match the specification.

## Calculation is a model with a domain

Trace applied forces and reactions through contacts and section changes.
Choose checks for the relevant mechanism: stress, deflection, buckling, fatigue,
contact, thermal expansion, vibration, or stability. Record units, boundary
conditions, material properties and their provenance, geometry idealization,
and acceptance limits. Perform dimensional and order-of-magnitude checks.

Use an independent hand calculation, limiting case, or experiment to challenge a
simulation result. Mesh convergence alone cannot validate wrong loads or contacts.
Do not invent a universal safety factor, material allowable, fit, or minimum
wall thickness. Use supplied criteria or an applicable, checked technical source.
A shape-valid result establishes neither service performance nor process capability.

## Verify response as well as the current state

For intended editable relations, perturb a meaningful driver within its supported
range in a disposable copy or reversible transaction. Predict which quantities
move and which remain fixed. Measure actual geometry at more than one value,
including near a relevant limit, then restore and verify the original state.
Preserve expressions, names, dependencies, and object placements during restoration.

This detects a frozen coordinate that happens to agree at the nominal value, a
wrong driving owner, or a solver branch flip. An expression or dependency path is
structural evidence, not proof of the correct response. A failing perturbation may
indicate a domain boundary; record the supported range rather than demanding all
parameters work for arbitrary values.

## Evidence and acceptance

Choose independent evidence for each failure mode. Local dimensions reveal
interface motion; section geometry exposes hidden walls; exact differences
localize changes; solver diagnostics expose constraint errors; manufacturing
review checks access and sequence. Several summaries derived from the same B-rep
are correlated and do not replace a source or functional check.

Set numeric acceptance bounds in the dimension's units before seeing results.
Separate engineering tolerance, source resolution, and computational uncertainty.
Use combined absolute/relative tolerances where justified by measurement scale,
not an arbitrary percentage of total part volume for every local feature.
If uncertainty straddles a limit, refine the measurement or report indeterminate.
Do not widen tolerances after failure merely to obtain acceptance.
