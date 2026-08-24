# -*- coding: utf-8 -*-
"""Provider management — models, registry + persistent store."""

from __future__ import annotations

__all__ = [
    "ActiveModelsInfo",
    "ModelInfo",
    "Provider",
    "ProviderCatalogService",
    "ProviderManager",
    "ProviderInfo",
]


def __getattr__(name: str):
    if name in {
        "ProviderManager",
        "ActiveModelsInfo",
    }:
        from .provider_manager import (
            ActiveModelsInfo as _ActiveModelsInfo,
            ProviderManager as _ProviderManager,
        )

        exports = {
            "ProviderManager": _ProviderManager,
            "ActiveModelsInfo": _ActiveModelsInfo,
        }
        return exports[name]
    if name == "ProviderCatalogService":
        from .provider_catalog_service import (
            ProviderCatalogService as _ProviderCatalogService,
        )

        return _ProviderCatalogService
    if name in {"ModelInfo", "Provider", "ProviderInfo"}:
        from .provider import (
            ModelInfo as _ModelInfo,
            Provider as _Provider,
            ProviderInfo as _ProviderInfo,
        )

        exports = {
            "ModelInfo": _ModelInfo,
            "Provider": _Provider,
            "ProviderInfo": _ProviderInfo,
        }
        return exports[name]
    raise AttributeError(name)
