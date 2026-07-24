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
    knowledge_retrieval_handler,
    task_execution_handler,
    noop_handler,
)
from atlas.reasoning.execution.models import ExecutionResult


HANDLERS = {
    "conversation": conversation_handler,
    "knowledge_retrieval": knowledge_retrieval_handler,
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
    expected = {"conversation", "knowledge_retrieval", "analysis", "task_execution", "noop"}
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
