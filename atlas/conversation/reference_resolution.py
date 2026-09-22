"""Atlas Conversation — Reference Resolution (P9.3).

Deterministic, conservative resolution of conversational references such as
"that problem", "that task", "run it again", "what did you find?" against the
structured :class:`ConversationState` established by P9.1/P9.2.

Core safety invariant::

    AMBIGUITY -> CLARIFICATION. NEVER GUESS.

The resolver NEVER uses an LLM, NEVER performs semantic guessing, and NEVER
silently selects one candidate when multiple plausible referents exist.

Resolution statuses:
  - RESOLVED   -> exactly one valid referent
  - UNRESOLVED -> no valid referent
  - AMBIGUOUS  -> more than one plausible referent

This module is side-effect free, authorization-independent, and
execution-independent. It produces only structured information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.normalization import (
    canonicalize_surface,
    collapse_whitespace,
)

if TYPE_CHECKING:
    from atlas.conversation.conversation_context import ConversationContext


#: Precompiled word-boundary patterns per reference phrase. Matching is
#: WORD-BOUNDARY based (not substring), so triggers such as ``it`` can never
#: match inside ordinary words (``priority``, ``architecture``, ``quality``,
#: ``repository``) and ``again`` can never match inside ``against``.
_PHRASE_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Return the deterministic word-boundary pattern for one phrase."""
    pattern = _PHRASE_PATTERN_CACHE.get(phrase)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b")
        _PHRASE_PATTERN_CACHE[phrase] = pattern
    return pattern


def has_bounded_reference(text: str) -> bool:
    """True when ``text`` contains a recognized MULTI-WORD reference phrase.

    Bounded detection guard for the production turn flow: only multi-word
    phrases (e.g. ``"that investigation"``, ``"what did you find"``) qualify,
    so bare single-word triggers (``it``/``that``/``this``/``again``/
    ``continue``) can never cause unsafe universal invocation on ordinary
    turns. Deterministic; no NLP; no inference.
    """
    if not isinstance(text, str) or not text:
        return False
    normalized = canonicalize_surface(text).lower()
    if not normalized:
        return False
    for phrases, _fields, _category in _REFERENCE_PATTERNS:
        for phrase in phrases:
            if " " not in phrase:
                continue
            if _phrase_pattern(phrase).search(normalized):
                return True
    return False


# ---------------------------------------------------------------------------
# Repeat / re-check requests (bounded, WHOLE-TURN).
#
# A repeat request refers to the most recent GOVERNED OPERATION, not to a
# subject or a result. Recognition is deliberately anchored to the whole turn
# so an incidental "again" inside an ordinary sentence can never become a
# repeat command. This layer only recognizes the form: the operation KIND is
# never inferred from the verb here — the caller resolves it from the retained
# operation record.
# ---------------------------------------------------------------------------

_REPEAT_REQUEST_RE = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"(?:check|do|run|repeat|investigate)\s+(?:that|this|it)(?:\s+again)?"
    r"|again"
    r")\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def is_repeat_request(text: str) -> bool:
    """True when the WHOLE turn is a bounded repeat/re-check request.

    Matches only the enumerated verbs (``check``/``do``/``run``/``repeat``/
    ``investigate``) followed by ``that``/``this``/``it`` (optionally followed
    by ``again``), or a bare ``again``. Anchored to the whole turn, so ordinary
    uses of "again" within a larger sentence are never repeat commands.
    Deterministic; no NLP, no inference.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    return _REPEAT_REQUEST_RE.match(canonicalize_surface(text)) is not None


class ReferenceResolutionStatus(str, Enum):
    """Outcome of attempting to resolve a conversational reference."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ReferenceResolutionResult:
    """Immutable result of a reference-resolution attempt.

    Carries enough structure for a caller to generate a clarification request
    without guessing.
    """

    status: ReferenceResolutionStatus
    query: str
    resolved_field: Optional[str] = None
    resolved_value: Optional[str] = None
    candidates: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "status": self.status.value,
            "query": self.query,
            "resolved_field": self.resolved_field,
            "resolved_value": self.resolved_value,
            "candidates": list(self.candidates),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Reference patterns: (trigger_phrases, candidate_fields, category_name)
#
# CRITICAL: patterns are sorted by longest phrase length (descending) so that
# multi-word phrases ("that investigation") are checked before single-word
# substrings ("that"). Without this, "that" would greedily match first and
# misclassify "that investigation" as a subject reference.
# ---------------------------------------------------------------------------

_REFERENCE_PATTERNS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    # "what you found" may refer to investigation or result
    (
        ("what you just found", "what did you find", "what you found"),
        ("current_investigation", "latest_result"),
        "findings",
    ),
    # Continuation references
    (
        ("continue with that", "continue"),
        ("current_task", "current_investigation", "development_intent"),
        "continuation",
    ),
    # Action references (repeat/again)
    (
        ("do that again", "run it again", "repeat that", "again"),
        ("current_task", "relevant_prior_action"),
        "action",
    ),
    # Investigation references
    (
        ("this investigation", "that investigation", "the investigation"),
        ("current_investigation",),
        "investigation",
    ),
    # Subject references (multi-word first)
    (
        ("this topic", "that topic", "this issue", "that issue", "the problem"),
        ("current_subject",),
        "subject",
    ),
    # Task references
    (
        ("this task", "that task", "the task"),
        ("current_task",),
        "task",
    ),
    # Result references. The qualifier aliases ("previous result" / "last
    # result" / "prior result") are BOUNDED ALIASES to the single retained
    # ``latest_result``: Atlas keeps exactly one result in
    # ``ConversationState``, so these phrases express no genuine historical
    # ordering and select no older result. They resolve only when
    # ``latest_result`` is set and stay UNRESOLVED otherwise (fail closed).
    # This is deliberate coverage, not result-history semantics — revisit only
    # if result history is ever introduced.
    (
        (
            "that result",
            "the result",
            "the findings",
            "previous result",
            "last result",
            "prior result",
        ),
        ("latest_result",),
        "result",
    ),
    # Development intent references
    (
        ("that improvement", "the development"),
        ("development_intent",),
        "development",
    ),
    # Pending question
    (
        ("the question", "my question"),
        ("pending_question",),
        "question",
    ),
    # Pending confirmation
    (
        ("that confirmation", "the confirmation"),
        ("pending_confirmation",),
        "confirmation",
    ),
    # "it" resolves only to the active task (conservative, single-word last)
    (
        ("it",),
        ("current_task",),
        "task",
    ),
    # Single-word subject triggers (checked last — most generic)
    (
        ("this", "that"),
        ("current_subject",),
        "subject",
    ),
)


# ---------------------------------------------------------------------------
# Phase 4 — bounded contextual reference resolution.
#
# References resolve against the bounded ConversationContext (recent USER
# turns) plus the structured ConversationState. Candidates are *investigation
# subjects* only: an explicitly set ``state.current_investigation`` and recent
# USER turns carrying an explicit investigation lead cue. Nothing else is a
# candidate, so a bare "it"/"that"/"this" can never resolve merely because some
# previous turn exists.
#
# L5 adds a bounded, lower-precedence candidate source: facts established
# explicitly in an earlier turn — the subject recorded deterministically by L4
# entity identification (``current_subject``) and the development intent
# retained for a completed development request (``development_intent``). These
# are consulted only when no investigation-derived candidate exists, so they
# never override one and a bare pronoun still cannot resolve from the mere
# existence of a previous turn.
#
# Deterministic and fail-closed: exactly one distinct candidate -> RESOLVED;
# more than one -> AMBIGUOUS; none -> UNRESOLVED. Never guesses — two distinct
# established facts are genuinely ambiguous and force clarification rather than
# one silently winning.
# ---------------------------------------------------------------------------

#: Bounded lead cues that mark a prior USER turn as an investigation subject.
_SUBJECT_LEAD_RE = re.compile(
    r"\b(?:investigate|investigation|analyze|analyse|diagnose|inspect"
    r"|examine|trace|debug)\b"
)

#: Bounded explicit contextual reference form: "the <phrase>" (1..6 words).
_EXPLICIT_CONTEXT_RE = re.compile(
    r"\bthe\s+([a-z0-9][a-z0-9_-]*(?:\s+[a-z0-9][a-z0-9_-]*){0,5})"
)

#: Bounded bare demonstrative/pronoun reference (one word, optionally followed
#: by one generic noun). Never resolved on its own.
_BARE_REFERENCE_RE = re.compile(
    r"\b(?:it|that|this)"
    r"(?:\s+(?:issue|problem|subject|topic|one|investigation|result|task|thing))?\b"
)

#: Field label reported for a context-derived referent.
_CONTEXT_SUBJECT_FIELD = "context_subject"

#: Field label reported for the explicitly established subject fallback.
_ESTABLISHED_SUBJECT_FIELD = "current_subject"

#: Field label reported when the contextual referent is the investigation
#: subject ACTUALLY STORED in ``ConversationState.current_investigation``.
#: Reporting the real state field (rather than the derived
#: ``context_subject`` label) is what makes the result consumable by the
#: existing reference-restatement path.
_STATE_INVESTIGATION_FIELD = "current_investigation"

#: Field label reported for the established development-intent fallback.
_ESTABLISHED_DEVELOPMENT_INTENT_FIELD = "development_intent"

#: Maximum distinct contextual subject candidates considered.
_MAX_CONTEXT_SUBJECTS = 8


def _subject_key(text: str) -> str:
    """Normalized comparison key (case/punctuation/whitespace insensitive)."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _context_subject_candidates(
    context: Any,
    state: ConversationState | None,
    query: str,
) -> tuple[tuple[str, str], ...]:
    """Return distinct bounded investigation-subject candidates.

    Each candidate is returned as ``(field, text)``. A subject that comes from
    an ACTUAL ``ConversationState`` field is reported under that real field name
    (``current_investigation``) so the bounded result stays consumable; a
    subject derived from a recent USER turn has no stored state fact and keeps
    the derived ``context_subject`` label. The current turn (whose text matches
    ``query``) is excluded, so a turn can never resolve to itself. Deterministic
    order; bounded count.
    """
    query_key = _subject_key(query)
    candidates: list[tuple[str, str]] = []

    def _add(field: str, value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text and _subject_key(text) != query_key:
                candidates.append((field, text))

    if state is not None:
        _add(
            _STATE_INVESTIGATION_FIELD,
            getattr(state, "current_investigation", None),
        )

    for turn in getattr(context, "recent_turns", ()) or ():
        if getattr(turn, "role", "") != "user":
            continue
        content = getattr(turn, "content", "")
        if isinstance(content, str) and _SUBJECT_LEAD_RE.search(content.lower()):
            _add(_CONTEXT_SUBJECT_FIELD, content)

    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in candidates:
        key = _subject_key(pair[1])
        if key and key not in seen:
            seen.add(key)
            ordered.append(pair)
    return tuple(ordered[:_MAX_CONTEXT_SUBJECTS])


def _resolved_field(pairs: tuple[tuple[str, str], ...], default: str) -> str:
    """Return the single stored-state field name for ``pairs``, else ``default``.

    A contextual referent that came from one actual ``ConversationState`` field
    is reported under that REAL field name. Derived turn-based referents and
    mixed candidate sets (which resolve AMBIGUOUS anyway) keep the bounded
    ``context_subject`` label.
    """
    fields = {field for field, _text in pairs}
    if len(fields) == 1 and pairs:
        return pairs[0][0]
    return default


def _established_facts(
    state: ConversationState | None,
    query: str,
) -> tuple[tuple[str, str], ...]:
    """Return the explicitly established state facts, as ``(field, text)`` (L5).

    Last-resort bounded source: facts recorded deterministically in an earlier
    turn — ``ConversationState.current_subject`` (L4 entity identification) and
    ``ConversationState.development_intent`` (a development request that
    completed in an earlier turn). Consulted only when no investigation-derived
    candidate exists, so it can never override one, and it never resolves a
    turn to itself.

    Deterministic field order, bounded count. Absent, blank, non-string, or
    self-matching facts are skipped — fail closed, never guess. Two distinct
    established facts are returned as two candidates, so the caller's existing
    exactly-one contract yields AMBIGUOUS (clarification) rather than silently
    preferring one.
    """
    if state is None:
        return ()
    facts: list[tuple[str, str]] = []
    for field_name in (
        _ESTABLISHED_SUBJECT_FIELD,
        _ESTABLISHED_DEVELOPMENT_INTENT_FIELD,
    ):
        value = getattr(state, field_name, None)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or _subject_key(text) == _subject_key(query):
            continue
        facts.append((field_name, text))
    return tuple(facts)


class ConversationReferenceResolver:
    """Deterministic resolver of conversational references against state.

    Side-effect free: never mutates the supplied :class:`ConversationState`.
    """

    def resolve(
        self,
        query: str,
        state: ConversationState,
    ) -> ReferenceResolutionResult:
        """Resolve a conversational reference against structured state.

        Args:
            query: the raw reference phrase (e.g. "run it again").
            state: the current :class:`ConversationState`.

        Returns:
            A structured :class:`ReferenceResolutionResult`.
        """
        normalized = canonicalize_surface(query).lower()

        # Find the first matching reference pattern.
        matched_fields: Optional[tuple[str, ...]] = None
        category: str = "unknown"
        for phrases, fields, cat in _REFERENCE_PATTERNS:
            if any(_phrase_pattern(phrase).search(normalized) for phrase in phrases):
                matched_fields = fields
                category = cat
                break

        if matched_fields is None:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.UNRESOLVED,
                query=query,
                reason=f"Unrecognized reference: no pattern matches {query!r}.",
            )

        # Collect candidate fields that have a value in the current state.
        candidates = [
            f for f in matched_fields if getattr(state, f) is not None
        ]

        if len(candidates) == 0:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.UNRESOLVED,
                query=query,
                reason=f"No active {category} found in current state.",
            )

        if len(candidates) == 1:
            field = candidates[0]
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.RESOLVED,
                query=query,
                resolved_field=field,
                resolved_value=getattr(state, field),
                reason=f"Unique {category} referent resolved to {field}.",
            )

        # Multiple plausible referents -> ambiguous, never guess.
        return ReferenceResolutionResult(
            status=ReferenceResolutionStatus.AMBIGUOUS,
            query=query,
            candidates=tuple(candidates),
            reason=(
                f"Multiple plausible {category} referents: "
                f"{', '.join(candidates)}. Clarification required."
            ),
        )

    def resolve_contextual(
        self,
        query: str,
        context: ConversationContext | None,
        state: ConversationState | None = None,
    ) -> ReferenceResolutionResult:
        """Resolve a bounded contextual reference against recent context.

        Recognizes only two bounded forms:

          * explicit ``the <phrase>`` references, matched by word-boundary
            containment against the candidate subjects;
          * bare demonstrative/pronoun references (``it``/``that``/``this``,
            optionally with one generic noun), matched only against the
            candidate subjects.

        Exactly one matching candidate -> RESOLVED. Multiple -> AMBIGUOUS.
        None -> UNRESOLVED. The resolver never guesses, never mutates the
        supplied context/state, and never executes anything.

        L5 bounded carry-forward: when no investigation-derived candidate
        exists, the facts established explicitly in an earlier turn
        (``ConversationState.current_subject`` and, for a development request
        that completed in an earlier turn, ``ConversationState
        .development_intent``) are used as fallback candidates, so a follow-up
        referring back to one of them resolves deterministically.
        Investigation candidates always keep precedence, a single established
        fact is still exactly one candidate, and two distinct established facts
        remain AMBIGUOUS — the fail-closed contract is unchanged.
        """
        normalized = canonicalize_surface(query).lower()
        if not normalized:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.UNRESOLVED,
                query=query,
                reason="Empty contextual reference query.",
            )

        pairs = _context_subject_candidates(context, state, query)
        referent_field = _CONTEXT_SUBJECT_FIELD
        if not pairs:
            established = _established_facts(state, query)
            if len(established) == 1:
                referent_field, text = established[0]
                pairs = ((referent_field, text),)
            elif len(established) > 1:
                # Two distinct established facts are genuinely ambiguous: the
                # existing exactly-one contract below yields AMBIGUOUS, so
                # clarification is requested instead of one silently winning.
                pairs = established

        explicit = _EXPLICIT_CONTEXT_RE.search(normalized)
        if explicit is not None:
            phrase = explicit.group(1).strip()
            if phrase:
                matches = tuple(
                    pair
                    for pair in pairs
                    if _phrase_pattern(phrase).search(
                        collapse_whitespace(pair[1]).lower()
                    )
                )
                return self._context_result(
                    query,
                    tuple(text for _field, text in matches),
                    f"the {phrase}",
                    _resolved_field(matches, referent_field),
                )

        if _BARE_REFERENCE_RE.search(normalized):
            return self._context_result(
                query,
                tuple(text for _field, text in pairs),
                normalized,
                _resolved_field(pairs, referent_field),
            )

        return ReferenceResolutionResult(
            status=ReferenceResolutionStatus.UNRESOLVED,
            query=query,
            reason=f"Unrecognized contextual reference: {query!r}.",
        )

    @staticmethod
    def _context_result(
        query: str,
        matches: tuple[str, ...],
        label: str,
        field: str = _CONTEXT_SUBJECT_FIELD,
    ) -> ReferenceResolutionResult:
        """Build a fail-closed result for a tuple of candidate matches."""
        if len(matches) == 1:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.RESOLVED,
                query=query,
                resolved_field=field,
                resolved_value=matches[0],
                reason=f"Unique contextual referent resolved for {label!r}.",
            )
        if len(matches) > 1:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.AMBIGUOUS,
                query=query,
                candidates=tuple(matches),
                reason=(
                    f"Multiple plausible contextual referents for {label!r}: "
                    f"{', '.join(matches)}. Clarification required."
                ),
            )
        return ReferenceResolutionResult(
            status=ReferenceResolutionStatus.UNRESOLVED,
            query=query,
            reason=f"No active contextual referent found for {label!r}.",
        )
