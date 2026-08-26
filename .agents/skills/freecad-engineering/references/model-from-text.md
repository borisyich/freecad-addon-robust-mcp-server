# Model a part from textual requirements

Use this workflow when the primary source is prose, a dimension list, a table,
or a verbal change specification rather than a technical drawing.

## Goal

Turn textual requirements into an explicit engineering specification first,
then build the simplest editable model that represents that specification.

## 1. Normalize the request before modeling

Extract a compact requirement table containing:

- overall envelope and units;
- functional datums or symmetry axes;
- main body form;
- holes, pockets, slots, bosses, ribs, grooves, flanges, bends, or other
  features;
- dimensions and tolerances that affect geometry;
- repeated-feature counts and spacing;
- manufacturing clues;
- ambiguous or missing values.

Separate three kinds of values:

- **explicit** — stated by the user;
- **derived** — follows uniquely from explicit dimensions or symmetry;
- **assumed** — needed to construct the model but not specified.

Do not silently promote an assumption into a user requirement.

## 2. Determine the dominant body family

Before selecting tools, classify the main form. Typical families include:

- prismatic/block/plate;
- axisymmetric/turned;
- thin-walled housing or shell;
- ribbed/spoked/cored body;
- sheet-metal folded body;
- freeform/lofted body;
- hybrid.

Build the dominant form first. If the first valid model is the wrong body family,
replace the base strategy instead of patching it with local cuts and fillets.

## 3. Choose stable datums and parameters

- Put the primary functional/symmetry datum on an origin plane or stable datum.
- Center symmetric geometry when that simplifies later edits or patterns.
- Create named sketch dimensions or Spreadsheet aliases for values reused by
  several features.
- Derive dependent positions from those parameters instead of copying numeric
  coordinates into multiple features.

## 4. Build in dependency order

A robust default sequence is:

1. base mass or primary shell/profile;
2. major cavities and section-defining cuts;
3. bosses, ribs, flanges, steps, or secondary masses;
4. one seed of every repeated feature;
5. patterns/mirrors;
6. holes and local machining details;
7. finishing fillets/chamfers.

Change the order when geometry dependencies require it; do not treat the list as
a rigid recipe.

## 5. Verify against the text, not against your own model

After each major feature, compare the observed state to the requirement table:

- required count exists;
- required dimension is measured from the intended datum;
- feature is on the correct side/axis/plane;
- solid remains connected when it should be one part;
- no helper solid is accidentally visible in the final result.

For a repeated feature, verify the seed before creating the pattern and verify
the final instance count afterward.

## 6. Handling ambiguity

Choose an assumption autonomously when it is low risk and geometrically
conventional. Record it in the final report.

If an unspecified value changes function or creates distinct plausible designs,
prefer a reversible, explicitly recorded assumption when useful work can still
continue. Request clarification only when the task cannot meaningfully proceed, for
example:

- through hole vs blind hole;
- inside vs outside bend radius when both are plausible;
- mating-interface diameter;
- critical wall thickness;
- first-angle vs third-angle interpretation when a supplied view set cannot be
  reconciled otherwise.

## Completion checks

- The model implements every explicit textual requirement.
- Derived values are traceable to explicit requirements.
- Assumptions are few and disclosed.
- The feature tree expresses the intended design rather than only the final
  silhouette.
- Final `validate_parametric_model` findings are reviewed and summarized.
