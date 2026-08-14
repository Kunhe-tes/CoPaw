# -*- coding: utf-8 -*-
"""HTML 预览事件表迁移契约测试。"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "scripts/sql/html_preview_event_dimensions_migration.sql"
)
BASELINE_PATH = REPO_ROOT / "scripts/sql/html_preview_click_events.sql"


def test_event_migration_uses_standard_mysql_alter_syntax():
    """迁移不能使用标准 MySQL 不支持的 ADD ... IF NOT EXISTS。"""
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS" not in sql
    assert "ADD INDEX IF NOT EXISTS" not in sql
    assert "ALGORITHM=INPLACE" in sql
    assert "LOCK=NONE" in sql


def test_event_target_comments_only_describe_modules():
    """子方案由模板字段关联，event_target 只描述具体模块。"""
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    baseline_sql = BASELINE_PATH.read_text(encoding="utf-8")

    assert "子方案或模块" not in migration_sql
    assert "子方案或模块" not in baseline_sql
    assert "模块的稳定标识" in migration_sql
    assert "模块的稳定标识" in baseline_sql


def test_root_event_index_includes_root_result_dimension():
    """同一主模板的不同生成结果应能使用联合索引筛选。"""
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    baseline_sql = BASELINE_PATH.read_text(encoding="utf-8")
    expected_columns = (
        "source_id, root_template_id, root_result_id, event_type, clicked_at"
    )

    assert expected_columns in " ".join(migration_sql.split())
    assert expected_columns in " ".join(baseline_sql.split())
