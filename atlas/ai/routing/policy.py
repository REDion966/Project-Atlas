"""
Atlas Routing Policy

Pure logic for selecting the best model profile for a routing request.
"""

from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest


class RoutingPolicy:
    """
    Selects a model profile based on a routing request.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge, or
    interact with any service.
    """

    def select(
        self,
        request: RoutingRequest,
        profiles: list[ModelProfile],
    ) -> RoutingDecision | None:
        """
        Select the best matching model profile for the given request.

        The current policy matches profiles whose complexity_score is at
        least the request complexity, then selects the one with the lowest
        complexity_score above the threshold. If no profile matches the
        complexity requirement, the highest-priority profile is used as a
        fallback.

        Args:
            request: The routing request describing request needs.
            profiles: Available model profiles.

        Returns:
            A RoutingDecision with the selected provider/model and an
            ordered fallback chain, or None if no profiles are available.
        """

        if not profiles:
            return None

        # Sort by priority descending for fallback ordering.
        sorted_by_priority = sorted(
            profiles,
            key=lambda profile: profile.priority,
            reverse=True,
        )

        # Profiles whose complexity_score meets the request complexity.
        candidates = [
            profile
            for profile in sorted_by_priority
            if profile.complexity_score >= request.complexity
        ]

        if candidates:
            # Prefer the cheapest model that satisfies the requirement,
            # then by priority as a tie-breaker.
            selected = min(
                candidates,
                key=lambda profile: (
                    profile.complexity_score,
                    -profile.priority,
                ),
            )
            reason = (
                f"Selected {selected.model_name} from {selected.provider_name} "
                f"for complexity {request.complexity}"
            )
            confidence = 1.0
        else:
            # Fallback to the highest-priority profile.
            selected = sorted_by_priority[0]
            reason = (
                f"No profile matched complexity {request.complexity}; "
                f"falling back to {selected.model_name} from "
                f"{selected.provider_name}"
            )
            confidence = 0.5

        # Build fallback chain excluding the selected profile,
        # ordered by priority descending.
        fallback_chain = [
            (profile.provider_name, profile.model_name)
            for profile in sorted_by_priority
            if profile is not selected
        ]

        return RoutingDecision(
            provider_name=selected.provider_name,
            model_name=selected.model_name,
            confidence=confidence,
            reason=reason,
            fallback_chain=fallback_chain,
            metadata={
                "request_complexity": request.complexity,
                "selected_complexity": selected.complexity_score,
                "selected_priority": selected.priority,
            },
        )
