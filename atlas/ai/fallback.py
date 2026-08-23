"""
Atlas AI Fallback Executor

A small, dependency-injected executor that optionally retries a non-streaming
chat attempt against an eligible fallback candidate, and additionally applies
the streaming fallback policy:

  - Before the first stream token: a fallback-eligible provider failure may
    move to the next eligible candidate (same capability guard and attempt
    cap as chat).
  - After the first token: the provider/model is NEVER switched; a subsequent
    failure raises :class:`StreamInterruptedError` (audited, no retry).
  - Cancellation (GeneratorExit / caller abandoning the stream) is never
    converted into a fallback or retry.

Fallback is OFF unless the caller explicitly enables it via
``RoutingRequest.allow_fallback``.  The executor never runs by itself; the
AIService only invokes it when the caller opted in.

Guarantees:
    - The primary attempt always happens normally.
    - Fallback is attempted only when:
        * a RoutingDecision exists,
        * the failure is classified as transient / model-unavailable
          (i.e. not FATAL), and
        * the filtered fallback chain contains an eligible candidate.
    - Maximum ``max_attempts`` total attempts (default 3: 1 primary + 2
      fallbacks).  No nested retries.
    - Fatal failures terminate immediately (the original exception is
      re-raised).
    - The raw fallback_chain is never executed blindly: every candidate is
      resolved against the ModelProfileRegistry and dropped when its
      complexity_score is below the original request's complexity.
    - No candidate is attempted twice, and the primary is never re-entered.
    - If every eligible attempt fails, the final/most useful failure is
      surfaced with the list of attempted (provider, model) pairs.
    - A fake success is never returned.
    - Post-first-token stream failure never triggers a provider switch.

This module holds no provider, registry, or service references; all are
injected.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable

from atlas.ai.failure import FailureClass, classify_failure
from atlas.ai.routing.models import RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.utils.logger import Logger

#: The ChatCall signature: ``fb(provider_name, model_name) -> response``.
ChatCall = Callable[[str, str], Any]

#: The StreamCall signature:
#: ``fb(provider_name, model_name) -> Iterator[str]``.
StreamCall = Callable[[str, str], Any]

#: AuditCallback consumes a flat dict record per fallback event.  The record
#: never contains secrets, prompts, or response bodies.
AuditCallback = Callable[[dict], Any]


@dataclass(frozen=True, slots=True)
class FallbackResult:
    """Outcome of a fallback-executed attempt sequence.

    Attributes:
        response: On success, the provider ``AIResponse`` (or any non-
            exception return value).  None when every eligible attempt failed.
        attempted: Ordered list of ``(provider_name, model_name)`` pairs that
            were actually invoked.
        final_error: The last exception raised, or None on success.
        used_fallback: True when the response came from a fallback candidate
            rather than the primary provider/model.
    """

    response: Any = None
    attempted: list[tuple[str, str]] = field(default_factory=list)
    final_error: BaseException | None = None
    used_fallback: bool = False


class FallbackExecutor:
    """Policy-controlled fallback executor for non-streaming chat.

    Dependencies (constructor-injected):
        - profile_registry: Optional ``ModelProfileRegistry`` used for the
            capability guard. When None, capability filtering is skipped
            (candidates are only deduplicated and kept in order).
        - max_attempts: Total number of provider attempts per request,
            including the primary. Default 3 (1 primary + 2 fallbacks).
        - audit_callback: Optional ``Callable[[dict], Any]`` receiving a flat
            audit record per fallback event.  When None, no events are
            emitted (D1 preserve-by-default behavior).
        - provider_available: Optional ``Callable[[str], bool]`` deciding
            whether a provider is available to receive fallback attempts.
            When provided, candidates whose provider is not available are
            dropped before execution.  This is fed from the authoritative
            ``AIProviderRegistry`` (real provider availability), and when
            None the availability guard is disabled.
    """

    def __init__(
        self,
        profile_registry: ModelProfileRegistry | None = None,
        max_attempts: int = 3,
        audit_callback: AuditCallback | None = None,
        provider_available: Callable[[str], bool] | None = None,
    ) -> None:
        self._profile_registry = profile_registry
        self._max_attempts = max(1, int(max_attempts))
        self._audit_callback = audit_callback
        self._provider_available = provider_available

    @property
    def max_attempts(self) -> int:
        """Return the configured total attempt limit."""
        return self._max_attempts

    @property
    def audit_callback(self) -> AuditCallback | None:
        """Return the injected audit callback, or None."""
        return self._audit_callback

    @property
    def provider_available(self) -> Callable[[str], bool] | None:
        """Return the injected provider-availability guard, or None."""
        return self._provider_available

    @property
    def max_attempts(self) -> int:
        """Return the configured total attempt limit."""
        return self._max_attempts

    @property
    def audit_callback(self) -> AuditCallback | None:
        """Return the injected audit callback, or None."""
        return self._audit_callback

    def _audit(self, record: dict) -> None:
        """Emit a bounded audit record when a callback is injected."""
        if self._audit_callback is None:
            return
        try:
            self._audit_callback(record)
        except Exception:  # noqa: BLE001 - audit must never break execution
            return

    def _request_id(self, request: RoutingRequest) -> str | None:
        """Return an existing request_id when present, else a generated one.

        Prefers a caller-supplied ``metadata["request_id"]`` when available.
        Falls back to a fresh UUID only when auditing is enabled, keeping the
        UUID generation a small, isolated field.
        """
        supplied = request.metadata.get("request_id")
        if isinstance(supplied, str) and supplied:
            return supplied
        if self._audit_callback is None:
            return None
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        request: RoutingRequest,
        decision: RoutingDecision,
        call: ChatCall,
    ) -> FallbackResult:
        """Attempt the primary chat call and eligible fallbacks.

        Args:
            request: The routing request that produced ``decision``.
            decision: The routing decision whose fallback_chain is consulted.
            call: ``call(provider_name, model_name) -> response``. May raise.

        Returns:
            A :class:`FallbackResult`.  On success ``final_error`` is None
            and ``response`` is the provider return value.  On total failure
            ``response`` is None and ``final_error`` carries the last error;
            the primary exception is re-raised for FATAL failures.
        """

        if request is None or decision is None:
            raise ValueError("request and decision are required")

        request_id = self._request_id(request)

        attempted: list[tuple[str, str]] = []
        last_error: BaseException | None = None

        primary = (decision.provider_name, decision.model_name)
        attempted.append(primary)

        # --- 1. Primary attempt (always runs) --------------------------
        try:
            result = call(primary[0], primary[1])
        except BaseException as exc:  # noqa: BLE001 - classifier handles it
            last_error = exc
            classification = classify_failure(exc)
            self._audit_attempt(
                request_id=request_id,
                attempt=len(attempted),
                provider=primary[0],
                model=primary[1],
                outcome="failure",
                classification=classification,
                error=exc,
            )
            # Fatal or non-eligible failures terminate immediately.
            if classification.failure_class == FailureClass.FATAL:
                raise exc
        else:
            self._audit_attempt(
                request_id=request_id,
                attempt=len(attempted),
                provider=primary[0],
                model=primary[1],
                outcome="success",
                classification=None,
                error=None,
            )
            return FallbackResult(
                response=result,
                attempted=attempted,
                used_fallback=False,
            )

        # --- 2. Eligible fallback candidates --------------------------
        chain = self._filtered_chain(request, decision, request_id=request_id)

        for provider_name, model_name in chain:
            if len(attempted) >= self._max_attempts:
                break

            candidate = (provider_name, model_name)
            if candidate in attempted:
                continue
            attempted.append(candidate)

            try:
                result = call(provider_name, model_name)
            except BaseException as exc:  # noqa: BLE001
                last_error = exc
                classification = classify_failure(exc)
                self._audit_attempt(
                    request_id=request_id,
                    attempt=len(attempted),
                    provider=candidate[0],
                    model=candidate[1],
                    outcome="failure",
                    classification=classification,
                    error=exc,
                )
                # A fatal failure on a fallback terminates the whole
                # sequence immediately.
                if classification.failure_class == FailureClass.FATAL:
                    raise exc
                continue

            self._audit_attempt(
                request_id=request_id,
                attempt=len(attempted),
                provider=candidate[0],
                model=candidate[1],
                outcome="success",
                classification=None,
                error=None,
            )
            return FallbackResult(
                response=result,
                attempted=attempted,
                used_fallback=True,
            )

        # --- 3. Exhausted ---------------------------------------------
        self._audit_exhausted(
            request_id=request_id,
            attempted=attempted,
            error=last_error,
        )
        raise _exhaustion_error(last_error, attempted)

    def execute_stream(
        self,
        request: RoutingRequest,
        decision: RoutingDecision,
        stream_call: StreamCall,
    ) -> Iterator[str]:
        """Attempt a streamed chat through eligible fallbacks (pre-token only).

        Streaming fallback policy (Phase D design):
          - Before the first chunk: a fallback-eligible failure may move to
            the next capability-compatible candidate, subject to the
            ``max_attempts`` cap.
          - Fatal failures stop immediately (original exception re-raised).
          - After the first chunk: providers/models are NEVER switched.  A
            later failure raises :class:`StreamInterruptedError` carrying the
            provider/model and underlying error, audited, no retry.
          - Cancellation (GeneratorExit from an abandoning caller) is never
            converted into a fallback.

        Args:
            request: The routing request that produced ``decision``.
            decision: The routing decision consulted for fallback candidates.
            stream_call: ``stream_call(provider_name, model_name)`` returning
                an iterator of text chunks.  May raise.

        Returns:
            An iterator of text chunks.  It may raise
            :class:`StreamInterruptedError` after the first chunk.
        """

        if request is None or decision is None:
            raise ValueError("request and decision are required")

        request_id = self._request_id(request)

        # Ordered candidate list: primary first, then the filtered chain,
        # bounded by the configured attempt cap.
        candidates: list[tuple[str, str]] = [
            (decision.provider_name, decision.model_name)
        ]
        candidates.extend(self._filtered_chain(request, decision, request_id=request_id))
        candidates = candidates[: self._max_attempts]

        last_error: BaseException | None = None

        for attempt_index, (provider_name, model_name) in enumerate(
            candidates,
            start=1,
        ):
            generator = stream_call(provider_name, model_name)

            # --- Preflight: fetch the first chunk ----------------------
            try:
                first_chunk = next(generator)
            except StopIteration:
                # A provider that returns an empty stream: treat as a clean,
                # empty success (no fallback, no synthetic content).
                self._audit_attempt(
                    request_id=request_id,
                    attempt=attempt_index,
                    provider=provider_name,
                    model=model_name,
                    outcome="success",
                    classification=None,
                    error=None,
                    mode="stream",
                )
                return iter(())
            except GeneratorExit:
                # Caller abandoned before the first token: never fall back.
                raise
            except BaseException as exc:  # noqa: BLE001 - classifier handles it
                last_error = exc
                classification = classify_failure(exc)
                self._audit_attempt(
                    request_id=request_id,
                    attempt=attempt_index,
                    provider=provider_name,
                    model=model_name,
                    outcome="failure",
                    classification=classification,
                    error=exc,
                    mode="stream",
                )
                if classification.failure_class == FailureClass.FATAL:
                    raise
                # Fallback-eligible pre-token failure: continue to the next
                # candidate.
                continue

            # First chunk obtained: audit success and stream the remainder.
            self._audit_attempt(
                request_id=request_id,
                attempt=attempt_index,
                provider=provider_name,
                model=model_name,
                outcome="success",
                classification=None,
                error=None,
                mode="stream",
            )
            return self._stream_continuation(
                generator,
                first_chunk,
                provider_name=provider_name,
                model_name=model_name,
                request_id=request_id,
                attempt=attempt_index,
            )

        # --- Exhausted before any chunk was produced --------------------
        self._audit_exhausted(
            request_id=request_id,
            attempted=candidates,
            error=last_error,
        )
        raise _exhaustion_error(last_error, candidates)

    # ------------------------------------------------------------------
    # Capability guard
    # ------------------------------------------------------------------

    def _filtered_chain(
        self,
        request: RoutingRequest,
        decision: RoutingDecision,
        request_id: str | None = None,
    ) -> list[tuple[str, str]]:
        """Filter the decision's fallback_chain without reordering.

        Drops:
            - the primary (provider, model) itself,
            - any duplicate (provider, model),
            - any candidate whose provider is not available (when a
              provider_available guard is injected),
            - any candidate whose profile is below the request's complexity,
            - any candidate not resolvable via the registry.

        The resulting list preserves the original chain ordering.
        """

        primary: tuple[str, str] = (decision.provider_name, decision.model_name)
        seen: set[tuple[str, str]] = set()
        filtered: list[tuple[str, str]] = []

        for provider_name, model_name in decision.fallback_chain:
            if provider_name is None or model_name is None:
                self._audit_skipped(
                    request_id=request_id,
                    provider=str(provider_name),
                    model=str(model_name),
                    reason="missing_names",
                )
                continue
            key = (provider_name, model_name)
            if key == primary:
                self._audit_skipped(
                    request_id=request_id,
                    provider=provider_name,
                    model=model_name,
                    reason="is_primary",
                )
                continue
            if key in seen:
                self._audit_skipped(
                    request_id=request_id,
                    provider=provider_name,
                    model=model_name,
                    reason="duplicate",
                )
                continue
            if (
                self._provider_available is not None
                and not self._provider_available(provider_name)
            ):
                self._audit_skipped(
                    request_id=request_id,
                    provider=provider_name,
                    model=model_name,
                    reason="provider_unavailable",
                )
                continue
            if not self._capability_ok(request, provider_name, model_name):
                self._audit_skipped(
                    request_id=request_id,
                    provider=provider_name,
                    model=model_name,
                    reason="capability_filtered",
                )
                continue
            seen.add(key)
            filtered.append(key)

        return filtered

    def _capability_ok(
        self,
        request: RoutingRequest,
        provider_name: str,
        model_name: str,
    ) -> bool:
        """True when the candidate profile meets the request's complexity."""

        if self._profile_registry is None:
            return True

        profile = self._profile_registry.get(provider_name, model_name)
        if profile is None:
            return False
        return profile.complexity_score >= request.complexity

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------

    def _audit_attempt(
        self,
        request_id: str | None,
        attempt: int,
        provider: str,
        model: str,
        outcome: str,
        classification,
        error: BaseException | None,
        mode: str | None = None,
    ) -> None:
        """Emit a bounded attempt audit record (never secrets/prompts)."""
        record: dict = {
            "event": "ai.routing.fallback.attempt",
            "request_id": request_id,
            "attempt": attempt,
            "provider": provider,
            "model": model,
            "outcome": outcome,
        }
        if mode is not None:
            record["mode"] = mode
        if classification is not None:
            record["failure_class"] = classification.failure_class.value
            record["failure_reason"] = classification.reason
            if classification.status_code is not None:
                record["status_code"] = classification.status_code
        if error is not None:
            record["exception_type"] = type(error).__name__
            record["error"] = str(error)[:300]
        self._audit(record)

    def _audit_skipped(
        self,
        request_id: str | None,
        provider: str,
        model: str,
        reason: str,
    ) -> None:
        """Emit a skipped-candidate audit record."""
        self._audit(
            {
                "event": "ai.routing.fallback.skipped",
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "reason": reason,
            }
        )

    def _audit_exhausted(
        self,
        request_id: str | None,
        attempted: list[tuple[str, str]],
        error: BaseException | None,
    ) -> None:
        """Emit an exhaustion audit record with the attempted pairs."""
        record: dict = {
            "event": "ai.routing.fallback.exhausted",
            "request_id": request_id,
            "attempted": [list(pair) for pair in attempted],
        }
        if error is not None:
            record["exception_type"] = type(error).__name__
            record["error"] = str(error)[:300]
        self._audit(record)

    def _audit_interrupted(
        self,
        request_id: str | None,
        provider: str,
        model: str,
        attempt: int,
        error: BaseException,
    ) -> None:
        """Emit a post-first-token stream-interruption audit record."""
        record: dict = {
            "event": "ai.routing.fallback.interrupted",
            "request_id": request_id,
            "attempt": attempt,
            "provider": provider,
            "model": model,
            "outcome": "interrupted",
            "exception_type": type(error).__name__,
            "error": str(error)[:300],
        }
        self._audit(record)

    # ------------------------------------------------------------------
    # Streaming continuation (post-first-token)
    # ------------------------------------------------------------------

    def _stream_continuation(
        self,
        generator,
        first_chunk: str,
        provider_name: str,
        model_name: str,
        request_id: str | None,
        attempt: int,
    ) -> Iterator[str]:
        """Yield the first chunk then stream the remainder of ``generator``.

        After the first token, the provider/model is never switched.  Any
        later failure is audited and surfaced as :class:`StreamInterruptedError`.
        Cancellation is propagated (never converted into a fallback).
        """

        def _continue() -> Iterator[str]:
            try:
                yield first_chunk
                while True:
                    try:
                        chunk = next(generator)
                    except StopIteration:
                        generator.close()
                        return
                    except GeneratorExit:
                        generator.close()
                        raise
                    except BaseException as exc:  # noqa: BLE001
                        generator.close()
                        self._audit_interrupted(
                            request_id=request_id,
                            provider=provider_name,
                            model=model_name,
                            attempt=attempt,
                            error=exc,
                        )
                        raise StreamInterruptedError(
                            provider=provider_name,
                            model=model_name,
                            message=(
                                f"Stream from {provider_name}/{model_name} was "
                                f"interrupted after first token: "
                                f"{type(exc).__name__}: {exc}"
                            ),
                            underlying=exc,
                        ) from exc
                    yield chunk
            except GeneratorExit:
                generator.close()
                raise

        return _continue()


def _exhaustion_error(
    last_error: BaseException | None,
    attempted: list[tuple[str, str]],
) -> BaseException:
    """Build the exception to surface when every eligible attempt failed.

    Attaches the attempted ``(provider, model)`` list to the most useful
    failure so the caller can identify which pairs were tried.  Falls back
    to a :class:`FallbackExhaustedError` wrapper only when the underlying
    exception cannot carry the attribute.
    """

    if last_error is None:
        return FallbackExhaustedError(
            "All fallback attempts failed with no recorded error.",
            attempted=attempted,
        )

    if hasattr(last_error, "atlas_attempted"):
        return last_error
    try:
        setattr(last_error, "atlas_attempted", list(attempted))
        return last_error
    except Exception:  # noqa: BLE001 - never mask the underlying error
        return FallbackExhaustedError(
            f"Fallback exhausted: {last_error}",
            attempted=attempted,
            final_error=last_error,
        )


class FallbackExhaustedError(Exception):
    """Raised when every eligible fallback candidate failed.

    Attributes:
        attempted: The ordered ``(provider, model)`` pairs attempted.
        final_error: The last exception seen, or None.
    """

    def __init__(
        self,
        message: str,
        attempted: list[tuple[str, str]] | None = None,
        final_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.attempted: list[tuple[str, str]] = attempted or []
        self.final_error = final_error


class StreamInterruptedError(Exception):
    """Raised when a stream fails AFTER having emitted at least one chunk.

    Providers are never switched after the first token.  This error carries
    the provider/model that was streaming and the underlying failure so the
    caller can identify exactly what happened.

    Attributes:
        provider: The provider whose stream was interrupted.
        model: The model whose stream was interrupted.
        underlying: The original exception that interrupted the stream.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        message: str,
        underlying: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.underlying = underlying


def format_fallback_audit(record: dict) -> str:
    """Format a fallback audit record as a single bounded log line.

    Never contains API keys, authorization headers, prompts, or response
    bodies.  Uses the stable ``ai.routing.fallback`` prefix.
    """

    parts = ["ai.routing.fallback"]
    event = record.get("event", "attempt")
    parts.append(f"event={event}")

    request_id = record.get("request_id")
    if request_id:
        parts.append(f"request_id={request_id}")

    attempt = record.get("attempt")
    if attempt is not None:
        parts.append(f"attempt={attempt}")

    mode = record.get("mode")
    if mode:
        parts.append(f"mode={mode}")

    provider = record.get("provider")
    if provider:
        parts.append(f"provider={provider}")

    model = record.get("model")
    if model:
        parts.append(f"model={model}")

    outcome = record.get("outcome")
    if outcome:
        parts.append(f"outcome={outcome}")

    failure_class = record.get("failure_class")
    if failure_class:
        parts.append(f"failure_class={failure_class}")

    failure_reason = record.get("failure_reason")
    if failure_reason:
        parts.append(f"failure_reason={failure_reason}")

    status_code = record.get("status_code")
    if status_code is not None:
        parts.append(f"status_code={status_code}")

    reason = record.get("reason")
    if reason:
        parts.append(f"reason={reason}")

    exception_type = record.get("exception_type")
    if exception_type:
        parts.append(f"exception_type={exception_type}")

    error = record.get("error")
    if error:
        parts.append(f"error={error}")

    attempted = record.get("attempted")
    if attempted:
        parts.append(f"attempted={attempted}")

    return " | ".join(parts)


def make_fallback_audit_callback() -> AuditCallback:
    """Return a Logger-backed audit callback for production fallback events.

    Uses the existing ``atlas.utils.logger.Logger`` infrastructure.  Success
    and skipped-candidate events are logged at INFO; failures and exhaustion
    at WARNING.  The callback never raises.
    """

    def _audit(record: dict) -> None:
        line = format_fallback_audit(record)
        outcome = record.get("outcome")
        event = record.get("event")
        if (
            outcome == "failure"
            or event == "ai.routing.fallback.exhausted"
            or event == "ai.routing.fallback.interrupted"
        ):
            Logger.warning(line)
        else:
            Logger.info(line)

    return _audit