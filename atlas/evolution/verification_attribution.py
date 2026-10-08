"""Atlas Evolution — verification attribution (Command 4).

Deterministic classification of a bounded verification result against its
PRE-CHANGE (baseline) status, so Atlas can tell an **ATTRIBUTABLE regression**
(the change broke a previously-passing targeted test) from a **PRE-EXISTING**
failure (the test already failed without the change).

This is the smallest Atlas-native mechanism that makes failure attribution
precise: one bounded pre-change probe per iteration, standard library only, and
no dependency, authority, governance or execution change. It adapts the CONCEPT
(not the code) of established transition/differential test-status practice
(SWE-bench FAIL_TO_PASS / PASS_TO_PASS, test-impact analysis, "test before and
after a patch") — a pattern, not a library.

Pure, deterministic, no I/O, no model, no side effects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

#: Key under which a development outcome carries its pre-change baseline status.
BASELINE_METADATA_KEY: str = "verification_baseline"


class VerificationTransition(str, Enum):
    """The bounded pre-change -> post-change verification transition."""

    #: The targeted test passed BEFORE the change and fails AFTER it.
    REGRESSION = "pass_to_fail"
    #: The targeted test failed BEFORE the change and passes AFTER it.
    FIXED = "fail_to_pass"
    #: The targeted test passes both before and after (no verification signal).
    STILL_PASSING = "pass_to_pass"
    #: The targeted test fails both before and after (pre-existing failure).
    ALREADY_FAILING = "fail_to_fail"
    #: The baseline was not established (no probe) or the status is unknown.
    UNKNOWN = "unknown"


def classify_transition(
    baseline_passed: Any, after_passed: Any
) -> VerificationTransition:
    """Classify a pre-change -> post-change verification transition (pure).

    Returns :data:`VerificationTransition.UNKNOWN` whenever either status is not
    a real boolean, so unknown evidence never asserts attributability.
    """
    if not isinstance(baseline_passed, bool) or not isinstance(after_passed, bool):
        return VerificationTransition.UNKNOWN
    if baseline_passed and after_passed:
        return VerificationTransition.STILL_PASSING
    if baseline_passed and not after_passed:
        return VerificationTransition.REGRESSION
    if not baseline_passed and after_passed:
        return VerificationTransition.FIXED
    return VerificationTransition.ALREADY_FAILING


def baseline_of(outcome: Any) -> bool | None:
    """The recorded pre-change baseline status for ``outcome`` (or ``None``)."""
    metadata = getattr(outcome, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(BASELINE_METADATA_KEY)
    return value if isinstance(value, bool) else None


def transition_of(outcome: Any) -> VerificationTransition:
    """The verification transition for a development ``outcome`` (pure)."""
    return classify_transition(
        baseline_of(outcome), bool(getattr(outcome, "verification_passed", False))
    )


def is_attributable(transition: VerificationTransition) -> bool:
    """True when the CHANGE caused the verification failure."""
    return transition is VerificationTransition.REGRESSION


def is_recoverable(transition: VerificationTransition) -> bool:
    """True when a bounded repair may legitimately address the failure.

    Only an attributable regression is recoverable: a pre-existing failure is
    not the change's fault, so repairing it would be misdirected work.
    """
    return transition is VerificationTransition.REGRESSION


_DESCRIPTIONS: dict[VerificationTransition, str] = {
    VerificationTransition.REGRESSION: (
        "the targeted test passed before the change and fails after it "
        "(attributable regression)"
    ),
    VerificationTransition.FIXED: (
        "the targeted test failed before the change and passes after it"
    ),
    VerificationTransition.STILL_PASSING: (
        "the targeted test passes both before and after the change"
    ),
    VerificationTransition.ALREADY_FAILING: (
        "the targeted test already failed WITHOUT the change (pre-existing, "
        "not attributable)"
    ),
    VerificationTransition.UNKNOWN: (
        "no pre-change baseline was established, so attributability is unknown"
    ),
}


def describe(transition: VerificationTransition) -> str:
    """A bounded human-readable description of ``transition``."""
    return _DESCRIPTIONS.get(transition, _DESCRIPTIONS[VerificationTransition.UNKNOWN])


__all__ = [
    "BASELINE_METADATA_KEY",
    "VerificationTransition",
    "baseline_of",
    "classify_transition",
    "describe",
    "is_attributable",
    "is_recoverable",
    "transition_of",
]
