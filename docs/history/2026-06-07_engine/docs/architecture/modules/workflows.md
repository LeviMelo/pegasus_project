# `workflows` — the stage-orchestration spine (acquire → compile → investigate → report)

A faithful code map of `src/pegasus/workflows/` (~4.9k LOC): the driver layer that wires the pipeline
stages end-to-end — **acquire** (fetch DATASUS via the R-bridge + SIDRA, combine per-UF/national) →
**compile** (population solve + SHE substrate + autonomous EFG + tensor flush) → **investigate** (run the
LDO over the compiled panel) → **report** (describe-only readers). It owns intent→params→merge→compile
sequencing and nothing else: every heavy computation is delegated. Companion deep maps:
[`datasus.md`](datasus.md) (the R-bridge fetch + normalizers this drives), [`efg.md`](efg.md) (the graph
build this attaches), [`she.md`](she.md) (the substrate + `CommonPanel` it assembles),
[`ldo.md`](ldo.md) (the estimator investigate runs), [`output.md`](output.md) (the bundle it flushes +
validates). Verify against live code (CLAUDE.md §IX). At [`../MODULE_MAP.md`](../MODULE_MAP.md) depth-plus.

## 1. Responsibility

`workflows` is **orchestration only** — "purely the intent→params→merge→compile orchestration"
(`pipeline.py:12-13`). It resolves acquisition parameters from a `UserIntent`, fetches real sources,
merges one materialized-external source manifest, and sequences the compile stages, threading telemetry
and run identity through. It does **not** own any math: fetch/normalize belong to `datasus`/`sidra`, the
population tensor to `denominators`, substrate admission to `she.substrate`, the EFG build+execution to
`efg.dag`/`efg.compile_attach`, panel assembly to `she.panel`, the estimator to `ldo`, and
bundle/validate to `output`. The load-bearing spine is four files — `pipeline.py` (615), `compile.py`
(1062), `investigate.py` (435), `stage_plan.py` (282); the `acquire/`, `construct/`, `report/`
subpackages are mostly **thin CLI-command wrappers** over those engines (the three `__init__.py` are
empty — no package re-exports, callers import submodules directly).

## 2. The stage spine — the load-bearing drivers

- **`run_live_pipeline`** (`pipeline.py:478`) — the end-to-end entry (CLI `run`, `cli.py:293`):
  `(*, intent_path, data_root='data', run_dir=None, sidra_metadata_dir='data/metadata/sidra/normalized',
  datasus_client=None, sidra_client=None, dry_run=False, require_complete_datasus=False) ->
  LivePipelineResult`. `plan_live_pipeline` (`:369`) is its network-free/R-free dry-run (intent→params
  resolution only, for `--dry-run`).
- **National-vs-state branch** — `national = intent.execution_scale == "national"` (`pipeline.py:496`).
  *National* → `_acquire_national` (all 27 UFs, combined per-(system,role); §3) → one national source
  manifest → `run_compile(..., require_materialized_external=True)` (`:520-538`). *State/smoke* →
  sequential single-UF acquire (`uf = ufs[0]`): `_acquire_datasus` + the SIDRA population / strata /
  census-2000 / civil-registry / compendium bundle + optional race-bridge prior → merged manifest →
  `run_compile` (`:550-599`). Both write `data/manifests/runs/live_{stem}_{hash}.source_manifest.json`.
- **`run_compile`** (`compile.py:1046`, CLI `compile` `cli.py:270`): `(*, intent_path, run_dir=None,
  data_root='data', source_manifest=None, require_materialized_external=False) -> dict`. Delegates to
  `_run_compile_impl` (`:992`), a 7-phase pipeline over a resolved `_CompilePlan` (`:431`): `_resolve_
  compile_plan` (`:475`) → `_hash_and_manifest_sources` (`:613`) → `_materialize_population_and_substrate`
  (`:658`) → `_derive_stage_status` (`:716`, PURE) → `_apply_derived_telemetry` (`:771`) →
  `_serialize_run_bundle` (`:810`) → `_flush_and_investigate` (`:947`) → `validate_output_bundle`
  (`:1026`). `source_manifest is None` is a hard error (`:536` — production compile requires it).
- **Compile scale branch** — `_intent_municipality_filter_cod6` (`:80`) + `_geo_scope_from_intent`
  (`:118`) fork on `execution_scale ∈ {national, state, smoke}`: national → `GeoScope.national`
  (all UFs, `geography.codes=[]` enforced `:85`); state → `GeoScope.from_uf` (exactly one UF); smoke →
  a single resolved cod6 allowlist.
- **`run_investigate`** (`investigate.py:302`): `(run_dir, *, intent=None, resolution='year', K=3,
  lambda1=0.1, lambda2=1.0, write=True, multiresolution='auto', spec_reliability=False, **ldo_kwargs)
  -> InvestigateResult`. Invoked by compile's `_flush_and_investigate` **iff**
  `str(intent.execution_stage) == "investigate"` (`compile.py:976`); also re-runnable standalone against
  an already-compiled `run_dir`. It **reuses the existing compiled panel** (reads `V_fields` +
  `Tables/efg_tensors` via `compile_common_panel`) — it does **not** rebuild the EFG (§4).

## 3. The acquire sub-flow (fetch → per-UF normalize → combine per (system,role))

- **DATASUS** `_acquire_datasus` (`pipeline.py:190`): one `client.fetch_systems` call fans out across
  systems×years in a single global worker pool. Per system it triages `success`/`cached` vs `blocked`
  (missing/broken R bridge → **hard-fail** `:236`) vs `failed`/`timeout` (an **explicit partial-coverage
  warning** `:226`, and fail-closed when `require_complete` `:241`); zero usable across all systems is a
  hard error (`:246`). Anti-silence per the full-data mandate.
- **The monthly/annual chunk union** — `_combine_processed_datasus_chunks` (`:167`) concatenates the
  fetched per-chunk parquets (annual SIM/SINASC + **monthly** SIH/CNES) into **ONE** combined
  `processed.parquet` per `(system, uf, years)` via a lazy `pl.concat(...).sink_parquet` (`:185-186`),
  *before* SHE normalization. So a multi-file DATASUS system becomes a **single canonical**, never
  fragmented parallel field lineages downstream. `_combine_normalize_one` (`:251`) then combines →
  `_normalize_datasus` (`:151`, dispatching `_NORMALIZERS[system]` `:143` →
  `datasus.normalize.normalize_{sim_do,sinasc,sih_rd,cnes_st}_events`) → `inspect_source_artifact`
  (`processed_events` role); run ≤2-wide across systems (`:330`, RAM-bounded).
- **Content-addressed `combined_hash`** (`:271`) — keyed on the **sorted set** of per-chunk
  `processed_sha256` (`:266-270`), NOT volatile manifest bytes (the 75784a3 fix; embedded per-run
  timestamps had made the key non-deterministic → cache never hit → re-normalize every run, comment
  `:259-265`). Canonical short-circuit skips combine+normalize when `canonical.parquet` already exists
  (`:291`); the combined intermediate is pruned once its canonical lands (`:305`, re-derivable, keeps the
  layer at O(1 unit) not ~19 GB national).
- **`_resolve_systems`** (`:122`): `SIM-DO` + `SINASC` always; `+SIH-RD +CNES-ST` iff `include_cnes_sih`
  ∈ `context_policy`; minus `exclude_systems`.
- **National combine** `_combine_national_artifacts` (`sidra_national.py:78`): groups per-UF artifacts by
  `(system, role)` and, per group, streams a **pyarrow row-group-batch** concat (250k-row batches against
  one unified schema, `:119-128`) into `data/normalized/national/{system}__{role}.parquet` (`:106`), ≤3
  workers (`:150`). Peak is one batch, never the ~25 GB national frame (per-UF dtype drift defeats naive
  streaming, comment `:108-114`). Writes a `.window.json` sidecar (`:135`) so warm reuse cannot cross
  windows; `_national_datasus_cached` (`:181`) is the window-gated warm fast path (skips the whole per-UF
  re-acquire on a matching re-run, fail-closed on window mismatch).
- **SIDRA** (`acquire/sidra_population.py`, `sidra_compendium.py`): `_acquire_sidra_population` (`:307`,
  9606 census + 6579 intercensal → `normalized_facts` closure anchor) is unconditional; the tensor inputs
  `_acquire_sidra_population_strata` (`:405` → `population_strata`), `_acquire_sidra_census_2000_strata`
  (`:485`, 2093 → `census_2000_strata`), and `_acquire_sidra_civil_registry_vital` (`:362`, 2609/2683 →
  `civil_registry_{births,deaths}`) all gate on `_population_tensor_requested` (`:103`). Strata/census
  periods are **scope-invariant** (all censuses regardless of the query window, FAL-POP `:419-424`). The
  compendium `_acquire_sidra_compendium_context` (`sidra_compendium.py:160` → `context_facts`) gates on
  `run_profile ∈ {contextual, full}` (`:41`) and **isolates per-table failures** (`:156`, one flaky table
  never sinks the ~94-table fetch). National SIDRA is fetched for all UFs concurrently
  (`_SIDRA_UF_PARALLEL=6`, `sidra_national.py:157`) then combined; metadata is warmed once single-threaded
  first (`:242`, avoids a write race).

## 4. The compile→investigate seam (EFG build → tensor flush → panel → LDO)

- **Materialize** `_materialize_population_and_substrate` (`compile.py:658`): stage `population_solver`
  (`_build_population_tensor_artifact` `:270` → `denominators`, subprocess-isolated at national scale
  `:377`) appends a `population_tensor` artifact → stage `she_build` (`build_substrate_bundle` `:686`) →
  stage `efg_build` (`build_efg` `:689` + `attach_autonomous_efg_to_run` `:695`).
- **Tensors land in a STAGE WORKSPACE, not the run dir.** The attach (`efg/compile_attach.py:589-598`)
  seeds a `{run_dir}__efg_stage_workspace/` bundle and calls `execute_efg_result` to materialize each
  field tensor into `…workspace/Tables/efg_tensors/{field_id}.parquet` (+ `.measured_quantity.parquet`
  sidecars) and compute `Q_tensor` diagnostics — `V_fields`/`Q_tensor`/`VariableDictionary`/`E_DAG` are
  written here.
- **Flush, then investigate** `_flush_and_investigate` (`compile.py:947`): stage `output_bundle_flush`
  copies the workspace into the final `run_dir` (`bundle.flush_to_disk` `:960`) and **`rmtree`s the
  workspace** (`:966`, else every national run leaves a multi-GB duplicate). Only *then*, iff
  `execution_stage == "investigate"`, `run_investigate(run_dir, intent=intent)` (`:979`).
- **Investigate reads the flushed panel.** `compile_common_panel(run_dir, resolution, geography_prefixes,
  time_window)` (`investigate.py:325`) streams the panel from `V_fields` + `Tables/efg_tensors`; the
  study-window scope (`_time_window` `:46`) keeps SIDRA census/historical years from leaking extra time
  points. It then builds the LDO's side inputs from `V_fields`/`Q_tensor` — `analytical_variable_ids`
  (`:333`, drop raw passthroughs), `disease_variable_meta` (`:111`, ICD `code_set`+topology from
  `support.restrict_conditions`/`axes`), `variable_carriers` (`:149`), `measured_quantity_refs` (`:171`,
  the count|exposure sidecars), `state_reliability_weights` (`:237`, Kish×fragility×provenance→W) — and
  dispatches `run_ldo` or `run_ldo_multiresolution`. The `multiresolution='auto'` gate fires on
  `resolution != 'year' or cells > 300_000 or S > 1000` (`:385` — so the national municipality×year run,
  ~139k cells, qualifies via `S>1000`). Writes `Hypotheses.parquet` (`write_hypotheses` `:416`) +
  `Coverage.json` (`:422`).
- **Path-staleness** — `V_fields.path` points into the pruned workspace, so consumers reconstruct
  `run_dir/Tables/efg_tensors/{basename}`: `measured_quantity_refs` falls back explicitly (`:214`), as
  does `she.panel._tensor_path` (see [`she.md`](she.md) §2.2). The missing shared abstraction (a
  final-tensor-dir resolver) is CLAUDE.md §X.

## 5. Seams & contracts

- **Consumes:** the intent JSON (`UserIntent`); a **materialized-external source manifest** (production
  compile refuses otherwise, `:536`), validated by `_validate_compile_manifest_artifacts` (`compile.py:194`)
  against a required `(system, role)` set — `{SIM-DO,SINASC}:processed_events` + `SIDRA:normalized_facts`,
  `+{CNES-ST,SIH-RD}` iff `include_cnes_sih`, `+SIDRA:context_facts` iff contextual/full,
  `+RACE-BRIDGE:emission_prior` iff a race bridge is planned/embedded, minus `exclude_systems`; registry
  hashes from `_registry_hashes` (`:42`).
- **Produces on disk (`run_dir`):** `UserIntent.json`, `RunConfig.json`, `ReproducibilityManifest.json`,
  `V_fields.parquet`, `Q_tensor.parquet`, `VariableDictionary.parquet`, `E_DAG.parquet`,
  `Tables/efg_tensors/{field_id}.parquet` (+`.measured_quantity.parquet`), `Tables/efg_{execution,
  autonomous}_manifest.json` + domain summaries, then (investigate) `Hypotheses.parquet` + `Coverage.json`
  + `spatial_fields/`. Side artifacts under `data/`: `manifests/runs/{run_id}.compile_manifest.json` +
  `live_*.source_manifest.json`, `normalized/national/*`, and the versioned population-tensor asset store.
- **Stage-plan contract** (`stage_plan.py`): `build_compile_stage_plan` (`:137`) emits a proof-carrying
  `CompilerStagePlan` (`:56`) over the optional stages (`geo_support`, `population_solver`, `stdfm`,
  `pirs_model`, `pirs_hsic`); a stage may be `skipped` **only** when unrequested by intent
  (`skip_allowed = not requested`, `:129`). `validate_compiler_stage_plan` (`:250`) enforces
  telemetry↔plan consistency (requested-but-skipped, skip-without-reason) and is consumed by
  `acceptance.contracts` (`:12`). The `pirs_model`/`pirs_hsic` executors are `None` — retired into the LDO
  investigate stage (LDO-06, `:212,222`).
- **CLI surface** (`cli.py`, typer): `compile` → `run_compile`; `run` → `run_live_pipeline`; plus granular
  manual-stage commands wiring `acquire/*` (datasus/sidra ingest+normalize, source-artifact inspect),
  `construct/*` (substrate build/summary, EFG materialize), `report/*` (dashboard inspect, acceptance,
  compile-source-reality, race-bridge validate/plan).

## 6. Known flags / debts

- **The `construct/` + most `acquire`/`report` wrappers are NOT on the live compile path.** `run_compile`
  inlines `build_substrate_bundle` / `build_efg` / `attach_autonomous_efg_to_run` **directly**
  (`compile.py:686-695`); the `construct/build_substrate.py` + `efg_materialize.py` + `build_efg.py`
  wrappers are a **parallel granular-CLI surface** (manual per-stage commands), orphaned from the driver
  (CLAUDE.md §IX orphaned-but-callable). Faithful to the templates: existence in code ≠ use in the live path.
- **Manual domain attachers retired/orphaned.** `report/race_bridge.py::run_attach_race_bridge` (`:161`)
  is a manual EFG-field attacher with **no live `src/` caller** — the MSD cutover forbids manual domain
  attachers (race-bridge fields must flow through the autonomous EFG bridge/operator, `compile.py:733-735`);
  it survives for the CLI/tests. `construct/build_efg.py::build_sim_compiler_run` is a retired stub that
  **raises** (`:30-31`); `build_sim_fixture_efg_run` (`:138`) is a test-only fixture builder.
- **National race prior is deferred.** `race_prior_artifact = None  # national race prior selection is
  UF-independent; wired later` (`pipeline.py:528`) — a national run emits no `RACE-BRIDGE:emission_prior`,
  so a national intent whose `race_tensor_mode` plans/embeds a bridge would fail the manifest-artifact
  gate. A real, flagged gap (state/smoke wire it via `_race_bridge_prior_artifact` `:341`).
- **Silent-degrade fallbacks (auditable, bare `except`).** `_combine_national_artifacts` eager-concat
  fallback if the pyarrow stream throws (`sidra_national.py:129`); `_combine_facts_parquet` eager fallback
  (`sidra_population.py:98`); `plan_live_pipeline` swallows a metadata read in dry-run (`pipeline.py:394`);
  the EFG-workspace cleanup is best-effort (`compile.py:969`). None fabricate signal, but a malformed (vs
  absent) input degrades rather than raises.
- **Anti-silence done right (for contrast):** `measured_quantity_refs` loudly surfaces sidecars that
  resolve nowhere (`investigate.py:225` — else a count silently loses its §III.5 margin and leaks
  population into the residual scan); `_acquire_datasus` partial-coverage warning + `require_complete`
  fail-closed; the national `.window.json` reuse guard.
- **Scale limits live downstream, cross-referenced, not here:** national migration-flow refusal and the
  LDO residual-scan coarsening are in [`denominators.md`](denominators.md) / [`ldo.md`](ldo.md).
- **Deep-map status:** this page joins the completed core set —
  [`ldo.md`](ldo.md), [`efg.md`](efg.md), [`she.md`](she.md), [`datasus.md`](datasus.md),
  [`output.md`](output.md), [`denominators.md`](denominators.md) (see [`../MODULE_MAP.md`](../MODULE_MAP.md)).
