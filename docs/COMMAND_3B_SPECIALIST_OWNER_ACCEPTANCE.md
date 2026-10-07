# Command 3B — Real Specialist → Governed Development Acceptance

Status: **PASS** (real provider-enabled OWNER acceptance, provider-disabled proof,
and adversarial boundary all pass).

This document is the durable OWNER evidence for the `code.generate` specialist
capability running end-to-end through Atlas's EXISTING governed development path.
It is produced by a real local model call (not simulated).

---

## 1. Starting state

| Field | Value |
|---|---|
| Starting commit | `3397c373a85bbf2c4bdb15c6a42e89828679ca93` |
| Branch | `main` |
| Working tree at start | clean |
| `HEAD == origin/main` | yes |
| Local runtime | Ollama `http://127.0.0.1:11434` (reachable) |
| Available models | `qwen2.5-coder:7b`, `deepseek-coder-v2:latest`, `qwen3:8b`, `nomic-embed-text:latest` |
| Intended specialist model | `qwen2.5-coder:7b` |

## 2. Provider configuration used for the real run

```toml
[specialists]
enabled = true
provider_id = "ollama.qwen2.5-coder-7b"
model = "qwen2.5-coder:7b"
host = "http://127.0.0.1:11434"
timeout_seconds = 180.0
```

The default in the committed `config.toml` is `enabled = false` (no provider
constructed; deterministic path unchanged).

## 3. Real provider-enabled OWNER run

| Field | Value |
|---|---|
| Timestamp (UTC) | `2026-10-07T22:23:32.881311+00:00` |
| Proposal ID | `DEV-33e9b0e645fac5c2` |
| Approval request ID | `APPR-20261008042412-0001` |
| Candidate ID | `605ecb814df43f79` |
| Provider ID | `ollama.qwen2.5-coder-7b` |
| Model ID | `qwen2.5-coder:7b` |
| Specialist capability | `code.generate` |
| Target (declared) | `atlas/specialist_transport.py` |
| Provider invocations | 1 (real) |
| Task context | 1 file, 3348 chars (bounds: 20000 source / 24 files / 60000 chars) |
| Task request | 236 chars (bound 4000) |
| Task plan | `{target, target_kind: module, route: specialist_model, constraints: [preserving]}` |
| Verification tests given to the task | `["tests/test_specialist_transport.py"]` |
| Generated file | `atlas/specialist_transport.py`, 3349 chars |
| Generated sha256 | `d459969f6ccffa8fa67636ea295c9f172b9c7404bc288dc1ee6b328d22485446` |
| Generated differs from original | **yes** (real inference produced new content) |
| `change_origin` | `specialist-proposal` |
| `content_status` | `unverified-draft` |
| Authoring payload | `ok=true`, status `PENDING_APPROVAL`, `authorized=false`, `executed=false` |
| Source sha256 before / after | `49f77eac9ee28816a394ab191d5814d42194aeb7c7336bb74c8cba983437a46e` / same |
| Repository target unchanged | **yes** (governed execution is sandbox-only) |

### Governance transitions

| Stage | Result |
|---|---|
| Specialist proposal | validated by Atlas (`SpecialistRegistry` + `validate_proposal`) |
| Authoring | `SpecialistChangeSupplier` consumed it; exactly ONE `code_changes` entry |
| Proposal | `PENDING_APPROVAL` (stopped at the human boundary) |
| OWNER session | `principal_id=owner`, `authority=owner` |
| OWNER approval (explicit) | `APPROVED` |
| Execution (OWNER-gated, sandbox-only) | `SUCCESS`, 1 iteration |
| Changed files (sandbox) | `atlas/specialist_transport.py` |
| Verification target | `tests/test_specialist_transport.py` (plan-selected, bounded) |
| Verification | `verified`; `test_outcome=passed`; `verification_passed=true` |
| Promotion | not performed; pending promotions `0` before and after |
| Automatic promotion | **none** (promotion is a separate OWNER step) |

### Bounded request actually sent to the real runtime

```json
{
  "capability": "code.generate",
  "target": "atlas/specialist_transport.py",
  "context_files": 1,
  "context_chars": 3348,
  "plan": {
    "target": "atlas/specialist_transport.py",
    "target_kind": "module",
    "route": "specialist_model",
    "constraints": ["preserving"]
  },
  "verification_tests": ["tests/test_specialist_transport.py"],
  "request_chars": 236
}
```

## 4. Provider-disabled acceptance (fail-closed)

With the supported default configuration (`[specialists].enabled = false`):

| Field | Value |
|---|---|
| Specialist constructed | no (`_specialist_author is None`) |
| `provider_enabled_config` | `false` |
| Authoring payload | `ok=false`, `reason="the request supplies no code block"` |
| Proposal ID | `""` (none created) |
| OWNER approval | not requested |
| Execution | not performed |
| Promotion pending | 0 |
| Automatic promotion | none |
| Repository target | unchanged |

## 5. Adversarial boundary acceptance

### 5a. Provider unavailable (enabled but transport raises)

Specialist constructed, but the provider raised → proposal `None` → the request
fails closed: no proposal, no approval, no execution, no promotion, no
repository mutation.

### 5b. Provider output escapes the bounded target (end-to-end)

A transport returning a file **outside** the declared target
(`atlas/kernel/atlas.py`) was offered to the gate: the specialist seam refused
it (`failures: [["supplier", "supplier produced no changes"]]`), no proposal
was created, no execution occurred, and the target was unchanged.

### 5c. Provider output exceeds the one-file bound (end-to-end)

A transport returning **two** files was refused identically.

### 5d. Focused adversarial unit cases

The committed focused suites additionally pin, at the seam level:
malformed proposal, wrong capability, missing/empty provider identity,
missing/zero/multiple files, proposal-path/file mismatch, absolute path,
Windows drive path, traversal, out-of-target path, invalid/whitespace-only
content, non-string path/content, unauthorized action/metadata keys, and
oversized content — all fail closed. See `tests/test_specialist_change_supplier.py`
and `tests/test_specialist_development_author.py`.

## 6. Focused regression results

Commands and results (Windows, Python 3.14):

| Command | Result |
|---|---|
| `pytest tests/test_specialist_foundation.py tests/test_specialist_provider_http.py tests/test_specialist_transport.py tests/test_specialist_change_supplier.py tests/test_specialist_development_author.py tests/test_development_envelope_config_parsing.py tests/test_phase93_change_design_independence.py tests/test_phase123_model_seam_audit.py -q` | **166 passed** |
| `pytest tests/test_evolution_model_assisted_supplier.py tests/test_evolution_model_assisted_activation.py tests/test_governed_development_bridge.py tests/test_supplied_edit_bridge.py -q` | **107 passed** |
| `pytest tests/test_development_change_plan.py tests/test_development_target_bridge.py tests/test_development_contract_propagation.py tests/test_development_capability_step2.py tests/test_conversation_development_intake.py "tests/test_investigation.py::TestAuthoringWiring" -q` | **168 passed** |
| `pytest tests/test_evidence_governed_development.py -q` | 18 passed, **2 failed (pre-existing)** |
| `pytest tests/test_phase43_governed_development_validation.py -q` | **10 passed** |

### Pre-existing failures (NOT regressions)

`tests/test_evidence_governed_development.py::TestRealKernel::
test_evidence_proposal_waits_for_owner_without_running_anything` and
`::test_owner_approval_reaches_the_promotion_boundary_but_never_promotes`
fail with `"no resolvable real evidence gap"`. Both were reproduced against a
pristine `fa6f775` worktree and are data-dependent real-kernel failures unrelated
to this change (the same class previously recorded for Command 3A).

## 7. Changed-file set (this commit)

| File | Change |
|---|---|
| `atlas/evolution/specialist_development.py` | NEW — bounded specialist → development producer |
| `atlas/evolution/specialist_change_supplier.py` | forward the plan-derived `test_files` / `repository_context` (bounded verification leg) |
| `atlas/kernel/atlas.py` | build the OPT-IN specialist author; consult it in `development_authoring_request` when no explicit edit is supplied |
| `atlas/config/configuration.py`, `atlas/config/configuration_models.py` | typed `[specialists]` settings (default disabled) |
| `config.toml` | `[specialists]` section (default `enabled = false`) |
| `tests/test_specialist_change_supplier.py` | verification-forwarding tests |
| `tests/test_specialist_development_author.py` | NEW producer tests |
| `docs/COMMAND_3B_SPECIALIST_OWNER_ACCEPTANCE.md` | this evidence artifact |

No execution, approval or promotion path was weakened. The specialist remains an
**untrusted proposal source**; Atlas retains authority over interpretation,
localization, planning, bounds, validation, approval, execution, verification and
promotion.

## 8. Capability status

`code.generate` is now **ACTIVE as a validated specialist capability within
governed development**, with Atlas retaining authority over interpretation,
localization, planning, bounds, validation, approval, execution, verification,
and promotion.

Automatic promotion: **none**. Pending promotion reviews: **0**.
