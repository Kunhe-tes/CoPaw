# -*- coding: utf-8 -*-
"""Attribute legacy shares only from trusted workspace and Chat evidence."""

from pathlib import Path

from ..chat_mutations import load_metadata_json
from .source_inputs import safe_input_entries


def share_source(report, service, record):
    from .tenant_discovery import _source_configs
    from .in_place_review import frozen_share_source

    frozen = frozen_share_source(record["token"])
    if frozen is not None:
        return frozen
    candidates = {
        source
        for _path, tenant, source in _source_configs(service)
        if tenant == record["tenant_id"]
    }
    matches, checked, invalid = set(), set(), set()
    for workspace in report["workspaces"]:
        if (workspace["service_unit_id"], workspace["tenant_id"]) != (
            service["service_unit_id"],
            record["tenant_id"],
        ):
            continue
        source = workspace["source_id"]
        candidates.add(source)
        root = Path(workspace["root"])
        registry = workspace.get("registry_path", "chats.json")
        path = root / registry
        try:
            safe_input_entries(
                root,
                [registry],
                recursive=False,
                trusted_root=root,
                allow_in_root_symlinks=True,
            )
            if not path.exists():
                checked.add(source)
                continue
            chats = load_metadata_json(path.read_bytes())["chats"]
            if any(c["id"] == record["chat_id"] for c in chats):
                matches.add(source)
            checked.add(source)
        except (ValueError, TypeError, KeyError):
            invalid.add(source)
            continue
    if matches and ((candidates - checked) | invalid) - matches:
        raise ValueError("share source ownership is absent or ambiguous")
    owners = matches or candidates
    if len(owners) != 1:
        raise ValueError("share source ownership is absent or ambiguous")
    return owners.pop()
