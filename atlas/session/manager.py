"""Atlas Session — SessionManager (P1/B1.2).

In-memory registry for Session objects. Validates every session against a
live AuthorityService so unknown/invalid principals fail closed and session
attribution is deterministic.

No persistence, no schema change, no authentication.
"""

from __future__ import annotations

from datetime import datetime, timezone

from atlas.authority.service import AuthorityService
from atlas.session.models import Session, new_session_id


class SessionManager:
    """In-memory session registry bound to one AuthorityService.

    Each session is immutable and permanently attributed to the Principal it
    was created with; there is no principal reassignment.

    Args:
        authority_service: The live AuthorityService that validates principals.
            Must be non-None; sessions are always created through it.
    """

    def __init__(self, authority_service: AuthorityService) -> None:
        if authority_service is None or not isinstance(authority_service, AuthorityService):
            raise ValueError("authority_service must be a valid AuthorityService (fail-closed)")
        self._authority = authority_service
        self._sessions: dict[str, Session] = {}

    def create_session(self, principal_id: str) -> Session:
        """Create a new session for ``principal_id``.

        Fails closed when the principal is unknown or invalid (no session
        is created, no side effects).

        Args:
            principal_id: Stable principal id resolved through AuthorityService.

        Returns:
            A new immutable Session.

        Raises:
            ValueError: when ``principal_id`` is empty.
            PermissionError: when the principal is unknown (fail-closed).
        """
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id must be a non-empty string (fail-closed)")
        principal = self._authority.resolve(principal_id.strip())
        if principal is None:
            raise PermissionError(f"unknown principal '{principal_id.strip()}' (fail-closed)")
        session = Session(
            session_id=new_session_id(),
            principal=principal,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """Return the session for ``session_id``, or None when unknown."""
        if not isinstance(session_id, str):
            return None
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        """Return the session or raise PermissionError (fail-closed)."""
        session = self.get(session_id)
        if session is None:
            raise PermissionError(f"unknown session '{session_id}' (fail-closed)")
        return session

    def is_valid(self, session_id: str) -> bool:
        return session_id in self._sessions

    def count(self) -> int:
        return len(self._sessions)

    def sessions_for_principal(self, principal_id: str) -> list[Session]:
        return [s for s in self._sessions.values() if s.principal_id == principal_id]

    def all_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def clear(self) -> None:
        self._sessions.clear()
