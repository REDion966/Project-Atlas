"""Task 1.1 — model-backed conversation provenance reporting.

Contract under test (the two conversation response paths identified by Task 1):

  A. pipeline-final-response (``conversation_service``): the accepted pipeline
     answer already carries ``ai_provenance`` (validated by the L8-b-ii
     precedence gate) — the returned message must report ``model_used: True``
     and preserve the provenance.
  B. residual/generic AI path: the ``AIResponse`` already carries
     ``provider`` / ``model`` — the returned message must report
     ``model_used: True`` for a genuine external provider, and must NOT claim it
     for the deterministic local no-network tier.

Deterministic/builtin answers stay ``model_used: False``, and a provider failure
that ends in the deterministic fallback must never claim ``model_used: True``.

Everything here is offline: provider behaviour is exercised through injected
doubles, so no network, no provider, and no configuration change is involved.
"""

from __future__ import annotations

from typing import Any

from atlas.ai.routing.models import LOCAL_PROVIDER_NAMES
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import (
    ConversationService,
    _external_provider_provenance,
    _pipeline_provider_provenance,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.models.ai_response import AIResponse

_MODEL_PROMPT = "What should I look for when reviewing a smartphone camera?"


class _FakeAI:
    """Minimal AI service double: returns a configured AIResponse or raises."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[Any] = []

    def chat(self, messages, routing_context=None):
        self.calls.append((messages, routing_context))
        if self._error is not None:
            raise self._error
        return self._response


class _Decision:
    """Minimal CognitionDecision double (only what the path reads)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.action = "respond"
        self.reasoning = "deterministic-double"
        self.data = data


class _FakeCognition:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.calls = 0

    def process(self, **kwargs) -> _Decision:  # noqa: ARG002
        self.calls += 1
        return _Decision(self._data)


def _service(ai: Any, *, cognition: Any = None, builtin: Any = None) -> ConversationService:
    return ConversationService(
        ai,
        task_intake=TaskIntake(),
        builtin_response=builtin,
        cognition_api=cognition,
    )


def _external_response() -> AIResponse:
    return AIResponse(
        text="Focus on sensor size, aperture, stabilization and low-light samples.",
        provider="Ollama",
        model="qwen3:8b",
    )


# ---------------------------------------------------------------------------
# Path B — residual / generic AI path
# ---------------------------------------------------------------------------


class TestResidualAiPath:
    def test_external_provider_answer_reports_model_used_true(self):
        message = _service(_FakeAI(_external_response())).send(_MODEL_PROMPT)
        assert message.content.startswith("Focus on sensor size")
        assert message.metadata["model_used"] is True
        assert message.metadata["ai_provenance"] == {
            "provider": "Ollama",
            "model": "qwen3:8b",
        }

    def test_local_no_network_tier_answer_is_not_model_backed(self):
        local = next(iter(LOCAL_PROVIDER_NAMES))
        message = _service(
            _FakeAI(AIResponse(text="deterministic tier text", provider=local, model="m"))
        ).send(_MODEL_PROMPT)
        assert message.metadata["model_used"] is False
        assert "ai_provenance" not in message.metadata

    def test_provider_without_identity_is_never_model_backed(self):
        message = _service(
            _FakeAI(AIResponse(text="unattributed text", provider="", model=""))
        ).send(_MODEL_PROMPT)
        assert message.metadata["model_used"] is False
        assert "ai_provenance" not in message.metadata

    def test_provider_failure_falls_back_without_claiming_model_used(self):
        """Mirrors the observed kernel behaviour: a failed provider attempt
        whose turn ends in the deterministic floor reports the failure, never
        a model-backed answer."""
        ai = _FakeAI(error=RuntimeError("provider unavailable"))
        service = _service(
            ai,
            cognition=_FakeCognition({}),  # pipeline produced nothing usable
            builtin=BuiltinResponseService(),
        )
        message = service.send(_MODEL_PROMPT)
        assert message.metadata.get("model_used") is not True
        assert message.metadata.get("fallback_after_provider_failure") is True
        assert "Focus on sensor size" not in message.content

    def test_ai_path_exception_reports_no_model_backing(self):
        """Path B's own failure branch: the attempt is made, no claim is kept."""
        ai = _FakeAI(error=RuntimeError("provider unavailable"))
        message = _service(ai).send(_MODEL_PROMPT)
        assert ai.calls, "the AI path must have been attempted"
        assert message.metadata.get("model_used") is not True
        assert "ai_provenance" not in message.metadata


# ---------------------------------------------------------------------------
# Path A — pipeline-final-response
# ---------------------------------------------------------------------------


class TestPipelineFinalResponsePath:
    @staticmethod
    def _data(provider: Any = "Ollama", model: Any = "qwen3:8b") -> dict[str, Any]:
        provenance: dict[str, Any] = {"provider": provider}
        if model is not None:
            provenance["model"] = model
        return {
            "final_response": "Use a larger sensor and check low-light samples.",
            "ai_provenance": provenance,
        }

    def test_pipeline_answer_reports_model_used_true_and_preserves_cognition(self):
        cognition = _FakeCognition(self._data())
        service = _service(
            _FakeAI(RuntimeError("the residual AI path must not be used")),
            cognition=cognition,
            builtin=BuiltinResponseService(),
        )
        message = service.send(_MODEL_PROMPT)
        assert cognition.calls == 1
        assert message.content == "Use a larger sensor and check low-light samples."
        assert message.metadata["model_used"] is True
        assert message.metadata["ai_provenance"] == {
            "provider": "Ollama",
            "model": "qwen3:8b",
        }
        assert message.metadata["cognition"] == {"source": "pipeline_final_response"}

    def test_pipeline_answer_without_provenance_is_not_marked_model_backed(self):
        data = {"final_response": "Unsourced answer."}
        service = _service(
            _FakeAI(error=RuntimeError("provider unavailable")),
            cognition=_FakeCognition(data),
            builtin=BuiltinResponseService(),
        )
        message = service.send(_MODEL_PROMPT)
        assert message.metadata.get("model_used") is not True
        assert "Unsourced answer." not in message.content

    def test_local_tier_pipeline_answer_is_not_marked_model_backed(self):
        local = next(iter(LOCAL_PROVIDER_NAMES))
        service = _service(
            _FakeAI(error=RuntimeError("provider unavailable")),
            cognition=_FakeCognition(self._data(provider=local, model="atlas-mock-v1")),
            builtin=BuiltinResponseService(),
        )
        message = service.send(_MODEL_PROMPT)
        assert message.metadata.get("model_used") is not True


# ---------------------------------------------------------------------------
# Deterministic baseline — unchanged
# ---------------------------------------------------------------------------


class TestDeterministicBaseline:
    def test_builtin_answer_still_reports_model_used_false(self):
        service = _service(_FakeAI(_external_response()), builtin=BuiltinResponseService())
        message = service.send("hello")
        assert message.metadata["builtin_intent"] == "greeting"
        assert message.metadata["model_used"] is False
        assert "ai_provenance" not in message.metadata


# ---------------------------------------------------------------------------
# The shared provenance helper (unit contract)
# ---------------------------------------------------------------------------


class TestProvenanceHelper:
    def test_external_provider_yields_bounded_provenance(self):
        assert _external_provider_provenance("Ollama", "qwen3:8b") == {
            "provider": "Ollama",
            "model": "qwen3:8b",
        }

    def test_missing_model_is_omitted_not_invented(self):
        assert _external_provider_provenance("SomeProvider", None) == {
            "provider": "SomeProvider"
        }

    def test_local_tier_and_missing_identity_yield_none(self):
        for local in LOCAL_PROVIDER_NAMES:
            assert _external_provider_provenance(local, "m") is None
        assert _external_provider_provenance(None, None) is None
        assert _external_provider_provenance("   ", "m") is None

    def test_pipeline_provenance_requires_the_existing_payload_shape(self):
        assert _pipeline_provider_provenance(None) is None
        assert _pipeline_provider_provenance({"final_response": "x"}) is None
        assert _pipeline_provider_provenance({"ai_provenance": "nope"}) is None
        assert _pipeline_provider_provenance(
            {"ai_provenance": {"provider": "Ollama", "model": "qwen3:8b"}}
        ) == {"provider": "Ollama", "model": "qwen3:8b"}
