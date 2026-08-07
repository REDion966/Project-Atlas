"""Atlas Advanced Reasoning — Provider Protocols (Track D, Batch 1).

Pure interfaces for the external surfaces Track D consumes. Concrete
wrappers (e.g. a ``KnowledgeManager``-backed ``EvidenceProvider`` or a
``WorldModelEngine``-backed ``CausalGraphProvider``) are constructed at the
kernel boundary and injected — pure Track D modules never import the
underlying services.

Model protocols (``ReasoningModel``, ``VerificationModel``, ``HypothesisModel``)
are optional enhancers for the deterministic core. They are fail-soft: when
not injected, the deterministic reasoners run without model assistance.

No infrastructure dependencies. No AI provider SDKs. No storage. No kernel.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from atlas.advanced_reasoning.models import (
    CausalPath,
    Hypothesis,
    ReasoningTraceStep,
    VerificationFinding,
)


@runtime_checkable
class EvidenceProvider(Protocol):
    """Injected surface for querying aggregated evidence.

    Implementors wrap read-only sources (e.g. ``KnowledgeManager.query``);
    the protocol never mutates state. Returns stable evidence reference
    strings suitable for ``evidence_refs`` on reasoning artifacts.
    """

    def query(self, query_text: str, limit: int = 10) -> list[str]:
        """Return evidence reference strings relevant to ``query_text``.

        Deterministic callers expect a stable, ranked result list; empty
        results are valid (no usable evidence).
        """
        ...


@runtime_checkable
class CausalGraphProvider(Protocol):
    """Injected surface for read-only causal graph traversal.

    Implementors wrap the world model (entities, relationships, causal
    chains). Traversal never mutates the underlying graph — the provider
    only reads.
    """

    def causal_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> tuple[CausalPath, ...]:
        """Return causal paths from ``source`` to ``target``.

        Paths are ordered by confidence (highest first) and bounded by
        ``max_depth`` edges.
        """
        ...

    def related_entities(
        self,
        entity_id: str,
        max_depth: int = 5,
    ) -> tuple[str, ...]:
        """Return entity IDs causally related to ``entity_id``.

        Ordered by relevance; bounded by ``max_depth`` edges.
        """
        ...


@runtime_checkable
class ReasoningModel(Protocol):
    """Optional model enhancer for multi-step reasoning.

    When injected, the ``MultiStepReasoner`` may request model-proposed
    steps and merge them into the deterministic trace. When absent, the
    reasoner proceeds deterministically without model assistance.
    """

    def propose_steps(
        self,
        question: str,
        max_steps: int = 20,
    ) -> tuple[ReasoningTraceStep, ...]:
        """Return model-proposed reasoning steps for ``question``.

        Failure is handled by the caller: a raising or malformed model
        never crashes the deterministic reasoner.
        """
        ...


@runtime_checkable
class VerificationModel(Protocol):
    """Optional model enhancer for semantic verification checks.

    Injected into the ``SelfVerifier`` to perform checks the deterministic
    layer cannot (e.g. paraphrase-level contradiction detection). Absence
    or failure falls back to the deterministic checks only.
    """

    def assess(
        self,
        claim: str,
        context: dict[str, Any],
    ) -> VerificationFinding | None:
        """Return a semantic verification finding, or None if undecidable.

        The finding must carry a stable ``finding_id`` and a ``check_type``
        the verifier recognizes.
        """
        ...


@runtime_checkable
class HypothesisModel(Protocol):
    """Optional model enhancer for hypothesis generation.

    Injected into the ``HypothesisGenerator`` to propose candidate
    hypotheses that the deterministic layer then scores and ranks.
    Absence or failure falls back to deterministic template families.
    """

    def generate(
        self,
        claim: str,
        limit: int = 5,
    ) -> tuple[Hypothesis, ...]:
        """Return model-proposed hypotheses for ``claim``.

        Scores on returned hypotheses are advisory; the deterministic
        ranker re-scores all candidates.
        """
        ...
