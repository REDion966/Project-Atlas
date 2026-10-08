# Command 3 — Final Coding Specialist Acceptance

Status: **COMMAND 3 COMPLETE**.

Closes the specialist coding capability: bounded specialist inference → governed
authoring → OWNER approval → sandbox verification → **failure diagnosis → bounded
specialist repair → corrective change → re-verification**.

Related evidence:
- `docs/COMMAND_3B_SPECIALIST_OWNER_ACCEPTANCE.md` (real OWNER lifecycle)
- `docs/COMMAND_3C_CAPABILITY_GAP_ASSESSMENT.md` (gap assessment)
- this document (final closure)

---

## 1. Final capability matrix

| Capability | Status |
|---|---|
| NL development intent / routing / localization / bounded context / symbols / deps | VALIDATED |
| ChangePlan / bounded target / verification expectations / verification-target selection | VALIDATED (selection heuristic noted in §9) |
| Deterministic, supplied-code, structural, **specialist-generated** authoring | VALIDATED |
| Bounded proposal validation / model-provider isolation | VALIDATED |
| Bounded sandbox verification + failure classification + result propagation | VALIDATED |
| **Failure → diagnostic → bounded specialist repair → re-verification** | **VALIDATED (implemented this command)** |
| OWNER approval / fail-closed / promotion boundary / no auto-promotion | VALIDATED |
| Provider-disabled / provider-unavailable | VALIDATED |
| Multi-file authoring | BOUNDED (one-file contract intentionally preserved) |
| Operational (task ledger/worktrees/parallel) | NOT YET JUSTIFIED |

## 2. Real specialist generation

- Provider `ollama.qwen2.5-coder-7b`, model `qwen2.5-coder:7b`, capability `code.generate`.
- Real inference produced a validated `SpecialistProposal` for
  `atlas/ai/providers/mock_provider.py` and `atlas/specialist_transport.py`;
  Atlas-owned seam (`BoundedSpecialistTask` → `SpecialistRegistry` → `validate_proposal`).

## 3. Governed authoring

`SpecialistChangeSupplier` consumed the proposal through the EXISTING
`CompositeChangeSupplier`; exactly ONE `code_changes` entry, `change_origin =
"specialist-proposal"`, `content_status = "unverified-draft"`, no unauthorized
mutation. The declared target is enforced (path + dotted forms).

## 4. OWNER approval → verification (Command 3B evidence)

`PENDING_APPROVAL` → explicit OWNER approval → `APPROVED` → sandbox execution →
bounded verification against the plan-selected test; repository unchanged; no
auto-promotion. (See Command 3B evidence.)

## 5. Failure classification (this command)

`DevelopmentDiagnostic` now marks an **attributable** verification failure (an
applied change whose targeted test failed/errored) `recoverable=True`;
`DevelopmentRecovery` therefore returns **`REVISE_AND_RETRY`**. Rollbacks
(change not applied), verification timeouts and governance/objective/capability
failures remain non-recoverable.

The development outcome message now carries the REAL pytest reason (bounded to
1200 chars), so a repair reasons about WHAT failed instead of a bare
"pytest failed to start".

## 6. Repair (implemented this command)

`RepairChangeSupplier` now prefers the **ACTIVE** `code.generate` specialist seam
(the same `SpecialistDevelopmentAuthor`/`SpecialistRegistry` used for initial
generation) and falls back to the pre-existing generic model supplier. The
corrective change is:

- untrusted and validated by the EXISTING `SpecialistChangeSupplier` (identity,
  capability, one file, confinement, target containment);
- restricted to the SAME single authorized target (no scope expansion);
- required to **differ** from the failing content (the Command 3C
  identical-workload failure is refused);
- re-verified against the SAME baseline tests/target;
- bounded by the existing iteration budget; fail-closed on any deviation;
- never promoting, never bypassing approval/authorization.

The kernel wires it lazily: `repair_author=lambda: self._specialist_author`
(single specialist instance; `None` when disabled).

### Deterministic end-to-end repair acceptance (controlled provider)

| Step | Result |
|---|---|
| Target | `atlas/specialist_transport.py` (focused test `tests/test_specialist_transport.py`) |
| Initial (bad) change | `1e64179f4383` → verification **FAILED** (`test_outcome=failed`) |
| Diagnosis | `failure_class=verification, confidence=known, recoverable=true` |
| Recovery | `strategy=revise_and_retry` |
| Activist repair (ACTIVE seam) | produced a **DIFFERENT** corrective change `49f77eac9ee2` |
| Re-verification | **passed** (`verification_passed=true`) |
| Run | **SUCCESS**, 2 iterations, 2 provider calls |
| Repository | target **unchanged**; promotion pending **0** |

### Real-model repair probe (real `qwen2.5-coder:7b`)

The real model path was exercised end to end: the bad initial change failed
verification, the diagnostic was `verification`/`known`/`recoverable=true`, the
recovery selected `revise_and_retry`, and the **ACTIVE specialist repair fired**
(`plan_route=specialist_repair`, a genuinely different corrective change was
produced, bounded, same target, fail-closed). In this session the 7B model's
corrective **content** did not pass verification within the 3-iteration budget —
a model-output-quality limitation, not an integration defect (the integration is
proven by the deterministic acceptance above and by the real run's identical
control flow). The external model remains optional.

## 7. Governance

OWNER-controlled authorization, sandbox-only execution, mandatory approval,
separate promotion, fail-closed behavior and the non-authoritative model are all
unchanged. Repair adds no new approval/authorization/promotion path: retries stay
inside the single approved, bounded sandbox run.

## 8. Provider-disabled / adversarial

- `[specialists].enabled=false` → no specialist constructed; requests fail
  closed (no proposal, no execution, no promotion, repository unchanged). **PASS**.
- Provider-unavailable (enabled, transport raises) → fail closed. **PASS**.
- Adversarial repair boundary (`tests/test_specialist_repair.py`): wrong target,
  multiple files, traversal, absolute path, empty content, malformed proposal,
  wrong capability, missing/empty provider identity, unavailable/raising provider,
  non-recoverable failures (rollback/timeout), and identical-content restatement
  all fail closed; no authority surface; inputs not mutated. **PASS**.

## 9. Focused tests

- Batch A (specialist foundation/provider/transport/change-supplier/development-author/repair + development repair + sandbox newline) — **190 passed**.
- Batch B (specialist governed acceptance; failure-recovery phases 89/98/119; governed development bridge; supplied-edit bridge; development capability Step 2; conversation development intake; kernel authoring wiring; sandbox tools/phases 95/117) — **220 passed**.
- New focused suites: `tests/test_specialist_repair.py` (17), `tests/test_sandbox_newline_stability.py` (3).

### Known pre-existing failures (separately classified, unchanged)

- `tests/test_evidence_governed_development.py::TestRealKernel` — 2 data-dependent failures ("no resolvable real evidence gap"), reproduced at pristine `fa6f775`.
- `tests/test_evidence_directed_development.py::TestRealKernel::test_real_gap_produces_a_pending_approval_proposal` — same class.

## 10. Command 3C findings reassessed

- **A. Verification-target suitability** — real but heuristic; the demonstrated
  instance was self-inflicted (Command 3B test, resolved) and one probe target
  fails regardless of the change. Recorded as a SECONDARY GAP, not a blocker.
- **B. E2 newline stability** — was a genuine blocker (a valid CRLF change was
  rejected at apply). Fixed: `CodeSandbox.write_text`/`read_text` are now
  newline-faithful (`newline=""`); regression `tests/test_sandbox_newline_stability.py`.
- **C. Multi-file** — one-file contract preserved (bounded); FUTURE EVIDENCE CANDIDATE.
- **D. Repository intelligence** — no new failure; no framework introduced.
- **E. Operational development** — no evidence; not introduced.

## 11. Final repository state

- Start `03af1b65614e7c9f9e076529856f279dc3457138` (`HEAD == origin/main`, clean).
- `code.generate` remains ACTIVE within governed development.

---

**COMMAND 3 IS COMPLETE.**
