# Command 3C — Evidence-Driven Coding Capability Gap Assessment

Status: **PASS — GAP IDENTIFIED**. One defect caused by Command 3B was found and
resolved (test-only); a single evidence-backed next capability is selected below.

## 1. Method

Real-world probes were driven through the NORMAL Atlas entry point
(`Atlas.development_authoring_request` → governed cycle → OWNER approval →
governed execution → bounded verification) with the REAL local model
(`qwen2.5-coder:7b`). Failure paths were reproduced with the loop's own verifier
(controlled env, 30 s bound) and the E2 applier directly. No architecture was
expanded; no full suite was run.

## 2. Real-world probe results

| Probe | Purpose | Authoring | Execution | Verification | Observed failure |
|---|---|---|---|---|---|
| A | straightforward generation (repeatability) | ok (`specialist-proposal`) | SUCCESS (1 iter) | **verified** | none (PASS) |
| B | existing-code modification | ok | ITERATIONS_EXHAUSTED (3) | unverified | model broke `select_relevant_tests`; 3 tests failed |
| B2 | deliberate failure + repair (model-assisted ON) | ok | ITERATIONS_EXHAUSTED (3) | unverified | repair returned the **identical** workload each retry |
| C | multi-file reasoning | ok | ITERATIONS_EXHAUSTED (3) | unverified | E2 apply read-back rejected content (CRLF); multi-file intent collapsed to one target |
| D | deliberate failure | ok | (applied cleanly) | failed | verification target unsuitable (resolved by the fix below) |

Probe A was re-run after the fix in §3 and now passes end to end.

### Probe B — exact cause (reproduced)

The model's full-file rewrite of `atlas/evolution/development_test_selection.py`
made `select_relevant_tests` return an EMPTY tuple where derived candidates
should be returned. The selected verification target
(`tests/test_authoring_contract_test_projection.py`) failed with:

```
AssertionError: assert () == ('tests/test_...tion.py', ...)   (3 failed, 33 passed)
```

Atlas **detected and correctly classified** this (`verification`, confidence
`known`). It then retried the SAME broken change three times and stopped at
`ITERATIONS_EXHAUSTED`. No corrective change was ever authored.

### Probe B2 — repair is wired but ineffective (decisive)

With `[development].model_assisted_authoring = true`,
`RepairChangeSupplier` (`repair_enabled=true`) was invoked for all three
iterations and returned a **byte-identical** workload every time:

```
history_len=0 -> sha 327aaec82ed4   (the failing change)
history_len=1 -> sha 327aaec82ed4   (unchanged)
history_len=2 -> sha 327aaec82ed4   (unchanged)
```

The corrective authoring produced nothing usable, so the supplier fell back to
the baseline workload. `DevelopmentRecovery` also returned
`strategy=no_recovery` (the diagnostics set `recoverable=None`), so the
REVISE_AND_RETRY branch is effectively unreachable. The newly ACTIVE
`code.generate` specialist is **not** used by the repair path at all.

### Probe C — E2 apply read-back is not newline-stable

A valid single-file change was rejected at apply time. Reproduced directly:

```
apply_success=true  verify_passed=false
path=atlas/intelligence/cognitive_service.py
requested_len=847 read_len=847 match=false
requested_crlf=3  read_crlf=0
```

`CodeApplier.verify` compares `reader.read(path) == change.content`, but the
sandbox reader/writer use `Path.read_text`/`write_text` with default newline
translation, so CRLF in the model output is not preserved on read-back → the
change is rolled back (`E2 verification failed; sandbox restored`).

## 3. Defect caused by Command 3B — found and resolved

The Command 3B test `tests/test_specialist_governed_acceptance.py` statically
imports `atlas.specialist_transport` (and the kernel). The repository map derives
its test→module graph from static `import` statements, so that test became the
**first** import-derived verification target for `atlas/specialist_transport.py`
changes. In the sandbox it cannot run (it reads `config.toml`, which the
verification closure does not carry) → a correct change was reported as a
verification failure.

**Resolution (test-only):** the test now imports every `atlas` module LAZILY via
`importlib` inside helpers, so it is not a static dependent of any `atlas` module
and is never selected as a bounded verification target. Verified: the plan's
verification set for `atlas/specialist_transport.py` is now exactly
`[tests/test_specialist_transport.py]`, and Probe A passes (SUCCESS / verified /
repository unchanged); the test itself still passes (3 passed).

## 4. Failure → repair assessment (section 5 questions)

1. Failed verification reaches classification? **Yes** (`DevelopmentDiagnostic`).
2. Structurally represented? **Yes** (failure class + confidence + evidence on the outcome/history).
3. Relevant changed target identified? **Partially** — `changed_files` travel on the outcome, but no repair authors against them.
4. Authoring vs test/environment distinguished? **Yes** (implementation/verification/environment classes).
5. Existing repair seam? **Yes** — `RepairChangeSupplier` wired as the loop's change supplier (opt-in).
6. Specialist invoked for repair? **No** — repair uses the separate `ModelAssistedChangeSupplier`/`AIService` seam, which yields nothing.
7. Repaired proposal re-enters the governed path? N/A — repair is an in-sandbox retry, not a new proposal.
8. Same approval/governance boundary? **Yes** — retries stay inside the single approved, bounded sandbox run; promotion remains separate.
9. Repeated repair bounded? **Yes** (iteration budget 3).
10. Enough infrastructure for a very small additive change? **Yes** — the seam and bounds exist; only the corrective author is missing.

## 5. Multi-file assessment

- The localizer/plan represent a SINGLE target. A request naming two modules
  ("update both A and B") localized to one (`atlas.intelligence.cognitive_service`)
  and the plan carried only that module's verification.
- The one-file specialist contract is an intentional bounded safety restriction,
  **not** a proven defect: Atlas can already govern multiple changes
  (`max_code_changes=5`; `StructuralChangeSupplier.MAX_FILES=4`).
- Demonstrated limitation: the model returned only ONE file for a two-file
  request → an incomplete change, silently. **Not selected** (expanding scope is
  architectural and unproven as the binding constraint).

## 6. Repository-understanding / modification / operational assessments

- **Understanding** (localization, context, symbols, dependencies): no probe
  failure — every request localized to the correct module. **VALIDATED**.
- **Modification mechanism**: full-file regeneration is fragile (Probe B broke
  surrounding behaviour) and the applier is not newline-stable (Probe C). No
  evidence for tree-sitter/ast-grep/LibCST/Morph/Aider — recorded as **future
  candidates only**.
- **Operational** (Task Ledger, worktrees, leases, rollback, parallel): no probe
  required durable state, ownership or parallelism. **NOT YET JUSTIFIED**.

## 7. Ranked capability gaps

| Rank | Gap | Evidence | User impact | Workaround | Smallest justified solution | Confidence |
|---|---|---|---|---|---|---|
| 1 | **Failure → repair ineffective** | Probe B/B2: 3 retries, identical workload; recovery `no_recovery` | a broken change can never be corrected; run exhausts | none | author the corrective change through the ACTIVE `code.generate` seam in `RepairChangeSupplier` | High |
| 2 | E2 apply read-back not newline-stable | Probe C: `requested_crlf=3`, `match=false` | valid changes silently rejected | none (model-dependent) | byte-stable text I/O in the sandbox read/write (or compare normalized) | High |
| 3 | Verification-target suitability | Probe B (27 s target vs 30 s bound); pre-fix Probe A/D | heavy/unrelated first test can falsely fail a correct change | keep a focused name-matching test | prefer the change-corresponding test in `_plan_verify_target` | Medium |
| 4 | Multi-file intent not represented | Probe C | incomplete changes accepted silently | split requests manually | (architectural — defer) | Medium |
| 5 | Misleading failure message | "pytest failed to start" for ordinary test failures | poor diagnosability | none | surface the real pytest reason | Medium |
| 6 | Repair recovery decision unreachable | `recoverable=None` ⇒ always `no_recovery` | inconsistent with the loop's retry | none | derive `recoverable` from the diagnostic | Medium |

## 8. NEXT IMPLEMENTATION TARGET

**Bounded failure → repair via the ACTIVE specialist `code.generate` seam.**

- **Capability definition:** after a bounded sandbox verification failure, Atlas
  authors ONE corrective change to the SAME authorized target through the
  EXISTING Atlas-owned specialist seam, and re-verifies it inside the same
  governed, bounded, sandbox-only run.
- **Observed failure / reproduction:** §2 Probe B/B2 (identical workload across
  all retries despite `repair_enabled=true`).
- **Why the current architecture is insufficient:** the corrective author is
  bound to the `ModelAssistedChangeSupplier`/`AIService` seam, which produces no
  usable output; the proven `code.generate` seam is not used, and the recovery
  decision never selects REVISE_AND_RETRY.
- **Smallest viable solution:** give `RepairChangeSupplier` an injectable
  corrective author (default = current behaviour) that reuses
  `SpecialistDevelopmentAuthor`/`SpecialistRegistry` bounded to the failing
  target; wire it in the kernel when `[specialists].enabled` and
  `[development].model_assisted_authoring` are both true.
- **Exact boundary to modify:** `atlas/evolution/development_repair.py`
  (`RepairChangeSupplier`); kernel `Atlas._development_repair_supplier`.
- **Governance implications:** none — opt-in, UNTRUSTED, bounded retries inside
  the single approved sandbox run; no new approval, no promotion, no egress.
- **Verification strategy:** focused tests for the corrective-author injection +
  a real probe where a broken change is repaired and re-verified.
- **Acceptance criteria:** a verification failure yields a DIFFERENT corrective
  workload, the run reaches `verified`, and promotion remains untouched.
- **External research needed:** no. **External model optional:** yes (deterministic-first preserved).
- **Must NOT change:** approval/authorization, promotion, the sandbox boundary,
  `CodeChangeSet` validation semantics, the one-file specialist contract, or any
  completed architecture.

Not implemented in 3C (recommend Command 3D) to keep this command an assessment
and to give the capability its own focused acceptance.

## 9. Tests/probes performed

- Real probes A, B, B2, C, D via the governed entry point (real local model).
- Verification reproductions: `pytest` under the loop's controlled env for the
  selected targets; direct E2 apply + read-back reproduction.
- `pytest tests/test_specialist_governed_acceptance.py -q` → **3 passed** (after hardening).

## 10. Repository state

- Start: `586724de8f5c45dcd5b6fde90557cb3bcecf8ea3` (`HEAD == origin/main`, clean).
- This commit: test-only hardening of `tests/test_specialist_governed_acceptance.py`
  (resolves the Command 3B defect) + this assessment document.
- `code.generate` remains ACTIVE within governed development (unchanged).
