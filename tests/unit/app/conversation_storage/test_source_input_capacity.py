# -*- coding: utf-8 -*-
"""Regression tests for admission during selected-input traversal."""

from pathlib import Path

import pytest

from swe.app.conversation_storage.migration import (
    source_inputs,
)
from swe.app.conversation_storage.migration.spool import MigrationCapacityError


@pytest.mark.parametrize("directories", [False, True])
def test_entry_admission_stops_large_selected_directory(
    monkeypatch,
    tmp_path,
    directories,
):
    selected = tmp_path / "sessions"
    selected.mkdir()
    for index in range(100):
        path = selected / str(index)
        if directories:
            path.mkdir()
        else:
            path.write_bytes(b"x")
    original = source_inputs.os.scandir
    yielded = []

    class ObservedScan:
        def __init__(self, path):
            self.scan = original(path)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.scan.close()

        def __iter__(self):
            for item in self.scan:
                yielded.append(item.name)
                yield item

    monkeypatch.setattr(source_inputs.os, "scandir", ObservedScan)
    with pytest.raises(
        MigrationCapacityError,
        match="entries.*memory allowance",
    ):
        source_inputs.safe_input_entries(tmp_path, ["sessions"], entry_limit=8)
    assert len(yielded) == 7  # root + sessions + six admitted, one rejected


def test_oversized_first_file_stops_before_scanning_rest(
    monkeypatch,
    tmp_path,
):
    selected = tmp_path / "sessions"
    selected.mkdir()
    for index in range(20):
        (selected / str(index)).write_bytes(b"x" * 65)
    original = Path.lstat
    examined_files = []

    def observed(path, *args, **kwargs):
        if path.parent == selected:
            examined_files.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", observed)
    with pytest.raises(MigrationCapacityError, match="bounded reader limit"):
        source_inputs.safe_input_entries(
            tmp_path,
            ["sessions"],
            max_file_bytes=64,
        )
    assert len(examined_files) == 1


def test_total_bytes_admitted_before_whole_tree_returns(tmp_path):
    selected = tmp_path / "dialog"
    selected.mkdir()
    for index in range(10):
        (selected / str(index)).write_bytes(b"x" * 40)
    with pytest.raises(MigrationCapacityError, match="memory allowance"):
        source_inputs.safe_input_entries(
            tmp_path,
            ["dialog"],
            max_total_file_bytes=64,
        )


def test_overlapping_entrances_count_each_entry_once(tmp_path):
    selected = tmp_path / "sessions"
    selected.mkdir()
    body = selected / "one.json"
    body.write_bytes(b"x" * 64)
    assert source_inputs.safe_input_entries(
        tmp_path,
        ["sessions", "sessions/one.json", "sessions"],
        entry_limit=3,
        max_file_bytes=64,
        max_total_file_bytes=64,
    ) == sorted([tmp_path, selected, body])


def test_symlink_and_unselected_parent_boundaries_remain(tmp_path):
    selected = tmp_path / "sessions"
    selected.mkdir()
    outside = tmp_path / "business"
    outside.mkdir()
    (outside / "ignored-link").symlink_to("/missing")
    source_inputs.safe_input_entries(tmp_path, ["sessions"], entry_limit=2)
    (selected / "bad-link").symlink_to("/missing")
    with pytest.raises(ValueError, match="symlink"):
        source_inputs.safe_input_entries(tmp_path, ["sessions"], entry_limit=2)
