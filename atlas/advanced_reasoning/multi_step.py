"""Atlas Advanced Reasoning — MultiStepReasoner (Track D, Batch 2).

Deterministic multi-step reasoning. Decomposes a question into sub-goals,
binds each sub-goal to evidence (via an injected :class:`EvidenceProvider`),
chains the steps into a dependency-aware reasoning sequence, and propagates
confidence forward through the chain. Produces immutable
:class:`~atlas.advanced_reasoning.models.ReasoningTrace` artifacts.

Guarantees:
  * Deterministic output for deterministic inputs (model timestamps aside).
  * Fail-soft: empty/invalid questions yield a FAILED trace, never an exception.
  * Optional :class:`ReasoningModel` enhancement is protocol-injected and may
    only add validated, acyclic steps — a raising or invalid model is ignored.
  * Cycle detection protects both the deterministic chain and model steps.

Pure logic. No AI SDKs. No storage. No kernel. No atlas.reasoning imports.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from atlas.advanced_reasoning.catalog import (
    REASONER_VERSION,
    STEP_ID_PREFIX,
    TRACE_ID_PREFIX,
)
from atlas.advanced_reasoning.models import (
    ReasoningConfig,
    ReasoningStrategy,
    ReasoningTrace,
    ReasoningTraceStep,
    TraceStatus,
)
from atlas.advanced_reasoning.protocols import (
    EvidenceProvider,
    ReasoningModel,
)

#: Confidence assigned to a step that is bound to evidence.
_STEP_CONFIDENCE_WITH_EVIDENCE: float = 0.8
#: Confidence assigned to a step with no evidence binding.
_STEP_CONFIDENCE_WITHOUT_EVIDENCE: float = 0.4
#: Confidence penalty applied per chained step beyond the first.
_CHAIN_DECAY_PER_STEP: float = 0.05
#: Minimum acceptable sub-goal fragment length.
_MIN_FRAGMENT_LENGTH: int = 3

#: Question-word prefixes stripped to build an assertion-form conclusion.
_QUESTION_PREFIXES: tuple[str, ...] = (
    "is it true that ",
    "what is ",
    "what are ",
    "how does ",
    "how do ",
    "is ",
    "are ",
    "was ",
    "were ",
    "does ",
    "do ",
    "did ",
    "will ",
    "would ",
    "can ",
    "could ",
    "should ",
)

#: Delimiters used to split a question into deterministic sub-goals.
_SPLIT_PATTERN = re.compile(
    r"\s+(?:and|&\s)+|,\s*|;\s*|\s+plus\s+|\s+as well as\s+|\d+\)\s*"
)


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 digest of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MultiStepReasoner:
    """Deterministic multi-step reasoner with dependency-aware chaining.

    Args:
        evidence_provider: Optional injected evidence source. When absent the
            reasoner still produces steps, marked without evidence.
        reasoning_model: Optional model enhancer. Its proposed steps are only
            merged when valid and acyclic; failures are ignored (fail-soft).
        config: Optional reasoning configuration; a default is used when
            ``None`` is given.
    """

    def __init__(
        self,
        evidence_provider: EvidenceProvider | None = None,
        reasoning_model: ReasoningModel | None = None,
        config: ReasoningConfig | None = None,
    ) -> None:
        self._evidence_provider = evidence_provider
        self._reasoning_model = reasoning_model
        self._config = config or ReasoningConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reason(
        self,
        question: str,
        max_steps: int | None = None,
        trace_id: str | None = None,
    ) -> ReasoningTrace:
        """Run deterministic multi-step reasoning on ``question``.

        The returned trace is immutable and fully determined by ``question``
        (and the injected provider state).

        Args:
            question: The query/claim to reason about.
            max_steps: Optional step budget override; defaults to the
                configured ``max_steps``.
            trace_id: Optional stable trace identifier; a deterministic
                timestamped id is generated when omitted.

        Returns:
            A ReasoningTrace with status COMPLETED, RAN_OUT_OF_BUDGET, or
            FAILED (invalid/empty question — never an exception).
        """
        budget = max(1, max_steps or self._config.max_steps)
        normalized = self._normalize(question)
        if not normalized:
            return self._failed_trace(question, trace_id, "empty question")

        sub_goals = self.sub_goals(normalized)
        steps = self._build_steps(sub_goals, budget)

        # Optional model enhancement (validated; fail-soft).
        steps = self._merge_model_steps(normalized, steps, budget)

        if len(steps) > budget:
            steps = steps[:budget]
            status = TraceStatus.RAN_OUT_OF_BUDGET
        elif len(sub_goals) > budget:
            status = TraceStatus.RAN_OUT_OF_BUDGET
        else:
            status = TraceStatus.COMPLETED

        propagated = self._propagate_confidences(steps)
        final_confidence = self._final_confidence(steps, propagated)
        conclusion = steps[-1].conclusion if steps else ""
        evidence_refs = tuple(
            sorted({ref for step in steps for ref in step.evidence_refs})
        )

        metadata: dict[str, Any] = {
            "sub_goals": list(sub_goals),
            "is_below_threshold": final_confidence < self._config.confidence_threshold,
        }

        return ReasoningTrace(
            trace_id=trace_id or self._default_trace_id(normalized),
            question=question.strip(),
            strategy=ReasoningStrategy.DECOMPOSE,
            steps=steps,
            status=status,
            conclusion=conclusion,
            confidence=round(final_confidence, 4),
            evidence_refs=evidence_refs,
            started_at=datetime.now(),
            completed_at=datetime.now() if status == TraceStatus.COMPLETED else None,
            reasoner_version=REASONER_VERSION,
            metadata=metadata,
        )

    def sub_goals(self, question: str) -> tuple[str, ...]:
        """Split ``question`` into deterministic atomic sub-goals.

        Empty and too-short fragments are dropped. The result is stable for
        the same input.
        """
        normalized = self._normalize(question)
        if not normalized:
            return ()
        fragments = [
            part.strip()
            for part in _SPLIT_PATTERN.split(normalized)
            if len(part.strip()) >= _MIN_FRAGMENT_LENGTH
        ]
        deduped: list[str] = []
        for fragment in fragments:
            if fragment not in deduped:
                deduped.append(fragment)
        return tuple(deduped)

    def validate_dependency_graph(
        self,
        steps: tuple[ReasoningTraceStep, ...],
    ) -> tuple[str, ...]:
        """Return the cyclic step-id loop if ``steps`` contain a cycle.

        A cycle is detected as a step (transitively) depending on itself
        through premise_step_ids. Returns the ordered cycle ids, or an empty
        tuple when the graph is acyclic or references absent ids.
        """
        ids = {step.step_id for step in steps}
        adjacency: dict[str, list[str]] = {}
        for step in steps:
            adjacency[step.step_id] = [
                premise for premise in step.premise_step_ids if premise in ids
            ]

        status: dict[str, int] = {}  # 1 = visiting, 2 = done
        stack: list[str] = []

        def visit(node: str) -> list[str] | None:
            status[node] = 1
            stack.append(node)
            for target in adjacency.get(node, ()):
                if target not in status:
                    cycle = visit(target)
                    if cycle is not None:
                        return cycle
                elif status[target] == 1:
                    start = stack.index(target)
                    return stack[start:] + [target]
            status[node] = 2
            stack.pop()
            return None

        for node in sorted(ids):
            if node not in status:
                cycle = visit(node)
                if cycle is not None:
                    return tuple(cycle)
        return ()

    @staticmethod
    def assertion_form(sub_goal: str) -> str:
        """Convert a question-like sub-goal into a deterministic assertion.

        Strips leading question prefixes (e.g. "Is the sky blue?" becomes
        "the sky blue") and removes a trailing question mark. Non-question
        fragments are returned unchanged.
        """
        text = sub_goal.strip().rstrip("?")
        lower = text.lower()
        for prefix in _QUESTION_PREFIXES:
            if lower.startswith(prefix):
                rest = text[len(prefix):].strip()
                return rest or text
        return text

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(question: str) -> str:
        """Collapse whitespace and trim the question."""
        return " ".join(question.split()).strip()

    def _build_steps(
        self,
        sub_goals: tuple[str, ...],
        budget: int,
    ) -> tuple[ReasoningTraceStep, ...]:
        """Build a deterministic sequential chain for the sub-goals."""
        steps: list[ReasoningTraceStep] = []
        for index, sub_goal in enumerate(sub_goals[:budget]):
            evidence = self._query_evidence(sub_goal)
            confidence = (
                _STEP_CONFIDENCE_WITH_EVIDENCE if evidence
                else _STEP_CONFIDENCE_WITHOUT_EVIDENCE
            )
            premise_ids = (steps[-1].step_id,) if steps else ()
            steps.append(
                ReasoningTraceStep(
                    step_id=f"{STEP_ID_PREFIX}:{index:04d}",
                    description=f"Resolve sub-goal: {sub_goal}",
                    premise_step_ids=premise_ids,
                    evidence_refs=evidence,
                    confidence=confidence,
                    conclusion=self.assertion_form(sub_goal),
                    metadata={"sub_goal": sub_goal, "index": index},
                )
            )
        return tuple(steps)

    def _query_evidence(self, sub_goal: str) -> tuple[str, ...]:
        """Query the injected evidence provider (fail-soft)."""
        provider = self._evidence_provider
        if provider is None:
            return ()
        try:
            results = provider.query(sub_goal, limit=self._config.evidence_limit)
            return tuple(sorted(str(ref) for ref in results[: self._config.evidence_limit]))
        except Exception:
            return ()

    def _merge_model_steps(
        self,
        question: str,
        deterministic: tuple[ReasoningTraceStep, ...],
        budget: int,
    ) -> tuple[ReasoningTraceStep, ...]:
        """Merge validated model-proposed steps ahead of the deterministic chain.

        A raising, malformed, or cyclic proposal is discarded entirely
        (fail-soft) — the deterministic chain is always preserved.
        """
        model = self._reasoning_model
        if model is None:
            return deterministic
        try:
            proposed = tuple(model.propose_steps(question, max_steps=budget))
        except Exception:
            return deterministic

        merged: list[ReasoningTraceStep] = []
        used_ids: set[str] = set()
        for step in proposed:
            if not step.step_id or step.step_id in used_ids:
                continue  # duplicate or empty id — invalid
            if any(premise == step.step_id for premise in step.premise_step_ids):
                continue  # self-reference — invalid
            if any(premise not in used_ids for premise in step.premise_step_ids):
                continue  # forward/absent reference — invalid in chain order
            used_ids.add(step.step_id)
            merged.append(step)
            if len(merged) >= budget:
                break

        if not merged:
            return deterministic

        # Relink the deterministic chain onto the last model step. The first
        # preserved step depends on the last merged model step; every later
        # step chains sequentially. Model ids are disjoint from deterministic
        # ids, so this relink cannot introduce a cycle.
        preserved: list[ReasoningTraceStep] = []
        for deterministic_step in deterministic:
            if deterministic_step.step_id in used_ids:
                continue
            premise_ids = (
                (merged[-1].step_id,)
                if not preserved
                else (preserved[-1].step_id,)
            )
            preserved.append(
                ReasoningTraceStep(
                    step_id=deterministic_step.step_id,
                    description=deterministic_step.description,
                    premise_step_ids=premise_ids,
                    evidence_refs=deterministic_step.evidence_refs,
                    confidence=deterministic_step.confidence,
                    conclusion=deterministic_step.conclusion,
                    metadata=deterministic_step.metadata,
                )
            )

        candidate = tuple(merged + preserved[: max(0, budget - len(merged))])
        if self.validate_dependency_graph(candidate):
            return deterministic  # cycle introduced by model — fall back
        return candidate

    @staticmethod
    def _propagate_confidences(
        steps: tuple[ReasoningTraceStep, ...],
    ) -> list[float]:
        """Propagate confidence forward through the premise graph.

        Each step's effective confidence is its own confidence multiplied by
        the minimum effective confidence of its premises.
        """
        effective: dict[str, float] = {}
        propagated: list[float] = []
        for step in steps:
            premises = [effective[p] for p in step.premise_step_ids if p in effective]
            premise_confidence = min(premises) if premises else 1.0
            value = round(step.confidence * premise_confidence, 4)
            effective[step.step_id] = value
            propagated.append(value)
        return propagated

    @staticmethod
    def _final_confidence(
        steps: tuple[ReasoningTraceStep, ...],
        propagated: list[float],
    ) -> float:
        """Final trace confidence: last propagated value, decayed per chain step.

        A single-step trace keeps its step confidence; each additional
        chained step applies a small deterministic penalty.
        """
        if not steps or not propagated:
            return 0.0
        chain_penalty = max(0.0, 1.0 - _CHAIN_DECAY_PER_STEP * (len(steps) - 1))
        return round(propagated[-1] * chain_penalty, 4)

    @staticmethod
    def _default_trace_id(question: str) -> str:
        """Timestamped trace id with a deterministic question digest."""
        stamp = datetime.now().isoformat()
        return f"{TRACE_ID_PREFIX}:{_sha16(question)}:{stamp}"

    @staticmethod
    def _failed_trace(
        question: str,
        trace_id: str | None,
        reason: str,
    ) -> ReasoningTrace:
        """Fail-closed trace for invalid input (never raises)."""
        return ReasoningTrace(
            trace_id=trace_id or f"{TRACE_ID_PREFIX}:empty:{_sha16(question)}",
            question=question.strip(),
            strategy=ReasoningStrategy.DECOMPOSE,
            steps=(),
            status=TraceStatus.FAILED,
            conclusion="",
            confidence=0.0,
            evidence_refs=(),
            started_at=datetime.now(),
            reasoner_version=REASONER_VERSION,
            metadata={"error": reason},
        )
