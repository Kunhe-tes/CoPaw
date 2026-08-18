# -*- coding: utf-8 -*-
"""测试 Skill ZIP 安全解包边界."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from swe.security.skill_scanner.safe_unpack import safe_unpack_skill_zip


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    """构造内存 ZIP 数据，便于覆盖包体边界。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_safe_unpack_rejects_zip_slip(tmp_path: Path) -> None:
    data = _zip_bytes({"../escape.py": b"print('escape')\n"})

    with pytest.raises(ValueError, match="ZIP 成员路径不安全"):
        safe_unpack_skill_zip(data, tmp_path / "stage")


def test_safe_unpack_rejects_absolute_path(tmp_path: Path) -> None:
    data = _zip_bytes({"/tmp/escape.py": b"print('escape')\n"})

    with pytest.raises(ValueError, match="ZIP 成员路径不安全"):
        safe_unpack_skill_zip(data, tmp_path / "stage")


def test_safe_unpack_rejects_symlink_member(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("demo/link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "/etc/passwd")

    with pytest.raises(ValueError, match="ZIP 符号链接成员不允许"):
        safe_unpack_skill_zip(buffer.getvalue(), tmp_path / "stage")


def test_safe_unpack_rejects_too_many_members(tmp_path: Path) -> None:
    entries = {f"demo/file_{idx}.txt": b"x" for idx in range(4)}
    data = _zip_bytes(entries)

    with pytest.raises(ValueError, match="ZIP 成员数量超过限制"):
        safe_unpack_skill_zip(data, tmp_path / "stage", max_entries=3)


def test_safe_unpack_rejects_oversized_member(tmp_path: Path) -> None:
    data = _zip_bytes({"demo/large.bin": b"abcd"})

    with pytest.raises(ValueError, match="ZIP 单个成员体积超过限制"):
        safe_unpack_skill_zip(data, tmp_path / "stage", max_member_bytes=3)


def test_safe_unpack_extracts_valid_skill(tmp_path: Path) -> None:
    data = _zip_bytes(
        {
            "demo/SKILL.md": (b"---\nname: demo\ndescription: demo\n---\n"),
        },
    )

    unpacked = safe_unpack_skill_zip(data, tmp_path / "stage")

    assert (unpacked / "demo" / "SKILL.md").exists()
