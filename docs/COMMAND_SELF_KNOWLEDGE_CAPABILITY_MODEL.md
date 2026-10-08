# Command 6 — Atlas Self-Knowledge & Capability Model

Status: **SELF-KNOWLEDGE FOUNDATION COMPLETE.**

Atlas now has a deterministic, evidence-backed, queryable understanding of its own
governed-DEVELOPMENT capabilities, reachable through both an Atlas-owned structured
interface and the EXISTING conversation self-knowledge surface.

---

## 1. Starting commit

- `0b837cfd08be0d14a2647e2b7148f663b63c3484` (`HEAD == origin/main`, clean).
- Command 5 COMPLETE; the governed development capability is CLOSED.

## 2. Objective

Give Atlas ONE deterministic, Atlas-owned, model-independent identity for its
development capabilities — what they are, their status, where they live, what
interface they expose, what governance applies, whether they are deterministic or
externally assisted, whether they are validated, and an evidence reference — plus a
structured query interface, and connect that to the existing conversation and
development boundaries.

## 3. Architecture

The addition is deliberately SMALL and reuses the existing self-knowledge stack:

```
atlas/self_knowledge/operational_capabilities.py   (Step 12 catalogue)  ─┐
atlas/self_knowledge/development_capabilities.py   (Command 6 catalogue) ─┤
                                                                          ├─► CapabilityModel
atlas/self_knowledge/capability_model.py  (unified, read-only projection) ┘        │
                                                                                  ▼
kernel: Atlas.capability_model() / capability_contract()   ──►  conversation self-knowledge
kernel: Atlas.development_self_model() / development_capability_boundary()  (structured)
```

- **New — `atlas/self_knowledge/development_capabilities.py`**: the bounded,
  evidence-grounded catalogue + `DevelopmentCapabilityModel` (+
  `CapabilityStatus`, `DevelopmentCapability`, `build_development_capability_model`,
  `find_development_capability`). Standard library only, no I/O, no model, no
  authority. An unknown capability yields `None`/`""`/`()` — never invented.
- **Kernel** (`atlas/kernel/atlas.py`): the development catalogue is projected into
  the SAME bounded operational surface (`to_operational_capabilities()`), so the
  EXISTING self-knowledge answers cover it with **no new conversation code**; plus
  two structured accessors — `Atlas.development_self_model()` and
  `Atlas.development_capability_boundary(name)`.

## 4. Self-knowledge schema

`DevelopmentCapability`: `id`, `name`, `purpose`, `status`, `owner_module`,
`entry` (the public interface), `dependencies`, `governance` (boundaries),
`dependency_class` (`deterministic` | `external_model_dependent`), `validated`,
`evidence` (module/doc/test references), `aliases`, `extends` (extension
relationships), `limitations`.

`CapabilityStatus` (closed): `ACTIVE`, `PARTIAL`, `FUTURE`, `NOT_AVAILABLE`
(grounded in the current wiring). Extension boundary (closed token):
`existing` / `future` / `unavailable` / `unknown`.

The catalogue covers the Command 1–5 development machinery: `development.localization`,
`development.planning`, `code.generate`, `governed.authoring`,
`development.verification`, `development.attribution`, `code.repair`,
`governance.approval`, `development.execution`, `governance.promotion`,
`development.extension`, plus the honest FUTURE entries `code.multifile` and
`development.autonomous`. Governance boundaries represented: `owner_approval`,
`sandbox_execution`, `provider_isolation`, `no_auto_promotion`, `fail_closed`.

## 5. Evidence grounding

Do NOT ask a model to describe Atlas. Every claim is traceable to an Atlas-owned
reference: the entry's `owner_module`/`entry` name the real implementation, and
`evidence` names a module + a durable evidence document or focused test
(e.g. `atlas.evolution.verification_attribution`,
`docs/COMMAND_4_EVIDENCE_DRIVEN_EVOLUTION.md`,
`tests/test_verification_attribution.py`). Availability is GROUNDED in the actual
runtime wiring (specialist constructed / repair loop wired / governed boundary
wired) — never inferred from a name. Unknown capability → fail-closed.

## 6. Conversation integration

`_operational_capabilities()` (the kernel's single grounded catalogue) now returns
the Step-12 catalogue **plus** the development catalogue. Because the EXISTING
conversation self-knowledge surface answers from that unified model, development
capability questions resolve deterministically with **no new conversation code**.
Verified in the real runtime (§9): `explain code.generate`, `is code.generate
available?` (→ "governed"), `what capabilities do you have?`, `which capabilities
are governed?` — all answered with `model_used: false`.

## 7. Development integration

`Atlas.development_capability_boundary(name)` returns the authoritative structured
bridge for development planning: `{found, status, effective_status, extension,
owner_module, entry, dependencies, governance, evidence, limitations, …}` — or
`{"found": False}` for an undeclared capability. The EXISTING capability-discovery
surface (`Atlas.capability_contract`) also resolves the development capabilities
(verified: `found: true`, `category: development`). This is the information Atlas
will need to decide *whether a requested capability already exists, which subsystem
is relevant, and what governance applies* — **without** granting any permission to
change anything.

## 8. Governance boundaries

The self-knowledge model is READ-ONLY and carries no authority surface (no
`apply`/`approve`/`promote`/`authorize`/`execute`). Querying it cannot mutate
Atlas, approve, promote or bypass any boundary. It sits on the **Atlas
reasoning/capability side** of the architecture, is model-independent and
deterministic-first, and its output is descriptive metadata only — the existing
OWNER approval, sandbox execution, verification and promotion boundaries are
unchanged.

## 9. Real-world probes (actual runtime)

Two real kernel runs (default config; specialist + repair wired):

| Item | Default | Enabled |
|---|---|---|
| `code.generate` status | `not_available` (grounded: specialist off) | **`active`**, `validated=true` |
| where it lives | `atlas.evolution.specialist_development` — `SpecialistDevelopmentAuthor.propose` | same |
| governance | `owner_approval`, `sandbox_execution`, `provider_isolation` | same |
| extension | `code.generate`=unavailable; `development.verification`=existing; `code.multifile`=`future`; `development.autonomous`=`future` | `code.generate`/`code.repair`=`existing`; futures unchanged |
| planning bridge | `found=true` | `found=true` |
| unified model includes development capabilities | yes | yes |

Conversation-boundary turns (enabled kernel, all `model_used: false`):
`explain code.generate` → operational capability, category `development`, supports
`SpecialistDevelopmentAuthor.propose`; `is code.generate available?` → **governed**
(OWNER approval boundary); `which capabilities are governed?` → lists
`code.generate` and `development.execution`; `what capabilities do you have?` →
the confirmed inventory. Unknown capability → `found: false` (fail-closed); no
authority surface present. The repository was not mutated.

## 10. Tests

- **Focused (new)** `tests/test_development_capability_self_model.py` — **28 passed**:
  bounded/ordered catalogue; evidence-grounded entries; lookup by id/alias/name;
  module/entry/governance/dependency/status/evidence lookup; deterministic
  ordering and bounded results; fail-closed for unknown and malformed queries;
  the existing/partial/future/unavailable extension boundary; wiring-grounded
  status; the operational projection; and the no-authority surface.
- **Coherent regression** (affected surfaces: capability model, conversation
  self-knowledge, Command 3–5 development foundation): **238 + 228 + 27 + 1 passed**
  (`test_capability_model`, `test_capability_contracts`,
  `test_step12/13/14`, `test_development_gap_capability_adjudication`,
  `test_builtin_self_knowledge`, `test_self_knowledge_bridge`,
  `test_c5_self_knowledge_surface`, `test_c4_1_capability_detail_routing`,
  and the development foundation: attribution, repair, phase42, governed bridge,
  specialist suites, self-development loop, supplied-edit bridge).
- **One intentional contract update**: `test_step13::test_step12_catalogue_is_intact`
  now asserts the kernel operational surface equals the Step-12 catalogue **plus**
  the Command-6 development catalogue — the SAME "nothing is invented" invariant
  over the extended, still-exactly-declared surface. No test was weakened, skipped
  or deleted.

### Known pre-existing failure (separately classified)
`test_builtin_self_knowledge.py::TestKernelWiring::test_kernel_architecture_provider_is_cache_only`
— reproduced against a pristine `f602faf` worktree; **not caused by this command**.

## 11. Limitations / future

### IMPLEMENTED AND VALIDATED
- Evidence-backed development capability model with status, owner, interface,
  dependencies, governance, dependency class, validation and evidence references.
- Deterministic structured query interface + a development-planning bridge.
- Conversation access through the EXISTING self-knowledge surface (model-free).
- Existing/partial/future/unavailable extension representation.

### FUTURE (explicitly deferred, not unfinished current work)
- **Autonomous self-development** (`development.autonomous`, declared FUTURE): the
  self-knowledge foundation is in place; Atlas does not yet modify itself
  autonomously.
- **Multi-file authoring** (`code.multifile`, declared FUTURE) — the one-file
  contract remains an intentional bounded safety restriction.
- **Richer unrestricted natural-language mapping** onto the self-knowledge model
  (only bounded deterministic phrasings are claimed today).
- **Operational capability** (durable task state, leases, parallel work) — NOT YET
  JUSTIFIED.

## 12. Final status

**SELF-KNOWLEDGE FOUNDATION COMPLETE.** The model is deterministic-first,
Atlas-owned, model-independent, evidence-backed, queryable, bounded, reproducible
and fail-closed, and it cannot bypass authorization or execution boundaries.
