"""
Atlas Lifecycle — Predefined Core Component Definitions.

Central registry of metadata for all core Atlas components.
ComponentRegistry uses these during kernel startup to register
each known component with its package, module path, dependencies,
and capabilities.

Phase 13.2 — Self Model Expansion.

This is a pure data file. No logic. No infrastructure.
"""

from atlas.lifecycle.models import ComponentMetadata

# ---------------------------------------------------------------------------
# Core component definitions
#
# Each entry defines one component that Atlas creates during startup.
# The actual instances are constructed in atlas/kernel/atlas.py; this
# file only provides the metadata that describes each component.
#
# When adding a new component to Atlas:
#   1. Add its ComponentMetadata here.
#   2. Register it in atlas/kernel/atlas.py using self._register_component().
# ---------------------------------------------------------------------------

CORE_COMPONENTS: list[ComponentMetadata] = [
    # ------------------------------------------------------------------
    # AI & Model Layer
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="ai_service",
        package="atlas.ai",
        module_path="atlas.ai.ai_manager.AIManager.service",
        description="AI provider abstraction and model routing service.",
        version=1,
        provided_capabilities=["ai_chat", "ai_stream", "model_routing"],
    ),
    ComponentMetadata(
        name="model_router",
        package="atlas.ai.routing",
        module_path="atlas.ai.routing.router.ModelRouter",
        description="Routes requests to the optimal AI model based on profile.",
        version=1,
        dependencies=["model_profile_registry"],
        provided_capabilities=["model_selection", "routing_decision"],
    ),
    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="memory_service",
        package="atlas.memory.service",
        module_path="atlas.memory.service.memory_manager_service.MemoryManagerService",
        description="Memory retrieval, search, ranking, and storage.",
        version=1,
        dependencies=["memory_repository", "ranking_engine", "search_engine"],
        provided_capabilities=["memory_search", "memory_store", "memory_ranking"],
    ),
    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="knowledge_manager",
        package="atlas.knowledge",
        module_path="atlas.knowledge.knowledge_manager.KnowledgeManager",
        description="Knowledge base querying and management.",
        version=1,
        provided_capabilities=["knowledge_query", "knowledge_store"],
    ),
    # ------------------------------------------------------------------
    # Understanding
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="understanding_engine",
        package="atlas.understanding",
        module_path="atlas.understanding.understanding_engine.UnderstandingEngine",
        description="Concept extraction, pattern detection, and insight generation.",
        version=1,
        dependencies=["understanding_storage"],
        provided_capabilities=[
            "concept_extraction",
            "pattern_detection",
            "insight_generation",
            "understanding_persistence",
        ],
    ),
    # ------------------------------------------------------------------
    # Reasoning Pipeline
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="reasoning_controller",
        package="atlas.reasoning",
        module_path="atlas.reasoning.controller.ReasoningController",
        description="Creates reasoning plans from cognitive decisions.",
        version=1,
        provided_capabilities=["reasoning_planning"],
    ),
    ComponentMetadata(
        name="capability_analyzer",
        package="atlas.reasoning.capabilities",
        module_path="atlas.reasoning.capabilities.analyzer.CapabilityAnalyzer",
        description="Analyzes reasoning plans to identify required capabilities.",
        version=1,
        dependencies=["reasoning_controller"],
        provided_capabilities=["capability_analysis"],
    ),
    ComponentMetadata(
        name="capability_router",
        package="atlas.reasoning.execution",
        module_path="atlas.reasoning.execution.routing.CapabilityRouter",
        description="Routes capabilities to registered handlers.",
        version=1,
        dependencies=["capability_registry"],
        provided_capabilities=["capability_routing"],
    ),
    ComponentMetadata(
        name="capability_dispatcher",
        package="atlas.reasoning.execution",
        module_path="atlas.reasoning.execution.dispatcher.CapabilityDispatcher",
        description="Dispatches capabilities to their registered handlers.",
        version=1,
        dependencies=["capability_registry"],
        provided_capabilities=["capability_execution"],
    ),
    ComponentMetadata(
        name="reasoning_recorder",
        package="atlas.reasoning.outcomes",
        module_path="atlas.reasoning.outcomes.ReasoningRecorder",
        description="Records reasoning outcomes for analysis and reflection.",
        version=1,
        provided_capabilities=["outcome_recording", "outcome_query"],
    ),
    ComponentMetadata(
        name="reflection_engine",
        package="atlas.reasoning",
        module_path="atlas.reasoning.reflection.ReflectionEngine",
        description="Analyzes reasoning outcomes to produce improvement suggestions.",
        version=1,
        dependencies=["reasoning_recorder"],
        provided_capabilities=["reflection_analysis"],
    ),
    ComponentMetadata(
        name="planning_engine",
        package="atlas.reasoning.planning",
        module_path="atlas.reasoning.planning.PlanningEngine",
        description="Decomposes goals into executable step sequences.",
        version=1,
        provided_capabilities=["plan_decomposition", "step_validation"],
    ),
    # ------------------------------------------------------------------
    # Tool Intelligence
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="tool_engine",
        package="atlas.tools",
        module_path="atlas.tools.engine.ToolEngine",
        description="Tool selection, execution, and result management.",
        version=1,
        dependencies=["tool_registry", "tool_selector", "tool_executor"],
        provided_capabilities=["tool_selection", "tool_execution", "tool_registration"],
    ),
    # ------------------------------------------------------------------
    # World Model
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="world_model_engine",
        package="atlas.world_model",
        module_path="atlas.world_model.world_model_engine.WorldModelEngine",
        description="Tracks entities, relations, and behavioral rules.",
        version=1,
        provided_capabilities=[
            "entity_tracking",
            "relation_tracking",
            "world_state_summary",
        ],
    ),
    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="learning_engine",
        package="atlas.learning_engine",
        module_path="atlas.learning_engine.learning_engine.LearningEngine",
        description="Extracts insights from pipeline execution data.",
        version=1,
        provided_capabilities=["pipeline_learning", "insight_extraction"],
    ),
    # ------------------------------------------------------------------
    # Identity & Self-Model
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="identity_engine",
        package="atlas.identity",
        module_path="atlas.identity.identity_engine.IdentityEngine",
        description="Maintains Atlas's long-term cognitive identity.",
        version=1,
        provided_capabilities=[
            "identity_snapshot",
            "belief_management",
            "capability_profiling",
            "decision_style",
        ],
    ),
    ComponentMetadata(
        name="experience_repository",
        package="atlas.experience",
        module_path="atlas.experience.experience_repository.ExperienceRepository",
        description="Stores and retrieves structured execution experiences.",
        version=1,
        dependencies=["experience_storage"],
        provided_capabilities=["experience_storage", "experience_query"],
    ),
    ComponentMetadata(
        name="self_model_engine",
        package="atlas.experience",
        module_path="atlas.experience.self_model_engine.SelfModelEngine",
        description="Produces self-model snapshots from accumulated experiences.",
        version=1,
        dependencies=["experience_repository", "trend_analyzer", "outcome_tracker"],
        provided_capabilities=["self_model", "trend_analysis", "goal_tracking"],
    ),
    ComponentMetadata(
        name="outcome_tracker",
        package="atlas.experience",
        module_path="atlas.experience.outcome_tracker.OutcomeTracker",
        description="Tracks recommendation and goal outcomes over time.",
        version=1,
        dependencies=["experience_repository"],
        provided_capabilities=["goal_outcome_tracking"],
    ),
    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="self_observation_engine",
        package="atlas.evolution",
        module_path="atlas.evolution.self_observation.SelfObservationEngine",
        description="Produces structured observations about Atlas's own behavior.",
        version=1,
        provided_capabilities=["runtime_observation", "metric_collection"],
    ),
    ComponentMetadata(
        name="improvement_planner",
        package="atlas.evolution",
        module_path="atlas.evolution.improvement_planner.ImprovementPlanner",
        description="Detects weaknesses from observations and creates improvement plans.",
        version=1,
        dependencies=["self_observation_engine"],
        provided_capabilities=["weakness_detection", "improvement_planning"],
    ),
    ComponentMetadata(
        name="evolution_memory",
        package="atlas.evolution",
        module_path="atlas.evolution.evolution_memory.EvolutionMemory",
        description="Stores evolution proposals, approvals, and execution records.",
        version=1,
        dependencies=["evolution_storage"],
        provided_capabilities=[
            "proposal_storage",
            "approval_storage",
            "evolution_history",
        ],
    ),
    ComponentMetadata(
        name="intelligence_engine",
        package="atlas.evolution",
        module_path="atlas.evolution.intelligence_engine.EvolutionIntelligenceEngine",
        description="Analyzes evolution proposals and produces insights.",
        version=1,
        dependencies=["evolution_memory", "experience_repository"],
        provided_capabilities=["proposal_analysis", "evolution_insight", "planner_feedback"],
    ),
    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    ComponentMetadata(
        name="runtime_coordinator",
        package="atlas.runtime",
        module_path="atlas.runtime.runtime_coordinator.RuntimeCoordinator",
        description="Single permanent orchestrator for all cognitive processing.",
        version=1,
        dependencies=[
            "understanding_engine",
            "world_model_engine",
            "reasoning_controller",
            "planning_engine",
            "tool_engine",
            "learning_engine",
            "identity_engine",
            "evolution_memory",
        ],
        provided_capabilities=[
            "cognitive_pipeline",
            "stage_orchestration",
            "cognitive_context",
        ],
    ),
    ComponentMetadata(
        name="goal_intelligence_engine",
        package="atlas.goals",
        module_path="atlas.goals.goal_intelligence_engine.GoalIntelligenceEngine",
        description="Analyzes evidence and generates improvement recommendations.",
        version=1,
        dependencies=["goal_repository"],
        provided_capabilities=["recommendation_generation", "opportunity_analysis"],
    ),
    ComponentMetadata(
        name="conversation_service",
        package="atlas.conversation",
        module_path="atlas.conversation.conversation_service.ConversationService",
        description="Manages conversation history and delegates to cognition pipeline.",
        version=1,
        dependencies=["ai_service", "context_engine", "cognition_api"],
        provided_capabilities=["conversation_management", "chat", "stream"],
    ),
]
