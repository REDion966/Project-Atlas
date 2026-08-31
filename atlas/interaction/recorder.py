"""Atlas Interaction — InteractionRecorder (P3/B3.1).

Builds provenance-carrying preference and correction records from a P1
SessionContext and stores them in an InteractionRepository. This is the
capture seam that Phase 3 interaction learning will consume.

Design contract:
  * Provenance is projected from the immutable SessionContext (session id,
    principal id, authority) — never from free text, never mutable.
  * Authority is the originating session's ``AuthorityLevel`` value
    (OWNER > USER). A User's correction is attributed to the User; it can
    never self-elevate.
  * All free-text fields are hard-bounded and control-character-stripped so
    user input can never produce oversized or injection-shaped state.
  * Fail-closed: missing/invalid session or empty principal produces None
    and stores nothing; never raises.
  * Deterministic record ids via a monotonic, seeded counter.

No infrastructure, no AI, no execution, no governance. Pure logic.
"""

from __future__ import annotations

from typing import Any

from atlas.interaction.models import (
    CorrectionRecord,
    PreferenceRecord,
    Provenance,
)
from atlas.interaction.repository import InteractionRepository

#: Bounded field limits (all derived text is hard-capped).
_MAX_KEY_CHARS: int = 200
_MAX_VALUE_CHARS: int = 1_000
_MAX_TARGET_CHARS: int = 200
_MAX_DESCRIPTION_CHARS: int = 2_000
_MAX_CORRECTION_CHARS: int = 2_000
_MAX_ACTION_CHARS: int = 120
_MAX_SOURCE_CHARS: int = 64

#: Control characters are stripped from derived text fields.
_CONTROL_CHARS: set[str] = {chr(i) for i in range(0x20)} | {chr(0x7F)}


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded, control-free string, or '' for non-strings."""
    if not isinstance(value, str):
        return ""
    stripped = "".join(ch for ch in value if ch not in _CONTROL_CHARS)
    return stripped.strip()[:limit]


def _provenance_from_session(session_context: Any, action: str, source: str) -> Provenance | None:
    """Project immutable provenance from a P1 SessionContext (or None).

    Accepts the SessionContext duck-typed so this pure module never imports
    the session package. Requires a non-empty principal_id and authority
    value; otherwise returns None (fail-closed).
    """
    if session_context is None:
        return None
    principal_id = getattr(session_context, "principal_id", None)
    if not isinstance(principal_id, str) or not principal_id.strip():
        return None
    authority = getattr(session_context, "authority", None)
    authority_value = getattr(authority, "value", None)
    if not isinstance(authority_value, str) or not authority_value.strip():
        return None
    session_id = getattr(session_context, "session_id", None)
    return Provenance(
        principal_id=principal_id.strip(),
        authority=authority_value.strip(),
        session_id=session_id.strip() if isinstance(session_id, str) else "",
        action=_bounded_text(action, _MAX_ACTION_CHARS),
        source=_bounded_text(source, _MAX_SOURCE_CHARS),
    )


class InteractionRecorder:
    """Records per-user preferences and corrections with provenance.

    Args:
        repository: The bounded store to write into (defaults to a fresh
            :class:`InteractionRepository`).
    """

    def __init__(self, repository: InteractionRepository | None = None) -> None:
        self._repository = repository or InteractionRepository()
        self._preference_counter = 0
        self._correction_counter = 0

    @property
    def repository(self) -> InteractionRepository:
        return self._repository

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def record_preference(
        self,
        session_context: Any,
        key: str,
        value: str,
        *,
        action: str = "record_preference",
        source: str = "interaction",
    ) -> PreferenceRecord | None:
        """Capture a per-user preference, or None (fail-closed).

        Args:
            session_context: The P1 attribution envelope (required).
            key: Bounded preference key.
            value: Bounded preference value.
            action: Optional action label for provenance.
            source: Optional provenance source.
        """
        provenance = _provenance_from_session(session_context, action, source)
        if provenance is None:
            return None
        bounded_key = _bounded_text(key, _MAX_KEY_CHARS)
        bounded_value = _bounded_text(value, _MAX_VALUE_CHARS)
        if not bounded_key or not bounded_value:
            return None
        self._preference_counter += 1
        record = PreferenceRecord(
            record_id=f"PREF-{self._preference_counter:08d}",
            principal_id=provenance.principal_id,
            key=bounded_key,
            value=bounded_value,
            provenance=provenance,
        )
        self._repository.store_preference(record)
        return record

    def record_correction(
        self,
        session_context: Any,
        target: str,
        description: str,
        correction: str,
        *,
        action: str = "record_correction",
        source: str = "interaction",
    ) -> CorrectionRecord | None:
        """Capture a per-user correction, or None (fail-closed).

        Args:
            session_context: The P1 attribution envelope (required).
            target: Bounded subject of the mistake.
            description: Bounded description of the observed mistake.
            correction: Bounded correction the user provided.
            action: Optional action label for provenance.
            source: Optional provenance source.
        """
        provenance = _provenance_from_session(session_context, action, source)
        if provenance is None:
            return None
        bounded_target = _bounded_text(target, _MAX_TARGET_CHARS)
        bounded_description = _bounded_text(description, _MAX_DESCRIPTION_CHARS)
        bounded_correction = _bounded_text(correction, _MAX_CORRECTION_CHARS)
        if not bounded_target or not bounded_correction:
            return None
        self._correction_counter += 1
        record = CorrectionRecord(
            record_id=f"CORR-{self._correction_counter:08d}",
            principal_id=provenance.principal_id,
            target=bounded_target,
            description=bounded_description,
            correction=bounded_correction,
            provenance=provenance,
        )
        self._repository.store_correction(record)
        return record

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def seed_counter(self, preference_n: int, correction_n: int) -> None:
        """Seed record counters (for future restore parity)."""
        self._preference_counter = max(0, preference_n)
        self._correction_counter = max(0, correction_n)
