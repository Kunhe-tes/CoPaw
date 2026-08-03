# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from swe.agents.utils.tool_output_compaction import compact_text_output


def test_returns_original_text_without_artifact_when_within_budget(
    tmp_path: Path,
) -> None:
    text = "short output\n"

    result = compact_text_output(
        text,
        max_bytes=len(text.encode("utf-8")),
        artifact_dir=tmp_path,
    )

    assert result.text == text
    assert result.artifact_path is None
    assert result.original_bytes == len(text.encode("utf-8"))
    assert result.retained_bytes == len(text.encode("utf-8"))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "text",
    [
        "first line\nsecond line\nthird line\nfourth line\n",
        "第一行🍀\n第二行é\n第三行漢字\n第四行🦊\n",
    ],
)
def test_compacts_to_exact_utf8_budget_with_line_aware_excerpt(
    text: str,
    tmp_path: Path,
) -> None:
    max_bytes = 512

    result = compact_text_output(
        text * 20,
        max_bytes=max_bytes,
        artifact_dir=tmp_path,
    )

    assert len(result.text.encode("utf-8")) == max_bytes
    assert result.retained_bytes == max_bytes
    assert result.original_bytes == len((text * 20).encode("utf-8"))
    assert result.text.count("<<<TRUNCATED>>>") == 1
    assert "read_file" in result.text
    assert "first line" in result.text or "第一行" in result.text
    assert "fourth line" in result.text or "第四行" in result.text
    assert result.artifact_path is not None
    assert result.artifact_path.read_text(encoding="utf-8") == text * 20


def test_marks_and_recovers_a_single_line_that_exceeds_budget(
    tmp_path: Path,
) -> None:
    text = "🍀" * 500

    result = compact_text_output(text, max_bytes=512, artifact_dir=tmp_path)

    assert len(result.text.encode("utf-8")) == 512
    assert result.text.count("<<<TRUNCATED>>>") == 1
    assert "read_file" in result.text
    assert result.artifact_path is not None
    assert result.artifact_path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "text",
    [
        "normal line\n" * 200,
        "🍀" * 500,
    ],
)
def test_uses_recoverable_compact_notice_at_minimum_budget(
    text: str,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    artifact_dir = workspace_dir / "tool_result"

    result = compact_text_output(
        text,
        max_bytes=100,
        artifact_dir=artifact_dir,
        workspace_dir=workspace_dir,
    )

    assert len(result.text.encode("utf-8")) == 100
    assert result.text.count("<<<TRUNCATED>>>") == 1
    assert "read_file tool_result/" in result.text
    assert result.artifact_path is not None
    assert result.artifact_path.name in result.text
    reference = result.text.rsplit("read_file ", maxsplit=1)[1].strip()
    assert workspace_dir / reference == result.artifact_path
    assert result.artifact_path.read_text(encoding="utf-8") == text


def test_escapes_source_marker_in_displayed_excerpt(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    artifact_dir = workspace_dir / "tool_result"
    text = ("before\n<<<TRUNCATED>>>\nafter\n") * 100

    result = compact_text_output(
        text,
        max_bytes=512,
        artifact_dir=artifact_dir,
        workspace_dir=workspace_dir,
    )

    assert result.text.count("<<<TRUNCATED>>>") == 1
    assert "<<<TRUNCATED>>?" in result.text
    assert result.artifact_path is not None
    assert result.artifact_path.read_text(encoding="utf-8") == text


def test_replaces_lone_surrogates_for_compaction_and_artifact(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    artifact_dir = workspace_dir / "tool_result"
    text = ("before\ud800after\n") * 200

    result = compact_text_output(
        text,
        max_bytes=512,
        artifact_dir=artifact_dir,
        workspace_dir=workspace_dir,
    )

    assert result.original_bytes == len(text.encode("utf-8", errors="replace"))
    assert len(result.text.encode("utf-8", errors="replace")) == 512
    assert result.artifact_path is not None
    assert result.artifact_path.read_bytes() == text.encode(
        "utf-8",
        errors="replace",
    )


def test_returns_original_text_when_artifact_write_cannot_be_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "line\n" * 200

    def fail_replace(self: Path, target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail_replace)

    result = compact_text_output(text, max_bytes=512, artifact_dir=tmp_path)

    assert result.text == text
    assert result.artifact_path is None
    assert result.original_bytes == len(text.encode("utf-8"))
    assert result.retained_bytes == len(text.encode("utf-8"))
    assert list(tmp_path.iterdir()) == []
