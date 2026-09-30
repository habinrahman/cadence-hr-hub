"""Who is allowed to act. Agents are never users."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    kind: str
    user_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"user", "agent", "system"}:
            raise ValueError("actor kind must be user, agent, or system")
        if self.kind == "user" and self.user_id is None:
            raise ValueError("a user actor needs a user id")
        if self.kind != "user" and self.user_id is not None:
            raise ValueError("only a user actor carries a user id")


SYSTEM = Actor(kind="system")
AGENT = Actor(kind="agent")
