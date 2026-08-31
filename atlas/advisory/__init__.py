"""Atlas Advisory — Proactive Advisory (P5).

Bounded, advisory-only user-facing surface that composes the existing
post-core F1/F10/F11 signals and the B3.x/P4 seams into one JSON-safe,
principal-scoped report. Never autonomous; never invokes a tool,
capability, orchestration, development, governance, approval, or
promotion boundary directly. The suggested actions are bounded hints
that name the EXISTING governed kernel/CLI path.
"""

from atlas.advisory.models import (
    AdvisoryItem,
    AdvisoryReport,
    AdvisorySeverity,
    AdvisorySource,
)
from atlas.advisory.advisor import ProactiveAdvisor

__all__ = [
    "AdvisoryItem",
    "AdvisoryReport",
    "AdvisorySeverity",
    "AdvisorySource",
    "ProactiveAdvisor",
]
