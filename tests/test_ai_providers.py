"""
Phase 6.10 — Multi-Provider AI Layer Tests.

Tests for OpenAI, LM Studio, and Anthropic providers
using mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from atlas.ai.providers.anthropic_provider import AnthropicProvider
from atlas.ai.providers.lmstudio_provider import LMStudioProvider
from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.providers.ollama_provider import OllamaProvider
from atlas.ai.providers.openai_provider import OpenAIProvider
from atlas.models.ai_response import AIResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def messages():
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]


@pytest.fixture
def openai_provider():
    return OpenAIProvider(
        model="gpt-4o-mini",
        timeout=30,
        api_key="test-key-openai",
    )


@pytest.fixture
def lmstudio_provider():
    return LMStudioProvider(
        model="local-model",
        timeout=30,
    )


@pytest.fixture
def anthropic_provider():
    return AnthropicProvider(
        model="claude-sonnet-4-20250514",
        timeout=30,
        api_key="test-key-anthropic",
    )


# ---------------------------------------------------------------------------
# MockProvider (existing — regression)
# ---------------------------------------------------------------------------


class TestMockProvider:

    def test_name(self):
        assert MockProvider().name() == "Mock Provider"

    def test_chat(self, messages):
        result = MockProvider().chat(messages)
        assert isinstance(result, AIResponse)
        assert result.provider == "Mock Provider"
        assert result.model == "atlas-mock-v1"
        assert len(result.text) > 0

    def test_stream_chat(self, messages):
        chunks = list(MockProvider().stream_chat(messages))
        assert len(chunks) > 0
        assert all(isinstance(c, str) for c in chunks)

    def test_complete(self):
        result = MockProvider().complete("test")
        assert isinstance(result, AIResponse)
        assert "test" in result.text

    def test_models(self):
        models = MockProvider().models()
        assert "atlas-mock-v1" in models


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------


class TestOpenAIProvider:

    def test_name(self, openai_provider):
        assert openai_provider.name() == "OpenAI"

    def test_init_does_not_require_api_key(self, messages):
        """API key check is deferred to usage time."""
        provider = OpenAIProvider(model="gpt-4o-mini", timeout=30, api_key="")
        assert provider._api_key == ""
        with pytest.raises(RuntimeError, match="API key"):
            provider.chat(messages)

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_chat(self, mock_post, openai_provider, messages):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        mock_post.return_value = mock_response

        result = openai_provider.chat(messages)

        assert isinstance(result, AIResponse)
        assert result.text == "Hello!"
        assert result.provider == "OpenAI"
        assert result.model == "gpt-4o-mini"
        assert result.tokens == 15
        assert result.finish_reason == "stop"
        assert result.metadata["prompt_tokens"] == 10
        assert result.metadata["completion_tokens"] == 5

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "chat/completions" in args[0]

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_stream_chat(self, mock_post, openai_provider, messages):
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b"data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" world\"}}]}",
            b"data: {\"choices\": [{\"delta\": {}}]}",
            b"data: [DONE]",
        ]
        mock_post.return_value = mock_response

        chunks = list(openai_provider.stream_chat(messages))

        assert chunks == ["Hello", " world"]

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_complete(self, mock_post, openai_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Completion result"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        }
        mock_post.return_value = mock_response

        result = openai_provider.complete("test prompt")

        assert isinstance(result, AIResponse)
        assert result.text == "Completion result"

    @patch("atlas.ai.providers.openai_provider.requests.get")
    def test_models(self, mock_get, openai_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o-mini"},
                {"id": "gpt-4o"},
            ]
        }
        mock_get.return_value = mock_response

        models = openai_provider.models()

        assert "gpt-4o-mini" in models
        assert "gpt-4o" in models

    @patch("atlas.ai.providers.openai_provider.requests.post")
    def test_chat_http_error(self, mock_post, openai_provider, messages):
        mock_post.side_effect = requests.exceptions.HTTPError("401 Unauthorized")

        with pytest.raises(requests.exceptions.HTTPError):
            openai_provider.chat(messages)

    def test_headers(self, openai_provider):
        headers = openai_provider._headers()
        assert headers["Authorization"] == "Bearer test-key-openai"
        assert headers["Content-Type"] == "application/json"

    def test_env_var_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider(model="gpt-4o-mini", timeout=30)
            assert provider._api_key == "env-key"

    def test_no_api_key_raises_on_use(self, messages):
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenAIProvider(model="gpt-4o-mini", timeout=30, api_key="")
            with pytest.raises(RuntimeError, match="API key"):
                provider.chat(messages)


# ---------------------------------------------------------------------------
# LM Studio Provider
# ---------------------------------------------------------------------------


class TestLMStudioProvider:

    def test_name(self, lmstudio_provider):
        assert lmstudio_provider.name() == "LM Studio"

    @patch("atlas.ai.providers.lmstudio_provider.requests.post")
    def test_chat(self, mock_post, lmstudio_provider, messages):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Local response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        mock_post.return_value = mock_response

        result = lmstudio_provider.chat(messages)

        assert isinstance(result, AIResponse)
        assert result.text == "Local response"
        assert result.provider == "LM Studio"
        assert result.model == "local-model"

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "chat/completions" in args[0]

    @patch("atlas.ai.providers.lmstudio_provider.requests.post")
    def test_stream_chat(self, mock_post, lmstudio_provider, messages):
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b"data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" from\"}}]}",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" LM\"}}]}",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" Studio\"}}]}",
            b"data: [DONE]",
        ]
        mock_post.return_value = mock_response

        chunks = list(lmstudio_provider.stream_chat(messages))

        assert chunks == ["Hello", " from", " LM", " Studio"]

    @patch("atlas.ai.providers.lmstudio_provider.requests.post")
    def test_complete(self, mock_post, lmstudio_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Completion response"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 3},
        }
        mock_post.return_value = mock_response

        result = lmstudio_provider.complete("test prompt")

        assert isinstance(result, AIResponse)
        assert result.text == "Completion response"

    @patch("atlas.ai.providers.lmstudio_provider.requests.get")
    def test_models(self, mock_get, lmstudio_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "local-model"},
                {"id": "llama-3.2-3b"},
            ]
        }
        mock_get.return_value = mock_response

        models = lmstudio_provider.models()

        assert "local-model" in models
        assert "llama-3.2-3b" in models

    def test_custom_base_url(self):
        provider = LMStudioProvider(
            model="test",
            timeout=30,
            base_url="http://localhost:8080/v1",
        )
        assert provider._base_url == "http://localhost:8080/v1"

    def test_default_base_url(self, lmstudio_provider):
        assert lmstudio_provider._base_url == "http://localhost:1234/v1"

    def test_headers(self, lmstudio_provider):
        headers = lmstudio_provider._headers()
        assert headers["Content-Type"] == "application/json"

    @patch("atlas.ai.providers.lmstudio_provider.requests.post")
    def test_chat_http_error(self, mock_post, lmstudio_provider, messages):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(requests.exceptions.ConnectionError):
            lmstudio_provider.chat(messages)


# ---------------------------------------------------------------------------
# Anthropic Provider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:

    def test_name(self, anthropic_provider):
        assert anthropic_provider.name() == "Anthropic"

    def test_init_does_not_require_api_key(self, messages):
        """API key check is deferred to usage time."""
        provider = AnthropicProvider(
            model="claude-sonnet-4-20250514", timeout=30, api_key=""
        )
        assert provider._api_key == ""
        with pytest.raises(RuntimeError, match="API key"):
            provider.chat(messages)

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_chat(self, mock_post, anthropic_provider, messages):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "Hello from Claude"},
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 8,
            },
        }
        mock_post.return_value = mock_response

        result = anthropic_provider.chat(messages)

        assert isinstance(result, AIResponse)
        assert result.text == "Hello from Claude"
        assert result.provider == "Anthropic"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.tokens == 20
        assert result.finish_reason == "end_turn"
        assert result.metadata["input_tokens"] == 12
        assert result.metadata["output_tokens"] == 8

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "messages" in args[0]

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_chat_multiple_content_blocks(self, mock_post, anthropic_provider, messages):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "from Claude"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }
        mock_post.return_value = mock_response

        result = anthropic_provider.chat(messages)

        assert result.text == "Hello from Claude"

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_stream_chat(self, mock_post, anthropic_provider, messages):
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"type": "content_block_delta", "delta": {"text": "Hello"}}',
            b'data: {"type": "content_block_delta", "delta": {"text": " from"}}',
            b'data: {"type": "content_block_delta", "delta": {"text": " Claude"}}',
            b'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}',
            b"data: [DONE]",
        ]
        mock_post.return_value = mock_response

        chunks = list(anthropic_provider.stream_chat(messages))

        assert chunks == ["Hello", " from", " Claude"]

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_complete(self, mock_post, anthropic_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Anthropic completion"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 3},
        }
        mock_post.return_value = mock_response

        result = anthropic_provider.complete("test prompt")

        assert isinstance(result, AIResponse)
        assert result.text == "Anthropic completion"

    @patch("atlas.ai.providers.anthropic_provider.requests.get")
    def test_models(self, mock_get, anthropic_provider):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-sonnet-4-20250514"},
                {"id": "claude-opus-4-20250514"},
            ]
        }
        mock_get.return_value = mock_response

        models = anthropic_provider.models()

        assert "claude-sonnet-4-20250514" in models
        assert "claude-opus-4-20250514" in models

    def test_headers(self, anthropic_provider):
        headers = anthropic_provider._headers()
        assert headers["x-api-key"] == "test-key-anthropic"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["Content-Type"] == "application/json"

    def test_env_var_api_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-anthropic-key"}):
            provider = AnthropicProvider(model="claude-sonnet-4-20250514", timeout=30)
            assert provider._api_key == "env-anthropic-key"

    def test_no_api_key_raises_on_use(self, messages):
        with patch.dict("os.environ", {}, clear=True):
            provider = AnthropicProvider(
                model="claude-sonnet-4-20250514",
                timeout=30,
                api_key="",
            )
            with pytest.raises(RuntimeError, match="API key"):
                provider.chat(messages)

    @patch("atlas.ai.providers.anthropic_provider.requests.post")
    def test_chat_http_error(self, mock_post, anthropic_provider, messages):
        mock_post.side_effect = requests.exceptions.HTTPError("403 Forbidden")

        with pytest.raises(requests.exceptions.HTTPError):
            anthropic_provider.chat(messages)


# ---------------------------------------------------------------------------
# Provider interface compliance
# ---------------------------------------------------------------------------


class TestProviderInterfaceCompliance:
    """Every provider must implement the full AIProvider interface."""

    def _check_interface(self, provider):
        assert hasattr(provider, "name")
        assert hasattr(provider, "chat")
        assert hasattr(provider, "stream_chat")
        assert hasattr(provider, "complete")
        assert hasattr(provider, "models")

        assert callable(provider.name)
        assert callable(provider.chat)
        assert callable(provider.stream_chat)
        assert callable(provider.complete)
        assert callable(provider.models)

    def test_openai_implements_interface(self, openai_provider):
        self._check_interface(openai_provider)

    def test_lmstudio_implements_interface(self, lmstudio_provider):
        self._check_interface(lmstudio_provider)

    def test_anthropic_implements_interface(self, anthropic_provider):
        self._check_interface(anthropic_provider)

    def test_ollama_implements_interface(self):
        provider = OllamaProvider(model="test-model", timeout=30)
        self._check_interface(provider)

    def test_mock_implements_interface(self):
        self._check_interface(MockProvider())