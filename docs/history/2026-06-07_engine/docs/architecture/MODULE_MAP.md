# PegaSUS module map — the repo-wide architecture index

A navigable, faithful map of every `src/pegasus/` module: its role, primary entry points, key data
structures, and status. This complements [`PIPELINE.md`](PIPELINE.md) (the end-to-end data *flow*) and
[`DOCS.md`](../../DOCS.md) (the *plans* precedence index). Two modules have **deep** code+math maps —
[`modules/ldo.md`](modules/ldo.md) and [`modules/efg.md`](modules/efg.md); the remaining data-plane
modules are mapped here at medium depth (deep maps are the parallelizable follow-up). Verify against the
live code (CLAUDE.md §IX). Consolidated 2026-07-12.

## The spine (analysis heart)

| module | role | primary entry point |
|---|---|---|
| **efg** | Entity-Field Graph — compile source events → typed `FieldNode` graph | `dag/spine.py::_build_efg_base`, `executor/run.py::execute_efg_result` → **[deep map](modules/efg.md)** |
| **she** | Substrate Harmonization Engine — normalized events + EFG tensors → the `CommonPanel` | `she/panel.py::compile_common_panel` → **[deep map](modules/she.md)** |
| **ldo** | Latent Dependency Operator — panel → certified dependency edges | `ldo/orchestrator.py::run_ldo` → **[deep map](modules/ldo.md)** |
| **workflows** | stage orchestration (acquire → compile → investigate → report) | `workflows/{compile,investigate,pipeline}.py::{run_compile,run_investigate}` |

## Data plane (source → normalized → denominators)

### `datasus` (~5.2k LOC) — DATASUS fetch + normalizers → **[deep map](modules/datasus.md)**
Owns BOTH the **R-bridge fetch** (subprocess/heartbeat/cache of the microdatasus R process → per-chunk
`processed.parquet`) and the vectorized raw→canonical decode. Decode primitives on shared `Cols`/`vec.Cols`
(`decode_sim_idade`, `decode_sih_age`, `decode_datasus_date/hour`, `filter_cnpj`, `clamp_bool`); an in-house
**codebook registry** replaces microdatasus `process_*`. Row-batched decode (memory-bounded, byte-identical
parallel); cache keyed on `processed_sha256` (75784a3). Record/scalar fns are the oracle — but only
*primitive*-level parity is tested (see the map's §4/§6). The combine→canonical *driving* is in `workflows/pipeline.py`.

### `sidra` (~2.1k LOC) — IBGE SIDRA socioeconomic fetch
Pulls IBGE SIDRA tables (the socioeconomic context) via a **compendium registry** (`load_sidra_compendium`,
`select_compendium_tables`); `classification_expr`/`locality_expr`/`pipe_expr` build the API requests;
`stable_request_hash` content-addresses the fetch. Parallel/isolated fetch with 599-retry; compact
(no duplicate raw-JSON) writes. Emits `SIDRA__*_facts.parquet` (context, census strata, civil registry).

### `denominators` (~6.4k LOC) — the population/demographic data plane → **[deep map](modules/denominators.md)**
The demographic engine that produces the **population tensor** (the exposure denominators the LDO's
count|exposure margin conditions on). Subpackages: `population/build` (the two-layer solve — closed-form
census interpolation prior + an 8-term Spectral Projected Gradient refine only when a flow term is
informative; locality-blocked, streamed, ~5-6 GB peak after POP-PERF), `population/migration` (latent O→D
flows from a net residual via gravity + net-marginal CTR), plus census-anchored closure (SIDRA 9606/6579 +
2093 census-2000 + FAL-POP-SV single-vintage re-anchor) and AMC carve. Fields carry the
`population_denominator_seed` role — the LDO **excludes** these from analytical outcomes (§IV, they are
exposures not determinants). Map flags: the national `solver_backend` label is the *policy band*, not the
executed per-block math; the CTR certification gate + ADMM/state-space backends are orphaned-but-callable.

### `measurement` (~1.4k LOC) — measurement-model bridges
`load_race_bridge_prior` + `bridge_admin_race_group_counts` + `fixedc_dynamic_weight_bridge`: the **live**
**RaceBridge** (administrative → self-declared race) — a per-cell crosswalk whose confusion matrix C is
currently the **identity** prior (`identity_admin_as_selfdeclared_v1`, no reclassification correction). The
hierarchical-Poisson **ecological deconvolution** that would make C non-trivial (`race_ecological.py` +
`race_calibration.py`, W-RACE-2) is **built + validated but UNWIRED** — reachable only from tests; the live
compile never calls the calibration. Do not read the deconvolution as operative. Also
`directly_standardized_rate`/`standardize_grouped` (age-standardization) + `load_reference_population`.

## Geography & disease semantics

### `geo` (~1.7k LOC) — the spatial substrate
The `SpatialWeightGraph`: `load_adjacency` (structural queen contiguity, cod6), `spatial_graph` (blocks
+ symmetric-normalized Laplacian for the GMRF whitening), real IBGE **centroids** via geobr
(`load_municipality_centroids`, `build_centroids_artifact`), and the alternative kernels the LDO can opt
into — `knn_distance_graph`, `distance_decay_edge_weights`, `gravity_edge_weights`, `estimate_spatial_range`.
`contract_to_amc` harmonizes municipality boundary changes. (Kernel choice is empirically marginal for
the residual layer — see `LDO_DECONFOUNDING_DESIGN.md` §7d.)

### `disease` (~0.9k LOC) — the Disease Semantic Axis (MSD-II §II.13)
The ICD/CID adapter (`cid`, `add_dot`/`remove_dot`, `is_valid_who`, `ancestors`/`descendants`) over
`simple-icd-10` (CID-10 authoritative; dengue A90/A91 not coerced) + `icd-mappings` (CCSR/CCI/CCC) + the
Brazilian ICSAP list; a multi-label provenance-typed concept registry; and the `DiseaseGraph` structural
prior `L_D` the LDO folds into its precision (DIS-04, Laplacian-regularized graphical lasso). The
per-variable ICD `code_set` here feeds the §5.3 mechanical-overlap/nesting guard.

### `causal` (~0.5k LOC) — the causal escalation ladder (MSD-III Part IV)
Rung-1 non-Gaussian orientation (`lingam_pairwise_direction`, `is_non_gaussian`, `is_collider`,
`orient_links`) and rung-2 quasi-experimental escalation (`interrupted_time_series`). Wired live into the
LDO output (`orient_links` on the emitted edges; ITS on directed edges with a detected structural break).

## Output & infrastructure

### `output` (~3.1k LOC) — the 17-key run bundle + query layer → **[deep map](modules/output.md)**
`create_empty_output_bundle` (schema seed) + `OutputBundleManager` (atomic flush, id-keyed
`append_replace_rows`) + `validate_output_bundle`; the **run catalog** (`scan_runs`/`find_runs`); and the
**Output Query Layer** (FEAT-P3+P4 — `materialize_query` edge/count/rate; the natural home for edge
credibility banding, §7f). Measured caveats in the map: the live `Hypotheses` is the LDO **LinkRecord**
schema (not the seed), so the validator's inference-invariant checks are live no-ops, `_enrich_edges`
enrichment is mostly stripped at write, and the query layer/catalog are orphaned-but-callable.

### `compute` (~1.6k LOC) — the numerical backend policy
Central sizing/device policy (`resources.py`, `devices.py`, `kernels.py`, `torch_backend.py`,
`random.py`): the compute envelope, memory-budgeted parallelism (DP-2), the torch/GPU seam, and
deterministic seeding. The LDO/EFG consult this, never hardcode device/dtype/worker counts.

### `registries` (~2.5k LOC) — config registry loaders
The typed registry layer over `config/registries/` (datasus/health/demographic/ontology/fields/inference/
spatial subdirs). REG-07 unified the 3 divergent loader contracts into one typed registry with a
decode-validated merge. `validators.py` is the load/validation surface.

### `core` (~0.8k LOC) — shared schemas & enums
`schemas.py` (`FieldNode`, `Lineage`, `DeltaResult`, `AlignmentResult`, `OperatorResult` — the EFG type
atoms) and `enums.py` (`FieldState`, `MaterializationState`). The content-addressing (`field_id_from_lineage`)
lives here. `hashing.py`, `text.py`.

### `sources`, `source_artifacts`, `storage`, `assets`, `dashboard`, `validation`, `acceptance`, `pirs`
Supporting planes: `sources` (source-specific transform/context modules); `source_artifacts` (the
compile-time **source-reality contract** — a materialized-external manifest is required to compile,
`compile_policy.py`); `storage` (the production storage boundary — DATASUS v4 bridge, zstd, no raw.rds);
`assets` (versioned build-once assets); `dashboard` (read-only views); `validation` (holdout /
demographic-sanity); `acceptance` (bundle contracts); `pirs` (~0.4k LOC residual — the old slice-zoo was
exterminated; what remains is thin).

## Status / where to look next
- **Deep maps:** `modules/{ldo,efg,she,datasus,output,denominators,workflows,registries}.md` — the analysis
  spine, the data plane, the orchestration spine, and the config layer. The rest (sidra, disease, causal,
  measurement, geo, compute, core, storage) are at medium depth above; deepen them as touched.
- **Registry note (measured):** `REGISTRY_FILES` lives in `registries/events.py`, not `validators.py`; and
  REG-07 unified the `is_active` admission rule + `RegistryEntry` shim, NOT the three load paths (loader
  mtime-cache / generic fresh-read+sha256 / source_fields bespoke still coexist) — see `modules/registries.md`.
- **Governing plans + precedence:** `../../DOCS.md`. **Redesign backlog:** `ARCHITECTURAL_DEBT.md`.
