"""P10.2 — B1 Authority Enforcement at Executor Boundary.

Verifies that the execution boundary (ApplicationEngine) enforces
authorization independently of any upstream caller.

Core security invariant:
  A caller bypassing an upstream governance/authorization check MUST NOT be
  able to directly invoke the execution boundary and perform an unauthorized
  action.

Authorization must be enforced where execution actually occurs.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from typing import Any

from atlas.evolution.autonomy.application_engine import ApplicationEngine
from atlas.evolution.autonomy.authorization_manager import (
    AuthorizationManager,
    AuthorizationRequest,
)
from atlas.evolution.autonomy.applier import DictStateReader, DictStateWriter
from atlas.evolution.autonomy.applier_registry import ApplierRegistry
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionRequestStatus,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
)
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel


class _InMemorySnapshotStorage:
    """Minimal snapshot storage for tests."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}

    def store_snapshot(
        self,
        snapshot_id: str,
        request_id: str,
        snapshot_data: dict[str, Any],
        checksum: str,
        created_at: str,
    ) -> None:
        self._snapshots[snapshot_id] = snapshot_data

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        return self._snapshots.get(snapshot_id)


def _make_request(
    request_id: str = "RQ-1",
    scope: ScopeType = ScopeType.MEMORY,
    authorization: EvolutionAuthorization | None = None,
    status: EvolutionRequestStatus = EvolutionRequestStatus.SCHEDULED,
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=scope,
        change_payload={"entries": [{"memory_id": "M1", "content": "hello"}]},
        intended_level=ExecutionLevel.INFORMATION,
        status=status,
        authorization=authorization,
        rollback=RollbackPlan(
            strategy=RollbackStrategy.SNAPSHOT,
            snapshot_ref="snap-1",
        ),
        risk=RiskAssessment(risk_level=RiskLevel.LOW),
    )


def _make_authorized_request(
    request_id: str = "RQ-1",
    scope: ScopeType = ScopeType.MEMORY,
    authorized_by: str = "user:cli",
    expires_at: datetime | None = None,
) -> EvolutionRequest:
    auth = EvolutionAuthorization(
        request_id=request_id,
        authorized_by=authorized_by,
        mode=AuthorizationMode.EXPLICIT,
        granted_at=datetime(2026, 1, 1, 12, 0, 0),
        expires_at=expires_at,
    )
    return _make_request(request_id, scope, authorization=auth)


class TestAuthorityEnforcementAtBoundary(unittest.TestCase):
    """P10.2 — Authorization enforced at the execution boundary."""

    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.snapshot_storage = _InMemorySnapshotStorage()
        self.registry = ApplierRegistry.default()
        # Policy enabled so authorization can be granted for authorized tests.
        self.policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.MEMORY, ScopeType.KNOWLEDGE],
            max_risk_level=RiskLevel.HIGH,
            effective_execution_level=ExecutionLevel.INFORMATION,
        )
        self.manager = AuthorizationManager(
            policy=self.policy,
            clock=lambda: self.now,
        )

    def _make_engine(
        self,
        manager: AuthorizationManager | None = None,
    ) -> ApplicationEngine:
        states: dict = {}
        writers = {
            scope: DictStateWriter(states.setdefault(scope, {}))
            for scope in ScopeType
        }
        readers = {
            scope: DictStateReader(states.get(scope, {}))
            for scope in ScopeType
        }
        return ApplicationEngine(
            registry=self.registry,
            snapshot_storage=self.snapshot_storage,
            readers=readers,
            writers=writers,
            clock=lambda: self.now,
            authorization_manager=manager,
        )

    # ------------------------------------------------------------------
    # A. Authorized execution
    # ------------------------------------------------------------------
    def test_authorized_execution_succeeds(self):
        """Valid authority → execution proceeds."""
        engine = self._make_engine(manager=self.manager)
        req = _make_authorized_request()
        result = engine.apply(req)
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")

    # ------------------------------------------------------------------
    # B. Unauthorized execution
    # ------------------------------------------------------------------
    def test_unauthorized_execution_rejected(self):
        """No authorization → execution rejected at boundary."""
        engine = self._make_engine(manager=self.manager)
        req = _make_request()  # no authorization
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        self.assertIn("Authorization refused", result.error)

    # ------------------------------------------------------------------
    # C. Missing authority
    # ------------------------------------------------------------------
    def test_missing_authority_rejected(self):
        """None authorization → rejected, never treated as trusted."""
        engine = self._make_engine(manager=self.manager)
        req = _make_request(authorization=None)
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")

    # ------------------------------------------------------------------
    # D. Invalid authority
    # ------------------------------------------------------------------
    def test_mismatched_request_id_rejected(self):
        """Authorization for a different request ID → rejected."""
        engine = self._make_engine(manager=self.manager)
        # Authorization belongs to a different request than the one being
        # executed — the boundary must detect the mismatch.
        auth = EvolutionAuthorization(
            request_id="OTHER-REQUEST",
            authorized_by="user:cli",
            mode=AuthorizationMode.EXPLICIT,
        )
        req = _make_request(request_id="RQ-1", authorization=auth)
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")

    # ------------------------------------------------------------------
    # E. MANDATORY direct bypass test
    # ------------------------------------------------------------------
    def test_direct_bypass_denied(self):
        """MANDATORY: untrusted/direct caller invoking the executor boundary
        directly with insufficient authority is DENIED and the protected
        operation does NOT occur."""
        engine = self._make_engine(manager=self.manager)
        # Direct call to apply() — bypassing the gateway entirely — with no
        # authorization. This simulates an untrusted caller.
        req = _make_request(request_id="BYPASS-1")
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        # Verify no state mutation occurred (no receipt, no applied change)
        self.assertIsNone(result.receipt)
        self.assertIsNone(result.request.receipt)

    # ------------------------------------------------------------------
    # F. Wrong scope
    # ------------------------------------------------------------------
    def test_constitutionally_protected_scope_rejected(self):
        """CODE scope is constitutionally protected → rejected even with
        authorization attempt."""
        engine = self._make_engine(manager=self.manager)
        req = _make_authorized_request(scope=ScopeType.CODE)
        result = engine.apply(req)
        self.assertFalse(result.success)

    # ------------------------------------------------------------------
    # G. Expired authority
    # ------------------------------------------------------------------
    def test_expired_authority_rejected(self):
        """Expired authorization → rejected at boundary."""
        engine = self._make_engine(manager=self.manager)
        expired = _make_authorized_request(
            expires_at=self.now - timedelta(seconds=1)
        )
        result = engine.apply(expired)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        self.assertIn("expired", result.error.lower())

    # ------------------------------------------------------------------
    # H. Approval without authority
    # ------------------------------------------------------------------
    def test_approval_state_without_authority_rejected(self):
        """Request in SCHEDULED/APPROVED-like status but without structured
        authorization → executor still rejects."""
        engine = self._make_engine(manager=self.manager)
        # Status suggests workflow progress, but no authorization record.
        req = _make_request(status=EvolutionRequestStatus.SCHEDULED)
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")

    # ------------------------------------------------------------------
    # I. Conversational confirmation without authority
    # ------------------------------------------------------------------
    def test_conversational_confirmation_without_authority_rejected(self):
        """A conversational 'yes' (metadata only) without structured
        authorization → executor rejects."""
        engine = self._make_engine(manager=self.manager)
        req = _make_request()
        req.metadata["user_confirmed"] = "yes"  # conversational, not authority
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")

    # ------------------------------------------------------------------
    # J. Repeated execution determinism
    # ------------------------------------------------------------------
    def test_repeated_execution_deterministic(self):
        """Authorization behavior remains deterministic across calls."""
        engine = self._make_engine(manager=self.manager)
        req = _make_request()
        r1 = engine.apply(req)
        r2 = engine.apply(req)
        self.assertEqual(r1.terminal_status, r2.terminal_status)
        self.assertFalse(r1.success)
        self.assertFalse(r2.success)

    # ------------------------------------------------------------------
    # K. No manager wired → backward compatible
    # ------------------------------------------------------------------
    def test_no_manager_allows_execution(self):
        """When no AuthorizationManager is wired, the engine remains
        backward compatible (relies on upstream governance)."""
        engine = self._make_engine(manager=None)
        req = _make_request()  # no authorization
        result = engine.apply(req)
        # Without a manager, the engine proceeds (upstream governance is
        # assumed to have checked). This preserves existing behavior.
        self.assertTrue(result.success)

    # ------------------------------------------------------------------
    # L. Side-effect safety
    # ------------------------------------------------------------------
    def test_rejected_operation_performs_no_mutation(self):
        """A rejected operation must not mutate state."""
        engine = self._make_engine(manager=self.manager)
        req = _make_request(request_id="NO-MUTATE")
        result = engine.apply(req)
        self.assertFalse(result.success)
        # No receipt means no mutation occurred
        self.assertIsNone(result.receipt)
        self.assertIsNone(result.request.receipt)

    # ------------------------------------------------------------------
    # M. Forged authority metadata
    # ------------------------------------------------------------------
    def test_forged_authority_metadata_rejected(self):
        """Authorization with mismatched/forged request_id is rejected."""
        engine = self._make_engine(manager=self.manager)
        # Attempt to forge authorization for a different request
        forged_auth = EvolutionAuthorization(
            request_id="FORGED-100",
            authorized_by="user:cli",
            mode=AuthorizationMode.EXPLICIT,
        )
        req = _make_request(request_id="REAL-1", authorization=forged_auth)
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")


if __name__ == "__main__":
    unittest.main()
