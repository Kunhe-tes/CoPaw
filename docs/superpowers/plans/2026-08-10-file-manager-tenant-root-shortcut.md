# File Manager Tenant Root Shortcut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tenant/source-scoped “根目录” File Manager shortcut rooted at `/opt/deployments/app/working/<effective-scope>/`, without changing the default active working directory.

**Architecture:** Keep `resolve_file_manager_workspace_dir()` unchanged because its upstream impact is CRITICAL (8 direct Console route callers). Add a narrow resolver that derives one validated storage-scope component from the middleware-owned `TenantWorkspaceContext`, then pass the deployment base and component to `FileManagerService`. The service opens the source-scope component with `O_NOFOLLOW` from the fixed base, and archives its explicit root metadata with existing per-Agent-workspace recycle data.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, descriptor-based POSIX filesystem APIs, pytest, React, TypeScript, Vitest, React Testing Library, GitNexus.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/swe/app/agent_context.py` | Resolve the trusted source-scope base/component from request tenant workspace state without changing Agent workspace selection. |
| `src/swe/app/file_manager.py` | Add `source_scope`, descriptor-safe root opening/provisioning, and explicit archive root metadata. |
| `src/swe/app/routers/console.py` | Construct one File Manager service per request with the verified source-scope location. |
| `tests/unit/routers/test_agents_tenant_scope.py` | Prove request-to-scope component mapping and fail-closed behavior. |
| `tests/unit/app/test_file_manager.py` | Prove root operations, missing-root provisioning, archive/restore, cursor separation, and symlink rejection. |
| `tests/unit/routers/test_console_chat_stream.py` | Prove every File Manager HTTP route passes the request-scoped root location. |
| `console/src/api/modules/chat.ts` | Extend the File Manager root protocol union. |
| `console/src/pages/Chat/components/FileManager/index.tsx` | Render the new shortcut immediately after the working-directory shortcut. |
| `console/src/pages/Chat/components/FileManager/index.test.tsx` | Cover ordering, working default, and source-scope selection request. |

## Task 1: Define request-scoped root location without touching the critical resolver

**Files:**
- Modify: `tests/unit/routers/test_agents_tenant_scope.py`
- Modify: `src/swe/app/agent_context.py`

- [ ] **Step 1: Write failing resolver tests**

  Add tests for a normal tenant and for `tenant_id="default"` with `source_id`. Build each request with a `TenantWorkspaceContext` whose `workspace_dir` is the canonical effective-scope directory. Patch the source-scope base to a temporary parent and assert that the result is `(base, workspace_dir.name)`, never the raw `tenant_id`.

  ```python
  location = agent_context.resolve_file_manager_source_scope_location(request)

  assert location.base_dir == source_scope_base
  assert location.component == tenant_workspace_dir.name
  ```

  Add failing cases for a missing/invalid `request.state.workspace` and an unsafe component (`""`, `".."`, or one containing `/`). Assert a `503` response error with no host path in its detail.

- [ ] **Step 2: Run the focused tests and verify failure**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_agents_tenant_scope.py -k "file_manager_source_scope" -v
  ```

  Expected: FAIL because `resolve_file_manager_source_scope_location` does not exist.

- [ ] **Step 3: Add the narrow location value and resolver**

  In `src/swe/app/agent_context.py`, add a frozen value object plus a public synchronous resolver beside `resolve_file_manager_workspace_dir()`. Read only the middleware-installed `TenantWorkspaceContext`; derive the component from its resolved `workspace_dir.name`; validate that it is exactly one non-empty pathname component. Use the fixed deployment base constant `Path("/opt/deployments/app/working")` and do not accept a path from HTTP input.

  ```python
  FILE_MANAGER_SOURCE_SCOPE_BASE_DIR = Path(
      "/opt/deployments/app/working",
  )

  @dataclass(frozen=True)
  class FileManagerSourceScopeLocation:
      base_dir: Path
      component: str

  def resolve_file_manager_source_scope_location(
      request: Request,
  ) -> FileManagerSourceScopeLocation:
      tenant_workspace = getattr(request.state, "workspace", None)
      if not isinstance(tenant_workspace, TenantWorkspaceContext):
          raise HTTPException(503, "Tenant workspace is unavailable")
      component = Path(tenant_workspace.workspace_dir).resolve().name
      if component in {"", ".", ".."} or "/" in component:
          raise HTTPException(503, "Tenant workspace is unavailable")
      return FileManagerSourceScopeLocation(
          FILE_MANAGER_SOURCE_SCOPE_BASE_DIR,
          component,
      )
  ```

  Export the resolver and value object from the module's `__all__`. Do not modify `resolve_file_manager_workspace_dir()` or recompute the effective tenant from headers.

- [ ] **Step 4: Run focused tests and commit**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_agents_tenant_scope.py -k "file_manager_source_scope" -v
  ```

  Expected: PASS.

  ```bash
  git add src/swe/app/agent_context.py tests/unit/routers/test_agents_tenant_scope.py
  git commit -m "feat(file-manager): resolve tenant source root"
  ```

## Task 2: Extend the descriptor-safe file service and archive contract

**Files:**
- Modify: `tests/unit/app/test_file_manager.py`
- Modify: `src/swe/app/file_manager.py`

- [ ] **Step 1: Write failing source-scope service tests**

  Construct `FileManagerService(workspace, source_scope_base_dir=base, source_scope_component="tenant-a", ...)`. Cover listing, upload, read, text save, download, archive, restore and purge using `FileManagerRoot.SOURCE_SCOPE`. Assert all bytes live beneath `base / "tenant-a"`, while the archive index remains beneath the original Agent workspace.

  ```python
  archived = service.archive_file("source_scope", "report.txt", actor="test")

  assert archived.original_path == "source_scope/report.txt"
  assert (workspace / "governance" / "archive" / "index.json").exists()
  assert not (base / "tenant-a" / "report.txt").exists()
  ```

  Add focused negative tests: a cursor issued for `source_scope` fails under `working`; a `tenant-a` source root implemented as a symlink is rejected; and a missing source root lists empty but is provisioned on upload. Preserve all existing root tests as legacy-archive compatibility coverage.

- [ ] **Step 2: Run the focused tests and verify failure**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k "source_scope" -v
  ```

  Expected: FAIL because `source_scope` is not a valid root.

- [ ] **Step 3: Add the root and open it from a trusted parent descriptor**

  Add `SOURCE_SCOPE = "source_scope"` to `FileManagerRoot` and give it the same capabilities as `WORKING`. Extend the service constructor with optional `source_scope_base_dir` and `source_scope_component` arguments; reject source-scope access when either is absent.

  Replace the single `_workspace_dir` opening assumption with `_open_root_fd(root, *, create_source_scope_root=False)`. For `SOURCE_SCOPE`, open the configured base with directory flags, create only the single validated component with `os.mkdir(..., dir_fd=base_fd)` when an upload targets the source-scope root, then open it with `O_NOFOLLOW`. For other roots, retain the current workspace root and component behavior unchanged.

  ```python
  def _open_root_fd(
      self,
      root: FileManagerRoot,
      *,
      create_source_scope_root: bool = False,
  ) -> int | None:
      if root is not FileManagerRoot.SOURCE_SCOPE:
          return os.open(self._workspace_dir, self._directory_open_flags())
      if self._source_scope_base_dir is None or self._source_scope_component is None:
          raise FileManagerPathError("Source-scope root is unavailable")
      base_fd = os.open(self._source_scope_base_dir, self._directory_open_flags())
      try:
          if create_source_scope_root:
              try:
                  os.mkdir(self._source_scope_component, 0o700, dir_fd=base_fd)
              except FileExistsError:
                  pass
          return os.open(
              self._source_scope_component,
              self._directory_open_flags(),
              dir_fd=base_fd,
          )
      except FileNotFoundError:
          return None
      finally:
          os.close(base_fd)
  ```

  Keep child traversal, regular-file checks and symlink rejection on the returned root descriptor. Do not call `Path.resolve()` on the tenant component or use the display path as an access grant.

  Make `_root_components(SOURCE_SCOPE)` return `()`, make `_root_path(SOURCE_SCOPE)` return the configured base/component only for the non-authoritative display result of `resolve_path()`, and have `_open_directory_fd()` start from `_open_root_fd()`. `list_directory()` should return an empty root listing when that root is absent; only `upload_stream()` requests root provisioning, and nested destination directories retain the existing “not found” behavior.

- [ ] **Step 4: Store explicit archive locations and retain legacy entries**

  New archive items must store `root: resolved_root.value` and `relative_path: normalised_path`, while retaining `original_path` for the current API display contract. Introduce one helper that validates an archive row and returns `(root, relative_path, display_path)`. Rows without the new fields must retain the existing `media`/`static`/working interpretation.

  Route restore, recovery and file-identity checks through that helper so a `source_scope` row restores to the external root, and an existing archive index remains readable.

  Rename the current validation helper to `_validate_legacy_archive_original_path()` and add the display helper used by the new-row branch:

  ```python
  def _archive_display_path(
      self,
      root: FileManagerRoot,
      relative_path: str,
  ) -> str:
      if root is FileManagerRoot.SOURCE_SCOPE:
          return f"{root.value}/{relative_path}"
      return self._workspace_relative_path(root, relative_path)

  def _archive_item_location(
      self, item: Mapping[str, object],
  ) -> tuple[FileManagerRoot, str, str]:
      if "root" in item or "relative_path" in item:
          root = FileManagerRoot(str(item.get("root") or ""))
          relative_path = self._normalise_relative_path(
              str(item.get("relative_path") or ""),
          )
          self._validate_root_and_path(root, relative_path)
          return root, relative_path, self._archive_display_path(
              root, relative_path,
          )
      original_path = self._validate_legacy_archive_original_path(item)
      root, relative_path = self._root_from_workspace_relative(original_path)
      return root, relative_path, original_path
  ```

- [ ] **Step 5: Run unit coverage and commit**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/app/test_file_manager.py -v
  ```

  Expected: PASS, including existing archive-recovery coverage and the new source-scope cases.

  ```bash
  git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py
  git commit -m "feat(file-manager): add tenant source root"
  ```

## Task 3: Assemble request services for all File Manager routes

**Files:**
- Modify: `tests/unit/routers/test_console_chat_stream.py`
- Modify: `src/swe/app/routers/console.py`

- [ ] **Step 1: Write failing route-assembly tests**

  Extend `_build_file_manager_client` so it patches both workspace and source-scope location resolution. Record the arguments passed to `get_file_manager_service`. Exercise directory listing, read, download, text save, upload, archive, restore and purge with `root=source_scope`; assert each receives the request's workspace plus the same base/component pair.

  ```python
  response = client.get(
      "/console/file-manager/directories",
      params={"root": "source_scope"},
  )

  assert response.status_code == 200
  assert observed_locations == [(source_scope_base, "tenant-a")]
  ```

- [ ] **Step 2: Run the focused HTTP tests and verify failure**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -k "file_manager" -v
  ```

  Expected: FAIL because the routes construct the service with only `workspace_dir`.

- [ ] **Step 3: Add one service factory helper and use it in every route**

  In `console.py`, add `_get_file_manager_service_for_request(request)` that awaits the unchanged workspace resolver, calls `resolve_file_manager_source_scope_location(request)`, and passes both values to `get_file_manager_service`. Replace the repeated two-line construction in all eight File Manager handlers with this helper.

  ```python
  async def _get_file_manager_service_for_request(
      request: Request,
  ) -> FileManagerService:
      workspace_dir = await resolve_file_manager_workspace_dir(request)
      location = resolve_file_manager_source_scope_location(request)
      return get_file_manager_service(
          workspace_dir,
          source_scope_base_dir=location.base_dir,
          source_scope_component=location.component,
      )
  ```

  Before editing each handler, run GitNexus upstream impact on its exact symbol. The prior impact result for `resolve_file_manager_workspace_dir` is CRITICAL, so it must remain unchanged.

- [ ] **Step 4: Run HTTP tests and commit**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -k "file_manager" -v
  ```

  Expected: PASS; existing working-root requests remain unchanged and source-scope requests are routed to their tenant directory.

  ```bash
  git add src/swe/app/routers/console.py tests/unit/routers/test_console_chat_stream.py
  git commit -m "feat(console): bind file manager source root"
  ```

## Task 4: Add the shortcut without changing the default root

**Files:**
- Modify: `console/src/api/modules/chat.ts`
- Modify: `console/src/pages/Chat/components/FileManager/index.tsx`
- Modify: `console/src/pages/Chat/components/FileManager/index.test.tsx`

- [ ] **Step 1: Write failing component tests**

  In the open-dialog test, assert that shortcut buttons appear in this order: `工作目录`, `根目录`, `上传目录`, `下载目录`, `对话目录`, `回收站`. Assert working remains `aria-pressed="true"` and root is not pressed on first open. Add a click test for 根目录 which waits for `listDirectory` and asserts its latest request has `root: "source_scope"` and an empty path.

  ```tsx
  fireEvent.click(within(shortcuts).getByRole("button", { name: "根目录" }));

  await waitFor(() =>
    expect(listDirectory).toHaveBeenLastCalledWith(
      expect.objectContaining({ root: "source_scope", path: "" }),
    ),
  );
  ```

- [ ] **Step 2: Run the focused component test and verify failure**

  Run:

  ```bash
  pnpm test:run src/pages/Chat/components/FileManager/index.test.tsx
  ```

  Expected: FAIL because `source_scope` is not in the frontend protocol or shortcut list.

- [ ] **Step 3: Extend the protocol and shortcut list**

  Add `"source_scope"` to `FileManagerRoot` in `chat.ts`. In `index.tsx`, add one shortcut object immediately after working. Reuse the existing folder icon and do not change `useState<FileManagerRoot>("working")`, `uploadDisabledReason`, navigation state, or capability checks.

  ```tsx
  { root: "working", label: "工作目录", icon: <FolderOpenOutlined /> },
  { root: "source_scope", label: "根目录", icon: <FolderOpenOutlined /> },
  { root: "upload", label: "上传目录", icon: <UploadOutlined /> },
  ```

- [ ] **Step 4: Run frontend validation and commit**

  Run:

  ```bash
  pnpm test:run src/pages/Chat/components/FileManager/index.test.tsx
  pnpm exec tsc --noEmit
  ```

  Expected: PASS.

  ```bash
  git add console/src/api/modules/chat.ts console/src/pages/Chat/components/FileManager/index.tsx console/src/pages/Chat/components/FileManager/index.test.tsx
  git commit -m "feat(chat): add tenant root shortcut"
  ```

## Task 5: End-to-end regression review

**Files:**
- Modify: `docs/superpowers/specs/2026-08-10-file-manager-tenant-root-shortcut-design.md` only if implementation exposes a confirmed design mismatch.
- Modify: `docs/superpowers/plans/2026-08-10-file-manager-tenant-root-shortcut.md` only to mark completed steps during execution.

- [ ] **Step 1: Run cross-layer regression checks**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/app/test_file_manager.py tests/unit/routers/test_console_chat_stream.py tests/unit/routers/test_agents_tenant_scope.py -v
  pnpm test:run src/pages/Chat/components/FileManager/index.test.tsx
  pnpm exec tsc --noEmit
  ```

  Expected: PASS.

- [ ] **Step 2: Verify scope and execution-flow impact**

  Run GitNexus `detect_changes({scope: "all"})`. Review any changed symbol outside the File Manager service, Console routes, request-location resolver, and File Manager frontend. Run `git diff --check` and verify that no unrelated user changes are staged.

- [ ] **Step 3: Commit plan/spec status only when changed**

  If execution marked plan steps or corrected an approved design decision, commit only those documentation changes:

  ```bash
  git add docs/superpowers/specs/2026-08-10-file-manager-tenant-root-shortcut-design.md docs/superpowers/plans/2026-08-10-file-manager-tenant-root-shortcut.md
  git commit -m "docs(file-manager): record root shortcut delivery"
  ```
