# Project Atlas — Final End-State Pre-Validation Audit

**Type:** read-only pre-validation audit (not the final acceptance validation).
**Scope:** repository state, architecture, independence, governance/boundedness, final end-state chain.
**Method:** static inspection (AST scans, targeted source reads) + previously executed and newly executed *focused* test runs. No source/config/git modifications were made; the only file created is this report.

---

## 1. Repository State

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `648d870 feat: complete bounded self-knowledge interface` |
| Recent commits | `648d870` (bounded self-knowledge interface), `5620f8a` (architecture self-knowledge → development planning), `47f6ae7` (L3–L10 language integration), `1fe8ed4` (test consolidation), `0d83245` (docs consolidation) |
| Working tree | 12 modified, 138 untracked, 0 staged |
| Modified (all pre-existing, not from this audit) | `atlas/conversation/builtin_response.py`, `atlas/conversation/development_need_coordinator.py`, `atlas/conversation/development_need_dialogue.py`, `docs/ROADMAP.md`, and 8 `tests/*.py` |
| Untracked | Phase 7–13 production modules (`atlas/research/technology_analysis.py`, `atlas/evolution/{capability_acquisition,capability_discovery,self_development_inventory,self_evolution,evolution_continuity}.py`, `atlas/self_knowledge/independence_inventory.py`), Phase 2.5–13 test files, `docs/INDEPENDENCE.md`, `docs/CONTINUOUS_EVOLUTION.md`, `tests/test_conversational_independence.py` |

**Generated / scratch artifacts present in the tree (git-ignored or untracked, pre-existing):**
`atlas_data/atlas_experience.db` (281 MB), `atlas_data/atlas_experience.db.bak` (14 MB), `atlas_data/evolution.sqlite3` (0 bytes), `data/memory.json`, `logs/atlas.log`, `MagicMock/DEFAULT_WORKSPACE/` (stray `unittest.mock` path leaked to disk), and root scratch files `atlas_entry_inspection.txt`, `atlas_entry_references.txt`, `mission_output.txt`.

**Structural observations:** `atlas/` is an implicit namespace package (no `atlas/__init__.py`) while `pyproject.toml` declares `packages = ["atlas"]`. All 10 storage adapters share `DEFAULT_DB_PATH = atlas_data/atlas_experience.db`; the 0-byte `atlas_data/evolution.sqlite3` is not referenced by any `DEFAULT_DB_PATH` found in `atlas/storage/`.

---

## 2. Architecture Summary

**Scale:** 41 packages under `atlas/` (~118,900 LOC); 439 files under `tests/`.

**Entry points:** `main.py` → `atlas.cli.cli.AtlasCLI.run()` (interactive REPL: `while True` + blocking `input()`, one `Atlas.tick()` per completed turn); console script `atlas.cli.main:main` (argparse one-shot subcommands, e.g. `workspace`, `evolution`, `autonomy`, `promotion`).

**Kernel:** `atlas/kernel/atlas.py::Atlas.start()` wires 12 domains in order: `_init_ai_provider` → `_init_memory_knowledge` → `_init_reasoning_pipeline` → `_init_cognitive_engines` → `_init_tracks` → `_init_evolution_pipeline` (+ `_init_promotion_gate`) → `_init_environment_observer` → `_init_lifecycle_assessor` → `_init_adaptation_engine` → `_init_adaptation_evaluator` → `_init_adaptation_orchestrator` → `_init_operation_controller` → `_init_development_cycle` → `_init_self_management_review` → `_init_proactive_advisor` → `_init_runtime_services` (+ `_init_information_acquisition`).

**Subsystem boundaries (actual files):**

| Subsystem | Implementation |
|---|---|
| Conversation / language | `atlas/conversation/conversation_service.py` (`send()` line 671; built-in deterministic engine + `_deterministic_fallback` line 609), `task_intake.py`, `builtin_response.py`, `investigation.py`, `level1–level5_execution.py` |
| Understanding / cognition | `atlas/understanding/*`, `atlas/cognition/{engine,pipeline,decision}.py`, `atlas/services/cognition_service.py` |
| Reasoning / planning | `atlas/reasoning/{engine,analyzer,controller,reflection,outcomes}.py`, `atlas/runtime/{runtime_coordinator,heartbeat,health}.py`, `atlas/goals/{goal_execution_engine,priority_engine}.py` |
| Self-knowledge | `atlas/self_knowledge/{architecture_model,capability_model,independence_inventory}.py`, `atlas/research/repository_map.py` |
| Capability system | `atlas/reasoning/execution/{registry,routing,dispatcher}.py`, `atlas/reasoning/capabilities/`, `atlas/tools/{registry,selector,executor}.py` |
| Development engine | `atlas/evolution/{development_cycle,development_planner,development_scaffold_supplier,development_test_selection,self_development_loop,development_verification,development_diagnostic,development_recovery}.py` |
| Sandbox | `atlas/evolution/autonomy/{code_sandbox,code_execution,sandbox_tools}.py` |
| Governance / approval | `atlas/evolution/{approval_manager,development_authorization,development_envelope,execution_gateway}.py`, `atlas/evolution/governance/{rule_engine,constraint_registry}.py`, `atlas/authority/` |
| Promotion / activation | `atlas/evolution/{promotion_gate,promotion_executor,promotion_artifact,capability_activation}.py` |
| Evolution / self-development | `atlas/evolution/{self_evolution,capability_discovery,capability_acquisition,development_gap,evolution_memory,evolution_continuity,self_management,improvement_planner,scheduler,operation/}.py`, `atlas/evolution/autonomy/` |
| Research / acquisition | `atlas/research/{planner,selector,extractor,verifier,coordinator,validated_retrieval,technology_analysis}.py`, `atlas/research/sources/web.py` |
| Persistence / history | `atlas/storage/*_storage.py` (10 adapters), `atlas/memory/`, `atlas/longterm/`, `atlas/experience/`, `atlas/evolution/evolution_memory.py` |
| AI (optional) | `atlas/ai/{ai_manager,ai_service,registry,provider,availability}.py`, `atlas/ai/providers/*` |

**Governed path (direct-evolution family):** `Discovery (Phase 10) → Eligibility → Objective → DevelopmentNeed → DevelopmentCycleController (research gate + plan + DRAFT proposal) → ApprovalManager (PENDING_APPROVAL) → [HUMAN APPROVAL] → SelfDevelopmentLoop (disposable CodeSandbox + pytest) → DevelopmentVerification → DevelopmentDiagnostic/Recovery → EvolutionMemory evidence → PromotionGate (review) → [HUMAN PROMOTION AUTHORIZATION] → PromotionExecutor (+ CapabilityActivator) → self-model validation → outcome learning → TERMINATE.**

**Second execution family (Phase-16 autonomy envelopes):** `atlas/evolution/autonomy/{authorization_manager,application_engine,dispatcher,validator,risk_assessor,schedule_store}.py`. It is *separately* governed: `validator.py:348` and `authorization_manager.py:159,280` reject `UNKNOWN`/`IDENTITY`/**`CODE`** scopes, and `execution_gateway.py:368-373` refuses the same scopes on the UNKNOWN-close invariant; `authorize_autonomously` therefore cannot authorize code change, and `code_execution.py` applies CODE only inside a sandbox. Autonomy authorizations carry a 60-minute TTL (`models.py:134`) and expired ones are rejected (`dispatcher.py:437-441`, `authorization_manager.py:364-368`).

---

## 3. Model Independence

**Determination: external AI is NOT mandatory. Atlas core runs model-free.**

| Evidence | Detail |
|---|---|
| External (non-stdlib) imports in `atlas/**` | **only `requests`** — `atlas/ai/failure.py`, `atlas/ai/providers/{openai,anthropic,ollama,lmstudio,openrouter}_provider.py`. No AI/model/provider SDK is imported anywhere. |
| Provider credential reads | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` — read **only** inside `atlas/ai/providers/*` |
| Active provider at boot | `MockProvider` (local, no-network). External providers require `[ai].external_providers = true` (default `false`); `allow_fallback = false`; API keys empty by default (`config.toml`) |
| Governance/verification independence | `promotion_gate.py`, `promotion_executor.py`, `capability_activation.py`, `approval_manager.py`, `development_verification.py`, `development_diagnostic.py`, `development_recovery.py`, `governance/rule_engine.py`, `self_knowledge/capability_model.py`, `evolution_continuity.py` import **no** `atlas.ai`, `requests`, or network module |
| Executed proof (Phase 12, previously run) | Kernel boot + conversation + full governed lifecycle with every AI SDK unimportable, all AI env vars removed, and every socket connection refused; zero connection attempts; no AI SDK entered `sys.modules` |
| Classification of the 96 provider-name occurrences (24 files) | **B** optional seam: `atlas/ai/providers/*`, `ai_manager.py`, routing/model vocabulary, `ModelAssistedChangeSupplier` (opt-in, default off). **E** documentation/audit/comment references: `self_knowledge/independence_inventory.py`, `conversation/builtin_response.py` (deterministic engine text), config/model comments. **F** dead/legacy: `MagicMock/`, and the unreachable `atlas/core/application.py` + `atlas/runtime/runtime.py` loop. **No `A` core mandatory external AI dependency exists.** |

---

## 4. Final End-State Chain

| Step | Capability | Evidence (implementation → test) | Status |
|---|---|---|---|
| 1 | Human ↔ natural conversation | `AtlasCLI.run()` → `Atlas.chat/stream` → `ConversationService.send()` → `builtin_response.py`; `tests/test_phase125_model_free_conversation.py` | PASS |
| 2 | Goal understanding | `task_intake.py` (`TaskSpec`), `understanding/*`, cognition pipeline; `tests/test_phase42_goal_interpretation.py`, `test_builtin_self_knowledge.py` | PASS |
| 3 | Self-understanding | `self_knowledge/architecture_model.py`, `capability_model.py`, `research/repository_map.py`; `tests/test_architecture_model.py`, `test_phase124_model_free_boot.py` | PASS |
| 4 | Capability assessment | `capability_model.py` (101 entries at boot), `reasoning/analyzer.py`, `capability_dispatcher.py`; `tests/test_capability_model.py`, `test_phase51–59`, `test_phase124` | PASS |
| 5 | Genuine gap detection | `evolution/capability_discovery.py` (`run_discovery_cycle`); `tests/test_phase101–108`, `test_phase1310` | PASS |
| 6 | External research | `research/{planner,source_selection,source_adapter,acquisition,coordinator}.py`, `sources/web.py` (deny-by-default allowlist, empty by default); `tests/test_phase71–73`, `test_phase34_external_knowledge.py` | PARTIAL — pipeline + policy tested with local/fake sources; **no live external fetch executed** |
| 7 | Research validation | `research/{extractor,verifier,validated_retrieval}.py`; `tests/test_phase74–77`, `test_validated_knowledge_retrieval.py`, `test_phase126` | PASS |
| 8 | Technology/mechanism analysis | `research/technology_analysis.py`; `tests/test_phase74–76`, `test_phase126` | PASS |
| 9 | Atlas-native design | `development_cycle.py` (objective → bounded scaffold design), `development_scaffold_supplier.py`; `tests/test_phase115`, `test_phase94` | PARTIAL — design is bounded to the deterministic scaffold change class; no research→design end-to-end test |
| 10 | Governed development plan | `development_planner.py` + `DevelopmentCycleController.run_development_cycle`; `tests/test_phase115`, `test_phase62` | PASS |
| 11 | Implementation | `SelfDevelopmentLoop` + `SandboxImplementer`; `tests/test_phase117` | PASS |
| 12 | Sandbox execution | `autonomy/code_sandbox.py` (disposable root), `code_execution.py`; `tests/test_phase117`, `test_phase129` (escape → `SandboxPathError`) | PASS |
| 13 | Tests executed | `development_test_selection.py` + E4 `pytest_tool` in `sandbox_tools.py`; `tests/test_phase96`, `test_phase117` | PASS |
| 14 | Verification | `development_verification.py` (`VERIFIED`/`UNVERIFIED`/`PARTIAL`/`UNVERIFIABLE`); `tests/test_phase118`, `test_phase67` | PASS |
| 15 | Evidence/provenance | `EvolutionMemory` records + `EvolutionRecord`/`EvolutionInsight`; `tests/test_phase1110`, `test_phase1312` | PASS |
| 16 | Approval requested | `approval_manager.create_approval_request` → `PENDING_APPROVAL`; `tests/test_phase116`, `test_phase610` | PASS |
| 17 | Approval granted | `ApprovalManager.approve` + `update_proposal_from_decision`; `tests/test_phase116`, `test_phase912` | PASS |
| 18 | Separate promotion authorization | `PromotionExecutor.promote(authorized=...)` → `REFUSED_UNAUTHORIZED`; `tests/test_phase1111`, `test_phase911` | PASS |
| 19 | Integration/promotion | `promotion_artifact.capture_promotion_artifact` + `PromotionExecutor` (transactional, verified rollback); `tests/test_phase1111`, `test_phase1310` | PASS |
| 20 | Self-knowledge updated | `self_evolution.project_evolved_capability` + `validate_self_model`; `tests/test_phase1112` | PASS |
| 21 | Capability model updated | `build_capability_model(component_registry, capability_registry=...)`; `tests/test_phase1112`, `test_phase139` | PASS |
| 22 | Evolution history persisted | `EvolutionMemory(storage=SQLiteEvolutionStorage)` + `restore()`; `tests/test_phase132` | PASS |
| 23 | State survives restart | `tests/test_phase136_cross_process_restart.py` (two OS processes) | PASS |
| 24 | Later cycle uses history | `evolution_continuity.continuation_view` + `gate_candidates`; `tests/test_phase1310` (Cycle 1 → terminate → Cycle 2) | PASS |
| 25 | Prior authorization cannot authorize a new cycle | per-invocation `owner_approved`/`promotion_authorized` (default `False`); `tests/test_phase138` | PASS |

---

## 5. Acceptance Matrix

| # | Criterion | Evidence | Status | Confidence | Gap |
|---|---|---|---|---|---|
| 1 | Complete chain demonstrated | `test_phase1210_end_to_end_independence.py`; `test_phase1310` (2 cycles) | PASS | High | research leg is component-level only |
| 2 | Chain works without external AI | Phase 12 suite (92 tests) + `test_phase127`, `test_phase139` | PASS | High | — |
| 3 | Accurate architecture self-knowledge | `architecture_model.py`; boot test asserts non-None + component counts | PASS | High | derived from `ComponentRegistry` (35 components) |
| 4 | Accurate capability/limitation knowledge | `capability_model.py` (101 entries, evidence-derived dependency/availability/limitations) | PASS | High | AI-dependent entries carry explicit limitations |
| 5 | Genuine gap detection | `capability_discovery.py`; `test_phase101–108` | PASS | High | lexical matching, documented |
| 6 | External research + validation | `research/*`, `validated_retrieval.py`, web policy | PARTIAL | Medium | no live external fetch; unverified claims correctly unusable |
| 7 | Research → Atlas-native design | `technology_analysis.py`; `test_phase78_research_to_development.py` | PARTIAL | Medium | no single research→design→plan e2e test |
| 8 | Governed development lifecycle | `test_phase1114`, `test_phase6*`, `test_phase9*` | PASS | High | scaffold-class change generation only |
| 9 | Sandbox prevents production modification | `code_sandbox.py`; `test_phase117`, `test_phase129`; production written only by `PromotionExecutor` | PASS | High | — |
| 10 | Verification evidence required | `development_verification.py`; `test_phase118`; `PromotionGate` → `NOT_PROMOTABLE` | PASS | High | — |
| 11 | Human approval authoritative | `ApprovalManager`; `test_phase116`, `test_phase610`, `test_phase138` | PASS | High | — |
| 12 | Promotion requires separate authorization | `PromotionExecutor` authorized flag; `test_phase1111` | PASS | High | — |
| 13 | Evolution updates self-knowledge/capability state | `project_evolved_capability`, `validate_self_model`; `test_phase1112`, `test_phase912` | PASS | High | — |
| 14 | Evolution persists across processes | `EvolutionMemory`+`SQLiteEvolutionStorage`; `test_phase132`, `test_phase136` | PASS | High | — |
| 15 | Later invocation uses previous history | `continuation_view`, `gate_candidates`; `test_phase1310` | PASS | High | window-bounded (`max_records`) |
| 16 | Previous authorization cannot authorize a future cycle | `test_phase138` (fresh approval/authorization required per cycle) | PARTIAL | Medium-High | a restored `APPROVED` proposal stays executable at OWNER request via `Atlas.run_development_execution` — no approval expiry on that path |
| 17 | No external AI in core path | AST scans; `config.toml` defaults; Phase 12 executed evidence | PASS | High | `requests` (non-AI) is imported at boot |
| 18 | No uncontrolled recursion/daemon/scheduler/infinite evolution | no `threading`/`asyncio` imports; `SelfEvolutionPolicy` caps; `next_cycle_allowed=False`; **but** `atlas/runtime/runtime.py::AtlasRuntime.run()` is an unbounded `while … time.sleep` loop reachable only via `atlas/core/application.py`/`startup.py`, which nothing imports | PARTIAL | High | unreachable autonomous loop surface; `EvolutionScheduler.tick()` auto-generates DRAFT proposals (analysis only) |
| 19 | Failure/uncertainty/missing evidence/invalid state fail closed | `test_phase11_negative_paths.py` (25 paths), `test_phase129` (17 invariants) | PASS | High | — |
| 20 | Modular and deterministic-first | 41 packages; deterministic engines; provider optional | PASS | High | legacy/overlapping packages (`intelligence`, `learning`, `learning_engine`, `collective`, `advisory`) |
| 21 | No speculative Phase 14 / mandatory future subsystem | `docs/ROADMAP.md` ends at Phase 13 (COMPLETE); `test_phase1314`, `test_phase1211` | PASS | High | — |
| 22 | No hidden second development architecture | two families exist: direct-evolution and Phase-16 autonomy envelopes; both governed, autonomy cannot reach `CODE` (`validator.py:348`, `authorization_manager.py:159,280`, `execution_gateway.py:368-373`) | PARTIAL | High | duplicate surface, not a bypass |
| 23 | No uncontrolled autonomous evolution loop | `next_cycle_allowed=False`; no self-chaining; `test_phase135`, `test_phase1310` | PASS | High | see #18 caveat (unreachable Runtime loop) |

**Tally:** PASS 18 · PARTIAL 5 · FAIL 0 · UNKNOWN 0.

---

## 6. Governance Findings

- **Approval:** per-proposal only. `DevelopmentCycleController` submits a DRAFT proposal to `ApprovalManager` and stops at `PENDING_APPROVAL`; `SelfDevelopmentLoop.run` refuses anything that is not `APPROVED`/`SANDBOX_AUTHORIZED` → `GOVERNANCE_DENIED`. `SelfEvolutionLoop.run` requires explicit `owner_approved` and `promotion_authorized` (both default `False`).
- **Authorization:** `execution_gateway.py` UNKNOWN-close invariant refuses `UNKNOWN`/`IDENTITY`/`CODE`; the autonomy validator/authorizer refuse the same scopes; autonomy authorizations expire after 60 minutes; `PromotionExecutor` refuses without explicit OWNER authorization.
- **Promotion:** review ≠ promotion (`PromotionGate.approve` sets `APPROVED`, never `PROMOTED`); `PromotionExecutor` is transactional with verified rollback (`REFUSED_STALE`, `FAILED_ROLLED_BACK`, `ROLLBACK_UNVERIFIED`); architecture-sensitive prefixes (`atlas.kernel.`, `atlas.storage.`, `atlas.runtime.`, `atlas.evolution.governance`) are refused unless explicitly allowed.
- **Sandbox:** every development write goes through a disposable `CodeSandbox`; path escape raises `SandboxPathError`; the only production writer is `PromotionExecutor` (byte-hash pre/post state, path confinement).
- **Evidence:** `DevelopmentVerification` must return `VERIFIED`; `PromotionGate.assess` yields `NOT_PROMOTABLE` on non-SUCCESS/rollback/unverified; `EvolutionMemory` stores `self_evolution_development`, `promotion_review`, `evolution_outcome` records plus insights.
- **Persistence:** `EvolutionMemory` + `SQLiteEvolutionStorage` (`store_*`/`load_*`, `restore()`); Phase 13 continuity projection is read-only over it and creates no second store.
- **Bounded execution:** `SelfEvolutionPolicy.max_development_iterations ≤ 3`; `MAX_EXPLICIT_CYCLES = 5` (further capped by `OperationPolicy`); no `threading`/`asyncio` imports anywhere in `atlas/`; `EvolutionContinuity` contains no loop/thread/subprocess/time usage.
- **Fail-closed transitions:** missing evidence → `REJECTED_CANDIDATE`/`RESEARCH_REQUIRED`; unapproved → `STOPPED_AT_APPROVAL`; sandbox failure → `SANDBOX_FAILED`; unverified → `VERIFICATION_FAILED`; stale/duplicate promotion → `PROMOTION_FAILED` with rollback; malformed lifecycle → `INVALID_LIFECYCLE_STATE`; unknown terminal → `DEFERRED` (never `READY`).

---

## 7. Targeted Verification

**Executed in this audit pass (focused, read-only, no kernel boot):**

| Command | Result |
|---|---|
| `pytest tests/test_phase11_negative_paths.py tests/test_phase1310_multi_cycle_demonstration.py tests/test_phase136_cross_process_restart.py tests/test_phase129_governance_boundedness.py -q` | **49 passed** (17.1 s) |
| AST census over `atlas/**` (external imports, subprocess sites, dynamic imports, API-key env vars) | only `requests`; 2 subprocess sites; 4 dynamic-import sites (all `atlas.*`); 3 provider key env vars |
| AST scan of 10 governance/verification modules for `atlas.ai`/network imports | clean (first-party only) |
| `git status` / `git log` / artifact listing | see §1 |

**Previously executed in this repository (cited, not re-run):** Phase 13 suite 75 passed; Phase 11–13 suites 264 passed; Phase 12 suite 92 passed; a 2,635-test checkpoint across Phases 1–12 + AI + `test_evolution_*` with **6 failures in `tests/test_evolution_model_assisted_activation.py`** (they assert the kernel wires a bare `DeterministicChangeSupplier`, but `atlas/kernel/atlas.py` has wired a deterministic-first `CompositeChangeSupplier` since the Phase 5.2 era) — pre-existing, unrelated to Phases 11–13; `py_compile` clean; `git diff --check` exit 0.

**Documentation discrepancy:** `docs/ATLAS_STATE.md` (§ baseline) claims `5,945 test items, 5,876 passed, 0 failed` as the authoritative current baseline; a full-suite run was not performed in this audit and the observed 6 failures mean that claim is not reproducible as stated.

---

## 8. Critical Blockers

**None.** No mandatory external AI dependency, no reachable governance bypass, no reachable uncontrolled evolution loop, and no unresolved `UNKNOWN` dependency classification was found.

---

## 9. Missing Evidence

*(missing proof, not missing implementation)*

1. No single-pass full-suite green baseline (`5,876 passed / 0 failed` is documented but currently includes 6 stale failures and previously out-of-scope suites).
2. No live external-research execution (by design: `web_allowed_hosts = []` deny-by-default); the research leg is verified with local/fake sources.
3. No research → technology-analysis → design → plan single-flow end-to-end test.
4. No coverage measurement was produced, so no numeric coverage claim is made.
5. The final system-level acceptance validation has not been performed.

---

## 10. Non-Critical Weaknesses

1. **Unreachable autonomous loop surface:** `atlas/runtime/runtime.py::AtlasRuntime.run()` (`while self.state.running: kernel.tick(); time.sleep(...)`) reachable only via `atlas/core/application.py::Application.run()` and `atlas/core/startup.py::start()`, neither of which is imported by any entry point (`main.py` uses `AtlasCLI`; the console script uses `atlas.cli.main:main`). It cannot approve/promote/develop, but it is a latent loop.
2. **Tick-driven proposal generation:** `Atlas.tick()` → `EvolutionScheduler.tick()` (threshold/interval-gated) creates DRAFT proposals + approval requests and calls `goal_executor.settle()`/`autonomy_dispatcher.settle()`. Analysis only — never execution, approval, or promotion — but it is an automatic *proposal* path that deserves explicit documentation in the acceptance test.
3. **No approval expiry on the owned-proposal execution path:** `Atlas.run_development_execution(proposal_id)` accepts any restored `APPROVED` proposal after an OWNER authority check; `ApprovalRequest` has no TTL (the Phase-16 autonomy authorizations do, 60 min).
4. **Packaging:** `atlas/` has no `__init__.py` while `pyproject.toml` declares `packages = ["atlas"]`.
5. **Repository hygiene:** stray `MagicMock/DEFAULT_WORKSPACE/`, three root scratch `.txt` files, a 281 MB `atlas_data/atlas_experience.db` (+14 MB `.bak`), and a 0-byte unreferenced `atlas_data/evolution.sqlite3`.
6. **Two execution families** (direct-evolution vs Phase-16 autonomy envelopes) — both governed, neither bypasses the other's boundaries, but the duplication increases audit surface.
7. **Six stale tests** in `tests/test_evolution_model_assisted_activation.py`.
8. **Stale documentation baseline** in `docs/ATLAS_STATE.md` (§ baseline).

---

## 11. False Positives

| Looks concerning | Why it is correctly governed |
|---|---|
| Active provider named "Mock Provider" | Deliberate local **no-network** tier; external providers activate only with explicit `[ai].external_providers = true` |
| `requests` imported at boot | Generic HTTP client, not an AI SDK; used by the optional provider seam and authorized research |
| `subprocess.run` in two modules | Bounded local tools: `rg` with a fixed literal argv (`conversation/investigation.py`), sandbox `pytest` with built argv, `shell=False`, controlled env, timeout (`evolution/autonomy/sandbox_tools.py`) |
| `ScopeType.CODE` constants in policy/authorization code | Refused by the gateway UNKNOWN-close invariant and rejected by the autonomy validator/authorizer; CODE executes only inside a sandbox |
| Five concrete provider modules in `atlas/ai/providers/` | Atlas's own inert classes; never invoked unless opted in |
| `MagicMock/` and `data/`, `logs/` | Test/runtime artifacts, not architecture |
| Provider names in `config.toml`/models | Configuration vocabulary, not a dependency |
| `improvement_planner`, `adaptation/*`, `operation/*` "parallel" mechanisms | Pre-existing bounded F-series analysis layers; they produce proposals/decisions and cannot approve, execute, or promote |

---

## 12. Final Readiness

**READY FOR FINAL VALIDATION**

The repository is internally coherent enough to proceed: the governed chain (discovery → eligibility → objective → plan → human approval → sandbox → focused tests → verification → evidence → promotion review → separate promotion authorization → activation → self-model validation → durable outcome → later explicitly invoked bounded cycle) is implemented, and its critical boundaries are enforced and test-verified; Atlas boots, converses, reasons, plans, researches, develops, verifies, promotes, activates, and continues across processes **without any external AI dependency**. The five PARTIAL criteria are limitations of *demonstration breadth* (live research, research→design e2e, approval-expiry on one legacy execution path, an unreachable loop surface, and a duplicate-but-governed execution family) — none of them is a blocker, and all are documented above for the final acceptance run to address or explicitly accept.

---

## 13. Evidence Index

**Production modules:** `atlas/kernel/atlas.py` (`Atlas.start`, `tick`, `run_development_cycle`, `run_development_execution`, `approve_promotion_review`, `promote_validated_change`); `atlas/conversation/conversation_service.py` (`send`, `_deterministic_fallback`); `atlas/conversation/task_intake.py`; `atlas/self_knowledge/{architecture_model,capability_model,independence_inventory}.py`; `atlas/reasoning/execution/{registry,routing,dispatcher}.py`; `atlas/evolution/{development_cycle,development_planner,self_development_loop,development_verification,promotion_gate,promotion_executor,promotion_artifact,capability_activation,approval_manager,evolution_memory,self_evolution,capability_discovery,capability_acquisition,evolution_continuity,development_gap}.py`; `atlas/evolution/autonomy/{code_sandbox,code_execution,sandbox_tools,authorization_manager,validator,execution_gateway}.py`; `atlas/research/{planner,validated_retrieval,technology_analysis,sources/web}.py`; `atlas/storage/evolution_storage.py`; `atlas/ai/{ai_manager,provider}.py`.

**Tests (key):** `tests/test_phase1210_end_to_end_independence.py`, `test_phase124_model_free_boot.py`, `test_phase127_model_free_development.py`, `test_phase129_governance_boundedness.py`, `test_phase1310_multi_cycle_demonstration.py`, `test_phase1311_safety_audit.py`, `test_phase1312_long_term_knowledge.py`, `test_phase1314_acceptance.py`, `test_phase136_cross_process_restart.py`, `test_phase138_human_governed_continuation.py`, `test_phase11_negative_paths.py`, `test_phase1114_bounded_cycle.py`, `test_phase911_governed_promotion.py`, `test_phase912_model_free_development.py`, `tests/phase12_environment.py`, `tests/phase13_support.py`.

**Documents:** `docs/ROADMAP.md` (Phases 0–13 COMPLETE), `docs/INDEPENDENCE.md`, `docs/CONTINUOUS_EVOLUTION.md`, `docs/ATLAS_STATE.md`, `docs/ATLAS_CORE.md`.

**Configuration:** `config.toml` (`[ai] external_providers = false, allow_fallback = false`; `[development] model_assisted_authoring = false`; `[research] web_allowed_hosts = []`), `pyproject.toml`, `requirements.txt` (`requests>=2.28`).
