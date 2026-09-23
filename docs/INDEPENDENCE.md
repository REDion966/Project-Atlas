# Atlas Runtime Independence Report (Phase 12)

Evidence-backed validation that Atlas is genuinely independent of external AI
models, external AI provider APIs, and external coding agents **at runtime**.

Method: static AST analysis of the whole `atlas/**` tree, a deterministic
dependency inventory (`atlas/self_knowledge/independence_inventory.py`),
model-free boot and lifecycle tests, subprocess-isolated clean-environment
tests, and one bounded end-to-end demonstration. Nothing was imported,
executed, or modified by the audit itself.

> Regenerate the machine-readable inventory with:
> `python -c "from atlas.self_knowledge.independence_inventory import *; print(build_independence_inventory(repository_root()).to_markdown())"`

## 1. External runtime dependency inventory

Exactly **one** external (non-stdlib) module is imported anywhere in
`atlas/**`:

| module | classification | imported at boot | AI-related | imported by |
| --- | --- | --- | --- | --- |
| `requests` | `INFORMATION_SOURCE` | yes | **no** | `atlas/ai/failure.py`, `atlas/ai/providers/*.py` |

* **Required external AI dependencies: none.**
* **Prohibited AI/coding-agent imports found: 0.**
* **Unclassified dependencies: none.**
* Declared requirements (`pyproject.toml` / `requirements.txt`): `requests>=2.28`
  (declared) and `pytest>=8` (test extra only).

`requests` is a generic HTTP client. It is imported transitively at boot
because the kernel imports `atlas.ai.ai_manager`, which imports the (inert)
provider classes. It backs the authorized research web source and the
*optional* external-provider seam. It is **not** an AI/model/provider SDK, and
no AI SDK is installed or imported.

## 2. Dependency classification

| class | members | evidence |
| --- | --- | --- |
| `REQUIRED_RUNTIME` | *(none)* | no AI/provider SDK is imported; the only required library is classified `INFORMATION_SOURCE` |
| `OPTIONAL_RUNTIME` | `atlas.ai.providers.*` (OpenAI / Ollama / LM Studio / Anthropic / OpenRouter) | Atlas's own classes; the ACTIVE provider is the local no-network tier unless `[ai].external_providers = true` |
| `DEVELOPMENT_ONLY` | `pytest`; **local tool executables** `pytest` (sandbox runner) and `rg` (bounded repository search) | only used by tests/sandbox and bounded local search; neither is an AI agent |
| `INFORMATION_SOURCE` | `requests`, plus the authorized web research adapter (host-allowlisted, SSRF-guarded) | ordinary authorized retrieval, not AI interpretation |
| `UNKNOWN` | *(none)* | eliminated by the inventory |

## 3. Development-time tooling vs runtime dependency

Command Code / Cline / IDE tooling used while developing Atlas is
**development-time tooling only**. The audit found no runtime reference to any
such tool: no import, no subprocess invocation of an agent CLI, and no
configuration entry. Only two subprocess sites exist, both bounded local tools:

* `atlas/conversation/investigation.py` — `rg` with a fixed literal argv for
  repository search;
* `atlas/evolution/autonomy/sandbox_tools.py` — the sandbox pytest runner with a
  built argv, a controlled env, `shell=False`, a timeout, and a confined
  workspace.

## 4. Optional model seams (never required, never authoritative)

| seam | guarantee |
| --- | --- |
| `ModelAssistedChangeSupplier` | OFF by default (`[development].model_assisted_authoring = false`); needs an injected authoring model; returns `None` on any failure; output is `origin="model-assisted-draft"` and `content_status="unverified-draft"`; rejects unsafe/sensitive paths and unsupported fields; never imports `atlas.ai` |
| `atlas.ai.providers.*` | inert objects; `external_providers = false` by default makes the active provider the local no-network tier; API keys empty by default; `allow_fallback = false` |
| `ChangeSupplier` protocol | default implementation is deterministic (`DeterministicChangeSupplier` / `ScaffoldChangeSupplier`) |
| Web research | deny-by-default host allowlist (`web_allowed_hosts = []`); SSRF protections mandatory |

## 5. Model-free boot evidence

With every external AI ecosystem unimportable, the AI environment variables
absent, and every outbound socket connection refused, `Atlas().start()`
succeeds and initializes: architecture/capability/repository self-knowledge, the
component registry, capability registry/dispatcher, research coordinator,
governance rule engine, and the self-development loop. The active provider is
`Mock Provider` (local, no network); no connection attempt is recorded; no AI
SDK enters `sys.modules`.

## 6. Model-free behaviour evidence

* Conversation: deterministic built-in engine answers greet/self-knowledge
  turns with `model_used: False`; ambiguous requests ask for clarification;
  unsupported requests are declined honestly. A provider double that always
  raises still yields a deterministic answer with no leaked/fabricated output.
* Self-knowledge / memory / research: architecture/capability/repository models,
  history, validated-knowledge retrieval, deny-by-default web policy, and
  technology analysis all run without a model. Unverified claims remain
  unusable; a missing research store fails closed with no fallback.
* Development / self-evolution: the full governed lifecycle completes with no
  external AI and spawns only Python/pytest processes — never an agent CLI.
* Capability acquisition: the acquisition-strategy and post-internalization
  validation layers run model-free and stay advisory.

## 7. Governance and boundedness

Verified mechanically: external AI cannot grant authority; discovery cannot
authorize development; research cannot activate capabilities; verification
cannot authorize promotion; review approval does not activate; activation does
not start another cycle; unapproved development is denied; unverified changes
cannot be promoted; unauthorized promotion is refused; escaping sandbox changes
fail closed; architecture-sensitive targets are protected; malformed lifecycle
state fails closed; model absence never fabricates success; evolution is bounded
(hard cap of 3 sandbox iterations, one cycle, `next_cycle_allowed = False`); no
daemon/tick/`run_forever`/scheduler surface; no `eval`/`exec`/`shell=True`/
unrestricted subprocess/network mechanism.

## 8. Clean/minimal-environment evidence

An isolated child process with a minimal environment (no AI variables, no user
site-packages, AI SDKs unimportable) boots Atlas, answers a conversation turn,
and reports `Mock Provider` with a positive capability count. Blocking the one
required external library (`requests`) produces an explicit import failure —
the required-core vs missing-optional distinction. No AI dependency behaves
this way.

## 9. Genuine limitations

* **`requests` is required at boot** (via the provider modules) even though no
  external AI is ever contacted. It is a generic HTTP library, not an AI
  dependency; removing that import path would be a cosmetic refactor and was
  deliberately not performed in a validation phase.
* Provider *classes* are imported at boot; they are inert and never invoked
  unless `external_providers = true`.
* Discovery/eligibility matching is lexical; change generation is bounded to
  deterministic scaffold classes (arbitrary open-ended synthesis is not
  implemented and is not solved with an LLM).
* The web source requires an explicit allowlist entry before any fetch; that is
  a deliberate governance property, not an independence gap.

## 10. Verdict

No mandatory external AI/model/provider dependency, no external coding-agent
dependency, no unresolved `UNKNOWN` classification, and no governance bypass
was found. Atlas's core identity, reasoning, research, development, and
self-evolution paths are deterministic and model-independent; external models
remain optional, bounded, fail-soft seams.
