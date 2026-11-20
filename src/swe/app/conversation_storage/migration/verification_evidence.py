# -*- coding: utf-8 -*-
"""Keep fast publication checks and full audits as separate evidence."""

import json


def merge_verification(existing, result):
    current = (
        json.loads(existing or "{}")
        if isinstance(existing, str) or existing is None
        else existing
    )
    if not isinstance(current, dict):
        raise ValueError("invalid migration verification evidence")
    level = result.get("verification_level")
    if level not in ("fast", "full") or type(result.get("passed")) is not bool:
        raise ValueError("invalid verification result")
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
            "blockers",
        )
        if key in result
    }
    if isinstance(result.get("checked"), list):
        summary["checked_count"] = len(result["checked"])
    reports[level] = summary
    current["verification_results"] = reports
    if reports.get("fast", {}).get("passed") is True:
        current["verification_level"] = "fast"
    elif result["passed"]:
        current["verification_level"] = level
    return current
