"""Atlas Conversation — Development Need Coordinator (P7.4).

Small conversation-local coordinator that connects the P7.2 detector and P7.3
dialogue to the EXISTING explicit development route. It owns only the minimal
pending-confirmation state needed to carry a detection through explanation →
explicit confirmation → confirmed intent hand-off.

This module does NOT import evolution execution machinery. It produces a
``DEVELOPMENT_REQUEST`` :class:`TaskSpec` (via the pure P7.4 router) that the
``ConversationService`` routes through its already-injected
``development_bridge`` — the same seam used by explicit development requests.

Design contract:
  * Conversation-local: imports only conversation-owned modules. No kernel,
    no runtime, no storage, no AI, no evolution/orchestration/advisory
    execution, no approval, no execution.
  * Fail-closed: a pending confirmation is bound to a specific session +
    principal; a mismatched or missing context never confirms, never clears,
    and never develops anything.
  * Minimal state: a single pending-confirmation slot (replaced on each new
    detection). No persistence, no workflow engine, no history framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.conversation.development_need_detector import (
    DetectedDevelopmentNeed,
    DevelopmentNeedDetector,
)
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
)
from atlas.conversation.development_need_router import explicit_intent_to_task_spec
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskSpec


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    """Minimal pending-confirmation context bound to one session/principal."""

    need: DetectedDevelopmentNeed
    session_id: str = ""
    principal_id: str = ""
    authority: str = ""


class DevelopmentNeedCoordinator:
    """Coordinates detection → explanation → confirmation → intent hand-off.

    Stateless apart from the single pending-confirmation slot. All detection
    and dialogue semantics live in the pure P7.2/P7.3 modules; this module only
    sequences them and retains the minimal conversational state.
    """

    def __init__(
        self,
        detector: DevelopmentNeedDetector | None = None,
        dialogue: DevelopmentNeedDialogue | None = None,
    ) -> None:
        self._detector = detector or DevelopmentNeedDetector()
        self._dialogue = dialogue or DevelopmentNeedDialogue()
        self._pending: PendingConfirmation | None = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_unresolved_action(
        self,
        spec: TaskSpec,
        *,
        missing_capability: str = "",
    ) -> Message | None:
        """Detect a capability gap / unresolved action for a well-specified
        ACTION request whose target could not be resolved.

        Returns an explanation :class:`Message` (which also records the
        pending-confirmation context) when a genuine deterministic signal is
        found, else ``None`` (no detection, no state change).
        """
        detected = self._detector.detect(
            spec,
            resolution=False,
            missing_capability=missing_capability,
        )
        if detected is None:
            return None

        self._pending = PendingConfirmation(
            need=detected,
            session_id=detected.session_id,
            principal_id=detected.principal_id,
            authority=detected.authority,
        )
        return self._dialogue.explain(detected)

    # ------------------------------------------------------------------
    # Advisory input (P7.7)
    # ------------------------------------------------------------------

    def advisory_input(self, advisory, session_context=None) -> Message | None:
        """Feed a bounded advisory signal into the detector (P7.7).

        If the signal detects an advisory improvement opportunity, establish a
        pending confirmation bound to the AUTHORITATIVE session context and
        return the explanation. Otherwise return ``None`` (no detection, no
        state change).

        Advisory alone never invokes the development bridge. The pending
        confirmation (if any) is bound to the passed-in session context so that
        only an explicit human confirmation in that session can continue — the
        advisory's own provenance is preserved on the detected need but never
        overrides authoritative identity/authority (P7.6).
        """
        detected = self._detector.detect(None, advisory=advisory)
        if detected is None:
            return None
        # The detected need carries the advisory signal's own provenance
        # (principal_id/authority/session_id). That provenance must NEVER
        # override authoritative identity (P7.6): the acting principal, authority
        # and session come from the authoritative session context, not from
        # advisory content. A USER must never be elevated to OWNER because an
        # advisory recommends something. Rebuild the need so the authoritative
        # session identity flows into the later intent/TaskSpec while the
        # advisory's signal/reason/evidence/capability are preserved.
        if session_context is not None:
            authority = session_context.authority
            authority = authority.value if hasattr(authority, "value") else str(authority)
            detected = DetectedDevelopmentNeed(
                signal_kind=detected.signal_kind,
                reason=detected.reason,
                evidence=detected.evidence,
                capability=detected.capability,
                principal_id=session_context.principal_id,
                authority=authority,
                session_id=session_context.session_id,
            )
            session_id = session_context.session_id
            principal_id = session_context.principal_id
        else:
            session_id = detected.session_id
            principal_id = detected.principal_id
        self._pending = PendingConfirmation(
            need=detected,
            session_id=session_id,
            principal_id=principal_id,
            authority=detected.authority,
        )
        return self._dialogue.explain(detected)

    # ------------------------------------------------------------------
    # Confirmation handling
    # ------------------------------------------------------------------

    def handle_reply(
        self,
        text: str,
        session_context: Any | None = None,
    ) -> Message | TaskSpec | None:
        """Interpret a user reply against the pending confirmation.

        Returns:
          * ``None`` — no pending confirmation, or the reply's session /
            principal does not match the pending context (fail-closed; the
            caller treats the message as ordinary input).
          * :class:`Message` — a conversational response (denial or re-ask).
          * :class:`TaskSpec` — a CONFIRMED ``DEVELOPMENT_REQUEST`` to be
            routed by the caller through its existing development bridge.
        """
        if self._pending is None:
            return None

        if not self._matches_session(session_context):
            return None

        status = self._dialogue.interpret_confirmation(text, self._pending.need)
        if status is ConfirmationStatus.DENIED:
            self._pending = None
            return self._dialogue.denied_response()
        if status is ConfirmationStatus.AMBIGUOUS:
            return self._dialogue.clarification_response()
        if status is ConfirmationStatus.NO_PENDING_CONTEXT:
            return None

        # CONFIRMED: hand off the explicit intent as a development request
        # TaskSpec. The caller routes it through the existing development
        # bridge (never directly to F9 from here).
        confirmed_need = self._pending.need
        self._pending = None
        intent = self._dialogue.build_intent(confirmed_need)
        return explicit_intent_to_task_spec(intent)

    # ------------------------------------------------------------------
    # Matching (fail-closed)
    # ------------------------------------------------------------------

    def _matches_session(self, session_context: Any | None) -> bool:
        if session_context is None:
            return False
        session_id = getattr(session_context, "session_id", "")
        principal_id = getattr(session_context, "principal_id", "")
        if not session_id or not self._pending.session_id:
            return False
        if session_id != self._pending.session_id:
            return False
        if self._pending.principal_id and principal_id != self._pending.principal_id:
            return False
        return True
