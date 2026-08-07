"""Track D — Shared test doubles for Batch 2 engine tests.

Structural stand-ins for the injected protocols (EvidenceProvider,
CausalGraphProvider, ReasoningModel, VerificationModel, HypothesisModel)
and for read-only history providers duck-typed with the ReasoningRecorder /
ReasoningTraceRecorder surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.advanced_reasoning.models import (
    CausalPath,
    Hypothesis,
    ReasoningTrace,
    ReasoningTraceStep,
    VerificationFinding,
)


@dataclass
class FakeEvidenceProvider:
    """Deterministic evidence source keyed by exact substrings."""

    rows: dict[str, tuple[str, ...]]

    def query(self, query_text: str, limit: int = 10) -> list[str]:
        matches: list[str] = []
        for needle, refs in self.rows.items():
            if needle.lower() in query_text.lower():
                matches.extend(refs)
        return sorted(matches)[:limit]


class FakeCausalGraphProvider:
    """Deterministic read-only causal graph stand-in.

    ``paths`` maps (source, target) -> tuple[CausalPath]; ``related`` maps
    entity -> tuple of related entities. Tracks call counts so tests can
    verify the reasoner never writes and always goes through the protocol.
    """

    def __init__(
        self,
        paths: dict[tuple[str, str], tuple[CausalPath, ...]] | None = None,
        related: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.paths = paths or {}
        self.related = related or {}
        self.causal_paths_calls: list[tuple[str, str, int]] = []
        self.related_entities_calls: list[tuple[str, int]] = []

    def causal_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> tuple[CausalPath, ...]:
        self.causal_paths_calls.append((source, target, max_depth))
        return self.paths.get((source, target), ())

    def related_entities(
        self,
        entity_id: str,
        max_depth: int = 5,
    ) -> tuple[str, ...]:
        self.related_entities_calls.append((entity_id, max_depth))
        return self.related.get(entity_id, ())


class RaisingCausalGraphProvider:
    """Causal provider that always raises (fail-soft verification)."""

    def causal_paths(self, source, target, max_depth=5):
        raise RuntimeError("boom")

    def related_entities(self, entity_id, max_depth=5):
        raise RuntimeError("boom")


class FakeReasoningModel:
    """Model stand-in returning scripted proposed steps."""

    def __init__(self, steps: tuple[ReasoningTraceStep, ...] = ()) -> None:
        self.steps = steps
        self.calls: list[tuple[str, int]] = []

    def propose_steps(self, question: str, max_steps: int = 20) -> tuple[ReasoningTraceStep, ...]:
        self.calls.append((question, max_steps))
        return self.steps


class RaisingReasoningModel:
    """Model stand-in that always raises (fail-soft verification)."""

    def propose_steps(self, question: str, max_steps: int = 20):
        raise RuntimeError("model down")


class FakeVerificationModel:
    """Model stand-in returning a scripted semantic finding."""

    def __init__(
        self,
        finding: VerificationFinding | None = None,
        failure: bool = False,
    ) -> None:
        self.finding = finding
        self.failure = failure
        self.calls: list[tuple[str, dict]] = []

    def assess(self, claim: str, context: dict | None = None):
        self.calls.append((claim, dict(context or {})))
        if self.failure:
            raise RuntimeError("verification down")
        return self.finding


class FakeHypothesisModel:
    """Model stand-in returning scripted hypotheses."""

    def __init__(self, hypotheses: tuple[Hypothesis, ...] = ()) -> None:
        self.hypotheses = hypotheses
        self.calls: list[tuple[str, int]] = []

    def generate(self, claim: str, limit: int = 5) -> tuple[Hypothesis, ...]:
        self.calls.append((claim, limit))
        return self.hypotheses


class RaisingHypothesisModel:
    """Hypothesis model that always raises (fail-soft verification)."""

    def generate(self, claim: str, limit: int = 5):
        raise RuntimeError("hypothesis model down")


@dataclass
class FakeHistoryProvider:
    """Duck-typed read-only history stand-in for meta-reasoning.

    Mirrors the ReasoningRecorder / ReasoningTraceRecorder surface:
    ``recent(n)``, ``count()``, ``summary()``.
    """

    records: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recent_calls: list[int] = []

    def recent(self, n: int = 10) -> list[Any]:
        self.recent_calls.append(n)
        return self.records[-n:] if n > 0 else []

    def count(self) -> int:
        return len(self.records)

    def summary(self) -> dict[str, Any]:
        return {"count": len(self.records)}

    @staticmethod
    def build_trace(
        trace_id: str = "t1",
        question: str = "Q",
        strategy_name: str = "DECOMPOSE",
        status_name: str = "COMPLETED",
        step_count: int = 1,
    ) -> ReasoningTrace:
        """Build a ReasoningTrace with the requested strategy/status."""
        from atlas.advanced_reasoning.models import (
            ReasoningStrategy,
            TraceStatus,
        )

        steps = tuple(
            ReasoningTraceStep(
                step_id=f"s{i}",
                description="d",
                premise_step_ids=(),
                conclusion="c",
            )
            for i in range(step_count)
        )
        assert hasattr(TraceStatus, status_name), f"bad status {status_name}"
        return ReasoningTrace(
            trace_id=trace_id,
            question=question,
            strategy=ReasoningStrategy[strategy_name],
            steps=steps,
            status=TraceStatus[status_name],
            conclusion="c",
            confidence=0.8,
        )


def causal_path(
    path_id: str,
    source: str = "a",
    target: str = "b",
    entity_ids: tuple[str, ...] = (),
    relation_types: tuple[str, ...] = (),
    confidence: float = 0.7,
) -> CausalPath:
    """Build a CausalPath with defaults for compact tests."""
    return CausalPath(
        path_id=path_id,
        source=source,
        target=target,
        entity_ids=entity_ids,
        relation_types=relation_types,
        confidence=confidence,
    )
