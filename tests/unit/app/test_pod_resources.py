# -*- coding: utf-8 -*-
"""Tests for unprivileged current-container resource collectors."""

from pathlib import Path

import pytest

from swe.app.pod_resources import (
    collect_pod_disk_io_bytes,
    collect_pod_open_fd_count,
)


def test_collect_pod_open_fd_count_sums_numeric_processes(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    for pid, count in (("1", 2), ("42", 3)):
        fd_dir = proc_root / pid / "fd"
        fd_dir.mkdir(parents=True)
        for index in range(count):
            (fd_dir / str(index)).touch()
    (proc_root / "self").mkdir()

    assert collect_pod_open_fd_count(proc_root) == 5


def test_collect_pod_open_fd_count_fails_on_incomplete_scan(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    (proc_root / "1" / "fd").mkdir(parents=True)
    (proc_root / "2").mkdir(parents=True)

    with pytest.raises(OSError):
        collect_pod_open_fd_count(proc_root)


def test_collect_pod_disk_io_bytes_parses_cgroup_v2(tmp_path: Path) -> None:
    proc_self_cgroup = tmp_path / "proc-self-cgroup"
    proc_self_cgroup.write_text("0::/kubepods/pod-a\n", encoding="utf-8")
    io_stat = tmp_path / "cgroup" / "kubepods" / "pod-a" / "io.stat"
    io_stat.parent.mkdir(parents=True)
    io_stat.write_text(
        "8:0 rbytes=100 wbytes=200 rios=1 wios=2\n"
        "8:16 rbytes=300 wbytes=400 rios=3 wios=4\n",
        encoding="utf-8",
    )

    assert collect_pod_disk_io_bytes(
        proc_self_cgroup=proc_self_cgroup,
        cgroup_root=tmp_path / "cgroup",
    ) == (400, 600)


def test_collect_pod_disk_io_bytes_parses_cgroup_v1(tmp_path: Path) -> None:
    proc_self_cgroup = tmp_path / "proc-self-cgroup"
    proc_self_cgroup.write_text(
        "8:blkio:/kubepods/pod-a\n",
        encoding="utf-8",
    )
    service_bytes = (
        tmp_path
        / "cgroup"
        / "blkio"
        / "kubepods"
        / "pod-a"
        / "blkio.throttle.io_service_bytes"
    )
    service_bytes.parent.mkdir(parents=True)
    service_bytes.write_text(
        "8:0 Read 100\n"
        "8:0 Write 200\n"
        "8:16 Read 300\n"
        "8:16 Write 400\n"
        "Total 1000\n",
        encoding="utf-8",
    )

    assert collect_pod_disk_io_bytes(
        proc_self_cgroup=proc_self_cgroup,
        cgroup_root=tmp_path / "cgroup",
    ) == (400, 600)


def test_collect_pod_disk_io_bytes_fails_without_matching_cgroup(
    tmp_path: Path,
) -> None:
    proc_self_cgroup = tmp_path / "proc-self-cgroup"
    proc_self_cgroup.write_text("1:cpu:/pod-a\n", encoding="utf-8")

    with pytest.raises(OSError):
        collect_pod_disk_io_bytes(
            proc_self_cgroup=proc_self_cgroup,
            cgroup_root=tmp_path / "cgroup",
        )
