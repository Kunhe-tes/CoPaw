# -*- coding: utf-8 -*-
"""Keep fast publication checks and full audits as separate evidence."""

import json


def merge_verification(existing, result):
    current = (
        json.loads(existing or "{}") if isinstance(existing, str) else existing
    )
    if not isinstance(current, dict):
        raise ValueError("invalid migration verification evidence")
    level = result.get("verification_level")
    if level not in ("fast", "full") or result.get("passed") is not True:
        raise ValueError("only a passed verification can be recorded")
    reports = current.get("verification_results", {})
    if not isinstance(reports, dict):
        raise ValueError("invalid migration verification results")
    reports = dict(reports)
    summary = {
        key: result[key]
        for key in (
            "passed",
            "verification_level",
            "fast_summary",
        )
        if key in result
    }
    if isinstance(result.get("checked"), list):
        summary["checked_count"] = len(result["checked"])
    reports[level] = summary
    current["verification_results"] = reports
    current["verification_level"] = (
        "fast" if reports.get("fast", {}).get("passed") is True else level
    )
    return current
