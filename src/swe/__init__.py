# -*- coding: utf-8 -*-
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .utils.my_logging import setup_logger

# Fallback before we can safely read canonical constant definitions.
LOG_LEVEL_ENV = "SWE_LOG_LEVEL"

_bootstrap_err: Exception | None = None
_dotenv_err: Exception | None = None
try:
    _project_root = Path(__file__).resolve().parent.parent.parent
    _base_env_path = _project_root / ".env"
    try:
        if _base_env_path.exists():
            load_dotenv(_base_env_path, override=False)
    except Exception as exc:
        _dotenv_err = exc

    from .envs.store import load_envs_into_environ

    load_envs_into_environ()

    from .env_defaults import load_env_defaults

    load_env_defaults()
except Exception as exc:
    _bootstrap_err = exc

_t0 = time.perf_counter()
setup_logger(os.environ.get(LOG_LEVEL_ENV, "info"))
if _bootstrap_err is not None:
    logging.getLogger(__name__).warning(
        "swe: failed to load persisted envs on init: %s",
        _bootstrap_err,
    )
if _dotenv_err is not None:
    logging.getLogger(__name__).debug(
        "swe: skipped base .env during bootstrap: %s",
        _dotenv_err,
    )
logging.getLogger(__name__).debug(
    "%.3fs package init",
    time.perf_counter() - _t0,
)
