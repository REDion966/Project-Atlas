# C4.1 — REAL-WORLD CAPABILITY-GAP ACQUISITION & VALIDATION — EVIDENCE REPORT

Milestone: C4.1 (Phase C — Evidence-Driven Evolution)
Classification: **evidence / capability-acquisition** (not an implementation milestone)

---

## 1. STATUS

**C4.1 — NO VALIDATED CAPABILITY GAP FOUND**

Real-world use of Atlas through its production conversational entrypoint
(failing external AI) surfaced **no genuine Atlas capability gap (category A)**.
The strongest real-world limitation found is a **category D — interface /
usability limitation** (an internal deterministic capability exists but is not
reachable from the user-facing path); the remaining probes are a
deterministic-reasoning limitation, a later-milestone capability (C6), and an
unsupported task. No defect was found. No capability gap was manufactured.

---

## 2. BASELINE

- Branch: `main`
- HEAD: `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2`
- Working tree (unchanged before and after this investigation):
  - Modified tracked (7, all pre-existing): `atlas/conversation/conversation_service.py`,
    `atlas/conversation/investigation.py`, `atlas/conversation/task_intake.py`,
    `atlas/evolution/development_cycle.py`, `atlas/kernel/atlas.py`,
    `tests/test_conversation_state.py`, `tests/test_investigation.py`.
  - Untracked (pre-existing): `mission_output.txt`, `test_results.log`,
    `test_results_p18.log`, `tests/test_c1_1_dependency_inversion.py`.
  - Untracked (C3.3, expected): `atlas/conversation/investigation_synthesis.py`,
    `tests/test_investigation_synthesis.py`.
  - Staged / deleted / renamed: none.
- Only new artifact produced by C4.1: this evidence report.

---

## 3. REAL-WORLD TASK

**Primary task (impact / reverse-dependency analysis).** A developer-partner
question a user would plausibly ask an engineering assistant:

> "If I change `atlas.conversation.conversation_state`, which other modules
> depend on it and what would be affected?"

Why it is realistic: Atlas presents itself as an intelligent partner that owns a
repository map and reasoning (`docs/ATLAS_VISION.md`; `atlas/research/repository_map.py`).
Impact analysis ("what changes if I touch X?") is a routine, bounded,
deterministic repository task a partner should answer without a language model.

Production entrypoint used: `Atlas.chat(...)` → `ConversationService.send(...)`
on the kernel-built conversation service (`atlas/kernel/atlas.py:3309-3323`,
`:3457`), with the external AI made unavailable via the existing failing-AI
mechanism (no model configured, installed, or invoked).

Supporting probes (same session): test-coverage comparison; conversational
memory set/recall; plan-from-goal. See §4.

---

## 4. OBSERVED BEHAVIOR

Sequence of real turns (production entrypoint, failing AI):

| # | User request | Classification | Observed result |
|---|---|---|---|
| 1 | "Investigate the conversation state subsystem." | `INVESTIGATION_REQUEST` | Read-only investigation report; `modification_status=NONE` |
| 2 | "Give me the final report" | `REPORT_REQUEST` | C3.3 investigation synthesis (`status="investigation"`, focus ranked, NONE) |
| 3 | **"If I change `atlas.conversation.conversation_state`, which other modules depend on it and what would be affected?"** | `QUESTION` | **No deterministic answer** — AI unavailable → `degraded_notice` ("External AI inference is currently unavailable…") |
| 4 | "Which has better test coverage — the conversation or evolution subsystem?" | `QUESTION` | AI unavailable → `degraded_notice` |
| 5 | "Please remember that this project's test command is `python -m pytest -q`." | `CONVERSATION` | AI unavailable → `degraded_notice` (nothing retained) |
| 6 | "What test command did I ask you to remember?" | `QUESTION` | AI unavailable → `degraded_notice` |
| 7 | "Give me a step-by-step plan to add a new capability handler to Atlas." | `DEVELOPMENT_REQUEST` | F9 preparation **failed closed** ("supplier: supplier produced no changes") |

Relevant state: `active_proposal_id` set after turn 1; `current_investigation`
set; `evolution_proposal_id` remained `null`; conversation history accumulated
(2 messages per turn). External AI calls: 4 (all failed → deterministic
fallback); the investigation/report turns required 0 model calls.

Key observation (turn 3): Atlas produced **no** impact analysis even though the
underlying deterministic capability exists in the repository.

---

## 5. EXPECTED CAPABILITY

For the primary task, a successful deterministic result requires Atlas to:

1. resolve the cited module against its existing repository map;
2. compute direct dependents and the transitive reverse-dependency closure;
3. present the result (dependents / impact set) conversationally with evidence.

This is deterministic graph reasoning over an existing structure — no language
model required.

---

## 6. REPRODUCTION

Environment: Windows, repository root `F:\Project Atlas`, isolated temp
evolution storage, external AI failing.

Procedure (read-only):

1. Start `Atlas()` and `atlas.start()` with a temp `SQLiteEvolutionStorage`.
2. Replace the conversation service's AI with a failing double
   (`conv._ai = FailingAI()`) — the existing unavailable-model mechanism.
3. `atlas.chat("If I change atlas.conversation.conversation_state, which other modules depend on it and what would be affected?")`.
4. Observe classification `QUESTION` and a `degraded_notice` fallback with no
   impact data.

A second execution reproduced the same essential result (no impact analysis;
`degraded_notice`; `error_context="No AI available"`). The limitation is
deterministic and reproducible.

Existing deterministic capability check (proves the algorithm exists):

- `python -c "from atlas.research.repository_map import RepositoryMapBuilder; m=RepositoryMapBuilder('.').build(); print(len(m.dependents_of('atlas.conversation.conversation_state')))"`
  returns a non-empty dependent set.

---

## 7. ARCHITECTURAL INVESTIGATION

- **Affected production path:** `ConversationService.send` (`atlas/conversation/conversation_service.py:340`) → router cascade → no handler for a repo-reasoning `QUESTION` → cognition + AI (`:492-576`) → deterministic fallback (`conversation_service.py:551`).
- **Existing capability (already present):**
  - `RepositoryMap.dependencies_of` — `atlas/research/repository_map.py:114`
  - `RepositoryMap.dependents_of` — `atlas/research/repository_map.py:119`
  - `RepositoryMap.impact_set` (transitive reverse closure) — `atlas/research/repository_map.py:123`
  - `RepositoryMapBuilder.build` — `atlas/research/repository_map.py:208`
- **Internal production use:** `atlas/evolution/development_planner.py:241` calls `impact_set(...)` for planning impact expansion. So the algorithm is production-wired internally.
- **Not surfaced conversationally:** `InvestigationService._trace_relationships` (`atlas/conversation/investigation.py:431`) emits only **outgoing** dependency findings via `dependencies_of` (`:454`); it never calls `dependents_of`/`impact_set`. No `INVESTIGATION`/`REPORT`/`QUESTION` handler exposes reverse dependencies.
- **Conclusion:** the existing architecture **already contains the ability** required by the primary task; the limitation is that this ability is not reachable through the user-facing deterministic path. Under the C4.1 taxonomy this is **not** a missing capability (category A) — it is an interface/usability (integration) limitation.

---

## 8. CLASSIFICATION

Primary category (for the strongest observed limitation):

**D — INTERFACE / USABILITY LIMITATION.**

Rationale: the required capability exists in the architecture
(`RepositoryMap.dependents_of`/`impact_set`) and is production-used
(`development_planner.py:241`); it is simply not surfaced through investigation/
report/conversation. Per C4.1 §11, a category-A gap requires proving the
architecture *cannot* satisfy the requirement — that proof fails here.

Per-task classification:

| Task | Category | Why not A |
|---|---|---|
| Impact / reverse-dependency (turn 3) | **D — interface/usability** | `impact_set`/`dependents_of` exist and are used internally |
| Test-coverage comparison (turn 4) | **E — deterministic-reasoning limitation** (also unsupported as posed) | No comparative analysis over multiple investigations; overlaps reasoning maturity |
| Conversational memory set/recall (turns 5–6) | **C6 milestone** (knowledge/learning maturity) | Memory/knowledge subsystems exist; conversational durable memory belongs to C6 |
| Plan-from-goal (turn 7) | **C — unsupported task** (fail-closed, honest) | Planning requires a prior investigation proposal by contract; no defect (fail-closed, no false success) |

No category **G — GENUINE DEFECT** was found: no observed behavior contradicted a
documented contract. In particular, turn 7's fail-closed refusal is the designed
behavior (`DevelopmentCycleController` fails closed when no bounded change is
supplied).

---

## 9. EVIDENCE

1. Turn-3 transcript: classification `QUESTION`; content = deterministic
   `degraded_notice`; metadata `degraded=true`, `model_available=false`,
   `fallback_type="degraded_notice"`, `error_context="No AI available"`; no
   impact data.
2. Existing capability: `repository_map.py:119` (`dependents_of`), `:123`
   (`impact_set`); production use at `development_planner.py:241`.
3. Investigation limitation: `investigation.py:431-468` uses only
   `dependencies_of` (`:454`) — outgoing edges only.
4. Routing: no deterministic handler for repo-reasoning `QUESTION`; the
   AI/fallback path is the only destination (`conversation_service.py:492-576`).
5. Model-independence: 4 AI calls attempted, all failed; all deterministic
   turns made 0 calls.
6. Reproducibility: repeated execution produced the same essential result.

---

## 10. PIPELINE-CONSUMABLE CANDIDATE

**Not produced.** A pipeline-consumable candidate is defined only when a genuine
category-A Atlas capability gap is validated (C4.1 §13). None was validated, so
no change surface / gap ID is asserted here.

For the record, the strongest finding (category D) would be expressible as a
bounded, deterministic integration improvement — *surface the existing
`RepositoryMap.dependents_of` / `impact_set` capability through the read-only
investigation/report path* — with an objective verification (a conversational
impact request returns the same dependent/impact set as `impact_set` computes,
with `modification_status="NONE"`). However, this is an **interface/usability**
improvement, not a category-A capability gap, and therefore is **not** a C4.1
validated gap and does not authorize C4.2 by itself.

---

## 11. FUTURE MILESTONE CLASSIFICATION

- Impact/reverse-dependency surfacing (turn 3): **C4-adjacent interface work** (category D), not a C4.1 validated gap.
- Test-coverage comparison (turn 4): deterministic-reasoning limitation; overlaps reasoning maturity.
- Conversational durable memory (turns 5–6): **C6 — Knowledge & Learning Maturity.**
- Reference resolution (GAP-C31-02): **C7 — Human Understanding** (remains deferred; not implemented).
- Self-knowledge / capability model: **C5.**
- Promotion/apply automation, code writer: **C8** (restricted/reserved) — not authorized.

---

## 12. VERIFICATION

- `python -m pytest tests/test_repository_map.py tests/test_repository_map_kernel.py tests/test_investigation_synthesis.py tests/test_conversation_service.py tests/test_governance_assurance_m5.py tests/test_reference_resolution.py -q`
  → **106 passed, 0 failed, 0 errors (exit 0)**, 46.7s.
- Earlier in this session (unchanged tree): governance/evolution verification
  set **175 passed, 1 skipped**; C3.3 focused **19**; mission regression **312**;
  broader group **153**; full suite **5814 passed, 0 failed, 0 errors, 2 skipped**.
- No failure was observed; nothing to classify. No defect found.

---

## 13. INTEGRITY

- No production code, test, configuration, governance, authorization, sandbox,
  or execution semantics were modified.
- Branch `main` and HEAD `f85de89` unchanged. No commit, push, reset, clean,
  stash, checkout, delete, or rename.
- `git status`, staged set, and `git diff --stat HEAD` are identical to baseline.
- The only new artifact is this evidence report. GAP-C31-01 was not reopened;
  GAP-C31-02 was not implemented; no C5–C9 capability was introduced; no roadmap
  document was modified.

---

## 14. FINAL VERDICT

**C4.1 — NO VALIDATED CAPABILITY GAP FOUND.** No genuine category-A Atlas
capability gap was established from real-world use: the strongest finding is a
category-D interface/usability limitation (existing deterministic impact
capability not surfaced), and the remaining findings are a deterministic-reasoning
limitation, a C6 capability, and an unsupported task. No defect was found.

**C4.2 is NOT authorized to be planned.** Per C4.1 §21, C4.2 becomes authorizable
only when a genuine, reproducible, bounded, objectively verifiable category-A
capability gap is validated — which did not occur here. If the project owner
wishes to treat the category-D finding (surfacing the existing
reverse-dependency/impact capability) as a C4 target, that requires an explicit
scope decision, since it is not a category-A capability gap under the C4.1
taxonomy.
