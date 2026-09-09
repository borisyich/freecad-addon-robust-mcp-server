"""Session-local background jobs for long-running MCP tool calls."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

_JOB_TOOL_NAMES = {"start_tool_job", "get_tool_job", "cancel_tool_job"}
_MAX_JOBS = 64
_TERMINAL_STATES = {"completed", "failed", "cancelled", "unknown_after_timeout"}


def _jsonable(value: Any) -> Any:
    """Convert MCP SDK models and ordinary containers into JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return repr(value)


def _payload_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_payload_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_payload_text(item) for item in value)
    return str(value)


def _running_request_id(value: Any) -> str | None:
    text = _payload_text(value)
    if "continues_running=true" not in text.lower():
        return None
    match = re.search(r"request_id=([0-9A-Za-z-]+)", text)
    return match.group(1) if match else None


def _is_error_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(value.get("isError") or value.get("is_error"))


def register_job_tools(
    mcp: Any,
    get_bridge: Callable[[], Awaitable[Any]] | None = None,
) -> None:
    """Register non-blocking wrappers for any ordinary MCP tool."""
    jobs: dict[str, dict[str, Any]] = {}

    def _public(job: dict[str, Any], *, include_result: bool) -> dict[str, Any]:
        payload = {
            key: value for key, value in job.items() if key not in {"task", "result"}
        }
        if include_result and job["state"] in _TERMINAL_STATES:
            payload["result"] = job.get("result")
        return payload

    def _prune_finished() -> None:
        if len(jobs) < _MAX_JOBS:
            return
        finished = sorted(
            (job for job in jobs.values() if job["state"] in _TERMINAL_STATES),
            key=lambda item: item["created_at"],
        )
        while len(jobs) >= _MAX_JOBS and finished:
            jobs.pop(finished.pop(0)["job_id"], None)
        if len(jobs) >= _MAX_JOBS:
            raise ValueError(
                "Tool job limit (64) reached and every retained job is active"
            )

    async def _follow_bridge_request(job: dict[str, Any], request_id: str) -> None:
        job["bridge_request_id"] = request_id
        job["state"] = "freecad_running"
        job["operation_state"] = "running"
        job["continues_running"] = True
        job["freecad_busy"] = True
        if get_bridge is None:
            job["state"] = "unknown_after_timeout"
            job["operation_state"] = "unknown"
            job["continues_running"] = None
            job["freecad_busy"] = None
            return
        bridge = await get_bridge()
        status_reader = getattr(bridge, "get_execution_status", None)
        if status_reader is None:
            job["state"] = "unknown_after_timeout"
            job["operation_state"] = "unknown"
            job["continues_running"] = None
            job["freecad_busy"] = None
            return
        while True:
            try:
                status = await status_reader(request_id)
            except Exception as exc:
                job["state"] = "unknown_after_timeout"
                job["operation_state"] = "unknown"
                job["continues_running"] = None
                job["freecad_busy"] = None
                job["error"] = (
                    f"{job['error']}; execution status unavailable: "
                    f"{type(exc).__name__}: {exc}"
                )
                return
            job["bridge_status"] = _jsonable(status)
            if not status.get("found", False):
                job["state"] = "unknown_after_timeout"
                job["operation_state"] = "unknown"
                job["continues_running"] = None
                job["freecad_busy"] = None
                return
            operation_state = str(status.get("operation_state", "unknown"))
            continues = status.get("continues_running")
            job["operation_state"] = operation_state
            job["continues_running"] = continues
            job["freecad_busy"] = bool(continues)
            if operation_state in {"queued", "running"} or continues is True:
                await asyncio.sleep(0.25)
                continue
            if operation_state == "cancelled":
                job["state"] = "cancelled"
                job["error"] = status.get("error_message") or status.get("stderr")
            elif status.get("success") is True:
                job["state"] = "completed"
                job["result"] = _jsonable(status.get("result"))
                job["result_source"] = "retained_bridge_execution"
                job["error"] = None
            else:
                job["state"] = "failed"
                job["error"] = (
                    status.get("error_traceback")
                    or status.get("error_message")
                    or status.get("stderr")
                    or "Retained FreeCAD execution failed"
                )
            return

    async def _run(job: dict[str, Any]) -> None:
        try:
            # Yield once so a caller may cancel a job that has only been queued.
            await asyncio.sleep(0)
            if job["state"] == "cancelled":
                return
            job["state"] = "running"
            job["cancellable"] = False
            job["started_at"] = time.time()
            result = await mcp.call_tool(job["tool_name"], job["arguments"])
            serialized = _jsonable(result)
            request_id = _running_request_id(serialized)
            if request_id is not None:
                job["error"] = _payload_text(serialized)
                await _follow_bridge_request(job, request_id)
            elif _is_error_payload(serialized):
                job["state"] = "failed"
                job["error"] = _payload_text(serialized)
            else:
                job["result"] = serialized
                job["state"] = "completed"
        except asyncio.CancelledError:
            job["state"] = "cancelled"
            job["error"] = "Cancelled before the wrapped tool started"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            request_id = _running_request_id(error)
            if request_id is not None:
                job["error"] = error
                await _follow_bridge_request(job, request_id)
            else:
                job["state"] = "failed"
                job["error"] = error
        finally:
            if job["state"] in _TERMINAL_STATES:
                job["completed_at"] = time.time()

    @mcp.tool()
    async def start_tool_job(
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start any ordinary MCP tool asynchronously and return a polling ID."""
        normalized_name = tool_name.strip()
        if not normalized_name:
            raise ValueError("tool_name must not be empty")
        if normalized_name in _JOB_TOOL_NAMES:
            raise ValueError("Job-control tools cannot be submitted as jobs")
        manager = getattr(mcp, "_tool_manager", None)
        if manager is not None and manager.get_tool(normalized_name) is None:
            raise ValueError(f"Unknown MCP tool: {normalized_name!r}")
        _prune_finished()
        job_id = str(uuid.uuid4())
        job: dict[str, Any] = {
            "job_id": job_id,
            "tool_name": normalized_name,
            "arguments": dict(arguments or {}),
            "state": "queued",
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "cancel_requested": False,
            "cancellable": True,
            "isolation": "in_process",
            "hard_cancel_supported": False,
            "freecad_busy": False,
            "operation_state": "queued",
            "continues_running": False,
            "bridge_request_id": None,
            "bridge_status": None,
            "result_source": "mcp_tool",
            "error": None,
            "result": None,
            "task": None,
        }
        jobs[job_id] = job
        job["task"] = asyncio.create_task(_run(job), name=f"freecad-tool-job-{job_id}")
        return _public(job, include_result=False)

    @mcp.tool()
    async def get_tool_job(
        job_id: str,
        include_result: bool = True,
    ) -> dict[str, Any]:
        """Poll a background tool job and optionally return its final result."""
        job = jobs.get(job_id.strip())
        if job is None:
            raise ValueError(f"Tool job not found: {job_id!r}")
        return _public(job, include_result=include_result)

    @mcp.tool()
    async def cancel_tool_job(job_id: str) -> dict[str, Any]:
        """Cancel queued work; report running FreeCAD/OCCT work as non-interruptible."""
        job = jobs.get(job_id.strip())
        if job is None:
            raise ValueError(f"Tool job not found: {job_id!r}")
        job["cancel_requested"] = True
        if job["state"] == "queued":
            job["state"] = "cancelled"
            job["cancellable"] = False
            task = job.get("task")
            if task is not None:
                task.cancel()
            job["completed_at"] = time.time()
        elif job["state"] in {"running", "freecad_running"}:
            job["cancellable"] = False
            job["error"] = (
                "Cancellation requested, but an active FreeCAD/OCCT main-thread "
                "operation cannot be interrupted safely; poll until it finishes"
            )
        return _public(job, include_result=False)
