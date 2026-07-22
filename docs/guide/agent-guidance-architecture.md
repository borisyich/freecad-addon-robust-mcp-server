# Agent guidance architecture

Reliable CAD work cannot depend on one long user prompt. The system has four distinct instruction channels, and they do not have equal delivery guarantees.

## What reaches the agent first

### 1. Client-native repository instructions

These are the most reliable project-level bootstrap layer because the client loads them as repository instructions:

- `AGENTS.md` — Codex;
- `.clinerules/freecad-modeling.md` — Cline;
- `.agents/AGENT.md` — repository copy for clients/workflows that use this convention;
- `CLAUDE.md` — project/development guidance for Claude-compatible clients.

The files contain the compact non-negotiable rules: task routing, standard-tool priority, one document/Body, evidence extraction, ACT-OBSERVE-REACT checkpoints, stop criteria, rollback, and completion gates.

### 2. MCP tool descriptions and schemas

When the MCP server is connected, the client discovers tools and their schemas. This is the only server-side context that must be available for tool selection. Tool descriptions therefore carry local behavioral requirements where they matter:

- `compare_images` states that it does not calculate correctness and requires a discrepancy ledger;
- `evaluate_model_checkpoint` returns the deterministic `continue` or `rework` decision;

### 3. MCP prompts

Prompts are task-specific templates exposed by the server. Availability does not guarantee automatic invocation by every MCP client.

- `freecad_startup` — compact session bootstrap and task router;
- `reproduce_from_drawing` — complete drawing reconstruction workflow;
- `modify_existing_model` — design-intent-preserving modification workflow;
- `freecad_guidance` — narrower technical guidance.

The client or user should explicitly invoke the task prompt when supported.

### 4. MCP resources

Resources are read-only reference material. They are discoverable, but the agent must read them or the client must inject them.

- `freecad://best-practices`;
- `freecad://workflows/drawing-reconstruction`;
- `freecad://workflows/model-modification`;
- state resources such as documents and objects.

## Why the previous system failed

The former rule required screenshots and `compare_images`, but it did not define a state transition after observation. The agent could inspect a visibly wrong result and still proceed because there was no mandatory discrepancy representation, no blocking categories, and no explicit next-action decision.

The revised loop is:

```text
ACT one feature
  ↓
OBSERVE geometry validity and measurable effect
  ↓
OBSERVE equivalent-view visual evidence
  ↓
WRITE discrepancy ledger
  ↓
evaluate_model_checkpoint
  ├─ continue → next feature
  └─ rework   → undo failed feature, restore previous Tip, retry checkpoint
```

## Division of responsibility

### FreeCAD and deterministic tools

Use for facts that should not depend on visual judgment:

- shape validity and error state;
- Body Tip and solid count;
- volume change;
- bounds, placement, dimensions, and expressions;
- sketch constraint status;
- rollback state.

### Vision model

Use for:

- identifying views and feature evidence in a drawing;
- interpreting local shape semantics;
- describing discrepancies between equivalent views;
- choosing a correction strategy.

The vision model must not be the only authority for dimensions, topology, or geometric validity.

### `compare_images`

This is a presentation tool, not a metric. It places reference and candidate images side by side. It does not align them, calculate a score, or approve a checkpoint.

### `evaluate_model_checkpoint`

This tool does not inspect pixels. It enforces the reaction policy on the evidence supplied by the agent. Major/blocking discrepancies force `rework`; only a clean checkpoint returns `continue`.

## Remaining architectural gap

The current comparison remains qualitative. A stronger next layer should render canonical orthographic/section views and compute local geometric metrics such as silhouette IoU, contour distance, bounding-box error, hole center/diameter error, and feature counts. These metrics should become additional inputs to `evaluate_model_checkpoint`, while the VLM handles semantic interpretation.
