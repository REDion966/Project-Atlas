"""Atlas CLI — Promotion Review Visibility (Stage H operator surface).

Presentation-only command over the EXISTING Stage H kernel bridge
(``Atlas.pending_promotion_reviews()``). Read-only: it surfaces the
prioritized PENDING_REVIEW promotion queue so an operator can see what has
been assessed and is awaiting human promotion.

Hard boundaries:
  - No approve, reject, promote, execute, or schedule.
  - No governance mutation; the kernel bridge itself never mutates anything.
  - Never imports evolution autonomy, the gateway, or the dispatcher.
"""

from __future__ import annotations

from typing import Any


def _score(value: Any) -> str:
    """Render a bounded decision-quality score for human display."""
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}"


def cmd_promotion_pending(atlas: Any, args: Any) -> str:
    """List PENDING_REVIEW promotion requests, highest priority first.

    CLI: atlas promotion pending

    Delegates to the kernel-owned ``Atlas.pending_promotion_reviews()``
    read-only view. Never approves, rejects, promotes, or executes anything.
    """
    pending = atlas.pending_promotion_reviews()
    if not pending:
        return "No promotion reviews pending."

    lines = [f"{len(pending)} promotion review(s) pending:\n"]
    for item in pending:
        evidence = "complete" if item.get("evidence_complete") else "incomplete"
        lines.append(
            f"  [{item.get('request_id', '')}] "
            f"{item.get('proposal_id', '')} "
            f"risk={item.get('risk_level', '')} "
            f"recommendation={item.get('recommendation', '')} "
            f"score={_score(item.get('final_priority_score'))} "
            f"evidence={evidence} "
            f"files={item.get('manifest_file_count', 0)}"
        )
    return "\n".join(lines)
