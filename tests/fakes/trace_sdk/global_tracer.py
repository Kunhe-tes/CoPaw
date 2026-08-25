# -*- coding: utf-8 -*-
"""Documented shutdown import used by the FastAPI lifespan test."""

from . import _records


def shutdown_global_tracer() -> None:
    _records.shutdown_calls += 1
