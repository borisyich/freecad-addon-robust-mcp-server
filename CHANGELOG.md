# Changelog
## AFTER FORK ORIGINAL REPO

- Debugged tools
- Added effective-volume validation and rollback for Pad, Revolution, Additive Loft, and Additive Pipe.
- Reworked screenshots to activate the target 3D view, fit and refresh the GUI, verify image output, and optionally save without returning base64.
- Added engineering-agent modeling rules, a tooling roadmap, and a full bracket integration regression.
- Added `create_cylindrical_cut` for validated radial and off-face holes with an explicit world-space axis.
- Extended `create_sketch` to accept explicit `Object.FaceN` and datum-plane object names.
- Added an optional world-space `direction` argument to `pad_sketch`. This avoids relying on plane-specific `Reversed` semantics, which can differ with sketch support orientation. The tool now reports `sketch_normal`, `effective_direction`, and the resolved `reversed` value.
- Added multimodal image delivery: `get_screenshot(return_image=True)`, `open_image(path)`, and `compare_images(reference_path, candidate_path)` now return real MCP `ImageContent` instead of relying on paths or base64 text.
- Fixed the global X/Y/Z corner indicator in screenshots. FreeCAD's native corner cross is a screen-space feedback decoration and can be omitted by `saveImage`; `get_screenshot(show_corner_cross=True)` now derives the projected axes from the active camera and composites the triad into the PNG using Qt `QImage`/`QPainter`.
- Added root `AGENTS.md` and synchronized Codex/Cline/repository engineering rules.
- Added `reproduce_from_drawing` and `modify_existing_model` MCP prompts.
- Added `freecad://workflows/drawing-reconstruction` and `freecad://workflows/model-modification` resources.
- Reworked `freecad_startup` into a compact task router and clarified that MCP prompts/resources are discoverable but not guaranteed to be auto-injected by every client.
- Added deterministic `evaluate_model_checkpoint` decisions (`continue`, `rework`) from geometry evidence, visual-checkpoint status, unresolved dimensions, and a structured discrepancy ledger.
- Reworked best practices, documentation, and tests around ACT → OBSERVE → REACT, same-view comparison, stop criteria, design-intent-preserving model edits, and standard-tool-first execution.

This project uses **component-specific versioning**. Each component has its own
release notes and version history.

## Component Release Notes

| Component              | Release Notes                                                        | Description                                           |
| ---------------------- | -------------------------------------------------------------------- | ----------------------------------------------------- |
| **Robust MCP Server**  | [RELEASE_NOTES.md](src/freecad_mcp/RELEASE_NOTES.md)                 | MCP server for AI assistant integration (PyPI/Docker) |
| **Robust MCP Bridge**  | [RELEASE_NOTES.md](freecad/RobustMCPBridge/RELEASE_NOTES.md)         | FreeCAD workbench addon                               |

## Versioning Scheme

Each component follows [Semantic Versioning](https://semver.org/) independently:

- **Robust MCP Server**: Released via git tags `robust-mcp-server-vX.Y.Z`
- **Robust MCP Bridge**: Released via git tags `robust-mcp-workbench-vX.Y.Z`

## Latest Versions

To see the current latest versions of each component:

```bash
just release::latest-versions
```

## Full Documentation

For detailed release process and contribution guidelines, see:

- [Release Process](https://spkane.github.io/freecad-robust-mcp-and-more/development/releasing/)
- [Contributing Guide](https://spkane.github.io/freecad-robust-mcp-and-more/development/contributing/)
