"""
AbstractionRegistry — Phase 8.2.1a

Dynamic rule registry for abstraction generation.
Replaces hardcoded rules with pluggable registration.
Deterministic, rule-based, no AI.

Supports:
  - rule registration
  - rule lookup
  - rule priority
  - future learning compatibility (external callers can add rules)
"""

from typing import Any

from atlas.understanding.models import Concept, ConceptDomain


class AbstractionRule:
    """A single abstraction rule."""

    def __init__(
        self,
        rule_id: str,
        abstraction_label: str,
        description: str,
        trigger_concepts: set[str],
        abstraction_domain: ConceptDomain = ConceptDomain.GENERAL,
        min_matches: int = 2,
        priority: int = 5,
    ):
        self.rule_id = rule_id
        self.abstraction_label = abstraction_label
        self.description = description
        self.trigger_concepts = {t.lower().strip() for t in trigger_concepts}
        self.abstraction_domain = abstraction_domain
        self.min_matches = max(1, min_matches)
        self.priority = max(1, min(10, priority))


class AbstractionRegistry:
    """
    Dynamic registry of abstraction rules.

    Rules are matched against concept sets to produce higher-level
    abstractions. Rules can be added, removed, and prioritized.
    Future learning systems can register new rules here.
    """

    DEFAULT_RULES: list[AbstractionRule] = [
        AbstractionRule("ABS-001", "AI Inference Stack", "Hardware/software stack for AI model inference",
                         {"gpu", "cuda", "tensorrt", "nvidia", "deep learning", "inference"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=7),
        AbstractionRule("ABS-002", "Testing Framework", "Software testing tools and methodologies",
                         {"python", "pytest", "unittest", "test", "testing", "mock", "coverage"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=6),
        AbstractionRule("ABS-003", "Cognitive Architecture", "Atlas cognitive subsystem architecture",
                         {"memory", "knowledge", "understanding", "cognition", "reasoning"},
                         ConceptDomain.SYSTEM_METRIC, min_matches=2, priority=8),
        AbstractionRule("ABS-004", "Software Architecture", "Software design principles and patterns",
                         {"architecture", "design", "pattern", "modular", "abstraction"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=6),
        AbstractionRule("ABS-005", "Self-Identity Model", "Atlas cognitive identity framework",
                         {"identity", "belief", "principle", "preference", "style"},
                         ConceptDomain.SYSTEM_METRIC, min_matches=2, priority=7),
        AbstractionRule("ABS-006", "AI Provider Layer", "Multi-provider AI abstraction layer",
                         {"ollama", "openai", "anthropic", "lm studio", "provider", "model"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=7),
        AbstractionRule("ABS-007", "Knowledge Graph", "Structured knowledge representation graph",
                         {"concept", "pattern", "relationship", "graph", "understanding"},
                         ConceptDomain.TECHNICAL, min_matches=3, priority=5),
        AbstractionRule("ABS-008", "Tool Intelligence System", "Atlas tool selection and execution framework",
                         {"tool", "execution", "selector", "registry", "engine"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=6),
        AbstractionRule("ABS-009", "Self-Improvement System", "Atlas feedback and evolution systems",
                         {"feedback", "learning", "evolution", "improvement", "reflection"},
                         ConceptDomain.SYSTEM_METRIC, min_matches=2, priority=7),
        AbstractionRule("ABS-010", "Data Persistence Layer", "Storage, memory, and persistence infrastructure",
                         {"storage", "memory", "repository", "database", "persistence"},
                         ConceptDomain.TECHNICAL, min_matches=2, priority=5),
    ]

    def __init__(self):
        self._rules: dict[str, AbstractionRule] = {}
        self._seed_defaults()
        self._abstraction_counter = 0

    def _seed_defaults(self) -> None:
        """Seed default abstraction rules."""
        for rule in self.DEFAULT_RULES:
            self._rules[rule.rule_id] = rule

    def register_rule(self, rule: AbstractionRule) -> None:
        """Register a new or updated abstraction rule."""
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if found."""
        return self._rules.pop(rule_id, None) is not None

    def get_rule(self, rule_id: str) -> AbstractionRule | None:
        return self._rules.get(rule_id)

    def list_rules(self) -> list[AbstractionRule]:
        """Return all rules sorted by priority (highest first)."""
        return sorted(self._rules.values(), key=lambda r: r.priority, reverse=True)

    def generate_abstractions(
        self,
        concepts: list[Concept],
    ) -> list[Concept]:
        """
        Generate abstraction concepts by matching rules against concept set.

        Args:
            concepts: Current concepts to analyze.

        Returns:
            List of newly generated abstract concepts.
        """
        if not concepts:
            return []

        existing_labels = {c.label.lower().strip() for c in concepts}
        abstractions: list[Concept] = []

        for rule in self.list_rules():
            matches = rule.trigger_concepts & existing_labels

            if len(matches) >= rule.min_matches:
                abstract_label = rule.abstraction_label
                if abstract_label.lower() not in existing_labels:
                    self._abstraction_counter += 1
                    concept_id = f"ABS-{self._abstraction_counter:06d}"
                    abstraction = Concept(
                        concept_id=concept_id,
                        label=abstract_label,
                        domain=rule.abstraction_domain,
                        confidence=self._calc_confidence(len(matches)),
                        source=f"abstraction_registry:{rule.rule_id}",
                        metadata={
                            "abstracted_from": sorted(list(matches)),
                            "rule_id": rule.rule_id,
                            "description": rule.description,
                            "priority": rule.priority,
                        },
                    )
                    abstractions.append(abstraction)
                    existing_labels.add(abstract_label.lower())

        return abstractions

    @staticmethod
    def _calc_confidence(n_matches: int) -> float:
        if n_matches <= 1:
            return 0.3
        if n_matches <= 2:
            return 0.5
        if n_matches <= 3:
            return 0.7
        return 0.85

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def abstraction_count(self) -> int:
        return self._abstraction_counter

    def summary(self) -> dict[str, Any]:
        return {
            "rules_registered": len(self._rules),
            "abstractions_generated": self._abstraction_counter,
        }