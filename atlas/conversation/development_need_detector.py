"""Atlas Conversation — Development Need Detector (P7.2).

A pure, deterministic, side-effect-free conversation-layer detector that
reifies NON-explicit development/improvement signals as a small immutable
detection record. It is the DETECTION half of conversational self-development
— it never proposes, approves, executes, or promotes anything.

Explicit development requests deliberately return ``None`` here: they already
flow through the existing B3 intake (``task_spec_to_development_need``) into
the governed F9 pipeline. This detector only exists for signals that are NOT
already explicit development requests, for example:

  * a well-specified ACTION_REQUEST whose target could not be resolved to a
    registered capability (capability gap / unresolved action);
  * a repeated clarification loop caused by inability to satisfy a task;
  * a bounded advisory improvement opportunity.

Design contract:
  * Pure: imports only conversation-owned data types. No kernel, no runtime,
    no storage, no EventBus, no AI, no evolution execution, no orchestration
    execution, no advisory runtime.
  * Deterministic: identical inputs produce identical output; no wall-clock,
    no randomness, no counters.
  * Fail-closed: insufficient or ambiguous evidence returns ``None``. A
    capability gap is NEVER invented merely because something "might" be
    useful.
  * Side-effect-free: safe to invoke repeatedly; no network, filesystem,
    subprocess, model, approval, or execution calls.
  * Detection only: the emitted :class:`DetectedDevelopmentNeed` carries no
    lifecycle, approval, sandbox, promotion, or execution state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from atlas.conversation.task_intake import TaskSpec, TaskType

# ---------------------------------------------------------------------------
# Bounds (aligned with the conversation/advisory field conventions).
# ---------------------------------------------------------------------------

_MAX_REASON_CHARS: int = 400
_MAX_CAPABILITY_CHARS: int = 200
_MAX_ID_CHARS: int = 128
_MAX_ACTION_CHARS: int = 200
_MAX_EVIDENCE: int = 8
_MAX_EVIDENCE_CHARS: int = 200

#: Strip control characters from every derived text field.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Number of prior clarification rounds that turn a vague action into a
#: deterministic "repeated clarification" detection signal. Below this the
#: existing bounded clarification behavior remains authoritative.
_CLARIFICATION_REPEAT_THRESHOLD: int = 2

#: Governed self-development/improvement entry points. An advisory item whose
#: ``suggested_action`` names one of these is a detectable improvement
#: opportunity. The detector NEVER invokes these paths; it only records the
#: signal.
_IMPROVEMENT_ACTION_HINTS: frozenset[str] = frozenset({
    "atlas.run_development_cycle",
    "atlas.run_self_management_review",
})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DevelopmentSignalKind(str, Enum):
    """Deterministic classification of a detected (non-explicit) signal."""

    CAPABILITY_GAP = "capability_gap"
    UNRESOLVED_ACTION = "unresolved_action"
    REPEATED_CLARIFICATION = "repeated_clarification"
    ADVISORY_OPPORTUNITY = "advisory_opportunity"


@dataclass(frozen=True, slots=True)
class DetectedDevelopmentNeed:
    """Immutable detection record for one non-explicit development signal.

    Carries only information useful for later confirmation/reporting (P7.3).
    It deliberately omits proposal/approval/lifecycle/sandbox/promotion/
    execution state.
    """

    signal_kind: str
    reason: str
    evidence: tuple[str, ...] = ()
    capability: str = ""
    principal_id: str = ""
    authority: str = ""
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_kind": self.signal_kind,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "capability": self.capability,
            "principal_id": self.principal_id,
            "authority": self.authority,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class AdvisorySignal:
    """Bounded, conversation-owned projection of an advisory item.

    The detector never imports ``atlas.advisory``; callers project the
    relevant fields into this pure record (keeps the conversation layer free
    of any advisory-runtime dependency).
    """

    kind: str = ""
    summary: str = ""
    suggested_action: str = ""
    evidence_ids: tuple[str, ...] = ()
    principal_id: str = ""
    authority: str = ""


# ---------------------------------------------------------------------------
# Bounded helpers
# ---------------------------------------------------------------------------


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded, control-free string, or ``""`` for non-strings."""
    if not isinstance(value, str):
        return ""
    return _CONTROL_RE.sub(" ", value).strip()[:limit]


def _bounded_items(values: Any, max_items: int = _MAX_EVIDENCE) -> tuple[str, ...]:
    """Deduplicate and bound an iterable of strings (order preserved)."""
    if not isinstance(values, (list, tuple)):
        return ()
    seen: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        item = _bounded_text(value, _MAX_EVIDENCE_CHARS)
        if item and item not in seen:
            seen.append(item)
        if len(seen) >= max_items:
            break
    return tuple(seen)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class DevelopmentNeedDetector:
    """Deterministic detector for non-explicit development/improvement signals.

    Stateless and safe to reuse. ``detect`` never mutates its inputs and never
    performs I/O or external calls.
    """

    def detect(
        self,
        spec: TaskSpec | None,
        *,
        resolution: bool | None = None,
        missing_capability: str = "",
        clarification_count: int = 0,
        advisory: AdvisorySignal | None = None,
    ) -> DetectedDevelopmentNeed | None:
        """Detect a bounded development signal, or ``None``.

        Args:
            spec: The parsed :class:`TaskSpec` (or ``None``).
            resolution: Optional observable resolution outcome for the current
                request. ``True`` = target resolved, ``False`` = target NOT
                resolved, ``None`` = resolution signal unavailable (treated as
                insufficient evidence).
            missing_capability: Optional name of a specific capability/tool the
                request referenced but that is not registered. When non-empty
                and ``resolution`` is ``False``, the signal is classified as a
                capability gap rather than a generic unresolved action.
            clarification_count: Number of prior clarification rounds already
                observed for this task.
            advisory: Optional bounded :class:`AdvisorySignal`.

        Returns:
            A :class:`DetectedDevelopmentNeed` when, and only when, enough
            deterministic information justifies a detection signal. Otherwise
            ``None`` (fail-closed).
        """
        # An advisory improvement opportunity is independent of the current
        # spec and is detected purely from its bounded suggestion.
        if advisory is not None:
            detected = self._detect_advisory(advisory)
            if detected is not None:
                return detected

        if spec is None or not isinstance(spec, TaskSpec):
            return None

        # Explicit development requests belong to the existing B3 intake path.
        # Never duplicate or reroute them.
        if spec.task_type is TaskType.DEVELOPMENT_REQUEST:
            return None

        # Only ACTION requests can carry a capability-gap / unresolved-target
        # signal. Questions, research, and ordinary conversation never do.
        if spec.task_type is not TaskType.ACTION_REQUEST:
            return None

        if bool(spec.needs_clarification):
            # Vague action: existing clarification is authoritative. Only a
            # repeated clarification loop justifies a detection signal.
            if clarification_count >= _CLARIFICATION_REPEAT_THRESHOLD:
                return self._detect_repeated_clarification(spec)
            return None

        # Well-specified action: resolution signal decides.
        if resolution is True:
            return None
        if resolution is False:
            return self._detect_unresolved(spec, missing_capability)
        # resolution is None -> insufficient evidence; do not invent a gap.
        return None

    # ------------------------------------------------------------------
    # Internal detectors (each fail-closed)
    # ------------------------------------------------------------------

    def _detect_unresolved(
        self,
        spec: TaskSpec,
        missing_capability: str,
    ) -> DetectedDevelopmentNeed:
        capability = _bounded_text(missing_capability, _MAX_CAPABILITY_CHARS)
        if capability:
            return DetectedDevelopmentNeed(
                signal_kind=DevelopmentSignalKind.CAPABILITY_GAP.value,
                reason=(
                    f"Requested capability {capability!r} is not available "
                    "or not registered."
                ),
                evidence=(capability,),
                capability=capability,
                principal_id=_bounded_text(spec.context.get("principal_id"), _MAX_ID_CHARS),
                authority=_bounded_text(spec.context.get("authority"), _MAX_ID_CHARS),
                session_id=_bounded_text(spec.context.get("session_id"), _MAX_ID_CHARS),
            )
        intent = _bounded_text(spec.intent, _MAX_CAPABILITY_CHARS)
        return DetectedDevelopmentNeed(
            signal_kind=DevelopmentSignalKind.UNRESOLVED_ACTION.value,
            reason=(
                "Action target could not be resolved to a registered "
                "capability."
            ),
            evidence=(intent,) if intent else (),
            capability=intent,
            principal_id=_bounded_text(spec.context.get("principal_id"), _MAX_ID_CHARS),
            authority=_bounded_text(spec.context.get("authority"), _MAX_ID_CHARS),
            session_id=_bounded_text(spec.context.get("session_id"), _MAX_ID_CHARS),
        )

    def _detect_repeated_clarification(self, spec: TaskSpec) -> DetectedDevelopmentNeed:
        questions = _bounded_items(
            getattr(spec.ambiguity, "clarification_questions", ()) or ()
        )
        intent = _bounded_text(spec.intent, _MAX_CAPABILITY_CHARS)
        return DetectedDevelopmentNeed(
            signal_kind=DevelopmentSignalKind.REPEATED_CLARIFICATION.value,
            reason=(
                "Repeated clarification suggests the current capabilities "
                "cannot satisfy this task."
            ),
            evidence=questions or ((intent,) if intent else ()),
            capability=intent,
            principal_id=_bounded_text(spec.context.get("principal_id"), _MAX_ID_CHARS),
            authority=_bounded_text(spec.context.get("authority"), _MAX_ID_CHARS),
            session_id=_bounded_text(spec.context.get("session_id"), _MAX_ID_CHARS),
        )

    def _detect_advisory(self, advisory: AdvisorySignal) -> DetectedDevelopmentNeed | None:
        action = _bounded_text(advisory.suggested_action, _MAX_ACTION_CHARS)
        # Only a suggestion that names a governed self-development path is a
        # detectable improvement opportunity. Everything else fails closed.
        if action not in _IMPROVEMENT_ACTION_HINTS:
            return None
        summary = _bounded_text(advisory.summary, _MAX_REASON_CHARS)
        return DetectedDevelopmentNeed(
            signal_kind=DevelopmentSignalKind.ADVISORY_OPPORTUNITY.value,
            reason=summary or f"Advisory suggests governed action {action!r}.",
            evidence=_bounded_items(advisory.evidence_ids),
            capability="",
            principal_id=_bounded_text(advisory.principal_id, _MAX_ID_CHARS),
            authority=_bounded_text(advisory.authority, _MAX_ID_CHARS),
            session_id="",
        )
