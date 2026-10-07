"""Concrete specialist providers built on the Atlas-owned seam.

One adapter, deliberately vendor-neutral. It carries no model identity into
Atlas's architecture: the provider is configured at the boundary, speaks a
bounded structured contract, and returns an UNTRUSTED
:class:`~atlas.specialists.SpecialistProposal`.

Design constraints (why it looks like this)
-------------------------------------------
* **No vendor import.** The adapter never imports an SDK, an HTTP client or a
  framework. Transport is INJECTED as a callable, so Atlas stays
  dependency-free and one provider can be substituted for another without
  touching any other module.
* **No authority.** The adapter cannot reach the filesystem, a sandbox, an
  approval surface or the promotion gate. It proposes; Atlas decides.
* **Fail-closed.** Provider unavailability, a raising transport, malformed
  output, a wrong capability or a provider identity mismatch all yield
  ``None`` — never a partial or guessed proposal.
* **Bounded in.** It only ever forwards
  :meth:`BoundedSpecialistTask.bounded`, so a provider cannot be handed an
  unbounded repository.

The first capability wired is ``code.generate``: Atlas's one remaining
authoring gap is turning a bounded, already-localized change request into a
candidate implementation. Every stage around it (localization, ChangePlan,
VerificationExpectation, validation, sandbox, approval, promotion) is already
Atlas-owned and stays so.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.specialists import (
    CODE_GENERATE,
    MAX_IDENTIFIER_CHARS,
    BoundedSpecialistTask,
    SpecialistProposal,
)

#: A transport maps a bounded request dict to a response dict. Implementations
#: own ALL network/process concerns; this module never opens a socket.
Transport = Callable[[dict[str, Any]], dict[str, Any]]


class ProviderUnavailable(RuntimeError):
    """Raised only where a caller asks a provider to be constructed without one."""


def build_code_generation_request(
    task: BoundedSpecialistTask,
) -> dict[str, Any]:
    """The bounded, vendor-neutral request body for ``code.generate``.

    Contains only what the task already authorized: the bounded request, the
    localized target, the bounded context, the plan summary and the plan's
    authoritative verification tests. Bounds are re-applied here so a caller
    cannot bypass them by constructing a task directly.
    """
    bounded = task.bounded()
    return {
        "capability": bounded.capability,
        "request": bounded.request,
        "target": bounded.target,
        "context": dict(bounded.context),
        "plan": dict(bounded.plan),
        "verification_tests": list(bounded.verification_tests),
        "instructions": (
            "Propose the smallest change that satisfies the request without "
            "altering unrelated behaviour. Reply with a JSON object of the "
            "form {\"files\": {path: full_new_content}, \"note\": str}. Paths "
            "must be repository-relative and inside the target."
        ),
    }


def parse_code_generation_response(
    response: Any,
    task: BoundedSpecialistTask,
    *,
    provider_id: str,
    model_id: str = "",
    confidence: float = 0.0,
) -> SpecialistProposal | None:
    """Parse a transport response into an UNTRUSTED proposal (fail-closed).

    Accepts only a mapping carrying a non-empty ``files`` mapping of
    repository-relative path to new content. Anything else — a non-mapping, a
    missing or empty ``files``, a non-string body, or a field of the wrong type
    — yields ``None``. No path is resolved or trusted here; containment is
    Atlas's job in ``validate_proposal``.
    """
    if not isinstance(response, dict):
        return None
    files = response.get("files")
    if not isinstance(files, dict) or not files:
        return None
    payload_files: dict[str, str] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not path.strip():
            return None
        if not isinstance(content, str) or not content.strip():
            return None
        payload_files[path.strip()] = content
    note = response.get("note", "")
    return SpecialistProposal(
        provider_id=provider_id,
        capability=task.capability,
        payload={
            "paths": sorted(payload_files),
            "files": payload_files,
            "note": str(note)[:MAX_IDENTIFIER_CHARS * 8],
        },
        model_id=model_id,
        confidence=float(confidence),
    )


class HttpCodeGenerationProvider:
    """A bounded ``code.generate`` specialist over an INJECTED transport.

    Configured at the boundary (provider id, model id, transport, availability).
    The adapter itself is inert: with no transport, or when marked unavailable,
    ``propose`` returns ``None`` and Atlas continues on its deterministic path.
    """

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        provider_id: str = "http.code",
        model_id: str = "",
        available: bool = True,
        confidence: float = 0.0,
    ) -> None:
        if not str(provider_id).strip():
            raise ValueError("provider_id must be non-empty")
        self._transport = transport
        self._provider_id = str(provider_id).strip()
        self._model_id = str(model_id)
        self._available = bool(available)
        self._confidence = float(confidence)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def available(self) -> bool:
        return self._available and callable(self._transport)

    def capabilities(self) -> frozenset[str]:
        return frozenset({CODE_GENERATE})

    def propose(self, task: BoundedSpecialistTask) -> SpecialistProposal | None:
        """Return an untrusted proposal, or ``None`` (fail-closed).

        Refuses a task outside the declared capability, an unavailable provider
        and a raising transport. The transport receives ONLY the bounded
        request; nothing is written or executed by this adapter.
        """
        if task.capability != CODE_GENERATE:
            return None
        if not self.available:
            return None
        try:
            response = self._transport(build_code_generation_request(task))
        except Exception:  # noqa: BLE001 — any transport failure falls back
            return None
        return parse_code_generation_response(
            response,
            task,
            provider_id=self._provider_id,
            model_id=self._model_id,
            confidence=self._confidence,
        )


__all__ = [
    "HttpCodeGenerationProvider",
    "ProviderUnavailable",
    "Transport",
    "build_code_generation_request",
    "parse_code_generation_response",
]
