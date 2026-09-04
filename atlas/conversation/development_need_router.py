"""Atlas Conversation — Development Need Router (P7.4).

Pure, deterministic conversation-local bridge between a CONFIRMED P7.3
:class:`ExplicitDevelopmentIntent` and the EXISTING explicit development
intake representation (a ``DEVELOPMENT_REQUEST`` :class:`TaskSpec`).

This module does NOT call F9, ApprovalManager, DevelopmentPlanner, or any
evolution execution machinery. Its only job is to convert a confirmed intent
into the same TaskSpec shape the existing B3 intake already understands, so
the kernel-injected ``development_bridge`` can route it through the existing
governed path.

Design contract:
  * Pure: imports only conversation-owned data types. No kernel, no runtime,
    no storage, no AI, no evolution execution, no orchestration execution,
    no advisory runtime.
  * Deterministic: identical intent -> identical TaskSpec (modulo created_at,
    which is wall-clock like the existing TaskIntake).
  * Provenance-preserving: session_id / principal_id / authority flow into the
    TaskSpec context; they are never elevated or invented.
  * Never fabricates code_changes / test_files (the existing deterministic
    change supplier therefore fails closed without concrete external input).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from atlas.conversation.development_need_dialogue import ExplicitDevelopmentIntent
from atlas.conversation.task_intake import AmbiguityReport, TaskSpec, TaskType


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _bounded_text(value: str, limit: int) -> str:
    return value.strip()[:limit]


def explicit_intent_to_task_spec(intent: ExplicitDevelopmentIntent) -> TaskSpec:
    """Convert a CONFIRMED development intent into a ``DEVELOPMENT_REQUEST``
    ``TaskSpec`` suitable for the existing ``development_bridge``.

    The result is a clear (``needs_clarification=False``) development request
    so the existing B3 intake accepts it and maps it to a ``DevelopmentNeed``.
    No proposal/approval/execution state is produced here.
    """
    title = _bounded_text(intent.title, 400) or "Improve Atlas capability"
    rationale = _bounded_text(intent.rationale, 2000) or title
    capability = _bounded_text(intent.capability, 200)
    success_criteria = (capability or "governed development proposal prepared",)

    context: dict[str, Any] = {
        "source": "development_need_dialogue",
        "signal_kind": intent.signal_kind,
    }
    if intent.session_id:
        context["session_id"] = intent.session_id
    if intent.principal_id:
        context["principal_id"] = intent.principal_id
    if intent.authority:
        context["authority"] = intent.authority

    digest = _stable_hash(title)
    return TaskSpec(
        task_id=digest,
        task_type=TaskType.DEVELOPMENT_REQUEST,
        intent=title,
        goal=rationale,
        constraints=(),
        priorities=(),
        success_criteria=success_criteria,
        context=context,
        ambiguity=AmbiguityReport(
            ambiguity_score=0.0,
            ambiguities=(),
            clarification_questions=(),
        ),
        confidence=1.0,
        needs_clarification=False,
        source="development_need_dialogue",
        verified=True,
        model_metadata={},
        created_at=datetime.now(timezone.utc),
        input_hash=digest,
    )
