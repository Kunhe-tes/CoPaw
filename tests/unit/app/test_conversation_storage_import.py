# -*- coding: utf-8 -*-
"""Check startup imports in a fresh interpreter, without cached modules."""

import os
from pathlib import Path
import subprocess
import sys


def test_tenant_workspace_import_does_not_load_repository():
    root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        (str(root / "src"), str(root / "tests" / "fakes")),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from swe.app.middleware.tenant_workspace "
            "import TenantWorkspaceContext; "
            "assert 'swe.app.conversation_storage.chat_repository' "
            "not in sys.modules; "
            "from swe.app.conversation_storage import MySQLChatRepository; "
            "from swe.app.conversation_storage.chat_repository "
            "import MySQLChatRepository as implementation; "
            "assert MySQLChatRepository is implementation",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
