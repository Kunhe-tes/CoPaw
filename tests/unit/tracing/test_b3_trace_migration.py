"""Source-contract tests for the B3 trace identity migration.

These tests validate portable SQL structure; they do not replace a live
database migration smoke test.
"""

import re
from pathlib import Path

import pytest


MIGRATION_SQL = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "sql"
    / "tracing_b3_trace_id_migration.sql"
).read_text(encoding="utf-8")


def test_b3_trace_migration_avoids_alter_if_not_exists() -> None:
    """MySQL ALTER clauses must not use unsupported IF NOT EXISTS syntax."""
    unsupported = re.search(
        r"\bADD\s+(?:COLUMN|INDEX)\s+IF\s+NOT\s+EXISTS\b",
        MIGRATION_SQL,
        re.IGNORECASE,
    )

    assert unsupported is None


@pytest.mark.parametrize(
    ("catalog", "object_field", "object_name"),
    [
        ("COLUMNS", "COLUMN_NAME", "b3_trace_id"),
        ("STATISTICS", "INDEX_NAME", "idx_source_b3_trace"),
    ],
)
def test_b3_trace_migration_uses_schema_scoped_catalog_guard(
    catalog: str,
    object_field: str,
    object_name: str,
) -> None:
    """Each DDL operation is guarded by its exact database object identity."""
    guard_match = re.search(
        rf"FROM\s+INFORMATION_SCHEMA\.{catalog}\s+WHERE(?P<clauses>.*?);",
        MIGRATION_SQL,
        re.IGNORECASE | re.DOTALL,
    )

    assert guard_match is not None
    clauses = guard_match.group("clauses")
    assert re.search(r"TABLE_SCHEMA\s*=\s*DATABASE\(\)", clauses, re.IGNORECASE)
    assert re.search(
        r"TABLE_NAME\s*=\s*'swe_tracing_traces'",
        clauses,
        re.IGNORECASE,
    )
    assert re.search(
        rf"{object_field}\s*=\s*'{object_name}'",
        clauses,
        re.IGNORECASE,
    )


def test_b3_trace_migration_runs_two_conditional_prepared_statements() -> None:
    """Column and index DDL use conditional SQL without stored procedures."""
    assert len(
        re.findall(r"SET\s+@\w+_sql\s*=\s*IF\s*\(", MIGRATION_SQL, re.IGNORECASE),
    ) == 2
    assert len(
        re.findall(
            r"^\s*PREPARE\s+\w+\s+FROM\s+@\w+_sql\s*;",
            MIGRATION_SQL,
            re.IGNORECASE | re.MULTILINE,
        ),
    ) == 2
    assert len(
        re.findall(
            r"^\s*EXECUTE\s+\w+\s*;",
            MIGRATION_SQL,
            re.IGNORECASE | re.MULTILINE,
        ),
    ) == 2
    assert len(
        re.findall(
            r"^\s*DEALLOCATE\s+PREPARE\s+\w+\s*;",
            MIGRATION_SQL,
            re.IGNORECASE | re.MULTILINE,
        ),
    ) == 2
    assert "DELIMITER" not in MIGRATION_SQL.upper()


def test_b3_trace_migration_defines_exact_composite_index() -> None:
    """The lookup index keeps source_id first and remains non-unique."""
    assert re.search(
        r"ADD\s+INDEX\s+`idx_source_b3_trace`\s*"
        r"\(\s*`source_id`\s*,\s*`b3_trace_id`\s*\)",
        MIGRATION_SQL,
        re.IGNORECASE,
    )
    assert not re.search(
        r"ADD\s+UNIQUE(?:\s+INDEX)?\s+`idx_source_b3_trace`",
        MIGRATION_SQL,
        re.IGNORECASE,
    )


def test_b3_trace_migration_does_not_backfill_history() -> None:
    """Historical trace identities cannot be classified reliably."""
    assert not re.search(
        r"^\s*UPDATE\b",
        MIGRATION_SQL,
        re.IGNORECASE | re.MULTILINE,
    )
    assert "cannot be classified reliably" in MIGRATION_SQL
