"""Atlas specialists — the Atlas-owned seam for optional external intelligence.

Purpose
-------
A single, replaceable seam through which Atlas may consult an EXTERNAL
specialist (language interpreter, code generator, reviewer, researcher) for a
bounded task. This module defines only the contract and its validation; it
registers no provider and imports no model, SDK, network client or framework.

Authority (non-negotiable)
--------------------------
A specialist is an UNTRUSTED tool. It may interpret, generate, suggest,
classify, summarise, propose code, propose repairs, review, or reason over the
bounded context it is given. It may NOT authorize, approve, promote, bypass
governance, mutate the real repository, execute arbitrary commands, redefine
policy, or become a prerequisite for ordinary operation.

Atlas owns everything consequential: meaning, context, intent, routing,
validation, planning, governance, verification, approval, promotion and
evidence. A :class:`SpecialistProposal` is input to Atlas's judgement — never a
decision. Nothing in this module can reach the filesystem, a sandbox, an
approval surface or the promotion gate.

Deterministic-first
-------------------
With ZERO providers registered, every selection returns ``None`` and callers
continue on their existing deterministic path. A provider failure, an
unavailable provider or an invalid proposal must equally fall back — never
silently escalate authority.

Standard library only. Deterministic ordering. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: Closed capability vocabulary. Atlas asks for a CAPABILITY, never a model.
LANGUAGE_INTERPRET: str = "language.interpret"
CODE_GENERATE: str = "code.generate"
CODE_REPAIR: str = "code.repair"
CODE_REVIEW: str = "code.review"
RESEARCH_ASSIST: str = "research.assist"

#: The closed set of capabilities a provider may declare or Atlas may request.
SPECIALIST_CAPABILITIES: frozenset[str] = frozenset(
    {
        LANGUAGE_INTERPRET,
        CODE_GENERATE,
        CODE_REPAIR,
        CODE_REVIEW,
        RESEARCH_ASSIST,
    }
)

#: Hard bounds on a specialist task (a provider never receives unbounded input).
MAX_TASK_CHARS: int = 4_000
MAX_CONTEXT_FILES: int = 24
MAX_CONTEXT_CHARS: int = 60_000
MAX_PROPOSAL_CHARS: int = 40_000
MAX_IDENTIFIER_CHARS: int = 128


@dataclass(frozen=True, slots=True)
class BoundedSpecialistTask:
    """The ONLY thing a specialist ever receives: a bounded, explicit request.

    Attributes:
        capability: One of :data:`SPECIALIST_CAPABILITIES`.
        request: The user's request, bounded.
        target: The already-localized target (module/symbol/path), if any.
        context: Bounded ``path -> content`` repository context.
        plan: A bounded, JSON-safe summary of the ChangePlan, if any.
        verification_tests: The plan's authoritative verification tests, if any.
        evidence: Bounded provenance strings.
    """

    capability: str
    request: str = ""
    target: str = ""
    context: dict[str, str] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    verification_tests: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.capability not in SPECIALIST_CAPABILITIES:
            raise ValueError(f"unsupported specialist capability {self.capability!r}")

    def bounded(self) -> "BoundedSpecialistTask":
        """Return a strictly bounded copy (files and sizes capped, ordered).

        Deterministic: ``context`` is capped in sorted key order and the bound
        applies to the WHOLE payload, so a large repository can never be handed
        to a provider by accident.
        """
        context: dict[str, str] = {}
        total = 0
        for path in sorted(self.context)[:MAX_CONTEXT_FILES]:
            content = str(self.context[path])
            if total + len(content) > MAX_CONTEXT_CHARS:
                break
            context[path] = content
            total += len(content)
        return BoundedSpecialistTask(
            capability=self.capability,
            request=str(self.request)[:MAX_TASK_CHARS],
            target=str(self.target)[:MAX_IDENTIFIER_CHARS],
            context=context,
            plan=dict(self.plan),
            verification_tests=tuple(self.verification_tests)[:MAX_CONTEXT_FILES],
            evidence=tuple(str(e)[:MAX_IDENTIFIER_CHARS] for e in self.evidence),
        )


@dataclass(frozen=True, slots=True)
class SpecialistProposal:
    """An UNTRUSTED proposal. Never a decision, never a change."""

    provider_id: str
    capability: str
    payload: dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "capability": self.capability,
            "confidence": self.confidence,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Atlas's verdict on a specialist proposal (Atlas-owned, fail-closed)."""

    accepted: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "reason": self.reason}


@runtime_checkable
class SpecialistProvider(Protocol):
    """A replaceable specialist. Implementations must be side-effect free.

    A provider MUST NOT write to the repository, execute commands, touch the
    sandbox, approve, promote, or reach governance. It receives a bounded task
    and returns a proposal (or ``None`` when unable).
    """

    @property
    def provider_id(self) -> str:
        """Stable identity of the provider (not of a model)."""
        ...

    def capabilities(self) -> frozenset[str]:
        """The subset of :data:`SPECIALIST_CAPABILITIES` this provider serves."""
        ...

    def propose(self, task: BoundedSpecialistTask) -> SpecialistProposal | None:
        """Return an untrusted proposal, or ``None`` when unable."""
        ...


def validate_proposal(
    proposal: Any,
    task: BoundedSpecialistTask,
    *,
    allowed_paths: tuple[str, ...] = (),
) -> ValidationOutcome:
    """Atlas-owned validation of an untrusted proposal (fail-closed).

    Checks the schema, the requested capability, the declared paths (containment
    and allowed-file limits) and emptiness. It deliberately does NOT trust any
    claim the proposal makes about itself, and it grants nothing.
    """
    if proposal is None:
        return ValidationOutcome(False, "no proposal")
    if not isinstance(proposal, SpecialistProposal):
        return ValidationOutcome(False, "malformed proposal type")
    if not str(proposal.provider_id).strip():
        return ValidationOutcome(False, "proposal has no provider identity")
    if str(proposal.capability) != str(task.capability):
        return ValidationOutcome(False, "capability does not match the request")
    payload = proposal.payload
    if not isinstance(payload, dict) or not payload:
        return ValidationOutcome(False, "empty or malformed payload")
    if len(str(payload)) > MAX_PROPOSAL_CHARS:
        return ValidationOutcome(False, "proposal exceeds the size bound")

    # Code-shaped proposals must declare paths; every path must be safe.
    paths = payload.get("paths") or ()
    if paths:
        if not isinstance(paths, (list, tuple)):
            return ValidationOutcome(False, "malformed paths")
        for path in paths:
            try:
                from atlas.evolution.autonomy.code_sandbox import CodeChangeSet

                CodeChangeSet.validate_path(str(path))
            except Exception as exc:  # noqa: BLE001
                return ValidationOutcome(False, f"unsafe path {path!r}: {exc}")
            if allowed_paths and str(path) not in allowed_paths:
                return ValidationOutcome(False, f"path {path!r} is outside the target")
    return ValidationOutcome(True, "")


class SpecialistRegistry:
    """Deterministic, explicit capability -> provider selection.

    Deliberately simple: registration order is the only ranking, so selection
    is reproducible and a provider can be substituted without changing Atlas
    anywhere else. With no providers registered, every selection is ``None``.
    """

    def __init__(self) -> None:
        self._providers: list[SpecialistProvider] = []

    def register(self, provider: SpecialistProvider) -> None:
        """Register ``provider`` once (idempotent by ``provider_id``)."""
        if provider is None or not str(getattr(provider, "provider_id", "")).strip():
            raise ValueError("provider must expose a non-empty provider_id")
        if any(p.provider_id == provider.provider_id for p in self._providers):
            return
        self._providers.append(provider)

    def providers(self) -> tuple[SpecialistProvider, ...]:
        return tuple(self._providers)

    def supports(self, capability: str) -> bool:
        return self.select(capability) is not None

    def select(self, capability: str) -> SpecialistProvider | None:
        """The first registered provider serving ``capability``, or ``None``.

        ``None`` is the deterministic-first outcome: the caller continues on its
        existing deterministic path. Selection never consults a model, a
        network, a clock or any hidden state.
        """
        if capability not in SPECIALIST_CAPABILITIES:
            return None
        for provider in self._providers:
            try:
                declared = provider.capabilities()
            except Exception:  # noqa: BLE001 — a broken provider is not selectable
                continue
            if capability in set(declared or ()):
                return provider
        return None

    def request(
        self,
        task: BoundedSpecialistTask,
        proposals: dict[str, Any] | None = None,
    ) -> SpecialistProposal | None:
        """Run ONE bounded specialist request, validated, fail-closed.

        Returns a validated proposal, or ``None`` when no provider serves the
        capability, the provider fails, or its output is rejected. ``proposals``
        is an optional provider_id -> proposal mapping used instead of invoking
        a provider (for callers that already hold an untrusted proposal).
        Failures never propagate and never escalate authority.
        """
        bounded = task.bounded()
        provider = self.select(bounded.capability)
        if provider is None:
            return None
        try:
            candidate = (
                proposals.get(provider.provider_id)
                if isinstance(proposals, dict)
                else provider.propose(bounded)
            )
        except Exception:  # noqa: BLE001 — provider failure falls back
            return None
        outcome = validate_proposal(candidate, bounded)
        return candidate if outcome.accepted else None


__all__ = [
    "BoundedSpecialistTask",
    "CODE_GENERATE",
    "CODE_REPAIR",
    "CODE_REVIEW",
    "LANGUAGE_INTERPRET",
    "MAX_CONTEXT_CHARS",
    "MAX_CONTEXT_FILES",
    "MAX_PROPOSAL_CHARS",
    "MAX_TASK_CHARS",
    "RESEARCH_ASSIST",
    "SPECIALIST_CAPABILITIES",
    "SpecialistProposal",
    "SpecialistProvider",
    "SpecialistRegistry",
    "ValidationOutcome",
    "validate_proposal",
]
