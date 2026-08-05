# -*- coding: utf-8 -*-
"""历史 span skill_id 初始化服务.

为 swe_tracing_spans 中 skill_id 为空的记录按 swe_skills 补齐 skill_id。
- 同一 source_id + skill_name 关联出 swe_skills 候选。
- 仅有一个候选时直接写入，计入 matched。
- 多个候选时按 cn_name 非空、enabled=1、updated_at DESC、id DESC 选一个写入，
  计入 ambiguous + selected_from_ambiguous。
- 完全没有候选时跳过，计入 unmatched / skipped。
- dry_run=True 时执行完整匹配与选择，但不更新数据库。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from ...database import get_db_connection, DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass
class InitResult:
    """历史初始化结果统计."""

    dry_run: bool = False
    scanned: int = 0
    matched: int = 0
    updated: int = 0
    unmatched: int = 0
    skipped: int = 0
    ambiguous: int = 0
    selected_from_ambiguous: int = 0
    errors: list[dict] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为可序列化字典."""
        return {
            "dry_run": self.dry_run,
            "scanned": self.scanned,
            "matched": self.matched,
            "updated": self.updated,
            "unmatched": self.unmatched,
            "skipped": self.skipped,
            "ambiguous": self.ambiguous,
            "selected_from_ambiguous": self.selected_from_ambiguous,
            "errors": self.errors,
            "samples": self.samples,
        }


# 候选选择：cn_name 非空 > enabled=1 > updated_at DESC > id DESC
SKILL_CANDIDATE_SORT = (
    "CASE WHEN cn_name IS NOT NULL AND TRIM(cn_name) <> '' THEN 0 ELSE 1 END ASC, "
    "CASE WHEN enabled = 1 THEN 0 ELSE 1 END ASC, "
    "updated_at DESC, id DESC"
)

PENDING_SPAN_SCAN_SQL_TEMPLATE = """
    SELECT span_id, source_id, skill_name, start_time
    FROM swe_tracing_spans
    WHERE (start_time, span_id) > (%s, %s)
      AND (skill_id IS NULL OR TRIM(skill_id) = '')
      AND skill_name IS NOT NULL
      AND TRIM(skill_name) <> ''
      {source_filter}
    ORDER BY start_time ASC, span_id ASC
    LIMIT %s
"""


class SkillIdInitializer:
    """历史 span skill_id 初始化服务."""

    DEFAULT_BATCH_SIZE = 1000
    MAX_SAMPLE_RECORDS = 20

    def __init__(self, db: Optional[DatabaseConnection] = None) -> None:
        self._db = db or get_db_connection()

    async def initialize(
        self,
        source_id: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
    ) -> InitResult:
        """循环处理全部待初始化 span，直至没有剩余记录。"""
        result = InitResult(dry_run=dry_run)
        batch_size = max(1, min(batch_size, self.DEFAULT_BATCH_SIZE * 5))
        cursor_start_time = datetime(1000, 1, 1)
        cursor_span_id = ""

        source_filter_sql, source_params = self._build_source_filter(source_id)
        scan_sql = PENDING_SPAN_SCAN_SQL_TEMPLATE.format(
            source_filter=source_filter_sql,
        )

        try:
            while True:
                span_rows = await self._db.fetch_all(
                    scan_sql,
                    tuple(
                        [
                            cursor_start_time,
                            cursor_span_id,
                            *source_params,
                            batch_size,
                        ],
                    ),
                )
                if not span_rows:
                    break

                pending_keys = [
                    (row["source_id"], row["skill_name"]) for row in span_rows
                ]
                result.scanned += len(span_rows)
                candidate_map = await self._fetch_candidate_map(
                    pending_keys,
                    source_id,
                )

                updates: list[tuple[str, str]] = []
                for row in span_rows:
                    key = (row["source_id"], row["skill_name"])
                    candidates = candidate_map.get(key, [])
                    if not candidates:
                        result.unmatched += 1
                        result.skipped += 1
                        self._record_sample(result, kind="unmatched", span=row)
                        continue
                    if len(candidates) == 1:
                        chosen = candidates[0]
                        result.matched += 1
                    else:
                        chosen = candidates[0]
                        result.ambiguous += 1
                        result.selected_from_ambiguous += 1
                        self._record_sample(
                            result,
                            kind="ambiguous",
                            span=row,
                            candidates=candidates,
                            chosen=chosen,
                        )
                    updates.append((chosen["skill_id"], row["span_id"]))

                if updates and not dry_run:
                    result.updated += await self._apply_updates(updates)

                last_row = span_rows[-1]
                cursor_start_time = last_row["start_time"]
                cursor_span_id = last_row["span_id"]

                if len(span_rows) < batch_size:
                    break
        except Exception as exc:
            logger.exception("init_skill_id failed: %s", exc)
            result.errors.append({"error": str(exc)})

        return result

    async def _fetch_candidate_map(
        self,
        pending_keys: Iterable[tuple[str, str]],
        source_id: Optional[str],
    ) -> dict[tuple[str, str], list[dict]]:
        """根据 source_id+skill_name 拉取候选."""
        keys = [k for k in pending_keys if k[1]]
        if not keys:
            return {}

        placeholders = ", ".join(["(%s, %s)"] * len(keys))
        params: list[Any] = []
        for src, name in keys:
            params.append(src)
            params.append(name)

        sql = f"""
            SELECT id, source_id, skill_name, skill_id, cn_name, enabled, updated_at
            FROM swe_skills
            WHERE skill_id IS NOT NULL
              AND TRIM(skill_id) <> ''
              AND (source_id, skill_name) IN ({placeholders})
            ORDER BY {SKILL_CANDIDATE_SORT}, source_id, skill_name, skill_id
        """
        rows = await self._db.fetch_all(sql, tuple(params))

        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            grouped.setdefault(
                (row["source_id"], row["skill_name"]),
                [],
            ).append(row)
        return grouped

    async def _apply_updates(self, updates: list[tuple[str, str]]) -> int:
        """执行批量更新，返回成功条数."""
        if not updates:
            return 0
        sql = "UPDATE swe_tracing_spans SET skill_id = %s WHERE span_id = %s"
        try:
            return await self._db.execute_many(sql, updates)
        except Exception as exc:
            logger.exception("batch update skill_id failed: %s", exc)
            return 0

    @staticmethod
    def _build_source_filter(
        source_id: Optional[str],
    ) -> tuple[str, list[Any]]:
        if source_id:
            return " AND source_id = %s", [source_id]
        return "", []

    def _record_sample(
        self,
        result: InitResult,
        kind: str,
        span: dict,
        candidates: Optional[list[dict]] = None,
        chosen: Optional[dict] = None,
    ) -> None:
        if len(result.samples) >= self.MAX_SAMPLE_RECORDS:
            return
        record: dict[str, Any] = {
            "kind": kind,
            "span_id": span.get("id"),
            "source_id": span.get("source_id"),
            "skill_name": span.get("skill_name"),
        }
        if candidates:
            record["candidates"] = [
                {
                    "skill_id": c.get("skill_id"),
                    "cn_name": c.get("cn_name"),
                    "enabled": c.get("enabled"),
                    "updated_at": (
                        c.get("updated_at").isoformat()
                        if c.get("updated_at")
                        else None
                    ),
                }
                for c in candidates
            ]
        if chosen:
            record["chosen_skill_id"] = chosen.get("skill_id")
        result.samples.append(record)
