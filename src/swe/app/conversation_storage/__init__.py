# -*- coding: utf-8 -*-
"""MySQL conversation metadata and immutable NAS content primitives."""

from .bundle import BundleBlock, BundleStore, new_operation_key
from .identity import SessionIdentity, WorkspaceScope

__all__ = [
    "BundleBlock",
    "BundleStore",
    "SessionIdentity",
    "WorkspaceScope",
    "MySQLChatRepository",
    "new_operation_key",
]


def __getattr__(name: str):
    # Admission middleware must not pull in the repository's runtime imports.
    if name == "MySQLChatRepository":
        from .chat_repository import MySQLChatRepository

        return MySQLChatRepository
    raise AttributeError(name)
