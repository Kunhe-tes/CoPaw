# -*- coding: utf-8 -*-
"""Scheduler CLI entrypoint."""

import argparse
import os

import uvicorn

from scheduler.config.constant import DEFAULT_HOST, DEFAULT_PORT, LOG_LEVEL_ENV


def cli() -> None:
    parser = argparse.ArgumentParser(description="Cron Scheduler service")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "scheduler.app._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=os.environ.get(LOG_LEVEL_ENV, "info"),
    )
