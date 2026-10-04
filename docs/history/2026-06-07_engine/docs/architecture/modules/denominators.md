# `denominators` — the population-denominator data plane (the exposure tensor)

A faithful code+math map of `src/pegasus/denominators/`: the demographic engine that reconstructs the
**population tensor** `(municipality_cod6, year, age_group, sex, race)` — the exposure denominators the
LDO's `count|exposure` margin conditions on. Two sub-packages: `population/` (SIDRA-anchored cube
construction + orchestration, moved from `sidra.population_cube`) and `reconstruction/` (the generic
Constrained-Tensor-Reconstruction solver math, moved from `she.reconstruction`) — see `__init__.py:6-7`.
Companion deep maps: [`efg.md`](efg.md) (materializes the denominator FieldNode), [`she.md`](she.md)
(assembles the panel), [`ldo.md`](ldo.md) (excludes the denominator from analytical outcomes, §IV).
Verify against live code (CLAUDE.md §IX). This page is at [`../MODULE_MAP.md`](../MODULE_MAP.md) depth-plus.

## 1. Responsibility

`denominators` owns the **person-time denominator** end-to-end: it turns disaggregated IBGE census strata
(SIDRA 9606/2093) + intercensal totals (6579) + DATASUS vital events (SIM/SINASC) into one dense,
census-anchored, projection-typed population tensor, and reconstructs the latent migration flow field.
It does **not** fetch SIDRA/DATASUS (that is `sidra`/`datasus`), compute rates or bridges (that is
`efg`/`she`), or estimate dependencies (that is `ldo`). It emits the tensor parquet + a `FieldNode`
carrying the `population_denominator_seed` role; downstream owns everything after.

## 2. The build spine — `population/build/orchestrator.py`

Entry: `solve_population_tensor_from_sidra_strata(*, population_strata_path, total_anchor_path,
output_path, census_2000_strata_path=None, mode='independent_denominator', sim_events_path=…,
sinasc_events_path=…, civil_registry_births_path=…, civil_registry_deaths_path=…,
race_bridge_prior_path=…, reconstruct_migration=False, max_iterations=12, tolerance=1e-5,
allow_national_gpu=False) -> PopulationTensorBuild` (`orchestrator.py:428`). The degenerate single-cell
counterpart is `solve_population_tensor_from_sidra_anchor` (`:889`). In production both are wrapped by the
**asset lifecycle** `resolve_or_build_population_tensor` (`assets/foundation.py:73` — build-once at
national+full-history, store immutable version, serve every query as a lazy `slice_population_tensor`)
and run in a **subprocess-isolated** child via `run_population_build_isolated` (`population/build/
isolated.py:74`; `taskkill /F /T` process-tree kill, RAM floor, 2 GPU tries → 1 CPU fallback).

Sequence (`solve_population_tensor_from_sidra_strata`):
1. Read 9606 strata → canonical `records_df` (`strata.py:47` project-then-parse: parse each distinct
   category tuple once + join, so 11.25M rows never become 11M dicts). Only categories mappable through
   `demographic_axis_maps.yaml` become strata; `UNKNOWN`/unmapped are dropped, not relabelled (`:32`).
2. Fold in the **2000 census** (table 2093) as a third anchor, CTR-disaggregated bracket→single-year
   (`_census_2000_records_from_facts`, `strata.py:110`; §4), then **AMC carve** (`census_2000.py:315`; §4).
3. **Closure panel** — stitch 9606 (census) + 6579 (intercensal) totals (`anchor.py:118`
   `load_combined_population_totals_frame`); vectorized `np.add.at` anchor scatter (`orchestrator.py:545-561`,
   NaN=absent); strata-sum fallback; then **FAL-POP-SV single-vintage re-anchor**
   (`_reanchor_closure_single_vintage`, `closure.py:108`; §4).
4. Flow priors — `_sim_death_priors`/`_sinasc_birth_priors` (`priors.py:174/249`) + the net-migration
   residual (`_migration_residual_totals`, `closure.py:67`; §4).
5. **Weights** — `PopulationObjectiveWeights` gated on data availability (`orchestrator.py:711`: anchor=10;
   aging/age_smooth iff multi-year/-age; birth iff births; death iff `sim_informed`+SIM prior;
   migration/migration_total iff ≥3 years / observed residual; race iff a real ≥2-category race axis).
6. **Two-layer solve** (`_solve_locality_blocked`, `orchestrator.py:146`): the `informative` gate (`:729`
   — ≥2 censuses OR a death/birth/migration flow term) decides. **Not informative** → return Layer-1
   closed-form directly (`_np_project_population` of the prior mean); **informative** → refine it. Built AND
   solved **one locality-block at a time** so peak RAM is O(block) not O(national) — the SIDRA objective is
   locality-separable (`_locality_separable`, `solvers.py:116`) so each block equals the exact sliced
   sub-problem (byte-identical, `:78`).
7. **Streamed emit** — `_write_population_tensor_parquet` (`orchestrator.py:292`): dictionary-coded Arrow
   batches (O(batch) RAM at 135M national rows), `.partial`-then-`os.replace`d atomically. Plus
   projection-envelope classification (§4) + optional migration-flow reconstruction (§4).

### 2.1 Layer 1 — the closed-form prior mean (`population/build/layer1.py:30`)

`interpolate_census_composition` is the data-poor reconstruction AND the solver warm start:
`P⁰_{s,t,a,x,r} = E_{s,t} · π_{s,t,a,x,r}`, where π is the locality's census joint (age,sex,race) share
**linearly interpolated in share-space** across census years, clamped outside the bracket, scaled to each
year's closure total. Census years reproduce their strata exactly. Vectorized on `_census_count_arrays`
(`indexing.py:68`, one `np.add.at` scatter, not a per-cell loop). When no flow term is informative this
IS the answer — the underdetermined (a,x,r) optimum equals the prior mean (`orchestrator.py:725-734`).

### 2.2 Layer 2 — the SPG solver (`reconstruction/`)

`solve_population_tensor_problem` (`solvers.py:19`) dispatches by the registry-selected `backend`:
`projected_gradient_small` → `solve_projected_gradient_small` (the live default); `sparse_block_coordinate`
/`sparse_admm`/`state_space_smoother` → their impls. `select_population_solver`
(`registries/population.py:141`) picks the first `active` spec for the mode — `projected_gradient_small_v1`
for problems ≤ `DENSE_NATIONAL_CELL_THRESHOLD`=10M cells (`:50,62`). **Nuance:** the national build records
`sparse_block_coordinate_v1` because metadata is selected on the *full* 135M cell count (`orchestrator.py:724`,
sort at `population.py:160`), but the blocked path re-selects **per ≤2M-cell block** → every block actually
executes `projected_gradient_small` (`_solve_locality_blocked` re-invokes the dispatch with `solver_id=None`,
`orchestrator.py:249`). So the emitted `solver_backend` is the *policy band*, not the executed math.

The real solver is `_solve_projected_gradient_vectorized` (`projected_gradient.py:319`): a **Spectral
Projected Gradient** (Birgin-Martínez-Raydán) — Barzilai-Borwein step `α=⟨s,s⟩/⟨s,y⟩` (`:392`), first step
`1/‖g‖_∞` (`:355`), GLL non-monotone line search against `max` of a 10-step window (`:373,403`), safeguarded
quadratic-interpolation backtracking capped at 8 (`:431`), stall-exit marks non-convergence (`:449`).
**Projection** = clip≥0 then per-(locality,year) Euclidean **simplex** onto `{P≥0, ΣP=closure}`
(`_np_project_population` → Duchi/Held `_simplex_project_rows`, `:174/151`); migration clipped to ±bounds.
An optional GPU torch mirror runs at study/state scale only (`prefer_gpu`, forced off nationally by the
`_GPU_MAX_SAFE_BLOCKS`=12 segfault guard, `solvers.py:75` / `projected_gradient.py:209`).

The objective `evaluate_population_loss` (`loss.py:171`) is **8 quadratic terms with analytic gradients**
over the latent `[P | net-migration η]`: (1) anchor `(P−anchor)²`; (2) aging cohort-survival identity
`P_{t,a}=P_{t-1,a-1}·surv+η` + terminal accumulation (`:213`); (3) birth `P_{t,0}=births_{t-1}+η` (`:239`);
(4) death `(rate·P−sim_deaths)²`, sim-informed only (`:255`); (5) race ILR-distance to census composition
(`:267`); (6) migration 2nd-difference temporal smoothness (`:289`); (7) migration_total per-(s,t) `Ση=net`
(`:302`); (8) age_smooth 2nd-difference over age (`:315`). Problem-invariant constants (masks, survival,
ILR basis, target race-ILR) are cached once on the problem (`_loss_constants`, `:202`).

## 3. Key data structures

- `PopulationTensorProblem` (`schema.py:58`) — the typed objective; `shape=(S,T,A,X,R)`, priors normalized
  to numpy in `__post_init__` (None→NaN sentinel), **stored float32** (`_STORE_DTYPE:22`, lossless ≤16.7M
  persons, solver promotes to f64). `PopulationObjectiveWeights` (`:43`) = the 8 default weights.
- `PopulationSolverTelemetry` / `PopulationTensorResult` (`schema.py:102/216`) — convergence + per-term
  objective; the result carries `tensor_values`/`migration_values` **by count only** (arrays persist to
  parquet, never inlined — a ~450MB-manifest bug, `:268`).
- `PopulationTensorBuild` (`orchestrator.py:85`) — the return: result + axes + migration paths +
  `migration_flow_skip_reason` + `anchored_range`/`max_projection_horizon`.
- `MigrationFlowReconstruction` (`migration.py:48`); generic **CTR** core (`reconstruction/problem.py`):
  `CTRProblem`/`ObservationTerm`/`QuadraticPenalty`/`MarginalConstraint` + `solve_ctr`
  (normal-equations-first, else Lipschitz/backtracking PG, `:165`).

## 4. Census-closure / migration / AMC sub-areas

- **Census closure (9606/6579).** `anchor.py` loads 9606 (var 93, census-year disaggregation) + 6579
  (var 9324, intercensal totals) and stitches them (9606 wins overlaps, `:118`). **FAL-POP-SV**
  (`geometric_interpolate_closure`, `:143` + `_reanchor_closure_single_vintage`, `closure.py:108`) replaces
  the 6579 *projection* vintage on intercensal years with constant-growth-rate interpolation between census
  enumerations — 6579's pre-census projection was revised down ~10M by the 2022 census, so mixing vintages
  injected a spurious ~5% denominator jump. Needs ≥2 anchors, else the prior closure is kept (telemetried).
- **2000 census + AMC** (`census_2000.py`). Table 2093's overlapping age brackets → a clean partition
  (`CLEAN_AGE_BRACKETS_2093`, `:33`, roll-ups never summed) CTR-disaggregated to single-year via the 2010
  shape (`disaggregate_bracket`, `:129`); undeclared-race mass **reconciled** into declared races by local
  composition, never dropped (`reconcile_undeclared_race`, `:57`). `carve_pre_census_children_frame` (`:315`)
  carves post-census municipalities out of their parents (mass-preserving) so a census total stays the
  enumerated total; parents come from the AMC crosswalk (`load_amc_crosswalk`, `:201`) or explicit genealogy
  overrides (`:219`), never inferred.
- **Net-migration residual + flow field.** `_migration_residual_totals` (`closure.py:67`) solves
  `NetMig(s,t)=E(s,t)−E(s,t-1)−Births+Deaths` for consecutive years, from SIDRA civil-registry totals
  (births 2609/var217, deaths 2683/var343) preferred, DATASUS event counts as fallback (`_sidra_vital_totals`
  /`_datasus_event_totals`, `:15/46`). `population/migration.py` reconstructs the latent O→D **flow field**
  `F(i→j,t)` from those net marginals via a production-constrained **gravity prior** (`_gravity_prior`,
  `:120`; origin emits `base_rate·Pop_i` split by `Pop_j/hops^γ`) + the net marginal + optional census O→D
  anchor, solved as the generic `migration_flow_instance` CTR (`solve_ctr`, `:237`); pairs bounded to
  `max_hops` contiguity (`hop_distances`, `:74`). Output induces the `geo.migration_affinity` kernel.
- **Projection envelope** (`projection_envelope.py:17`). `_classify_projection_years` types every year
  `census`/`interpolated`/`projected_{forward,backward}`/`unanchored` with horizon-growing uncertainty
  `σ(h)=√(base²+h·per_year²)`, `fragile` within 5 yr then `unreliable` — a projected denominator carries
  visibly wider bars.

## 5. Seams & contracts

- **Consumes:** SIDRA facts (9606 strata + total anchor, 2093 census-2000, 6579 intercensal, 2609/2683
  civil-registry) via `sidra`; DATASUS SIM/SINASC event parquets via `datasus` (lazy column projection,
  `_scan_select_present`, `priors.py:77`); the `RaceBridge` prior via `measurement.race` (admin race enters
  a real self-declared axis ONLY through the bridge, never a direct crosswalk — `priors.py:132`); the
  `demographic_axis` + `population` registries (canonical axes, solver policy).
- **Produces:** `population_tensor.parquet` (the exposure tensor) + migration flow/affinity parquets;
  and via `denominators.population.fields.build_sidra_demographic_population_fields` (`fields.py:45`) a
  `FieldNode` with `role=["population_tensor","population_denominator_seed","demographic_stratified",
  "source_field"]` (`:101`, `dashboard_safe=False`).
- **Downstream consumers of the tensor / seed role:** `efg/materialize.py` materializes the seed field
  (`:330,477`); `efg/bridges.py:98` pairs `population_denominator_seed` seeds with death/birth/admission
  seeds into `mortality_rate_bridge`/`birth_rate_bridge`/`admission_rate_bridge` (and blocks with
  `population_denominator_seed_missing` when absent, `:120`) — this is the `count|exposure` margin; and
  crucially `ldo/field_selection.py:49` **EXCLUDES** any `population_denominator_seed` field from
  analytical outcomes (§IV: a denominator is the exposure, not a determinant to test — it is mechanically
  collinear with its own strata and would manufacture CKA≈1 residual edges).

## 6. Known flags / debts

- **Orphaned-but-callable surface.** The generic CTR **certification gate** (`certify_ctr`/
  `assert_ctr_verified_promotion_allowed`, `certify.py:83/123`) has **no live `src/` caller** — the §II.3.1
  promotion gate is unwired, and computes nothing itself (it consumes a caller-supplied holdout-MAPE /
  variance / stability: **no p/n gate, no cross-fit**). Likewise `age_bin_disaggregation_instance`,
  `solve_population_tensor_blocked` (`solvers.py:123`, superseded by the orchestrator's own
  `_solve_locality_blocked`), and the ADMM / state-space-smoother backends are **never auto-selected**
  (only via explicit `solver_id`). Only `solve_ctr`+`migration_flow_instance` are live generically (migration).
- **National solver-backend mislabel.** Per §2.2 the emitted `solver_backend`/`solver_id`
  (`sparse_block_coordinate_v1`) is the national *policy band*; the executed per-block math is
  `projected_gradient_small` — a reader of the parquet metadata infers the wrong solver.
- **National migration flows refuse.** `MAX_DENSE_FLOW_PAIRS`=8000 (`migration.py:41`) — the ~16k queen-
  contiguity pairs at 5570 munis exceed it, so the dense CTR refuses. `flows.py:40-84` **surfaces** this
  (`RuntimeWarning` + `migration_flow_skip_reason`, never silent, §V) and falls back to structural
  contiguity. A sparse backend is the documented (unbuilt) scaling path.
- **Deliberate iteration cap.** `max_iterations=12` (`orchestrator.py:445`): with one census + free
  migration the (a,x,r) structure is underdetermined and its optimum IS the census warm start, so few
  steps suffice; well-conditioned runs early-stop. Non-convergence is flagged + widens uncertainty.
- **Stale docstrings.** `fields.py:11-13`, `schema.py:270`, `projected_gradient.py:125` still reference the
  pre-move `she.reconstruction` / `sidra.population_cube.build` paths — a §IX doc-vs-code drift.
- **Silent swallows (auditable, non-raising).** `_pairs` (`strata.py:23`) / `_is_total_9606`
  (`anchor.py:63`) / `_detect_classification_id` (`fields.py:41`) `except Exception` on a malformed
  category tuple (drops the row); `torch_solver.py:44` silently disables the GPU plan; `solvers.py:178`
  silently skips BLAS thread-pinning if `threadpoolctl` is absent. None raise on malformed (vs absent) input.
- **Deep-map status:** this page **completes** the deep-map set — [`ldo.md`](ldo.md), [`efg.md`](efg.md),
  [`she.md`](she.md), [`datasus.md`](datasus.md), [`output.md`](output.md), denominators (see
  [`../MODULE_MAP.md`](../MODULE_MAP.md)).
