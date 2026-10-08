# COMMAND 2 — ATLAS ARCHITECTURAL BACKBONE — EVIDENCE

Baseline commit: `01ba400b76fa651b2d3a7931c3bfc2cc67707114` (HEAD == origin/main, clean tree)

## 1. Scope actually implemented

Four bounded mechanisms, no new runtime dependency (stdlib only), no second
repository map, no second editor, no second authority:

| Item | Mechanism | Location |
| --- | --- | --- |
| A1 | bounded symbol/region graph on the EXISTING map | `atlas/research/repository_map.py` |
| A1 | ONE reusable bounded context builder | `atlas/evolution/context_builder.py` (new) |
| A2 | deterministic change guards | `atlas/evolution/change_guard.py` (new) |
| A3 | held-out author/repair boundary | `atlas/evolution/held_out_context.py` (new) |
| A4 | specialist `full_file \| structural` discriminator | `atlas/evolution/specialist_change_supplier.py` |
| A4 | structural activation via the EXISTING editor | `atlas/evolution/structural_editor.py` |

## 2. A1 — symbol/region repository graph

`SymbolInfo` gains (additively, all defaulted) `end_line`, `reference_sites`,
`callers`, `callees`. New frozen dataclasses `ReferenceSite`, `SymbolEdge`,
`SymbolRegion`. `RepositoryMap` gains `regions`, `edges` and the queries
`references_of`, `callers_of`, `callees_of`, `region_of`, `regions_for`.
`to_dict()` only ADDS keys (`region_count`, `symbol_edge_count`, `end_line`,
`reference_sites`, `callers`, `callees`).

Everything is derived from ONE deterministic scoped traversal per module
(`_scan_module`), which replaced the previous single `ast.walk` — name tallies
cover the whole tree exactly as before, and a call site is attributed ONLY to the
definition that lexically contains it.

Bounds (module-level constants): `MAX_REFERENCE_SITES_PER_SYMBOL=32`,
`MAX_EDGES_PER_SYMBOL=32`, `MAX_EDGES_TOTAL=40000`, `MAX_REGION_CHARS=2000`,
`MAX_REGION_TOTAL_CHARS=12_000_000`.

**Never guess**: a name resolves to an edge ONLY when exactly one repo-defined
symbol carries it. Ambiguous names produce NO edge in either direction (the
reverse caller index skips ambiguous callee names entirely).

Real-repository measurement (`F:\Project Atlas`, `RepositoryMapBuilder(".")`):

| | baseline `01ba400` | Command 2 |
| --- | --- | --- |
| modules | 1180 | **1180 (unchanged)** |
| symbols | 20000 | **20000 (unchanged)** |
| bounded regions | 0 | 18785 |
| unambiguous caller→callee edges | 0 | 20485 |
| build seconds | 7.96 | 9.97 (+25%) |

Real symbol probes (deterministic, bounded, repository-true):

```
region_of("atlas.research.repository_map.SymbolInfo")
  -> atlas.research.repository_map.SymbolInfo lines 249-288 (1554 chars)
callers_of("RepositoryMapBuilder")
  -> atlas.conversation.investigation.InvestigationService._repository_map, ...
callees_of("atlas.evolution.change_author_router.ChangeAuthorRouter")
  -> plan_change, DeterministicChangeSupplier, ScaffoldChangeSupplier, ...
references_of("SymbolInfo") -> [(atlas.research.repository_map, 360), (…, 393), ...]
region_of("nope.Nope") -> None     callers_of("nope.Nope") -> ()
```

## 3. A1 — bounded context builder (W2)

`build_repository_context(map, RepositoryContextRequest)` is pure, read-only,
deterministic, model-free and I/O-free. Fixed selection order: target region →
callers/callees → dependency-aware neighbours → repository-derived tests → the
EXISTING lexical module ranking as a **fallback only** (used when the declared
target cannot be resolved, never to override one that was declared). One hard
character budget; bounded rationale per inclusion; unknown/hostile input fails
closed to an empty unresolved context.

`context_sources()` gives the reusable `path -> source` form.

Reused from BOTH `model_assisted_supplier.py` (the target's region-first
selection is reported as bounded identity evidence, preserving the existing
whole-file `source_excerpt` source contract) and `development_repair.py` (the
corrective author's context).

## 4. A2 — change guards (W3)

`characterise_change(base=…, applied=…, target=…)` returns a bounded
`ChangeCharacterisation` (paths, out_of_target, per-file line delta, removed
definitions, signature changes, structurally_valid, bounded, ok, reasons). It
never raises and fails closed on: malformed input, unparseable before/after
content, an empty applied payload, more than `max_paths` paths, oversized
content, a removed top-level definition, a removed parameter from an existing
top-level definition, and a no-op.

Wired into `SelfDevelopmentLoop._run_iteration` **after application and before
pytest**. On refusal: `test_outcome="guard_failed"`, the characterisation is
attached to metadata, pytest is NOT executed, the recorded verification baseline
is cleared, and the change can never be promoted. `DevelopmentDiagnostic`
classifies it as an IMPLEMENTATION (authoring/change) defect with
`recoverable=True`; `transition_of()` reports `unknown`, so it is never
reinterpreted as `pass_to_fail` / `fail_to_fail`. Existing verification
attribution semantics are unchanged.

**Deliberate, justified deviation from the work order.** A pure NO-OP is refused
by `characterise_change` (contract kept, and unit-tested) but is NOT wired as a
hard stop in the loop: an existing, documented contract
(`tests/test_verification_attribution.py::TestBaselineProbe::test_a_passing_change_reports_a_pass_to_pass_transition`)
intentionally measures a no-op change and requires the loop to report the honest
`pass_to_pass` verdict. A no-op is not a SAFETY violation, and the existing
attribution already models it. The loop therefore records the characterisation
and continues. This was discovered by the coherent regression, not assumed.

## 5. A3 — held-out author/repair boundary (W4)

`VerificationExpectation` gains `held_out: bool = False` (in `to_dict()`), set to
True whenever the plan selects a non-empty bounded verification test set.

`held_out_context.py` provides `HeldOutBoundary`, `boundary_of`,
`held_out_paths`, `safe_context`, `safe_verification_tests`, `safe_metadata` and
`abstract_failure_category`. Removing a test file from a context mapping is NOT
sufficient: surviving values are redacted line-by-line against the held-out
SOURCES, so an assertion, a fixture or a traceback excerpt cannot leak through a
neighbouring file, a rationale or a failure message.

`development_repair.py` now:
* derives ONE boundary from the workload's verification tests;
* **removed** the previous injection of `baseline.test_files` content into the
  repair context (the actual leak);
* sends `verification_tests=()` — the held-out identities never cross;
* sends a bounded abstract failure CATEGORY (`assertion_failure`,
  `execution_error`, `timeout`, `change_refused`, `unknown`) instead;
* redacts the bounded failure summary;
* enforces the same boundary on the generic model author.

## 6. A4 — specialist discriminator + structural activation (W5/W6)

Payload forms (absent `change` = backward-compatible `full_file`; an unknown
value is refused fail-closed):

```json
{"files": {"path": "full content"}, "note": "..."}                       // full_file
{"change": "structural", "path": "…", "symbol": "…",
 "kind": "replace|insert_after|delete", "source": "…", "note": "…"}      // structural
```

Per-form allowed-field sets replace the single allow-list, so a structural field
on a full-file proposal (or vice versa) is refused. The structural form is
translated into the EXISTING `metadata["structural"]` convention and delegated to
`StructuralChangeSupplier` → `apply_structural_edits(...)`. No second editor, no
`search_replace` mode, no multi-file authoring. Additional refusals: unknown
kind, missing/oversized source, unresolvable symbol, unparseable result,
architecture-sensitive target prefix, out-of-target path, wrong capability.

`StructuralChangeSupplier` gained an optional explicit `base_source` per path, so
a REPAIR anchors its edit on the CURRENT failing content instead of the pristine
repository file. Default behaviour (on-disk source) is unchanged.

## 7. Invariants preserved

Model-independent core; specialist output untrusted; deterministic-first;
OWNER approval, sandbox verification and promotion boundaries unchanged;
provider-disabled behaviour still fail-closed; no automatic approval or
promotion; one repository map; one context builder; one structural editor; no new
kernel service; no new runtime dependency; no second source of truth.
`CodeChangeSet` safety semantics and verification attribution semantics are
untouched.

## 8. Tests

New focused suites (96 + reruns, all green):

| File | Focus |
| --- | --- |
| `tests/test_repository_symbol_graph.py` | sites, bounds, determinism, unambiguous vs ambiguous edges, regions, unknown symbols, real-repo stability |
| `tests/test_repository_context_builder.py` | selection order, budget, determinism, fallback + rationale, fail-closed |
| `tests/test_evolution_change_guard.py` | clean/out-of-target/removed-definition/parameter/no-op/parse/oversized/malformed, guard metadata, diagnostic + repairability |
| `tests/test_held_out_author_context.py` | held_out flag, no source/assertion/fixture leakage, redaction, safe metadata only, real repair seam |
| `tests/test_specialist_structural_authoring.py` | both forms, unknown change, delegation, byte preservation, all structural refusals, full-file compatibility |

Coherent regression (affected foundation): `test_repository_map`,
`test_repository_map_kernel`, `test_repository_symbols`, `test_repository_impact`,
`test_authoring_source_context`, `test_authoring_contract_test_projection`,
`test_repository_ranking_authoring_context`, `test_development_target_bridge`,
`test_development_change_plan`, `test_development_localization`,
`test_development_capability_step2`, `test_phase42_development_lifecycle`,
`test_verification_attribution`, `test_development_capability_self_model` →
**379 passed** after the two regressions below were fixed.

Two regressions were introduced by the first implementation pass and are
recorded honestly rather than reclassified:

1. `test_authoring_source_context.py::test_small_target_source_is_complete` —
   the first pass replaced the target module's whole-file excerpt with its symbol
   region. Fixed by keeping the excerpt and reporting the region selection as
   bounded identity evidence.
2. `test_verification_attribution.py::TestBaselineProbe::test_a_passing_change_reports_a_pass_to_pass_transition`
   — the guard hard-stopped an intentional no-op change. Fixed as described in
   section 4 (deviation reported).

**Pre-existing, separately classified (NOT Command 2):**
`tests/test_builtin_self_knowledge.py::TestKernelWiring::test_kernel_architecture_provider_is_cache_only`
(reproduced at pristine `f602faf`), the `TestRealKernel` "no resolvable … gap"
failures in `tests/test_evidence_governed_development.py` (reproduced at pristine
`fa6f775`), and `test_intake_contract[H7-0]` /
`test_development_need_confirmation_fails_closed`. None was modified, weakened or
reclassified. The real-model specialist suites
(`test_specialist_repair.py`, `test_specialist_governed_acceptance.py`) were
excluded from the timed regression run because they invoke local Ollama and made
the suite exceed the available wall clock; their provider-free paths are covered
by `test_specialist_change_supplier.py` and `test_specialist_development_author.py`.

## 9. Limitations

* The end-to-end structural probe through a REAL provider (`code.generate`) and
  the full specialist-seam regression were not executed within this command's
  wall clock. The structural path is demonstrated at the seam level (real
  repository files, real `apply_structural_edits`, real byte-preservation
  assertions) rather than through a live model.
* Regions beyond `MAX_REGION_TOTAL_CHARS` (allocated in deterministic
  `(module, qualified)` order) have no stored region and `region_of` returns
  `None`; this is a bound, not a guess.
* `MAX_SYMBOLS_TOTAL = 20000` already capped the map before Command 2; the
  Command 2 graph inherits that cap.
* A no-op change is characterised but not hard-stopped (section 4).
