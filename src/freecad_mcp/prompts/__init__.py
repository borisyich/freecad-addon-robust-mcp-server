"""Compact MCP prompt routers for FreeCAD engineering tasks.

Detailed engineering workflow policy lives in the ``freecad-engineering`` Skill;
registered prompts provide compatibility entrypoints and operation pointers.
"""

from freecad_mcp.prompts.freecad import register_prompts

__all__ = ["register_prompts"]
