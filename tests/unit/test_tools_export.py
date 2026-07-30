"""Tests for the consolidated import and export tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult


class TestExportTools:
    """Tests for import/export routing and validation."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock MCP server that respects explicit tool names."""
        mcp = MagicMock()
        mcp._registered_tools = {}

        def tool_decorator(name=None, **_kwargs):
            def wrapper(func):
                mcp._registered_tools[name or func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self):
        """Create a mock FreeCAD bridge."""
        return AsyncMock()

    @pytest.fixture
    def register_tools(self, mock_mcp, mock_bridge):
        """Register export tools and return the registered functions."""
        from freecad_mcp.tools.export import register_export_tools

        async def get_bridge():
            return mock_bridge

        register_export_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    def test_only_consolidated_tools_are_registered(self, register_tools):
        """The public surface should contain only export and import."""
        assert set(register_tools) == {"export", "import"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("file_format", "expected_method"),
        [("step", "shape.exportStep"), ("iges", "shape.exportIges")],
    )
    async def test_export_routes_brep_formats(
        self, register_tools, mock_bridge, file_format, expected_method
    ):
        """STEP and IGES should use precise BREP export, not meshing."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "format": file_format,
                    "path": f"/tmp/part.{file_format}",
                    "object_count": 2,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["export"](
            file_format=file_format,
            file_path=f"/tmp/part.{file_format}",
            object_names=["Body", "Fixture"],
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert expected_method in code
        assert "Part.makeCompound" in code
        assert "MeshPart.meshFromShape" not in code
        assert result["format"] == file_format
        assert result["object_count"] == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("file_format", ["stl", "3mf", "obj"])
    async def test_export_routes_mesh_formats(
        self, register_tools, mock_bridge, file_format
    ):
        """Mesh formats should share one meshing path and honor tolerance."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "format": file_format,
                    "path": f"/tmp/part.{file_format}",
                    "object_count": 1,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["export"](
            file_format=file_format,
            file_path=f"/tmp/part.{file_format}",
            object_names=["Body"],
            mesh_tolerance=0.025,
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert "MeshPart.meshFromShape" in code
        assert "LinearDeflection=0.025" in code
        assert "final_mesh.write" in code
        assert result["format"] == file_format

    @pytest.mark.asyncio
    async def test_export_rejects_invalid_mesh_tolerance_before_bridge(
        self, register_tools, mock_bridge
    ):
        """Invalid mesh settings must not execute code in FreeCAD."""
        with pytest.raises(ValueError, match="mesh_tolerance must be positive"):
            await register_tools["export"](
                file_format="stl", file_path="/tmp/part.stl", mesh_tolerance=0
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_export_rejects_unknown_format_before_bridge(
        self, register_tools, mock_bridge
    ):
        """Unsupported formats must fail before touching FreeCAD."""
        with pytest.raises(ValueError, match="Unsupported export format"):
            await register_tools["export"](
                file_format="fcstd", file_path="/tmp/part.FCStd"
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("file_format", "expected_module"), [("step", "Part"), ("stl", "Mesh")]
    )
    async def test_import_routes_supported_formats_with_consistent_result(
        self, register_tools, mock_bridge, file_format, expected_module
    ):
        """Both import formats should report all newly imported objects."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "format": file_format,
                    "document": "Target",
                    "objects": ["Imported001", "Imported002"],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["import"](
            file_format=file_format,
            file_path=f"/tmp/input.{file_format}",
            doc_name="Target",
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert f"import {expected_module}" in code
        assert f"{expected_module}.insert" in code
        assert "before_count = len(doc.Objects)" in code
        assert result["objects"] == ["Imported001", "Imported002"]
        assert result["document"] == "Target"

    @pytest.mark.asyncio
    async def test_import_rejects_unknown_format_before_bridge(
        self, register_tools, mock_bridge
    ):
        """The import tool accepts only formats with implemented behavior."""
        with pytest.raises(ValueError, match="Unsupported import format"):
            await register_tools["import"](
                file_format="obj", file_path="/tmp/input.obj"
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_export_propagates_bridge_failure(self, register_tools, mock_bridge):
        """FreeCAD execution failures should remain visible to the agent."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="permission denied",
                execution_time_ms=5.0,
                error_type="PermissionError",
                error_traceback="Traceback: PermissionError: permission denied",
            )
        )

        with pytest.raises(ValueError, match="PermissionError"):
            await register_tools["export"](
                file_format="step", file_path="/protected/part.step"
            )
