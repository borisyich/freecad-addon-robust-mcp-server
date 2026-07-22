"""Canonical workflow guidance shared by MCP prompts, resources, and tools.

The MCP protocol exposes prompts and resources, but individual clients decide
whether to load them. Client-native instruction files such as ``AGENTS.md`` or
``.clinerules`` therefore remain necessary. This module keeps the server-side
workflow text and checkpoint policy in one place so prompts, resources, and
validation tools use the same terminology.
"""

from __future__ import annotations

from typing import Final

CHECKPOINT_DECISIONS: Final[tuple[str, ...]] = (
    "continue",
    "rework",
)

BLOCKING_DISCREPANCY_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "geometry_invalid",
        "missing_element",
        "extra_element",
        "wrong_count",
        "wrong_dimension",
        "wrong_position",
        "wrong_orientation",
        "wrong_profile",
        "wrong_bend",
        "silhouette_mismatch",
        "view_mismatch",
        "topology_mismatch",
    }
)

UNCERTAINTY_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "unreadable_dimension",
        "ambiguous_geometry",
        "insufficient_evidence",
        "conflicting_views",
    }
)

DISCREPANCY_LEDGER_FIELDS: Final[tuple[str, ...]] = (
    "category",
    "severity",
    "expected",
    "observed",
    "evidence",
    "proposed_reaction",
)

DRAWING_RECONSTRUCTION_WORKFLOW: Final[str] = r"""# Drawing reconstruction workflow

Use this workflow when the target geometry is supplied as a drawing, screenshot,
photograph, or set of orthographic views. A valid FreeCAD solid is not proof that
the model matches the reference.

## 0. Non-negotiable rules

- Prefer standard MCP modeling tools. Use `safe_execute` or `execute_python` only
  when a required operation is missing or a standard tool is demonstrably
  invalid for the case. Keep fallback code local to one operation and validate it
  immediately.
- Reuse one explicit document and one PartDesign Body for one part. Do not create
  new documents or Bodies to hide failed attempts.
- Do not infer symmetry, mirrored features, repeated counts, equal spacing, bend
  directions, or hidden geometry unless the drawing explicitly dimensions or
  proves them.
- Do not guess `FaceN` or `EdgeN`. Select geometry by plane, normal, location,
  dimensions, and adjacency whenever possible.
- Build the complete additive blank first; perform holes, pockets, bores, and
  cutouts after additive geometry; apply fillets and chamfers last unless the
  manufacturing logic requires a different order.

## 1. Reference acquisition and evidence map

1. Call `open_image(reference_path)` so the model receives pixels, not only a
   filesystem path.
2. Inspect the whole sheet only for layout and view identification.
3. Create an evidence table before modeling. Each row must contain:
   - feature or requirement;
   - explicit dimension/value;
   - source view or crop;
   - status: `explicit`, `derived`, or `assumed`;
   - confidence and unresolved questions.
4. If a required dimension is unreadable, contradictory, or missing, stop and ask
   the user. Do not invent a convenient value and continue silently.

Minimum feature inventory:

- overall silhouette and overall dimensions;
- coordinate convention and intended principal views;
- additive regions: base, walls, bosses, ribs, flanges, bends;
- subtractive regions: holes, slots, pockets, counterbores, internal voids;
- quantities and patterns;
- radii, chamfers, angles, bend directions, and thickness;
- symmetry only when explicitly supported;
- ambiguous areas and alternative interpretations.

## 2. Parametric construction plan

Before changing FreeCAD, write a feature-by-feature plan containing:

- document and Body names;
- spreadsheet aliases or named constraints for key dimensions;
- sketch plane/support and world-space feature direction;
- expected Body Tip after each feature;
- expected dimensional or volume effect;
- exact reference view used to accept that feature;
- rollback target if the feature fails.

Prefer editing aliases, constraints, and existing feature parameters over placing
unrelated hard-coded geometry.

## 3. Mandatory ACT → OBSERVE → REACT gate

After every major feature such as a Pad, Revolution, wall/thickness operation,
boss, bend, Pocket, Hole, cut, pattern, fillet, or chamfer:

### ACT

Execute exactly one logically reviewable feature. Recompute the document.

### OBSERVE — geometry

- Validate the new feature and document.
- Confirm the expected Body Tip and solid count.
- For additive features, confirm positive added volume and expected world-space
  bounds/direction.
- For subtractive features, confirm positive removed volume and that the intended
  region was cut.
- Inspect sketch status, placements, expressions, and relevant dimensions.

### OBSERVE — visual correspondence

1. Set the candidate camera to the same view as the selected reference crop.
2. Save a screenshot with `show_corner_cross=True` and open it from disk.
3. Call `compare_images(reference_crop, candidate_screenshot)`.
4. Never compare an orthographic candidate with an isometric reference, and never
   treat a comparison against the entire drawing sheet as feature evidence.
5. Write a discrepancy ledger with these fields for every mismatch:
   `category`, `severity`, `expected`, `observed`, `evidence`,
   `proposed_reaction`.

`compare_images` only arranges images for inspection. It does not calculate CAD
correctness or approve the checkpoint.

### REACT

Call `evaluate_model_checkpoint` with geometry results, unresolved dimensions,
and the discrepancy ledger.

- `continue`: checkpoint accepted; proceed to the next planned feature.
- `rework`: do not add the next feature. Undo/delete only the failed feature,
  confirm the previous Body Tip and valid solid are restored, correct the cause,
  and repeat the same checkpoint.

A screenshot without a written discrepancy ledger and reaction decision is not a
completed observation.

## 4. Blocking conditions

Do not proceed when any of the following is true:

- invalid geometry, wrong Body Tip, or unexpected solid count;
- missing or extra major element;
- wrong quantity of holes, bosses, ribs, bends, or repeated features;
- clearly different silhouette, profile, orientation, or bend direction;
- wrong or unverified major dimension;
- reference and candidate views are not equivalent;
- a required dimension cannot be read confidently;
- visual evidence conflicts with geometric measurements.

Minor rendering differences, color, antialiasing, line thickness, and UI overlays
are not geometric discrepancies by themselves.

## 5. Final acceptance

Before completion, repeat acceptance feature by feature rather than giving a
single "looks similar" judgment. Verify:

- every explicit feature from the evidence table is represented exactly once;
- all quantities, major dimensions, radii, angles, and thickness values;
- one intended valid solid and correct Body Tip;
- parametric aliases/constraints and sensible feature order;
- no visible helper or cutting Bodies;
- matching Front/Top/Right or section views as applicable;
- final discrepancy ledger contains no blocking items;
- document is saved to the requested path.
"""

MODEL_MODIFICATION_WORKFLOW: Final[str] = r"""# Existing model modification workflow

Use this workflow when changing an existing FreeCAD model, including changes
requested from a drawing or image.

## 1. Preserve design intent first

1. Open or reuse the intended document; never create a duplicate silently.
2. List objects and inspect the Body history, current Tip, sketches, constraints,
   expressions, Spreadsheet aliases, dependencies, visibility, and placements.
3. Identify the earliest existing parameter or feature that semantically owns the
   requested change.
4. Prefer changing that parameter, constraint, sketch, or feature over appending a
   compensating solid/cut at the end of the tree.
5. Record a baseline checkpoint: document validity, solid count, bounds, volume,
   standard screenshots, and requested invariants that must remain unchanged.

## 2. Change classification

Classify the request before acting:

- parameter-only change;
- sketch geometry/constraint change;
- feature parameter or support change;
- insertion/removal/reordering of a feature;
- topology-sensitive repair;
- reference-driven reconstruction of a local region.

If changing an upstream feature will break topological references, inspect and
plan the dependent repairs before editing.

## 3. One change per checkpoint

Apply one logically reviewable change, recompute, and run both validations:

- FreeCAD validity: feature state, shape validity, solid count, Body Tip,
  expressions, and expected volume/bounds change;
- requirement correspondence: same-view screenshot or dimensional evidence
  showing that the requested change occurred and unrelated regions did not
  regress.

For image-driven modifications, use the same ACT → OBSERVE → REACT gate and
`evaluate_model_checkpoint` described by the drawing reconstruction workflow.

## 4. Reaction policy

- If the change is correct and invariants are preserved: continue.
- If the requested feature is wrong or an unrelated feature regressed: undo the
  change, restore the baseline Tip/state, diagnose the dependency, and rework.
- If the requested value or intended interpretation is ambiguous: ask the user.
- Do not hide a failed edit by creating a replacement Body, duplicate document,
  or disconnected auxiliary solid.

## 5. Completion

Confirm the requested change, preserved invariants, parametric editability,
feature order, expressions, final standard views, and saved document path.
"""

VISUAL_CHECKPOINT_PROTOCOL: Final[str] = r"""# Visual checkpoint protocol

1. Use a reference crop containing one comparable view.
2. Set the FreeCAD camera to the same view and orientation.
3. Save and open the candidate screenshot.
4. Run `compare_images`.
5. Produce a discrepancy ledger with category, severity, expected, observed,
   evidence, and proposed reaction.
6. Run `evaluate_model_checkpoint`.
7. Continue only when the returned decision is `continue`.

A valid solid and a visually plausible screenshot are independent checks; both
must pass.
"""
