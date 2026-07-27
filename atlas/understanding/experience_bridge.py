"""
Atlas Experience → Understanding Bridge — Phase 9.2a

Transforms StructuredExperience records into understanding inputs
(Concept, Pattern, UnderstandingInsight, Relationship) so Atlas can
understand its own execution history without flattening it into text.

Pure logic. No infrastructure. No storage. No services.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from atlas.experience.models import (
    ExperienceOutcome,
    StructuredExperience,
)
from atlas.understanding.models import (
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
)


class ExperienceSource(Protocol):
    """Structural interface for read-only access to stored experiences."""

    def get_window(self, size: int) -> list[StructuredExperience]:
        """Return the most recent `size` experiences."""
        ...

    def get_experiences_since(
        self,
        since: datetime,
    ) -> list[StructuredExperience]:
        """Return experiences observed since `since`."""
        ...

    def get_experiences_by_outcome(
        self,
        outcome: Any,
        n: int = 100,
    ) -> list[StructuredExperience]:
        """Return up to `n` experiences with the given outcome."""
        ...


@dataclass(frozen=True)
class BridgeResult:
    """Output of ExperienceBridge.transform()."""

    concepts: list[Concept] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    insights: list[UnderstandingInsight] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


class ExperienceBridge:
    """
    Converts structured experience records into understanding inputs.

    The bridge is intentionally conservative. It extracts meaning only from
    structured fields:
      - reasoning_capabilities
      - planning_goal
      - tool_name
      - outcome
      - capability trends across the supplied window

    It does NOT extract concepts from user_input — that remains the role of
    process_text().

    Every generated concept, pattern, insight, and relationship carries
    provenance via `source` (the originating experience_id) and `metadata`.
    """

    def __init__(self) -> None:
        self._concept_counter = 0
        self._pattern_counter = 0
        self._insight_counter = 0
        self._relationship_counter = 0

    def transform(
        self,
        experiences: list[StructuredExperience],
    ) -> BridgeResult:
        """
        Transform a list of experiences into understanding inputs.

        Args:
            experiences: A list of StructuredExperience records.

        Returns:
            A BridgeResult containing concepts, patterns, insights, and
            relationships derived from the experiences.
        """
        if not experiences:
            return BridgeResult()

        concepts = self._extract_concepts(experiences)
        relationships = self._extract_relationships(experiences, concepts)
        patterns = self._detect_patterns(experiences, concepts)
        insights = self._generate_insights(experiences, concepts, patterns)

        return BridgeResult(
            concepts=concepts,
            patterns=patterns,
            insights=insights,
            relationships=relationships,
        )

    # ------------------------------------------------------------------
    # Concept extraction
    # ------------------------------------------------------------------

    def _extract_concepts(
        self,
        experiences: list[StructuredExperience],
    ) -> list[Concept]:
        """Extract concepts from structured experience fields."""
        concepts: list[Concept] = []

        for experience in experiences:
            source = experience.experience_id
            timestamp = experience.timestamp

            # Outcome concept
            concepts.append(self._create_concept(
                label=f"outcome:{experience.outcome.name.lower()}",
                domain=ConceptDomain.SYSTEM_METRIC,
                source=source,
                timestamp=timestamp,
                metadata={
                    "field": "outcome",
                    "outcome": experience.outcome.name,
                },
            ))

            # Capability concepts
            for capability in experience.reasoning_capabilities:
                if capability and capability.strip():
                    concepts.append(self._create_concept(
                        label=capability.strip(),
                        domain=ConceptDomain.TECHNICAL,
                        source=source,
                        timestamp=timestamp,
                        metadata={
                            "field": "reasoning_capability",
                            "outcome": experience.outcome.name,
                        },
                    ))

            # Planning goal concept
            if experience.planning_goal and experience.planning_goal.strip():
                concepts.append(self._create_concept(
                    label=experience.planning_goal.strip(),
                    domain=ConceptDomain.GENERAL,
                    source=source,
                    timestamp=timestamp,
                    metadata={
                        "field": "planning_goal",
                        "outcome": experience.outcome.name,
                    },
                ))

            # Tool name concept
            if experience.tool_name and experience.tool_name.strip():
                concepts.append(self._create_concept(
                    label=experience.tool_name.strip(),
                    domain=ConceptDomain.TECHNICAL,
                    source=source,
                    timestamp=timestamp,
                    metadata={
                        "field": "tool_name",
                        "outcome": experience.outcome.name,
                    },
                ))

        return concepts

    def _create_concept(
        self,
        label: str,
        domain: ConceptDomain,
        source: str,
        timestamp: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Concept:
        self._concept_counter += 1
        return Concept(
            concept_id=f"EXP-CON-{self._concept_counter:06d}",
            label=label,
            domain=domain,
            confidence=0.6,
            source=source,
            frequency=1,
            first_seen=timestamp,
            last_seen=timestamp,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Relationship extraction
    # ------------------------------------------------------------------

    def _extract_relationships(
        self,
        experiences: list[StructuredExperience],
        concepts: list[Concept],
    ) -> list[Relationship]:
        """Connect concepts within each experience."""
        relationships: list[Relationship] = []

        # Index concepts by originating experience for fast lookup
        concepts_by_source: dict[str, list[Concept]] = {}
        for concept in concepts:
            concepts_by_source.setdefault(concept.source, []).append(concept)

        for experience in experiences:
            exp_concepts = concepts_by_source.get(experience.experience_id, [])
            if not exp_concepts:
                continue

            outcome_concepts = [
                c for c in exp_concepts
                if c.metadata.get("field") == "outcome"
            ]
            capability_concepts = [
                c for c in exp_concepts
                if c.metadata.get("field") == "reasoning_capability"
            ]
            tool_concepts = [
                c for c in exp_concepts
                if c.metadata.get("field") == "tool_name"
            ]
            goal_concepts = [
                c for c in exp_concepts
                if c.metadata.get("field") == "planning_goal"
            ]

            # Capability → Outcome
            for cap in capability_concepts:
                for outcome in outcome_concepts:
                    rel_type = RelationshipType.CAUSES
                    if experience.outcome in (
                        ExperienceOutcome.FAILURE,
                        ExperienceOutcome.PARTIAL,
                    ):
                        rel_type = RelationshipType.CONTRADICTS
                    relationships.append(self._create_relationship(
                        source=cap,
                        target=outcome,
                        relationship_type=rel_type,
                        weight=0.6,
                    ))

            # Capability ↔ Tool
            for cap in capability_concepts:
                for tool in tool_concepts:
                    relationships.append(self._create_relationship(
                        source=cap,
                        target=tool,
                        relationship_type=RelationshipType.ASSOCIATED_WITH,
                        weight=0.5,
                    ))

            # Goal → Capability
            for goal in goal_concepts:
                for cap in capability_concepts:
                    relationships.append(self._create_relationship(
                        source=goal,
                        target=cap,
                        relationship_type=RelationshipType.DEPENDS_ON,
                        weight=0.5,
                    ))

        # Cross-experience contradiction detection for same capability
        capability_outcomes: dict[str, dict[str, list[Concept]]] = {}
        for concept in concepts:
            if concept.metadata.get("field") != "reasoning_capability":
                continue
            label = concept.label.lower().strip()
            outcome = concept.metadata.get("outcome", "")
            capability_outcomes.setdefault(label, {}).setdefault(outcome, []).append(concept)

        for label, outcome_map in capability_outcomes.items():
            if len(outcome_map) > 1:
                # Same capability produced different outcomes
                all_concepts = [
                    c for concepts_list in outcome_map.values() for c in concepts_list
                ]
                for i in range(len(all_concepts)):
                    for j in range(i + 1, len(all_concepts)):
                        c1, c2 = all_concepts[i], all_concepts[j]
                        if c1.metadata.get("outcome") != c2.metadata.get("outcome"):
                            relationships.append(self._create_relationship(
                                source=c1,
                                target=c2,
                                relationship_type=RelationshipType.CONTRADICTS,
                                weight=0.7,
                            ))

        return relationships

    def _create_relationship(
        self,
        source: Concept,
        target: Concept,
        relationship_type: RelationshipType,
        weight: float,
    ) -> Relationship:
        self._relationship_counter += 1
        return Relationship(
            source_id=source.concept_id,
            target_id=target.concept_id,
            relationship_type=relationship_type,
            weight=weight,
            confidence=min(source.confidence, target.confidence),
            observed_count=1,
            first_observed=datetime.now(),
            last_observed=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def _detect_patterns(
        self,
        experiences: list[StructuredExperience],
        concepts: list[Concept],
    ) -> list[Pattern]:
        """Detect patterns across the supplied experiences."""
        patterns: list[Pattern] = []

        # Outcome distribution pattern
        outcome_counts: dict[str, int] = {}
        for experience in experiences:
            outcome_counts[experience.outcome.name] = outcome_counts.get(experience.outcome.name, 0) + 1

        if len(outcome_counts) >= 1:
            dominant_outcome = max(outcome_counts, key=lambda k: outcome_counts[k])
            total = len(experiences)
            outcome_concepts = [
                c for c in concepts
                if c.metadata.get("field") == "outcome"
            ]
            related_ids = [c.concept_id for c in outcome_concepts[:10]]
            patterns.append(self._create_pattern(
                label=f"Outcome distribution: {dominant_outcome}",
                description=(
                    f"Across {total} experience(s), outcome '{dominant_outcome}' "
                    f"occurs {outcome_counts[dominant_outcome]} time(s)."
                ),
                confidence=round(outcome_counts[dominant_outcome] / total, 4) if total else 0.5,
                related_concept_ids=related_ids,
            ))

        # Capability trend patterns
        capability_stats: dict[str, dict[str, int]] = {}
        for experience in experiences:
            for capability in experience.reasoning_capabilities:
                if not capability or not capability.strip():
                    continue
                label = capability.strip()
                capability_stats.setdefault(label, {"SUCCESS": 0, "PARTIAL": 0, "FAILURE": 0, "SKIPPED": 0})
                capability_stats[label][experience.outcome.name] = (
                    capability_stats[label].get(experience.outcome.name, 0) + 1
                )

        for capability, stats in capability_stats.items():
            total = sum(stats.values())
            success_rate = stats.get("SUCCESS", 0) / total if total else 0.0
            failure_rate = (stats.get("FAILURE", 0) + stats.get("PARTIAL", 0)) / total if total else 0.0

            # Find related capability concepts
            related_ids = [
                c.concept_id for c in concepts
                if c.metadata.get("field") == "reasoning_capability"
                and c.label.lower().strip() == capability.lower().strip()
            ]
            related_ids = list(dict.fromkeys(related_ids))[:5]

            if success_rate >= 0.7:
                patterns.append(self._create_pattern(
                    label=f"Capability trend: {capability} succeeds",
                    description=(
                        f"Capability '{capability}' succeeded in {stats.get('SUCCESS', 0)} "
                        f"of {total} observed experience(s)."
                    ),
                    confidence=round(success_rate, 4),
                    related_concept_ids=related_ids,
                ))
            elif failure_rate >= 0.5:
                patterns.append(self._create_pattern(
                    label=f"Capability trend: {capability} fails",
                    description=(
                        f"Capability '{capability}' failed or partially succeeded in "
                        f"{stats.get('FAILURE', 0) + stats.get('PARTIAL', 0)} of {total} "
                        f"observed experience(s)."
                    ),
                    confidence=round(failure_rate, 4),
                    related_concept_ids=related_ids,
                ))

        return patterns

    def _create_pattern(
        self,
        label: str,
        description: str,
        confidence: float,
        related_concept_ids: list[str],
    ) -> Pattern:
        self._pattern_counter += 1
        return Pattern(
            pattern_id=f"EXP-PAT-{self._pattern_counter:06d}",
            label=label,
            description=description,
            confidence=round(confidence, 4),
            related_concept_ids=related_concept_ids,
            frequency=1,
            first_observed=datetime.now(),
            last_observed=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Insight generation
    # ------------------------------------------------------------------

    def _generate_insights(
        self,
        experiences: list[StructuredExperience],
        concepts: list[Concept],
        patterns: list[Pattern],
    ) -> list[UnderstandingInsight]:
        """Generate insights from experiences and detected patterns."""
        insights: list[UnderstandingInsight] = []

        # One insight per experience summarizing its execution
        for experience in experiences:
            related_ids = [
                c.concept_id for c in concepts
                if c.source == experience.experience_id
            ]
            insights.append(self._create_insight(
                category=UnderstandingCategory.TREND_INSIGHT,
                summary=(
                    f"Experience {experience.experience_id} had outcome "
                    f"{experience.outcome.name}."
                ),
                detail=self._build_experience_detail(experience),
                confidence=0.6,
                related_concept_ids=related_ids,
                source=experience.experience_id,
            ))

        # One insight per pattern
        for pattern in patterns:
            insights.append(self._create_insight(
                category=UnderstandingCategory.PATTERN_INSIGHT,
                summary=pattern.label,
                detail=pattern.description,
                confidence=pattern.confidence,
                related_concept_ids=pattern.related_concept_ids,
                related_pattern_ids=[pattern.pattern_id],
                source="experience_bridge",
            ))

        return insights

    def _build_experience_detail(self, experience: StructuredExperience) -> str:
        parts = [
            f"Pipeline path: {', '.join(experience.pipeline_path)}",
            f"Outcome: {experience.outcome.name}",
        ]
        if experience.reasoning_capabilities:
            parts.append(f"Capabilities: {', '.join(experience.reasoning_capabilities)}")
        if experience.planning_goal:
            parts.append(f"Planning goal: {experience.planning_goal}")
        if experience.tool_name:
            parts.append(f"Tool: {experience.tool_name}")
        return "; ".join(parts)

    def _create_insight(
        self,
        category: UnderstandingCategory,
        summary: str,
        detail: str,
        confidence: float,
        related_concept_ids: list[str],
        source: str,
        related_pattern_ids: list[str] | None = None,
    ) -> UnderstandingInsight:
        self._insight_counter += 1
        return UnderstandingInsight(
            insight_id=f"EXP-INS-{self._insight_counter:06d}",
            category=category,
            summary=summary,
            detail=detail,
            confidence=round(confidence, 4),
            related_concept_ids=related_concept_ids,
            related_pattern_ids=related_pattern_ids or [],
            source=source,
            timestamp=datetime.now(),
            metadata={"origin": "experience_bridge"},
        )
