# -*- coding: utf-8 -*-
"""提供基于 jobs.json 的 cron 任务仓库实现。"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .base import BaseJobRepository
from ..models import CronJobSpec, JobsFile


@dataclass(frozen=True)
class _FileSignature:
    """描述 jobs.json 当前可观测状态，用于判断快照是否仍然有效。"""

    exists: bool
    mtime_ns: int | None = None
    size: int | None = None


class JsonJobRepository(BaseJobRepository):
    """基于单文件存储 cron job，并维护进程内读取快照。"""

    def __init__(self, path: Path | str):
        """初始化仓库路径和快照状态。"""
        if isinstance(path, str):
            path = Path(path)
        self._path = path.expanduser()
        self._snapshot_signature: _FileSignature | None = None
        self._snapshot: JobsFile | None = None
        self._job_index: dict[str, CronJobSpec] = {}

    @property
    def path(self) -> Path:
        """返回底层 jobs.json 路径。"""
        return self._path

    def _file_signature(self) -> _FileSignature:
        if not self._path.exists():
            return _FileSignature(exists=False)
        stat_result = self._path.stat()
        return _FileSignature(
            exists=True,
            mtime_ns=stat_result.st_mtime_ns,
            size=stat_result.st_size,
        )

    def _load_sync(self) -> tuple[_FileSignature, JobsFile]:
        if not self._path.exists():
            return self._file_signature(), JobsFile(version=1, jobs=[])

        data = json.loads(self._path.read_text(encoding="utf-8"))
        jobs_file = JobsFile.model_validate(data)
        return self._file_signature(), jobs_file

    def _save_sync(self, jobs_file: JobsFile) -> _FileSignature:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        payload = jobs_file.model_dump(mode="json")
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        shutil.move(str(tmp_path), str(self._path))
        return self._file_signature()

    def _set_snapshot(
        self,
        signature: _FileSignature,
        jobs_file: JobsFile,
    ) -> None:
        self._snapshot_signature = signature
        self._snapshot = jobs_file
        self._job_index = {job.id: job for job in jobs_file.jobs}

    async def load(self) -> JobsFile:
        """在线程池中读取、解析和校验 jobs.json。"""
        signature, jobs_file = await asyncio.to_thread(self._load_sync)
        self._set_snapshot(signature, jobs_file)
        return jobs_file

    async def save(self, jobs_file: JobsFile) -> None:
        """在线程池中序列化、写入临时文件并替换 jobs.json。"""
        signature = await asyncio.to_thread(self._save_sync, jobs_file)
        self._set_snapshot(signature, jobs_file)

    async def get_job(self, job_id: str) -> Optional[CronJobSpec]:
        """优先复用未失效快照中的 job 索引。"""
        signature = await asyncio.to_thread(self._file_signature)
        if (
            self._snapshot is not None
            and self._snapshot_signature == signature
        ):
            return self._job_index.get(job_id)

        await self.load()
        return self._job_index.get(job_id)
