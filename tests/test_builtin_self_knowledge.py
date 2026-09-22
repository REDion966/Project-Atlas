"""WS — conversational self-knowledge on the deterministic floor.

Covers two bounded repairs of the existing builtin-response surface:

* G.1 — named capability/tool detail resolves even when the request is adorned
  ("explain the capability reasoning.causal", "explain the tool sandbox_git_diff"),
  while unknown names stay fail-closed and the general inventory is unchanged.
* G.2 — a bounded architecture/self-knowledge intent answers questions about
  Atlas's own structure from the EXISTING injected ArchitectureModel, is
  deterministic/read-only/provider-free, and fails soft to the unsupported floor
  when no usable model is available.
"""

from __future__ import annotations

import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _capability_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register("reasoning.causal", lambda *_a, **_k: None)
    reg.register("memory_search", lambda *_a, **_k: None)
    return reg


def _tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="sandbox_git_diff",
            description="Run git diff read-only inside a sandbox workspace.",
            category="code",
        )
    )
    reg.register(Tool(name="echo", description="Echo", category="utility"))
    return reg


def _service(architecture_model_provider=None) -> BuiltinResponseService:
    return BuiltinResponseService(
        tool_registry=_tool_registry(),
        capability_registry=_capability_registry(),
        architecture_model_provider=architecture_model_provider,
    )


def _repo_map(tmp_path):
    root = tmp_path / "repo"
    files = {
        "atlas/__init__.py": "",
        "atlas/memory/__init__.py": "",
        "atlas/memory/service/__init__.py": "",
        "atlas/memory/service/memory_manager_service.py": "import atlas.knowledge\n",
        "atlas/knowledge/__init__.py": "",
        "atlas/knowledge/knowledge_manager.py": "import os\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return RepositoryMapBuilder(root).build()


def _model(tmp_path, with_repo_map: bool = True):
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path=(
                "atlas.memory.service.memory_manager_service.MemoryManagerService"
            ),
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            dependencies=["knowledge_manager"],
            provided_capabilities=["memory_search"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="knowledge_manager",
            package="atlas.knowledge",
            module_path="atlas.knowledge.knowledge_manager.KnowledgeManager",
            description="Knowledge base querying and management.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["knowledge_query"],
        )
    )
    capability_model = build_capability_model(
        registry, _capability_registry(), None
    )
    return build_architecture_model(
        registry,
        capability_model=capability_model,
        repository_map=_repo_map(tmp_path) if with_repo_map else None,
    )


def _intent(message):
    return (message.metadata or {}).get("builtin_intent")


# ---------------------------------------------------------------------------
# G.1 — capability / tool detail
# ---------------------------------------------------------------------------


class TestCapabilityToolDetail:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("explain reasoning.causal", "reasoning.causal"),
            ("describe reasoning.causal", "reasoning.causal"),
            ("explain the capability reasoning.causal", "reasoning.causal"),
            ("Explain the capability reasoning.causal.", "reasoning.causal"),
            ("explain sandbox_git_diff", "sandbox_git_diff"),
            ("describe sandbox_git_diff", "sandbox_git_diff"),
            ("explain the tool sandbox_git_diff", "sandbox_git_diff"),
            ("Explain the tool sandbox_git_diff.", "sandbox_git_diff"),
        ],
    )
    def test_named_detail_resolves(self, text, expected):
        msg = _service().respond(text)
        assert msg is not None
        assert _intent(msg) == "capability_detail"
        assert expected in msg.content

    def test_unknown_capability_name_is_unsupported(self):
        msg = _service().respond("explain does_not_exist")
        assert _intent(msg) == "unsupported"

    def test_unknown_tool_name_is_unsupported(self):
        msg = _service().respond("explain the tool nope_tool")
        assert _intent(msg) == "unsupported"

    @pytest.mark.parametrize(
        "text",
        [
            "what capabilities do you have?",
            "What capabilities are registered?",
            "What tools do you have?",
            "What capabilities and tools do you have?",
            "What are you capable of?",
        ],
    )
    def test_general_inventory_unchanged(self, text):
        msg = _service().respond(text)
        assert _intent(msg) == "capabilities"


class TestCapabilityDetailDoForm:
    """GAP 1 — the natural "what does <name> do?" singular detail form."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("What does reasoning.causal do?", "reasoning.causal"),
            ("what does reasoning.causal do?", "reasoning.causal"),
            ("What does the capability reasoning.causal do?", "reasoning.causal"),
            ("What does sandbox_git_diff do?", "sandbox_git_diff"),
            ("What does the sandbox_git_diff tool do?", "sandbox_git_diff"),
            ("What does the tool sandbox_git_diff do?", "sandbox_git_diff"),
        ],
    )
    def test_do_form_resolves(self, text, expected):
        msg = _service().respond(text)
        assert msg is not None
        assert _intent(msg) == "capability_detail"
        assert expected in msg.content

    # An unknown name never produces a fabricated detail. When the phrase
    # carries the bare inventory keyword ("capability"), the pre-existing
    # _CAPABILITIES_RE path claims it (the same honest behavior as the
    # existing "explain the capability <unknown>" form); the keyword-free
    # forms fall through to the unsupported floor.
    @pytest.mark.parametrize(
        "text",
        [
            "What does nonsense_xyz do?",
            "What does the tool nope_tool do?",
            "What does nope_tool do?",
        ],
    )
    def test_do_form_unknown_name_is_fail_closed(self, text):
        assert _intent(_service().respond(text)) == "unsupported"

    def test_do_form_unknown_name_with_bare_keyword_stays_inventory(self):
        message = _service().respond("What does the capability nonsense_xyz do?")
        assert _intent(message) == "capabilities"
        assert "nonsense_xyz" not in message.content

    def test_dotted_name_is_not_split_by_do_form(self):
        capabilities = CapabilityRegistry()
        capabilities.register("toolchain.execute_chain", lambda *_a, **_k: None)
        svc = BuiltinResponseService(
            tool_registry=_tool_registry(),
            capability_registry=capabilities,
        )

        msg = svc.respond("What does toolchain.execute_chain do?")

        assert _intent(msg) == "capability_detail"
        assert "toolchain.execute_chain" in msg.content


# ---------------------------------------------------------------------------
# GAP 2 — module-connection question must not be a greeting
# ---------------------------------------------------------------------------


class TestModuleConnectionQuestion:
    def test_reaches_architecture(self, tmp_path):
        svc = _service(architecture_model_provider=lambda: _model(tmp_path))
        msg = svc.respond("How are your modules connected?")
        assert _intent(msg) == "architecture"
        assert "architecture self-knowledge" in msg.content

    @pytest.mark.parametrize(
        "text",
        [
            "Hello Atlas",
            "hello",
            "hi there",
            "good morning",
            "nice to meet you",
        ],
    )
    def test_normal_greetings_still_greeting(self, text):
        assert _intent(_service().respond(text)) == "greeting"


class TestGreetingIntakeConsistency:
    """The mirrored TaskIntake greeting cue stays coherent with the floor."""

    def test_module_connection_question_is_a_question(self):
        spec = TaskIntake().intake("How are your modules connected?")
        assert spec.task_type is TaskType.QUESTION

    @pytest.mark.parametrize("text", ["Hello Atlas", "hello", "how are you"])
    def test_normal_greetings_remain_conversation(self, text):
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.CONVERSATION


# ---------------------------------------------------------------------------
# G.2 — architecture self-knowledge intent
# ---------------------------------------------------------------------------


class TestArchitectureIntentRecognition:
    @pytest.mark.parametrize(
        "text",
        [
            "What are the main systems that make up Atlas?",
            "What are Atlas's components?",
            "What are the major subsystems of Atlas?",
            "Can you explain your actual architecture?",
            "What does your architecture model know about you?",
            "What can you tell me about the dependencies between your modules?",
        ],
    )
    def test_architecture_question_resolves(self, tmp_path, text):
        svc = _service(architecture_model_provider=lambda: _model(tmp_path))
        msg = svc.respond(text)
        assert msg is not None
        assert _intent(msg) == "architecture"
        assert "architecture self-knowledge" in msg.content

    def test_provider_available_gives_bounded_answer(self, tmp_path):
        model = _model(tmp_path)
        svc = _service(architecture_model_provider=lambda: model)

        content = svc.respond("What are Atlas's components?").content

        assert f"- Components (registered): {model.component_count}" in content
        assert f"- Subsystems (packages): {model.subsystem_count}" in content
        assert "Representative subsystems:" in content
        # Bounded: a concise summary, never a raw repository dump.
        assert content.count("\n") < 60

    def test_dependency_question_uses_model_evidence(self, tmp_path):
        svc = _service(architecture_model_provider=lambda: _model(tmp_path))

        content = svc.respond(
            "What can you tell me about the dependencies of "
            "atlas.memory.service.memory_manager_service?"
        ).content

        assert (
            "Matched module: `atlas.memory.service.memory_manager_service`"
            in content
        )
        assert "Direct dependencies (1):" in content
        assert "`atlas.knowledge`" in content

    def test_answer_never_claims_absent_facts(self, tmp_path):
        # Without a repository map the model honestly reports zero modules.
        model = _model(tmp_path, with_repo_map=False)
        svc = _service(architecture_model_provider=lambda: model)

        content = svc.respond("What are Atlas's components?").content

        assert "- Repository modules: 0" in content
        assert "Repository map unavailable" in content


class TestArchitectureFailSoft:
    def test_provider_absent_falls_back_to_unsupported(self):
        svc = _service(architecture_model_provider=None)
        msg = svc.respond("What are Atlas's components?")
        assert _intent(msg) == "unsupported"

    def test_provider_none_falls_back_to_unsupported(self):
        svc = _service(architecture_model_provider=lambda: None)
        msg = svc.respond("What are Atlas's components?")
        assert _intent(msg) == "unsupported"

    def test_raising_provider_is_swallowed(self):
        def boom():
            raise RuntimeError("no model from here")

        svc = _service(architecture_model_provider=boom)
        msg = svc.respond("What are Atlas's components?")
        assert _intent(msg) == "unsupported"

    def test_non_model_return_is_ignored(self):
        svc = _service(architecture_model_provider=lambda: "not a model")
        msg = svc.respond("What are Atlas's components?")
        assert _intent(msg) == "unsupported"


class TestArchitectureReadOnly:
    def test_render_does_not_mutate_model_or_registries(self, tmp_path):
        model = _model(tmp_path)
        registry = _capability_registry()
        before_model = model.to_dict()
        before_count = registry.count

        svc = BuiltinResponseService(
            tool_registry=_tool_registry(),
            capability_registry=registry,
            architecture_model_provider=lambda: model,
        )
        msg = svc.respond("What are the main systems that make up Atlas?")

        assert _intent(msg) == "architecture"
        assert model.to_dict() == before_model
        assert registry.count == before_count

    def test_message_metadata_is_json_safe(self, tmp_path):
        svc = _service(architecture_model_provider=lambda: _model(tmp_path))
        msg = svc.respond("What are Atlas's components?")
        json.dumps(msg.metadata)


# ---------------------------------------------------------------------------
# Regression — existing deterministic intents are unchanged
# ---------------------------------------------------------------------------


class TestPreservedIntents:
    @pytest.mark.parametrize(
        ("text", "intent"),
        [
            ("Who are you?", "identity"),
            ("What exactly is Atlas?", "identity"),
            ("What can you do?", "help"),
            ("What capabilities are registered?", "capabilities"),
            ("What tools do you have?", "capabilities"),
            ("What is your status?", "status"),
            ("How are things looking?", "status"),
            ("hello", "greeting"),
        ],
    )
    def test_preserved(self, text, intent):
        svc = _service(architecture_model_provider=lambda: None)
        msg = svc.respond(text)
        assert _intent(msg) == intent


# ---------------------------------------------------------------------------
# Kernel wiring — cache-only, provider-free
# ---------------------------------------------------------------------------


class TestKernelWiring:
    def test_kernel_architecture_provider_is_cache_only(self):
        from atlas.conversation.task_intake import TaskIntake
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            svc = atlas._builtin_response
            assert svc is not None
            assert svc.architecture_model_provider is not None

            # Lazy world: no repository map built yet.
            assert atlas._repository_map is None

            prompt = "What are the main systems that make up Atlas?"
            spec = TaskIntake().intake(prompt)
            msg = svc.respond(prompt, spec=spec)

            assert msg is not None
            assert _intent(msg) == "architecture"
            # Asking a casual architecture question must not trigger a scan.
            assert atlas._repository_map is None
        finally:
            atlas.shutdown()

    def test_kernel_architecture_answer_makes_no_provider_call(
        self, monkeypatch
    ):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            def _boom(*_a, **_k):
                raise AssertionError("self-knowledge contacted a provider")

            service = atlas._ai_manager.service
            monkeypatch.setattr(service, "chat", _boom, raising=False)

            msg = atlas._builtin_response.respond("What are Atlas's components?")
            assert _intent(msg) == "architecture"
        finally:
            atlas.shutdown()
