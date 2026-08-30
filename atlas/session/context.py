"""Atlas Session — SessionContext envelope (P1/B1.2).

Single immutable attribution envelope propagated through the conversational
context path instead of duplicating the full Session into every subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.authority.models import AuthorityContext, AuthorityLevel, Principal
from atlas.session.models import Session


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Immutable per-interaction attribution envelope.

    Carries the session + principal attribution for one conversational turn.
    Subsystems consume this envelope rather than re-deriving identity.

    Attributes:
        session: The immutable Session for this interaction.
        principal: Derived from session.principal (kept explicit for call sites).
        action: Optional action label (e.g. "send", "context.build").
    """

    session: Session
    action: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.session, Session):
            raise ValueError("session must be a valid Session (fail-closed)")

    @property
    def principal(self) -> Principal:
        return self.session.principal

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def principal_id(self) -> str:
        return self.session.principal_id

    @property
    def authority(self) -> AuthorityLevel:
        return self.session.authority

    @property
    def is_owner(self) -> bool:
        return self.session.is_owner

    def authority_context(self, action: str | None = None) -> AuthorityContext:
        return AuthorityContext(
            principal=self.principal,
            action=action if action is not None else self.action,
        )

    def satisfies(self, required: AuthorityLevel) -> bool:
        return self.principal.authority >= required

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "authority": self.authority.value,
            "action": self.action,
            "created_at": self.session.created_at.isoformat(),
        }

    @staticmethod
    def from_session(session: Session, action: str = "") -> "SessionContext":
        return SessionContext(session=session, action=action)
