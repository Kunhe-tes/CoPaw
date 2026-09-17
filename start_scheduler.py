# -*- coding: utf-8 -*-
"""Start the Cron Scheduler service in a local virtual environment."""

import os
import subprocess
import sys

SERVICE_NAME = "scheduler"
VENV_DIR = "venv_scheduler"
HOST = os.environ.get("SCHEDULER_HOST", "127.0.0.1")
PORT = int(os.environ.get("SCHEDULER_PORT", "9100"))
LOG_LEVEL = os.environ.get("SCHEDULER_LOG_LEVEL", "info")


def get_venv_python() -> str:
    if sys.platform == "win32":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def ensure_venv() -> None:
    venv_python = get_venv_python()
    if not os.path.exists(venv_python):
        print(f"[{SERVICE_NAME}] creating virtual environment {VENV_DIR}...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    print(f"[{SERVICE_NAME}] installing dependencies...")
    subprocess.check_call(
        [venv_python, "-m", "pip", "install", "-e", "./scheduler", "--quiet"],
    )


def run_in_venv() -> None:
    repo_root = os.path.dirname(os.path.abspath(__file__))
    scheduler_src = os.path.join(repo_root, "scheduler", "src")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [scheduler_src, env.get("PYTHONPATH", "")],
    )
    subprocess.check_call(
        [
            get_venv_python(),
            "-m",
            "uvicorn",
            "scheduler.app._app:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            LOG_LEVEL,
        ],
        env=env,
    )


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    ensure_venv()
    print(f"[{SERVICE_NAME}] starting on {HOST}:{PORT}")
    run_in_venv()
