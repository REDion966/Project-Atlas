# PROJECT ATLAS — C6.1 VALIDATED KNOWLEDGE RETRIEVAL — CONTRACT RESOLUTION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C6.1 CONTRACT VALIDATED**

All six outstanding decisions (B1–B6) from `C6_1_SCOPE_CONTRACT_INVESTIGATION.md`
are resolved from existing repository evidence, without inventing new semantics.
No material architectural decision remains. (This does **not** authorize
implementation; it produces the evidence for the following review.)

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree: pre-existing modified/untracked files + C3–C6 artifacts —
  unchanged by this investigation. No staged/deleted/renamed files.
- Relevant verification (run for this investigation):
  `python -m pytest tests/test_research_storage.py tests/test_research_models.py tests/test_research_verifier.py tests/test_research_evidence_summary.py tests/test_knowledge.py tests/test_knowledge_service.py tests/test_learning_engine.py tests/test_persistent_learning.py tests/test_phase21_research_feedback.py -q`
  → **135 passed, 0 failed, 0 errors (exit 0)**.

---

## 3. B1 — AUTHORITATIVE SOURCE CONTRACT

**Resolution: OPTION A — research claims / verifications / citations ONLY.**

Evidence:

- `KnowledgeClaim` (`atlas/research/models.py:99`) = `claim_id`, `statement`,
  `citations: tuple[CitationRecord]`, `confidence`, `extracted_at`. It is a
  **validated proposition**: verification is a separate record
  (`ClaimVerification`, `:122`) carrying `status`/`score`/`evidence_summary`.
- `LearningInsight` (`atlas/learning_engine/models.py:36`) = `insight_id`,
  `category`, `title`, `description`, `importance`, `confidence`,
  `observation_count`, `reusable`, `applicable_areas`, timestamps, `metadata`.
  It has **no claim/citation structure, no verification record, and no validation
  status** — it is a **distinct knowledge class** (outcome-derived learning), not
  validated knowledge.
- **No cross-class reconciliation contract exists**: nothing in the repository
  maps insights ↔ claims, and their fields are disjoint. Merging them would
  require inventing a reconciliation rule. Per the mission, that is rejected.

Therefore C6.1's authoritative source is the persisted research claim set
(`research_claims` + `research_verifications` + `research_citations`, migration
v7, `atlas/storage/migration.py:330`; reads via
`atlas/storage/research_storage.py:201,246,289`).

---

## 4. B2 — INTEGRATION SURFACE CONTRACT

**Resolution: OPTION B — a dedicated read-only validated-knowledge accessor
(kernel) + read-only CLI, leaving the existing general knowledge path unchanged.**

Blast radius of Option A (extending the existing path) — production callers of
`KnowledgeManager` / `KnowledgeBase` / `KnowledgeStore`:

- cognition pipeline read/write: `atlas/cognition/pipeline.py:306-312, 622-623`
- cognition service read/write/accessor: `atlas/services/cognition_service.py:242-243, 273-274, 479`
- runtime coordinator stage read/write: `atlas/runtime/runtime_coordinator.py:417-423, 910-911`
- `knowledge_retrieval` capability: `atlas/knowledge/capability_handlers.py:101`
- user-facing deterministic fallback: `atlas/conversation/deterministic_fallback.py:119-180`
- advanced-reasoning evidence provider: `atlas/kernel/atlas.py:247-260`
- **governed KNOWLEDGE applier**: `atlas/evolution/autonomy/adapters/knowledge_adapter.py:84,92,112`
- ServiceContainer `"knowledge"`: `atlas/kernel/atlas.py:3377`

Changing `KnowledgeManager.query` would alter cognition, reasoning evidence, the
user-facing fallback, and the governed knowledge applier simultaneously — a broad
behavior change. A dedicated read-only accessor (like C5.1's
`Atlas.capability_model()`) is the **smallest, safest** surface: it adds a new
validated-knowledge read path and leaves all existing behavior untouched.

C6.1 therefore introduces a new read-only accessor/CLI; it does **not** modify
the existing knowledge path. (Unifying the legacy in-memory surface is explicitly
out of C6.1.)

---

## 5. B3 — CONFIDENCE CONTRACT

**Resolution: surface BOTH values, explicitly labelled; never merge.**

Evidence:

- `KnowledgeClaim.confidence` is the extractor's **provisional confidence**
  (`atlas/research/_verification.py:1-5` docstring: "the knowledge extractor's
  provisional confidence assignment").
- `ClaimVerification.score` is the **evidence-based verification score** from
  `confidence_from_evidence(supporting, contradicting)` (`_verification.py:18-42`;
  base 0.5, +0.15 if uncontested, +0.1/supporting capped at +0.3, cap 0.95).

They are different quantities. C6.1 exposes `claim_confidence` and
`verification_score` as separate, labelled fields. No averaging/normalization/
derivation.

---

## 6. B4 — DETERMINISTIC MATCHING CONTRACT

**Resolution: reuse the existing deterministic helpers; NO ranking.**

Reusable deterministic helpers (pure, no AI):
`norm_alpha` (`research/_verification.py:13`), `significant_tokens`
(`research/_text.py:49`), `normalize_whitespace` (`:39`), `similarity_ratio`
(`_verification.py:45`). The existing verifier matches with
`claim_norm in source_norm` (substring) and token containment
(`verifier.py:198-205`); `KnowledgeSearch` uses substring (`knowledge_search.py:32`).
`KnowledgeRanker` is a **no-op placeholder** (`knowledge_ranker.py:10`) — there is
**no ranking contract to reuse**, so C6.1 must not rank.

**INPUT → MATCHING → FILTERING → ORDERING → OUTPUT** (precise):

1. **INPUT:** a non-empty query string `q` (whitespace-only → empty result).
2. **MATCHING:** for each persisted claim `c`, match iff `norm_alpha(q)` is
   non-empty AND (`norm_alpha(q) in norm_alpha(c.statement)` OR
   `significant_tokens(q) ⊆ significant_tokens(c.statement)`). (Mirrors the
   verifier's existing deterministic predicates; no embeddings/semantic/NLP.)
3. **FILTERING:** keep a matched claim only if it has a verification record whose
   **latest** entry — max by `(verified_at, verification_id)` over the
   append-only log — has `status == SUPPORTED`.
4. **ORDERING:** sort ascending by `claim_id` (stable, unique).
5. **OUTPUT:** for each item: `claim_id`, `statement`, `validation_status`
   (`"SUPPORTED"`), `claim_confidence`, `verification_score`, `citations`
   (provenance), `extracted_at`, `verified_at`.

Deterministic; no time-dependent behavior; no new scoring/ranking.

---

## 7. B5 — VALIDATION / CONFLICT / FAILURE CONTRACT

**Resolution: return only `SUPPORTED`, each labelled; never present non-supported
as validated; no conflict resolution; fail closed.**

Status behavior (from `VerificationStatus` `models.py:20` and
`_to_verification_status` `verifier.py:250`):

- `SUPPORTED` → returned as validated (`validation_status="SUPPORTED"`).
- `UNVERIFIED` (no/unknown evidence) → **not** returned as validated.
- `CONTRADICTED` (contested) → **not** returned as validated.
- `AMBIGUOUS` → not produced by `ClaimVerifier` (`verifier.py:250-256`); if present
  in a store it is treated as non-supported.
- missing verification / malformed claim / missing citation / missing confidence →
  the claim does not qualify (excluded), never upgraded.

**No automatic conflict resolution.** No claim-vs-claim conflict analysis exists
(verification is claim-vs-source only); C6.1 must not invent one, and no claim is
mutated or deleted. Returning only `SUPPORTED` is the **definition** of a
*validated*-knowledge retrieval surface, not silent suppression: non-supported
claims remain stored and are retrievable through the existing research surfaces.
Empty validated result → explicit empty output (not an error), never a fallback
to unvalidated knowledge presented as validated.

---

## 8. B6 — STORAGE AVAILABILITY CONTRACT

**Resolution: gate on `is_available()`; fail closed on unavailable/error; never
fall back to unvalidated in-memory knowledge.**

Evidence: `ResearchSQLiteStorage.is_available()` (`research_storage.py:83`) returns
`self._available and self._conn is not None`; `initialize()` sets availability and
applies migrations (`:49-69`); `_execute()` raises and marks the adapter
unavailable on SQLite error (`:91-99`). Contract: if `is_available()` is False or a
read raises, C6.1 returns an explicit fail-closed result (empty/typed error) and
**must not** substitute the in-memory `KnowledgeBase` while representing the
result as validated. Empty database / no matching claims / partial records → empty
validated result (no error). Missing research tables are created by `initialize()`
(migrations); if they are genuinely absent and reads fail, the fail-closed path
applies.

---

## 9. FINAL C6.1 CONTRACT

A new **deterministic, read-only** surface that returns **validated
(`SUPPORTED`) persisted research claims** matching a query, each item carrying
`validation_status`, `claim_confidence`, `verification_score`, and `citations`
(provenance). Sources: `research_claims`/`research_verifications`/`research_citations`
via `ResearchSQLiteStorage.load_*`. Integration: a new read-only kernel accessor +
read-only CLI (existing knowledge path untouched). Matching/ordering/filtering as
in B4. Failure/fail-closed as in B5/B6. No new persistence/schema, no model, no
NLP/NLU, no mutation.

---

## 10. ACCEPTANCE CRITERIA

1. Authoritative source is explicit (research claims + verifications + citations). ✅
2. Only evidence-supported (`SUPPORTED`) knowledge qualifies. ✅
3. Validation semantics are explicit (`VerificationStatus`; latest verification). ✅
4. Provenance is preserved (`CitationRecord` verbatim). ✅
5. Confidence semantics are explicit (two labelled values). ✅
6. No confidence values are silently merged. ✅
7. Deterministic matching is explicit (B4 predicates). ✅
8. Ordering is stable (by `claim_id`). ✅
9. Repeated retrieval is identical for identical store state. ✅
10. Conflicts cannot be silently misrepresented (only `SUPPORTED` returned/labelled). ✅
11. Unavailable storage fails closed. ✅
12. No fallback to unvalidated knowledge presented as validated. ✅
13. No external model required. ✅
14. Retrieval is read-only. ✅
15. Governance unchanged. ✅
16. No new persistence/schema required. ✅
17. No NLU/NLP introduced. ✅
18. No C7/C8/C9 behavior introduced. ✅
19. Existing regression remains clean. ✅
20. Real production retrieval can be validated (kernel accessor + CLI). ✅

(All criteria are supported by the resolved architecture; no criterion depends on
an unresolved decision.)

---

## 11. TEST STRATEGY

Reuse (do not modify): `tests/test_research_storage.py` (load_* ordering/round-trip),
`tests/test_research_models.py`, `tests/test_research_verifier.py` (status mapping),
`tests/test_research_evidence_summary.py`, `tests/test_knowledge.py`,
`tests/test_knowledge_service.py`, `tests/test_learning_engine.py`,
`tests/test_persistent_learning.py`, `tests/test_phase21_research_feedback.py`, plus
cognition/runtime tests for the untouched existing path. A future implementation
adds a focused test for the new accessor only (validated-only semantics,
provenance/confidence preservation, determinism, fail-closed, no-fallback). Smallest
focused set = the new accessor test + `test_research_storage.py` +
`test_research_verifier.py`.

---

## 12. REAL-WORLD VALIDATION PLAN

Future validation: real kernel, isolated temp `ResearchSQLiteStorage`; seed one
`SUPPORTED`, one `UNVERIFIED`, one `CONTRADICTED` claim (with citations and
confidence) via existing `store_*`; exercise the new accessor and CLI; assert only
the `SUPPORTED` claim is returned with provenance/confidence/status; repeated
retrieval identical; empty query/missing knowledge → explicit empty; store
unavailable (closed connection) → fail-closed, no substitution; external AI
unavailable → **0 AI calls**; git/read-only integrity; record actual counts (no
hard-coded values). Not performed here.

---

## 13. MODEL-INDEPENDENCE

**PASS.** Retrieval reads persisted SQLite rows only; no Ollama/Qwen/llama.cpp/
OpenAI/Anthropic/Gemini, no localhost inference, no API key, no network. The
verifier's optional model is an upstream acquisition seam and is not invoked by
retrieval.

---

## 14. READ-ONLY / GOVERNANCE BOUNDARY

Pure `load_*` SELECTs: no mutation of knowledge/persistence/beliefs/governance, no
approval/execution/promotion/evolution; the new accessor and CLI are read-only.
Governance, authorization, sandbox, and execution are unchanged.

---

## 15. C5/C7/C8/C9 BOUNDARY

Excluded: **C5** capability self-knowledge; **C7** human understanding /
conversational self-Q&A / reference resolution; **C8** autonomous action; **C9**
continuous autonomous evolution. Also excluded: new persistence/schema,
embeddings/semantic search, automatic conflict resolution, automatic revision,
forgetting, autonomous learning, external-model retrieval, broad knowledge
architecture rewrite.

---

## 16. REMAINING UNRESOLVED DECISIONS

**None material.** Two points are explicitly resolved / bounded rather than open:

- **Append-only verification log → selection rule:** "latest verification by
  `(verified_at, verification_id)`" is the deterministic selection rule (resolved
  in B4/B5); it is required because verifications are an append-only log.
- **Cross-claim conflict detection:** out of C6.1 scope (no existing mechanism;
  inventing one is prohibited). Documented boundary, not a blocker.

---

## 17. DEFECT ANALYSIS

**No defect found.** No contract is violated; the in-memory KB is a documented
design; verifier/storage behave per contract. 135 relevant tests passed; no
unresolved failure. (The 0-failure rule is satisfied.)

---

## 18. READ-ONLY INTEGRITY

- Branch `main`; HEAD `f85de89` — unchanged before/after.
- No tracked source, test, configuration, persistence/schema, governance, CLI, or
  conversation change; no commit/reset/clean/stash; no deletion/rename; no staged
  files. The only new artifact is this report.

---

## 19. RECOMMENDATION

**A. READY FOR C6.1 IMPLEMENTATION AUTHORIZATION.**

B1–B6 are concretely resolved from existing repository evidence (research-claims-only
source; dedicated read-only accessor; both confidence values labelled; deterministic
matching reuse; `SUPPORTED`-only labelled output with fail-closed behavior;
`is_available()`-gated storage), with no material architectural decision remaining
and all 20 acceptance criteria supported by the resolved architecture.

**This report does not authorize implementation.** No code, test, configuration,
schema, persistence, governance, CLI, or conversation change was made; the only new
artifact is this report. Any C6.1 implementation requires an explicit, separate
authorization command.
