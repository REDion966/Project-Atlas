# PHASE 16 — GOVERNED AUTONOMOUS EVOLUTION
## Architecture Specification v2.0

**Status:** Approved · **Scope:** Architecture reference · **Implementation:** IMPLEMENTED in the current repository (Evolution Framework autonomy stack, GOV-011, `execute_request()`/dispatcher) · **Supersedes:** v1.0 (74/100, NOT APPROVED) · **Integrates with:** Phase 15

> This document is the historical design/reference specification for the Phase 16 governed-autonomy framework. The current implementation status is the authoritative source maintained in `docs/ATLAS_STATE.md` (see §11 Governance / Evolution Framework Boundaries); this document is not a current implementation instruction.

- [x] Pre-flight checks (status, HEAD, doc tree)
- [x] Phase 3A: Archive moves (19)
- [x] Phase 3B: Historical banners on TRACK_A/B/C/D
- [x] Phase 3C: Current-document fixes (ATLAS_STATE, ATLAS_CORE, PHASE_16)
- [ ] Phase 3D: Deletes (11 files)
- [ ] Phase 3E: Empty directory cleanup
- [ ] Phase 3F: Reference integrity search + fixes
- [ ] Phase 3G/H: Source protection + validation
- [ ] Phase 3I: Final report (no commit)


---

## 1. Design Decisions

| # | Decision | Resolves |
|---|----------|----------|
| D1 | **Two artifacts, not four.** `EvolutionProposal` proposes; `ImprovementGoal` prioritizes and tool-executes; `EvolutionRequest` orders a governed change to Atlas's own state. Capability upgrades are **not** a fourth artifact — they are `EvolutionRequest`s with `target_scope=CAPABILITY` and `change_payload.upgrade_kind ∈ {REGISTER, ENHANCE, DEPRECATE}`. One lifecycle, one gateway, one rollback/version path. | C4 |
| D2 | **Closed scope map.** `AutonomyRequestAdapter` derives `target_components` **exclusively** from `EvolutionRequest.target_scope` via a closed, immutable map (`CONFIG→["config","autonomy:config"]`, `MEMORY→["memory","autonomy:memory"]`, `KNOWLEDGE→["knowledge","autonomy:knowledge"]`, `CAPABILITY→["capability","autonomy:capability"]`). Components are never user- or payload-influenced, so governance classification cannot be smuggled. A request declaring `target_scope` is structurally unable to produce an UNKNOWN classification. | C1 |
| D3 | **Two typed gateway entry points on one choke point.** Phase 13.4 `execute(proposal)` is **unchanged** (administrative path — proposals/goals). New `execute_request(request)` is the **only** applied-evolution path and requires: translated proposal with pinned scope + injected `application_engine`. Missing either ⇒ fail-closed refusal. Both entry points pass the identical `RuleEngine` governance at the gateway's `current_execution_level`. **Invariant: `execute_request()` refuses any request classifying UNKNOWN, regardless of level.** | C1 |
| D4 | `ToolEngine` remains sole executor for `ActionType.TOOL_INVOCATION` (Phase 15). State mutations are applied only by scope-specific appliers. No cross-channel reuse. | — |
| D5 | Gateway level is set only from `AutonomyPolicy.effective_execution_level` at startup, only when `policy.enabled`. Default remains `ADMINISTRATIVE`. Level is explicit config, never behavior-derived. | — |
| D6 | **Six deterministic gates** (see §7), all fail-closed, including the new translation + UNKNOWN-close gate inside the gateway. | C1 |
| D7 | Autonomy is config-bounded. The running system can never widen its own envelope, alter `ConstraintRegistry`, or change the gateway level. Policy swap is blocked while any request is in a non-terminal state (in-flight exclusion). | C5-adjacent safety |
| D8 | Mandatory rollback: snapshot captured before mutation; rollback plan attached to every applied request; rollback itself versioned and audited. | — |
| D9 | Versioning is a persistent manifest with parent-chain, not a counter. | — |
| D10 | **Single application owner.** `EvolutionAutonomyDispatcher` is the sole caller of `gateway.execute_request()`. CLI `apply` is removed as a direct application path — it becomes `schedule-now` (enqueue). Atomic claim: single-statement CAS `SCHEDULED→APPLIED` in storage; the claim also verifies `current_version == request.version_target.current_version`; mismatch ⇒ `SUPERSEDED`. No double application, no manual bypass. | C2 |
| D11 | **APPLIED ≠ EFFECTIVE.** Config changes are **staged**: applier writes a durable `StagedConfigEntry` (schema-validated) and the request moves to `APPLIED → PENDING_EFFECTIVE`. Activation occurs at next boot via a new **boot activation + verification** step; `COMPLETED` is reached only when the change is effective *and* verified in-session or at boot. Boot failure ⇒ `SAFE_MODE` (system boots on base config; overlay preserved; request → rollback path). Hot-reloadable settings (explicit allowlist in policy) may complete in-session after immediate verification; no hot-reload mechanism is built in Phase 16. | C3, M4 |
| D12 | **Explicit goal transcription rule.** A Phase 15 goal is transcribed into an `EvolutionRequest` **only** at activation when the user/policy declares `execution_mode="state_evolution"` (CLI flag or policy enrollment). Default activation leaves the goal on the Phase 15 ToolEngine path. Transcription sets goal status to a new additive `GoalStatus.TRANSCRIBED`, which `settle()` excludes — the same intent can never execute twice. The `EvolutionRequest` carries the `GoalAuthorization` strategy/planning-context snapshot, preserving Phase 17 evidence linkage. | C5 |
| D13 | Failure is first-class. Governance/validation/authorization failures ⇒ `REJECTED`, never auto-retried; fresh draft required. Application failure ⇒ `FAILED` + immediate rollback if partial mutation detected. Rollback failure ⇒ `EVOLUTION_HOLD`. | — |
| D14 | Governance registry holds only `RuleEngine`-enforceable rules. Add **GOV-005** (CAPABILITY requires SELF_CONFIG) and **GOV-006** (SKILLS requires SELF_CONFIG, additive keyword). **GOV-007 is not registered** — autonomy-envelope membership is not evaluable by `RuleEngine`; it is enforced exclusively in `AuthorizationManager` and stated as a constitutional policy, not a registry rule. | M8 |
| D15 | **Isolation layering.** `autonomy/**` never imports `execution_gateway`, `kernel`, `services`, `ai`, or EventBus. The gateway *injects* the application engine (dependency flows downward). Persistence uses a **new** `AutonomySQLiteStorage` adapter (additive tables); `EvolutionSQLiteStorage` and all Phase 13–15 modules remain untouched. Appliers are pure logic over injected repository interfaces. | M6 |

---

## 2. Dependency Graph

```
atlas/evolution/models.py (existing, + no changes)
        │
        ▲
        │ (pure dataclasses only)
atlas/evolution/autonomy/models.py
   │
   ├───────────────────────────────────────────────┬──────────────────────────┐
   ▼                                               ▼                          ▼
 autonomy/validator.py                     autonomy/risk_assessor.py   autonomy/request_factory.py
 autonomy/scope_classifier.py              (reads DecisionIntelligence (uses GoalRepository,
        │                                   knowledge_query read-only    GoalAuthorization for
        │                                   + goal-layer signals)        transcription source)
        │                                                               autonomy_policy.py (config mirror)
        ▼                                                                       │
 autonomy/authorization_manager.py  ◄────────────── (envelope checks) ──────────┘
        │
        ▼
 autonomy/schedule_store.py ──► storage/autonomy_storage.py ──► SQLite (additive tables only)
        │
        ▼
 autonomy/autonomy_request_adapter.py   (D2 closed scope map; Phase 15 adapter untouched)
        │
        ▼
 atlas/evolution/execution_gateway.py  (extended additively: optional application_engine
        │                                + execute_request() → same RuleEngine governance
        │                                + UNKNOWN-scope invariant)
        ▼
 autonomy/application_engine.py
   ├── appliers/config_applier.py           (SELF_CONFIG; staged, never in-session-effective)
   ├── appliers/information_applier.py      (INFORMATION; memory/knowledge/world-model via interfaces)
   ├── appliers/capability_applier.py       (CAPABILITY; upgrade registry + ComponentRegistry metadata)
   ├── appliers/rollback.py — rollback_manager.py ──► autonomy_storage
   └── verification_service.py ──► version_manager.py ──► autonomy_storage ──► EvolutionRecord audit
                                        │
                                        ▼
        autonomy/dispatcher.py (SOLE caller of gateway.execute_request(); atomic CAS claim)
                                        │
                              EvolutionKnowledgePipeline (Phase 13.6) ◄── structured EvolutionOutcomeRecord
```

**Acyclic guarantee:** models ← validators ← assessors ← authorizers ← scheduler/store ← gateway ← application engine ← appliers ← verifiers/versioning/audit. Every cross-module edge is constructor-injected. `autonomy/**` imports `models.py` downward only; no autonomy module imports the gateway; the gateway never imports autonomy internals beyond the injected `application_engine` protocol.

---

## 3. Component Diagram

New package `atlas/evolution/autonomy/`:

```
autonomy/
├── models.py                    # EvolutionRequest, status, risk, auth, schedule, version,
│                                #   rollback, receipt, verification, outcome, policy, staged-config, status-report
├── request_factory.py           # proposal / goal (transcribed) / scheduler / CLI sources → EvolutionRequest
├── validator.py                 # per-scope payload schema + preconditions (pure)
├── scope_classifier.py          # closed scope→component map + classification (pure)
├── risk_assessor.py             # deterministic risk score; consumes PlanningContext + goal-layer signals
├── autonomy_policy.py           # config mirror + envelope checks + quota accounting (pure)
├── authorization_manager.py     # user:cli / user:policy / system:autonomy + TTL + in-flight exclusion
├── schedule_store.py            # persistent request store + window/throttle + atomic CAS claim
├── autonomy_request_adapter.py  # SOLE translator EvolutionRequest → scope-pinned EvolutionProposal
├── application_engine.py        # orchestrates appliers behind the gateway (snapshot→apply→verify→version)
├── dispatcher.py                # tick-driven; ONE claim+execute per tick; SOLE execute_request() caller
├── audit_query.py               # read-only "phase16.*" audit surface
└── appliers/
    ├── base.py                  # Applier protocol (validate/apply/revert/verify/capture_snapshot) + ApplierRegistry
    ├── config_applier.py        # SELF_CONFIG: writes StagedConfigEntry (never live config)
    ├── information_applier.py   # INFORMATION: repository interfaces (memory/knowledge/world-model)
    ├── capability_applier.py    # CAPABILITY: register/enhance/deprecate via upgrade registry
    └── rollback.py              # snapshot restore + inverse ops
```

New storage adapter `atlas/storage/autonomy_storage.py` — `AutonomySQLiteStorage`, additive tables: `evolution_requests`, `evolution_versions`, `evolution_receipts`, `evolution_snapshots`, `evolution_outcomes`, `staged_config`.

**Existing files modified (additive only):**

| File | Change |
|---|---|
| `atlas/kernel/atlas.py` | Construct autonomy stack when policy enabled; inject `application_engine` + `autonomy_request_adapter` into gateway; call `dispatcher.settle()` in `tick()`; register container keys; shutdown durability flush |
| `atlas/evolution/execution_gateway.py` | Optional `application_engine` + `request_adapter` kwargs; new `execute_request()` method (same governance, UNKNOWN-close); `execute()` untouched |
| `atlas/evolution/governance/models.py` | + `ScopeType.CAPABILITY` (additive enum member) |
| `atlas/evolution/governance/rule_engine.py` | + additive keyword mappings `"capability"` → CAPABILITY, `"skills"` → SKILLS |
| `atlas/evolution/governance/constraint_registry.py` | + GOV-005, GOV-006 (GOV-007 intentionally absent) |
| `atlas/goals/models.py` | + `GoalStatus.TRANSCRIBED` (additive enum member) |

**No Phase 15 file redesigned, no `atlas/evolution/evolution_storage.py` modification, no `atlas/goals/execution_request_adapter.py` modification.**

---

## 4. Data Models (pure dataclasses)

**`AutonomyPolicy`** — `enabled: bool (default False)`, `effective_execution_level: ExecutionLevel (default ADMINISTRATIVE)`, `allowed_scopes: list[ScopeType]`, `max_risk_level: RiskLevel`, `max_requests_per_window: int`, `authorization_ttl_minutes: int`, `requires_user_approval_scopes: list[ScopeType]`, `hot_reload_allowlist: list[str]` (config keys eligible for in-session completion), `window (window_start, window_end)`, `version: str` (policy manifest version; immutable once loaded).

**`EvolutionRequest`** — `request_id`, `source (proposal_id | goal_id | scheduler | cli)`, `target_scope: ScopeType`, `change_payload: dict` (schema-validated per scope), `intended_level: ExecutionLevel`, `status: EvolutionRequestStatus`, `validation: ValidationReport|None`, `risk: RiskAssessment|None`, `authorization: EvolutionAuthorization|None`, `schedule` (embedded: `scheduled_at, window_start, window_end, max_attempts=1 (application), cooldown_until`), `version_target: VersionTarget|None`, `rollback: RollbackPlan|None`, `receipt: ChangeReceipt|None`, `verification: VerificationResult|None`, `outcome: EvolutionOutcomeRecord|None`, `parent_request_ids: list[str]` (rollback-cascade edges), `created_at, updated_at, metadata`.

**`EvolutionRequestStatus`** (16 states) — `DRAFTED, VALIDATED, RISK_ASSESSED, PENDING_AUTHORIZATION, AUTHORIZED, SCHEDULED, APPLIED, PENDING_EFFECTIVE, COMPLETED, FAILED, ROLLED_BACK, SUPERSEDED, CANCELLED, EXPIRED, REJECTED, EVOLUTION_HOLD`. (`VERIFIED` collapsed into `VerificationResult`; `DETECTED` removed — provenance lives in `source`.)

**`ValidationReport`** — `valid, violations, warnings, schema_version, validator_version`.

**`RiskAssessment`** — `risk_level ∈ {LOW, MEDIUM, HIGH, CRITICAL}`, `score ∈ [0,1]`, `factors: dict`, `requires_user_approval`, `requires_rollback`, `summary`. (Risk-domain semantics; explicitly documented as independent of `ImprovementPriority`.)

**`EvolutionAuthorization`** — `request_id, authorized_by ∈ {"user:cli","user:policy","system:autonomy"}, mode ∈ {EXPLICIT, POLICY, AUTONOMY}, granted_at, expires_at (policy TTL), policy_ref, comment`.

**`VersionTarget`** — `target_kind (CONFIG|MEMORY|KNOWLEDGE|CAPABILITY)`, `current_version`, `target_version`, `state_version_at_creation: str` (optimistic-concurrency anchor).

**`RollbackPlan`** — `strategy ∈ {SNAPSHOT, INVERSE_OP}`, `snapshot_ref`, `inverse_description`, `steps: list[str]`, `cascade_targets: list[request_id]`, `requires_user_approval (default False)`.

**`ChangeReceipt`** — `request_id, changed_keys, before_refs, after_refs: dict, version_delta, target_tags: list[str], applied_at`.

**`VerificationResult`** — `passed, checks: list[dict], details, verified_at, scope` (one per probe).

**`AtlasStateVersion`** — `major, minor, patch`, `manifest_id`, `applied_request_ids, parent_version, scope_versions (config/memory/knowledge/per-capability), tags, created_at`.

**`EvolutionOutcomeRecord`** — the **Phase 17 evidence contract** (mirrors Phase 15 `GoalExecutionRecord` role): `request_id, scope, area, risk_level, intended_level, authorization_mode, outcome (COMPLETED|ROLLED_BACK|FAILED), verification_passed, rollback_occurred, effectiveness_proxy, timestamps, related_ids (proposal_id, goal_id, tracked_goal_id, evolution_record_id), strategy_key, planning_context_version, metadata`. Phase 16 persists these records only; the Phase 13.6 pipeline consolidates them into patterns/strategies/capability trajectories; Phase 16 never aggregates.

**`StagedConfigEntry`** — `entry_id, request_id, key, value, schema_status, activated_at|None, applied_at`.

**`EvolutionStatusReport`** — typed bound query for `atlas evolution status`: `state_version, hold: bool, pending_authorizations: int, scheduled: list, in_flight (APPLIED|PENDING_EFFECTIVE): list, window_quota_used: int, envelope: summary dict, policy_version`.

---

## 5. Runtime Flow

```
S O U R C E S
  Authorized Goal (execution_mode="state_evolution") ─┐
  Approved Proposal targeting state scope             ─┼─► request_factory │ (D12 transcription when applicable)
  Scheduler opportunity / CLI create                  ─┘
        │
        ▼
  EvolutionRequest (DRAFTED)
        │
        ▼  Validator (gate 2: per-scope schema + preconditions)         ─► VALIDATED
        ▼  RiskAssessor (gate 3: PlanningContext + goal signals)        ─► RISK_ASSESSED
        ▼  AuthorizationManager (gate 4):
              envelope member → system:autonomy (audited)  ─► AUTHORIZED
              out-of-envelope / HIGH+ / listed scope → PENDING_AUTHORIZATION
                    → user:cli / user:policy decision      ─► AUTHORIZED
        ▼  ScheduleStore (window open + quota)                          ─► SCHEDULED
        ▼
  ══════════════ SOLE APPLICATION OWNER: dispatcher.settle() ══════════
        │  1. Atomic claim: CAS status SCHEDULED→APPLIED in storage
        │     (claim also verifies current state_version == version_target anchor; else SUPERSEDED)
        │  2. Gate 5: intended_level ≤ policy.effective_execution_level (else REJECTED, audited)
        ▼
  AutonomyRequestAdapter (D2 closed map → scope-pinned EvolutionProposal, status APPROVED)
        ▼
  gateway.execute_request(request)
        │  Gate 1: RuleEngine (scope + level @ current_execution_level)
        │  Invariant: scope == UNKNOWN ⇒ REFUSED (audited; request → REJECTED)
        ▼  Gate 6 passed
  application_engine.apply(request)
        │  capture_snapshot → RollbackPlan stored (before ANY mutation)
        │  applier.apply()
        │    CONFIG      → staged, NEVER live        → APPLIED → PENDING_EFFECTIVE (boot-activation)
        │    INFORMATION → repository write          → APPLIED
        │    CAPABILITY  → registry change           → APPLIED
        │  change_receipt recorded + version bump
        ▼
  verification_service (per-scope probes; boot probes for staged config)
        │  PASS → COMPLETED (effective+verified)          [INFORMATION/CAPABILITY: in-session]
        │  PASS → PENDING_EFFECTIVE → (next boot) → boot activation + boot verification
        │                                                → COMPLETED | SAFE_MODE → rollback
        │  FAIL → rollback_manager cascade → ROLLED_BACK | EVOLUTION_HOLD
        ▼
  EvolutionOutcomeRecord persisted → EvolutionKnowledgePipeline (13.6) consolidates
```

---

## 6. Lifecycle

```
 DRAFTED ─► VALIDATED ─► RISK_ASSESSED ─► PENDING_AUTHORIZATION ─► AUTHORIZED ─► SCHEDULED
    │            │              │                │                     │              │
    │            └──────────────┴────────────────┴──(user withdraw)──► CANCELLED     │
    │                                                              (window passes)  ► EXPIRED
    ▼                                                                                 │
 REJECTED ◄── (gate 1/2/3/5 failure or auth expiry or version mismatch ⇒ SUPERSEDED) ◄┘
                                                                                      │
                                                              ┌───────────────────────┘
                                                              ▼
                                                          APPLIED (atomic claim)
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                  INFORMATION / CAPABILITY:            CONFIG:
                                  verification                         staged → PENDING_EFFECTIVE
                                              │                                   │ (next boot)
                                              ▼                                   ▼
                                          COMPLETED (effective)          boot activation + boot verification
                                              │                                   │
                                              │                    ┌──────────────┴─────────────┐
                                              │                    ▼                            ▼
                                              │            COMPLETED (effective)         SAFE_MODE ─► rollback ─► ROLLED_BACK
                                              │                                                          │ rollback fails
                                              ▼                                                          ▼
                    FAILED (apply error) ──► (partial mutation? immediate rollback)                 EVOLUTION_HOLD
                    (no automatic retry)                                                           (user must clear;
                                                                                                    all application blocked)
```

**Transition rules:** every transition is recorded as an `EvolutionRecord` (`event_type="phase16.*"`) and (for terminal states) an `EvolutionOutcomeRecord`. `CANCELLED`/`EXPIRED`/`REJECTED`/`SUPERSEDED`/`FAILED`/`ROLLED_BACK` are terminal; revival requires a fresh draft (`request_id`). Authorization TTL expiry while `PENDING_AUTHORIZATION`/`SCHEDULED` ⇒ `EXPIRED`. `EVOLUTION_HOLD` clears only via explicit user CLI action, which itself bumps the patch version and is audited.

---

## 7. Governance

Six ordered deterministic gates; missing dependency at any gate = fail-closed refusal, audited.

| Gate | Component | Fails closed when |
|---|---|---|
| 1 | `RuleEngine` (scope + `min_execution_level`) @ gateway current level | Scope/level violation (e.g. IDENTITY, CODE, or CAPABILITY at ADMINISTRATIVE) |
| 2 | `Validator` | Payload fails per-scope schema or violates preconditions |
| 3 | `RiskAssessor` | `risk_level > policy.max_risk_level` |
| 4 | `AuthorizationManager` | No valid, unexpired authorization for scope/risk; or `system:autonomy` outside envelope |
| 5 | Dispatcher level pre-check | `intended_level > policy.effective_execution_level` |
| 6 | Gateway translation + UNKNOWN-close | Translated proposal classifies `UNKNOWN` (refused unconditionally); adapter or application engine missing |

**Registry rules (RuleEngine-enforceable only):** GOV-001 IDENTITY→level 5 (unreachable), GOV-002 CODE→level 3 (unreachable), GOV-003 CONFIG→level 1, GOV-004 MEMORY/KNOWLEDGE→level 2, GOV-005 CAPABILITY→level 1, GOV-006 SKILLS→level 1. **GOV-007 (autonomy envelope) is policy, not registry** — enforced solely by `AuthorizationManager`; documented in the constitution section, absent from `ConstraintRegistry`.

**Constitutional invariants:** identity and code remain untouchable; a request can never alter `AutonomyPolicy`, `ConstraintRegistry`, or gateway level; UNKNOWN scope can never execute at any level.

---

## 8. Authorization

- **`user:cli`** — explicit per-request approval; required for out-of-envelope, HIGH/CRITICAL, or `requires_user_approval_scopes`.
- **`user:policy`** — declarative pre-authorization, must enumerate exact scope+risk+quota combinations; never blanket.
- **`system:autonomy`** — granted only when ALL hold: scope ∈ `allowed_scopes`; risk ≤ `max_risk_level`; `requires_user_approval == False`; documentable rollback plan present; window active; quota available; request unexpired. Every grant emits an audit record + increments a user-visible counter.
- **TTL:** every authorization carries `expires_at` from `authorization_ttl_minutes`; expired authorizations cannot authorize application.
- **In-flight exclusion:** policy reload (user-only) is rejected while any request is `APPLIED` or `PENDING_EFFECTIVE`.
- **No self-escalation:** no request, applier, or engine may modify the policy, the registry, or the gateway level. These surfaces are user-only.

---

## 9. Rollback

- **Precondition:** snapshot captured and `RollbackPlan` stored *before* any mutation; `ChangeReceipt` records the exact keys/version delta.
- **Triggers:** verification failure; boot `SAFE_MODE`; health-probe invariant violation; explicit user rollback command `atlas evolution request rollback <id>` (routed via dispatcher queue, never direct).
- **Snapshot:** `AutonomySQLiteStorage` persists a **store-level artifact** (deterministic export of the affected store, checksummed, FK-safe) per `evolution_snapshots` row, linked to request + version. No row-level partial snapshots. Retention: indefinite (audit requirement); pruning is user-initiated and itself audited.
- **Cascade:** rollback of request R follows declared `parent_request_ids` plus manifest-derived application order: every *later* request whose receipt tags the same target is rolled back first (LIFO), each with its own audit + outcome record. Any cascade step failing ⇒ `EVOLUTION_HOLD`.
- **Hold:** `EVOLUTION_HOLD` blocks all application until user clears; state remains consistent because rollback is applied within the same synchronous dispatcher cycle.
- **Versioning:** rollback bumps patch version under manifest tag `"rollback"`; history remains reconstructable.

---

## 10. Versioning

- `AtlasStateVersion major.minor.patch`: major — execution-level advance or user-issued `atlas evolution version bump-major`; minor — capability register/enhance or new scope activation; patch — applied state change or rollback.
- **Genesis:** baseline `1.0.0` written at first autonomy-enabled start; policy version tracked independently and never mutated at runtime.
- **Manifest:** append-only `evolution_versions` — version, parent_version, applied_request_ids, scope_versions, receipt refs, snapshot refs, tags, timestamp. No destructive overwrite.
- **Optimistic concurrency:** every request anchors `state_version_at_creation`; claim-time comparison detects drift ⇒ `SUPERSEDED`. This + atomic CAS is the double-application defense.
- **Per-scope versions** (`config_version`, `memory_version`, `knowledge_version`, per-capability) expose blast radius; readers surface them via `EvolutionStatusReport`.

---

## 11. Runtime Integration

- **`Atlas.start()`:** load `[evolution.autonomy]` (default disabled). If disabled: construct nothing beyond a policy mirror; gateway is constructed exactly as Phase 15 (no `application_engine`); `set_execution_level` not called; dispatcher not registered; Phase 15 behavior byte-for-byte identical. If enabled: build policy → registry → factory → validator → risk assessor → authorizer → schedule store (backed by `AutonomySQLiteStorage`, tables initialized) → appliers + `ApplierRegistry` → `ApplicationEngine` → `VerificationService` → `RollbackManager` → `VersionManager` → `AutonomyRequestAdapter` → pass `application_engine` + adapter into gateway → `gateway.set_execution_level(policy.effective_execution_level)` → construct `EvolutionAutonomyDispatcher` → staged-config boot activation + boot verification + `SAFE_MODE` handling run *after* storage init, before services start.
- **`Atlas.tick()`:** `task_manager.tick()` → `evolution_scheduler.tick()` → `goal_executor.settle()` → `if dispatcher: dispatcher.settle()` (one claim+execute per tick; non-blocking).
- **Shutdown/durability rule:** synchronous apply within a tick means no mid-apply shutdown; staged entries and request status must be durably committed in the same storage transaction before `PENDING_EFFECTIVE`/`COMPLETED` is recorded. `shutdown()` flushes the manifest and closes `AutonomySQLiteStorage`.
- **Container keys:** `evolution_autonomy`, `evolution_requests` (store/factory surface), `evolution_application`, `evolution_rollback`, `evolution_versioning`, `capability_upgrades`, `evolution_dispatcher`.
- **CLI (presentation-only):** `atlas evolution request list|show|create|authorize|schedule|schedule-now|cancel`, `atlas evolution request rollback <id>`, `atlas evolution audit`, `atlas evolution policy show|reload`, `atlas evolution version bump-major`, `atlas evolution status`. CLI never calls `execute_request()` or applies anything directly; `schedule-now` enqueues.
- **Events:** `evolution.policy.changed`, `evolution.request.created/authorized/scheduled/applied/pending_effective/completed/failed/rolled_back/rejected/cancelled/expired/superseded`, `evolution.hold.entered`, `evolution.hold.cleared`.

---

## 12. Extension Points

1. **New scopes/appliers** — `Applier` protocol (`validate/apply/revert/verify/capture_snapshot`) + `ApplierRegistry`; future `TASK`, `AGENT`, `SKILL` scopes are additive.
2. **New risk factors** — `RiskFactorProvider` protocol (deterministic, ordered).
3. **New validation rules** — pluggable `ValidatorRule` per scope/schema.
4. **New authorization sources** — additional policy formats resolved by `AuthorizationManager`.
5. **New rollback strategies** — beyond `SNAPSHOT`/`INVERSE_OP` (future `DELTA` replay).
6. **Capability upgrade kinds** — `CapabilityUpgradeApplier` dispatches by `upgrade_kind`; new kinds additive.
7. **Transcription policy types** — future `execution_mode` values can be policy-enrolled rather than per-goal (D12 stays deterministic via a closed enum).
8. **Audit sinks & version consumers** — subscribe to `phase16.*` events; `VersionManager` read surface for identity/self-model context (Phase 9.0).

---

## 13. Implementation Roadmap

| Sub-phase | Content | Exit criteria |
|---|---|---|
| 16.1 | `models.py`, `request_factory.py`, `scope_classifier.py`, `autonomy_request_adapter.py` | Factory + adapter produce scope-pinned requests from all four sources; UNKNOWN-close proven by test |
| 16.2 | `validator.py`, `risk_assessor.py` | Per-scope schema gate + deterministic scoring; weights constant-reviewed |
| 16.3 | `autonomy_policy.py`, `authorization_manager.py` + config section | Envelope/TTL/quota logic; no self-escalation proven; GOV-007 absence verified |
| 16.4 | `AutonomySQLiteStorage` (6 tables), `schedule_store.py` | Atomic CAS claim proof test; optimistic-concurrency drift → SUPERSEDED |
| 16.5 | `ApplierRegistry`, `config_applier.py`, `information_applier.py`, `capability_applier.py`, `application_engine.py` | Apply produces `ChangeReceipt`; snapshot captured pre-mutation; CAPABILITY merged-request path tested |
| 16.6 | `verification_service.py`, `rollback_manager.py`, `version_manager.py` | Probe suite; cascade rollback incl. failure injection; `EVOLUTION_HOLD` path; manifest chain |
| 16.7 | Staged config + boot activation + `SAFE_MODE` + `PENDING_EFFECTIVE` | `COMPLETED` only when effective+verified; SAFE_MODE boots on base config; disabled-policy boot path identical to Phase 15 |
| 16.8 | Gateway `execute_request()`, dispatcher, CLI, kernel wiring, events | Dispatcher sole caller proven (call-site check); CLI presentation-only; container keys registered |
| 16.9 | Full suite, state-machine conformance test, `ATLAS_STATE.md` + ADR, commit + tag `phase-16-complete` | 1585+ tests green, zero regressions, architecture verified |

---

## 14. Binding Constraints

1. Gateway remains the only execution entry point; `execute_request()` is the only applied-evolution path.
2. No mutation without all six gates; UNKNOWN scope never executes.
3. `system:autonomy` only inside the configured envelope; envelope, registry, and level are user-only mutable.
4. `EvolutionAutonomyDispatcher` is the sole application owner; CLI and factory never apply directly.
5. One request per tick, single-threaded, non-blocking; applies are short, deterministic store mutations.
6. Every applied request has a pre-mutation snapshot and a rollback plan; rollback and versioning are mandatory.
7. `COMPLETED` means effective and verified — never "written but inert"; config changes are staged by default.
8. ToolEngine never applies state mutations; appliers do.
9. Goal transcription is opt-in and single-owner (`GoalStatus.TRANSCRIBED`); double execution structurally impossible.
10. No code, identity, or policy changes in Phase 16; `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` locked.
11. Missing dependencies fail closed; every transition audited (`phase16.*`).
12. Default `enabled=false` ⇒ Phase 15 unchanged; all modifications additive.

---

## 15. Review Checklist

- [ ] Gateway both entry points verified as sole choke point (dependency inspection tool).
- [ ] UNKNOWN-scope refusal proven with translated-proposal test fixture.
- [ ] Atomic CAS + optimistic-concurrency double-application test.
- [ ] Sole-caller discipline: `execute_request()` referenced only from `dispatcher.settle()` (call-site scan).
- [ ] `COMPLETED`-only-when-effective conformance test (staged config + boot activation + SAFE_MODE).
- [ ] Goal transcription exclusion proven: no goal executes twice across both paths.
- [ ] No circular imports (`autonomy/**` never imports gateway/kernel/services/ai; architecture checker).
- [ ] Pure-logic isolation per ATLAS_CORE §10; prohibited-import list enforced.
- [ ] Rollback cascade + `EVOLUTION_HOLD` under injected failure.
- [ ] Audit record per lifecycle transition; `EvolutionOutcomeRecord` persisted and pipeline-consolidated.
- [ ] Additive storage: 6 new tables, existing tables unmodified; migration backward-compatible.
- [ ] Full `pytest` green (1585+); `atlas evolution status` sane; default-policy parity test vs Phase 15.

---

## 16. Ready-for-Implementation Criteria

1. This v2.0 accepted as the official Phase 16 spec.
2. Phase 15 suite (1585) green on `phase-15-complete`; baseline hash recorded.
3. `[evolution.autonomy]` config contract finalized (fields, defaults, `hot_reload_allowlist`, TTL, quota).
4. Storage schema addendum (6 tables, CAS statement semantics) approved.
5. Sub-phase order (16.1→16.9) accepted; tests-first; each sub-phase exits green.
6. Implementation brief restates the four non-negotiables: no AI-authored payloads; no code/identity/policy mutation; default policy disabled; single application owner.

---

## 17. Summary of Changes from v1 → v2.0

| Review item | Resolution |
|---|---|
| C1 Gateway contract mismatch / UNKNOWN-scope bypass | D2 + D3: closed scope map in `AutonomyRequestAdapter`; typed `execute_request()` with unconditional UNKNOWN-close; scope derived, never influenced by payload |
| C2 Double application / CLI bypass | D10: single dispatcher owner; CLI `apply` removed (→ `schedule-now`); atomic CAS claim + optimistic version check |
| C3 APPLIED vs EFFECTIVE config | D11: staged config, `PENDING_EFFECTIVE`, boot activation + boot verification, `SAFE_MODE`; `COMPLETED` only when effective+verified |
| C4 `CapabilityUpgradeRequest` artifact | Removed; capability changes are `EvolutionRequest` with `target_scope=CAPABILITY` + `upgrade_kind` payload |
| C5 Goal double execution | D12: explicit opt-in transcription (`execution_mode="state_evolution"`), `GoalStatus.TRANSCRIBED`, settle() exclusion, evidence linkage preserved |
| M1 Cancellation/expiry/auth-TTL lifecycle | Added `CANCELLED`, `EXPIRED`, authorization `expires_at`; consistent `REJECTED` terminology |
| M2 Rollback cascade | `parent_request_ids` + manifest application-order; LIFO cascade with per-step audit; cascade failure ⇒ `EVOLUTION_HOLD` |
| M3 Snapshot storage/granularity | Store-level checksummed artifacts in `evolution_snapshots`; FK-safe; retention/audit policy defined |
| M4 Verification probes | Concrete per-scope probes + boot probes; weak-probe risk flagged for test-first hardening |
| M5 Dispatcher ownership vs scheduler | Standalone `EvolutionAutonomyDispatcher`; observes nothing, generates nothing; Phase 13.3 untouched |
| M6 DI contracts / prohibited imports | D15 table: appliers over injected interfaces; `autonomy/**` banned imports enumerated; new storage adapter |
| M7 Structured knowledge evidence | `EvolutionOutcomeRecord` as the Phase 17 evidence contract; persisted + consumed by Phase 13.6 pipeline; no aggregation in Phase 16 |
| M8 GOV-007 placement | Removed from registry; enforced in `AuthorizationManager` as policy, not rule |

Minor items: `VERIFIED` state removed (→ `VerificationResult`) · `DETECTED` removed (→ `source` provenance) · risk levels documented as risk-domain, independent of `ImprovementPriority` · version genesis + `version bump-major` command · external side-effect boundary documented · `EvolutionStatusReport` typed · RiskAssessor consumes goal-layer signals.

---

## Self-Evaluation — Remaining Weaknesses (honest)

1. **Restart-spanning lifecycle is operationally novel.** `PENDING_EFFECTIVE` + `SAFE_MODE` extend the boot path. Correctness now depends on boot-verification probe quality; weak probes weaken `COMPLETED` semantics. Mitigation: probes are the first artifact tested in 16.6/16.7; SAFE_MODE is inactive unless a staged overlay exists.
2. **Sole-caller discipline is convention, not language-enforced.** `execute_request()` is private-to-dispatcher by review-check, not by mechanism. Accepted risk, enforced by the call-site scan in the checklist.
3. **Single-process assumption.** The atomic claim is SQLite-local; multi-process Atlas and cross-process coordination are explicitly out of scope and would need a distributed claim primitive (`CAS on advisory lock`) — deferred.
4. **In-session completion for INFORMATION/CAPABILITY is only as safe as the per-scope probes.** A read-back probe on a repository interface validates write visibility, not semantic correctness. Semantic verification at boot (`SAFE_MODE`-style) for these scopes is a Phase 17 candidate; documented as a limitation now.
5. **Long-applier stalls the tick loop.** Bounded by design (deterministic, short store mutations) and checked in review; a watchdog is a future addition if applier kinds grow.
6. **Concurrent user actions** (e.g., `authorize` while dispatcher claims) are safe via CAS on the request row; policy reload is excluded during non-terminal requests. Residual risk is limited to UX-level races (double-authorized display), not state corruption.
7. **Transcription density is intentionally low.** Opt-in `execution_mode` per goal keeps default behavior identical but limits autonomous goal→evolution flow until policy-enrolled transcription types arrive (documented extension point).
8. **State count (16) is large.** Each state must be conformance-tested; the matrix in §6 and the 16.9 state-machine test make this tractable but it is the highest-cost surface area of the phase.

**Verdict:** All five critical issues and the requested medium issues are resolved in this revision. The remaining weaknesses are accepted, bounded, and explicitly documented rather than unresolved defects.

**Phase 16 Architecture Approved (v2.0)** — ready for implementation under the readiness criteria in §16.
