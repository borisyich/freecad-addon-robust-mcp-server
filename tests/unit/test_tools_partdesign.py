"""Tests for PartDesign tools module."""

import inspect
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
        result = await create_sketch(body_name="Body")
        generated_code = mock_bridge.execute_python.await_args.args[0]

        assert result["name"] == "Sketch"
        assert "'XY_Plane'" in generated_code
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
        await create_sketch(
            body_name="Body",
            support={"kind": "feature_face", "feature": "Pad", "face": "Face6"},
        )
        generated_code = mock_bridge.execute_python.await_args.args[0]

        assert 'plane.rsplit(".", 1)' in generated_code
        assert 'TypeId", "") != "PartDesign::Plane"' in generated_code

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("support", "expected_reference"),
        [
            ({"kind": "origin_plane", "plane": "XZ_Plane"}, "XZ_Plane"),
            ({"kind": "body_tip_face", "face": "Face3"}, "Face3"),
            (
                {"kind": "feature_face", "feature": "Pad", "face": "Face6"},
                "Pad.Face6",
            ),
            ({"kind": "datum_plane", "name": "DP_OilHole"}, "DP_OilHole"),
        ],
    )
    async def test_create_sketch_normalizes_typed_support(
        self, register_tools, mock_bridge, support, expected_reference
    ):
        """Every typed support variant should reach the established resolver."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "label": "Sketch",
                    "type_id": "Sketcher::SketchObject",
                    "support": expected_reference,
                    "support_kind": support["kind"],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["create_sketch"](
            body_name="Body", support=support
        )
        generated_code = mock_bridge.execute_python.await_args.args[0]

        assert repr(expected_reference) in generated_code
        assert result["support_kind"] == support["kind"]

    def test_create_sketch_support_schema_is_discriminated(self):
        """The public schema must preserve variant discovery and face patterns."""
        from freecad_mcp.tools.partdesign import _SKETCH_SUPPORT_ADAPTER

        schema = _SKETCH_SUPPORT_ADAPTER.json_schema()
        assert schema["discriminator"]["propertyName"] == "kind"
        assert set(schema["discriminator"]["mapping"]) == {
            "origin_plane",
            "body_tip_face",
            "feature_face",
            "datum_plane",
        }
        assert (
            schema["$defs"]["BodyTipFaceSketchSupport"]["properties"]["face"]["pattern"]
            == r"^Face[1-9]\d*$"
        )

    def test_create_sketch_has_no_legacy_plane_parameter(self, register_tools):
        """The removed plane argument must not leak into the public tool signature."""
        parameters = inspect.signature(register_tools["create_sketch"]).parameters

        assert "plane" not in parameters
        assert "support" in parameters

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
                    "operations_applied": 13,
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
            {
                "op": "add_regular_polygon",
                "center_x": 0,
                "center_y": 0,
                "radius": 3,
            },
            {
                "op": "add_polyline",
                "points": [[0, 0], [3, 0], [3, 2]],
                "closed": True,
            },
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
    async def test_edit_sketch_geometry_supports_endpoint_radius_arc(
        self, register_tools, mock_bridge
    ):
        """Endpoint/radius arcs should generate deterministic minor-arc code."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 1,
                    "operation_results": [],
                    "sketch_status": {},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools["edit_sketch_geometry"](
            "Sketch",
            [
                {
                    "op": "add_arc",
                    "arc_mode": "endpoints_radius",
                    "x1": 0,
                    "y1": 0,
                    "x2": 20,
                    "y2": 0,
                    "radius": 15,
                    "arc_side": "left",
                }
            ],
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '"endpoints_radius"' in generated_code
        assert "Part.Arc(start, arc_midpoint, end)" in generated_code
        assert 'operation["arc_side"]' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_geometry_supports_tangent_fillet_arc(
        self, register_tools, mock_bridge
    ):
        """A radius fillet between two lines should use SketchObject.fillet."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 1,
                    "operation_results": [],
                    "sketch_status": {},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools["edit_sketch_geometry"](
            "Sketch",
            [
                {
                    "op": "add_arc",
                    "arc_mode": "tangent_fillet",
                    "line1_index": 0,
                    "line2_index": 1,
                    "radius": 4,
                }
            ],
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '"tangent_fillet"' in generated_code
        assert "sketch.fillet(" in generated_code
        assert "ref1 = (line1.StartPoint + line1.EndPoint) * 0.5" in generated_code
        assert "ref2 = (line2.StartPoint + line2.EndPoint) * 0.5" in generated_code
        assert "endpoint_pairs" not in generated_code
        assert "fillet_status" not in generated_code
        assert "after_count <= before_count" in generated_code
        assert '"trimmed_line_indices"' in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_geometry_rejects_impossible_endpoint_radius_arc(
        self, register_tools, mock_bridge
    ):
        """A chord longer than the diameter must fail before FreeCAD execution."""
        with pytest.raises(ValueError, match="farther apart than the diameter"):
            await register_tools["edit_sketch_geometry"](
                "Sketch",
                [
                    {
                        "op": "add_arc",
                        "arc_mode": "endpoints_radius",
                        "x1": 0,
                        "y1": 0,
                        "x2": 20,
                        "y2": 0,
                        "radius": 5,
                    }
                ],
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
    async def test_edit_sketch_constraints_supports_spreadsheet_expressions(
        self, register_tools, mock_bridge
    ):
        """Constraint expressions should be created, changed, and cleared in one API."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 3,
                    "operation_results": [],
                    "sketch_status": {},
                    "geometry": [],
                    "constraints": [],
                    "expressions": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools["edit_sketch_constraints"](
            "Sketch",
            [
                {
                    "op": "distance",
                    "geometry1": 0,
                    "value": 20,
                    "constraint_name": "PlateWidth",
                    "expression": "Dimensions.PlateWidth",
                },
                {
                    "op": "set_expression",
                    "constraint_index": 0,
                    "expression": "Dimensions.PlateWidth * 0.5",
                },
                {"op": "clear_expression", "constraint_index": 0},
            ],
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'rename_constraint(constraint_index, constraint_name)' in generated_code
        assert 'sketch.setExpression(expression_path, expression)' in generated_code
        assert 'f"Constraints[{constraint_index}]"' in generated_code
        assert '"set_expression"' in generated_code
        assert '"clear_expression"' in generated_code
        assert "existing_type not in dimensional_types" in generated_code
        assert "Expressions can be assigned only to dimensional" in generated_code
        assert "**_sketch_detailed_info(sketch)" in generated_code

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_rejects_incomplete_expression_edits(
        self, register_tools, mock_bridge
    ):
        with pytest.raises(ValueError, match="set_expression requires expression"):
            await register_tools["edit_sketch_constraints"](
                "Sketch", [{"op": "set_expression", "constraint_index": 0}]
            )
        with pytest.raises(ValueError, match="clear_expression requires"):
            await register_tools["edit_sketch_constraints"](
                "Sketch", [{"op": "clear_expression"}]
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_rejects_expression_on_geometric_constraint(
        self, register_tools, mock_bridge
    ):
        with pytest.raises(
            ValueError, match="expression is supported only for dimensional constraints"
        ):
            await register_tools["edit_sketch_constraints"](
                "Sketch",
                [{"op": "horizontal", "geometry1": 0,
                  "expression": "Dimensions.Width"}],
            )
        with pytest.raises(
            ValueError, match="expression is supported only for dimensional constraints"
        ):
            await register_tools["edit_sketch_constraints"](
                "Sketch",
                [{
                    "op": "add_constraint",
                    "constraint_type": "Horizontal",
                    "geometry1": 0,
                    "expression": "Dimensions.Width",
                }],
            )
        mock_bridge.execute_python.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_edit_sketch_constraints_embeds_fix_ratio_guard(
        self, register_tools, mock_bridge
    ):
        """Fix/Block edits must enforce the 50-percent geometry ceiling."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "operations_applied": 1,
                    "operation_results": [],
                    "sketch_status": {},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools["edit_sketch_constraints"](
            "Sketch", [{"op": "fix", "geometry1": 0}]
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'getattr(existing_constraint, "Type", "") == "Block"' in generated_code
        assert "projected_fix_count > geometry_count * 0.5" in generated_code
        assert "Cannot apply Fix/Block constraints" in generated_code
        assert "sketch geometry" in generated_code

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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                    "base_volume": 100.0,
                    "result_volume": 90.0,
                    "removed_volume": 10.0,
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        fillet = register_tools["fillet_edges"]
        result = await fillet(object_name="Pad", radius=2.0)

        assert result["name"] == "Fillet"
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '_require_current_body_tip(body, obj, "Fillet")' in generated_code
        assert "_validate_single_solid_feature" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        chamfer = register_tools["chamfer_edges"]
        result = await chamfer(object_name="Pad", size=1.0)

        assert result["name"] == "Chamfer"
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '_require_current_body_tip(body, obj, "Chamfer")' in generated_code
        assert "_validate_single_solid_feature" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
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
    async def test_create_hole_accepts_iso_fine_with_underscore(
        self, register_tools, mock_bridge
    ):
        """The documented ISO_FINE spelling must resolve to FreeCAD's enum."""
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
            thread_type="ISO_FINE",
            thread_size="M12x1.25",
        )

        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "resolved_thread_profile = 'ISOMetricFineProfile'" in generated_code
        assert "requested_size = 'M12x1.25'.strip()" in generated_code

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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        mirrored = register_tools["mirrored_feature"]
        result = await mirrored(feature_name="Pad", plane="XY")

        assert result["name"] == "Mirrored"
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '_require_current_body_tip(body, feature, "Mirrored feature")' in generated_code
        assert "body.Tip = feature" in generated_code
        assert "transform_mode = _configure_feature_transform_mode(mirror)" in generated_code
        assert "body.Tip = mirror" in generated_code
        assert "_validate_single_solid_feature(mirror, body)" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
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
                    "validated": True,
                    "base_plane": "XY_Plane",
                    "map_mode": "FlatFace",
                    "offset": 10.0,
                    "tip": "Pad",
                    "tip_preserved": True,
                    "status": [],
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
        assert result["validated"] is True
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "_feature_status_strings(datum)" in generated_code
        assert "Datum plane unexpectedly changed Body Tip" in generated_code
        assert "doc.removeObject(created_name)" in generated_code
        compile(generated_code, "<create-datum-plane>", "exec")
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                    "map_mode": "Deactivated",
                    "direction": [1.0, 0.0, 0.0],
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
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert 'datum.MapMode = "Deactivated"' in generated_code
        assert "FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), target_direction)" in generated_code
        assert "datum.Placement.Rotation.multVec" in generated_code
        assert "ObjectXY" not in generated_code
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
                    "validated": True,
                    "map_mode": "Deactivated",
                    "position": [10.0, 20.0, 30.0],
                    "position_error": 0.0,
                    "tip": "Pad",
                    "tip_preserved": True,
                    "status": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_point = register_tools["create_datum_point"]
        result = await create_datum_point(body_name="Body", position=[10.0, 20.0, 30.0])
        generated_code = mock_bridge.execute_python.await_args.args[0]

        assert result["name"] == "DatumPoint"
        assert result["type_id"] == "PartDesign::Point"
        assert result["validated"] is True
        assert 'datum.MapMode = "Deactivated"' in generated_code
        assert "datum.Placement = FreeCAD.Placement" in generated_code
        assert "_feature_status_strings(datum)" in generated_code
        assert "Datum point unexpectedly changed Body Tip" in generated_code
        assert "doc.removeObject(created_name)" in generated_code
        assert '_resolve_body_origin_feature(body, "Point")' not in generated_code
        compile(generated_code, "<create-datum-point>", "exec")
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
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
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '_require_current_body_tip(body, obj, "Draft")' in generated_code
        assert "_validated_shape_subelement_names" in generated_code
        assert "_validate_single_solid_feature(draft, body)" in generated_code
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
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
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert '_require_current_body_tip(body, obj, "Thickness")' in generated_code
        assert "_validated_shape_subelement_names" in generated_code
        assert "_validate_single_solid_feature(thick, body)" in generated_code
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                    "removed_volume": 100.0,
                    "base_volume": 1000.0,
                    "result_volume": 900.0,
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
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "_validate_subtractive_feature(loft, body, base_shape)" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
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
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                    "removed_volume": 100.0,
                    "base_volume": 1000.0,
                    "result_volume": 900.0,
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
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "Profile and spine must be inside the same PartDesign Body" in generated_code
        assert "_validate_subtractive_feature(pipe, body, base_shape)" in generated_code
        assert "_cleanup_failed_partdesign_feature" in generated_code
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_shape_tools_reject_invalid_inputs_before_bridge_call(
        self, register_tools, mock_bridge
    ):
        with pytest.raises(ValueError, match="Fillet radius"):
            await register_tools["fillet_edges"](object_name="Pad", radius=0)
        with pytest.raises(ValueError, match="Chamfer size"):
            await register_tools["chamfer_edges"](object_name="Pad", size=0)
        with pytest.raises(ValueError, match="Thickness must be positive"):
            await register_tools["thickness_feature"](
                object_name="Pad", thickness=0, faces_to_remove=["Face1"]
            )
        with pytest.raises(ValueError, match="at least two sketches"):
            await register_tools["subtractive_loft"](sketch_names=["Sketch"])
        with pytest.raises(ValueError, match="must be distinct"):
            await register_tools["subtractive_loft"](
                sketch_names=["Sketch", "Sketch"]
            )
        with pytest.raises(ValueError, match="must be different sketches"):
            await register_tools["subtractive_pipe"](
                profile_sketch="Sketch", spine_sketch="Sketch"
            )
        with pytest.raises(ValueError, match="must be different sketches"):
            await register_tools["sweep_sketch"](
                profile_sketch="Sketch", spine_sketch="Sketch"
            )
        mock_bridge.execute_python.assert_not_called()

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
                    "geometry": [
                        {
                            "index": 0,
                            "geometry_type": "LineSegment",
                            "start_point": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "end_point": {"x": 20.0, "y": 0.0, "z": 0.0},
                            "geometry": {},
                        }
                    ],
                    "constraints": [
                        {
                            "index": 0,
                            "constraint_type": "Distance",
                            "expression_path": "Constraints[0]",
                            "expression": "Dimensions.Width",
                        }
                    ],
                    "expressions": [
                        {
                            "path": "Constraints[0]",
                            "expression": "Dimensions.Width",
                        }
                    ],
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
        assert result["geometry"][0]["start_point"]["x"] == 0.0
        assert result["geometry"][0]["end_point"]["x"] == 20.0
        assert result["constraints"][0]["expression"] == "Dimensions.Width"
        assert result["expressions"][0]["path"] == "Constraints[0]"
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "sketch.solve()" in generated_code
        assert "sketch.DoF" in generated_code
        assert "_sketch_detailed_info(sketch)" in generated_code
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


def test_sketch_geometry_operation_separates_regular_polygon_and_polyline() -> None:
    """Regular polygons and explicit polylines must have distinct contracts."""
    from pydantic import ValidationError

    from freecad_mcp.tools.partdesign import SketchGeometryOperation

    regular = SketchGeometryOperation.model_validate(
        {
            "op": "add_regular_polygon",
            "center_x": 0,
            "center_y": 0,
            "radius": 5,
            "sides": 6,
        }
    )
    polyline = SketchGeometryOperation.model_validate(
        {
            "op": "add_polyline",
            "points": [[0, 0], [4, 0], [4, 2]],
            "closed": True,
        }
    )

    assert regular.op == "add_regular_polygon"
    assert polyline.op == "add_polyline"
    with pytest.raises(ValidationError):
        SketchGeometryOperation.model_validate(
            {"op": "add_polygon", "center_x": 0, "center_y": 0, "radius": 5}
        )


@pytest.mark.asyncio
async def test_pocket_sketch_exposes_direction_and_explicit_base() -> None:
    """Pocket code should set Reversed and resolve an explicit base safely."""
    from freecad_mcp.tools.partdesign import register_partdesign_tools

    mcp = MagicMock()
    registered = {}
    mcp.tool = lambda: lambda fn: registered.setdefault(fn.__name__, fn) or fn
    bridge = AsyncMock()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={
                "name": "Pocket",
                "validated": True,
                "shape_valid": True,
                "solid_count": 1,
                "base_volume": 100.0,
                "result_volume": 80.0,
                "removed_volume": 20.0,
            },
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    async def get_bridge():
        return bridge

    register_partdesign_tools(mcp, get_bridge)
    await registered["pocket_sketch"](
        "PocketSketch",
        12,
        direction="reversed",
        base_feature_name="LinearPatternBands",
    )
    code = bridge.execute_python.await_args.args[0]
    assert "_resolve_partdesign_base_feature" in code
    assert "'LinearPatternBands'" in code
    assert 'pocket.Reversed = \'reversed\' == "reversed"' in code
    assert '"volume_diagnostics"' in code

    await registered["pocket_sketch"](
        "PocketSketch",
        12,
        type="UpToFace",
        up_to_face="Pad.Face3",
    )
    up_to_face_code = bridge.execute_python.await_args.args[0]
    assert (
        "up_to_object_name, up_to_element = 'Pad.Face3'.rsplit(\".\", 1)"
        in up_to_face_code
    )
    assert "pocket.UpToFace = up_to_face_reference" in up_to_face_code

    with pytest.raises(ValueError, match="requires up_to_face"):
        await registered["pocket_sketch"](
            "PocketSketch", 12, type="UpToFace"
        )
    with pytest.raises(ValueError, match="valid only"):
        await registered["pocket_sketch"](
            "PocketSketch", 12, up_to_face="Pad.Face3"
        )


@pytest.mark.asyncio
async def test_pattern_tools_validate_shape_tip_and_reject_nested_patterns() -> None:
    """Pattern code should validate its result and direct agents to MultiTransform."""
    from freecad_mcp.tools.partdesign import register_partdesign_tools

    mcp = MagicMock()
    registered = {}
    mcp.tool = lambda: lambda fn: registered.setdefault(fn.__name__, fn) or fn
    bridge = AsyncMock()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={"name": "Pattern", "validated": True},
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    async def get_bridge():
        return bridge

    register_partdesign_tools(mcp, get_bridge)
    await registered["linear_pattern"]("Pocket", length=20, occurrences=3)
    linear_code = bridge.execute_python.await_args.args[0]
    assert "_reject_nested_partdesign_pattern(feature)" in linear_code
    assert "_validate_single_solid_feature(pattern, body)" in linear_code
    assert "_configure_feature_transform_mode(pattern)" in linear_code
    assert 'pattern.TransformMode = "Features"' not in linear_code
    assert "_pattern_material_change_diagnostics" in linear_code
    assert "material_change[\"consistent\"]" in linear_code
    assert "_cleanup_failed_partdesign_feature" in linear_code
    assert '"volume_diagnostics"' in linear_code
    assert '"material_change_diagnostics"' in linear_code

    await registered["polar_pattern"]("Pocket", angle=360, occurrences=12)
    polar_code = bridge.execute_python.await_args.args[0]
    assert "_reject_nested_partdesign_pattern(feature)" in polar_code
    assert "_validate_single_solid_feature(pattern, body)" in polar_code
    assert "_configure_feature_transform_mode(pattern)" in polar_code
    assert 'pattern.TransformMode = "Features"' not in polar_code
    assert "_pattern_material_change_diagnostics" in polar_code
    assert '"material_change_diagnostics"' in polar_code
    assert "body.Tip = feature" in polar_code


@pytest.mark.asyncio
async def test_multi_transform_pattern_uses_internal_empty_original_stages() -> None:
    """Chained patterns should be represented by a native MultiTransform."""
    from freecad_mcp.tools.partdesign import register_partdesign_tools

    mcp = MagicMock()
    registered = {}
    mcp.tool = lambda: lambda fn: registered.setdefault(fn.__name__, fn) or fn
    bridge = AsyncMock()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={"name": "MultiTransform", "validated": True},
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    async def get_bridge():
        return bridge

    register_partdesign_tools(mcp, get_bridge)
    await registered["multi_transform_pattern"](
        "PocketSeed",
        [
            {"kind": "polar", "axis": "X", "angle": 360, "occurrences": 12},
            {"kind": "linear", "direction": "X", "length": 40, "occurrences": 3},
        ],
    )
    code = bridge.execute_python.await_args.args[0]
    assert 'body.newObject(\n        "PartDesign::MultiTransform"' in code
    assert "_configure_feature_transform_mode(multi)" in code
    assert "_configure_feature_transform_mode(stage_obj)" in code
    assert 'TransformMode = "Features"' not in code
    assert "stage_obj.Originals = []" in code
    assert "multi.Transformations = stage_objects" in code
    assert "_pattern_material_change_diagnostics" in code
    assert '"material_change_diagnostics"' in code
    assert "body.Tip = multi" in code


@pytest.mark.asyncio
async def test_thread_helix_and_set_body_tip_are_registered_and_validated() -> None:
    """Thread and Tip operations should be native typed tools."""
    from freecad_mcp.tools.partdesign import register_partdesign_tools

    mcp = MagicMock()
    registered = {}
    mcp.tool = lambda: lambda fn: registered.setdefault(fn.__name__, fn) or fn
    bridge = AsyncMock()
    bridge.execute_python = AsyncMock(
        side_effect=[
            ExecutionResult(
                success=True,
                result={
                    "name": "AdditiveHelix",
                    "validated": True,
                    "shape_valid": True,
                    "solid_count": 1,
                    "base_volume": 100.0,
                    "result_volume": 110.0,
                    "added_volume": 10.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
            ),
            ExecutionResult(
                success=True,
                result={
                    "body": "Body",
                    "previous_tip": "Pocket",
                    "tip": "Pad",
                    "shape_valid": True,
                    "solid_count": 1,
                    "volume": 100.0,
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
            ),
        ]
    )

    async def get_bridge():
        return bridge

    register_partdesign_tools(mcp, get_bridge)
    thread = await registered["thread_helix"](
        "ThreadProfile", pitch=1.5, height=12, axis="Base_X"
    )
    helix_code = bridge.execute_python.await_args_list[0].args[0]
    assert thread["validated"] is True
    assert '"PartDesign::AdditiveHelix"' in helix_code
    assert "helix.Pitch = 1.5" in helix_code
    assert "_validate_additive_feature" in helix_code

    tip = await registered["set_body_tip"]("Body", "Pad")
    tip_code = bridge.execute_python.await_args_list[1].args[0]
    assert tip["tip"] == "Pad"
    assert "_is_valid_single_solid_feature(feature)" in tip_code
    assert "body.Tip = feature" in tip_code
