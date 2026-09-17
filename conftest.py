# -*- coding: utf-8 -*-
"""为整个仓库测试统一绑定当前 worktree 的源码导入路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SOURCE_DIRS = [
    _ROOT / "src",
    _ROOT / "scheduler" / "src",
    _ROOT / "market" / "src",
    _ROOT / "monitor" / "src",
]

for source_dir in reversed(_SOURCE_DIRS):
    source_dir_str = str(source_dir)
    if source_dir_str in sys.path:
        sys.path.remove(source_dir_str)
    sys.path.insert(0, source_dir_str)

# 测试进程可能已经从安装包或主仓库缓存过同名模块；这里统一清理，
# 确保后续导入命中当前 worktree 下的源码。
_STALE_PREFIXES = ("swe", "scheduler", "market", "monitor")
_stale_modules = [
    name
    for name in sys.modules
    if name in _STALE_PREFIXES
    or any(name.startswith(f"{prefix}.") for prefix in _STALE_PREFIXES)
]
for name in _stale_modules:
    del sys.modules[name]
