"""Read-only MCP resources for FreeCAD state and engineering Skill routing.

Use ``resources/list`` for the runtime inventory. Detailed engineering policy is
exposed through ``freecad://skills/freecad-engineering`` and its task references.
"""

from freecad_mcp.resources.freecad import register_resources

__all__ = ["register_resources"]
