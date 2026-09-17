# -*- coding: utf-8 -*-
"""Cron Scheduler service entrypoint."""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

_src_dir = Path(__file__).resolve().parent / "src"
if _src_dir.exists() and str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from scheduler.config.constant import DEFAULT_HOST, DEFAULT_PORT, LOG_LEVEL_ENV


def main() -> None:
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


if __name__ == "__main__":
    main()
