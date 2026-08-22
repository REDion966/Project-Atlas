"""Atlas CLI - Autonomy Request Management (Foundation Strengthening Batch 14).

CLI is presentation + human-authorization surface. It is the ONLY production
path that moves a ``PENDING_AUTHORIZATION`` EvolutionRequest to ``AUTHORIZED``
then ``SCHEDULED``. It delegates ALL governance decisions to the existing,
authoritative ``AuthorizationManager`` and persists lifecycle transitions
through the existing ``ScheduleStore``.

Hard boundaries:
  - AutonomyPolicy.enabled stays False; system:autonomy is never used.
  - authorize_autonomously() is NEVER called.
  - No authorization is ever manufactured/synthesized here.
  - Human authorization ALWAYS goes through
    ``AuthorizationManager.request_user_authorization(...)`` with
    ``authorized_by="user:cli"`` and ``mode=EXPLICIT``.
  - The CLI never calls ApplicationEngine / gateway / dispatcher internals;
    a request is only AUTHORIZED and SCHEDULED here - it is never executed.
  - ``ScheduleStore.record_authorization`` is guarded by a caller-side
    eligibility check (PENDING_AUTHORIZATION + no existing authorization)
    because ``record_authorization`` itself does not enforce pending state.
"""

from datetime import datetime
from typing import Any


def _fmt(ts):
    if ts is None:
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _scope_name(scope):
    return getattr(scope, "name", str(scope))


def _level_name(level):
    return getattr(level, "name", str(level))


def _payload_summary(payload):
    if not payload:
        return "(empty)"
    parts = []
    for key in ("operation", "entry_id", "memory_id", "knowledge_key", "key", "domain"):
        if key in payload:
            parts.append(f"{key}={payload[key]}")
    if not parts:
        keys = ", ".join(sorted(str(k) for k in payload.keys()))
        parts = [f"keys=[{keys}]"]
    return "; ".join(parts[:6])


def _validation_line(request):
    validation = request.validation
    if validation is None:
        return "  Validation: (not validated)"
    status = "valid" if validation.valid else "invalid"
    details = ""
    if validation.violations:
        details = f"; violations={len(validation.violations)}"
    elif validation.warnings:
        details = f"; warnings={len(validation.warnings)}"
    return f"  Validation: {status}{details}"


def _risk_line(request):
    risk = request.risk
    if risk is None:
        return "  Risk: (not assessed)"
    line = f"  Risk: {risk.risk_level.name}"
    if risk.score is not None:
        line += f" (score={risk.score:.2f})"
    if getattr(risk, "summary", ""):
        line += f" - {risk.summary}"
    return line


def _authorization_line(request):
    auth = request.authorization
    if auth is None:
        return "  Authorization: (none)"
    line = (
        f"  Authorization: {auth.mode.name} by "
        f"{auth.authorized_by} granted {_fmt(getattr(auth, 'granted_at', None))}"
    )
    if getattr(auth, "expires_at", None):
        line += f" (expires {_fmt(auth.expires_at)})"
    if getattr(auth, "comment", ""):
        line += f" - {auth.comment}"
    return line


def _format_request(request):
    lines = [
        f"Request: {request.request_id}",
        f"  Status: {request.status.name}",
        f"  Source: {request.source}",
        f"  Scope: {_scope_name(request.target_scope)}",
        f"  Intended Level: {_level_name(request.intended_level)}",
        f"  Payload: {_payload_summary(request.change_payload)}",
        f"  Created: {_fmt(getattr(request, 'created_at', None))}",
        f"  Updated: {_fmt(getattr(request, 'updated_at', None))}",
        _validation_line(request),
        _risk_line(request),
        _authorization_line(request),
    ]
    schedule = getattr(request, "schedule", None)
    if schedule is not None:
        lines.append(f"  Scheduled: {_fmt(getattr(schedule, 'scheduled_at', None))}")
    version_target = getattr(request, "version_target", None)
    if version_target is not None:
        lines.append(
            f"  Version Target: {version_target.target_kind} "
            f"{version_target.current_version}->"
            f"{version_target.target_version}"
            f" (anchor {version_target.state_version_at_creation})"
        )
    return "\n".join(lines)


def cmd_requests_pending(schedule_store, args):
    """List requests awaiting human authorization (read-only).

    CLI: atlas evolution pending
    """
    requests = schedule_store.pending_authorization()
    if not requests:
        return "No requests awaiting authorization."
    lines = [f"{len(requests)} request(s) awaiting authorization:\n"]
    for request in sorted(requests, key=lambda r: getattr(r, "created_at", datetime.max)):
        lines.append(
            f"  [{request.request_id}] {_scope_name(request.target_scope)} "
            f"({_level_name(request.intended_level)}) source={request.source} "
            f"payload={_payload_summary(request.change_payload)}"
        )
    return "\n".join(lines)


def cmd_request_show(schedule_store, args):
    """Show full governance context for a request (read-only).

    CLI: atlas evolution show <request_id>
    """
    request_id = getattr(args, "request_id", "")
    if not request_id:
        return "error: evolution show requires a request_id"
    request = schedule_store.get_request(request_id)
    if request is None:
        return f"Request '{request_id}' not found."
    return _format_request(request)


def cmd_request_authorize(schedule_store, args):
    """Authorize a pending request as user:cli and schedule it.

    CLI: atlas evolution authorize <request_id> --comment "..."
    """
    from atlas.evolution.autonomy.authorization_manager import (
        AuthorizationManager,
        AuthorizationRequest,
        AuthorizationRefusal,
    )
    from atlas.evolution.autonomy.models import AuthorizationMode

    request_id = getattr(args, "request_id", "")
    if not request_id:
        return "error: evolution authorize requires a request_id"

    request = schedule_store.get_request(request_id)
    if request is None:
        return f"error: Request '{request_id}' not found."

    # Caller-side eligibility gate BEFORE any mutation.
    status = request.status.name
    if status != "PENDING_AUTHORIZATION":
        return (
            f"error: Request '{request_id}' is not awaiting authorization "
            f"(status={status}). No authorization was recorded."
        )
    if request.authorization is not None:
        return (
            f"error: Request '{request_id}' already has an authorization. "
            f"No re-grant was performed."
        )

    comment = getattr(args, "comment", "")
    manager = AuthorizationManager(policy=schedule_store.policy)
    auth_request = AuthorizationRequest(
        authorized_by="user:cli",
        mode=AuthorizationMode.EXPLICIT,
        comment=comment,
    )

    try:
        result = manager.request_user_authorization(request, auth_request)
    except AuthorizationRefusal as exc:
        return (
            f"error: Authorization refused for '{request_id}': {exc}. "
            "No status change was made."
        )

    if not result.authorized or result.authorization is None:
        reason = result.reason or "authorization refused"
        return (
            f"error: Authorization refused for '{request_id}': {reason}. "
            "No status change was made."
        )

    updated = schedule_store.record_authorization(request_id, result.authorization)
    if updated is None:
        return f"error: Failed to record authorization for '{request_id}'."
    scheduled = schedule_store.schedule_request(request_id)
    if scheduled is None:
        return (
            f"error: Authorization recorded for '{request_id}' but could not "
            "be scheduled (status did not transition)."
        )

    return (
        f"Request '{request_id}' AUTHORIZED by user:cli (EXPLICIT) and SCHEDULED. "
        "Execution will proceed via the governed dispatcher on a later tick."
    )


def cmd_requests_status(schedule_store, args):
    """Report lifecycle status/counts via the existing ScheduleStore.

    CLI: atlas evolution status
    """
    report = schedule_store.status_report()
    lines = [
        "Evolution status:",
        f"  State version: {report.state_version or '(none)'}",
        f"  Hold: {'yes' if report.hold else 'no'}",
        f"  Pending authorizations: {report.pending_authorizations}",
        f"  Scheduled: {len(report.scheduled)}",
        f"  In-flight (APPLIED/PENDING_EFFECTIVE): {len(report.in_flight)}",
        f"  Window quota used: {report.window_quota_used}",
        f"  Policy version: {report.policy_version or '(default)'}",
    ]
    envelope = report.envelope or {}
    lines.append(
        f"  Policy enabled: {envelope.get('enabled', False)}"
        f" (effective level {envelope.get('effective_execution_level', 'ADMINISTRATIVE')})"
    )
    if report.scheduled:
        lines.append(f"  Scheduled IDs: {', '.join(report.scheduled)}")
    if report.in_flight:
        lines.append(f"  In-flight IDs: {', '.join(report.in_flight)}")
    return "\n".join(lines)
