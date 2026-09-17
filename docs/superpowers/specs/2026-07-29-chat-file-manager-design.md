# Chat File Manager Design

## Purpose

Replace the chat header's flat generated-file drawer and nested preview modal with a tenant-scoped file-management overlay. The overlay keeps chat in context while providing directory browsing, safe file operations, and in-place previews.

## Scope and boundaries

The implementation is a dedicated chat File Manager overlay backed by a controlled directory API. It is not a general host filesystem browser or a new global filesystem page.

The API accepts a shortcut-root identity and a relative path only. The server resolves paths within the current tenant and Agent workspace, applies per-root capabilities, rejects path escapes, and never exposes arbitrary host paths as operations.

### Directory roots

| UI root | Workspace mapping | Capabilities |
| --- | --- | --- |
| 工作目录 | Tenant Agent workspace root | Browse, upload, edit eligible text, download a file, move a file to recycle bin |
| 上传目录 | `media` | Browse, upload, edit eligible text, download a file, move a file to recycle bin |
| 下载目录 | `static` | Browse, upload, edit eligible text, download a file, move a file to recycle bin |
| 对话目录 | `sessions` | Browse, preview, download a file only |
| 回收站 | Controlled view of the governance archive | Restore or permanently delete only |

The Working Directory omits `sessions` and `governance`; all other workspace files and directories remain visible. `sessions` is available through its dedicated read-only root. `governance` is never browsed as a raw filesystem directory; its archive is exposed only through the Recycle Bin. Symbolic links remain visible as restricted entries but cannot be followed or acted on.

## Visual design

The overlay follows the supplied reference image: a refined white desktop surface with a light shadow and rounded corners, a thin-divider information hierarchy, blue interactive accents, and low-contrast secondary dates. It occupies approximately 75% of viewport width and 85% of height. It adapts to the existing dark theme through semantic color tokens rather than changing its structure.

The top area has two rows:

1. Breadcrumbs, current-directory search, Upload, and close.
2. Shortcut roots: Upload, Download, Working, Recycle Bin, and Conversation.

Breadcrumbs begin at the active shortcut root, not a synthetic `Home`. Clicking any breadcrumb reanchors that directory as the left-column start and clears stale preview/path state.

The main area is always `2:2:6`: the left and middle columns each use 20% of the content width; the right column uses 60%. Thin vertical dividers separate columns. Rows use a type icon, name, and weak date line; they have no table headers, Size column, or Modified column. Selected rows use a pale blue highlight and show a delete affordance only where deletion is permitted.

On narrow viewports, the overlay fills the available screen. The `2:2:6` layout preserves a minimum width and the three columns scroll horizontally as one strip; each column still scrolls vertically on its own.

## Navigation model

The visible columns are a moving window over continuous directory levels, not fixed parent/current/preview modules.

### Initial and reanchored paths

When the overlay opens, a shortcut root is selected, or a breadcrumb is clicked:

1. The left column shows a synthetic anchor for the target directory itself; its direct items populate the middle column.
2. Folders sort before files; entries in each kind use case-insensitive natural-name order.
3. The first folder in the middle column becomes the right directory. Each non-anchor column lists the direct contents of its directory.
4. If the target directory has no child folder, the right column states that no child folder exists; the UI never selects or previews a first file just to fill the space.

### User selection

- Selecting a folder in the left column backfills its parent (or the shortcut anchor at the root) into the left column, moves the former left directory to the middle column, and loads the selected folder in the right column.
- Selecting a folder in the middle column keeps the left and middle directories in place and loads the selected folder in the right column.
- Selecting a folder or file in the right column advances the three-column window left by one level: former middle becomes left, former right becomes middle, and the selection occupies the right-side destination.
- When the right-column selection is a file, the newly exposed right column renders that file's Preview/Details panel in place. There is no nested preview modal.
- Search filters only the middle directory's direct children, case-insensitively, and does not change path or selection. If no middle directory exists, it filters the active shortcut root.

Upload targets the directory represented by the middle column. If no middle directory exists, it targets the active shortcut root.

## Files, preview, and editing

The right-side file view shows the type icon, filename, file size, Preview and Details tabs, and contextual Edit or Download actions.

Eligible plain UTF-8 text files, including Markdown and HTML, edit in place. Binary files, Office documents, PDFs, images, audio, and video do not show Edit.

Text files at or below 1 MB are read in full and can be edited. Files larger than 1 MB show the first 1 MB only, remain downloadable, and cannot be edited. HTML previews run in an iframe sandbox that permits scripts but withholds same-origin access, top-level navigation, popups, and download permissions.

Text saves carry a file revision identifier. A changed server revision rejects the save without overwriting, retains the local draft, and prompts the user to resolve the conflict. Closing the overlay or triggering navigation with unsaved text requires Save, Discard, or Cancel; the pending action proceeds only after a successful save or explicit discard.

## Mutations and recycle bin

Upload is enabled only for Working, Upload, and Download roots. It opens a file picker for the current destination, rejects a name collision without overwriting or renaming, and refreshes the destination after success without selecting the new file.

Only files can be moved to the recycle bin in the first release; folders have no delete control. A normal deletion requires confirmation and moves the file to the governance archive through the existing archive semantics.

The Recycle Bin displays archived files by original identity and archived-at time rather than raw governance records. Restore returns a file to its original path only. If that path contains a file, restore fails without overwriting or removing the archived item. Permanent deletion shows a second destructive confirmation containing the original path; after confirmation it has no undo.

Working, Upload, Download, and Conversation roots support single-file download from the Details panel. Folder ZIP downloads and recycle-bin downloads are out of scope.

Every upload, save, recoverable deletion, restore, and permanent deletion writes an application audit record containing actor, time, action, path, and outcome, without recording file contents. Preview and download do not create audit records.

## API and resilience

Directory listing responses return paged direct entries, including type, display metadata, weak date, preview classification, capability flags, and stable revision identity. Each column loads its own first page of 100 entries and incrementally loads later pages as the user approaches its bottom. Current-directory search uses the same server-side filtering and pagination.

Read, save, upload, download, archive, restore, and permanent-delete endpoints are discrete controlled operations. Governance-archive operations adapt existing archive records rather than exposing governance control files.

Loading, error, and retry state belongs to one column. A failed column shows its own retry affordance and does not close the overlay or clear healthy columns.

## Verification

Automated tests should cover:

- Default Working-root selection, automatic path construction, folder-first natural ordering, and early termination.
- Shortcut and breadcrumb reanchoring, non-right and right-column selection, and file-preview advance.
- Root capability enforcement, hidden managed entries, link restriction, and path-escape rejection.
- Independent 100-item incremental loading, search scope, loading/error/retry isolation, and responsive column behavior.
- Preview classification, 1 MB text behavior, HTML sandbox configuration, edit eligibility, save conflict, and unsaved-edit guard.
- Upload destination, same-name rejection, file-only recycle deletion, restore conflict, permanent-delete confirmation, and mutation auditing.

Manual acceptance should compare the completed desktop surface to the provided reference for hierarchy, spacing, selected rows, two-row navigation, and `2:2:6` visual balance, and verify dark theme plus narrow-screen horizontal column access.

## Out of scope

- Folder deletion, folder download archives, folder upload, and drag-and-drop moves.
- Editing binary, Office, PDF, image, audio, or video files.
- Raw `governance` browsing and any operation on a symbolic link.
- Workspace-wide or recursive search.
