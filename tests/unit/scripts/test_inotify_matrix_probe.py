# -*- coding: utf-8 -*-
"""Tests for the inotify matrix probe helper."""

from __future__ import annotations

import importlib.util
import json
import builtins
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
                            {
                                "function": "awatch",
                                "paths": ["/workspace/memory"],
                                "stack": [
                                    '  File "/opt/python/asyncio/events.py", '
                                    "line 80, in _run\n",
                                    "  File "
                                    '"/site-packages/reme/core/'
                                    'file_watcher/base_file_watcher.py", '
                                    "line 184, in _watch_loop\n",
                                ],
                            },
                            {
                                "function": "watch",
                                "paths": ["/tmp/mcp.json"],
                                "stack": [
                                    {
                                        "filename": (
                                            "/site-packages/fastmcp/client.py"
                                        ),
                                        "lineno": 42,
                                        "function": "start",
                                    },
                                ],
                            },
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
    assert snapshot["proc"]["inotify_fds"] == [
        {
            "fd": 3,
            "watch_count": 2,
            "watch_samples": [
                {
                    "raw": (
                        "inotify wd:1 ino:abc sdev:01 "
                        "mask:00000800 ignored_mask:0"
                    ),
                    "wd": "1",
                    "ino": "abc",
                    "sdev": "01",
                    "mask": "00000800",
                },
                {
                    "raw": (
                        "inotify wd:2 ino:def sdev:01 "
                        "mask:00000800 ignored_mask:0"
                    ),
                    "wd": "2",
                    "ino": "def",
                    "sdev": "01",
                    "mask": "00000800",
                },
            ],
        },
    ]
    assert snapshot["proc"]["thread_count"] == 2
    assert snapshot["proc"]["thread_name_counts"] == {
        "notify-rs": 1,
        "swe": 1,
    }
    assert snapshot["runtime"]["inotify_fd_count"] == 1
    assert snapshot["runtime"]["watchfiles_stack_event_count"] == 2
    assert snapshot["runtime"]["watchfiles_stack_summary"] == {
        "event_count": 2,
        "function_counts": {"awatch": 1, "watch": 1},
        "owner_counts": {"fastmcp": 1, "reme": 1},
        "path_samples": ["/workspace/memory", "/tmp/mcp.json"],
        "owner_samples": {
            "fastmcp": ["/site-packages/fastmcp/client.py:42::start"],
            "reme": [
                '  File "/site-packages/reme/core/'
                'file_watcher/base_file_watcher.py", '
                "line 184, in _watch_loop\n",
            ],
        },
    }


def test_summarize_watchfiles_stack_events_handles_missing_stack() -> None:
    probe = _load_probe_module()

    summary = probe.summarize_watchfiles_stack_events(
        [
            {"function": "awatch", "paths": ["/workspace"]},
            {"function": "awatch", "paths": ["/workspace"]},
        ],
    )

    assert summary == {
        "event_count": 2,
        "function_counts": {"awatch": 2},
        "owner_counts": {"unknown": 2},
        "path_samples": ["/workspace"],
        "owner_samples": {},
    }


def test_collect_proc_snapshot_bounds_watch_samples(tmp_path) -> None:
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
    (fdinfo_dir / "3").write_text(
        "\n".join(
            f"inotify wd:{index} ino:{index:x} sdev:01 mask:00000800"
            for index in range(10)
        ),
        encoding="utf-8",
    )

    snapshot = probe.collect_proc_snapshot(pid=42, proc_root=proc_root)

    assert snapshot["inotify_watch_count"] == 10
    assert snapshot["inotify_fds"][0]["watch_count"] == 10
    assert [
        item["wd"] for item in snapshot["inotify_fds"][0]["watch_samples"]
    ] == [
        "0",
        "1",
        "2",
        "3",
        "4",
    ]


def test_summarize_watchfiles_stack_events_bounds_path_samples() -> None:
    probe = _load_probe_module()

    summary = probe.summarize_watchfiles_stack_events(
        [
            {
                "function": "awatch",
                "paths": [f"/workspace/{index}"],
                "stack": [],
            }
            for index in range(10)
        ],
    )

    assert summary["path_samples"] == [
        "/workspace/0",
        "/workspace/1",
        "/workspace/2",
        "/workspace/3",
        "/workspace/4",
    ]


def test_collect_runtime_snapshot_ignores_malformed_stack_events(
    monkeypatch,
) -> None:
    probe = _load_probe_module()

    def fake_urlopen(request, timeout):  # pylint: disable=unused-argument
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "watchfiles_stack_events": [
                            {"function": "awatch", "stack": []},
                            "malformed",
                            None,
                        ],
                    },
                ).encode("utf-8")

        return _Response()

    monkeypatch.setattr(probe.request, "urlopen", fake_urlopen)

    payload = probe.collect_runtime_snapshot(
        runtime_url="http://127.0.0.1:8080/api/runtime/inotify-diagnostic",
        token=None,
        timeout_seconds=1.0,
    )

    assert payload["watchfiles_stack_event_count"] == 1
    assert payload["watchfiles_stack_summary"]["event_count"] == 1


def test_summarize_matrix_reports_consecutive_deltas() -> None:
    probe = _load_probe_module()

    summary = probe.summarize_matrix(
        [
            {
                "label": "empty",
                "proc": {
                    "inotify_fd_count": 1,
                    "inotify_watch_count": 2,
                    "thread_name_counts": {
                        "notify-rs": 1,
                        "notify-rs broken": "bad",
                        "swe": 3,
                    },
                },
            },
            {
                "label": "workspaces",
                "proc": {
                    "inotify_fd_count": 4,
                    "inotify_watch_count": 8,
                    "thread_name_counts": {
                        "notify-rs": 2,
                        "notify-rs inoti": 2,
                        "swe": 5,
                    },
                },
            },
        ],
    )

    assert summary == {
        "steps": [
            {
                "label": "empty",
                "totals": {
                    "inotify_fd_count": 1,
                    "inotify_watch_count": 2,
                    "notify_thread_count": 1,
                },
                "has_previous_snapshot": False,
                "consecutive_delta": None,
            },
            {
                "label": "workspaces",
                "totals": {
                    "inotify_fd_count": 4,
                    "inotify_watch_count": 8,
                    "notify_thread_count": 4,
                },
                "has_previous_snapshot": True,
                "consecutive_delta": {
                    "inotify_fd_count": 3,
                    "inotify_watch_count": 6,
                    "notify_thread_count": 3,
                },
            },
        ],
    }


def test_main_prompt_between_labels_waits_before_each_snapshot(
    monkeypatch,
    capsys,
) -> None:
    probe = _load_probe_module()
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return ""

    def fake_collect_snapshot(**kwargs):
        return {
            "label": kwargs["label"],
            "pid": kwargs["pid"],
            "proc": {
                "inotify_fd_count": 0,
                "inotify_watch_count": 0,
                "thread_name_counts": {},
            },
        }

    monkeypatch.setattr(probe, "_input_from_stderr", fake_input)
    monkeypatch.setattr(probe, "collect_snapshot", fake_collect_snapshot)
    monkeypatch.setattr(
        probe.sys,
        "argv",
        [
            "inotify_matrix_probe.py",
            "--pid",
            "42",
            "--label",
            "empty",
            "--label",
            "workspaces",
            "--prompt-between-labels",
        ],
    )

    assert probe.main() == 0

    output = json.loads(capsys.readouterr().out)
    assert [item["label"] for item in output["snapshots"]] == [
        "empty",
        "workspaces",
    ]
    assert prompts == [
        (
            "Prepare matrix step for label 'empty', then press Enter "
            "to collect snapshot..."
        ),
        (
            "Prepare matrix step for label 'workspaces', then press Enter "
            "to collect snapshot..."
        ),
    ]


def test_input_from_stderr_keeps_prompt_out_of_stdout(
    monkeypatch,
    capsys,
) -> None:
    probe = _load_probe_module()
    monkeypatch.setattr(builtins, "input", lambda: "")

    assert probe._input_from_stderr("continue?") == ""

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "continue?"


def test_load_snapshots_from_files_merges_probe_outputs(tmp_path) -> None:
    probe = _load_probe_module()
    first = tmp_path / "empty.json"
    second = tmp_path / "workspaces.json"
    first.write_text(
        json.dumps(
            {
                "snapshots": [
                    {
                        "label": "empty",
                        "proc": {"inotify_fd_count": 1},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            {
                "label": "workspaces",
                "proc": {"inotify_fd_count": 4},
            },
        ),
        encoding="utf-8",
    )

    snapshots = probe.load_snapshots_from_files([first, second])

    assert [snapshot["label"] for snapshot in snapshots] == [
        "empty",
        "workspaces",
    ]


def test_load_snapshots_from_files_rejects_malformed_snapshot_item(
    tmp_path,
) -> None:
    probe = _load_probe_module()
    capture = tmp_path / "bad.json"
    capture.write_text(
        json.dumps({"snapshots": [{"label": "empty", "proc": {}}, None]}),
        encoding="utf-8",
    )

    try:
        probe.load_snapshots_from_files([capture])
    except ValueError as exc:
        assert f"{capture} snapshots[1] is not an object" in str(exc)
    else:
        raise AssertionError("expected malformed snapshot item to fail")


def test_main_from_json_recomputes_summary(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    probe = _load_probe_module()
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "snapshots": [
                    {
                        "label": "empty",
                        "proc": {
                            "inotify_fd_count": 1,
                            "inotify_watch_count": 2,
                            "thread_name_counts": {"notify-rs": 1},
                        },
                    },
                    {
                        "label": "workspaces",
                        "proc": {
                            "inotify_fd_count": 3,
                            "inotify_watch_count": 6,
                            "thread_name_counts": {"notify-rs inoti": 3},
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        probe.sys,
        "argv",
        [
            "inotify_matrix_probe.py",
            "--from-json",
            str(capture),
        ],
    )

    assert probe.main() == 0

    output = json.loads(capsys.readouterr().out)
    assert [snapshot["label"] for snapshot in output["snapshots"]] == [
        "empty",
        "workspaces",
    ]
    assert output["summary"]["steps"][1]["consecutive_delta"] == {
        "inotify_fd_count": 2,
        "inotify_watch_count": 4,
        "notify_thread_count": 2,
    }


def test_main_from_json_reports_file_errors(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    probe = _load_probe_module()
    capture = tmp_path / "bad.json"
    capture.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        probe.sys,
        "argv",
        [
            "inotify_matrix_probe.py",
            "--from-json",
            str(capture),
        ],
    )

    assert probe.main() == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"inotify_matrix_probe: {capture}:" in captured.err


def test_main_rejects_from_json_with_label(monkeypatch, capsys) -> None:
    probe = _load_probe_module()
    monkeypatch.setattr(
        probe.sys,
        "argv",
        [
            "inotify_matrix_probe.py",
            "--from-json",
            "capture.json",
            "--label",
            "empty",
        ],
    )

    try:
        probe.main()
    except SystemExit as exc:
        assert exc.code == 2
        assert (
            "--from-json cannot be combined with --label"
            in capsys.readouterr().err
        )
    else:
        raise AssertionError("expected argparse to reject mixed modes")
