# Develop engineering drawings from a 3D model

Status: **TODO / not yet a first-class freecad-mcp workflow**.

This file reserves the routing target for engineering-drawing creation. The MCP
currently has strong 3D modeling, inspection, image, measurement, and export
capabilities, but no dedicated high-level TechDraw tool family that can reliably
create and validate production drawings end to end.

## Intended workflow

When dedicated drawing tooling is implemented, this route should cover:

1. validate the source 3D model;
2. choose the principal/front view from function and manufacturing intent;
3. add the minimum orthographic/section/detail views needed to define the part;
4. place dimensions from stable geometric references, avoiding duplicated or
   contradictory dimensions;
5. add center marks, hole/thread callouts, tolerances, surface notes, material,
   scale, projection symbol, and title-block data when required;
6. check that every manufacturing-critical feature is defined by the drawing;
7. export the required drawing format and inspect the result.

The future route should maintain a drawing-definition ledger: view IDs and
camera/section definitions, each manufacturing feature, its one authoritative
location/size callout, datum/GD&T relationships, and a coverage status. Visual
legibility and semantic completeness are separate gates; a clean page may still
omit a manufacturing-critical feature.

Deterministic checks should include projection/view-axis consistency, measured
dimension-label agreement, duplicated or contradictory dimensions, feature
coverage, annotation/view overlap, page bounds, and exported-artifact inspection.

## Current behavior

Do not pretend a complete drawing workflow exists through ordinary 3D tools.
If the user asks for a production drawing today:

- state that dedicated drawing tooling is not yet implemented;
- use FreeCAD Python/TechDraw only when that fallback is explicitly appropriate
  for the task;
- keep any generated drawing provisional and report which checks could not be
  performed deterministically through MCP.

Do not present a screenshot with manually placed text as a production drawing
unless dimensions remain associated with model geometry and the missing semantic
checks are made explicit.
