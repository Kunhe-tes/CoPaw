# -*- coding: utf-8 -*-
"""Skill 外来压缩包安全解包工具."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Callable

_DEFAULT_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
_DEFAULT_MAX_MEMBER_BYTES = 20 * 1024 * 1024
_DEFAULT_MAX_ENTRIES = 2000

MemberNameDecoder = Callable[[zipfile.ZipInfo], str]


def safe_unpack_skill_zip(
    data: bytes,
    target_dir: Path,
    *,
    max_uncompressed_bytes: int = _DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_member_bytes: int = _DEFAULT_MAX_MEMBER_BYTES,
    max_entries: int = _DEFAULT_MAX_ENTRIES,
    decode_member_name: MemberNameDecoder | None = None,
) -> Path:
    """将 Skill ZIP 安全解包到隔离目录."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("上传文件不是有效的 ZIP 压缩包")

    target_dir.mkdir(parents=True, exist_ok=True)
    root_path = target_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > max_entries:
            raise ValueError("ZIP 成员数量超过限制")

        total_size = sum(info.file_size for info in members)
        if total_size > max_uncompressed_bytes:
            raise ValueError("ZIP 解压后体积超过限制")
        if any(info.file_size > max_member_bytes for info in members):
            raise ValueError("ZIP 单个成员体积超过限制")

        for info in members:
            member_name = _normalized_member_name(info, decode_member_name)
            target = (target_dir / member_name).resolve()
            if not target.is_relative_to(root_path):
                raise ValueError(f"ZIP 成员路径不安全: {member_name}")
            if _is_symlink(info):
                raise ValueError(f"ZIP 符号链接成员不允许: {member_name}")

        for info in members:
            member_name = _normalized_member_name(info, decode_member_name)
            target = (target_dir / member_name).resolve()
            _extract_member(archive, info, target)
    return target_dir


def _normalized_member_name(
    info: zipfile.ZipInfo,
    decode_member_name: MemberNameDecoder | None,
) -> str:
    """统一成员名格式，避免不同编码绕过路径边界."""
    raw_name = (
        decode_member_name(info) if decode_member_name else info.filename
    )
    member_name = (raw_name or "").replace("\\", "/").strip()
    if not member_name or member_name.startswith("/"):
        raise ValueError(f"ZIP 成员路径不安全: {member_name}")
    return member_name


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """判断 ZIP 成员是否声明为符号链接。"""
    return info.external_attr >> 16 & 0o120000 == 0o120000


def _extract_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
) -> None:
    """按已校验目标路径复制单个成员，避免 zipfile 自行拼路径."""
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, target.open("wb") as dest:
        shutil.copyfileobj(source, dest, length=1024 * 1024)
