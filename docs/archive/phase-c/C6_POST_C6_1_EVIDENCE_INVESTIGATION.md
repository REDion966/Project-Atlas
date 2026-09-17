# PROJECT ATLAS — C6 POST-C6.1 EVIDENCE / NEXT-GAP INVESTIGATION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C6 IN PROGRESS — no Category-A gap identified; one bounded exposure/consumption
limitation found.**

C6.1 delivered validated-knowledge **retrieval**, but repository evidence shows the
validated-knowledge surface is **not consumed by any Atlas decision mechanism**
(only the read-only CLI reads it), while the paths that *do* consume "knowledge"
(cognition, reasoning evidence, fallback) read the legacy unvalidated in-memory
store. This is an **exposure/consumption limitation of an existing capability**, not
a missing core capability. Recommendation **C**.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`) — verified, **unchanged** by C6.1 (C6.1 added untracked files and modified tracked files, but no commit/tag).
- Working tree: pre-existing modified/untracked files + C3–C6.1 artifacts; no staged/deleted/renamed files.
- Relevant verification (this investigation): see §22.

---

## 3. C6 OBJECTIVE

C6 matures Atlas's knowledge/learning so it can **ACQUIRE → VALIDATE → RETAIN →
RETRIEVE → USE** knowledge with provenance, confidence, freshness awareness,
revision awareness, contradiction awareness, deterministically and model-independently,
driving evidence-backed decisions. The intended loop is
**USE → OBSERVE → EVIDENCE → VALIDATE → LEARN → RETAIN → RETRIEVE → USE**.

---

## 4. C6.1 VERIFIED BASELINE

Verified by source inspection (not assumption):

- `atlas/research/validated_retrieval.py` — `ValidatedKnowledgeRetriever.retrieve`
  (`:193`), `select_latest_verifications` (`:153`), `ValidatedKnowledgeItem`/
  `ValidatedKnowledgeResult`; `SUPPORTED`-only filtering; `claim_confidence` vs
  `verification_score` distinct; citations preserved; deterministic matching via
  `norm_alpha`/`significant_tokens`; ordering by `claim_id`; fail-closed
  (`store_unavailable`/`store_error`); read-only.
- Kernel `Atlas.validated_knowledge(query)` (`atlas/kernel/atlas.py:3560`) →
  `ValidatedKnowledgeRetriever(self._research_storage)`.
- CLI `atlas validated-knowledge [query] [--json]` (`atlas/cli/main.py:367,704,1071`;
  `atlas/cli/validated_knowledge_commands.py`).
- Persisted store: `research_claims`/`research_verifications`/`research_citations`
  (migration v7) with ordered reads (`storage/research_storage.py:201,246`).
- The **legacy general knowledge path is unchanged** (`KnowledgeManager`/`KnowledgeBase`
  untouched).

---

## 5. KNOWLEDGE / LEARNING ARCHITECTURE INVENTORY

| Mechanism | Represents | Persistent | Validated | Provenance | Confidence | Freshness | Revision | Contradiction | Deterministic | Prod. reachable | Used in loop | Tested | Real capability? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `atlas/knowledge` KB (`KnowledgeEntry/Base/Manager`) | free text (title/content/source) | **no** (in-memory) | no | no | no | no | no | no | yes | **yes** (cognition/fallback/evidence) | yes (as unvalidated) | yes | infra (thin) |
| `KnowledgeRanker` / `KnowledgeIndex` | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | yes | **no (dormant/placeholder)** | no | partial | not a capability |
| `atlas/learning` `KnowledgeStore`/`KnowledgeFeedback` | learned strings | **no** (in-memory) | no | no | no | no | no | no | yes | yes (write-only) | no | limited | infra |
| Research claims/verifications/citations | validated propositions + evidence | **yes** (v7) | **yes** | **yes** | **yes** (2 values) | timestamps only | latest-verification | statuses | yes | yes (C6.1 + coordinator) | **retrieved, not consumed** | yes | **real** |
| `LearningInsight` (`learning_engine`) | outcome insights | **yes** (v11) | no (insights) | limited | yes | no | consolidate | no | yes | yes | yes (capability selection) | yes | **real** |
| Longterm episodes/procedures | experiences/procedures | **yes** (v9) | no | limited | no | decay policy | consolidation flags | no | yes | yes | retrieval only | yes | **real** |
| Experience/self-model | performance self-model | **yes** (v1/v2) | n/a | n/a | yes | trends | no | no | yes | yes | prompt-context | yes | real |
| F2 freshness (`KnowledgeRef`/assessor) | freshness/staleness | read-only | n/a | yes (`claim_id`/`verification_id` fields) | yes | **yes** | recommended actions | via statuses | yes | yes (acquisition gate, adaptation) | gate only | yes | **real** |
| Identity `belief_manager` | beliefs | via identity | n/a | partial | yes | no | weaken/retire | **yes** | yes | yes | advisory | yes | real |
| Advanced-reasoning verifier | reasoning verification | yes (v10) | yes | evidence | yes | no | no | **yes** | yes | yes | reasoning | yes | real |
| `KnowledgeEvidenceProvider` (kernel `:247-268`) | knowledge→reasoning evidence seam | read-only | n/a | partial | no | no | no | no | yes | yes | **uses legacy KB** | yes | real (seam) |

---

## 6. COMPLETE KNOWLEDGE LOOP

| Stage | Status | Evidence |
|---|---|---|
| ACQUIRE | **SATISFIED** | research planner/extractor/coordinator/acquisition (`research/*`); deterministic-first, optional model |
| VALIDATE | **SATISFIED** | `ClaimVerifier` + `VerificationStatus` (`research/verifier.py`); reasoning verifier |
| LEARN | **SATISFIED (experience) / PARTIAL (from validated claims)** | `LearningEngine`, `build_learning_insight`; no learning derived from validated claims |
| RETAIN | **SATISFIED (research/learning/longterm) / IMMATURE (general KB)** | v7/v11/v9 persistence; general KB in-memory by design |
| RETRIEVE | **SATISFIED** | C6.1 validated retrieval; `memory.semantic_query`; `knowledge_retrieval` |
| USE | **PARTIAL** | general knowledge is consumed (cognition/evidence); **validated knowledge is not consumed** |
| FEEDBACK | **SATISFIED** | capability-selection learning adjustment (`reasoning/capabilities/analyzer.py:186`), F7 loop, DecisionIntelligence→planner |

---

## 7. ACQUISITION ANALYSIS

Deterministic-first acquisition exists: `ResearchPlanner` (`planner.py:138`),
`KnowledgeExtractor` (`extractor.py:57`, optional `ExtractionModel`), web adapter
deny-by-default. Production-wired (`atlas.py:2718-2749`; capability
`research.query`). Optional model assistance is injected and OFF by default.
**No gap.**

---

## 8. VALIDATION ANALYSIS

`ClaimVerifier` produces `VerificationStatus` (`UNVERIFIED`/`SUPPORTED`/`CONTRADICTED`;
`AMBIGUOUS` defined, not produced). Advanced-reasoning `SelfVerifier` checks
circularity/premises/contradiction. **Validation is a real, deterministic capability.
No gap.**

---

## 9. LEARNING ANALYSIS

Learning exists and is persistent: `LearningEngine.learn_from_pipeline`,
`build_learning_insight` (`evolution/self_development_loop.py:237`),
`LearningMemory` (`learning_insights`, v11). Learning **feeds behavior** via
`CapabilityAnalyzer._apply_learning_adjustment` (`analyzer.py:186`, wired
`atlas.py:2557`). **No gap** for experience-driven learning. (No learning is
derived from validated research claims — noted as a future integration, §11.)

---

## 10. RETENTION ANALYSIS

Validated research claims/verifications/citations persist (v7); learning insights
persist (v11); episodes/procedures persist (v9); experiences/self-model persist
(v1/v2). The **general `atlas/knowledge` KB is in-memory** (by design; documented).
Retention of validated knowledge is **SATISFIED**; the general KB's ephemerality is
a documented boundary, not a C6 requirement.

---

## 11. RETRIEVAL ANALYSIS

- **Legacy general retrieval:** `knowledge_retrieval` capability + cognition
  KNOWLEDGE_RETRIEVAL (`runtime_coordinator.py:413-425`) + fallback → thin,
  unvalidated, ephemeral entries.
- **Validated research retrieval (C6.1):** kernel accessor + CLI → `SUPPORTED`
  claims with provenance/confidence.
- **Learning insight retrieval:** `LearningMemory.get_insights`.
- **Longterm retrieval:** `memory.semantic_query`, episodes/procedures.

Retrieval is **SATISFIED** (multiple surfaces). The gap is not retrieval; it is that
validated retrieval has **no downstream consumer** (§12).

---

## 12. USE / FEEDBACK ANALYSIS

- **General knowledge IS used:** `KnowledgeEvidenceProvider` (`kernel/atlas.py:247-268`)
  supplies knowledge to advanced reasoning; cognition retrieves it; fallback uses it.
- **Validated knowledge is NOT used:** grep shows `validated_knowledge` /
  `ValidatedKnowledgeRetriever` are referenced only by the CLI and tests — **no
  cognition/reasoning/planning consumer**. So C6.1's validated retrieval is
  *exposed but not consumed*.
- **Feedback IS present:** learning→capability selection, F7, DecisionIntelligence.
  Research claims also feed the governed ingest bridge (`ResearchIngestBridge`).

This is the single material limitation: the C6 loop's **USE** stage for *validated*
knowledge is unmet.

---

## 13. FRESHNESS ANALYSIS

F2 exists and is deterministic (`evolution/freshness/assessor.py:59`); `KnowledgeRef`
already models `claim_id`/`verification_id` (`freshness/models.py:91-92,107-108`) and
the assessment carries them (`:159`). It is invoked by the acquisition gate
(`research/acquisition.py:270`) and the adaptation orchestrator
(`evolution/adaptation/orchestrator.py:231`). **No production caller constructs
`KnowledgeRef`s from persisted research claims**, so freshness cannot currently
flag a stale validated claim. Because the model already supports claim references,
this is an **application/exposure gap of an existing capability**, not a new one.

---

## 14. REVISION / CONTRADICTION ANALYSIS

- Verification history is preserved (append-only `research_verifications`).
- Current vs previous verification is distinguishable via the C6.1 latest-verification
  rule (`validated_retrieval.py:153`).
- Contradictory evidence is representable (`CONTRADICTED`, contradicting source URIs).
- Belief-level contradiction exists (`identity/belief_manager.py:97,135`); reasoning
  contradiction exists (`advanced_reasoning/verify.py:227`).
- **No cross-claim contradiction algorithm exists**; inventing one is prohibited.
  Distinguishing "conflicting claims" from "one claim's changed verification" is
  **not required** by the current C6 evidence boundary.

**No Category-A gap.** The append-only log + latest-verification rule already give
safe "current knowledge" semantics for validated retrieval.

---

## 15. C6.1 IMPACT ANALYSIS

- **New capability:** Atlas can now deterministically retrieve `SUPPORTED`
  validated research claims with provenance/confidence, read-only, fail-closed.
- **Newly retrievable evidence:** validation status, both confidence values,
  citations — previously not exposed as a knowledge retrieval surface.
- **Still inaccessible:** nothing exposes the legacy general KB as validated.
- **Meaningful new production capability?** Yes — a new validated, provenance-bearing
  retrieval surface (operator-reachable via kernel/CLI).
- **Revealed next-stage limitation:** the validated surface has **no consumer**;
  the legacy/validated separation is **neither a healthy boundary nor a defect** —
  it is an **integration/exposure opportunity** because the loop's USE stage for
  validated knowledge is unmet.

---

## 16. REAL-WORLD CAPABILITY EVIDENCE

From C3 (real-world capability evidence), C4 (impact-analysis exposure), C5
(capability model), C6.1 (validated retrieval), the demonstrated production
limitation that remains is: **Atlas can retrieve validated knowledge but cannot use
it** in any decision path; the only consumer is a read-only CLI. This is a
reproducible, meaningful limitation (an operator/component can retrieve validated
knowledge, but Atlas's own reasoning/cognition never benefits from it).

---

## 17. GAP CLASSIFICATION

| Candidate limitation | Category |
|---|---|
| Validated-knowledge surface not consumed by any decision mechanism | **B — existing capability, insufficiently exposed/consumed** |
| F2 freshness not applied to persisted research claims (model already supports `claim_id`) | **B — existing capability, insufficiently applied/exposed** |
| Legacy general KB ephemeral/unvalidated | **C — intentional boundary** (C6.1 Option B; documented) |
| Learning derived from validated claims | **C/E — future integration opportunity / speculative** |
| Conversational use of knowledge / self-Q&A | **D — C7** |
| Semantic/embedding retrieval | **E — speculative** |
| Cross-claim contradiction resolution | **E — speculative (no mechanism; prohibited to invent)** |
| General knowledge use, learning feedback, retention, acquisition, validation | **F — no gap** |

---

## 18. CATEGORY-A GAPS

**NO CATEGORY-A GAP IDENTIFIED.**

No missing *core* capability is evidenced: acquisition, validation, retention
(validated stores), retrieval (including C6.1), and learning feedback all exist and
are production-reachable; freshness and contradiction are represented. The material
limitations are **exposure/consumption of existing capabilities** (Category B),
not missing capabilities.

---

## 19. C6 BOUNDARY

C6 concerns knowledge/learning maturity: representation, validation, retention,
retrieval, and use of knowledge. The Category-B items (validated-knowledge
consumption; F2-over-claims) are within C6. The legacy KB's ephemerality is a
documented boundary; unifying it is not required by the current C6 objective.

---

## 20. C5/C7/C8/C9 BOUNDARY

- **C5:** CLOSED (capability model); not reopened (no defect found).
- **C7:** conversational knowledge interaction / self-Q&A / reference resolution —
  **excluded**.
- **C8:** autonomous action — **excluded** (recommendation is read-only/investigation).
- **C9:** continuous evolution — **excluded**.

---

## 21. MODEL-INDEPENDENCE

All findings are model-independent: validated retrieval, freshness, learning, and
retention are deterministic; optional models remain injected/OFF by default
(extractor/verifier). **No external LLM is required** for C6 or the recommended
bounded exposure investigation.

---

## 22. TEST / REGRESSION EVIDENCE

- `python -m pytest tests/test_validated_knowledge_retrieval.py tests/test_research_storage.py tests/test_research_verifier.py tests/test_knowledge_service.py tests/test_knowledge.py tests/test_persistent_learning.py tests/test_longterm_semantic_recall.py tests/test_evolution_f2_knowledge_freshness.py -q` → **129 passed, 0 failed, 0 errors (exit 0)**.
- C6.1 evidence (from its implementation report): focused **30**, relevant **230**,
  full suite **5906 / 0 failed / 0 errors / 2 skipped**.
- No failure observed; nothing to classify.

---

## 23. DEFECT ANALYSIS

**No defect found.** C6.1 verified intact; no contract contradiction; no regression;
no unresolved failure.

---

## 24. READ-ONLY INTEGRITY

- HEAD `f85de89` unchanged; no source/test/config/schema/persistence/governance/CLI/
  conversation/roadmap change; no staged files; no commit/reset/clean/stash;
  no deletion/rename. Only new artifact: this report.

---

## 25. RECOMMENDATION

**C. EXISTING CAPABILITY NEEDS EXPOSURE — INVESTIGATE BOUNDED EXPOSURE.**

**Exposure gap (why the underlying capability already exists):** C6.1 established a
deterministic, read-only validated-knowledge retrieval capability
(`ValidatedKnowledgeRetriever` + `Atlas.validated_knowledge` + CLI), and an existing
deterministic knowledge→reasoning seam already exists
(`KnowledgeEvidenceProvider`, `kernel/atlas.py:247-268`); F2 freshness already models
research `claim_id`/`verification_id` references. The gap is that **no Atlas decision
mechanism consumes the validated-knowledge surface** (only the CLI reads it), so the
loop's USE stage for validated knowledge is unmet.

**Bounded investigation to authorize next (do NOT implement now):**
- Objective: determine the smallest, deterministic, read-only way to expose/consume
  validated knowledge through an **existing** consumer seam (e.g. the existing
  `KnowledgeEvidenceProvider` reasoning-evidence seam, and/or applying the existing
  F2 assessor to persisted research claims).
- Scope: read-only; reuse existing machinery; do not modify the legacy KB behavior;
  no new persistence/schema; no model.
- Non-goals: legacy KB replacement, semantic search/embeddings, conversational
  knowledge (C7), cross-claim contradiction resolution, autonomous learning, C8/C9.
- Acceptance direction (future): a bounded consumer demonstrably uses SUPPORTED
  validated claims deterministically; preserves provenance/confidence; read-only;
  model-independent; existing behavior unchanged; objectively testable.
- This report only **recommends** a bounded exposure investigation. It does **not**
  authorize implementation and does **not** create C6.2.

---

## 26. REMAINING QUESTIONS

- Is consuming validated knowledge in reasoning/decision a C6 requirement or a
  Track-D/integration concern? (Evidence supports C6 "USE", but ownership of the
  consumer seam should be confirmed before authorization.)
- Should F2 freshness be applied to persisted research claims, and is that the
  smallest useful exposure step (vs the reasoning-evidence seam)?
- How to keep the bounded exposure strictly read-only and behavior-preserving for
  existing consumers.

These are contract questions for the next (investigation) step, not blockers to the
conclusion above.
