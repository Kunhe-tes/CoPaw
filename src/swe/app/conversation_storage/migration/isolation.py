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


async def iter_states(states, keys, *, table, fields):
    """Read advisory states in bounded groups; transitions still lock SQL rows."""
    from itertools import islice

    iterator = iter(keys)
    while chunk := list(islice(iterator, 256)):
        encoded = [states._keys(*key)[1:] for key in chunk]
        placeholders = ",".join(
            ["(" + ",".join(["%s"] * len(fields)) + ")"] * len(chunk),
        )
        rows = await states.db.fetch_all(
            "SELECT "
            + ",".join(fields)
            + ",state FROM "
            + table
            + " WHERE migration_id=%s AND ("
            + ",".join(fields)
            + ") IN ("
            + placeholders
            + ")",
            (
                states.migration_id,
                *(value for key in encoded for value in key),
            ),
        )
        found = {
            tuple(
                (
                    row[field].decode()
                    if isinstance(row[field], bytes)
                    else row[field]
                )
                for field in fields
            ): row
            for row in rows
        }
        for key in chunk:
            yield key, found.get(key)
