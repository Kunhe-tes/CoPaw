# -*- coding: utf-8 -*-
"""Completion Judge protocol tests."""

from swe.app.goals.review import parse_completion_review


def test_parse_completion_review_returns_acceptance_and_evidence() -> None:
    parsed = parse_completion_review(
        (
            '{"reviews":[{"criterion_id":"criterion-1",'
            '"decision":"accept","reason":"Observed output",'
            '"evidence_refs":["tool-1"]}]}'
        ),
        {"criterion-1"},
    )

    assert parsed == {"criterion-1": (True, "tool-1")}


def test_parse_completion_review_rejects_all_criteria_on_invalid_output() -> None:
    requested = {"criterion-1", "criterion-2"}

    parsed = parse_completion_review("not json", requested)

    assert parsed == {
        "criterion-1": (False, "completion review output is malformed"),
        "criterion-2": (False, "completion review output is malformed"),
    }


def test_parse_completion_review_rejects_all_on_duplicate_unknown_or_missing_ids() -> None:
    requested = {"criterion-1", "criterion-2"}
    payload = (
        '{"reviews":['
        '{"criterion_id":"criterion-1","decision":"accept",'
        '"reason":"done","evidence_refs":[]},'
        '{"criterion_id":"criterion-1","decision":"reject",'
        '"reason":"duplicate","evidence_refs":[]},'
        '{"criterion_id":"unknown","decision":"accept",'
        '"reason":"unknown","evidence_refs":[]}'
        ']}'
    )

    parsed = parse_completion_review(payload, requested)

    assert parsed == {
        "criterion-1": (False, "completion review output does not match criteria"),
        "criterion-2": (False, "completion review output does not match criteria"),
    }
