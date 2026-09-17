# -*- coding: utf-8 -*-
"""技能 ZIP 下载打包 helper。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_UNSAFE_ZIP_FILENAME_RE = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')
_SKIPPED_SKILL_FILES = {"skill.json"}


def sanitize_zip_filename(filename: str) -> str:
    """清洗 ZIP 文件名，避免非法字符和异常后缀。"""
    cleaned = _UNSAFE_ZIP_FILENAME_RE.sub("_", str(filename or "").strip())
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "skill"
    if not cleaned.lower().endswith(".zip"):
        cleaned = f"{cleaned}.zip"
    return cleaned


def build_skill_zip(
    skill_dir: Path,
    output_name: str,
    temp_dir: Path,
) -> Path:
    """将技能目录打包为 ZIP，并保留目录内相对路径。"""
    skill_dir = Path(skill_dir)
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    zip_path = temp_dir / sanitize_zip_filename(output_name)
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for file_path in sorted(skill_dir.rglob("*")):
            if (
                file_path.is_file()
                and file_path.name not in _SKIPPED_SKILL_FILES
            ):
                zf.write(file_path, arcname=file_path.relative_to(skill_dir))
    return zip_path
