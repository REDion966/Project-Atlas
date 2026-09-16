# PROJECT ATLAS — C6.1 VALIDATED KNOWLEDGE RETRIEVAL — SCOPE & CONTRACT INVESTIGATION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C6.1 SCOPE NOT VALIDATED (REFINE REQUIRED)**

The candidate is **real, bounded, and implementable with existing mechanisms** —
the authoritative validated knowledge is already persisted with deterministic read
APIs, provenance, confidence, and a validation status enum. However, the candidate
as stated (integrate validated retrieval into the **existing** `knowledge_retrieval`
capability / cognition KNOWLEDGE_RETRIEVAL stage / deterministic fallback) carries
**unresolved contract decisions** (source set and reconciliation, integration
surface, confidence surfacing, matching semantics, freshness scope, conflict
handling). Per the recommendation rule, this is **B. REFINE C6.1 SCOPE**, not A.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree: pre-existing modified/untracked files + C3–C6 artifacts —
  unchanged by this investigation. No staged/deleted/renamed files.
- Relevant test baseline (run for this investigation):
  `python -m pytest tests/test_research_models.py tests/test_research_storage.py tests/test_research_verifier.py tests/test_research_evidence_summary.py tests/test_knowledge.py tests/test_knowledge_service.py tests/test_learning_engine.py tests/test_persistent_learning.py tests/test_phase21_research_feedback.py -q`
  → **135 passed, 0 failed, 0 errors (exit 0)**.
- Reference: full suite (unchanged tree) 5876 / 0 failed / 0 errors / 2 skipped.

---

## 3. C6.1 OBJECTIVE

Make Atlas's production knowledge-retrieval surface return **validated,
provenance-bearing, confidence-labelled** knowledge derived deterministically from
Atlas's **existing persistent validated knowledge stores**, instead of depending
only on the ephemeral, unvalidated in-memory `KnowledgeBase`/`KnowledgeStore`.
(Per the C6 readiness investigation, `C6_READINESS_INVESTIGATION.md` §9.)

---

## 4. AUTHORITATIVE KNOWLEDGE SOURCES

| Source | Stores | Persistent | Validated | Provenance | Confidence | Freshness | Production reachable | Deterministic | Read-only safe |
|---|---|---|---|---|---|---|---|---|---|
| `research_claims` (`atlas/research/models.py:99` `KnowledgeClaim`) | claim statement, confidence, citations, extracted_at | **yes** (migration v7, `atlas/storage/migration.py:330`; adapter `atlas/storage/research_storage.py:35`) | via `research_verifications` | **yes** (citations attached on load, `research_storage.py:206-218`) | `KnowledgeClaim.confidence` | timestamp `extracted_at` (no F2 wiring) | **yes** (coordinator persists; acquisition reads reports) | **yes** (`load_claims` ordered `extracted_at ASC, claim_id ASC`, `research_storage.py:201-204`) | **yes** (pure SELECT) |
| `research_verifications` (`models.py:122` `ClaimVerification`) | status, score, evidence_summary, verified_at | **yes** (v7) | **yes** (`VerificationStatus`) | evidence summary + metadata | `ClaimVerification.score` | `verified_at` | yes | **yes** (`load_verifications` ordered `verified_at ASC`, `:246-251`) | yes |
| `research_citations` (`models.py:147` `CitationRecord`) | source_uri/title/kind/section/page/retrieved_at | **yes** (v7) | n/a (evidence) | **yes** (the provenance record) | n/a | `retrieved_at` | yes | **yes** (`load_citations`, `:289`) | yes |
| `research_reports` (`models.py:174` `ResearchReport`) | findings, claims/verifications/citations, confidence | **yes** (v7) | aggregate | yes | `ResearchReport.confidence` | `created_at` | yes (best-effort persist) | yes (`load_reports`, `:342`) | yes |
| persistent `learning_insights` (`atlas/learning_engine/models.py:36` `LearningInsight`) | insight text, confidence, category, metadata | **yes** (migration v11, `migration.py:873`) | **no validation status** (insights, not claims) | limited (metadata) | `LearningInsight.confidence` (`models.py:61`) | observation metadata | yes | yes (`LearningMemory.get_insights:199`) | yes |

**Authoritative conclusion:** the authoritative **validated** knowledge source is
the research claim/verification/citation set (persisted, deterministic reads,
explicit validation status + confidence + provenance). `learning_insights` is a
**different knowledge class** (learning insights, no validation status) and is not
a validated-knowledge source per se.

---

## 5. KNOWLEDGE ITEM CONTRACT

A retrieved validated knowledge item needs: identity, content/claim, validation
status, confidence, provenance/citations, source, stable identifier, supporting
evidence. **An existing model already represents all of this**: `KnowledgeClaim`
(id `claim_id`, statement, `confidence`, `citations: tuple[CitationRecord]`) +
`ClaimVerification` (status, score, evidence_summary) + `CitationRecord`
(provenance). **Reuse is possible; no new parallel knowledge model is required.**
(Freshness is available only as timestamps, not as an F2 status — see §8.)

---

## 6. VALIDATION / CONFIDENCE / PROVENANCE CONTRACT

- **Validation semantics (verified):** `VerificationStatus` ∈ {`UNVERIFIED`,
  `SUPPORTED`, `CONTRADICTED`, `AMBIGUOUS`} (`research/models.py:20`).
  `ClaimVerifier` (`research/verifier.py:92`) maps `ClaimOutcome` →
  status via `_to_verification_status` (`:250`): `UNKNOWN→UNVERIFIED`,
  `CONTESTED→CONTRADICTED`, `VERIFIED|PLAUSIBLE→SUPPORTED`. **"Validated" =
  `SUPPORTED`.** (`AMBIGUOUS` is defined but not produced by `ClaimVerifier`.)
- **Confidence (verified):** two values exist — `KnowledgeClaim.confidence`
  (extractor) and `ClaimVerification.score` (`confidence_from_evidence`). They are
  not the same quantity; a single "confidence" would require inventing a merge.
- **Provenance (verified):** `CitationRecord` per claim (uri/title/kind/section/
  page/retrieved_at); verification metadata carries `supporting`/`contradicting`
  source URIs (`verifier.py:163-168`).
- **Reuse, don't invent:** surface `status`, `claim.confidence`,
  `verification.score`, and citations as-is, clearly labelled.

---

## 7. RECONCILIATION AND CONFLICT CONTRACT

- **Source classes are not the same knowledge:** research claims are validated
  propositions; learning insights are outcome-derived patterns. Merging them has
  **no existing deterministic rule** → reconciliation across classes would be
  invented. → **Boundary decision (§14):** C6.1 should restrict to validated
  research claims, or treat learning insights as a clearly separate labelled class
  (decision B1).
- **Conflicts (contradictions):** the system records conflicting evidence as
  `CONTRADICTED` status (`verifier.py:139-144`) and the verifier explicitly
  surfaces `contradicting` sources; identity-level contradiction handling exists
  separately (`atlas/identity/belief_manager.py:97,135`) and reasoning-level
  (`atlas/advanced_reasoning/verify.py:227`). **There is no knowledge-store
  conflict-resolution algorithm.** The safe, evidence-consistent behavior is to
  **expose conflicting claims with their status/evidence (never present a
  `CONTRADICTED`/`UNVERIFIED` claim as validated; never silently suppress)** — or
  fail closed. Selecting between "expose labelled" and "suppress" is a decision
  (B5).

---

## 8. FRESHNESS / STALENESS BOUNDARY

F2 (`atlas/evolution/freshness/assessor.py:59` `KnowledgeFreshnessAssessor`) is
deterministic and read-only but consumes `KnowledgeRef` inputs
(`freshness/models.py:81`) and is currently invoked by the acquisition path
(`research/acquisition.py:270`) and the adaptation orchestrator
(`evolution/adaptation/orchestrator.py:231-236`) — **not** over persisted research
claims. Claims/citations carry timestamps (`extracted_at`, `verified_at`,
`retrieved_at`), but there is **no wired mapping** from research claims into
`KnowledgeRef`. **Therefore freshness is a documented boundary: C6.1 should NOT
add freshness filtering; it may surface existing timestamps only.** Including F2
freshness semantics would require a new mapping (out of C6.1).

---

## 9. PRODUCTION RETRIEVAL PATH

Current path (verified): `knowledge_retrieval` capability handler
(`atlas/knowledge/capability_handlers.py:71`) → `KnowledgeManager.query`
(`knowledge_manager.py:47`) → `KnowledgeBase` (in-memory, `knowledge_base.py:10`);
the cognition stage reads only `KnowledgeManager`
(`runtime_coordinator.py:413-425`); the user-facing deterministic fallback reads
`KnowledgeManager`/`KnowledgeBase` (`deterministic_fallback.py:119-123,195`).

**Important:** there is **no existing capability that retrieves persisted
validated claims.** `research.query` (`research/capability_handlers.py:220`) runs
the full research *pipeline* (plan→acquire→extract→verify→report), not retrieval
of persisted claims; `acquisition.py:399` reads `load_reports()` for sufficiency
gating, not query retrieval. So C6.1 must add a **new read path** over
`ResearchSQLiteStorage.load_claims/load_verifications/load_citations`, with a
deterministic matching function (reusing existing deterministic helpers
`research/_text.py significant_tokens`, `research/_verification.py norm_alpha`).
**How this new path relates to the existing `knowledge_retrieval`/KB surface is a
scope decision (B2):** (a) extend the existing retrieval surface (behavior change),
or (b) add a separate read-only accessor/CLI without altering current behavior.

**Retrieval semantics:** storage exposes list reads with no query filter; matching
must be deterministic (token/substring over `statement`), never semantic/NLP.

---

## 10. FAILURE / FAIL-CLOSED CONTRACT

Evidence-based defaults, plus items needing a decision:

- **No validated knowledge / unknown target:** return an explicit empty result
  (fail-closed, not an error) — consistent with existing retrieval behavior.
- **Missing provenance / missing confidence / unverified claim / rejected
  (`CONTRADICTED`) claim:** must **not** be presented as validated; either exclude
  or label — **decision B5**.
- **Malformed knowledge / unavailable store:** `ResearchSQLiteStorage` methods are
  safe reads; `is_available()` (`storage_protocol.py:31`) exists → fail-closed on
  unavailable store (decision B6 on exact behavior).
- **Stale knowledge:** out of C6.1 (boundary, §8).
- **Conflicting claims:** expose labelled or fail closed — decision B5.
- **Partial source availability:** return what is safely retrievable; no invented
  completeness (decision B6).

---

## 11. DETERMINISM CONTRACT

- Stable ordering: `load_claims` (`extracted_at ASC, claim_id ASC`),
  `load_verifications` (`verified_at ASC`), `load_citations` — deterministic;
  retrieval must additionally sort by a stable key (e.g., `claim_id`).
- Stable identifiers: `claim_id`/`verification_id`/`record_id` already stable.
- Repeatability: identical store state → identical output.
- No time-dependent nondeterminism unless explicitly freshness-scoped (out of
  C6.1). Objective check: repeated retrieval returns byte-identical serialization.

---

## 12. MODEL-INDEPENDENCE CONTRACT

**PASS.** C6.1 retrieval reads persisted SQLite rows only. No Ollama/Qwen/
llama.cpp/OpenAI/Anthropic/Gemini, no localhost inference, no API key, no network.
`ClaimVerifier`'s optional model is an *upstream acquisition* seam (never alters
status/score unless `strict_llm`, and is injected/optional); retrieval itself does
not invoke it.

---

## 13. READ-ONLY / GOVERNANCE CONTRACT

Reading `load_claims/load_verifications/load_citations` is pure SELECT — no
mutation of knowledge/persistence/beliefs/governance, no approval, no execution,
no files, no promotion, no evolution. (Verified: `ResearchStorage` exposes only
`store_*`/`load_*`; retrieval would use `load_*`.) A new accessor/CLI can be
read-only like C5.1's. Extending the *existing* retrieval path is still read-only
but changes production behavior (decision B2).

---

## 14. SCOPE BOUNDARY

**In C6.1 (minimal):** deterministic, read-only retrieval of **validated
(`SUPPORTED`) persisted research claims**, returning statement, status, claim
confidence, verification score, and citations (provenance), via a read path over
existing storage.

**Out of C6.1 (evaluated and rejected):** new persistence/schema; knowledge
authoring/extraction; web acquisition; embeddings/semantic search; automatic
contradiction resolution; automatic revision; forgetting; autonomous learning;
conversational self-Q&A; human modeling; autonomous evolution; **freshness
filtering (F2 mapping)**; **learning-insight reconciliation** (unless explicitly
authorized as a separate labelled class).

---

## 15. ACCEPTANCE CRITERIA (proposed, testable if later authorized)

1. Retrieved items come from existing persistent validated sources (`research_claims` + `research_verifications` + `research_citations`); no newly invented knowledge.
2. Unvalidated/`CONTRADICTED`/`UNVERIFIED` claims are never presented as validated.
3. Provenance (`CitationRecord`) is preserved verbatim from persisted evidence.
4. Confidence is preserved from existing evidence (claim `confidence` and/or verification `score`), labelled as-is.
5. Validation state (`VerificationStatus`) is preserved.
6. Deterministic ordering (stable sort key) and stable identifiers.
7. Repeated retrieval from identical state is reproducible (byte-identical serialization).
8. Missing/invalid evidence follows the fail-closed contract (§10 decisions resolved).
9. No external AI model is required.
10. Retrieval is read-only (no mutation of knowledge/persistence/governance).
11. Existing governance/authorization unchanged.
12. Existing knowledge/research/learning tests remain green.
13. The production retrieval path is actually exercised (kernel accessor + CLI/none invented).
14. No new persistence/schema introduced.
15. No conversational NLU/reference resolution introduced.
16. No C7/C8/C9 capability introduced.

(Criteria 6–8 depend on the unresolved decisions B1–B6 being resolved first.)

---

## 16. TEST STRATEGY

Reuse/extend existing tests (do not invent equivalents):
- **Storage:** `tests/test_research_storage.py` (load_* round-trip/ordering).
- **Models/verifier:** `tests/test_research_models.py`, `tests/test_research_verifier.py` (status mapping).
- **Evidence summary / planner:** `tests/test_research_evidence_summary.py`, `tests/test_research_planner.py`.
- **Knowledge surface:** `tests/test_knowledge.py`, `tests/test_knowledge_service.py`.
- **Learning:** `tests/test_learning_engine.py`, `tests/test_persistent_learning.py`.
- **Cognition/feedback:** `tests/test_phase21_research_feedback.py`, `tests/test_cognition_*`.
- **Conversation fallback:** deterministic-fallback tests (via conversation suite).
- New focused tests would cover only the new retrieval contract.

---

## 17. REAL-WORLD VALIDATION PLAN

Future validation through the real kernel: isolated temp storage; seed known
`SUPPORTED` + known `UNVERIFIED`/`CONTRADICTED` claims via the existing storage;
assert validated retrieval returns only validated items with provenance/confidence/
status; repeated reads identical; missing knowledge → fail-closed; external AI
unavailable → **0 AI calls** during retrieval; git/read-only integrity; actual
counts recorded (no hard-coded values).

---

## 18. C6/C7/C8/C9 BOUNDARY

Rejected drift: **C5** capability self-knowledge (different model); **C7** human
understanding / conversational self-Q&A / reference resolution (not implemented,
not retrieval); **C8** autonomous action; **C9** continuous evolution. C6.1 is
strictly deterministic validated-knowledge retrieval.

---

## 19. DEFECT ANALYSIS

**No defect found.** No contract is violated: the in-memory KB is a documented
design; the verifier maps statuses as documented; storage reads are ordered and
safe. 135 relevant tests passed. No unresolved failure.

---

## 20. IMPLEMENTATION READINESS

**Not yet ready to authorize.** Mechanisms exist and reuse is viable, but the
following **contract decisions must be resolved before implementation** (these are
the reason for recommendation B):

- **B1 — Source set & reconciliation:** validated research claims only, or also
  persistent `learning_insights` (different class, no validation status)? If both,
  define the (currently non-existent) reconciliation semantics.
- **B2 — Integration surface:** extend the existing `knowledge_retrieval`/KB path
  (production behavior change) vs add a separate read-only accessor/CLI (no change
  to current behavior). The readiness candidate implied the former; the latter is
  the minimal, lower-risk choice.
- **B3 — Confidence surfacing:** surface both `claim.confidence` and
  `verification.score` (labelled) vs one — do not invent a merged score.
- **B4 — Matching semantics:** define the deterministic query-matching function
  over `statement` (reuse `significant_tokens`/`norm_alpha`); no NLP/embeddings.
- **B5 — Conflict/failure presentation:** expose `CONTRADICTED`/`UNVERIFIED`
  labelled vs exclude; and the empty-result contract.
- **B6 — Store-unavailable/partial behavior:** exact fail-closed contract.

Freshness inclusion is **rejected** (no wired mapping; §8).

---

## 21. RECOMMENDATION

**B. REFINE C6.1 SCOPE.**

The candidate is a **genuine, bounded, evidence-backed** C6 requirement whose
authoritative source, validation semantics, provenance, confidence, and
deterministic read APIs already exist — but it is **not yet concrete enough to
authorize** because decisions **B1–B6** (source set/reconciliation, integration
surface, confidence surfacing, matching semantics, conflict presentation,
store-unavailable behavior) are unresolved architectural/contract choices. Resolve
those (a short, bounded refinement), then C6.1 can be authorized.

**This investigation does not authorize implementation.** No code, test,
configuration, schema, persistence, governance, CLI, or conversation change was
made; the only new artifact is this report.
