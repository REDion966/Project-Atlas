"""
AbstractionEngine — Phase 8.2.1

Converts multiple low-level concepts into higher-level abstractions.
This is deterministic and rule-based. No AI providers.

Examples:
  GPU, CUDA, TensorRT → AI Inference Stack
  Python, pytest, unittest → Testing Framework
  Memory, Knowledge, Understanding → Cognitive Architecture

Pure logic. Pattern-matching on known concept clusters.
"""

from typing import Any

from atlas.understanding.models import Concept, ConceptDomain


class AbstractionEngine:
    """
    Elevates multiple related low-level concepts into higher-level abstractions.

    Operates on predefined abstraction rules that map clusters of
    related concepts to parent abstractions. This is entirely
    deterministic — no AI, no model inference, no external calls.

    Each rule defines:
      - trigger_concepts: set of concept labels (case-insensitive)
      - min_matches: minimum number of trigger concepts required
      - abstraction_label: the name of the higher-level concept
      - abstraction_domain: the domain for the abstract concept
      - description: human-readable explanation
    """

    # Predefined abstraction rules
    RULES = [
        {
            "trigger_concepts": {"gpu", "cuda", "tensorrt", "nvidia", "deep learning", "inference"},
            "min_matches": 2,
            "abstraction_label": "AI Inference Stack",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Hardware and software stack for AI model inference",
        },
        {
            "trigger_concepts": {"python", "pytest", "unittest", "test", "testing", "mock", "coverage"},
            "min_matches": 2,
            "abstraction_label": "Testing Framework",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Software testing tools and methodologies",
        },
        {
            "trigger_concepts": {"memory", "knowledge", "understanding", "cognition", "reasoning"},
            "min_matches": 2,
            "abstraction_label": "Cognitive Architecture",
            "abstraction_domain": ConceptDomain.SYSTEM_METRIC,
            "description": "Atlas cognitive subsystem architecture",
        },
        {
            "trigger_concepts": {"architecture", "design", "pattern", "modular", "abstraction"},
            "min_matches": 2,
            "abstraction_label": "Software Architecture",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Software design principles and patterns",
        },
        {
            "trigger_concepts": {"identity", "belief", "principle", "preference", "style"},
            "min_matches": 2,
            "abstraction_label": "Self-Identity Model",
            "abstraction_domain": ConceptDomain.SYSTEM_METRIC,
            "description": "Atlas cognitive identity framework",
        },
        {
            "trigger_concepts": {"ollama", "openai", "anthropic", "lm studio", "provider", "model"},
            "min_matches": 2,
            "abstraction_label": "AI Provider Layer",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Multi-provider AI abstraction layer",
        },
        {
            "trigger_concepts": {"concept", "pattern", "relationship", "graph", "understanding"},
            "min_matches": 3,
            "abstraction_label": "Knowledge Graph",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Structured knowledge representation graph",
        },
        {
            "trigger_concepts": {"tool", "execution", "selector", "registry", "engine"},
            "min_matches": 2,
            "abstraction_label": "Tool Intelligence System",
            "abstraction_domain": ConceptDomain.TECHNICAL,
            "description": "Atlas tool selection and execution framework",
        },
    ]

    def __init__(self):
        self._abstraction_counter = 0

    def generate_abstractions(
        self,
        concepts: list[Concept],
    ) -> list[Concept]:
        """
        Analyze a list of concepts and generate higher-level abstractions.

        For each rule, if the concept set contains at least min_matches
        trigger concepts, an abstraction concept is created.

        Args:
            concepts: Current concepts to analyze for abstraction potential.

        Returns:
            List of newly generated abstract concepts (empty if none triggered).
        """
        if not concepts:
            return []

        # Build a set of existing concept labels (lowered)
        existing_labels = {c.label.lower().strip() for c in concepts}

        abstractions: list[Concept] = []

        for rule in self.RULES:
            triggers = {t.lower().strip() for t in rule["trigger_concepts"]}
            matches = existing_labels & triggers

            if len(matches) >= rule["min_matches"]:
                # Check if abstraction already exists
                abstract_label = rule["abstraction_label"]
                if abstract_label.lower() not in existing_labels:
                    self._abstraction_counter += 1
                    concept_id = f"ABS-{self._abstraction_counter:06d}"
                    abstraction = Concept(
                        concept_id=concept_id,
                        label=abstract_label,
                        domain=rule["abstraction_domain"],
                        confidence=self._calc_abstraction_confidence(matches),
                        source=f"abstraction_engine:matched={len(matches)}",
                        metadata={
                            "abstracted_from": sorted(list(matches)),
                            "rule_triggered": abstract_label,
                            "description": rule["description"],
                        },
                    )
                    abstractions.append(abstraction)

        return abstractions

    @staticmethod
    def _calc_abstraction_confidence(matched_concepts: set[str]) -> float:
        """
        Confidence in an abstraction scales with how many trigger
        concepts matched, but never reaches 1.0.
        """
        n = len(matched_concepts)
        if n <= 1:
            return 0.3
        if n <= 2:
            return 0.5
        if n <= 3:
            return 0.7
        return 0.85

    @property
    def abstraction_count(self) -> int:
        return self._abstraction_counter