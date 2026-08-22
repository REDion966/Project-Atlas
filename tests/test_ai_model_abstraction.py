"""
AI Provider/Model Abstraction Batch — Tests.

Covers:
  GAP-1: RoutingDecision.model_name reaches the selected provider.
  GAP-2: OpenRouterProvider behind the AIProvider abstraction (mocked HTTP).
  GAP-3: Config-driven model profile loading with safe defaults.

All transport is mocked — no real network calls.
"""

import tomllib
from unittest.mock import MagicMock, patch

import pytest

from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.providers.openrouter_provider import OpenRouterProvider
from atlas.ai.router.ai_router import AIRouter
from atlas.ai.routing.models import ModelProfile, RoutingDecision
from atlas.ai.routing.profile_loader import load_model_profiles
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.models.ai_response import AIResponse


MESSAGES = [{"role": "user", "content": "Hello"}]


# ---------------------------------------------------------------------------
# GAP-1: per-call model override
# ---------------------------------------------------------------------------


class TestProviderModelOverride:
    """model=None uses the configured default; model=X uses X."""

    def test_mock_default_model(self):
        response = MockProvider().chat(MESSAGES)
        assert response.model == "atlas-mock-v1"

    def test_mock_override_model(self):
        response = MockProvider().chat(MESSAGES, model="other-model")
        assert response.model == "other-model"

    def test_mock_complete_override(self):
        response = MockProvider().complete("hi", model="override-m")
        assert response.model == "override-m"

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_openai_override_reaches_payload(self, mock_post):
        from atlas.ai.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="default-m", timeout=30, api_key="k")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
        }
        mock_post.return_value = mock_response

        provider.chat(MESSAGES, model="routed-model")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "routed-model"

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_openai_none_uses_default(self, mock_post):
        from atlas.ai.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="default-m", timeout=30, api_key="k")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
        }
        mock_post.return_value = mock_response

        provider.chat(MESSAGES)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "default-m"

    @patch("atlas.ai.providers.ollama_provider.requests.post")
    def test_ollama_override_reaches_payload_and_response(self, mock_post):
        from atlas.ai.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider(model="qwen3:8b", timeout=30)
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "ok"}}
        mock_post.return_value = mock_response

        result = provider.chat(MESSAGES, model="llama3:8b")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "llama3:8b"
        assert result.model == "llama3:8b"

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_anthropic_override_reaches_payload(self, mock_post):
        from atlas.ai.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(model="claude-default", timeout=30, api_key="k")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        mock_post.return_value = mock_response

        provider.chat(MESSAGES, model="claude-routed")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "claude-routed"


class TestAIRouterModelForwarding:
    """AIRouter forwards RoutingDecision.model_name to the provider."""

    def _router_with_spy(self, profile_registry=None):
        router = AIRouter(model_profile_registry=profile_registry)
        provider = MockProvider()
        router.registry.register(provider)
        router.use("Mock Provider")
        return router, provider

    def test_decision_model_reaches_provider(self):
        router, provider = self._router_with_spy()
        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="routed-model",
        )

        with patch.object(provider, "chat", wraps=provider.chat) as spy:
            response = router.chat(MESSAGES, routing_decision=decision)

        spy.assert_called_once_with(MESSAGES, model="routed-model")
        assert response.model == "routed-model"

    def test_no_decision_uses_default_model(self):
        router, provider = self._router_with_spy()

        with patch.object(provider, "chat", wraps=provider.chat) as spy:
            router.chat(MESSAGES)

        spy.assert_called_once_with(MESSAGES, model=None)

    def test_stream_decision_model_reaches_provider(self):
        router, provider = self._router_with_spy()
        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="routed-model",
        )

        with patch.object(
            provider, "stream_chat", wraps=provider.stream_chat
        ) as spy:
            chunks = list(router.stream_chat(MESSAGES, routing_decision=decision))

        spy.assert_called_once_with(MESSAGES, model="routed-model")
        assert len(chunks) > 0

    def test_unregistered_model_raises_with_profile_registry(self):
        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
        ))
        router, _provider = self._router_with_spy(profile_registry=registry)

        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="unknown-model",
        )

        with pytest.raises(RuntimeError, match="not"):
            router.chat(MESSAGES, routing_decision=decision)

    def test_registered_model_passes_validation(self):
        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
        ))
        router, _provider = self._router_with_spy(profile_registry=registry)

        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
        )

        response = router.chat(MESSAGES, routing_decision=decision)
        assert response.model == "atlas-mock-v1"

    def test_without_profile_registry_no_validation(self):
        """Without a profile registry the decision model is trusted."""
        router, _provider = self._router_with_spy(profile_registry=None)
        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="anything",
        )

        response = router.chat(MESSAGES, routing_decision=decision)
        assert response.model == "anything"


# ---------------------------------------------------------------------------
# GAP-2: OpenRouterProvider
# ---------------------------------------------------------------------------


class TestOpenRouterProvider:
    """OpenRouter behind the AIProvider abstraction, mocked transport."""

    def _provider(self):
        return OpenRouterProvider(
            model="openai/gpt-4o-mini",
            timeout=30,
            api_key="test-openrouter-key",
        )

    def test_name(self):
        assert self._provider().name() == "OpenRouter"

    def test_default_base_url(self):
        assert self._provider()._base_url == "https://openrouter.ai/api/v1"

    def test_custom_base_url(self):
        provider = OpenRouterProvider(
            model="m", timeout=30, api_key="k", base_url="http://localhost:9/v1/"
        )
        assert provider._base_url == "http://localhost:9/v1"

    def test_headers(self):
        headers = self._provider()._headers()
        assert headers["Authorization"] == "Bearer test-openrouter-key"
        assert headers["Content-Type"] == "application/json"

    def test_no_api_key_raises_on_use(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenRouterProvider(model="m", timeout=30, api_key="")
            with pytest.raises(RuntimeError, match="API key"):
                provider.chat(MESSAGES)

    def test_env_var_api_key(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-key"}):
            provider = OpenRouterProvider(model="m", timeout=30)
            assert provider._api_key == "env-key"

    @patch("atlas.ai.providers.openrouter_provider.requests.post")
    def test_chat(self, mock_post):
        provider = self._provider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Router!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
        mock_post.return_value = mock_response

        result = provider.chat(MESSAGES)

        assert isinstance(result, AIResponse)
        assert result.text == "Router!"
        assert result.provider == "OpenRouter"
        assert result.model == "openai/gpt-4o-mini"
        assert result.tokens == 6
        assert result.finish_reason == "stop"
        assert result.metadata["prompt_tokens"] == 4
        assert result.metadata["completion_tokens"] == 2

        args, kwargs = mock_post.call_args
        assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["json"]["model"] == "openai/gpt-4o-mini"

    @patch("atlas.ai.providers.openrouter_provider.requests.post")
    def test_chat_model_override(self, mock_post):
        provider = self._provider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
        }
        mock_post.return_value = mock_response

        result = provider.chat(MESSAGES, model="meta-llama/llama-3.1-70b")

        assert result.model == "meta-llama/llama-3.1-70b"
        assert mock_post.call_args.kwargs["json"]["model"] == (
            "meta-llama/llama-3.1-70b"
        )

    @patch("atlas.ai.providers.openrouter_provider.requests.post")
    def test_stream_chat(self, mock_post):
        provider = self._provider()
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b"data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" router\"}}]}",
            b"data: {\"choices\": [{\"delta\": {}}]}",
            b"data: [DONE]",
        ]
        mock_post.return_value = mock_response

        chunks = list(provider.stream_chat(MESSAGES))

        assert chunks == ["Hello", " router"]
        assert mock_post.call_args.kwargs["json"]["stream"] is True

    @patch("atlas.ai.providers.openrouter_provider.requests.post")
    def test_complete(self, mock_post):
        provider = self._provider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 2},
        }
        mock_post.return_value = mock_response

        result = provider.complete("prompt here")

        assert result.text == "done"
        assert mock_post.call_args.kwargs["json"]["messages"] == [
            {"role": "user", "content": "prompt here"}
        ]

    @patch("atlas.ai.providers.openrouter_provider.requests.get")
    def test_models(self, mock_get):
        provider = self._provider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "openai/gpt-4o-mini"},
                {"id": "meta-llama/llama-3.1-70b"},
            ]
        }
        mock_get.return_value = mock_response

        models = provider.models()

        assert "openai/gpt-4o-mini" in models
        assert "meta-llama/llama-3.1-70b" in models

    @patch("atlas.ai.providers.openrouter_provider.requests.post")
    def test_chat_http_error(self, mock_post):
        import requests

        provider = self._provider()
        mock_post.side_effect = requests.exceptions.HTTPError("402")

        with pytest.raises(requests.exceptions.HTTPError):
            provider.chat(MESSAGES)


class TestOpenRouterRegistration:
    """OpenRouter registers through AIManager but is never the default."""

    def test_registered_and_optional(self):
        from atlas.ai.ai_manager import AIManager

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=30,
            api_keys=None,
        )

        assert manager._router.registry.exists("OpenRouter")
        # Active provider is the configured one, not OpenRouter.
        assert manager.provider.name() == "Mock Provider"

    def test_openrouter_not_selected_without_config(self):
        from atlas.ai.ai_manager import AIManager

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=30,
        )

        # No key configured → OpenRouter must not be activated.
        assert manager.provider.name() != "OpenRouter"


# ---------------------------------------------------------------------------
# GAP-3: profile loader
# ---------------------------------------------------------------------------


class TestProfileLoader:
    """Config-driven profiles with safe defaults."""

    def test_defaults_when_unconfigured(self):
        profiles = load_model_profiles(None, "qwen3:8b")

        assert len(profiles) == 2
        by_key = {(p.provider_name, p.model_name): p for p in profiles}
        mock = by_key[("Mock Provider", "atlas-mock-v1")]
        ollama = by_key[("Ollama", "qwen3:8b")]

        assert mock.complexity_score == 0.3
        assert mock.priority == 10
        assert ollama.complexity_score == 0.8
        assert ollama.priority == 20
        assert ollama.supported_tasks == ["conversation", "analysis", "code"]

    def test_defaults_when_empty(self):
        profiles = load_model_profiles([], "any-model")
        assert {(p.provider_name) for p in profiles} == {"Mock Provider", "Ollama"}
        assert profiles[1].model_name == "any-model"

    def test_configured_profiles_override_defaults(self):
        entries = [
            {
                "provider_name": "OpenRouter",
                "model_name": "openai/gpt-4o-mini",
                "complexity_score": 0.9,
                "priority": 30,
            },
            {
                "provider_name": "Ollama",
                "model_name": "",
                "complexity_score": 0.6,
                "priority": 20,
            },
        ]

        profiles = load_model_profiles(entries, "qwen3:8b")

        assert len(profiles) == 2
        by_key = {(p.provider_name, p.model_name): p for p in profiles}
        assert ("OpenRouter", "openai/gpt-4o-mini") in by_key
        # Empty model_name resolves to the configured model.
        assert ("Ollama", "qwen3:8b") in by_key

    def test_defaults_reproduce_previous_kernel_behavior(self):
        """The loaded defaults must match the previously hard-coded
        kernel profiles exactly (routing behavior preserved)."""
        profiles = load_model_profiles(None, "qwen3:8b")
        registry = ModelProfileRegistry()
        for profile in profiles:
            registry.register(profile)

        assert registry.get("Mock Provider", "atlas-mock-v1") is not None
        assert registry.get("Ollama", "qwen3:8b") is not None
        assert registry.get("Mock Provider", "qwen3:8b") is None


class TestConfigProfilesSection:
    """Configuration loads the optional [ai.profiles] section."""

    def test_config_without_profiles_defaults_to_empty(self, tmp_path):
        from atlas.config.configuration import Configuration

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "\n".join([
                "[application]",
                'name = "Atlas"',
                'version = "0.0.0"',
                "[ai]",
                'provider = "Mock Provider"',
                'model = "atlas-mock-v1"',
                "temperature = 0.7",
                "timeout = 30",
                "[conversation]",
                "history_limit = 5",
                "[logging]",
                'level = "INFO"',
            ])
        )

        config = Configuration(str(config_file))
        config.load()

        assert config.settings.ai.profiles == []

    def test_config_with_profiles_loads_entries(self, tmp_path):
        from atlas.config.configuration import Configuration

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "\n".join([
                "[application]",
                'name = "Atlas"',
                'version = "0.0.0"',
                "[ai]",
                'provider = "Mock Provider"',
                'model = "atlas-mock-v1"',
                "temperature = 0.7",
                "timeout = 30",
                "[[ai.profiles]]",
                'provider_name = "OpenRouter"',
                'model_name = "openai/gpt-4o-mini"',
                "complexity_score = 0.9",
                "priority = 30",
                "[conversation]",
                "history_limit = 5",
                "[logging]",
                'level = "INFO"',
            ])
        )

        config = Configuration(str(config_file))
        config.load()

        assert len(config.settings.ai.profiles) == 1
        assert config.settings.ai.profiles[0]["provider_name"] == "OpenRouter"

        profiles = load_model_profiles(
            config.settings.ai.profiles, config.settings.ai.model
        )
        assert profiles[0].model_name == "openai/gpt-4o-mini"


if __name__ == "__main__":
    pytest.main([__file__])
