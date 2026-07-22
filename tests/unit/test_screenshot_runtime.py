"""Tests for the generated FreeCAD screenshot workflow."""

from freecad_mcp.bridge._screenshot_runtime import build_screenshot_code


def test_screenshot_runtime_activates_fits_updates_and_verifies_file() -> None:
    """Generated code should follow the proven GUI saveImage sequence."""
    code = build_screenshot_code(
        view_angle="Isometric",
        width=800,
        height=600,
        doc_name="Bracket",
        fit_all=True,
        background="White",
        show_corner_cross=True,
        corner_cross_size=10,
        save_to_disk=True,
        output_path="screenshots/bracket.png",
        return_data=False,
    )

    assert "FreeCAD.setActiveDocument(doc.Name)" in code
    assert "view.viewIsometric()" in code
    assert "view.fitAll()" in code
    assert "view.setCornerCrossVisible(show_corner_cross)" in code
    assert "view.setCornerCrossSize(corner_cross_size)" in code
    assert "view.isCornerCrossVisible()" in code
    assert "view.getCornerCrossSize()" in code
    assert "view.setCornerCrossVisible(previous_corner_cross_visible)" in code
    assert code.count("FreeCADGui.updateGui()") >= 2
    assert "view.saveImage" in code
    assert "os.path.getsize(image_path)" in code
    assert '"saved_to_disk": bool(save_to_disk)' in code


def test_screenshot_runtime_supports_temp_base64_mode() -> None:
    """Backward-compatible screenshots may still return base64 only."""
    code = build_screenshot_code(
        view_angle="Front",
        width=640,
        height=480,
        doc_name=None,
        fit_all=True,
        background="Current",
        show_corner_cross=False,
        corner_cross_size=10,
        save_to_disk=False,
        output_path=None,
        return_data=True,
    )

    assert "tempfile.NamedTemporaryFile" in code
    assert "base64.b64encode" in code
    assert "os.unlink(image_path)" in code
