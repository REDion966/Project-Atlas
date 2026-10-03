"""Atlas Conversation — communicative function + context-aware routing (Stage 4).

The layer that distinguishes WHAT THE USER IS DOING from WHAT THE USER IS TALKING
ABOUT. It determines a bounded **communicative function** for a turn (from the
EXISTING interpretation evidence — the shared lexicon, the L3 utterance meaning
and the semantic frame) and then, where the function is a query about prior
output, resolves a bounded **target** against the Stage 3
:class:`~atlas.conversation.discourse_state.DiscourseState` referents.

The central distinction: the noun "investigation" (a TOPIC) must never by itself
select the "start an investigation" FUNCTION. "Can you explain the result of the
investigation you just completed?" is a QUERY about an existing result, not a new
operation request — even though the word "investigation" appears.

Boundaries (mandatory):

  * Representation only — the function and the routing decision DESCRIBE what the
    turn appears to be doing. They authorize nothing: ``REQUEST_OPERATION`` does
    NOT mean approved/authorized/executable. Governance is unchanged.
  * Deterministic and model-independent — standard library plus the EXISTING
    lexicon / clarification matchers. No clock, no randomness, no I/O, no model,
    no embeddings, no second parser.
  * Fail-closed — an unresolved/ambiguous target is reported (clarification),
    never guessed.
  * Bounded and JSON-safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from atlas.conversation import discourse_state as _ds
from atlas.conversation import salience as _salience
from atlas.conversation.clarification import candidate_matches
from atlas.conversation.lexicon import tokens

#: Bounded communicative-function vocabulary justified by the current failures.
FUNCTION_REQUEST_OPERATION: str = "request_operation"
FUNCTION_QUERY_RESULT: str = "query_result"
FUNCTION_QUERY_CAUSE: str = "query_cause"
FUNCTION_QUERY_STATUS: str = "query_status"
#: A COMPARISON of recorded results ("compare this with what you found earlier").
#: Bounded: it consumes the same discourse referents as the other queries.
FUNCTION_COMPARE: str = "query_comparison"
#: A relation QUESTION ("does A relate to B?"). Deliberately NOT in
#: ``QUERY_FUNCTIONS``: it is answered by its own bounded consumer from RECORDED
#: direct edges, never by the single-target contextual result route.
FUNCTION_RELATION: str = "query_relation"
FUNCTION_UNKNOWN: str = "unknown"

FUNCTIONS: frozenset[str] = frozenset(
    {
        FUNCTION_REQUEST_OPERATION,
        FUNCTION_QUERY_RESULT,
        FUNCTION_QUERY_CAUSE,
        FUNCTION_QUERY_STATUS,
        FUNCTION_COMPARE,
        FUNCTION_RELATION,
        FUNCTION_UNKNOWN,
    }
)

#: The functions that ask about prior output and therefore consume referents.
QUERY_FUNCTIONS: frozenset[str] = frozenset(
    {
        FUNCTION_QUERY_RESULT,
        FUNCTION_QUERY_CAUSE,
        FUNCTION_QUERY_STATUS,
        FUNCTION_COMPARE,
    }
)

#: A bounded RELATION question ("does A relate to B?"). Recognized so the turn is
#: represented explicitly for routing; the wording itself never decides an answer.
_RELATION_QUERY_RE = re.compile(
    r"^\s*(?:and\s+)?does\s+(?P<a>.{2,60}?)\s+relate\s+(?:to|with)\s+"
    r"(?P<b>.{2,60}?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)


def relation_query_parts(text: Any) -> tuple[str, str] | None:
    """Return ``(a, b)`` for a bounded relation question, else ``None``.

    Bounded and whole-turn anchored, so a generic architectural "relate" usage
    ("how do the modules relate to each other?") never enters this route.
    """
    if not isinstance(text, str):
        return None
    match = _RELATION_QUERY_RE.match(text)
    if match is None:
        return None
    a = match.group("a").strip()
    b = match.group("b").strip()
    if not a or not b:
        return None
    return (a, b)


#: The L3 operation value that marks a request to COMPARE recorded results.
_COMPARE_OP: str = "compare"

#: P2-4 — bounded CONTEXTUAL COMPARISON vocabulary. A comparison whose operands
#: are anaphoric/contextual ("that", "the previous result", "what we had before")
#: resolves against RECORDED referents; a comparison naming external subjects
#: ("compare the S26 and the iPhone") is NOT matched by the anaphor gate below and
#: keeps its existing route.
_COMPARE_CONTEXT_RE = re.compile(
    r"\b(?:compare|comparison|comparing|differ|differs|differed|difference|"
    r"differences|different)\b",
    re.IGNORECASE,
)
_COMPARE_ANAPHOR_RE = re.compile(
    r"\b(?:that|this|those|these|previous|prior|last|former|earlier|"
    r"what\s+we\s+had|what\s+we've\s+had)\b",
    re.IGNORECASE,
)

#: G1.1 — a bounded EXPLANATION request whose whole object is a bare anaphor
#: ("can you explain that?"). The object is supplied by the existing reference/
#: state machinery, so the turn is a query about the retained result.
_EXPLAIN_ANAPHOR_RE = re.compile(
    r"^\s*(?:can|could|would|will)\s+you\s+(?:please\s+)?explain\s+"
    r"(?:that|it|this|those|these|them)\s*[.?]*\s*$",
    re.IGNORECASE,
)

#: P2-2 — bounded RESULT-GROUNDED ELABORATION / SIMPLIFICATION requests
#: ("can you explain that more simply?", "explain that in simpler terms",
#: "can you clarify that?", "what does that mean?", "can you elaborate on that?").
#: Each form refers to a PRIOR output through a bare anaphor (or an explicit
#: simplification phrase), so it is a query about the RETAINED result. A named
#: object ("explain the memory service") is deliberately NOT matched.
_ELABORATION_RE = re.compile(
    r"\b(?:explain|clarify|elaborate|simplify|rephrase|restate)\b[^.?!]{0,40}"
    r"\b(?:simpl(?:e|er|y)|plain(?:ly)?|plain\s+terms|simpler\s+terms|"
    r"more\s+simply|in\s+other\s+words)\b"
    r"|\bwhat\s+(?:does|did)\s+(?:that|this|it)\s+mean\b"
    r"|\bwhat\s+do\s+you\s+mean\s+by\s+(?:that|this|it)\b"
    r"|\b(?:can|could|would)\s+you\s+(?:please\s+)?(?:elaborate|clarify|simplify|"
    r"rephrase|restate)(?:\s+on)?\s+(?:that|this|it)\b"
    r"|\b(?:elaborate|expand)\s+(?:on\s+)?(?:that|this|it)\b"
    r"|\b(?:clarify|simplify|rephrase|restate)\s+(?:that|this|it)\b",
    re.IGNORECASE,
)

#: P3 — a bounded IMPERATIVE result-request ("tell me what you find/found"). It is
#: the same retrieval as "what did you find?" (a query about prior output), so it
#: must reach the EXISTING retained-result route; with no retained result the route
#: fails closed rather than inventing one.
#: Whole-turn anchored: a bounded leading filler ("just", "please", "okay,") is
#: allowed, but the request must BE the turn — so it never matches a clause inside
#: a compound ("Investigate X and tell me what you find.").
_RESULT_REQUEST_RE = re.compile(
    r"^\s*(?:just\s+|please\s+|ok(?:ay)?[,\s]+|alright[,\s]+|so\s+|and\s+)*"
    r"(?:tell|show|give)\s+me\s+what\s+(?:you|we)\s+(?:just\s+)?"
    r"(?:find|found|learn|learned|learnt|discover|discovered|conclude|concluded|"
    r"get|got|produce|produced|see|saw)\b[.?!\s]*$",
    re.IGNORECASE,
)

#: Output nouns that orient a question/explain request at an existing result.
#: Deliberately excludes broad words ("output", "produce") that describe an
#: arbitrary object rather than a PRIOR operation's produced result.
_RESULT_NOUNS: frozenset[str] = frozenset(
    {
        "result", "results", "finding", "findings", "outcome", "outcomes",
        "conclusion", "conclusions", "diagnosis", "summary", "summaries",
        "report", "reports",
    }
)

#: Retrospective verbs: the turn asks what a PRIOR operation produced/did.
_RETROSPECTIVE_VERBS: frozenset[str] = frozenset(
    {
        "find", "found", "learn", "learned", "learnt", "produce", "produced",
        "show", "showed", "shown", "conclude", "concluded", "discover",
        "discovered", "happen", "happened", "result", "resulted", "change",
        "changed", "come", "came", "turn", "turned", "yield", "yielded",
    }
)

#: Retrospective cause words.
_CAUSE_WORDS: frozenset[str] = frozenset({"why", "cause", "because"})

#: The L3 operation value that marks a request to EXPLAIN something.
_EXPLAIN_OP: str = "explain"

#: L3 operation values that, as an IMPERATIVE, direct a NEW operation.
_NEW_OPERATION_OPS: frozenset[str] = frozenset(
    {"investigate", "develop", "act", "research"}
)

#: A bounded POLITE REQUEST wrapper. The interrogative form of an operation
#: request ("Can you investigate X?", "Could you develop a plan for Y?") is a
#: REQUEST, not a question ABOUT a past occurrence, so it must not be excluded
#: from the operation-request function merely by its trailing "?".
_POLITE_REQUEST_RE = re.compile(
    r"^\s*(?:can|could|would|will|please)\s+you\b", re.IGNORECASE
)

#: Question AUXILIARIES that open a question ABOUT a past occurrence
#: ("Did you investigate X?", "Has X been investigated?"). They must never
#: select the operation-request function, so the leading-operation-verb
#: discriminator below can be read from the order.
_QUESTION_AUXILIARIES: frozenset[str] = frozenset(
    {
        "do", "did", "does", "done", "has", "have", "had", "was", "were",
        "is", "are", "am", "be", "been", "being", "will", "would", "can",
        "could", "should", "shall", "may", "might", "must", "what", "which",
        "who", "when", "where", "why", "how",
    }
)

#: Explicit target extraction: an output/operation noun bound to a name by a
#: preposition ("the result of the memory router investigation"). Bounded regex
#: over the existing noun vocabulary — no general parsing.
_EXPLICIT_TARGET_RE = re.compile(
    r"\b(?:result|results|finding|findings|outcome|outcomes|conclusion|"
    r"conclusions|summary|summaries|report|reports|diagnosis|investigation|"
    r"investigations|operation|operations|research|analysis|study|studies|work)"
    r"\b\s+(?:of|for|about|from)\s+(?P<target>.+?)\s*[.?!]*$",
    re.IGNORECASE,
)

_MAX_LABEL_CHARS: int = 200

#: Deictic/retrospective markers. A target phrase carrying one of these is a
#: DEFINITE DESCRIPTION of the recent operation ("the investigation you just
#: completed", "that investigation"), not a NAME, so it resolves to the latest
#: result rather than to a named referent.
_DEICTIC_WORDS: frozenset[str] = frozenset(
    {
        "you", "your", "yours", "we", "our", "i", "my", "it", "its",
        "just", "now", "recent", "recently", "current", "currently", "new",
        "that", "this", "these", "those", "last", "latest", "previous", "prior",
        "former", "earlier", "above", "before", "one", "completed", "complete",
        "finished", "finally", "again",
    }
)


def _bounded(value: Any, limit: int = _MAX_LABEL_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _explicit_target(text: Any) -> str:
    """Return the bounded named target of an output/operation phrase, or ``""``."""
    if not isinstance(text, str):
        return ""
    match = _EXPLICIT_TARGET_RE.search(text)
    return _bounded(match.group("target"), _MAX_LABEL_CHARS) if match else ""


#: Bounded NAMED-TOPIC follow-up forms ("what about X?", "and X?", "regarding X",
#: "about X") that name a PRIOR referent without a result/operation noun.
_TOPIC_FOLLOWUP_RE = re.compile(
    r"^\s*(?:and\s+|what\s+about\s+|how\s+about\s+|regarding\s+|about\s+)"
    r"(?P<target>.+?)\s*[.?!]*\s*$",
    re.IGNORECASE,
)
_MAX_FOLLOWUP_TARGET_TOKENS: int = 8
_MAX_FOLLOWUP_TARGET_CHARS: int = 120


def _named_follow_up_target(text: Any) -> str:
    """Return the bounded target of a short topic follow-up, or ``""``.

    Only a SHORT phrase counts (a sentence is never a named topic), so the form
    can never swallow a full request.
    """
    if not isinstance(text, str):
        return ""
    match = _TOPIC_FOLLOWUP_RE.match(text.strip())
    if match is None:
        return ""
    target = match.group("target").strip()[:_MAX_FOLLOWUP_TARGET_CHARS]
    if not target or len(tokens(target)) > _MAX_FOLLOWUP_TARGET_TOKENS:
        return ""
    return target


def classify_function(
    text: Any,
    *,
    illocution: str = "",
    operation: str = "",
) -> str:
    """Return the bounded communicative function of one turn (deterministic).

    Uses the EXISTING interpretation evidence only: the shared lexicon token
    classes, the L3 utterance ``illocution`` (question/request/statement) and the
    L3 leading ``operation`` (research/investigate/develop/act/explain/compare).
    It never re-parses the raw text and never consults a model.
    """
    if not isinstance(text, str) or not text.strip():
        return FUNCTION_UNKNOWN
    lemmas = frozenset(tokens(text))
    question = illocution == "question" or text.rstrip().endswith("?")
    # The cause cues are read from BOTH the lemma set and the raw surface words:
    # the noun "reason" is a cause cue, but the bounded lemmatizer folds
    # "reasoning"/"reasoned" onto it, and a subsystem named "reasoning" must not
    # turn an unrelated question into a cause query.
    raw_words = frozenset(re.findall(r"[a-z']+", text.lower()))
    why = bool(lemmas & _CAUSE_WORDS) or "reason" in raw_words
    result_noun = bool(lemmas & _RESULT_NOUNS)
    retrospective = bool(lemmas & _RETROSPECTIVE_VERBS)
    explain = operation == _EXPLAIN_OP

    # 0. A bounded RELATION question ("does A relate to B?") is its own function:
    #    it asks whether a RECORDED relationship exists between two targets and is
    #    never downgraded to a result query or a comparison.
    if _RELATION_QUERY_RE.match(text):
        return FUNCTION_RELATION

    # 1. A retrospective CAUSE question ("why did you investigate that?").
    if why and question:
        return FUNCTION_QUERY_CAUSE

    # 1b. A bounded NAMED-TOPIC follow-up ("what about X?", "and X?",
    #     "regarding X") that names no operation is a query about a prior
    #     referent — never a new operation.
    if not operation and _named_follow_up_target(text):
        return FUNCTION_QUERY_RESULT

    # 1c. A bounded EXPLANATION request whose whole object is a bare anaphor
    #     ("can you explain that?") asks about the RETAINED result. The L3
    #     operation ("explain") is preserved; the existing reference/state
    #     machinery supplies the target, and with no retained result the route
    #     fails closed rather than inventing one.
    if explain and _EXPLAIN_ANAPHOR_RE.search(text):
        return FUNCTION_QUERY_RESULT

    # 1c-bis. P2-2 — a bounded RESULT-GROUNDED ELABORATION / SIMPLIFICATION
    #     request ("explain that more simply", "what does that mean?") refers to
    #     the RETAINED result through a bare anaphor, so it is a query about prior
    #     output. A named object ("explain the memory service") is not matched.
    if _ELABORATION_RE.search(text):
        return FUNCTION_QUERY_RESULT

    # 1c-ter. P3 — a bounded IMPERATIVE result-request ("tell me what you find")
    #     is the same retrieval as "what did you find?" and reaches the same
    #     retained-result route (fail-closed when no result is retained).
    if _RESULT_REQUEST_RE.search(text):
        return FUNCTION_QUERY_RESULT

    # 1d. A COMPARISON request keeps its own bounded function: "compare this with
    #     what you found earlier" must not be downgraded to a single-result query
    #     by its retrospective wording ("found"). P2-4 extends the family with
    #     bounded CONTEXTUAL comparison forms whose operands are anaphoric
    #     ("what's different from what we had before?"); a comparison naming
    #     external subjects ("compare the S26 and the iPhone") is NOT matched by
    #     the anaphor gate and keeps its existing route.
    if operation == _COMPARE_OP or (
        _COMPARE_CONTEXT_RE.search(text) and _COMPARE_ANAPHOR_RE.search(text)
    ):
        return FUNCTION_COMPARE

    # 2. A question/explain request aimed at an OUTPUT. A turn that IMPERATIVELY
    #    directs a NEW operation is never a query, so operation-topic vocabulary
    #    ("investigation") cannot by itself select the query function.
    directs_new_operation = operation in ("investigate", "develop") and not question
    if not directs_new_operation:
        if result_noun and (question or explain or illocution == "request"):
            return FUNCTION_QUERY_RESULT
        if retrospective and (question or illocution == "request"):
            return FUNCTION_QUERY_RESULT

    # 3. An imperative that names an operation and directs it at a new object.
    if not question and operation in _NEW_OPERATION_OPS:
        return FUNCTION_REQUEST_OPERATION

    # 3b. A POLITE question form of the same request ("Can you investigate X?",
    #     "Investigate the cache layer?") still DIRECTS a new operation. The L3
    #     frame already owns the operation and a new objective, so only the
    #     interrogative wrapper differs. Bounded to an explicit request
    #     illocution, a leading polite auxiliary, or a LEADING operation verb
    #     that is not a question auxiliary — so a genuine question about a PAST
    #     occurrence ("Did you investigate the cache layer?", "Has X been
    #     investigated?") stays unknown instead of starting a second
    #     investigation.
    if (
        question
        and operation in _NEW_OPERATION_OPS
        and (
            illocution == "request"
            or _POLITE_REQUEST_RE.match(text)
            or _opens_with_the_operation(text)
        )
    ):
        return FUNCTION_REQUEST_OPERATION

    return FUNCTION_UNKNOWN


def _opens_with_the_operation(text: str) -> bool:
    """True when the turn's FIRST content token is its own operation verb.

    The bounded lemmatizer preserves order, so a direct operation request
    ("Investigate the cache layer?") is distinguishable from an interrogative
    question ABOUT an operation ("Did you investigate the cache layer?"), which
    always opens with a question auxiliary instead.
    """
    ordered = tokens(text)
    for token in ordered:
        if token in _QUESTION_AUXILIARIES:
            return False
        return token in _NEW_OPERATION_OPS
    return False


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """A bounded, inspectable, authority-free routing decision (Stage 4).

    Describes WHAT the turn appears to be asking (``communicative_function``) and
    WHICH existing referent/route that is applied to. It is descriptive only — it
    never authorizes, executes or approves anything.
    """

    communicative_function: str = FUNCTION_UNKNOWN
    target_kind: str = ""
    target_referent_id: str = ""
    target_label: str = ""
    route: str = "existing"
    clarification_required: bool = False
    candidates: tuple[str, ...] = ()
    reason: str = ""
    evidence: tuple[str, ...] = ()
    #: Stage 6 — the bounded salience/ambiguity assessment this decision was
    #: derived from (empty when the turn is not a contextual query). Descriptive
    #: only; it never grants authority.
    assessment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "communicative_function": self.communicative_function,
            "target_kind": self.target_kind,
            "target_referent_id": self.target_referent_id,
            "target_label": self.target_label,
            "route": self.route,
            "clarification_required": self.clarification_required,
            "candidates": list(self.candidates),
            "reason": self.reason,
            "evidence": list(self.evidence),
            "assessment": dict(self.assessment),
        }


def _produced_result(discourse: "_ds.DiscourseState | None", operation_id: str) -> Optional[_ds.Referent]:
    """Return the RESULT referent produced by ``operation_id``, or ``None``."""
    if discourse is None or not operation_id:
        return None
    for relation in discourse.relations:
        if relation.source_id != operation_id or relation.relation != _ds.REL_PRODUCED:
            continue
        referent = discourse.find(relation.target_id)
        if referent is not None and referent.kind == _ds.KIND_RESULT:
            return referent
    return None


def assess(
    text: Any,
    *,
    illocution: str = "",
    operation: str = "",
    discourse: "_ds.DiscourseState | None" = None,
) -> RoutingDecision:
    """Return the bounded routing decision for one turn (classify + resolve)."""
    return resolve_routing(
        text,
        classify_function(text, illocution=illocution, operation=operation),
        discourse,
    )


def resolve_routing(
    text: Any,
    function: str,
    discourse: "_ds.DiscourseState | None" = None,
    thread_state: Any = None,
) -> RoutingDecision:
    """Resolve the contextual target for an already-determined ``function``.

    Determines the contextual target against the Stage 3 referents, using the
    Stage 6 salience/ambiguity assessment. ``route`` is one of ``existing``
    (nothing to do — the existing cascade owns the turn), ``result`` (answer from
    the selected result/referent), ``clarify`` (ambiguous/unmatched target — fail
    closed) or ``fail_closed`` (a clear query with no supported candidate).
    """
    if function not in QUERY_FUNCTIONS:
        return RoutingDecision(
            communicative_function=function,
            route="existing",
            reason="not a contextual query about prior output",
            evidence=("function", function),
        )

    # 1d-comparison. A comparison consumes TWO recorded results and never falls
    # back to the single most recent one.
    if function == FUNCTION_COMPARE:
        return _compare_decision(function, discourse)

    explicit = _explicit_target(text)
    if explicit and (frozenset(tokens(explicit)) & _DEICTIC_WORDS):
        # A definite description of the RECENT operation ("the investigation you
        # just completed", "that investigation"), not a NAME.
        explicit = ""
    # Stage 10 — a bounded named-topic follow-up ("what about X?", "and X?",
    # "regarding X") names a prior referent without an output noun. It is a SOFT
    # explicit target: if nothing matches it, the turn falls through unchanged so
    # no unrelated "what about X?" turn is ever captured.
    named = _named_follow_up_target(text) if not explicit else ""
    target_phrase = explicit or named
    soft = bool(named) and not explicit

    if target_phrase:
        if discourse is None:
            if soft:
                return RoutingDecision(
                    communicative_function=function,
                    route="existing",
                    reason="named follow-up with no candidate set",
                    evidence=("named-follow-up",),
                )
            assessment = _salience.SalienceAssessment(
                status=_salience.STATUS_UNCERTAIN,
                reason="no candidate set is available",
            )
            return _clarify_decision(function, target_phrase, assessment)
        operations = [
            r
            for r in discourse.referents
            if r.kind == _ds.KIND_OPERATION and r.label
        ]
        hits = candidate_matches(target_phrase, [r.label for r in operations])
        matched = [r for r in operations if r.label in hits]
        assessment = _salience.assess_candidates(
            _salience.operation_candidates(
                discourse, tuple(r.referent_id for r in matched)
            ),
            explicit_target=target_phrase,
        )
        if assessment.status == _salience.STATUS_RESOLVED:
            operation_referent = next(
                (r for r in matched if r.referent_id == assessment.selected_referent_id),
                None,
            )
            if operation_referent is not None:
                result = _produced_result(discourse, operation_referent.referent_id)
                return RoutingDecision(
                    communicative_function=function,
                    target_kind="operation",
                    target_referent_id=operation_referent.referent_id,
                    target_label=(result.label if result is not None else ""),
                    route="result" if result is not None else "fail_closed",
                    reason=("named topic target" if soft else "explicit operation target"),
                    evidence=(("named-topic-target",) if soft else ("explicit-target",)),
                    assessment=assessment.to_dict(),
                )
        if assessment.status == _salience.STATUS_AMBIGUOUS:
            return _clarify_decision(function, target_phrase, assessment)
        if soft:
            # A named follow-up that matches no referent must NOT be forced into a
            # clarification: the existing cascade owns the turn (fail-closed).
            return RoutingDecision(
                communicative_function=function,
                route="existing",
                reason="named follow-up matched no referent",
                evidence=("unmatched-named-follow-up",),
                assessment=assessment.to_dict(),
            )
        # A clearly anchored target that matches no referent must not fall back to
        # the latest result (that would silently return a different answer).
        return _clarify_decision(function, target_phrase, assessment)

    # No explicit target: assess the result candidates by the evidence hierarchy.
    assessment = _salience.assess(
        discourse,
        thread_state,
        latest_referent_id=(
            getattr(discourse, "latest_result_id", "") if discourse is not None else ""
        ),
    )
    if assessment.status == _salience.STATUS_RESOLVED:
        return RoutingDecision(
            communicative_function=function,
            target_kind="result",
            target_referent_id=assessment.selected_referent_id,
            target_label=assessment.selected_label,
            route="result",
            reason=assessment.reason,
            evidence=("salience", assessment.reason),
            assessment=assessment.to_dict(),
        )
    if assessment.status == _salience.STATUS_AMBIGUOUS:
        return RoutingDecision(
            communicative_function=function,
            target_kind="result",
            route="clarify",
            clarification_required=True,
            candidates=assessment.labels(),
            reason=assessment.reason,
            evidence=("ambiguous", assessment.reason),
            assessment=assessment.to_dict(),
        )
    # No result candidate: a status query may still target the latest operation.
    if (
        function == FUNCTION_QUERY_STATUS
        and discourse is not None
        and discourse.latest_operation_id
    ):
        return RoutingDecision(
            communicative_function=function,
            target_kind="operation",
            target_referent_id=discourse.latest_operation_id,
            route="result",
            reason="latest retained operation",
            evidence=("latest-operation",),
            assessment=assessment.to_dict(),
        )
    return RoutingDecision(
        communicative_function=function,
        target_kind="result",
        route="fail_closed",
        reason=assessment.reason,
        evidence=("no-result",),
        assessment=assessment.to_dict(),
    )


def _clarify_decision(
    function: str, explicit: str, assessment: "_salience.SalienceAssessment"
) -> RoutingDecision:
    """Build a bounded clarification routing decision from an assessment."""
    return RoutingDecision(
        communicative_function=function,
        target_kind="operation",
        target_label=explicit,
        route="clarify",
        clarification_required=True,
        candidates=assessment.labels(),
        reason=assessment.reason,
        evidence=("ambiguous-explicit-target",),
        assessment=assessment.to_dict(),
    )


def _compare_decision(function: str, discourse: Any) -> RoutingDecision:
    """Resolve a COMPARISON to the two most recent recorded results.

    Deterministic and fail-closed: a comparison needs TWO recorded results, so a
    turn with fewer than two fails closed instead of silently presenting the
    single most recent one. Only existing discourse referents are read — no
    target is invented and no relationship between them is asserted.
    """
    results = [
        referent
        for referent in (getattr(discourse, "referents", ()) or ())
        if getattr(referent, "kind", "") == _ds.KIND_RESULT
        and getattr(referent, "label", "")
    ]
    if len(results) < 2:
        return RoutingDecision(
            communicative_function=function,
            target_kind="comparison",
            route="fail_closed",
            reason="a comparison needs two recorded results",
            evidence=("comparison-insufficient",),
        )
    latest, earlier = results[-1], results[-2]
    assessment = _salience.SalienceAssessment(
        status=_salience.STATUS_RESOLVED,
        reason="two recorded results are available to compare",
    )
    return RoutingDecision(
        communicative_function=function,
        target_kind="comparison",
        target_referent_id=latest.referent_id,
        target_label=latest.label,
        candidates=(latest.label, earlier.label),
        route="result",
        reason="two recorded results are available to compare",
        evidence=("comparison",),
        assessment=assessment.to_dict(),
    )


__all__ = [
    "FUNCTION_COMPARE",
    "FUNCTION_RELATION",
    "FUNCTION_REQUEST_OPERATION",
    "FUNCTION_QUERY_RESULT",
    "FUNCTION_QUERY_CAUSE",
    "FUNCTION_QUERY_STATUS",
    "FUNCTION_UNKNOWN",
    "FUNCTIONS",
    "QUERY_FUNCTIONS",
    "RoutingDecision",
    "relation_query_parts",
    "classify_function",
    "resolve_routing",
    "assess",
]
