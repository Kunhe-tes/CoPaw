# -*- coding: utf-8 -*-
"""Explicitly attributable tenant input failures, never SQL authority errors."""


class TenantInputError(ValueError):
    """One tenant's frozen input cannot be imported."""


class SourceChanged(TenantInputError):
    """One tenant's input changed after its accepted evidence boundary."""
