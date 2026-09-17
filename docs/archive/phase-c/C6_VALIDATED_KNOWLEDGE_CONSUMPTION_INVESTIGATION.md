# PROJECT ATLAS — C6 VALIDATED KNOWLEDGE CONSUMPTION — BOUNDED EXPOSURE INVESTIGATION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C6 OBJECTIVE SATISFIED — no actionable C6 consumption gap; no defect.**

The one residual item (validated knowledge is retrievable but not consumed by any
Atlas decision mechanism) cannot be turned into a **bounded C6 step**, because the
only existing knowledge→decision seam (`EvidenceProvider.query -> list[str]`) is a
**string-only, advisory** contract that cannot carry provenance/validation/confidence
without changing a non-C6 (advanced-reasoning) contract. Any consumption work is a
**cross-subsystem integration outside C6**. C6.1's validated retrieval is a real,
operator-useful capability.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`) — verified.
- Working tree: pre-existing modified/untracked files + C3–C6.1 artifacts; no
  staged/deleted/renamed files.
- Relevant verification (this investigation): **172 passed, 0 failed, 0 errors** (§19).

---

## 3. C6 OBJECTIVE

`ACQUIRE → VALIDATE → RETAIN → RETRIEVE → USE` knowledge with provenance,
confidence, freshness/revision/contradiction awareness — deterministic,
model-independent, evidence-backed (loop `USE→OBSERVE→EVIDENCE→VALIDATE→LEARN→RETAIN→RETRIEVE→USE`).

---

## 4. C6.1 VERIFIED BASELINE

`atlas/research/validated_retrieval.py` (`ValidatedKnowledgeRetriever.retrieve`,
`select_latest_verifications`, `ValidatedKnowledgeItem/Result`): SUPPORTED-only,
distinct `claim_confidence`/`verification_score`, citations preserved, deterministic
`norm_alpha`/`significant_tokens` matching, `claim_id` ordering, fail-closed
(`store_unavailable`/`store_error`), read-only. Kernel `Atlas.validated_knowledge`
(`kernel/atlas.py:3560`); CLI `validated-knowledge` (`cli/main.py:367,704,1071`;
`cli/validated_knowledge_commands.py`). Persistent store v7
(`storage/research_storage.py:201,246`). **Verified deterministic, read-only,
SUPPORTED-only, provenance/confidence-bearing, model-independent, fail-closed.**

---

## 5. CURRENT KNOWLEDGE USE PATH

```
LEGACY (current decision path)
  KnowledgeManager.query  (in-memory KnowledgeBase; unvalidated)
    → KnowledgeEvidenceProvider.query   (kernel/atlas.py:247-268)
        → "source:title" reference strings
        → AdvancedReasoning MultiStepReasoner._query_evidence (multi_step.py:292-297)
          / HypothesisGenerator._query_evidence (hypotheses.py:258)
            → ReasoningTraceStep.evidence_refs / Hypothesis.evidence_refs
              → step/hypothesis confidence thresholds (ADVISORY) → reasoning output

VALIDATED (C6.1, exposed but NOT consumed)
  ResearchSQLiteStorage.load_claims/load_verifications  (v7)
    → ValidatedKnowledgeRetriever.retrieve  (research/validated_retrieval.py)
        → Atlas.validated_knowledge(...)  (kernel/atlas.py:3560)
            → validated-knowledge CLI only   ← no decision consumer
```

---

## 6. KNOWLEDGE EVIDENCE CONTRACT

`EvidenceProvider` (`advanced_reasoning/protocols.py:29-43`):
`query(query_text: str, limit: int = 10) -> list[str]` — returns **stable evidence
reference strings**; "the protocol never mutates state". `KnowledgeEvidenceProvider`
(`kernel/atlas.py:246-268`) implements it over `KnowledgeManager.query`, formatting
`"{source}:{title}"`, sorted, bounded, fail-soft (`except → []`).

Answers to the mission's questions: input = a query string; origin = kernel-wired
KnowledgeManager; it is restricted to the legacy KB; the contract carries **no**
provenance/confidence/validation/claim_id/freshness fields — only strings; it
mutates nothing; it provides evidence (does not decide). **It is the only existing
knowledge→reasoning seam, but its contract is lossy for validated knowledge.**

---

## 7. REASONING CONSUMPTION ANALYSIS

Callers of the seam: `MultiStepReasoner` (`multi_step.py:273-289`) and
`HypothesisGenerator` (`hypotheses.py:231-254`). Evidence refs only select a
step/hypothesis **confidence constant** (`_STEP_CONFIDENCE_WITH_EVIDENCE` vs
`_STEP_CONFIDENCE_WITHOUT_EVIDENCE`; weak-evidence thresholds in hypotheses). It is
**advisory evidence**: no planning, approval, execution, mutation, promotion, or
governance decision reads `evidence_refs`. Kernel wiring: `atlas.py:2835-2838`
(EvidenceProvider wraps KnowledgeManager; injected into the advanced-reasoning
service). Tests: `test_kernel_advanced_reasoning_integration.py:73-105`,
`test_phase20_closed_loop.py:307-309`, `_advanced_reasoning_fakes.FakeEvidenceProvider`.

---

## 8. VALIDATED KNOWLEDGE → EVIDENCE MAPPING

A `ValidatedKnowledgeItem` carries `claim_id`, `statement`, `validation_status`,
`claim_confidence`, `verification_score`, `citations`. The existing evidence contract
accepts **only `list[str]`**. Therefore mapping requires either:
- (i) **encoding** status/id/provenance into the reference string (a new convention
  with no existing precedent — the legacy provider uses `source:title`; every
  downstream consumer treats refs as opaque strings used only for confidence
  thresholds), which **loses** the semantics that make validated knowledge valuable
  (validation status, both confidences, citations are not modelled); or
- (ii) **changing** the `EvidenceProvider` contract to a structured type — an
  advanced-reasoning (Track D) contract change, **outside C6**.

Neither is a "minimum subset that preserves provenance" within C6: the contract has
no field to preserve it in. No combined/authority confidence is invented (per the
contract, `claim_confidence` and `verification_score` stay distinct and simply cannot
be conveyed here).

---

## 9. INTEGRATION CANDIDATE ANALYSIS

| Candidate | Reuses | Blast radius | Behavior change | Deterministic | Read-only | Governance | New arch | C7/C8/C9 | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| A: ValidatedKnowledgeRetriever → KnowledgeEvidenceProvider directly | retriever | advanced reasoning inputs | yes (evidence refs change) | yes | yes | none | no | no | **rejected** — lossy (strings only); validated semantics dropped |
| B: Adapter to evidence contract | retriever + protocol | reasoning inputs | yes | yes | yes | none | **new convention** | no | **rejected** — invents an evidence-string convention to smuggle status; still drops confidence/citations |
| C: Provider queries both legacy + validated | both sources | legacy provider semantics change | yes | yes | yes | none | no | no | **rejected** — changes legacy provider semantics; blends unvalidated with validated in one opaque ref list (violates §8 distinction) |
| D: Apply F2 freshness to validated claims and feed reasoning | F2 | F2/claims | yes | yes | yes | none | mapping needed | no | **rejected as C6 step** — freshness is not the USE seam; no production claim→`KnowledgeRef` construction exists |
| E: New validated-knowledge reasoning subsystem | — | large | large | yes | yes | none | **yes** | risk | **rejected** — speculative new architecture |

None is both **meaningful** and **bounded within C6**.

---

## 10. LEGACY KNOWLEDGE BOUNDARY

The legacy path is **unchanged** and can remain so: `validated_knowledge` is a
separate read-only surface (`kernel/atlas.py:3560`); the legacy KB is read by
cognition (`runtime_coordinator.py:413-425`), the evidence provider
(`atlas.py:247-268`), and the fallback (`deterministic_fallback.py:119-180`). No
candidate requires touching it, and none should: validated and legacy sources are
**explicitly distinguishable** today (separate modules/surfaces) with **no shared
mutable state**. Preserving that distinction is exactly why smuggling validated refs
into the legacy string seam is rejected.

---

## 11. F2 FRESHNESS ANALYSIS

`KnowledgeRef` already models `claim_id`/`verification_id`
(`evolution/freshness/models.py:91-92,107-108`) and the assessment preserves them
(`:159`). The assessor is deterministic (`freshness/assessor.py:59`) and is used by
the acquisition gate (`research/acquisition.py:270`) and adaptation
(`evolution/adaptation/orchestrator.py:231`). **No production caller constructs
`KnowledgeRef`s from persisted research claims** (grep: `KnowledgeRef(` appears only
inside `assessor.py`). A deterministic mapping from claim fields
(`claim_id`, `verification_id`, `retrieved_at`/`verified_at`, `confidence`) to
`KnowledgeRef` is feasible in principle, but freshness is **not** the USE seam, would
add a new assessment wiring, and is not required for validated-knowledge
consumption. (Mission §16 answer: **B — freshness is not required for the minimum
consumption step and should remain a separate future concern.**)

---

## 12. REVISION / CONTRADICTION ANALYSIS

The C6.1 latest-verification rule (`validated_retrieval.py:153`) already gives safe
"current knowledge" semantics: an older `CONTRADICTED` followed by a newer
`SUPPORTED` yields SUPPORTED (current); the reverse yields exclusion. Verification
history is preserved (append-only `research_verifications`). Cross-claim conflict
detection does not exist and is not required (inventing it is prohibited). **The
latest-verification rule is sufficient for safe first-stage consumption**, but there
is no consumer to consume it.

---

## 13. GOVERNANCE / EXECUTION ANALYSIS

`EvidenceProvider` output is **advisory evidence** only (§7): it cannot influence
approval, authorization, execution, mutation, promotion, or self-modification.
Adding validated evidence at the seam would not change any governance contract —
validated knowledge would be **read-only evidence**, never authorization or automatic
action. (This is a property of the seam; it does not create a C6 step.)

---

## 14. MODEL-INDEPENDENCE

**PASS.** Validated retrieval (C6.1), the evidence seam, and F2 are deterministic;
optional models remain injected/OFF by default. Reaching reasoning with validated
knowledge requires no Ollama/Qwen/llama.cpp/OpenAI/Anthropic endpoint, API key, or
network.

---

## 15. REAL-WORLD CAPABILITY SCENARIO

- **Current behavior:** a query routed to advanced reasoning draws evidence from the
  legacy in-memory KB; validated research claims (persisted, provenance-bearing) are
  never consulted. An operator can inspect validated claims via
  `atlas validated-knowledge`, but Atlas's own reasoning does not benefit.
- **Desired behavior:** validated SUPPORTED claims could contribute evidence to
  reasoning.
- **Exact missing exposure:** no structured knowledge→reasoning interface exists to
  carry validation status/confidence/provenance.
- **Why it matters:** without it, validated knowledge does not influence Atlas
  decisions.
- **Can the existing reasoning path consume it?** Only as opaque strings (advisory
  confidence), i.e. without its validated semantics.
- **Objectively validatable?** A string-only integration is objectively testable but
  its value is marginal and semantically lossy; a structured integration would be a
  non-C6 contract change. Scenario does **not** require C7 conversational self-Q&A.

---

## 16. GAP CLASSIFICATION

| Issue | Category |
|---|---|
| Validated knowledge not consumed by reasoning | **E — the only bounded way is lossy; meaningful integration requires a non-C6 (advanced-reasoning) contract change ⇒ outside C6** |
| F2 freshness not applied to claims | **B — existing capability, separable; not required for C6 completion (separate future concern)** |
| Legacy KB ephemeral/unvalidated | **C — intentional documented boundary** |
| Acquisition/validation/retention/retrieval/learning-feedback | **F — no gap** |

**No Category-A (missing capability) gap.** No Category-B item yields a bounded,
non-lossy, C6-owned step.

---

## 17. MINIMUM BOUNDED NEXT STEP

**None is justified within C6.** The smallest possible change (string evidence refs)
is semantically lossy (drops validation/provenance/confidence) and risks conflating
validated with unvalidated evidence — exactly what §8 forbids; the meaningful
alternative requires changing the advanced-reasoning `EvidenceProvider` contract,
which is **outside C6**. Therefore no bounded C6 consumption step is defined.

(Separately, applying F2 freshness to validated claims is a **bounded, C6-adjacent,
read-only** improvement of an existing capability, but it is **not** the USE seam and
is not required for C6's objective; it is recorded as a future concern, not a
justified next step.)

---

## 18. ACCEPTANCE CRITERIA

Not applicable — no bounded C6 step is proposed. (If an owner later authorizes a
**cross-subsystem** reasoning-evidence integration outside C6, its criteria would be:
structured evidence carrying `claim_id`/`validation_status`/`claim_confidence`/
`verification_score`/citations; deterministic; read-only; model-independent; legacy
KB unchanged; existing reasoning tests updated deliberately; objectively testable.)

---

## 19. TEST STRATEGY

Relevant existing tests inspected/run (no modification): `test_validated_knowledge_retrieval.py`,
`test_advanced_reasoning_protocols.py`, `test_advanced_reasoning_multi_step.py`,
`test_advanced_reasoning_hypotheses.py`, `test_kernel_advanced_reasoning_integration.py`,
`test_evolution_f2_knowledge_freshness.py`, `test_research_verifier.py`,
`test_knowledge_service.py`, `test_phase20_closed_loop.py`.

Command: `python -m pytest <above> -q` → **172 passed, 0 failed, 0 errors (exit 0)**.

---

## 20. REAL-WORLD VALIDATION PLAN

Not applicable — no C6 step to validate. (C6.1 already validated its own surface:
real kernel, temp storage, SUPPORTED-only, provenance/confidence, determinism,
fail-closed, 0 AI calls, read-only.)

---

## 21. C5/C7/C8/C9 BOUNDARY

- **C5:** CLOSED; not reopened (no defect).
- **C7:** conversational knowledge interaction/self-Q&A — excluded (scenario does not need it).
- **C8:** autonomy — excluded.
- **C9:** continuous evolution — excluded.
Any future reasoning-evidence integration is **outside C6** (Track D / cross-subsystem).

---

## 22. DEFECT ANALYSIS

**No defect found.** C6.1 verified intact; the evidence seam behaves as documented;
172 relevant tests passed; no unresolved failure.

---

## 23. READ-ONLY INTEGRITY

- HEAD `f85de89` unchanged; no source/test/config/schema/persistence/governance/CLI/
  conversation/roadmap change; no staged files; no commit/reset/clean/stash; no
  deletion/rename. Only new artifact: this report.

---

## 24. RECOMMENDATION

**A. NO ACTIONABLE C6 GAP — CLOSE C6.**

C6's objective is satisfied by existing production mechanisms across every stage
(acquisition, validation, retention in v7/v9/v11 stores, retrieval including C6.1's
validated surface, and advisory knowledge use + learning feedback). The remaining
"consume validated knowledge in reasoning" item cannot be implemented as a bounded,
semantically-safe C6 step: the only existing decision seam is a string-only advisory
`EvidenceProvider`, and preserving the validated/provenance semantics requires
changing that advanced-reasoning contract — **outside C6**. The legacy/validated
separation is an intentional, documented boundary (C6.1 Option B), not a gap. F2
freshness over claims is a separate future concern, not required for C6.

This report does **not** authorize implementation and does **not** create C6.2.

---

## 25. REMAINING QUESTIONS

- If the owner wants validated knowledge to influence reasoning, should that be
  scoped as a **cross-subsystem reasoning-evidence** effort (structured evidence
  type) rather than a C6 knowledge step?
- Should F2 freshness over persisted claims be scheduled as a separate bounded C6
  concern, and does it need a claim→`KnowledgeRef` mapping (deterministic, read-only)?
- Is the operator-facing `validated-knowledge` surface (kernel/CLI) sufficient for
  near-term needs, deferring any reasoning integration?
