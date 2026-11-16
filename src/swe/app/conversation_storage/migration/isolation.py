# -*- coding: utf-8 -*-
"""Explicit publication units; old tenant jobs retain their boundary."""


def unit_key(data, item):
    key = item["service_unit_id"], item["tenant_id"]
    if data.get("source_isolation"):
        return (*key, item["source_id"])
    return key


def belongs(item, key):
    fields = ("service_unit_id", "tenant_id", "source_id")[: len(key)]
    return tuple(item.get(field) for field in fields) == tuple(key)


def state_store(database, manifest):
    from .tenant_state import TenantState
    from .source_state import SourceState

    cls = SourceState if manifest.data.get("source_isolation") else TenantState
    return cls(database, manifest.migration_id)
