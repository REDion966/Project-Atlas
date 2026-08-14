"""Atlas Toolchain — Learned-Skill Authoring & Promotion (Phase 22, Batch 3).

Additive, in-memory authoring/promotion surface over the existing Track B
seams. No new governance layer and no persistence:

  * :class:`ToolSkillAuthor` — pure authoring surface: validates source
    material and builds a learned-skill candidate without activating,
    registering, executing, or persisting anything.
  * :class:`LearnedSkillCandidate` — in-memory candidate wrapping a
    ``DRAFT`` :class:`~atlas.toolchain.models.Skill` (``SkillKind.LEARNED``)
    with the source chain/steps/strategy preserved.
  * :class:`SkillPromotionRequest` — the deterministic intent to promote a
    candidate.
  * :class:`LearnedSkillPromoter` — routes activation EXCLUSIVELY through
    the existing :class:`~atlas.toolchain.evolution_integration.ToolchainIngestBridge`
    (GOV-009). Without a governed sink the promotion fails closed; the
    candidate is never registered, never persisted, and never mutated.

Candidate lifecycle (strictly separated states):

    chain / ToolLearningRecommendation
        → ToolSkillAuthor            (validate; build DRAFT LEARNED candidate)
        → LearnedSkillCandidate      (in-memory; unregistered)
        → SkillPromotionRequest      (pure intent; no I/O)
        → LearnedSkillPromoter       → ToolchainIngestBridge → GOV-009
        → Phase 16 governed pipeline decides activation/mutation

Authoring NEVER executes tools, NEVER touches :class:`SkillRegistry`, and
NEVER persists. Promotion NEVER calls ``SkillRegistry.register()`` /
``activate()`` and NEVER calls storage directly — the only mutation path is
the governed sink's ``EvolutionRequest``. Candidate construction is pure:
identical source always yields identical candidate ids and logical fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.toolchain.evolution_integration import (
    IngestHandoffResult,
    ToolchainIngestBridge,
)
from atlas.toolchain.learner import ToolLearningRecommendation
from atlas.toolchain.models import Skill, SkillKind, SkillStatus, ToolChain

#: Identifier prefix for authored learned-skill candidates.
CANDIDATE_ID_PREFIX: str = "candidate::"
#: Identifier prefix for promotion requests.
PROMOTION_REQUEST_ID_PREFIX: str = "promote::"
#: Metadata marker proving a skill was authored by this surface.
AUTHORED_MARKER: str = "tool_skill_author"


# ---------------------------------------------------------------------------
# Candidate / request models (pure, frozen, slots)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LearnedSkillCandidate:
    """An in-memory learned-skill candidate produced by the authoring surface.

    The wrapped skill is always ``SkillKind.LEARNED`` with
    ``SkillStatus.DRAFT`` — authoring never activates. The source
    chain/steps/strategy are preserved verbatim so the learned behavior can
    be reproduced exactly.
    """

    candidate_id: str
    skill: Skill
    source_chain_id: str
    source_strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillPromotionRequest:
    """The deterministic intent to promote a learned-skill candidate.

    Pure intent: building this object performs no I/O, no governance, and no
    mutation. Activation itself is owned by the governed ingest path.
    """

    request_id: str
    candidate_id: str
    skill_id: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Authoring surface
# ---------------------------------------------------------------------------


class ToolSkillAuthor:
    """Pure authoring surface for learned-skill candidates.

    Two deterministic entry points:

      * :meth:`author_from_chain` — author from any validated
        :class:`ToolChain` (sequential, fallback, conditional, or parallel;
        the chain is preserved verbatim).
      * :meth:`author_from_learn` — author from an existing
        :class:`ToolLearningRecommendation` emitted by the
        :class:`~atlas.toolchain.learner.ToolLearner` (the ``learn_skill``
        action carries the LEARNED skill candidate).

    Authoring never runs tools, never registers skills, and never persists.
    Malformed/incomplete input is rejected deterministically with
    ``ValueError``.
    """

    # ------------------------------------------------------------------
    # Public authoring
    # ------------------------------------------------------------------

    def author_from_learn(
        self,
        recommendation: ToolLearningRecommendation,
    ) -> LearnedSkillCandidate:
        """Author a candidate from a learner recommendation.

        Reuses the existing :class:`ToolLearningRecommendation` model — no
        second recommendation model is introduced. The recommendation's
        embedded skill must be present and ``SkillKind.LEARNED``; its chain
        is preserved verbatim.

        Args:
            recommendation: A learner output (typically the ``learn_skill``
                action carrying a skill).

        Returns:
            The authored in-memory candidate.

        Raises:
            ValueError: If the recommendation is missing, carries no skill,
                or the skill is malformed / not a learned skill.
        """
        if recommendation is None:
            raise ValueError("recommendation is required")
        skill: Skill | None = recommendation.skill
        if skill is None:
            raise ValueError(
                "recommendation carries no skill candidate "
                "(expected a learn_skill recommendation)"
            )
        self._validate_skill(skill)

        metadata: dict[str, Any] = dict(skill.metadata or {})
        metadata["source_recommendation_id"] = recommendation.recommendation_id
        metadata["learned"] = True
        draft: Skill = _with_metadata(
            _with_status(skill, SkillStatus.DRAFT),
            metadata,
        )
        source_chain_id: str = str(
            skill.metadata.get("source_chain_id") or recommendation.chain_id
        )
        source_strategy: str = (
            draft.chain.strategy if draft.chain is not None else "sequential"
        )
        return LearnedSkillCandidate(
            candidate_id=f"{CANDIDATE_ID_PREFIX}{draft.skill_id}",
            skill=draft,
            source_chain_id=source_chain_id,
            source_strategy=source_strategy,
            metadata=dict(metadata),
        )

    def author_from_chain(
        self,
        chain: ToolChain,
        *,
        skill_id: str,
        name: str,
        description: str = "",
        category: str = "toolchain",
    ) -> LearnedSkillCandidate:
        """Author a candidate from a validated source chain.

        Args:
            chain: The source :class:`ToolChain` to preserve verbatim
                (steps and strategy).
            skill_id: Non-empty deterministic skill id for the candidate.
            name: Non-empty human-readable skill name.
            description: Optional skill description.
            category: Optional category for the skill.

        Returns:
            The authored in-memory candidate.

        Raises:
            ValueError: If the chain is malformed/incomplete or required
                fields are missing.
        """
        if chain is None:
            raise ValueError("chain is required")
        if not skill_id or not skill_id.strip():
            raise ValueError("skill_id is required")
        if not name or not name.strip():
            raise ValueError("name is required")
        self._validate_chain(chain)

        skill = Skill(
            skill_id=skill_id.strip(),
            name=name.strip(),
            description=description,
            kind=SkillKind.LEARNED,
            category=category,
            chain=chain,
            status=SkillStatus.DRAFT,
            metadata={
                "source_chain_id": chain.chain_id,
                "learned": True,
                "authored": AUTHORED_MARKER,
            },
        )
        return LearnedSkillCandidate(
            candidate_id=f"{CANDIDATE_ID_PREFIX}{skill.skill_id}",
            skill=skill,
            source_chain_id=chain.chain_id,
            source_strategy=chain.strategy,
            metadata={"authored": AUTHORED_MARKER},
        )

    # ------------------------------------------------------------------
    # Validation (deterministic rejection)
    # ------------------------------------------------------------------

    @classmethod
    def validate_skill(cls, skill: Skill) -> None:
        """Validate a learned-skill candidate skill (public helper)."""
        cls._validate_skill(skill)

    @staticmethod
    def _validate_skill(skill: Skill) -> None:
        """Validate the required shape of a LEARNED skill candidate.

        Raises:
            ValueError: On any malformed/incomplete field.
        """
        if skill is None:
            raise ValueError("skill is required")
        if not skill.skill_id or not skill.skill_id.strip():
            raise ValueError("skill.skill_id is required")
        if not skill.name or not skill.name.strip():
            raise ValueError("skill.name is required")
        if skill.kind is not SkillKind.LEARNED:
            raise ValueError(
                f"skill.kind must be SkillKind.LEARNED, got {skill.kind!r}"
            )
        if skill.chain is None:
            raise ValueError("skill.chain is required for a learned skill")
        ToolSkillAuthor._validate_chain(skill.chain)

    @staticmethod
    def _validate_chain(chain: ToolChain) -> None:
        """Validate the preserved source chain.

        Raises:
            ValueError: On malformed/incomplete chain or steps.
        """
        if not chain.steps:
            raise ValueError("chain.steps must not be empty")
        seen: set[str] = set()
        for step in chain.steps:
            if not step.step_id or not step.step_id.strip():
                raise ValueError("every step requires a non-empty step_id")
            if not step.tool_name or not step.tool_name.strip():
                raise ValueError(
                    f"step '{step.step_id or '<unknown>'}' requires a tool_name"
                )
            if step.step_id in seen:
                raise ValueError(
                    f"duplicate step_id '{step.step_id}' in chain"
                )
            seen.add(step.step_id)


# ---------------------------------------------------------------------------
# Promotion surface
# ---------------------------------------------------------------------------


class LearnedSkillPromoter:
    """Hands a learned-skill candidate to the governed evolution path.

    Promotion is strictly separated from activation:

      1. :meth:`request_promotion` builds the deterministic
         :class:`SkillPromotionRequest` (pure intent; no I/O).
      2. :meth:`promote` hands the candidate through the existing
         :class:`ToolchainIngestBridge` (GOV-009). Without a wired governed
         sink the promotion FAILS CLOSED — the candidate is never
         registered, never persisted, and never mutated.

    This surface NEVER calls ``SkillRegistry.register()`` / ``activate()``
    and NEVER calls storage or the gateway directly — activation is owned by
    the Phase 16 governed pipeline.
    """

    def __init__(self, bridge: ToolchainIngestBridge | None = None) -> None:
        """Initialise the promoter with the governed ingest bridge.

        Args:
            bridge: The :class:`ToolchainIngestBridge` (GOV-009) used for
                activation hand-off. If ``None``, an unwired bridge is
                created — promotion fails closed until a sink is injected.
        """
        self._bridge = bridge or ToolchainIngestBridge()

    @property
    def bridge(self) -> ToolchainIngestBridge:
        """The governed ingest bridge used for promotion hand-off."""
        return self._bridge

    @property
    def has_sink(self) -> bool:
        """True when the governed ingest sink is wired."""
        return self._bridge.has_sink

    @staticmethod
    def request_promotion(
        candidate: LearnedSkillCandidate,
    ) -> SkillPromotionRequest:
        """Build the deterministic intent to promote a candidate.

        Pure: no I/O, no governance, no mutation.

        Args:
            candidate: The in-memory candidate to promote.

        Returns:
            The :class:`SkillPromotionRequest`.

        Raises:
            ValueError: If the candidate is missing or its skill is not a
                promotable DRAFT learned skill.
        """
        if candidate is None:
            raise ValueError("candidate is required")
        skill: Skill = candidate.skill
        if skill.kind is not SkillKind.LEARNED:
            raise ValueError(
                f"candidate skill.kind must be SkillKind.LEARNED, "
                f"got {skill.kind!r}"
            )
        if skill.status is not SkillStatus.DRAFT:
            raise ValueError(
                f"candidate skill.status must be DRAFT to promote, "
                f"got {skill.status!r}"
            )
        return SkillPromotionRequest(
            request_id=f"{PROMOTION_REQUEST_ID_PREFIX}{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            skill_id=skill.skill_id,
            reason=(
                f"Promote learned skill candidate '{candidate.candidate_id}' "
                "through the governed ingest path."
            ),
            metadata={
                "source_chain_id": candidate.source_chain_id,
                "source_strategy": candidate.source_strategy,
            },
        )

    def promote(self, candidate: LearnedSkillCandidate) -> IngestHandoffResult:
        """Submit the candidate's activation through GOV-009.

        The governed request is built and handed through the existing
        :class:`ToolchainIngestBridge`. Without a wired sink this returns
        ``accepted=False`` (fail closed); the candidate is never
        registered/persisted/mutated by this surface.

        Args:
            candidate: The in-memory candidate to promote.

        Returns:
            The :class:`IngestHandoffResult` from the governed bridge — the
            existing result model; no new result type is introduced.
        """
        self.request_promotion(candidate)  # validates intent deterministically
        return self._bridge.ingest(candidate.skill)


# ---------------------------------------------------------------------------
# Helpers (frozen-dataclass transition)
# ---------------------------------------------------------------------------


def _with_status(skill: Skill, status: SkillStatus) -> Skill:
    """Return a copy of ``skill`` with a new ``status``.

    Skills are frozen dataclasses; this helper performs a non-mutating
    status transition by reconstructing the dataclass with all original
    fields except ``status``. Mirrors ``registry._with_status``.
    """
    return Skill(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        kind=skill.kind,
        category=skill.category,
        tool_name=skill.tool_name,
        chain=skill.chain,
        tags=skill.tags,
        status=status,
        created_at=skill.created_at,
        metadata=skill.metadata,
    )


def _with_metadata(skill: Skill, metadata: dict[str, Any]) -> Skill:
    """Return a copy of ``skill`` with new ``metadata``.

    Non-mutating reconstruction for frozen skills, preserving every other
    field.
    """
    return Skill(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        kind=skill.kind,
        category=skill.category,
        tool_name=skill.tool_name,
        chain=skill.chain,
        tags=skill.tags,
        status=skill.status,
        created_at=skill.created_at,
        metadata=dict(metadata),
    )
