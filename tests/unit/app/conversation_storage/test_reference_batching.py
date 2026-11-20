# -*- coding: utf-8 -*-
"""Cold Turn reference and direct NAS body locator validation."""

import pytest

from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.projection_references import (
    ProjectionReferences,
    TURN_FIELDS,
    _resolve_payload,
)
from tests.unit.app.conversation_storage.test_reference_queries import (
    ReferenceDatabase,
    SERVICE,
)


def turn_row(identity=3):
    return {
        "id": identity,
        "service_unit_key": SERVICE,
        "session_id": 1,
        "chat_id": 2,
        "terminal_publication_id": 1,
        "history_status": "completed",
        "question_msg_key": b"q",
    }


@pytest.mark.parametrize("field", TURN_FIELDS)
async def test_turn_revalidation_keeps_original_fields_and_ordinary_read(
    field,
):
    expected = turn_row()
    db = ReferenceDatabase(
        turns={
            3: {
                **expected,
                field: (
                    b"changed" if isinstance(expected[field], bytes) else 999
                ),
            },
        },
    )
    with pytest.raises(IntegrityError):
        await ProjectionReferences(turns={3: expected}).revalidate(db)
    assert "FOR SHARE" not in db.calls[0][0]
    assert "FOR UPDATE" not in db.calls[0][0]


def test_direct_locator_positions_keep_duplicate_message_ids():
    bodies = [
        {"id": "q", "content": "first"},
        {"id": "q", "content": "second"},
    ]
    assert _resolve_payload(bodies, {"position": 0}, {}) == bodies[0]
    assert _resolve_payload(bodies, {"position": 1}, {}) == bodies[1]
    with pytest.raises(IntegrityError, match="position"):
        _resolve_payload(bodies, {"position": 2}, {})
