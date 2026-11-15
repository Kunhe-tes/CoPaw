# -*- coding: utf-8 -*-
"""Configuration for the independent metadata event emitter."""

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def capture_enabled() -> bool:
    return os.environ.get("SWE_AGENTOBS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class EmitterConfig:
    max_event_bytes: int = 24 * 1024
    max_queue_events: int = 4096
    max_queue_bytes: int = 8 * 1024 * 1024
    shutdown_timeout: float = 1.0

    @classmethod
    def from_environment(cls) -> "EmitterConfig":
        return cls(
            max_event_bytes=_positive_int(
                "SWE_AGENTOBS_MAX_EVENT_BYTES",
                24 * 1024,
            ),
            max_queue_events=_positive_int("SWE_AGENTOBS_QUEUE_EVENTS", 4096),
            max_queue_bytes=_positive_int(
                "SWE_AGENTOBS_QUEUE_BYTES",
                8 * 1024 * 1024,
            ),
        )

    def __post_init__(self) -> None:
        if (
            min(
                self.max_event_bytes,
                self.max_queue_events,
                self.max_queue_bytes,
            )
            <= 0
        ):
            raise ValueError("emitter limits must be positive")
        object.__setattr__(
            self,
            "shutdown_timeout",
            min(1.0, max(0.0, self.shutdown_timeout)),
        )
