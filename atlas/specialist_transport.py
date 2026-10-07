"""The ONE real specialist transport: a local Ollama runtime.

Chosen because it is genuinely reachable in this environment and satisfies the
architectural constraints exactly:

* **Local** — inference happens on ``127.0.0.1``; no data leaves the machine, no
  hosted account, no API key, no egress policy question.
* **Replaceable** — it is a plain ``dict -> dict`` callable behind
  :class:`~atlas.specialist_providers.HttpCodeGenerationProvider`. Swapping the
  runtime or the model is a configuration change, never an Atlas change.
* **Bounded specialist, not an agent** — one stateless prompt/response; no tool
  loop, no autonomy, no repository access.
* **No vendor in Atlas core** — this module uses only the standard library and
  is wired at the composition boundary.

The model is a parameter, never an identity: ``qwen2.5-coder:7b`` is a
purpose-built coding model already present locally, and the configured default
(``qwen3:8b``) or ``deepseek-coder-v2`` can be substituted without touching any
other module.

Fail-closed by construction: a transport error, a timeout, a non-JSON body or an
oversized response raises or yields an empty mapping, which the adapter turns
into ``None`` so Atlas continues on its deterministic path.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable

#: Bounds (a specialist call can never hang or flood Atlas).
DEFAULT_HOST: str = "http://127.0.0.1:11434"
DEFAULT_MODEL: str = "qwen2.5-coder:7b"
DEFAULT_TIMEOUT_SECONDS: float = 180.0
MAX_RESPONSE_CHARS: int = 40_000


def ollama_transport(
    *,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_response_chars: int = MAX_RESPONSE_CHARS,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a bounded ``Transport`` over a local Ollama runtime.

    The returned callable sends the ALREADY-BOUNDED request as a single JSON
    prompt with ``temperature=0`` and ``format="json"`` so output is a single
    parseable object, then returns the decoded mapping. It performs no retry,
    no streaming and no tool use, and it never touches the filesystem.
    """

    def transport(request: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(
            {
                "model": model,
                "prompt": json.dumps(request),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            f"{host.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            body = json.loads(response.read())
        text = body.get("response")
        if not isinstance(text, str) or len(text) > max_response_chars:
            return {}
        try:
            decoded = json.loads(text)
        except Exception:  # noqa: BLE001 — unparseable output is not a proposal
            return {}
        return decoded if isinstance(decoded, dict) else {}

    return transport


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_CHARS",
    "ollama_transport",
]
