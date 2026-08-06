"""Tests for the main server module."""

import json
import os
import queue
import sys
import threading
import time
from typing import BinaryIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from freecad_mcp.config import FreecadMode

# Default argv for main() tests to avoid argparse errors
DEFAULT_ARGV: list[str] = ["freecad-mcp"]


def _read_until_with_timeout(
    pipe: BinaryIO,
    marker: bytes,
    timeout: float,
) -> bytes:
    """Read subprocess output until ``marker`` appears or the timeout expires.

    ``os.set_blocking`` is not available for Windows anonymous pipes. A daemon
    reader thread sends complete lines through a queue, while the test thread
    retains a strict timeout.
    """

    line_queue: queue.Queue[bytes | BaseException | None] = queue.Queue()

    def _reader() -> None:
        try:
            while True:
                line = pipe.readline()
                if not line:
                    line_queue.put(None)
                    return
                line_queue.put(line)
        except BaseException as exc:  # pragma: no cover - defensive subprocess IO
            line_queue.put(exc)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout
    output = bytearray()

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return bytes(output)

        try:
            item = line_queue.get(timeout=remaining)
        except queue.Empty:
            return bytes(output)

        if item is None:
            return bytes(output)
        if isinstance(item, BaseException):
            raise item

        output.extend(item)
        if marker in output:
            return bytes(output)


def _readline_with_timeout(pipe: BinaryIO, timeout: float) -> bytes:
    """Read at most one complete binary line with a cross-platform timeout."""

    return _read_until_with_timeout(pipe, marker=b"\n", timeout=timeout)


class TestGetInstanceId:
    """Tests for get_instance_id function."""

    def test_returns_string(self):
        """Instance ID should be a string."""
        from freecad_mcp.server import get_instance_id

        instance_id = get_instance_id()
        assert isinstance(instance_id, str)

    def test_returns_uuid_format(self):
        """Instance ID should be a valid UUID format."""
        from freecad_mcp.server import get_instance_id

        instance_id = get_instance_id()
        # UUID format: 8-4-4-4-12 hex characters
        parts = instance_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_consistent_across_calls(self):
        """Instance ID should be consistent within a process."""
        from freecad_mcp.server import get_instance_id

        id1 = get_instance_id()
        id2 = get_instance_id()
        assert id1 == id2


class TestGetBridge:
    """Tests for get_bridge function."""

    @pytest.mark.asyncio
    async def test_raises_when_not_initialized(self):
        """Should raise RuntimeError when bridge is not initialized."""
        import freecad_mcp.server as server_module

        # Save original bridge
        original_bridge = server_module._bridge

        try:
            # Set bridge to None
            server_module._bridge = None

            with pytest.raises(RuntimeError, match="not initialized"):
                await server_module.get_bridge()
        finally:
            # Restore original bridge
            server_module._bridge = original_bridge

    @pytest.mark.asyncio
    async def test_returns_bridge_when_initialized(self):
        """Should return bridge when it's initialized."""
        import freecad_mcp.server as server_module

        # Save original bridge
        original_bridge = server_module._bridge

        try:
            # Set up mock bridge
            mock_bridge = MagicMock()
            server_module._bridge = mock_bridge

            bridge = await server_module.get_bridge()
            assert bridge is mock_bridge
        finally:
            # Restore original bridge
            server_module._bridge = original_bridge


class TestLifespan:
    """Tests for the lifespan context manager."""

    @pytest.mark.asyncio
    async def test_embedded_mode_initialization(self):
        """Should initialize embedded bridge in embedded mode."""
        import freecad_mcp.server as server_module

        mock_config = MagicMock()
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.freecad_path = None

        mock_embedded_bridge = AsyncMock()
        mock_embedded_bridge.get_freecad_version = AsyncMock(
            return_value={"version": "1.0.0", "gui_available": False}
        )

        with (
            patch.object(server_module, "get_config", return_value=mock_config),
            patch(
                "freecad_mcp.bridge.embedded.EmbeddedBridge",
                return_value=mock_embedded_bridge,
            ) as mock_embedded_class,
        ):
            mock_server = MagicMock()

            async with server_module.lifespan(mock_server):
                # Bridge should be initialized
                mock_embedded_class.assert_called_once_with(freecad_path=None)
                mock_embedded_bridge.connect.assert_called_once()

            # After exiting, disconnect should be called
            mock_embedded_bridge.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_xmlrpc_mode_initialization(self):
        """Should initialize XML-RPC bridge in xmlrpc mode."""
        import freecad_mcp.server as server_module

        mock_config = MagicMock()
        mock_config.mode = FreecadMode.XMLRPC
        mock_config.socket_host = "localhost"
        mock_config.xmlrpc_port = 9875
        mock_config.require_bounded_xmlrpc = False

        mock_xmlrpc_bridge = AsyncMock()
        mock_xmlrpc_bridge.get_freecad_version = AsyncMock(
            return_value={"version": "1.0.0", "gui_available": True}
        )

        with (
            patch.object(server_module, "get_config", return_value=mock_config),
            patch(
                "freecad_mcp.bridge.xmlrpc.XmlRpcBridge",
                return_value=mock_xmlrpc_bridge,
            ) as mock_xmlrpc_class,
        ):
            mock_server = MagicMock()

            async with server_module.lifespan(mock_server):
                mock_xmlrpc_class.assert_called_once_with(
                    host="localhost",
                    port=9875,
                    require_bounded_execute=False,
                )
                mock_xmlrpc_bridge.connect.assert_called_once()

            mock_xmlrpc_bridge.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_socket_mode_initialization(self):
        """Should initialize socket bridge in socket mode."""
        import freecad_mcp.server as server_module

        mock_config = MagicMock()
        mock_config.mode = FreecadMode.SOCKET
        mock_config.socket_host = "localhost"
        mock_config.socket_port = 9876

        mock_socket_bridge = AsyncMock()
        mock_socket_bridge.get_freecad_version = AsyncMock(
            return_value={"version": "1.0.0", "gui_available": True}
        )

        with (
            patch.object(server_module, "get_config", return_value=mock_config),
            patch(
                "freecad_mcp.bridge.socket.SocketBridge",
                return_value=mock_socket_bridge,
            ) as mock_socket_class,
        ):
            mock_server = MagicMock()

            async with server_module.lifespan(mock_server):
                mock_socket_class.assert_called_once_with(host="localhost", port=9876)
                mock_socket_bridge.connect.assert_called_once()

            mock_socket_bridge.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_version_lookup_is_deferred_during_startup(self):
        """Startup should not block on an additional version queue request."""
        import freecad_mcp.server as server_module

        mock_config = MagicMock()
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.freecad_path = None

        mock_bridge = AsyncMock()
        mock_bridge.get_freecad_version = AsyncMock()

        with (
            patch.object(server_module, "get_config", return_value=mock_config),
            patch(
                "freecad_mcp.bridge.embedded.EmbeddedBridge",
                return_value=mock_bridge,
            ),
        ):
            mock_server = MagicMock()

            async with server_module.lifespan(mock_server):
                mock_bridge.connect.assert_awaited_once()

            mock_bridge.get_freecad_version.assert_not_called()


class TestRegisterAllComponents:
    """Tests for register_all_components function."""

    def test_registers_tools(self):
        """Should register all tool categories."""
        from freecad_mcp.server import mcp

        # The function is called at module load, but we can verify
        # that the mcp instance exists and has tools registered
        assert mcp is not None
        assert mcp.name == "freecad-mcp"


class TestMain:
    """Tests for main function."""

    def test_main_prints_instance_id(self):
        """Main should print instance ID on startup when FREECAD_MCP_TESTING is set."""
        import freecad_mcp.server as server_module
        from freecad_mcp.config import TransportType

        mock_config = MagicMock()
        mock_config.log_level = "INFO"
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.transport = TransportType.STDIO

        with (
            patch.object(sys, "argv", DEFAULT_ARGV),
            patch.object(server_module, "get_config", return_value=mock_config),
            patch.object(server_module.mcp, "run") as mock_run,
            patch("builtins.print") as mock_print,
            patch.dict(os.environ, {"FREECAD_MCP_TESTING": "1"}),
        ):
            # Mock run to exit immediately
            mock_run.return_value = None

            server_module.main()

            # Check that instance ID was printed to stderr (not stdout, to avoid
            # corrupting JSON-RPC in stdio mode)
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any("FREECAD_MCP_INSTANCE_ID=" in call for call in print_calls)
            # Verify it was printed to stderr
            instance_id_call = next(
                call
                for call in mock_print.call_args_list
                if "FREECAD_MCP_INSTANCE_ID=" in str(call)
            )
            assert instance_id_call.kwargs.get("file") == sys.stderr

    def test_main_no_instance_id_without_testing_env(self):
        """Main should NOT print instance ID when FREECAD_MCP_TESTING is unset."""
        import freecad_mcp.server as server_module
        from freecad_mcp.config import TransportType

        mock_config = MagicMock()
        mock_config.log_level = "INFO"
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.transport = TransportType.STDIO

        # Ensure FREECAD_MCP_TESTING is not set
        env_without_testing = {
            k: v for k, v in os.environ.items() if k != "FREECAD_MCP_TESTING"
        }

        with (
            patch.object(sys, "argv", DEFAULT_ARGV),
            patch.object(server_module, "get_config", return_value=mock_config),
            patch.object(server_module.mcp, "run") as mock_run,
            patch("builtins.print") as mock_print,
            patch.dict(os.environ, env_without_testing, clear=True),
        ):
            # Mock run to exit immediately
            mock_run.return_value = None

            server_module.main()

            # Check that instance ID was NOT printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert not any("FREECAD_MCP_INSTANCE_ID=" in call for call in print_calls)

    def test_main_http_transport(self):
        """Main should start HTTP transport when configured."""
        import freecad_mcp.server as server_module
        from freecad_mcp.config import TransportType

        mock_config = MagicMock()
        mock_config.log_level = "INFO"
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.transport = TransportType.HTTP
        mock_config.http_host = "127.0.0.1"
        mock_config.http_port = 8080
        mock_config.access_token = "x" * 64
        mock_config.http_json_response = True
        mock_config.http_unstructured_tool_results = True
        mock_config.log_tool_arguments = True
        mock_config.log_tool_results = True
        mock_config.log_value_max_chars = 4_000
        mock_config.wire_audit_enabled = True
        mock_config.wire_audit_dir = "logs/mcp-wire"
        mock_config.wire_save_raw = True
        mock_config.wire_console_body = True
        mock_config.wire_console_max_chars = 50_000
        mock_config.wire_capture_max_bytes = 128 * 1024 * 1024
        mock_config.wire_validate = True

        upstream_app = object()
        with (
            patch.object(sys, "argv", DEFAULT_ARGV),
            patch.object(server_module, "get_config", return_value=mock_config),
            patch.object(
                server_module.mcp,
                "streamable_http_app",
                return_value=upstream_app,
            ) as mock_http_app,
            patch("uvicorn.run") as mock_uvicorn_run,
            patch("builtins.print"),
        ):
            server_module.main()

            mock_http_app.assert_called_once_with()
            mock_uvicorn_run.assert_called_once()
            call_args, call_kwargs = mock_uvicorn_run.call_args

            from freecad_mcp.http_auth import (
                McpMethodAuditMiddleware,
                StaticBearerAuthMiddleware,
            )

            auth_app = call_args[0]
            assert isinstance(auth_app, StaticBearerAuthMiddleware)
            assert isinstance(auth_app.app, McpMethodAuditMiddleware)
            assert auth_app.app.app is upstream_app
            assert auth_app.app.wire_audit_enabled is True
            assert auth_app.app.wire_save_raw is True
            assert auth_app.app.wire_console_body is True
            assert auth_app.app.wire_validate is True
            assert call_kwargs["host"] == "127.0.0.1"
            assert call_kwargs["port"] == 8080
            assert call_kwargs["log_level"] == "info"

    def test_main_stdio_transport(self):
        """Main should start stdio transport by default."""
        import freecad_mcp.server as server_module
        from freecad_mcp.config import TransportType

        mock_config = MagicMock()
        mock_config.log_level = "INFO"
        mock_config.mode = FreecadMode.EMBEDDED
        mock_config.transport = TransportType.STDIO

        with (
            patch.object(sys, "argv", DEFAULT_ARGV),
            patch.object(server_module, "get_config", return_value=mock_config),
            patch.object(server_module.mcp, "run") as mock_run,
            patch("builtins.print"),
        ):
            server_module.main()

            # Should call run without transport arguments (stdio is default)
            mock_run.assert_called_once_with()


class TestStdioProtocolCleanliness:
    """Tests to ensure stdio mode produces clean JSON-RPC output.

    These tests verify that stdout contains ONLY valid JSON-RPC messages,
    with no debug output, print statements, or other text that would corrupt
    the MCP protocol. This is critical for compatibility with MCP clients
    like Claude Desktop.

    The bug this catches: Any print() to stdout (instead of stderr) will
    cause MCP clients to fail with JSON parse errors like:
        "Unexpected token 'F', "FREECAD_MC"... is not valid JSON"
    """

    def test_no_stdout_before_jsonrpc(self):
        """Verify no stray output appears on stdout before JSON-RPC messages.

        This test spawns the MCP server as a subprocess and validates that
        ALL stdout output is valid JSON-RPC. Any non-JSON output on stdout
        will corrupt the MCP protocol.
        """
        import json
        import os
        import subprocess

        # Start the MCP server process
        # Use a non-existent FreeCAD host so it won't actually connect
        proc = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "freecad_mcp.server",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **dict(os.environ),
                "FREECAD_MODE": "xmlrpc",
                "FREECAD_XMLRPC_PORT": "59999",  # Non-existent port
                "FREECAD_SOCKET_HOST": "localhost",
            },
        )

        try:
            # Ensure pipes are available
            assert proc.stdin is not None
            assert proc.stdout is not None

            # Send a minimal MCP initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"},
                },
            }
            request_bytes = json.dumps(init_request).encode() + b"\n"
            proc.stdin.write(request_bytes)
            proc.stdin.flush()

            # Read one protocol line with a bounded, cross-platform wait.
            # Zero bytes are acceptable here: this regression test verifies that
            # any output that does appear is valid JSON-RPC, not that startup must
            # complete against the intentionally unavailable FreeCAD endpoint.
            stdout_data = _readline_with_timeout(proc.stdout, timeout=1.0)

            # Validate that ALL stdout is valid JSON-RPC
            # Each line should be a valid JSON object
            stdout_text = stdout_data.decode("utf-8", errors="replace")
            lines = [line.strip() for line in stdout_text.split("\n") if line.strip()]

            for line in lines:
                try:
                    parsed = json.loads(line)
                    # Should be a JSON-RPC message (has jsonrpc field)
                    assert "jsonrpc" in parsed, (
                        f"stdout contains JSON but not JSON-RPC: {line[:100]}"
                    )
                except json.JSONDecodeError as e:
                    pytest.fail(
                        f"stdout contains non-JSON output which corrupts MCP protocol!\n"
                        f"Invalid line: {line[:200]!r}\n"
                        f"JSON error: {e}\n\n"
                        f"All stdout lines:\n{stdout_text[:1000]}"
                    )

        finally:
            # Clean up the process
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    def test_instance_id_on_stderr_not_stdout(self) -> None:
        """Verify FREECAD_MCP_INSTANCE_ID is printed to stderr, not stdout.

        The instance ID must go to stderr because stdout is reserved for
        JSON-RPC messages in stdio mode.
        """
        import os
        import subprocess

        proc = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "freecad_mcp.server",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **dict(os.environ),
                "FREECAD_MODE": "xmlrpc",
                "FREECAD_XMLRPC_PORT": "59999",
                "FREECAD_SOCKET_HOST": "localhost",
                "FREECAD_MCP_TESTING": "1",  # Enable stderr instance ID output
            },
        )

        try:
            # Ensure pipes are available
            assert proc.stdout is not None
            assert proc.stderr is not None

            # The instance ID is written as one flushed stderr line. Reading it
            # in a bounded helper thread works for both POSIX descriptors and
            # Windows anonymous subprocess pipes.
            max_wait = 5.0
            stderr_data = _read_until_with_timeout(
                proc.stderr,
                marker=b"FREECAD_MCP_INSTANCE_ID=",
                timeout=max_wait,
            )
            stderr_text = stderr_data.decode("utf-8", errors="replace")

            # Instance ID should be in stderr
            assert "FREECAD_MCP_INSTANCE_ID=" in stderr_text, (
                f"Instance ID not found in stderr after {max_wait}s.\n"
                f"stderr: {stderr_text[:500]}"
            )

            # No initialize request was sent, so stdout should remain empty.
            stdout_data = _readline_with_timeout(proc.stdout, timeout=0.25)
            stdout_text = stdout_data.decode("utf-8", errors="replace")

            # Instance ID should NOT be in stdout
            assert "FREECAD_MCP_INSTANCE_ID=" not in stdout_text, (
                f"Instance ID incorrectly appears in stdout, corrupting MCP protocol!\n"
                f"stdout: {stdout_text[:500]}"
            )

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


class TestHttpToolResultCompatibility:
    """Regression tests for conservative HTTP tool result formatting."""

    @pytest.mark.asyncio
    async def test_unstructured_default_always_returns_content_blocks(self):
        from freecad_mcp.server import FreecadFastMCP

        server = FreecadFastMCP(
            "compatibility-test",
            default_structured_output=False,
        )

        @server.tool()
        async def sample_tool() -> dict[str, object]:
            return {"name": "Document1", "path": None}

        listed = await server.list_tools()
        tool = next(item for item in listed if item.name == "sample_tool")
        assert tool.outputSchema is None

        result = await server.call_tool("sample_tool", {})
        assert isinstance(result, list)
        assert result
        assert getattr(result[0], "type", None) == "text"
        assert "Document1" in getattr(result[0], "text", "")


class TestMcpInstructions:
    """Tests for protocol-level server instructions."""

    def test_server_exposes_engineering_instructions(self):
        """FastMCP initialization should include the required agent workflow."""
        from freecad_mcp import server as server_module

        instructions = server_module.MCP_INSTRUCTIONS
        assert server_module.mcp.instructions == instructions
        normalized_instructions = " ".join(instructions.split())

        required_clauses = (
            "inspect the intended document and existing feature history",
            "use select_subshapes rather than manual Face/Edge enumeration",
            "save every explicit non-starred dimension",
            "bind the alias to the dimensional constraint expression path",
            "compare_images",
            "Compare one seed element before applying any pattern",
            "validate_parametric_model",
            "required_dimension_names",
        )
        for clause in required_clauses:
            assert clause in normalized_instructions

    @pytest.mark.asyncio
    async def test_tools_list_does_not_duplicate_global_guidance_or_schema_titles(self):
        """Global policy is delivered once; tool metadata stays context-efficient."""
        from freecad_mcp import server as server_module

        listed = await server_module.mcp.list_tools()
        descriptions = "\n".join(tool.description or "" for tool in listed)
        payload = json.dumps(
            [tool.model_dump(by_alias=True, exclude_none=True) for tool in listed],
            ensure_ascii=False,
        )

        assert (
            "inspect the intended document and existing feature history"
            not in descriptions
        )
        assert max(len(tool.description or "") for tool in listed) <= 360
        assert '"title":' not in payload
        assert len(payload) < 90_000
