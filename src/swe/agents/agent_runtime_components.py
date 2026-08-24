# -*- coding: utf-8 -*-
"""Small contracts for the dependencies installed on a :class:`SWEAgent`."""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AgentRequestContext:
    """Typed view of the legacy request-context dictionary.

    The fixed names deliberately retain their legacy spelling because the
    request context crosses several compatibility boundaries.
    """

    session_id: str | None = None
    user_id: str | None = None
    channel: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    chat_id: str | None = None
    turn_id: str | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    _FIXED_KEYS = (
        "session_id",
        "user_id",
        "channel",
        "agent_id",
        "tenant_id",
        "chat_id",
        "turn_id",
    )

    @classmethod
    def from_legacy_dict(
        cls,
        context: Mapping[str, Any] | None,
    ) -> "AgentRequestContext":
        values = dict(context or {})
        return cls(
            **{key: values.pop(key, None) for key in cls._FIXED_KEYS},
            extras=values,
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        result = {
            key: value
            for key, value in self.extras.items()
            if key not in self._FIXED_KEYS
        }
        result.update(
            {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "channel": self.channel,
                "agent_id": self.agent_id,
                "tenant_id": self.tenant_id,
                "chat_id": self.chat_id,
                "turn_id": self.turn_id,
            },
        )
        return {
            key: value for key, value in result.items() if value is not None
        }


@dataclass(frozen=True)
class AgentRuntimeComponents:
    """The collaborators required by ``ReActAgent.__init__``."""

    toolkit: Any
    system_prompt: str
    model: Any
    formatter: Any
    memory: Any
