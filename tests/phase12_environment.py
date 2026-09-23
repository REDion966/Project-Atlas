"""Phase 12 test support: a controlled model-free environment.

Not a test module (no ``test_`` prefix, so pytest does not collect it). It
provides the isolation primitive used by every Phase 12 independence test:

* external AI/model/provider/coding-agent modules become unimportable;
* AI-related environment variables are removed for the duration;
* outbound socket connections are refused and recorded.

It never mutates the user's environment permanently: every effect is restored
on exit.
"""

from __future__ import annotations

import contextlib
import importlib.abc
import os
import socket
import sys
from typing import Any, Iterator

#: External AI/model/provider and coding-agent ecosystems. Importing any of
#: these during a Phase 12 test is an independence failure.
BLOCKED_MODULES: tuple[str, ...] = (
    "openai",
    "anthropic",
    "google.generativeai",
    "genai",
    "gemini",
    "ollama",
    "llama_cpp",
    "llamacpp",
    "transformers",
    "torch",
    "litellm",
    "mistralai",
    "cohere",
    "vllm",
    "dashscope",
    "qwen",
    "vertexai",
    "langchain",
    "huggingface_hub",
    "sentence_transformers",
    "cline",
    "copilot",
    "commandcode",
    "command_code",
    "httpx",
    "aiohttp",
)

#: AI-related environment variables removed for the duration of a test.
AI_ENV_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
    "OLLAMA_HOST",
    "LMSTUDIO_HOST",
)


class _Blocker(importlib.abc.MetaPathFinder):
    """Refuses any import of a blocked external AI ecosystem."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        for prefix in BLOCKED_MODULES:
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise ImportError(
                    f"blocked for independence validation: {fullname}"
                )
        return None


@contextlib.contextmanager
def model_free_environment(
    block_network: bool = True,
) -> Iterator[list[Any]]:
    """Yield a list collecting every refused outbound connection attempt."""
    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    removed_env = {k: os.environ.pop(k) for k in AI_ENV_VARS if k in os.environ}
    attempts: list[Any] = []
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def _refuse(self, address, *args, **kwargs):  # noqa: ANN001, ARG001
        attempts.append(("socket.connect", address))
        raise OSError("network access blocked for independence validation")

    def _refuse_create(address, *args, **kwargs):  # noqa: ANN001, ARG001
        attempts.append(("create_connection", address))
        raise OSError("network access blocked for independence validation")

    if block_network:
        socket.socket.connect = _refuse
        socket.create_connection = _refuse_create
    try:
        yield attempts
    finally:
        if block_network:
            socket.socket.connect = real_connect
            socket.create_connection = real_create
        try:
            sys.meta_path.remove(blocker)
        except ValueError:
            pass
        for key, value in removed_env.items():
            os.environ[key] = value


def boot_model_free_kernel() -> Any:
    """Return a started, model-free Atlas kernel (caller shuts it down)."""
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas
