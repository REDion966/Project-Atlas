"""
Atlas Goal Execution Engine — Phase 15.2

Orchestrates the adaptive goal execution loop:

  authorize → factory → adapter → gateway → binder → execute → record → result

The engine is the sole orchestrator. It depends only on interfaces; it
never imports ``EvolutionProposal`` fields or ``ToolRequest`` internals.

Fail-closed on: missing authorization, missing RuleEngine, missing executor,
non-user authorization, invalid goal state.

Pure logic. No infrastructure. No AI. No autonomous retries.
"""

from datetime import datetime
from typing import Any

from atlas.goals.execution_models import (
    ActionType,
    ExecutionAction,
    ExecutionOutcome,
    GoalAuthorization,
    GoalExecutionRecord,
    GoalExecutorResult,
)
from atlas.goals.goal_repository import GoalRepository
from atlas.goals.models import GoalCategory, GoalStatus, ImprovementGoal


# ---------------------------------------------------------------------------
# Category → canonical evolution area (shared with priority_engine)
# ---------------------------------------------------------------------------

_CATEGORY_TO_AREA: dict[GoalCategory, str] = {
    GoalCategory.PERFORMANCE: "runtime",
    GoalCategory.RELIABILITY: "reliability",
    GoalCategory.UNDERSTANDING: "understanding",
    GoalCategory.CAPABILITY: "capability",
    GoalCategory.TOOLING: "tooling",
    GoalCategory.EVOLUTION: "evolution",
    # ARCHITECTURE has no canonical evolution area — remains neutral
}


# ---------------------------------------------------------------------------
# ActionFactory — builds ExecutionAction from goal + authorization
# ---------------------------------------------------------------------------


class ActionFactory:
    """
    Builds a generic ``ExecutionAction`` envelope from an
    ``ImprovementGoal`` and ``GoalAuthorization``.

    The factory owns the envelope. The engine owns the orchestration.
    """

    @staticmethod
    def build(
        goal: ImprovementGoal,
        authorization: GoalAuthorization,
    ) -> ExecutionAction:
        """
        Create an executor-agnostic ExecutionAction for a goal.

        Args:
            goal: The approved ImprovementGoal.
            authorization: The stored GoalAuthorization.

        Returns:
            A new ExecutionAction with action_type TOOL_INVOCATION.
        """
        action_id = f"ACTION-{goal.goal_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return ExecutionAction(
            action_id=action_id,
            goal_id=goal.goal_id,
            action_type=ActionType.TOOL_INVOCATION,
            payload={
                "description": goal.description,
                "category": goal.category.name,
                "title": goal.title,
                "evidence_summary": f"Based on {goal.evidence_count} evidence items",
            },
            context={
                "goal_id": goal.goal_id,
                "category": goal.category.name,
                "priority_score": str(goal.priority.value),
                "authorized_by": authorization.authorized_by,
                "strategy_key": authorization.strategy_key,
            },
            expected_impact=goal.confidence,
            risk=0.5,
            confidence=goal.confidence,
        )


# ---------------------------------------------------------------------------
# GoalExecutionEngine — orchestrator
# ---------------------------------------------------------------------------


class GoalExecutionEngine:
    """
    Orchestrates user-authorized goal execution through the governance gate.

    Lifecycle: authorize → activate → execute → record.

    Dependencies are all optional via injection. Missing dependencies
    cause operations to fail closed with recorded errors — never silently.

    Binding constraints (per §12 of spec):
      - No goal executes without a GoalAuthorization with authorized_by
        == "user:cli".
      - ExecutionGateway is the only execution path.
      - No automatic retries — failed goals require fresh authorization.
      - settle() never blocks, never spawns threads.
    """

    def __init__(
        self,
        repository: GoalRepository | None = None,
        execution_gateway: Any = None,
        binder_registry: Any = None,
        outcome_tracker: Any = None,
        evolution_memory: Any = None,
        decision_intelligence: Any = None,
        event_bus: Any = None,
    ):
        """
        Initialise the goal execution engine.

        Args:
            repository: GoalRepository for goal state and authorizations.
            execution_gateway: EvolutionExecutionGateway instance.
            binder_registry: ExecutionActionBinderRegistry.
            outcome_tracker: OutcomeTracker for TrackedGoal creation.
            evolution_memory: EvolutionMemory for EvolutionRecord storage.
            decision_intelligence: DecisionIntelligenceEngine for
                strategy/planning-context snapshots at activation.
            event_bus: Optional EventBus for lifecycle events.
        """
        self._repository = repository or GoalRepository()
        self._gateway = execution_gateway
        self._binder_registry = binder_registry
        self._outcome_tracker = outcome_tracker
        self._evolution_memory = evolution_memory
        self._decision_intelligence = decision_intelligence
        self._event_bus = event_bus
        self._record_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def repository(self) -> GoalRepository:
        """Return the injected GoalRepository."""
        return self._repository

    @property
    def gateway(self) -> Any:
        """Return the injected execution gateway, or None."""
        return self._gateway

    @property
    def binder_registry(self) -> Any:
        """Return the injected binder registry, or None."""
        return self._binder_registry

    # ------------------------------------------------------------------
    # Activation (CLI surface)
    # ------------------------------------------------------------------

    def activate(
        self,
        goal_id: str,
        comment: str = "",
    ) -> GoalExecutorResult:
        """
        Authorize and activate a goal for execution.

        This is the CLI entry point: ``atlas goals activate <goal_id>``.

        Sequence:
          1. Look up goal — must be in an activatable state (RECOMMENDED,
             APPROVED, or FAILED — i.e. not already IN_PROGRESS/COMPLETED/
             REJECTED/DEFERRED).
          2. Validate authorization — must be ``user:cli``.
          3. Snapshot strategy + planning-context provenance from
             DecisionIntelligenceEngine via category→area mapping.
          4. Create and store GoalAuthorization.
          5. Transition goal → APPROVED.
          6. Optionally publish ``goal.activation.requested`` event.

        Args:
            goal_id: The ImprovementGoal ID to activate.
            comment: Optional user comment on the authorization.

        Returns:
            A GoalExecutorResult describing success/refusal.
        """
        goal = self._repository.get_goal(goal_id)
        if goal is None:
            return GoalExecutorResult(
                success=False,
                goal_id=goal_id,
                status="",
                error=f"Goal '{goal_id}' not found.",
            )

        # Validate state — only RECOMMENDED, APPROVED, or FAILED goals
        # can be (re-)activated.
        activatable = {GoalStatus.RECOMMENDED, GoalStatus.APPROVED, GoalStatus.FAILED}
        if goal.status not in activatable:
            return GoalExecutorResult(
                success=False,
                goal_id=goal_id,
                status=goal.status.name,
                error=(
                    f"Cannot activate goal '{goal_id}' in status "
                    f"'{goal.status.name}'. Must be RECOMMENDED, APPROVED, "
                    f"or FAILED."
                ),
            )

        # --- Snapshot strategy + planning-context provenance ---
        strategy_key = ""
        strategy_name = ""
        planning_context_version = ""
        if self._decision_intelligence is not None:
            area = _CATEGORY_TO_AREA.get(goal.category)
            if area:
                try:
                    strategies = self._decision_intelligence.suggest_strategies(area)
                    if strategies:
                        top = strategies[0]
                        strategy_key = top.strategy_key
                        strategy_name = top.strategy_name
                except Exception:
                    pass

                try:
                    ctx = self._decision_intelligence.get_planning_context()
                    if ctx is not None:
                        generated = getattr(ctx, "generated_at", None)
                        if hasattr(generated, "isoformat"):
                            planning_context_version = generated.isoformat()
                        elif isinstance(generated, str):
                            planning_context_version = generated
                except Exception:
                    pass

        # Create and store authorization
        authorization = GoalAuthorization(
            goal_id=goal_id,
            authorized_by="user:cli",
            comment=comment,
            strategy_key=strategy_key,
            strategy_name=strategy_name,
            planning_context_version=planning_context_version,
        )
        self._repository.store_authorization(authorization)

        # Transition goal → APPROVED (create new instance — frozen dataclass)
        goal = self._repository.get_goal(goal_id)
        if goal is not None:
            updated = ImprovementGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                description=goal.description,
                category=goal.category,
                priority=goal.priority,
                status=GoalStatus.APPROVED,
                evidence_count=goal.evidence_count,
                confidence=goal.confidence,
                proposed_at=goal.proposed_at,
            )
            self._repository.store_goal(updated)

        # Store lifecycle event
        self._store_event(
            event_type="goal_activation",
            description=f"Goal '{goal_id}' activated by user:cli. Comment: {comment}",
            related_ids=[goal_id],
        )

        # Publish optional event
        if self._event_bus is not None:
            try:
                self._event_bus.publish(
                    "goal.activation.requested",
                    {
                        "goal_id": goal_id,
                        "authorized_by": "user:cli",
                        "comment": comment,
                        "strategy_key": strategy_key,
                    },
                )
            except Exception:
                pass

        return GoalExecutorResult(
            success=True,
            goal_id=goal_id,
            status=GoalStatus.APPROVED.name,
            execution_summary={
                "action": "activated",
                "authorized_by": "user:cli",
                "strategy_key": strategy_key,
            },
        )

    # ------------------------------------------------------------------
    # settle() — tick-driven dispatch (called from Atlas.tick())
    # ------------------------------------------------------------------

    def settle(self) -> GoalExecutorResult | None:
        """
        Process one APPROVED goal per tick, if any are waiting.

        Called from ``Atlas.tick()`` immediately after
        ``EvolutionScheduler.tick()``. Single-threaded; at most one
        execution per call. Never blocks.

        The queue IS the goal status set in GoalRepository:
        ``APPROVED`` = waiting.

        Returns:
            A GoalExecutorResult if a goal was processed, or None if
            no work was pending.
        """
        approved = self._repository.get_goals_by_status(GoalStatus.APPROVED)
        if not approved:
            return None

        # Take the first approved goal (oldest first)
        goal = approved[0]
        return self._execute(goal)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(self, goal: ImprovementGoal) -> GoalExecutorResult:
        """
        Execute a single approved goal through the full loop.

        Sequence:
          1. Validate authorization exists
          2. Build ExecutionAction via ActionFactory
          3. Build gateway request via adapter
          4. gateway.execute() → GatewayExecutionResult
          5. On approval: binder resolve → ToolEngine.fulfill()
          6. Build GoalExecutionRecord + persist
          7. TrackedGoal update via OutcomeTracker
          8. Transition goal → COMPLETED | FAILED
        """
        goal_id = goal.goal_id

        # --- 1. Authorization guard ---
        auth = self._repository.get_authorization(goal_id)
        if auth is None:
            return self._refuse(goal, "No GoalAuthorization found. Activate first.")

        if auth.authorized_by != "user:cli":
            return self._refuse(
                goal,
                f"Authorization is '{auth.authorized_by}', not 'user:cli'. Refused.",
            )

        # --- 2. Build action ---
        action = ActionFactory.build(goal, auth)

        # --- 3. Build gateway request via adapter ---
        from atlas.goals.execution_request_adapter import ExecutionRequestAdapter

        gateway_request = ExecutionRequestAdapter.to_gateway_request(action, auth)

        # --- 4. Gateway ---
        if self._gateway is None:
            return self._refuse(goal, "ExecutionGateway is not available.", action)

        started_at = datetime.now()
        self._store_updated_goal(goal, GoalStatus.IN_PROGRESS, started_at)

        self._store_event(
            event_type="goal_execution_started",
            description=f"Goal '{goal_id}' dispatched to gateway.",
            related_ids=[goal_id],
        )

        gateway_result = self._gateway.execute(gateway_request)

        # Gateway refused
        if not gateway_result.success:
            return self._complete(
                goal=goal,
                action=action,
                auth=auth,
                success=False,
                outcome=ExecutionOutcome.REFUSED,
                error=gateway_result.error or "Governance refused execution.",
                started_at=started_at,
                gateway_result=gateway_result,
            )

        # --- 5. Gateway approved → resolve binder → execute ---
        binder = None
        if self._binder_registry is not None:
            binder = self._binder_registry.resolve(action.action_type)

        tool_result = None
        if binder is None:
            return self._complete(
                goal=goal,
                action=action,
                auth=auth,
                success=False,
                outcome=ExecutionOutcome.REFUSED,
                error=f"No binder registered for ActionType '{action.action_type.name}'.",
                started_at=started_at,
                gateway_result=gateway_result,
            )

        try:
            tool_result = binder.bind(action)
        except Exception as exc:
            return self._complete(
                goal=goal,
                action=action,
                auth=auth,
                success=False,
                outcome=ExecutionOutcome.FAILED,
                error=f"Binder raised: {exc}",
                started_at=started_at,
                gateway_result=gateway_result,
            )

        # --- 6. Build record & persist ---
        success = getattr(tool_result, "success", False)
        tool_name = getattr(tool_result, "tool_name", "")
        exec_time_ms = getattr(tool_result, "execution_time_ms", 0.0)
        tool_error = getattr(tool_result, "error", "")

        if success:
            outcome = ExecutionOutcome.COMPLETED
        else:
            outcome = ExecutionOutcome.FAILED

        return self._complete(
            goal=goal,
            action=action,
            auth=auth,
            success=success,
            outcome=outcome,
            error=tool_error,
            started_at=started_at,
            gateway_result=gateway_result,
            tool_name=tool_name,
            exec_time_ms=exec_time_ms,
            tool_result=tool_result,
        )

    # ------------------------------------------------------------------
    # Completion helpers
    # ------------------------------------------------------------------

    def _complete(
        self,
        goal: ImprovementGoal,
        action: ExecutionAction,
        auth: GoalAuthorization,
        success: bool,
        outcome: ExecutionOutcome,
        error: str,
        started_at: datetime,
        gateway_result: Any,
        tool_name: str = "",
        exec_time_ms: float = 0.0,
        tool_result: Any = None,
    ) -> GoalExecutorResult:
        """Finalize execution: record, TrackedGoal, status transition."""
        goal_id = goal.goal_id
        finished_at = datetime.now()

        # Determine area
        area = _CATEGORY_TO_AREA.get(goal.category, goal.category.name.lower())

        # Effectiveness proxy
        effectiveness = 1.0 if outcome == ExecutionOutcome.COMPLETED else 0.0

        # Build record
        record = GoalExecutionRecord(
            record_id=self._next_record_id(),
            goal_id=goal_id,
            category=goal.category,
            area=area,
            strategy_key=auth.strategy_key,
            strategy_name=auth.strategy_name,
            planning_context_version=auth.planning_context_version,
            action_type=action.action_type,
            action_tool=tool_name,
            success=success,
            outcome=outcome,
            effectiveness_proxy=effectiveness,
            execution_time_ms=exec_time_ms,
            confidence=goal.confidence,
            error=error,
            related_ids=self._collect_related_ids(gateway_result),
            started_at=started_at,
            finished_at=finished_at,
            metadata=self._build_record_metadata(gateway_result, tool_result),
        )
        self._repository.store_execution_record(record)

        # Transition goal status (create new frozen instance)
        new_status = GoalStatus.COMPLETED if outcome == ExecutionOutcome.COMPLETED else GoalStatus.FAILED
        self._store_updated_goal(goal, new_status, finished_at)

        # EvolutionRecord lifecycle event
        event_type = (
            "goal_execution_succeeded"
            if outcome == ExecutionOutcome.COMPLETED
            else (
                "goal_execution_refused"
                if outcome == ExecutionOutcome.REFUSED
                else "goal_execution_failed"
            )
        )
        self._store_event(
            event_type=event_type,
            description=(
                f"Goal '{goal_id}' {event_type.replace('goal_execution_', '')}. "
                f"Tool: {tool_name or 'none'}. Error: {error[:100]}"
            ),
            related_ids=[goal_id, record.record_id],
            metadata={
                "strategy_key": auth.strategy_key,
                "planning_context_version": auth.planning_context_version,
            },
        )

        # TrackedGoal via OutcomeTracker
        tracked_goal_id = ""
        if self._outcome_tracker is not None:
            from atlas.evolution.execution_engine import _TrackableProposal

            class _GoalTrackable:
                __slots__ = ("_goal",)

                def __init__(self, g: ImprovementGoal) -> None:
                    self._goal = g

                @property
                def item_id(self) -> str:
                    return self._goal.goal_id

                @property
                def problem(self) -> str:
                    return self._goal.title

            try:
                tracked = self._outcome_tracker.track_recommendation(
                    recommendation=_GoalTrackable(goal),
                    related_experience_id=record.record_id,
                )
                if tracked is not None:
                    tracked_goal_id = tracked.goal_id
            except Exception:
                pass

        # Publish event
        if self._event_bus is not None:
            try:
                self._event_bus.publish(
                    f"goal.{event_type}",
                    {
                        "goal_id": goal_id,
                        "success": success,
                        "outcome": outcome.name,
                        "record_id": record.record_id,
                        "tracked_goal_id": tracked_goal_id,
                    },
                )
            except Exception:
                pass

        return GoalExecutorResult(
            success=success and outcome != ExecutionOutcome.REFUSED,
            goal_id=goal_id,
            status=goal.status.name,
            record_id=record.record_id,
            tracked_goal_id=tracked_goal_id,
            execution_summary={
                "tool_name": tool_name,
                "outcome": outcome.name,
                "effectiveness": effectiveness,
                "execution_time_ms": exec_time_ms,
            },
            error=error,
        )

    def _refuse(
        self,
        goal: ImprovementGoal,
        error: str,
        action: ExecutionAction | None = None,
    ) -> GoalExecutorResult:
        """Refuse execution before dispatch (fail-closed)."""
        goal_id = goal.goal_id

        self._store_event(
            event_type="goal_execution_refused",
            description=f"Goal '{goal_id}' refused: {error}",
            related_ids=[goal_id],
        )

        return GoalExecutorResult(
            success=False,
            goal_id=goal_id,
            status=goal.status.name,
            error=error,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_record_id(self) -> str:
        """Generate a unique goal execution record identifier."""
        self._record_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"GER-{timestamp}-{self._record_counter:04d}"

    def _store_updated_goal(
        self,
        goal: ImprovementGoal,
        new_status: GoalStatus,
        timestamp: datetime | None = None,
    ) -> None:
        """
        Store a goal with an updated status.

        Since ImprovementGoal is a frozen dataclass, this creates a
        new instance with the desired status and stores it, replacing
        the old entry in the repository.

        Args:
            goal: The current goal instance.
            new_status: The new GoalStatus to set.
            timestamp: Optional updated_at timestamp (defaults to now).
        """
        updated = ImprovementGoal(
            goal_id=goal.goal_id,
            title=goal.title,
            description=goal.description,
            category=goal.category,
            priority=goal.priority,
            status=new_status,
            evidence_count=goal.evidence_count,
            confidence=goal.confidence,
            proposed_at=goal.proposed_at,
            updated_at=timestamp or datetime.now(),
        )
        self._repository.store_goal(updated)

    def _collect_related_ids(self, gateway_result: Any) -> list[str]:
        """Collect related IDs from a gateway result."""
        ids: list[str] = []
        if gateway_result is not None:
            rid = getattr(gateway_result, "record_id", "")
            if rid:
                ids.append(rid)
            tgid = getattr(gateway_result, "tracked_goal_id", "")
            if tgid:
                ids.append(tgid)
        return ids

    def _build_record_metadata(
        self,
        gateway_result: Any,
        tool_result: Any,
    ) -> dict[str, Any]:
        """Build metadata dict for GoalExecutionRecord."""
        meta: dict[str, Any] = {
            "binder_name": "ToolExecutionActionBinder",
        }
        if gateway_result is not None:
            gstatus = getattr(gateway_result, "status", "")
            if gstatus:
                meta["gateway_status"] = gstatus
            gerror = getattr(gateway_result, "error", "")
            if gerror:
                meta["gateway_error"] = gerror
        if tool_result is not None:
            toutput = getattr(tool_result, "output", None)
            if toutput is not None:
                import json

                try:
                    truncated = json.dumps(toutput)[:2048]
                except (TypeError, ValueError):
                    truncated = str(toutput)[:2048]
                meta["executor_output"] = truncated
        return meta

    def _store_event(
        self,
        event_type: str,
        description: str,
        related_ids: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store an EvolutionRecord lifecycle event."""
        if self._evolution_memory is None:
            return
        try:
            from atlas.evolution.models import EvolutionRecord

            record = EvolutionRecord(
                record_id=f"GOALEV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._record_counter:04d}",
                event_type=event_type,
                description=description,
                related_ids=related_ids,
                metadata=metadata or {},
            )
            self._evolution_memory.store_record(record)
        except Exception:
            pass