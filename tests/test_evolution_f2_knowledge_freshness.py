"""Phase F2 — Knowledge Freshness & Provenance tests.

Deterministic, offline coverage across the 20 F2 acceptance criteria:

 1. Fresh knowledge → FRESH
 2. Old source → STALE
 3. Old verification → STALE
 4. Low confidence behavior
 5. Missing provenance
 6. Missing timestamps
 7. Relevant environment change invalidates knowledge
 8. Irrelevant environment change does not invalidate knowledge
 9. Multiple stale reasons preserved
10. Provenance references preserved
11. Assessment does not mutate source knowledge
12. Deterministic output
13. Injected clock/time works
14. Configurable policy thresholds
15. Multiple knowledge entries
16. Candidate priority/recommendation deterministic
17. No research/external API execution
18. No governance subsystem imports
19. F1 integration works through existing environment models
20. Existing Phase E behavior remains intact

All assertions use fixed UTC timestamps — no wall-clock, no network.
"""

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.evolution.freshness import (
    FreshnessPolicy,
    FreshnessReason,
    FreshnessStatus,
    KnowledgeFreshnessAssessor,
    KnowledgeRef,
    RecommendedAction,
    StaleKnowledgeCandidate,
)

from atlas.evolution.environment.models import (
    EnvironmentChange,
    EnvironmentChangeType,
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentState,
    ObservationReliability,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _ref(
    knowledge_id,
    domain="MODEL",
    entity_key="",
    source_uris=(),
    claim_id="",
    verification_id="",
    retrieved_at=None,
    verified_at=None,
    confidence=None,
    affected_domains=(),
    affected_entity_keys=(),
):
    """Convenience KnowledgeRef builder with fixed defaults."""
    return KnowledgeRef(
        knowledge_id=knowledge_id,
        domain=domain,
        entity_key=entity_key,
        source_uris=tuple(source_uris),
        claim_id=claim_id,
        verification_id=verification_id,
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        confidence=confidence,
        affected_domains=frozenset(affected_domains),
        affected_entity_keys=frozenset(affected_entity_keys),
    )


def _change(
    domain,
    entity_id,
    change_type=EnvironmentChangeType.CHANGED,
    observed_at=NOW,
):
    """Build a real F1 EnvironmentChange record."""
    entity = EnvironmentEntity(EnvironmentDomain[domain], entity_id)
    return EnvironmentChange(
        entity=entity,
        change_type=change_type,
        current={"state": "new"},
        observed_at=observed_at,
        source="tool_registry",
        reliability=ObservationReliability.MEDIUM,
    )


def _made(now=None):
    return KnowledgeFreshnessAssessor(now=lambda: now or NOW)


class TestFreshClassifications(unittest.TestCase):
    """1–6: core freshness classification."""

    def test_fresh_knowledge_is_fresh(self):
        ref = _ref(
            "k1",
            retrieved_at=NOW - timedelta(days=5),
            verified_at=NOW - timedelta(days=2),
            confidence=0.9,
        )
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.FRESH)
        self.assertEqual(assessment.reasons, ())

    def test_old_source_is_stale(self):
        ref = _ref(
            "k1",
            retrieved_at=NOW - timedelta(days=600),
            verified_at=NOW - timedelta(days=2),
            confidence=0.9,
        )
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.SOURCE_AGE, assessment.reasons)

    def test_old_verification_is_stale(self):
        ref = _ref(
            "k1",
            retrieved_at=NOW - timedelta(days=5),
            verified_at=NOW - timedelta(days=400),
            confidence=0.9,
        )
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.VERIFICATION_AGE, assessment.reasons)

    def test_low_confidence_uncertain(self):
        ref = _ref(
            "k1",
            retrieved_at=NOW - timedelta(days=5),
            verified_at=NOW - timedelta(days=2),
            confidence=0.2,
        )
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.UNCERTAIN)
        self.assertIn(FreshnessReason.LOW_CONFIDENCE, assessment.reasons)

    def test_missing_provenance_is_uncertain(self):
        ref = _ref("k1")  # no source_uris, no retrieved_at, no verified_at
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.UNCERTAIN)
        self.assertIn(FreshnessReason.MISSING_PROVENANCE, assessment.reasons)

    def test_missing_timestamp_never_treated_as_fresh(self):
        # Has a source URI but no retrieval timestamp.
        ref = _ref("k1", source_uris=("http://src/1",))
        assessment = _made().assess(ref)
        self.assertIsNot(assessment.status, FreshnessStatus.FRESH)
        self.assertIn(FreshnessReason.MISSING_PROVENANCE, assessment.reasons)

    def test_named_verification_without_timestamp_is_stale(self):
        ref = _ref(
            "k1",
            source_uris=("http://src/1",),
            retrieved_at=NOW - timedelta(days=5),
            verification_id="VER-1",
        )
        assessment = _made().assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.VERIFICATION_AGE, assessment.reasons)


class TestEnvironmentChangeRelevance(unittest.TestCase):
    """7-8: F1 environment-change relevance is deterministic."""

    def test_relevant_entity_change_invalidates(self):
        ref = _ref(
            "k1", entity_key="MODEL:openai:gpt-4",
            affected_entity_keys=("MODEL:openai:gpt-4",),
            source_uris=("http://src/1",),
            retrieved_at=NOW - timedelta(days=5),
        )
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(ref, changes=[change])
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.ENVIRONMENT_CHANGE, assessment.reasons)
        self.assertEqual(
            assessment.triggering_environment_entity_key, change.entity.key
        )

    def test_relevant_domain_change_invalidates(self):
        ref = _ref("k1", affected_domains=("MODEL",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=5))
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(ref, changes=[change])
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.ENVIRONMENT_CHANGE, assessment.reasons)

    def test_irrelevant_change_does_not_invalidate(self):
        ref = _ref("k1", domain="TOOL", entity_key="TOOL:sandbox_pytest",
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=5),
                   verified_at=NOW - timedelta(days=2), confidence=0.9)
        change = _change("MODEL", "openai:gpt-4")  # unrelated domain
        assessment = _made().assess(ref, changes=[change])
        self.assertIs(assessment.status, FreshnessStatus.FRESH)
        self.assertNotIn(FreshnessReason.ENVIRONMENT_CHANGE, assessment.reasons)

    def test_unclassifiable_change_is_not_relevant(self):
        ref = _ref("k1", source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=5))
        change = _change("MODEL", "openai:gpt-4")
        self.assertFalse(KnowledgeFreshnessAssessor._is_relevant(change, ref))


class TestMultipleReasons(unittest.TestCase):
    """9: all deterministic reasons preserved."""

    def test_source_and_verification_age_both_present(self):
        ref = _ref("k1", source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600),
                   verified_at=NOW - timedelta(days=400),
                   confidence=0.1)
        assessment = _made().assess(ref)
        reason_set = set(assessment.reasons)
        self.assertIn(FreshnessReason.SOURCE_AGE, reason_set)
        self.assertIn(FreshnessReason.VERIFICATION_AGE, reason_set)
        self.assertIn(FreshnessReason.LOW_CONFIDENCE, reason_set)
        self.assertEqual(len(assessment.reasons), len(reason_set))  # no dupes

    def test_environment_change_plus_age(self):
        ref = _ref("k1", domain="MODEL", affected_domains=("MODEL",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600))
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(ref, changes=[change])
        self.assertIn(FreshnessReason.SOURCE_AGE, assessment.reasons)
        self.assertIn(FreshnessReason.ENVIRONMENT_CHANGE, assessment.reasons)


class TestProvenance(unittest.TestCase):
    """10-11: provenance preserved; no mutation of source artifacts."""

    def test_assessment_carries_provenance_refs(self):
        ref = _ref("k1", domain="MODEL", entity_key="MODEL:openai:gpt-4",
                   source_uris=("http://src/1", "http://src/2"),
                   claim_id="CLAIM-1", verification_id="VER-1",
                   retrieved_at=NOW - timedelta(days=600))
        assessment = _made().assess(ref)
        self.assertEqual(assessment.source_uris, ("http://src/1", "http://src/2"))
        self.assertEqual(assessment.claim_id, "CLAIM-1")
        self.assertEqual(assessment.verification_id, "VER-1")
        self.assertEqual(assessment.retrieved_at, ref.retrieved_at)

    def test_assessment_does_not_mutate_reference(self):
        ref = _ref("k1", source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600),
                   verified_at=NOW - timedelta(days=2), confidence=0.9)
        before = (ref.retrieved_at, ref.verified_at, ref.confidence,
                  tuple(ref.source_uris))
        _made().assess(ref)
        after = (ref.retrieved_at, ref.verified_at, ref.confidence,
                 tuple(ref.source_uris))
        self.assertEqual(before, after)

    def test_assessment_does_not_mutate_real_f1_change(self):
        change = _change("MODEL", "openai:gpt-4")
        ref = _ref("k1", domain="MODEL", affected_domains=("MODEL",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600))
        _made().assess(ref, changes=[change])
        self.assertEqual(change.entity.key, "MODEL:openai:gpt-4")
        self.assertIs(change.change_type, EnvironmentChangeType.CHANGED)


class TestDeterminism(unittest.TestCase):
    """12-13: deterministic output; injected clock works."""

    def test_identical_inputs_produce_identical_assessments(self):
        ref = _ref("k1", source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600))
        changes = [_change("MODEL", "openai:gpt-4")]
        a1 = _made().assess(ref, changes=changes)
        a2 = _made().assess(ref, changes=changes)
        self.assertEqual(a1.status, a2.status)
        self.assertEqual(a1.reasons, a2.reasons)
        self.assertEqual(a1.rationale, a2.rationale)

    def test_assessed_at_uses_injected_clock(self):
        ref = _ref("k1", source_uris=("http://src/",),
                   retrieved_at=NOW - timedelta(days=5))
        assessor = KnowledgeFreshnessAssessor(
            now=lambda: datetime(2025, 5, 5, tzinfo=timezone.utc)
        )
        assessment = assessor.assess(ref)
        self.assertEqual(assessment.assessed_at,
                         datetime(2025, 5, 5, tzinfo=timezone.utc))

    def test_naive_timestamps_normalized_to_utc(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        ref = _ref("k1", source_uris=("http://src/",), retrieved_at=naive)
        self.assertIsNotNone(ref.retrieved_at)
        self.assertIsNotNone(ref.retrieved_at.tzinfo)


class TestPolicy(unittest.TestCase):
    """14: configurable policy thresholds."""

    def test_longer_source_floor_keeps_fresh(self):
        policy = _policy(max_source_age=timedelta(days=2000))
        ref = _ref("k1", source_uris=("http://src/",),
                   retrieved_at=NOW - timedelta(days=1200),
                   verified_at=NOW - timedelta(days=2), confidence=0.9)
        assessment = KnowledgeFreshnessAssessor(policy=policy, now=lambda: NOW).assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.FRESH)

    def test_invalidating_domains_configurable(self):
        policy = _policy(
            invalidating_domains=frozenset({"MODEL"}),
            environment_invalidated_status=FreshnessStatus.STALE,
        )
        ref = _ref("k1", affected_domains=("MODEL",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=5))
        change = _change("MODEL", "openai:gpt-4")
        assessment = KnowledgeFreshnessAssessor(policy=policy, now=lambda: NOW).assess(
            ref, changes=[change]
        )
        self.assertIs(assessment.status, FreshnessStatus.STALE)

    def test_missing_provenance_status_switch(self):
        policy = _policy(missing_provenance_status=FreshnessStatus.STALE)
        ref = _ref("k1")
        assessment = KnowledgeFreshnessAssessor(policy=policy, now=lambda: NOW).assess(ref)
        self.assertIs(assessment.status, FreshnessStatus.STALE)

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            _policy(max_source_age=timedelta(0))
        with self.assertRaises(ValueError):
            _policy(min_confidence=1.5)


class TestCandidatesAndMany(unittest.TestCase):
    """15-16: multiple entries; deterministic candidate ordering."""

    def test_assess_many_sorted_by_knowledge_id(self):
        refs = [
            _ref("k2", source_uris=("http://s2",),
                 retrieved_at=NOW - timedelta(days=600)),
            _ref("k1", source_uris=("http://s1",),
                 retrieved_at=NOW - timedelta(days=5)),
        ]
        assessments = _made().assess_many(refs)
        self.assertEqual([a.knowledge_id for a in assessments], ["k1", "k2"])

    def test_find_stale_candidates_ordering(self):
        refs = [
            _ref("fresh", source_uris=("http://s",),
                 retrieved_at=NOW - timedelta(days=5),
                 verified_at=NOW - timedelta(days=2), confidence=0.9),
            _ref("env", domain="MODEL", affected_domains=("MODEL",),
                 source_uris=("http://s",),
                 retrieved_at=NOW - timedelta(days=600)),
            _ref("uncertain", source_uris=("http://s",)),
        ]
        changes = [_change("MODEL", "openai:gpt-4")]
        candidates = _made().find_stale_candidates(refs, changes=changes)
        names = [c.knowledge_id for c in candidates]
        self.assertNotIn("fresh", names)
        self.assertEqual(names, ["env", "uncertain"])

    def test_candidate_action_and_priority_deterministic(self):
        ref = _ref("k1", domain="MODEL", affected_domains=("MODEL",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=600))
        change = _change("MODEL", "openai:gpt-4")
        candidates = _made().find_stale_candidates([ref], changes=[change])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.priority, 1.0)
        self.assertIs(candidate.recommended_action, RecommendedAction.RESEARCH)
        self.assertEqual(candidate.provenance_refs, ("http://src/1",))
        self.assertEqual(candidate.reasons, (FreshnessReason.SOURCE_AGE,
                                            FreshnessReason.ENVIRONMENT_CHANGE))


class TestNoExternalSideEffects(unittest.TestCase):
    """17-18: no research/governance/external surface imported or executed."""

    def test_no_research_or_governance_imports(self):
        freshness_dir = _REPO_ROOT / "atlas" / "evolution" / "freshness"
        forbidden_prefixes = (
            "atlas.research", "atlas.ai", "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway", "atlas.evolution.approval_manager",
            "atlas.evolution.governance", "subprocess", "urllib", "requests",
        )
        violations = []
        for path in sorted(freshness_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p)
                               for p in forbidden_prefixes):
                            violations.append((str(path), alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(node.module == p or node.module.startswith(p)
                                           for p in forbidden_prefixes):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])


class TestF1Integration(unittest.TestCase):
    """19: F1 EnvironmentChange models integrate via duck-typed access."""

    def test_real_f1_change_drives_assessment(self):
        ref = _ref("k1", domain="MODEL", entity_key="MODEL:openai:gpt-4",
                   affected_entity_keys=("MODEL:openai:gpt-4",),
                   source_uris=("http://src/1",),
                   retrieved_at=NOW - timedelta(days=5))
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(ref, changes=[change])
        self.assertIs(assessment.status, FreshnessStatus.STALE)
        self.assertIn(FreshnessReason.ENVIRONMENT_CHANGE, assessment.reasons)
        # Deterministic change-ID fallback (entity@observed_at).
        self.assertTrue(assessment.triggering_environment_change_id)


def _policy(**overrides):
    defaults = dict(
        max_source_age=timedelta(days=180),
        max_verification_age=timedelta(days=90),
        min_confidence=0.5,
    )
    defaults.update(overrides)
    return FreshnessPolicy(**defaults)


if __name__ == "__main__":
    unittest.main()