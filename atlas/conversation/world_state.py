"""Atlas Conversation — bounded conversational world state (Step 8).

A bounded, deterministic representation of the *relevant state of an ongoing
conversation*: the ACTIVE topic (and what kind of thing it is), the bounded
ordered history of PRIOR topics, and the most recent unresolved reference.

It exists because the baseline (real Atlas/kernel, multi-turn) demonstrated that
Atlas retained only the ACTIVE context plus the single most recent result, with
no representation that separated ACTIVE state from HISTORICAL state. The
consequences were concrete:

  * after a topic switch, a PRIOR topic's turn still competed as an active
    contextual candidate, so a plain pronoun reference became ambiguous and fell
    to the generic floor, even though one topic was unambiguously current;
  * there was no representation of the topics the conversation had covered, so
    returning to an earlier topic was not recognized at all;
  * there was no record that a reference had been left UNRESOLVED.

Design contract (mirrors :mod:`atlas.conversation.conversation_state`):

  * immutable frozen value objects — every transition produces a new value;
  * bounded — at most :data:`MAX_WORLD_TOPICS` topics, every field length-capped;
  * deterministic — no clock, no randomness, no I/O, no model, no network;
  * authority-free — facts only. It never authorizes, approves, executes,
    promotes, or mutates governed state, and it is NOT a durable memory store.

It is deliberately a REPRESENTATION, not a second persistence mechanism: the
existing :class:`~atlas.conversation.conversation_state.ConversationStateManager`
remains the single owner and serialization point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Optional

#: Upper bound on retained conversational topics (older topics dropped).
MAX_WORLD_TOPICS: int = 6

#: Bound applied to each retained topic label.
_MAX_TOPIC_CHARS: int = 200

#: Bound applied to a retained topic kind.
_MAX_KIND_CHARS: int = 32

#: Bound applied to a retained result reference.
_MAX_RESULT_REF_CHARS: int = 300

#: Bound applied to a retained unresolved reference.
_MAX_REFERENCE_CHARS: int = 200

#: How recent a topic must be to remain in history (position, not time).
_MAX_TOPIC_ORDER: int = 1_000_000

#: Topic status values. ``active`` is the single current topic; ``superseded``
#: is a topic that a later topic replaced; ``completed`` is kept distinct so a
#: finished topic is never re-read as the current one.
STATUS_ACTIVE: str = "active"
STATUS_SUPERSEDED: str = "superseded"
STATUS_COMPLETED: str = "completed"


def _key(text: Any) -> str:
    """Case/punctuation/whitespace-insensitive comparison key."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _bounded(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_turn(value: Any) -> int:
    try:
        turn = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(turn, _MAX_TOPIC_ORDER))


@dataclass(frozen=True, slots=True)
class WorldTopic:
    """One bounded conversational topic (facts only).

    ``label`` is the bounded topic text (an investigation target, a knowledge
    query, a goal objective, or a corrected reading), ``kind`` is what produced
    it (``investigation`` / ``knowledge`` / ``goal`` / ``correction``),
    ``turn_index`` is the deterministic conversation order at which it was
    established, ``status`` is one of the :data:`STATUS_ACTIVE` /
    :data:`STATUS_SUPERSEDED` / :data:`STATUS_COMPLETED` values, and
    ``result_ref`` is a bounded reference to the topic's own result when one
    exists.
    """

    label: str
    kind: str = "objective"
    turn_index: int = 0
    status: str = STATUS_SUPERSEDED
    result_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "label": self.label,
            "kind": self.kind,
            "turn_index": self.turn_index,
            "status": self.status,
            "result_ref": self.result_ref,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["WorldTopic"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        label = _bounded(data.get("label"), _MAX_TOPIC_CHARS)
        if not label:
            return None
        kind = _bounded(data.get("kind"), _MAX_KIND_CHARS) or "objective"
        status = _bounded(data.get("status"), _MAX_KIND_CHARS)
        if status not in (STATUS_ACTIVE, STATUS_SUPERSEDED, STATUS_COMPLETED):
            status = STATUS_SUPERSEDED
        return cls(
            label=label,
            kind=kind,
            turn_index=_bounded_turn(data.get("turn_index")),
            status=status,
            result_ref=_bounded(data.get("result_ref"), _MAX_RESULT_REF_CHARS),
        )


@dataclass(frozen=True, slots=True)
class ConversationWorld:
    """Bounded, deterministic conversational world state.

    Attributes:
        active_topic: the CURRENT topic label (``""`` when none is established).
        active_kind: what established the current topic.
        turn_index: the conversation order at which the active topic was set.
        topics: bounded ordered record of topics, MOST RECENT FIRST, including
            the active one. History is preserved across topic switches.
        unresolved_reference: the most recent reference Atlas could not resolve
            (kept so an unresolved reference stays visibly unresolved).
    """

    active_topic: str = ""
    active_kind: str = ""
    turn_index: int = 0
    topics: tuple[WorldTopic, ...] = ()
    unresolved_reference: str = ""

    @property
    def has_active_topic(self) -> bool:
        """True when a current topic is established."""
        return bool(self.active_topic)

    @property
    def prior_topics(self) -> tuple[WorldTopic, ...]:
        """Topics that are NOT the active one (bounded historical context)."""
        active_key = _key(self.active_topic)
        return tuple(
            topic for topic in self.topics if _key(topic.label) != active_key
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "active_topic": self.active_topic,
            "active_kind": self.active_kind,
            "turn_index": self.turn_index,
            "topics": [topic.to_dict() for topic in self.topics],
            "unresolved_reference": self.unresolved_reference,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["ConversationWorld"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        topics: list[WorldTopic] = []
        raw_topics = data.get("topics")
        if isinstance(raw_topics, (list, tuple)):
            for item in raw_topics:
                topic = item if isinstance(item, WorldTopic) else WorldTopic.from_dict(item)
                if topic is not None:
                    topics.append(topic)
        return cls(
            active_topic=_bounded(data.get("active_topic"), _MAX_TOPIC_CHARS),
            active_kind=_bounded(data.get("active_kind"), _MAX_KIND_CHARS),
            turn_index=_bounded_turn(data.get("turn_index")),
            topics=tuple(topics)[:MAX_WORLD_TOPICS],
            unresolved_reference=_bounded(
                data.get("unresolved_reference"), _MAX_REFERENCE_CHARS
            ),
        )


def _rebuild(
    world: ConversationWorld,
    *,
    active_label: str,
    active_kind: str,
    turn_index: int,
    extra: Optional[WorldTopic] = None,
) -> tuple[WorldTopic, ...]:
    """Return the bounded topic tuple with ``active_label`` active.

    Every other ACTIVE topic becomes ``superseded`` (history preserved). A
    topic with the same normalized label is not duplicated: its kind, status and
    result reference are refreshed in place. ``extra`` prepends a topic that is
    not yet present (used when establishing a brand-new topic from a context
    that has no stored label, e.g. a knowledge query).
    """
    active_key = _key(active_label)
    rebuilt: list[WorldTopic] = []
    seen: set[str] = set()
    prepended = False
    for topic in world.topics:
        key = _key(topic.label)
        if not key or key in seen:
            continue
        if key == active_key:
            seen.add(key)
            rebuilt.insert(
                0,
                replace(
                    topic,
                    kind=active_kind or topic.kind,
                    turn_index=turn_index,
                    status=STATUS_ACTIVE,
                ),
            )
            prepended = True
            continue
        seen.add(key)
        if topic.status == STATUS_ACTIVE:
            rebuilt.append(replace(topic, status=STATUS_SUPERSEDED))
        else:
            rebuilt.append(topic)
    if not prepended and active_label:
        rebuilt.insert(
            0,
            WorldTopic(
                label=active_label,
                kind=active_kind or "objective",
                turn_index=turn_index,
                status=STATUS_ACTIVE,
                result_ref=extra.result_ref if extra is not None else "",
            ),
        )
    elif prepended and extra is not None:
        # Refresh the active topic's result reference when one is supplied.
        rebuilt[0] = replace(rebuilt[0], result_ref=extra.result_ref)
    return tuple(rebuilt[:MAX_WORLD_TOPICS])


def observe_topic(
    world: ConversationWorld,
    label: Any,
    kind: Any,
    *,
    result_ref: Any = "",
    turn_index: Any = 0,
) -> ConversationWorld:
    """Record a topic as the ACTIVE conversation topic (deterministic).

    Establishes ``label`` as the current topic. Any previously active topic is
    demoted to ``superseded`` and retained as bounded history. Re-observing the
    topic that is already active is a continuation (it just refreshes the
    result reference), not a new topic. A blank label is ignored (fail closed).
    """
    text = _bounded(label, _MAX_TOPIC_CHARS)
    if not text:
        return world
    kind_text = _bounded(kind, _MAX_KIND_CHARS) or "objective"
    result = _bounded(result_ref, _MAX_RESULT_REF_CHARS)
    index = _bounded_turn(turn_index)
    topics = _rebuild(
        world,
        active_label=text,
        active_kind=kind_text,
        turn_index=index,
        extra=WorldTopic(label=text, kind=kind_text, result_ref=result),
    )
    return replace(
        world,
        active_topic=text,
        active_kind=kind_text,
        turn_index=index,
        topics=topics,
        unresolved_reference="",
    )


def match_topics(world: ConversationWorld, query: Any) -> tuple[WorldTopic, ...]:
    """Return the bounded topics whose label matches ``query`` (deterministic).

    A match is normalized equality or bounded containment (the query names the
    topic, or the topic names the query). The whole ACTIVE topic is matched too,
    so a return to the current topic is representable. Never fuzzy, never
    semantic: a short/blank query matches nothing (fail closed).
    """
    query_key = _key(query)
    if len(query_key) < 3:
        return ()
    matches: list[WorldTopic] = []
    seen: set[str] = set()
    for topic in world.topics:
        key = _key(topic.label)
        if not key or key in seen:
            continue
        if query_key == key or query_key in key or key in query_key:
            seen.add(key)
            matches.append(topic)
    return tuple(matches)


def reactivate_topic(world: ConversationWorld, query: Any) -> Optional[ConversationWorld]:
    """Return a world with a PRIOR topic made ACTIVE again, or ``None``.

    Fails closed (``None``) unless exactly one topic matches, so two distinct
    candidate topics never collapse into one another without evidence. The
    previously active topic is demoted to ``superseded`` — history is preserved,
    not erased.
    """
    matches = match_topics(world, query)
    if len(matches) != 1:
        return None
    target = matches[0]
    target_key = _key(target.label)
    topics: list[WorldTopic] = []
    for topic in world.topics:
        key = _key(topic.label)
        if key == target_key:
            topics.append(replace(topic, status=STATUS_ACTIVE))
        elif topic.status == STATUS_ACTIVE:
            topics.append(replace(topic, status=STATUS_SUPERSEDED))
        else:
            topics.append(topic)
    return replace(
        world,
        active_topic=target.label,
        active_kind=target.kind,
        turn_index=world.turn_index,
        topics=tuple(topics[:MAX_WORLD_TOPICS]),
        unresolved_reference="",
    )


def complete_topic(world: ConversationWorld, label: Any) -> ConversationWorld:
    """Mark a topic COMPLETE (distinct from ACTIVE) without erasing history.

    A completed topic is no longer the active context; a new topic is not
    invented. A blank/unknown label is ignored (fail closed).
    """
    key = _key(label)
    if not key:
        return world
    topics: list[WorldTopic] = []
    completed_active = False
    for topic in world.topics:
        if _key(topic.label) == key:
            topics.append(replace(topic, status=STATUS_COMPLETED))
            completed_active = True
        else:
            topics.append(topic)
    if not completed_active:
        return world
    fields: dict[str, Any] = {"topics": tuple(topics[:MAX_WORLD_TOPICS])}
    if _key(world.active_topic) == key:
        fields["active_topic"] = ""
        fields["active_kind"] = ""
    return replace(world, **fields)


def mark_unresolved_reference(world: ConversationWorld, text: Any) -> ConversationWorld:
    """Record the most recent reference Atlas could not resolve.

    Kept so an unresolved reference stays visibly unresolved across turns; the
    active topic is NOT changed (an unresolved reference never becomes a topic).
    """
    reference = _bounded(text, _MAX_REFERENCE_CHARS)
    if not reference:
        return world
    return replace(world, unresolved_reference=reference)
