# -*- coding: utf-8 -*-
"""Optional value-free observation at database execution boundaries."""

from contextlib import contextmanager
from contextvars import ContextVar
import time

_OBSERVER = ContextVar("database_operation_observer", default=None)


@contextmanager
def observe_operations(observer):
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def record_operation(kind, seconds=0.0):
    observer = _OBSERVER.get()
    if observer is not None:
        observer(kind, seconds)


@contextmanager
def timed_operation(kind):
    started = time.perf_counter()
    try:
        yield
    finally:
        record_operation(kind, time.perf_counter() - started)
