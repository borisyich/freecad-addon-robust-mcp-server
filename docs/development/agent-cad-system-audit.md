# Agent + MCP + FreeCAD system audit

## Objective

The target system must reliably support three related tasks:

1. reconstruct a parametric 3D model from a drawing or image;
2. modify an existing parametric model from a textual or visual change request;
3. detect incorrect intermediate results and react before errors accumulate.

The core requirement is not merely tool execution. It is a closed engineering loop in which every major action produces evidence, an explicit discrepancy analysis, and a controlled state transition.

## Current architecture

```text
user/reference drawing
        ↓
agent host (Codex, Cline, other MCP client)
        ↓
client-native instructions + MCP prompts/resources/tool schemas
        ↓
freecad-mcp server
        ↓
XML-RPC/socket/embedded bridge
        ↓
FreeCAD document + GUI renderer
        ↑
geometry inspection + screenshots + image tools
```

### Strengths already present

- Broad standard-tool coverage for documents, PartDesign, Sketcher, validation, views, and export.
- Transaction-based undo/redo and validation tools.
- Improved feature tools that report measurable effects such as added/removed volume and direction.
- Real MCP `ImageContent` from `open_image`, `get_screenshot`, and `compare_images`.
- Camera-aware global-axis triad embedded in screenshots.
- Existing engineering rules covering one Body, additive-before-subtractive order, explicit directions, and rollback.

### Main failure found

The previous workflow implemented `act` and part of `observe`, but not a binding `reaction` transition. The rule required screenshots and comparisons, yet:

- `compare_images` only created a side-by-side image;
- there was no mandatory discrepancy representation;
- no categories were declared blocking;
- no deterministic decision controlled whether the agent could continue;
- whole-sheet and mismatched-view comparisons were not prohibited strongly enough;
- a valid FreeCAD shape could be treated as success even when it was the wrong part.

This allows an agent to acknowledge a mismatch and still add the next feature.

## Guidance delivery audit

### Client-native files

These are the practical first layer and must contain concise non-negotiable rules:

- Codex reads root `AGENTS.md` as repository guidance;
- Cline loads applicable `.clinerules` files;
- other hosts may use their own project instruction mechanism.

The former `.agents/AGENT.md` was not a reliable Codex bootstrap. A root `AGENTS.md` is now present, and the engineering rules are mirrored across supported repository files.

### MCP prompts

Prompts are discoverable templates, not a universal automatic startup channel. `freecad_startup` previously described itself as auto-loadable and contained generic advice that encouraged `safe_execute` too early. It now acts as a compact task router, while detailed workflows are isolated in:

- `reproduce_from_drawing`;
- `modify_existing_model`;
- task-specific `freecad_guidance` modes.

### MCP resources

`freecad://best-practices` previously mixed general API advice, version notes, and execution examples, but lacked a drawing evidence model and reaction policy. It now exposes structured task routing, tool priority, dual validation, discrepancy categories, stop criteria, and workflow resources.

### Tool schemas/descriptions

Tool descriptions are important because they are available when tools are discovered. Critical local constraints are now attached directly to the relevant tools:

- `compare_images`: no correctness score and mandatory next reaction step;
- `evaluate_model_checkpoint`: deterministic workflow decision.

## Revised control loop

### Pre-model evidence stage

The agent must transform a drawing into an evidence map before construction:

- identify views, sections, details, and coordinate orientation;
- crop relevant regions at readable resolution;
- inventory additive/subtractive features;
- record dimensions, quantities, radii, angles, bends, and thickness;
- label each item `explicit`, `derived`, or `assumed`;
- stop on unresolved required dimensions.

This prevents premature modeling from a vague global impression.

### Feature checkpoint stage

Each major feature is one checkpoint:

1. **Act:** create one logically reviewable feature.
2. **Observe geometry:** validate shape, Tip, solid count, dimensions, bounds, placement, and volume effect.
3. **Observe correspondence:** compare an equivalent candidate view with a reference crop.
4. **Describe:** write a complete discrepancy ledger.
5. **React:** call `evaluate_model_checkpoint`.

The next feature is allowed only for `decision=continue`.

### Deterministic stop policy

`evaluate_model_checkpoint` blocks continuation when:

- geometry is invalid;
- the visual checkpoint was skipped;
- solid count, dimensions, or view equivalence fail;
- the ledger is incomplete;
- a missing/extra/wrong-count/wrong-position/wrong-orientation/profile/bend/silhouette/topology discrepancy exists;
- any other discrepancy is major or critical.

Unreadable dimensions, conflicting views, and insufficient evidence unless a geometry/rework failure must be resolved first.

## Existing-model modification audit

Model editing requires a different plan from greenfield construction. The main risks are:

- appending workaround geometry rather than changing the semantic owner;
- breaking downstream topological references;
- losing expressions or constraints;
- changing unrelated regions;
- replacing a failed edit with a new Body/document.

The revised workflow requires:

- inspection of history, Tip, aliases, constraints, dependencies, visibility, and placement;
- a baseline of invariants and views;
- classification of the requested change;
- editing the earliest semantic parameter/feature where practical;
- one change per checkpoint;
- regression checks for unaffected geometry.

## What remains unsolved

### 1. Visual comparison is still qualitative

`compare_images` does not align views or compute geometry metrics. It depends on the VLM to identify discrepancies. The reaction gate improves behavior but does not make vision infallible.

Recommended next tools:

- canonical orthographic and section rendering;
- reference/candidate registration and scale normalization;
- silhouette IoU and contour-distance metrics;
- bounding-box and projected-dimension error;
- hole center, diameter, and count checks;
- overlay and difference-map generation.

### 2. Drawing parsing is not yet structured

`compare_images` provides overview, but there is no persistent `DrawingSpec` or evidence graph. A future schema may be should store features, dimensions, source regions, confidence, and explicit/derived/assumed status.

### 3. Checkpoint evidence is agent-authored

The tool enforces policy on supplied evidence, but an agent can still omit or misclassify discrepancies. Future quantitative tools should feed checkpoint fields directly rather than relying entirely on prose.

### 4. Workflow enforcement is not server-global

MCP cannot guarantee that every host invokes a prompt/resource. Repository instruction files and tool-level requirements reduce this risk, but strict enforcement would require a stateful session controller that tracks required checkpoints between modifying tool calls.

## Recommended roadmap

### P0 — implemented in this revision

- Root `AGENTS.md` and synchronized host rules.
- Drawing reconstruction and model modification prompts/resources.
- Drawing crop tool.
- Explicit discrepancy ledger.
- Deterministic reaction gate.
- Compare-tool metadata requiring the next step.
- Documentation and tests.

### P1 — next practical increment

- Render a standard multi-view checkpoint package: Front, Top, Right, Isometric, and optional section.
- Add image overlay/difference views with scale and orientation normalization.
- Add projected bbox, silhouette, and feature-count metrics.
- Extend `evaluate_model_checkpoint` with quantitative metric thresholds.

### P2 — structured drawing reasoning

- Add `DrawingView`, `DrawingPrimitive`, dimension evidence, and feature hypothesis schemas.
- Persist a drawing evidence ledger across the session.
- Link each modeled feature to drawing evidence and acceptance results.

### P3 — stateful workflow controller

- Track document/Body/checkpoint state in the MCP server.
- Mark a document as blocked after modifying operations until the required validation and reaction steps are completed.
- Reject further feature creation when the previous checkpoint is unresolved.

## Acceptance criteria for the system

A drawing-to-model task is successful only when:

- the source evidence was explicitly extracted;
- every major feature passed geometric and correspondence gates;
- every mismatch produced a reaction rather than silent continuation;
- unresolved dimensions were escalated;
- the model remains parametric and editable;
- feature-by-feature final acceptance has no blocking discrepancies.
