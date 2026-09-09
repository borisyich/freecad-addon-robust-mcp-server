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
_TERMINAL_STATES = {
    "completed",
    "failed",
    "cancelled",
    "unknown_after_timeout",
    "unknown_after_transport_error",
}


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


def _nested_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for item in value.values():
            found = _nested_value(item, key)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _nested_value(item, key)
            if found is not None:
                return found
    return None


def _text_value(text: str, key: str) -> str | None:
    match = re.search(
        rf"(?:^|[\s;,]){re.escape(key)}\s*=\s*([^\s;,]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _tri_state(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _execution_metadata(value: Any) -> dict[str, Any]:
    """Extract transport execution evidence without assuming it is still running."""
    text = _payload_text(value)

    def field(key: str) -> Any:
        structured = _nested_value(value, key)
        return structured if structured is not None else _text_value(text, key)

    request_id = field("request_id")
    operation_state = field("operation_state")
    continues_raw = field("continues_running")
    error_type = field("error_type")
    timed_out = bool(
        str(error_type).strip().lower() == "timeouterror"
        or re.search(r"\b(?:timeouterror|timed out|timeout)\b", text, re.IGNORECASE)
    )
    return {
        "request_id": str(request_id) if request_id else None,
        "operation_state": (
            str(operation_state).strip().lower() if operation_state else None
        ),
        "continues_running": _tri_state(continues_raw),
        "timed_out": timed_out,
        "has_execution_state": operation_state is not None or continues_raw is not None,
    }


def _is_error_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(
        _tri_state(_nested_value(value, key)) is True for key in ("isError", "is_error")
    )


def _stopped_before_start(
    operation_state: str | None,
    continues_running: bool | None,
    *,
    timed_out: bool,
) -> bool:
    if continues_running is True:
        return False
    if operation_state == "cancelled":
        return True
    return timed_out and (
        operation_state == "not_started"
        or (operation_state == "queued" and continues_running is False)
    )


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

    def _mark_unknown(job: dict[str, Any], *, after_timeout: bool) -> None:
        job["state"] = (
            "unknown_after_timeout"
            if after_timeout
            else "unknown_after_transport_error"
        )
        if job.get("operation_state") not in {"queued", "running", "cancelled"}:
            job["operation_state"] = "unknown"
        continues = job.get("continues_running")
        job["freecad_busy"] = continues if isinstance(continues, bool) else None
        job["termination_reason"] = job["state"]

    async def _follow_bridge_request(
        job: dict[str, Any],
        request_id: str,
        metadata: dict[str, Any],
    ) -> None:
        job["bridge_request_id"] = request_id
        initial_state = metadata.get("operation_state") or "unknown"
        initial_continues = metadata.get("continues_running")
        job["state"] = (
            "freecad_running"
            if initial_state in {"queued", "running"} or initial_continues is True
            else "tracking_execution"
        )
        job["operation_state"] = initial_state
        job["continues_running"] = initial_continues
        job["freecad_busy"] = (
            initial_continues if isinstance(initial_continues, bool) else None
        )
        if get_bridge is None:
            _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
            return
        bridge = await get_bridge()
        status_reader = getattr(bridge, "get_execution_status", None)
        if status_reader is None:
            _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
            return
        while True:
            try:
                status = await status_reader(request_id)
            except Exception as exc:
                _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
                job["error"] = (
                    f"{job['error']}; execution status unavailable: "
                    f"{type(exc).__name__}: {exc}"
                )
                return
            job["bridge_status"] = _jsonable(status)
            if not status.get("found", False):
                _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
                return
            operation_state = (
                str(status.get("operation_state", "unknown")).strip().lower()
            )
            continues = _tri_state(status.get("continues_running"))
            job["operation_state"] = operation_state
            job["continues_running"] = continues
            job["freecad_busy"] = continues if isinstance(continues, bool) else None
            if _stopped_before_start(
                operation_state,
                continues,
                timed_out=bool(metadata.get("timed_out")),
            ):
                job["state"] = "cancelled"
                job["termination_reason"] = (
                    "timeout_before_start"
                    if metadata.get("timed_out")
                    else "remote_cancelled"
                )
                job["error"] = status.get("error_message") or status.get("stderr")
            elif continues is True or (
                operation_state in {"queued", "running"} and continues is not False
            ):
                job["state"] = "freecad_running"
                await asyncio.sleep(0.25)
                continue
            elif operation_state in {"queued", "running"}:
                _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
            elif status.get("success") is True:
                job["state"] = "completed"
                job["result"] = _jsonable(status.get("result"))
                job["result_source"] = "retained_bridge_execution"
                job["error"] = None
            elif operation_state == "unknown" or continues is None:
                _mark_unknown(job, after_timeout=bool(metadata.get("timed_out")))
            elif operation_state in {"completed", "failed"} or (
                status.get("success") is False
            ):
                job["state"] = "failed"
                job["termination_reason"] = "tool_failure"
                job["error"] = (
                    status.get("error_traceback")
                    or status.get("error_message")
                    or status.get("stderr")
                    or "Retained FreeCAD execution failed"
                )
            else:
                job["state"] = "failed"
                job["termination_reason"] = "tool_failure"
                job["error"] = (
                    status.get("error_traceback")
                    or status.get("error_message")
                    or status.get("stderr")
                    or "Retained FreeCAD execution failed"
                )
            return

    async def _handle_error(job: dict[str, Any], value: Any) -> None:
        job["error"] = _payload_text(value)
        metadata = _execution_metadata(value)
        job["timed_out"] = metadata["timed_out"]
        operation_state = metadata["operation_state"]
        continues = metadata["continues_running"]
        request_id = metadata["request_id"]
        if operation_state is not None:
            job["operation_state"] = operation_state
        if metadata["has_execution_state"]:
            job["continues_running"] = continues
            job["freecad_busy"] = continues if isinstance(continues, bool) else None
        if _stopped_before_start(
            operation_state,
            continues,
            timed_out=metadata["timed_out"],
        ):
            job["state"] = "cancelled"
            job["operation_state"] = operation_state
            job["continues_running"] = False
            job["freecad_busy"] = False
            job["termination_reason"] = (
                "timeout_before_start" if metadata["timed_out"] else "remote_cancelled"
            )
        elif operation_state in {"completed", "failed", "not_started"} and (
            continues is not True
        ):
            job["state"] = "failed"
            job["termination_reason"] = "tool_failure"
        elif request_id and (metadata["has_execution_state"] or metadata["timed_out"]):
            await _follow_bridge_request(job, request_id, metadata)
        elif metadata["timed_out"] or operation_state == "unknown":
            job["operation_state"] = operation_state or "unknown"
            job["continues_running"] = continues
            _mark_unknown(job, after_timeout=metadata["timed_out"])
        else:
            job["state"] = "failed"
            if operation_state is None:
                job["operation_state"] = "failed"
                job["continues_running"] = False
                job["freecad_busy"] = False
            job["termination_reason"] = "tool_failure"

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
            if _is_error_payload(serialized):
                await _handle_error(job, serialized)
            else:
                job["result"] = serialized
                job["state"] = "completed"
        except asyncio.CancelledError:
            job["state"] = "cancelled"
            job["error"] = "Cancelled before the wrapped tool started"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            await _handle_error(job, error)
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
            "timed_out": False,
            "termination_reason": None,
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
        elif job["state"] in {"running", "freecad_running", "tracking_execution"}:
            job["cancellable"] = False
            job["error"] = (
                "Cancellation requested, but an active FreeCAD/OCCT main-thread "
                "operation cannot be interrupted safely; poll until it finishes"
            )
        return _public(job, include_result=False)
