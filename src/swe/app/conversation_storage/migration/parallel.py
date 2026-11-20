# -*- coding: utf-8 -*-
"""Bounded migration work with SQL commands executed by the calling task."""

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import Context, ContextVar
from dataclasses import dataclass
from functools import partial
import time

from swe.database.observation import observe_operations

from .progress import current_progress

HEALTH_CHECK_INTERVAL = 15.0
SQL_BATCH_GRACE_SECONDS = 0.003
SQL_BATCH_LIMIT = 32
_WORK_POSITION = ContextVar("migration_work_position", default=None)


async def _drain(task, *, propagate_cancel=False):
    """Observe real completion despite repeated cancellation of the caller."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            continue
        except Exception:
            break
    result = task.result()
    if cancelled and propagate_cancel:
        raise asyncio.CancelledError
    return result


class MigrationStopped(RuntimeError):
    """The coordinator has stopped accepting commands."""


class MigrationIO:
    """Bound submitted threads as well as active threads; never abandon IO."""

    def __init__(self, workers=4):
        if not 1 <= workers <= 32:
            raise ValueError("IO workers must be between 1 and 32")
        self._progress = current_progress()
        if self._progress:
            self._progress.open_io += 1
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="migration-io",
        )
        self._slots = asyncio.Semaphore(workers)
        self._closed = False
        self._pending = set()

    def _observed_call(self, function):
        if self._progress is None:
            return function()
        with observe_operations(self._progress.record_operation):
            return function()

    async def call(self, function, *args, **kwargs):
        async with self._slots:
            if self._closed:
                raise MigrationStopped("migration IO is closed")
            # run_in_executor deliberately does not copy the SQL task context.
            future = asyncio.get_running_loop().run_in_executor(
                self._executor,
                Context().run,
                partial(
                    self._observed_call,
                    partial(function, *args, **kwargs),
                ),
            )
            self._pending.add(future)
            started = time.monotonic()
            if self._progress:
                data = self._progress.data
                data["io_active"] += 1
                data["io_calls"] += 1
                data["io_peak"] = max(data["io_peak"], data["io_active"])
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                try:
                    await _drain(future)
                except (Exception, asyncio.CancelledError):
                    pass
                raise
            finally:
                self._pending.discard(future)
                if self._progress:
                    self._progress.data["io_active"] -= 1
                    self._progress.data["io_seconds"] += (
                        time.monotonic() - started
                    )

    async def close(self):
        if self._closed:
            return
        self._closed = True
        cleanup = asyncio.ensure_future(
            asyncio.gather(*tuple(self._pending), return_exceptions=True),
        )
        try:
            await _drain(cleanup, propagate_cancel=True)
        finally:
            self._executor.shutdown(wait=True)
            if self._progress:
                self._progress.open_io -= 1
                self._progress.uncertain_io |= any(
                    not item.done() for item in self._pending
                )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        await self.close()


class MigrationResources:
    """One job's shared parser, IO and decoded-memory admission limits."""

    def __init__(
        self,
        *,
        workers=4,
        io_workers=4,
        memory_bytes=512 * 1024 * 1024,
        io=None,
    ):
        from .spool import ByteBudget

        if not 1 <= workers <= 32:
            raise ValueError("workers must be between 1 and 32")
        self.workers = workers
        self.memory = ByteBudget(memory_bytes)
        self.allowance = memory_bytes // workers
        if not self.allowance:
            raise ValueError("memory budget is smaller than worker count")
        self._slots = asyncio.Semaphore(workers)
        self._owns_io = io is None
        self.io = MigrationIO(io_workers) if io is None else io

    @asynccontextmanager
    async def reserve(self):
        async with self._slots:
            async with self.memory.reserve(self.allowance):
                yield self.allowance

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        if self._owns_io:
            await self.io.close()


@dataclass
class _Command:
    name: str
    arguments: tuple
    result: asyncio.Future
    queued_at: float
    position: object


class MigrationCoordinator:
    """Serve registered domain commands in the original SQL-owner task.

    Workers only receive ``request``. Handlers are registered by trusted migration
    code, never supplied as callbacks or SQL text by a worker. Each handler owns
    its complete transaction and must not wait for work done by a worker.
    """

    def __init__(
        self,
        handlers,
        *,
        workers=4,
        health_check=None,
        batch_handlers=None,
        batch_limit=SQL_BATCH_LIMIT,
    ):
        if not 1 <= workers <= 32:
            raise ValueError("workers must be between 1 and 32")
        if not 1 <= batch_limit <= 256:
            raise ValueError("SQL batch limit must be between 1 and 256")
        self._progress = current_progress()
        self._handlers = dict(handlers)
        self._batch_handlers = dict(batch_handlers or {})
        self._batch_limit = batch_limit
        self._workers = workers
        self._commands = deque()
        self._slots = asyncio.Semaphore(2 * workers)
        self._wake = asyncio.Event()
        self._stopped = False
        self._started = False
        self._health_check = health_check
        self._next_health_check = 0.0

    async def request(self, name, *arguments):
        if name not in self._handlers:
            raise ValueError("unknown migration command: " + name)
        async with self._slots:
            if self._stopped:
                raise MigrationStopped("migration coordinator is stopping")
            result = asyncio.get_running_loop().create_future()
            self._commands.append(
                _Command(
                    name,
                    arguments,
                    result,
                    time.monotonic(),
                    _WORK_POSITION.get(),
                ),
            )
            if self._progress:
                data = self._progress.data
                data["sql_queue_depth"] = len(self._commands)
                data["sql_queue_peak"] = max(
                    data["sql_queue_peak"],
                    len(self._commands),
                )
            self._wake.set()
            try:
                return await asyncio.shield(result)
            except asyncio.CancelledError:
                # A submitted transaction may already have committed. Observe
                # its outcome before releasing its queue capacity.
                try:
                    await _drain(result)
                except (Exception, asyncio.CancelledError):
                    pass
                raise

    async def run(self, items, operation):
        if self._started:
            raise RuntimeError("migration coordinator cannot be reused")
        self._started = True
        if self._progress:
            self._progress.data.update(
                completed=0,
                task_total=len(items) if hasattr(items, "__len__") else None,
                counter_unit="tasks",
            )
        iterator = iter(items)
        tasks = [
            asyncio.create_task(self._worker(iterator, operation))
            for _ in range(self._workers)
        ]
        for task in tasks:
            task.add_done_callback(lambda _task: self._wake.set())
        try:
            await self._serve(tasks)
        finally:
            self._stopped = True
            self._reject_pending()
            for task in tasks:
                if not task.done():
                    task.cancel()
            cleanup = asyncio.ensure_future(
                asyncio.gather(*tasks, return_exceptions=True),
            )
            await _drain(cleanup, propagate_cancel=True)

    async def _worker(self, iterator, operation):
        while not self._stopped:
            try:
                item = next(iterator)
            except StopIteration:
                return
            position = item.get("position") if isinstance(item, dict) else None
            token = _WORK_POSITION.set(position)
            if (
                self._progress
                and self._progress.data["failure_position"] is None
            ):
                self._progress.data["position"] = position
            try:
                await operation(item, self.request)
            except Exception:
                if self._progress:
                    self._progress.failed_at(position)
                raise
            finally:
                _WORK_POSITION.reset(token)
            if self._progress:
                self._progress.data["completed"] += 1

    async def _serve(self, tasks):
        while True:
            # Check errors before starting another transaction.
            for task in tasks:
                if task.done():
                    task.result()
            if all(task.done() for task in tasks):
                return
            if self._health_check is not None:
                now = asyncio.get_running_loop().time()
                if now >= self._next_health_check:
                    # Await directly: SQL health probes belong to this task too.
                    await self._health_check()
                    self._next_health_check = (
                        asyncio.get_running_loop().time()
                        + HEALTH_CHECK_INTERVAL
                    )
                    # A worker may fail while the health probe awaits SQL.
                    # Observe it before admitting another domain transaction.
                    continue
            if self._commands:
                first = self._commands.popleft()
                batch_handler = self._batch_handlers.get(first.name)
                if batch_handler is not None:
                    commands = [first]
                    if self._commands:
                        await asyncio.sleep(SQL_BATCH_GRACE_SECONDS)
                    while (
                        len(commands) < self._batch_limit
                        and self._commands
                        and self._commands[0].name == first.name
                    ):
                        commands.append(self._commands.popleft())
                    for task in tasks:
                        if not task.done():
                            continue
                        try:
                            task.result()
                        except BaseException as error:
                            for command in commands:
                                if not command.result.done():
                                    command.result.set_exception(error)
                            raise
                    await self._run_batch(batch_handler, commands)
                    continue
                await self._run_single(first)
                continue
            self._wake.clear()
            if self._health_check is None:
                await self._wake.wait()
            else:
                remaining = max(
                    0.0,
                    self._next_health_check
                    - asyncio.get_running_loop().time(),
                )
                try:
                    await asyncio.wait_for(self._wake.wait(), remaining)
                except asyncio.TimeoutError:
                    pass

    async def _run_single(self, command):
        started = time.monotonic()
        if self._progress:
            self._progress.data["sql_queue_depth"] = len(self._commands)
            self._progress.data["sql_wait_seconds"] += (
                started - command.queued_at
            )
        try:
            value = await self._handlers[command.name](*command.arguments)
        except BaseException as error:
            if self._progress:
                self._progress.failed_at(command.position)
                self._record_sql(
                    command,
                    started,
                    succeeded=False,
                    batch_size=1,
                )
            command.result.set_exception(error)
            raise
        if self._progress:
            self._record_sql(
                command,
                started,
                succeeded=True,
                batch_size=1,
            )
        command.result.set_result(value)

    async def _run_batch(self, handler, commands):
        started = time.monotonic()
        if self._progress:
            self._progress.data["sql_queue_depth"] = len(self._commands)
            self._progress.data["sql_wait_seconds"] += sum(
                started - command.queued_at for command in commands
            )
        try:
            values = await handler(tuple(commands))
            if len(values) != len(commands):
                raise ValueError("migration SQL batch result count differs")
        except BaseException as error:
            if self._progress:
                self._progress.failed_at(commands[0].position)
                self._record_sql(
                    commands[0],
                    started,
                    succeeded=False,
                    batch_size=len(commands),
                )
            for command in commands:
                command.result.set_exception(error)
            raise
        if self._progress:
            self._record_sql(
                commands[0],
                started,
                succeeded=True,
                batch_size=len(commands),
            )
        for command, value in zip(commands, values):
            command.result.set_result(value)

    def _record_sql(self, command, started, *, succeeded, batch_size):
        elapsed = time.monotonic() - started
        self._progress.data["sql_seconds"] += elapsed
        self._progress.data["sql_batches"] += 1
        self._progress.data["sql_batch_size_peak"] = max(
            self._progress.data["sql_batch_size_peak"],
            batch_size,
        )
        self._progress.data["last_sql_command"] = command.name
        self._progress.data["last_sql_position"] = command.position
        self._progress.data["last_sql_seconds"] = round(elapsed, 6)
        self._progress.data["last_sql_succeeded"] = succeeded

    def _reject_pending(self):
        if self._progress:
            self._progress.data["sql_queue_depth"] = 0
        while self._commands:
            command = self._commands.popleft()
            command.result.set_exception(
                MigrationStopped("migration coordinator is stopping"),
            )
