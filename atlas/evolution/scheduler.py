"""
Atlas Evolution Scheduler — Phase 13.3.

Background analysis cycle for evolution processing. Moves evolution
analysis out of the synchronous RuntimeCoordinator pipeline into a
rate-limited, threshold-gated tick cycle.

The scheduler:
  - Collects observations from SelfObservationEngine.
  - Only runs analysis when enough observations have accumulated.
  - Detects weaknesses, creates improvement plans, generates proposals.
  - Stores proposals and approval requests in EvolutionMemory.
  - Does NOT execute proposals (governance + approval are separate gates).

Single-threaded. No async. No concurrent cycles. No autonomous execution.

Pure logic. All dependencies injected. Fully testable.

Post-Core F5: evolution insight / decision intelligence / knowledge
pipeline integrations stay fail-soft (best-effort), but the most recent
integration error is now observable via ``EvolutionSchedulerResult.last_error``
and ``EvolutionScheduler.last_error``.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_observation import SelfObservationEngine


@dataclass(frozen=True, slots=True)
class EvolutionSchedulerResult:
    """Result of a single scheduler tick cycle.

    Attributes:
        cycle_number: Which tick cycle this result corresponds to.
        ran_analysis: Whether analysis actually ran (threshold was met).
        observation_count: Number of observations available.
        weaknesses_detected: Number of weaknesses found.
        proposals_generated: Number of proposals created.
        proposals_stored: Number of proposals stored in EvolutionMemory.
        ran_at: When the tick was executed.
        is_running: Whether a cycle was already in progress (skipped).
        last_error: Most recent fail-soft integration error message from
            this cycle ("" when no error occurred). Diagnostics only —
            does not change fail-soft semantics.
    """

    cycle_number: int
    ran_analysis: bool = False
    observation_count: int = 0
    weaknesses_detected: int = 0
    proposals_generated: int = 0
    proposals_stored: int = 0
    ran_at: datetime = field(default_factory=datetime.now)
    is_running: bool = False
    last_error: str = ""


class EvolutionScheduler:
    """
    Background analysis cycle for evolution processing.

    The scheduler is called from Atlas.tick() or RuntimeCoordinator
    post-pipeline. It runs analysis periodically (every tick_interval
    calls) and only when enough observations have accumulated.

    All evolution components are injected via constructor. Optional
    dependencies (intelligence_engine, governance_engine) default to
    None and are skipped gracefully.

    Single-threaded. No concurrent cycles. No autonomous execution.
    """

    def __init__(
        self,
        observation_engine: SelfObservationEngine,
        improvement_planner: ImprovementPlanner,
        proposal_generator: ProposalGenerator,
        approval_manager: ApprovalManager,
        evolution_memory: EvolutionMemory,
        intelligence_engine: Any = None,
        governance_engine: Any = None,
        knowledge_pipeline: Any = None,
        decision_intelligence: DecisionIntelligenceEngine | None = None,
        tick_interval: int = 10,
        min_observations: int = 5,
        research_evidence_provider: Any = None,
    ) -> None:
        """
        Initialise the evolution scheduler.

        Args:
            observation_engine: Engine that produces and stores observations.
            improvement_planner: Planner that detects weaknesses and plans.
            proposal_generator: Generator that creates EvolutionProposals.
            approval_manager: Manager that creates approval requests.
            evolution_memory: Memory that stores proposals and requests.
            intelligence_engine: Optional EvolutionIntelligenceEngine for
                insight-aware planning. Skipped if None.
            governance_engine: Optional RuleEngine for governance validation.
                Currently analysis-only; does not gate execution.
                Skipped if None.
            knowledge_pipeline: Optional EvolutionKnowledgePipeline for
                automatic consolidation of weaknesses and insights.
                Skipped if None.
            decision_intelligence: Optional DecisionIntelligenceEngine for
                adaptive planning based on consolidated evolution
                knowledge. Skipped if None.
            tick_interval: How many tick() calls between analysis runs.
                Default 10. Minimum 1.
            min_observations: Minimum new observations needed to trigger
                analysis. Default 5. Minimum 1.
            research_evidence_provider: Optional CACHE-ONLY zero-argument
                callable returning a bounded research-evidence dict (or
                None). Stage F: when present, the current evidence snapshot
                is passed into plan creation — the scheduler NEVER triggers
                acquisition itself. Absent provider = identical legacy
                behavior.
        """
        self._observation_engine = observation_engine
        self._improvement_planner = improvement_planner
        self._proposal_generator = proposal_generator
        self._approval_manager = approval_manager
        self._evolution_memory = evolution_memory
        self._intelligence_engine = intelligence_engine
        self._governance_engine = governance_engine
        self._knowledge_pipeline = knowledge_pipeline
        self._decision_intelligence = decision_intelligence
        self._research_evidence_provider = research_evidence_provider

        self._tick_interval = max(1, tick_interval)
        self._min_observations = max(1, min_observations)
        self._tick_counter = 0
        self._cycle_number = 0
        self._running = False
        self._last_result: EvolutionSchedulerResult | None = None
        self._last_error = ""

        # Track observation count at last analysis to detect new data
        self._last_observation_count = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_result(self) -> EvolutionSchedulerResult | None:
        """Return the most recent tick result, or None if never ticked."""
        return self._last_result

    @property
    def total_cycles(self) -> int:
        """Return the total number of tick cycles executed."""
        return self._cycle_number

    @property
    def tick_counter(self) -> int:
        """Return the internal tick counter for diagnostics."""
        return self._tick_counter

    @property
    def running(self) -> bool:
        """Return True if a tick cycle is currently in progress."""
        return self._running

    @property
    def last_error(self) -> str:
        """Return the most recent fail-soft integration error, or ''.

        Diagnostics only (Post-Core F5). Never changes fail-soft semantics.
        """
        return self._last_error

    # ------------------------------------------------------------------
    # Main tick cycle
    # ------------------------------------------------------------------

    def tick(self) -> EvolutionSchedulerResult | None:
        """
        Execute one tick cycle.

        Analysis runs when:
          1. tick_counter is a multiple of tick_interval, AND
          2. new observations >= min_observations since last analysis, AND
          3. no tick cycle is already running.

        Returns:
            An EvolutionSchedulerResult describing what happened this cycle,
            or None if this wasn't an analysis tick.
        """
        self._tick_counter += 1

        # Rate limit: only run every tick_interval calls
        if self._tick_counter % self._tick_interval != 0:
            return None

        # Guard against concurrent cycles
        if self._running:
            result = EvolutionSchedulerResult(
                cycle_number=self._cycle_number,
                ran_analysis=False,
                is_running=True,
            )
            self._last_result = result
            return result

        self._cycle_number += 1
        self._running = True

        try:
            result = self._run_analysis()
            self._last_result = result
            return result
        finally:
            self._running = False

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _run_analysis(self) -> EvolutionSchedulerResult:
        """Core analysis logic. Collects observations and runs the
        evolution pipeline if the threshold is met.

        Returns:
            An EvolutionSchedulerResult with the outcome.
        """
        # Reset fail-soft diagnostic for this cycle
        self._last_error = ""

        # Collect observations
        observations = self._observation_engine.recent_observations(n=100)
        current_count = len(observations)
        new_observations = current_count - self._last_observation_count

        # Check threshold
        if new_observations < self._min_observations:
            return EvolutionSchedulerResult(
                cycle_number=self._cycle_number,
                ran_analysis=False,
                observation_count=current_count,
            )

        # Phase 20 Batch 5 — Evolution Intelligence feedback closure:
        # executed proposals are already stored in EvolutionMemory (with
        # their execution EvolutionRecords) by the time the scheduler runs
        # an analysis cycle. analyze_all() turns those into EvolutionInsights
        # that feed the existing knowledge pipeline and get consumed by
        # get_insights() below. Missing engine stays fail-soft.
        if self._intelligence_engine is not None:
            try:
                self._intelligence_engine.analyze_all()
            except Exception as exc:
                self._last_error = f"intelligence_engine.analyze_all failed: {exc}"

        # Fetch evolution insights if available
        insights = None
        if self._intelligence_engine is not None:
            try:
                insights = self._intelligence_engine.get_insights()
            except Exception as exc:
                self._last_error = f"intelligence_engine.get_insights failed: {exc}"

        # Phase 14.3: Build planning context once from decision intelligence
        planning_context = None
        if self._decision_intelligence is not None:
            try:
                planning_context = self._decision_intelligence.get_planning_context()
            except Exception as exc:
                self._last_error = f"decision_intelligence failed: {exc}"

        # Detect weaknesses
        weaknesses = self._improvement_planner.detect_weaknesses(
            observations,
            insights=insights,
            planning_context=planning_context,
        )

        if not weaknesses:
            self._last_observation_count = current_count
            return EvolutionSchedulerResult(
                cycle_number=self._cycle_number,
                ran_analysis=True,
                observation_count=current_count,
                weaknesses_detected=0,
                last_error=self._last_error,
            )

        # Create improvement plan (Stage F: cache-only research evidence,
        # when a provider is wired — the scheduler never triggers acquisition)
        research_evidence = None
        if self._research_evidence_provider is not None:
            try:
                research_evidence = self._research_evidence_provider()
            except Exception:
                research_evidence = None

        if research_evidence:
            plan = self._improvement_planner.create_improvement_plan(
                weaknesses,
                insights=insights,
                planning_context=planning_context,
                research_evidence=research_evidence,
            )
        else:
            plan = self._improvement_planner.create_improvement_plan(
                weaknesses,
                insights=insights,
                planning_context=planning_context,
            )
        if plan is None:
            self._last_observation_count = current_count
            return EvolutionSchedulerResult(
                cycle_number=self._cycle_number,
                ran_analysis=True,
                observation_count=current_count,
                weaknesses_detected=len(weaknesses),
                proposals_generated=0,
                last_error=self._last_error,
            )

        # Generate proposal
        proposal = self._proposal_generator.generate_proposal(plan)

        # Create approval request
        approval_request = self._approval_manager.create_approval_request(proposal)

        # Store in evolution memory
        self._evolution_memory.store_proposal(proposal)
        self._evolution_memory.store_approval_request(approval_request)

        # Feed weaknesses into knowledge pipeline for consolidation
        if self._knowledge_pipeline is not None:
            try:
                self._knowledge_pipeline.record_weaknesses(weaknesses)
                self._knowledge_pipeline.consolidate()
            except Exception as exc:
                self._last_error = f"knowledge_pipeline failed: {exc}"

        # Update last observation count for next cycle
        self._last_observation_count = current_count

        return EvolutionSchedulerResult(
            cycle_number=self._cycle_number,
            ran_analysis=True,
            observation_count=current_count,
            weaknesses_detected=len(weaknesses),
            proposals_generated=1,
            proposals_stored=1,
            last_error=self._last_error,
        )

    def reset_threshold(self) -> None:
        """Reset the observation threshold counter.

        Call this after manually processing observations outside the
        scheduler to avoid double-processing on the next tick.
        """
        self._last_observation_count = self._observation_engine.observation_count

    def reset(self) -> None:
        """Reset all scheduler state.

        Useful for testing. Resets counters, clears the running guard,
        and resynchronises the observation threshold.
        """
        self._tick_counter = 0
        self._cycle_number = 0
        self._running = False
        self._last_result = None
        self._last_error = ""
        self._last_observation_count = 0
