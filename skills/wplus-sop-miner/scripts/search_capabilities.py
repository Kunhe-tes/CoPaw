#!/usr/bin/env python3
"""Search the sanitized W+ capability registry without contacting W+."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "references" / "capability-registry.json"


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        registry = json.load(handle)
    if registry.get("schema_version") != "1.0":
        raise ValueError("Unsupported capability registry schema_version")
    if not isinstance(registry.get("capabilities"), list):
        raise ValueError("Capability registry must contain a capabilities array")
    return registry


def _normalize(text: str) -> str:
    return re.sub(r"[\s_\-/]+", "", text.casefold())


def search_capabilities(
    registry: dict[str, Any], query: str, limit: int = 8
) -> list[dict[str, Any]]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return []

    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for capability in registry["capabilities"]:
        score = 0
        terms = list(capability.get("keywords", []))
        terms.extend([capability.get("name", ""), capability.get("business_area", "")])
        for term in terms:
            normalized_term = _normalize(str(term))
            if normalized_term and normalized_term in normalized_query:
                score += max(1, len(normalized_term))
        if score:
            ranked.append((score, capability["id"], capability))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Chinese or English work-description query")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    results = search_capabilities(load_registry(args.registry), args.query, args.limit)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
