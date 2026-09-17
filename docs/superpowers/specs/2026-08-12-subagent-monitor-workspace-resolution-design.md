# SubAgent Monitor Workspace Resolution Design

## Goal

Make the SubAgent run monitor APIs resolve the same complete, agent-scoped
Workspace as the chat APIs so that an active SubAgent run snapshot can be
returned to the existing Console monitor.

## Problem

`TenantWorkspaceMiddleware` stores a lightweight `TenantWorkspaceContext` in
`request.state.workspace`. It contains tenant and directory information only;
it deliberately has no `chat_manager`. The SubAgent router's private
`_get_workspace` dependency returns this object before invoking the normal
agent resolver. `_get_chat` then fails with `ChatManager not initialized`.

The Console monitor treats the failed snapshot request as an empty snapshot
and returns `null`, so no progress control is rendered.

## Decision

The SubAgent router will use `get_workspace` from `swe.app.runner.api`, the
same dependency used by the chat APIs. That dependency delegates to
`get_agent_for_request`, which already rejects `TenantWorkspaceContext` as a
runtime workspace and lazily resolves the complete agent-scoped Workspace.

The local `_get_workspace` implementation and its direct
`get_agent_for_request` import will be removed. The endpoint URLs, request
fields, response schemas, monitoring store, polling, SSE refresh event, and
Console UI styling will not change.

## Request Flow After Change

```text
GET /api/subagents/runs?chat_id=<chat UUID>
  -> Depends(runner.api.get_workspace)
  -> get_agent_for_request(request)
  -> MultiAgentManager.get_agent(...)
  -> complete Workspace.chat_manager
  -> resolve chat UUID to logical session_id
  -> return matching SubAgent run snapshot
```

The same dependency is used by `POST /api/subagents/runs/{run_id}/cancel`,
keeping read and cancel operations within one tenant/agent scope.

## Test Strategy

Router tests will stop relying on the obsolete `app.state.workspace` fallback
and will inject a complete Workspace through FastAPI dependency overrides.
A regression case will set `request.state.workspace` to a
`TenantWorkspaceContext`, assert that the standard resolver is used, and
verify that `GET /subagents/runs` returns a snapshot rather than a 500.
Existing snapshot filtering and cancellation tests remain unchanged in
behavior.

## Acceptance Criteria

- A request that has a lightweight tenant workspace context resolves a complete
  Workspace before the SubAgent router accesses `chat_manager`.
- `GET /api/subagents/runs?chat_id=<existing UUID>` returns HTTP 200 and the
  snapshot for that chat's logical session.
- The cancel endpoint continues to return the existing 200/404/409 outcomes.
- The Console receives a non-empty `runs` array for an active Background
  SubAgent and renders the existing floating progress trigger.
