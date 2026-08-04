"""FreeCAD Robust MCP Server - Main entry point.

This module provides the main Robust MCP Server implementation for FreeCAD
integration with AI assistants (Claude, GPT, and other MCP-compatible tools).
It exposes tools, resources, and prompts for interacting with FreeCAD.

Features:
    - Full Python console access (GUI and headless modes)
    - Document and object management
    - PartDesign workflow (sketches, pads, pockets, fillets)
    - Import/export (STEP, STL, OBJ, IGES)
    - Macro management
    - Screenshot capture
    - Multiple connection modes (embedded, XML-RPC, socket)

Example:
    Run as a module::

        $ python -m freecad_mcp.server

    Or use the installed command::

        $ freecad-mcp

    With environment variables::

        $ FREECAD_MODE=socket FREECAD_SOCKET_HOST=localhost freecad-mcp

    Show help::

        $ freecad-mcp --help
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from freecad_mcp.config import FreecadMode, TransportType, get_config

if TYPE_CHECKING:
    from freecad_mcp.bridge.base import FreecadBridge

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Generate unique instance ID at module load time
# This ID is stable for the lifetime of this server process
INSTANCE_ID: str = str(uuid.uuid4())

MCP_INSTRUCTIONS = """Use the FreeCAD engineering workflow for mechanical modeling.
Before modifying geometry:
- inspect the intended document and existing feature history;
- reuse one explicit document and one PartDesign Body;
- establish drawing-view to FreeCAD-plane correspondence;
- for drawing/sketch input, save every explicit non-starred dimension under a
  stable identifier before modeling.
Prefer standard MCP tools. Use execute_python or safe_execute only when
a required operation is unavailable or broken.
After every major feature:
- recompute;
- inspect the result;
- for drawing reconstruction, compare the equivalent reference/candidate view
  with compare_images;
- correct the causal feature if geometry differs from the target.
Compare one seed element before applying any pattern.
Before completing a geometry-changing task, call
validate_parametric_model and report significant findings. For drawing/sketch
input, pass all saved dimension identifiers as required_dimension_names.
"""

# Global bridge instance (initialized on startup via lifespan)
_bridge: Any = None


def get_instance_id() -> str:
    """Get the unique instance ID for this Robust MCP Server process.

    Returns:
        The UUID string that uniquely identifies this server instance.
    """
    return INSTANCE_ID


async def get_bridge() -> "FreecadBridge":
    """Get the active FreeCAD bridge.

    Returns:
        The active FreecadBridge instance.

    Raises:
        RuntimeError: If bridge is not initialized.
    """
    if _bridge is None:
        msg = "FreeCAD bridge not initialized"
        raise RuntimeError(msg)
    return _bridge


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage FreeCAD bridge lifecycle.

    This async context manager initializes the FreeCAD bridge on startup
    and disconnects it on shutdown.

    Args:
        _server: The FastMCP server instance (unused).

    Yields:
        None - the bridge is stored in the global _bridge variable.
    """
    global _bridge
    config = get_config()

    logger.info("Initializing FreeCAD bridge...")
    bridge: FreecadBridge

    if config.mode == FreecadMode.EMBEDDED:
        from freecad_mcp.bridge.embedded import EmbeddedBridge

        bridge = EmbeddedBridge(
            freecad_path=str(config.freecad_path) if config.freecad_path else None,
        )
        logger.info("Using embedded bridge (headless mode)")

    elif config.mode == FreecadMode.XMLRPC:
        from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

        bridge = XmlRpcBridge(
            host=config.socket_host,
            port=config.xmlrpc_port,
            require_bounded_execute=config.require_bounded_xmlrpc,
        )
        logger.info(
            "Using XML-RPC bridge: %s:%d", config.socket_host, config.xmlrpc_port
        )

    else:  # SOCKET mode
        from freecad_mcp.bridge.socket import SocketBridge

        bridge = SocketBridge(
            host=config.socket_host,
            port=config.socket_port,
        )
        logger.info(
            "Using socket bridge: %s:%d", config.socket_host, config.socket_port
        )

    try:
        await bridge.connect()
        _bridge = bridge
        logger.info("FreeCAD bridge connected and execution queue verified")
        logger.info(
            "FreeCAD version lookup is deferred until requested; MCP startup "
            "will not wait on a second GUI-queue operation"
        )
        yield
    finally:
        if _bridge is bridge:
            _bridge = None
        try:
            logger.info("Disconnecting FreeCAD bridge...")
            await bridge.disconnect()
        except Exception as exc:
            logger.warning("Could not disconnect FreeCAD bridge cleanly: %s", exc)


_SENSITIVE_LOG_KEY_PARTS = (
    "authorization",
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "credential",
)

_BINARY_LOG_KEY_PARTS = (
    "base64",
    "image_data",
    "binary",
)


def _sanitize_for_log(
    value: Any,
    *,
    key: str | None = None,
    max_chars: int = 4_000,
    depth: int = 0,
) -> Any:
    """Return a JSON-safe diagnostic representation without secrets or blobs."""
    normalized_key = (key or "").lower()
    if any(part in normalized_key for part in _SENSITIVE_LOG_KEY_PARTS):
        return "<redacted>"
    if any(part in normalized_key for part in _BINARY_LOG_KEY_PARTS):
        length = len(value) if hasattr(value, "__len__") else None
        return f"<binary omitted; length={length}>"
    if depth > 8:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return f"{value[:max_chars]}…<truncated; chars={len(value)}>"
    if isinstance(value, bytes):
        return f"<bytes omitted; length={len(value)}>"
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_for_log(
                item_value,
                key=str(item_key),
                max_chars=max_chars,
                depth=depth + 1,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_for_log(
                item,
                max_chars=max_chars,
                depth=depth + 1,
            )
            for item in value
        ]
    if hasattr(value, "model_dump"):
        try:
            return _sanitize_for_log(
                value.model_dump(),
                max_chars=max_chars,
                depth=depth + 1,
            )
        except Exception:
            pass
    return repr(value)


def _log_json(value: Any, *, max_chars: int = 4_000) -> str:
    """Serialize a sanitized value for one-line structured logs."""
    safe_value = _sanitize_for_log(value, max_chars=max_chars)
    return json.dumps(safe_value, ensure_ascii=False, sort_keys=True)


def _summarize_content_block(block: Any, *, max_chars: int) -> dict[str, Any]:
    block_type = str(getattr(block, "type", type(block).__name__))
    summary: dict[str, Any] = {"type": block_type}
    if block_type == "text":
        text = str(getattr(block, "text", ""))
        summary.update(
            {
                "chars": len(text),
                "preview": _sanitize_for_log(text, max_chars=min(max_chars, 500)),
            }
        )
    elif block_type == "image":
        data = getattr(block, "data", "") or ""
        summary.update(
            {
                "mimeType": getattr(block, "mimeType", None),
                "base64_chars": len(data),
                "approx_binary_bytes": (len(data) * 3) // 4,
            }
        )
    elif hasattr(block, "model_dump"):
        dumped = block.model_dump()
        summary["fields"] = sorted(dumped.keys())
    return summary


def _summarize_tool_result(result: Any, *, max_chars: int) -> dict[str, Any]:
    """Describe the outbound result shape without logging image/base64 payloads."""
    summary: dict[str, Any] = {"result_type": type(result).__name__}
    content = getattr(result, "content", None)
    if isinstance(content, list):
        summary["content_count"] = len(content)
        summary["content"] = [
            _summarize_content_block(block, max_chars=max_chars) for block in content
        ]
    elif isinstance(result, list):
        summary["content_count"] = len(result)
        summary["content"] = [
            _summarize_content_block(block, max_chars=max_chars) for block in result
        ]
    else:
        summary["content_present"] = content is not None

    if hasattr(result, "isError"):
        summary["isError"] = getattr(result, "isError")
    structured = getattr(result, "structuredContent", None)
    summary["structuredContent_present"] = structured is not None
    if isinstance(structured, dict):
        summary["structuredContent_keys"] = sorted(str(key) for key in structured)
    return summary


def _build_transport_security(config: Any) -> TransportSecuritySettings:
    """Allow loopback hosts plus one explicitly configured public tunnel host."""
    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]

    if config.public_host:
        public_host = config.public_host.strip().rstrip(".").lower()
        if not public_host or "://" in public_host or "/" in public_host:
            msg = "FREECAD_PUBLIC_HOST must be a hostname without scheme or path"
            raise ValueError(msg)
        allowed_hosts.extend([public_host, f"{public_host}:*"])
        allowed_origins.extend(
            [f"https://{public_host}", f"https://{public_host}:*"]
        )

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


class FreecadFastMCP(FastMCP):
    """FastMCP variant with explicit remote-client compatibility defaults.

    Some SaaS MCP runtimes still mishandle ``outputSchema`` /
    ``structuredContent`` and expect every tool result to contain classic MCP
    content blocks. For HTTP transport we can disable automatic structured
    output while preserving it for local stdio clients.

    The protocol-level tool logs are deliberately emitted here rather than
    relying only on ASGI-body inspection. They prove whether a parsed
    ``tools/call`` request actually reached FastMCP.
    """

    def __init__(
        self,
        *args: Any,
        default_structured_output: bool | None = None,
        log_tool_arguments: bool = False,
        log_tool_results: bool = False,
        log_value_max_chars: int = 4_000,
        **kwargs: Any,
    ) -> None:
        self._default_structured_output = default_structured_output
        self._log_tool_arguments = log_tool_arguments
        self._log_tool_results = log_tool_results
        self._log_value_max_chars = log_value_max_chars
        super().__init__(*args, **kwargs)

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("structured_output") is None:
            kwargs["structured_output"] = self._default_structured_output
        return super().tool(*args, **kwargs)

    async def list_tools(self) -> list[Any]:
        tools = await super().list_tools()
        logger.info("MCP tools/list completed: count=%d", len(tools))
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        started_at = time.perf_counter()
        logger.info("MCP tools/call started: tool=%s", name)
        if self._log_tool_arguments:
            logger.info(
                "MCP tools/call arguments: tool=%s arguments=%s",
                name,
                _log_json(arguments, max_chars=self._log_value_max_chars),
            )
        try:
            result = await super().call_tool(name, arguments)
            duration_ms = (time.perf_counter() - started_at) * 1000
            if self._log_tool_results:
                logger.info(
                    "MCP tools/call result: tool=%s summary=%s",
                    name,
                    _log_json(
                        _summarize_tool_result(
                            result, max_chars=self._log_value_max_chars
                        ),
                        max_chars=self._log_value_max_chars,
                    ),
                )
            logger.info(
                "MCP tools/call completed: tool=%s result_type=%s "
                "duration_ms=%.1f",
                name,
                type(result).__name__,
                duration_ms,
            )
            return result
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "MCP tools/call failed: tool=%s duration_ms=%.1f",
                name,
                duration_ms,
            )
            raise

# Create the Robust MCP Server instance with explicit DNS-rebinding protection.
_initial_config = get_config()
_default_structured_output: bool | None = None
if (
    _initial_config.transport == TransportType.HTTP
    and _initial_config.http_unstructured_tool_results
):
    _default_structured_output = False

mcp = FreecadFastMCP(
    name="freecad-mcp",
    instructions=MCP_INSTRUCTIONS,
    lifespan=lifespan,
    host=_initial_config.http_host,
    port=_initial_config.http_port,
    json_response=(
        _initial_config.http_json_response
        if _initial_config.transport == TransportType.HTTP
        else False
    ),
    default_structured_output=_default_structured_output,
    log_tool_arguments=_initial_config.log_tool_arguments,
    log_tool_results=_initial_config.log_tool_results,
    log_value_max_chars=_initial_config.log_value_max_chars,
    transport_security=_build_transport_security(_initial_config),
)


def register_all_components() -> None:
    """Register all MCP components (tools, resources, prompts)."""
    # Register tools
    from freecad_mcp.tools import register_all_tools

    register_all_tools(mcp, get_bridge)

    # Register resources
    from freecad_mcp.resources import register_resources

    register_resources(mcp, get_bridge)

    # Register prompts
    from freecad_mcp.prompts import register_prompts

    register_prompts(mcp, get_bridge)


# Register all components
register_all_components()


async def check_freecad_connection(
    mode: str | None = None, host: str | None = None, port: int | None = None
) -> bool:
    """Test FreeCAD bridge connection.

    Args:
        mode: Connection mode override (xmlrpc, socket, embedded).
        host: Host override for connection.
        port: Port override for connection.

    Returns:
        True if connection successful, False otherwise.
    """
    import os

    # Apply overrides to env
    if mode:
        os.environ["FREECAD_MODE"] = mode
    if host:
        os.environ["FREECAD_SOCKET_HOST"] = host
    if port:
        mode_val = mode or os.environ.get("FREECAD_MODE", "xmlrpc")
        if mode_val == "xmlrpc":
            os.environ["FREECAD_XMLRPC_PORT"] = str(port)
        else:
            os.environ["FREECAD_SOCKET_PORT"] = str(port)

    config = get_config()
    print(f"Testing connection to FreeCAD ({config.mode.value} mode)...")

    try:
        bridge: FreecadBridge
        if config.mode == FreecadMode.EMBEDDED:
            from freecad_mcp.bridge.embedded import EmbeddedBridge

            bridge = EmbeddedBridge(
                freecad_path=(
                    str(config.freecad_path) if config.freecad_path else None
                ),
            )
        elif config.mode == FreecadMode.XMLRPC:
            from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

            bridge = XmlRpcBridge(
                host=config.socket_host,
                port=config.xmlrpc_port,
                require_bounded_execute=config.require_bounded_xmlrpc,
            )
            print(f"  Host: {config.socket_host}:{config.xmlrpc_port}")
        else:
            from freecad_mcp.bridge.socket import SocketBridge

            bridge = SocketBridge(
                host=config.socket_host,
                port=config.socket_port,
            )
            print(f"  Host: {config.socket_host}:{config.socket_port}")

        await bridge.connect()
        if config.mode == FreecadMode.XMLRPC:
            from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

            xmlrpc_bridge = cast(XmlRpcBridge, bridge)
            queue_latency_ms = await xmlrpc_bridge.check_execution_queue(
                timeout_ms=5000
            )
            print(f"  Queue latency: {queue_latency_ms:.1f} ms")
            try:
                version_info = await xmlrpc_bridge.get_freecad_version(
                    timeout_ms=3000
                )
            except Exception as exc:
                print(f"  Warning: version lookup failed: {exc}")
                version_info = {
                    "version": "unknown",
                    "gui_available": "unknown",
                }
        else:
            try:
                version_info = await bridge.get_freecad_version()
            except Exception as exc:
                print(f"  Warning: version lookup failed: {exc}")
                version_info = {
                    "version": "unknown",
                    "gui_available": "unknown",
                }
        await bridge.disconnect()

        print("✓ Connection successful!")
        print(f"  FreeCAD version: {version_info.get('version', 'unknown')}")
        print(f"  GUI available: {version_info.get('gui_available', 'unknown')}")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def apply_cli_args_to_env(args: argparse.Namespace) -> None:
    """Apply CLI arguments as environment variables.

    CLI arguments override existing environment variables.

    Args:
        args: Parsed command-line arguments.
    """
    import os

    if args.mode:
        os.environ["FREECAD_MODE"] = args.mode
    if args.transport:
        os.environ["FREECAD_TRANSPORT"] = args.transport
    if args.host:
        os.environ["FREECAD_SOCKET_HOST"] = args.host
    if args.port:
        # Set appropriate port based on mode
        mode = os.environ.get("FREECAD_MODE", "xmlrpc")
        if mode == "xmlrpc":
            os.environ["FREECAD_XMLRPC_PORT"] = str(args.port)
        else:
            os.environ["FREECAD_SOCKET_PORT"] = str(args.port)
    if args.http_host:
        os.environ["FREECAD_HTTP_HOST"] = args.http_host
    if args.http_port:
        os.environ["FREECAD_HTTP_PORT"] = str(args.http_port)
    if args.log_level:
        os.environ["FREECAD_LOG_LEVEL"] = args.log_level


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="freecad-mcp",
        description="FreeCAD Robust MCP Server - Connect AI assistants to FreeCAD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  FREECAD_MODE           Connection mode: xmlrpc, socket, or embedded
                         (default: xmlrpc)
  FREECAD_SOCKET_HOST    Host for socket/XML-RPC connection (default: localhost)
  FREECAD_SOCKET_PORT    Port for socket connection (default: 9876)
  FREECAD_XMLRPC_PORT    Port for XML-RPC connection (default: 9875)
  FREECAD_TRANSPORT      Transport type: stdio or http (default: stdio)
  FREECAD_HTTP_HOST      Bind host for HTTP transport (default: 127.0.0.1)
  FREECAD_HTTP_PORT      Port for HTTP transport (default: 8000)
  FREECAD_ACCESS_TOKEN   Fixed Bearer token for HTTP transport (minimum 32 chars)
  FREECAD_PUBLIC_HOST    Public hostname allowed by MCP Host/Origin validation
  FREECAD_HTTP_JSON_RESPONSE
                         Use JSON responses for HTTP POST requests (default: true)
  FREECAD_HTTP_UNSTRUCTURED_TOOL_RESULTS
                         Disable structured tool output in HTTP mode for broad
                         SaaS compatibility (default: true)
  FREECAD_LOG_TOOL_ARGUMENTS
                         Log sanitized parsed tool arguments (default: false)
  FREECAD_LOG_TOOL_RESULTS
                         Log compact result/content summaries (default: false)
  FREECAD_LOG_VALUE_MAX_CHARS
                         Maximum retained string length in diagnostics (default: 4000)
  FREECAD_LOG_LEVEL      Logging level: DEBUG, INFO, WARNING, ERROR
                         (default: INFO)

Examples:
  # Start with default settings (XML-RPC mode, stdio transport)
  freecad-mcp

  # Use socket mode
  FREECAD_MODE=socket freecad-mcp

  # Use HTTP transport for remote access
  FREECAD_TRANSPORT=http FREECAD_HTTP_PORT=8080 freecad-mcp

  # Connect to remote FreeCAD instance
  FREECAD_SOCKET_HOST=192.168.1.100 freecad-mcp

Prerequisites:
  The FreeCAD Robust MCP Bridge must be running before starting this server.
  Start it via:
    - FreeCAD GUI: Install Robust MCP Bridge workbench, enable auto-start
    - Headless: just freecad::run-headless
    - Development: just freecad::run-gui
""",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Test FreeCAD connection and exit (doesn't start MCP server)",
    )

    parser.add_argument(
        "--mode",
        choices=["xmlrpc", "socket", "embedded"],
        help="Connection mode (overrides FREECAD_MODE env var)",
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        help="Transport type (overrides FREECAD_TRANSPORT env var)",
    )

    parser.add_argument(
        "--host",
        help="Host for FreeCAD connection (overrides FREECAD_SOCKET_HOST)",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port for FreeCAD connection (mode-dependent)",
    )

    parser.add_argument(
        "--http-host",
        help="Bind host for HTTP transport (overrides FREECAD_HTTP_HOST)",
    )

    parser.add_argument(
        "--http-port",
        type=int,
        help="Port for HTTP transport (overrides FREECAD_HTTP_PORT)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (overrides FREECAD_LOG_LEVEL)",
    )

    return parser.parse_args()


def main() -> None:
    """Run the FreeCAD Robust MCP Server."""
    # Parse arguments first - this handles --help without connecting to FreeCAD
    args = parse_args()

    # Handle --version
    if args.version:
        try:
            from importlib.metadata import version

            ver = version("freecad-mcp")
        except Exception:
            ver = "unknown"
        print(f"freecad-mcp {ver}")
        print(f"Instance ID: {INSTANCE_ID}")
        sys.exit(0)

    # Handle --check (test connection without starting MCP server)
    if args.check:
        import asyncio

        success = asyncio.run(
            check_freecad_connection(mode=args.mode, host=args.host, port=args.port)
        )
        sys.exit(0 if success else 1)

    # Apply CLI arguments as environment variables (they override existing ones)
    apply_cli_args_to_env(args)

    # Now get config (which reads from environment)
    config = get_config()

    # Set up logging
    logging.getLogger().setLevel(config.log_level)

    # Print instance ID to stderr only for test automation (when env var is set).
    # This avoids unwanted output during normal use.
    # Must use stderr because stdout is reserved for JSON-RPC in stdio mode.
    if os.environ.get("FREECAD_MCP_TESTING"):
        print(f"FREECAD_MCP_INSTANCE_ID={INSTANCE_ID}", file=sys.stderr, flush=True)

    logger.info("Starting FreeCAD Robust MCP Server")
    logger.info("Instance ID: %s", INSTANCE_ID)
    logger.info("Mode: %s", config.mode.value)
    logger.info("Transport: %s", config.transport.value)

    # Run the server
    if config.transport == TransportType.HTTP:
        import uvicorn

        from freecad_mcp.http_auth import (
            McpMethodAuditMiddleware,
            StaticBearerAuthMiddleware,
        )

        if not config.access_token:
            msg = (
                "FREECAD_ACCESS_TOKEN is required for HTTP transport. "
                "Use a random token containing at least 32 characters."
            )
            raise RuntimeError(msg)

        logger.info(
            "Starting authenticated HTTP transport on %s:%d",
            config.http_host,
            config.http_port,
        )
        logger.info(
            "HTTP compatibility: json_response=%s, unstructured_tool_results=%s",
            config.http_json_response,
            config.http_unstructured_tool_results,
        )
        logger.info(
            "Tool diagnostics: arguments=%s, results=%s, max_chars=%d",
            config.log_tool_arguments,
            config.log_tool_results,
            config.log_value_max_chars,
        )
        logger.info(
            "Wire audit: enabled=%s, save_raw=%s, console_body=%s, "
            "validate=%s, directory=%s",
            config.wire_audit_enabled,
            config.wire_save_raw,
            config.wire_console_body,
            config.wire_validate,
            config.wire_audit_dir,
        )
        if config.wire_save_raw:
            logger.warning(
                "Raw MCP wire auditing is enabled. Audit files may contain "
                "complete images, model data, local paths, and tool output."
            )
        mcp_app = McpMethodAuditMiddleware(
            mcp.streamable_http_app(),
            wire_audit_enabled=config.wire_audit_enabled,
            wire_audit_dir=config.wire_audit_dir,
            wire_save_raw=config.wire_save_raw,
            wire_console_body=config.wire_console_body,
            wire_console_max_chars=config.wire_console_max_chars,
            wire_capture_max_bytes=config.wire_capture_max_bytes,
            wire_validate=config.wire_validate,
        )

        app = StaticBearerAuthMiddleware(
            mcp_app,
            config.access_token,
        )
        uvicorn.run(
            app,
            host=config.http_host,
            port=config.http_port,
            log_level=config.log_level.lower(),
        )
    else:
        logger.info("Starting stdio transport")
        logger.info(
            "Waiting for MCP client connection (FreeCAD connection tested on first request)..."
        )
        logger.info(
            "Tip: Use 'freecad-mcp --check' to test FreeCAD connection directly"
        )
        mcp.run()


if __name__ == "__main__":
    main()
