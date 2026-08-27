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


def cmd_promotion_show(atlas: Any, args: Any) -> str:
    """Show full detail of ONE promotion review (read-only).

    CLI: atlas promotion show <request_id>

    Delegates to the kernel-owned ``Atlas.promotion_review_details()``
    read-only view over the existing promotion-review state. Never
    approves, rejects, promotes, or executes anything.
    """
    request_id = getattr(args, "request_id", "")
    if not request_id:
        return "error: promotion show requires a request_id"

    detail = atlas.promotion_review_details(request_id)
    if detail is None:
        return f"Promotion request '{request_id}' not found."

    evidence = "complete" if detail.get("evidence_complete") else "incomplete"
    lines = [
        f"Promotion request: {detail.get('request_id', '')}",
        f"  proposal_id:       {detail.get('proposal_id', '') or '-'}",
        f"  status:            {detail.get('status', '') or '-'}",
        f"  risk_level:        {detail.get('risk_level', '') or '-'}",
        f"  recommendation:    {detail.get('recommendation', '') or '-'}",
        f"  created_at:        {detail.get('created_at', '') or '-'}",
        f"  decided_at:        {detail.get('decided_at', '') or '-'}",
        f"  decision_comment:  {detail.get('decision_comment', '') or '-'}",
        f"  evidence:          {evidence} "
        f"({detail.get('manifest_file_count', 0)} file(s))",
        f"  verification:      {detail.get('verification_status', '') or '-'}",
        f"  test_summary:      {detail.get('test_summary', '') or '-'}",
    ]
    changed_files = detail.get("changed_files") or []
    if changed_files:
        lines.append("  changed_files:     " + ", ".join(changed_files))
    manifest = detail.get("change_manifest") or {}
    manifest_files = manifest.get("files") or []
    if manifest_files:
        lines.append("  change_manifest:")
        for entry in manifest_files:
            path = entry.get("path", "")
            size = entry.get("size", "")
            excerpt = entry.get("excerpt", "")
            lines.append(f"    - {path} ({size} bytes)")
            if excerpt:
                lines.append(f"        {excerpt}")
        if manifest.get("truncated"):
            lines.append("    (manifest truncated)")
    return "\n".join(lines)
