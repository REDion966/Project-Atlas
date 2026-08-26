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

    def __init__(self, repository_map_provider=None) -> None:
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
        """
        self._repository_map_provider = repository_map_provider
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

    def _validate(self, proposal: EvolutionProposal) -> None:
        if proposal.status != ProposalStatus.APPROVED:
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
