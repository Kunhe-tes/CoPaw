# -*- coding: utf-8 -*-
import json

from swe.app.conversation_storage.migration.verification_evidence import (
    merge_verification,
)


def test_fast_and_full_verification_results_remain_independent():
    fast = {
        "passed": True,
        "verification_level": "fast",
        "fast_summary": {"publications": 2},
    }
    full = {
        "passed": True,
        "verification_level": "full",
        "checked": ["messages", "archives"],
    }

    evidence = merge_verification("{}", fast)
    evidence = merge_verification(evidence, full)
    evidence = merge_verification(evidence, fast)

    assert evidence["verification_level"] == "fast"
    assert evidence["verification_results"]["fast"]["fast_summary"] == {
        "publications": 2,
    }
    assert evidence["verification_results"]["full"]["checked_count"] == 2
    assert json.loads(json.dumps(evidence)) == evidence
