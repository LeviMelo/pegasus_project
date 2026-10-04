# `she` — the Substrate Harmonization Engine (the CommonPanel spine)

A faithful code map of `src/pegasus/she/`: the boundary that turns normalized source artifacts into an
admissible **substrate**, and assembles the EFG's per-field tensors into the **CommonPanel** the LDO
consumes. This is the LDO's direct input — the `(cell × variable)` frame `assemble_ldo_tensor` reads.
Companion deep maps: [`efg.md`](efg.md) (produces the field tensors this module assembles),
[`ldo.md`](ldo.md) (consumes the panel this module produces). Verify against live code (CLAUDE.md §IX).

## 1. Responsibility

`she` owns two boundaries, at opposite ends of the compile:

1. **Substrate admission** (`substrate.py` + `zero_variance.py` + `source_registry.py`) — the *entry* SHE
   boundary (slice 13A). Consumes local source artifacts, applies source-field-registry semantics and a
   zero-variance/all-missing exclusion gate, and emits a typed `SubstrateBundle` of admissible
   `SubstrateFieldCandidate`s (+ audited `SubstrateFieldExclusion`s). It does **not** build the EFG,
   compute rates, fetch, or materialize output keys.
2. **Panel assembly** (`panel.py`) — the *exit* boundary. After the EFG has materialized each field as its
   own tensor, `compile_common_panel` assembles those heterogeneous-support tensors onto one shared
   `(municipality_cod6, year[, month])` cell index → the `CommonPanel`.

Plus domain **summarizers** (`cnes_capacity`, `sih_costs`, `maternal_child`, `maternal_child_linkage`) and
the high-dimensional SIDRA **bounded pushforward** (`high_dimensional.py`).

## 2. The panel spine — `panel.py::compile_common_panel` (the load-bearing function)

Signature: `compile_common_panel(run_dir, *, resolution='year', v_fields_path=None, geography_prefixes=None, time_window=None) -> CommonPanel`.

`CommonPanel` (dataclass): `index` (one row per cell), `values` (**index columns + one column per
`field_id`, wide**), `manifest` (long `(field_id, cell_keys, state, reason)`), `fields: list[PanelField]`.
`values` is exactly what `ldo/assemble.py` scatters into the `(p, S, T)` tensor — **axis-0 is keyed on
`field_id`, never on `name`** (so duplicate display names cannot collide LDO variables; see efg.md §7.5).

Sequence:
1. Read the `V_fields.parquet` catalog (metadata only — no tensors held).
2. `_build_index_streaming` — the shared cell index = **union** of every field's `(muni, year[, month])`
   cells, via `scan_parquet → select keys → unique` per parquet (peak RAM O(unique cells), not Σ tensor
   sizes). Prefers full muni×year fields; falls back to whatever geo/time cells exist.
3. **Axis scoping** (both critical for the LDO's working set):
   - `time_window=(lo,hi)` restricts the TIME axis to the intent's study window — **without it, SIDRA
     census/historical years (1970, 1980, 1991, …) leak in** as extra time points (national C25: 42 yrs
     vs the declared 25), diluting the temporal model and inflating the O(p·S·T) stability subtensors.
   - `geography_prefixes` (2-digit cod6 UF prefixes) restricts the index to the run's geographic scope
     (a defensive mirror of the EFG executor's scope guard).
4. **Per-field loop** (bounded RAM — one tensor live at a time, Finding 6): resolve tensor path →
   read only `[*support_keys, value]` → `_align_field` → **join as a `field_id` column** onto
   `value_frame` → `del tensor`. Coarser-support fields broadcast (see §2.1).
5. **Vectorized provenance manifest** — per `(field, cell)` a `when/then` state column, concatenated
   (never a per-cell Python append loop; the old row-by-row build crashed polars schema inference on the
   all-null-then-string `reason` column — it is now explicitly `Utf8`).

### 2.1 The anti-silence contract (§II.2.1 / §II.11) — **a panel cell is never blank**

`_align_field` returns `(index+value, broadcast_state)`; every value carries how it reached the cell:
`observed` (field has both muni+year) · `geo_invariant_broadcast` (no muni) · `time_invariant_broadcast`
(no year/month) · `domain_scalar_broadcast` (no keys → one value to all cells) · a coarser-grain field on
a finer panel is honestly `unavailable_on_panel` with reason `field_resolution_coarser_than_panel:year`
(never fabricated). A missing cell always gets an explicit `reason` (`cell_absent_from_field_support`,
`field_not_materialized`, `no_value_column`). Duplicate cell rows within one field collapse by **mean**
(defensive, `group_by(keys).agg(mean)`).

### 2.2 The stale-path fallback — `_tensor_path`

`V_fields.path` is an absolute path into the transient `{run_dir}__efg_stage_workspace/` that compile
`rmtree`s after flushing tensors to `run_dir/Tables/efg_tensors/`. On a completed run that stored path is
dead, so `_tensor_path` **ignores it** and reconstructs `run_dir/Tables/efg_tensors/{field_id}.parquet`.
Trusting the stored path alone made the national panel find zero tensors → empty index → LDO `T=0`. This
is the same path-staleness class as `investigate.measured_quantity_refs` (efg.md §6) — the missing shared
abstraction (a final-tensor-dir resolver) is CLAUDE.md §X.

## 3. The substrate boundary — `substrate.py::build_substrate_bundle`

`build_substrate_bundle(*, artifacts, allow_heuristic_registry=True) -> SubstrateBundle`. Per artifact:
skip model-prior JSONs (`RACE-BRIDGE` / `emission_prior` — they enter via the `Bridge_R` operator, not the
field substrate); a missing artifact → a `SubstrateFieldExclusion(reason='missing_artifact')` (audited, not
silent); else `profile_table_variance(path)` → `resolve_source_fields(system, columns)` → per column:

- registry-unresolved column → `SubstrateFieldExclusion(reason='unresolved_source_field')`.
- `profile.admissible AND spec.admissible_by_registry` → a `SubstrateFieldCandidate` (carries carrier /
  unit / aggregation / role / axes / provenance / `substrate_kind` + the variance profile stats).
- else → `SubstrateFieldExclusion(reason= profile.exclusion_reason or spec.registry_reason)`.

The `SubstrateBundle` is content-addressed (`substrate_id = _stable_id(payload)`) over its candidate/
exclusion ids + registry hashes, and carries `source_reality_mode` (development vs materialized_external —
the compile-time source-reality contract). `materialize_substrate_bundle` (in **efg**, not here) turns
candidates into root `FieldNode`s (efg.md §7.2).

### 3.1 The exclusion gate — `zero_variance.py::profile_table_variance`

Source-**agnostic**, conservative: excludes 100%-missing columns, constant (zero-variance) columns, and
structural non-analytical columns by name/suffix — identifiers/hashes/raw payloads (`_id`, `_hash`,
`_json`, `_raw`, `row_hash`, `raw_record_hash`, …) and state markers (`_state`, `_parse_state`, …). These
stay auditable but never become analytical candidates. `NULL_TOKENS` normalizes missingness. Emits
`ColumnVarianceProfile` / `TableVarianceProfile` (row/non-null/unique counts, missing_rate, numeric range,
`admissible`, `exclusion_reason`).

### 3.2 Canonical field resolution — `source_registry.py`

The compatibility boundary to the YAML `registries.source_fields` layer: `resolve_source_field(s)` maps
each source column to a `SourceFieldSpec` (canonical `CarrierId`, unit, aggregation, role, axes,
provenance, `substrate_kind`, `admissible_by_registry`, `registry_reason`). `allow_heuristic` permits a
best-effort spec for columns absent from the registry; `_is_unknown_entry` flags unresolved ones. This is
where a source column's **canonical semantics** are declared once (CLAUDE.md §X — consult the registry, do
not re-derive by string-matching downstream).

## 4. Satellites

- `high_dimensional.py` — the bounded pushforward for high-cardinality SIDRA exposure: `HighDimensionalBound`,
  `bound_high_dimensional_sidra_exposure`, `execute_bounded_pushforward`, `require_bounded_pushforward`;
  raises `HighDimensionalExposureError` when `estimated_cells` exceeds the guard without a declared bound
  (the passive check the EFG legality axes-term mirrors — efg.md §3.1).
- `cnes_capacity.py` / `sih_costs.py` — `summarize_cnes_capacity` / `summarize_sih_costs`: per-(run) facility
  stock and SIH cost summaries (the `slice5a_*_summary.parquet` artifacts).
- `maternal_child.py` / `maternal_child_linkage.py` — `summarize_maternal_child_events` /
  `summarize_maternal_child_linkage`: SINASC/SIM birth-outcome summaries with a plausibility guard
  (`_assert_plausible_anomaly_rate`) — the perinatal cross-scope inputs.

## 5. Seams & contracts

- **Upstream (from efg):** consumes `run_dir/V_fields.parquet` (the field catalog) + `Tables/efg_tensors/
  {field_id}.parquet` (the materialized tensors). Assumes each tensor carries a `value` column + some subset
  of `(municipality_cod6, year, month)`.
- **Downstream (to ldo):** `CommonPanel.values` (wide, one col per field_id) + `.cell_keys` is exactly what
  `ldo.assemble.assemble_ldo_tensor(panel, …)` reads; `.manifest` states feed the reliability weights.
  `write_common_panel` persists `common_panel_{values,manifest,summary}` for audit.
- **Registries consulted:** `registries.source_fields` (via `source_registry`) for canonical carrier/unit/
  role/axes; the zero-variance name lists are module constants (source-agnostic).

## 6. Known flags / debts

- **Silent tensor-read swallow.** `_load_field_tensor` / `_tensor_columns` return `None`/`()` on any read
  exception (bare `except Exception`) — a corrupt/renamed tensor becomes a silently `unavailable_on_panel`
  field rather than a raised error. The manifest records `field_not_materialized`, so it is *auditable*, but
  nothing raises (weaker than CLAUDE.md §V would prefer for a malformed — vs absent — tensor).
- **`_align_field` broadcast-state branch is exhaustive but brittle.** State is assigned by *which* of
  `{municipality_cod6, year, month}` is absent from the field's keys; the trailing `else: observed` is
  effectively unreachable for the real key space (a non-empty `missing_keys` that omits both year and month
  can only be `[municipality_cod6]`, already caught by the `geo_invariant_broadcast` branch). It is correct
  today, but the hand-enumerated conditions would silently mislabel if a fourth cell key were ever added.
- **Vestigial `V_fields.path`.** The stored absolute path is dead on completed runs (§2.2); consumers must
  use the `run_dir` reconstruction. The column is retained but misleading.
- **Deep-map status:** this page + [`ldo.md`](ldo.md) + [`efg.md`](efg.md) are the three deep maps;
  `denominators/population`, `datasus` normalizers, and `output` remain the follow-up (see
  [`../MODULE_MAP.md`](../MODULE_MAP.md)).
