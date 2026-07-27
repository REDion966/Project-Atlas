"""
Atlas Experience & Self-Model — Phase 9.1

Persistent experience accumulation and self-model evolution.
Captures every cognitive pipeline execution as a structured experience,
analyzes trends across executions, and provides evidence for gradual
identity evolution and improvement planning.

Pure logic. No AI providers. No infrastructure. No autonomous modification.
"""

from atlas.experience.models import (
    ExperienceOutcome,
    StructuredExperience,
    TrendAnalysis,
    SelfModelSnapshot,
    GoalOutcome,
)
from atlas.experience.storage_interface import ExperienceStorage, RestoreResult
from atlas.experience import serialization
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.trend_analyzer import TrendAnalyzer
from atlas.experience.outcome_tracker import OutcomeTracker
from atlas.experience.self_model_engine import SelfModelEngine

__all__ = [
    "ExperienceOutcome",
    "StructuredExperience",
    "TrendAnalysis",
    "SelfModelSnapshot",
    "GoalOutcome",
    "ExperienceStorage",
    "RestoreResult",
    "serialization",
    "ExperienceRepository",
    "ExperienceAccumulator",
    "TrendAnalyzer",
    "OutcomeTracker",
    "SelfModelEngine",
]
