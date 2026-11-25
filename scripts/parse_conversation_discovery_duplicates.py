# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Explain duplicate workspace blockers in a discovery JSON report."""

import argparse
from collections import defaultdict
import json
from pathlib import Path


def _compact(item):
    fields = (
        "position",
        "root",
        "runtime_root",
        "service_unit_id",
        "tenant_id",
        "source_id",
        "agent_id",
        "evidence_refs",
    )
    return {key: item[key] for key in fields if key in item}


def _duplicates(workspaces, key):
    grouped = defaultdict(list)
    for item in workspaces:
        grouped[tuple(item.get(field) for field in key)].append(item)
    return [items for items in grouped.values() if len(items) > 1]


def parse(report):
    workspaces = report.get("workspaces", [])
    blockers = [
        item
        for item in report.get("blockers", [])
        if item.get("code") == "duplicate_workspace"
    ]
    root_groups = _duplicates(workspaces, ("root",))
    scope_groups = _duplicates(
        workspaces,
        ("service_unit_id", "tenant_id", "source_id", "agent_id"),
    )
    by_position = {item.get("position"): item for item in workspaces}
    details = []
    for blocker in blockers:
        workspace = by_position.get(blocker.get("position"))
        details.append(
            {
                "blocker": blocker,
                "workspace": _compact(workspace) if workspace else None,
                "same_root": [
                    _compact(item)
                    for group in root_groups
                    for item in group
                    if workspace and item.get("root") == workspace.get("root")
                ],
                "same_scope": [
                    _compact(item)
                    for group in scope_groups
                    for item in group
                    if workspace
                    and all(
                        item.get(field) == workspace.get(field)
                        for field in (
                            "service_unit_id",
                            "tenant_id",
                            "source_id",
                            "agent_id",
                        )
                    )
                ],
            },
        )
    return {
        "report_status": report.get("status"),
        "duplicate_blockers": len(blockers),
        "duplicate_root_groups": [
            [_compact(item) for item in group] for group in root_groups
        ],
        "duplicate_scope_groups": [
            [_compact(item) for item in group] for group in scope_groups
        ],
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse duplicate_workspace blockers from discovery JSON",
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with args.report.open(encoding="utf-8") as stream:
        result = parse(json.load(stream))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is None:
        print(encoded)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
