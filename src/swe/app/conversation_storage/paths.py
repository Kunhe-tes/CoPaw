# -*- coding: utf-8 -*-
"""Workspace path validation."""

from pathlib import Path


def existing_root(path):
    root = Path(path).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "conversation storage requires an existing nonsymlink root",
        )
    return root
