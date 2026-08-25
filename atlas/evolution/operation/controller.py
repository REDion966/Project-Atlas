"""Atlas Post-Core F7 - Autonomous Operation Controller.

A thin, bounded operational controller that wraps the existing F1-F6
adaptation pipeline with an explicit cooldown / budget / failure policy.

The controller NEVER approves, NEVER executes, NEVER calls an AI model,
NEVER creates a daemon or infinite loop, and NEVER introduces a new
infrastructure subsystem. It is manually invoked by an external host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from atlas.evolution.operation.policy import OperationDecision, OperationPolicy


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


#: One F6 adaptation-cycle callable returning an AdaptationCycleResult-like.
CycleRunner = Callable[..., Any]

#: Optional callable returning True when useful work exists.
WorkProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Bounded, deterministic result of one operation invocation.

    Attributes:
        operation_id: Monotonic identifier for this run.
        decision: OperationDecision for this run.
        status: ok | partial | failed | cooldown | no_work.
        cycles_ran: number of adaptation cycles actually invoked.
        useful_work: whether meaningful work signals were present.
        consecutive_failures: consecutive failed-cycle counter.
        cooldown_remaining_seconds: cooldown left after the last cycle.
        adaptation_cycle_id: id of the most recent cycle run.
        candidate_ids: bounded DRAFT candidate ids produced.
        proposal_ids: bounded DRAFT proposal ids produced.
        evaluation_count: F5 evaluations produced (when injected).
        feedback_count: F5 feedback records produced (when injected).
        truncated: stages deterministically truncated (bounded).
        failures: bounded (stage, message) fail-closed records.
        ran_at: when this run happened.
    """

    operation_id: str
    decision: OperationDecision
    status: str = "ok"
    cycles_ran: int = 0
    useful: bool = False
    consecutive_failures: int = 0
    cooldown_remaining_seconds: float = 0.0
    adaptation_cycle_id: str = ""
    candidate_ids: tuple[str, ...] = ()
    proposal_ids: tuple[str, ...] = ()
    evaluation_count: int = 0
    feedback_count: int = 0
    truncated: tuple[str, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    ran_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "decision": self.decision.name,
            "status": self.status,
            "cycles_ran": self.cycles_ran,
            "useful": self.useful,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_remaining_seconds": self.cooldown_remaining_seconds,
            "adaptation_cycle_id": self.adaptation_cycle_id,
            "candidate_ids": list(self.candidate_ids),
            "proposal_ids": list(self.proposal_ids),
            "evaluation_count": self.evaluation_count,
            "feedback_count": self.feedback_count,
            "truncated": list(self.truncated),
            "failures": list(self.failures),
            "ran_at": self.ran_at.isoformat(),
        }


class OperationController:
    """Thin, bounded, manually-invoked operational controller around F6.

    Args:
        policy: Deterministic OperationPolicy (default fresh policy).
        cycle_runner: Optional callable that runs one bounded adaptation cycle
            (e.g. ``Atlas.run_adaptation_cycle``). When omitted, ``run_operation``
            returns a bounded fail-closed result because no runner is set.
        work_probe: Optional deterministic callable returning True when useful
            work exists. When omitted, useful_work is derived from the F6
            cycle result (non-empty candidates / proposals / env changes).
        evaluator: Optional F5 AdaptationEvaluator. When provided, produced
            DRAFT proposals are evaluated (evaluation-only; never execution).
        evolution_memory: Optional duck-typed EXISTING EvolutionMemory.
        learning_memory: Optional duck-typed EXISTING LearningMemory.
        now: Optional clock callable (UTC) - injectable for tests.
    """

    def __init__(
        self,
        policy: OperationPolicy | None = None,
        cycle_runner: CycleRunner | None = None,
        work_probe: WorkProbe | None = None,
        evaluator: Any | None = None,
        evolution_memory: Any | None = None,
        learning_memory: Any | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy or OperationPolicy()
        self._cycle_runner = cycle_runner
        self._work_probe = work_probe
        self._evaluator = evaluator
        self._evolution_memory = evolution_memory
        self._learning_memory = learning_memory
        self._now = now or utc_now

        # Bounded in-memory cross-invocation state (cooldown / failures).
        self._last_cycle_at: datetime | None = None
        self._consecutive_failures = 0
        self._operation_counter = 0

    @property
    def policy(self) -> OperationPolicy:
        """The applied policy (read-only)."""
        return self._policy

    @property
    def operation_counter(self) -> int:
        """Number of explicit operation invocations driven by this controller."""
        return self._operation_counter

    @property
    def consecutive_failures(self) -> int:
        """Running consecutive failed-cycle counter."""
        return self._consecutive_failures

    def run_operation(
        self,
        *,
        knowledge_refs=(),
        lifecycle_targets=(),
        supplied_changes=(),
        evaluate_pairs=(),
        max_cycles: int | None = None,
        now: datetime | None = None,
    ) -> OperationResult:
        """Run ONE bounded operation invocation (manually/external drive).

        1. cooldown check           -> COOLDOWN_ACTIVE
        2. work probe (if injected) -> NO_WORK when no meaningful work
        3. derive useful_work from the F6 cycle result (when no probe)
        4. bounded budget loop over EXISTING adaptation cycle runner
        5. fail-closed: failures are bounded and surfaced, never raise
        6. never approve / execute / call an AI model
        """
        self._operation_counter += 1
        op_id = f"OP-{self._operation_counter:06d}"
        ran_at = now if now is not None else self._now()
        failures: list[tuple[str, str]] = []
        truncated: list[str] = []
        proposal_ids: list[str] = []
        candidate_ids: list[str] = []
        eval_count = 0
        feedback_count = 0
        cycles_run = 0
        useful = False
        cycle_id = ""

        # 1. Cooldown.
        if self._last_cycle_at is not None:
            gap = (ran_at - self._last_cycle_at).total_seconds()
            remaining = max(0.0, self._policy.cooldown_seconds - gap)
        else:
            remaining = 0.0
        if remaining > 0:
            return OperationResult(
                operation_id=op_id,
                decision=OperationDecision.COOLDOWN_ACTIVE,
                status="cooldown",
                cooldown_remaining_seconds=round(remaining, 3),
                ran_at=ran_at,
            )

        # 2. Deterministic work probe (if any) - fail closed.
        if self._work_probe is not None:
            try:
                probe = bool(self._work_probe())
            except Exception as exc:
                failures.append(("work_probe", _bounded_text(exc)))
                return OperationResult(
                    operation_id=op_id,
                    decision=OperationDecision.NO_WORK,
                    status="partial",
                    useful=False,
                    failures=tuple(failures),
                    ran_at=ran_at,
                )
            if not probe:
                return OperationResult(
                    operation_id=op_id,
                    decision=OperationDecision.NO_WORK,
                    status="ok",
                    useful=False,
                    failures=tuple(failures),
                    ran_at=ran_at,
                )

        # 3. Bounded budget loop over the EXISTING adaptation cycle runner.
        budget = max_cycles or self._policy.max_cycles_per_invocation
        budget = min(budget, self._policy.max_budget_cycles)
        for _ in range(budget):
            if self._cycle_runner is None:
                failures.append(("cycle", "cycle runner not configured"))
                truncated.append("operation_cycles")
                break
            try:
                cycle = self._cycle_runner(
                    knowledge_refs=knowledge_refs,
                    lifecycle_targets=lifecycle_targets,
                    supplied_changes=supplied_changes,
                    evaluate_pairs=evaluate_pairs,
                )
            except Exception as exc:
                self._consecutive_failures += 1
                failures.append(("cycle", _bounded_text(exc)))
                cycles_run += 1
                if (
                    self._consecutive_failures
                    >= self._policy.max_consecutive_failures
                ):
                    truncated.append("consecutive_failures")
                    break
                continue

            self._last_cycle_at = ran_at
            cycles_run += 1
            self._consecutive_failures = 0
            cycle_id = getattr(cycle, "cycle_id", "") or ""

            props = tuple(getattr(cycle, "proposals", None) or ())
            cands = tuple(getattr(cycle, "candidates", None) or ())
            envs = tuple(getattr(cycle, "environment_changes", None) or ())
            if props or cands or envs:
                useful = True
            for p in props:
                pid = getattr(p, "proposal_id", "")
                if pid and pid not in proposal_ids:
                    proposal_ids.append(pid)
            for c in cands:
                cid = getattr(c, "candidate_id", "")
                if cid and cid not in candidate_ids:
                    candidate_ids.append(cid)

            # The cycle run doubles as the deterministic work detector: when
            # no work probe is injected and the F6 result carries no
            # candidates/proposals/env changes, stop early (NO_WORK).
            if not useful and cycles_run >= 1:
                truncated.append("operation_cycles")
                break

            # Optional F5 evaluation of produced DRAFT proposals (eval only).
            if self._evaluator is not None and props:
                for p in props:
                    try:
                        evaluation = self._evaluator.evaluate_proposal(p, now=ran_at)
                    except Exception as exc:
                        failures.append(("evaluation", _bounded_text(exc)))
                        continue
                    if getattr(evaluation, "evaluation_id", ""):
                        eval_count += 1
                    try:
                        feedback = self._evaluator.feedback_for(evaluation, now=ran_at)
                    except Exception:
                        feedback = None
                    if feedback is not None and getattr(feedback, "feedback_id", ""):
                        feedback_count += 1

        # 4. Decide result.
        if self._consecutive_failures >= self._policy.max_consecutive_failures:
            decision = OperationDecision.FAILURE_LIMIT
            status = "failed"
            truncated.append("consecutive_failures")
        elif cycles_run and useful:
            decision = OperationDecision.RAN_LIMITED
            status = "partial" if failures else "ok"
        elif failures and not cycles_run:
            decision = OperationDecision.NO_WORK
            status = "partial"
        elif not useful:
            # The probe/cycle found no meaningful work: WAIT for next wake.
            decision = OperationDecision.NO_WORK
            status = "ok"
        else:
            decision = OperationDecision.NO_WORK
            status = "ok"

        # 5. Best-effort ledger record into EXISTING EvolutionMemory/Learning.
        self._record_ledger(
            op_id, decision, cycles_run, useful,
            proposal_ids, failures, ran_at,
        )

        return OperationResult(
            operation_id=op_id,
            decision=decision,
            status=status,
            cycles_ran=cycles_run,
            useful=useful,
            consecutive_failures=self._consecutive_failures,
            adaptation_cycle_id=cycle_id,
            candidate_ids=tuple(candidate_ids),
            proposal_ids=tuple(proposal_ids),
            evaluation_count=eval_count,
            feedback_count=feedback_count,
            truncated=tuple(dict.fromkeys(truncated)),
            failures=tuple(failures),
            ran_at=ran_at,
        )

    def _record_ledger(
        self,
        op_id: str,
        decision: Any,
        cycles: int,
        useful: bool,
        proposal_ids: list[str],
        failures: tuple[tuple[str, str], ...],
        timestamp: datetime,
    ) -> None:
        """Best-effort bounded ledger record into the EXISTING EvolutionMemory.

        Uses the duck-typed ``store_record(EvolutionRecord)`` surface of the
        existing memory; never creates a new store or DB. Failures are ignored
        (best-effort) so the F7 path is never broken by persistence.
        """
        store_record = getattr(self._evolution_memory, "store_record", None)
        if store_record is None:
            return
        from atlas.evolution.models import EvolutionRecord

        try:
            store_record(EvolutionRecord(
                record_id=f"OPR-{op_id}",
                event_type="operation_cycle",
                description=(
                    f"{getattr(decision, 'name', str(decision))} "
                    f"cycles={cycles} useful={useful}"
                ),
                related_ids=list(proposal_ids),
                timestamp=timestamp,
                metadata={
                    "operation_id": op_id,
                    "decision": getattr(decision, "name", str(decision)),
                    "cycles": cycles,
                    "useful": useful,
                    "failures": list(failures),
                },
            ))
        except Exception:
            pass


def _bounded_text(exc: Exception, limit: int = 200) -> str:
    """Return a bounded, secret-free error message for a failure."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]