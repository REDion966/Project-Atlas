"""Atlas Conversation — optional local learned reference proposer (Stage 9).

A narrow, OFF-BY-DEFAULT seam through which an OPTIONAL local learned model may
PROPOSE bounded coreference/reference evidence for the Stage 6 gap identified in
the Stage 8 audit (pronoun / discourse coreference). It mirrors the existing
:class:`atlas.conversation.model_intent_parser.ModelIntentParser` contract:

  * no ``atlas.ai`` import — the model is a duck-typed callable, so this module
    stays pure and the composition layer owns any provider wiring;
  * OFF by default — ``model=None`` makes :meth:`propose` return ``unavailable``;
  * proposal-only — Atlas DECIDES. A proposal never executes, authorizes,
    approves, promotes, mutates state, generates the final response, or becomes
    the reference resolver. Stage 6 salience remains authoritative;
  * structured + strictly validated — one JSON object, a closed proposal schema,
    a closed relation vocabulary, bounded strings, bounded counts, integer
    confidence only, and every candidate referent id must EXIST in the evidence
    Atlas supplied. Anything else is rejected (fail-closed, never repaired);
  * no executable semantics — executable-looking keys/values are rejected; the
    model cannot smuggle an Atlas command;
  * provenance — every proposal carries provider/model/source, so learned
    evidence stays distinguishable from native deterministic evidence;
  * local only — the seam depends on a narrow callable, never a cloud API. If the
    local model is absent the deterministic path continues unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from atlas.conversation.lexicon import tokens as _tokens

#: Context key under which the bounded, advisory learned proposals ride the TaskSpec.
REFERENCE_PROPOSALS_KEY: str = "reference_proposals"

#: The only relation this seam represents (Stage 3's referent vocabulary is the
#: source of truth for referents; this is our own bounded relation name).
RELATION_REFERS_TO: str = "refers_to"
RELATIONS: frozenset[str] = frozenset({RELATION_REFERS_TO})

#: Proposal result statuses.
PROPOSAL_OK: str = "ok"
PROPOSAL_UNAVAILABLE: str = "unavailable"
PROPOSAL_INVALID: str = "invalid"
PROPOSAL_ERROR: str = "error"

PROPOSAL_STATUSES: frozenset[str] = frozenset(
    {PROPOSAL_OK, PROPOSAL_UNAVAILABLE, PROPOSAL_INVALID, PROPOSAL_ERROR}
)

#: Bounds — the model can never inject unbounded or arbitrary content.
MAX_PROMPT_TEXT_CHARS: int = 400
MAX_MENTION_CHARS: int = 40
MAX_CANDIDATES: int = 12
MAX_PROPOSALS: int = 6
MAX_MODEL_CHARS: int = 64
MAX_CONFIDENCE: int = 100

#: A proposal is only worth a model call when the turn carries a reference cue.
_REFERENCE_CUES: frozenset[str] = frozenset(
    {"it", "its", "they", "them", "their", "that", "this", "these", "those",
     "one", "ones", "previous", "last", "first", "second", "other", "former",
     "earlier"}
)

#: Top-level keys the model may return (anything else rejects the payload).
_TOP_KEYS: frozenset[str] = frozenset({"proposals"})
#: Per-proposal keys the model may return (anything else rejects the proposal).
_PROPOSAL_KEYS: frozenset[str] = frozenset(
    {"mention", "candidate", "relation", "confidence"}
)

#: Executable/authority-looking keys/values that must never be accepted.
_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"execute", "approve", "promote", "delete", "modify", "run", "authorize",
     "permission", "command", "operation", "grant", "bypass"}
)


def _bounded(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _looks_executable(value: str) -> bool:
    lowered = f" {value.lower()} "
    return any(token in lowered for token in _FORBIDDEN_TOKENS)


@dataclass(frozen=True, slots=True)
class ReferenceProposal:
    """One bounded, advisory reference proposal (evidence only, never authority)."""

    mention: str = ""
    candidate_referent_id: str = ""
    relation: str = RELATION_REFERS_TO
    confidence: int = 0  # advisory 0..100; 0 == not supplied
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mention": self.mention,
            "candidate_referent_id": self.candidate_referent_id,
            "relation": self.relation,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["ReferenceProposal"]:
        if not isinstance(data, dict):
            return None
        mention = _bounded(data.get("mention"), MAX_MENTION_CHARS)
        candidate = _bounded(data.get("candidate_referent_id"), 32)
        if not mention or not candidate:
            return None
        relation = _bounded(data.get("relation"), 32)
        if relation not in RELATIONS:
            relation = RELATION_REFERS_TO
        confidence = data.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, int):
            confidence = 0
        confidence = max(0, min(int(confidence), MAX_CONFIDENCE))
        return cls(
            mention=mention,
            candidate_referent_id=candidate,
            relation=relation,
            confidence=confidence,
            provider=_bounded(data.get("provider"), MAX_MODEL_CHARS),
            model=_bounded(data.get("model"), MAX_MODEL_CHARS),
        )


@dataclass(frozen=True, slots=True)
class ReferenceProposalResult:
    """The bounded outcome of one proposer invocation (with provenance)."""

    status: str = PROPOSAL_UNAVAILABLE
    provider: str = ""
    model: str = ""
    proposals: tuple[ReferenceProposal, ...] = ()
    reason: str = ""

    @property
    def is_ok(self) -> bool:
        return self.status == PROPOSAL_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "proposals": [p.to_dict() for p in self.proposals],
            "reason": self.reason,
        }


def _candidate_map(candidates: Any) -> dict[str, str]:
    """Build a bounded ``{referent_id: label}`` map from Atlas-supplied evidence."""
    out: dict[str, str] = {}
    if isinstance(candidates, dict):
        items = candidates.items()
    elif isinstance(candidates, (list, tuple)):
        items = []
        for entry in candidates:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                items.append((entry[0], entry[1]))
            else:
                items.append((getattr(entry, "referent_id", ""), getattr(entry, "label", "")))
    else:
        items = []
    for referent_id, label in items:
        key = _bounded(referent_id, 32)
        if key and key not in out:
            out[key] = _bounded(label, MAX_MENTION_CHARS)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


class LearnedReferenceProposer:
    """Optional local learned proposer over a narrow, duck-typed inference callable.

    Args:
        model: A duck-typed callable invoked with one bounded prompt string. It
            may return a ``str`` (one JSON object), a ``dict`` (already-decoded),
            or any object exposing a ``.text`` string. ``None`` (default)
            disables the proposer entirely.
        provider: Provenance label for the inference boundary (e.g. "ollama").
        model_name: Provenance label for the specific local model.
    """

    def __init__(
        self,
        model: Callable[[str], Any] | None = None,
        *,
        provider: str = "local",
        model_name: str = "",
    ) -> None:
        self._model = model
        self._provider = _bounded(provider, MAX_MODEL_CHARS) or "local"
        self._model_name = _bounded(model_name, MAX_MODEL_CHARS)

    @property
    def enabled(self) -> bool:
        return self._model is not None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._model_name

    def propose(
        self,
        text: Any,
        *,
        candidates: Any,
        context: Any = None,
    ) -> ReferenceProposalResult:
        """Return bounded, validated reference proposals, or a fail-closed result.

        Consults the model ONLY for a turn that carries a reference cue AND for
        which Atlas supplied at least one candidate referent. Every failure mode
        returns a bounded result and leaves the deterministic path unchanged.
        """
        if self._model is None:
            return ReferenceProposalResult(
                status=PROPOSAL_UNAVAILABLE, provider=self._provider,
                model=self._model_name, reason="no local model wired",
            )
        if not isinstance(text, str) or not text.strip():
            return ReferenceProposalResult(
                status=PROPOSAL_UNAVAILABLE, provider=self._provider,
                model=self._model_name, reason="empty turn",
            )
        candidates_map = _candidate_map(candidates)
        if not candidates_map:
            return ReferenceProposalResult(
                status=PROPOSAL_UNAVAILABLE, provider=self._provider,
                model=self._model_name, reason="no candidate referents",
            )
        if not (frozenset(_tokens(text)) & _REFERENCE_CUES):
            return ReferenceProposalResult(
                status=PROPOSAL_UNAVAILABLE, provider=self._provider,
                model=self._model_name, reason="no reference cue",
            )
        try:
            raw = self._model(self._build_prompt(text, candidates_map))
        except Exception:  # a local model must never break a turn
            return ReferenceProposalResult(
                status=PROPOSAL_ERROR, provider=self._provider,
                model=self._model_name, reason="inference failed",
            )
        payload = _extract_payload(raw)
        if payload is None:
            return ReferenceProposalResult(
                status=PROPOSAL_INVALID, provider=self._provider,
                model=self._model_name, reason="not a JSON object",
            )
        return self._validate(payload, candidates_map)

    # -- internals ---------------------------------------------------------

    def _build_prompt(self, text: str, candidates_map: dict[str, str]) -> str:
        listing = "\n".join(f"- {rid}: {label}" for rid, label in candidates_map.items())
        return (
            "You are a bounded coreference evidence helper for a deterministic "
            "assistant. Read ONE user turn and the list of possible referents, "
            "then return ONE JSON object and NO prose:\n"
            '{"proposals": [{"mention": "<word from the turn>", '
            '"candidate": "<one referent id from the list>", '
            '"relation": "refers_to", "confidence": <0-100>}]}\n'
            "Use ONLY the listed referent ids. Propose evidence only: never an "
            "action, command, approval, permission, or instruction. If nothing is "
            'referenced, return {"proposals": []}.\n'
            f"Referents:\n{listing}\n"
            f"User turn: {text.strip()[:MAX_PROMPT_TEXT_CHARS]}"
        )

    def _validate(
        self, payload: dict[str, Any], candidates_map: dict[str, str]
    ) -> ReferenceProposalResult:
        if not set(payload.keys()) <= _TOP_KEYS:
            return ReferenceProposalResult(
                status=PROPOSAL_INVALID, provider=self._provider,
                model=self._model_name, reason="unexpected top-level keys",
            )
        raw_proposals = payload.get("proposals")
        if not isinstance(raw_proposals, list):
            return ReferenceProposalResult(
                status=PROPOSAL_INVALID, provider=self._provider,
                model=self._model_name, reason="proposals is not a list",
            )
        proposals: list[ReferenceProposal] = []
        saw_item = False
        for item in raw_proposals[: MAX_PROPOSALS * 2]:
            saw_item = True
            if not isinstance(item, dict):
                continue
            if not set(item.keys()) <= _PROPOSAL_KEYS:
                continue  # an unexpected (possibly executable) key -> reject item
            mention = _bounded(item.get("mention"), MAX_MENTION_CHARS)
            candidate = _bounded(item.get("candidate"), 32)
            relation = _bounded(item.get("relation"), 32) or RELATION_REFERS_TO
            if (
                not mention
                or candidate not in candidates_map  # existence validation
                or relation not in RELATIONS
                or _looks_executable(mention)
            ):
                continue
            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, int):
                confidence = 0
            confidence = max(0, min(int(confidence), MAX_CONFIDENCE))
            proposals.append(
                ReferenceProposal(
                    mention=mention,
                    candidate_referent_id=candidate,
                    relation=relation,
                    confidence=confidence,
                    provider=self._provider,
                    model=self._model_name,
                )
            )
            if len(proposals) >= MAX_PROPOSALS:
                break
        if saw_item and not proposals:
            return ReferenceProposalResult(
                status=PROPOSAL_INVALID, provider=self._provider,
                model=self._model_name, reason="no valid proposal survived validation",
            )
        return ReferenceProposalResult(
            status=PROPOSAL_OK,
            provider=self._provider,
            model=self._model_name,
            proposals=tuple(proposals),
        )


def _extract_payload(raw: Any) -> dict[str, Any] | None:
    """Normalize a model response into a decoded dict, or ``None``."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_json(raw)
    text = getattr(raw, "text", None)
    if isinstance(text, str):
        return _parse_json(text)
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def adjudicate_proposals(
    result: ReferenceProposalResult,
    *,
    deterministic_candidate_ids: Any = (),
    selected_referent_id: str = "",
) -> dict[str, Any]:
    """Atlas's bounded, DESCRIPTIVE reading of the learned proposals.

    It never changes a decision: it only states whether the learned evidence
    corroborates the deterministic selection, conflicts with it, or is
    insufficient. Stage 6 remains authoritative regardless of the outcome.
    """
    deterministic = {str(i) for i in (deterministic_candidate_ids or ()) if isinstance(i, str)}
    selected = _bounded(selected_referent_id, 32)
    if not isinstance(result, ReferenceProposalResult) or not result.is_ok or not result.proposals:
        return {
            "status": "insufficient",
            "provider": getattr(result, "provider", ""),
            "selected_referent_id": selected,
            "notes": ["no usable learned evidence"],
        }
    agrees = any(p.candidate_referent_id == selected for p in result.proposals)
    conflicts = any(
        p.candidate_referent_id in deterministic and p.candidate_referent_id != selected
        for p in result.proposals
    )
    if conflicts:
        status = "conflict"
    elif agrees:
        status = "corroborated"
    else:
        status = "insufficient"
    return {
        "status": status,
        "provider": result.provider,
        "model": result.model,
        "selected_referent_id": selected,
        "proposed": [p.candidate_referent_id for p in result.proposals],
        "notes": [p.mention for p in result.proposals],
    }


__all__ = [
    "REFERENCE_PROPOSALS_KEY",
    "RELATION_REFERS_TO",
    "RELATIONS",
    "PROPOSAL_OK",
    "PROPOSAL_UNAVAILABLE",
    "PROPOSAL_INVALID",
    "PROPOSAL_ERROR",
    "PROPOSAL_STATUSES",
    "MAX_PROPOSALS",
    "MAX_CANDIDATES",
    "MAX_CONFIDENCE",
    "ReferenceProposal",
    "ReferenceProposalResult",
    "LearnedReferenceProposer",
    "adjudicate_proposals",
]
