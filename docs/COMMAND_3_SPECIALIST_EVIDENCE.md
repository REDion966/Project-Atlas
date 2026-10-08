# COMMAND 3 — EVIDENCE: REAL-WORLD PROOF + SPECIALIST DISCOVERY + ATLAS-NATIVE INTEGRATION

Starting commit: `7d91641` (Command 2 complete, HEAD == origin/main, clean tree)

## 1. What was researched

The previous four-model inventory was treated as **input, not law**. Fresh
independent research was performed against GitHub, Hugging Face, PyPI, project
documentation and arXiv across the five required categories (NLU,
repository/code understanding, development intelligence, self-knowledge,
autonomy infrastructure). Full per-candidate results — capability, size, runtime,
CPU/GPU, license, language coverage, Atlas role, gap, dependency cost, failure
behaviour, disable-ability, replaceability, duplication and recommendation — are
in **`docs/COMMAND_3_SPECIALIST_CANDIDATE_INVENTORY.md`**.

Headline outcome: **1 INTEGRATE, 4 ADAPT, 11 REJECT, 13 DEFER, 1
OPTIONAL_PROVIDER.** Most research candidates turned out to be mechanisms Atlas
already had (`REJECT`/`ADAPT`), and the only capability with **no Atlas-native
mechanism at all** was semantic similarity.

## 2. Real-world end-to-end proof (Task 2)

Driven through the NORMAL kernel entry point with the **real** local provider.

### 2a. Full governed development cycle — PASS

```
request        "Add a module-level docstring line to atlas/research/relevance.py
                describing the module's lexical ranking, preserving behaviour."
latency        78.5 s
ok             true
proposal_id    DEV-43d84ba3120b6e5f
status         PENDING_APPROVAL
specialist     provider_id=ollama.qwen2.5-coder-7b  model=qwen2.5-coder:7b
               capability=code.generate  paths=[atlas/research/relevance.py]
authorized     false
executed       false
pending_promotions 0
failures       []
```

The path exercised: natural-language request → deterministic development intake →
localization (`atlas.research.relevance`) → bounded repository context → real
proposal → Atlas `validate_proposal` → the existing F9 `DevelopmentCycleController`
→ **STOPS at the human approval boundary**. Nothing was authorized, executed or
promoted.

### 2b. Real STRUCTURAL authoring — PASS (closes Command 2's unproven item)

Command 2 could not exercise structural authoring through a real provider.
It now can. The real model was asked for a bounded structural payload and the
existing editor applied it against a REAL repository file's content:

```
latency        34.6 s
raw_keys       ["change","kind","note","path","source","symbol"]
outcome        APPLIED          origin specialist-proposal
result_parses  true             (the result is valid Python)
prefix_preserved  true          suffix_preserved  true
differs_from_base true
```

**Every unrelated byte was preserved** and the anchored change was applied through
`apply_structural_edits` — no second editor, no rewritten architecture.

### 2c. Provider disabled — PASS (fail-closed)

`specialist_enabled=false`, `ok=false`, no proposal, no approval, no execution, no
promotion.

### 2d. Repository integrity — PASS

SHA-256 of both probe target files identical before and after every probe
(`unchanged: true`). The pipeline writes **nothing** to the repository.

### 2e. Capability gap discovered — Atlas-language, NOT model

A real, realistic request phrased *"Implement a development change in <path>: add
a bounded helper function …"* or *"Add a small bounded helper function to the …"*
returns **`{}`** from `development_supplied_edit` — i.e. it is never recognised as
a development request at all. A differently-phrased request ("Add … to <path> …
preserving behaviour.") is routed correctly.

**Classification:** a *deterministic intake / language-understanding* limitation,
**not** a model limitation and **not** an architectural gap. The fix is a targeted
deterministic intake improvement, not a specialist model. Recorded, not papered
over.

## 3. Selected specialist: `semantic.similarity` (INTEGRATE)

### Why this and nothing else

* It is the **only** capability with no Atlas-native mechanism: Atlas's ranking is
  BM25 over identifier tokens, its reference resolution is lexical, and its own
  source repeatedly asserts the absence of embeddings.
* **Zero new Python dependency.** The runtime (`nomic-embed-text`, already
  installed locally) is reached through the *existing* stdlib transport pattern.
* Small, local, offline, CPU-capable, fully disable-able, artifact-replaceable.
* It **cannot become an authority**: it may only **re-order Atlas's own candidate
  set** — never add a candidate, remove one, authorize, execute or promote.

### Atlas-native shape (external mechanism → Atlas contract)

```
local runtime  →  ollama_embedding_transport(...)            (injected transport)
               →  SpecialistEmbeddingModel                   (Atlas-owned adapter)
               →  EmbeddingResult / EmbeddingVector          (Atlas-owned result)
               →  rerank_candidates(...)                     (Atlas-owned policy)
               →  Atlas.semantic_module_search(...)          (read-only surface)
```

New: `atlas/semantic_similarity.py`, `atlas/evolution/semantic_ranking.py`,
`ollama_embedding_transport` in `atlas/specialist_transport.py`, the
`SEMANTIC_SIMILARITY` capability in the existing closed
`SPECIALIST_CAPABILITIES` vocabulary, `SpecialistsSettings.embeddings_*` typed
config, `Atlas._build_embedding_model`, `Atlas.semantic_similarity_available`,
`Atlas.semantic_module_search`. **No new registry, no new framework, no second
source of truth.**

### Trust boundary (applied, not asserted)

specialist output → count/dimension/finiteness/schema validation → Atlas-owned
result → deterministic margin policy → re-order of Atlas's own candidates, or the
deterministic order unchanged. Never `specialist output → execution`. Never
`confidence → authorization`.

### Real measurement (real model, real repository)

| Query | applied | lead | outcome |
| --- | --- | --- | --- |
| "where does Atlas rank repository modules by lexical relevance" | **true** | +0.0797 | re-ordered; `repository_map` → #1 |
| "how does Atlas repair a failed change after a test failure" | **false** | +0.0451 | **refused — inside the 0.05 uncertainty margin** |
| "how is human approval enforced before anything is promoted" | **true** | +0.0892 | re-ordered |

*Every* run: `is_permutation: true` (the candidate set was never changed),
768 dimensions, provider `ollama.embeddings`, model `nomic-embed-text`.

Measured cost: ~13.8 s cold (first call loads the model) for 3 texts, then
**25–53 ms warm** per call; 6-candidate re-ranking adds ~0.1–1 s. Deterministic:
identical input → identical vectors. Semantic separation is real (similar pair
0.607 vs unrelated 0.360).

### Bugs found BY the real probes and fixed

1. **Typed config ignored the new keys.** `SpecialistsSettings` is a typed
   dataclass and `_specialists_settings` dropped unknown keys, so
   `embeddings_enabled` silently resolved to `false`. Fixed in
   `configuration_models.py` + `configuration.py`.
2. **The transport's response bound was far too small** for numeric payloads
   (`MAX_RESPONSE_CHARS = 40_000` clipped a 7×768 reply, so every call returned
   `{}`). Fixed with the dedicated `MAX_EMBEDDING_RESPONSE_CHARS = 2_000_000`.
3. **`rerank_candidates` could raise** on a non-iterable candidate set. Fixed —
   it is now total.

None of these were visible without actually running the model.

## 4. Verification status of the specialist

| State | Verdict |
| --- | --- |
| PREPARED | yes |
| AVAILABLE | yes (`nomic-embed-text`, local) |
| INTEGRATED | yes (kernel-wired, opt-in, off by default) |
| **REAL-EXECUTED** | **yes** (real model, real repository, real kernel surface) |
| **VALIDATED** | **yes** (focused tests + real probes, all three policy outcomes) |

## 5. Tests

* `tests/test_semantic_similarity.py` — adapter/contract: bounding, malformed
  replies, non-finite values, booleans-as-numbers, dimension bounds, count
  mismatch, undefined cosine, unavailable/disabled/raising transports, determinism,
  protocol conformance.
* `tests/test_semantic_ranking.py` — the consumer boundary: the permutation
  invariant, refusals (no candidates / no query / no specialist / no signal),
  uncertainty preservation (agrees / below margin), applied re-ordering, ties,
  bounds, malformed inputs, "never raises", no-authority fields.
* `tests/test_semantic_specialist_kernel.py` — kernel integration: the
  deterministic default posture, the opt-in posture over an injected transport,
  the permutation invariant, auditability, no-authority fields, determinism, and
  the repository-unchanged check.

**59 focused tests pass** (49 contract + 10 kernel integration).

## 6. What was NOT done, and why

* **No GLiNER / SetFit / compact intent / coreference / code-encoder / cross-encoder
  model was installed.** Each would add `torch`/`onnxruntime` for a capability
  Atlas either already has deterministically or has no evidenced gap for. Every
  one is recorded as `DEFER` with its reasoning.
* **No vector database, no orchestration framework, no second generative coding
  LLM.** `REJECT`, per the hard limits.
* **No durable task ledger / resumption.** Not evidenced: the loop is bounded,
  single-process and sandbox-disposable.
* **The deterministic intake phrasing gap (2e) was recorded, not fixed** — it is a
  bounded follow-up that belongs to the language/intake area, and fixing it inside
  this command would have been uncontrolled scope growth.

## 7. Remaining limitations

* The semantic specialist **cannot invent candidates**; it only re-orders the set
  Atlas's lexical ranking produced. This is a deliberate, principled boundary
  (it keeps the specialist out of the authority path), and it means a request
  with zero lexical overlap with any module still gets no candidates.
* `nomic-embed-text`'s exact license terms should be re-verified at deployment
  before any redistribution; the model is a **parameter**, so it can be swapped
  without touching Atlas.
* `Atlas.semantic_module_search` builds the repository map lazily on first use
  (~10 s for this repository); the map is then cached.
* The `specialists` code-generation provider and the embedding specialist remain
  **off by default** (`config.toml`), so default Atlas behaviour is
  byte-for-byte deterministic.

## 8. Pre-existing failures

Not modified, weakened or reclassified. Known and unchanged:
`tests/test_builtin_self_knowledge.py::TestKernelWiring::test_kernel_architecture_provider_is_cache_only`,
the `TestRealKernel` "no resolvable … gap" failures in
`tests/test_evidence_governed_development.py` and
`tests/test_evidence_directed_development.py`, plus `test_intake_contract[H7-0]`
and `test_development_need_confirmation_fails_closed`.

## 9. Recommended next step

The highest-value next step is **NOT** another model. It is the bounded
deterministic intake improvement identified in §2e: make the development-request
recognizer robust to ordinary natural phrasings so a realistic request is routed
to the (already working) governed development pipeline. That is a
language-understanding fix with the strongest evidence base of anything in this
command.
