"""File governance helpers shared by routers and source-level tasks."""

from .archive_maintenance import (
    ARCHIVE_FILES_DIR,
    ARCHIVE_INDEX_FILE,
    PROTECTED_PATHS_FILE,
    WorkspaceArchiveMaintenanceResult,
    archive_old_orphans_for_workspace,
    archive_workspace_files,
    scan_orphan_files,
)

__all__ = [
    "ARCHIVE_FILES_DIR",
    "ARCHIVE_INDEX_FILE",
    "PROTECTED_PATHS_FILE",
    "WorkspaceArchiveMaintenanceResult",
    "archive_old_orphans_for_workspace",
    "archive_workspace_files",
    "scan_orphan_files",
]
