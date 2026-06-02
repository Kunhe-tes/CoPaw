# -*- coding: utf-8 -*-
"""Shared helpers for canonical runtime scope conversion."""

from __future__ import annotations

from dataclasses import dataclass

from .context import decode_scope_id, encode_scope_id, is_valid_identity_value


@dataclass(frozen=True)
class EncodedScope:
    """Canonical scope encoding result."""

    tenant_id: str
    source_id: str
    scope_id: str


@dataclass(frozen=True)
class DecodedScope:
    """Canonical scope decoding result."""

    scope_id: str
    tenant_id: str
    source_id: str


def encode_canonical_scope_id(
    tenant_id: str,
    source_id: str,
) -> EncodedScope:
    """Encode logical tenant/source identifiers into a canonical scope ID."""
    if not is_valid_identity_value(tenant_id):
        raise ValueError("Invalid tenant_id")
    if not is_valid_identity_value(source_id):
        raise ValueError("Invalid source_id")
    return EncodedScope(
        tenant_id=tenant_id,
        source_id=source_id,
        scope_id=encode_scope_id(tenant_id, source_id),
    )


def decode_canonical_scope_id(scope_id: str) -> DecodedScope:
    """Decode canonical scope IDs and reject legacy-prefixed values."""
    normalized_scope_id = scope_id.strip()
    if not normalized_scope_id:
        raise ValueError("Invalid scope_id")
    if normalized_scope_id.startswith("scope.v1."):
        raise ValueError("Legacy scope IDs are not supported")
    tenant_id, source_id = decode_scope_id(normalized_scope_id)
    return DecodedScope(
        scope_id=normalized_scope_id,
        tenant_id=tenant_id,
        source_id=source_id,
    )
