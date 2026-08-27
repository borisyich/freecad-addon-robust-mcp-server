# Agent modeling patterns

The canonical modeling guidance is the repository Skill:

```text
.agents/skills/freecad-engineering/SKILL.md
```

Codex can activate it as `$freecad-engineering`. MCP clients can read the same
text from:

```text
freecad://skills/freecad-engineering
```

## Core pattern

Before selecting a base feature, classify:

- likely stock: plate/block, sheet, round/tube, hex, profile, preform, or hybrid;
- dominant process: milling, turning, sheet-metal bending/forming, or hybrid.

The classification should guide the model history:

- prismatic machined parts commonly start from an additive base or a stock-like
  block followed by progressive removals;
- turned parts commonly start from a constrained half-profile and Revolution;
- sheet-metal parts require constant nominal thickness, connected panels/bends,
  and explicit treatment of bend radius/allowance assumptions.

Use stable datums, constrained sketches, semantic PartDesign features, and a
feature order that preserves design intent. Holes, patterns, small details, and
edge treatments should normally be delayed until the supporting form is stable.

Use `select_subshapes` before face-supported sketches, Fillet/Chamfer/Draft/Thickness operations, and topology measurements; inspect the returned semantic records before consuming the `FaceN`/`EdgeN`/`VertexN` references.

For drawing/sketch input, extract and save every explicit dimension before
modeling, preserving drafting markers rather than using them as exclusion rules.
Give each value a stable identifier, source view, and semantic target. Classify
it as `driving` or `verification`: only driving dimensions must become named
constraints or connected Spreadsheet aliases, while both classes must be
measured against the same semantic elements in the reproduced source-view
context.

## Verification

Use lightweight checks proportional to risk rather than a mandatory state
machine after every operation:

- `get_sketch_info` for sketch solver/profile state;
- `validate_object` and `validate_document` for geometry health;
- `compare_images` after every major feature in drawing reconstruction; a saved
  screenshot alone is not a completed visual checkpoint;
- comparison of one accepted seed element before any pattern operation;
- a complete drawing view manifest containing every source view/detail/section,
  with standard camera/plane mappings where applicable and explicit recipes for
  non-standard cameras or sections;
- feature-relevant same-view checks during modeling and exhaustive one-to-one
  comparison of every source-view manifest record before final acceptance;
- `validate_parametric_model(required_dimension_names=[...])` for the mandatory
  final structural report when a source dimension inventory exists.

The validator is informative. It reports actual Bodies, Tips, history, sketches,
constraints, and direct solids, but does not prove that the model matches a
reference drawing or is manufacturable. It also reports required source
dimensions that are missing/unlinked and Spreadsheet aliases that do not connect
directly or transitively to the feature tree.
