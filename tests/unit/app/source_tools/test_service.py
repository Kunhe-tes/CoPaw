# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from swe.app.source_tools.service import (
    SourceToolConflict,
    SourceToolSafetyError,
    SourceToolService,
)
from swe.app.source_tools.store import SourceToolStore
from swe.app.source_tools.validation import SourceToolValidationError


def _script(name: str = "lookup_invoice") -> bytes:
    return f"""
TOOL_NAME = "{name}"
TOOL_DESCRIPTION = "Look up an invoice."
TOOL_JSON_SCHEMA = {{"type": "object", "properties": {{}}}}
REQUIRED_ENV = []

async def execute(arguments, context):
    return {{"ok": True}}
""".encode()


def _service(tmp_path: Path) -> SourceToolService:
    return SourceToolService(
        SourceToolStore(tmp_path),
        safety_scan=lambda _content, _name: True,
    )


def test_draft_publish_replacement_and_activation_history(tmp_path: Path):
    service = _service(tmp_path)
    draft = service.create_draft("source-a", _script(), actor="manager")

    assert draft.name == "lookup_invoice"
    assert draft.status == "draft"
    first = service.publish("source-a", draft.name, actor="manager")
    assert first.version == 1
    assert service.get_active_catalog("source-a")[0].version == 1

    replacement = service.create_draft(
        "source-a",
        _script().replace(b'"Look up an invoice."', b'"New description."'),
        actor="manager",
    )
    with pytest.raises(SourceToolConflict, match="confirmation"):
        service.publish("source-a", replacement.name, actor="manager")

    second = service.publish(
        "source-a",
        replacement.name,
        actor="manager",
        confirm_replace=True,
    )
    assert second.version == 2
    assert [
        record.version for record in service.history("source-a", draft.name)
    ] == [2, 1]

    service.deactivate("source-a", draft.name, actor="manager")
    assert service.get_active_catalog("source-a") == ()
    assert [event.event for event in service.audit("source-a")] == [
        "draft_created",
        "published",
        "draft_created",
        "published",
        "deactivated",
    ]


def test_only_one_unpublished_draft_per_source_and_tool(tmp_path: Path):
    service = _service(tmp_path)
    service.create_draft("source-a", _script(), actor="manager")

    with pytest.raises(SourceToolConflict, match="draft"):
        service.create_draft("source-a", _script(), actor="manager")

    service.create_draft(
        "source-a",
        _script(),
        actor="manager",
        replace_draft=True,
    )
    assert len(service.list_drafts("source-a")) == 1
    service.discard_draft("source-a", "lookup_invoice", actor="manager")
    assert service.list_drafts("source-a") == ()


def test_upload_fails_closed_when_scan_is_unavailable_or_unsafe(
    tmp_path: Path,
):
    unavailable = SourceToolService(
        SourceToolStore(tmp_path),
        safety_scan=lambda _content, _name: (_ for _ in ()).throw(
            RuntimeError(),
        ),
    )
    with pytest.raises(SourceToolSafetyError, match="unavailable"):
        unavailable.create_draft("source-a", _script(), actor="manager")

    unsafe = SourceToolService(
        SourceToolStore(tmp_path / "unsafe"),
        safety_scan=lambda _content, _name: False,
    )
    with pytest.raises(SourceToolSafetyError, match="unsafe"):
        unsafe.create_draft("source-a", _script(), actor="manager")


def test_uploaded_content_is_revalidated_and_not_exposed_in_metadata(
    tmp_path: Path,
):
    service = _service(tmp_path)
    with pytest.raises(SourceToolValidationError):
        service.create_draft("source-a", b"not python", actor="manager")

    draft = service.create_draft("source-a", _script(), actor="manager")
    service.publish("source-a", draft.name, actor="manager")
    metadata = service.list_metadata("source-a")
    assert metadata[0].content_digest == draft.content_digest
    assert not hasattr(metadata[0], "script")
    assert service.download_version("source-a", draft.name, 1) == _script()


def test_publish_rejects_builtin_override_with_mismatched_schema(
    tmp_path: Path,
):
    service = _service(tmp_path)
    draft = service.create_draft(
        "source-a",
        _script("execute_shell_command"),
        actor="manager",
    )

    with pytest.raises(SourceToolValidationError, match="schema"):
        service.publish("source-a", draft.name, actor="manager")

    assert service.get_active_catalog("source-a") == ()


def test_invocation_audit_excludes_arguments_and_credentials(tmp_path: Path):
    service = _service(tmp_path)
    draft = service.create_draft("source-a", _script(), actor="manager")
    published = service.publish("source-a", draft.name, actor="manager")

    service.record_invocation(
        source_id="source-a",
        tool=published,
        tenant_id="tenant-a",
        agent_id="agent-a",
        result="succeeded",
    )

    event = service.audit("source-a")[-1]
    assert event.event == "invoked"
    assert event.version == 1
    assert event.tenant_id == "tenant-a"
    assert event.result == "succeeded"
    assert "arguments" not in event.to_dict()


def test_manual_test_audit_keeps_only_execution_metadata(tmp_path: Path):
    service = _service(tmp_path)
    draft = service.create_draft("source-a", _script(), actor="manager")
    version = service.publish("source-a", draft.name, actor="manager")

    service.record_manual_test(
        source_id="source-a",
        tool=version,
        actor="manager",
        tenant_id="tenant-a",
        agent_id="agent-a",
        result="completed",
    )

    event = service.audit("source-a")[-1]
    assert event.event == "manual_test_completed"
    assert event.actor == "manager"
    assert event.tenant_id == "tenant-a"
    assert "script" not in event.to_dict()
