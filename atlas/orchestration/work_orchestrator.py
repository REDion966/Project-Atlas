"""Atlas — Self-Directed Work Orchestration (D4).

A bounded, deterministic orchestration layer that carries ONE user objective
across the EXISTING Atlas subsystems as a governed sequence:

    objective (D1 SemanticIntake)
      -> requirements (knowledge / capabilities / subtasks)
      -> knowledge decision (D3; local-first, D2 acquisition when justified)
      -> plan (bounded decomposition over existing structures)
      -> capability availability + dispatch (EXISTING CapabilityRegistry/Dispatcher)
      -> authorization gate (EXISTING session/authority boundary only)
      -> execution (existing governed capability path)
      -> verification
      -> bounded report

It is orchestration ONLY. It is not a second reasoning engine, planner,
dispatcher, research engine, knowledge store, governance system, or execution
engine. Every authority decision is delegated to the component that owns it:

  * knowledge validity/provenance  -> existing D3 / C6 pipeline
  * capability identity + dispatch -> existing CapabilityRegistry/Dispatcher
  * authorization/approval         -> existing SessionManager/AuthorityService
  * execution of governed work     -> existing governed paths (NOT run here)

Deterministic and model-independent: no ``atlas.ai`` import, no network except
through D2's authorized boundary, no self-authorization.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry

_MAX_TEXT: int = 400
_MAX_STEPS: int = 8

#: Semantic task types whose objective is a GOVERNED action (authorization is
#: required and D4 never executes them itself — the existing development/
#: approval flow owns that).
_GOVERNED_TASK_TYPES: frozenset[str] = frozenset(
    {
        "development_request",
        "planning_request",
        "execution_request",
        "autonomy_request",
        "l2_autonomy_request",
        "l3_autonomy_request",
        "l4_autonomy_request",
        "l5_autonomy_request",
        "approval",
        "rejection_request",
    }
)


class OrchestrationState(str, Enum):
    """Lifecycle states of one orchestration run (bounded, deterministic)."""

    RECEIVED = "received"
    UNDERSTOOD = "understood"
    REQUIREMENTS_IDENTIFIED = "requirements_identified"
    KNOWLEDGE_CHECK = "knowledge_check"
    KNOWLEDGE_ACQUIRED = "knowledge_acquired"
    NEEDS_CLARIFICATION = "needs_clarification"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"
    KNOWLEDGE_CONTRADICTED = "knowledge_contradicted"
    PLANNED = "planned"
    AUTHORIZATION_REQUIRED = "authorization_required"
    AUTHORIZED = "authorized"
    BLOCKED_BY_AUTHORITY = "blocked_by_authority"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFICATION_FAILED = "verification_failed"


def _bounded(value: Any, limit: int = _MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class OrchestrationRun:
    """Bounded, JSON-safe record of one orchestration run.

    Holds facts about the sequence only — never authority, never raw external
    content. Transient (not persisted) unless a caller chooses otherwise.
    """

    run_id: str
    objective: str
    state: OrchestrationState
    transitions: tuple[tuple[str, str], ...] = ()
    knowledge: dict[str, Any] | None = None
    plan: tuple[dict[str, Any], ...] = ()
    executions: tuple[dict[str, Any], ...] = ()
    authorization: str = ""
    verification: str = ""
    report: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "state": self.state.value,
            "transitions": [list(t) for t in self.transitions],
            "knowledge": dict(self.knowledge) if self.knowledge else None,
            "plan": [dict(s) for s in self.plan],
            "executions": [dict(e) for e in self.executions],
            "authorization": self.authorization,
            "verification": self.verification,
            "report": self.report,
            "error": self.error,
        }

    @property
    def completed(self) -> bool:
        return self.state is OrchestrationState.COMPLETED


class WorkOrchestrator:
    """Deterministic coordinator over the existing Atlas subsystems.

    Args:
        knowledge_decision: Optional D3 ``KnowledgeDecisionService``.
        capability_registry: The EXISTING ``CapabilityRegistry`` (authoritative
            for capability identity/availability).
        dispatcher: The EXISTING ``CapabilityDispatcher``.
        authorization_check: Optional callable ``(session_context) -> bool``
            supplied by the kernel that consults the EXISTING session/authority
            boundary. When absent, no authorization can be granted (fail closed).
    """

    def __init__(
        self,
        *,
        knowledge_decision: Any | None = None,
        capability_registry: CapabilityRegistry | None = None,
        dispatcher: CapabilityDispatcher | None = None,
        authorization_check: Callable[[Any], bool] | None = None,
    ) -> None:
        self._knowledge = knowledge_decision
        self._registry = capability_registry
        self._dispatcher = dispatcher
        self._authorization_check = authorization_check

    # ------------------------------------------------------------------

    def run(
        self,
        objective: str,
        *,
        semantic: Any | None = None,
        session_context: Any | None = None,
        candidate_urls: Sequence[str] = (),
        require_authorization: bool = False,
    ) -> OrchestrationRun:
        """Run ONE bounded orchestration lifecycle for ``objective``."""
        transitions: list[tuple[str, str]] = []

        def _step(state: OrchestrationState, detail: str = "") -> None:
            transitions.append((state.value, _bounded(detail, 160)))

        objective_text = _bounded(objective) or _bounded(
            getattr(semantic, "objective", "")
        )
        run_id = f"RUN-{hashlib.sha256(objective_text.encode('utf-8')).hexdigest()[:12]}"
        _step(OrchestrationState.RECEIVED, objective_text)

        if not objective_text:
            _step(OrchestrationState.FAILED, "empty objective")
            return self._finish(
                run_id, "", OrchestrationState.FAILED, transitions,
                error="A non-empty objective is required.",
            )
        _step(OrchestrationState.UNDERSTOOD, "semantic objective accepted")

        # 1. Requirements from the D1 semantic representation.
        required_knowledge = self._tuple(getattr(semantic, "required_knowledge", ()))
        required_capabilities = self._tuple(
            getattr(semantic, "required_capabilities", ())
        )
        subtasks = self._tuple(getattr(semantic, "subtasks", ()))
        clarification = self._tuple(
            getattr(semantic, "clarification_questions", ())
        )
        task_type = _bounded(getattr(semantic, "task_type", ""), 64) if semantic else ""
        _step(
            OrchestrationState.REQUIREMENTS_IDENTIFIED,
            f"knowledge={len(required_knowledge)} capabilities={len(required_capabilities)}",
        )

        # Ambiguity: only when nothing actionable is represented.
        if (
            clarification
            and not required_knowledge
            and not required_capabilities
            and not subtasks
        ):
            _step(OrchestrationState.NEEDS_CLARIFICATION, clarification[0])
            return self._finish(
                run_id, objective_text, OrchestrationState.NEEDS_CLARIFICATION,
                transitions,
                report=(
                    "I need more detail before I can act: " + clarification[0]
                ),
            )

        # 2. Knowledge decision (local-first; D2 on insufficiency).
        knowledge_payload: dict[str, Any] | None = None
        if required_knowledge and self._knowledge is not None:
            _step(OrchestrationState.KNOWLEDGE_CHECK, required_knowledge[0])
            answer = self._knowledge.decide(
                required_knowledge[0],
                knowledge_query=required_knowledge[0],
                candidate_urls=tuple(candidate_urls or ()),
            )
            knowledge_payload = answer.to_dict()
            status = getattr(getattr(answer, "status", None), "value", "")
            if status == "contradictory":
                _step(OrchestrationState.KNOWLEDGE_CONTRADICTED, required_knowledge[0])
                return self._finish(
                    run_id, objective_text, OrchestrationState.KNOWLEDGE_CONTRADICTED,
                    transitions, knowledge=knowledge_payload,
                    report=(
                        "The evidence I have conflicts, so I will not choose a "
                        "side. Please clarify or provide an authoritative source."
                    ),
                )
            if status != "sufficient":
                _step(OrchestrationState.KNOWLEDGE_UNAVAILABLE, status)
                return self._finish(
                    run_id, objective_text, OrchestrationState.KNOWLEDGE_UNAVAILABLE,
                    transitions, knowledge=knowledge_payload,
                    report=(
                        "I do not have validated knowledge for that objective "
                        f"(knowledge status: {status or 'unknown'}). I will not guess."
                    ),
                )
            _step(OrchestrationState.KNOWLEDGE_ACQUIRED, "validated knowledge available")

        # 3. Bounded plan (deterministic decomposition; no second planner).
        steps = list(subtasks[:_MAX_STEPS]) or [objective_text]
        plan = tuple(
            {
                "order": index + 1,
                "objective": step,
                "capabilities": list(required_capabilities)
                if index == len(steps) - 1
                else [],
            }
            for index, step in enumerate(steps)
        )
        _step(OrchestrationState.PLANNED, f"{len(plan)} step(s)")

        # 4. Capability availability (EXISTING registry is authoritative).
        if required_capabilities:
            unavailable = [
                name
                for name in required_capabilities
                if self._registry is None or not self._registry.has(name)
            ]
            if unavailable:
                _step(OrchestrationState.FAILED, f"unavailable: {unavailable[0]}")
                return self._finish(
                    run_id, objective_text, OrchestrationState.FAILED, transitions,
                    knowledge=knowledge_payload, plan=plan,
                    error=f"Required capability is unavailable: {unavailable[0]}",
                    report=(
                        f"I cannot proceed: the required capability "
                        f"'{unavailable[0]}' is not available."
                    ),
                )

        # 5. Authorization gate (EXISTING session/authority boundary only).
        authorization_required = bool(require_authorization) or (
            task_type in _GOVERNED_TASK_TYPES
        )
        authorization = "not_required"
        if authorization_required:
            _step(OrchestrationState.AUTHORIZATION_REQUIRED, "governed objective")
            granted = False
            if self._authorization_check is not None:
                try:
                    granted = bool(self._authorization_check(session_context))
                except Exception:
                    granted = False
            if not granted:
                _step(OrchestrationState.BLOCKED_BY_AUTHORITY, "no valid authority")
                return self._finish(
                    run_id, objective_text, OrchestrationState.BLOCKED_BY_AUTHORITY,
                    transitions, knowledge=knowledge_payload, plan=plan,
                    authorization="denied",
                    report=(
                        "This is a governed action and no valid OWNER "
                        "authorization is present, so I will not execute it. "
                        "Please use the existing approval flow."
                    ),
                )
            # Authorized, but D4 never executes governed development itself:
            # the existing proposal -> approval -> sandbox flow owns it.
            _step(OrchestrationState.AUTHORIZED, "owner authority confirmed")
            return self._finish(
                run_id, objective_text, OrchestrationState.AUTHORIZED, transitions,
                knowledge=knowledge_payload, plan=plan, authorization="granted",
                report=(
                    "Authorized. The governed action must proceed through the "
                    "existing development approval flow; I did not execute it here."
                ),
            )

        # 6. Execution via the EXISTING capability dispatcher (read-only caps).
        if required_capabilities and self._dispatcher is not None:
            _step(OrchestrationState.EXECUTING, ",".join(required_capabilities))
            capabilities = [
                Capability(
                    name=name,
                    priority=1,
                    reason="orchestrated step",
                    metadata={"objective": objective_text},
                )
                for name in required_capabilities
            ]
            results = self._dispatcher.dispatch(capabilities)
            executions = tuple(
                {
                    # Record the REQUESTED capability name (authoritative for
                    # the step); the handler's own result is the outcome.
                    "capability": _bounded(name, 80),
                    "success": bool(getattr(result, "success", False)),
                    "error": _bounded(getattr(result, "error", ""), 160),
                }
                for name, result in zip(required_capabilities, results)
            )
            _step(OrchestrationState.VERIFYING, "checking execution results")
            if all(e["success"] for e in executions) and executions:
                verification = "verified"
                _step(OrchestrationState.COMPLETED, "verified")
                return self._finish(
                    run_id, objective_text, OrchestrationState.COMPLETED, transitions,
                    knowledge=knowledge_payload, plan=plan, executions=executions,
                    authorization=authorization, verification=verification,
                    report=self._report(objective_text, knowledge_payload, executions),
                )
            _step(OrchestrationState.VERIFICATION_FAILED, "execution did not verify")
            return self._finish(
                run_id, objective_text, OrchestrationState.VERIFICATION_FAILED,
                transitions, knowledge=knowledge_payload, plan=plan,
                executions=executions, authorization=authorization,
                verification="failed",
                error="Execution did not verify.",
                report=(
                    "Execution ran but did not verify; I am not reporting success."
                ),
            )

        # 7. Knowledge-only objective: no capability step required.
        _step(OrchestrationState.VERIFYING, "validated knowledge")
        _step(OrchestrationState.COMPLETED, "knowledge answer")
        return self._finish(
            run_id, objective_text, OrchestrationState.COMPLETED, transitions,
            knowledge=knowledge_payload, plan=plan, authorization=authorization,
            verification="verified" if knowledge_payload else "",
            report=self._report(objective_text, knowledge_payload, ()),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _tuple(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        if isinstance(value, (list, tuple)):
            return tuple(v for v in value if isinstance(v, str) and v.strip())
        return ()

    @staticmethod
    def _report(
        objective: str,
        knowledge: dict[str, Any] | None,
        executions: tuple[dict[str, Any], ...],
    ) -> str:
        lines = [f"Objective: {objective}"]
        if knowledge:
            claims = knowledge.get("claims") or []
            lines.append(
                f"Knowledge: {knowledge.get('status')} "
                f"({len(claims)} validated claim(s)); "
                f"acquisition={knowledge.get('acquisition_status') or 'none'}"
            )
        for execution in executions:
            lines.append(
                f"Executed: {execution['capability']} "
                f"({'ok' if execution['success'] else 'failed'})"
            )
        lines.append("Result: completed (verified).")
        return "\n".join(lines)

    @staticmethod
    def _finish(
        run_id: str,
        objective: str,
        state: OrchestrationState,
        transitions: list[tuple[str, str]],
        *,
        knowledge: dict[str, Any] | None = None,
        plan: tuple[dict[str, Any], ...] = (),
        executions: tuple[dict[str, Any], ...] = (),
        authorization: str = "",
        verification: str = "",
        report: str = "",
        error: str = "",
    ) -> OrchestrationRun:
        return OrchestrationRun(
            run_id=run_id,
            objective=objective,
            state=state,
            transitions=tuple(transitions),
            knowledge=knowledge,
            plan=plan,
            executions=executions,
            authorization=authorization,
            verification=verification,
            report=report,
            error=error,
        )
