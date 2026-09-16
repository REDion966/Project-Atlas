"""C1.1 defect-resolution regression tests.

These tests pin the architectural correction implemented for the C1.1 defects:

  * Defect A — conversation accesses autonomy only through the injected kernel
    boundary; the injected ``autonomy_check`` is actually used by the L1-L5
    handlers and fails closed when absent.
  * Kernel ownership — the kernel's ``_autonomy_check`` reproduces the
    level -> policy mapping the conversation handlers previously built inline,
    and the composition root wires it into the conversation service.
  * Defect B — investigation path validation no longer depends on the
    ``atlas.evolution.autonomy`` sandbox module and remains behaviorally
    equivalent to the E2 ``CodeChangeSet.validate_path`` check.
"""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace

import pytest

from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.evolution.autonomy.code_sandbox import CodeChangeSet, SandboxPathError
from atlas.evolution.development_cycle import validate_change_path
from atlas.evolution.models import ApprovalDecision, ProposalStatus
from atlas.kernel.atlas import Atlas
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


# ---------------------------------------------------------------------------
# Shared doubles
# ---------------------------------------------------------------------------


class _FakeAI:
    def chat(self, prompt, routing_context=None):
        return SimpleNamespace(text="ok")

    def stream_chat(self, prompt, routing_context=None):
        yield "ok"


def _owner_session() -> SessionContext:
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return SessionContext.from_session(manager.create_session("owner"))


def _spec():
    return TaskIntake().intake("proceed autonomously")


def _denied(level: int) -> SimpleNamespace:
    """A duck-typed AutonomyDecisionProtocol that denies execution."""
    return SimpleNamespace(
        can_proceed=False,
        reason=f"denied at L{level}",
        escalation_required=False,
        authorization_mode=None,
        evidence={"level": level},
    )


class _Recorder:
    """Callable autonomy-check double that records each invocation."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, proposal, session_context, *, level):
        self.calls.append(
            {"proposal": proposal, "session": session_context, "level": level}
        )
        return _denied(level)


def _service(*, autonomy_check=None) -> ConversationService:
    return ConversationService(
        _FakeAI(), task_intake=TaskIntake(), autonomy_check=autonomy_check
    )


def _prime_l1(svc: ConversationService):
    """Prime a service so the L1 autonomy handler reaches the boundary check."""
    proposal = SimpleNamespace(
        proposal_id="P-L1", status=ProposalStatus.APPROVED, metadata={}
    )
    request = SimpleNamespace(
        proposal_id="P-L1",
        decision=ApprovalDecision.APPROVED,
        is_valid_for=lambda p: True,
    )
    svc._active_evolution_proposals["P-L1"] = proposal
    svc._active_approval_requests["R-L1"] = request
    svc._state_manager.update(evolution_proposal_id="P-L1", pending_approval_id="R-L1")
    svc._last_session_context = _owner_session()
    return proposal


_L2_TO_L5 = [
    (2, "_maybe_handle_l2_autonomy_request", "l2_autonomy"),
    (3, "_maybe_handle_l3_autonomy_request", "l3_autonomy"),
    (4, "_maybe_handle_l4_autonomy_request", "l4_autonomy"),
    (5, "_maybe_handle_l5_autonomy_request", "l5_autonomy"),
]


# ---------------------------------------------------------------------------
# Defect A — injected autonomy boundary
# ---------------------------------------------------------------------------


def test_conversation_service_stores_injected_autonomy_check():
    recorder = _Recorder()
    svc = _service(autonomy_check=recorder)
    assert svc._autonomy_check is recorder


@pytest.mark.parametrize("level,handler_name,meta_key", _L2_TO_L5)
def test_l2_to_l5_handlers_use_injected_autonomy_check(level, handler_name, meta_key):
    recorder = _Recorder()
    svc = _service(autonomy_check=recorder)
    svc._last_session_context = _owner_session()

    message = getattr(svc, handler_name)(_spec())

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["level"] == level
    assert recorder.calls[0]["proposal"] is None
    assert message is not None
    assert message.metadata[meta_key]["status"] == "denied"


@pytest.mark.parametrize("level,handler_name,meta_key", _L2_TO_L5)
def test_l2_to_l5_handlers_fail_closed_without_autonomy_check(
    level, handler_name, meta_key
):
    svc = _service(autonomy_check=None)
    svc._last_session_context = _owner_session()

    message = getattr(svc, handler_name)(_spec())

    assert message is not None
    assert message.metadata[meta_key]["status"] == "not_available"


def test_l1_handler_uses_injected_autonomy_check():
    recorder = _Recorder()
    svc = _service(autonomy_check=recorder)
    proposal = _prime_l1(svc)

    message = svc._maybe_handle_autonomy_request(_spec())

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["level"] == 1
    assert recorder.calls[0]["proposal"] is proposal
    assert message is not None
    assert message.metadata["autonomy"]["status"] == "denied"


def test_l1_handler_fails_closed_without_autonomy_check():
    svc = _service(autonomy_check=None)
    _prime_l1(svc)

    message = svc._maybe_handle_autonomy_request(_spec())

    assert message is not None
    assert message.metadata["autonomy"]["status"] == "not_available"


# ---------------------------------------------------------------------------
# Kernel ownership — level -> policy mapping + composition-root wiring
# ---------------------------------------------------------------------------


def _owner_stub():
    return SimpleNamespace(is_owner=True, authority=SimpleNamespace(value="owner"))


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_kernel_autonomy_check_permits_approved_owner_per_level(level):
    atlas = object.__new__(Atlas)  # no heavy __init__; method only uses class attrs
    proposal = SimpleNamespace(status=ProposalStatus.APPROVED)

    decision = atlas._autonomy_check(proposal, _owner_stub(), level=level)

    assert decision.can_proceed is True
    assert decision.authorization_mode is not None


def test_kernel_autonomy_check_rejects_unknown_level():
    atlas = object.__new__(Atlas)
    with pytest.raises(ValueError):
        atlas._autonomy_check(None, _owner_stub(), level=99)


def test_kernel_wires_autonomy_check_into_conversation():
    atlas = Atlas()
    try:
        atlas.start()
        seam = atlas._conversation._autonomy_check
        assert seam is not None
        # The seam is the real kernel boundary and works end-to-end.
        decision = seam(
            SimpleNamespace(status=ProposalStatus.APPROVED),
            _owner_stub(),
            level=1,
        )
        assert decision.can_proceed is True
    finally:
        atlas.shutdown()


# ---------------------------------------------------------------------------
# Defect B — investigation path validation stays safe and equivalent
# ---------------------------------------------------------------------------


def test_investigation_module_has_no_sandbox_import():
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "atlas" / "conversation" / "investigation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        module = getattr(node, "module", None)
        if module:
            assert not module.startswith("atlas.evolution.autonomy")
            assert not module.startswith("atlas.evolution.governance")


_INVALID_PATHS = [
    "",
    "/abs/path.py",
    "\\abs\\path.py",
    "C:/x.py",
    "c:x.py",
    "../x.py",
    "a/../b.py",
    "a/./b.py",
    "a//b.py",
    ".",
]

_VALID_PATHS = [
    "atlas/module.py",
    "docs/note.md",
    "a/b/c.txt",
    "tests/test_x.py",
]


@pytest.mark.parametrize("path", _INVALID_PATHS)
def test_validate_change_path_rejects_invalid(path):
    with pytest.raises(ValueError):
        validate_change_path(path)


@pytest.mark.parametrize("path", _VALID_PATHS)
def test_validate_change_path_accepts_valid(path):
    validate_change_path(path)  # must not raise


@pytest.mark.parametrize("path", _INVALID_PATHS + _VALID_PATHS)
def test_validate_change_path_matches_e2_sandbox_behavior(path):
    try:
        CodeChangeSet.validate_path(path)
        e2_rejected = False
    except SandboxPathError:
        e2_rejected = True

    try:
        validate_change_path(path)
        new_rejected = False
    except ValueError:
        new_rejected = True

    assert new_rejected == e2_rejected


def test_validate_change_path_enforces_length_bound():
    with pytest.raises(ValueError):
        validate_change_path("a" * 300)
    validate_change_path("a" * CodeChangeSet.MAX_PATH_LEN)  # boundary allowed
