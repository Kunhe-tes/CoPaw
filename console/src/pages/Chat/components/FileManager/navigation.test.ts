import { describe, expect, it } from "vitest";
import type {
  FileManagerDirectoryListing,
  FileManagerItem,
} from "../../../../../api/modules/chat";
import {
  canLeaveDirtyEditor,
  initialNavigation,
  reanchor,
  selectItem,
} from "./navigation";

const capabilities = {
  browse: true,
  read: true,
  upload: true,
  edit: true,
  download: true,
  archive: true,
};

function directory(
  path: string,
  items: FileManagerItem[] = [],
): FileManagerDirectoryListing {
  return {
    root: "working",
    path,
    items,
    next_cursor: null,
    has_child_directory: items.some((item) => item.kind === "directory"),
    first_child_directory:
      items.find((item) => item.kind === "directory")?.path ?? null,
    capabilities,
  };
}

function folder(path: string): FileManagerItem {
  return {
    name: path.split("/").at(-1) ?? path,
    path,
    kind: "directory",
    capabilities,
  };
}

function file(path: string): FileManagerItem {
  return {
    name: path.split("/").at(-1) ?? path,
    path,
    kind: "file",
    size_bytes: 4,
    capabilities,
  };
}

describe("file-manager navigation", () => {
  const workspace = directory("", [folder("projects")]);
  const projects = directory("projects", [folder("projects/docs")]);
  const docs = directory("projects/docs", [file("projects/docs/README.md")]);

  it("anchors the initial window at root and fills two folder levels without previewing a file", () => {
    expect(initialNavigation(workspace, projects, docs)).toEqual({
      root: "working",
      columns: [workspace, projects, docs],
      selected: ["projects", "projects/docs", null],
      detail: null,
    });
  });

  it("places a middle-column file in the detail column without moving the window", () => {
    const state = initialNavigation(workspace, projects, docs);
    const readme = file("projects/docs/README.md");

    expect(selectItem(state, 1, readme)).toMatchObject({
      columns: [workspace, projects, null],
      selected: ["projects", "projects/docs/README.md", null],
      detail: { root: "working", entry: readme },
    });
  });

  it("moves the window left when selecting a rightmost folder", () => {
    const deeper = directory("projects/docs/guides", [
      file("projects/docs/guides/a.md"),
    ]);
    const state = initialNavigation(
      workspace,
      projects,
      directory("projects/docs", [folder("projects/docs/guides")]),
    );

    expect(
      selectItem(state, 2, folder("projects/docs/guides"), deeper),
    ).toMatchObject({
      columns: [projects, state.columns[2], deeper],
      selected: ["projects/docs", "projects/docs/guides", null],
      detail: null,
    });
  });

  it("moves the window left when selecting a rightmost file and opens its detail", () => {
    const state = initialNavigation(workspace, projects, docs);
    const readme = file("projects/docs/README.md");

    expect(selectItem(state, 2, readme)).toMatchObject({
      columns: [projects, docs, null],
      selected: ["projects/docs", "projects/docs/README.md", null],
      detail: { root: "working", entry: readme },
    });
  });

  it("reanchors breadcrumbs and shortcuts to their first folder descendants", () => {
    expect(reanchor(workspace, projects, docs)).toEqual(
      initialNavigation(workspace, projects, docs),
    );
  });

  it("allows ordinary navigation only after a dirty editor is saved or discarded", () => {
    expect(canLeaveDirtyEditor(true, "navigate")).toBe(false);
    expect(canLeaveDirtyEditor(false, "navigate")).toBe(true);
    expect(canLeaveDirtyEditor(true, "save")).toBe(true);
    expect(canLeaveDirtyEditor(true, "discard")).toBe(true);
  });
});
