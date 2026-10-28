# -*- coding: utf-8 -*-
"""验证正常服务入口能打印业务日志，且不改变其他库的日志级别。"""

import os
from pathlib import Path
import subprocess
import sys

import pytest


def _scheduler_env(level):
    scheduler_src = Path(__file__).resolve().parents[3] / "scheduler" / "src"
    pythonpath = os.pathsep.join(
        [str(scheduler_src), os.environ.get("PYTHONPATH", "")],
    )
    return {**os.environ, "PYTHONPATH": pythonpath, "SCHEDULER_LOG_LEVEL": level}


@pytest.mark.parametrize("level", ["info", "invalid-level"])
def test_app_import_enables_info_and_repeated_setup_does_not_duplicate(level):
    code = """
import logging
import uvicorn
uvicorn.Config('unused:app', log_level='info')
root_level = logging.getLogger().level
import scheduler.app._app
from scheduler.logging import configure_logging
configure_logging()
configure_logging()
logging.getLogger('scheduler.app.probe').info('SCHEDULER_INFO_PROBE')
assert logging.getLogger().level == root_level
assert not logging.getLogger('unrelated_library').isEnabledFor(logging.INFO)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=_scheduler_env(level),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("SCHEDULER_INFO_PROBE") == 1


def test_configured_warning_level_keeps_business_info_disabled():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import logging
from scheduler.logging import configure_logging
configure_logging()
logger = logging.getLogger('scheduler.app.probe')
logger.info('INFO_SHOULD_BE_HIDDEN')
logger.warning('SCHEDULER_WARNING_PROBE')
""",
        ],
        env=_scheduler_env("warning"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "INFO_SHOULD_BE_HIDDEN" not in result.stdout
    assert result.stdout.count("SCHEDULER_WARNING_PROBE") == 1
