#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect inotify/thread snapshots for runtime watcher attribution."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import request

_STACK_OWNER_MARKERS = (
    ("reme", "reme"),
    ("fastmcp", "fastmcp"),
    ("mcp", "mcp"),
    ("swe", "swe"),
    ("watchfiles", "watchfiles"),
)
_MAX_SUMMARY_SAMPLES = 5


def _parse_inotify_watch_count(fdinfo_text: str) -> int:
    return sum(
        1 for line in fdinfo_text.splitlines() if line.startswith("inotify ")
    )


def _thread_name(status_text: str) -> str:
    for line in status_text.splitlines():
        if line.startswith("Name:"):
            return line.split(":", 1)[1].strip()
    return ""


def collect_proc_snapshot(
    *,
    pid: int,
    proc_root: str | Path = "/proc",
) -> dict[str, Any]:
    proc_dir = Path(proc_root) / str(pid)
    fd_dir = proc_dir / "fd"
    fdinfo_dir = proc_dir / "fdinfo"
    task_dir = proc_dir / "task"

    inotify_fds: list[dict[str, Any]] = []
    for fd_path in sorted(fd_dir.iterdir(), key=lambda path: int(path.name)):
        try:
            target = os.readlink(fd_path)
        except OSError:
            continue
        if target != "anon_inode:inotify":
            continue
        try:
            fdinfo_text = (fdinfo_dir / fd_path.name).read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            fdinfo_text = ""
        inotify_fds.append(
            {
                "fd": int(fd_path.name),
                "watch_count": _parse_inotify_watch_count(fdinfo_text),
            },
        )

    thread_names: Counter[str] = Counter()
    for status_path in sorted(task_dir.glob("*/status")):
        try:
            name = _thread_name(status_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if name:
            thread_names[name] += 1

    return {
        "inotify_fd_count": len(inotify_fds),
        "inotify_watch_count": sum(
            item["watch_count"] for item in inotify_fds
        ),
        "inotify_fds": inotify_fds,
        "thread_count": sum(thread_names.values()),
        "thread_name_counts": dict(sorted(thread_names.items())),
    }


def _normalize_stack_frame(frame: Any) -> str:
    if isinstance(frame, dict):
        filename = str(
            frame.get("filename")
            or frame.get("file")
            or frame.get("path")
            or "",
        )
        function = str(frame.get("name") or frame.get("function") or "")
        lineno = frame.get("lineno") or frame.get("line")
        location = filename
        if lineno:
            location = f"{location}:{lineno}" if location else str(lineno)
        if function:
            return f"{location}::{function}" if location else function
        return location
    return str(frame)


def _stack_owner_and_sample(stack: Any) -> tuple[str, str | None]:
    if not isinstance(stack, list):
        return "unknown", None
    normalized_frames = []
    for frame in stack:
        normalized = _normalize_stack_frame(frame)
        if normalized:
            normalized_frames.append(normalized)
    for marker, owner in _STACK_OWNER_MARKERS:
        for frame in normalized_frames:
            if marker in frame.lower():
                return owner, frame
    for frame in normalized_frames:
        lowered = frame.lower()
        if (
            "inotify_matrix_probe" not in lowered
            and "runtime_diagnostic" not in lowered
        ):
            return frame, frame
    return "unknown", None


def summarize_watchfiles_stack_events(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    function_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    path_samples: list[str] = []
    owner_samples: dict[str, list[str]] = {}

    for event in events:
        function = str(event.get("function") or "unknown")
        owner, owner_sample = _stack_owner_and_sample(event.get("stack"))
        function_counts[function] += 1
        owner_counts[owner] += 1

        for raw_path in event.get("paths") or []:
            if len(path_samples) >= _MAX_SUMMARY_SAMPLES:
                break
            path = str(raw_path)
            if path not in path_samples:
                path_samples.append(path)

        samples = owner_samples.setdefault(owner, [])
        if (
            owner_sample
            and len(samples) < _MAX_SUMMARY_SAMPLES
            and owner_sample not in samples
        ):
            samples.append(owner_sample)

    return {
        "event_count": len(events),
        "function_counts": dict(sorted(function_counts.items())),
        "owner_counts": dict(sorted(owner_counts.items())),
        "path_samples": path_samples,
        "owner_samples": {
            owner: samples
            for owner, samples in sorted(owner_samples.items())
            if samples
        },
    }


def collect_runtime_snapshot(
    *,
    runtime_url: str,
    token: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    headers = {}
    if token:
        headers["X-Runtime-Diagnostic-Token"] = token
    runtime_request = request.Request(runtime_url, headers=headers)
    with request.urlopen(runtime_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    raw_events = payload.get("watchfiles_stack_events") or []
    events = [event for event in raw_events if isinstance(event, dict)]
    payload["watchfiles_stack_event_count"] = len(events)
    payload["watchfiles_stack_summary"] = summarize_watchfiles_stack_events(
        events,
    )
    return payload


def collect_snapshot(
    *,
    label: str,
    pid: int,
    proc_root: str | Path = "/proc",
    runtime_url: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "label": label,
        "pid": pid,
        "proc": collect_proc_snapshot(pid=pid, proc_root=proc_root),
    }
    if runtime_url:
        snapshot["runtime"] = collect_runtime_snapshot(
            runtime_url=runtime_url,
            token=token,
            timeout_seconds=timeout_seconds,
        )
    return snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect labeled inotify/thread snapshots. Run after each "
            "matrix step: empty, N workspaces, N MCP clients, N queries."
        ),
    )
    parser.add_argument("--pid", type=int, default=1)
    parser.add_argument("--proc-root", default="/proc")
    parser.add_argument(
        "--runtime-url",
        help=(
            "Optional /api/runtime/inotify-diagnostic URL. Include "
            "?include_fdinfo=true when SWE_RUNTIME_DIAGNOSTIC_TOKEN is set."
        ),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("SWE_RUNTIME_DIAGNOSTIC_TOKEN"),
        help="Runtime diagnostic token; defaults to env var.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--label",
        action="append",
        required=True,
        help="Snapshot label. Repeat to collect multiple back-to-back labels.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshots = [
        collect_snapshot(
            label=label,
            pid=args.pid,
            proc_root=args.proc_root,
            runtime_url=args.runtime_url,
            token=args.token,
            timeout_seconds=args.timeout_seconds,
        )
        for label in args.label
    ]
    print(json.dumps({"snapshots": snapshots}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
