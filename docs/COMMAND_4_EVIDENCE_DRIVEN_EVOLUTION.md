# Command 4 — Evidence-Driven Capability Evolution

Status: **COMMAND 4 COMPLETE — CAPABILITY EVOLUTION VALIDATED (Outcome A)**.

Selected capability: **verification attribution** — Atlas can now distinguish a
change-caused test failure from a pre-existing one, using a bounded pre-change
(baseline) verification probe.

---

## 1. Starting commit

- `639a6b908db24a8cd6735e5aa3381c38e6419364` (`HEAD == origin/main`, clean).
- Command 3 COMPLETE; `code.generate` ACTIVE; governed authoring + verification +
  repair proven.

## 2. Investigated capability matrix (Commands 1–3 evidence + this investigation)

| Area | Capability | Status |
|---|---|---|
| Understanding | NL intent, routing, localization, context, symbols, deps | VALIDATED |
| Planning | ChangePlan, bounded target, verification expectations + selection | VALIDATED |
| Authoring | deterministic / supplied / structural / specialist, isolation, validation | VALIDATED |
| Verification | bounded sandbox verification, failure classification, propagation | VALIDATED |
| **Verification attribution** | **change-caused vs pre-existing failure** | **GAP → VALIDATED (this command)** |
| Repair | diagnostic → bounded specialist repair → re-verification | VALIDATED (Command 3) |
| Governance | OWNER approval, fail-closed, promotion boundary, no auto-promotion | VALIDATED |
| Provider | disabled/unavailable fail-closed, untrusted output | VALIDATED |
| Knowledge | acquisition, evaluation, retention, provenance | VALIDATED |
| Self-knowledge | architecture/module/dependency/capability awareness | VALIDATED |
| Conversational development | multi-turn, references, corrections | VALIDATED |
| Operational | multi-step, state, ownership, rollback, parallel | NOT YET JUSTIFIED |

## 3. Selected gap (one)

**Verification attribution.** Atlas could not tell whether a verification failure
was caused by the change or already existed — it assumed every applied-change
failure was attributable.

## 4. Evidence proving the gap

1. **Command 3 real probes.** The development loop applied a change, ran the
   plan-selected test, and on failure classified `verification` with
   `recoverable=True` **without any pre-change reference**. In the real
   `mock_provider` probe the selected verification target had **failed on the
   original module**, so the failure was not the change's fault — yet a repair
   was authored against it (wasted bounded iterations, misdirected work).
2. **No baseline existed.** `VerificationExpectation.baseline` was a static
   `"not_executed"` placeholder; the loop seeded the support closure but
   deliberately skipped the changed path, so the unmodified target was never
   available for comparison.
3. **Command 4 re-measurement.** Even after Command 3's fix, iteration
   attribution was a bare heuristic (`applied + test failed/errored`).

## 5. Researched mechanisms (2–5)

| Mechanism | Idea | Verdict for Atlas |
|---|---|---|
| **FAIL_TO_PASS / PASS_TO_PASS transition test status** (SWE-bench grading) | grade a patch by tests that flip fail→pass and stay pass→pass; the common failure mode is the PASS_TO_PASS regression | **Adapted** — the exact, minimal, deterministic core |
| Test-impact analysis (TIA) | run only tests affected by a change | Already effectively present (`tests_for_module` / selective verification); not the gap |
| Differential / A-B testing | run the same probe before and after a change | **Adapted** — the pre-change baseline probe |
| SBFL / fault localization (Ochiai, spectra) | rank suspicious statements from coverage | Overkill; no evidence a ranking is needed to attribute |
| Mutation testing | inject faults to judge test strength | Orthogonal (test quality, not attribution) |

No framework/dependency is adopted: the selected mechanism is a **pattern**
(two bounded status readings + a transition), implementable Atlas-natively with
the standard library and the EXISTING sandbox verifier.

## 6. Selected approach

A single bounded **pre-change (baseline) verification probe** per iteration,
using the SAME verifier and the SAME plan-selected target, and a pure transition
classifier — `pass_to_fail` (attributable regression), `fail_to_pass` (fixed),
`pass_to_pass`, `fail_to_fail` (pre-existing), `unknown`.

## 7. Implementation summary

- **`atlas/evolution/verification_attribution.py` (new, pure).**
  `VerificationTransition`, `classify_transition`, `baseline_of`,
  `transition_of`, `is_attributable`, `is_recoverable`, `describe`. Stdlib only,
  no I/O, no model, no side effects.
- **`atlas/evolution/self_development_loop.py`.** In one iteration the loop now
  (a) seeds the PRE-CHANGE content of each changed path from the workload's
  bounded repository context (the apply overwrites it, so post-change state is
  unchanged), (b) resolves the bounded verification target BEFORE the apply,
  (c) runs a bounded BASELINE probe on it, and (d) records
  `metadata["verification_baseline"]` on the outcome.
- **`atlas/evolution/development_diagnostic.py`.** The verification diagnosis now
  carries the transition in its evidence (`transition=…`). The **fail-closed
  recovery contract is restored** (`recoverable=None`): see §8.
- **`atlas/evolution/development_repair.py`.** `_is_repairable` now requires an
  attributable failure: a recorded `fail_to_fail` baseline is **not** repaired;
  the transition travels in the repair plan and prompt. Unknown baselines keep
  the previous conservative heuristic.

## 8. Regression fixed (Command 3-introduced)

Command 3 made verification failures `recoverable=True`, which contradicted the
deliberate fail-closed recovery contract and **broke 4 pre-existing tests**
(`tests/test_phase42_development_lifecycle.py`) that Command 3 did not run:
`recoverable is None`, `recovery.strategy == "no_recovery"` (twice), and the
persisted-evidence contract. Command 4 **restores the original fail-closed
recovery contract** (the loop's bounded retry — and therefore specialist repair —
is driven by the existing iteration budget, not by an automatic recovery grant)
and expresses attribution through the new dedicated mechanism instead. The 4
tests pass **unmodified**; no test was weakened, skipped or reclassified.

## 9. Tests

- `tests/test_verification_attribution.py` (new, 16) — pure transitions (incl.
  non-boolean → `unknown`), only-regression-attributable/recoverable, outcome
  baseline reader, **real sandbox baseline probe** (`pass_to_fail`,
  `fail_to_fail`, `pass_to_pass`), and repair eligibility (regression repaired;
  pre-existing not repaired; unknown → legacy heuristic).
- Coherent-checkpoint regressions (loop/verification/repair/sandbox/governed,
  Command 3 capability): **187 + 139 + 65 + 167 = 558 passed** across
  `test_evolution_self_development_loop`, `test_phase42/43/65/67/68/89/95/96/97/98/117/119/912/1114`,
  `test_phase25_test_verification_mapping`, the p7 outcome suites,
  `test_governed_development_bridge`, `test_supplied_edit_bridge`,
  `test_development_contract_propagation`,
  `test_evolution_development_history_bridge`, `test_development_repair`,
  `test_specialist_repair`, and the Command 3 specialist suites.
- Known pre-existing failures unchanged and separately classified (real-kernel
  data-dependent `TestRealKernel`).

## 10. Real-world runtime probe

Real Atlas runtime (governed entry point → OWNER approval → governed execution →
sandbox verification) with the ACTIVE `qwen2.5-coder:7b` specialist on
`atlas/ai/providers/mock_provider.py`:

| Iteration | test_outcome | baseline | transition | repair attempted |
|---|---|---|---|---|
| 1 | failed | **true** | **pass_to_fail** | **yes** (attributable) |
| 2 | error | false | fail_to_fail | **no** (not attributable) |

The loop ran the bounded baseline probe in the real sandbox, computed the
transition, repaired only the attributable failure, and **declined to repair a
non-attributable one** (author trace shows exactly one repair invocation).
Repository unchanged; promotion pending 0.

Limitation observed: for a slow/borderline test the 30 s sandbox bound can make
the baseline itself flaky (`unknown`/spurious `fail_to_fail`) — recorded in §12.

## 11. Governance / invariant audit

- Command 3 specialist capability ACTIVE — specialist suites pass (167).
- Governed authoring, OWNER approval, sandbox verification, promotion boundary,
  no auto-promotion — unchanged (governed bridge + phase43 + evidence suites pass).
- Provider-disabled: `[specialists].enabled=false` → no specialist, request fails
  closed, no proposal/execution/promotion, repository unchanged — **PASS**.
- Deterministic-first behavior unchanged; external model remains non-authoritative
  and optional; recovery stays fail-closed (restored).
- No new dependency, authority, governance path, or mandatory mechanism.

## 12. Limitations

- The baseline probe costs one extra bounded test run per iteration (bounded by
  the existing iteration budget).
- When no bounded repository context carries the pre-change target, no baseline is
  established → transition `unknown` → the previous conservative heuristic is kept.
- A slow test can exceed the 30 s sandbox bound on either probe, degrading the
  transition to `unknown`/spurious; attribution is only as good as the bounded
  probe. (Verification-target suitability remains a secondary gap.)

## 13. Remaining future gaps

- **Verification-target suitability** (prefer a focused, runnable, change-related
  test) — secondary; the baseline probe now partly mitigates it.
- **Multi-file authoring** — one-file specialist contract intentionally preserved.
- **Operational capability** (durable task state, leases, worktrees, parallel
  work) — NOT YET JUSTIFIED; no probe required it.

## 14. Final capability status

`code.generate` remains **ACTIVE** within governed development. **Verification
attribution is now ACTIVE and VALIDATED**: a bounded pre-change baseline probe
plus a deterministic PASS_TO_PASS/FAIL_TO_PASS transition, wired into the governed
development loop and repair eligibility, proven by focused tests (including a real
sandbox probe) and a real-runtime probe.
