"""G2 — Deep Self-Knowledge + Open-Ended Knowledge (target-state gate).

Evidence-driven acceptance tests for the G2 milestone:

* DEEP SELF-KNOWLEDGE — dependency/dependent/impact answers for an explicit
  named module come from the EXISTING ``ArchitectureModel``/``RepositoryMap``,
  and the bounded relationship provider is consulted ONLY for an explicit
  named target (a casual architecture question can never trigger a build).
* WORDING GAPS — the evidenced natural-language gaps route to the correct
  EXISTING surface: "how does the knowledge decision work?" and "how would you
  add a new capability?" are Atlas self-knowledge, while "I want to know about
  X" is an information request (not a capability gap).
* OPEN-ENDED KNOWLEDGE — an unmatched knowledge question is answered with the
  EXISTING D3 decision's own sufficiency + governed-acquisition status, plus
  the boundary: nothing is acquired, inferred, or invented.

Invariants asserted throughout: deterministic, model-free (``model_used`` is
False), deny-by-default acquisition, no new store/registry/model, no authority
granted, and no duplicate architecture.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_ARCHITECTURE,
    BUILTIN_INTENT_SELF_KNOWLEDGE,
    BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
    BuiltinResponseService,
    _FRAME_CONCEPT_TOPICS,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.research.knowledge_decision import KnowledgeAnswer, KnowledgeSufficiency
from atlas.self_knowledge.architecture_model import build_architecture_model


# ---------------------------------------------------------------------------
# Deterministic doubles (no repository scan, no network, no model)
# ---------------------------------------------------------------------------


class _FakeModuleInfo:
    def __init__(self, module: str, *, is_package: bool = False) -> None:
        self.module = module
        self.is_package = is_package
        self.path = module.replace(".", "/") + ".py"
        self.internal_imports = ("atlas.demo.dep",)


class _FakeRepositoryMap:
    """Minimal RepositoryMap-shaped double: the fields ``locate()`` consumes."""

    def __init__(self) -> None:
        self.modules = (_FakeModuleInfo("atlas.demo.target"),)
        self.module_count = 1
        self.edge_count = 2

    def dependencies_of(self, module: str) -> tuple[str, ...]:
        return ("atlas.demo.dep",)

    def dependents_of(self, module: str) -> tuple[str, ...]:
        return ("atlas.demo.user",)

    def impact_set(self, module: str) -> tuple[str, ...]:
        return ("atlas.demo.user", "atlas.demo.transitive")


class _EmptyKnowledgeResult:
    """Validated-knowledge result shape: nothing matched."""

    status = "empty"
    items: tuple[Any, ...] = ()
    message = "No validated (SUPPORTED) knowledge matched the query."


class _MatchedKnowledgeClaim:
    statement = "A supported claim."
    validation_status = "SUPPORTED"
    claim_confidence = 0.9
    verification_score = 0.8
    citations: tuple[Any, ...] = ()


class _MatchedKnowledgeResult:
    status = "ok"
    items = (_MatchedKnowledgeClaim(),)
    message = ""


def _cache_only_model() -> Any:
    """Model built with NO repository map (the cache-only production snapshot)."""
    return build_architecture_model(
        component_registry=None, capability_model=None, repository_map=None
    )


def _rich_model() -> Any:
    """Model built from a repository map (the bounded relationship snapshot)."""
    return build_architecture_model(
        component_registry=None,
        capability_model=None,
        repository_map=_FakeRepositoryMap(),
    )


def _service(**kwargs: Any) -> BuiltinResponseService:
    return BuiltinResponseService(started=True, service_names=(), **kwargs)


def _intent(message: Any) -> str:
    return str((message.metadata or {}).get("builtin_intent") or "")


# ---------------------------------------------------------------------------
# A. Wording gaps — the four evidenced phrasings
# ---------------------------------------------------------------------------


class TestWordingGaps:
    def test_knowledge_decision_mechanism_is_self_knowledge(self):
        frame = sf.interpret("How does the knowledge decision work?")
        assert frame.domain is sf.SemanticDomain.SELF_KNOWLEDGE
        assert frame.concept in ("component", "knowledge_sufficiency")

    def test_knowledge_decision_mechanism_is_answered_from_verified_anchor(self):
        svc = _service(architecture_model_provider=_cache_only_model)
        message = svc.respond("How does the knowledge decision work?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        # The responsibility is answered from the EXISTING component, verified
        # present — never invented.
        assert "KnowledgeDecisionService" in message.content
        assert "atlas/research/knowledge_decision.py" in message.content

    def test_location_question_keeps_the_architecture_route(self):
        frame = sf.interpret("Which part of Atlas decides knowledge sufficiency?")
        assert frame.domain is sf.SemanticDomain.SELF_KNOWLEDGE
        assert frame.concept == "component"

    def test_interest_phrasing_is_an_information_request(self):
        for text in (
            "I want to know about the Europa Clipper mission.",
            "I want to learn about Europa.",
            "I'd like to know more about the Europa Clipper mission.",
        ):
            frame = sf.interpret(text)
            assert frame.domain is sf.SemanticDomain.KNOWLEDGE, text
            assert sf.SemanticDomain.DEVELOPMENT is not frame.domain, text

    def test_interest_phrasing_subject_is_preserved(self):
        frame = sf.interpret("I want to know about the Europa Clipper mission.")
        assert "europa" in frame.subject.lower()

    def test_imperative_capability_request_stays_development(self):
        for text in (
            "Add a new capability that summarizes documents.",
            "Atlas needs a capability that reads PDFs.",
        ):
            assert sf.interpret(text).domain is sf.SemanticDomain.DEVELOPMENT, text

    def test_explanatory_add_capability_is_self_knowledge_not_development(self):
        spec = TaskIntake().intake("How would you add a new capability?")
        svc = _service(architecture_model_provider=_cache_only_model)
        message = svc.respond("How would you add a new capability?", spec=spec)
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_SELF_KNOWLEDGE
        assert "extension points" in message.content.lower()
        # The development path never answers an explanatory question.
        assert "Development preparation FAILED" not in message.content
        assert (message.metadata or {}).get("model_used") is False

    def test_unrouted_self_concept_still_fails_closed(self):
        """A concept with no existing topic stays unrouted (pinned elsewhere)."""
        frame = sf.interpret("how does your memory system work?")
        assert frame.concept == "operation"
        assert _FRAME_CONCEPT_TOPICS.get("operation") is None


# ---------------------------------------------------------------------------
# B. Deep self-knowledge — relationships, bounded and cached
# ---------------------------------------------------------------------------


class TestRelationshipSelfKnowledge:
    def _calls(self) -> list[int]:
        return []

    def test_explicit_target_uses_bounded_relationship_provider(self):
        calls = self._calls()
        svc = _service(
            architecture_model_provider=_cache_only_model,
            architecture_relationship_provider=lambda: (calls.append(1), _rich_model())[1],
        )
        message = svc.respond("What are the dependencies of atlas.demo.target?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert calls == [1]
        # The facts come from the EXISTING model's locate(), not a new index.
        assert "Direct dependencies (1)" in message.content
        assert "atlas.demo.dep" in message.content
        assert "Direct dependents (1)" in message.content
        assert "atlas.demo.user" in message.content
        assert "Transitive impact (2)" in message.content
        assert (message.metadata or {}).get("model_used") is False

    def test_casual_architecture_question_never_consults_the_provider(self):
        calls = self._calls()
        svc = _service(
            architecture_model_provider=_cache_only_model,
            architecture_relationship_provider=lambda: (calls.append(1), _rich_model())[1],
        )
        message = svc.respond("What are the main systems that make up Atlas?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert calls == []

    def test_provider_not_consulted_without_an_explicit_target(self):
        calls = self._calls()
        svc = _service(
            architecture_model_provider=_cache_only_model,
            architecture_relationship_provider=lambda: (calls.append(1), _rich_model())[1],
        )
        svc.respond("How does the conversation subsystem fit together?")
        assert calls == []

    def test_provider_not_consulted_when_the_model_already_has_module_facts(self):
        calls = self._calls()
        svc = _service(
            architecture_model_provider=_rich_model,
            architecture_relationship_provider=lambda: (calls.append(1), _rich_model())[1],
        )
        message = svc.respond("What are the dependencies of atlas.demo.target?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert calls == []
        assert "atlas.demo.dep" in message.content

    def test_provider_is_fail_soft(self):
        def _raising() -> Any:
            raise RuntimeError("no map available")

        svc = _service(
            architecture_model_provider=_cache_only_model,
            architecture_relationship_provider=_raising,
        )
        message = svc.respond("What are the dependencies of atlas.demo.target?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert "Repository modules: 0" in message.content

    def test_absent_provider_keeps_the_existing_answer(self):
        svc = _service(architecture_model_provider=_cache_only_model)
        message = svc.respond("What are the dependencies of atlas.demo.target?")
        assert message is not None
        assert "Repository modules: 0" in message.content


# ---------------------------------------------------------------------------
# C. Open-ended knowledge — honest, governed, structured
# ---------------------------------------------------------------------------


class TestGovernedKnowledgeAnswer:
    def _status_provider(self) -> Any:
        def _decide(_query: str) -> KnowledgeAnswer:
            return KnowledgeAnswer(
                status=KnowledgeSufficiency.UNKNOWN,
                objective="tell me about the subject",
                query="the subject",
                acquisition_status="no_authorized_source",
                message="No authorized external source is available (deny-by-default).",
            )

        return _decide

    def test_unmatched_knowledge_reports_sufficiency_and_boundary(self):
        svc = _service(
            validated_knowledge_provider=lambda _q: _EmptyKnowledgeResult(),
            knowledge_status_provider=self._status_provider(),
        )
        message = svc.respond("What did you find about quantum flux capacitors?")
        assert message is not None
        assert _intent(message) == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        content = message.content
        # The existing (C6.1) reporting is preserved verbatim.
        assert "No validated knowledge matched" in content
        assert "nothing is acquired, inferred, or invented" in content
        # G2 — the EXISTING D3 decision is reported as-is.
        assert "- Knowledge decision (D3): sufficiency unknown." in content
        assert "- Governed acquisition: no_authorized_source." in content
        assert "deny-by-default" in content
        assert "- Required to answer: validated claims from an authorized source" in content
        assert (message.metadata or {}).get("model_used") is False

    def test_absent_status_provider_keeps_the_existing_answer(self):
        svc = _service(validated_knowledge_provider=lambda _q: _EmptyKnowledgeResult())
        message = svc.respond("What did you find about quantum flux capacitors?")
        assert message is not None
        assert "No validated knowledge matched" in message.content
        assert "- Knowledge decision (D3):" not in message.content

    def test_status_provider_failure_is_fail_soft(self):
        def _raising(_query: str) -> Any:
            raise RuntimeError("decision unavailable")

        svc = _service(
            validated_knowledge_provider=lambda _q: _EmptyKnowledgeResult(),
            knowledge_status_provider=_raising,
        )
        message = svc.respond("What did you find about quantum flux capacitors?")
        assert message is not None
        assert "No validated knowledge matched" in message.content
        assert "- Knowledge decision (D3):" not in message.content

    def test_matched_knowledge_needs_no_sufficiency_block(self):
        calls: list[str] = []

        def _decide(query: str) -> KnowledgeAnswer:
            calls.append(query)
            return KnowledgeAnswer(
                status=KnowledgeSufficiency.SUFFICIENT, objective=query
            )

        svc = _service(
            validated_knowledge_provider=lambda _q: _MatchedKnowledgeResult(),
            knowledge_status_provider=_decide,
        )
        message = svc.respond("What did you find about quantum flux capacitors?")
        assert message is not None
        assert "validated (SUPPORTED) claim(s) matched" in message.content
        assert calls == []

    def test_knowledge_answer_grants_no_authority(self):
        svc = _service(
            validated_knowledge_provider=lambda _q: _EmptyKnowledgeResult(),
            knowledge_status_provider=self._status_provider(),
        )
        message = svc.respond("What did you find about quantum flux capacitors?")
        metadata = dict(message.metadata or {})
        assert "approval" not in metadata
        assert "development" not in metadata
        assert "execution" not in metadata
        assert "orchestration" not in metadata


# ---------------------------------------------------------------------------
# D. Kernel wiring — one bounded builder, one decision service, no new system
# ---------------------------------------------------------------------------


class TestKernelWiring:
    def test_kernel_wires_the_g2_providers_without_a_scan(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            svc = atlas._builtin_response
            assert svc is not None
            assert svc.architecture_relationship_provider is not None
            assert svc.knowledge_status_provider is not None
            # Wiring alone builds nothing: the map is built on FIRST explicit
            # named-target relationship question, never at construction.
            assert atlas._repository_map is None
            # The relationship provider is the EXISTING architecture model
            # builder (no duplicate self-knowledge system).
            assert svc.architecture_relationship_provider == atlas.architecture_model
        finally:
            atlas.shutdown()

    def test_kernel_knowledge_status_is_fail_soft(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            decision = atlas._knowledge_status("")
            # Either a real decision or a clean decline — never an exception.
            assert decision is None or isinstance(decision, KnowledgeAnswer)
            assert atlas._repository_map is None
        finally:
            atlas.shutdown()
