"""Live coverage for general-purpose imported/static BREP surgery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.brep import register_brep_tools

pytestmark = pytest.mark.integration


class _ToolCollector:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        def decorator(function: Any) -> Any:
            self.tools[function.__name__] = function
            return function

        return decorator


@pytest_asyncio.fixture
async def live_bridge() -> AsyncIterator[XmlRpcBridge]:
    bridge = XmlRpcBridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.disconnect()


@pytest.fixture
def brep_tools(live_bridge: XmlRpcBridge) -> dict[str, Any]:
    collector = _ToolCollector()

    async def get_bridge() -> XmlRpcBridge:
        return live_bridge

    register_brep_tools(collector, get_bridge)
    return collector.tools


async def _close(bridge: XmlRpcBridge, name: str) -> None:
    await bridge.execute_python(
        f"""
if {name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({name!r})
_result_ = True
"""
    )


@pytest.mark.asyncio
async def test_group_and_detect_rotational_pattern(
    live_bridge: XmlRpcBridge,
    brep_tools: dict[str, Any],
) -> None:
    doc_name = "MCPBrepPatternAnalysis"
    setup = await live_bridge.execute_python(
        f"""
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
obj = doc.addObject("Part::Feature", "PatternSource")
left = Part.makeBox(2, 2, 2, FreeCAD.Vector(-11, -1, 0))
right = Part.makeBox(2, 2, 2, FreeCAD.Vector(9, -1, 0))
obj.Shape = Part.makeCompound([left, right])
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.failure_details("setup failed")
    try:
        grouped = await brep_tools["group_feature_faces"](
            object_name="PatternSource",
            face_names=[f"Face{index}" for index in range(1, 13)],
            doc_name=doc_name,
        )
        assert grouped["group_count"] == 2

        detected = await brep_tools["detect_rotational_pattern"](
            object_name="PatternSource",
            face_groups=[group["face_names"] for group in grouped["groups"]],
            doc_name=doc_name,
        )
        assert detected["pattern_detected"] is True
        assert detected["occurrence_count"] == 2
        assert detected["expected_pitch_deg"] == pytest.approx(180.0)
    finally:
        await _close(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_representative_analysis_precedes_component_limit(
    live_bridge: XmlRpcBridge,
    brep_tools: dict[str, Any],
) -> None:
    doc_name = "MCPBrepCandidatePopulation"
    setup = await live_bridge.execute_python(
        f"""
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
source = doc.addObject("Part::Feature", "ImportedRepeatedFeatures")
support = doc.addObject("Part::Feature", "RecoveredSupport")
base = Part.makeBox(24, 12, 5)
source_shape = base
for x_value in (4, 12, 20):
    local_feature = Part.makeCylinder(
        1.5,
        3,
        FreeCAD.Vector(x_value, 6, 5),
    )
    source_shape = source_shape.fuse(local_feature)
source.Shape = source_shape
support.Shape = base
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.failure_details("setup failed")
    try:
        extracted = await brep_tools["extract_feature_material"](
            source_name="ImportedRepeatedFeatures",
            healed_name="RecoveredSupport",
            component_sort_by="volume",
            component_limit=1,
            result_prefix="Candidate",
            doc_name=doc_name,
        )

        analysis = extracted["representative_analysis"]
        assert extracted["created_component_count"] == 1
        assert analysis["scope"] == "all_valid_components_before_selection"
        assert analysis["analyzed_component_count"] == 3
        assert analysis["candidate_count"] == 3
        assert analysis["candidate_indices"] == [1, 2, 3]
        assert analysis["largest_group_is_unique"] is True
        assert analysis["leading_group_count"] == 1
        assert analysis["selection_status"] == "unique_largest_topology_group"
        assert len(analysis["largest_topology_signatures"]) == 1
        assert "preferred_topology_signature" not in analysis
    finally:
        await _close(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_equal_largest_topology_groups_are_explicitly_ambiguous(
    live_bridge: XmlRpcBridge,
    brep_tools: dict[str, Any],
) -> None:
    doc_name = "MCPBrepTopologyTie"
    setup = await live_bridge.execute_python(
        f"""
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
source = doc.addObject("Part::Feature", "ImportedMixedFeatures")
support = doc.addObject("Part::Feature", "RecoveredSupport")
base = Part.makeBox(32, 16, 4)
features = [
    Part.makeCylinder(1.5, 3, FreeCAD.Vector(5, 4, 4)),
    Part.makeCylinder(1.5, 3, FreeCAD.Vector(13, 4, 4)),
    Part.makeBox(3, 3, 3, FreeCAD.Vector(20, 3, 4)),
    Part.makeBox(3, 3, 3, FreeCAD.Vector(26, 3, 4)),
]
source_shape = base
for feature in features:
    source_shape = source_shape.fuse(feature)
source.Shape = source_shape
support.Shape = base
doc.recompute()
_result_ = True
"""
    )
    assert setup.success, setup.failure_details("setup failed")
    try:
        extracted = await brep_tools["extract_feature_material"](
            source_name="ImportedMixedFeatures",
            healed_name="RecoveredSupport",
            component_limit=1,
            result_prefix="SelectedCandidate",
            doc_name=doc_name,
        )

        analysis = extracted["representative_analysis"]
        assert extracted["created_component_count"] == 1
        assert analysis["analyzed_component_count"] == 4
        assert analysis["topology_group_count"] == 2
        assert analysis["largest_group_size"] == 2
        assert analysis["largest_group_is_unique"] is False
        assert analysis["leading_group_count"] == 2
        assert analysis["selection_status"] == "ambiguous_topology_group_tie"
        assert len(analysis["largest_topology_signatures"]) == 2
        assert "preferred_topology_signature" not in analysis
        assert analysis["candidate_count"] == 4
        assert sorted(analysis["candidate_indices"]) == [1, 2, 3, 4]
        assert {group["component_count"] for group in analysis["leading_groups"]} == {2}
        assert "majority_topology_signature" not in analysis
    finally:
        await _close(live_bridge, doc_name)


@pytest.mark.asyncio
async def test_defeature_extract_pattern_sew_heal_and_make_solid(
    live_bridge: XmlRpcBridge,
    brep_tools: dict[str, Any],
) -> None:
    doc_name = "MCPBrepSurgeryPipeline"
    setup = await live_bridge.execute_python(
        f"""
import Part
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
doc = FreeCAD.newDocument({doc_name!r})
source = doc.addObject("Part::Feature", "ImportedStatic")
base = Part.makeBox(20, 20, 5)
boss = Part.makeCylinder(2, 3, FreeCAD.Vector(15, 10, 5))
source.Shape = base.fuse(boss)
doc.recompute()
feature_faces = [
    f"Face{{index}}"
    for index, face in enumerate(source.Shape.Faces, start=1)
    if float(face.CenterOfMass.z) > 5.000001
]
_result_ = {{"feature_faces": feature_faces}}
"""
    )
    assert setup.success, setup.failure_details("setup failed")
    feature_faces = setup.result["feature_faces"]
    assert len(feature_faces) >= 2
    try:
        healed = await brep_tools["defeature_faces"](
            object_name="ImportedStatic",
            face_names=feature_faces,
            result_name="RecoveredBase",
            hide_source=False,
            doc_name=doc_name,
        )
        assert healed["solid_count"] == 1
        assert healed["shape_valid"] is True
        assert healed["measurable_change"] is True

        extracted = await brep_tools["extract_feature_material"](
            source_name="ImportedStatic",
            healed_name="RecoveredBase",
            component_volume_min=1.0,
            component_sort_by="volume",
            component_sort_order="desc",
            component_limit=1,
            result_prefix="RecoveredFeature",
            doc_name=doc_name,
        )
        assert extracted["container_valid"] is True
        assert extracted["available_component_count"] == 1
        assert extracted["valid_component_count"] == 1
        assert extracted["created_component_count"] == 1
        pattern_seed = extracted["components"][0]["name"]

        patterned = await brep_tools["polar_pattern_shape"](
            object_name=pattern_seed,
            occurrences=4,
            axis_origin=[10, 10, 0],
            result_name="RepeatedFeatures",
            expected_solid_count=4,
            doc_name=doc_name,
        )
        assert patterned["occurrences"] == 4
        assert patterned["solid_count"] == 4
        assert patterned["fuse_strategy"] == "compound"

        fused_pattern = await brep_tools["polar_pattern_shape"](
            object_name=pattern_seed,
            occurrences=4,
            axis_origin=[10, 10, 0],
            result_name="RepeatedFeaturesMultiFuse",
            fuse=True,
            refine=False,
            expected_solid_count=4,
            doc_name=doc_name,
        )
        assert fused_pattern["solid_count"] == 4
        assert fused_pattern["fuse_strategy"] == "multi_fuse"

        sewn = await brep_tools["sew_shell"](
            object_names=["RecoveredBase"],
            result_name="BaseShell",
            doc_name=doc_name,
        )
        assert sewn["closed"] is True

        solid = await brep_tools["make_solid"](
            object_name="BaseShell",
            result_name="BaseSolid",
            doc_name=doc_name,
        )
        assert solid["solid_count"] == 1
        assert solid["volume"] > 0.0

        repaired = await brep_tools["heal_shape"](
            object_name="BaseSolid",
            result_name="HealedBaseSolid",
            expected_solid_count=1,
            doc_name=doc_name,
        )
        assert repaired["shape_valid"] is True
        assert repaired["solid_count"] == 1
        assert repaired["refined"] == repaired["refine_applied"]
    finally:
        await _close(live_bridge, doc_name)
