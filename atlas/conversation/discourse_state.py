"""Atlas Conversation — bounded discourse referents + operation/result lifecycle (Stage 3).

The foundational Atlas-native **discourse-referent** representation: structured,
deterministic, bounded objects for the things a conversation can refer back to —
operations, their results, findings, evidence, proposals and verifications — plus
typed relationships between them (``operation --produced--> result``,
``result --supported_by--> evidence``, ``proposal --concerns--> operation``,
``operation --verified_by--> verification``, ``result --supersedes--> result``).

It exists so later stages (context-aware reference resolution, QUD/threads,
salience/ambiguity) can identify an operation and its result as *distinct,
structured* objects — e.g. "What did you find?" (a result), "Explain that result."
(a result), "Which evidence supports that?" (evidence), "What did verification
show?" (verification). It deliberately does NOT resolve those phrases yet.

Boundaries (mandatory):

  * Single source of truth — this is NOT a second conversation store. It is a
    field of ``ConversationState`` and is written only through the existing
    :class:`~atlas.conversation.conversation_state.ConversationStateManager`.
  * Representation only — it never routes, authorizes, approves, executes,
    promotes, mutates governed state, or contacts a model/provider. A referent
    DESCRIBES an operation/proposal/verification; it is never authority.
  * Deterministic and model-independent — standard library only, no clock, no
    randomness, no I/O, no network, no model.
  * Bounded and JSON-safe — referents and relations are capped; labels are
    length-capped; eviction is deterministic (oldest first). It never copies the
    conversation transcript and stores no raw message text.

Later-stage concepts (QUD threads, salience ranking, automatic reference
selection, communicative-function routing) are deliberately NOT implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

#: Referent kinds actually produced/needed by this stage (a bounded vocabulary —
#: not the full audit list; unrepresented kinds are added later only on evidence).
KIND_OPERATION: str = "operation"
KIND_RESULT: str = "result"
KIND_FINDING: str = "finding"
KIND_EVIDENCE: str = "evidence"
KIND_PROPOSAL: str = "proposal"
KIND_VERIFICATION: str = "verification"

KINDS: frozenset[str] = frozenset(
    {
        KIND_OPERATION,
        KIND_RESULT,
        KIND_FINDING,
        KIND_EVIDENCE,
        KIND_PROPOSAL,
        KIND_VERIFICATION,
    }
)

#: Typed relationship verbs (bounded; only those with repository evidence).
REL_PRODUCED: str = "produced"
REL_SUPPORTED_BY: str = "supported_by"
REL_CONCERNS: str = "concerns"
REL_VERIFIED_BY: str = "verified_by"
REL_SUPERSEDES: str = "supersedes"

RELATIONS: frozenset[str] = frozenset(
    {REL_PRODUCED, REL_SUPPORTED_BY, REL_CONCERNS, REL_VERIFIED_BY, REL_SUPERSEDES}
)

#: Minimal lifecycle vocabulary justified by the repository. ``running`` /
#: ``cancelled`` are deliberately omitted (no existing evidence for them).
STATUS_PENDING: str = "pending"
STATUS_COMPLETED: str = "completed"
STATUS_FAILED: str = "failed"
STATUS_BLOCKED: str = "blocked"
STATUS_SUPERSEDED: str = "superseded"
STATUS_PROPOSED: str = "proposed"
STATUS_VERIFIED: str = "verified"

STATUSES: frozenset[str] = frozenset(
    {
        STATUS_PENDING,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_BLOCKED,
        STATUS_SUPERSEDED,
        STATUS_PROPOSED,
        STATUS_VERIFIED,
    }
)

#: Hard bounds (a malformed/oversized turn can never produce unbounded state).
MAX_REFERENTS: int = 24
MAX_RELATIONS: int = 32
_MAX_LABEL_CHARS: int = 200
_MAX_ORIGIN_CHARS: int = 40
_MAX_REF_CHARS: int = 200
_MAX_ID_CHARS: int = 16
_MAX_ITEMS: int = 8
_MAX_TURN_INDEX: int = 1_000_000


def _bounded(value: Any, limit: int) -> str:
    """Return a trimmed, length-bounded string (non-strings degrade to ``""``)."""
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_index(value: Any) -> int:
    """Return a bounded non-negative conversation index (0 on malformed input)."""
    try:
        index = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(index, _MAX_TURN_INDEX))


def _bounded_items(values: Any, *, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    """Return bounded, de-duplicated, non-empty bounded strings."""
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    for value in values:
        text = _bounded(value, _MAX_LABEL_CHARS)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Referent:
    """One bounded discourse referent (facts only, no authority).

    ``referent_id`` is a stable, deterministic, per-conversation identifier
    (``ref-######``). ``kind`` is one of :data:`KINDS`. ``origin`` records what
    produced it (e.g. the operation's ``TaskType`` value). ``ref`` deliberately
    WRAPS an existing identifier (an investigation target, a proposal id, …)
    rather than inventing a second one. ``label``/``status``/``turn_index`` are
    the bounded descriptive fields later stages use.
    """

    referent_id: str
    kind: str = KIND_OPERATION
    label: str = ""
    status: str = STATUS_PENDING
    origin: str = ""
    turn_index: int = 0
    ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "referent_id": self.referent_id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "origin": self.origin,
            "turn_index": self.turn_index,
            "ref": self.ref,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["Referent"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        referent_id = _bounded(data.get("referent_id"), _MAX_ID_CHARS)
        if not referent_id:
            return None
        kind = _bounded(data.get("kind"), _MAX_ORIGIN_CHARS)
        if kind not in KINDS:
            kind = KIND_OPERATION
        status = _bounded(data.get("status"), _MAX_ORIGIN_CHARS)
        if status not in STATUSES:
            status = STATUS_PENDING
        return cls(
            referent_id=referent_id,
            kind=kind,
            label=_bounded(data.get("label"), _MAX_LABEL_CHARS),
            status=status,
            origin=_bounded(data.get("origin"), _MAX_ORIGIN_CHARS),
            turn_index=_bounded_index(data.get("turn_index")),
            ref=_bounded(data.get("ref"), _MAX_REF_CHARS),
        )


@dataclass(frozen=True, slots=True)
class Relation:
    """One bounded typed relationship between two referents."""

    source_id: str
    relation: str
    target_id: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "source_id": self.source_id,
            "relation": self.relation,
            "target_id": self.target_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["Relation"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        source_id = _bounded(data.get("source_id"), _MAX_ID_CHARS)
        target_id = _bounded(data.get("target_id"), _MAX_ID_CHARS)
        relation = _bounded(data.get("relation"), _MAX_ORIGIN_CHARS)
        if not source_id or not target_id or relation not in RELATIONS:
            return None
        return cls(source_id=source_id, relation=relation, target_id=target_id)


@dataclass(frozen=True, slots=True)
class DiscourseState:
    """Bounded, deterministic discourse-referent state (facts only).

    A field of ``ConversationState`` — never a second store. ``sequence`` is the
    monotonic counter behind deterministic referent ids; the ``latest_*`` slots
    are bounded pointers into the registry used by later stages.
    """

    referents: tuple[Referent, ...] = ()
    relations: tuple[Relation, ...] = ()
    sequence: int = 0
    latest_operation_id: str = ""
    latest_result_id: str = ""
    latest_result_label: str = ""
    latest_proposal_id: str = ""

    def find(self, referent_id: str) -> Optional[Referent]:
        """Return the referent with ``referent_id``, or ``None``."""
        for referent in self.referents:
            if referent.referent_id == referent_id:
                return referent
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "referents": [r.to_dict() for r in self.referents],
            "relations": [r.to_dict() for r in self.relations],
            "sequence": self.sequence,
            "latest_operation_id": self.latest_operation_id,
            "latest_result_id": self.latest_result_id,
            "latest_result_label": self.latest_result_label,
            "latest_proposal_id": self.latest_proposal_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["DiscourseState"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        referents: list[Referent] = []
        raw_referents = data.get("referents")
        if isinstance(raw_referents, (list, tuple)):
            for item in raw_referents:
                referent = item if isinstance(item, Referent) else Referent.from_dict(item)
                if referent is not None:
                    referents.append(referent)
        relations: list[Relation] = []
        raw_relations = data.get("relations")
        if isinstance(raw_relations, (list, tuple)):
            for item in raw_relations:
                relation = item if isinstance(item, Relation) else Relation.from_dict(item)
                if relation is not None:
                    relations.append(relation)
        try:
            sequence = max(0, int(data.get("sequence", 0)))
        except (TypeError, ValueError):
            sequence = 0
        return cls(
            referents=tuple(referents)[-MAX_REFERENTS:],
            relations=tuple(relations)[-MAX_RELATIONS:],
            sequence=sequence,
            latest_operation_id=_bounded(data.get("latest_operation_id"), _MAX_ID_CHARS),
            latest_result_id=_bounded(data.get("latest_result_id"), _MAX_ID_CHARS),
            latest_result_label=_bounded(
                data.get("latest_result_label"), _MAX_LABEL_CHARS
            ),
            latest_proposal_id=_bounded(data.get("latest_proposal_id"), _MAX_ID_CHARS),
        )


@dataclass(frozen=True, slots=True)
class DiscourseTurnOutcome:
    """The explicit, bounded inputs to a discourse/referent transition.

    Produced from the EXISTING operation/result facts (the operation kind, the
    retained result, and — for an investigation — its bounded findings/evidence)
    plus the operation's proposal reference. It is a value object only.
    """

    turn_index: int = 0
    operation_origin: str = ""
    operation_label: str = ""
    operation_status: str = STATUS_COMPLETED
    result_label: str = ""
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    proposal_ref: str = ""


def _evict(
    referents: list[Referent], relations: list[Relation]
) -> tuple[list[Referent], list[Relation]]:
    """Enforce the referent/relation bounds deterministically (oldest dropped)."""
    if len(referents) > MAX_REFERENTS:
        referents = referents[-MAX_REFERENTS:]
    live = {r.referent_id for r in referents}
    relations = [r for r in relations if r.source_id in live and r.target_id in live]
    if len(relations) > MAX_RELATIONS:
        relations = relations[-MAX_RELATIONS:]
    return referents, relations


def apply_turn(
    current: "DiscourseState | None", outcome: "DiscourseTurnOutcome"
) -> DiscourseState:
    """The single, deterministic discourse/referent transition (pure).

    Records an OPERATION referent for the turn's operation (when one is named),
    a distinct RESULT referent when a fresh result was produced, and — where the
    existing architecture provides them — FINDING / EVIDENCE / PROPOSAL /
    VERIFICATION referents plus their typed relationships. Nothing is invented:
    a missing fact produces no referent. The transition re-bounds every field, so
    a malformed outcome can never produce unbounded state.
    """
    base = current if isinstance(current, DiscourseState) else DiscourseState()
    referents: list[Referent] = list(base.referents)
    relations: list[Relation] = list(base.relations)
    sequence = base.sequence

    def _add(kind: str, label: str, status: str, origin: str, ref: str = "") -> str:
        nonlocal sequence
        sequence += 1
        referent = Referent(
            referent_id=f"ref-{sequence:06d}",
            kind=kind if kind in KINDS else KIND_OPERATION,
            label=_bounded(label, _MAX_LABEL_CHARS),
            status=status if status in STATUSES else STATUS_PENDING,
            origin=_bounded(origin, _MAX_ORIGIN_CHARS),
            turn_index=_bounded_index(outcome.turn_index),
            ref=_bounded(ref, _MAX_REF_CHARS),
        )
        referents.append(referent)
        return referent.referent_id

    def _link(source: str, relation: str, target: str) -> None:
        if source and target and relation in RELATIONS:
            relations.append(Relation(source_id=source, relation=relation, target_id=target))

    # 1. The operation (and, for a verification origin, a VERIFICATION referent).
    operation_id = ""
    operation_origin = _bounded(outcome.operation_origin, _MAX_ORIGIN_CHARS)
    if operation_origin:
        if operation_origin == "verification_request":
            operation_id = _add(
                KIND_VERIFICATION,
                outcome.operation_label or operation_origin,
                STATUS_VERIFIED,
                operation_origin,
            )
            # An existing operation is verified by this verification.
            _link(base.latest_operation_id, REL_VERIFIED_BY, operation_id)
        else:
            operation_id = _add(
                KIND_OPERATION,
                outcome.operation_label or operation_origin,
                outcome.operation_status or STATUS_COMPLETED,
                operation_origin,
            )

    # 2. A fresh result produced by that operation (idempotent on the label).
    result_id = ""
    result_label = _bounded(outcome.result_label, _MAX_LABEL_CHARS)
    if result_label and result_label != base.latest_result_label:
        result_id = _add(
            KIND_RESULT, result_label, STATUS_COMPLETED, operation_origin
        )
        _link(operation_id, REL_PRODUCED, result_id)
        # ``latest_result`` is single-valued in the existing state, so a fresh
        # result genuinely SUPERSEDES the previous one.
        if base.latest_result_id and base.latest_result_id != result_id:
            _link(result_id, REL_SUPERSEDES, base.latest_result_id)
            referents = [
                replace(r, status=STATUS_SUPERSEDED)
                if r.referent_id == base.latest_result_id
                else r
                for r in referents
            ]

    # 3. Findings (investigation) — one referent each, produced by the operation.
    for finding in _bounded_items(outcome.findings):
        finding_id = _add(KIND_FINDING, finding, STATUS_COMPLETED, operation_origin)
        _link(operation_id, REL_PRODUCED, finding_id)

    # 4. Evidence — supports the result it evidences.
    for item in _bounded_items(outcome.evidence):
        evidence_id = _add(KIND_EVIDENCE, item, STATUS_COMPLETED, operation_origin)
        _link(result_id or operation_id, REL_SUPPORTED_BY, evidence_id)

    # 5. A proposal concerns the operation it was generated from.
    proposal_id = ""
    proposal_ref = _bounded(outcome.proposal_ref, _MAX_REF_CHARS)
    if proposal_ref:
        proposal_id = _add(
            KIND_PROPOSAL, proposal_ref, STATUS_PROPOSED, "proposal", ref=proposal_ref
        )
        _link(proposal_id, REL_CONCERNS, operation_id)

    referents, relations = _evict(referents, relations)

    return DiscourseState(
        referents=tuple(referents),
        relations=tuple(relations),
        sequence=sequence,
        latest_operation_id=operation_id or base.latest_operation_id,
        latest_result_id=result_id or base.latest_result_id,
        latest_result_label=result_label or base.latest_result_label,
        latest_proposal_id=proposal_id or base.latest_proposal_id,
    )


__all__ = [
    "KIND_OPERATION",
    "KIND_RESULT",
    "KIND_FINDING",
    "KIND_EVIDENCE",
    "KIND_PROPOSAL",
    "KIND_VERIFICATION",
    "KINDS",
    "REL_PRODUCED",
    "REL_SUPPORTED_BY",
    "REL_CONCERNS",
    "REL_VERIFIED_BY",
    "REL_SUPERSEDES",
    "RELATIONS",
    "STATUS_PENDING",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_BLOCKED",
    "STATUS_SUPERSEDED",
    "STATUS_PROPOSED",
    "STATUS_VERIFIED",
    "STATUSES",
    "MAX_REFERENTS",
    "MAX_RELATIONS",
    "Referent",
    "Relation",
    "DiscourseState",
    "DiscourseTurnOutcome",
    "apply_turn",
]
