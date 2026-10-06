"""Atlas Evolution — bounded development failure classification (STEP 2K).

Turns the EXISTING development/verification evidence into ONE closed failure
kind, so a caller can tell a syntax failure from a test failure, a wrong target
from an unrelated change, and an environment problem from a governance refusal.

It classifies; it does not act. In particular it never authorizes a repair: it
reports whether a bounded repair is even *warranted* for the observed kind, and
the existing development loop still owns any retry, its bound, its verification
and its termination.

Adapted (not imported) from the researched fault-localization /
independent-patch-verification ideas: the useful part for Atlas today is the
DETERMINISTIC TAXONOMY of what actually went wrong, not a localization algorithm.

Pure, deterministic, standard library only. No model, no I/O, no execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Bound on retained evidence text.
MAX_REASON_CHARS: int = 300
MAX_EVIDENCE_ITEMS: int = 8


class FailureKind(str, Enum):
    """The closed taxonomy of development failure kinds."""

    SYNTAX = "syntax_failure"
    IMPORT = "import_failure"
    TEST = "test_failure"
    REGRESSION = "behavioral_regression"
    WRONG_TARGET = "wrong_target"
    INCOMPLETE = "incomplete_change"
    UNRELATED = "unrelated_change"
    ENVIRONMENT = "verification_environment_failure"
    PROVIDER = "provider_failure"
    GOVERNANCE = "governance_failure"
    UNKNOWN = "unknown"


#: Deterministic cue -> kind table, most specific first. Cues are matched
#: case-insensitively against the bounded reason text only.
_CUES: tuple[tuple[FailureKind, tuple[str, ...]], ...] = (
    (FailureKind.GOVERNANCE, (
        "not authorized", "unauthorized", "approval", "owner", "forbidden",
        "permission", "governance", "envelope denied", "refused by policy",
    )),
    (FailureKind.SYNTAX, (
        "syntaxerror", "syntax error", "invalid syntax", "indentationerror",
        "unexpected eof", "cannot parse", "does not parse", "invalid syntax",
    )),
    (FailureKind.IMPORT, (
        "importerror", "modulenotfounderror", "no module named",
        "cannot import", "import error", "unresolved import",
    )),
    (FailureKind.ENVIRONMENT, (
        "no such file", "permission denied", "timed out", "timeout",
        "disk", "oserror", "environment", "pytest not", "interpreter",
        "sandbox unavailable", "workspace unavailable",
    )),
    (FailureKind.PROVIDER, (
        "provider", "model returned", "malformed json", "not json",
        "author_unavailable", "no authoring content",
    )),
    (FailureKind.WRONG_TARGET, (
        "symbol not found", "not found in", "wrong target", "no such symbol",
        "target not resolved", "unresolved target", "was not found",
        "cannot be resolved to",
    )),
    (FailureKind.UNRELATED, (
        "unrelated", "out of scope", "escapes", "path escapes",
        "outside the target",
    )),
    (FailureKind.INCOMPLETE, (
        "incomplete", "missing content", "empty content", "no changes",
        "produced no changes", "nothing supplied",
    )),
    (FailureKind.REGRESSION, (
        "regression", "previously passing", "broke existing",
        "test failure count increased",
    )),
    (FailureKind.TEST, (
        "assertionerror", "failed test", "test failed", "tests failed",
        "assert", "pytest", "verification failed",
    )),
)

#: Kinds for which a BOUNDED repair attempt is plausibly warranted. Everything
#: else must not be retried: a governance refusal or a wrong target is a
#: decision/evidence problem, not a code-authoring problem.
REPAIRABLE_KINDS: frozenset[FailureKind] = frozenset({
    FailureKind.SYNTAX,
    FailureKind.IMPORT,
    FailureKind.TEST,
    FailureKind.REGRESSION,
    FailureKind.INCOMPLETE,
})


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """One bounded, deterministic classification of a development failure."""

    kind: FailureKind = FailureKind.UNKNOWN
    reason: str = ""
    evidence: tuple[str, ...] = ()
    repairable: bool = False
    guidance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "repairable": self.repairable,
            "guidance": self.guidance,
        }


_GUIDANCE: dict[FailureKind, str] = {
    FailureKind.SYNTAX: "the authored change did not parse; re-author it",
    FailureKind.IMPORT: "an import the change relies on does not resolve",
    FailureKind.TEST: "a targeted test failed; inspect the failing assertion",
    FailureKind.REGRESSION: "an existing behaviour changed; the change is not compatibility-preserving",
    FailureKind.WRONG_TARGET: "the change was anchored to the wrong symbol or module",
    FailureKind.INCOMPLETE: "the author produced no usable content",
    FailureKind.UNRELATED: "the change touched something outside the target",
    FailureKind.ENVIRONMENT: "the verification environment failed; not a code defect",
    FailureKind.PROVIDER: "the optional authoring provider did not return usable output",
    FailureKind.GOVERNANCE: "a governance/approval boundary refused the action; not a code defect",
    FailureKind.UNKNOWN: "the failure could not be classified from the available evidence",
}


def classify_failure(
    reason: Any = "",
    *,
    stage: Any = "",
    execution_status: Any = "",
    verification_status: Any = "",
) -> FailureClassification:
    """Classify ONE development failure deterministically (never raises).

    The cues are matched against the bounded reason text plus the optional stage
    and status strings, so the SAME evidence always yields the SAME kind.
    """
    parts = [
        str(reason or ""),
        str(stage or ""),
        str(execution_status or ""),
        str(verification_status or ""),
    ]
    haystack = " | ".join(part for part in parts if part).strip().lower()[:MAX_REASON_CHARS * 4]
    if not haystack:
        return FailureClassification(
            kind=FailureKind.UNKNOWN,
            reason="no failure evidence was supplied",
            guidance=_GUIDANCE[FailureKind.UNKNOWN],
        )

    evidence: list[str] = []
    for kind, cues in _CUES:
        for cue in cues:
            if cue in haystack:
                evidence.append(f"cue:{cue}")
                break
        if evidence:
            return FailureClassification(
                kind=kind,
                reason=str(reason or "")[:MAX_REASON_CHARS],
                evidence=tuple(evidence[:MAX_EVIDENCE_ITEMS]),
                repairable=kind in REPAIRABLE_KINDS,
                guidance=_GUIDANCE[kind],
            )
    return FailureClassification(
        kind=FailureKind.UNKNOWN,
        reason=str(reason or "")[:MAX_REASON_CHARS],
        evidence=("no-known-cue",),
        repairable=False,
        guidance=_GUIDANCE[FailureKind.UNKNOWN],
    )


def classify_outcomes(outcomes: Any) -> tuple[FailureClassification, ...]:
    """Classify each bounded failure of a development run (deterministic order).

    Accepts any iterable of outcome-like objects exposing ``status``/``reason``
    (the EXISTING development outcome shape). Non-failures are skipped, so the
    result contains only genuine failures.
    """
    classified: list[FailureClassification] = []
    for outcome in tuple(outcomes or ())[:MAX_EVIDENCE_ITEMS]:
        status = str(getattr(getattr(outcome, "status", None), "value", "") or "")
        if status.lower() in ("success", "", "skipped"):
            continue
        classified.append(
            classify_failure(
                getattr(outcome, "reason", "") or getattr(outcome, "detail", ""),
                stage=getattr(outcome, "stage", ""),
                execution_status=status,
            )
        )
    return tuple(classified)


__all__ = [
    "FailureClassification",
    "FailureKind",
    "REPAIRABLE_KINDS",
    "classify_failure",
    "classify_outcomes",
]
