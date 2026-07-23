# Agent + MCP + FreeCAD system audit

## Scope

The repository supports three different concerns that must remain separate:

1. **agent guidance** — how to choose a modeling strategy and preserve design intent;
2. **MCP capability** — tools that create, inspect, render, and modify FreeCAD objects;
3. **evidence/diagnostics** — what the document actually contains and whether the
   geometry and parametric structure require review.

A valid OpenCASCADE solid is not sufficient evidence of a good engineering
model. Conversely, a diagnostic warning such as an intentionally
under-constrained construction sketch is not automatically a failed part.

## Current guidance architecture

```text
Codex/Cline project bootstrap
        ↓
AGENTS.md or .clinerules (short routing rules)
        ↓
.agents/skills/freecad-engineering/SKILL.md
        ↓
optional Skill references for process-specific detail
        ↓
MCP tools + FreeCAD document
        ↓
validate_parametric_model final structural report
```

### Single source of detailed policy

The canonical engineering guidance is:

```text
.agents/skills/freecad-engineering/SKILL.md
```

The root `AGENTS.md` is intentionally short. It tells Codex when the Skill is
mandatory and requires the final diagnostic. Cline receives the same routing
through `.clinerules/freecad-modeling.md`. MCP prompts and resources also point
to the Skill rather than maintaining independent copies of the workflow.

This reduces drift, but the delivery mechanisms are not equivalent:

- Codex reads applicable `AGENTS.md` files before work;
- Codex initially sees Skill metadata and loads full `SKILL.md` when the Skill is
  selected;
- MCP prompts and resources are discoverable, but a client is not required to
  inject every prompt/resource automatically;
- tool descriptions are visible only when the corresponding MCP tool catalog is
  loaded.

Therefore, the root `AGENTS.md` remains necessary as a small router even though
all detailed engineering content lives in the Skill.

## Modeling policy

The current policy is deliberately **not** a rigid state machine. The agent may
choose standard tools, `execute_python`, `safe_execute`, or `run_macro` according
to the task. The required outcome is normally a native editable FreeCAD model
with a meaningful Body/Sketch/PartDesign history, unless the user explicitly
requests a disposable direct B-rep/imported-shape workflow.

The Skill first classifies:

- probable stock form: plate/block, sheet, round/tube, hex, profile, preform, or
  hybrid;
- dominant process: milling, turning, sheet-metal bending/forming, or hybrid.

That classification guides the base feature and feature dependency order. It is
not a claim that the CAD tree must reproduce the literal shop-floor sequence.

## Image delivery and visual reasoning

`open_image` returns actual MCP `ImageContent` for one source image.
`open_image_tiles` returns:

- a numbered whole-image overview;
- up to nine overlapping enlarged fragments;
- a text block before every fragment identifying its grid location, source pixel
  rectangle, overlap, and resize scale;
- optional saved files for later same-view comparison.

This improves the amount of visual budget allocated to small dimensions and
local geometry. It does not perform OCR, reconstruct missing pixels, infer CAD
semantics, or prove that the model interpreted every fragment correctly.

`compare_images` remains a qualitative side-by-side aid. It does not align the
images or calculate correctness. A formal discrepancy ledger and
`evaluate_model_checkpoint` are optional tools, not a mandatory global
ACT-OBSERVE-REACT protocol.

## Final parametric diagnostic

`validate_parametric_model` is the final informative scan after geometry creation
or modification. It reports:

- document metadata and object-type counts;
- every `PartDesign::Body`, its state, shape validity, solid count, placement,
  Tip, and ordered history;
- history object type/role counts, dependencies, expressions, and shape summaries;
- every sketch, solver status, remaining DoF, profile state, supports,
  expressions, constraint-type counts, named constraints, and solver-reported
  conflicting/redundant indices where available;
- standalone sketches, Spreadsheets, and solid objects outside Bodies;
- findings categorized as errors or warnings;
- explicit limitations.

The report is intentionally not a hard pass/fail gate. It cannot prove:

- correspondence to a drawing;
- correctness of dimensions not encoded in model properties;
- manufacturability, tolerances, fits, material, or process planning;
- semantic design intent merely from object names/types.

Project instructions require the agent to call the tool immediately before its
final user-facing response after geometry changes and summarize significant
findings. MCP itself cannot prevent a client/model from emitting text without a
tool call, so this is an instruction-level requirement rather than a protocol
lock. The report makes non-parametric shortcuts and unhealthy sketches visible
when the requirement is followed.

## Documentation/code consistency findings

The current revision corrected the main drift found in the uploaded project:

- removed obsolete references to a missing `submit_modeling_plan` workflow;
- removed image-only `VISUAL ACK` requirements from `open_image_tiles` and docs;
- removed `ask_user` from checkpoint outcomes; ambiguity is handled
  autonomously through best-supported assumptions and rework;
- changed `compare_images` and `evaluate_model_checkpoint` from mandatory gates
  to optional review aids;
- kept `execute_python`, `safe_execute`, and `run_macro` registered;
- aligned resource/prompt catalogs with the canonical Skill and final validator;
- updated tool reference, user guide, configuration guide, changelog, and release
  notes.

## Remaining technical risks

1. **Instruction compliance is probabilistic.** `AGENTS.md` + Skill routing
   strongly improves consistency but does not guarantee the model will call the
   final validator.
2. **Sketch solver API varies by FreeCAD version.** The validator uses guarded
   feature detection and reports unavailable fields as empty/unknown rather than
   failing the whole scan.
3. **Topology naming remains fragile.** Generated `FaceN`/`EdgeN` references can
   change after upstream edits. Prefer origin/datum planes and semantic
   references where available.
4. **Visual comparison is qualitative.** Future high-value additions are
   canonical orthographic rendering, alignment, silhouette/contour metrics,
   projected bounding-box checks, and hole/count measurements.
5. **Sheet-metal approximations are limited.** Without a dedicated sheet-metal
   feature set, a constant-thickness formed-state model does not validate bend
   allowance or flat-pattern correctness.

## Recommended next increments

- Add live integration fixtures for representative milling, turning, and
  sheet-metal documents and snapshot the validator schema.
- Add a compact human-readable formatter for `validate_parametric_model` while
  retaining the full JSON report.
- Add deterministic same-view rendering and image-registration tools before
  introducing any stricter visual workflow.
- Evaluate Skill activation and validator-call rate across Codex App/Cline logs;
  tune the Skill description and root routing based on measured failures rather
  than adding duplicated instructions.
