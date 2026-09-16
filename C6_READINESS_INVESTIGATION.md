# PROJECT ATLAS — C6 READINESS INVESTIGATION: KNOWLEDGE & LEARNING MATURITY

Mode: INVESTIGATION ONLY (no code/test/config/schema/governance/roadmap changes)

---

## 1. STATUS

**GENUINE C6 GAP EXISTS**

Atlas already possesses a broad, mostly production-wired knowledge/learning
pipeline (acquisition, verification, freshness, persistence, retrieval, learning
feedback). However, **Atlas's own knowledge representation and retrieval surface
is immature**: the knowledge stores Atlas actually retrieves from are
**in-memory, ephemeral, unvalidated, and provenance-free**, while the validated,
provenance-bearing, confidence-scored representation exists only inside the
research subsystem and is not unified with the knowledge surface used by the
cognition pipeline, the `knowledge_retrieval` capability, and the user-facing
deterministic fallback. One bounded candidate for the next step is identified
(§9, §14). Nothing was implemented.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree: pre-existing modified/untracked files + C3–C5 artifacts —
  unchanged by this investigation. No staged/deleted/renamed files.
- Relevant test baseline (run for this investigation):
  `tests/test_knowledge.py tests/test_knowledge_service.py tests/test_research_models.py tests/test_longterm_semantic_recall.py tests/test_persistent_learning.py tests/test_evolution_f2_knowledge_freshness.py`
  → **89 passed, 0 failed, 0 errors (exit 0)**.
- Reference: full suite (unchanged tree) 5876 passed / 0 failed / 0 errors / 2 skipped.

---

## 3. AUTHORITATIVE C6 OBJECTIVE

Reconstructed from the frozen Phase C roadmap (C6 = "Knowledge & Learning
Maturity") and the Atlas vision (`docs/ATLAS_VISION.md:72` "improvement is
systematic, evidence-driven") / model-independence directive
(`docs/ATLAS_STATE.md` §26): Atlas should be able to **acquire, validate,
retain, retrieve, and use knowledge**, with **provenance, confidence,
freshness, revision/staleness handling, and contradiction awareness**, through a
closed **USE → OBSERVE → EVIDENCE → VALIDATE → LEARN → RETAIN → RETRIEVE → USE**
loop, deterministically, model-independently, and read-only where possible.
External models are optional tools, never the source of Atlas's knowledge.

---

## 4. CURRENT KNOWLEDGE & LEARNING ARCHITECTURE

**Knowledge representation (two tiers):**

- **Thin/immature surface (used by production knowledge retrieval):**
  - `atlas/knowledge/knowledge_entry.py:11` `KnowledgeEntry` — fields: `title`,
    `content`, `source` **only** (no provenance/confidence/timestamp/validation).
  - `atlas/knowledge/knowledge_base.py:10` `KnowledgeBase` — in-memory
    `list[KnowledgeEntry]`; `add` (19), `all` (26). **No persistence, no dedup,
    no versioning, no revision.**
  - `atlas/knowledge/knowledge_manager.py:13` `KnowledgeManager` — `remember` (26),
    `query` (47).
  - `atlas/knowledge/knowledge_ranker.py:10` `KnowledgeRanker` — **no-op placeholder**
    ("Placeholder ranking system").
  - `atlas/learning/knowledge_store.py:8` `KnowledgeStore` — in-memory `list[str]`;
    wrapped by `atlas/learning/knowledge_feedback.py:10` `KnowledgeFeedback`
    (kernel-wired, fed by the learning stage).
- **Rich/validated tier (lives in research):**
  - `atlas/research/models.py:99` `KnowledgeClaim` — statement, citations,
    **`confidence`**, `extracted_at`.
  - `:122` `ClaimVerification` — `status` (`VerificationStatus`: UNVERIFIED/
    SUPPORTED/CONTRADICTED/AMBIGUOUS), `score`, `evidence_summary`, `verified_at`.
  - `:147` `CitationRecord` — `source_uri`, `source_kind`, `retrieved_at` (provenance).
  - Persisted: `research_claims`, `research_verifications`, `research_citations`
    (migration v7, `atlas/storage/migration.py:330`).

**Acquisition / validation:** `atlas/research/` planner (`planner.py:138`),
extractor (`extractor.py:57`, deterministic-first, optional model), verifier
(`verifier.py:92`, deterministic cross-source), coordinator (`coordinator.py:103`),
acquisition service (`acquisition.py:165`); F2 freshness assessor
(`atlas/evolution/freshness/assessor.py:59`, deterministic, never mutates);
F4/F5/F6 adaptation (`atlas/evolution/adaptation/*`; kernel
`run_adaptation_cycle` `atlas.py:779`, `generate_adaptation_proposals`
`atlas.py:703`, DRAFT-only, manually triggered).

**Memory / retention:** `atlas/memory/service/memory_manager_service.py:18`
(JSON-file persistence, `data/memory.json`); long-term learning
`atlas/longterm/*` (episodes/procedures, migration v9; semantic recall
`semantic_recall.py:157` deterministic; consolidation flags only).

**Learning / experience:** `atlas/learning_engine/learning_engine.py:27`,
`learning_memory.py:107` (**persistent**, `learning_insights`, migration v11);
`atlas/experience/self_model_engine.py:32`, `experience_repository.py:29`
(persistent). Learning from outcomes: `build_learning_insight`
(`atlas/evolution/self_development_loop.py:237`).

**Contradiction / revision:** `atlas/identity/belief_manager.py:97` `weaken_belief`
(contradictory evidence → lower confidence; `retire_belief` :135);
`atlas/advanced_reasoning/verify.py:227` contradiction check; F2 recommended
actions (`assessor.py:301`).

---

## 5. PRODUCTION REACHABILITY

| Mechanism | Reachability | Evidence |
|---|---|---|
| `KnowledgeManager` (thin KB) | **production reachable** | kernel `atlas.py:2503`, container `"knowledge"` `:3377`; pipeline stage `runtime_coordinator.py:413-425`; capability `knowledge_retrieval` `capability_handlers.py:27,71`; user-facing fallback `deterministic_fallback.py:119-123,195` |
| `KnowledgeFeedback`/`KnowledgeStore` | production reachable (write-only) | kernel `atlas.py:2516`; fed from learning stage `cognition/pipeline.py:619,622`, `runtime_coordinator.py:907,910` |
| Research pipeline (planner/extractor/verifier/coordinator/acquisition) | **production reachable** | kernel `atlas.py:2718-2749`, `888-934`; capabilities `research.*`; CLI `atlas research` |
| F2 freshness / F4-F6 adaptation | production reachable (manual/kernel) | `atlas.py:660,703,779` |
| Learning engine + persistent insights | **production reachable** | `atlas.py:2556-2559,2710-2715`; `learning_insights` v11 |
| Longterm episodes/procedures | **production reachable** | `atlas.py:2786-2818`; event-driven `:3431-3462` |
| Experience / self-model | production reachable | `atlas.py:3395-3397` |
| Learning → capability selection | production reachable | `analyzer.py:186` `_apply_learning_adjustment`, wired `atlas.py:2557` |
| DecisionIntelligence → planning | production reachable | `atlas.py:3071-3075`; `scheduler.py:275` |
| `KnowledgeRanker`, `KnowledgeIndex` | **dormant/placeholder** | no-op ranker; unused index |
| Legacy `atlas/memory/manager.py`, `memory_manager.py`, `agent_memory_service.py` | dormant duplicates | duplicate `MemoryManager`s; `AgentMemoryService` unreferenced |

---

## 6. EVIDENCE MATRIX

| Requirement | Evidence | Prod. reachability | Verification | Status | Notes |
|---|---|---|---|---|---|
| Knowledge representation | `KnowledgeEntry` (`knowledge_entry.py:11`) | yes | `test_knowledge.py` | **IMMATURE** | title/content/source only |
| Knowledge provenance | rich in `research/models.py:147`; absent on `KnowledgeEntry` | research yes; KB no | `test_research_models.py` | **PARTIAL/NOT UNIFIED** | provenance not on retrieval surface |
| Confidence | `KnowledgeClaim.confidence` (`:99`) | research yes; KB no | `test_research_models.py` | PARTIAL | not surfaced on retrieval |
| Validation | `ClaimVerification.status` (`:122`), `verifier.py:92` | research yes | `test_research_verifier.py` | EXISTS (research) | KB returns unvalidated entries |
| Information acquisition | `acquisition.py:165`, coordinator | yes | `test_phase21_*`, `test_evolution_f8_*` | SATISFIED | |
| Retention/persistence | `learning_insights` v11, episodes v9, research v7, experiences v1 | yes (research/longterm/learning) | storage tests | PARTIAL | **`atlas/knowledge` & `atlas/learning` stores have no persistence** |
| Retrieval | `knowledge_retrieval` (`capability_handlers.py:71`), semantic recall, memory query | yes | `test_longterm_semantic_recall.py`, `test_knowledge_service.py` | SATISFIED (mechanism) | retrieval surface is thin |
| Revision / invalidation | belief-level `belief_manager.py:97,135`; freshness flags `assessor.py:301`; governed appliers (`autonomy_wiring.py:161-164` writers include KNOWLEDGE/MEMORY) | kernel/governed | `test_identity.py`, `test_evolution_f2_*` | PARTIAL | no revision API on the KB |
| Contradiction detection | `advanced_reasoning/verify.py:227`; research `CONTRADICTED`; belief weaken/retire | yes (reasoning/belief) | `test_advanced_reasoning_verify.py` | PARTIAL | not applied to KB |
| Staleness/freshness | `KnowledgeFreshnessAssessor` (`assessor.py:59`) | kernel/manual | `test_evolution_f2_knowledge_freshness.py` | EXISTS (advisory) | |
| Learning from outcomes | `build_learning_insight` (`self_development_loop.py:237`), persistent insights | yes | `test_evolution_self_development_loop.py`, `test_persistent_learning.py` | SATISFIED | |
| Learning affects future behavior | `_apply_learning_adjustment` (`analyzer.py:186`) | yes | `test_phase20_batch4_learning_selection.py` | SATISFIED | closed loop present |

---

## 7. KNOWLEDGE / LEARNING LOOP ANALYSIS

`USE → OBSERVE → EVIDENCE → VALIDATE → LEARN → RETAIN → RETRIEVE → USE`

| Stage | Implemented | Deterministic | Prod. reachable | Tested | Real-world validated |
|---|---|---|---|---|---|
| USE | yes (pipeline/conversation) | yes | yes | yes | yes (C4) |
| OBSERVE | yes (`runtime_observations.py`, self-observation) | yes | yes | yes | partial |
| EVIDENCE | yes (`research/`, `EvolutionRecord`) | yes | yes | yes | partial |
| VALIDATE | yes (`research/verifier.py`, `advanced_reasoning/verify.py`, F2) | yes | yes | yes | partial |
| LEARN | yes (`learning_engine`, `build_learning_insight`) | yes | yes | yes | partial |
| RETAIN | yes (insights v11, episodes v9, research v7, experiences v1) — **but `atlas/knowledge`/`atlas/learning` stores are in-memory** | yes | yes (except the thin stores) | yes | partial |
| RETRIEVE | yes (`semantic_recall`, memory query, `knowledge_retrieval`) — **validated knowledge not on the general retrieval surface** | yes | yes | yes | partial |
| USE (feedback) | yes (`_apply_learning_adjustment`, `decision_intelligence`) | yes | yes | yes | partial |

The loop exists end-to-end. The weak link is **RETAIN/RETRIEVE of Atlas's own
general knowledge**: the store is ephemeral and unvalidated, and validated
knowledge is siloed in research.

---

## 8. MODEL-INDEPENDENCE ANALYSIS

Atlas-native deterministic: `atlas/knowledge/*`, `atlas/learning/*`,
`atlas/research/` (planner/extractor/verifier/coordinator/acquisition),
`atlas/evolution/freshness/*`, `atlas/longterm/*`, `atlas/learning_engine/*`,
`atlas/experience/*`, `atlas/identity/belief_manager.py`,
`advanced_reasoning/verify.py`, all migrations.

Optional external-tool (OFF by default, protocol-injected): `KnowledgeExtractor(model=…)`
(`extractor.py:60-67`), `ClaimVerifier(model=…)` (`verifier.py:95-101`, never
alters score), `SelfVerifier(verification_model=…)`, model-assisted authoring
(`atlas.py:958-964`), deny-by-default web adapter.

C6 requires **no** Ollama/Qwen/llama.cpp/OpenAI/Anthropic/Gemini, localhost
inference, API key, or network access. **PASS.**

---

## 9. C6 GAP ANALYSIS

**Genuine gap (one):** Atlas's **own knowledge representation and retrieval
surface is not validated, not provenance-bearing, and not retained**:

- `KnowledgeEntry` carries only `title`/`content`/`source`
  (`knowledge_entry.py:11-20`); `KnowledgeBase` is in-memory
  (`knowledge_base.py:10-30`); `KnowledgeStore` is an in-memory `list[str]`
  (`knowledge_store.py:8-26`).
- That surface is what production retrieval uses: the cognition
  KNOWLEDGE_RETRIEVAL stage (`runtime_coordinator.py:413-425`), the
  `knowledge_retrieval` capability (`capability_handlers.py:71-122`), and the
  user-facing deterministic fallback (`deterministic_fallback.py:119-123`).
- Atlas already has a validated, provenance-bearing, confidence-scored,
  **persisted** representation (`KnowledgeClaim`/`ClaimVerification`/`CitationRecord`,
  `research/models.py:99-160`; migration v7) that is **not unified** with that
  knowledge surface.

This is required by C6 ("validated knowledge", "provenance", "confidence",
"retention"), demonstrably absent on the knowledge surface, meaningful (Atlas
retrieves unvalidated, untraceable, non-durable knowledge), concrete, bounded,
and objectively verifiable — i.e. it passes the mission's gap test.

**Gap test:** the C6 objective requires it ✅; architecture demonstrably lacks it
✅; meaningful ✅; concrete evidence ✅; bounded ✅; objective verification ✅;
non-speculative ✅ (reuses the existing validated model); not C5/C7/C8/C9 ✅.

**Not claimed as gaps:** the absence of *silent* knowledge revision (governed
apply is the intended path), flag-only forgetting (intentional governed design),
and the dormant no-op `KnowledgeRanker` (a placeholder, not a required behavior).

---

## 10. BOUNDARY ANALYSIS

- **C5 (self-knowledge):** capability surface — not knowledge content. Rejected.
- **C7 (human understanding):** conversational self-Q&A / reference resolution /
  human-facing reasoning — rejected; C6 concerns knowledge representation,
  validation, retention, retrieval.
- **C8 (controlled autonomy):** no autonomy is required; C6.1 is read-only.
- **C9 (continuous evolution):** no continuous/autonomous evolution required.
- **Already satisfied (do not re-address):** research acquisition/verification,
  F2 freshness, learning engine + persistent insights, longterm episodes/
  procedures, experience/self-model, learning→selection feedback, adaptation
  orchestration.
- **Speculative/non-requirements:** a new semantic/embedding knowledge model,
  silent knowledge revision, a model-backed knowledge extractor by default,
  conversation-level knowledge NLU.

---

## 11. DEFECT ANALYSIS

**No C6-related defect found.** The thin/immature knowledge store is a design
choice (documented as an in-memory store), not a contract violation; no existing
behavior contradicts a documented contract. No unresolved failure; the 89
relevant tests passed.

---

## 12. VERIFICATION

- `python -m pytest tests/test_knowledge.py tests/test_knowledge_service.py tests/test_research_models.py tests/test_longterm_semantic_recall.py tests/test_persistent_learning.py tests/test_evolution_f2_knowledge_freshness.py -q`
  → **89 passed, 0 failed, 0 errors (exit 0)**, 10.8s.
- Source inspection with file:line evidence throughout (§4–§9).
- No failure, regression, or unexpected behavior observed.

---

## 13. READ-ONLY INTEGRITY

- Branch `main`; HEAD `f85de89` — unchanged before/after.
- No source/test/config/schema/persistence/governance/CLI/conversation changes;
  no commits/reset/clean/stash; no deletion/rename; no staged files.
- The only new artifact is this investigation report.

---

## 14. RECOMMENDATION

**DEFINE ONE BOUNDED C6.1** — candidate (not implemented, not authorized here):

**C6.1 (candidate) — Validated Knowledge Retrieval (deterministic, read-only).**
Make Atlas's knowledge retrieval surface return **validated, provenance-bearing,
confidence-labelled** knowledge derived deterministically from Atlas's existing
persistent validated stores (`research_claims` / `research_verifications` /
`research_citations`, and persistent `learning_insights`), reusing the existing
verification model — instead of only the ephemeral, unvalidated in-memory
`KnowledgeBase`/`KnowledgeStore` strings.

- **Exact production boundary:** the `knowledge_retrieval` capability + the
  cognition KNOWLEDGE_RETRIEVAL stage + the deterministic fallback knowledge path.
- **Required behavior:** each retrieved item exposes validation status,
  confidence, and provenance (source reference); results are derived from
  existing persisted evidence with **no newly invented knowledge**; deterministic
  ordering/reproducibility; fail-closed on no evidence.
- **Non-goals:** no new persistence/schema, no new NLP/NLU, no conversational
  self-Q&A (C7), no external model, no governance/authorization change, no
  autonomy, no merging of the memory/longterm/research subsystems.
- **Acceptance direction:** retrieval returns validation/confidence/provenance
  per item from existing stores; deterministic across repeated calls; read-only;
  model-independent; focused tests + a production accessor/CLI check; regression
  clean.
- **Why C6 (not C5/C7/C8/C9):** it concerns the trustworthiness and provenance of
  Atlas's own knowledge, not its capability surface, human understanding,
  autonomy, or continuous evolution.

If the owner prefers only the *retention* half of this gap, that is a separate
sub-decision (it would require additive persistence); it is deliberately **not**
bundled into the smallest C6.1 candidate above.

**Do not implement C6.1 without an explicit authorization command.**
