"""
Atlas Evolution — Development Planner — Phase E3

Converts an approved EvolutionProposal into a deterministic, ordered
DevelopmentPlan.

Responsibilities
----------------
* Accept only proposals whose status is ProposalStatus.APPROVED.
* Produce the same DevelopmentPlan every time for the same proposal.
* Generate seven lifecycle steps: inspect → define → identify →
  test_spec → implement → verify → accept.
* Extract affected-file hints from the proposal when available.
* Never execute code.
* Never manufacture authorization.
* Never bypass the approval lifecycle or the governance subsystem.

Pure logic component. No infrastructure. No AI. No side effects.
Phase E3 — Development Task Planner.
"""

from __future__ import annotations

from datetime import datetime

from atlas.evolution.development_models import (
    DevelopmentPlan,
    DevelopmentStep,
    StepPhase,
    StepStatus,  # noqa: F401
)
from atlas.evolution.models import EvolutionProposal, ProposalStatus

# Depth bound for repository impact expansion (dependents-of-dependents).
IMPACT_MAX_DEPTH: int = 3

# Suffix stripped when a file target is normalised into a dotted module query.
_MODULE_FILE_SUFFIXES: tuple[str, ...] = (".py",)


def _module_query(target: str) -> str:
    """Normalise an affected-file target into a dotted module query.

    A path (``atlas/evolution/development_planner.py``) becomes the dotted
    module (``atlas.evolution.development_planner``); an already-dotted name
    is returned unchanged. Pure token normalisation — no resolution is
    attempted here (that is the architecture model's ``locate()``).
    """
    text = str(target).strip().replace("\\", "/").lstrip("./")
    for suffix in _MODULE_FILE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.replace("/", ".").strip(".")


class DevelopmentPlannerError(Exception):
    """Raised when DevelopmentPlanner cannot produce a plan."""


class DevelopmentPlanner:
    """Converts an approved EvolutionProposal into an ordered DevelopmentPlan.

    Pure logic component — no infrastructure, no AI, no side effects.

    Governance contract
    -------------------
    * Only proposals with status == ProposalStatus.APPROVED are accepted.
    * An unapproved proposal raises DevelopmentPlannerError (fails closed).
    * The planner never calls the authorization or constraint subsystems.
    * The planner never constructs a sandbox executor or executes code.
    """

    def __init__(
        self,
        repository_map_provider=None,
        planning_context_provider=None,
        architecture_model_provider=None,
    ) -> None:
        """
        Initialise the planner.

        Args:
            repository_map_provider: Optional zero-argument callable
                returning an already-built ``RepositoryMap`` (or None).
                Stage C awareness-only validation: when a map is available,
                affected-file targets are checked against it and the
                dependency impact is expanded into plan metadata. The
                planner NEVER builds a map itself and never fails because
                of repository-validation problems — an absent map, a None
                snapshot, or a raising provider all preserve the historical
                behavior exactly.
            planning_context_provider: Optional zero-argument callable
                returning a bounded, JSON-safe ``PlanningContext``
                (Stage D) — attached verbatim as advisory
                ``metadata["planning_context"]`` on produced plans.
                Fail-soft: provider exceptions leave plans untouched.
            architecture_model_provider: Optional zero-argument callable
                returning an already-built ``ArchitectureModel`` (or None).
                WS4 self-knowledge integration: when a model is available,
                each affected target is resolved through the model's
                evidence-only ``locate()`` and the bounded architectural
                facts are attached as advisory
                ``metadata["architecture_evidence"]``. The planner NEVER
                builds or mutates a model itself and never fails because of
                it — an absent provider, a None snapshot, a non-model value,
                or a raising provider all preserve the historical behavior
                exactly. Advisory only: this evidence can never authorize,
                execute, schedule, promote, or activate anything.
        """
        self._repository_map_provider = repository_map_provider
        self._planning_context_provider = planning_context_provider
        self._architecture_model_provider = architecture_model_provider
        self._plan_counter = 0

    def plan(self, proposal: EvolutionProposal) -> DevelopmentPlan:
        """Produce an ordered DevelopmentPlan for an approved proposal.

        Args:
            proposal: An EvolutionProposal whose status is APPROVED.

        Returns:
            A DevelopmentPlan with seven ordered DevelopmentSteps.

        Raises:
            DevelopmentPlannerError: If the proposal is not APPROVED or
                is otherwise incomplete.
        """
        self._validate(proposal)
        plan_id = self._next_plan_id()
        affected_files = self._extract_affected_files(proposal)
        steps = self._build_steps(proposal, affected_files)
        development_plan = DevelopmentPlan(
            plan_id=plan_id,
            proposal_id=proposal.proposal_id,
            title=proposal.title,
            summary=proposal.summary,
            steps=steps,
            affected_files=affected_files,
        )

        # Stage C — impact-aware planning validation (awareness only).
        # The result is advisory metadata; it can never fail planning.
        validation = self._validate_targets_against_repository(affected_files)
        if validation is not None:
            development_plan.metadata["repository_validation"] = validation

        # Stage WS4 — self-knowledge integration: attach bounded, read-only
        # ArchitectureModel evidence for the plan's affected-file targets.
        # Advisory metadata only; it can never fail or authorize planning.
        architecture_evidence = self._build_architecture_evidence(affected_files)
        if architecture_evidence is not None:
            development_plan.metadata["architecture_evidence"] = (
                architecture_evidence
            )

        # Stage D — context-aware planning: attach the kernel-supplied
        # PlanningContext (evolution history, development outcomes,
        # repository impact) as advisory metadata. Fail-soft.
        if self._planning_context_provider is not None:
            try:
                context = self._planning_context_provider()
                # Accept either a plain dict or a PlanningContext object
                # (flattened to its JSON-safe metadata + confidence).
                if not isinstance(context, dict) and hasattr(
                    context, "metadata"
                ):
                    flattened = dict(getattr(context, "metadata", {}) or {})
                    flattened.setdefault(
                        "overall_confidence",
                        getattr(context, "overall_confidence", 0.0),
                    )
                    context = flattened
                if isinstance(context, dict) and context:
                    development_plan.metadata["planning_context"] = context
            except Exception:
                pass

        # Stage G — decision-quality scoring (advisory only). Synthesizes
        # the evidence already collected above (repository validation +
        # history/development/research context) into bounded scores.
        # Pure computation; can never fail planning.
        try:
            from atlas.evolution.decision_quality import (
                compute_decision_quality,
            )

            context_payload = development_plan.metadata.get(
                "planning_context", {}
            ) or {}
            validation = development_plan.metadata.get(
                "repository_validation", {}
            ) or {}
            research_section = context_payload.get("research") or {}

            quality = compute_decision_quality(
                overall_confidence=context_payload.get("overall_confidence"),
                previous_attempts=(
                    context_payload.get("history", {}).get(
                        "previous_attempts"
                    )
                ),
                unknown_target_count=len(validation.get("unknown_targets", [])),
                known_target_count=len(validation.get("known_targets", [])),
                dependency_count=int(validation.get("dependency_count", 0)),
                research_confidence=research_section.get("confidence"),
                has_research_claim_support=bool(
                    research_section.get("claim_count")
                ),
            )
            development_plan.metadata["decision_quality"] = quality
            # Mirror onto the proposal so downstream consumers (approval
            # surfaces, promotion reviews) see decision quality without
            # needing the plan object. Best-effort: proposals may be
            # lightweight stand-ins in some callers.
            proposal_metadata = getattr(proposal, "metadata", None)
            if isinstance(proposal_metadata, dict):
                proposal_metadata["decision_quality"] = quality
        except Exception:
            # Advisory scoring must never break planning.
            pass

        return development_plan

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_targets_against_repository(
        self,
        affected_files: list[str],
    ) -> dict | None:
        """
        Validate affected-file targets against the repository map.

        Stage C awareness-only layer. A target is *known* when it matches
        either a mapped module's dotted name or its relative path; known
        targets are expanded with their transitive dependents (impact).
        Unknown targets are preserved and reported — never dropped, never
        failed. Returns None when no repository context is available
        (no provider / None snapshot / provider failure), preserving the
        historical no-map behavior byte for byte.
        """
        if self._repository_map_provider is None:
            return None
        try:
            repository_map = self._repository_map_provider()
        except Exception:
            return None
        if repository_map is None:
            return None

        try:
            from atlas.research.repository_map import RepositoryMap

            if not isinstance(repository_map, RepositoryMap):
                return None

            path_to_module = {
                info.path: info.module for info in repository_map.modules
            }
            known_modules = set(path_to_module.values())

            known_targets: list[str] = []
            unknown_targets: list[str] = []
            resolved_modules: list[str] = []

            for target in affected_files:
                module = path_to_module.get(target)
                if module is None:
                    dotted = target.replace("/", ".").removesuffix(".py")
                    if dotted in known_modules:
                        module = dotted
                if module is not None:
                    known_targets.append(target)
                    resolved_modules.append(module)
                else:
                    unknown_targets.append(target)

            impact_expansion: set[str] = set()
            related_affected_files: set[str] = set()
            for module in dict.fromkeys(resolved_modules):
                for dependent in repository_map.impact_set(
                    module, max_depth=IMPACT_MAX_DEPTH
                ):
                    if dependent in resolved_modules:
                        continue
                    impact_expansion.add(dependent)
                    path = next(
                        (
                            info.path
                            for info in repository_map.modules
                            if info.module == dependent
                        ),
                        "",
                    )
                    if path:
                        related_affected_files.add(path)

            return {
                "known_targets": known_targets,
                "unknown_targets": unknown_targets,
                "impact_expansion": sorted(impact_expansion),
                "related_affected_files": sorted(related_affected_files),
                "dependency_count": len(impact_expansion),
            }
        except Exception:
            # Awareness must never break planning.
            return None

    def _build_architecture_evidence(
        self,
        affected_files: list[str],
    ) -> dict | None:
        """Project bounded, read-only ArchitectureModel evidence for targets.

        Stage WS4 self-knowledge integration. When an already-built
        ``ArchitectureModel`` is supplied, each affected target is resolved
        through the model's evidence-only ``locate()`` and the bounded
        architectural facts (matched kind, module, packages, components,
        dependencies, dependents, impact) are returned for advisory plan
        metadata.

        Returns None when no provider is wired, the provider yields None or a
        non-``ArchitectureModel``, the projection raises, or no target
        resolves — preserving the historical no-architecture behavior
        exactly. The model and repository are never mutated, and the returned
        evidence can never authorize, execute, schedule, promote, or activate
        anything.
        """
        if self._architecture_model_provider is None:
            return None
        try:
            architecture_model = self._architecture_model_provider()
        except Exception:
            return None
        if architecture_model is None:
            return None

        try:
            from atlas.self_knowledge.architecture_model import ArchitectureModel

            if not isinstance(architecture_model, ArchitectureModel):
                return None

            targets: list[dict] = []
            unresolved: list[str] = []
            for target in affected_files:
                located = architecture_model.locate(_module_query(target))
                if not located.found:
                    unresolved.append(target)
                    continue
                targets.append(
                    {
                        "target": target,
                        "query": located.query,
                        "matched_kind": located.matched_kind,
                        "module": located.module,
                        "packages": list(located.packages),
                        "components": list(located.components),
                        "module_paths": list(located.module_paths),
                        "dependencies": list(located.dependencies),
                        "dependents": list(located.dependents),
                        "impact": list(located.impact),
                    }
                )

            if not targets:
                # No architectural fact resolved for any target: omit the
                # section entirely, mirroring the historical absence rather
                # than attaching an empty projection.
                return None
            return {"targets": targets, "unresolved_targets": unresolved}
        except Exception:
            # Advisory self-knowledge must never break planning.
            return None

    def _validate(self, proposal: EvolutionProposal) -> None:
        # ``APPROVED`` is the OWNER (human) approval state; Phase 5 adds
        # ``SANDBOX_AUTHORIZED`` (bounded Development Envelope) as a DISTINCT
        # state that authorizes SANDBOX-only planning/execution. Neither
        # authorizes promotion.
        allowed = {ProposalStatus.APPROVED}
        sandbox_authorized = getattr(
            ProposalStatus, "SANDBOX_AUTHORIZED", ProposalStatus.APPROVED
        )
        allowed.add(sandbox_authorized)
        if proposal.status not in allowed:
            raise DevelopmentPlannerError(
                f"Cannot plan proposal '{proposal.proposal_id}': "
                f"status is {proposal.status.name!r}, expected 'APPROVED'."
            )
        if not proposal.proposal_id.strip():
            raise DevelopmentPlannerError(
                "Cannot plan a proposal with an empty proposal_id."
            )
        if not proposal.title.strip():
            raise DevelopmentPlannerError(
                f"Cannot plan proposal '{proposal.proposal_id}': title is empty."
            )

    def _next_plan_id(self) -> str:
        self._plan_counter += 1
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"DEVPLAN-{ts}-{self._plan_counter:04d}"

    def _extract_affected_files(self, proposal: EvolutionProposal) -> list[str]:
        explicit: list[str] = proposal.metadata.get("affected_files", [])
        if explicit and isinstance(explicit, list):
            return [str(f) for f in explicit if str(f).strip()]
        return list(proposal.plan.target_components or [])

    def _build_steps(
        self,
        proposal: EvolutionProposal,
        affected_files: list[str],
    ) -> list[DevelopmentStep]:
        return [
            self._step_inspect(proposal, affected_files),
            self._step_define(proposal),
            self._step_identify(affected_files),
            self._step_test_spec(proposal),
            self._step_implement(proposal, affected_files),
            self._step_verify(affected_files),
            self._step_accept(),
        ]

    # ------------------------------------------------------------------
    # Step builders
    # ------------------------------------------------------------------

    def _step_inspect(
        self, proposal: EvolutionProposal, affected_files: list[str]
    ) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-001",
            phase=StepPhase.INSPECT,
            order=1,
            objective=(
                f"Research the existing implementation relevant to"
                f" '{proposal.title}'. Identify current state, patterns,"
                f" and constraints."
            ),
            affected_files=list(affected_files),
        )

    def _step_define(self, proposal: EvolutionProposal) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-002",
            phase=StepPhase.DEFINE,
            order=2,
            objective=f"Define the intended change for '{proposal.title}'.",
            intent=proposal.implementation_approach,
            depends_on=["STEP-001"],
        )

    def _step_identify(self, affected_files: list[str]) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-003",
            phase=StepPhase.IDENTIFY,
            order=3,
            objective=(
                "Identify the exact files and resources that will be modified."
            ),
            affected_files=list(affected_files),
            depends_on=["STEP-002"],
        )

    def _step_test_spec(self, proposal: EvolutionProposal) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-004",
            phase=StepPhase.TEST_SPEC,
            order=4,
            objective=(
                f"Define the verification and test requirements for"
                f" '{proposal.title}'. Specify acceptance criteria."
            ),
            intent=(
                f"Verify: {proposal.expected_benefit}. "
                "Tests must pass before the change is accepted."
            ),
            depends_on=["STEP-003"],
        )

    def _step_implement(
        self, proposal: EvolutionProposal, affected_files: list[str]
    ) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-005",
            phase=StepPhase.IMPLEMENT,
            order=5,
            objective=(
                f"Implement '{proposal.title}' inside an E2 sandbox. "
                "Apply the code change through the E2 sandbox executor."
            ),
            intent=proposal.implementation_approach,
            affected_files=list(affected_files),
            depends_on=["STEP-004"],
        )

    def _step_verify(self, affected_files: list[str]) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-006",
            phase=StepPhase.VERIFY,
            order=6,
            objective=(
                "Run the verification probe defined in STEP-004. "
                "Confirm all affected files match the expected content."
            ),
            intent=(
                "If verification fails, the sandbox executor will automatically "
                "roll back to the prior snapshot."
            ),
            affected_files=list(affected_files),
            depends_on=["STEP-005"],
        )

    def _step_accept(self) -> DevelopmentStep:
        return DevelopmentStep(
            step_id="STEP-007",
            phase=StepPhase.ACCEPT,
            order=7,
            objective=(
                "Accept the verified change or confirm the rollback. "
                "Record the outcome for evolution memory."
            ),
            depends_on=["STEP-006"],
        )
