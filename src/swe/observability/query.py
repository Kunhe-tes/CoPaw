# -*- coding: utf-8 -*-
"""Authorized run-list query and tamper-evident pagination cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..config.context import is_valid_identity_value
from .config import EmitterConfig, capture_enabled
from .emitter import default_emitter
from .store import ObservabilityStore

router = APIRouter(prefix="/agent-observability", tags=["agent-observability"])
_MAX_PAGE_SIZE = 200
_MAX_EVENT_PAGE_SIZE = 500
_MAX_EVENT_RESPONSE_BYTES = 1_000_000
_MAX_WINDOW = timedelta(days=31)


class RunListResponse(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None
    generated_at: datetime
    window_start: datetime
    window_end: datetime


class CapabilitiesResponse(BaseModel):
    capture_enabled: bool
    storage_configured: bool
    storage_ready: bool
    projector_running: bool
    queue_events: int
    queue_bytes: int
    max_event_bytes: int


class HealthResponse(BaseModel):
    capture_enabled: bool
    storage_ready: bool
    projector_running: bool
    dropped_events: int | None
    generated_at: datetime


class RunDetailResponse(BaseModel):
    run: dict[str, Any]
    attempts: list[dict[str, Any]]
    spans: list[dict[str, Any]]
    generated_at: datetime
    spans_has_more: bool
    spans_next_cursor: str | None = None


class EventListResponse(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None
    generated_at: datetime


def _require_observability_reader(request: Request) -> str:
    role = request.headers.get("X-User-Role", "").strip().lower()
    if role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    if role == "manager" and not getattr(request.state, "source_id", None):
        raise HTTPException(status_code=403, detail="Source scope required")
    return role


async def _storage_ready(request: Request) -> bool:
    store = getattr(request.app.state, "agent_observability_store", None)
    if not isinstance(store, ObservabilityStore):
        return False
    try:
        readiness = await store.readiness()
    except Exception:
        return False
    return bool(readiness.get("ready"))


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(request: Request) -> CapabilitiesResponse:
    _require_observability_reader(request)
    config = EmitterConfig.from_environment()
    return CapabilitiesResponse(
        capture_enabled=capture_enabled(),
        storage_configured=getattr(
            request.app.state,
            "agent_observability_connection",
            None,
        )
        is not None,
        storage_ready=await _storage_ready(request),
        projector_running=bool(
            getattr(
                getattr(
                    request.app.state,
                    "agent_observability_projector",
                    None,
                ),
                "running",
                False,
            ),
        ),
        queue_events=config.max_queue_events,
        queue_bytes=config.max_queue_bytes,
        max_event_bytes=config.max_event_bytes,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    if _require_observability_reader(request) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    dropped_events = None
    if capture_enabled():
        try:
            dropped_events = default_emitter().dropped_count
        except Exception:
            dropped_events = None
    return HealthResponse(
        capture_enabled=capture_enabled(),
        storage_ready=await _storage_ready(request),
        projector_running=bool(
            getattr(
                getattr(
                    request.app.state,
                    "agent_observability_projector",
                    None,
                ),
                "running",
                False,
            ),
        ),
        dropped_events=dropped_events,
        generated_at=datetime.now(timezone.utc),
    )


def _authorized_sources(
    request: Request,
    requested: list[str] | None,
) -> list[str]:
    role = request.headers.get("X-User-Role", "").strip().lower()
    current = getattr(request.state, "source_id", None)
    if role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    if not isinstance(current, str) or not current:
        raise HTTPException(status_code=403, detail="Source scope required")
    if role == "manager":
        if requested and any(source != current for source in requested):
            raise HTTPException(status_code=403, detail="Source scope denied")
        return [current]
    sources = list(dict.fromkeys(requested or [current]))
    if not sources or any(
        not is_valid_identity_value(source) or len(source.encode()) > 256
        for source in sources
    ):
        raise HTTPException(status_code=400, detail="Invalid Source filter")
    if len(sources) > 100:
        raise HTTPException(status_code=400, detail="Too many Source filters")
    return sources


def _cursor_secret() -> bytes:
    secret = os.environ.get("SWE_AGENTOBS_CURSOR_SECRET", "")
    if len(secret.encode()) < 32:
        raise HTTPException(
            status_code=503,
            detail="Observability cursor key unavailable",
        )
    return secret.encode()


def _encode_cursor(
    last_started: datetime,
    run_id: str,
    scope: dict[str, Any],
) -> str:
    body = json.dumps(
        {
            "v": 1,
            "started_at": last_started.isoformat(),
            "run_id": run_id,
            "scope": scope,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_cursor_secret(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def _decode_cursor(
    cursor: str,
    expected_authority: dict[str, Any],
) -> tuple[datetime, str, dict[str, Any]]:
    try:
        packed = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body, signature = packed[:-32], packed[-32:]
        if not hmac.compare_digest(
            signature,
            hmac.new(_cursor_secret(), body, hashlib.sha256).digest(),
        ):
            raise ValueError("bad signature")
        payload = json.loads(body)
        scope = payload.get("scope")
        if payload.get("v") != 1 or not isinstance(scope, dict):
            raise ValueError("scope changed")
        if any(
            scope.get(key) != value
            for key, value in expected_authority.items()
        ):
            raise ValueError("authorization changed")
        started_at = datetime.fromisoformat(payload["started_at"])
        if started_at.tzinfo is not None:
            started_at = started_at.astimezone(timezone.utc).replace(
                tzinfo=None,
            )
        run_id = str(payload["run_id"])
        if len(run_id) != 36:
            raise ValueError("invalid run ID")
        return started_at, run_id, scope
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid run cursor",
        ) from exc


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    request: Request,
    source_id: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    cursor: str | None = Query(None, max_length=2048),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> RunListResponse:
    sources = _authorized_sources(request, source_id)
    _cursor_secret()
    authority = {
        "role": request.headers.get("X-User-Role", "").strip().lower(),
        "sources": sources,
    }
    decoded = _decode_cursor(cursor, authority) if cursor else None
    cursor_scope = decoded[2] if decoded else {}
    start_at = start or (
        datetime.fromisoformat(cursor_scope["start"])
        if cursor_scope
        else datetime.now(timezone.utc) - timedelta(hours=24)
    )
    end_at = end or (
        datetime.fromisoformat(cursor_scope["end"])
        if cursor_scope
        else datetime.now(timezone.utc)
    )
    if decoded:
        if start and start.isoformat() != cursor_scope.get("start"):
            raise HTTPException(
                status_code=400,
                detail="Run cursor filter changed",
            )
        if end and end.isoformat() != cursor_scope.get("end"):
            raise HTTPException(
                status_code=400,
                detail="Run cursor filter changed",
            )
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="Time filters must include a timezone",
        )
    if end_at <= start_at or end_at - start_at > _MAX_WINDOW:
        raise HTTPException(
            status_code=400,
            detail="Invalid run-list time window",
        )
    scope = {
        **authority,
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
    }
    before = decoded[:2] if decoded else None
    store = getattr(request.app.state, "agent_observability_store", None)
    if not isinstance(store, ObservabilityStore):
        raise HTTPException(
            status_code=503,
            detail="Agent observability storage unavailable",
        )
    try:
        rows = await store.list_runs(
            service_unit_id=os.environ.get("SWE_SERVICE_UNIT_ID", "swe"),
            source_ids=sources,
            limit=limit + 1,
            before=before,
            start_at=start_at,
            end_at=end_at,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent observability query unavailable",
        ) from exc
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(
            last["started_at"],
            str(last["run_id"]),
            scope,
        )
    items = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            elif isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            item[key] = value
        items.append(item)
    return RunListResponse(
        items=items,
        next_cursor=next_cursor,
        generated_at=datetime.now(timezone.utc),
        window_start=start_at,
        window_end=end_at,
    )


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            elif isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            item[key] = value
        result.append(item)
    return result


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def run_detail(
    run_id: str,
    request: Request,
    attempt_id: str | None = Query(None),
    span_limit: int = Query(200, ge=1, le=500),
    span_cursor: str | None = Query(None, max_length=2048),
) -> RunDetailResponse:
    role = _require_observability_reader(request)
    try:
        UUID(run_id)
        if attempt_id is not None:
            UUID(attempt_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid run identity",
        ) from exc
    sources = _authorized_sources(request, None)
    authority = {
        "role": role,
        "sources": sources,
        "run_id": run_id,
        "attempt_id": attempt_id,
    }
    decoded = _decode_cursor(span_cursor, authority) if span_cursor else None
    store = getattr(request.app.state, "agent_observability_store", None)
    if not isinstance(store, ObservabilityStore):
        raise HTTPException(
            status_code=503,
            detail="Agent observability storage unavailable",
        )
    try:
        row = await store.get_run(
            service_unit_id=os.environ.get("SWE_SERVICE_UNIT_ID", "swe"),
            run_id=run_id,
            source_ids=sources,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        attempts = await store.list_attempts(run_id=run_id)
        spans = await store.list_spans(
            run_id=run_id,
            attempt_id=attempt_id,
            limit=span_limit + 1,
            after=decoded[:2] if decoded else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent observability query unavailable",
        ) from exc
    span_rows = _serialize_rows(spans[:span_limit])
    has_more = len(spans) > span_limit
    next_cursor = None
    if has_more and span_rows:
        last = span_rows[-1]
        next_cursor = _encode_cursor(
            last["started_at"],
            str(last["span_id"]),
            authority,
        )
    return RunDetailResponse(
        run=_serialize_rows([row])[0],
        attempts=_serialize_rows(attempts),
        spans=span_rows,
        generated_at=datetime.now(timezone.utc),
        spans_has_more=has_more,
        spans_next_cursor=next_cursor,
    )


@router.get("/runs/{run_id}/events", response_model=EventListResponse)
async def run_events(
    run_id: str,
    request: Request,
    span_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=_MAX_EVENT_PAGE_SIZE),
    cursor: str | None = Query(None, max_length=2048),
) -> EventListResponse:
    role = _require_observability_reader(request)
    try:
        UUID(run_id)
        if span_id is not None:
            UUID(span_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid event identity",
        ) from exc
    sources = _authorized_sources(request, None)
    authority = {
        "role": role,
        "sources": sources,
        "run_id": run_id,
        "span_id": span_id,
    }
    decoded = _decode_cursor(cursor, authority) if cursor else None
    store = getattr(request.app.state, "agent_observability_store", None)
    if not isinstance(store, ObservabilityStore):
        raise HTTPException(
            status_code=503,
            detail="Agent observability storage unavailable",
        )
    try:
        run = await store.get_run(
            service_unit_id=os.environ.get("SWE_SERVICE_UNIT_ID", "swe"),
            run_id=run_id,
            source_ids=sources,
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        rows = await store.list_events(
            run_id=run_id,
            source_ids=sources,
            span_id=span_id,
            before=decoded[:2] if decoded else None,
            limit=limit + 1,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent observability query unavailable",
        ) from exc

    serialized = _serialize_rows(rows)
    items: list[dict[str, Any]] = []
    for row in serialized[:limit]:
        try:
            metadata = json.loads(row.pop("metadata_text"))
        except (json.JSONDecodeError, TypeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Agent observability event unavailable",
            ) from exc
        if not isinstance(metadata, dict):
            raise HTTPException(
                status_code=503,
                detail="Agent observability event unavailable",
            )
        candidate = {**row, "metadata": metadata}
        projected = json.dumps(
            [*items, candidate],
            ensure_ascii=False,
            separators=(",", ":"),
            default=lambda value: (
                value.isoformat()
                if isinstance(value, datetime)
                else str(value)
            ),
        ).encode("utf-8")
        if len(projected) > _MAX_EVENT_RESPONSE_BYTES:
            break
        items.append(candidate)

    has_more = len(serialized) > len(items)
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(
            last["occurred_at"],
            str(last["event_id"]),
            authority,
        )
    return EventListResponse(
        items=items,
        next_cursor=next_cursor,
        generated_at=datetime.now(timezone.utc),
    )
