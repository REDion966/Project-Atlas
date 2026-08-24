"""
Atlas Evolution — Self-Development Loop — Phase E5

The bounded, governed iteration loop connecting the E2 sandbox execution
foundation, the E3 DevelopmentPlanner, and the E4 sandbox toolchain into an
inspectable development workflow.

Run flow::

    approved EvolutionProposal
        → DevelopmentPlanner.plan()              (E3)
        → ordered DevelopmentSteps
        → per-iteration lifecycle:
            IMPLEMENT → E2 CodeApplier inside a CodeSandbox
            VERIFY     → E4 pytest inside the same workspace
            ACCEPT     → only when the change was verified + tests passed
        → DevelopmentOutcome recorded
        → (optional) LearningInsight stored in the existing LearningMemory
        → later iterations biased by prior outcomes (bounded by max_iterations)

GOVERNANCE / SAFETY CONTRACT
------------------------------
* The loop consumes an ALREADY-APPROVED proposal. It never calls the
  authorization, rule, constraint, or approval subsystems; the existing
  DevelopmentPlanner gate (``ProposalStatus.APPROVED``) plus an explicit
  pre-flight check here enforce the approval lifecycle.
* The loop NEVER mutates the real repository. Every write goes through a disposable
  ``CodeSandbox`` root that is removed after each iteration.
* The loop never promotes code to the real workspace. Promotion is the job of the
  existing governance/approval machinery; an optional injected ``promotion_gate`` is consulted and,
  when it refuses, the run records ``GOVERNANCE_DENIED``.
* No infinite autonomy: ``max_iterations`` bounds the loop; there is no recursion, no
  task spawning, no self-invocation.
* No authority escalation: the loop mints no authorizations, does not alter the
  constitutional CODE boundary, and always preserves the sandbox.

LEARNING
---------
Development outcomes are bridged into the EXISTING ``LearningMemory`` as ``LearningInsight`` records
(or to any injected store exposing ``record(outcome)``). Accumulated history is given to the
``change_supplier`` on later iterations so prior failures can bias the next bounded attempt —
without inventing a new memory subsystem.

Pure infrastructure. No gateway. No AI. No kernel access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from atlas.evolution.autonomy.code_execution import CodeApplier
from atlas.evolution.autonomy.code_sandbox import CodeChangeSet, CodeSandbox
from atlas.evolution.autonomy.sandbox_tools import SandboxWorkspace, pytest_tool
from atlas.evolution.development_planner import DevelopmentPlanner, DevelopmentPlannerError
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    DevelopmentPlan,
    DevelopmentStep,
    SandboxWorkload,
    StepPhase,
    StepStatus,
)
from atlas.evolution.models import EvolutionProposal, ProposalStatus
#: Default iteration budget when the caller passes ``None``.
DEFAULT_MAX_ITERATIONS: int = 3


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DevelopmentRunResult:
    """Outcome of a bounded self-development run.

    Attributes:
        status:          Terminal run status.
        plan:            The DevelopmentPlan that was executed (``None`` on early refusal).
        outcomes:         Ordered per-iteration DevelopmentOutcome records.
        iterations_used: Number of consumed iterations.
        message:          Human-readable summary.
        sandbox_path:     The last sandbox root (removed after the run);
            empty when no sandbox was created.
    """

    status: DevelopmentOutcomeStatus
    plan: DevelopmentPlan | None = None
    outcomes: list[DevelopmentOutcome] = field(default_factory=list)
    iterations_used: int = 0
    message: str = ""
    sandbox_path: str = ""


# ---------------------------------------------------------------------------
# Default change supplier
# ---------------------------------------------------------------------------


def metadata_change_supplier(
    proposal: EvolutionProposal,
    history: list[DevelopmentOutcome] | None = None,
) -> SandboxWorkload | None:
    """Build a SandboxWorkload from proposal metadata.

    Reads ``proposal.metadata["code_changes"]`` (list of
    ``{"path": ..., "content": ...}`` dicts) and ``proposal.metadata["test_files"]``
    (``{path: content}``). Returns ``None`` when no code change is present.
    ``history`` is accepted for protocol compatibility with stateful suppliers.
    """
    raw_changes = proposal.metadata.get("code_changes", [])
    if not isinstance(raw_changes, list) or not raw_changes:
        return None
    changes = tuple(
        {"path": str(item["path"]), "content": str(item["content"])}
        for item in raw_changes
        if isinstance(item, dict) and "path" in item and "content" in item
    )
    if not changes:
        return None
    test_files = proposal.metadata.get("test_files", {})
    if not isinstance(test_files, dict):
        test_files = {}
    return SandboxWorkload(
        code_changes=changes,
        test_files={str(k): str(v) for k, v in test_files.items()},
        verify_target=str(proposal.metadata.get("verify_target", "")),
    )


def _code_request(
    proposal: EvolutionProposal,
    workload: SandboxWorkload,
    iteration: int,
) -> Any:
    """Build a CODE EvolutionRequest for the E2 applier."""
    from atlas.evolution.autonomy.models import EvolutionRequest
    from atlas.evolution.governance.models import ScopeType

    return EvolutionRequest(
        request_id=f"E5-{proposal.proposal_id}-{iteration}",
        source=proposal.proposal_id,
        target_scope=ScopeType.CODE,
        change_payload={"code_changes": list(workload.code_changes)},
    )


class SandboxImplementer:
    """Apply a SandboxWorkload inside a CodeSandbox via E2 CodeApplier.

    Uses the same machinery as SandboxCodeExecutor: snapshot prior state,
    apply through CodeApplier, verify with a read-back probe, restore on
    failure. Never touches the real repository.
    """

    def apply(
        self,
        sandbox: CodeSandbox,
        proposal: EvolutionProposal,
        workload: SandboxWorkload,
        iteration: int,
    ) -> tuple[bool, list[str], str]:
        """Return ``(success, changed_files, message)``."""
        changeset = CodeChangeSet.from_payload(
            {"code_changes": list(workload.code_changes)}
        )
        request = _code_request(proposal, workload, iteration)

        reader = sandbox.reader()
        writer = sandbox.writer()
        paths = [change.path for change in changeset.changes]
        snapshot = sandbox.snapshot(paths)

        applier = CodeApplier()
        apply_result = applier.apply(request, writer)
        if not apply_result.success:
            sandbox.restore(snapshot)
            return False, paths, apply_result.error or "apply failed"

        verification = applier.verify(request, reader)
        if not verification.passed:
            sandbox.restore(snapshot)
            return False, paths, "E2 verification failed; sandbox restored"

        return True, paths, ""

    def __call__(
        self,
        sandbox: CodeSandbox,
        proposal: EvolutionProposal,
        workload: SandboxWorkload,
        iteration: int,
    ) -> tuple[bool, list[str], str]:
        """Callable alias of ``apply`` so the loop can call it uniformly."""
        return self.apply(sandbox, proposal, workload, iteration)


class SandboxVerifier:
    """Run E4 pytest against a sandbox workspace.

    ``run`` returns ``(passed, test_outcome, message)``.
    """

    def run(
        self,
        workspace: str,
        target: str,
        timeout: float | None = None,
    ) -> tuple[bool, str, str]:
        params: dict[str, Any] = {"workspace": workspace}
        if target:
            params["target"] = target
        if timeout is not None:
            params["timeout_seconds"] = timeout
        result = pytest_tool().handler(params)
        outcome = result.output.get("outcome", "error")
        return result.success and outcome == "passed", outcome, result.error or ""

    def __call__(
        self,
        workspace: str,
        target: str,
        timeout: float | None = None,
    ) -> tuple[bool, str, str]:
        """Callable alias of ``run`` so the loop can call it uniformly."""
        return self.run(workspace, target, timeout)


# ---------------------------------------------------------------------------
# Learning bridge
# ---------------------------------------------------------------------------


def build_learning_insight(outcome: DevelopmentOutcome) -> Any:
    """Convert a DevelopmentOutcome into an existing LearningInsight."""
    from atlas.learning_engine.models import (
        InsightImportance,
        LearningCategory,
        LearningInsight,
    )

    is_success = outcome.outcome == DevelopmentOutcomeStatus.SUCCESS
    return LearningInsight(
        insight_id=(
            f"E5-{outcome.proposal_id}-{outcome.iteration}-"
            f"{int(outcome.recorded_at.timestamp())}"
        ),
        category=(
            LearningCategory.TOOL_USAGE
            if is_success
            else LearningCategory.FAILURE_AVOIDANCE
        ),
        title=(
            "Self-development iteration succeeded"
            if is_success
            else "Self-development iteration failed"
        ),
        description=outcome.message or outcome.outcome.name.lower(),
        importance=(
            InsightImportance.LOW if is_success else InsightImportance.MEDIUM
        ),
        confidence=1.0 if is_success else 0.5,
        observation_count=1,
        source_pipeline_ids=[outcome.plan_id] if outcome.plan_id else [],
        reusable=True,
        applicable_areas=list(outcome.changed_files) or ["self_development"],
        metadata={
            "outcome": outcome.outcome.name,
            "proposal_id": outcome.proposal_id,
            "iteration": outcome.iteration,
            "effectiveness_proxy": outcome.effectiveness_proxy,
            "test_outcome": outcome.test_outcome,
            "verification_passed": outcome.verification_passed,
            "rollback_occurred": outcome.rollback_occurred,
        },
    )


def _record_learning(
    outcomes: list[DevelopmentOutcome],
    store: Any,
) -> None:
    """Record outcomes into an existing learning store.

    ``store`` may be a ``LearningMemory`` (then ``store_insights`` is
    used) or any object exposing ``record(outcome)``.
    """
    insights = [build_learning_insight(o) for o in outcomes]
    if hasattr(store, "store_insights"):
        store.store_insights(insights)
    elif hasattr(store, "record"):
        store.record(outcomes)


# ---------------------------------------------------------------------------
# The SelfDevelopmentLoop
# ---------------------------------------------------------------------------


#: Sentinel distinguishing "not provided" from an explicit ``None``.
_UNSET = object()


class SelfDevelopmentLoop:
    """A bounded, governed development loop over an approved proposal.

    Purely mechanics — never authorizes, never promotes to the real
    workspace by itself, never bypasses governance. It:

    1. Pre-flights that the proposal is already ``ProposalStatus.APPROVED``.
    2. Delegates planning to E3 ``DevelopmentPlanner``.
    3. For each bounded iteration (up to ``max_iterations``):
       - seeds test files from the ``SandboxWorkload``,
       - executes the E3 plan steps in order,
       - IMPLEMENT via E2 ``SandboxImplementer`` (CodeApplier on a CodeSandbox),
       - VERIFY / TEST_SPEC via E4 ``SandboxVerifier`` (pytest in the workspace),
       - ACCEPT only when implementation + verification both passed,
       - records a bounded, secret-free ``DevelopmentOutcome``.
    4. Stores outcomes as ``LearningInsight`` in the injected
       ``learning_store`` (an existing ``LearningMemory``).
    5. Handles the accumulated ``history`` to the change-supplier so the next
       attempt can be biased by prior outcomes — always bounded.

    No recursion. No task spawning. No authority escalation.
    """

    def __init__(
        self,
        planner: DevelopmentPlanner | None = None,
        change_supplier: Callable[[EvolutionProposal, list[DevelopmentOutcome]],
                                  SandboxWorkload | None] | None = None,
        implementer: Callable[..., tuple[bool, list[str], str]] | None = _UNSET,
        verifier: Callable[..., tuple[bool, str, str]] | None = _UNSET,
        learning_store: Any | None = None,
        promotion_gate: Callable[[EvolutionProposal, DevelopmentOutcome], bool] | None = None,
        base_dir: str | None = None,
    ) -> None:
        self._planner = planner or DevelopmentPlanner()
        self._change_supplier = change_supplier or metadata_change_supplier
        self._implementer = SandboxImplementer() if implementer is _UNSET else implementer
        self._verifier = SandboxVerifier() if verifier is _UNSET else verifier
        self._learning_store = learning_store
        self._promotion_gate = promotion_gate
        self._base_dir = base_dir

    def run(
        self,
        proposal: EvolutionProposal,
        max_iterations: int | None = None,
    ) -> DevelopmentRunResult:
        """Run the bounded self-development loop for an approved proposal."""
        if proposal is None or proposal.status != ProposalStatus.APPROVED:
            return DevelopmentRunResult(
                status=DevelopmentOutcomeStatus.GOVERNANCE_DENIED,
                plan=None, outcomes=[], iterations_used=0,
                message="Proposal not APPROVED; refusing self-development.",
            )
        # Fail closed on malformed/incomplete objectives first.
        try:
            plan = self._planner.plan(proposal)
        except DevelopmentPlannerError as exc:
            return DevelopmentRunResult(
                status=DevelopmentOutcomeStatus.INVALID_OBJECTIVE,
                plan=None, outcomes=[], iterations_used=0,
                message=f"INVALID_OBJECTIVE: {exc}",
            )

        # Capability availability check (fail-closed).
        if self._implementer is None or self._verifier is None:
            return DevelopmentRunResult(
                status=DevelopmentOutcomeStatus.UNAVAILABLE_CAPABILITY,
                plan=plan, outcomes=[], iterations_used=0,
                message="Required self-development capability unavailable.",
            )

        budget = (
            DEFAULT_MAX_ITERATIONS if max_iterations is None else max_iterations
        )
        if budget < 0:
            budget = 0

        history: list[DevelopmentOutcome] = []
        outcomes: list[DevelopmentOutcome] = []
        last_sandbox_path = ""

        for iteration in range(1, budget + 1):
            workload = self._change_supplier(proposal, history)
            if workload is None:
                outcome = self._make_outcome(
                    DevelopmentOutcomeStatus.INVALID_OBJECTIVE,
                    proposal, plan, iteration,
                    message="Change supplier returned no code change.",
                )
                outcomes.append(outcome)
                self._record_outcome(outcome)
                return DevelopmentRunResult(
                    status=DevelopmentOutcomeStatus.INVALID_OBJECTIVE,
                    plan=plan, outcomes=outcomes, iterations_used=iteration,
                    message="INVALID_OBJECTIVE: no code change supplied.",
                )

            iteration_outcome, iter_sandbox = self._run_iteration(
                proposal, plan, workload, iteration,
            )
            last_sandbox_path = iter_sandbox
            outcomes.append(iteration_outcome)
            self._record_outcome(iteration_outcome)
            history.append(iteration_outcome)

            # Success inside the sandbox; consult the optional promotion gate.
            if iteration_outcome.outcome == DevelopmentOutcomeStatus.SUCCESS:
                if self._promotion_gate is not None \
                        and not self._promotion_gate(proposal, iteration_outcome):
                    denied = self._with_status(
                        iteration_outcome, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)
                    outcomes[-1] = denied
                    return DevelopmentRunResult(
                        status=DevelopmentOutcomeStatus.GOVERNANCE_DENIED,
                        plan=plan, outcomes=outcomes, iterations_used=iteration,
                        message="Promotion gate refused; no promotion performed.",
                        sandbox_path=last_sandbox_path,
                    )
                return DevelopmentRunResult(
                    status=DevelopmentOutcomeStatus.SUCCESS,
                    plan=plan, outcomes=outcomes, iterations_used=iteration,
                    message="Development completed inside sandbox.",
                    sandbox_path=last_sandbox_path,
                )
            # Else continue to the next bounded iteration.

        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED,
            plan=plan, outcomes=outcomes, iterations_used=budget,
            message=f"ITERATIONS_EXHAUSTED after {budget} iterations",
            sandbox_path=last_sandbox_path,
        )

    # ------------------------------------------------------------------
    # Iteration internals
    # ------------------------------------------------------------------

    def _run_iteration(
        self,
        proposal: EvolutionProposal,
        plan: DevelopmentPlan,
        workload: SandboxWorkload,
        iteration: int,
    ) -> tuple[DevelopmentOutcome, str]:
        """Execute one bounded iteration inside a disposable sandbox.

        Returns ``(outcome, sandbox_path)``. The sandbox is always cleaned
        up before returning.
        """
        code_sandbox: CodeSandbox | None = None
        sandbox_path = ""
        try:
            code_sandbox = CodeSandbox(base_dir=self._base_dir)
            workspace = SandboxWorkspace.from_code_sandbox(code_sandbox)
            sandbox_path = str(workspace.path)

            # Seed the test files for this workload.
            for rel_path, content in workload.test_files.items():
                workspace.write_text(rel_path, content)

            applied = False
            passed = False
            changed_files: list[str] = []
            apply_message = ""
            test_outcome = "error"
            test_message = ""

            # Ordered E3 lifecycle execution.
            for step in sorted(plan.steps, key=lambda s: s.order):
                step.status = StepStatus.IN_PROGRESS
                if step.phase == StepPhase.IMPLEMENT:
                    applied, changed_files, apply_message = self._implementer(
                        code_sandbox, proposal, workload, iteration)
                    step.status = (
                        StepStatus.COMPLETED if applied else StepStatus.FAILED
                    )
                elif step.phase == StepPhase.VERIFY:
                    if not applied:
                        step.status = StepStatus.SKIPPED
                        continue
                    passed, test_outcome, test_message = self._verifier(
                        workspace.path, workload.verify_target)
                    step.status = (
                        StepStatus.COMPLETED if passed else StepStatus.FAILED
                    )
                elif step.phase == StepPhase.TEST_SPEC:
                    # TEST_SPEC defines the test requirement; it is
                    # bookkeeping only (E3 lifecycle) and never executes.
                    step.status = StepStatus.COMPLETED
                elif step.phase == StepPhase.ACCEPT:
                    step.status = (
                        StepStatus.COMPLETED if applied and passed
                        else StepStatus.FAILED
                    )
                else:
                    step.status = StepStatus.COMPLETED

            if applied and passed:
                return self._make_outcome(
                    DevelopmentOutcomeStatus.SUCCESS,
                    proposal, plan, iteration,
                    message="Development iteration succeeded in sandbox.",
                    changed_files=changed_files,
                    verification_passed=True,
                    test_outcome=test_outcome,
                    effectiveness_proxy=1.0,
                ), sandbox_path

            return self._make_outcome(
                DevelopmentOutcomeStatus.FAILED,
                proposal, plan, iteration,
                message=apply_message or test_message or "iteration failed.",
                changed_files=changed_files,
                verification_passed=False,
                rollback_occurred=not applied,
                test_outcome=test_outcome or "error",
            ), sandbox_path
        except Exception as exc:  # fail closed on infrastructure errors
            return self._make_outcome(
                DevelopmentOutcomeStatus.FAILED,
                proposal, plan, iteration,
                message=f"iteration failed closed: {exc}",
            ), sandbox_path
        finally:
            if code_sandbox is not None:
                code_sandbox.cleanup()

    def _make_outcome(
        self,
        status: DevelopmentOutcomeStatus,
        proposal: EvolutionProposal,
        plan: DevelopmentPlan,
        iteration: int,
        message: str = "",
        changed_files: list[str] | None = None,
        verification_passed: bool = False,
        rollback_occurred: bool = False,
        test_outcome: str = "",
        effectiveness_proxy: float = 0.0,
    ) -> DevelopmentOutcome:
        """Build a bounded, secret-free DevelopmentOutcome."""
        return DevelopmentOutcome(
            outcome=status,
            proposal_id=proposal.proposal_id,
            plan_id=plan.plan_id,
            iteration=iteration,
            message=message,
            changed_files=list(changed_files or []),
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            test_outcome=test_outcome,
            effectiveness_proxy=effectiveness_proxy,
        )

    def _record_outcome(self, outcome: DevelopmentOutcome) -> None:
        """Bridge a single outcome into the existing learning store."""
        if self._learning_store is None:
            return
        _record_learning([outcome], self._learning_store)

    @staticmethod
    def _with_status(
        outcome: DevelopmentOutcome,
        status: DevelopmentOutcomeStatus,
    ) -> DevelopmentOutcome:
        """Return a copy of ``outcome`` with a different terminal status."""
        return DevelopmentOutcome(
            outcome=status,
            proposal_id=outcome.proposal_id,
            plan_id=outcome.plan_id,
            iteration=outcome.iteration,
            message=f"{status.name}: {outcome.message}".strip(),
            changed_files=list(outcome.changed_files),
            verification_passed=outcome.verification_passed,
            rollback_occurred=outcome.rollback_occurred,
            test_outcome=outcome.test_outcome,
            effectiveness_proxy=outcome.effectiveness_proxy,
            recorded_at=outcome.recorded_at,
            metadata=dict(outcome.metadata),
        )