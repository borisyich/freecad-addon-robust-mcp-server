"""Session-local background jobs for long-running MCP tool calls."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from typing import Any

_JOB_TOOL_NAMES = {"start_tool_job", "get_tool_job", "cancel_tool_job"}
_MAX_JOBS = 64


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


def register_job_tools(mcp: Any) -> None:
    """Register non-blocking wrappers for any ordinary MCP tool."""
    jobs: dict[str, dict[str, Any]] = {}

    def _public(job: dict[str, Any], *, include_result: bool) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in job.items()
            if key not in {"task", "result"}
        }
        if include_result and job["state"] in {"completed", "failed"}:
            payload["result"] = job.get("result")
        return payload

    def _prune_finished() -> None:
        if len(jobs) < _MAX_JOBS:
            return
        finished = sorted(
            (
                job
                for job in jobs.values()
                if job["state"] in {"completed", "failed", "cancelled"}
            ),
            key=lambda item: item["created_at"],
        )
        while len(jobs) >= _MAX_JOBS and finished:
            jobs.pop(finished.pop(0)["job_id"], None)
        if len(jobs) >= _MAX_JOBS:
            raise ValueError(
                "Tool job limit (64) reached and every retained job is active"
            )

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
            job["result"] = _jsonable(result)
            job["state"] = "completed"
        except asyncio.CancelledError:
            job["state"] = "cancelled"
            job["error"] = "Cancelled before the wrapped tool started"
        except Exception as exc:
            job["state"] = "failed"
            job["error"] = f"{type(exc).__name__}: {exc}"
        finally:
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
        elif job["state"] == "running":
            job["cancellable"] = False
            job["error"] = (
                "Cancellation requested, but an active FreeCAD/OCCT main-thread "
                "operation cannot be interrupted safely; poll until it finishes"
            )
        return _public(job, include_result=False)
