# PROJECT ATLAS — C5 AUTHORITATIVE SCOPE / READINESS INVESTIGATION

Milestone: C5 — Atlas Self-Knowledge / Capability Model (Phase C)
Mode: INVESTIGATION ONLY (no production/test/config/governance/roadmap changes)

---

## 1. STATUS

**READY** — C5's authoritative interpretation is established, a genuine C5
capability gap is validated with evidence, and one bounded first step
(**C5.1 — Canonical Deterministic Capability Model**) is justified and defined.
No implementation was performed.

---

## 2. BASELINE

- Branch: `main`; HEAD: `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree (unchanged by this investigation): 7 pre-existing modified tracked
  files; pre-existing untracked files plus the C3.3/C4 artifacts
  (`atlas/conversation/investigation_synthesis.py`, `test_investigation_synthesis.py`,
  `atlas/conversation/repository_impact.py`, `test_repository_impact.py`,
  `C4_CHARTER.md`, `C4_1_CAPABILITY_GAP_EVIDENCE.md`, `C4_2_REAL_WORLD_VALIDATION.md`).
- Staged/deleted/renamed: none. Only new artifact: this report.

---

## 3. AUTHORITATIVE C5 INTERPRETATION

C5 is **Atlas understanding itself**: what Atlas is, what it can do, what it
cannot, which capabilities are deterministic vs dependent on optional external
tools, which are production-reachable, what evidence supports each claim, and
what boundaries/limitations are known — and being able to reason about and
report that surface honestly, model-independently, deterministically-first,
read-only, with no governance change.

---

## 4. EXISTING SELF-KNOWLEDGE ARCHITECTURE

Atlas already contains substantial internal self-knowledge:

- **Lifecycle `ComponentRegistry`** (`atlas/lifecycle/component_registry.py:19`)
  with `ComponentMetadata` (`atlas/lifecycle/models.py:33`: name, package,
  module_path, description, version, status, dependencies, provided_capabilities).
  Populated at startup from `CORE_COMPONENTS` (`atlas/lifecycle/component_definitions.py:28`)
  plus per-track wiring, via `Atlas._register_components` (`atlas/kernel/atlas.py:3544`,
  called `:3370`); exposed as `Atlas.component_registry` (`:3540`) and registered
  in the ServiceContainer as `component_registry` (`:3373`). Query API:
  `get_all`, `get_by_package`, `get_by_capability`, `get_capability_map`,
  `get_all_capabilities`, `summary`, status observation.
- **`CapabilityRegistry`** (`atlas/reasoning/execution/registry.py:12`) — handler
  functions keyed by capability name; exposes only `registered_names`/`count`
  (names, no descriptions/classification).
- **`ToolRegistry`** (`atlas/tools/registry.py:15`) — registered tools.
- **`CapabilityProfiler`** (`atlas/identity/capability_profiler.py:14`) — profiles
  capabilities with confidence/maturity/stability; seeded from a **hardcoded**
  `DEFAULT_CAPABILITIES` list of 10 abstract abilities (`:25`); stored in
  `IdentityMemory`.
- **`SelfModelEngine`** (`atlas/experience/self_model_engine.py:32`) +
  `SelfModelSnapshot` (`atlas/experience/models.py:118`) — *performance*
  self-model; wired at kernel `:2631`, set on the RuntimeCoordinator `:3223`,
  persisted (`atlas/storage/experience_storage.py:382`, `self_model_snapshots`
  table `atlas/storage/migration.py:983`).
- **Per-track catalogs / metadata** (`research/source_catalog.py`,
  `longterm/catalog.py`, `toolchain/catalog.py`, `advanced_reasoning/catalog.py`)
  and per-track `wiring.py` registrars.
- **CLI self-management review** — `atlas postcore review`
  (`atlas/cli/postcore_commands.py:348`) reports degraded/offline components,
  availability, and maintenance needs, sourced from lifecycle component statuses
  (`atlas/evolution/self_management.py:339-384`). Health-oriented, CLI-only.

---

## 5. EXISTING CAPABILITY MODEL / INVENTORY

- There **is** an inventory, but it is **component-centric**, not capability-centric:
  `ComponentRegistry` holds components with a flat, hand-maintained
  `provided_capabilities` string list. Observed at runtime: **35 components,
  86 capability strings** (pilot).
- There is **no single authoritative capability-centric source of truth**.
  Overlapping/partial sources exist:
  1. `ComponentRegistry` (35 components / 86 capability strings; structure + status).
  2. `CapabilityRegistry` (handler names only; no metadata).
  3. `ToolRegistry` (tools only, different concept).
  4. `CapabilityProfiler.DEFAULT_CAPABILITIES` (10 hardcoded abstract abilities —
     not derived from the registries; potential conflict/duplication).
  5. Per-track catalogs.
- There is **no classification** of deterministic vs external-model-dependent
  capability, **no production-reachability flag**, **no per-claim evidence/provenance
  field**, and **no limitations representation** anywhere (repo-wide search for
  limitation/unsupported/unavailable/locked found only runtime notices and
  governance docs, not a capability model).

---

## 6. PRODUCTION REACHABILITY

- **Conversation (`Atlas.chat` → `ConversationService.send`): NO path** to the
  component/capability model. Pilot (failing AI): "What are your capabilities?"
  → `QUESTION` → `tool_guidance` (lists registered **tools** only);
  "What are your limitations?" and "How many components do you have?" →
  `QUESTION` → `degraded_notice`. None surfaced the 35 components/86 capabilities.
- **Kernel:** `Atlas.component_registry` accessor exists but has **no production
  consumer** (only tests: `tests/test_evolution_gateway.py:612`,
  `tests/test_kernel_longterm_integration.py:93`, `tests/test_kernel_advanced_reasoning_integration.py:189`).
- **CLI:** `atlas postcore review` exposes component **health**, not the
  capability inventory; no CLI command exposes the capability model.
- **Self-model:** surfaced only as **AI prompt context** via
  `RuntimeCoordinator._build_self_model_section` (`runtime_coordinator.py:1271`
  → `:1213-1215`), never returned deterministically to the user.

Status summary: ComponentRegistry = production-populated, **internal/test-observed**;
CapabilityRegistry/ToolRegistry = production-reachable internally; CapabilityProfiler/
SelfModelEngine = production-wired, prompt-context only; CLI review = production,
health-only; **conversational self-knowledge = absent**.

---

## 7. CAPABILITY CLAIM + EVIDENCE ANALYSIS

- `ComponentMetadata` carries **no evidence/provenance** field; capability claims
  are declarative.
- `CapabilityProfiler` carries confidence/maturity/stability metrics but seeds a
  **hardcoded** capability list that can diverge from the runtime registries.
- No claim is traceable to a test, record, or evolution artifact from within a
  capability model (Evidence/EvolutionRecord/LearningInsight exist but are not
  linked to capability claims).

---

## 8. CURRENT LIMITATIONS

- No representation of capabilities that are **unavailable / deferred /
  governance-restricted** in a capability model (only scattered runtime notices
  and roadmap prose).
- No distinction between **deterministic** capabilities and those requiring an
  **optional external AI model**.
- No honest **"what Atlas cannot do"** surface.
- Rich self-knowledge exists but is **unreachable** through the conversational
  path and not exposed as a capability model anywhere.

---

## 9. DEFECT VS CAPABILITY-GAP CLASSIFICATION

- **No defect found.** No existing contract is violated: the registries and
  self-model behave as documented; `Atlas.component_registry` is intentionally an
  observation accessor; the conversational fallback is the designed behavior for
  questions without a deterministic handler.
- The missing conversational self-knowledge surface alone would be a
  **category D (interface/capability-exposure)** limitation.
- However, evidence shows a deeper issue: **there is no canonical, authoritative,
  evidence-backed capability model** (multiple overlapping partial sources, no
  classification, no limitations, no provenance). That is a genuine
  **C5 architectural capability gap**, not merely a missing interface.

---

## 10. C3/C4 RELATIONSHIP

- C3 produced real-world **capability-gap evidence**; C4 turned a validated gap
  into a **governed capability improvement** (C4.2 real-world validated).
- C5 is complementary: **Atlas's own knowledge of its capability surface and
  boundaries**. It can consume existing sources (ComponentRegistry,
  CapabilityRegistry, ToolRegistry, CapabilityProfiler, plus EvolutionRecord/
  LearningInsight evidence) **without redesigning C3/C4**.

---

## 11. C6/C7/C8/C9 BOUNDARY CHECK

- General conversational reference resolution (GAP-C31-02) → **C7** (deferred).
- Knowledge/learning maturity → **C6**.
- Human understanding → **C7**.
- Controlled autonomy expansion / promotion automation → **C8**.
- Continuous Atlas evolution → **C9**.
None is an unavoidable C5 dependency (C5's model is a deterministic read-only
projection over existing registry sources).

---

## 12. MODEL-INDEPENDENCE AUDIT

C5 (and C5.1) require **no** Ollama/Qwen/llama.cpp/OpenAI/Anthropic/Gemini, no
localhost model endpoint, and no API key. The capability model would be a pure
deterministic projection; it must explicitly mark which capabilities *depend on*
an optional external tool, without Atlas itself depending on one. **PASS.**

---

## 13. GENUINE C5 GAP?

**YES.**
Evidence:
- Runtime `ComponentRegistry` = 35 components / 86 capability strings, yet no
  canonical capability-centric source of truth; ≥5 overlapping/partial sources
  (§5).
- No deterministic-vs-external-tool classification, no production-reachability
  flag, no per-claim evidence, no limitations representation (§5, §7, §8).
- Conversational self-knowledge is absent: 3/3 realistic self-questions fell to
  the AI fallback; `tool_guidance` listed tools only (§6; pilot).
- Reproducible, bounded, and not a defect (§9); not C6–C9 (§11).

---

## 14. SMALLEST JUSTIFIED NEXT STEP

**OUTCOME A** — authorize a single bounded C5.1: build ONE canonical,
deterministic, read-only capability model by projecting the existing authoritative
sources, with classification, status, evidence sourcing, and honest limitations,
exposed through a deterministic read-only production surface. This is the minimum
architectural responsibility: an authoritative source of truth derived from
existing data — **no new capability registration, no persistence, no
conversational NLU, no governance change, no model**.

---

## 15. C5.1 — EXACT SCOPE

**Name:** C5.1 — Canonical Deterministic Capability Model

**Objective:** Produce one authoritative, deterministic, read-only capability
model for Atlas that unifies existing runtime sources and classifies each
capability, with evidence-based limitations, reachable through a deterministic
read-only production surface.

**Problem/evidence:** §5–§8, §13.

**Production boundary:** kernel-owned read-only accessor (e.g.
`Atlas.capability_model()`) + a read-only CLI presentation command. **No
conversational NLU** (that would be a separate later substep).

**Likely files/symbols:** a new pure module (e.g.
`atlas/self_knowledge/capability_model.py`) projecting
`ComponentRegistry.get_all()/get_all_capabilities()/get_capability_map()`,
`CapabilityRegistry.registered_names`, `ToolRegistry`; a kernel accessor in
`atlas/kernel/atlas.py`; a presentation-only CLI command; focused tests.
No change to existing registries or `ComponentMetadata`.

**Required behavior:**
- enumerate capabilities from existing sources, each citing its source;
- classify each: **capability vs tool**, and **deterministic vs
  external-model-dependent** (evidence rule: providing component's package is
  `atlas.ai`);
- include component health status from the lifecycle registry;
- represent **evidence-based limitations** only (e.g., external-model-dependent
  capabilities; deferred conversational reference resolution) — no invented ones;
- stable, sorted, deterministic ordering.

**Non-goals:** no new registries/persistence/schema; no conversational NLU or
reference resolution (GAP-C31-02); no governance/authorization/execution/sandbox
change; no autonomous behavior; no external model; not C6–C9.

**Invariants:** model-independent; deterministic-first; read-only; fail-closed;
no mutation; no governance change.

**Acceptance criteria:**
1. A single canonical inventory enumerates capabilities from the existing sources, each citing its source.
2. Each entry classifies capability vs tool and deterministic vs external-model-dependent, using the registry's own fields (not a guess).
3. Component health status is included from the lifecycle `ComponentRegistry`.
4. Known limitations/boundaries are represented and each is tied to evidence; no fabricated limitations.
5. Deterministic/reproducible: identical inputs → identical output (stable ordering).
6. Read-only: no mutation; no new persistence/schema; `modification_status` NONE.
7. Model-independent: works with the external AI unavailable; no external model required.
8. Reachable through a production surface (kernel accessor + read-only CLI command), not tests only.
9. No governance/authorization/execution/sandbox change; no new capability registration.
10. Focused tests cover enumeration, classification, status, limitations, determinism, and the accessor.
11. Existing regression remains clean (0 failed / 0 errors).
12. Does not implement GAP-C31-02 or general NLU.

**Verification strategy:** focused unit tests for the pure model; an integration
test through the kernel accessor; a CLI smoke test; then the relevant regression
suite (and full suite when implemented).

**Real-world validation strategy:** run against a live `Atlas` instance and show
the canonical inventory (e.g. 35 components / 86 capabilities) with per-entry
source, classification, and limitations, deterministically and with the external
AI unavailable.

**Dependencies:** `ComponentRegistry`, `CapabilityRegistry`, `ToolRegistry`,
`CapabilityProfiler`, kernel composition.

**Why C5 (not C6–C9):** it concerns Atlas's own capability surface and boundaries,
not knowledge/learning maturity (C6), human understanding (C7), autonomy (C8), or
continuous evolution (C9).

---

## 16. TEST / VERIFICATION RESULTS

- `python -m pytest tests/test_lifecycle_component_registry.py tests/test_identity.py tests/test_cognitive_context_self_model.py tests/test_model_independence_p6.py tests/test_experience.py -q`
  → **172 passed, 0 failed, 0 errors (exit 0)**, 20.3s.
- Pilot (real `Atlas.chat`, failing AI, read-only, temp storage): internal
  `ComponentRegistry` = 35 components / 86 capabilities; 3/3 self-knowledge
  questions fell to the deterministic AI fallback; `git status` unchanged.
- No failure observed; nothing to classify.

---

## 17. REPOSITORY INTEGRITY

- Branch `main`; HEAD `f85de89` — unchanged throughout.
- No production file, test, config, governance, sandbox, or execution change;
  no commit/push/reset/clean/stash; no deletion/renaming; pre-existing changes
  preserved. Only new artifact: this investigation report.

---

## 18. FINAL VERDICT

**READY.** C5 is authoritatively interpreted as Atlas's knowledge of its own
capability surface and boundaries. A genuine C5 architectural capability gap is
validated by evidence — there is no canonical, evidence-backed capability model
(multiple overlapping partial sources; no deterministic-vs-tool classification;
no limitations; not conversationally reachable), despite a populated 35-component/
86-capability registry. The smallest justified next step is **C5.1 — Canonical
Deterministic Capability Model** (§15), bounded to a read-only deterministic
projection plus a read-only production accessor. **No C5.x was implemented and no
roadmap document was modified.** A separate C5.1 implementation command may be
issued against this scope.
