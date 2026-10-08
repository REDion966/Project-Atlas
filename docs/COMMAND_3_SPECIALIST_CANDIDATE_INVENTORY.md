# COMMAND 3 — SPECIALIST CANDIDATE INVENTORY

Bounded research artifact. **This is an inventory, not a dependency list.**
Nothing here is added to Atlas because it appears here; each row states what was
decided and why.

Baseline: `7d91641` (Command 2 complete). Atlas runtime dependencies at the start
of this command: **`requests>=2.28` only** (plus `pytest` as a test extra). No ML
framework of any kind was present.

## 0. Method

`research → candidate capability → Atlas current-state inspection → actual
evidence/gap → mechanism evaluation → smallest useful implementation →
Atlas-native adaptation → focused verification → real probe → evidence →
decision`

Fresh independent research was performed (GitHub, Hugging Face, project
documentation, PyPI, papers) **in addition to** the previous four-model
inventory, which was treated as input, not law. Type classes:

* **TYPE 1 — architecture mechanism** (may be implemented natively),
* **TYPE 2 — small specialist model** (may be integrated behind an Atlas seam),
* **TYPE 3 — large/general external model** (optional provider only, never core).

Recommendations: `REJECT` / `DEFER` / `ADAPT` / `INTEGRATE` / `OPTIONAL_PROVIDER`.

## 1. What Atlas already has (checked BEFORE evaluating anything)

Inspected directly, not assumed:

| Area | Atlas-native mechanism that already exists |
| --- | --- |
| Repository structure | `atlas/research/repository_map.py` — modules, imports, symbols, **symbol regions, reference sites, unambiguous caller/callee edges** (Command 2), BM25 `rank_modules` |
| Repository context | `atlas/evolution/context_builder.py` — one bounded builder, fixed selection order, hard character budget |
| Structural editing | `atlas/evolution/structural_editor.py` — AST-anchored `replace`/`insert_after`/`delete` |
| Development intelligence | `development_localization`, `development_planner`, `change_author_router` (ChangePlan), `development_test_selection`, `verification_attribution`, `change_guard`, `development_diagnostic`, `development_repair` |
| Governance | `approval_manager`, `promotion_gate`, sandbox (`CodeApplier`/`CodeSandbox`), `development_authorization` |
| Self-knowledge | `architecture_model`, `capability_model`, `operational_capabilities`, `development_capabilities` (Command 6) |
| Language | `atlas/language/` (L0–L10 mapping) + `atlas/conversation/` — deterministic intake, semantic frame, entity identification/capture, reference resolution (RESOLVED/UNRESOLVED/AMBIGUOUS), salience, discourse state, clarification |
| Optional model seams | `atlas/specialists.py` (registry/proposal/task), `specialist_providers.py`, `specialist_transport.py`, `model_intent_parser.py`, `learned_proposer.py`, `linguistic.py`, `language/providers.py` |

**Consequence:** several research candidates are already-implemented mechanisms
wearing a different name. Those are `REJECT`/`ADAPT`, never `INTEGRATE`.

## 2. Inventory

### A/B. Repository & code understanding

| # | Capability | Candidate | Source | Type | Size | Runtime | LICENSE | Atlas gap? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Repo map + symbol ranking | Aider repo map (PageRank over symbols) | aider docs/repo | 1 | — | any | Apache-2.0 | **No** — Command 2 symbol graph + BM25 covers it | **REJECT** (mechanism already absorbed; PageRank **DEFER** — no evidenced ranking gap) |
| A2 | Compact repo/file/symbol views | **ast-outline / ast-bro** | github.com/ast-outline, pypi, lib.rs | 1 | 1 MB CLI | Tree-sitter | MIT | **No** for outline/map/symbol/structural-grep — Atlas has all four natively. **Hybrid semantic search = a REAL gap** | **ADAPT** — absorb the mechanism (semantic signal), do **not** take the Tree-sitter dependency |
| A3 | AST-aware search + ranking + context budgeting | **Probe** | research inventory | 1 | — | — | — | **No** — Command 2 `context_builder` already does region→callers/deps→tests→budget | **ADAPT** (already adapted) |
| A4 | AST graph + optional semantic retrieval | **Astra** | research inventory | 1 | — | — | — | Partly — the *semantic* half was missing | **ADAPT** — implemented via A2/A16 |
| A5 | Structural search/rewrite | ast-grep | github | 1 | Rust binary | — | MIT | **No** for rewrite (structural editor). *Search* not yet needed | **DEFER** |
| A6 | Multi-language parsing | Tree-sitter / LibCST | — | 1 | — | native | MIT | **No** — Atlas targets one language; `ast` is sufficient, stdlib, zero-dep | **REJECT** (dependency cost > value today) |
| A7 | Graph-based symbol ranking | PageRank over the call graph | multiple | 1 | — | — | — | Not evidenced | **DEFER** |
| A8 | Hybrid lexical + structural retrieval | (pattern) | A2–A4 | 1 | — | — | — | Yes — now delivered natively | **INTEGRATED (Command 2 + 3)** |

### A. Natural-language understanding

| # | Capability | Candidate | Source | Type | Size | CPU | LICENSE | Atlas gap? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A9 | Zero-shot NER (open types) | **GLiNER / GLiNER2** (`gliner2-multi-v1`, ONNX exports) | github.com/fastino-ai/GLiNER2, HF `lion-ai/gliner2-multi-v1-onnx`, PyPI `gliner2-onnx`, arXiv 2507.18546 | 2 | ~200–500 MB | Yes (CPU-efficient, per paper) | MIT (per mirrored card) | **Not evidenced** — Atlas's entity path is catalog-grounded and deliberately high-precision; open-type spans are a *speculative* widening | **DEFER** (would add `onnxruntime`/torch; revisit when a real open-type extraction gap is observed) |
| A10 | Few-shot text classification | **SetFit** | github.com/huggingface/setfit | 2 | sentence-transformer + head | Yes | Apache-2.0 | **No** — needs a labelled corpus + a training pipeline Atlas does not have | **DEFER** |
| A11 | Compact intent classification | `rbojja/intent-classification-small` (SetFit + bge-small), encoder + logistic head | HF, avchauzov blog | 2 | ~30–130 MB | Yes | varies | **No** — `model_intent_parser.py` already occupies the optional-intent slot | **DEFER** (would duplicate a seam) |
| A12 | Dialogue-act classification | compact DA models | research inventory | 2 | ~100 MB | Yes | varies | **No** — `communicative_function.py` + `utterance_meaning.Illocution` are deterministic and sufficient | **DEFER** |
| A13 | Coreference / reference resolution | coreferee, compact span models | research inventory | 2 | ~100 MB+ | Yes | MIT/varies | **No** — `reference_resolution.py` + `discourse_state` + `salience` already resolve with AMBIGUOUS-preserving semantics | **DEFER** |
| A14 | Language identification | (mechanism) | — | 1 | — | — | — | **No** — `atlas/language/routing.detect_language` exists | **REJECT** (duplicate) |
| A15 | Semantic similarity | **`nomic-embed-text`** bi-encoder | Ollama local library; nomic-ai model card | 2 | ~137 M / 768-dim | Yes | Apache-2.0 (verify at deployment) | **YES — Atlas has NO semantic similarity anywhere and says so repeatedly** | **INTEGRATED** ✅ |

### B/C. Ranking, retrieval & code models

| # | Capability | Candidate | Source | Type | Size | CPU | LICENSE | Atlas gap? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | Cross-encoder re-ranking | **mxbai-rerank-xsmall-v1** (0.1B), base (0.2B), large (1.5B) | HF, pypi `mxbai-rerank` | 2 | 100 M–1.5 B | Yes (slow) | Apache-2.0 | Partly — Command 3 delivers *bi-encoder* re-ranking; a cross-encoder is the next precision step | **OPTIONAL_PROVIDER** — reachable through the SAME Atlas seam already built (a different transport + adapter), **DEFER** adoption |
| B2 | Tiny/turbo re-rankers | **jina-reranker-v1-tiny-en / turbo-en** (8k ctx, ONNX exists at `corto-ai/...-turbo-en-onnx`) | jina.ai news, HF | 2 | ~35 M / ~150 M | Yes | **Check per model** (Jina models have usage terms) | Same as B1 | **DEFER** (license must be verified before any use) |
| B3 | Multilingual re-ranking | `bge-reranker-v2-m3`, `Qwen3-Reranker` | recal.so 2026 comparison | 2/3 | 0.5–8 B | Marginal | Apache/MIT varies | **No** — Atlas is English-first with a small multilingual surface | **REJECT** for now |
| B4 | Code encoder / similarity | **CodeBERT / GraphCodeBERT** (125 M, 12 layers, 768-dim, 512 ctx) | github.com/microsoft/CodeBERT, HF | 2 | ~500 MB | Yes | MIT | **No** — Command 2's symbol/reference/region graph answers *structural* similarity; A15 answers *natural-language* similarity | **DEFER** |
| B5 | Generative code model | CodeT5, CodeLlama, DeepSeek-Coder (present locally as `deepseek-coder-v2`) | — | 3 | — | marginal | varies | **No** — Atlas already has the optional `code.generate` provider | **REJECT** (no second generative coding LLM) |
| B6 | Vector database | FAISS / Chroma / Qdrant | — | 1 | — | — | varies | **No** — candidate sets are bounded (≤24) and computed in-memory | **REJECT** (second source of truth; no scale need) |
| B7 | Embeddings | local Ollama `/api/embed` (already installed) | this command | 1 | — | Yes | — | — | **INTEGRATED** ✅ (zero new Python dependency) |

### D. Self-knowledge / architecture intelligence

| # | Capability | Candidate | Type | Atlas gap? | Recommendation |
| --- | --- | --- | --- | --- | --- |
| D1 | Architecture graph | (mechanism) | 1 | **No** — `architecture_model` + `repository_map` | **REJECT** (duplicate) |
| D2 | Capability registry | (mechanism) | 1 | **No** — two catalogues already exist (operational, development) | **REJECT** (a third would be a second source of truth) |
| D3 | Architecture drift detection | (mechanism) | 1 | Not evidenced | **DEFER** |
| D4 | Action/observation records | (mechanism) | 1 | **No** — `evolution_memory`, `runtime_observations`, `self_observation` | **REJECT** (duplicate) |
| D5 | Evidence-backed capability discovery | (mechanism) | 1 | **No** — `development_capabilities` + `capability_gap` | **REJECT** (duplicate) |

### E. Future autonomy infrastructure

| # | Capability | Candidate | Type | Atlas gap? | Recommendation |
| --- | --- | --- | --- | --- | --- |
| E1 | Durable task ledger / resumable execution | `sqlite-task-ledger` pattern, SQLite workflow guides, `larzstate`, `python-durable` | 1/3 | **Not evidenced** — the loop is bounded, single-process and sandbox-disposable | **DEFER** (the *pattern* is absorbable natively with stdlib `sqlite3` when a real resumption need appears; do **not** add a framework) |
| E2 | Orchestration platforms | Temporal, Ray, LangGraph, Durable Task | 3 | **No** | **REJECT** (explicitly forbidden; would become a second authority) |
| E3 | Isolated dev environments | git worktrees, containers, gVisor/Firecracker | 1 | **No** — the disposable sandbox already isolates; a worktree is **not** a security boundary | **DEFER** |

### F. Findings from THIS command's own evidence (not from any model's research)

| # | Finding | Kind | Decision |
| --- | --- | --- | --- |
| F1 | The deterministic development-request recognizer is **phrasing-sensitive**: `"Add … to <path> … preserving behaviour."` is routed to development; `"Implement a development change in <path>: add …"` and `"Add a bounded helper …"` are not (`development_supplied_edit` → `{}`) | Atlas **language/intake** limitation | Recorded as evidence. **Not** a model gap — a targeted deterministic intake improvement is the correct fix, and it is a bounded follow-up, not a specialist. |
| F2 | The real model **can** produce a valid structural proposal (`change/kind/path/source/symbol`) that the existing editor applies with unrelated bytes byte-identical | Atlas capability now **REAL-EXECUTED** | Closes Command 2's unproven item. No new mechanism needed. |
| F3 | A compact embedding model is already installed locally and needs **zero** Python dependency (plain HTTP) | Capability enabler | Led directly to A15's `INTEGRATE`. |

## 3. Decisions actually taken

**INTEGRATE (1):** `semantic.similarity` — a compact local bi-encoder
(`nomic-embed-text`) behind an Atlas-owned contract
(`atlas/semantic_similarity.py`) with a bounded consumer
(`atlas/evolution/semantic_ranking.py`). Chosen because:
(a) it is the ONLY capability with **no** Atlas-native mechanism at all;
(b) it costs **no** new Python dependency (the runtime is already present and is
reached through the existing stdlib transport pattern);
(c) it is small, local, offline, CPU-capable and fully disable-able;
(d) it cannot become an authority — it may only **re-order Atlas's own candidate
set**, never add, remove, authorize, execute or promote.

**ADAPT (4):** ast-outline / Probe / Astra / Aider mechanisms — the useful
*mechanism* (compact structural views, hybrid lexical + semantic ranking,
bounded context budgeting) was absorbed natively in Command 2 and Command 3; no
upstream tool was imported.

**REJECT (11):** Tree-sitter, LibCST as dependencies; Level-3 orchestration
platforms; vector databases; a second generative code LLM; a third capability
registry; duplicate language-ID / architecture-graph / observation mechanisms;
multilingual re-rankers.

**DEFER (13):** GLiNER/GLiNER2, SetFit, compact intent/DA/coref models, code
encoders, cross-encoder and tiny/turbo re-rankers, PageRank symbol ranking,
ast-grep structural search, architecture drift detection, durable task
ledger/resumption, isolated dev environments.

**OPTIONAL_PROVIDER (1):** mxbai-rerank-xsmall-v1 — a plausible precision
upgrade reachable through the *same* Atlas seam, not adopted now.

## 4. The rule that governed every row

> Research findings are not implementation requirements. A candidate is adopted
> only when Atlas has an evidenced gap, the mechanism is narrow, the dependency
> cost is proportionate, and the specialist cannot become an authority.

## Sources

- [ast-outline (GitHub)](https://github.com/ast-outline/ast-outline/) · [ast-outline (PyPI)](https://pypi.org/project/ast-outline/) · [ast-outline → ast-bro (Lib.rs)](https://lib.rs/crates/ast-outline) · [ast-outline semantic search internals](https://deepwiki.com/aeroxy/ast-outline/4.3-semantic-search-internals)
- [mxbai-rerank-xsmall-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-xsmall-v1) · [mxbai-rerank (PyPI)](https://pypi.org/project/mxbai-rerank/) · [Jina Rerankers Turbo and Tiny](https://jina.ai/en-US/news/smaller-faster-cheaper-jina-rerankers-turbo-and-tiny/) · [jina-reranker-v1-turbo-en-onnx](https://huggingface.co/corto-ai/jina-reranker-v1-turbo-en-onnx) · [Best Local Reranker Models 2026](https://www.recal.so/blog/best-local-reranker-models-2026)
- [GLiNER (GitHub)](https://github.com/urchade/GLiNER) · [fastino-ai/GLiNER2](https://github.com/fastino-ai/GLiNER2) · [GLiNER2: An Efficient Multi-Task Information Extraction System (arXiv 2507.18546)](https://arxiv.org/pdf/2507.18546v1) · [gliner2-onnx (PyPI)](https://pypi.org/project/gliner2-onnx/)
- [SetFit (GitHub)](https://github.com/huggingface/setfit) · [intent-classification-small](https://huggingface.co/rbojja/intent-classification-small) · [Embeddings for intent classification: architecture trade-offs](https://avchauzov.github.io/blog/2026/intent-routing-architecture-tradeoffs/) · [Intent Detection in the Age of LLMs (arXiv 2410.01627)](https://arxiv.org/html/2410.01627v1)
- [microsoft/CodeBERT](https://github.com/microsoft/CodeBERT) · [microsoft/graphcodebert-base](https://huggingface.co/microsoft/graphcodebert-base)
- [sqlite-task-ledger](https://github.com/ViceSaber/sqlite-task-ledger) · [Durable workflows with SQLite](https://www.coddykit.com/pages/blog-detail?id=512838&slug=build-durable-workflows-with-sqlite-a-step-by-step-guide) · [python-durable (PyPI)](https://pypi.org/project/python-durable/) · [Durable Task (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/durable-task/)
