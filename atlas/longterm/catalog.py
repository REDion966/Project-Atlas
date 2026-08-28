"""Atlas Long-Term Learning — Catalog & Constants (Track C, Batch 1).

Shared, pure constants describing the long-term learning ecosystem: episode
categories, procedure categories, consolidation operation names, and default
decay-policy values. Imported by the repositories, consolidator, and
capability handlers so discovery and consolidation can never drift apart.

No runtime dependencies beyond the standard library and the pure
``atlas.longterm.models`` enums.
"""

from __future__ import annotations

from atlas.longterm.models import (
    ConsolidationStatus,
    EpisodeKind,
    ProcedureKind,
)


# ---------------------------------------------------------------------------
# Episode categories (functional grouping)
# ---------------------------------------------------------------------------

#: Categories an episode may belong to.
EPISODE_CATEGORIES: frozenset[str] = frozenset(
    {
        "pipeline",
        "session",
        "task",
        "conversation",
        "research",
        "tool",
        "planning",
        "reasoning",
        "learning",
        "system",
    }
)

#: Default category when an episode does not declare one.
DEFAULT_EPISODE_CATEGORY: str = "pipeline"


# ---------------------------------------------------------------------------
# Procedure categories (functional grouping)
# ---------------------------------------------------------------------------

#: Categories a procedure may belong to.
PROCEDURE_CATEGORIES: frozenset[str] = frozenset(
    {
        "analysis",
        "research",
        "tool",
        "planning",
        "reasoning",
        "memory",
        "knowledge",
        "utility",
        "system",
    }
)

#: Default category when a procedure does not declare one.
DEFAULT_PROCEDURE_CATEGORY: str = "utility"


# ---------------------------------------------------------------------------
# Episode / procedure kind names (stable string identifiers)
# ---------------------------------------------------------------------------

EPISODE_KIND_NAMES: frozenset[str] = frozenset(
    {
        EpisodeKind.PIPELINE.name,
        EpisodeKind.SESSION.name,
        EpisodeKind.TASK.name,
    }
)

PROCEDURE_KIND_NAMES: frozenset[str] = frozenset(
    {
        ProcedureKind.DISTILLED.name,
        ProcedureKind.MANUAL.name,
    }
)

CONSOLIDATION_STATUS_NAMES: frozenset[str] = frozenset(
    {
        ConsolidationStatus.PENDING.name,
        ConsolidationStatus.APPLIED.name,
        ConsolidationStatus.REJECTED.name,
    }
)


# ---------------------------------------------------------------------------
# Consolidation operation names
# ---------------------------------------------------------------------------

#: Supported consolidation operations.
CONSOLIDATION_OPERATIONS: frozenset[str] = frozenset(
    {
        "merge",
        "dedup",
        "forget",
        "distill",
    }
)

#: Default consolidation operation.
DEFAULT_CONSOLIDATION_OPERATION: str = "merge"


# ---------------------------------------------------------------------------
# Decay-policy defaults
# ---------------------------------------------------------------------------

#: Default maximum number of episodes retained before consolidation.
DEFAULT_MAX_EPISODES: int = 10_000

#: Default maximum number of procedures retained before consolidation.
DEFAULT_MAX_PROCEDURES: int = 1_000

#: Default episode TTL in days (0 disables age-based forgetting).
DEFAULT_EPISODE_TTL_DAYS: int = 90

#: Default procedure TTL in days (0 disables age-based forgetting).
DEFAULT_PROCEDURE_TTL_DAYS: int = 180

#: Default minimum importance threshold for retention.
DEFAULT_MIN_IMPORTANCE: float = 0.1

#: Default minimum number of episodes sharing a pattern before a procedure
#: is distilled.
DEFAULT_CONSOLIDATION_THRESHOLD: int = 3

#: Default enabled state for consolidation/forgetting.
DEFAULT_CONSOLIDATION_ENABLED: bool = True


# ---------------------------------------------------------------------------
# ID prefixes
# ---------------------------------------------------------------------------

EPISODE_ID_PREFIX: str = "episode"
EVENT_ID_PREFIX: str = "event"
PROCEDURE_ID_PREFIX: str = "procedure"
STEP_ID_PREFIX: str = "pstep"
CONSOLIDATION_ID_PREFIX: str = "consol"