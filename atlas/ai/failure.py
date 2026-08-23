"""
Atlas AI Failure Classification

A small, deterministic typed taxonomy used by the fallback executor to decide
whether a provider failure may be retried against an eligible fallback
candidate.

Classification is based on exception type and (where available) the HTTP
status code carried by ``requests.HTTPError``.  It does not rely on fragile
string matching.

Categories:
    FALLBACK_ELIGIBLE
        - HTTP 5xx
        - HTTP 429 (rate limiting)
        - requests.ConnectionError
        - requests.Timeout
        - model unavailable (HTTP 404, or a model-resolution failure carrying
          that semantic)
    FATAL (no fallback)
        - authentication / missing API key
        - HTTP 4xx other than 429
        - malformed JSON / malformed provider response body
        - invalid provider response structure (e.g. KeyError)
        - no active provider / configuration errors
        - programming errors (TypeError / ValueError / AttributeError)
        - cancellation / interruption
        - streaming malformed-line behavior (never a fallback trigger)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import requests


class FailureClass(Enum):
    """The fallback-relevant category of a provider failure."""

    FALLBACK_ELIGIBLE = "fallback_eligible"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """Typed result of classifying a provider exception."""

    failure_class: FailureClass
    # A stable, short machine-readable reason, e.g. "http_5xx",
    # "rate_limited", "connection", "timeout", "model_unavailable".
    reason: str
    # The HTTP status code when known, otherwise None.
    status_code: int | None = None


def classify_failure(exc: BaseException) -> FailureClassification:
    """Classify a provider exception into a fallback decision.

    Args:
        exc: The exception raised by a provider call.

    Returns:
        A :class:`FailureClassification` with a ``FailureClass`` and a
        deterministic reason string.

    The classifier must never raise.  Any unrecognised exception is
    conservatively treated as FATAL (no fallback).
    """

    # --- timeout ---------------------------------------------------------
    if isinstance(exc, requests.Timeout):
        return FailureClassification(
            failure_class=FailureClass.FALLBACK_ELIGIBLE,
            reason="timeout",
        )

    # --- network / connection -------------------------------------------
    if isinstance(exc, requests.ConnectionError):
        return FailureClassification(
            failure_class=FailureClass.FALLBACK_ELIGIBLE,
            reason="connection_error",
        )

    # --- HTTP status ------------------------------------------------------
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None

        if status is not None and 500 <= status < 600:
            return FailureClassification(
                failure_class=FailureClass.FALLBACK_ELIGIBLE,
                reason="http_5xx",
                status_code=status,
            )

        if status == 429:
            return FailureClassification(
                failure_class=FailureClass.FALLBACK_ELIGIBLE,
                reason="rate_limited",
                status_code=status,
            )

        if status == 404:
            # Model (or endpoint) unavailable on the provider.
            return FailureClassification(
                failure_class=FailureClass.FALLBACK_ELIGIBLE,
                reason="model_unavailable",
                status_code=status,
            )

        if status is not None and 400 <= status < 500:
            return FailureClassification(
                failure_class=FailureClass.FATAL,
                reason="http_4xx",
                status_code=status,
            )

        if status is None:
            return FailureClassification(
                failure_class=FailureClass.FATAL,
                reason="http_error_no_status",
            )

    # --- malformed / invalid response -----------------------------------
    if isinstance(exc, (ValueError, KeyError)):
        # ValueError covers json.JSONDecodeError and DataError; KeyError
        # covers an invalid provider response shape.
        return FailureClassification(
            failure_class=FailureClass.FATAL,
            reason="malformed_response",
        )

    # --- programming / configuration errors ------------------------------
    if isinstance(exc, (TypeError, AttributeError)):
        return FailureClassification(
            failure_class=FailureClass.FATAL,
            reason="programming_error",
        )

    # --- no active provider / configuration ------------------------------
    if isinstance(exc, RuntimeError):
        return FailureClassification(
            failure_class=FailureClass.FATAL,
            reason="configuration_error",
        )

    # --- cancellation / interruption -------------------------------------
    if isinstance(exc, (GeneratorExit, KeyboardInterrupt, SystemExit)):
        return FailureClassification(
            failure_class=FailureClass.FATAL,
            reason="cancelled",
        )

    # --- authentication / missing key -------------------------------------
    if isinstance(exc, PermissionError):
        return FailureClassification(
            failure_class=FailureClass.FATAL,
            reason="authentication",
        )

    # Unrecognised exceptions are conservatively fatal.
    return FailureClassification(
        failure_class=FailureClass.FATAL,
        reason="unknown",
    )