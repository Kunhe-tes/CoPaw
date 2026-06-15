# -*- coding: utf-8 -*-
"""Unprivileged collectors for current-container resources."""

from __future__ import annotations

from pathlib import Path

_PROC_ROOT = Path("/proc")
_PROC_SELF_CGROUP = _PROC_ROOT / "self" / "cgroup"
_CGROUP_ROOT = Path("/sys/fs/cgroup")


def collect_pod_open_fd_count(proc_root: Path = _PROC_ROOT) -> int:
    """Count file descriptors across the current PID namespace."""
    process_dirs = [
        entry for entry in proc_root.iterdir() if entry.name.isdigit()
    ]
    return sum(
        len(list((process_dir / "fd").iterdir()))
        for process_dir in process_dirs
    )


def collect_pod_disk_io_bytes(
    *,
    proc_self_cgroup: Path = _PROC_SELF_CGROUP,
    cgroup_root: Path = _CGROUP_ROOT,
) -> tuple[int, int]:
    """Return cumulative read and write bytes for the current cgroup."""
    memberships = proc_self_cgroup.read_text(encoding="utf-8").splitlines()
    for membership in memberships:
        hierarchy_id, controllers, cgroup_path = membership.split(
            ":",
            maxsplit=2,
        )
        relative_path = cgroup_path.lstrip("/")
        if hierarchy_id == "0" and not controllers:
            return _parse_v2_io_stat(cgroup_root / relative_path / "io.stat")
        if "blkio" in controllers.split(","):
            blkio_root = cgroup_root / "blkio" / relative_path
            for file_name in (
                "blkio.throttle.io_service_bytes",
                "blkio.io_service_bytes",
            ):
                path = blkio_root / file_name
                if path.exists():
                    return _parse_v1_service_bytes(path)
    raise OSError("Current container cgroup disk I/O counters are unavailable")


def _parse_v2_io_stat(path: Path) -> tuple[int, int]:
    read_bytes = 0
    write_bytes = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise OSError("Current container cgroup v2 io.stat is empty")
    for line in lines:
        counters = dict(
            item.split("=", maxsplit=1) for item in line.split()[1:]
        )
        read_bytes += int(counters.get("rbytes", 0))
        write_bytes += int(counters.get("wbytes", 0))
    return read_bytes, write_bytes


def _parse_v1_service_bytes(path: Path) -> tuple[int, int]:
    read_bytes = 0
    write_bytes = 0
    found = False
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        _device, operation, value = parts
        if operation == "Read":
            read_bytes += int(value)
            found = True
        elif operation == "Write":
            write_bytes += int(value)
            found = True
    if not found:
        raise OSError("Current container cgroup v1 blkio counters are empty")
    return read_bytes, write_bytes
