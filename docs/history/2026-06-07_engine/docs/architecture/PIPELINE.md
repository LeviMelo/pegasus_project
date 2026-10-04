# PegaSUS — the operational picture (end-to-end)

**Read this first, every time.** This is the whole object in one page so we stop forgetting core entities
(the population tensor) and chasing orphan paths. Verified against live code 2026-07-13 via a 6-way
parallel code reconnaissance; file:line refs drift — trust the code, fix this doc. Deep per-module maps
are under [`modules/`](modules/); this page is the *flow that ties them together*.

## The object in four stages

PegaSUS is, at its core, four moves:

```
1. INGEST + ONTOLOGISE   raw DATASUS (SIM/SINASC/SIH/CNES) + SIDRA
                          → patched, decoded, canonical data with a shared ontology
2. ENRICH + MAKE RELIABLE (a) build the SYNTHETIC POPULATION CUBE (the demographic tensor):
                              census strata extrapolated across all years, solver-reconstructed
                          (b) RACEBRIDGE: reconcile administrative race (DATASUS) with
                              self-declared census race (the tensor)
3. COMPILE → ENTITIES     the EFG turns data into statistical objects via operators:
                          mortality/hospitalisation/births as age×sex×race-specific
                          COUNTS, RATES, joint strata, cause-specific, clinical, procedure …
4. HUNT RELATIONSHIPS     the LDO finds statistical dependencies among those entities
                          → certified hypothesis edges
```

The single most important thing to hold: **stage 3 forms a rate as `numerator ÷ denominator`, where the
numerator is a DATASUS event count and the DENOMINATOR is the population tensor from stage 2a — never a
raw SIDRA table.** (See INVARIANTS.)

```
intent JSON (config/intents/*.json, validated against UserIntent)
  │   workflows/pipeline.py::run_live_pipeline (pipeline.py:478)   [CLI: `pegasus run`]
  ▼
STAGE 1  ACQUIRE + NORMALISE
  ├ DATASUS  MicrodatasusClient (R bridge) → normalize_{sim,sinasc,sih,cnes}_events
  │          → data/normalized/datasus/{system}/…/canonical.parquet     role: processed_events
  └ SIDRA    SidraClient → normalize → data/sidra/…                     roles: normalized_facts (9606/6579
             (national: → data/normalized/national/{system}__{role}.parquet)   totals), population_strata (9606 strata)
  │
  ▼  one merged manifest: data/manifests/runs/live_*.source_manifest.json
STAGE 2  ENRICH
  ├ 2a POPULATION TENSOR   denominators/population/build::solve_population_tensor_from_sidra_strata
  │    (built once, national, persistent)  → data/assets/population_tensor/v2025.3/population_tensor.parquet
  │                                          role: population_tensor   [SKIPPED in official_sidra_anchor mode]
  └ 2b RACEBRIDGE          registries/race_bridge + measurement/race  (live crosswalk; identity C today)
  │
  ▼  workflows/compile.py::run_compile → _run_compile_impl  (7 phases)   [CLI: `pegasus compile`]
STAGE 3  COMPILE (EFG)
  ├ substrate  efg/materialize.py::materialize_substrate_bundle
  │              denominator = _population_solver_materialized_fields (tensor → total+marginals+JOINT cell)
  ├ spine      efg/dag/spine.py::build_efg   numerators: event_count, ICD strata, demographic marginal+joint,
  │              clinical, procedure ; RATES via RN pairing on equal demographic-axis frozenset
  └ executor   efg/executor/run.py::execute_efg_result → per-field tensors
  │            → run-dir: V_fields, E_DAG, Q_tensor, VariableDictionary, Tables/efg_tensors/…
  ▼  (iff intent.execution_stage == "investigate")
STAGE 4  INVESTIGATE (LDO)
       workflows/investigate.py::run_investigate → she/panel.py::compile_common_panel (stratum pivot)
       → ldo/orchestrator.py::run_ldo (CPW sparse+low-rank ADMM + lags + structural priors)
       → Hypotheses.parquet  (the certified dependency edges — the deliverable)
```

---

## Stage 1 — Ingest → data ontology
`workflows/pipeline.py`, `datasus/`, `sidra/`, `config/registries/`

- **DATASUS fetch** (live path): `pipeline.py:190 _acquire_datasus` → `datasus/client_microdatasus.py:35 MicrodatasusClient.fetch_systems` → per-(UF,year|month) chunks (`datasus/manifests.py:300`) → `datasus/subprocess.py:175 fetch_datasus_chunk` (Rscript on `datasus/r_scripts/fetch_process_microdatasus.R`, v4 zstd-canonical bridge). Cache keyed on `processed.parquet`.
- **DATASUS normalise** (raw DBC codes → canonical SHE columns, fully vectorised Polars): `pipeline.py:151 _normalize_datasus` → `datasus/normalize/{sim,sinasc,sih,cnes}.py::normalize_*_events`. Shared decode library `datasus/normalize/primitives.py::Cols` (date / municipality cod6→cod7 / sex / race_admin / cnpj mod-11 / icd_norm). Codebook `datasus/normalize/codebook.py` ← `config/registries/datasus/datasus_codebook.yaml`.
- **SIDRA**: `sidra/api.py SidraClient` → `sidra/plan.py` → `sidra/extract.py` → `sidra/facts.py::write_facts_parquet`. Population acquisition: `workflows/acquire/sidra_population.py` (`_acquire_sidra_population` 9606+6579, `_acquire_sidra_population_strata` 9606 sex×race×age, `_acquire_sidra_census_2000_strata` 2093, `_acquire_sidra_civil_registry_vital` 2609/2683).
- **The data ontology** (reference registries, git-tracked, sha256-pinned): CID-10 `config/registries/disease/cid10.parquet` (V2008, 14 233 codes) via `disease/cid10_table.py`; SIGTAP `config/registries/health/sigtap_procedures.parquet` (202607) via `datasus/sigtap_table.py`; demographic axis maps `registries/demographic_axis.py`; clinical axes `registries/clinical_axis.py` ← `config/registries/health/clinical_stratification_axes.yaml`.
- **Artifact-role tagging** (`source_artifacts/contracts.py::ALLOWED_ARTIFACT_ROLES`): DATASUS canonical → `processed_events`; SIDRA 9606+6579 totals → `normalized_facts`; SIDRA 9606 strata → `population_strata`; solver output → `population_tensor`; race bridge → `emission_prior`; compendium → `context_facts`.

## Stage 2 — Enrich & make reliable

### 2a. The population tensor (synthetic demographic cube) — THE denominator
`denominators/population/build/`  ·  asset: `data/assets/population_tensor/v2025.3/population_tensor.parquet`

The demographic tensor is a **solver-reconstructed, national, build-once, persistent** object: census
sex×age×race *strata* extrapolated across the whole year range, constrained to official yearly *totals*,
refined by vital events and migration. **This is the exposure denominator for every rate.** It is not the
raw SIDRA census table; it is *built from* it.

- **Build entry:** `denominators/population/build/orchestrator.py:428 solve_population_tensor_from_sidra_strata` (moved here from the now-stale `sidra.population_cube` / `she.reconstruction` names still cited in many docstrings). Two-layer, per-locality-blocked (peak RAM O(block)):
  - *Layer 1* — closed-form census-composition interpolation (`build/layer1.py`) scaled to each year's closure total = the warm start, and the final answer in the data-poor case.
  - *Layer 2* — refine (only when `informative`: ≥2 censuses or death/birth/migration weight>0) via `denominators/reconstruction/solvers.py`; the auto-selected per-block backend is **projected-gradient (SPG)** despite the persisted `solver_id` label saying `sparse_block_coordinate` (a verified metadata mislabel).
  - National scale runs in a hard-timeout **child subprocess** (`build/isolated.py:172`, GPU re-enabled under isolation).
- **Inputs to the solve** (`orchestrator.py`): anchors = census 9606 (2010/2022) + 2093 (2000); closure totals = census + intercensal **EstimaPop** (SIDRA 6579), re-anchored to census vintage (`anchor.py`); SIM deaths / SINASC births as loss terms; migration residual `NetMig = ΔTotals − Births + Deaths` (prefers civil-registry 2609/2683).
- **Modes** (intent `population_mode` → solver mode): `official_sidra_anchor` = **no solver** (single directly-observed census, raw strata used directly — the fallback below); `independent_population_tensor` = solver reconstructs, no death feedback; `sim_informed_population_tensor` = adds SIM-death feedback (downgrades to independent if no SIM prior). Mapper `compile.py:248 _population_tensor_mode_to_solver_mode`.
- **The asset** (`assets/foundation.py`, `assets/store.py`): build-once key = content-hash of inputs+mode+code_version; version `v{max_year}.{seq}`, immutable append-only, `data/assets/index.json` registry. Only `build_scope == national_full_history` is persisted. On-disk today: `v2025.3` = 146,294,460 rows, 26 years (2000–2025), 5571 munis × 101 ages × 2 sex × 5 race, `independent_denominator`, served by `latest()`. Query = `slice_population_tensor` lazy year-filter — never a re-materialisation.
- **Consumption:** the sliced tensor re-enters the compile as `SourceArtifactRef(SIDRA, population_tensor, materialized_external)` (`compile.py:420`), producing the denominator fields (Stage 3).

### 2b. The RaceBridge
`registries/race_bridge.py`, `measurement/race.py`, `measurement/race_ecological.py`

DATASUS records **administrative** race (as coded by a clerk); the census/tensor carries **self-declared**
race. Dividing an admin-race numerator by a self-declared denominator is an ecological mismatch, so the
EFG requires a bridge.

- **Live mechanism (wired):** per-cell crosswalk `measurement/race.py:220 bridge_admin_race_group_counts` → `fixedc_dynamic_weight_bridge`; consumed by the population-tensor build (`build/priors.py:159`) and the EFG count executor (`efg/executor/kernels.py:305`). The prior is selected at compile from `config/registries/demographic/race_bridge_priors.yaml`.
- **Current C is IDENTITY.** Only `identity_admin_as_selfdeclared_v1` has `enabled_for_compile: true` — a literal 5×5 identity that makes NO reclassification correction (admin passed through as self-declared). The confusion-matrix correction that *would* fix branca/parda/preta discordance lives in `measurement/race_ecological.py` (`fit_ecological_race_deconvolution`) + `measurement/race_calibration.py::calibrate_race_bridge_prior` — **built and validated but UNWIRED** (imported only by tests). This is the real open race gap (W-RACE-2), not a bug.
- **EFG declaration + gate:** denominator race tagged `race_axis_type = ibge_self_declared` (`materialize.py:512`); a bridged numerator tagged `self_declared_bridged` + role `race_bridge_posterior` (`operators.py:326`). The `race_bridge_required` alignment error (`align.py:152/167/191`) fires only for **raw admin race with no bridge configured** (i.e. `race_tensor_mode: decoupled`). With a bridge prior (even identity), the race rate forms.

## Stage 3 — Compile → statistical entities (the EFG)
`workflows/compile.py`, `efg/materialize.py`, `efg/dag/spine.py`, `efg/executor/`

`run_compile` (`compile.py:1046`) → `_run_compile_impl` runs 7 phases: resolve plan + source-reality gate → hash/manifest sources → **materialise population + substrate** → derive stage status → serialise bundle → flush + investigate → validate. The source-artifact manifest must be `materialized_external` and carry SIM-DO + SINASC `processed_events` + exactly one SIDRA `normalized_facts` (+ CNES/SIH, context, race-bridge as configured); the population tensor is **built during compile** (or reused from the asset), not a required manifest input except `population_strata` in tensor mode.

- **Denominator admission** (`efg/materialize.py::materialize_substrate_bundle`):
  - PRODUCTION — `_population_solver_materialized_fields` (`materialize.py:425`): reads the `population_tensor` artifact, emits one field per marginal — `total` (crude) + `age_group` + `sex` + `race` — **plus the JOINT age×sex×race cell** (`materialize.py:490`), the only partner a joint count can divide.
  - FALLBACK — `_sidra_demographic_population_materialized_fields` (`materialize.py:376`): raw SIDRA strata, **returns `[]` (disabled) whenever a solver tensor is present** (`materialize.py:389`). Live only in `official_sidra_anchor` mode.
- **Numerators** (`efg/dag/spine.py::build_efg`), per (artifact, carrier) event group: `event_count`; ICD cause-specific strata (chapter/block/category/curated, `requested_icd_levels`); demographic **marginal** strata (one per axis in `available_demographic_axes` — the set populated *only* from admitted demographic denominators, `spine.py:223`); **joint** multi-axis strata (age×sex×race, cause×demographic, `requested_joint_strata`); clinical axes (bed_specialty/place_of_death/… intra-carrier); procedure (SIGTAP); σ-restricted clinical events; Ψ functional fields.
- **Rate formation** (the RN pairing, `spine.py:482-525`): denominators indexed by `(carrier, demographic-axis frozenset)`; a numerator pairs **only** with the denominator on its *own* axis frozenset (a `{sex}` count ÷ the `{sex}` marginal, a crude/ICD count ÷ the `{}` total, a joint count ÷ the joint cell). Emits an `RN` edge (numerator) + a `denominator_link` edge (denominator). Rate roles (`mortality_rate`/`hospitalization_rate`/`birth_rate`) are declared in `config/registries/health/clinical_event_definitions.yaml`, not hardcoded.
- **Executor** (`efg/executor/run.py::execute_efg_result`, kernels in `kernels.py`): `_count_tensor` (streaming group_by→len, handles joint `stratify_specs`), `_population_solver_tensor` (streamed marginal/joint over the national tensor), `_compute_rn_ratio` (tensor÷tensor on intersecting keys + a count|exposure MeasuredQuantity sidecar). Output → `Tables/efg_tensors/<field_id>.parquet`.

## Stage 4 — Hunt relationships (the LDO)
`workflows/investigate.py`, `she/panel.py`, `ldo/`

- **Entry:** `run_investigate` (`investigate.py:329`) assembles the panel (`she/panel.py:311 compile_common_panel`), restricts to `analytical_variable_ids`, and calls `ldo/orchestrator.py::run_ldo` (or `run_ldo_multiresolution` for national municipality×year). The **stratum pivot** (`panel.py:417`) turns per-stratum rate fields into `{base}~strat~{axis}={value}` variables (caps 24 marginal / 120 joint; over-cap → denominator-weighted rollup or a loud collapse warning).
- **Estimator:** CPW sparse+low-rank ADMM `Ω = S − L` (`ldo/lowrank.py:148`) + lag extension (`ldo/lags.py:71`, adaptive K). Structural priors **live by default**: disease L_D (adaptive-ℓ1 + quadratic Laplacian), age-ordinal Laplacian (`ordinal_prior.py`), spatial GMRF whitening, common-trend detrend. Off by default (wired): temporal-lag-smoothness (`gamma_temporal=0`), AR(1) whitening, StARS.
- **Inference machinery (live):** stability selection (Place×Time subsampling), n_eff dependence deflation (spatial Moran + temporal Bartlett), **Benjamini-Yekutieli FDR enforced**, residual HSIC scan with block cross-fit + in-sample-bias gate + CKA effect-size floor, mechanical-overlap guard, LiNGAM + collider orientation, certification conjunction gates + standing-abort backstop.
- **Output:** **`Hypotheses.parquet`** — typed `LinkRecord`s (`ldo/records.py`, per-row `certification_status` ∈ {selected, descriptive}, `causal_rung`, `fdr_qvalue`, …) + `Coverage.json` + optional `spatial_fields/`. Query layer: `output/query/engine.py`.

---

## INVARIANTS & common confusions — read before touching denominators

1. **The rate denominator is the population TENSOR asset, never a raw SIDRA table.** Raw census strata are an *input to the solver*, not a denominator. The raw-strata admission (`_sidra_demographic_population_materialized_fields`) is a **disabled fallback** — it returns `[]` whenever a `population_tensor` artifact is present (`materialize.py:389`), and is live only in `official_sidra_anchor` mode.
2. **`population_mode` picks the denominator path.** `official_sidra_anchor` → no solver, raw single-census strata (only coherent for a fully-observed census year, e.g. 2022 alone). `independent_population_tensor` / `sim_informed_population_tensor` → solver builds (or reuses) the tensor. A multi-year run needs a tensor mode; asking for `official_sidra_anchor` over a year range is incoherent.
3. **A slice compile must carry the tensor.** To exercise real denominators on a quick slice, put the tensor asset (or a state slice of it) in the manifest as a `population_tensor` artifact — do **not** hand-feed raw census facts as `population_strata` and force the fallback.
4. **The LDO writes `Hypotheses.parquet`.** `ModelAssociations.parquet` and `ResidualAssociations.parquet` are **retired PIRS-era keys**, kept as anti-silence empties — never read them for findings.
5. **The age×sex×race RATE forms today** (via the identity bridge) when `race_tensor_mode` embeds/bridges race and the joint denominator cell exists. `race_bridge_required` blocks only *raw admin* race (`decoupled` mode). The open race gap is the *ecological C correction* (unwired), not rate formation.
6. **The stage-workspace seam rewrites paths.** `V_fields`/`Q_tensor`/`E_DAG`/`efg_tensors` are written to `{run_dir}__efg_stage_workspace/` then flushed into `run_dir` and the workspace deleted; `V_fields.path` / `measured_quantity_ref` carry stale workspace paths — consumers reconstruct `run_dir/Tables/efg_tensors/<basename>` (`investigate.py:206`).

## Persistent assets (the physical inventory)

| Asset | Disk path | Producer → consumer |
|---|---|---|
| **Population tensor** | `data/assets/population_tensor/v2025.3/population_tensor.parquet` (146M rows, national, build-once) | `compile.py::_build_population_tensor_artifact` → `materialize._population_solver_materialized_fields` |
| Normalised DATASUS | `data/normalized/datasus/{system}/…/canonical.parquet`; national `data/normalized/national/{system}__{role}.parquet` | `pipeline._normalize_datasus` → SHE substrate |
| SIDRA facts (live) | `data/sidra/{population,population_strata_demographic,…}_<UF>_…/` | `_acquire_sidra_*` → tensor build + SHE |
| CID-10 | `config/registries/disease/cid10.parquet` (+manifest) | `disease/cid10_ingest.py` → EFG disease axis |
| SIGTAP | `config/registries/health/sigtap_procedures.parquet` (+manifest) | `datasus/sigtap_ingest.py` → procedure axis |
| Spatial centroids / contiguity | `config/registries/spatial/municipality_{centroids,contiguity_queen,amc_crosswalk}.parquet` | geo build → LDO spatial kernel |
| Run bundle | `data/runs/<run_id>/` | `run_compile` → `run_investigate` / dashboard |

## The run-dir bundle (`data/runs/<run_id>/`)

`UserIntent.json` (frozen intent) · `RunConfig.json` (geo/`population_mode`/`race_tensor_mode`/stage plan/registry+source hashes) · `ReproducibilityManifest.json` · `V_fields.parquet` (materialised FieldNodes) · `Q_tensor.parquet` (per-field QState: n_eff, denom_fragility, moran_i, race_bridge_cv …) · `E_DAG.parquet` (edge lineage) · `VariableDictionary.parquet` · `Warnings/FailedBranches/QuarantinedFields/ForcedFields.parquet` · `Hypotheses.parquet` (LDO output) · `Coverage.json` · `Tables/{efg_autonomous_manifest.json, efg_execution_manifest.json, efg_tensors/<field_id>.parquet(+.measured_quantity)}`.

## Orchestration & the UserIntent

`run_live_pipeline` (`pipeline.py:478`, CLI `pegasus run`) drives: load intent → branch on `execution_scale` (national fans out 27 UFs + combines; state/smoke single-UF) → acquire DATASUS + SIDRA → write one source manifest → `run_compile(require_materialized_external=True)` → (iff `execution_stage=="investigate"`) `run_investigate`. **UserIntent** (`core/schemas.py:25`, `extra="forbid"`): `run_profile`, `execution_stage` (validate/compile/investigate), `execution_scale` (smoke/state/region/national), `geography`, `time`, `health_seeds`, `population_mode`, `race_tensor_mode`, `context_policy`, `budget`, ….

## Deep maps (go here for detail)

`modules/workflows.md` (orchestration — reliable, current) · `modules/denominators.md` (tensor build math) · `modules/efg.md` (compile engine — deep) · `modules/she.md` (panel) · `modules/ldo.md` (inference — deep) · `modules/datasus.md`, `modules/output.md`, `modules/registries.md`. Repo index: `MODULE_MAP.md`. Redesign backlog: `ARCHITECTURAL_DEBT.md`.

## Orphans & stale-doc index (don't re-chase these)

- Stale **module paths** in docstrings: `sidra.population_cube.*` / `she.reconstruction` → now `denominators.population.build` / `denominators.reconstruction` (`fields.py:11`, `materialize.py:428`, `core/schemas.py:63`, …).
- `MODULE_MAP.md:46-49` implies the **ecological race deconvolution is operative** — it is not; live C is identity.
- `ldo/disease_prior.py:10-16` docstring says the quadratic Laplacian is "not yet implemented" — it **is** wired-live (`lowrank.py:389`, `orchestrator.py:239`).
- Retired/empty: `ModelAssociations`/`ResidualAssociations` (PIRS-era), `support_index.parquet` (orphan writer, no reader), `_moran_proxy` (deprecated placeholder).
- Orphan disk paths: `data/denominators/national_population_tensor/` (pre-FAL-POP-VER, zero `src/` refs), `data/processed/sidra/facts/` (fixtures/smoke; live facts are under `data/sidra/`), `data/intermediate/{efg,pirs,she}/` (empty scaffolds).
- Off-live-path callables: `workflows/construct/*` (compile inlines the engines), most `workflows/acquire`/`report` CLI wrappers, `workflows/acquire/ingest_sidra.py`; CLI `population_app` (empty) + `efg_validate_race_bridge_prior` (undecorated).
- Real gap: **national race prior deferred** — `pipeline.py:528 race_prior_artifact = None`, so a national intent that plans a bridge fails the manifest-artifact gate.
- Metadata mislabel: population-tensor `solver_id`/`solver_backend` columns say `sparse_block_coordinate` but the executed per-block math is projected-gradient (SPG).
