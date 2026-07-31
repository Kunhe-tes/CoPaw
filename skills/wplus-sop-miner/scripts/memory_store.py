#!/usr/bin/env python3
"""Append an explicitly approved, sanitized W+ memory candidate to JSONL."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from privacy import sensitive_key_findings, sensitive_value_findings


ALLOWED_TYPES = {"common_wplus_knowledge", "user_wplus_usage", "sop_case"}


def _fingerprint(candidate: dict[str, Any]) -> str:
    comparable = {"type": candidate.get("type"), "content": candidate.get("content")}
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_candidate(candidate: Any) -> list[str]:
    if not isinstance(candidate, dict):
        return ["memory candidate must be an object"]
    errors = []
    if candidate.get("type") not in ALLOWED_TYPES:
        errors.append("invalid memory candidate type")
    if not isinstance(candidate.get("content"), dict) or not candidate["content"]:
        errors.append("memory candidate content must be a non-empty object")
    if not isinstance(candidate.get("evidence"), str) or not candidate["evidence"].strip():
        errors.append("memory candidate requires evidence")
    errors.extend(sensitive_key_findings(candidate.get("content"), "$.content"))
    errors.extend(sensitive_value_findings(candidate))
    return errors


def append_memory(path: Path | str, candidate: dict[str, Any], approved: bool) -> str:
    if not approved:
        raise PermissionError("memory write requires explicit user approval")
    errors = validate_candidate(candidate)
    if errors:
        raise ValueError("; ".join(errors))

    target = Path(path)
    fingerprint = _fingerprint(candidate)
    if target.exists():
        for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}") from error
            if _fingerprint(existing) == fingerprint:
                return "duplicate"

    target.parent.mkdir(parents=True, exist_ok=True)
    record = dict(candidate)
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return "appended"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memory_file", type=Path)
    parser.add_argument("candidate_file", type=Path)
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    with args.candidate_file.open("r", encoding="utf-8") as handle:
        candidate = json.load(handle)
    try:
        result = append_memory(args.memory_file, candidate, approved=args.approved)
    except (PermissionError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
