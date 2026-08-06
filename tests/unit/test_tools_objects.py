"""Tests for object tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult, ObjectInfo


class TestObjectTools:
    """Tests for object management tools."""

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
        """Register object tools and return the registered functions."""
        from freecad_mcp.tools.objects import register_object_tools

        async def get_bridge():
            return mock_bridge

        register_object_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_list_objects_empty(self, register_tools, mock_bridge):
        """list_objects should return empty list when no objects."""
        mock_bridge.get_objects = AsyncMock(return_value=[])

        list_objects = register_tools["list_objects"]
        result = await list_objects()

        assert result == []
        mock_bridge.get_objects.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_list_objects_with_objects(self, register_tools, mock_bridge):
        """list_objects should return object info."""
        mock_objects = [
            ObjectInfo(
                name="Box",
                label="My Box",
                type_id="Part::Box",
                visibility=True,
                children=[],
                parents=[],
            ),
            ObjectInfo(
                name="Cylinder",
                label="My Cylinder",
                type_id="Part::Cylinder",
                visibility=False,
                children=[],
                parents=[],
            ),
        ]
        mock_bridge.get_objects = AsyncMock(return_value=mock_objects)

        list_objects = register_tools["list_objects"]
        result = await list_objects(doc_name="TestDoc")

        assert len(result) == 2
        assert result[0]["name"] == "Box"
        assert result[0]["type_id"] == "Part::Box"
        assert result[0]["visibility"] is True
        assert result[1]["name"] == "Cylinder"
        assert result[1]["visibility"] is False
        mock_bridge.get_objects.assert_called_once_with("TestDoc")

    @pytest.mark.asyncio
    async def test_inspect_object(self, register_tools, mock_bridge):
        """inspect_object should return detailed object info."""
        mock_object = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0, "Width": 20.0, "Height": 30.0},
            shape_info={
                "shape_type": "Solid",
                "volume": 6000.0,
                "area": 2200.0,
                "is_valid": True,
            },
            visibility=True,
            children=["Fillet001"],
            parents=[],
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        inspect_object = register_tools["inspect_object"]
        result = await inspect_object(object_name="Box", include_properties=True)

        assert result["name"] == "Box"
        assert result["type_id"] == "Part::Box"
        assert result["properties"]["Length"] == 10.0
        assert result["shape_info"]["volume"] == 6000.0
        assert result["children"] == ["Fillet001"]
        mock_bridge.get_object.assert_called_once_with(
            "Box",
            None,
            include_properties=True,
            include_shape=True,
            include_topology=True,
            face_offset=0,
            face_limit=20,
            edge_offset=0,
            edge_limit=20,
        )

    @pytest.mark.asyncio
    async def test_inspect_object_reuses_top_level_shape_summary(
        self, register_tools, mock_bridge
    ):
        """The Shape property should not duplicate the full shape_info payload."""
        mock_object = ObjectInfo(
            name="Pad",
            label="Pad",
            type_id="PartDesign::Feature",
            properties={
                "Shape": {
                    "type": "Part::PropertyPartShape",
                    "group": "Data",
                    "value": {"shape_type": "Solid", "volume": 100.0},
                }
            },
            shape_info={"shape_type": "Solid", "volume": 100.0},
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        result = await register_tools["inspect_object"]("Pad", include_properties=True)

        assert result["properties"]["Shape"]["value"] == {"summary_ref": "shape_info"}
        assert result["shape_info"]["volume"] == 100.0

    @pytest.mark.asyncio
    async def test_inspect_object_without_properties(self, register_tools, mock_bridge):
        """inspect_object should exclude properties when not requested."""
        mock_object = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0},
            shape_info=None,
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        inspect_object = register_tools["inspect_object"]
        result = await inspect_object(
            object_name="Box", include_properties=False, include_shape=False
        )

        assert result["name"] == "Box"
        assert "properties" not in result
        assert "shape_info" not in result

    @pytest.mark.asyncio
    async def test_inspect_object_default_is_compact(self, register_tools, mock_bridge):
        mock_bridge.get_object = AsyncMock(
            return_value=ObjectInfo(
                name="Body",
                label="Body",
                type_id="PartDesign::Body",
                shape_info={"volume": 42.0, "face_count": 80},
            )
        )

        result = await register_tools["inspect_object"]("Body")

        assert result["detail_level"] == "summary"
        assert result["shape_info"]["face_count"] == 80
        mock_bridge.get_object.assert_awaited_once_with(
            "Body",
            None,
            include_properties=False,
            include_shape=True,
            include_topology=False,
            face_offset=0,
            face_limit=20,
            edge_offset=0,
            edge_limit=20,
        )

    @pytest.mark.asyncio
    async def test_select_subshapes_filters_and_sorts_faces(
        self, register_tools, mock_bridge
    ):
        """Semantic face selection should return consumable FaceN references."""
        mock_bridge.get_object = AsyncMock(
            return_value=ObjectInfo(
                name="Pad",
                label="Pad",
                type_id="PartDesign::Feature",
                shape_info={
                    "shape_type": "Solid",
                    "is_null": False,
                    "faces": [
                        {
                            "name": "Face1",
                            "index": 1,
                            "surface_type": "Plane",
                            "normal": {"x": 0.0, "y": 0.0, "z": -1.0},
                            "area": 200.0,
                            "center": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "adjacent_faces": ["Face3"],
                            "convexity": "flat",
                        },
                        {
                            "name": "Face2",
                            "index": 2,
                            "surface_type": "Plane",
                            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                            "area": 200.0,
                            "center": {"x": 0.0, "y": 0.0, "z": 10.0},
                            "adjacent_faces": ["Face3"],
                            "convexity": "flat",
                        },
                    ],
                    "edges": [],
                },
            )
        )

        result = await register_tools["select_subshapes"](
            object_name="Pad",
            criteria={
                "kind": "face",
                "surface_types": ["Plane"],
                "normal": [0, 0, 1],
                "sort_by": "center_z",
                "sort_order": "desc",
                "limit": 1,
            },
            detail_level="summary",
        )

        assert result["references"] == ["Face2"]
        assert result["matches"][0]["centroid"]["z"] == 10.0

    @pytest.mark.asyncio
    async def test_select_subshapes_filters_edges_by_direction_and_adjacency(
        self, register_tools, mock_bridge
    ):
        """Edge direction is undirected and adjacent surfaces are semantic filters."""
        mock_bridge.get_object = AsyncMock(
            return_value=ObjectInfo(
                name="Pad",
                label="Pad",
                type_id="PartDesign::Feature",
                shape_info={
                    "shape_type": "Solid",
                    "is_null": False,
                    "faces": [
                        {"name": "Face1", "surface_type": "Plane"},
                        {"name": "Face2", "surface_type": "Cylinder"},
                    ],
                    "edges": [
                        {
                            "name": "Edge1",
                            "index": 1,
                            "curve_type": "Line",
                            "direction": {"x": -1.0, "y": 0.0, "z": 0.0},
                            "length": 20.0,
                            "radius": None,
                            "center": {"x": 10.0, "y": 0.0, "z": 0.0},
                            "adjacent_faces": ["Face1", "Face2"],
                        },
                        {
                            "name": "Edge2",
                            "index": 2,
                            "curve_type": "Circle",
                            "direction": None,
                            "length": 12.0,
                            "radius": 2.0,
                            "center": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "adjacent_faces": ["Face1"],
                        },
                    ],
                },
            )
        )

        result = await register_tools["select_subshapes"](
            object_name="Pad",
            criteria={
                "kind": "edge",
                "curve_types": ["Line"],
                "direction": [1, 0, 0],
                "adjacent_surface_types": ["Plane", "Cylinder"],
            },
        )

        assert result["references"] == ["Edge1"]
        assert "matches" not in result

    def test_subshape_centroid_field_is_explicit_and_legacy_center_is_accepted(self):
        from freecad_mcp.tools.objects import FaceSelectionCriteria

        criteria = FaceSelectionCriteria.model_validate(
            {"kind": "face", "center": {"z_min": 5.0}}
        )

        assert criteria.centroid_bounds is not None
        assert criteria.centroid_bounds.z_min == 5.0
        dumped = criteria.model_dump(exclude_none=True)
        assert "centroid_bounds" in dumped
        assert "center" not in dumped

    @pytest.mark.asyncio
    async def test_select_subshapes_rejects_zero_direction(
        self, register_tools, mock_bridge
    ):
        with pytest.raises(ValueError, match="direction must be a non-zero vector"):
            await register_tools["select_subshapes"](
                object_name="Pad",
                criteria={"kind": "edge", "direction": [0, 0, 0]},
            )
        mock_bridge.get_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_subshapes_accepts_common_type_aliases_and_sorts_missing_last(
        self, register_tools, mock_bridge
    ):
        mock_bridge.get_object = AsyncMock(
            return_value=ObjectInfo(
                name="Pad",
                label="Pad",
                type_id="PartDesign::Feature",
                shape_info={
                    "shape_type": "Solid",
                    "is_null": False,
                    "faces": [],
                    "edges": [
                        {
                            "name": "Edge1",
                            "index": 1,
                            "curve_type": "LineSegment",
                            "length": None,
                            "adjacent_faces": [],
                        },
                        {
                            "name": "Edge2",
                            "index": 2,
                            "curve_type": "Line",
                            "length": 30.0,
                            "adjacent_faces": [],
                        },
                    ],
                },
            )
        )

        result = await register_tools["select_subshapes"](
            object_name="Pad",
            criteria={
                "kind": "edge",
                "curve_types": ["linear"],
                "sort_by": "length",
                "sort_order": "desc",
            },
        )

        assert result["references"] == ["Edge2", "Edge1"]

    @pytest.mark.asyncio
    async def test_create_object(self, register_tools, mock_bridge):
        """create_object should create and return object info."""
        mock_object = ObjectInfo(
            name="Box",
            label="Box",
            type_id="Part::Box",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_object = register_tools["create_object"]
        result = await create_object(type_id="Part::Box", name="Box")

        assert result["name"] == "Box"
        assert result["type_id"] == "Part::Box"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_object(self, register_tools, mock_bridge):
        """edit_object should update object properties."""
        mock_object = ObjectInfo(
            name="Box",
            label="Box",
            type_id="Part::Box",
            properties={"Length": 20.0, "Width": 10.0},
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.edit_object = AsyncMock(return_value=mock_object)

        edit_object = register_tools["edit_object"]
        result = await edit_object(object_name="Box", properties={"Length": 20.0})

        assert result["name"] == "Box"
        mock_bridge.edit_object.assert_called_once_with("Box", {"Length": 20.0}, None)

    @pytest.mark.asyncio
    async def test_delete_object(self, register_tools, mock_bridge):
        """delete_object should delete and return success."""
        mock_bridge.delete_object = AsyncMock(return_value=True)

        delete_object = register_tools["delete_object"]
        result = await delete_object(object_name="Box")

        assert result["success"] is True
        mock_bridge.delete_object.assert_called_once_with("Box", None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("primitive", "expected_type", "expected_properties"),
        [
            (
                {"kind": "box", "length": 20.0, "width": 10.0, "height": 5.0},
                "Part::Box",
                {"Length": 20.0, "Width": 10.0, "Height": 5.0},
            ),
            (
                {"kind": "cylinder", "radius": 5.0, "height": 20.0, "angle": 180.0},
                "Part::Cylinder",
                {"Radius": 5.0, "Height": 20.0, "Angle": 180.0},
            ),
            (
                {"kind": "sphere", "radius": 10.0},
                "Part::Sphere",
                {"Radius": 10.0},
            ),
            (
                {"kind": "cone", "radius1": 10.0, "radius2": 0.0, "height": 20.0},
                "Part::Cone",
                {"Radius1": 10.0, "Radius2": 0.0, "Height": 20.0, "Angle": 360.0},
            ),
            (
                {"kind": "torus", "radius1": 20.0, "radius2": 5.0},
                "Part::Torus",
                {
                    "Radius1": 20.0,
                    "Radius2": 5.0,
                    "Angle1": -180.0,
                    "Angle2": 180.0,
                    "Angle3": 360.0,
                },
            ),
            (
                {"kind": "wedge", "xmax": 12.0, "ymax": 8.0, "zmax": 6.0},
                "Part::Wedge",
                {
                    "Xmin": 0.0,
                    "Ymin": 0.0,
                    "Zmin": 0.0,
                    "X2min": 2.0,
                    "Z2min": 2.0,
                    "Xmax": 12.0,
                    "Ymax": 8.0,
                    "Zmax": 6.0,
                    "X2max": 8.0,
                    "Z2max": 8.0,
                },
            ),
            (
                {
                    "kind": "helix",
                    "pitch": 5.0,
                    "height": 20.0,
                    "radius": 4.0,
                    "angle": 2.0,
                    "left_handed": True,
                },
                "Part::Helix",
                {
                    "Pitch": 5.0,
                    "Height": 20.0,
                    "Radius": 4.0,
                    "Angle": 2.0,
                    "LocalCoord": 1,
                },
            ),
        ],
    )
    async def test_create_primitive_maps_each_kind_to_freecad(
        self, register_tools, mock_bridge, primitive, expected_type, expected_properties
    ):
        """Each primitive kind should map to its exact FreeCAD object contract."""
        mock_object = ObjectInfo(
            name="Primitive",
            label="Primitive",
            type_id=expected_type,
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        result = await register_tools["create_primitive"](
            primitive=primitive, name="Primitive", doc_name="PartDoc"
        )

        assert result["kind"] == primitive["kind"]
        assert result["type_id"] == expected_type
        mock_bridge.create_object.assert_awaited_once_with(
            expected_type, "Primitive", expected_properties, "PartDoc"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kind", "expected_type", "expected_properties"),
        [
            (
                "cone",
                "Part::Cone",
                {"Radius1": 5.0, "Radius2": 0.0, "Height": 10.0, "Angle": 360.0},
            ),
            (
                "helix",
                "Part::Helix",
                {
                    "Pitch": 5.0,
                    "Height": 20.0,
                    "Radius": 5.0,
                    "Angle": 0.0,
                    "LocalCoord": 0,
                },
            ),
        ],
    )
    async def test_create_primitive_preserves_legacy_kind_defaults(
        self, register_tools, mock_bridge, kind, expected_type, expected_properties
    ):
        """Consolidation must not silently change existing primitive defaults."""
        mock_bridge.create_object = AsyncMock(
            return_value=ObjectInfo(
                name="Primitive",
                label="Primitive",
                type_id=expected_type,
                visibility=True,
                children=[],
                parents=[],
            )
        )

        await register_tools["create_primitive"](primitive={"kind": kind})

        mock_bridge.create_object.assert_awaited_once_with(
            expected_type, None, expected_properties, None
        )

    def test_primitive_schema_is_discriminated_by_kind(self):
        """The tool schema should expose one strict parameter shape per primitive."""
        from pydantic import TypeAdapter

        from freecad_mcp.tools.objects import PrimitiveSpec

        schema = TypeAdapter(PrimitiveSpec).json_schema()
        assert schema["discriminator"]["propertyName"] == "kind"
        assert set(schema["discriminator"]["mapping"]) == {
            "box",
            "cylinder",
            "sphere",
            "cone",
            "torus",
            "wedge",
            "helix",
        }
        assert len(schema["oneOf"]) == 7

    @pytest.mark.asyncio
    async def test_create_primitive_rejects_fields_from_another_kind(
        self, register_tools, mock_bridge
    ):
        """A consolidated tool must not silently ignore another kind's fields."""
        with pytest.raises(ValueError):
            await register_tools["create_primitive"](
                primitive={"kind": "box", "radius": 5.0}
            )
        mock_bridge.create_object.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_primitive_reports_box_volume(
        self, register_tools, mock_bridge
    ):
        """The consolidated tool should retain useful box-specific output."""
        mock_bridge.create_object = AsyncMock(
            return_value=ObjectInfo(
                name="Box",
                label="Box",
                type_id="Part::Box",
                visibility=True,
                children=[],
                parents=[],
            )
        )

        result = await register_tools["create_primitive"](
            primitive={"kind": "box", "length": 4.0, "width": 5.0, "height": 6.0}
        )

        assert result["volume"] == 120.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "primitive",
        [
            {"kind": "box", "length": 0},
            {"kind": "cylinder", "radius": -1},
            {"kind": "cone", "radius1": 0, "radius2": 0},
            {"kind": "helix", "pitch": 0},
            {"kind": "wedge", "xmin": 5, "xmax": 5},
        ],
    )
    async def test_create_primitive_rejects_invalid_geometry_before_bridge(
        self, register_tools, mock_bridge, primitive
    ):
        """Invalid primitive dimensions must not create FreeCAD objects."""
        with pytest.raises(ValueError):
            await register_tools["create_primitive"](primitive=primitive)
        mock_bridge.create_object.assert_not_awaited()

    def test_legacy_primitive_tools_are_not_registered(self, register_tools):
        """Removed primitive aliases must not remain in tools/list."""
        legacy_tools = {
            "create_box",
            "create_cylinder",
            "create_sphere",
            "create_cone",
            "create_torus",
            "create_wedge",
            "create_helix",
        }
        assert "create_primitive" in register_tools
        assert legacy_tools.isdisjoint(register_tools)

    # Tests for execute_python based tools

    @pytest.mark.asyncio
    async def test_boolean_operation_fuse(self, register_tools, mock_bridge):
        """boolean_operation should perform union operation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fusion",
                    "label": "Fusion",
                    "type_id": "Part::MultiFuse",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        boolean_operation = register_tools["boolean_operation"]
        result = await boolean_operation(
            operation="fuse", object1_name="Box", object2_name="Cylinder"
        )

        assert result["name"] == "Fusion"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_placement(self, register_tools, mock_bridge):
        """set_placement should set position and rotation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"position": [10.0, 20.0, 30.0], "rotation": [0.0, 0.0, 45.0]},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        set_placement = register_tools["set_placement"]
        result = await set_placement(object_name="Box", position=[10.0, 20.0, 30.0])

        assert result["position"] == [10.0, 20.0, 30.0]
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_object(self, register_tools, mock_bridge):
        """scale_object should scale an object via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "ScaledBox",
                    "label": "ScaledBox",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        scale_object = register_tools["scale_object"]
        result = await scale_object(object_name="Box", scale=2.0)

        assert result["name"] == "ScaledBox"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_object(self, register_tools, mock_bridge):
        """rotate_object should rotate an object via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 45.0]},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        rotate_object = register_tools["rotate_object"]
        result = await rotate_object(
            object_name="Box", axis=[0.0, 0.0, 1.0], angle=45.0
        )

        assert result["rotation"] == [0.0, 0.0, 45.0]
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_copy_object(self, register_tools, mock_bridge):
        """copy_object should create a copy via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Box001", "label": "Box001", "type_id": "Part::Box"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        copy_object = register_tools["copy_object"]
        result = await copy_object(object_name="Box")

        assert result["name"] == "Box001"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_mirror_object(self, register_tools, mock_bridge):
        """mirror_object should mirror across a plane via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "MirroredBox",
                    "label": "MirroredBox",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        mirror_object = register_tools["mirror_object"]
        result = await mirror_object(object_name="Box", plane="XY")

        assert result["name"] == "MirroredBox"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_selection_get_returns_structured_selection(
        self, register_tools, mock_bridge
    ):
        """selection(action='get') should return objects and sub-elements."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "action": "get",
                    "selected": [
                        {
                            "name": "Pad",
                            "label": "Pad",
                            "type_id": "PartDesign::Feature",
                            "sub_elements": ["Face1"],
                        }
                    ],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["selection"]("get", doc_name="Part")

        assert result["selected"][0]["sub_elements"] == ["Face1"]
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "getSelectionEx('Part')" in generated_code

    @pytest.mark.asyncio
    async def test_selection_set_reports_selected_and_missing_objects(
        self, register_tools, mock_bridge
    ):
        """selection(action='set') should preserve evidence about missing names."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": False,
                    "action": "set",
                    "selected_count": 1,
                    "selected_names": ["Pad"],
                    "missing_names": ["Missing"],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["selection"](
            "set", object_names=["Pad", "Missing"], clear_existing=False
        )

        assert result["selected_names"] == ["Pad"]
        assert result["missing_names"] == ["Missing"]
        generated_code = mock_bridge.execute_python.await_args.args[0]
        assert "clearSelection()" in generated_code
        assert "if False:" in generated_code

    @pytest.mark.asyncio
    async def test_selection_clear_uses_same_entry_point(
        self, register_tools, mock_bridge
    ):
        """selection(action='clear') should clear GUI selection."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "action": "clear", "selected_count": 0},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        result = await register_tools["selection"]("clear")

        assert result["selected_count"] == 0
        assert (
            "FreeCADGui.Selection.clearSelection()"
            in (mock_bridge.execute_python.await_args.args[0])
        )

    @pytest.mark.asyncio
    async def test_selection_set_requires_object_names(
        self, register_tools, mock_bridge
    ):
        """An empty set operation should fail before executing FreeCAD code."""
        with pytest.raises(ValueError, match="object_names is required"):
            await register_tools["selection"]("set")
        mock_bridge.execute_python.assert_not_awaited()

    def test_legacy_selection_tools_are_not_registered(self, register_tools):
        """Only the consolidated selection tool should remain public."""
        assert "selection" in register_tools
        assert {"get_selection", "set_selection", "clear_selection"}.isdisjoint(
            register_tools
        )

    # Tests for new Part primitives

    @pytest.mark.asyncio
    async def test_create_line(self, register_tools, mock_bridge):
        """create_line should create a line between two points."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Line", "label": "Line", "type_id": "Part::Feature"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_line = register_tools["create_line"]
        result = await create_line(point1=[0.0, 0.0, 0.0], point2=[10.0, 10.0, 10.0])

        assert result["name"] == "Line"
        assert result["type_id"] == "Part::Feature"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_plane(self, register_tools, mock_bridge):
        """create_plane should create a planar surface via create_object."""
        mock_object = ObjectInfo(
            name="Plane",
            label="Plane",
            type_id="Part::Plane",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_plane = register_tools["create_plane"]
        result = await create_plane(length=20.0, width=15.0)

        assert result["name"] == "Plane"
        assert result["type_id"] == "Part::Plane"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_ellipse(self, register_tools, mock_bridge):
        """create_ellipse should create an ellipse curve via create_object."""
        mock_object = ObjectInfo(
            name="Ellipse",
            label="Ellipse",
            type_id="Part::Ellipse",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_ellipse = register_tools["create_ellipse"]
        result = await create_ellipse(major_radius=10.0, minor_radius=5.0)

        assert result["name"] == "Ellipse"
        assert result["type_id"] == "Part::Ellipse"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_prism(self, register_tools, mock_bridge):
        """create_prism should create a prism via create_object."""
        mock_object = ObjectInfo(
            name="Prism",
            label="Prism",
            type_id="Part::Prism",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_prism = register_tools["create_prism"]
        result = await create_prism(polygon_sides=6, circumradius=10.0, height=20.0)

        assert result["name"] == "Prism"
        assert result["type_id"] == "Part::Prism"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_regular_polygon(self, register_tools, mock_bridge):
        """create_regular_polygon should create a flat polygon via create_object."""
        mock_object = ObjectInfo(
            name="RegularPolygon",
            label="RegularPolygon",
            type_id="Part::RegularPolygon",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_regular_polygon = register_tools["create_regular_polygon"]
        result = await create_regular_polygon(polygon_sides=8, circumradius=15.0)

        assert result["name"] == "RegularPolygon"
        assert result["type_id"] == "Part::RegularPolygon"
        mock_bridge.create_object.assert_called_once()

    # Tests for Part shape operations

    @pytest.mark.asyncio
    async def test_shell_object(self, register_tools, mock_bridge):
        """shell_object should create a hollow shell from a solid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Shell",
                    "label": "Shell",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        shell_object = register_tools["shell_object"]
        result = await shell_object(
            object_name="Box", thickness=2.0, faces_to_remove=["Face1"]
        )

        assert result["name"] == "Shell"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_offset_3d(self, register_tools, mock_bridge):
        """offset_3d should create an offset copy of a shape."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Offset",
                    "label": "Offset",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        offset_3d = register_tools["offset_3d"]
        result = await offset_3d(object_name="Box", offset=2.0)

        assert result["name"] == "Offset"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_slice_shape(self, register_tools, mock_bridge):
        """slice_shape should slice a shape with a plane."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Slice",
                    "label": "Slice",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        slice_shape = register_tools["slice_shape"]
        result = await slice_shape(
            object_name="Box",
            plane_point=[0.0, 0.0, 5.0],
            plane_normal=[0.0, 0.0, 1.0],
        )

        assert result["name"] == "Slice"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_section_shape(self, register_tools, mock_bridge):
        """section_shape should create a section of a shape."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Section",
                    "label": "Section",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        section_shape = register_tools["section_shape"]
        result = await section_shape(object_name="Box", plane="XY", offset=5.0)

        assert result["name"] == "Section"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part compound operations

    @pytest.mark.asyncio
    async def test_make_compound(self, register_tools, mock_bridge):
        """make_compound should combine objects into a compound."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Compound",
                    "label": "Compound",
                    "type_id": "Part::Compound",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_compound = register_tools["make_compound"]
        result = await make_compound(object_names=["Box", "Cylinder"])

        assert result["name"] == "Compound"
        assert result["type_id"] == "Part::Compound"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_explode_compound(self, register_tools, mock_bridge):
        """explode_compound should separate a compound into parts."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "parts": ["Part001", "Part002", "Part003"],
                    "count": 3,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        explode_compound = register_tools["explode_compound"]
        result = await explode_compound(object_name="Compound")

        assert result["success"] is True
        assert len(result["parts"]) == 3
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_fuse_all(self, register_tools, mock_bridge):
        """fuse_all should fuse multiple objects into one."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fusion",
                    "label": "Fusion",
                    "type_id": "Part::MultiFuse",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        fuse_all = register_tools["fuse_all"]
        result = await fuse_all(object_names=["Box", "Cylinder", "Sphere"])

        assert result["name"] == "Fusion"
        assert result["type_id"] == "Part::MultiFuse"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_common_all(self, register_tools, mock_bridge):
        """common_all should find intersection of multiple objects."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Common",
                    "label": "Common",
                    "type_id": "Part::MultiCommon",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        common_all = register_tools["common_all"]
        result = await common_all(object_names=["Box", "Cylinder"])

        assert result["name"] == "Common"
        assert result["type_id"] == "Part::MultiCommon"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part wire/face operations

    @pytest.mark.asyncio
    async def test_make_wire(self, register_tools, mock_bridge):
        """make_wire should create a wire from points."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Wire",
                    "label": "Wire",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_wire = register_tools["make_wire"]
        result = await make_wire(
            points=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
            closed=True,
        )

        assert result["name"] == "Wire"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_face(self, register_tools, mock_bridge):
        """make_face should create a face from a wire."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Face",
                    "label": "Face",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_face = register_tools["make_face"]
        result = await make_face(object_name="Wire")

        assert result["name"] == "Face"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_extrude_shape(self, register_tools, mock_bridge):
        """extrude_shape should extrude a 2D shape along a direction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Extrusion",
                    "label": "Extrusion",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        extrude_shape = register_tools["extrude_shape"]
        result = await extrude_shape(object_name="Face", direction=[0, 0, 20])

        assert result["name"] == "Extrusion"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_revolve_shape(self, register_tools, mock_bridge):
        """revolve_shape should revolve a shape around an axis."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Revolution",
                    "label": "Revolution",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        revolve_shape = register_tools["revolve_shape"]
        result = await revolve_shape(
            object_name="Face",
            axis_point=[0, 0, 0],
            axis_direction=[0, 0, 1],
            angle=360.0,
        )

        assert result["name"] == "Revolution"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part loft and sweep

    @pytest.mark.asyncio
    async def test_part_loft(self, register_tools, mock_bridge):
        """part_loft should create a loft through profiles."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Loft",
                    "label": "Loft",
                    "type_id": "Part::Loft",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        part_loft = register_tools["part_loft"]
        result = await part_loft(
            profile_names=["Circle1", "Circle2", "Circle3"],
            solid=True,
        )

        assert result["name"] == "Loft"
        assert result["type_id"] == "Part::Loft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_part_sweep(self, register_tools, mock_bridge):
        """part_sweep should sweep a profile along a spine."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sweep",
                    "label": "Sweep",
                    "type_id": "Part::Sweep",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        part_sweep = register_tools["part_sweep"]
        result = await part_sweep(
            profile_name="Circle",
            spine_name="Helix",
            solid=True,
        )

        assert result["name"] == "Sweep"
        assert result["type_id"] == "Part::Sweep"
        mock_bridge.execute_python.assert_called_once()
