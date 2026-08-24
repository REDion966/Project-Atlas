"""Atlas Post-Core F4 — Adaptation Decision Policy.

Deterministic, injectable policy controlling which F3 lifecycle assessments
become proposal candidates. Conservative by default: F4 never invents a
replacement or a fallback; REPLACE/FALLBACK only proceed when the assessment
already carries ``REPLACEMENT_AVAILABLE`` evidence, and REVIEW only proceeds
when the assessment priority clears a configurable threshold.

Pure config. No infra. No AI. No registry access.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdaptationDecisionPolicy:
    """Deterministic thresholds for the F4 decision engine.

    Attributes:
        review_priority_threshold: Minimum priority for a REVIEW assessment
            to become a candidate (below → deferred).
        deprecate_priority_threshold: Minimum priority for DEPRECATE.
        replace_priority_threshold: Minimum priority for REPLACE.
        fallback_priority_threshold: Minimum priority for FALLBACK.
        require_explicit_replacement: When True, REPLACE/FALLBACK candidates
            are produced only when the assessment includes
            ``REPLACEMENT_AVAILABLE`` evidence (never invented).
        uncertain_actionable: When False, assessments whose only signal is
            uncertainty produce no candidate. Keep default False.
        max_candidates: Hard upper bound on produced candidates (injectable
            cap, default small).
    """

    review_priority_threshold: float = 0.8
    deprecate_priority_threshold: float = 0.8
    replace_priority_threshold: float = 0.8
    fallback_priority_threshold: float = 0.8
    require_explicit_replacement: bool = True
    uncertain_actionable: bool = False
    max_candidates: int = 5

    def __post_init__(self) -> None:
        for name, value in {
            "review_priority_threshold": self.review_priority_threshold,
            "deprecate_priority_threshold": self.deprecate_priority_threshold,
            "replace_priority_threshold": self.replace_priority_threshold,
            "fallback_priority_threshold": self.fallback_priority_threshold,
        }.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be within [0.0, 1.0]")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")