# Command 5 — Development Capability Closure

Status: **COMMAND 5 COMPLETE — CURRENT DEVELOPMENT CAPABILITY CLOSED.**

This is a repository-wide closure pass over the governed development capability
(Commands 1–5). It fixes every *currently material* gap that is bounded and
safely resolvable now, and explicitly defers capabilities that require a future
architectural phase, new real-world evidence, or a stronger model.

---

## 1. Starting commit

- `f602faf7d9fffce0ab9ff6af9e70f03298dc9c7b` (`HEAD == origin/main`, clean).
- Command 3 COMPLETE (specialist + governed authoring + verification + repair),
  Command 4 COMPLETE (verification attribution).

## 2. Complete audit trail (traced)

Human request → language understanding → development intent → repository
understanding → target localization → bounded context → architecture context →
ChangePlan → verification expectations → **verification target** → authoring
(deterministic / supplied / structural / specialist) → governance → approval →
sandbox execution → verification → failure classification → **verification
attribution (baseline)** → repair decision → corrective authoring →
re-verification → promotion boundary. Also audited: conversation/development
continuity, follow-ups, ambiguity, references, repository-impact precedence,
provider-disabled behavior, retry limits, evidence/provenance, configuration,
sandbox behavior, newline handling, test selection, the one-file restriction and
the self-development loop.

## 3. Gap inventory (with evidence)

| # | Gap | Evidence | Tier |
|---|---|---|---|
| 1 | **Baseline probe asserted a TIMEOUT/ERROR as "already failing"** (`baseline_passed=False`) | Command 4 real probe showed a spurious `fail_to_fail` where the baseline merely timed out; the loop asserts a fact it does not have | **A** |
| 2 | **Verification target did not prefer the change-related focused test** | Repo-map audit: for `mock_provider`, `ai_router`, `specialist_change_supplier`, `cognitive_loop` the focused `test_<stem>.py` exists but is **not** selected (idx 7/3/1/1); the plan's bounded set (cap 3) dropped it entirely. First candidates were heavy kernel tests (unrunnable in the 30 s bound) and even non-test support modules | **B** |
| 3 | Multi-file authoring (one-file specialist contract) | No current evidence it blocks the governed development objective; Atlas already governs up to 5 changes | **C (future evidence candidate)** |
| 4 | Operational capability (durable task state, leases, worktrees, parallel, resumption) | No probe required it | **C (not yet justified)** |
| 5 | Sandbox verification bound (30 s) for slow tests | Real probe showed a borderline test can exceed it | **C (no evidence to change it; unknown path now conservative)** |
| 6 | Local 7B corrective-output quality | Real probes: the model's corrective content sometimes invalid/inadequate | **D (model-quality, not Atlas)** |
| 7 | Pre-existing `TestRealKernel` failures | Data-dependent real-kernel; reproduced at pristine baseline | **D (environmental, separately classified)** |
| 8 | One-file specialist contract | Intentional bounded safety restriction | **D (limitation by design)** |

## 4. Implemented fixes (all Tier A + justified Tier B)

### FIX 1 (Tier A) — baseline probe precision
`self_development_loop._run_iteration`: the pre-change baseline is now recorded
as `True` (the verifier passed), `False` **only for a genuine pre-change test
failure** (`outcome == "failed"`), and `None` (UNKNOWN) for timeout / error /
no-tests-collected. A timeout is never asserted as "it was already broken", so a
spurious `fail_to_fail` can no longer suppress a legitimate repair. Unknown stays
conservative.

### FIX 2 (Tier B) — verification-target suitability (root cause + local preference)
- **Root cause (planning):** `change_author_router.verification_expectations` now
  ORDERS the bounded verification set so the change-related focused test
  (`test_<stem>.py`, via the EXISTING `select_relevant_tests`) LEADS it — so a
  narrow, relevant test is not dropped by the downstream bound. No test is
  invented; only the order within the already-evidenced set changes.
- **Local preference (loop):** `self_development_loop._plan_verify_target` now
  prefers a related `test_<stem>.py` candidate before the plan's order (and thus
  before `_default_verify_target`), keeping the pytest invocation bounded.

Verified end to end: the plan for `atlas/ai/providers/mock_provider.py` now leads
with `tests/test_mock_provider.py` and the focused, light test is the verification
target.

## 5. Mechanisms / research used

The fixes reuse EXISTING Atlas-native mechanisms — `select_relevant_tests`
(change→test name convention), the bounded `VerificationExpectation`,
`verification_attribution` (Command 4) and the sandbox verifier. **No external
framework, dependency or research project was introduced**; the mechanisms were
already inside Atlas and only their ORDER/PRECISION changed.

## 6. Focused tests

- `tests/test_verification_attribution.py` — **23 passed** (new cases:
  verification-target selection preference/fallback/absence; baseline precision —
  a timed-out/errored baseline is `unknown`, a genuine baseline failure is
  `fail_to_fail`).

## 7. Coherent regression

Because the affected surface (development loop, verification selection, planning,
sandbox, governed path, specialist) is comprehensively covered by focused suites,
the following coherent checkpoint was run (a full-repository run was not practical
in the available budget given kernel-starting suites):

| Batch | Suites | Result |
|---|---|---|
| A — loop/verification/sandbox/repair | `test_evolution_self_development_loop`, `test_phase42/89/95/96/98/117/119/1114`, `test_phase25_test_verification_mapping`, `test_phase65/67/68/97/912`, p7-outcome suites, `test_development_repair`, `test_specialist_repair`, `test_verification_attribution`, sandbox tool suites | **253 passed** |
| B — governed + specialist + development | `test_governed_development_bridge`, `test_supplied_edit_bridge`, `test_development_contract_propagation`, `test_evolution_development_history_bridge`, `test_phase43`, `test_development_capability_step2`, `test_conversation_development_intake`, kernel authoring wiring, all specialist suites, `test_phase93`, `test_phase123` | **343 passed** |
| C — planning/verification-expectation | `test_development_change_plan`, `test_development_target_bridge`, `test_development_localization`, `test_authoring_contract_test_projection`, `test_phase93`, `test_phase123` | **155 passed** |
| focused | `test_verification_attribution` | **23 passed** |

**Total: 774 passed, 0 failed.** Every test file that references the changed
surface (`verification_expectations` / `plan_development_change` /
`change_author_router` / `_plan_verify_target`) is included. Known pre-existing
real-kernel failures remain separately classified and were not run as part of
these suites.

## 8. Real-world integrated validation

Real Atlas runtime (governed entry point → OWNER approval → governed execution →
sandbox verification), scenarios A–G:

| Scenario | Result |
|---|---|
| **A/B — normal + specialist development** | integrated deterministic governed repair acceptance: `SUCCESS`, 2 iterations, repository unchanged, promotion pending 0 |
| **C — `pass_to_fail` → repair eligible** | real 7B probe iteration 1: baseline `true`, transition **`pass_to_fail`**, repair **attempted** |
| **D — `fail_to_fail` → repair NOT eligible** | focused real-sandbox test: a pre-existing failure yields `ALREADY_FAILING`; the repair supplier returns the baseline unchanged (no corrective change) |
| **E — repair → corrective change → re-verification** | integrated acceptance: repair authored a **different** change → re-verified → `SUCCESS` |
| **F — provider disabled** | `[specialists].enabled=false` → no specialist, request fails closed, no proposal/execution/promotion, repository unchanged — **PASS** |
| **G — adversarial proposal** | specialist/adapter adversarial suites: malformed, wrong capability, missing/empty identity, missing/zero/multi files, traversal, absolute, out-of-target, invalid content, unauthorized fields → all fail closed, no mutation |
| FIX-1/FIX-2 evidence | real 7B probe: an errored baseline is now `unknown` (not a false `fail_to_fail`); the plan leads with the focused `tests/test_mock_provider.py` |

## 9. Governance / invariant audit

- `code.generate` specialist remains **ACTIVE** (all specialist suites pass).
- Governed authoring, OWNER approval, sandbox verification and the promotion
  boundary intact; **no automatic promotion** (pending promotions 0 throughout).
- Provider-disabled and provider-unavailable remain fail-closed.
- Verification attribution and repair remain ACTIVE; recovery stays fail-closed.
- Deterministic-first behavior unchanged; the external model remains optional and
  non-authoritative; no new dependency, authority or governance path.
- Known pre-existing `TestRealKernel` failures remain separately classified.

## 10. Regressions

None introduced. **No new failure remains unresolved.** (Command 4 had already
resolved the Command 3-introduced `recoverable=True` regression; Command 5's
coherent regression re-confirms it green, including `test_phase42`.)

## 11. Remaining limitations

- Verification-target suitability beyond the name convention (semantic relevance
  ranking, test runnability probing) — would need evidence to justify.
- The baseline probe costs one extra bounded test run per iteration.
- The 30 s sandbox verification bound can still time out a slow test; the outcome
  is now conservatively `unknown`.

## 12. Future capabilities (deferred, not unfinished)

- **Multi-file authoring** — future evidence candidate; the one-file contract is
  an intentional bound.
- **Operational capability** (durable task state, leases, worktrees, parallel
  work, interruption/resumption) — NOT YET JUSTIFIED.
- **Stronger local model / model-quality work** — model-quality, not Atlas.
- **Richer verification-target selection** — needs a demonstrated real failure.

## 13. Capability status (final assessment)

| Area | Status |
|---|---|
| Understanding (language, intent, repository, target, context, references, ambiguity) | **VALIDATED** |
| Planning (ChangePlan, bounded scope, verification expectations, verification target) | **VALIDATED** (target suitability now prefers the change-related focused test) |
| Authoring (deterministic, supplied, specialist, governed) | **VALIDATED** |
| Verification (sandbox, attribution, classification, propagation) | **VALIDATED** |
| Repair (diagnosis, eligibility, specialist corrective generation, re-verification, bounded retries) | **VALIDATED** |
| Governance (OWNER approval, fail-closed, containment, no auto-promotion, provider isolation) | **VALIDATED** |
| Conversation (development continuity, follow-up, contextual requests) | **VALIDATED** |
| Operational capability (current justified scope only) | **NOT JUSTIFIED (future)** |

**The CURRENT development capability is CLOSED.** Every Tier A gap is resolved;
justified Tier B gaps are resolved; the remaining items are explicitly future,
architectural, environmental, model-quality, or not-yet-justified — not unfinished
current work.
