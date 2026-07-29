"""Tests for PartDesign tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult, ObjectInfo


class TestPartDesignTools:
    """Tests for PartDesign tools."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock MCP server that captures tool registrations."""
        mcp = MagicMock()
        mcp._registered_tools = {}

        def tool_decorator():
            def wrapper(func):
                mcp._registered_tools[func.__name__] = func
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
        """Register PartDesign tools and return the registered functions."""
        from freecad_mcp.tools.partdesign import register_partdesign_tools

        async def get_bridge():
            return mock_bridge

        register_partdesign_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_create_partdesign_body(self, register_tools, mock_bridge):
        """create_partdesign_body should create a body container via create_object."""
        mock_object = ObjectInfo(
            name="Body",
            label="Body",
            type_id="PartDesign::Body",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_body = register_tools["create_partdesign_body"]
        result = await create_body(name="Body")

        assert result["name"] == "Body"
        assert result["type_id"] == "PartDesign::Body"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_sketch(self, register_tools, mock_bridge):
        """create_sketch should create a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "label": "Sketch",
                    "type_id": "Sketcher::SketchObject",
                    "support": "XY_Plane",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_sketch = register_tools["create_sketch"]
        result = await create_sketch(body_name="Body", plane="XY_Plane")

        assert result["name"] == "Sketch"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_sketch_supports_explicit_face_and_datum_names(
        self, register_tools, mock_bridge
    ):
        """create_sketch should expose explicit object faces and datum supports."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "label": "Sketch",
                    "type_id": "Sketcher::SketchObject",
                    "support": "Pad.Face6",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_sketch = register_tools["create_sketch"]
        await create_sketch(body_name="Body", plane="Pad.Face6")
        generated_code = mock_bridge.execute_python.await_args.args[0]

        assert 'plane.rsplit(".", 1)' in generated_code
        assert 'TypeId", "") != "PartDesign::Plane"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_geometry_batches_operations_atomically(
        self, register_tools, mock_bridge
    ):
        """Mixed geometry edits should use one bridge call and one transaction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 3,
                    "operation_results": [
                        {"op": "add_rectangle", "geometry_indices": [0, 1, 2, 3]},
                        {"op": "add_circle", "geometry_index": 4},
                        {
                            "op": "toggle_construction",
                            "geometry_index": 0,
                            "is_construction": True,
                        },
                    ],
                    "sketch_status": {"profile_ready": True},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["edit_sketch_geometry"](
            sketch_name="Sketch",
            operations=[
                {"op": "add_rectangle", "x": 0, "y": 0, "width": 20, "height": 10},
                {"op": "add_circle", "center_x": 10, "center_y": 5, "radius": 2},
                {"op": "toggle_construction", "geometry_index": 0},
            ],
        )

        assert result["operations_applied"] == 3
        assert result["sketch_status"]["profile_ready"] is True
        mock_bridge.execute_python.assert_awaited_once()
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'doc.openTransaction("Edit Sketch Geometry")' in generated_code
        assert generated_code.count("doc.recompute()") == 1
        assert '"add_rectangle"' in generated_code
        assert '"toggle_construction"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_geometry_supports_every_replaced_operation(
        self, register_tools, mock_bridge
    ):
        """The consolidated contract should cover every removed geometry tool."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 12,
                    "operation_results": [],
                    "sketch_status": {},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )
        operations = [
            {"op": "add_rectangle", "x": 0, "y": 0, "width": 10, "height": 5},
            {"op": "add_circle", "center_x": 0, "center_y": 0, "radius": 2},
            {"op": "add_line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
            {
                "op": "add_arc",
                "center_x": 0,
                "center_y": 0,
                "radius": 2,
                "start_angle": 0,
                "end_angle": 90,
            },
            {"op": "add_point", "x": 1, "y": 2},
            {
                "op": "add_ellipse",
                "center_x": 0,
                "center_y": 0,
                "major_radius": 3,
                "minor_radius": 2,
            },
            {"op": "add_polygon", "center_x": 0, "center_y": 0, "radius": 3},
            {
                "op": "add_slot",
                "center1_x": 0,
                "center1_y": 0,
                "center2_x": 5,
                "center2_y": 0,
                "radius": 1,
            },
            {"op": "add_bspline", "points": [[0, 0], [1, 1], [2, 0]]},
            {
                "op": "add_external_geometry",
                "object_name": "Pad",
                "element": "Edge1",
            },
            {"op": "delete_geometry", "geometry_index": 0},
            {"op": "toggle_construction", "geometry_index": 1},
        ]

        await register_tools["edit_sketch_geometry"]("Sketch", operations)
        generated_code = mock_bridge.execute_python.await_args.args[0]
        for operation in operations:
            assert f'"{operation["op"]}"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_geometry_rejects_invalid_payload_before_freecad(
        self, register_tools, mock_bridge
    ):
        """Invalid dimensions should fail without starting a FreeCAD operation."""
        with pytest.raises(ValueError, match="width must be positive"):
            await register_tools["edit_sketch_geometry"](
                "Sketch",
                [{"op": "add_rectangle", "x": 0, "y": 0, "width": 0, "height": 5}],
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_batches_named_generic_and_delete(
        self, register_tools, mock_bridge
    ):
        """Constraint edits should share one transaction and preserve generic access."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 4,
                    "operation_results": [
                        {"op": "horizontal", "constraint_index": 0},
                        {"op": "distance", "constraint_index": 1},
                        {"op": "add_constraint", "constraint_index": 2},
                        {"op": "delete_constraint", "deleted_constraint_index": 0},
                    ],
                    "sketch_status": {"solver": {"status": "under_constrained"}},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["edit_sketch_constraints"](
            "Sketch",
            [
                {"op": "horizontal", "geometry1": 0},
                {"op": "distance", "geometry1": 0, "value": 20},
                {
                    "op": "add_constraint",
                    "constraint_type": "Diameter",
                    "geometry1": 1,
                    "value": 4,
                },
                {"op": "delete_constraint", "constraint_index": 0},
            ],
        )

        assert result["operations_applied"] == 4
        mock_bridge.execute_python.assert_awaited_once()
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'doc.openTransaction("Edit Sketch Constraints")' in generated_code
        assert generated_code.count("doc.recompute()") == 1
        assert '"Diameter"' in generated_code
        assert '"delete_constraint"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_supports_every_replaced_operation(
        self, register_tools, mock_bridge
    ):
        """The consolidated contract should accept every removed constraint tool."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 15,
                    "operation_results": [],
                    "sketch_status": {},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )
        operations = [
            {
                "op": "add_constraint",
                "constraint_type": "Diameter",
                "geometry1": 0,
                "value": 4,
            },
            {"op": "horizontal", "geometry1": 0},
            {"op": "vertical", "geometry1": 1},
            {
                "op": "coincident",
                "geometry1": 0,
                "point1": 2,
                "geometry2": 1,
                "point2": 1,
            },
            {"op": "parallel", "geometry1": 0, "geometry2": 2},
            {"op": "perpendicular", "geometry1": 0, "geometry2": 1},
            {"op": "tangent", "geometry1": 3, "geometry2": 4},
            {"op": "equal", "geometry1": 3, "geometry2": 4},
            {"op": "distance", "geometry1": 0, "value": 20},
            {
                "op": "distance_x",
                "geometry1": 0,
                "point1": 1,
                "value": 5,
            },
            {
                "op": "distance_y",
                "geometry1": 0,
                "point1": 1,
                "value": 6,
            },
            {"op": "radius", "geometry1": 3, "value": 2},
            {"op": "angle", "geometry1": 0, "value": 45},
            {"op": "fix", "geometry1": 0, "point1": 1},
            {"op": "delete_constraint", "constraint_index": 0},
        ]

        await register_tools["edit_sketch_constraints"]("Sketch", operations)

        generated_code = mock_bridge.execute_python.await_args.args[0]
        for operation in operations:
            assert f'"{operation["op"]}"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_rejects_missing_semantic_arguments(
        self, register_tools, mock_bridge
    ):
        """Named constraints should require the geometry/value they operate on."""
        with pytest.raises(ValueError, match="distance requires value"):
            await register_tools["edit_sketch_constraints"](
                "Sketch", [{"op": "distance", "geometry1": 0}]
            )
        with pytest.raises(ValueError, match="parallel requires geometry2"):
            await register_tools["edit_sketch_constraints"](
                "Sketch", [{"op": "parallel", "geometry1": 0}]
            )
        mock_bridge.execute_python.assert_not_awaited()

    def test_legacy_sketch_edit_tools_are_not_registered(self, register_tools):
        """Only the two consolidated sketch-edit entry points should remain public."""
        removed = {
            "add_sketch_rectangle",
            "add_sketch_circle",
            "add_sketch_line",
            "add_sketch_arc",
            "add_sketch_point",
            "add_sketch_ellipse",
            "add_sketch_polygon",
            "add_sketch_slot",
            "add_sketch_bspline",
            "add_external_geometry",
            "delete_sketch_geometry",
            "toggle_construction",
            "add_sketch_constraint",
            "constrain_horizontal",
            "constrain_vertical",
            "constrain_coincident",
            "constrain_parallel",
            "constrain_perpendicular",
            "constrain_tangent",
            "constrain_equal",
            "constrain_distance",
            "constrain_distance_x",
            "constrain_distance_y",
            "constrain_radius",
            "constrain_angle",
            "constrain_fix",
            "delete_sketch_constraint",
        }
        assert "edit_sketch_geometry" in register_tools
        assert "edit_sketch_constraints" in register_tools
        assert removed.isdisjoint(register_tools)


    @pytest.mark.asyncio
    async def test_pad_sketch(self, register_tools, mock_bridge):
        """pad_sketch should extrude a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pad",
                    "label": "Pad",
                    "type_id": "PartDesign::Pad",
                    "validated": True,
                    "added_volume": 1000.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        result = await pad_sketch(sketch_name="Sketch", length=10)

        assert result["name"] == "Pad"
        assert result["type_id"] == "PartDesign::Pad"
        generated_code = mock_bridge.execute_python.call_args.args[0]
        assert "_validate_additive_feature(pad, body, base_shape)" in generated_code
        assert "body volume did not increase" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_pad_sketch_accepts_world_space_direction(
        self, register_tools, mock_bridge
    ):
        """pad_sketch should resolve Reversed from a requested world direction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pad",
                    "label": "Pad",
                    "type_id": "PartDesign::Pad",
                    "validated": True,
                    "added_volume": 50.0,
                    "sketch_normal": [0.0, 1.0, 0.0],
                    "effective_direction": [0.0, -1.0, 0.0],
                    "reversed": True,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        result = await pad_sketch(
            sketch_name="Sketch", length=10, direction=[0.0, -1.0, 0.0]
        )

        assert result["effective_direction"] == [0.0, -1.0, 0.0]
        generated_code = mock_bridge.execute_python.call_args.args[0]
        assert "requested_direction = [0.0, -1.0, 0.0]" in generated_code
        assert "sketch.getGlobalPlacement().Rotation.multVec" in generated_code

    @pytest.mark.asyncio
    async def test_pad_sketch_rejects_missing_additive_evidence(
        self, register_tools, mock_bridge
    ):
        """pad_sketch should reject successful execution without volume evidence."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pad",
                    "validated": False,
                    "added_volume": 0.0,
                    "solid_count": 1,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        with pytest.raises(ValueError, match="additive validation contract"):
            await pad_sketch(sketch_name="Sketch", length=10)

    @pytest.mark.asyncio
    async def test_pad_sketch_checks_optional_solid_count_when_present(
        self, register_tools, mock_bridge
    ):
        """Optional diagnostics remain strict when the API includes them."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pad",
                    "validated": True,
                    "added_volume": 10.0,
                    "solid_count": 2,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        with pytest.raises(ValueError, match="expected one solid"):
            await pad_sketch(sketch_name="Sketch", length=10)

    @pytest.mark.asyncio
    async def test_pad_sketch_rejects_inconsistent_optional_volume_snapshots(
        self, register_tools, mock_bridge
    ):
        """Volume snapshots are checked when a bridge version returns them."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pad",
                    "validated": True,
                    "base_volume": 100.0,
                    "result_volume": 150.0,
                    "added_volume": 40.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        with pytest.raises(ValueError, match="inconsistent additive volume"):
            await pad_sketch(sketch_name="Sketch", length=10)

    @pytest.mark.asyncio
    async def test_pocket_sketch(self, register_tools, mock_bridge):
        """pocket_sketch should cut into solid via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pocket",
                    "label": "Pocket",
                    "type_id": "PartDesign::Pocket",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pocket_sketch = register_tools["pocket_sketch"]
        result = await pocket_sketch(sketch_name="Sketch", length=5)

        assert result["name"] == "Pocket"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_revolution_sketch(self, register_tools, mock_bridge):
        """revolution_sketch should revolve a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Revolution",
                    "label": "Revolution",
                    "type_id": "PartDesign::Revolution",
                    "validated": True,
                    "added_volume": 200.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        revolution = register_tools["revolution_sketch"]
        result = await revolution(
            sketch_name="Sketch001",
            angle=360,
            axis="Base_Z",
            doc_name="MultiBody",
        )

        assert result["name"] == "Revolution"
        generated_code = mock_bridge.execute_python.call_args.args[0]
        assert (
            '_resolve_body_origin_feature(body, f"{axis_ref}_Axis")' in generated_code
        )
        assert "getGlobalPlacement" in generated_code
        assert "_validate_additive_feature(rev, body, base_shape)" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_groove_sketch(self, register_tools, mock_bridge):
        """groove_sketch should cut by revolving via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Groove",
                    "label": "Groove",
                    "type_id": "PartDesign::Groove",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        groove = register_tools["groove_sketch"]
        result = await groove(sketch_name="Sketch", angle=180)

        assert result["name"] == "Groove"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_fillet_edges(self, register_tools, mock_bridge):
        """fillet_edges should add rounded edges via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fillet",
                    "label": "Fillet",
                    "type_id": "PartDesign::Fillet",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        fillet = register_tools["fillet_edges"]
        result = await fillet(object_name="Pad", radius=2.0)

        assert result["name"] == "Fillet"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_chamfer_edges(self, register_tools, mock_bridge):
        """chamfer_edges should add beveled edges via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Chamfer",
                    "label": "Chamfer",
                    "type_id": "PartDesign::Chamfer",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        chamfer = register_tools["chamfer_edges"]
        result = await chamfer(object_name="Pad", size=1.0)

        assert result["name"] == "Chamfer"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_hole(self, register_tools, mock_bridge):
        """create_hole should create parametric holes via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Hole",
                    "label": "Hole",
                    "type_id": "PartDesign::Hole",
                    "validated": True,
                    "removed_volume": 100.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        create_hole = register_tools["create_hole"]
        result = await create_hole(sketch_name="HoleSketch", diameter=6.0, depth=10.0)

        assert result["name"] == "Hole"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_hole_rejects_object_only_success_payload(
        self, register_tools, mock_bridge
    ):
        """An existing Hole object is not proof of successful geometry."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Hole",
                    "label": "Hole",
                    "type_id": "PartDesign::Hole",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        create_hole = register_tools["create_hole"]
        with pytest.raises(ValueError, match="validation contract"):
            await create_hole(sketch_name="HoleSketch")

    @pytest.mark.asyncio
    async def test_create_hole_embeds_strict_freecad_validation(
        self, register_tools, mock_bridge
    ):
        """create_hole should validate geometry, history, and actual subtraction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Hole",
                    "validated": True,
                    "removed_volume": 100.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        create_hole = register_tools["create_hole"]
        result = await create_hole(
            sketch_name="HoleSketch",
            diameter=5.0,
            hole_type="ThroughAll",
            doc_name="HoleTest",
        )

        assert result["validated"] is True
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'support_type == "PartDesign::Plane"' in generated_code
        assert "create_cylindrical_cut" in generated_code
        assert "circle_probe_volumes" in generated_code
        mock_bridge.execute_python.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_hole_rejects_unsupported_depth_type(
        self, register_tools, mock_bridge
    ):
        """create_hole should reject depth modes unavailable in FreeCAD 1.0."""
        create_hole = register_tools["create_hole"]

        with pytest.raises(ValueError, match=r"Dimension.*ThroughAll"):
            await create_hole(sketch_name="HoleSketch", hole_type="UpToFirst")

        mock_bridge.execute_python.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_hole_rejects_invalid_dimensions(
        self, register_tools, mock_bridge
    ):
        """create_hole should reject non-positive diameter and depth early."""
        create_hole = register_tools["create_hole"]

        with pytest.raises(ValueError, match="diameter"):
            await create_hole(sketch_name="HoleSketch", diameter=0)
        with pytest.raises(ValueError, match="depth"):
            await create_hole(sketch_name="HoleSketch", depth=-1)

        mock_bridge.execute_python.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_hole_maps_thread_profile_and_auto_direction(
        self, register_tools, mock_bridge
    ):
        """create_hole should map ISO aliases and try both directions by default."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Hole",
                    "validated": True,
                    "removed_volume": 100.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )
        create_hole = register_tools["create_hole"]

        await create_hole(
            sketch_name="HoleSketch",
            threaded=True,
            thread_type="ISO",
            thread_size="M6",
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "resolved_thread_profile = 'ISOMetricProfile'" in generated_code
        assert "[False, True]" in generated_code

    @pytest.mark.asyncio
    async def test_create_cylindrical_cut(self, register_tools, mock_bridge):
        """create_cylindrical_cut should validate an explicit-axis cut."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "OilHole",
                    "label": "OilHole",
                    "type_id": "PartDesign::SubtractiveCylinder",
                    "validated": True,
                    "removed_volume": 250.0,
                    "axis_removed_volume": 250.0,
                    "axis_origin": [0.0, -19.0, 105.0],
                    "axis_direction": [0.0, 0.0, -1.0],
                    "diameter": 10.0,
                    "depth": 12.5,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_cut = register_tools["create_cylindrical_cut"]
        result = await create_cut(
            body_name="Body",
            axis_origin=[0, -19, 105],
            axis_direction=[0, 0, -1],
            diameter=10,
            depth=12.5,
            name="OilHole",
        )

        assert result["validated"] is True
        assert result["removed_volume"] == 250.0
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'body.newObject("PartDesign::SubtractiveCylinder"' in generated_code
        assert "FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), direction)" in generated_code
        assert "axis_removed_volume" in generated_code

    @pytest.mark.asyncio
    async def test_create_cylindrical_cut_rejects_invalid_axis(
        self, register_tools, mock_bridge
    ):
        """Explicit cylindrical-cut axes must be three-dimensional and non-zero."""
        create_cut = register_tools["create_cylindrical_cut"]

        with pytest.raises(ValueError, match="three components"):
            await create_cut(
                body_name="Body",
                axis_origin=[0, 0, 0],
                axis_direction=[0, 1],
                diameter=5,
                depth=10,
            )
        with pytest.raises(ValueError, match="non-zero"):
            await create_cut(
                body_name="Body",
                axis_origin=[0, 0, 0],
                axis_direction=[0, 0, 0],
                diameter=5,
                depth=10,
            )

        mock_bridge.execute_python.assert_not_called()

    @pytest.mark.asyncio
    async def test_linear_pattern(self, register_tools, mock_bridge):
        """linear_pattern should create linear pattern via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "LinearPattern",
                    "label": "LinearPattern",
                    "type_id": "PartDesign::LinearPattern",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        pattern = register_tools["linear_pattern"]
        result = await pattern(
            feature_name="Pad", direction="X", length=50, occurrences=5
        )

        assert result["name"] == "LinearPattern"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_polar_pattern(self, register_tools, mock_bridge):
        """polar_pattern should create circular pattern via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "PolarPattern",
                    "label": "PolarPattern",
                    "type_id": "PartDesign::PolarPattern",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        pattern = register_tools["polar_pattern"]
        result = await pattern(feature_name="Pad", axis="Z", angle=360, occurrences=6)

        assert result["name"] == "PolarPattern"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_mirrored_feature(self, register_tools, mock_bridge):
        """mirrored_feature should mirror a feature via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Mirrored",
                    "label": "Mirrored",
                    "type_id": "PartDesign::Mirrored",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        mirrored = register_tools["mirrored_feature"]
        result = await mirrored(feature_name="Pad", plane="XY")

        assert result["name"] == "Mirrored"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_loft_sketches(self, register_tools, mock_bridge):
        """loft_sketches should create a loft via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Loft",
                    "label": "Loft",
                    "type_id": "PartDesign::AdditiveLoft",
                    "validated": True,
                    "added_volume": 150.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        loft = register_tools["loft_sketches"]
        result = await loft(sketch_names=["Sketch", "Sketch001"])

        assert result["name"] == "Loft"
        generated_code = mock_bridge.execute_python.call_args.args[0]
        assert "_validate_additive_feature(loft, body, base_shape)" in generated_code
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_sweep_sketch(self, register_tools, mock_bridge):
        """sweep_sketch should sweep a profile via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sweep",
                    "label": "Sweep",
                    "type_id": "PartDesign::AdditivePipe",
                    "validated": True,
                    "added_volume": 125.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        sweep = register_tools["sweep_sketch"]
        result = await sweep(profile_sketch="Profile", spine_sketch="Spine")

        assert result["name"] == "Sweep"
        generated_code = mock_bridge.execute_python.call_args.args[0]
        assert "_validate_additive_feature(sweep, body, base_shape)" in generated_code
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign datum features

    @pytest.mark.asyncio
    async def test_create_datum_plane(self, register_tools, mock_bridge):
        """create_datum_plane should create a reference plane."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumPlane",
                    "label": "DatumPlane",
                    "type_id": "PartDesign::Plane",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_plane = register_tools["create_datum_plane"]
        result = await create_datum_plane(
            body_name="Body", offset=10.0, base_plane="XY_Plane"
        )

        assert result["name"] == "DatumPlane"
        assert result["type_id"] == "PartDesign::Plane"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_datum_line(self, register_tools, mock_bridge):
        """create_datum_line should create a reference line."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumLine",
                    "label": "DatumLine",
                    "type_id": "PartDesign::Line",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_line = register_tools["create_datum_line"]
        result = await create_datum_line(body_name="Body", base_axis="X_Axis")

        assert result["name"] == "DatumLine"
        assert result["type_id"] == "PartDesign::Line"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_datum_point(self, register_tools, mock_bridge):
        """create_datum_point should create a reference point."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumPoint",
                    "label": "DatumPoint",
                    "type_id": "PartDesign::Point",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_point = register_tools["create_datum_point"]
        result = await create_datum_point(body_name="Body", position=[10.0, 20.0, 30.0])

        assert result["name"] == "DatumPoint"
        assert result["type_id"] == "PartDesign::Point"
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign dress-up features

    @pytest.mark.asyncio
    async def test_draft_feature(self, register_tools, mock_bridge):
        """draft_feature should add draft angle to faces."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Draft",
                    "label": "Draft",
                    "type_id": "PartDesign::Draft",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        draft_feature = register_tools["draft_feature"]
        result = await draft_feature(
            object_name="Pad", angle=5.0, plane="XY", faces=["Face1", "Face2"]
        )

        assert result["name"] == "Draft"
        assert result["type_id"] == "PartDesign::Draft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_thickness_feature(self, register_tools, mock_bridge):
        """thickness_feature should shell a solid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Thickness",
                    "label": "Thickness",
                    "type_id": "PartDesign::Thickness",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        thickness_feature = register_tools["thickness_feature"]
        result = await thickness_feature(
            object_name="Pad", thickness=2.0, faces_to_remove=["Face1"]
        )

        assert result["name"] == "Thickness"
        assert result["type_id"] == "PartDesign::Thickness"
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign subtractive features

    @pytest.mark.asyncio
    async def test_subtractive_loft(self, register_tools, mock_bridge):
        """subtractive_loft should cut material with a loft."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "SubtractiveLoft",
                    "label": "SubtractiveLoft",
                    "type_id": "PartDesign::SubtractiveLoft",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        subtractive_loft = register_tools["subtractive_loft"]
        result = await subtractive_loft(sketch_names=["Sketch", "Sketch001"])

        assert result["name"] == "SubtractiveLoft"
        assert result["type_id"] == "PartDesign::SubtractiveLoft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_subtractive_pipe(self, register_tools, mock_bridge):
        """subtractive_pipe should cut material by sweeping."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "SubtractivePipe",
                    "label": "SubtractivePipe",
                    "type_id": "PartDesign::SubtractivePipe",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        subtractive_pipe = register_tools["subtractive_pipe"]
        result = await subtractive_pipe(profile_sketch="Profile", spine_sketch="Spine")

        assert result["name"] == "SubtractivePipe"
        assert result["type_id"] == "PartDesign::SubtractivePipe"
        mock_bridge.execute_python.assert_called_once()

    # Tests for sketch inspection

    @pytest.mark.asyncio
    async def test_get_sketch_info(self, register_tools, mock_bridge):
        """get_sketch_info should return sketch geometry and constraints."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "label": "Sketch",
                    "sketch_status": {
                        "geometry_count": 4,
                        "constraint_count": 8,
                        "solver": {
                            "status": "fully_constrained",
                            "solve_code": 0,
                            "fully_constrained": True,
                            "remaining_dof": 0,
                        },
                        "profile": {"state": "closed", "closed": True},
                        "profile_ready": True,
                    },
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_info = register_tools["get_sketch_info"]
        result = await get_info(sketch_name="Sketch")

        status = result["sketch_status"]
        assert status["geometry_count"] == 4
        assert status["constraint_count"] == 8
        assert status["solver"]["fully_constrained"] is True
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "sketch.solve()" in generated_code
        assert "sketch.DoF" in generated_code
        mock_bridge.execute_python.assert_called_once()


class TestOriginFeatureResolver:
    """Tests for Body-scoped origin feature resolution."""

    def test_resolves_numeric_suffixes_for_second_body(self):
        """Canonical names should resolve to Body001 origin features."""
        from freecad_mcp.tools._freecad_runtime_helpers import BODY_RUNTIME_HELPERS

        class Feature:
            def __init__(self, name):
                self.Name = name

        class Origin:
            pass

        class Body:
            pass

        origin = Origin()
        origin.OriginFeatures = [
            Feature("X_Axis001"),
            Feature("Y_Axis001"),
            Feature("Z_Axis001"),
            Feature("XY_Plane001"),
            Feature("XZ_Plane001"),
            Feature("YZ_Plane001"),
            Feature("Point001"),
        ]
        origin.OutList = []
        body = Body()
        body.Name = "Body001"
        body.Origin = origin

        namespace = {}
        exec(BODY_RUNTIME_HELPERS, namespace)  # noqa: S102
        resolve = namespace["_resolve_body_origin_feature"]

        assert resolve(body, "Z_Axis").Name == "Z_Axis001"
        assert resolve(body, "XZ_Plane").Name == "XZ_Plane001"
        assert resolve(body, "Point").Name == "Point001"
