"""Atlas Autonomy — the integrated autonomous intelligence loop (Step 25).

This package integrates the completed post-L10 capabilities (Steps 12-24) into
ONE governed end-to-end loop. It is orchestration only: every stage delegates to
an EXISTING mechanism, and no stage invents a new authority, source, capability,
implementation or promotion path.
"""

from atlas.autonomy.integrated_loop import (
    INTEGRATED_LOOP_RULE,
    IntegratedIntelligenceLoop,
    IntegratedLoopResult,
    LoopAction,
    LoopSeams,
    LoopStage,
    LoopStatus,
    integrated_intelligence_loop,
)

__all__ = [
    "INTEGRATED_LOOP_RULE",
    "IntegratedIntelligenceLoop",
    "IntegratedLoopResult",
    "LoopAction",
    "LoopSeams",
    "LoopStage",
    "LoopStatus",
    "integrated_intelligence_loop",
]
