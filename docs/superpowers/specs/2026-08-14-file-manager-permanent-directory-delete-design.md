# File Manager Permanent Directory Delete Design

## Goal

Allow a user to permanently delete a complete directory from the Console file
manager. The operation is available only for directories under the writable
working, source-scope, upload, and download roots. It does not use the recycle
bin. Existing single-file archive-to-recycle behavior remains unchanged.

## Interaction

Each directory row exposes a trailing delete icon while the row is hovered,
keyboard-focused, or selected. The icon has an accessible label and stops the
row-selection event so activating it does not open the directory.

The confirmation dialog shows the selected directory's complete relative path
and states that the directory and all its contents will be permanently deleted
and cannot be restored. Its confirmation action is danger-styled and labelled
"永久删除". Cancellation makes no request.

After a successful deletion, the file manager clears stale detail and selection
state for the removed directory, refreshes the affected current listing, and
shows "目录已永久删除". Request failures leave the current listing intact and
show the existing request error treatment.

## API and Backend

Introduce a dedicated directory-delete endpoint rather than changing the
existing `DELETE /console/file-manager/files` archive endpoint. The frontend
adds a matching `fileManager.deleteDirectory({ root, path })` adapter.

The file-manager service provides a serialized directory-deletion operation.
It validates the root and relative path using the existing controlled-root
policy, requires archive-capable (therefore writable) roots, rejects an empty
path, and opens directories without following symlinks. It recursively removes
entries through directory file descriptors:

- regular files and special entries are unlinked;
- nested directories are opened without following links, emptied, and removed;
- symlinks are unlinked as links and their targets are never traversed.

The same root protection continues to hide and prohibit deleting protected
working-root paths such as `sessions` and `governance`. Read-only conversation
and recycle roots are rejected.

## Data Flow

`FileColumn` exposes a directory action callback only where an entry advertises
archive/write capability and the current root is not conversation or recycle.
`FileManager` owns the confirmation dialog and request lifecycle. It invokes
the dedicated API adapter, clears dependent view state, and reloads the active
directory page. The router translates existing file-manager path errors and
records the permanent-directory-delete audit event.

## Error Handling

Directory deletion is not transactional across a tree: an operating-system
failure may leave an undeleted remainder. The response reports the failure;
the next directory refresh represents the actual remaining contents. No recycle
index entry is created, and no retry is automated.

## Tests

- Console: the delete control appears for an eligible directory in hover/focus
  and selected states, does not trigger navigation, asks for confirmation,
  calls the directory endpoint only after confirmation, refreshes on success,
  and surfaces request failure.
- Service: nested directories are deleted; symlink targets survive; root,
  protected, and read-only paths are rejected; a deletion failure retains the
  surviving filesystem state without following links.
- Router: the dedicated endpoint binds the request tenant scope, invokes the
  service, records success/failure audit actions, and returns the expected
  response.

## Scope Boundaries

This change does not add folder creation, bulk selection, undo, recycle-bin
directory entries, permanent deletion of ordinary files, or a global Console
restyle.
