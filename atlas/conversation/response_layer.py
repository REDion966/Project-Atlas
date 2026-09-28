"""Atlas Conversation — deterministic response realization (Step 11).

Turns an ALREADY-ESTABLISHED deterministic outcome into a natural, coherent,
bounded response. This is *presentation only*:

  * it never reasons, plans, retrieves, executes, authorizes or promotes;
  * it never invents a fact, a step, a result, an action or an authority;
  * it is deterministic and model-free (stdlib only);
  * it renders only values that the caller already established.

It exists because the baseline (real Atlas/kernel) showed the step/outcome report
was mechanically assembled: it echoed the whole request back ("Done: <whole
sentence>"), exposed internal step ids ("step-0000") and internal executor
targets ("retrieve" / "synthesize") as if they were results, duplicated the
target as the "output", and always printed internal attribution
("Executed as: owner (owner)"). It did not make clear what each step *was* and
what it actually *produced*, and completed / partial / failed / blocked work was
not presented in one consistent shape.

The contract is a fixed, truthful structure:

    Done. Steps completed: N/M.
    - <What>: <subject>: <state>[ — <result or reason>]

where ``<What>`` is a human label for the step's kind, ``<subject>`` is the
bounded subject the outcome itself recorded, ``<state>`` is the recorded state
(``completed`` / ``failed`` / ``blocked`` / ``skipped``), and the trailing detail
is the outcome's OWN recorded result (or its recorded reason, when it did not
succeed). Nothing is embellished.
"""

from __future__ import annotations

from typing import Any

#: Bounds (a malformed/oversized outcome can never produce unbounded output).
_MAX_STEPS: int = 8
_MAX_LINES: int = 64
_MAX_ERROR_CHARS: int = 400
_MAX_SUBJECT_CHARS: int = 120
_MAX_DETAIL_CHARS: int = 200

#: Human label per step kind (the existing executor kinds).
_STEP_LABELS: dict[str, str] = {
    "investigation": "Investigate",
    "knowledge": "Research",
    "analysis": "Analysis",
    "research_analysis": "Research analysis",
    "evidence_gap_analysis": "Evidence gap analysis",
    "capability": "Capability",
    "tool": "Tool",
    "workspace": "Workspace",
    "research": "Research",
    "goal": "Goal",
}

#: Internal executor targets that are NOT user-facing subjects.
_INTERNAL_TARGETS: frozenset[str] = frozenset(
    {
        "retrieve",
        "synthesize",
        "analyze_gaps",
        "analyse_gaps",
        "conclude",
        "acquire",
        "analyze",
        "analyse",
    }
)

#: Output fields that carry a real RESULT (in priority order). The first
#: non-empty one that is not just an echo of the subject is shown.
_RESULT_KEYS: tuple[str, ...] = (
    "diagnosis",
    "summary",
    "recommended_focus",
    "recommended_reason",
    "conclusion",
    "message",
    "answer",
    "text",
    "result",
    "statement",
)

#: Output fields that carry a bounded COUNT result.
_COUNT_KEYS: tuple[tuple[str, str], ...] = (
    ("component_count", "component(s)"),
    ("finding_count", "finding(s)"),
    ("claim_count", "claim(s)"),
    ("gap_count", "gap(s)"),
)

#: States rendered as a non-success (their recorded reason is shown).
_UNSUCCESSFUL_STATES: frozenset[str] = frozenset({"failed", "blocked", "skipped"})


def _kind_value(kind: Any) -> str:
    return str(getattr(kind, "value", kind) or "").lower()


def _state_value(state: Any) -> str:
    return str(getattr(state, "value", state) or "").lower()


def _bounded(value: Any, limit: int) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _key(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def step_label(kind: Any) -> str:
    """Return the human label for a step kind (never the internal id)."""
    value = _kind_value(kind)
    return _STEP_LABELS.get(value, value.replace("_", " ").title() or "Step")


def _step_subject(step: Any, label: str) -> str:
    """Return the bounded, user-facing subject the step actually recorded."""
    output = getattr(step, "output", None)
    output = output if isinstance(output, dict) else {}
    candidate = ""
    for key in ("question", "objective", "target"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            candidate = value.strip()
            break
    if not candidate:
        candidate = str(getattr(step, "target", "") or "").strip()
    if not candidate or candidate.lower() in _INTERNAL_TARGETS:
        return ""
    # Drop a leading verb that only repeats the label ("Investigate the X").
    head = label.split(" ", 1)[0].lower()
    words = candidate.split(" ", 1)
    if words and words[0].lower() == head and len(words) > 1:
        candidate = words[1].strip()
    return _bounded(candidate, _MAX_SUBJECT_CHARS)


def _step_detail(step: Any, subject: str) -> str:
    """Return the bounded RESULT the step recorded (never an input echo)."""
    output = getattr(step, "output", None)
    output = output if isinstance(output, dict) else {}
    subject_key = _key(subject)
    for key in _RESULT_KEYS:
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if _key(text) != subject_key:
                return _bounded(text, _MAX_DETAIL_CHARS)
    counts = [
        f"{int(output[key])} {word}"
        for key, word in _COUNT_KEYS
        if isinstance(output.get(key), int) and output.get(key) > 0
    ]
    if counts:
        return ", ".join(counts)
    findings = output.get("findings")
    if isinstance(findings, (list, tuple)) and findings:
        return f"{len(findings)} finding(s)"
    return ""


def describe_step(step: Any) -> str:
    """Render one bounded, truthful step line. Never invents a value."""
    if step is None:
        return ""
    label = step_label(getattr(step, "kind", ""))
    subject = _step_subject(step, label)
    state = _state_value(getattr(step, "state", ""))
    line = f"- {label}"
    if subject:
        line += f" ({subject})"
    line += f": {state}"
    if state in _UNSUCCESSFUL_STATES:
        error = _bounded(getattr(step, "error", ""), _MAX_ERROR_CHARS)
        if error:
            line += f" — {error}"
        return line
    detail = _step_detail(step, subject)
    if detail:
        line += f" — {detail}"
    return line


def _research_partial(step: Any) -> "tuple[list[str], list[str]] | None":
    """Return ``(supported, unsupported)`` dimensions for a partial research step."""
    metadata = getattr(step, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    completeness = metadata.get("research_completeness")
    if not isinstance(completeness, dict) or completeness.get("status") != "partial":
        return None
    supported = [d for d in (completeness.get("supported") or ()) if isinstance(d, str) and d]
    unsupported = [
        d for d in (completeness.get("unsupported") or ()) if isinstance(d, str) and d
    ]
    return supported, unsupported


def _research_partial_lines(steps: "tuple[Any, ...]") -> "list[str] | None":
    for step in steps:
        dims = _research_partial(step)
        if dims is None:
            continue
        supported, unsupported = dims
        lines = ["Research partially completed."]
        if supported:
            lines.append("Relevant evidence obtained for:")
            lines.extend(f"- {dimension}" for dimension in supported)
        if unsupported:
            lines.append("No sufficient evidence obtained for:")
            lines.extend(f"- {dimension}" for dimension in unsupported)
        return lines
    return None


def render_outcome(result: Any) -> str:
    """Render an :class:`OrchestrationResult`-like outcome into natural text.

    The deterministic status is the ground truth; this only *presents* it. The
    pinned truthful phrases are preserved: a completed run reports
    ``Steps completed: N/M.``; a partial run reports ``Completed with issues``;
    a failed run never claims ``Done`` or a completed step count.
    """
    status = _state_value(getattr(result, "status", ""))
    steps = tuple(getattr(result, "steps", ()) or ())[:_MAX_STEPS]
    total = len(steps)
    completed = int(getattr(result, "completed_count", 0) or 0)
    failed = int(getattr(result, "failed_count", 0) or 0)
    blocked = int(getattr(result, "blocked_count", 0) or 0)
    skipped = int(getattr(result, "skipped_count", 0) or 0)
    failure_kinds = tuple(getattr(result, "failure_kinds", ()) or ())

    if status == "completed":
        lines = [f"Done. Steps completed: {completed}/{total}."]
        lines.extend(line for line in (describe_step(s) for s in steps) if line)
        return "\n".join(lines[:_MAX_LINES])

    if status == "rejected":
        lines = ["Could not execute this request."]
        reason = _bounded(getattr(result, "error", ""), _MAX_ERROR_CHARS)
        if reason:
            lines.append(f"Reason: {reason}")
        denials = [
            f"{getattr(s, 'target', '')} ({_state_value(getattr(s, 'failure_kind', ''))})"
            for s in steps
            if getattr(s, "failure_kind", None) is not None
        ]
        if denials:
            lines.append("Details: " + "; ".join(denials))
        return "\n".join(lines[:_MAX_LINES])

    if status == "partial":
        partial_lines = _research_partial_lines(steps)
        if partial_lines is not None:
            return "\n".join(partial_lines[:_MAX_LINES])
        lines = ["Completed with issues."]
        lines.append(
            f"{completed} of {total} step(s) completed; {failed} failed, "
            f"{blocked} blocked, {skipped} skipped."
        )
        if failure_kinds:
            lines.append(f"Failure kinds: {', '.join(failure_kinds)}.")
        lines.extend(line for line in (describe_step(s) for s in steps) if line)
        error = _bounded(getattr(result, "error", ""), _MAX_ERROR_CHARS)
        if error:
            lines.append(error)
        return "\n".join(lines[:_MAX_LINES])

    if status in ("failed", "empty"):
        lines = ["Could not complete the request."]
        lines.append(
            f"{completed} of {total} step(s) completed; {failed} failed, "
            f"{blocked} blocked, {skipped} skipped."
        )
        if failure_kinds:
            lines.append(f"Failure kinds: {', '.join(failure_kinds)}.")
        lines.extend(line for line in (describe_step(s) for s in steps) if line)
        error = _bounded(getattr(result, "error", ""), _MAX_ERROR_CHARS)
        if error:
            lines.append(error)
        return "\n".join(lines[:_MAX_LINES])

    return f"Execution {status}." if status else "Execution finished."
