"""Tests for timeout cancellation in the FreeCAD-side execution queue."""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[3]
    / "freecad"
    / "RobustMCPBridge"
    / "freecad_mcp_bridge"
    / "server.py"
)
SPEC = importlib.util.spec_from_file_location("freecad_bridge_queue_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_cancelled_request_is_not_executed():
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)
    request = MODULE.ExecutionRequest(
        "raise RuntimeError('cancelled code must not run')",
        timeout_ms=1,
    )
    request.cancelled.set()
    plugin._request_queue.put(request)

    plugin._process_queue()

    assert request.completed.is_set()
    assert request.result is not None
    assert request.result["error_type"] == "CancelledError"


def test_report_view_error_turns_successful_exec_into_failure(monkeypatch):
    """A FreeCAD Report View exception must not be returned as success."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)
    snapshots = iter(
        [
            "",
            "10:42:16  <Exception> Property 'A1' not found in 'Parameters.A1'\n",
        ]
    )
    monkeypatch.setattr(plugin, "_get_report_view_text", lambda: next(snapshots))

    result = plugin._execute_code_sync("_result_ = {'ok': True}")

    assert result["success"] is False
    assert result["error_type"] == "FreeCADReportError"
    assert "Property 'A1' not found" in result["error_traceback"]


def test_report_view_is_read_after_gui_events_are_flushed(monkeypatch):
    """Queued Spreadsheet diagnostics must be visible before success is decided."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)
    state = {"flushed": False}

    def report_text():
        if state["flushed"]:
            return "Spreadsheet: Invalid expression in cell A1\n"
        return ""

    def flush():
        state["flushed"] = True

    monkeypatch.setattr(plugin, "_get_report_view_text", report_text)
    monkeypatch.setattr(plugin, "_flush_gui_events", flush)

    result = plugin._execute_code_sync("_result_ = {'success': True}")

    assert result["success"] is False
    assert result["error_type"] == "FreeCADReportError"
    assert "Invalid expression in cell A1" in result["error_traceback"]


def test_report_view_non_error_message_does_not_fail(monkeypatch):
    """Informational Report View output must not make a request fail."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)
    snapshots = iter(["", "10:42:16  Recompute finished\n"])
    monkeypatch.setattr(plugin, "_get_report_view_text", lambda: next(snapshots))

    result = plugin._execute_code_sync("_result_ = 42")

    assert result["success"] is True
    assert result["result"] == 42


def test_report_view_delta_uses_only_new_text():
    """Old Report View errors must not poison later bridge requests."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)

    assert plugin._report_view_delta("old error\n", "old error\nnew line\n") == (
        "new line\n"
    )


def test_report_view_delta_handles_trimmed_prefix():
    """Buffer trimming must not re-report old messages as new failures."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)

    shared_tail = "shared tail with enough stable context\n"
    before = "old line 1\nold line 2\n" + shared_tail
    after = shared_tail + "new error\n"

    assert plugin._report_view_delta(before, after) == "new error\n"


def test_report_view_errors_are_deduplicated():
    """Repeated recompute messages should produce one concise failure line."""
    text = "10:00 <Exception> No profile linked\n10:00 <Exception> No profile linked\n"

    assert MODULE._extract_report_error_lines(text) == [
        "10:00 <Exception> No profile linked"
    ]


def test_report_view_recognizes_spreadsheet_formula_errors_case_insensitively():
    """Spreadsheet diagnostics should translate to FreeCADReportError evidence."""
    assert MODULE._extract_report_error_lines(
        "10:00 spreadsheet: invalid expression in B7\n"
    ) == ["10:00 spreadsheet: invalid expression in B7"]
    assert MODULE._extract_report_error_lines("10:00 ERR: division by zero\n") == [
        "10:00 ERR: division by zero"
    ]
    assert MODULE._extract_report_error_lines("10:00 stderr: diagnostic\n") == []


def test_report_view_delta_ignores_tiny_accidental_overlap():
    """A shared character must not strip the start of genuinely new output."""
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)

    assert plugin._report_view_delta("old x", "x<Exception> new") == (
        "x<Exception> new"
    )
