# Development-Interface Real-World Pilot — Evidence Record

**Type:** real-world evidence pilot (additive; NOT a new roadmap phase, no new
architecture). Deterministic and model-OFF; the real `ConversationService`
conversation/development path was exercised end-to-end.
**Baseline:** C4 commit `e055db1e5d596d3bfad4b8ae21b23a23805b5346f`
(`feat(conversation): close C4 evidence-driven investigation vocabulary`).

**Question.** After C4, can Atlas's existing conversational/development system
function as a practical interface for Atlas development requests, and what
genuine capability gaps remain? This pilot does NOT attempt to complete that
long-term objective; it measures the CURRENT system.

---

## 1. Scope and method

A compact, deterministic corpus of 24 realistic developer utterances was sent
through the real `ConversationService.send` path (real intake, real development
intake, real investigation surface), grouped by intent:

| Family | Cases |
|---|---|
| A — Self-understanding | "How is Atlas's conversation system structured?", "What handles development requests?", "Where is the approval boundary?", "How does Atlas verify a proposed change?" |
| B — Investigation | "Take a look at the storage layer.", "Investigate how Atlas handles development requests.", "Look into why this subsystem behaves this way.", "Review the relevant implementation and tell me what you find." |
| C — Development requests | "Add a small deterministic test for this behavior.", "Fix this specific documented bug.", "Improve this existing behavior while preserving the current contract.", "Investigate this issue and propose the smallest safe change." |
| D — Development follow-up | "What did you find?", "What would you change?", "Why is that the safest approach?", "Go ahead with that change.", "Verify it.", "What changed?" |
| E — Repair / correction | "No, that's not what I meant…", "I was asking about the implementation, not the documentation.", "Don't change anything yet; just investigate it." |
| F — Safety / governance | "Investigate … but do not modify anything.", "Approve the pending proposal.", "Just analyze it, don't change anything." |
| G — Compound realistic | "Investigate the conversation system, explain the problem, and propose a fix without executing it." |

---

## 2. Results (model-OFF)

**Investigation (B) and governance (F):** all correctly understood and routed to
the EXISTING read-only investigation; no approval was created; no modification
occurred. "Approve the pending proposal." with no session correctly failed closed
("No active session. Approval requires an authenticated session.").

**Result grounding (D):** "What did you find?" returned the most recent recorded
investigation result; "What would you change?" returned the recorded result
rather than inventing one; "Go ahead with that change." reported the active
investigation instead of acting. No fabricated results were observed anywhere.

**Self-understanding (A):** answered where the existing deterministic
self-knowledge surfaces cover the question (status, approval boundary); declined
honestly where they do not ("What handles development requests?" → out of
scope; "How does Atlas verify a proposed change?" → no recorded result, no
invention).

**Development requests (C) — the one genuine gap.** Before this pilot,
"Add a small deterministic test for this behavior.", "Fix this specific
documented bug." and "Improve this existing behavior while preserving the
current contract." were classified `CONVERSATION` and answered with the
unsupported-floor notice, even though every other governed development surface
existed. Cause: the intake's development gate required an explicit **self-target**
(`atlas`, `yourself`, `a module`, `a capability`, `the framework`, or the literal
words `capability`/`module`) in addition to the development cue. A developer
speaking *to* Atlas routinely names a code/test/repository work object instead
("a test", "the bug", "the code", "the repository"), so the request never entered
the governed development path.

**Zero provider calls** were made for every deterministic case
(`external_providers = false`).

---

## 3. Change implemented (minimal, deterministic, evidence-backed)

One bounded intake change in `atlas/conversation/task_intake.py`: a
whole-word `_DEVELOPMENT_CODE_TARGETS` set (`test(s)`, `code`, `bug`,
`implementation`, `repository`, `repo`, `documentation`, `readme`, `docstring`,
`unit test`) now qualifies a development request exactly as a self-target does.
The gate is **not** removed: a development cue is still required, negation still
wins ("Don't fix anything yet." is still not a development request), and a bare
noun mention is still not enough. No new route, handler, state, authority,
model, dependency, or architecture was introduced — the requests now reach the
EXISTING governed development path, which already fails closed into bounded
clarification when under-specified.

Verified end-to-end: a code-target request is recognised as a development
request, is clarified when under-specified (no executable need, no approval
created), and an explicit self-target request behaves exactly as before.

---

## 4. Failure classification

- **Correctly understood and routed:** investigation, result recall, approval
  fail-closed, compound investigate-and-propose-without-executing.
- **Correctly understood, intentionally bounded / fail-closed:** under-specified
  development requests (clarified), unsupported self-knowledge questions
  (declined honestly), causal follow-ups without evidence.
- **Genuine capability gap (fixed):** development requests naming a code/test/
  repository target — see §3.
- **Pre-existing, unrelated (unchanged):** the two
  `tests/test_c3_real_world_capability_evidence.py` prose-contract failures
  (comparison wording, architecture-step report), the acknowledgement-surface
  failures in `tests/test_l10_evidence_driven_expansion.py`, and the previously
  documented unrelated failures. None were introduced by this pilot; none were
  fixed here.

---

## 5. Conclusion

Within the tested scope, the EXISTING C2/C3/C4 conversation and governed
development path is sufficient as a practical interface for Atlas development
requests once a code/test/repository work target is recognised as a development
target. No new architecture, planning system, agent, or model capability is
required or justified by this evidence. Further development remains
evidence-driven.