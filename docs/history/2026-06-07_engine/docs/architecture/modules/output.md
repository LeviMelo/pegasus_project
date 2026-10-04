# `output` — the run-bundle output contract + the query layer

A faithful code map of `src/pegasus/output/` (~3.1k LOC): the boundary that serializes a compile into the
canonical **17-key run bundle** and the read-side **Output Query Layer** that materializes derived datasets
from an emitted bundle. This is the LDO/EFG's terminal sink — it turns `Hypotheses` LinkRecords + per-field
tensors into a queryable, validated, reproducible artifact. Companion deep maps: [`efg.md`](efg.md)
(produces `V_fields` + `Tables/efg_tensors/{field_id}.parquet`), [`ldo.md`](ldo.md) (produces the
`Hypotheses` LinkRecords). Verify against live code (CLAUDE.md §IX; `file:line` drifts — trust the code).

## 1. Responsibility

`output` owns three read/write boundaries and nothing analytic:

1. **Bundle serialization** (`schema_seed.py`, `bundle.py`, `bundle_manager.py`, `table_io.py`, `schemas.py`)
   — the canonical 17-key contract: seed empty schemas, atomically flush accumulated rows, dedup by primary
   key, enforce the anti-silence declared-empty contract.
2. **Validation & source-reality** (`validate.py`, `source_reality_guard.py`) — `validate_output_bundle`
   checks exact-17-key presence + cross-reference integrity + per-domain contracts; the guard scans for
   fixture/synthetic contamination under `compile_source_mode=materialized_external`.
3. **Read side** (`output/query/`, `run_catalog.py`, `reproducibility.py`) — the Output Query Layer
   (`materialize_query`), the run-discovery catalog (`scan_runs`), the reproducibility manifest + telemetry.

It does **not** build the EFG, run the LDO, compute rates, or fetch. `compile.py` orchestrates it
(`OutputBundleManager` at compile.py:527, `validate_output_bundle` at compile.py:1026).

## 2. The 17-key run bundle

The single source of truth is `schemas.py:6` `OUTPUT_BUNDLE_FILES` — 11 parquet **table** keys, 4 **JSON**
keys (`UserIntent`, `RunConfig`, `P_vector`, `ReproducibilityManifest`), 2 **directory** keys (`Tables`,
`Maps`). All eleven table schemas are pinned in `schema_seed.py` (`V_FIELDS_SCHEMA`, `Q_TENSOR_SCHEMA`,
`HYPOTHESES_SCHEMA`, …).

- `schema_seed.py:202` `create_schema_seed_output_bundle(run_dir)` — `rmtree` + write every empty pinned
  schema + neutral JSON envelopes. Production-safe: no analytic rows.
- `bundle.py:82` `create_empty_output_bundle(run_dir)` — seed + a `slice0_scaffold_field` row into
  `V_fields`/`Q_tensor`/`VariableDictionary` + `empty_by_profile` warnings; hardcodes `run_profile=core_vital`.

### 2.1 `OutputBundleManager` — the atomic serialization boundary (`bundle_manager.py:132`)

The load-bearing writer. Accumulates rows in memory, then flushes atomically.
- `set_table(key, rows)` / `append_table(key, rows)` — ingest into `TABLE_KEYS`; every row is normalized at
  ingest (`_normalize_rows`, idempotent). `append_table` replaces by `PRIMARY_KEYS[key]` (bundle_manager.py:41
  — `V_fields`→`field_id`, `E_DAG`→`edge_id`, `Hypotheses`→`hypothesis_id`, …). `set_json`, `set_artifact_dir`.
- `from_existing(run_dir)` / `collect_missing_from_run` — hydrate a manager from an on-disk bundle.
- `write_stage_workspace(dir)` — write to the transient workspace; `flush_to_disk(run_dir)`
  (bundle_manager.py:323) — write to a tempdir, then `atomic_replace` swap with a `.pre_phaseE` rollback
  (uses `core.io_utils.atomic_replace`; tables via `storage.write_table(schema_policy="preserve")`).
- `_append_empty_by_profile_warnings` (bundle_manager.py:247) — **anti-silence**: every empty first-class key
  not required for `(run_profile, execution_stage)` gets a declared `empty_by_profile`/`empty_by_stage`
  Warnings row, so an empty artifact is never silently empty (shares `required_nonempty_keys` with the validator).
- `_check_first_class_consistency` (bundle_manager.py:301) — an `E_DAG` endpoint referencing a field absent
  from `V_fields` emits a `RuntimeWarning` (warns, never raises — a legit edge case can't break the atomic flush).
- `_normalize_variable_dictionary_row` (bundle_manager.py:66) — coerces a VD row to **exactly** the 14
  seed columns; **drops any extra column** (load-bearing for §3, §6). `_normalize_model_assoc_row` JSON-encodes list cells.

### 2.2 The profile contract (`schemas.py:54`)

`required_nonempty_keys(run_profile, execution_stage)` is the shared gate consumed by both the manager and
the validator (kept in one place so they can't drift). `PROFILE_NONEMPTY` (schemas.py:33) declares the
per-profile non-empty set (`core_vital`/`contextual`/`full`). `LEGACY_INFERENCE_KEYS`
(`ModelAssociations`/`ResidualAssociations`) are **never** required (LinkRecord-authoritative, MII-OUT-01);
`Hypotheses` is required only at `execution_stage=investigate`.

### 2.3 `table_io.py` — the parquet row helpers

`append_replace_rows(path, rows, id_column)` (table_io.py:99) — the append-with-replace used by the seed +
satellite writers. `write_rows_like` (table_io.py:69) preserves an existing table's schema; its
`_schema_with_promoted_nulls` (table_io.py:28) promotes an all-null seed column to the inferred type on first
real write (so a seed `Null` column can accept a later float). `empty_like`, `append_rows`, `read_rows`.

## 3. The Output Query Layer (`output/query/`)

An **additive reader** over an emitted bundle — never mutates first-class tables. `spec.py:13` `QuerySpec`
(`quantity`, `kind` default `"edge"`, `denominator`, `filters`, `enrich=True`; `QUERY_KINDS =
raw_field/count/rate/standardized_rate/edge`). `engine.py:232` `materialize_query(bundle_dir, spec) ->
MaterializedDataset(frame, provenance, kind, warnings)` dispatches:

- **`edge`** → `_edge_query` (engine.py:99): lazy `scan_parquet(Hypotheses.parquet)` + predicate-pushdown
  `filters` (national-safe — never loads the whole table); a filter on an absent column is a typed
  `QueryError`, never a no-op. If `enrich`, calls `_enrich_edges`.
  - `_enrich_edges` (engine.py:83) — **the field_id join**: `_variable_metadata` (engine.py:70) reads
    `VariableDictionary` (else `V_fields`) keyed on `field_id` (== the LDO variable id), then left-joins onto
    the edge's **`source_var`** and **`target_var`** endpoints (so the estimator stays decoupled from labels).
    Aspires to join `_ENRICH_COLS = name/carrier/unit/diagnostic_role/icd_group_id/icd_group_kind`
    (engine.py:67) — but see §6.4: only `carrier`/`unit` survive in a real bundle. **This is the natural home
    for edge credibility banding** (nothing consumes such a band yet).
- **`count` / `raw_field`** → `_field_query` (engine.py:126) via `field_tensor.py`: `resolve_field`
  (field_tensor.py:37 — by `field_id`/`technical_name`/`display_name`, ambiguity is an error) →
  `read_field_tensor` (field_tensor.py:100 — lazy read of `Tables/efg_tensors/{field_id}.parquet`, the
  bundle's own copy, **not** the stale `__efg_stage_workspace` manifest path). `count` flags a non-count
  `unit` (`COUNT_UNITS`, field_tensor.py:23) rather than treating a rate as a count.
- **`rate`** → `_rate_query` (engine.py:168): **selects** the EFG's already-materialized RN rate field by
  carrier (`resolve_field_by_carrier`, field_tensor.py:68) — never a query-time division. Denominator from
  the FEAT-P4 registry (`denominators.py:109` `resolve_denominator`, `denominator_carrier`; reads
  `config/registries/health/denominators.yaml`, exactly-one-default rule) or the literal override; default
  `resident_population`→`Population`.
- **`standardized_rate`** → refused (age-standardization is the compile-time `age_standardization` engine).

`export.py:16` `write_dataset(dataset, out_dir, name)` — writes `<name>.{parquet|csv}` + a mandatory
`<name>.provenance.json` sidecar (nothing written without provenance).

## 4. Run catalog + reproducibility manifest

- `run_catalog.py` — read-only discovery over `data/runs`. `scan_runs` (run_catalog.py:109) reads only the
  small identity JSONs (`UserIntent` + `ReproducibilityManifest`, never tensors) into `RunRecord`s;
  `find_runs`/`latest_run`/`RunRecord.matches` filter by uf/year/stage/scale/profile/seed;
  `build_catalog`/`load_catalog` persist the index. Pure discovery — does not touch the compile/flush path.
- `reproducibility.py` — `RunTelemetry` (reproducibility.py:44): a `stage(name)` context manager that
  records per-stage status/wall-seconds over `COMPILE_TELEMETRY_STAGES`, writes a heartbeat, and mirrors
  `telemetry` into `ReproducibilityManifest.json` on every `flush`. `write_reproducibility_manifest`
  (reproducibility.py:131) pins run_id/intent_hash/source_hashes/registry_hashes/seed + telemetry.

## 5. Seams & contracts

- **Upstream (from ldo):** the live `Hypotheses.parquet` is the LDO's **LinkRecord** schema
  (`ldo/records.py:20` `LinkRecord`, 25 cols: `source_var`/`target_var`/`edge_type`/`partial_correlation`/
  `stability`/`fdr_qvalue`/`certification_status`/`causal_rung`/…). `ldo/output.py:54` `write_hypotheses`
  writes it **directly** to `run_dir/Hypotheses.parquet` (bypassing `OutputBundleManager`), overwriting the
  seed schema — from both `compile.py:973` and standalone `workflows/investigate.py:416`. The `count`/`rate`
  path additionally consumes `Tables/efg_tensors/{field_id}.parquet` + the `VariableDictionary`.
- **Upstream (from efg):** `V_fields` + `VariableDictionary` rows are built by `efg/compile_attach.py`
  (`_dictionary_row` at compile_attach.py:432) and handed to `bundle.set_table(...)` (compile_attach.py:736).
- **Downstream:** the query layer + catalog serve consumers; `validate.py` is the acceptance gate.
- **Validation** (`validate.py:599` `validate_output_bundle`): exact-17-key presence (`_validate_first_class_keys`,
  flags missing **and extra** root artifacts) → JSON/telemetry contract → parquet contracts:
  required columns on V_fields/E_DAG/Q_tensor/VariableDictionary, `V_fields ⊆ VariableDictionary ∩ Q_tensor`
  coverage, E_DAG endpoint integrity, profile-nonempty anti-silence, per-domain contracts (race-bridge,
  cnes/sih, population-tensor), inference invariants, and `materialized_external` purity via
  `source_reality_guard.py:99`.

## 6. Known flags / debts

1. **`Hypotheses` schema duality.** The pinned `HYPOTHESES_SCHEMA` (schema_seed.py:124 —
   `outcome_field_id`/`covariate_field_id`/`residual_field_id`, `statistic`, `p_value`, `hsic_mode`) is only
   the **empty seed**; the live LDO overwrites it with the **LinkRecord** schema (`source_var`/`target_var`/
   `partial_correlation`/`edge_type`). The query layer is correctly built for LinkRecord; the validator is not (2–3).
2. **Validator inference-invariants are a no-op on live output.** `_validate_inference_invariants`
   (validate.py:388) keys on `hsic_mode`/`statistic`/`p_value`/`residual_mode` — **none exist** in the
   LinkRecord schema, so `active` is always falsy and the null-statistic check + the §10 in-sample-residual
   hard-abort never fire on a real `Hypotheses`. Only the `ModelAssociations`-fitted→`ResidualAssociations`
   check still runs (it reads `ModelAssociations`, not `Hypotheses`).
3. **Validator field-reference integrity skips `Hypotheses` endpoints.** `FIELD_REFERENCE_COLUMNS`
   (validate.py:25 — `field_id`/`parent`/`child`/`outcome`/`covariate`/`residual_field_id`) ∩ LinkRecord
   columns = ∅, so the `illegal_excluded` cross-reference check never inspects `source_var`/`target_var`.
4. **`_enrich_edges` columns are mostly aspirational.** `efg/compile_attach.py:432` emits
   `diagnostic_role`/`icd_group_id`/`icd_group_kind` on the VD row, but `bundle.set_table("VariableDictionary")`
   → `_normalize_variable_dictionary_row` (bundle_manager.py:66) **strips every column outside the 14 seed
   columns** before write, and VD stores `display_name` not `name`. So against a real bundle the edge join
   adds only `{source,target}_carrier` and `{source,target}_unit` — the ICD-group/topology/label enrichment
   is silently dropped.
5. **`Coverage.json` vs the exact-key validator.** `run_investigate` writes `Hypotheses.parquet` **and**
   `Coverage.json` directly to `run_dir` (investigate.py:414–422); `Coverage.json` is not one of the 17 keys,
   and `_validate_first_class_keys` flags any extra root artifact. `run_investigate` itself does not
   re-validate, so the tension only bites a validate run after a standalone investigate.
6. **Query layer + RunCatalog are orphaned-but-callable.** `materialize_query`, `write_dataset`, `scan_runs`,
   `build_catalog` have **no** CLI/workflow caller — only `tests/unit/test_output_query_*` + `test_run_catalog`.
   Real (`Grep`-verified) capability with test coverage, not wired into a production path.
7. **Satellite attach-writers orphaned from compile.** `sidra_denominator_anchor.py`
   (`attach_sidra_population_anchor_to_run` — official SIDRA population anchor + crude-rate field + edge),
   `sinasc_efg_bundle.py` (`write_sinasc_fixture_efg_bundle` — a self-described *fixture* writer),
   `maternal_child_compile_attach.py` — each is called only by its own unit test, never by the live compile.
8. **Direct-write bypass.** The satellite writers + `write_hypotheses` mutate bundle parquets directly
   (`table_io`/`polars.write_parquet`), not through `OutputBundleManager`, so the manager's normalization,
   consistency check, and atomic swap do not cover those writes.
