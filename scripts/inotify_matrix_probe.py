#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect inotify/thread snapshots for runtime watcher attribution."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable
from urllib import request

_STACK_OWNER_MARKERS = (
    ("reme", "reme"),
    ("fastmcp", "fastmcp"),
    ("mcp", "mcp"),
    ("swe", "swe"),
    ("watchfiles", "watchfiles"),
)
_MAX_SUMMARY_SAMPLES = 5
_MAX_RESOLVED_PATHS_PER_WATCH = 5


def _parse_inotify_watch_line(line: str) -> dict[str, str]:
    fields: dict[str, str] = {"raw": line}
    for token in line.split():
        if ":" not in token:
            continue
        key, value = token.split(":", 1)
        if key in {"wd", "ino", "sdev", "mask"}:
            fields[key] = value
    return fields


def _parse_hex_number(value: str) -> int | None:
    try:
        return int(value.strip().lower().removeprefix("0x"), 16)
    except ValueError:
        return None


def _watch_identity(watch: dict[str, str]) -> tuple[int, int, int] | None:
    ino = watch.get("ino")
    sdev = watch.get("sdev")
    if not ino or not sdev:
        return None
    inode = _parse_hex_number(ino)
    device = _parse_hex_number(sdev)
    if inode is None or device is None:
        return None
    return (device >> 20, device & ((1 << 20) - 1), inode)


def _iter_watch_root_paths(root: Path) -> Iterator[Path]:
    yield root
    if root.is_dir():
        try:
            yield from root.rglob("*")
        except OSError:
            return


def _build_watch_path_index(
    watch_roots: list[str | Path] | None,
    target_identities: set[tuple[int, int, int]],
) -> tuple[dict[tuple[int, int, int], list[str]], dict[str, Any]]:
    index: dict[tuple[int, int, int], list[str]] = {}
    diagnostics: dict[str, Any] = {
        "enabled": bool(watch_roots),
        "roots": [str(root) for root in watch_roots or []],
        "missing_roots": [],
        "scanned_path_count": 0,
        "scan_errors": [],
    }
    if not watch_roots or not target_identities:
        return index, diagnostics

    for raw_root in watch_roots:
        root = Path(raw_root).expanduser()
        try:
            resolved_root = root.resolve()
        except OSError:
            resolved_root = root.absolute()
        if not resolved_root.exists():
            diagnostics["missing_roots"].append(str(root))
            continue

        for path in _iter_watch_root_paths(resolved_root):
            try:
                stat = path.stat()
            except OSError as exc:
                if len(diagnostics["scan_errors"]) < _MAX_SUMMARY_SAMPLES:
                    diagnostics["scan_errors"].append(
                        {
                            "path": str(path),
                            "error": str(exc),
                        },
                    )
                continue
            diagnostics["scanned_path_count"] += 1
            key = (
                os.major(stat.st_dev),
                os.minor(stat.st_dev),
                stat.st_ino,
            )
            if key not in target_identities:
                continue
            paths = index.setdefault(key, [])
            if len(paths) >= _MAX_RESOLVED_PATHS_PER_WATCH:
                continue
            path_text = str(path)
            if path_text not in paths:
                paths.append(path_text)
    return index, diagnostics


def _thread_name(status_text: str) -> str:
    for line in status_text.splitlines():
        if line.startswith("Name:"):
            return line.split(":", 1)[1].strip()
    return ""


def collect_proc_snapshot(
    *,
    pid: int,
    proc_root: str | Path = "/proc",
    watch_roots: list[str | Path] | None = None,
) -> dict[str, Any]:
    proc_dir = Path(proc_root) / str(pid)
    fd_dir = proc_dir / "fd"
    fdinfo_dir = proc_dir / "fdinfo"
    task_dir = proc_dir / "task"

    inotify_fds: list[dict[str, Any]] = []
    watch_samples_by_fd: dict[int, list[dict[str, str]]] = {}
    watch_identities: set[tuple[int, int, int]] = set()
    candidate_watch_path_samples: list[str] = []
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
        watch_lines = [
            line
            for line in fdinfo_text.splitlines()
            if line.startswith("inotify ")
        ]
        watch_samples = [
            _parse_inotify_watch_line(line)
            for line in watch_lines[:_MAX_SUMMARY_SAMPLES]
        ]
        watch_samples_by_fd[int(fd_path.name)] = watch_samples
        for watch_sample in watch_samples:
            identity = _watch_identity(watch_sample)
            if identity is not None:
                watch_identities.add(identity)
        inotify_fds.append(
            {
                "fd": int(fd_path.name),
                "watch_count": len(watch_lines),
                "watch_samples": watch_samples,
            },
        )

    watch_path_index, watch_resolution_diagnostics = _build_watch_path_index(
        watch_roots,
        watch_identities,
    )
    for inotify_fd in inotify_fds:
        watch_samples = watch_samples_by_fd.get(int(inotify_fd["fd"]), [])
        for watch_sample in watch_samples:
            identity = _watch_identity(watch_sample)
            if identity is None:
                continue
            candidate_paths = watch_path_index.get(identity)
            if not candidate_paths:
                continue
            watch_sample["candidate_paths"] = candidate_paths
            for candidate_path in candidate_paths:
                if len(candidate_watch_path_samples) >= _MAX_SUMMARY_SAMPLES:
                    break
                if candidate_path not in candidate_watch_path_samples:
                    candidate_watch_path_samples.append(candidate_path)

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
        "candidate_watch_path_samples": candidate_watch_path_samples,
        "watch_resolution_diagnostics": watch_resolution_diagnostics,
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
    watch_roots: list[str | Path] | None = None,
    runtime_url: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "label": label,
        "pid": pid,
        "proc": collect_proc_snapshot(
            pid=pid,
            proc_root=proc_root,
            watch_roots=watch_roots,
        ),
    }
    if runtime_url:
        snapshot["runtime"] = collect_runtime_snapshot(
            runtime_url=runtime_url,
            token=token,
            timeout_seconds=timeout_seconds,
        )
    return snapshot


def _notify_thread_count(snapshot: dict[str, Any]) -> int:
    thread_counts = snapshot.get("proc", {}).get("thread_name_counts", {})
    if not isinstance(thread_counts, dict):
        return 0
    total = 0
    for name, count in thread_counts.items():
        if not str(name).startswith("notify-rs"):
            continue
        try:
            total += int(count)
        except (TypeError, ValueError):
            continue
    return total


def _metric(snapshot: dict[str, Any], key: str) -> int:
    value = snapshot.get("proc", {}).get(key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize_matrix(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize per-label inotify totals and deltas for matrix runs."""
    steps: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for snapshot in snapshots:
        totals = {
            "inotify_fd_count": _metric(snapshot, "inotify_fd_count"),
            "inotify_watch_count": _metric(snapshot, "inotify_watch_count"),
            "notify_thread_count": _notify_thread_count(snapshot),
        }
        previous_totals = (
            {
                "inotify_fd_count": _metric(previous, "inotify_fd_count"),
                "inotify_watch_count": _metric(
                    previous,
                    "inotify_watch_count",
                ),
                "notify_thread_count": _notify_thread_count(previous),
            }
            if previous is not None
            else None
        )
        deltas = (
            {
                key: value - previous_totals[key]
                for key, value in totals.items()
            }
            if previous_totals is not None
            else None
        )
        steps.append(
            {
                "label": snapshot.get("label"),
                "totals": totals,
                "has_previous_snapshot": previous_totals is not None,
                "consecutive_delta": deltas,
            },
        )
        previous = snapshot
    return {"steps": steps}


def _input_from_stderr(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def collect_snapshots(
    *,
    labels: list[str],
    pid: int,
    proc_root: str | Path = "/proc",
    watch_roots: list[str | Path] | None = None,
    runtime_url: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 5.0,
    prompt_between_labels: bool = False,
    input_func: Callable[[str], str] = _input_from_stderr,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for label in labels:
        if prompt_between_labels:
            input_func(
                f"Prepare matrix step for label {label!r}, then press Enter "
                "to collect snapshot...",
            )
        snapshots.append(
            collect_snapshot(
                label=label,
                pid=pid,
                proc_root=proc_root,
                watch_roots=watch_roots,
                runtime_url=runtime_url,
                token=token,
                timeout_seconds=timeout_seconds,
            ),
        )
    return snapshots


def load_snapshots_from_files(paths: list[Path]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: {exc}") from exc
        if isinstance(payload, dict) and isinstance(
            payload.get("snapshots"),
            list,
        ):
            for index, item in enumerate(payload["snapshots"]):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"{path} snapshots[{index}] is not an object",
                    )
                snapshots.append(item)
            continue
        if isinstance(payload, dict) and "proc" in payload:
            snapshots.append(payload)
            continue
        raise ValueError(f"{path} does not contain probe snapshots")
    return snapshots


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
        help=(
            "Snapshot label. Repeat to collect multiple labels; by default "
            "they are sampled back-to-back unless --prompt-between-labels is set."
        ),
    )
    parser.add_argument(
        "--from-json",
        action="append",
        type=Path,
        help=(
            "Load snapshots from a previous probe JSON file. Repeat to merge "
            "separate matrix captures and recompute the summary."
        ),
    )
    parser.add_argument(
        "--prompt-between-labels",
        action="store_true",
        help=(
            "Pause before each label so an operator can perform the next "
            "matrix action before sampling."
        ),
    )
    parser.add_argument(
        "--resolve-watch-root",
        action="append",
        dest="watch_roots",
        type=Path,
        help=(
            "Resolve fdinfo inotify sdev/ino samples to paths under this "
            "root. Repeat for multiple workspace roots."
        ),
    )
    args = parser.parse_args()
    if args.from_json and args.label:
        parser.error("--from-json cannot be combined with --label")
    if not args.from_json and not args.label:
        parser.error("one of --label or --from-json is required")
    if args.from_json and args.prompt_between_labels:
        parser.error("--prompt-between-labels requires --label")
    if args.from_json and args.watch_roots:
        parser.error("--resolve-watch-root requires --label")
    return args


def main() -> int:
    args = _parse_args()
    try:
        snapshots = (
            load_snapshots_from_files(args.from_json or [])
            if args.from_json
            else collect_snapshots(
                labels=args.label or [],
                pid=args.pid,
                proc_root=args.proc_root,
                watch_roots=args.watch_roots,
                runtime_url=args.runtime_url,
                token=args.token,
                timeout_seconds=args.timeout_seconds,
                prompt_between_labels=args.prompt_between_labels,
                input_func=_input_from_stderr,
            )
        )
    except ValueError as exc:
        print(f"inotify_matrix_probe: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "snapshots": snapshots,
                "summary": summarize_matrix(snapshots),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
