"""Tool fallback for MCP clients that do not expose prompt controls."""

from typing import Any


def register_prompt_access_tools(mcp: Any) -> None:
    """Register prompt discovery/rendering through the ordinary tool surface."""

    @mcp.tool()
    async def get_freecad_prompt(
        name: str = "",
        arguments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """List or render registered FreeCAD MCP prompts; example: name="modify_existing_model", arguments={"model_path":"part.FCStd","change_request":"add pocket"}."""
        prompts = await mcp.list_prompts()
        catalog = [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": [
                    {
                        "name": argument.name,
                        "description": argument.description,
                        "required": bool(argument.required),
                    }
                    for argument in (prompt.arguments or [])
                ],
            }
            for prompt in prompts
        ]
        normalized_name = name.strip()
        if not normalized_name:
            return {
                "success": True,
                "mode": "list",
                "native_mcp_method": "prompts/list",
                "prompts": catalog,
            }

        available = {item["name"] for item in catalog}
        if normalized_name not in available:
            raise ValueError(
                f"Unknown FreeCAD MCP prompt: {normalized_name!r}; "
                f"available={sorted(available)}"
            )

        rendered = await mcp.get_prompt(normalized_name, arguments or {})
        if hasattr(rendered, "model_dump"):
            prompt_result = rendered.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
        else:
            prompt_result = rendered
        return {
            "success": True,
            "mode": "render",
            "native_mcp_method": "prompts/get",
            "name": normalized_name,
            "prompt": prompt_result,
        }
