# -*- coding: utf-8 -*-
"""Tests for the inotify matrix probe helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_probe_module():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "inotify_matrix_probe.py"
    )
    spec = importlib.util.spec_from_file_location(
        "inotify_matrix_probe",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_snapshot_summarizes_proc_and_runtime_api(
    tmp_path,
    monkeypatch,
) -> None:
    probe = _load_probe_module()
    proc_root = tmp_path / "proc"
    proc_dir = proc_root / "42"
    fd_dir = proc_dir / "fd"
    fdinfo_dir = proc_dir / "fdinfo"
    task_dir = proc_dir / "task"
    fd_dir.mkdir(parents=True)
    fdinfo_dir.mkdir()
    task_dir.mkdir()
    (fd_dir / "3").symlink_to("anon_inode:inotify")
    (fd_dir / "4").symlink_to("socket:[1]")
    (fdinfo_dir / "3").write_text(
        "pos:\t0\n"
        "inotify wd:1 ino:abc sdev:01 mask:00000800 ignored_mask:0\n"
        "inotify wd:2 ino:def sdev:01 mask:00000800 ignored_mask:0\n",
        encoding="utf-8",
    )
    for tid, name in (("1", "swe"), ("2", "notify-rs")):
        status_path = task_dir / tid / "status"
        status_path.parent.mkdir()
        status_path.write_text(
            f"Name:\t{name}\nState:\tS (sleeping)\n",
            encoding="utf-8",
        )

    def fake_urlopen(request, timeout):  # pylint: disable=unused-argument
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "inotify_fd_count": 1,
                        "inotify_watch_count": 2,
                        "watchfiles_stack_events": [
                            {"function": "watch", "paths": ["/workspace"]},
                        ],
                    },
                ).encode("utf-8")

        return _Response()

    monkeypatch.setattr(probe.request, "urlopen", fake_urlopen)

    snapshot = probe.collect_snapshot(
        label="after_workspace",
        pid=42,
        proc_root=proc_root,
        runtime_url="http://127.0.0.1:8080/api/runtime/inotify-diagnostic",
        token="secret",
        timeout_seconds=1.0,
    )

    assert snapshot["label"] == "after_workspace"
    assert snapshot["pid"] == 42
    assert snapshot["proc"]["inotify_fd_count"] == 1
    assert snapshot["proc"]["inotify_watch_count"] == 2
    assert snapshot["proc"]["thread_count"] == 2
    assert snapshot["proc"]["thread_name_counts"] == {
        "notify-rs": 1,
        "swe": 1,
    }
    assert snapshot["runtime"]["inotify_fd_count"] == 1
    assert snapshot["runtime"]["watchfiles_stack_event_count"] == 1
