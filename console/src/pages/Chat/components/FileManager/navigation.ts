import type {
  FileManagerDirectoryListing,
  FileManagerItem,
  FileManagerRoot,
} from "../../../../../api/modules/chat";

export interface FileManagerDetail {
  root: FileManagerRoot;
  entry: FileManagerItem;
}

export interface FileManagerNavigationState {
  root: FileManagerRoot;
  columns: [
    FileManagerDirectoryListing | null,
    FileManagerDirectoryListing | null,
    FileManagerDirectoryListing | null,
  ];
  selected: [string | null, string | null, string | null];
  detail: FileManagerDetail | null;
}

export type DirtyEditorResolution =
  | "navigate"
  | "shortcut"
  | "breadcrumb"
  | "close"
  | "save"
  | "discard"
  | "cancel";

function emptyColumns(): FileManagerNavigationState["columns"] {
  return [null, null, null];
}

function emptySelection(): FileManagerNavigationState["selected"] {
  return [null, null, null];
}

/**
 * Anchors a three-column path window. The caller supplies directory pages so
 * this module remains independent from request timing and cache ownership.
 */
export function initialNavigation(
  rootDirectory: FileManagerDirectoryListing,
  firstFolderDirectory?: FileManagerDirectoryListing | null,
  firstChildFolderDirectory?: FileManagerDirectoryListing | null,
): FileManagerNavigationState {
  const columns = emptyColumns();
  const selected = emptySelection();
  columns[0] = rootDirectory;

  if (firstFolderDirectory) {
    columns[1] = firstFolderDirectory;
    selected[0] = firstFolderDirectory.path || null;
  }
  if (firstChildFolderDirectory) {
    columns[2] = firstChildFolderDirectory;
    selected[1] = firstChildFolderDirectory.path || null;
  }

  return {
    root: rootDirectory.root,
    columns,
    selected,
    detail: null,
  };
}

/** Rebuild the path window after a root shortcut or breadcrumb navigation. */
export function reanchor(
  rootDirectory: FileManagerDirectoryListing,
  firstFolderDirectory?: FileManagerDirectoryListing | null,
  firstChildFolderDirectory?: FileManagerDirectoryListing | null,
): FileManagerNavigationState {
  return initialNavigation(
    rootDirectory,
    firstFolderDirectory,
    firstChildFolderDirectory,
  );
}

function requireFolderPage(
  entry: FileManagerItem,
  directory: FileManagerDirectoryListing | null | undefined,
): FileManagerDirectoryListing {
  if (
    !directory ||
    entry.kind !== "directory" ||
    directory.path !== entry.path
  ) {
    throw new Error("A selected folder requires its matching directory page");
  }
  return directory;
}

/**
 * Applies a completed row selection. Folder pages are provided by the caller
 * after its fetch succeeds; file selections never issue implicit previews.
 */
export function selectItem(
  state: FileManagerNavigationState,
  columnIndex: 0 | 1 | 2,
  entry: FileManagerItem,
  folderDirectory?: FileManagerDirectoryListing | null,
): FileManagerNavigationState {
  const isFolder = entry.kind === "directory";
  const folderPage = isFolder
    ? requireFolderPage(entry, folderDirectory)
    : null;

  if (columnIndex === 2) {
    const priorMiddle = state.columns[1];
    const priorRight = state.columns[2];
    if (!priorMiddle || !priorRight) {
      throw new Error(
        "The rightmost selection requires an established path window",
      );
    }
    return {
      root: state.root,
      columns: [priorMiddle, priorRight, folderPage],
      selected: [state.selected[1], entry.path, null],
      detail: isFolder ? null : { root: state.root, entry },
    };
  }

  const columns = emptyColumns();
  const selected = emptySelection();
  columns[0] = state.columns[0];
  selected[0] = state.selected[0];

  if (columnIndex === 1) {
    columns[1] = state.columns[1];
    selected[1] = entry.path;
  } else {
    selected[0] = entry.path;
  }

  if (isFolder) {
    columns[columnIndex + 1] = folderPage;
    return { root: state.root, columns, selected, detail: null };
  }

  return {
    root: state.root,
    columns,
    selected,
    detail: { root: state.root, entry },
  };
}

/** Save/discard actions are allowed through the guard; other exits need a decision. */
export function canLeaveDirtyEditor(
  dirty: boolean,
  resolution: DirtyEditorResolution,
): boolean {
  return !dirty || resolution === "save" || resolution === "discard";
}
