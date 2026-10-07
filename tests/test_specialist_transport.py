"""The real local transport: bounded, local-only, fail-closed.

The live model is exercised once by the probe (not here); these tests pin the
transport's contract with a fake HTTP layer so they stay fast and deterministic.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from atlas.specialist_transport import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    MAX_RESPONSE_CHARS,
    ollama_transport,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub(monkeypatch, *, model_text=None, raises=None, body=None):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        if raises is not None:
            raise raises
        payload = body if body is not None else {"response": model_text}
        return _FakeResponse(json.dumps(payload))

    monkeypatch.setattr(
        "atlas.specialist_transport.urllib.request.urlopen", fake_urlopen
    )
    return captured


class TestTransportDefaults:
    def test_is_local_and_uses_a_code_specialist(self):
        assert DEFAULT_HOST.startswith("http://127.0.0.1")
        assert DEFAULT_MODEL == "qwen2.5-coder:7b"

    def test_request_targets_the_local_generate_endpoint(self, monkeypatch):
        captured = _stub(monkeypatch, model_text='{"files": {}}')
        ollama_transport()({"capability": "code.generate"})
        assert captured["url"] == f"{DEFAULT_HOST}/api/generate"
        assert captured["body"]["model"] == DEFAULT_MODEL
        assert captured["body"]["stream"] is False
        assert captured["body"]["format"] == "json"
        assert captured["body"]["options"] == {"temperature": 0}

    def test_the_prompt_is_the_bounded_request_verbatim(self, monkeypatch):
        request = {"capability": "code.generate", "target": "atlas/x.py"}
        captured = _stub(monkeypatch, model_text='{"files": {}}')
        ollama_transport()(request)
        assert json.loads(captured["body"]["prompt"]) == request


class TestTransportFailClosed:
    def test_valid_object_is_returned(self, monkeypatch):
        _stub(monkeypatch, model_text='{"files": {"a.py": "x = 1\\n"}}')
        assert ollama_transport()({}) == {"files": {"a.py": "x = 1\n"}}

    @pytest.mark.parametrize(
        "model_text",
        ["", "not json", "[1, 2, 3]", '"a string"', "42", "null"],
    )
    def test_unusable_model_output_becomes_an_empty_mapping(
        self, monkeypatch, model_text
    ):
        _stub(monkeypatch, model_text=model_text)
        assert ollama_transport()({}) == {}

    def test_oversized_output_is_refused(self, monkeypatch):
        _stub(monkeypatch, model_text='{"files": {"a.py": "x"}}')
        transport = ollama_transport(max_response_chars=5)
        assert transport({}) == {}

    def test_missing_response_field_is_refused(self, monkeypatch):
        _stub(monkeypatch, body={"not_response": "x"})
        assert ollama_transport()({}) == {}

    def test_non_string_response_is_refused(self, monkeypatch):
        _stub(monkeypatch, body={"response": {"files": {}}})
        assert ollama_transport()({}) == {}

    def test_connection_failure_propagates_to_the_adapter(self, monkeypatch):
        _stub(monkeypatch, raises=OSError("connection refused"))
        with pytest.raises(OSError):
            ollama_transport()({})


class TestNoVendorLeakage:
    def test_transport_uses_only_the_standard_library(self):
        import ast

        source = (ROOT / "atlas" / "specialist_transport.py").read_text(
            encoding="utf-8"
        )
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "openai", "anthropic", "requests", "httpx", "torch",
            "transformers", "langchain",
        ):
            assert forbidden not in imported

    def test_transport_cannot_touch_the_repository_or_governance(self):
        source = (ROOT / "atlas" / "specialist_transport.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "code_sandbox", "approval_manager", "promotion_gate",
            "pathlib", "subprocess", "shutil", "os.remove",
        ):
            assert forbidden not in source
