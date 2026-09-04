"""Atlas CLI - Post-Core operator surface (Operational Maturity track).

Presentation-only commands over the EXISTING post-Core kernel bridges:

    atlas postcore operate   -> F7  Atlas.run_operation_cycle()
    atlas postcore research  -> F8  Atlas.run_information_acquisition()
    atlas postcore develop   -> F9  Atlas.run_development_cycle()
    atlas postcore review    -> F11 Atlas.run_self_management_review()

Hard boundaries:
  - Presentation only. No command authorizes, executes, schedules, applies,
    promotes, or rolls back anything; governance is never consulted here
    because the kernel bridges themselves stop at the correct boundaries.
  - ``develop`` STOPS where the kernel controller stops: PENDING_APPROVAL.
  - Fail-closed: malformed need files, unwired controllers, runtime errors,
    and SAFE_MODE are surfaced clearly and never silently bypassed.
"""

from __future__ import annotations

import json


def _operator_session(atlas):
    """Resolve the authoritative operator session context.

    The Atlas CLI is the operator surface; the kernel establishes an Owner
    SessionContext during ``start()`` (the single-owner CLI flow). This helper
    hands that immutable context to the kernel bridge, which resolves and
    authorizes identity through the EXISTING SessionManager + AuthorityService.
    It never fabricates an identity and never supplies a raw principal id.
    """
    return getattr(atlas, "session_context", None)


def _safe_mode_line(atlas) -> str:
    """Return a SAFE_MODE notice line when boot recovery narrowed autonomy."""
    try:
        if getattr(atlas, "boot_safe_mode", False):
            reason = ""
            report = getattr(atlas, "boot_report", None)
            if report is not None:
                reason = f" ({getattr(report, 'safe_mode_reason', '')})"
            return (
                f"WARNING: SAFE_MODE active{reason} — "
                "autonomous advancement disabled."
            )
    except Exception as exc:  # fail closed on any introspection problem
        return f"WARNING: SAFE_MODE state unavailable: {exc}"
    return ""


def cmd_operate(atlas, args) -> str:
    """F7 — run ONE bounded autonomous-operation cycle."""
    result = atlas.run_operation_cycle()
    lines = [
        "Operation cycle complete.",
        f"  Cycle ID: {result.operation_id}",
        f"  Decision: {result.decision.name}",
        f"  Status: {result.status}",
        f"  Cycles ran: {result.cycles_ran}",
        f"  Consecutive failures: {result.consecutive_failures}",
    ]
    proposal_ids = list(result.proposal_ids)[:10]
    if proposal_ids:
        lines.append(f"  Draft proposals: {', '.join(proposal_ids)}")
    if result.failures:
        failures = "; ".join(
            f"{stage}: {msg}" for stage, msg in result.failures[:5]
        )
        lines.append(f"  Failures: {failures}")
    notice = _safe_mode_line(atlas)
    if notice:
        lines.append(notice)
    return "\n".join(lines)


def cmd_research(atlas, args) -> str:
    """F8 — run ONE bounded information-acquisition invocation."""
    question = (getattr(args, "question", "") or "").strip()
    if not question:
        return "error: research requires --question"
    sources = tuple(
        s.strip() for s in (getattr(args, "sources", None) or []) if s.strip()
    )
    result = atlas.run_information_acquisition(
        question=question,
        sources=sources,
        query_id=getattr(args, "query_id", "") or "",
    )
    lines = [
        "Acquisition complete.",
        f"  Acquisition ID: {result.acquisition_id}",
        f"  Decision: {result.decision}",
        f"  Status: {result.status}",
        f"  Query: {result.question}",
    ]
    if result.report_ids:
        lines.append(f"  Report IDs: {', '.join(result.report_ids)}")
    if result.sources:
        lines.append(f"  Sources: {', '.join(result.sources[:5])}")
    if result.findings:
        findings = result.findings[:400]
        lines.append(f"  Findings: {findings}")
    if result.failures:
        failures = "; ".join(
            f"{stage}: {msg}" for stage, msg in result.failures[:5]
        )
        lines.append(f"  Failures: {failures}")
    return "\n".join(lines)


def _load_need(args):
    """Load and validate a development-need JSON file. Raises ValueError.

    Contract (must match the E5 deterministic supplier / sandbox semantics):

    * ``code_changes`` — optional list of objects, each with a non-empty
      string ``path`` and a string ``content`` holding the LITERAL new file
      body (never instructions describing the change).
    * ``test_files`` — optional object mapping test-module paths
      (``test_*.py``) to string file bodies. These are executed by pytest
      during sandbox verification, so anything pytest will not collect can
      never satisfy verification and is rejected here.

    Raises ``ValueError`` identifying the offending field and expected shape.
    """
    path = getattr(args, "need_file", "") or ""
    if not path:
        raise ValueError("develop requires --need-file")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("need file must contain a JSON object")
    title = str(data.get("title", "")).strip()
    if not title:
        raise ValueError("need file requires a non-empty 'title'")

    metadata: dict = {}

    # --- code_changes: list of {path, content} objects ---------------------
    code_changes = data.get("code_changes", [])
    cleaned_changes: list[dict] = []
    if code_changes:
        if not isinstance(code_changes, list):
            raise ValueError(
                "'code_changes' must be a list of objects, each with "
                "string 'path' and string 'content'"
            )
        for index, item in enumerate(code_changes):
            if not isinstance(item, dict):
                raise ValueError(
                    f"'code_changes[{index}]' must be an object with "
                    "string 'path' and string 'content'"
                )
            entry_path = item.get("path")
            entry_content = item.get("content")
            if not isinstance(entry_path, str) or not entry_path.strip():
                raise ValueError(
                    f"'code_changes[{index}].path' must be a non-empty string"
                )
            if not isinstance(entry_content, str):
                raise ValueError(
                    f"'code_changes[{index}].content' must be a string "
                    "containing the literal new file body (not a "
                    "description of the change)"
                )
            if not entry_content.strip():
                raise ValueError(
                    f"'code_changes[{index}].content' must not be empty"
                )
            cleaned_changes.append(
                {"path": entry_path, "content": entry_content}
            )
        metadata["code_changes"] = cleaned_changes

    # --- test_files: object mapping test paths to pytest-collectable bodies -
    test_files = data.get("test_files", {})
    cleaned_tests: dict[str, str] = {}
    if test_files:
        if not isinstance(test_files, dict):
            raise ValueError(
                "'test_files' must be an object mapping test module paths "
                "(e.g. \"tests/test_x.py\") to string file bodies"
            )
        for tf_path, tf_content in test_files.items():
            if not isinstance(tf_path, str) or not tf_path.strip():
                raise ValueError("'test_files' paths must be non-empty strings")
            module_name = tf_path.replace("\\", "/").rsplit("/", 1)[-1]
            if not (
                module_name.startswith("test_")
                or module_name.endswith("_test.py")
            ):
                raise ValueError(
                    f"'test_files' path '{tf_path}' is not a pytest test "
                    "module (expected 'test_*.py'); put non-test files in "
                    "'code_changes'"
                )
            if not isinstance(tf_content, str) or not tf_content.strip():
                raise ValueError(
                    f"'test_files['{tf_path}']' content must be a non-empty "
                    "string"
                )
            cleaned_tests[tf_path] = tf_content
        metadata["test_files"] = cleaned_tests

    return {
        "title": title,
        "summary": str(data.get("summary", "")),
        "rationale": str(data.get("rationale", "")),
        "expected_benefit": str(data.get("expected_benefit", "")),
        "research_question": str(data.get("research_question", "")),
        "candidate_id": str(data.get("candidate_id", "")),
        "metadata": metadata,
    }


def cmd_develop(atlas, args) -> str:
    """F9 — prepare ONE bounded DRAFT development proposal.

    STOPS at PENDING_APPROVAL. Never approves, authorizes, executes,
    schedules, applies, or promotes anything.
    """
    from atlas.evolution.development_cycle import DevelopmentNeed

    try:
        need_data = _load_need(args)
    except FileNotFoundError as exc:
        return f"error: need file not found: {exc.filename}"
    except json.JSONDecodeError as exc:
        return f"error: malformed need JSON: {exc}"
    except ValueError as exc:
        return f"error: {exc}"

    need = DevelopmentNeed(
        title=need_data["title"],
        summary=need_data["summary"],
        rationale=need_data["rationale"],
        expected_benefit=need_data["expected_benefit"],
        research_question=need_data["research_question"],
        candidate_id=need_data["candidate_id"],
        metadata=need_data["metadata"],
    )
    result = atlas.run_development_cycle(need)

    if not result.ok:
        failures = "; ".join(
            f"{stage}: {msg}" for stage, msg in result.failures[:5]
        )
        return "\n".join([
            "Development preparation FAILED (fail-closed).",
            f"  Cycle ID: {result.cycle_id}",
            f"  Failures: {failures}",
        ])

    lines = [
        "Development proposal prepared.",
        f"  Cycle ID: {result.cycle_id}",
        f"  Proposal ID: {result.proposal_id}",
        f"  Approval Request: {result.approval_request_id}",
        f"  Status: {result.proposal_status}",
        "  STOPPED at the human approval boundary (PENDING_APPROVAL).",
        "  Nothing is approved, executed, or promoted by this command.",
    ]
    if result.researched:
        lines.append(
            "  Research: performed before drafting "
            f"(status={result.research_summary.get('status', '')})"
        )
    lines.append(
        "  Note: Draft content is UNVERIFIED and requires explicit human "
        "approval."
    )
    notice = _safe_mode_line(atlas)
    if notice:
        lines.append(notice)
    return "\n".join(lines)


def cmd_confirm(atlas, args) -> str:
    """Explicit human confirmation of a persisted development proposal."""
    proposal_id = (getattr(args, "proposal_id", "") or "").strip()
    if not proposal_id:
        return "error: confirm requires --proposal-id"
    comment = getattr(args, "comment", "") or ""
    # The operator is the single Owner; the kernel AUTHORIZES the operator's
    # authoritative session through SessionManager + AuthorityService before
    # any status transition.
    session_context = _operator_session(atlas)
    try:
        proposal = atlas.confirm_development_approval(
            session_context, proposal_id, comment=comment
        )
    except RuntimeError as exc:
        return f"error: {exc}"
    return "\n".join([
        f"✓ Proposal '{proposal.proposal_id}' approved by explicit human "
        "confirmation.",
        f"  Status: {proposal.status.name}",
        "  Execute it with: "
        f"atlas postcore execute --proposal-id {proposal.proposal_id}",
    ])


def cmd_execute(atlas, args) -> str:
    """Execute an APPROVED, persisted development proposal.

    Delegates to the kernel bridge, which loads the persisted proposal,
    requires APPROVED state (fail-closed), then runs the EXISTING
    DevelopmentPlanner + SelfDevelopmentLoop inside a disposable
    CodeSandbox. Never approves, authorizes, schedules, or promotes.
    """
    proposal_id = (getattr(args, "proposal_id", "") or "").strip()
    if not proposal_id:
        return "error: execute requires --proposal-id"

    # The operator is the single Owner; the kernel AUTHORIZES the operator's
    # authoritative session through SessionManager + AuthorityService before
    # any execution.
    session_context = _operator_session(atlas)
    try:
        run_result = atlas.run_development_execution(session_context, proposal_id)
    except RuntimeError as exc:
        return f"error: {exc}"

    lines = [
        "Governed development execution complete.",
        f"  Proposal ID: {proposal_id}",
        f"  Run status: {run_result.status.name}",
        f"  Iterations used: {run_result.iterations_used}",
    ]
    if run_result.outcomes:
        last = run_result.outcomes[-1]
        lines.extend([
            f"  Last outcome: {last.outcome.name}",
            f"  Verification passed: {last.verification_passed}",
            "  Changed files (sandbox): "
            + (", ".join(last.changed_files) or "(none)"),
        ])
    if run_result.message:
        lines.append(f"  Message: {run_result.message[:300]}")
    notice = _safe_mode_line(atlas)
    if notice:
        lines.append(notice)
    return "\n".join(lines)


def cmd_review(atlas, args) -> str:
    """F11 — run ONE bounded long-term self-management review."""
    report = atlas.run_self_management_review()
    lines = [
        "Self-management review complete.",
        f"  Review ID: {report.review_id}",
        f"  Status: {report.status}",
        f"  Failure streak: {report.failure_streak}",
        f"  Stale authorizations: {report.stale_authorization_count}",
        "  Degraded components: "
        + (", ".join(report.degraded_components) or "(none)"),
        "  Offline components: "
        + (", ".join(report.offline_components) or "(none)"),
        f"  Availability: {report.availability_status or '(unknown)'}",
    ]
    if report.needs:
        lines.append("  Maintenance needs:")
        for need in report.needs:
            evidence = ", ".join(need.evidence_ids) or "(no ids)"
            lines.append(
                f"    - {need.kind}: {need.summary} [evidence: {evidence}]"
            )
    else:
        lines.append("  Maintenance needs: (none)")
    if report.source_errors:
        errors = "; ".join(
            f"{src}: {msg}" for src, msg in report.source_errors[:5]
        )
        lines.append(f"  Source errors: {errors}")
    return "\n".join(lines)