# -*- coding: utf-8 -*-
"""CLI-only counters; never record SQL, parameters, or conversation bodies."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import threading

import psutil

from swe.database.observation import observe_operations

_CURRENT = ContextVar("migration_progress", default=None)


def current_progress():
    return _CURRENT.get()


class MigrationProgress:
    def __init__(self, operation, migration_id, *, stream=None, interval=5):
        self.stream = stream if stream is not None else sys.stderr
        self.interval = interval
        self.started = time.monotonic()
        self._stage_started = self.started
        self._stage_seconds = {}
        self.data = {
            "operation": operation,
            "migration_id": migration_id,
            "stage": "starting",
            "position": None,
            "failure_position": None,
            "completed": 0,
            "counter_unit": "tasks",
            "task_total": None,
            "inventory_completed_workspaces": 0,
            "inventoried_sessions": 0,
            "inventoried_chats": 0,
            "inventoried_source_bytes": 0,
            "inventory_blocker_count": 0,
            "sql_wait_seconds": 0.0,
            "sql_seconds": 0.0,
            "db_calls": 0,
            "db_seconds": 0.0,
            "db_statement_attempts": 0,
            "db_statement_seconds": 0.0,
            "db_executemany_calls": 0,
            "db_executemany_seconds": 0.0,
            "db_transaction_begins": 0,
            "db_transaction_commits": 0,
            "db_transaction_rollbacks": 0,
            "bundle_opens": 0,
            "binding_serializations": 0,
            "binding_serialized_bytes": 0,
            "binding_serialization_seconds": 0.0,
            "manifest_write_attempts": 0,
            "manifest_writes": 0,
            "manifest_written_bytes": 0,
            "manifest_write_seconds": 0.0,
            "bundle_index_parses": 0,
            "sql_queue_depth": 0,
            "sql_queue_peak": 0,
            "io_active": 0,
            "io_peak": 0,
            "io_seconds": 0.0,
            "io_calls": 0,
            "rss_peak_bytes": 0,
            "temp_peak_bytes": 0,
        }
        self._disk_lock = threading.Lock()
        self._disk_used = 0
        self.open_io = 0
        self.uncertain_io = False

    def disk_change(self, size):
        with self._disk_lock:
            self._disk_used += size
            self.data["temp_peak_bytes"] = max(
                self.data["temp_peak_bytes"],
                self._disk_used,
            )

    def stage(self, name):
        now = time.monotonic()
        previous = self.data["stage"]
        self._stage_seconds[previous] = (
            self._stage_seconds.get(previous, 0.0) + now - self._stage_started
        )
        self._stage_started = now
        self.data.update(stage=name, position=None, completed=0)

    def record_operation(self, kind, seconds):
        counters = {
            "db_statement": "db_statement_attempts",
            "db_executemany": "db_executemany_calls",
            "db_transaction_begin": "db_transaction_begins",
            "db_transaction_commit": "db_transaction_commits",
            "db_transaction_rollback": "db_transaction_rollbacks",
            "bundle_open": "bundle_opens",
            "bundle_index_parse": "bundle_index_parses",
        }
        with self._disk_lock:
            self.data[counters[kind]] += 1
            if kind in ("db_statement", "db_executemany"):
                self.data[kind + "_seconds"] += seconds

    def record_persistence(self, kind, size, seconds, *, succeeded=True):
        """Count completed UTF-8 output and attempted wall time, never values."""
        with self._disk_lock:
            if kind == "binding":
                self.data["binding_serializations"] += 1
                self.data["binding_serialized_bytes"] += size
                self.data["binding_serialization_seconds"] += seconds
            else:
                self.data["manifest_write_attempts"] += 1
                self.data["manifest_write_seconds"] += seconds
                if succeeded:
                    self.data["manifest_writes"] += 1
                    self.data["manifest_written_bytes"] += size

    def snapshot(self):
        now = time.monotonic()
        stages = dict(self._stage_seconds)
        stage = self.data["stage"]
        stages[stage] = stages.get(stage, 0.0) + now - self._stage_started
        try:
            self.data["rss_peak_bytes"] = max(
                self.data["rss_peak_bytes"],
                psutil.Process().memory_info().rss,
            )
        except (OSError, psutil.Error):
            pass
        return {
            **self.data,
            "elapsed_seconds": round(now - self.started, 3),
            "stage_wall_seconds": {
                name: round(seconds, 3) for name, seconds in stages.items()
            },
            "io_drained": (
                "unknown" if self.open_io or self.uncertain_io else True
            ),
        }

    def emit(self):
        try:
            self.stream.write(
                json.dumps(self.snapshot(), sort_keys=True) + "\n",
            )
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def failed_at(self, position):
        if self.data["failure_position"] is None and position is not None:
            self.data["failure_position"] = position
            self.data["position"] = position

    async def _report(self):
        while True:
            await asyncio.sleep(self.interval)
            self.emit()

    @contextmanager
    def activate(self):
        token = _CURRENT.set(self)
        try:
            with observe_operations(self.record_operation):
                yield self
        finally:
            _CURRENT.reset(token)

    async def run(self, operation):
        reporter = asyncio.create_task(self._report())
        try:
            return await operation
        finally:
            reporter.cancel()
            await asyncio.gather(reporter, return_exceptions=True)
            self.emit()

    def save_failure(self, manifest_path, error):
        path = Path(str(manifest_path) + ".failure.json")
        report = {
            "version": 1,
            "passed": False,
            "error_type": type(error).__name__,
            **self.snapshot(),
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=path.parent,
                delete=False,
                encoding="utf-8",
            ) as output:
                temporary = Path(output.name)
                os.chmod(temporary, 0o600)
                json.dump(report, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
