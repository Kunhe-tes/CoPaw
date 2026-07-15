# -*- coding: utf-8 -*-
"""Cron Scheduler service package."""

import logging

from . import _bootstrap as _bootstrap  # noqa: F401

_bootstrap_err: Exception | None = None
try:
    from .envs import load_envs_into_environ

    load_envs_into_environ()

    from .env_defaults import load_env_defaults

    load_env_defaults()
except Exception as exc:  # pragma: no cover - startup safety net
    _bootstrap_err = exc

if _bootstrap_err is not None:  # pragma: no cover - startup safety net
    logging.getLogger(__name__).warning(
        "scheduler: failed to load persisted envs on init: %s",
        _bootstrap_err,
    )
