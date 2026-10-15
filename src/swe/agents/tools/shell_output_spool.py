# -*- coding: utf-8 -*-
"""Bound enabled Shell output while retaining the exact terminal artifact."""

from __future__ import annotations

import codecs
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
import locale
import os
from pathlib import Path
import tempfile
import threading
from typing import BinaryIO, Callable, Iterator, ParamSpec, TypeVar
from uuid import uuid4

from swe.output_workers import run_output_work

from ..utils.tool_output_compaction import (
    _historical_artifact_display,
    _truncation_notice,
)

_CONFIG: ContextVar[tuple[Path, int] | None] = ContextVar(
    "shell_output_spool_config",
    default=None,
)
_ACTIVE: ContextVar[ShellOutputSpool | None] = ContextVar(
    "shell_output_spool",
    default=None,
)
_COPY_BYTES = 64 * 1024
P = ParamSpec("P")
T = TypeVar("T")
_TIMEOUT_MARKERS = (
    "timeouterror",
    "connecttimeout",
    "read timed out",
    "connection timed out",
)
_FAILURE_MARKERS = (
    "outside the allowed workspace",
    "MemoryError",
    "Cannot allocate memory",
    "Killed",
)


@contextmanager
def bind_shell_output_spool(workspace_dir: Path, max_bytes: int):
    """Enable recoverable bounded Shell output for an agent tool invocation."""
    token = _CONFIG.set((Path(workspace_dir), max_bytes))
    try:
        yield
    finally:
        _CONFIG.reset(token)


def get_active_shell_output_spool() -> ShellOutputSpool | None:
    return _ACTIVE.get()


def create_shell_output_spool(
    decode: Callable[[bytes], str],
    format_response: Callable[[int, str, str], str],
) -> ShellOutputSpool | None:
    config = _CONFIG.get()
    if config is None:
        return None

    workspace, max_bytes = config
    try:
        reference = f"tool_result/{uuid4().hex}.txt"
        _truncation_notice(
            original_bytes=2**64,
            retained_bytes=max_bytes,
            artifact_reference=reference,
            max_bytes=max_bytes,
        )
        return ShellOutputSpool(workspace, max_bytes, decode, format_response)
    except (OSError, ValueError):
        return None


async def run_shell_spool_work(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Keep a spool's files alive until a cancelled worker has finished."""
    work = asyncio.create_task(run_output_work(func, *args, **kwargs))
    return await await_shell_cleanup_task(work)


async def await_shell_cleanup_task(work: asyncio.Task[T]) -> T:
    """Wait through repeated cancellation and consume a task's exception."""
    cancelled = False
    while not work.done():
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not work.cancelled():
            work.exception()
        raise asyncio.CancelledError
    return work.result()


class _StreamBuffer:
    """One stream; file writes are synchronous and run in an output worker."""

    def __init__(self, directory: Path, limit: int):
        self.directory = directory
        self.limit = limit
        self.buffer = bytearray()
        self.file: BinaryIO | None = None
        self.size = 0
        self.failed = False
        self.lock = threading.RLock()

    def append(self, chunk: bytes) -> None:
        with self.lock:
            previous_size = self.size
            self.size += len(chunk)
            if self.failed or (
                self.file is None
                and len(self.buffer) + len(chunk) <= self.limit
            ):
                self.buffer.extend(chunk)
                return
            try:
                if self.directory.is_symlink():
                    raise OSError("Shell spool directory is a symlink")
                if self.file is None:
                    self.directory.mkdir(parents=True, exist_ok=True)
                    self.file = tempfile.TemporaryFile(
                        dir=self.directory,
                        mode="w+b",
                        buffering=0,
                    )
                    written = self.file.write(self.buffer)
                    if written != len(self.buffer):
                        raise OSError("Incomplete initial Shell spool write")
                    self.buffer.clear()
                self.file.seek(0, os.SEEK_END)
                written = self.file.write(chunk)
                if written != len(chunk):
                    raise OSError("Incomplete Shell spool write")
            except OSError:
                if self.file is not None:
                    if not self.buffer:
                        self.file.seek(0)
                        self.buffer = bytearray(self.file.read(previous_size))
                    self.file.close()
                    self.file = None
                self.buffer.extend(chunk)
                self.failed = True

    def read_all(self) -> bytes:
        with self.lock:
            if self.file is None:
                return bytes(self.buffer)
            self.file.seek(0)
            return self.file.read()

    def reader(self) -> BinaryIO:
        if self.file is None:
            return BytesIO(self.buffer)
        self.file.seek(0)
        return self.file

    def close(self) -> None:
        with self.lock:
            if self.file is not None:
                self.file.close()
                self.file = None
            self.buffer.clear()


def _stream_bounds(reader: BinaryIO) -> tuple[int, int]:
    reader.seek(0, os.SEEK_END)
    end = reader.tell()
    start = 0
    while start < end:
        reader.seek(start)
        chunk = reader.read(min(_COPY_BYTES, end - start))
        skipped = len(chunk) - len(chunk.lstrip(b"\n"))
        start += skipped
        if skipped != len(chunk):
            break
    while end > start:
        reader.seek(max(start, end - _COPY_BYTES))
        chunk = reader.read(end - max(start, end - _COPY_BYTES))
        skipped = len(chunk) - len(chunk.rstrip(b"\n"))
        end -= skipped
        if skipped != len(chunk):
            break
    return start, end


def _read_chunks(reader: BinaryIO, bounds: tuple[int, int]) -> Iterator[bytes]:
    start, end = bounds
    reader.seek(start)
    remaining = end - start
    while remaining:
        chunk = reader.read(min(_COPY_BYTES, remaining))
        if not chunk:
            raise OSError("Incomplete Shell spool read")
        remaining -= len(chunk)
        yield chunk


def _decoded_chunks(
    stream: _StreamBuffer,
    bounds: tuple[int, int],
) -> Iterator[str]:
    reader = stream.reader()
    encoding = "utf-8"
    decoder = codecs.getincrementaldecoder(encoding)()
    try:
        for chunk in _read_chunks(reader, bounds):
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        encoding = locale.getpreferredencoding(False) or "utf-8"
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    for chunk in _read_chunks(reader, bounds):
        yield decoder.decode(chunk)
    yield decoder.decode(b"", final=True)


class ShellOutputSpool:
    """Retain each pipe up to its budget, then stream it to a temporary file."""

    def __init__(
        self,
        workspace: Path,
        max_bytes: int,
        decode,
        format_response,
    ):
        self.workspace = workspace.resolve()
        self.directory = self.workspace / "tool_result"
        self.directory.resolve().relative_to(self.workspace)
        self.max_bytes = max_bytes
        self.decode = decode
        self.format_response = format_response
        self.streams = {
            source: _StreamBuffer(self.directory, max_bytes)
            for source in ("stdout", "stderr")
        }
        self.stderr_suffix = ""

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    @property
    def buffered_bytes(self) -> int:
        return sum(len(stream.buffer) for stream in self.streams.values())

    @property
    def total_bytes(self) -> int:
        return sum(stream.size for stream in self.streams.values())

    async def append(self, source: str, chunk: bytes) -> None:
        await run_shell_spool_work(self.streams[source].append, chunk)

    def decode_streams(self, stderr_suffix: str = "") -> tuple[str, str]:
        self.stderr_suffix = stderr_suffix
        output = [
            self.decode(stream.read_all()) if stream.file is None else ""
            for stream in self.streams.values()
        ]
        if stderr_suffix:
            output[1] = (
                f"{output[1]}\n{stderr_suffix}" if output[1] else stderr_suffix
            )
        return output[0], output[1]

    def _full_response(
        self,
        returncode: int,
        diagnostic: str,
    ) -> tuple[str, str]:
        stdout, stderr = [
            self.decode(stream.read_all()) for stream in self.streams.values()
        ]
        if self.stderr_suffix:
            stderr = (
                f"{stderr}\n{self.stderr_suffix}"
                if stderr
                else self.stderr_suffix
            )
        return (
            self.format_response(returncode, stdout, stderr) + diagnostic,
            stderr,
        )

    def _write_stream(
        self,
        target: BinaryIO,
        source: str,
        bounds: tuple[int, int],
    ) -> str:
        found = set()
        previous = ""
        for text in _decoded_chunks(self.streams[source], bounds):
            target.write(text.encode("utf-8", errors="replace"))
            if source == "stderr":
                scan = previous + text
                found.update(
                    marker for marker in _FAILURE_MARKERS if marker in scan
                )
                found.update(
                    marker
                    for marker in _TIMEOUT_MARKERS
                    if marker in scan.lower()
                )
                previous = scan[-128:]
        return "\n".join(found)

    def _write_response(
        self,
        target: BinaryIO,
        returncode: int,
        diagnostic: str,
    ):
        # Readers and append workers have drained before finalization. Keep
        # these immutable bounds local to this response, including empty pipes.
        bounds = {
            source: _stream_bounds(stream.reader())
            for source, stream in self.streams.items()
        }
        nonempty = {
            source: end > start for source, (start, end) in bounds.items()
        }
        if returncode == 0:
            if nonempty["stdout"]:
                self._write_stream(target, "stdout", bounds["stdout"])
            else:
                target.write(b"Command executed successfully (no output).")
        else:
            target.write(
                f"Command failed with exit code {returncode}.".encode(),
            )
            if nonempty["stdout"]:
                target.write(b"\n[stdout]\n")
                self._write_stream(target, "stdout", bounds["stdout"])
        stderr_markers = ""
        if nonempty["stderr"] or self.stderr_suffix:
            target.write(b"\n[stderr]\n")
            stderr_markers = self._write_stream(
                target,
                "stderr",
                bounds["stderr"],
            )
            if self.stderr_suffix:
                if nonempty["stderr"]:
                    target.write(b"\n")
                target.write(self.stderr_suffix.encode("utf-8"))
                stderr_markers += self.stderr_suffix
        target.write(diagnostic.encode("utf-8", errors="replace"))
        return stderr_markers

    def prepare_response(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        diagnostic: str,
    ) -> tuple[str, str]:
        if not any(
            stream.file is not None for stream in self.streams.values()
        ):
            return (
                self.format_response(returncode, stdout, stderr) + diagnostic,
                stderr,
            )
        artifact = self.directory / f"{uuid4().hex}.txt"
        temporary = artifact.with_suffix(".tmp")
        try:
            # Check again because tool commands may have changed the directory.
            self.directory.resolve().relative_to(self.workspace)
            if self.directory.is_symlink():
                raise OSError("Shell spool directory is a symlink")
            with temporary.open("xb") as target:
                stderr_markers = self._write_response(
                    target,
                    returncode,
                    diagnostic,
                )
                target.flush()
                os.fsync(target.fileno())
            temporary.replace(artifact)
            file_stat = artifact.stat()
            if file_stat.st_size <= self.max_bytes:
                text = artifact.read_text(encoding="utf-8")
                artifact.unlink()
                return text, stderr_markers
            text = _historical_artifact_display(
                artifact,
                file_stat,
                self.max_bytes,
                f"tool_result/{artifact.name}",
            )
            return text, stderr_markers
        except (OSError, ValueError):
            for path in (temporary, artifact):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            return self._full_response(returncode, diagnostic)

    async def aclose(self) -> None:
        def close_all() -> None:
            for stream in self.streams.values():
                stream.close()

        await run_shell_spool_work(close_all)
