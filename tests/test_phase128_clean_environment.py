"""Phase 12.8 — Clean/minimal environment validation.

Validation result: in an isolated child process with a minimal environment (no
AI-related variables, no user site-packages, and every external AI SDK
unimportable), Atlas boots and serves conversation. Blocking the ONE required
external library (``requests`` — a generic HTTP client, not an AI dependency)
produces an explicit import failure, which is exactly the required-core vs
missing-optional distinction.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_CHILD_SCRIPT = '''
import importlib.abc
import json
import sys

BLOCKED = (
    "openai", "anthropic", "google.generativeai", "genai", "gemini", "ollama",
    "llama_cpp", "llamacpp", "transformers", "torch", "litellm", "mistralai",
    "cohere", "vllm", "dashscope", "qwen", "vertexai", "langchain",
    "huggingface_hub", "sentence_transformers", "cline", "copilot",
    "commandcode", "command_code", "httpx", "aiohttp",
)

block_requests = sys.argv[1] == "1"


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        prefixes = BLOCKED + (("requests",) if block_requests else ())
        for prefix in prefixes:
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise ImportError("blocked: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

try:
    from atlas.kernel.atlas import Atlas
    atlas = Atlas()
    atlas.start()
    try:
        reply = atlas.chat("hello")
        payload = {
            "provider": atlas.provider.name(),
            "capabilities": len(atlas.capability_model().entries),
            "reply_nonempty": bool(str(getattr(reply, "content", reply)).strip()),
            "env_ai_vars": [
                k for k in (
                    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"
                ) if k in __import__("os").environ
            ],
        }
        print("CHILD_JSON " + json.dumps(payload, sort_keys=True))
    finally:
        atlas.shutdown()
except ImportError as exc:
    print("CHILD_IMPORT_ERROR " + str(exc))
    raise SystemExit(3)
'''


def _clean_env() -> dict[str, str]:
    env = {
        "PYTHONPATH": str(_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _run_child(tmp_path: Path, block_requests: bool) -> subprocess.CompletedProcess:
    script = tmp_path / "phase12_child.py"
    script.write_text(_CHILD_SCRIPT, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), "1" if block_requests else "0"],
        cwd=str(_ROOT),
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestPhase128CleanEnvironment:
    def test_minimal_isolated_environment_boots_and_converses(self, tmp_path):
        completed = _run_child(tmp_path, block_requests=False)
        assert completed.returncode == 0, completed.stderr[-2000:]
        marker = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith("CHILD_JSON ")
        )
        payload = json.loads(marker[len("CHILD_JSON ") :])
        assert payload["provider"] == "Mock Provider"
        assert payload["capabilities"] > 0
        assert payload["reply_nonempty"] is True
        assert payload["env_ai_vars"] == []

    def test_missing_optional_ai_dependency_does_not_stop_atlas(self, tmp_path):
        completed = _run_child(tmp_path, block_requests=False)
        assert completed.returncode == 0
        assert "CHILD_IMPORT_ERROR" not in completed.stdout

    def test_missing_required_core_library_fails_loudly_and_is_not_ai(self, tmp_path):
        completed = _run_child(tmp_path, block_requests=True)
        assert completed.returncode == 3
        assert "CHILD_IMPORT_ERROR" in completed.stdout
        assert "requests" in completed.stdout
        # The one required external library is a generic HTTP client, which the
        # inventory classifies as an information source — never an AI dependency.
        from atlas.self_knowledge.independence_inventory import (
            DependencyClass,
            build_independence_inventory,
            repository_root,
        )

        record = next(
            r
            for r in build_independence_inventory(repository_root()).external_dependencies
            if r.name == "requests"
        )
        assert record.classification is DependencyClass.INFORMATION_SOURCE
        assert record.ai_related is False

    def test_child_environment_contains_no_ai_configuration(self, tmp_path):
        env = _clean_env()
        assert set(env) <= {"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PATH", "SYSTEMROOT", "TEMP", "TMP"}
        assert not any("API_KEY" in key or "AI_" in key for key in env)
