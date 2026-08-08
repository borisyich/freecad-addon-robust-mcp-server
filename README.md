# FreeCAD Robust MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI Version](https://img.shields.io/pypi/v/freecad-robust-mcp)](https://pypi.org/project/freecad-robust-mcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/freecad-robust-mcp)](https://pypi.org/project/freecad-robust-mcp/)
[![Docker Image Version](https://img.shields.io/docker/v/spkane/freecad-robust-mcp?sort=semver&label=docker)](https://hub.docker.com/r/spkane/freecad-robust-mcp)
[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://spkane.github.io/freecad-addon-robust-mcp-server/)

[![CI Tests](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/test.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/test.yaml)
[![Docker Build](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/docker.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/docker.yaml)
[![Pre-commit](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/pre-commit.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/pre-commit.yaml)
[![CodeQL](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/codeql.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/codeql.yaml)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that enables integration between AI assistants (Claude, GPT, and other MCP-compatible tools) and [FreeCAD](https://www.freecadweb.org/), allowing AI-assisted development and debugging of 3D models, macros, and workbenches.

## Table of Contents

<!--TOC-->

- [FreeCAD Robust MCP Server](#freecad-robust-mcp-server)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Installation Requirements / Dependencies](#installation-requirements--dependencies)
  - [For Users](#for-users)
    - [Quick Links](#quick-links)
  - [Robust MCP Server](#robust-mcp-server)
    - [Installation](#installation)
      - [Using pip (recommended)](#using-pip-recommended)
      - [Using mise and just (from source)](#using-mise-and-just-from-source)
      - [Using Docker](#using-docker)
    - [Configuration](#configuration)
      - [Environment Variables](#environment-variables)
      - [Connection Modes](#connection-modes)
      - [MCP Client Configuration](#mcp-client-configuration)
    - [Usage](#usage)
      - [Starting the MCP Bridge in FreeCAD](#starting-the-mcp-bridge-in-freecad)
        - [Option A: Using the Workbench (Recommended)](#option-a-using-the-workbench-recommended)
        - [Option B: Using just commands (from source)](#option-b-using-just-commands-from-source)
      - [Uninstalling the MCP Bridge](#uninstalling-the-mcp-bridge)
        - [Checking for Legacy Components](#checking-for-legacy-components)
        - [Manual Cleanup (if needed)](#manual-cleanup-if-needed)
      - [Running Modes](#running-modes)
        - [XML-RPC Mode (Recommended)](#xml-rpc-mode-recommended)
        - [Socket Mode (JSON-RPC)](#socket-mode-json-rpc)
        - [Headless Mode](#headless-mode)
        - [Embedded Mode (Linux Only)](#embedded-mode-linux-only)
    - [Available Tools](#available-tools)
      - [Execution & Debugging](#execution--debugging)
      - [Document Management](#document-management)
      - [Object Creation - Primitives](#object-creation---primitives)
      - [Object Management](#object-management)
      - [PartDesign - Sketching](#partdesign---sketching-and-core-features)
      - [PartDesign - Patterns & Edges](#partdesign---patterns--edges)
      - [View & Display](#view--display)
      - [Undo/Redo](#undoredo)
      - [Export/Import](#exportimport)
      - [Macro Management](#macro-management)
      - [Parts Library](#parts-library)
  - [For Developers](#for-developers)
  - [Robust MCP Server Development](#robust-mcp-server-development)
    - [Prerequisites](#prerequisites)
    - [Initial Setup](#initial-setup)
    - [MCP Client Configuration (Development)](#mcp-client-configuration-development)
    - [Development Workflow](#development-workflow)
    - [Running FreeCAD with the MCP Bridge](#running-freecad-with-the-mcp-bridge)
      - [GUI Mode (recommended for development)](#gui-mode-recommended-for-development)
      - [Headless Mode (for automation/CI)](#headless-mode-for-automationci)
    - [Running Tests](#running-tests)
    - [Code Quality](#code-quality)
  - [Architecture](#architecture)
  - [Acknowledgements](#acknowledgements)
    - [Related Projects](#related-projects)
  - [License](#license)

<!--TOC-->

> The macros that were originally in this repo under the `/macros` directory have been permanently moved to two new GitHub repos:
>
> - [spkane/freecad-macro-cut-for-magnets](https://github.com/spkane/freecad-macro-cut-for-magnets)
> - [spkane/freecad-macro-3d-print-multi-export](https://github.com/spkane/freecad-macro-3d-print-multi-export)

**FreeCAD Forum:** [addon discussion post](https://forum.freecad.org/viewtopic.php?p=866012)

## Features

- **123 MCP Tools**: Compact CAD operations including primitives, PartDesign, measurements, booleans, and export
- **Multiple Connection Modes**: XML-RPC (recommended), JSON-RPC socket, or embedded
- **GUI & Headless Support**: Full modeling in headless mode, plus screenshots/colors in GUI mode
- **Macro Development**: Create, edit, run, and template FreeCAD macros via MCP

## Installation Requirements / Dependencies

- [FreeCAD](https://www.freecadweb.org/) 0.21+ or 1.0+
- Python 3.11 (required for FreeCAD ABI compatibility)

---

## For Users

This section covers installation and usage for end users who want to use the Robust MCP Server with AI assistants.

### Quick Links

| Resource                                                                              | Description                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------- |
| [**Documentation**](https://spkane.github.io/freecad-addon-robust-mcp-server/)        | Full documentation, guides, and API reference |
| [Docker Hub](https://hub.docker.com/r/spkane/freecad-robust-mcp)                      | Pre-built Docker images for easy deployment   |
| [PyPI](https://pypi.org/project/freecad-robust-mcp/)                                  | Python package for pip installation           |
| [GitHub Releases](https://github.com/spkane/freecad-addon-robust-mcp-server/releases) | Release archives and changelogs               |

## Robust MCP Server

> **Note**: The Linux container and PyPI package are both named `freecad-robust-mcp` which differs slightly from this git repository name.

### Installation

#### Using pip (recommended)

```bash
pip install freecad-robust-mcp
```

#### Using mise and just (from source)

```bash
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise via the Official mise installer script (if not already installed)
curl https://mise.run | sh

mise trust
mise install
just setup
```

#### Using Docker

Run the Robust MCP Server in a container. This is useful for isolated environments or when you don't want to install Python dependencies on your host.

```bash
# Pull from Docker Hub (when published)
docker pull spkane/freecad-robust-mcp

# Or build locally
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server
docker build -t freecad-robust-mcp .

# Or use just commands (if you have mise/just installed)
just docker::build        # Build for local architecture
just docker::build-multi  # Build multi-arch (amd64 + arm64)
```

**Note:** The containerized Robust MCP Server only supports `xmlrpc` and `socket` modes since FreeCAD runs on your host machine (not in the container). The container connects to FreeCAD via `host.docker.internal`.

### Configuration

#### Environment Variables

| Variable              | Description                                          | Default     |
| --------------------- | ---------------------------------------------------- | ----------- |
| `FREECAD_MODE`        | Connection mode: `xmlrpc`, `socket`, or `embedded`   | `xmlrpc`    |
| `FREECAD_PATH`        | Path to FreeCAD's lib directory (embedded mode only) | Auto-detect |
| `FREECAD_SOCKET_HOST` | Socket/XML-RPC server hostname                       | `localhost` |
| `FREECAD_SOCKET_PORT` | JSON-RPC socket server port                          | `9876`      |
| `FREECAD_XMLRPC_PORT` | XML-RPC server port                                  | `9875`      |
| `FREECAD_TIMEOUT_MS`  | Execution timeout in ms                              | `30000`     |

#### Connection Modes

| Mode       | Description                                 | Platform Support                  |
| ---------- | ------------------------------------------- | --------------------------------- |
| `xmlrpc`   | Connects to FreeCAD via XML-RPC (port 9875) | **All platforms** (recommended)   |
| `socket`   | Connects via JSON-RPC socket (port 9876)    | **All platforms**                 |
| `embedded` | Imports FreeCAD directly into process       | **Linux only** (crashes on macOS) |

**Note:** Embedded mode crashes on macOS because FreeCAD's `FreeCAD.so` links to `@rpath/libpython3.11.dylib`, which conflicts with external Python interpreters. Use `xmlrpc` or `socket` mode on macOS and Windows.

#### MCP Client Configuration

Add something like the following to your MCP client settings. For Claude Code, this is `~/.claude/claude_desktop_config.json` or a project `.mcp.json` file:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "freecad-mcp",
      "env": {
        "FREECAD_MODE": "xmlrpc"
      }
    }
  }
}
```

If installed from source with mise/uv:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "/path/to/mise/shims/uv",
      "args": ["run", "--project", "/path/to/freecad-addon-robust-mcp-server", "freecad-mcp"],
      "env": {
        "FREECAD_MODE": "xmlrpc"
      }
    }
  }
}
```

If using Docker:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--add-host=host.docker.internal:host-gateway",
        "-e", "FREECAD_MODE=xmlrpc",
        "-e", "FREECAD_SOCKET_HOST=host.docker.internal",
        "spkane/freecad-robust-mcp"
      ]
    }
  }
}
```

**Docker configuration notes:**

- `--rm` removes the container after it exits
- `-i` keeps stdin open for MCP communication
- `--add-host=host.docker.internal:host-gateway` allows the container to connect to FreeCAD on your host (Linux only; macOS/Windows have this built-in)
- `FREECAD_SOCKET_HOST=host.docker.internal` tells the Robust MCP Server to connect to FreeCAD on your host machine

### Usage

#### Starting the MCP Bridge in FreeCAD

Before your AI assistant can connect, you need to start the MCP bridge inside FreeCAD:

##### Option A: Using the Workbench (Recommended)

1. Install the Robust MCP Bridge workbench via FreeCAD's Addon Manager:

   - **Edit -> Preferences -> Addon Manager**
   - Search for "Robust MCP Bridge"
   - Install and restart FreeCAD

1. Start the bridge:

   - Switch to the Robust MCP Bridge workbench
   - Click the **Start MCP Bridge** button in the toolbar
   - Or use the menu: **MCP Bridge -> Start Bridge**

1. You should see in the FreeCAD console:

   ```text
   MCP Bridge started!
     - XML-RPC: localhost:9875
     - Socket: localhost:9876
   ```

##### Option B: Using just commands (from source)

```bash
# Start FreeCAD with MCP bridge auto-started
just freecad::run-gui

# Or for headless/automation mode:
just freecad::run-headless
```

After starting the bridge, start/restart your MCP client (Claude Code, etc.) - it will connect automatically

#### Uninstalling the MCP Bridge

To uninstall the Robust MCP Bridge workbench:

1. Open FreeCAD
1. Go to **Edit -> Preferences -> Addon Manager**
1. Find "Robust MCP Bridge" in the list
1. Click **Uninstall**
1. Restart FreeCAD

##### Checking for Legacy Components

If you previously used older versions of this project, you may have legacy components installed. Run this command to check what's installed and get cleanup instructions:

```bash
just install::status
```

##### Manual Cleanup (if needed)

Remove any legacy files that may conflict with the workbench:

```bash
# macOS - remove legacy plugin and macro
rm -rf ~/Library/Application\ Support/FreeCAD/Mod/MCPBridge/
rm -f ~/Library/Application\ Support/FreeCAD/Macro/StartMCPBridge.FCMacro

# Linux - remove legacy plugin and macro
rm -rf ~/.local/share/FreeCAD/Mod/MCPBridge/
rm -f ~/.local/share/FreeCAD/Macro/StartMCPBridge.FCMacro
```

#### Running Modes

##### XML-RPC Mode (Recommended)

Connects to a running FreeCAD instance via XML-RPC. Works on all platforms.

```bash
FREECAD_MODE=xmlrpc freecad-mcp
```

##### Socket Mode (JSON-RPC)

Connects via JSON-RPC socket. Works on all platforms.

```bash
FREECAD_MODE=socket freecad-mcp
```

##### Headless Mode

Run FreeCAD in console mode without GUI. Useful for automation.

```bash
# If installed from source:
just freecad::run-headless
```

**Note:** Screenshot and view features are not available in headless mode.

##### Embedded Mode (Linux Only)

Runs FreeCAD in-process. **Only works on Linux** - crashes on macOS/Windows.

```bash
FREECAD_MODE=embedded freecad-mcp
```

### Available Tools

The server currently registers **123 MCP tools**. The tables below list common tools rather than duplicating the exact inventory. See the generated [Tools Overview](docs/guide/tools.md) or the MCP client's discovered tool list for the authoritative inventory; [MCP Tools Reference](docs/MCP_TOOLS_REFERENCE.md) provides detailed examples for core tools, while `freecad://capabilities` is a curated runtime overview. Tools marked with **GUI** require FreeCAD to be running in GUI mode; they return a structured error in headless mode.

#### Execution & Debugging (5 tools)

| Tool                         | Description                                                   | Mode |
| ---------------------------- | ------------------------------------------------------------- | ---- |
| `execute_python`             | Execute arbitrary Python code in FreeCAD's context            | All  |
| `get_freecad_version`        | Get FreeCAD version, build date, and Python version           | All  |
| `get_connection_status`      | Check MCP bridge connection status and latency                | All  |
| `get_console_output`         | Get recent FreeCAD console output (up to N lines)             | All  |
| `get_mcp_server_environment` | Get Robust MCP Server environment (OS, hostname, instance_id) | All  |

#### Document Management (7 tools)

| Tool                  | Description                               | Mode |
| --------------------- | ----------------------------------------- | ---- |
| `list_documents`      | List all open documents with metadata     | All  |
| `get_active_document` | Get information about the active document | All  |
| `create_document`     | Create a new FreeCAD document             | All  |
| `open_document`       | Open an existing .FCStd file              | All  |
| `save_document`       | Save a document to disk                   | All  |
| `close_document`      | Close a document (with optional save)     | All  |
| `recompute_document`  | Force recomputation of all objects        | All  |

#### Object Creation - Primitives (2 tools)

| Tool               | Description                                                     | Mode |
| ------------------ | --------------------------------------------------------------- | ---- |
| `create_object`    | Create a generic FreeCAD object by type ID                      | All  |
| `create_primitive` | Create a Box, Cylinder, Sphere, Cone, Torus, Wedge, or Helix    | All  |

#### Object Management (12 common tools)

| Tool                | Description                                        | Mode |
| ------------------- | -------------------------------------------------- | ---- |
| `list_objects`      | List all objects in a document                     | All  |
| `inspect_object`    | Compact object metrics; paged topology/properties on request | All  |
| `select_subshapes`  | Select paged `FaceN`/`EdgeN`/`VertexN` references by geometric criteria | All  |
| `edit_object`       | Modify properties; resolve names for link properties | All  |
| `delete_object`     | Delete an object from a document                   | All  |
| `set_placement`     | Set object position and rotation                   | All  |
| `scale_object`      | Scale an object uniformly or non-uniformly         | All  |
| `rotate_object`     | Rotate an object around an axis                    | All  |
| `copy_object`       | Create a copy of an object                         | All  |
| `mirror_object`     | Mirror an object across a plane (XY, XZ, YZ)       | All  |
| `boolean_operation` | Fuse, cut, or intersect objects                    | All  |
| `selection`         | Get, set, or clear the GUI selection               | GUI  |

#### PartDesign - Sketching and Core Features (14 common tools)

| Tool                       | Description                                                | Mode |
| -------------------------- | ---------------------------------------------------------- | ---- |
| `create_partdesign_body`   | Create a PartDesign::Body container                        | All  |
| `set_body_tip`             | Set and validate the active Body Tip                       | All  |
| `create_sketch`            | Create a sketch with a typed plane/face/datum support      | All  |
| `edit_sketch_geometry`     | Apply an ordered batch of sketch geometry edits            | All  |
| `edit_sketch_constraints`  | Edit constraints, names, and Spreadsheet expressions       | All  |
| `pad_sketch`               | Extrude a sketch (additive)                                | All  |
| `pocket_sketch`            | Cut into solid using a sketch (subtractive)                | All  |
| `revolution_sketch`        | Revolve a sketch around an axis (additive)                 | All  |
| `groove_sketch`            | Revolve a sketch around an axis (subtractive)              | All  |
| `thread_helix`             | Create additive/subtractive editable helical thread        | All  |
| `create_hole`              | Create validated holes from a supported sketch             | All  |
| `create_cylindrical_cut`   | Create radial/off-face cylindrical cuts                    | All  |
| `loft_sketches`            | Create a loft through multiple sketches                    | All  |
| `sweep_sketch`             | Sweep a profile along a spine path                         | All  |

#### PartDesign - Patterns & Edges (6 common tools)

| Tool               | Description                                | Mode |
| ------------------ | ------------------------------------------ | ---- |
| `linear_pattern`   | Create linear pattern of a feature         | All  |
| `polar_pattern`    | Create validated polar pattern of one feature    | All  |
| `multi_transform_pattern` | Combine linear/polar stages natively | All |
| `mirrored_feature` | Mirror a feature across a plane            | All  |
| `fillet_edges`     | Add fillets (rounded edges)                | All  |
| `chamfer_edges`    | Add chamfers (beveled edges)               | All  |

#### Sheet Metal (5 tools)

Requires the external FreeCAD SheetMetal Workbench. These tools create native,
editable SheetMetal `FeaturePython` history and a separate flat-pattern
manufacturing representation.

| Tool | Description | Mode |
| ---- | ----------- | ---- |
| `sheet_metal_capabilities` | Report workbench version and native operation availability | All |
| `create_sheet_metal_base` | Create a flat blank or open base-wall profile from a sketch | All |
| `create_sheet_metal_feature` | Add typed flanges, folds, hems, reliefs, junctions, extensions, bends, or solid conversion | All |
| `unfold_sheet_metal` | Create a parametric unfold using explicit neutral-axis data | All |
| `inspect_sheet_metal` | Inspect thickness, bend faces, feature history, and unfold readiness | All |

#### View & Display (10 common tools)

| Tool                        | Description                                                   | Mode |
| --------------------------- | ------------------------------------------------------------- | ---- |
| `get_screenshot`            | Return the FreeCAD view as MCP image content                  | GUI  |
| `open_image`                | Open a local drawing or saved screenshot                      | Both |
| `open_image_tiles`          | Return a numbered overview plus enlarged overlapping tiles   | Both |
| `compare_images`            | Required major-feature/seed comparison for drawing reconstruction | Both |
| `evaluate_model_checkpoint` | Optional deterministic continue/rework assessment             | Both |
| `set_view_angle`            | Set camera to a standard view                                 | GUI  |
| `fit_all`                   | Fit all visible objects in the view                           | GUI  |
| `set_camera_position`       | Set position, target, screen-up, projection, scale, and roll  | GUI  |
| `get_camera_state`          | Read reproducible camera projection and orientation state     | GUI  |
| `set_visual_properties`     | Set visibility, RGB color, and/or display mode                | GUI  |
| `workbench`                 | List or activate a FreeCAD workbench                          | All  |

### Agent engineering guidance

Detailed modeling policy lives in the repository Skill:

```text
.agents/skills/freecad-engineering/SKILL.md
```

The root `AGENTS.md` is a short Codex router to `$freecad-engineering`; Cline
uses `.clinerules/freecad-modeling.md`. When the server runs from the repository checkout, MCP clients can read the
same Skill from `freecad://skills/freecad-engineering`. Prompts and
`freecad://best-practices` provide routing/context rather than copied policies.

The Skill classifies likely stock and manufacturing process, covers milling,
turning, and sheet-metal strategies, and requires native editable parametric
structure unless the user explicitly requests direct B-rep output.
`execute_python`, `safe_execute`, and `run_macro` remain available.

For drawing/sketch input, the Skill requires saving every explicit non-starred
source dimension before modeling. Each identifier must drive the model through a
named constraint or connected Spreadsheet alias. `compare_images` is required
after every major feature and before any pattern multiplies a seed element.

After any model creation or geometry change, call `validate_parametric_model`
immediately before the final response and summarize the actual Bodies, Tips,
history, sketches, solver state, source-dimension usage, Spreadsheet connectivity,
direct solids, and warnings. For drawing/sketch tasks, pass the complete saved
identifier list as `required_dimension_names`. The report is informative and
does not by itself prove drawing correspondence.

#### Validation & diagnostics (5 tools)

| Tool | Description | Mode |
| --- | --- | --- |
| `validate_object` | Check one object's shape and FreeCAD state | All |
| `validate_document` | Check geometric health across a document | All |
| `validate_parametric_model` | Compact final report; paged/expanded parametric diagnostics on request | All |
| `undo_if_invalid` | Undo after invalid document state | All |
| `safe_execute` | Run Python with optional validation and rollback | All |

#### History (1 tool)

| Tool      | Description                                   | Mode |
| --------- | --------------------------------------------- | ---- |
| `history` | Undo, redo, or inspect available history steps | All  |

#### Export/Import (2 tools)

| Tool     | Description                                      | Mode |
| -------- | ------------------------------------------------ | ---- |
| `export` | Export to STEP, IGES, STL, 3MF, or OBJ          | All  |
| `import` | Import STEP or STL into a FreeCAD document      | All  |

#### Macro Management (6 tools)

| Tool                         | Description                                    | Mode |
| ---------------------------- | ---------------------------------------------- | ---- |
| `list_macros`                | List all available FreeCAD macros              | All  |
| `run_macro`                  | Execute a macro by name                        | All  |
| `create_macro`               | Create a new macro file                        | All  |
| `read_macro`                 | Read macro source code                         | All  |
| `delete_macro`               | Delete a user macro                            | All  |
| `create_macro_from_template` | Create macro from template (basic, part, etc.) | All  |

#### Parts Library (2 tools)

| Tool                       | Description                           | Mode |
| -------------------------- | ------------------------------------- | ---- |
| `list_parts_library`       | List parts in FreeCAD's parts library | All  |
| `insert_part_from_library` | Insert a part from the library        | All  |

---

## For Developers

This section covers development setup, contributing, and working with the codebase.

## Robust MCP Server Development

### Prerequisites

- [mise](https://mise.jdx.dev/) - Tool version manager
- [FreeCAD](https://www.freecadweb.org/) 0.21+ or 1.0+

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise via the Official mise installer script (if not already installed)
curl https://mise.run | sh

# Install all tools (Python 3.11, uv, just, pre-commit)
mise trust
mise install

# Set up the development environment
just setup
```

This installs:

- **Python 3.11** - Required for FreeCAD ABI compatibility
- **uv** - Fast Python package manager
- **just** - Command runner for development workflows
- **pre-commit** - Git hooks for code quality

### MCP Client Configuration (Development)

Create a `.mcp.json` file in the project directory:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "/path/to/mise/shims/uv",
      "args": ["run", "--project", "/path/to/freecad-addon-robust-mcp-server", "freecad-mcp"],
      "env": {
        "FREECAD_MODE": "xmlrpc",
        "FREECAD_SOCKET_HOST": "localhost",
        "FREECAD_XMLRPC_PORT": "9875",
        "PATH": "/path/to/mise/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

**Replace the paths with your actual paths:**

| Placeholder                                 | Description                     | Example                                        |
| ------------------------------------------- | ------------------------------- | ---------------------------------------------- |
| `/path/to/mise/shims/uv`                    | Full path to uv via mise shims  | `~/.local/share/mise/shims/uv`                 |
| `/path/to/freecad-addon-robust-mcp-server`  | Project directory               | `/home/me/dev/freecad-addon-robust-mcp-server` |
| `/path/to/mise/shims`                       | mise shims directory for PATH   | `~/.local/share/mise/shims`                    |

**Finding your mise shims path:**

```bash
mise where uv | sed 's|/installs/.*|/shims|'
# Example: /home/user/.local/share/mise/shims (on Linux) or ~/.local/share/mise/shims (on macOS)
```

### Development Workflow

Commands are organized into modules. Use `just` to see top-level commands, or `just list-<module>` to see module-specific commands.

```bash
# Show top-level commands and available modules
just

# Show commands in a specific module
just list-mcp           # Robust MCP Server commands
just list-freecad       # FreeCAD plugin/macro commands
just list-install       # Installation commands
just list-quality       # Code quality commands
just list-testing       # Test commands
just list-docker        # Docker commands
just list-documentation # Documentation commands
just list-dev           # Development utilities

# List ALL commands from all modules
just list-all

# Install/update dependencies
just install::mcp-server

# Run all checks (linting, type checking, tests)
just all

# Quality commands
just quality::lint       # Run ruff linter
just quality::typecheck  # Run mypy type checker
just quality::format     # Format code
just quality::check      # Run all pre-commit hooks

# Testing commands
just testing::unit       # Run unit tests
just testing::cov        # Run tests with coverage
just testing::integration # Run integration tests

# Run the Robust MCP Server (or with debug logging)
just mcp::run
just mcp::run-debug

# Docker commands
just docker::build        # Build image for local architecture
just docker::build-multi  # Build multi-arch image (amd64 + arm64)
just docker::run          # Run container
```

### Running FreeCAD with the MCP Bridge

#### GUI Mode (recommended for development)

```bash
# Start FreeCAD with auto-started bridge
just freecad::run-gui
```

#### Headless Mode (for automation/CI)

```bash
just freecad::run-headless
```

### Running Tests

```bash
# Unit tests only (no FreeCAD required)
just testing::unit

# Unit tests with coverage
just testing::cov

# Integration tests (requires running FreeCAD bridge)
just testing::integration

# Integration tests with automatic FreeCAD startup
just testing::integration-auto
```

### Code Quality

The project uses strict code quality checks via pre-commit:

- **Ruff** - Linting and formatting
- **MyPy** - Type checking
- **Bandit** - Security scanning
- **Codespell** - Spell checking
- **Secrets scanning** - Gitleaks, detect-secrets, TruffleHog

```bash
# Run all pre-commit hooks
just quality::check

# Run security/secrets scans
just quality::security
just quality::secrets
```

---

## Architecture

See the [detailed architecture document](docs/development/architecture-detailed.md) for design documentation covering:

- Module structure
- Bridge communication protocols
- Tool registration patterns
- FreeCAD plugin architecture

---

## Acknowledgements

This project was developed after analyzing several existing FreeCAD Robust MCP implementations. We are grateful to these projects for their pioneering work and the ideas they contributed to the FreeCAD + AI ecosystem:

### Related Projects

- **[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp)** (MIT License) - The queue-based thread safety pattern and XML-RPC protocol design (port 9875) were directly inspired by this project. Our implementation maintains protocol compatibility while being a complete rewrite with additional features.

- **[jango-blockchained/mcp-freecad](https://github.com/jango-blockchained/mcp-freecad)** - Inspired our connection recovery mechanisms and multi-mode architecture approach.

- **[contextform/freecad-mcp](https://github.com/contextform/freecad-mcp)** - Informed our comprehensive PartDesign and Part workbench tool coverage.

- **[ATOI-Ming/FreeCAD-MCP](https://github.com/ATOI-Ming/FreeCAD-MCP)** - Inspired our macro development toolkit including templates, validation, and automatic imports.

- **[bonninr/freecad_mcp](https://github.com/bonninr/freecad_mcp)** - Influenced our simple socket-based communication approach.

See [docs/COMPARISON.md](docs/COMPARISON.md) for a detailed analysis of these implementations and the design decisions they informed.

---

## License

MIT License - see [LICENSE](LICENSE) for details.
