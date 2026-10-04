# The EFG (Entity-Field Graph) — architecture map

**What this is.** A faithful, current code+math map of the PegaSUS EFG — the compile-stage engine that
turns normalized DATASUS/SIDRA source events into a graph of typed analytical `FieldNode`s (the
"variables" the panel and LDO consume). Companion to [`ldo.md`](ldo.md) (the estimator that consumes the
EFG's output). Verify against the live code (CLAUDE.md §IX); this map is a point-in-time reference to
stop re-researching the module from source. Reconnoitered + consolidated 2026-07-12.

**One-line dataflow:** normalized source events → `SubstrateBundle` (SHE) → `build_efg`
(`dag/spine.py::_build_efg_base`, the metadata graph) → `execute_efg_result` (`executor/run.py`, the
value tensors) → `she.panel.CommonPanel` → LDO (`workflows/investigate.py::run_investigate`).

---


## 1. Overview & the field/node data model

**What the EFG is.** The Entity-Field Graph is the **compile-stage** engine that turns normalized DATASUS/SIDRA source events into a graph of typed analytical **`FieldNode`s** — the "variables" the panel and LDO consume. It sits between the SHE substrate and the analysis layer:

```
normalized source events (SIM/SIH/SINASC/CNES + SIDRA)
   → SubstrateBundle (SHE)
   → build_efg  [dag/spine.py::_build_efg_base]         metadata graph (V_fields + E_DAG)
   → execute_efg_result  [executor/run.py]              per-(year,municipality[,stratum]) value tensors
   → she.panel.CommonPanel                              (year,municipality)×variable panel
   → LDO (workflows/investigate.py::run_investigate)
```

The whole graph-construction layer is **pure metadata** — it manipulates field *descriptors*, not tensors. Numeric execution (COUNT/SUM/Ψ/RN kernels, streaming `group_by`) lives separately in `executor/kernels.py`. A `FieldNode` is thus first a typed metadata object; its `.path` to a materialized parquet is filled in later by the executor.

**`FieldNode`** (`core/schemas.py:95`, pydantic `extra=forbid`) is the atom. It is minted only through the thin factory `make_field_node` (`efg/node.py:10`), which does **no** legality or kind/aggregation-consistency validation of its own — it trusts the caller and simply constructs; all type-legality is enforced externally in `legality.py`. Fields:

- **`id`** — content-addressed, `= field_id_from_lineage(lineage)` (see below).
- **`kind`** — one of **9** `Literal`s: `extensive_measure` (additive counts), `intensive_density` (rates/ratios), `marked_functional` (Ψ of a per-record mark), `context_gradient`, `bridge_divergence`, `bridge_module`, `observer_proxy` (diagnostic/ICD observers), `latent_context`, `model_residual`.
- **`aggregation`** — one of **5** `Literal`s: `additive`, `weighted_mean`, `statistical_functional`, `compositional`, `non_aggregable`. (`node.py` will happily build an `extensive_measure` with `non_aggregable` — coherence is *only* checked in `legality.py`, so a direct caller can mint an inconsistent node.)
- **`carrier`** / **`unit`** — the semantic quantity and its unit; both registry-validated in legality (unit has a small hardcoded whitelist `{ICD10, rate, proportion, reais_hospital_services, reais_professional_services, reais_icu_services, reais_total_billing}` that bypasses the unit registry — a known drift smell).
- **`support`** (dict) — the σ/stratification/axis-bound descriptor (`restrict_predicate`, `stratify_icd`, `stratify_column`, `high_dimensional_bound`, `denom_fragility`, `measured_quantity_ref`, …) read by the executor at materialization time.
- **`axes`** (dict) — the 6 canonical analytical axes (geography, time, age, sex, race, diagnostic).
- **`role`** / **`source`** / **`provenance`** (lists), **`operator`** (str|None), **`warnings`**, **`path`** (str|None), **`dashboard_safe`** (bool|`'warning'`).

**`FieldState`** (`enums.py:25`) — the data-reliability verdict: `verified`, `fragile`, `forced_fragile`, `quarantined_descriptive`, `quarantined_nochildren`, `illegal_excluded`. **`MaterializationState`** (`enums.py:34`) — where the tensor stands: `unmaterialized`, `metadata_only`, `planned`, `materialized`, `cached`, `blocked`, `failed`, `quarantined`. Roots are minted `metadata_only` (path=None); `apply_operator` sets children `planned`; the executor promotes them to `materialized`.

**`Lineage` + content-addressed identity** (`efg/lineage.py`, `core/schemas.py:84`). Every node's identity is derived, not assigned. `make_lineage(*, parent_ids, operator_type, operator_params, registry_versions=None, source_manifest_hashes=None, code_version='0.1.0')` builds a `Lineage`; `lineage_hash(l) = content_hash(l.model_dump(json))`; `field_id_from_lineage` aliases `lineage_hash` and supplies `FieldNode.id`. So two fields with identical parents, operator, params, registry versions, source hashes and code version collapse to the **same id** — the graph is reproducible and deduplicable by construction. All three functions are WIRED-LIVE (16 call sites in `materialize.py` alone, plus `node.make_field_node` for *every* field). Edges are content-addressed the same way: `_edge` (`dag/helpers.py`) builds an `EFGEdge` with `edge_id = edge_{content_hash(payload)[:24]}`. This content-addressing is what makes `equivalence.precompress_fields` (signature-based dedup) and `_dedupe_edges` (canonical-map remap) sound — dedup is exact metadata equality, never numeric.

## 2. The operator grammar

The grammar is declared in `src/pegasus/efg/operators.py` as an `EFGOperator` str-enum (line 21) and a companion `OPERATOR_REGISTRY: dict[str, OperatorDefinition]` (line 54). Each `OperatorDefinition` (frozen dataclass, `operators.py:36`) fixes six facts about an operator — `name`, `arity: int | None`, `output_kind`, `output_aggregation`, `requires_alignment`, `description` — and `.spec(role, params)` projects it into the applied `OperatorSpec` (`declaration.py:8`, `extra=forbid`) that the spine actually instantiates. **The registry declares 12 operators; only 4 are ever applied on the live path.**

### 2.1 The 12 declared operators

| enum member | `.value` | arity | output_kind | output_aggregation | align? | status |
|---|---|---|---|---|---|---|
| `RAW_FIELD` | `raw_field` | 1 | observer_proxy | non_aggregable | no | declared-unimplemented |
| `OBSERVER_FIELD` | `observer_field` | 1 | observer_proxy | non_aggregable | no | declared-unimplemented |
| `DIAGNOSTIC_TOPOLOGY` | `diagnostic_topology` | 1 | observer_proxy | non_aggregable | no | declared-unimplemented |
| `COUNT_MEASURE` | `count_measure` | None | extensive_measure | additive | no | **LIVE** |
| `PSI_FUNCTIONAL` | `psi_functional` | None | marked_functional | statistical_functional | no | **LIVE** |
| `DENOMINATOR_LINK` | `denominator_link` | 2 | observer_proxy | non_aggregable | yes | edge-label only |
| `RN` | `RN` | 2 | intensive_density | weighted_mean | yes | **LIVE** |
| `DIVERGENCE` | `divergence_log_ratio` | 2 | bridge_divergence | non_aggregable | yes | **LIVE** |
| `PROJECT` | `pi_*` | 1 | extensive_measure | additive | no | orphaned-but-callable |
| `CLASSIFICATION_PROJECT` | `Pi_Clsf_to_Axis` | 1 | context_gradient | additive | no | declared-unimplemented |
| `BOUNDED_PROJECT` | `pi_bound_*` | 1 | extensive_measure | additive | no | orphaned-but-callable |
| `BRIDGE` | `Bridge` | None | bridge_module | non_aggregable | yes | declared-unimplemented |

Three tiers of reality sit behind this table. **Live** (COUNT_MEASURE, PSI_FUNCTIONAL, RN, DIVERGENCE): both instantiated by `dag/spine.py::_build_efg_base` and implemented as a branch in `apply_operator`. **Orphaned-but-callable** (PROJECT, BOUNDED_PROJECT): fully implemented in `apply_operator` (`operators.py:379`) and gated in `legality.py:259`, but the spine never mints an `OperatorSpec` with their names — so `BOUNDED_PROJECT`'s docstring claim of "Mandatory early marginalization of high-cardinality additive fields" is *not* enforced by any operator; high-cardinality control is instead a passive `support.high_dimensional_bound` declaration check in `legality._high_dimensional_axes_ok`. **Declared-unimplemented** (RAW_FIELD, OBSERVER_FIELD, DIAGNOSTIC_TOPOLOGY, CLASSIFICATION_PROJECT `Pi_Clsf_to_Axis`, BRIDGE): registry entries with no `apply_operator` branch — they fall through to `status='blocked'`, `'operator_execution_not_implemented'`. Root observer/diagnostic fields are minted directly by `materialize.py` via `make_field_node`, not through these operators. `DENOMINATOR_LINK` is a fourth case: a registry operator whose arity=2/requires_alignment=True definition is *never applied* — it exists only as the label on RN's second edge (`spine.py:205`).

### 2.2 `apply_operator` — the branching synthesizer

`apply_operator(*, operator, parents, delta, alignment=None, registries=None) -> tuple[OperatorResult, FieldNode|None]` (`operators.py:220`) is metadata-only: it touches no tensors, it synthesizes the *child* FieldNode's `support`/`axes`/`carrier`/`unit`/`aggregation`/`kind`/`role`. It fails fast if `not delta.legal` (`status='failed'`, carrying `delta.failed_branch_id`) or on `arity` mismatch (`'failed_operator_arity'`), then branches on `operator.name`:

- **COUNT_MEASURE** → `extensive_measure`, `unit='counts'`, `aggregation='additive'`. Layers σ restrictions into support: `restrict_predicate` (declarative predicate → derived carrier, adds `restricted_count` role), `stratify_icd` (adds an `icd_{level}` axis tagged `diagnostic_restriction`), and demographic `stratify_column` (sex/age/race). The **race** case is delicate: when `stratify_axis=='race'` *and* a `race_bridge_prior_path` is set, it stamps `axes['race']='self_declared_bridged'` and `axes['race_axis_type']='self_declared_bridged'` and adds the `race_bridge_posterior` role — so alignment later permits the rate against self-declared census population (§3.7.4).
- **PSI_FUNCTIONAL** → `marked_functional`, `aggregation='statistical_functional'`. Carries `functional` (mean/median) and `mark_column` into support (§3.10.4-6).
- **DIVERGENCE** → `bridge_divergence`, `unit='log_ratio'`, `aggregation='non_aggregable'`, carrier `f"{left.carrier}_vs_{right.carrier}"`. Stamps **`support['epsilon']=1e-9`** (the log-ratio smoothing constant), carries an optional integer `temporal_lag` (pairs left(t−k) with right(t), §2.11), and preserves the shared stratifier axes `icd_chapter/icd_block/curated_cause_group/sex/age_group/race`.
- **RN** → `intensive_density`, `aggregation='weighted_mean'`, carrier `f"{numerator.carrier}/{denominator.carrier}"`. It resolves `rule = ratio_rule(numerator, denominator, operator.role, registry_root=…)` and **raises `ValueError("legal RN operator has no matching ratio rule")`** if `rule is None`. Output `unit = rule.output_unit`, `role = [rule.role, "derived_ratio"]`. Axes are the numerator∩denominator intersection, then the numerator's stratifier axes are re-added (the population denominator is unstratified, so the intersection would wrongly drop the cause-specific/demographic axes that *define* the estimand).
- **PROJECT / BOUNDED_PROJECT** → drop the declared `drop_axes`, inherit the parent's `kind`/`unit`/`aggregation`, append the `projected` role.
- **anything else** → `status='blocked'`, `'operator_execution_not_implemented:{name}'`.

On success it builds a content-addressed `lineage = make_lineage(parent_ids=…, operator_type=operator.name, operator_params=…, code_version='slice19a')`, unions parent+delta+alignment warnings, adds the `efg_derived` provenance tag, and calls `make_field_node(... state='fragile' if warnings else 'verified', materialization_state='planned', dashboard_safe='warning' if warnings else False)`.

### 2.3 `ratio_rule` — registry-resolved, no hardcoded table

`ratio_rule(numerator, denominator, role=None, *, registry_root='config/registries') -> RatioRule | None` (`operators.py:134`) scans `clinical_ratio_specs` from `health/clinical_event_definitions.yaml`, matching on `numerator_carrier` + `denominator_carrier` + `numerator_unit` + `denominator.unit ∈ denominator_units` (+ optional `role`). It returns `None` when no registered ratio semantics exist — **the engine holds no hardcoded numerator→denominator map**. `RatioRule` (`operators.py:106`, frozen: `numerator_carrier, denominator_carrier, numerator_unit, denominator_units:tuple, role, output_unit`) is consumed both in `legality.evaluate_delta` (to *gate* the RN branch) and in `apply_operator` (to *build* the child's unit/carrier/role) — one resolution source, two call sites.

## 3. Legality, declaration & alignment

**What this covers.** The pure-metadata gate that decides whether a candidate operator may fire on two operands, before any tensor is touched. Three predicates run at the graph boundary in `dag/spine.py`'s inner `expand(operator, parents, alignment)` closure: `align_fields` (which produces the `AlignmentResult` fed into the next two), `evaluate_delta` (the central legality verdict, which internally calls `evaluate_declaration_compatibility` and `ratio_rule`), and — after a batch of fields is built — `precompress_fields` for signature dedup. All are metadata-only; numeric execution lives in `executor/kernels.py` (§ executor).

### 3.1 `evaluate_delta` — the 8-term legality product (`legality.py:163`)

`evaluate_delta(*, parents, operator, intent=None, registries=None, alignment=None) -> DeltaResult` is the central legality predicate. It initialises **8 independent delta terms to 1** and zeros any that fail; `legal = AND` over all eight:

```
legal = support ∧ axes ∧ carrier ∧ unit ∧ aggregation ∧ provenance ∧ quality ∧ declaration
```

- **support** — parents present, `alignment.ok`; COUNT_MEASURE/PSI single-carrier/single-artifact; RN both operands present.
- **axes** — dimensional legality incl. `_high_dimensional_axes_ok`: the high-dimensional SIDRA gate trips when `estimated_cells_raw > 49900` without a `support.high_dimensional_bound` (a *passive* declaration check — there is no live BOUNDED_PROJECT marginalization operator; see § wired-vs-orphaned).
- **carrier** — registry-known via `load_carrier_registry`, plus a `primary_event_carriers` gate for COUNT/PSI and a specialized-semantics gate.
- **unit** — `load_unit_registry` only (§X drift FIXED): the former hardcoded `_known_unit` whitelist that bypassed the registry is gone — its 7 units (ICD10, rate, proportion, the four reais_*) are now declared in `ontology/unit.yaml` (ICD10 had been stranded in a dead `entries:` block the loader never read), so `_known_unit` is a pure registry lookup and cannot drift.
- **aggregation** — `load_aggregation_registry`, plus PROJECT/RN additivity rules and a diagnostic-topology-not-additive rule.
- **provenance** — illegal / zero_variance / observer_rerouted / fixture gates.
- **quality** — `materialization_state` not in {blocked, failed}; `state` not in {illegal, quarantined_nochildren}.
- **declaration** — race-axis commensurability, delegated to `evaluate_declaration_compatibility` (below).

On any failure, `DeltaResult` (`schemas.py:294`) carries `legal=False`, the per-term `delta_*` ints, `failed_terms`, and `failed_branch_id = 'failed_' + content_hash(...)[:24]`; registry evidence tokens are attached. `make_failed_branch` (`legality.py:335`) adapts a rejected delta into a core-schema `FailedBranch`, with `failure_stage` inferred from `failed_terms` **prioritizing `'declaration'`**. Because the eight terms are equal-weight AND-gated, a single registry-lookup miss (unknown carrier/unit) hard-fails the whole branch into a `failed_branch` (counted as "illegal" in `legality_summary`) rather than surfacing a registry-coverage warning.

### 3.2 Declaration commensurability — race `Bridge_R` (`declaration.py:86`)

`evaluate_declaration_compatibility(*, numerator, denominator, operator, registries=None) -> DeclarationResult` is the **RN-only** race gate — the delicate case where an *administrative* race code must pass through `Bridge_R` before it can divide *self-declared* census population. It reads each operand's `_race_axis` and whether it `_race_metadata_required` (`declaration.py:37`, a substring token match on `race/raca/raça/cor_raca/cor/race_axis` over concatenated role+source+axes+support text). The **fail-closed matrix**:

| numerator race | denominator race | verdict |
|---|---|---|
| both `None`, one requires | — | fail `race_axis_declaration_unverifiable` |
| exactly one declares | — | fail `race_axis_metadata_missing_fail_closed` |
| equal axes | equal | **ok** |
| unequal, but `_bridge_applied(numerator)` | — | **ok** `race_axis_aligned_by_bridge` |
| unequal, no bridge | — | fail `race_axis_declaration_incommensurable` |

`_bridge_applied` is true when the numerator carries `Bridge_R` provenance/operator/role `race_bridge_posterior` **or** `axes.race_axis_type == self_declared_bridged`. **§X substring detector FIXED:** `_race_metadata_required` no longer blob-matches "race"/"cor" over concatenated text (which false-positived — `"race"⊂"trace"/"grace"`, `"cor"⊂"score"/"record"` — and missed differently-spelled fields); it now checks the DECLARED race axis (the canonical `race` axis key, `race_axis_type`/`race_axis`/`declaration_process`, or an exact race-role token), sound+complete because a race-stratified field always declares the race axis. `DeclarationResult` (`declaration.py:17`) = `ok, failed_terms, warnings, reason`.

### 3.3 Metadata alignment across 6 canonical axes (`align.py:88`)

`align_fields(*, left, right, operator, intent=None, geo_support=None, registries=None) -> AlignmentResult` compares two operands over **6 canonical axes: geography, time, age, sex, race, diagnostic**. It first canonicalizes surface spellings via `_canonical` (`align.py:31`, hardcoded: `birth_year/admission_year/annual → year`; `mun_residence_cod6/mun_facility_cod6/… → municipality_cod6` — the AD-1 canonical-axis concern, still string-matched inline rather than consulting one registry), then per-axis:

- **equal** → `exact`.
- **one-sided extra axis on an additive field** → `projectable` operation (marginalize).
- **geography mismatch** → hard failure requiring `geo_support_calculus`.
- **race** self-declared-vs-self-declared → `stratified_join` (Bridge_R posterior over census population); a race mismatch is otherwise a hard failure requiring `Bridge_R`.
- **age / sex** → `demographic_stratified_join` (executor matches canonical category codes).
- **diagnostic** topology mismatch → hard failure.

`ok = no failures`. `AlignmentResult` (`schemas.py:282`) returns `aligned_left_id/aligned_right_id, operations_applied, support_after_alignment:dict|None, warnings, failure_reason`; `support_after_alignment` is the descriptor consumed downstream by `apply_operator`/RN. This result is what feeds `evaluate_delta` (its `.ok` gates the support/axes terms).

### 3.4 Equivalence dedup + protection barriers (`equivalence.py:231`)

`precompress_fields(fields) -> (tuple[FieldNode,...], PrecompressionReport)` is **proof-carrying metadata dedup**, run twice on the live spine (once over roots, once over the final graph). For each field it computes `equivalence_signature` (`equivalence.py:226`) = `(kind, content_hash(_stable(_signature_payload)))` across **8 signature kinds**: `exact_projection_redundancy, shared_denominator_identity, nested_icd_exact_identity, compositional_closure_identity, cost_component_exact_identity, capacity_vector_exact_identity, same_field_semantics, identical_field_id`. A field is suppressed **iff** a prior field shares the signature **AND** `_protection()` raises no barrier — distinct **cost-components**, **capacity-indices**, and **diagnostic-topologies** are explicitly protected from collapse. Dedup is **exact metadata equality, never numeric**. The report emits `SuppressedEquivalent` + `ProtectedNonEquivalence` manifests (`equivalence.py:12/27`) plus a `canonical_by_field_id` map the spine uses to also dedup edges.

## 4. The executor & kernel math

Everything above is pure metadata. The **executor** (`efg/executor/{run,kernels,support}.py`) is the
EFG's numeric heart: given the graph of typed `FieldNode`s, it materializes each field to a
per-`(year, municipality_cod6[, stratum])` `value` parquet tensor (column `VALUE_COLUMN="value"`) that
the panel + LDO consume.

**The fixed-point driver.** The sole production entry is `execute_efg_result(efg, *, output_dir,
require_materialized=True, intent=None)` (`run.py:87`), called live at exactly one non-test site —
`compile_attach.py:593`. It sets a run-scoped `_GEO_SCOPE_PREFIXES: ContextVar` from the intent (so only
the intent's UF prefixes are kept — this fixed the "AL run polluted by national municipalities" bug),
then runs `_execute_efg_result_impl` (`run.py:104`), a **fixed-point loop** over a `pending` set for up
to `len(fields)+1` passes. Source/scalar/count/sum/functional/SIDRA fields materialize in pass 1; **RN
ratios and cross-source bridges stay pending across passes** until their parent tensors exist (an
intentional topological relaxation — there is no explicit topo-sort; per-field `last_error` is retained
so a permanently-blocked field reports the real cause, not a generic `parents_not_materialized`). The
loop terminates when `pending` is empty or a pass makes no progress; `require_materialized` then raises
listing any blocked fields (ends the "hollow success" regime). Output: a rebuilt `EFGResult` (fields
promoted to `materialized`) + an `EFGExecutionReport` (`.as_manifest()` → `efg_execution_manifest.json`).

**Streaming is a hard requirement.** National SIM/SIH ≈ 1e8 rows, so **every** count/sum/functional
kernel terminates in a streaming `group_by(...).agg(...)` whose peak RAM is `O(output cells)`, not
`O(events)`. A shared `SourceScanCache` (`{resolved_path: pl.LazyFrame}`) lets the *N* fields off one
events parquet reuse a single lazy scan-plan. `_source_field_tensor` deliberately does the cell-mean
reduction *inside* the group_by (not a per-event projection) to avoid materializing the national source
(AD-2); `_population_solver_tensor` projects 4–5 of 17 columns and streams (was a ~21 GB eager OOM).

**Dispatch table** (`run.py:126-152`), per field, by `operator`/`kind`:

| condition | kernel | math |
|---|---|---|
| `op=='RN'` or `kind=='intensive_density'` | `_compute_rn_ratio` | `value = numerator/denominator` (denom>0 else null) |
| `op=='psi_functional'` | `_functional_tensor` | `Ψ = mean\|median(__mark__)` per cell (MSD §3.10.4-6) |
| `op=='population_tensor_solver'` | `_population_solver_tensor` | marginal pop = Σ over demographic axes except `keep_axis` |
| `op.startswith('Bridge')` / `kind∈{bridge_module,bridge_divergence}` | `_compute_bridge_tensor` | race posterior / log-ratio divergence |
| `op` in `sidra_*` | `_sidra_{population,context,demographic_population}_tensor` | SIDRA anchors/gradients |
| else | `_execute_non_rn` → `_count_tensor` \| `_sum_tensor` \| `_source_field_tensor` \| `_scalar_tensor` | COUNT/SUM/raw |

**The count kernel (`_count_tensor` → `_finalize_count`).** The COUNT_MEASURE σ_C kernel: build the
support frame (`year`+`cod6`), apply the σ `restrict_conditions` predicate, optional ICD stratification
(adds an `icd_chapter`/`icd_block`/`curated_cause_group` axis), optional demographic stratification (age
by arithmetic bucketing to an `age_N` basis; **race via the `Bridge_R` posterior redistribution** or raw
admin code when no prior; sex via a `source_category_map` crosswalk), then `group_by(support_keys +
stratum axes).len()`. `TOTAL`/`UNKNOWN` age strata are dropped so counts partition the event population
exactly; ICD codes outside the registry map to an explicit `UNCLASSIFIED` stratum (not dropped).

**The rate kernel (`_compute_rn_ratio`).** The Radon–Nikodym rate: load numerator (`parent_ids[0]`) and
denominator (`parent_ids[1]`) tensors, join on **intersecting** support keys (a cross-join is *refused* —
prevents OOM / mis-aligned Δ), run the ecological-fallacy guard (aggregate a finer cod6 numerator up to a
coarser denominator's support), preserve numerator-only stratifier columns, compute
`value = numerator/denominator` (null when `denominator ≤ 0`), propagate
`denom_fragility = min(1, parent_fragility + missing_denom_rows/total_rows)`, and write **both** the rate
parquet **and** a `MeasuredQuantity` count+exposure sidecar (§7).

**The O7 extensive/intensive gate** (`kernels.py:419-430`, the denominator principle, MSD §I.2/§III.5).
The count-with-exposure (Poisson-offset) margin is valid *only* for an **extensive count** numerator
(deaths/births/hospitalizations); an intensive numerator (rate÷rate, density) must enter the LDO on the
plain rank-PIT margin. So `_compute_rn_ratio` advertises `support['measured_quantity_ref']` **only when
`numerator.kind == 'extensive_measure'`** — but *always* writes the sidecar as provenance, and always
sets `offset_semantics='log_exposure'`, `n_events=num_total`, `n_denom=den_total`. This gate is live
end-to-end: `kernels.py` → `investigate.py:302` `measured_quantity_refs` → LDO
`orchestrator.py` (pinned by `test_ldo_extensive_gate.py`). **Flag:** the gate keys on
`getattr(numerator,'kind','')`; if a genuine count numerator ever reaches it with `kind==''`, the gate
*silently* withholds `measured_quantity_ref` and the LDO falls back to rank-PIT with no warning — worth a
log (contrast the AMC path, which loudly warns on degrade).

**Support canonicalization (`support.py`).** `_support_frame_lazy` → `_with_year_lazy` + `_with_geo_lazy`
put source events on the panel lattice via the **registry-driven axis resolver** (AD-1, no hardcoded
name lists): the temporal column (SIM `year` / SIH `admission_year` / SINASC `birth_year`) →
`year` via `resolve_axis_column`; geography → `municipality_cod6` (6-digit extract, residence-preferred;
UF-total pseudo-municipalities `^\d{2}0000$` dropped); the `_GEO_SCOPE_PREFIXES` filter; optional IBGE
region coarsening with an authoritative crosswalk (unmapped → null, never mislabelled).
`_restrict_conditions_expr` is the σ predicate interpreter — the *only* place the declarative AND-list
from `health/clinical_event_definitions.yaml` is realized (`lt/le/gt/ge`, `eq/ne/in/not_in`,
`starts_with_any` ICD-prefix, `is_true/is_false` pt-BR truthy, `is_not_null`); a referenced-but-absent
column returns `False` → empty frame (unsatisfiable), never a silent no-op.

**`diagnostic_strata.py`** is a metadata-only **planner** wired into `dag/spine.py` (not the executor):
`requested_icd_levels`/`diagnostic_columns_by_event` (`spine.py:240`) plan which σ_C ICD strata to build;
`enforce_health_seeds` (`spine.py:602`) is the intent-contract gate (`HealthSeedContractError` on an
unsatisfied `health_seed`). **Flag (mitigated §V):** `seed_satisfaction` still treats an *unrecognized*
seed token as satisfied (to not break genuinely-new seeds), but it now emits a `RuntimeWarning` naming the
unverified seed + the known set, so a typo'd seed no longer *silently* passes the contract gate.

## 5. Q-tensor, state & uncertainty

**What this covers.** How the EFG scores per-field data reliability (the MSD §3.12 **Q-tensor**), classifies each field's `FieldState`, records rejected operator expansions, binds the graph's seed fields, and — decisively — how that uncertainty is propagated into the LDO observation weight **W**. Four modules with distinct roles and distinct wiring status: `efg/q_tensor.py` (the §3.12 mathematics), `efg/core_seed.py` + `efg/core_seed_registry.py` (two different "seed" abstractions), `efg/failed_branch.py` (audit records).

### 5.1 The reliability mathematics (`q_tensor.py`)

The §3.12 primitives, each a small pure function:

| function | math | wired? |
|---|---|---|
| `_kish_effective_n(weights)` | `n_eff = (Σ|w|)² / Σ|w|²`; `None` when `Σw²≤0`; = cell count under equal weights | **live** |
| `_moran_corrected_n_eff(base_n, moran_i)` | `n_eff = max(1, base_n · 1/(1+max(0,MoranI)))`; non-positive autocorrelation is a no-op | **live** |
| `provenance_risk(provenance)` | ordered ladder, first hit wins: `synthetic→1.0`, `latent→0.8`, `SIM_informed_denominator_prior`/`facility_linkage_filtered→0.5`, `reconstructed`/`geneallocated→0.4`, `classification_projected`/`longitudinally_stitched→0.3`, `harmonized`/`deflated`/`AMC_contracted→0.2`, else `0.0` | **live** |
| `default_denom_fragility(field, support)` | recorded `support['denom_fragility']` wins; else `n_denom` present→`0.0`; else bare count (`_is_count_field`)→`0.0`; else rate with absent denom→`1.0` (§3.12.8 no-denominator convention) | **live** |
| `_second_diff_roughness(values)` | `√mean((x_t−2x_{t-1}+x_{t-2})²)/|mean|`; zero on any straight line | **live** |
| `_denom_fragility_share(denom,μ_min=50)` / `_sampling_cv(values,denom)` | `mean(μ_den<50)`; rate `√(ΣC)/Σexp ÷ (ΣC/Σexp)`, count `1/√(ΣY)` (Poisson SE/est) | gated behind `spec_reliability=True` (default **False**) — **dormant** |

**The verdict — `classify_q_state(*, n_eff, denom_fragility, missingness, risk) → FieldState`.** The canonical reliability classifier (None-inputs coerced to worst case `n_eff=0, fragility=1, missingness=1`):

```
verified  iff n_eff≥100 AND denom_fragility<0.05 AND missingness<0.10 AND risk<0.5
else fragile iff n_eff≥30 AND denom_fragility<0.20
else quarantined_descriptive
```

It **never emits `FieldState.forced_fragile`** — that enum member (`enums.py:28`) is unreachable from this producer; `forced_fragile` is set elsewhere (declaration-time). `FieldState` (`enums.py:25`) spans `{verified, fragile, forced_fragile, quarantined_descriptive, quarantined_nochildren, illegal_excluded}`.

### 5.2 The live producer vs the orphaned one

There are **two Q-tensor assemblers, and the packaged one is dead.** `compute_q_state(...) → QState` (`q_tensor.py`) is the *declared* canonical producer, and `QState` (`core/schemas.py:209`) the declared model — but both have **zero `src/` callers** (only `tests/contract` + `tests/unit`). The live compile path instead re-implements the assembly inline: `compile_attach._q_row` (called from `attach_autonomous_efg_to_run` during the executor→Q-tensor bridge) imports the **primitives directly** (`classify_q_state`, `default_denom_fragility`, `provenance_risk`, `_kish_effective_n`, `_moran_corrected_n_eff`, `_second_diff_roughness`) and rebuilds the diagnostics in `_vector_diagnostics`. `_q_row` computes `n_eff` via Kish then Moran deflation over a **real** structural queen-contiguity graph (`structural_cod6_adjacency`), then `state = classify_q_state(n_eff, default_denom_fragility, missingness, provenance_risk)` when a materialized vector exists, else falls back to the declared `field.state`. This is the fix that de-orphaned `classify_q_state` (task EFG-QT). The orphaned `compute_q_state` uses a chain-contiguity Moran *proxy* (`_moran_contiguity`, IBGE-code sort order) when no `spatial_graph` is passed — inferior, but latent since it never runs live.

> **Flag — duplicated producer (EFG-11/GDM-09).** `compile_attach` carries its own copies of Moran/entropy/CV; `q_tensor`'s `_moran_contiguity`/`_spatial_entropy`/`_cv`/`_temporal_roughness` are reachable only through orphaned `compute_q_state`. Two implementations that can silently diverge.
>
> **Flag — column vs classifier divergence (FIXED 65593b5).** `_q_row` used to write the Q-tensor `denom_fragility` **column** as raw `support.get('denom_fragility')` (often `None`) while the **state** verdict used `default_denom_fragility(field, support)` (0/1) — and the LDO reliability weight reads that column, so a field's state and its LDO down-weight disagreed. The column now serializes `denom_fragility_val` (the classifier's value), so they agree.

### 5.3 Uncertainty → LDO weight W (`investigate.state_reliability_weights`)

`state_reliability_weights(run_dir, keep_variables, *, spec_reliability=False) → dict[field_id, float]` is **the live uncertainty→W bridge** (`investigate.py:336`). It reads back `Q_tensor.parquet` and folds the diagnostics into a per-field reliability, passed to `run_ldo`/`run_ldo_multiresolution` as `field_weights` (the LDO precision fit then down-weights uncertain fields):

```
kish = n_eff / base           base = n_denom (spec) else n_events
rel  = kish · (1 − min(frag,1)) · (1 − min(prov,1))
if race_bridge_cv > 0:  rel ·= 1/(1+cv)
rel  = clamp(rel, 0.1, 1.0)
```

> **Flag — questionable magnitude divide (FIXED).** `n_eff` (an effective **cell** count) was divided by `base = n_events` (the event TOTAL, ~millions) — a dimensionally inconsistent ratio that floored every high-volume field to 0.1, systematically over-downweighting the best-powered variables. Fixed: `_vector_diagnostics` now surfaces `n_obs` (observed-cell count) into the Q-tensor, and the weight is the Kish efficiency `kish = n_eff/n_obs ∈ (0,1]`; legacy Q-tensors without `n_obs` fall back to `kish=1` (no deflation) rather than reintroduce the bug (`test_reliability_weight_dimensional`).

### 5.4 Core seeds — two abstractions, same name

- **`core_seed.py` — heuristic role tagging.** `build_core_seed_set(fields, *, registry_root, intent) → CoreSeedSet` (+ `core_seed_summary`) tags **every** field with a seed role via `_seed_role` substring-blob matching over `id/name/kind/carrier/unit/role/source` (e.g. `'bed'|'capacity'→facility_capacity_seed`). Metadata-only, wired at `spine.py:587` and re-consumed by `bridges.plan_bridge_candidates`. **The `intent` arg is discarded** (`del intent`) — intent-scoped seeding is a no-op here.
- **`core_seed_registry.py` — canonical-id binding + contract.** A *distinct* abstraction: `resolve_core_seeds(fields)` binds canonical MSD seed ids (`V_C01`, `SIMDeathsAll`, …) to produced content-addressed fields via a declarative predicate (`fields/core_seed_registry.yaml`); `enforce_mandatory_fields(intent, fields)` **raises `MandatoryFieldContractError`** to refuse a hollow compile success (wired `spine.py:606-609`), with a `core_vital` escape hatch (`CORE_VITAL_PRECONDITION_TOKENS`) downgrading to `blocked_preconditions` instead of raising.

> **Flag.** These two share no code and answer different questions (role-tag-all vs canonical-id-bind + enforce) yet are both named "core seed" — easily conflated. `_seed_role`'s name-matching is the §X recognition smell; `seed_satisfaction` (in `diagnostic_strata.py`) still treats an *unrecognized* health-seed token as `satisfied=True` but now WARNS (§V mitigated), so a typo'd seed no longer silently passes the contract.

### 5.5 Failed branches (`failed_branch.py`)

`make_failed_branch_record(*, parents, operator, reason, delta=None, alignment=None, disposition='illegal', warnings=None) → FailedBranchRecord` produces a content-hash-identified, auditable record of a rejected operator expansion or substrate exclusion, `disposition ∈ {blocked, illegal, unsupported, deferred}`. **Heavily wired** in `spine._build_efg_base.expand()` — emitted on budget-exhausted, illegal-delta, and blocked-apply — plus `failed_exclusion(...)` for materialize-time exclusions (`spine.py:128,139,158,167,185,519,552`). All flow to `EFGResult.failed_branches → compile_attach._failed_row →` the `FailedBranches` output table, so a rejected branch is never silently dropped — it is surfaced as a typed row with its failure stage.

## 6. The measured-quantity seam to the LDO

This is the seam that lets the LDO model a normalized quantity as **count + exposure** (a Poisson log-offset, MSD-III §II.3 / §III.5) instead of a pre-divided rate. It crosses the EFG→LDO boundary as a 5-hop chain; only one file (`bridges.py`) *produces* the RN fields that create the sidecar, and — despite the slice name — `compile_attach` is **not** a measured-quantity consumer (it is a pass-through carrier; its real work is the Q-tensor diagnostics of §5). The consuming half lives one stage later in `investigate.py` + `ldo/assemble.py`; see [`ldo.md`](ldo.md) for the count|exposure margin on the LDO side.

### The sidecar object

`MeasuredQuantity` (`efg/measured_quantity.py`) is a frozen dataclass `{table: pl.DataFrame, offset_semantics: str, structure: dict, provenance: dict, uncertainty: dict}`. Properties `numerator_count` / `exposure` return the two columns; `implied_rate()` is a **display-only** derived view (`when(exposure>0) then numerator_count/exposure else None`) with no caller repo-wide. The table carries the raw count and exposure **verbatim, deliberately not their ratio** — preserving count variance and the offset.

- `measured_quantity_from_rn_join(joined, *, keys, strata, field_id, provenance=None, denom_fragility=0.0, axes=None, numerator_col='value_numerator', exposure_col='value_denominator') -> MeasuredQuantity` selects the structure cols + numerator/exposure aliased to the module constants `NUMERATOR_COLUMN` / `EXPOSURE_COLUMN`. No numeric transform.
- `write_measured_quantity(mq, path) -> Path` persists **only `mq.table`**. `offset_semantics='log_exposure'`, `structure`, `provenance`, and `uncertainty` (including the computed `denom_fragility`) die at the disk boundary — no consumer reads them, and the LDO reconstructs a *different* fragility from exposure magnitude.

### Producer and the count|exposure gate

`bridges.plan_bridge_candidates(fields, *, registry_root, intent) -> BridgePlan` (live at `spine.py:498`, metadata-only) cross-products core seeds into `death×population` / `birth×population` / `admission×(population|capacity)` / `cost×admission` RN candidates (`required_operator='ratio'`). `spine.py` turns each into an RN `OperatorSpec`.

The live RN producer `_compute_rn_ratio` / `_rn` (`executor/kernels.py:383-430`) joins numerator⋈denominator on shared keys (cross-join forbidden), writes `{field.id}.parquet` (the rate — the derived view), then `write_measured_quantity` emits the sidecar `{field.id}.measured_quantity.parquet`. It returns a `result` dict advertising `measured_quantity_ref` **only when `numerator.kind == 'extensive_measure'`** — the O7 / §I.2 denominator-principle gate (`kernels.py:419-430`): an extensive count (deaths/births/hospitalizations) may carry a Poisson offset; an intensive rate÷rate must enter the LDO on the plain rank-PIT margin. The sidecar is written **either way** as provenance; only the ref is suppressed for intensive fields. The result also sets `offset_semantics='log_exposure'`, `n_events=num_total`, `n_denom=den_total`, `measured_quantity_extensive=bool`.

### Wiring onto the panel

`executor/run.py` (lines ~129-155) merges that `result` dict into `field.support`, so `measured_quantity_ref` rides through into `V_fields.support_json` when `compile_attach.attach_autonomous_efg_to_run` serializes fields via `_v_row` — a pure pass-through, no reading or modeling.

At the investigate stage, `measured_quantity_refs(run_dir, keep_variables=None) -> dict[str,str]` (`workflows/investigate.py`) reads `V_fields.parquet` back and resolves `{field_id: sidecar_path}` from the `measured_quantity_ref` column / support_json, feeding `run_ldo` as `measured_quantity_by_variable`.

**The 524ea00 fix.** `FieldNode.path` and the stored ref are absolute paths into the transient `{run}__efg_stage_workspace/`, which compile rmtree's after flush — dead on a completed run. `measured_quantity_refs` now re-resolves the sidecar **basename** against `run_dir/Tables/efg_tensors/<basename>` (investigate.py:171-177). Without it the resolver returned `{}` on **every real national run**, and every count silently fell back to plain rank-PIT — leaking log-population into the residual scan as a co-scaling near-clique (count ~0.9-corr with log-population). This is the same path-staleness class already fixed for field tensors in bfd4744 (CLAUDE.md §X recurring-patch smell); the two basename re-resolutions now exist independently, with no shared final-tensor-dir resolver.

Finally `ldo/assemble._load_measured_quantity_tensors(sidecar_path, *, time_col, s_index, t_index, shape) -> (count(S,T), exposure(S,T))` group-sums `numerator_count`/`exposure` to `(municipality_cod6, time)`, scatters onto the `(S,T)` grid, sets `X[vi]=count` (the raw count **replaces** the rate) and `exposure[vi]=exp`, and ramps observation weights down for low-exposure cells (`frag = clip(exposure/denominator_min, 0, 1)`, Poisson CV ∝ 1/√exposure). The orchestrator counters `count_exposure_variables` / `n_exposure_margins` (`ldo/orchestrator.py:619-631`, threaded from `investigate.py:302` → `orchestrator.py:627`) confirm the margin fired.

### Flags

- **Silent-degrade (§V):** if the ref is absent and the basename is not under `Tables/efg_tensors`, `measured_quantity_refs` returns `{}` with **no warning**; counts Gaussianize by plain rank and the counters read 0, but nothing raises.
- **Cause-stratified sidecar:** `_load_measured_quantity_tensors` groups only by `(municipality_cod6, time)` — it does **not** group by ICD strata, so a σ_C-restricted sidecar would sum across causes into one `(S,T)` count. The margin is safe only for unstratified count numerators.
- **Extensive gate fragility (mitigated d787dbe):** the gate is a single `numerator.kind == 'extensive_measure'` string compare with no cross-check against unit. It no longer degrades *silently*: every withhold now records a `measured_quantity_withheld_reason` in `result` (`intensive_numerator` / `non_count_numerator:<kind>` / `undetermined_numerator_kind:*`), and a numerator with an unresolved (empty) kind emits a `RuntimeWarning` rather than masquerading as a deliberate intensive routing. A *mistyped-but-declared* count (e.g. a count wrongly tagged `intensive_density`) is still suppressed without a unit cross-check — that failure mode remains.

## 7. Materialization, lineage, DAG spine, wired-vs-orphaned & gaps

**Three files named `materialize*`, none writes a tensor.** `materialize.py` is *metadata-only* (`FieldNode`s with `materialization_state='metadata_only'`, `path=None`); `materialization_manifest.py` writes a JSON *admission-plan* audit artifact; the physical tensor write lives in `executor.execute_efg_result`, invoked from `compile_attach.py`. A reader chasing "where are field tensors materialized" is misled by all three.

### 7.1 The DAG spine — `dag/spine.py::_build_efg_base` (alias `build_efg`)

The autonomous EFG compiler core (WIRED-LIVE, `efg_build` stage, `compile.py:689`).
Signature: `_build_efg_base(*, substrate, registry_root='config/registries', intent, registries, compute, intent_constraints, operator_budget=256, operator_mode='standard') -> EFGResult`.

Sequence:
1. `materialize_substrate_bundle(substrate)` → root `FieldNode`s.
2. `precompress_fields(roots)` (equivalence classes).
3. Inner `expand(operator, parents, alignment)` closure — the single operator-application gate: `legality['attempted']++` → budget guard (`expansions>=256` appends an `operator_budget_exhausted` `FailedBranchRecord`, returns `None`) → `evaluate_delta` → if legal `apply_operator` → append child + `helpers._edge`(s). RN with 2 parents emits a numerator edge + a `DENOMINATOR_LINK` edge; else one edge per parent. Expansion order: event `COUNT_MEASURE` → ICD σ_C strata → demographic strata → σ-restricted clinical events → Ψ functionals → RN ratios (paired by `(denominator_carrier, numerator demographic-axis signature)`, so the join is O(numerators×specs×matching-denoms), not quadratic) → divergence bridges → `plan_bridge_candidates` bridges → `_append_race_bridge_fields`.
4. `precompress_fields(final)` again; `helpers._dedupe_edges(edges, canonical)`.
5. `resolve_core_seeds` / `enforce_mandatory_fields` / `enforce_health_seeds` — bind canonical `V_*` seed ids, **fail loudly** on unrealized `intent.mandatory_fields` / `health_seeds`.
6. Return immutable `EFGResult` (fields, edges, failed_branches, precompression, legality_summary, core_seed_summary, bridge_plan_summary, domain_summaries). `efg_id = content_hash(payload)[:24]`.

### 7.2 Materialization roots — `materialize.py`

`materialize_substrate_bundle(bundle) -> SubstrateMaterializationResult` maps each `SubstrateFieldCandidate` to a metadata-only `FieldNode` plus synthetic denominator/context fields: SIDRA 9606 population anchor, SIDRA context (socioeconomic) fields, SIDRA demographic population strata (suppressed if a solver tensor exists), one population-solver denominator per demographic marginal (in `{None, *demographic_axes}` because RN pairing needs equal numerator/denominator axis signatures), and CNES-ST facility stock. `state='fragile'` if warnings or `missing_rate>0.5` else `'verified'`; `sim_informed` denominator forced `'forced_fragile'`. `classify_substrate_candidate_kind` deterministically tags the 9 `FieldNode` kinds from unit/aggregation/role (diagnostic→`observer_proxy`, additive+count→`extensive_measure`, weighted_mean→`intensive_density`, …). `materialization_id = efg_materialization_{content_hash[:20]}`.

### 7.3 Lineage / edges — `lineage.py` + `dag/helpers.py`

`make_lineage(*, parent_ids, operator_type, operator_params, registry_versions, source_manifest_hashes, code_version='0.1.0') -> Lineage`; `lineage_hash = content_hash(model_dump(json))`; `field_id_from_lineage` aliases it and **is** the content-addressed `FieldNode.id` (used in `node.make_field_node`). All three WIRED-LIVE (16 call sites in `materialize.py` alone). `_edge` builds a content-addressed `EFGEdge` (`edge_id=edge_{content_hash(payload)[:24]}`); `_dedupe_edges` remaps through the precompression `canonical` map, drops self-loops, keys uniqueness on `(parent,child,operator)` — note it **re-hashes** `edge_id` from that key, so a deduped edge's id is NOT stable against its pre-dedupe id (treat final ids as authoritative).

### 7.4 Consolidated WIRED vs ORPHANED

| Component | Status | Live call site |
|---|---|---|
| `_build_efg_base` / `build_efg` | WIRED | `compile.py:689` |
| `materialize_substrate_bundle` | WIRED | `spine.py:123` |
| `lineage.*` (3 fns) | WIRED | `node.make_field_node` (every id), `materialize.py` ×16 |
| all `dag/helpers.py` (`_edge`, `_dedupe_edges`, `_append_race_bridge_fields`, …) | WIRED | `spine._build_efg_base` |
| tensor write `execute_efg_result` | WIRED | `compile_attach.py:593` |
| **entire `materialization_manifest.py`** (`substrate_bundle_from_manifest`, `load_substrate_bundle_for_efg`, `build_/write_efg_materialization_manifest`, `attach_efg_materialization_summary_to_run`) | ORPHANED from compile — CLI/audit only | `cli.py:588/602`, `construct/efg_materialize.py`, slice14 tests |
| `build_efg.py::build_sim_compiler_run` | DEAD (`raise RuntimeError('retired')`) | — |
| `build_sim_fixture_efg_run` | test-fixture only | — |

The compile pipeline never round-trips through a JSON substrate manifest; it passes the in-memory `SubstrateBundle` straight to `build_efg`. `materialization_manifest.py`'s own docstring (`writes_v_fields=False`, `writes_e_dag=False`, "admission plan not full EFG integration") describes a slice-14B boundary the live `build_efg` has since **superseded** — that summary is true only of the manifest module, not of the real compile.

### 7.5 Gaps, flags & questionable persistence

- **Exposure-path bug (mitigated, not fixed).** `FieldNode.path` in `V_fields` is an absolute path into the transient `{run}__efg_stage_workspace/Tables/efg_tensors/`, which `compile.py:966-968` `rmtree`s after flush. On a completed run that path is dead; `she.panel._resolve_field_tensor_path` (`panel.py:72-90`) **ignores** the stored path and reconstructs `run_dir/Tables/efg_tensors/{field_id}.parquet`. The stored `path` column is vestigial/misleading — any consumer trusting it gets zero tensors → LDO `T=0`. This same staleness class recurs in `investigate.measured_quantity_refs` (fixed 524ea00) and the field-tensor resolver (bfd4744); the missing abstraction is a shared final-tensor-dir resolver (CLAUDE.md §X).
- **Silent-degrade in denominator builders (FIXED 3cc773d).** `_sidra_demographic_population_materialized_fields`, `_population_solver_materialized_fields`, and `_cnes_facility_stock_materialized_fields` used to swallow a malformed/unreadable artifact with a bare `except Exception: continue`, yielding *silently fewer* denominator fields (→ RN never forms → missing rates, no signal). Each now emits a `RuntimeWarning` naming the artifact + the consequence (denominator dropped → those rates won't form). The missing-column skips (facility_id/cnpj, solver mode/id) warn too.
- **Axis-synonym drift (FIXED 3cc773d, §X).** `kernels._shift_year`'s `_YEAR_KEYS` (phantom `competence_year`) and `align._canonical`'s hardcoded time/geography sets (phantom `annual`, missing `mun_occurrence_cod6`/`mun_birth_cod6`) had drifted from each other AND the normalizers. Both now resolve the axis through `registries.canonical_axis` (AD-1) — the single registry-backed source the executor's `support.py` already uses — so they can never disagree; `_YEAR_KEYS` deleted.
- **`operator_budget=256`** can truncate the field set at national scale (many ICD×demographic strata); it *is* recorded as a `FailedBranchRecord`, but callers must read `legality['blocked']`/`failed_branches` to know coverage was bounded.
- **Path hygiene inconsistency.** `field.path` stores a platform-absolute Windows path with no POSIX/relative normalization, unlike `attach_efg_materialization_summary_to_run` which does `.replace('\\','/')`.
- **Duplicate variable *names* (measured 2026-07-12 — cosmetic, not a correctness gap).** On a current national run (`national_c25_full_ad2`) 18 display names are shared across >1 `field_id`. This is NOT the earlier feared *monthly-artifact fragmentation* — that is **already fixed**: `pipeline._combine_processed_datasus_chunks` unions the monthly SIH/CNES (and annual SIM/SINASC) chunks into ONE `processed_events` canonical per `(system, uf, years)` before the EFG, and `_combine_national_artifacts` unions per-UF into one national artifact per `(system, role)`; the current run shows `count`-field name-multiplicity `{}` (a stale June AL run with the pre-fix `uf=AL/{hash}/` layout — no `years=` segment — was the source of the fragmentation misread). The residual 18 are **legitimate variant multiplicity** — the DIS §5.1 generator crosses a measure against several denominators/concepts (`DengueHospitalAdmissions.admission_share` ×4, `observer_share` ×3, divergences ×5-7) whose distinguisher lives in the *lineage parents*, not a surface stratum field. Every output layer is disambiguated by `field_id`: `Hypotheses.parquet` keys edges on `outcome_field_id`/`covariate_field_id`, and the query-layer `_enrich_edges` joins names by `field_id`. A *proper* human-readable disambiguator would be field-type-specific (SIDRA table+classification id, denominator concept) — a scoped, low-priority display-layer follow-up, not an identity-touching EFG rename (§III: output is already correct + id-resolvable).

### 7.6 Prescribed plans vs live code (§IX reconciliation)

| Prescription | Verdict |
|---|---|
| MSD-I §3.8 legality predicate + declaration gate (8 delta terms) | **BUILT + WIRED** (`evaluate_delta`, `spine.py:150`) |
| Real tensor materialization, cross-join forbidden; precompression; core-seed/mandatory/health contracts | **BUILT + WIRED** |
| `classify_q_state` canonical Q-tensor verdict | **BUILT + WIRED** (`compile_attach._q_row`, EFG-QT commit 11fce28; previously zero-caller orphan) |
| MSD-III §II.3 MeasuredQuantity count+exposure → LDO (EFG-OUT-01) | **BUILT-BUT-PARTIAL** — emitted only as an *additive sidecar*; RN still writes the pre-divided **rate parquet as primary** (spec wants count+exposure as the *terminal* object). Refactor plan §4.9. |
| §II.1 single kind-tagged `source_registry_entry` (measures kind:flow\|stock\|field, extensive, exposure_ref) replacing ~40 registries | **PARTIAL** — callable resolver + loader unified (REG-07 / `callables.py`, done) but ~22 per-domain registries remain (EFG-REG-01 Partial); the round-trip-reachability cross-registry validator is the still-open teeth. |
| SIDRA context→EFG-node materialization (§II.7) | **WIRED but profile-gated** — default path shows `skipped`; ledger rules it defensible (intentional regime gating via `sidra_context._run_stdfm_for_context`). Confirm it materializes context nodes in a contextual-scope run. |
| Disease variable generator §5.1 (`variable_grammar.py`) | **ORPHANED by design** — the σ_C-restriction path (`spine.py:272`) is the canonical generator; DIS-06 deferred. |
| §II.6 disease embeddings / mechanical-overlap Jaccard | **NOT-YET-BUILT / marginal** (LDO doc: `type_mechanical_overlap` produced 0 edges nationally). |

**Doc staleness (§IX):** MSD-II ledger + refactor plan still cite the retired monolith — `efg/executor.py (1127 ln)`, `efg/executor.py:705`, `efg/dag.py`, `efg/empirical_compression.py`, `l.8891` Moran. Live: `executor/` is a package (`run,kernels,support`), `dag/` a package (`spine,helpers`), `empirical_compression`→`equivalence.py`; those line numbers are meaningless (Phase C decomposition, task #24, was not repointed). **Naming tripwire:** MSD-I §3.8 titles it "Seven-Part Structural Legality Predicate with Declaration Gate" (7 structural + declaration); MSD-II and `evaluate_delta` count **8** `delta_*` terms (7+1) — not a contradiction, but a reader trap.
