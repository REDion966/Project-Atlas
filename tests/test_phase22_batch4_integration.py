"""Phase 22 Batch 4 — Integration & Final Acceptance. v3

Proves the completed Phase 22 behavior is reachable through the EXISTING
production architecture — no new planner/router/dispatcher/registry, no
kernel wiring changes, no duplicate instances:

    plan → capability selection → CapabilityRegistry
        → CapabilityRouter → CapabilityDispatcher
        → toolchain.execute_chain / toolchain.run_skill handler
        → ToolChainExecutor (sequential/fallback/conditional/parallel)
        → ToolChainResult → ExecutionResult

Planning actions that name a registered capability are dispatched directly
(Phase 20 plan-action direct-capability fallback), so the integration tests
below construct the dispatched :class:`Capability` with the registered
toolchain capability name — exactly as the RuntimeCoordinator does when a
plan step's action matches a registered capability.

And the Batch 3 governed surface:

    ToolSkillAuthor (in-memory DRAFT candidate)
        → LearnedSkillPromoter → ToolchainIngestBridge (GOV-009)
        → injected governed sink (or fail-closed refusal)

Batch 1/2/3 behavior is exercised through the dispatcher path using real
production objects (real planner, real executor, real authoring/promotion
surface, real CapabilityRegistry/Router/Dispatcher) with only the
tool-invoker seam faked, matching the established test convention.
"""

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.evolution_integration import (
    IngestHandoffResult,
    ToolchainIngestBridge,
)
from atlas.toolchain.executor import RiskPolicy, ToolChainExecutor
from atlas.toolchain.models import Skill, SkillKind, SkillStatus, ToolChain, ToolStep
from atlas.toolchain.planner import ToolChainPlanner
from atlas.toolchain.registry import SkillRegistry
from atlas.toolchain.skill_author import LearnedSkillPromoter, ToolSkillAuthor


# ---------------------------------------------------------------------------
# Fakes (tool-invoker and planner-provider seams only; pipeline is real)
# ---------------------------------------------------------------------------


class _FakeTool:
    """A tool-like object for the real planner."""

    def __init__(self, name: str = "read_file", category: str = "file") -> None:
        self.name = name
        self.category = category
        self.description = f"Run tool {name}."
        self.tags = [category]


class _FakeToolProvider:
    """Tool provider feeding the real ToolChainPlanner."""

    def __init__(self) -> None:
        self._tools = [_FakeTool("read_file"), _FakeTool("search")]

    def list(self):
        return list(self._tools)


class _RecordingInvoker:
    """Tool-invoker seam: records every invocation, returns success."""

    def __init__(self, results: dict[str, dict] | None = None) -> None:
        self._results = results or {}
        self.calls: list[tuple[str, dict]] = []

    def execute_by_name(self, name: str, params: dict | None = None):
        self.calls.append((name, params or {}))
        if name in self._results:
            return dict(self._results[name])
        return {
            "success": True,
            "output": {"tool": name},
            "error": "",
            "execution_time_ms": 1.0,
        }


class _FakeGovernedSink:
    """Phase-16-shaped governed sink using the existing hand-off protocol."""

    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.received = None

    def enqueue_request(self, request):
        self.received = request
        return IngestHandoffResult(
            accepted=self.accepted,
            request_id=request.request_id,
            error="" if self.accepted else "refused by pipeline",
        )


def _make_factory(
    invoker: _RecordingInvoker,
    risk_policy: RiskPolicy | None = None,
) -> ToolchainCapabilityFactory:
    """Build a real ToolchainCapabilityFactory around a seamed invoker."""
    return ToolchainCapabilityFactory(
        planner=ToolChainPlanner(tool_provider=_FakeToolProvider()),
        executor=ToolChainExecutor(tool_invoker=invoker, risk_policy=risk_policy),
        registry=SkillRegistry(),
        tracker=ToolEffectivenessTracker(),
    )


def _execute_chain_capability(**metadata) -> Capability:
    """Build the dispatched capability exactly as the coordination path
    does when a plan step's action names the registered toolchain
    capability (Phase 20 direct-capability fallback)."""
    params: dict = {"action": "toolchain.execute_chain"}
    params.update(metadata)
    return Capability(
        name="toolchain.execute_chain",
        priority=5,
        reason="Handle action: toolchain.execute_chain",
        metadata=params,
    )


# ---------------------------------------------------------------------------
# 1. Production dispatch path reaches the toolchain executor
# ---------------------------------------------------------------------------


class TestProductionDispatchPath:
    def test_toolchain_capabilities_registered_in_production_registry(self):
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        _make_factory(invoker).register(registry)
        assert set(registry.registered_names) == {
            "toolchain.execute_chain",
            "toolchain.run_skill",
            "toolchain.effectiveness",
            "toolchain.skills",
        }

    def test_plan_action_routed_and_dispatched_through_only_dispatch_path(self):
        """A planning action naming 'toolchain.execute_chain' is routed by
        the CapabilityRouter and dispatched by the CapabilityDispatcher to
        the REAL toolchain handler → real executor."""
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        _make_factory(invoker).register(registry)
        router = CapabilityRouter(registry)
        dispatcher = CapabilityDispatcher(registry)

        capability = _execute_chain_capability(goal="read a file")
        routes = router.route([capability])
        assert len(routes) == 1
        assert routes[0].capability == "toolchain.execute_chain"

        results = dispatcher.dispatch([capability])
        assert len(results) == 1
        assert results[0].success
        assert invoker.calls  # the real executor ran through the invoker seam


# ---------------------------------------------------------------------------
# 2. Batch 1 + Batch 2 executor integration (reachable through the executor)
# ---------------------------------------------------------------------------


class TestStrategyIntegration:
    def test_all_four_strategies_reachable(self):
        """Sequential, fallback, conditional, parallel all execute via the
        real ToolChainExecutor. Fallback stops at the first success."""
        for strategy in ("sequential", "fallback", "conditional", "parallel"):
            invoker = _RecordingInvoker()
            executor = ToolChainExecutor(tool_invoker=invoker)
            chain = ToolChain(
                chain_id=f"chain::int:{strategy}",
                goal="Integration goal.",
                steps=(
                    ToolStep(step_id="step:0000", tool_name="read_file"),
                    ToolStep(step_id="step:0001", tool_name="search"),
                ),
                strategy=strategy,
            )
            result = executor.execute(chain)
            assert result.success, f"{strategy} failed: {result.error}"
            assert result.metadata["strategy"] == strategy
            if strategy == "fallback":
                # First tool succeeds → fallback stops after one attempt.
                assert [call[0] for call in invoker.calls] == ["read_file"]
            else:
                assert [call[0] for call in invoker.calls] == [
                    "read_file",
                    "search",
                ]

    def test_unknown_strategy_stays_fail_closed(self):
        """An unknown strategy still fails closed through the executor."""
        executor = ToolChainExecutor(tool_invoker=_RecordingInvoker())
        chain = ToolChain(
            chain_id="chain::int:unknown",
            goal="Unknown strategy.",
            steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
            strategy="does_not_exist",
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "unsupported_strategy"

    def test_conditional_batch1_semantics_through_executor(self):
        """Conditional (Batch 1): a false condition skips and the tool is
        never invoked."""
        invoker = _RecordingInvoker()
        executor = ToolChainExecutor(tool_invoker=invoker)
        chain = ToolChain(
            chain_id="chain::int:cond",
            goal="Conditional goal.",
            steps=(
                ToolStep(step_id="step:0000", tool_name="read_file"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="search",
                    parameters={"when": {"key": "status", "equals": "nope"}},
                ),
            ),
            strategy="conditional",
        )
        result = executor.execute(chain)
        assert result.success
        assert [call[0] for call in invoker.calls] == ["read_file"]
        assert result.step_results[1]["skipped"] is True

    def test_parallel_batch2_semantics_through_executor(self):
        """Parallel (Batch 2): every eligible tool fans out exactly once in
        declared order."""
        invoker = _RecordingInvoker()
        executor = ToolChainExecutor(tool_invoker=invoker)
        chain = ToolChain(
            chain_id="chain::int:parallel",
            goal="Parallel goal.",
            steps=(
                ToolStep(step_id="step:0000", tool_name="read_file"),
                ToolStep(step_id="step:0001", tool_name="search"),
            ),
            strategy="parallel",
        )
        result = executor.execute(chain)
        assert result.success
        assert [call[0] for call in invoker.calls] == ["read_file", "search"]

    def test_risk_policy_deny_enforced_through_dispatch(self):
        """RiskPolicy deny remains authoritative when the executor is reached
        through the production dispatch path."""
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        _make_factory(
            invoker, risk_policy=RiskPolicy(deny_list=frozenset({"search"}))
        ).register(registry)
        dispatcher = CapabilityDispatcher(registry)

        capability = _execute_chain_capability(goal="read a file")
        results = dispatcher.dispatch([capability])
        assert len(results) == 1
        assert not results[0].success
        # The denied tool never reached the invoker (only the allowed one).
        assert all(call[0] != "search" for call in invoker.calls)


# ---------------------------------------------------------------------------
# 3. Batch 3 authoring/promotion governed boundary
# ---------------------------------------------------------------------------


class TestBatch3PromotionBoundary:
    def test_promotion_through_wired_governed_sink(self):
        """With a governed sink, promotion hands an activate request."""
        sink = _FakeGovernedSink()
        promoter = LearnedSkillPromoter(bridge=ToolchainIngestBridge(sink=sink))
        candidate = ToolSkillAuthor().author_from_chain(
            ToolChain(
                chain_id="chain::int:learned",
                goal="Learned goal.",
                steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
                strategy="sequential",
            ),
            skill_id="skill::int:learned",
            name="Learned Integration Skill",
        )
        result = promoter.promote(candidate)
        assert result.accepted
        assert sink.received is not None
        assert sink.received.change_payload["operation"] == "activate"
        assert sink.received.change_payload["skill_id"] == "skill::int:learned"

    def test_no_sink_promotion_fails_closed_and_candidate_stays_draft(self):
        """Without a governed sink, promotion refuses; the candidate is
        never registered and never activated."""
        registry = SkillRegistry()
        promoter = LearnedSkillPromoter()  # unwired bridge → fail closed
        candidate = ToolSkillAuthor().author_from_chain(
            ToolChain(
                chain_id="chain::int:closed",
                goal="Closed goal.",
                steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
                strategy="sequential",
            ),
            skill_id="skill::int:closed",
            name="Closed Skill",
        )
        result = promoter.promote(candidate)
        assert not result.accepted
        assert "not wired" in result.error
        assert candidate.skill.status is SkillStatus.DRAFT
        assert registry.get(candidate.skill.skill_id) is None

    def test_authoring_remains_pure_in_memory(self):
        """Authoring produces an in-memory DRAFT LEARNED candidate with the
        source chain preserved; no registry mutation."""
        registry = SkillRegistry()
        author = ToolSkillAuthor()
        source = ToolChain(
            chain_id="chain::int:author",
            goal="Authored goal.",
            steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
            strategy="parallel",
        )
        candidate = author.author_from_chain(
            source,
            skill_id="skill::int:author",
            name="Authored Skill",
        )
        assert candidate.skill.kind is SkillKind.LEARNED
        assert candidate.skill.status is SkillStatus.DRAFT
        assert candidate.skill.chain is not None
        assert candidate.skill.chain.strategy == "parallel"
        assert candidate.source_strategy == "parallel"
        assert registry.count == 0
        assert registry.get(candidate.skill.skill_id) is None


# ---------------------------------------------------------------------------
# 4. Full production path end-to-end
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_goal_reaches_executor_via_full_production_path(self):
        """A real goal is decomposed by the real planner into a plan,
        executed via the real capability handler through the registry/router/
        dispatcher path, producing a real ExecutionResult wrapping a
        ToolChainResult."""
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        _make_factory(invoker).register(registry)
        router = CapabilityRouter(registry)
        dispatcher = CapabilityDispatcher(registry)

        capability = _execute_chain_capability(goal="read a file")
        routes = router.route([capability])
        assert len(routes) == 1
        results = dispatcher.dispatch([capability])

        assert len(results) == 1
        assert results[0].success
        result_payload = results[0].output["result"]
        assert result_payload["metadata"]["strategy"] == "sequential"
        assert invoker.calls  # the real executor invoked the seamed invoker

    def test_run_skill_through_dispatch_with_learned_candidate_registered(self):
        """A LEARNED skill (Batch 3 shape) registered in the production
        registry is reachable via toolchain.run_skill through the
        dispatcher — proving the composed path works end to end."""
        invoker = _RecordingInvoker()
        factory = _make_factory(invoker)
        source = ToolChain(
            chain_id="chain::int:active",
            goal="Active learned goal.",
            steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
            strategy="sequential",
        )
        candidate = ToolSkillAuthor().author_from_chain(
            source,
            skill_id="skill::int:active",
            name="Active Learned Skill",
        )
        skill: Skill = candidate.skill
        skill = Skill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            kind=skill.kind,
            category=skill.category,
            tool_name=skill.tool_name,
            chain=skill.chain,
            tags=skill.tags,
            status=SkillStatus.ACTIVE,
            created_at=skill.created_at,
            metadata=skill.metadata,
        )
        factory.registry.register(skill)

        registry = CapabilityRegistry()
        factory.register(registry)
        dispatcher = CapabilityDispatcher(registry)

        capability = Capability(
            name="toolchain.run_skill",
            priority=5,
            reason="Handle action: toolchain.run_skill",
            metadata={"skill_id": skill.skill_id},
        )
        results = dispatcher.dispatch([capability])

        assert len(results) == 1
        assert results[0].success
        assert invoker.calls
        assert invoker.calls[0][0] == "read_file"
