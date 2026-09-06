"""Atlas Conversation — Deterministic Task Intake (B2).

Converts a casual natural-language instruction into a bounded, structured
:class:`TaskSpec` WITHOUT executing anything and WITHOUT a mandatory model
call. This is the intake half of conversational understanding: the TaskSpec
is data that flows into the existing cognitive pipeline through its
``goal`` / ``metadata`` parameters.

Design contract:
  * Deterministic-first, model-independent, no mandatory LLM.
  * Optional model assistance exists only as an injected
    :class:`IntentParser` protocol; it is OFF by default, and any model
    output is untrusted (``verified=False``) and sanitized/bounded.
  * The module is pure: no ``atlas.ai``, no kernel, no storage, no EventBus,
    no capability execution, no governance surface.
  * Raw user input is data, never an instruction to the framework.

No infrastructure dependencies.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Bounds (all derived fields are hard-capped so oversized input cannot
# produce oversized state).
# ---------------------------------------------------------------------------

_MAX_INTENT_CHARS: int = 400
_MAX_GOAL_CHARS: int = 500
_MAX_ITEM_CHARS: int = 200
_MAX_ITEM_COUNT: int = 8
_MAX_CONTEXT_VALUES: int = 24

#: Control characters are stripped from every derived text field.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Alphanumeric token pattern (mirrors the deterministic semantic-recall
#: tokenization approach: lowercase alnum tokens, length >= 2).
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN: int = 2

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskType(Enum):
    """Deterministic classification of what a human instruction asks for."""

    CONVERSATION = "conversation"
    QUESTION = "question"
    INFORMATION_REQUEST = "information_request"
    ACTION_REQUEST = "action_request"
    DEVELOPMENT_REQUEST = "development_request"
    INVESTIGATION_REQUEST = "investigation_request"
    APPROVAL = "approval"
    EXECUTION_REQUEST = "execution_request"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Cue vocabularies (deterministic, order-independent).
# ---------------------------------------------------------------------------

_QUESTION_CUES: frozenset[str] = frozenset(
    {"how", "what", "why", "when", "where", "who", "which", "?"}
)

_RESEARCH_CUES: frozenset[str] = frozenset(
    {"find", "look up", "lookup", "research", "search", "latest", "investigate"}
)

#: Word-boundary greeting regex: short tokens ("hi", "hey") must not match
#: inside "this" / "they", while multi-word greetings match as phrases.
_GREETING_RE = re.compile(
    r"\b(?:hello|hi|hey)\b|how are you|good morning|good afternoon|good evening|nice to meet you"
)

_DEVELOPMENT_CUES: frozenset[str] = frozenset(
    {
        "add",
        "extend",
        "implement",
        "refactor",
        "fix",
        "build",
        "modify",
        "improve",
        "create a module",
        "create a capability",
    }
)

_SELF_TARGETS: frozenset[str] = frozenset(
    {"atlas", "yourself", "your self", "a module", "a capability", "the framework"}
)

_INVESTIGATION_CUES: frozenset[str] = frozenset(
    {
        "investigate",
        "investigation",
        "diagnose",
        "diagnosis",
        "inspect",
        "examine",
        "analyze",
        "analysis",
        "trace",
        "debug",
    }
)

#: Phrases that negate the following cue, preventing misclassification.
_NEGATION_PREFIXES: tuple[str, ...] = (
    "don't",
    "dont",
    "do not",
    "never",
    "no",
)

#: Explicit approval phrases that indicate the user is approving a proposal.
_APPROVAL_CUES: frozenset[str] = frozenset(
    {
        "approve",
        "approved",
        "approval",
        "accept",
        "accepted",
        "authorize",
        "authorized",
    }
)

#: Ambiguous responses that must NOT be treated as approval.
_AMBIGUOUS_RESPONSES: frozenset[str] = frozenset(
    {
        "ok",
        "okay",
        "sure",
        "fine",
        "sounds good",
        "looks good",
        "looks fine",
        "makes sense",
        "go ahead",
        "do it",
        "proceed",
    }
)

#: Explicit execution request phrases.
#: These cues indicate the user wants to execute an already-approved proposal.
#: NOTE: Bare "implement" or "apply" without "approved" context is ambiguous
#: and may indicate development intent (Level 2). Only unambiguous execution
#: language or "implement/apply the approved" triggers Level 3.
_EXECUTION_CUES: frozenset[str] = frozenset(
    {
        "execute",
        "execute the approved",
        "run the approved",
        "perform the approved",
        "implement the approved",
        "apply the approved",
        "begin implementation",
        "start implementation",
        "proceed with implementation",
        "carry out the approved",
    }
)

_ACTION_CUES: frozenset[str] = frozenset(
    {
        "create",
        "write",
        "run",
        "build",
        "organize",
        "make",
        "generate",
        "produce",
        "summarize",
        "analyze",
        "compute",
        "calculate",
        "compile",
        "deploy",
        "clean",
    }
)

_CONSTRAINT_CUES: tuple[str, ...] = (
    "must",
    "without",
    "using",
    "only",
    "keep",
    "do not",
    "don't",
    "do not use",
    "avoid",
)

_PRIORITY_CUES: tuple[str, ...] = (
    "first",
    "urgent",
    "priority",
    "important",
    "most important",
    "asap",
)

_SUCCESS_CUES: tuple[str, ...] = (
    "done when",
    "so that",
    "verify",
    "verified",
    "success when",
    "make sure",
    "ensure",
    "when it",
    "until",
)

#: Word-boundary pronoun detection for unresolved reference ambiguity.
#: A word-boundary regex avoids false positives such as "it" inside "priority".
_AMBIGUOUS_PRONOUN_RE = re.compile(r"\b(it|that|this|them|those)\b")

#: Wh-words used to build deterministic clarification questions.
_CLARIFY_CUES: dict[str, str] = {
    "success": "What outcome would tell you this is done?",
    "objective": "What is the exact objective you want Atlas to achieve?",
    "reference": "What does the ambiguous reference refer to?",
    "task_type": "What kind of task is this?",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bounded_text(value: str, limit: int) -> str:
    """Strip control chars and cap a derived string to ``limit`` chars."""
    if not value:
        return ""
    return _CONTROL_RE.sub(" ", value).strip()[:limit]


def _clauses(text: str) -> list[str]:
    """Split normalized text into non-empty, bounded clauses."""
    return [
        clause.strip()
        for clause in re.split(r"[;,\n]", text)
        if clause.strip()
    ]


def _first_hit(text: str, cues: frozenset[str] | tuple[str, ...]) -> bool:
    """Return True when any cue is present (whole-cue match)."""
    lowered = text.lower()
    return any(cue in lowered for cue in cues)


def _extract_items(text: str, cues: tuple[str, ...]) -> tuple[str, ...]:
    """Extract bounded, deduplicated cue-anchored clauses in appearance order.

    Every cue occurrence is located, sorted by position, then each clause is
    taken from the cue to the next clause boundary. Overlapping occurrences
    (e.g. "do not" inside "do not use") are collapsed so one cue produces one
    clause.
    """
    matches: list[tuple[int, str]] = []
    lowered = text.lower()
    for cue in cues:
        start = 0
        while True:
            idx = lowered.find(cue, start)
            if idx < 0:
                break
            matches.append((idx, cue))
            start = idx + 1
    matches.sort(key=lambda m: m[0])

    items: list[str] = []
    seen: set[str] = set()
    covered_until = -1
    for idx, _cue in matches:
        if idx < covered_until:
            continue
        clause = text[idx:]
        boundary = min(
            [b for b in (clause.find(";"), clause.find(", "), clause.find("\n")) if b >= 0]
            or [len(clause)]
        )
        item = _bounded_text(clause[:boundary], _MAX_ITEM_CHARS)
        if item:
            covered_until = idx + len(item)
            if item not in seen:
                seen.add(item)
                items.append(item)
        if len(items) >= _MAX_ITEM_COUNT:
            break
    return tuple(items)


def _tokens(text: str) -> tuple[str, ...]:
    """Return deduplicated, order-preserving lowercase alnum tokens."""
    seen: dict[str, None] = {}
    for raw in _TOKEN_RE.findall(text.lower()):
        if len(raw) >= _MIN_TOKEN_LEN:
            seen.setdefault(raw, None)
    return tuple(seen)


def _is_negated(text: str, cue: str) -> bool:
    """Return True when ``cue`` appears in ``text`` immediately after a
    negation prefix (e.g. "don't modify" -> ``modify`` is negated).

    This is intentionally narrow: it only detects the common contraction/
    adverb negation patterns required to prevent misclassification of
    explicit read-only boundaries such as "don't modify anything yet".
    """
    lowered = text.lower()
    idx = lowered.find(cue)
    if idx <= 0:
        return False
    prefix = lowered[:idx].rstrip()
    return any(prefix.endswith(neg) for neg in _NEGATION_PREFIXES)


def _is_explicit_approval(text: str) -> bool:
    """Return True when the text contains explicit approval language.

    Explicit approval requires unambiguous approval cues (e.g. "approve",
    "accept", "authorize"). Ambiguous responses like "okay", "sounds good",
    "go ahead" are NOT treated as approval.

    Args:
        text: the normalized request text.

    Returns:
        True if the text contains explicit approval language.
    """
    lowered = text.lower()
    # Must contain an explicit approval cue
    has_approval_cue = any(cue in lowered for cue in _APPROVAL_CUES)
    if not has_approval_cue:
        return False
    # Must NOT be negated (e.g. "don't approve")
    for cue in _APPROVAL_CUES:
        if cue in lowered and _is_negated(lowered, cue):
            return False
    return True


def _is_explicit_execution(text: str) -> bool:
    """Return True when the text contains explicit execution language.

    Explicit execution requires unambiguous execution cues (e.g. "execute",
    "implement", "apply the approved proposal"). Ambiguous responses like
    "okay", "go ahead", "do it" are NOT treated as execution.

    Args:
        text: the normalized request text.

    Returns:
        True if the text contains explicit execution language.
    """
    lowered = text.lower()
    # Must contain an explicit execution cue
    has_execution_cue = any(cue in lowered for cue in _EXECUTION_CUES)
    if not has_execution_cue:
        return False
    # Must NOT be negated (e.g. "don't execute")
    for cue in _EXECUTION_CUES:
        if cue in lowered and _is_negated(lowered, cue):
            return False
    return True


def _stable_hash(text: str) -> str:
    """Deterministic SHA-256 short hash of the raw input."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AmbiguityReport:
    """Deterministic ambiguity assessment for a parsed instruction."""

    ambiguity_score: float = 0.0
    ambiguities: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambiguity_score": self.ambiguity_score,
            "ambiguities": list(self.ambiguities),
            "clarification_questions": list(self.clarification_questions),
        }


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Structured, provenance-carrying representation of one instruction."""

    task_id: str
    task_type: TaskType
    intent: str
    goal: str
    constraints: tuple[str, ...]
    priorities: tuple[str, ...]
    success_criteria: tuple[str, ...]
    context: dict[str, Any]
    ambiguity: AmbiguityReport
    confidence: float
    needs_clarification: bool
    source: str
    verified: bool
    model_metadata: dict[str, Any]
    created_at: datetime
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe deterministic serialization (no raw prompt/response)."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "intent": self.intent,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "priorities": list(self.priorities),
            "success_criteria": list(self.success_criteria),
            "context": self.context,
            "ambiguity": self.ambiguity.to_dict(),
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "source": self.source,
            "verified": self.verified,
            "model_metadata": self.model_metadata,
            "created_at": self.created_at.isoformat(),
            "input_hash": self.input_hash,
        }

    def goal_string(self) -> str:
        """Render the bounded goal for the existing ``CognitionState.goal``."""
        return self.goal


@runtime_checkable
class IntentParser(Protocol):
    """Optional model-assisted parsing seam.

    Implementations live outside this pure module and are injected by the
    composition layer through an existing provider seam. They never receive
    capability/execution access; their output is untrusted data that this
    module validates, bounds, and marks ``verified=False``.
    """

    def parse(self, text: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """Return a bounded parse dict, or None to fall back deterministically."""
        ...


# ---------------------------------------------------------------------------
# TaskIntake
# ---------------------------------------------------------------------------


class TaskIntake:
    """Deterministic conversational task intake (optional model assist).

    Args:
        parser: Optional :class:`IntentParser`. When absent (default), intake
            is deterministic-only and no model is ever consulted. When
            present, its output is treated as untrusted, validated, and used
            only to fill the spec fields; any failure falls back to the
            deterministic result.
    """

    def __init__(self, parser: IntentParser | None = None, now: datetime | None = None) -> None:
        self._parser = parser
        self._now = now

    def intake(self, text: str, history_length: int = 0) -> TaskSpec:
        """Parse one instruction into a bounded, deterministic-first TaskSpec.

        Never raises: malformed/empty/non-string input produces a minimal,
        high-ambiguity ``UNKNOWN`` spec.
        """
        if not isinstance(text, str):
            text = ""
        raw = text
        normalized = re.sub(r"\s+", " ", text).strip()
        context = self._build_context(raw, history_length)

        model_fields: dict[str, Any] | None = None
        if self._parser is not None:
            try:
                parsed = self._parser.parse(raw, context)
                if isinstance(parsed, dict):
                    model_fields = self._sanitize_model_fields(parsed)
            except Exception:
                model_fields = None

        return self._build_spec(
            raw=raw,
            normalized=normalized,
            context=context,
            model_fields=model_fields,
        )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _build_context(self, raw: str, history_length: int) -> dict[str, Any]:
        """Derive bounded, non-secret context from the instruction."""
        tokens = _tokens(raw)
        return {
            "history_length": max(0, min(history_length, 10_000)),
            "concepts": list(tokens[:_MAX_CONTEXT_VALUES]),
            "token_count": len(tokens),
            "length": len(raw),
        }

    # ------------------------------------------------------------------
    # Model-assist sanitization (untrusted data)
    # ------------------------------------------------------------------

    def _sanitize_model_fields(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """Validate and bound an injected parser's output.

        Returns a dict of only the fields the deterministic path understands;
        malformed values are dropped. The raw model prompt/response never
        enters this structure.
        """
        fields: dict[str, Any] = {}

        task_type_raw = parsed.get("task_type")
        if isinstance(task_type_raw, str) and task_type_raw in _TASK_TYPE_BY_VALUE:
            fields["task_type"] = _TASK_TYPE_BY_VALUE[task_type_raw]

        for key, limit in (
            ("intent", _MAX_INTENT_CHARS),
            ("goal", _MAX_GOAL_CHARS),
        ):
            value = parsed.get(key)
            if isinstance(value, str):
                cleaned = _bounded_text(value, limit)
                if cleaned:
                    fields[key] = cleaned

        for key in ("constraints", "priorities", "success_criteria"):
            value = parsed.get(key)
            if isinstance(value, list):
                cleaned = []
                seen: set[str] = set()
                for item in value:
                    if not isinstance(item, str):
                        continue
                    text_item = _bounded_text(item, _MAX_ITEM_CHARS)
                    if text_item and text_item not in seen:
                        seen.add(text_item)
                        cleaned.append(text_item)
                    if len(cleaned) >= _MAX_ITEM_COUNT:
                        break
                fields[key] = cleaned

        return fields

    # ------------------------------------------------------------------
    # Deterministic classification / extraction
    # ------------------------------------------------------------------

    def _classify(self, normalized: str) -> TaskType:
        lowered = normalized.lower()
        if not normalized:
            return TaskType.UNKNOWN
        if not _tokens(normalized):
            return TaskType.UNKNOWN

        # Explicit execution is checked first. It requires unambiguous execution
        # language and cannot be ambiguous conversational responses.
        if _is_explicit_execution(normalized):
            return TaskType.EXECUTION_REQUEST

        # Explicit approval is checked next. It requires unambiguous approval
        # language and cannot be ambiguous conversational responses.
        if _is_explicit_approval(normalized):
            return TaskType.APPROVAL

        # Investigation cues are checked next and take precedence.
        # They are read-only by intent and must not be routed to development.
        investigation = _first_hit(lowered, _INVESTIGATION_CUES)
        if investigation:
            return TaskType.INVESTIGATION_REQUEST

        # Development cues are only treated as development when NOT negated.
        # "don't modify" must not become a development request.
        development_cue_hit = _first_hit(lowered, _DEVELOPMENT_CUES)
        development_negated = any(
            _is_negated(lowered, cue) for cue in _DEVELOPMENT_CUES if cue in lowered
        )
        development = (development_cue_hit and not development_negated) and (
            _first_hit(lowered, _SELF_TARGETS)
            or "capability" in lowered
            or "module" in lowered
        )
        research = _first_hit(lowered, _RESEARCH_CUES)
        greeting = bool(_GREETING_RE.search(lowered))
        question = "?" in normalized or (
            _first_hit(lowered, _QUESTION_CUES) and len(_tokens(normalized)) <= 20
        )
        action = _first_hit(lowered, _ACTION_CUES)

        # Development wins over generic research/action because it names
        # Atlas itself or its capabilities as the target.
        if development:
            return TaskType.DEVELOPMENT_REQUEST
        if research:
            return TaskType.INFORMATION_REQUEST
        if greeting:
            return TaskType.CONVERSATION
        if question:
            return TaskType.QUESTION
        if action:
            return TaskType.ACTION_REQUEST
        return TaskType.CONVERSATION

    def _extract_objective(self, normalized: str) -> str:
        lowered = normalized.lower()
        for cue in (
            *_DEVELOPMENT_CUES,
            *_ACTION_CUES,
            "research",
            "find",
            "look up",
            "lookup",
            "search",
        ):
            idx = lowered.find(cue)
            if idx >= 0:
                return _bounded_text(normalized[idx:], _MAX_INTENT_CHARS)
        return _bounded_text(normalized, _MAX_INTENT_CHARS)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _build_spec(
        self,
        raw: str,
        normalized: str,
        context: dict[str, Any],
        model_fields: dict[str, Any] | None,
    ) -> TaskSpec:
        # Deterministic fields (always computed, even when model assist is on,
        # so there is always a safe fallback).
        deterministic_type = self._classify(normalized)
        deterministic_intent = self._extract_objective(normalized)
        deterministic_constraints = _extract_items(normalized, _CONSTRAINT_CUES)
        deterministic_priorities = _extract_items(normalized, _PRIORITY_CUES)
        deterministic_success = _extract_items(normalized, _SUCCESS_CUES)

        using_model = model_fields is not None
        task_type = (
            model_fields.get("task_type", deterministic_type)
            if using_model
            else deterministic_type
        )
        intent = (
            model_fields.get("intent", deterministic_intent)
            if using_model
            else deterministic_intent
        )
        constraints = (
            tuple(model_fields.get("constraints", ()))
            if using_model and "constraints" in model_fields
            else deterministic_constraints
        )
        priorities = (
            tuple(model_fields.get("priorities", ()))
            if using_model and "priorities" in model_fields
            else deterministic_priorities
        )
        success_criteria = (
            tuple(model_fields.get("success_criteria", ()))
            if using_model and "success_criteria" in model_fields
            else deterministic_success
        )

        ambiguity = self._assess_ambiguity(
            normalized=normalized,
            task_type=task_type,
            objective=intent,
            constraints=constraints,
            success_criteria=success_criteria,
        )
        confidence = self._confidence(
            task_type=task_type,
            objective=intent,
            success_criteria=success_criteria,
            using_model=using_model,
        )

        goal = self._render_goal(
            task_type=task_type,
            objective=intent,
            constraints=constraints,
            priorities=priorities,
            success_criteria=success_criteria,
        )
        needs_clarification = (
            task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST)
            and ambiguity.ambiguity_score >= 0.5
        )

        source = "model_assisted" if using_model else "deterministic"
        verified = not using_model
        model_metadata: dict[str, Any] = {}
        if using_model:
            model_metadata = {
                "task_type": task_type.value,
                "intent_provided": "intent" in model_fields,
            }

        return TaskSpec(
            task_id=_stable_hash(raw),
            task_type=task_type,
            intent=intent,
            goal=goal,
            constraints=constraints,
            priorities=priorities,
            success_criteria=success_criteria,
            context=context,
            ambiguity=ambiguity,
            confidence=confidence,
            needs_clarification=needs_clarification,
            source=source,
            verified=verified,
            model_metadata=model_metadata,
            created_at=self._now if self._now is not None else datetime.now(),
            input_hash=_stable_hash(raw),
        )

    def _assess_ambiguity(
        self,
        normalized: str,
        task_type: TaskType,
        objective: str,
        constraints: tuple[str, ...],
        success_criteria: tuple[str, ...],
    ) -> AmbiguityReport:
        reasons: list[str] = []
        lowered = normalized.lower()

        if task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST) and not objective:
            reasons.append("objective")

        if task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST) and not success_criteria:
            reasons.append("success")

        if task_type == TaskType.UNKNOWN:
            reasons.append("task_type")

        if _AMBIGUOUS_PRONOUN_RE.search(lowered):
            reasons.append("reference")

        reasons = sorted(set(reasons))
        weight = 0.0
        for reason in reasons:
            if reason in ("objective", "success"):
                weight += 0.25
            elif reason == "reference":
                weight += 0.3
            elif reason == "task_type":
                weight += 0.35
        score = round(min(1.0, weight), 4)

        questions: list[str] = []
        seen: set[str] = set()
        for reason in reasons:
            template = _CLARIFY_CUES.get(reason)
            if template and template not in seen:
                seen.add(template)
                questions.append(template)

        return AmbiguityReport(
            ambiguity_score=score,
            ambiguities=tuple(reasons),
            clarification_questions=tuple(questions),
        )

    def _confidence(
        self,
        task_type: TaskType,
        objective: str,
        success_criteria: tuple[str, ...],
        using_model: bool,
    ) -> float:
        """Deterministic confidence (never inflates model-assist trust)."""
        score = 0.0
        if task_type is not TaskType.UNKNOWN:
            score += 0.3
        if objective:
            score += 0.3
        if success_criteria:
            score += 0.4
        if using_model:
            score = min(score, 0.5)
        return round(score, 4)

    def _render_goal(
        self,
        task_type: TaskType,
        objective: str,
        constraints: tuple[str, ...],
        priorities: tuple[str, ...],
        success_criteria: tuple[str, ...],
    ) -> str:
        """Render the bounded, prioritized goal string for CognitionState.goal."""
        verb = "respond" if task_type in (TaskType.CONVERSATION, TaskType.UNKNOWN) else "respond"
        parts = [f"{verb}: {objective}" if objective else f"{verb}"]
        if constraints:
            parts.append("constraints: " + "; ".join(constraints))
        if priorities:
            parts.append("priorities: " + "; ".join(priorities))
        if success_criteria:
            parts.append("success: " + "; ".join(success_criteria))
        return _bounded_text(" | ".join(parts), _MAX_GOAL_CHARS)


_TASK_TYPE_BY_VALUE: dict[str, TaskType] = {
    member.value: member for member in TaskType
}
