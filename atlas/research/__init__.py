"""Atlas Research Package (Phase 17.1–17.9, Track A).

Pure data models, source adapter layer, deterministic research planner,
knowledge extractor, claim verifier, SQLite storage protocol, capability
handlers, evolution ingest bridge (GOV-008), and lightweight wiring
metadata for Capability Track A.
"""

from atlas.research.capability_handlers import (
    ResearchCapabilityFactory,
    research_handlers,
)
from atlas.research.evolution_integration import (
    GOV_008_RULE_ID,
    IngestHandoffResult,
    ResearchEvolutionTracker,
    ResearchIngestBridge,
    ResearchIngestSink,
    register_gov_008,
)
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.acquisition import (
    AcquisitionPolicy,
    AcquisitionResult,
    InformationAcquisitionService,
    SourceEvidence,
    source_evidence,
)
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchPlan,
    ResearchReport,
    ResearchSource,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.research.planner import ResearchPlanner
from atlas.research.source_adapter import SourceAdapter
from atlas.research.sources import (
    CodebaseSourceAdapter,
    DocumentSourceAdapter,
    WebSourceAdapter,
    WorkspaceSourceAdapter,
)
from atlas.research.storage_protocol import ResearchStorage
from atlas.research.verifier import ClaimOutcome, ClaimVerifier
from atlas.research.wiring import (
    register_research_component,
    research_component,
    research_components,
)

__all__ = [
    # Models (17.1)
    "CitationRecord",
    "ClaimVerification",
    "KnowledgeClaim",
    "ResearchPlan",
    "ResearchReport",
    "ResearchSource",
    "SourceKind",
    "SourceProfile",
    "VerificationStatus",
    # Acquisition (F8)
    "AcquisitionPolicy",
    "AcquisitionResult",
    "InformationAcquisitionService",
    "SourceEvidence",
    "source_evidence",
    # Planner (17.3)
    "ResearchPlanner",
    # Source adapter layer (17.2)
    "SourceAdapter",
    "CodebaseSourceAdapter",
    "DocumentSourceAdapter",
    "WebSourceAdapter",
    "WorkspaceSourceAdapter",
    # Extractor (17.4)
    "KnowledgeExtractor",
    # Verifier (17.5)
    "ClaimOutcome",
    "ClaimVerifier",
    # Storage protocol (17.6)
    "ResearchStorage",
    # Capability handlers (17.7)
    "ResearchCapabilityFactory",
    "research_handlers",
    # Evolution integration (17.8)
    "GOV_008_RULE_ID",
    "IngestHandoffResult",
    "ResearchEvolutionTracker",
    "ResearchIngestBridge",
    "ResearchIngestSink",
    "register_gov_008",
    # Wiring (17.9)
    "register_research_component",
    "research_component",
    "research_components",
]
