"""Atlas Post-Core F6 — Full Adaptation Engine Orchestration.

The thinnest possible composition layer that bundles the EXISTING F1-F5 /
Phase-E APIs into one bounded, manually-triggered adaptation cycle:

    EnvironmentObserver (F1)
        -> KnowledgeFreshnessAssessor (F2)
        -> CapabilityLifecycleAssessor (F3)
        -> AdaptationDecisionEngine (F4)      -> DRAFT EvolutionProposal
        -> EXISTING GOVERNANCE HAND-OFF        (stopped here)
        -> (optional) AdaptationEvaluator (F5) for EXISTING proposal/outcome

F6 is an ORCHESTRATOR, NOT a governance or execution subsystem:
  * it NEVER approves a proposal (all generated proposals stay DRAFT)
  * it NEVER executes / sandboxes / subprocesses
  * it NEVER invokes SelfDevelopmentLoop / DevelopmentPlanner
  * it NEVER bypasses ApprovalManager / AuthorizationManager
  * it NEVER creates a second EventBus / scheduler / memory / registry
  * it NEVER auto-runs from Atlas.tick() or a background thread

Bounded + deterministic + fail-closed by construction: every stage truncates
deterministically, ordering is stable (never unordered iteration), invalid
inputs are filtered with bounded failures instead of raising, and repeated
equivalent inputs produce an equivalent cycle result.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from atlas.evolution.environment.models import EnvironmentChange
from atlas.evolution.environment.observer import EnvironmentObserver
from atlas.evolution.freshness.assessor import KnowledgeFreshnessAssessor
from atlas.evolution.freshness.models import KnowledgeRef
from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor
from atlas.evolution.lifecycle.models import LifecycleAssessment, LifecycleTarget
from atlas.evolution.adaptation.engine import AdaptationDecisionEngine
from atlas.evolution.adaptation.evaluation import (
    AdaptationEvaluation,
    AdaptationFeedback,
)
from atlas.evolution.adaptation.evaluator import AdaptationEvaluator
from atlas.evolution.adaptation.models import AdaptationProposalCandidate
from atlas.evolution.models import EvolutionProposal


def _entity_key(item: Any) -> str:
    """Stable identity key of an F1 EnvironmentChange-like object."""
    entity = getattr(item, "entity", None)
    if entity is None:
        return ""
    key = getattr(entity, "key", "") or ""
    if key:
        return str(key)
    domain = getattr(entity, "domain", None)
    domain_name = domain.name if hasattr(domain, "name") else str(domain or "")
    eid = getattr(entity, "entity_id", "")
    return f"{domain_name}:{eid}"


def _bounded_text(exc: Exception, limit: int = 200) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]


def _stable_cycle_id(
    changes: list[Any],
    refs: list[Any],
    targets: list[Any],
    proposals: list[Any],
    failures: list[tuple[str, str]],
) -> str:
    """Deterministic content-derived cycle identifier (no random/sequence)."""
    parts: list[str] = []
    for ch in changes:
        parts.append("E:" + _entity_key(ch))
    for r in refs:
        parts.append("K:" + r.knowledge_id)
    for t in targets:
        parts.append("T:" + getattr(t, "key", ""))
    for p in proposals:
        parts.append("P:" + p.proposal_id)
    for stage, msg in failures:
        parts.append(f"F:{stage}:{msg}")
    seed = "\x1f".join(sorted(part for part in parts if part))
    return "CYCLE-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class AdaptationCycleResult:
    """Bounded, deterministic result of one F6 adaptation cycle.

    Attributes:
        cycle_id: Deterministic content-derived cycle identifier.
        status: ``"ok"`` | ``"partial"`` | ``"failed"`` (fail-closed).
        environment_changes: F1 EnvironmentChange records observed.
        freshness_assessments: F2 freshness assessments (ordered by id).
        freshness_candidates: F2 stale knowledge candidates (ordered).
        lifecycle_assessments: F3 lifecycle assessments (ordered).
        candidates: F4 AdaptationProposalCandidate records (DRAFT, bounded).
        proposals: DRAFT EvolutionProposals (never APPROVED).
        evaluations: F5 evaluations, when evaluate_pairs were supplied.
        feedback: F5 feedback, when evaluations were produced.
        truncated: Stages that were deterministically truncated.
        failures: Tuple of ``(stage, message)`` bounded fail-closed records.
        ran_at: UTC timestamp of the run.
    """

    cycle_id: str
    status: str = "ok"
    environment_changes: tuple[Any, ...] = ()
    freshness_assessments: tuple[Any, ...] = ()
    freshness_candidates: tuple[Any, ...] = ()
    lifecycle_assessments: tuple[LifecycleAssessment, ...] = ()
    candidates: tuple[AdaptationProposalCandidate, ...] = ()
    proposals: tuple[EvolutionProposal, ...] = ()
    evaluations: tuple[AdaptationEvaluation, ...] = ()
    feedback: tuple[AdaptationFeedback, ...] = ()
    truncated: tuple[str, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    ran_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "status": self.status,
            "environment_change_ids": [_entity_key(c) for c in self.environment_changes],
            "freshness_assessment_ids": [
                a.knowledge_id for a in self.freshness_assessments
            ],
            "freshness_candidate_ids": [
                c.knowledge_id for c in self.freshness_candidates
            ],
            "lifecycle_target_keys": [
                a.target_key for a in self.lifecycle_assessments
            ],
            "candidate_ids": [c.candidate_id for c in self.candidates],
            "proposal_ids": [p.proposal_id for p in self.proposals],
            "proposal_statuses": [p.status.name for p in self.proposals],
            "feedback_ids": [f.feedback_id for f in self.feedback],
            "truncated": list(self.truncated),
            "failures": list(self.failures),
            "ran_at": self.ran_at.isoformat(),
        }


class AdaptationOrchestrator:
    """Compose F1-F5 into one bounded, manually-triggered adaptation cycle.

    Args:
        environment_observer: F1 EnvironmentObserver (or any object with
            ``observe_cycle()``). ``None`` disables the F1 step.
        freshness_assessor: F2 KnowledgeFreshnessAssessor (fresh default).
        lifecycle_assessor: F3 CapabilityLifecycleAssessor (fresh default).
        decision_engine: F4 AdaptationDecisionEngine (fresh by default).
        evaluator: F5 AdaptationEvaluator (fresh by default).
        now: Optional clock; for deterministic internal timestamps.
    """

    def __init__(
        self,
        environment_observer: EnvironmentObserver | None = None,
        freshness_assessor: KnowledgeFreshnessAssessor | None = None,
        lifecycle_assessor: CapabilityLifecycleAssessor | None = None,
        decision_engine: AdaptationDecisionEngine | None = None,
        evaluator: AdaptationEvaluator | None = None,
        now: Any | None = None,
    ) -> None:
        self._environment_observer = environment_observer
        self._freshness_assessor = (
            freshness_assessor or KnowledgeFreshnessAssessor(now=now)
        )
        self._lifecycle_assessor = (
            lifecycle_assessor or CapabilityLifecycleAssessor(now=now)
        )
        self._decision_engine = decision_engine or AdaptationDecisionEngine()
        self._evaluator = evaluator or AdaptationEvaluator(now=now)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cycle_count = 0

    @property
    def cycle_count(self) -> int:
        """Number of completed cycles this orchestrator drove (0 before first)."""
        return self._cycle_count

    # ------------------------------------------------------------------
    # One bounded, manually-triggered cycle
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        knowledge_refs: Iterable[KnowledgeRef] = (),
        lifecycle_targets: Iterable[LifecycleTarget] = (),
        supplied_changes: Iterable[EnvironmentChange] = (),
        evaluate_pairs: Iterable[tuple[Any, Any]] = (),
        max_changes: int = 100,
        max_knowledge: int = 100,
        max_lifecycle: int = 100,
        max_candidates: int = 5,
        max_evaluations: int = 10,
        now: datetime | None = None,
    ) -> AdaptationCycleResult:
        """Run one bounded F1-F5 (optional F5) adaptation cycle.

        F6 stops at the DRAFT proposal boundary; F5 evaluation only when
        explicit ``evaluate_pairs`` are supplied (existing already-approved
        proposals/outcomes). Nothing is approved, executed, or promoted.
        """
        self._cycle_count += 1
        failures: list[tuple[str, str]] = []
        truncated: list[str] = []

        # --- F1: environment observation (bounded) --------------------
        changes = self._collect_changes(supplied_changes, failures)
        if len(changes) > max(1, max_changes):
            changes = changes[: max(1, max_changes)]
            truncated.append("environment")

        # --- F2: knowledge freshness (bounded) ------------------------
        refs = [r for r in knowledge_refs if isinstance(r, KnowledgeRef)]
        if len(refs) > max(1, max_knowledge):
            refs = refs[: max(1, max_knowledge)]
            truncated.append("knowledge")
        freshness: tuple[Any, ...] = ()
        stale: tuple[Any, ...] = ()
        if refs:
            freshness = tuple(
                self._freshness_assessor.assess_many(
                    refs, changes=changes, now=now
                )
            )
            stale = tuple(
                self._freshness_assessor.find_stale_candidates(
                    refs, changes=changes, now=now
                )
            )[: max(1, max_knowledge)]

        # --- F3: lifecycle assessment (bounded) -----------------------
        targets = [t for t in lifecycle_targets if isinstance(t, LifecycleTarget)]
        if len(targets) > max(1, max_lifecycle):
            targets = targets[: max(1, max_lifecycle)]
            truncated.append("lifecycle")
        lifecycle_result = self._lifecycle_assessor.assess_many(
            targets, changes=changes, freshness=freshness, now=now
        )
        lifecycle = tuple(lifecycle_result.assessments)

        # --- F4: adaptation decision (bounded, DRAFT only) ------------
        candidates = self._decision_engine.decide(
            lifecycle, max_candidates=max_candidates
        )
        if len(candidates) > max(1, max_candidates):
            candidates = candidates[: max(1, max_candidates)]
            truncated.append("candidates")
        proposals = self._decision_engine.build_proposals(candidates)

        # --- Optional F5: evaluation + feedback ------------------------
        evaluation_items: list[AdaptationEvaluation] = []
        feedback_items: list[AdaptationFeedback] = []
        for pair in evaluate_pairs or ():
            if not isinstance(pair, (tuple, list)) or len(pair) < 1:
                failures.append(("evaluation", "malformed evaluation pair"))
                continue
            proposal = pair[0]
            outcome = pair[1] if len(pair) > 1 else None
            if not isinstance(proposal, EvolutionProposal):
                failures.append(("evaluation", "not an EvolutionProposal"))
                continue
            if len(evaluation_items) >= max(1, max_evaluations):
                truncated.append("evaluation")
                break
            evaluation = (
                self._evaluator.evaluate_outcome(proposal, outcome, now=now)
                if outcome is not None
                else self._evaluator.evaluate_proposal(proposal, now=now)
            )
            evaluation_items.append(evaluation)
            feedback_items.append(self._evaluator.feedback_for(evaluation, now=now))

        # --- Overall status (bounded fail-closed) ----------------------
        status: str
        if any(stage == "environment" for stage, _ in failures):
            status = "failed"
        elif failures:
            status = "partial"
        else:
            status = "ok"

        cycle_id = _stable_cycle_id(changes, refs, targets, proposals, failures)

        return AdaptationCycleResult(
            cycle_id=cycle_id,
            status=status,
            environment_changes=tuple(changes),
            freshness_assessments=tuple(freshness),
            freshness_candidates=tuple(stale),
            lifecycle_assessments=tuple(lifecycle),
            candidates=tuple(candidates),
            proposals=tuple(proposals),
            evaluations=tuple(evaluation_items),
            feedback=tuple(feedback_items),
            truncated=tuple(dict.fromkeys(truncated)),
            failures=tuple(dict.fromkeys(failures)),
            ran_at=now or self._now(),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _collect_changes(
        self,
        supplied: Iterable[Any],
        failures: list[tuple[str, str]],
    ) -> list[Any]:
        """Run F1 observe_cycle (if installed) and merge supplied changes."""
        changes: list[Any] = []
        if self._environment_observer is not None:
            observe = getattr(self._environment_observer, "observe_cycle", None)
            if observe is None:
                failures.append(("environment", "no observe_cycle()"))
            else:
                try:
                    result = observe()
                    changes.extend(x for x in (getattr(result, "changes", ()) or ()))
                except Exception as exc:  # fail-closed, bounded
                    failures.append(
                        ("environment", f"env observer failed: {_bounded_text(exc)}")
                    )
        for item in supplied or ():
            if getattr(item, "entity", None) is None:
                failures.append(("environment", "malformed environment change"))
                continue
            changes.append(item)
        # Stable ordering + dedup by entity key (never unordered iteration).
        deduped: dict[str, Any] = {}
        for ch in changes:
            key = _entity_key(ch)
            if not key:
                key = f"__raw:{type(ch).__name__}"
            if key not in deduped:
                deduped[key] = ch
        return sorted(deduped.values(), key=_entity_key)