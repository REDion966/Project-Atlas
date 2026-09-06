"""
Tests for default capability handlers.

These tests verify that the default runtime handlers:
- Return valid ExecutionResult objects.
- Report success=True.
- Include the correct capability name.
- Handle empty parameters safely.
- Are exposed via DEFAULT_HANDLERS.
- Do not depend on infrastructure services.
"""

import ast
import inspect
from pathlib import Path

import pytest

from atlas.reasoning.execution.handlers import (
    DEFAULT_HANDLERS,
    analysis_handler,
    conversation_handler,
    task_execution_handler,
    noop_handler,
)
from atlas.reasoning.execution.models import ExecutionResult


HANDLERS = {
    "conversation": conversation_handler,
    "analysis": analysis_handler,
    "task_execution": task_execution_handler,
}


NOOP_HANDLER = {"noop": noop_handler}


@pytest.mark.parametrize("name,handler", HANDLERS.items())
def test_handler_returns_execution_result(name, handler):
    """Every handler must return an ExecutionResult instance."""
    result = handler({})
    assert isinstance(result, ExecutionResult)


@pytest.mark.parametrize("name,handler", HANDLERS.items())
def test_handler_reports_success(name, handler):
    """Every handler must report success=True."""
    result = handler({})
    assert result.success is True


@pytest.mark.parametrize("name,handler", HANDLERS.items())
def test_handler_has_correct_capability_name(name, handler):
    """The result capability name must match the expected handler mapping."""
    result = handler({})
    assert result.capability == name


def test_noop_handler_returns_empty_capability():
    """The noop handler returns an empty capability name by design."""
    result = noop_handler({})
    assert result.capability == ""


@pytest.mark.parametrize("name,handler", HANDLERS.items())
def test_handler_handles_empty_params(name, handler):
    """Handlers must safely accept empty parameter dictionaries."""
    result = handler({})
    assert isinstance(result, ExecutionResult)
    assert result.success is True


@pytest.mark.parametrize("name,handler", HANDLERS.items())
def test_handler_accepts_arbitrary_params(name, handler):
    """Handlers should safely accept non-empty parameter dictionaries."""
    result = handler({"query": "hello", "context": "test"})
    assert isinstance(result, ExecutionResult)
    assert result.success is True


def test_default_handlers_contains_expected_entries():
    """DEFAULT_HANDLERS must include the expected capability entries."""
    expected = {"conversation", "analysis", "task_execution", "noop"}
    assert set(DEFAULT_HANDLERS.keys()) == expected
    for name, handler in HANDLERS.items():
        assert DEFAULT_HANDLERS[name] is handler


def _get_handlers_module_path() -> Path:
    return Path(inspect.getfile(conversation_handler)).resolve()


def test_handlers_module_has_no_infrastructure_dependencies():
    """
    The handlers module must not import services, memory, EventBus,
    AI providers, kernel components, or other infrastructure.
    """
    module_path = _get_handlers_module_path()
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = {
        "atlas.services",
        "atlas.memory",
        "atlas.events",
        "atlas.ai",
        "atlas.kernel",
        "atlas.conversation",
        "atlas.knowledge",
        "atlas.task",
        "atlas.state",
        "atlas.storage",
        "atlas.runtime",
        "EventBus",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name.startswith(prefix) for prefix in forbidden
                ), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not any(
                module.startswith(prefix) for prefix in forbidden
            ), f"Forbidden import: {module}"
            for alias in node.names:
                assert alias.name not in forbidden, f"Forbidden import name: {alias.name}"


def test_handlers_only_import_execution_models():
    """
    Handlers should only import from atlas.reasoning.execution.models
    and standard library modules.
    """
    module_path = _get_handlers_module_path()
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    allowed_third_party_prefixes = ("atlas.reasoning.execution.models",)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("atlas"):
                assert module.startswith(allowed_third_party_prefixes), (
                    f"Handlers module imports non-allowed atlas module: {module}"
                )


# ---------------------------------------------------------------------------
# Knowledge retrieval factory tests
# ---------------------------------------------------------------------------


class FakeKnowledgeEntry:
    """A fake knowledge entry for testing."""

    def __init__(self, title: str = "Test", content: str = "Content", source: str = "test"):
        self.title = title
        self.content = content
        self.source = source


class FakeKnowledgeManager:
    """A fake KnowledgeManager recording query calls."""

    def __init__(self, results: list[FakeKnowledgeEntry] | None = None):
        self.queries: list[str] = []
        self._results = results or []

    def query(self, text: str) -> list[FakeKnowledgeEntry]:
        self.queries.append(text)
        return self._results


def test_knowledge_factory_registers_capability():
    """Factory registers knowledge_retrieval capability."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory
    from atlas.reasoning.execution.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=FakeKnowledgeManager())
    factory.register(registry)

    assert registry.has("knowledge_retrieval")
    assert registry.get("knowledge_retrieval") is not None


def test_knowledge_handler_queries_manager():
    """Handler delegates to KnowledgeManager.query()."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    entry = FakeKnowledgeEntry("Python", "A language", "docs")
    manager = FakeKnowledgeManager(results=[entry])
    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=manager)
    handlers = factory.handlers()

    result = handlers["knowledge_retrieval"]({"query": "programming"})

    assert result.success is True
    assert result.capability == "knowledge_retrieval"
    assert manager.queries == ["programming"]
    assert result.output["count"] == 1
    assert result.output["results"][0]["title"] == "Python"


def test_knowledge_handler_rejects_missing_query():
    """Handler rejects missing query safely."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=FakeKnowledgeManager())
    handlers = factory.handlers()

    result = handlers["knowledge_retrieval"]({})

    assert result.success is False
    assert "query" in result.error.lower()


def test_knowledge_handler_rejects_empty_query():
    """Handler rejects empty/whitespace query safely."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=FakeKnowledgeManager())
    handlers = factory.handlers()

    result = handlers["knowledge_retrieval"]({"query": "   "})

    assert result.success is False
    assert "query" in result.error.lower()


def test_knowledge_handler_rejects_non_string_query():
    """Handler rejects non-string query safely."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=FakeKnowledgeManager())
    handlers = factory.handlers()

    result = handlers["knowledge_retrieval"]({"query": 123})

    assert result.success is False


def test_knowledge_handler_applies_limit():
    """Handler applies optional limit to results."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    entries = [FakeKnowledgeEntry(f"T{i}", f"C{i}", "src") for i in range(5)]
    manager = FakeKnowledgeManager(results=entries)
    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=manager)
    handlers = factory.handlers()

    result = handlers["knowledge_retrieval"]({"query": "test", "limit": 3})

    assert result.success is True
    assert result.output["count"] == 3


def test_knowledge_handler_does_not_mutate_manager():
    """Handler does not mutate KnowledgeManager state."""
    from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

    manager = FakeKnowledgeManager(results=[FakeKnowledgeEntry()])
    factory = KnowledgeRetrievalHandlerFactory(knowledge_manager=manager)
    handlers = factory.handlers()

    handlers["knowledge_retrieval"]({"query": "test"})

    # Manager should only record the query, not be mutated
    assert len(manager.queries) == 1
