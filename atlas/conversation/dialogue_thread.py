"""Atlas Conversation — QUD / active objective / dialogue-thread state (Stage 5).

The bounded, deterministic representation of WHAT QUESTION IS UNDER DISCUSSION,
WHAT OBJECTIVE IS BEING PURSUED, and WHICH CONVERSATIONAL THREAD a turn belongs
to — distinct from the latest utterance, from the topic words it contains, and
from the single most-recent result.

It complements the existing layers:

  * :mod:`atlas.conversation.meaning` (Stage 1)     — what this turn MEANS
  * :mod:`atlas.conversation.dialogue_state` (2)    — what happened recently
  * :mod:`atlas.conversation.discourse_state` (3)   — what referents exist
  * :mod:`atlas.conversation.communicative_function` (4) — what this turn DOES
  * this module (5)                                  — what we are discussing

Boundaries (mandatory):

  * Single source of truth — a field of ``ConversationState`` written only through
    the existing :class:`~atlas.conversation.conversation_state.ConversationStateManager`.
  * Reference, not copy — a thread stores stable referent IDs from the Stage 3
    ``DiscourseState``; it never duplicates referent objects.
  * Descriptive only — a thread/QUD never authorizes, approves, executes,
    promotes, or grants authority. A question records what was ASKED, never a
    generated "answer" as truth.
  * Deterministic and model-independent — standard library plus the EXISTING
    clarification matcher. No clock, no randomness, no I/O, no model, no
    embeddings, no salience scoring (Stage 6).
  * Bounded, JSON-safe and frozen; malformed input fails closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Optional

from atlas.conversation.clarification import candidate_matches
from atlas.conversation.communicative_function import (
    FUNCTION_REQUEST_OPERATION,
    FUNCTION_UNKNOWN,
    QUERY_FUNCTIONS,
)

#: Bounds (small, repository-consistent; a malformed/oversized turn cannot grow them).
MAX_THREADS: int = 12
MAX_QUD_HISTORY: int = 4
_MAX_TEXT_CHARS: int = 200
_MAX_ID_CHARS: int = 16
_MAX_KIND_CHARS: int = 40
_MAX_TURN_INDEX: int = 1_000_000

#: Thread lifecycle (smallest justified vocabulary). ``active`` is the single
#: current thread; ``superseded`` is a thread a later operation replaced as the
#: active objective (it stays represented, never erased).
STATUS_THREAD_ACTIVE: str = "active"
STATUS_THREAD_SUPERSEDED: str = "superseded"
THREAD_STATUSES: frozenset[str] = frozenset(
    {STATUS_THREAD_ACTIVE, STATUS_THREAD_SUPERSEDED}
)

#: QUD lifecycle (smallest justified vocabulary).
STATUS_QUD_OPEN: str = "open"
STATUS_QUD_ANSWERED: str = "answered"
QUD_STATUSES: frozenset[str] = frozenset({STATUS_QUD_OPEN, STATUS_QUD_ANSWERED})

#: Bounded leading follow-up forms that name a thread target ("what about X",
#: "regarding X"). Reused only to SELECT a thread — never to fabricate one.
_THREAD_TARGET_RE = re.compile(
    r"^\s*(?:and\s+|what\s+about\s+|how\s+about\s+|regarding\s+|about\s+)"
    r"(?P<target>.+?)\s*[.?!]*\s*$",
    re.IGNORECASE,
)


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_id(value: Any) -> str:
    return _bounded(value, _MAX_ID_CHARS)


def _bounded_index(value: Any) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(index, _MAX_TURN_INDEX))


def thread_target(text: Any) -> str:
    """Return the bounded named thread target of a short follow-up, or ``""``."""
    if not isinstance(text, str):
        return ""
    match = _THREAD_TARGET_RE.match(text)
    return _bounded(match.group("target")) if match else ""


@dataclass(frozen=True, slots=True)
class Question:
    """One bounded question under discussion (QUD) — facts only, no authority.

    ``kind`` is the Stage 4 communicative function that raised it; ``referent_id``
    is the Stage 3 referent it CONCERNS (a result/operation id), stored by
    reference. It records what was ASKED — never an answer as truth.
    """

    kind: str = ""
    referent_id: str = ""
    status: str = STATUS_QUD_OPEN
    turn_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "referent_id": self.referent_id,
            "status": self.status,
            "turn_index": self.turn_index,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["Question"]:
        if not isinstance(data, dict):
            return None
        status = _bounded(data.get("status"), _MAX_KIND_CHARS)
        if status not in QUD_STATUSES:
            status = STATUS_QUD_OPEN
        return cls(
            kind=_bounded(data.get("kind"), _MAX_KIND_CHARS),
            referent_id=_bounded_id(data.get("referent_id")),
            status=status,
            turn_index=_bounded_index(data.get("turn_index")),
        )


@dataclass(frozen=True, slots=True)
class Thread:
    """One bounded dialogue thread: an objective plus its current QUD.

    It references referents by ID (``operation_referent_id`` /
    ``result_referent_id``) — it never copies referent objects, so there is one
    registry. It grants no authority.
    """

    thread_id: str
    objective: str = ""
    operation_referent_id: str = ""
    result_referent_id: str = ""
    qud: Optional[Question] = None
    qud_history: tuple[Question, ...] = ()
    status: str = STATUS_THREAD_ACTIVE
    created_turn: int = 0
    last_active_turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "objective": self.objective,
            "operation_referent_id": self.operation_referent_id,
            "result_referent_id": self.result_referent_id,
            "qud": self.qud.to_dict() if isinstance(self.qud, Question) else None,
            "qud_history": [q.to_dict() for q in self.qud_history],
            "status": self.status,
            "created_turn": self.created_turn,
            "last_active_turn": self.last_active_turn,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["Thread"]:
        if not isinstance(data, dict):
            return None
        thread_id = _bounded_id(data.get("thread_id"))
        if not thread_id:
            return None
        status = _bounded(data.get("status"), _MAX_KIND_CHARS)
        if status not in THREAD_STATUSES:
            status = STATUS_THREAD_SUPERSEDED
        qud = data.get("qud")
        history: list[Question] = []
        raw_history = data.get("qud_history")
        if isinstance(raw_history, (list, tuple)):
            for item in raw_history:
                question = item if isinstance(item, Question) else Question.from_dict(item)
                if question is not None:
                    history.append(question)
        return cls(
            thread_id=thread_id,
            objective=_bounded(data.get("objective")),
            operation_referent_id=_bounded_id(data.get("operation_referent_id")),
            result_referent_id=_bounded_id(data.get("result_referent_id")),
            qud=qud if isinstance(qud, Question) else Question.from_dict(qud),
            qud_history=tuple(history)[:MAX_QUD_HISTORY],
            status=status,
            created_turn=_bounded_index(data.get("created_turn")),
            last_active_turn=_bounded_index(data.get("last_active_turn")),
        )


@dataclass(frozen=True, slots=True)
class DialogueThreadState:
    """Bounded, deterministic QUD / active-objective / thread state (facts only)."""

    threads: tuple[Thread, ...] = ()
    active_thread_id: str = ""
    sequence: int = 0

    def active(self) -> Optional[Thread]:
        """Return the ACTIVE thread, or ``None``."""
        for thread in self.threads:
            if thread.thread_id == self.active_thread_id:
                return thread
        return None

    def find(self, thread_id: str) -> Optional[Thread]:
        """Return the thread with ``thread_id``, or ``None``."""
        for thread in self.threads:
            if thread.thread_id == thread_id:
                return thread
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "threads": [t.to_dict() for t in self.threads],
            "active_thread_id": self.active_thread_id,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["DialogueThreadState"]:
        if not isinstance(data, dict):
            return None
        threads: list[Thread] = []
        raw = data.get("threads")
        if isinstance(raw, (list, tuple)):
            for item in raw:
                thread = item if isinstance(item, Thread) else Thread.from_dict(item)
                if thread is not None:
                    threads.append(thread)
        try:
            sequence = max(0, int(data.get("sequence", 0)))
        except (TypeError, ValueError):
            sequence = 0
        active_id = _bounded_id(data.get("active_thread_id"))
        if active_id and not any(t.thread_id == active_id for t in threads):
            active_id = ""
        return cls(
            threads=tuple(threads)[-MAX_THREADS:],
            active_thread_id=active_id,
            sequence=sequence,
        )


@dataclass(frozen=True, slots=True)
class ThreadTurnOutcome:
    """The bounded inputs to one thread/QUD transition (value object only)."""

    turn_index: int = 0
    function: str = FUNCTION_UNKNOWN
    objective: str = ""
    operation_referent_id: str = ""
    result_referent_id: str = ""
    target_referent_id: str = ""
    explicit_thread_target: str = ""


def _supersede(thread: Thread) -> Thread:
    if thread.status == STATUS_THREAD_ACTIVE:
        return replace(thread, status=STATUS_THREAD_SUPERSEDED)
    return thread


def _match_objective(threads: list[Thread], target: str) -> Optional[Thread]:
    """Return the single thread whose objective matches ``target``, or ``None``."""
    if not target:
        return None
    labels = [t.objective for t in threads if t.objective]
    hits = candidate_matches(target, labels)
    if len(hits) != 1:
        return None
    return next(t for t in threads if t.objective == hits[0])


def _select(base: DialogueThreadState, threads: list[Thread], outcome: ThreadTurnOutcome) -> Optional[Thread]:
    """Deterministically choose the thread a query turn belongs to (or ``None``)."""
    if outcome.target_referent_id:
        for thread in threads:
            if outcome.target_referent_id in (
                thread.result_referent_id,
                thread.operation_referent_id,
            ):
                return thread
    by_objective = _match_objective(threads, outcome.explicit_thread_target)
    if by_objective is not None:
        return by_objective
    return base.active()


def apply_turn(
    current: "DialogueThreadState | None", outcome: "ThreadTurnOutcome"
) -> DialogueThreadState:
    """The single deterministic thread/QUD transition (pure).

    * a REQUEST_OPERATION that completed an operation activates a NEW thread
      (superseding the previous active one, which stays represented);
    * a QUERY_* attaches to the relevant thread — chosen by target referent, then
      by an explicit named objective, then the active thread — and updates its
      QUD (the previous QUD moves into bounded history);
    * an UNKNOWN turn with an explicit named objective only SWITCHES the active
      thread (no new QUD);
    * anything else changes nothing (a thread is never invented for a stray turn).

    Every field is re-bounded here, so a malformed outcome cannot grow state.
    """
    base = current if isinstance(current, DialogueThreadState) else DialogueThreadState()
    threads = list(base.threads)
    sequence = base.sequence
    active_id = base.active_thread_id
    turn_index = _bounded_index(outcome.turn_index)

    if outcome.function == FUNCTION_REQUEST_OPERATION and outcome.operation_referent_id:
        sequence += 1
        result_id = _bounded_id(outcome.result_referent_id)
        thread = Thread(
            thread_id=f"thr-{sequence:04d}",
            objective=_bounded(outcome.objective),
            operation_referent_id=_bounded_id(outcome.operation_referent_id),
            result_referent_id=result_id,
            qud=Question(
                kind=FUNCTION_REQUEST_OPERATION,
                referent_id=result_id or _bounded_id(outcome.operation_referent_id),
                status=STATUS_QUD_ANSWERED if result_id else STATUS_QUD_OPEN,
                turn_index=turn_index,
            ),
            created_turn=turn_index,
            last_active_turn=turn_index,
        )
        threads = [_supersede(t) if t.thread_id == active_id else t for t in threads]
        threads.append(thread)
        active_id = thread.thread_id
    elif outcome.function in QUERY_FUNCTIONS:
        thread = _select(base, threads, outcome)
        if thread is not None:
            history = thread.qud_history
            if thread.qud is not None:
                history = (thread.qud,) + tuple(history)
                history = tuple(history)[:MAX_QUD_HISTORY]
            updated = replace(
                thread,
                qud=Question(
                    kind=_bounded(outcome.function, _MAX_KIND_CHARS),
                    referent_id=_bounded_id(outcome.target_referent_id)
                    or thread.result_referent_id
                    or thread.operation_referent_id,
                    status=STATUS_QUD_OPEN,
                    turn_index=turn_index,
                ),
                qud_history=history,
                status=STATUS_THREAD_ACTIVE,
                last_active_turn=turn_index,
            )
            threads = [
                updated
                if t.thread_id == thread.thread_id
                else (_supersede(t) if t.thread_id == active_id else t)
                for t in threads
            ]
            active_id = thread.thread_id
    elif outcome.function == FUNCTION_UNKNOWN and outcome.explicit_thread_target:
        thread = _match_objective(threads, outcome.explicit_thread_target)
        if thread is not None:
            threads = [
                replace(t, status=STATUS_THREAD_ACTIVE, last_active_turn=turn_index)
                if t.thread_id == thread.thread_id
                else (_supersede(t) if t.thread_id == active_id else t)
                for t in threads
            ]
            active_id = thread.thread_id

    if len(threads) > MAX_THREADS:
        threads = threads[-MAX_THREADS:]
    if active_id and not any(t.thread_id == active_id for t in threads):
        active_id = threads[-1].thread_id if threads else ""
    return DialogueThreadState(
        threads=tuple(threads), active_thread_id=active_id, sequence=sequence
    )


def thread_outcome_from(
    *,
    function: Any,
    turn_index: Any = 0,
    text: Any = "",
    objective: Any = "",
    operation_referent_id: Any = "",
    result_referent_id: Any = "",
    target_referent_id: Any = "",
) -> ThreadTurnOutcome:
    """Build the bounded transition outcome from already-derived evidence.

    Pure and duck-typed: it consumes the Stage 4 function, the Stage 3 referent
    ids recorded for the turn, the Stage 4 target (when the result-query route
    ran) and the turn text. It never re-parses meaning.
    """
    return ThreadTurnOutcome(
        turn_index=_bounded_index(turn_index),
        function=_bounded(function, _MAX_KIND_CHARS) or FUNCTION_UNKNOWN,
        objective=_bounded(objective),
        operation_referent_id=_bounded_id(operation_referent_id),
        result_referent_id=_bounded_id(result_referent_id),
        target_referent_id=_bounded_id(target_referent_id),
        explicit_thread_target=thread_target(text),
    )


__all__ = [
    "MAX_THREADS",
    "MAX_QUD_HISTORY",
    "STATUS_THREAD_ACTIVE",
    "STATUS_THREAD_SUPERSEDED",
    "STATUS_QUD_OPEN",
    "STATUS_QUD_ANSWERED",
    "THREAD_STATUSES",
    "QUD_STATUSES",
    "Question",
    "Thread",
    "DialogueThreadState",
    "ThreadTurnOutcome",
    "thread_target",
    "apply_turn",
    "thread_outcome_from",
]
