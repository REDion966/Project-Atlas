"""Atlas semantic similarity — an OPTIONAL specialist embedding seam.

Why this exists
---------------
Atlas has NO semantic similarity mechanism anywhere: its repository ranking is
Okapi BM25 over identifier tokens, its reference resolution is lexical, and its
own source repeatedly asserts the absence of embeddings. That is a real,
documented capability gap — a natural-language request that shares no token with
any module name simply cannot be matched to it.

This module closes that gap the Atlas way: a small, local, replaceable
specialist is wrapped behind an Atlas-owned contract and Atlas remains the
authority.

What it is
----------
* an Atlas-owned **request** (:func:`build_embedding_request`) — vendor-neutral
  and bounded;
* an Atlas-owned **result** (:class:`EmbeddingResult` / :class:`EmbeddingVector`)
  — validated, finite, bounded, never a decision;
* an Atlas-owned **adapter** (:class:`SpecialistEmbeddingModel`) over an INJECTED
  transport, plus :class:`NullEmbeddingModel` for the deterministic-first case;
* Atlas-owned **geometry** (:func:`cosine_similarity`).

Authority (non-negotiable)
--------------------------
An embedding is an UNTRUSTED numeric signal. It cannot authorize, approve,
promote, execute, mutate the repository, or introduce or remove a candidate: it
can only contribute a similarity number that a deterministic Atlas policy may
consult. With no specialist configured every call returns ``None`` and callers
continue on their existing deterministic path. Standard library only; no model,
framework or network client is imported here — the transport is injected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

#: Bounds (audit these; never per request).
MAX_TEXTS: int = 32
MAX_TEXT_CHARS: int = 2_000
MIN_VECTOR_DIM: int = 8
MAX_VECTOR_DIM: int = 4_096

#: The vendor-neutral request/response envelope this seam speaks. The transport
#: is a plain ``dict -> dict`` callable, exactly like the existing specialist
#: ``Transport``, so a runtime can be substituted without touching Atlas.
Texts = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One bounded, finite embedding vector."""

    values: tuple[float, ...] = ()

    @property
    def dimension(self) -> int:
        return len(self.values)

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension}


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """The validated, Atlas-owned outcome of one embedding request.

    ``texts`` is kept alongside ``vectors`` so a consumer can attribute a vector
    to its input without trusting an index convention. Nothing here is
    authoritative: it is evidence a deterministic policy may use.
    """

    provider_id: str = ""
    model_id: str = ""
    texts: tuple[str, ...] = ()
    vectors: tuple[EmbeddingVector, ...] = ()
    #: True when the input was clipped to satisfy the bounds.
    truncated: bool = False

    @property
    def dimension(self) -> int:
        return self.vectors[0].dimension if self.vectors else 0

    @property
    def vector_count(self) -> int:
        return len(self.vectors)

    def vector_for(self, index: int) -> EmbeddingVector | None:
        if 0 <= index < len(self.vectors):
            return self.vectors[index]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "text_count": len(self.texts),
            "dimension": self.dimension,
            "truncated": self.truncated,
        }


def bound_texts(texts: Any) -> tuple[tuple[str, ...], bool]:
    """Deterministically bound ``texts`` to the declared limits.

    Returns ``((), False)`` for anything that is not a non-empty sequence of
    non-blank strings — a malformed request is never sent anywhere.
    """
    if isinstance(texts, str) or not isinstance(texts, (list, tuple)):
        return (), False
    out: list[str] = []
    truncated = False
    for item in texts:
        if not isinstance(item, str):
            return (), False
        text = item.strip()
        if not text:
            return (), False
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS]
            truncated = True
        out.append(text)
        if len(out) >= MAX_TEXTS:
            truncated = truncated or len(texts) > MAX_TEXTS
            break
    if not out:
        return (), False
    return tuple(out), truncated


def build_embedding_request(texts: Any) -> dict[str, Any]:
    """The bounded, vendor-neutral body one embedding request may carry."""
    bounded, _truncated = bound_texts(texts)
    return {"texts": list(bounded)}


def parse_embedding_response(
    response: Any,
    *,
    expected_texts: tuple[str, ...],
    provider_id: str = "",
    model_id: str = "",
) -> EmbeddingResult | None:
    """Validate an untrusted transport reply into an Atlas-owned result.

    Fail-closed on EVERY deviation: a non-mapping reply, a missing/oversized/
    non-numeric vector list, a count that does not match the request, a vector
    whose dimension is outside the bounds or is inconsistent with its siblings,
    or any non-finite value. A partially valid reply is never accepted.
    """
    if not isinstance(response, dict):
        return None
    raw = response.get("embeddings")
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    if len(raw) != len(expected_texts):
        return None

    vectors: list[EmbeddingVector] = []
    dimension = 0
    for item in raw:
        if not isinstance(item, (list, tuple)) or not item:
            return None
        values: list[float] = []
        for value in item:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            number = float(value)
            if not math.isfinite(number):
                return None
            values.append(number)
        if not (MIN_VECTOR_DIM <= len(values) <= MAX_VECTOR_DIM):
            return None
        if dimension == 0:
            dimension = len(values)
        elif len(values) != dimension:
            return None
        vectors.append(EmbeddingVector(values=tuple(values)))

    return EmbeddingResult(
        provider_id=str(provider_id),
        model_id=str(model_id),
        texts=tuple(expected_texts),
        vectors=tuple(vectors),
    )


def cosine_similarity(left: Any, right: Any) -> float | None:
    """Cosine similarity of two vectors, or ``None`` when it is not defined.

    ``None`` (never 0.0) is returned for malformed input, a dimension mismatch
    or a zero-magnitude vector, so a caller can distinguish "no signal" from
    "measured as unrelated" — uncertainty is preserved rather than flattened.
    """
    if not isinstance(left, EmbeddingVector) or not isinstance(right, EmbeddingVector):
        return None
    if not left.values or len(left.values) != len(right.values):
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left.values, right.values):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        return None
    score = dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
    if not math.isfinite(score):
        return None
    return max(-1.0, min(1.0, score))


@runtime_checkable
class EmbeddingModel(Protocol):
    """The narrow Atlas-owned specialist interface consumers depend on.

    Any object exposing these members is usable — a different local model, a
    remote specialist, or a future Atlas-native implementation. Consumers must
    treat every method as able to return ``None``.
    """

    @property
    def provider_id(self) -> str:
        ...

    @property
    def model_id(self) -> str:
        ...

    @property
    def available(self) -> bool:
        ...

    def embed(self, texts: Any) -> EmbeddingResult | None:
        ...


class NullEmbeddingModel:
    """The deterministic-first embedding model: it encodes nothing.

    This is what Atlas uses when no specialist is configured, and what a caller
    should use as its default. It exists so that "no specialist" is an explicit,
    testable object rather than an ``if None`` scattered through callers.
    """

    provider_id: str = ""
    model_id: str = ""

    @property
    def available(self) -> bool:
        return False

    def embed(self, texts: Any) -> EmbeddingResult | None:
        return None


class SpecialistEmbeddingModel:
    """A small embedding specialist over an INJECTED bounded transport.

    The transport is a ``dict -> dict`` callable (the SAME shape as the existing
    specialist transport), so the runtime is a configuration choice. This class
    performs no I/O of its own, imports no model, holds no state between calls,
    and NEVER raises: every failure yields ``None`` so the caller continues on
    its deterministic path.
    """

    def __init__(
        self,
        *,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        provider_id: str = "ollama.embeddings",
        model_id: str = "",
        available: bool = True,
    ) -> None:
        self._transport = transport
        self._provider_id = str(provider_id)
        self._model_id = str(model_id)
        self._available = bool(available)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def available(self) -> bool:
        """True only when this specialist is enabled AND has a usable transport."""
        return self._available and callable(self._transport)

    def embed(self, texts: Any) -> EmbeddingResult | None:
        """Encode ``texts`` into validated vectors, or ``None`` (fail-closed)."""
        if not self.available:
            return None
        bounded, _truncated = bound_texts(texts)
        if not bounded:
            return None
        try:
            response = self._transport(build_embedding_request(bounded))
        except Exception:  # noqa: BLE001 — any transport failure is no signal
            return None
        result = parse_embedding_response(
            response,
            expected_texts=bounded,
            provider_id=self._provider_id,
            model_id=self._model_id,
        )
        if result is None:
            return None
        return result

    def similarity(self, left: str, right: str) -> float | None:
        """Bounded convenience: similarity of two texts, or ``None``."""
        result = self.embed([left, right])
        if result is None:
            return None
        first = result.vector_for(0)
        second = result.vector_for(1)
        if first is None or second is None:
            return None
        return cosine_similarity(first, second)


__all__ = [
    "MAX_TEXTS",
    "MAX_TEXT_CHARS",
    "MAX_VECTOR_DIM",
    "MIN_VECTOR_DIM",
    "EmbeddingModel",
    "EmbeddingResult",
    "EmbeddingVector",
    "NullEmbeddingModel",
    "SpecialistEmbeddingModel",
    "bound_texts",
    "build_embedding_request",
    "cosine_similarity",
    "parse_embedding_response",
]
