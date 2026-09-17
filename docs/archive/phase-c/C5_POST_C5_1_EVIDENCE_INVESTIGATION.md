# PROJECT ATLAS — C5 POST-C5.1 EVIDENCE INVESTIGATION

Milestone: C5 — Atlas Self-Knowledge / Capability Model (Phase C)
Mode: INVESTIGATION ONLY (no code/test/config/schema/governance/roadmap changes)

---

## 1. STATUS

**C5 OBJECTIVE SATISFIED**

After C5.1, Atlas possesses evidence-backed, deterministic, model-independent,
read-only self-knowledge of its capability surface: what capabilities exist, which
are deterministic vs dependent on optional external models/tools, which are
unknown, which components provide them, component health, per-claim
source/evidence attribution, and evidence-based limitations — reachable through a
production kernel accessor and a read-only CLI. No genuine remaining C5
capability gap was identified.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree: the pre-existing modified tracked files (7) and untracked
  artifacts (C3.3/C4/C5 evidence + implementation files) — unchanged by this
  investigation. No staged files.
- C5.1 baseline (validated): canonical model with 101 entries (96 capabilities +
  5 tools), 35 components, `deterministic=86 / external_model_dependent=5 /
  unknown=10`, `HEALTHY=35`, 3 source kinds, 2 evidence-based limitations;
  deterministic kernel accessor; read-only CLI; full lifecycle validation PASS;
  full suite 5876 passed / 0 failed / 0 errors / 2 skipped.

---

## 3. AUTHORITATIVE C5 OBJECTIVE

Reconstructed from the frozen roadmap and the C5 readiness artifact
(`C5_READINESS_INVESTIGATION.md` §3): C5 is *Atlas understanding itself* —
"what Atlas is, what it can do, what it cannot, which capabilities are
deterministic vs dependent on optional external tools, which are
production-reachable, what evidence supports each claim, and what
boundaries/limitations are known — reported honestly, model-independently,
deterministically-first, read-only, with no governance change."

Evidence: `C5_READINESS_INVESTIGATION.md:31-36`; the frozen Phase C roadmap
(C5 = "Atlas Self-Knowledge / Capability Model").

---

## 4. C5.1 CAPABILITY COVERAGE

C5.1 (`atlas/self_knowledge/capability_model.py`, kernel accessor
`atlas/kernel/atlas.py::capability_model`, CLI
`atlas/cli/capability_commands.py` + `atlas/cli/main.py` `capabilities`)
satisfies the capability-facing part of the objective:

- **What capabilities exist** — 101 canonical entries projected from
  `ComponentRegistry` (`lifecycle/component_registry.py:19`),
  `CapabilityRegistry.registered_names` (`reasoning/execution/registry.py:12,92`),
  and `ToolRegistry.list()` (`tools/registry.py:15,73`).
- **Which are deterministic vs external-model-dependent vs unknown** —
  `CapabilityDependency` derived from the providing component `package`
  (evidence rule `_EXTERNAL_MODEL_PACKAGE_PREFIX = "atlas.ai"`; unknown when no
  providing component/tool).
- **Which components provide them** — `CapabilityEntry.components`.
- **Health/availability** — `ComponentMetadata.status`
  (`lifecycle/models.py:67`) mapped via `_derive_availability`.
- **Evidence supporting claims** — `CapabilitySource(kind, reference, detail)`.
- **Known boundaries/limitations** — evidence-based per-entry and model-level
  limitations only; no invented "Atlas cannot X".
- **Deterministic, model-independent, read-only** — validated (see §10).
- **Production reachable** — kernel accessor + read-only CLI (validated).

---

## 5. REMAINING C5 REQUIREMENTS

| Requirement | Classification | Basis |
|---|---|---|
| Canonical capability inventory | **SATISFIED** | 101 entries from live registries |
| Deterministic vs external-tool classification | **SATISFIED** | `CapabilityDependency`; 86/5/10 |
| Providing component per capability | **SATISFIED** | `CapabilityEntry.components` |
| Component health/availability | **SATISFIED** | `status` → availability; `HEALTHY=35` |
| Evidence/source attribution | **SATISFIED** | `CapabilitySource`; 3 source kinds |
| Evidence-based limitations ("what it cannot") | **SATISFIED** | 2 grounded model limitations; no fabricated negatives |
| Honest unknown/uncertainty | **SATISFIED / EXPECTED UNKNOWN** | 10 handler-only entries explicitly `unknown` |
| Determinism / model-independence / read-only | **SATISFIED** | C5.1 validation §7–§8, §13 |
| Production surface (kernel + CLI) | **SATISFIED** | accessor + `capabilities` command |
| "What Atlas is" (identity) | **SATISFIED elsewhere / NOT REQUIRED here** | identity subsystem + self-model exist; not a capability-model field |
| Per-capability *user-facing* reachability label | **NOT REQUIRED (speculative)** | no authoritative reachability source exists; source-kind attribution already conveys registration origin |
| Conversational self-Q&A ("what are your capabilities?") | **OUTSIDE C5** | C7/human-understanding boundary (explicitly out of C5.1 scope) |
| Capability performance/learning over time | **OUTSIDE C5** | C6 knowledge/learning maturity (SelfModelEngine metrics) |
| Persistence/history of the capability model | **NOT REQUIRED** | C5.1 is read-only projection; no persistence authorized |

---

## 6. EVIDENCE MATRIX

| Requirement | Evidence | Status | Notes |
|---|---|---|---|
| Inventory populated | `capability_model.py` `CapabilityModelBuilder.build`; CLI `--json` | SATISFIED | 101 entries / 35 components |
| Deterministic classification | `_EXTERNAL_MODEL_PACKAGE_PREFIX="atlas.ai"`; `ai_service`/`model_router` packages | SATISFIED | 5 external, 0 misclassifications (C5.1 validation §10) |
| Source attribution | `CapabilitySource`; verified against registries | SATISFIED | 3 kinds; 0 fabricated sources |
| Health | `ComponentMetadata.status`; `_derive_availability` | SATISFIED | `HEALTHY=35`; no mutation |
| Limitations | per-entry + model-level, evidenced | SATISFIED | 2 statements; no "atlas cannot" |
| Determinism | 3× kernel builds + 2 CLI runs identical | SATISFIED | C5.1 validation §8 |
| Model independence | 0 AI calls; stdlib-only imports | SATISFIED | C5.1 validation §7 |
| Production surface | `Atlas.capability_model()`; `capabilities` CLI | SATISFIED | exit 0; JSON matches kernel |
| Reachability source (evidence) | Only registry origin (component/capability/tool) exists | PARTIAL→NOT REQUIRED | no user-facing reachability registry in repo (grep) |
| Identity ("what Atlas is") | `atlas/identity/*`, `atlas/experience/self_model_engine.py` | EXISTS (separate subsystem) | not a capability-model field |
| Conversational self-Q&A | none | OUTSIDE C5 | C7 boundary |

---

## 7. GAP ANALYSIS

**NO GENUINE C5 CAPABILITY GAP IDENTIFIED.**

The one plausible candidate — a per-capability *production/user-facing
reachability* field mentioned in the C5 objective ("which are
production-reachable") — does **not** qualify, because:

1. The repository contains **no authoritative source** recording user-facing
   reachability. The only "catalog" modules are constant vocabularies
   (`atlas/longterm/catalog.py:1-11` — episode/procedure categories), not
   capability-exposure data; a repo-wide search for `reachab|exposed|discovery`
   finds only docstrings about governance execution reachability, no registry.
2. Deriving it would require a **new mapping** (conversation `TaskType` →
   handler, CLI command → capability, orchestration tool → capability) — i.e.
   inventing a reconciliation rule, which the mission (§G) says to reject as
   speculative.
3. An **evidence-based registration-origin signal already exists** in the model:
   `CapabilitySource.kind` distinguishes `capability_registry` (dispatch-registered
   / routable), `tool_registry` (orchestration-reachable), and
   `component_registry` (component-declared capability). All three sources are
   production runtime registries populated at kernel startup, so every entry is
   production-registered by construction.
4. The 10 `unknown` entries are an **expected, honest** representation of
   handler-registered capabilities that no component declares — not a defect
   (§I).

Therefore C5's capability-self-knowledge objective is satisfied at the current
evidence boundary.

---

## 8. BOUNDARY ANALYSIS

- **C6 (knowledge/learning maturity):** capability *performance* metrics
  (`CapabilityProfiler` confidence/maturity/stability,
  `atlas/identity/capability_profiler.py:14`; `SelfModelEngine`) and
  knowledge lifecycle belong to C6; C5.1 correctly exposes capability existence,
  not learning maturity.
- **C7 (human understanding):** conversational self-Q&A and reference
  resolution (GAP-C31-02) are C7 concerns. The prior C5 readiness investigation
  explicitly identified conversational self-Q&A as a future boundary, not a C5.1
  requirement (`C5_READINESS_INVESTIGATION.md` §11, §15 non-goals).
- **C8 (autonomy):** no autonomy/exposure of new execution paths is required;
  C5.1 is read-only.
- **C9 (continuous evolution):** continuous/self-updating capability evolution is
  out of scope.
- **Already-completed C5.1:** inventory, classification, attribution, health,
  limitations, determinism, kernel accessor, CLI — all done and validated.
- **Speculative/non-requirements:** per-capability user-facing reachability label;
  persistence/history of the model; identity narrative in the model.

None of these constitutes a genuine C5 capability gap.

---

## 9. MODEL-INDEPENDENCE CHECK

C5/C5.1 requires no Ollama, Qwen, llama.cpp, OpenAI, Anthropic, Gemini, localhost
inference, or API key:

- `atlas/self_knowledge/capability_model.py` imports only `collections`,
  `dataclasses`, `enum`, `typing`; a test asserts no model/network imports.
- Live validation recorded **0 AI calls** while building the model with a
  failing-AI double present.
- The read-only CLI builds the full inventory with no model configured.

**PASS.**

---

## 10. VERIFICATION

- `python -m pytest tests/test_capability_model.py -q` → **39 passed, 0 failed,
  0 errors (exit 0)**, 21.5s. (No C5.1 defect introduced.)
- Live CLI: `python -m atlas.cli.main capabilities --json` → exit 0;
  `component_count=35`, `capability_count=96`, `tool_count=5`, `entry_count=101`;
  source kinds `{capability_registry, component_registry, tool_registry}`;
  `deterministic=86 / external_model_dependent=5 / unknown=10`; 2 limitations.
- Reference (C5.1 lifecycle validation, unchanged tree): full suite **5876
  passed, 0 failed, 0 errors, 2 skipped**.
- No failure, regression, or unexpected behavior observed; nothing to classify.

---

## 11. READ-ONLY INTEGRITY

- Branch `main`; HEAD `f85de89` — unchanged before/after this investigation.
- No source, test, configuration, schema, persistence, governance, CLI, or
  conversation behavior modified; no generated code; no roadmap change; no
  staged files; no commit/push/reset/clean/stash; no deletion/rename.
- The only new repository artifact is this investigation report.

---

## 12. RECOMMENDATION

**CLOSE C5.**

C5's objective — evidence-backed, deterministic, model-independent, read-only
self-knowledge of Atlas's capability surface (existence, providing components,
deterministic vs optional external-tool dependency, honest unknowns, health,
per-claim source/evidence, and evidenced limitations), exposed through a
production kernel accessor and a read-only CLI — is satisfied and validated by
C5.1. No genuine remaining C5 capability gap is supported by the repository
evidence; the plausible candidate (per-capability user-facing reachability) is a
speculative enrichment without an authoritative source, and conversational
self-Q&A is a C7 boundary. **No C5.2 is authorized or invented.**
