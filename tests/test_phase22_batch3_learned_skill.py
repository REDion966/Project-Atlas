"""Phase 22 Batch 3 — Learned-skill authoring + promotion.

Covers the Batch 3 acceptance criteria over the existing Track B seams:

  - authoring builds a DRAFT LEARNED ``Skill`` candidate in memory;
  - the source chain/steps/strategy are preserved verbatim;
  - malformed/incomplete candidates are rejected deterministically;
  - authoring never executes tools, never touches ``SkillRegistry``, and
    never persists;
  - promotion is a pure intent request, routed EXCLUSIVELY through the
    existing ``ToolchainIngestBridge`` / GOV-009 boundary;
  - without a governed sink, promotion fails closed and the candidate
    remains unactivated / unregistered / unpersisted;
  - the existing learner (``ACT_LEARN_SKILL`` / ``ACT_PROMOTE``) and
    Batch 1/2 execution strategies remain intact.
"""

import ast

import pytest

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.evolution_integration import (
    IngestHandoffResult,
    ToolchainIngestBridge,
)
from atlas.toolchain.learner import (
    ACT_LEARN_SKILL,
    ACT_PROMOTE,
    ACT_RECORD,
    ToolLearner,
    ToolLearningRecommendation,
)
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainResult,
    ToolStep,
)
from atlas.toolchain.registry import SkillRegistry
from atlas.toolchain.skill_author import (
    CANDIDATE_ID_PREFIX,
    LearnedSkillCandidate,
    LearnedSkillPromoter,
    PROMOTION_REQUEST_ID_PREFIX,
    SkillPromotionRequest,
    ToolSkillAuthor,
)


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


class _FakeGovernedSink:
    """Phase-16-shaped governed sink using the existing hand-off protocol."""

    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.received: EvolutionRequest | None = None

    def enqueue_request(self, request: EvolutionRequest) -> IngestHandoffResult:
        self.received = request
        return IngestHandoffResult(
            accepted=self.accepted,
            request_id=request.request_id,
            error="" if self.accepted else "refused by pipeline",
        )


def _chain(
    steps: list[ToolStep] | None = None,
    strategy: str = "sequential",
) -> ToolChain:
    return ToolChain(
        chain_id="chain::batch3:source",
        goal="Source goal.",
        steps=tuple(
            steps
            or [
                ToolStep(step_id="step:0000", tool_name="tool_a"),
                ToolStep(step_id="step:0001", tool_name="tool_b"),
            ]
        ),
        strategy=strategy,
    )


def _learn_skill_recommendation() -> ToolLearningRecommendation:
    """Run the real learner to obtain a ``learn_skill`` recommendation."""
    tracker = ToolEffectivenessTracker()
    tracker.record("tool_a", success=True, execution_time_ms=0.0)
    tracker.record("tool_b", success=True, execution_time_ms=0.0)
    learner = ToolLearner(tracker=tracker)
    result = ToolChainResult(
        chain_id="chain:learned:source",
        success=True,
        step_results=(
            {
                "step_id": "step:0000",
                "tool_name": "tool_a",
                "success": True,
                "output": {},
                "error": "",
                "execution_time_ms": 0.0,
            },
            {
                "step_id": "step:0001",
                "tool_name": "tool_b",
                "success": True,
                "output": {},
                "error": "",
                "execution_time_ms": 0.0,
            },
        ),
        execution_time_ms=0.0,
        metadata={"strategy": "sequential"},
    )
    recommendations = learner.learn(result)
    for rec in recommendations:
        if rec.action == ACT_LEARN_SKILL:
            return rec
    raise AssertionError("learner did not emit a learn_skill recommendation")


def _module_identifiers(module) -> set[str]:
    """Collect identifiers actually referenced by a module's executable code.

    AST-based, so docstrings and comments are excluded — only real names and
    attribute accesses are inspected.
    """
    with open(module.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    return identifiers


# ---------------------------------------------------------------------------
# 1-3. Authoring: valid candidates, kind, chain/strategy preservation
# ---------------------------------------------------------------------------


class TestAuthoring:
    def test_valid_candidate_creation_from_chain(self):
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:1", name="Source Skill"
        )
        assert isinstance(candidate, LearnedSkillCandidate)
        assert candidate.candidate_id == f"{CANDIDATE_ID_PREFIX}skill:batch3:1"
        assert candidate.skill.skill_id == "skill:batch3:1"

    def test_candidate_kind_is_learned_draft(self):
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:2", name="Source Skill"
        )
        assert candidate.skill.kind is SkillKind.LEARNED
        assert candidate.skill.status is SkillStatus.DRAFT

    def test_candidate_preserves_source_chain_steps_and_strategy(self):
        source = _chain(strategy="parallel")
        candidate = ToolSkillAuthor().author_from_chain(
            source, skill_id="skill:batch3:3", name="Source Skill"
        )
        skill: Skill = candidate.skill
        assert skill.chain is not None
        assert skill.chain.chain_id == source.chain_id
        assert skill.chain.strategy == "parallel"
        assert skill.chain.steps == source.steps
        assert skill.chain.tool_names == source.tool_names
        assert candidate.source_chain_id == source.chain_id
        assert candidate.source_strategy == "parallel"

    def test_candidate_from_conditional_and_parallel_strategies(self):
        """Any valid strategy is preserved verbatim (incl. Batch 1/2)."""
        for strategy in ("conditional", "parallel", "fallback", "sequential"):
            candidate = ToolSkillAuthor().author_from_chain(
                _chain(strategy=strategy),
                skill_id=f"skill:batch3:{strategy}",
                name="Source Skill",
            )
            assert candidate.source_strategy == strategy
            chain = candidate.skill.chain
            assert chain is not None
            assert chain.strategy == strategy


# ---------------------------------------------------------------------------
# 4. Malformed candidate rejection
# ---------------------------------------------------------------------------


class TestMalformedRejection:
    def test_empty_chain_rejected(self):
        empty = ToolChain(chain_id="chain:empty", goal="g", steps=())
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_chain(
                empty, skill_id="skill:x", name="X"
            )

    def test_missing_tool_name_rejected(self):
        bad = _chain(
            steps=[
                ToolStep(step_id="step:0000", tool_name="tool_a"),
                ToolStep(step_id="step:0001", tool_name=""),
            ]
        )
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_chain(
                bad, skill_id="skill:x", name="X"
            )

    def test_duplicate_step_ids_rejected(self):
        bad = _chain(
            steps=[
                ToolStep(step_id="step:0000", tool_name="tool_a"),
                ToolStep(step_id="step:0000", tool_name="tool_b"),
            ]
        )
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_chain(
                bad, skill_id="skill:x", name="X"
            )

    def test_missing_skill_id_rejected(self):
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_chain(
                _chain(), skill_id="", name="X"
            )

    def test_missing_name_rejected(self):
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_chain(
                _chain(), skill_id="skill:x", name=""
            )

    def test_recommendation_without_skill_rejected(self):
        rec = ToolLearningRecommendation(
            recommendation_id="rec::x",
            chain_id="chain:x",
            action="record",
            reason="no skill",
        )
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_learn(rec)

    def test_recommendation_with_non_learned_skill_rejected(self):
        builtin = Skill(
            skill_id="skill:builtin",
            name="Builtin",
            kind=SkillKind.BUILTIN,
            tool_name="tool_a",
        )
        rec = ToolLearningRecommendation(
            recommendation_id="rec::builtin",
            chain_id="chain:x",
            action="learn_skill",
            reason="x",
            skill=builtin,
        )
        with pytest.raises(ValueError):
            ToolSkillAuthor().author_from_learn(rec)


# ---------------------------------------------------------------------------
# 5. Deterministic construction
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_identical_source_produces_identical_candidate(self):
        author = ToolSkillAuthor()
        c1 = author.author_from_chain(
            _chain(), skill_id="skill:batch3:det", name="Det Skill"
        )
        c2 = author.author_from_chain(
            _chain(), skill_id="skill:batch3:det", name="Det Skill"
        )
        assert c1.candidate_id == c2.candidate_id
        assert c1.skill.skill_id == c2.skill.skill_id
        assert c1.source_chain_id == c2.source_chain_id
        assert c1.source_strategy == c2.source_strategy
        chain1 = c1.skill.chain
        chain2 = c2.skill.chain
        assert chain1 is not None
        assert chain2 is not None
        assert chain1.steps == chain2.steps

    def test_identical_recommendation_produces_identical_candidate(self):
        author = ToolSkillAuthor()
        rec1 = _learn_skill_recommendation()
        rec2 = _learn_skill_recommendation()
        c1 = author.author_from_learn(rec1)
        c2 = author.author_from_learn(rec2)
        assert c1.candidate_id == c2.candidate_id
        assert c1.skill.skill_id == c2.skill.skill_id
        chain1 = c1.skill.chain
        chain2 = c2.skill.chain
        assert chain1 is not None
        assert chain2 is not None
        assert chain1.steps == chain2.steps


# ---------------------------------------------------------------------------
# 6-7. Authoring has no side effects
# ---------------------------------------------------------------------------


class TestAuthoringCleanliness:
    def test_module_has_no_executor_or_invoker_references(self):
        """Authoring never executes tools: no executor/invoker in code."""
        import atlas.toolchain.skill_author as module

        forbidden = {"ToolChainExecutor", "execute", "invoker", "invoke"}
        assert not (forbidden & _module_identifiers(module))

    def test_authoring_does_not_mutate_skill_registry(self):
        registry = SkillRegistry()
        before = registry.count
        author = ToolSkillAuthor()
        author.author_from_chain(
            _chain(), skill_id="skill:batch3:reg", name="Reg Skill"
        )
        assert registry.count == before
        assert registry.get("skill:batch3:reg") is None


# ---------------------------------------------------------------------------
# 8-9. Promotion intent + governed routing
# ---------------------------------------------------------------------------


class TestPromotionRequest:
    def test_request_promotion_builds_intent(self):
        author = ToolSkillAuthor()
        candidate = author.author_from_chain(
            _chain(), skill_id="skill:batch3:promo", name="Promo Skill"
        )
        request: SkillPromotionRequest = LearnedSkillPromoter.request_promotion(
            candidate
        )
        assert request.request_id == (
            f"{PROMOTION_REQUEST_ID_PREFIX}{candidate.candidate_id}"
        )
        assert request.candidate_id == candidate.candidate_id
        assert request.skill_id == candidate.skill.skill_id

    def test_request_promotion_rejects_non_draft(self):
        """Only DRAFT candidates are promotable intents."""
        author = ToolSkillAuthor()
        candidate = author.author_from_chain(
            _chain(), skill_id="skill:batch3:active", name="Active Skill"
        )
        active = Skill(
            skill_id=candidate.skill.skill_id,
            name=candidate.skill.name,
            description=candidate.skill.description,
            kind=candidate.skill.kind,
            category=candidate.skill.category,
            tool_name=candidate.skill.tool_name,
            chain=candidate.skill.chain,
            tags=candidate.skill.tags,
            status=SkillStatus.ACTIVE,
            created_at=candidate.skill.created_at,
            metadata=candidate.skill.metadata,
        )
        blocked = LearnedSkillCandidate(
            candidate_id=candidate.candidate_id,
            skill=active,
            source_chain_id=candidate.source_chain_id,
            source_strategy=candidate.source_strategy,
        )
        with pytest.raises(ValueError):
            LearnedSkillPromoter.request_promotion(blocked)


class TestGovernedRouting:
    def test_promotion_routes_through_toolchain_ingest_bridge(self):
        """The promoter delegates to the EXISTING ToolchainIngestBridge."""
        sink = _FakeGovernedSink()
        bridge = ToolchainIngestBridge(sink=sink)
        promoter = LearnedSkillPromoter(bridge=bridge)
        assert promoter.bridge is bridge

        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:gov", name="Gov Skill"
        )
        result = promoter.promote(candidate)
        assert result.accepted
        # The governed hand-off arrived at the sink as a Phase-16 request.
        assert sink.received is not None
        assert sink.received.change_payload["operation"] == "activate"
        assert sink.received.change_payload["skill_id"] == "skill:batch3:gov"

    def test_promotion_uses_existing_bridge_class_not_a_new_one(self):
        """No second governance layer: the bridge is the existing class."""
        bridge = ToolchainIngestBridge(sink=_FakeGovernedSink())
        promoter = LearnedSkillPromoter(bridge=bridge)
        assert type(promoter.bridge) is ToolchainIngestBridge
        assert not hasattr(promoter, "_gateway")
        assert not hasattr(promoter, "_dispatcher")


# ---------------------------------------------------------------------------
# 10-13. Fail-closed promotion, GOV-009 safety negatives
# ---------------------------------------------------------------------------


class TestFailClosedSafety:
    def test_no_sink_promotion_fails_closed(self):
        promoter = LearnedSkillPromoter()  # unwired bridge → no sink
        assert not promoter.has_sink
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:closed", name="Closed Skill"
        )
        result = promoter.promote(candidate)
        assert not result.accepted
        assert "not wired" in result.error

    def test_no_sink_candidate_remains_unactivated(self):
        promoter = LearnedSkillPromoter()
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:closed2", name="Closed Skill 2"
        )
        promoter.promote(candidate)
        assert candidate.skill.status is SkillStatus.DRAFT

    def test_no_sink_candidate_never_registered(self):
        promoter = LearnedSkillPromoter()
        registry = SkillRegistry()
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:closed3", name="Closed Skill 3"
        )
        promoter.promote(candidate)
        assert registry.get(candidate.skill.skill_id) is None
        assert registry.count == 0

    def test_refused_sink_fails_closed_and_preserves_draft(self):
        promoter = LearnedSkillPromoter(
            bridge=ToolchainIngestBridge(sink=_FakeGovernedSink(accepted=False))
        )
        candidate = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:refused", name="Refused Skill"
        )
        result = promoter.promote(candidate)
        assert not result.accepted
        assert candidate.skill.status is SkillStatus.DRAFT

    def test_module_has_no_registry_or_storage_references(self):
        """The authoring/promotion surface never mutates registry/storage.

        AST-based scan of executable identifiers only — docstrings and
        comments are excluded. Proves the module's code contains no
        registry/storage mutation surface.
        """
        import atlas.toolchain.skill_author as module

        forbidden = {
            "SkillRegistry",
            "register",
            "activate",
            "persist",
            "sqlite",
            "storage",
            "database",
            "save",
        }
        assert not (forbidden & _module_identifiers(module))


# ---------------------------------------------------------------------------
# 14-15. Learner integration + existing actions compatibility
# ---------------------------------------------------------------------------


class TestLearnerIntegration:
    def test_author_from_learn_reuses_learner_output(self):
        """Authoring consumes the existing ToolLearningRecommendation."""
        rec = _learn_skill_recommendation()
        assert rec.action == ACT_LEARN_SKILL
        assert rec.skill is not None
        assert rec.skill.kind is SkillKind.LEARNED

        candidate = ToolSkillAuthor().author_from_learn(rec)
        assert candidate.skill.kind is SkillKind.LEARNED
        assert candidate.skill.status is SkillStatus.DRAFT
        chain = candidate.skill.chain
        assert chain is not None
        assert chain.tool_names == ("tool_a", "tool_b")
        assert candidate.source_chain_id == rec.chain_id
        assert (
            candidate.skill.metadata.get("source_recommendation_id")
            == rec.recommendation_id
        )

    def test_learner_still_emits_record_promote_learn(self):
        """Existing ACT_LEARN_SKILL / ACT_PROMOTE / ACT_RECORD unchanged."""
        tracker = ToolEffectivenessTracker()
        tracker.record("tool_a", success=True, execution_time_ms=0.0)
        tracker.record("tool_b", success=True, execution_time_ms=0.0)
        learner = ToolLearner(tracker=tracker)
        recommendations = learner.learn(
            ToolChainResult(
                chain_id="chain:compat",
                success=True,
                step_results=(
                    {"step_id": "step:0000", "tool_name": "tool_a", "success": True},
                    {"step_id": "step:0001", "tool_name": "tool_b", "success": True},
                ),
                execution_time_ms=0.0,
            )
        )
        actions = [r.action for r in recommendations]
        assert ACT_RECORD in actions
        assert ACT_PROMOTE in actions
        assert ACT_LEARN_SKILL in actions


# ---------------------------------------------------------------------------
# 16-17. Batch 1 + Batch 2 execution regressions
# ---------------------------------------------------------------------------


class TestBatchRegression:
    def test_batch1_conditional_still_green(self):
        """Conditional strategy behavior is untouched by Batch 3."""
        from atlas.toolchain.executor import ToolChainExecutor

        results = {}

        class Invoker:
            def execute_by_name(self, name, params=None):
                results[name] = True
                return {
                    "success": True,
                    "output": {"status": "ok"} if name == "tool_a" else {},
                    "error": "",
                }

        chain = ToolChain(
            chain_id="cond",
            goal="g",
            steps=(
                ToolStep(step_id="step:0000", tool_name="tool_a"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="tool_b",
                    parameters={"when": {"key": "status", "equals": "ok"}},
                ),
            ),
            strategy="conditional",
        )
        outcome = ToolChainExecutor(Invoker()).execute(chain)
        assert outcome.success
        assert "tool_b" in results

    def test_batch2_parallel_still_green(self):
        """Parallel strategy behavior is untouched by Batch 3."""
        from atlas.toolchain.executor import ToolChainExecutor

        calls = []

        class Invoker:
            def execute_by_name(self, name, params=None):
                calls.append(name)
                return {"success": True, "output": {}, "error": ""}

        chain = ToolChain(
            chain_id="par",
            goal="g",
            steps=(
                ToolStep(step_id="step:0000", tool_name="tool_a"),
                ToolStep(step_id="step:0001", tool_name="tool_b"),
            ),
            strategy="parallel",
        )
        outcome = ToolChainExecutor(Invoker()).execute(chain)
        assert outcome.success
        assert calls == ["tool_a", "tool_b"]
        assert outcome.metadata["strategy"] == "parallel"

    def test_risk_policy_still_authoritative(self):
        """RiskPolicy is untouched: denied tool still fails closed."""
        from atlas.toolchain.executor import RiskPolicy, ToolChainExecutor

        calls = []

        class Invoker:
            def execute_by_name(self, name, params=None):
                calls.append(name)
                return {"success": True, "output": {}, "error": ""}

        chain = ToolChain(
            chain_id="risk",
            goal="g",
            steps=(ToolStep(step_id="step:0000", tool_name="tool_a"),),
            strategy="sequential",
        )
        policy = RiskPolicy(deny_list=frozenset({"tool_a"}))
        outcome = ToolChainExecutor(Invoker(), policy).execute(chain)
        assert not outcome.success
        assert outcome.step_results[0].get("denied") is True
        assert calls == []


# ---------------------------------------------------------------------------
# 18. Surface sanity / regression surface
# ---------------------------------------------------------------------------


class TestSurfaceRegression:
    def test_new_surface_importable_and_exported(self):
        """The new authoring surface is reachable via the package export."""
        import atlas.toolchain as tc

        assert tc.ToolSkillAuthor is ToolSkillAuthor
        assert tc.LearnedSkillPromoter is LearnedSkillPromoter
        assert tc.LearnedSkillCandidate is LearnedSkillCandidate
        assert tc.SkillPromotionRequest is SkillPromotionRequest

    def test_registry_still_works_for_explicit_registration(self):
        """Explicit SkillRegistry registration is unchanged by Batch 3."""
        registry = SkillRegistry()
        skill = ToolSkillAuthor().author_from_chain(
            _chain(), skill_id="skill:batch3:reg2", name="Reg2"
        ).skill
        registry.register(skill)
        registered = registry.get("skill:batch3:reg2")
        assert registered is not None
        assert registered is skill
        assert registered.status is SkillStatus.DRAFT
