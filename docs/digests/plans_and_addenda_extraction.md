
Read in full (READ-ONLY, nothing edited): PEGASUS_ARCHITECTURE_ADDENDUM.md, PEGASUS_DISEASE_SEMANTIC_AXIS.md, PEGASUS_OPERATIONAL_IMPLEMENTATION_PLAN.md, PEGASUS_REFACTOR_MASTER_PLAN.md, PEGASUS_REDESIGN_ROADMAP.md, PEGASUS_COMPLETION_ROADMAP.md, PEGASUS_FEATURE_PROPOSALS.md, PEGASUS_DATA_LIFECYCLE.md, PEGASUS_OUTPUT_QUERY_LAYER.md, HANDOFF_2026-07-09_population_build_and_project_state.md, all in `C:\Users\Galaxy\LEVI\PegaSUS`.

Below is the full technical extraction, organized per document, as requested.

---

# 1. PEGASUS_ARCHITECTURE_ADDENDUM.md

**Purpose/status:** Companion to `PEGASUS_COMPLIANCE_AND_REMEDIATION.md` (that report fixes correctness; this addresses architecture/extensibility). Audience: PegaSUS devs + coding agents. Evaluates 12 raised proposals, triaging each Accept/Refine/Defer. Only #8 (higher-order functionals) is deferred; nothing rejected outright.

**Core thesis (§1):** "PegaSUS is a compiler platform. It onboards heterogeneous public-health data through declarative registries backed by named code plugins; it processes that data through two parallel lifecycles — an event lifecycle (SIM/SIH/SINASC/CNES record tables) and a cube lifecycle (SIDRA/census/GDP/sanitation OLAP tables) — that converge on a compiled common support panel; it reconstructs missing structure (population, fine age bins, latent context) through one shared constrained-tensor-reconstruction kernel with a certification gate; it instantiates epidemiological concept families into concrete legal fields via the EFG; and it investigates them via PIRS."

**Four structural pillars:**

1. **Registry Platform (§2).** Principle: "registries are executable authority, not post-hoc metadata." Target: "declarative routing + named code callables" — YAML declares *what* (route/decoder/output field/axes), a `CALLABLE_REGISTRY: dict[str, Callable]` (in `pegasus/registries/callables.py`) provides *how*. Registry set target state: `source_adapters.yaml`, `source_routing.yaml` (raw→canonical, = SHE-NORM-01 Path A), `canonical_fields.yaml` (kept), `composite_decoders.yaml`, `concepts.yaml`, `operators.yaml`, `spatial_graphs.yaml`, `cube_compendium`, `model_registry.yaml`. `SourceAdapter` plugin `Protocol`: `source_family: str`, `realm: Literal["event","cube"]`, `discover/read_raw/raw_schema`. Onboarding ergonomics acceptance table: new table=manifest entry only; new field encoding=one callable+registry entry; new source family=one adapter+registry entry; new concept=one `concepts.yaml` entry — none touch CLI/workflow/EFG/PIRS code.

2. **Two Lifecycles + CommonPanel (§3).** Event lifecycle: raw record → adapter → typed records → source_routing decode/parse → canonical event substrate → EFG count/functional operators → field cells on panel. Cube lifecycle: raw cube → adapter → typed cube+metadata → regime classify → classification projection → [disaggregation/reconstruction via CTR if regime demands] → bounded pushforward → substrate tagging (`B_official | B_harmonized | B_reconstructed | B_latent | B_cross-sectional`) → align to panel. `SourceAdapter.realm` dispatches into `she/lifecycle/event.py` or `.../cube.py`. **CommonPanel** (`ARCH-PANEL-01`, `she/panel.py`) is an explicit compiled phase: target panel P derived from UserIntent axes + legality; events/official cubes/reconstructed cubes each map to P cells with provenance tag (observed/projected/reconstructed/bounded); "a panel cell is never blank."

3. **Constrained Tensor Reconstruction (CTR) kernel (§4).** Unification insight: population tensor, age-bin disaggregation, synthetic context cubes, and ST-DFM latent factors are the *same* constrained optimization over a non-negative latent tensor — `she/population/loss.py` already contains anchors, linear aging operator, birth/death terms, ILR composition, 2nd-difference smoothness, and a `spatial_laplacian` penalty; "the population solver is already 90% of a general CTR kernel." Contract:
```python
@dataclass(frozen=True)
class CTRProblem:
    latent_shape: tuple[int, ...]
    observations: list[Observation]   # (A_operator, observed_values, weight)
    anchors: list[Anchor]
    nonnegativity: bool = True
    penalties: list[Penalty]          # 2nd-diff age/time, spatial Laplacian(W)
    dynamics: list[Dynamics]          # cohort aging, birth entry, death prior
    marginals: list[MarginalConstraint]
    composition: CompositionSpec | None = None   # ILR simplex (race)
```
Age-bin disaggregation as CTR instance:
```
minimize   Σ_obs ‖A·n_fine − n_broad‖²_W
subject to n_fine ≥ 0; Σ_fine within broad bin = n_broad; Σ_a n_fine[s,t,a,·,·] = marginals
penalties  λ_age·‖Δ²_age n_fine‖² + λ_cohort·‖cohort_continuity(n_fine)‖²
```
Output is `B_reconstructed`, dashboard-unsafe by default. **Certification gate** (`ARCH-CTR-03`, generalizing ST-DFM §2.10.4):
```
CTRCertification: holdout_mape ≤ verified:0.15 fragile:0.35
                  reconstruction_var ≤ verified:0.25 fragile:0.40
                  constraint_residual ≤ tol
                  stability ≥ 0.85
  ⇒ status ∈ {verified, fragile, illegal_excluded}
```
Hard rules: CTR output enters substrate only as `B_reconstructed`/`B_latent`, never `B_official`; dashboard-unsafe until `status=verified` AND uncertainty propagated; abort `ARCH-CTR-04` for promotion without certification.

4. **SpatialWeightGraph (§5).** One base graph (weighted, possibly directed edge list) + derived normalized views: `binary` (contiguity baseline), `row_standardized` (Moran's I, smoothing), `symmetric` (ICAR/CAR precision), `laplacian` (`L=D−W_sym`, CTR/ST-DFM penalty). Registry `config/registries/spatial_graphs.yaml` — example entries: `contiguity_queen` (legality_class `structural`), `knn_centroid_k8` (`structural`), `gravity_pop_distance` (`context_derived`), `commuting_flow` (`context_derived`). API: `load_spatial_graph(graph_id) -> SpatialGraph`; `SpatialGraph.view(kind)`; `SpatialGraph.blocks(n)`. **Legality guardrail (`ARCH-SPATIAL-03`, critical):** every graph has a `legality_class`; `structural` = geometry-only, always safe; `context_derived` = weight depends on a substantive variable (population/GDP/flows) — REJECTED as a prior for any test sharing provenance with the graph's own provenance (the circularity: weighting space by GDP then testing mortality~GDP smuggles the hypothesis into the null). Enforcement pseudocode given; abort added for this.

**Cross-cutting refinements:**
- **§6 Concept-family grammar** (Accept, sharpens `EFG-REG-01`): a concept (e.g. `mortality_rate`) is grammar, not a fixed column. `concepts.yaml` entries define family/numerator/denominator_family/legal_operators/required_axes/optional_stratifiers/restriction_templates/default_state. `efg/concept_planner.py` expands intent→concept→restriction→numerator→denominator→RN(...)→legality check→V-field. Division of labor: concept registry=grammar, instantiation planner=parser/codegen, legality engine=type checker, executor=backend.
- **§7 PIRS decision records** (Accept, cheap win): every modeled outcome emits a JSON decision record with a `"why"` string per decision (model_family, exposure_offset, spatial_mode, spatial_graph, residual_mode, null_regime, fdr_method, hsic_mode). `pirs/explain.py` renders human-readable summaries — "turns PIRS from a black box into a teachable, auditable instrument."
- **§8 DataScope × ExecutionStage** (Refine): two orthogonal axes replace the single "Run Profile." **DataScope** (`core_vital`/`contextual`/`full`) = which substrate exists. **ExecutionStage** (`validate`/`compile`/`investigate`) = how far the pipeline runs. Identity: `SHE+EFG` = compiler validity; `SHE+EFG+PIRS` = full investigative PegaSUS. `investigate` is the default; PIRS is never "optional," only deliberately skipped.
- **§9 Deferred: higher-order context-conditioned functionals** (`ARCH-HOF-01`, e.g. `Ψ_var(ρ|GDP-quintile)`). Defined now, implementation deferred until Phases 0-3 + an MSD §3 amendment — highest legality risk (context axis often shares provenance with the rate's denominator — same circularity as §5.4). Contract in `higher_order_operators.yaml` with `context_provenance_disjoint_from_input: true`, `output_state: quarantined_descriptive`.

**Roadmap (§10):** Phase 0 (honesty/hygiene + `ARCH-PROFILE-01`/`ARCH-REG-07`) → Phase 1 (Registry Platform via `SHE-NORM-01` Path A + SpatialWeightGraph structural view) → Phase 2 (PIRS-SPAT-01 via spatial graph + decision records) → Phase 3 (cube lifecycle/CommonPanel + CTR kernel + concept grammar) → Phase 4 (`full` scale + CTR solver backends) → Phase 5 (gated: higher-order functionals).

**MSD amendments required (§12):** §1.6 Two Lifecycles+CommonPanel; §2.13 CTR; §2.14/§6.10 SpatialWeightGraph; §3.16 Concept grammar; §8.7/§9.3 ExecutionStage; §3.17 (deferred) higher-order operators.

---

# 2. PEGASUS_DISEASE_SEMANTIC_AXIS.md (MSD-II §II.13 companion)

**Purpose/status:** Extends `PEGASUS_MSD_II.md`. Normative where it says MUST. Prompted by an external-AI handoff on ICD libraries (`simple-icd-10`, `icd-mappings`, AHRQ CCSR/CCIR/CCS, pediatric CCC, phecodes, `icdcodex`, Qwen3 embeddings) — treated as raw material, several framings corrected.

**One-sentence thesis:** disease should stop being a per-field restriction parameter (today's σ_C) and become "the primary organizing axis of the LDO's variable set" — carrying hierarchy, multi-label concept structure, and an optional embedding geometry — entering the estimator as a prior on the variable-dependency operator, exactly parallel to how geography enters as SpatialWeightGraph, but acting on the *variable* dimension.

**§1 Critique of the handoff:**
- Right: three-layer decomposition (mapping tables / hierarchy-topology / NLP-embeddings); multi-label concept membership (CCSR); provenance/projection-lossiness typing (ICD-10-CM ≠ Brazilian CID-10).
- Wrong/corrected: (1) "ICD as an axis like geo/time" is a type error — ICD is a *variable-identity* axis, not support/stratification. (2) Embeddings do NOT "generate hypotheses" — they supply a prior/search order only; data defines every edge. (3) Empirical co-occurrence embeddings as a prior are circular (same trap as spatial §II.4.1). (4) Multi-label overlap is a correctness trap: concept-variables sharing underlying codes are mechanically correlated by construction — must be modeled, not reported as discovery.
- Missing from handoff: how disease structure becomes a term in the LDO math (disease-space Laplacian `L_D` on `Ω_var`); the hard-constraint/soft-prior duality (hierarchy = additivity constraint for CTR, smoothness prior for LDO); PegaSUS's existing SIM cause-chain distinction (underlying cause vs mention); the autonomous-discovery search mechanism.

**§2 Type-theoretic correction — three axis kinds:**
| Axis kind | Examples | Role | Enters LDO as |
|---|---|---|---|
| Support | geography, time | domain of every field | lattice; `L_W`; `Σ_time` |
| Stratification | age, sex, race | subdivides within a cell | resolution/demographic axes |
| Variable-identity (semantic) | ICD/cause, procedure | determines what a variable *is* | index of variable set `X_1..X_p`; disease prior `L_D` on `Ω_var` |

Duality: a carrier stratified by disease is a tensor with a disease *stratification* axis; the LDO unfolds it into separate variables so cross-disease dependence is estimable.

**§3 What PegaSUS already does (extend, don't reinvent):** `diagnostic_topology.yaml` already types ICD fields with `topology_role` (e.g. `underlying_cause`), `icd_system: ICD-10`, `non_aggregable` aggregation, operators `icd_chapter_projection`/`icd_block_projection`. `icd_catalog.yaml` = chapter/block ranges. `icd_curated_groups.yaml` (MSD §3.11 `G_curated`) = partition-based cause groups with `OTHER` residual (used by σ_C, executor's `_add_icd_stratum`). Parse machinery: `parse_icd`/`parse_icd_ordered_chain` (LINHAA-D)/`parse_icd_unordered_set` (LINHAII). Gaps to fill: deterministic hierarchy (closure/NCA), multi-label external groupers, code-system provenance typing, disease geometry.

**§4 Normative architecture (§II.13), four components:**
1. **§II.13.1 Disease Concept Registry.** Record schema: `DiseaseConceptAssertion{code, code_system, concept_id, concept_family, source, multi_label: bool, projection_status: exact|parent_projection|approximate|unmappable|source_system_specific, chronic, warnings[]}`. Contracts: no silent cross-system truth (approximate/parent_projection ⇒ `state ≤ fragile`); multi-label preserved (partition only when explicitly requested, via declared tie-break + `OTHER` residual); round-trip validity.
2. **§II.13.2 ICD/CID Adapter.** Callables: `icd_validate/icd_add_dot/icd_remove_dot/icd_ancestors/icd_descendants/icd_nearest_common_ancestor/icd_children/icd_is_leaf`. `simple-icd-10`(-cm) wrapped; **Brazilian CID-10 remains authoritative** for DATASUS data. Guard: MUST NOT silently coerce CID-10↔ICD-10-CM; system-specific codes typed `source_system_specific`.
3. **§II.13.3 DiseaseGraph** (mirrors SpatialWeightGraph). `disease_graphs.yaml`: `cid10_hierarchy` (structural), `ccsr_membership` (structural), `label_embedding_knn_k8` (structural), `empirical_cooccurrence` (`context_derived`, GUARDED). API: `load_disease_graph(id).view("adjacency"|"laplacian"|"membership"|"distance")`, `DiseaseGraph.laplacian() -> L_D`, `.groups()` for overlapping concept groups. Same legality-class rule as spatial: `context_derived` rejected as same-data prior.
4. **§II.13.4 Disease embeddings.** Build-time asset only (never a runtime dependency for the LDO): Qwen3-Embedding family (Qwen3-0.6B default, ~14k CID-10 codes + ~500 concepts × 1024 dims ≈ 60 MB cache). Provenance-typed (label/synonym/hierarchy text = `structural`; co-occurrence-trained = `context_derived`). Never asserts an edge.

**§5 LDO integration (the heart):**
- **§5.1** Variable is generated: `variable = carrier × disease_selector(resolution r ∈ {chapter,block,category,curated_concept,ccsr_concept,leaf}) × stratification`. Resolution `r` is a first-class multi-resolution parameter (§II.7 applied to disease dim). A disease selector carries `topology_role ∈ {underlying_cause, mention, associated}` — these are distinct variables.
- **§5.2 The core mathematical move — `L_D` prior on `Ω_var`.** Hierarchy → fused/group penalty: `λ_H · Σ_{(i,j)∈hierarchy} ‖Ω_i· − Ω_j·‖²` (+ overlapping-group sparsity). Embedding similarity → smoothness prior: `L_D = D − W_D`, `λ_D · tr(Ω_var L_D Ω_varᵀ)`. Hierarchy → hard additivity constraint in CTR when reconstructing (children sum to parent). Net: `Prec(Z) ≈ Ω_var ⊗ Σ_space⁻¹ ⊗ Σ_time⁻¹`, with `Ω_var` regularized by `L_D` exactly as `Σ_space⁻¹` is built from `L_W`. "Disease becomes an axis of the estimator in the same mathematical sense as geography."
- **§5.3 Shared-code overlap correction (mandatory).** `O_ij = |codes(i)∩codes(j)| / |codes(i)∪codes(j)|` (Jaccard). High-overlap pairs handled by: fit on partition-view, or regress out shared-count component, or tag surviving edge `mechanical_overlap` (never reported as discovery).
- **§5.4 Coarse→fine + semantic search-space expansion (the autonomous-discovery mechanism).** (1) coarse pass at {chapter, curated/CCSR concept} — cheap, global disease-disease-context link graph. (2) expand along DiseaseGraph (down hierarchy + across kNN/sibling neighbors) for each certified coarse edge, refit locally. (3) stability-select and certify (§II.6.4). (4) stop on path agreement or explicit logged compute budget, never silent truncation. "The disease structure is the search policy."
- **§5.5 Disease circularity guard** — mirrors §II.4.1: structural geometry safe as prior; empirical (co-occurrence) geometry MAY be an *output* but never a same-data prior; `edge_type ∈ {contemporaneous, lagged_directed, latent_shared, nonlinear_residual, mechanical_overlap}` — no `embedding_similarity` edge type exists.

**§6 EFG legality/aggregation extensions:** disease aggregation law distinguishes `disease_hierarchy_additive` (partition, additive up tree) from `disease_concept_multilabel_nonadditive` (summing overlapping concepts double-counts — illegal, `Δ=0`); code-system provenance term (cross-system combination without declared projection is illegal, `approximate` ⇒ `state≤fragile`); closure legality for σ_C (must partition-with-OTHER or explicitly type multi-label).

**§7 Compute envelope:** embeddings precomputed/cached (~60 MB), not loaded at LDO runtime; `L_D` sparse (hierarchy ~1 parent+few children; kNN k≈8) → negligible VRAM.

**§9 TDD work items `MII-DIS-01..07`** (registry+import, ICD adapter, DiseaseGraph, `L_D` prior, overlap accounting, resolution multi-pass, build-time embeddings). Acceptance augmentation: the Zika→microcephaly test SHOULD be reachable without forced disease selectors — arbovirus and microcephaly variables instantiated by the disease-axis generator itself.

---

# 3. PEGASUS_OPERATIONAL_IMPLEMENTATION_PLAN.md (Current Code → MSD-III)

**Purpose/status:** The practical build order counterpart to MSD-III (spec). Grounded in a snapshot: 232 files / 40,113 lines in `/src` + `/config`. Governing principle: **strangler-fig, never big-bang** (pin → build alongside → route → migrate → delete). Test layout: `tests/{contract,unit,integration,synthetic,acceptance,fixtures}`.

**§1 Current-state map — layer inventory + disposition:**
| Layer | Files/Lines | Disposition |
|---|---|---|
| `efg/` (23/7765) | legality/DAG/executor/materialize/race_bridge/promotion | KEEP core, CHANGE output (measured-quantity objects), EXTRACT race_bridge → `measurement/` |
| `pirs/` (23/5770) | slice-zoo GLM+HSIC scanner | STRANGLE → `ldo/`; keep hsic/nulls/crossfit/fdr/nystrom/rff |
| `she/` (32/5390) | substrate, population tensor, ST-DFM, sidra context | KEEP+EXTEND: `population/`→`denominators/`; `stdfm/`→LDO low-rank |
| `datasus/` (16/4187) | decoders/normalizers/ICD/fetch | KEEP decoders; CONSOLIDATE 4 vectorized normalizers→declarative; move under `sources/datasus/` |
| `workflows/` (32/3655) | stage drivers | CONSOLIDATE → `build.py`, `investigate.py` |
| `sidra/` (17/2701) | acquire/metadata/compendium/project | KEEP; MOVE under `sources/sidra/` |
| `registries/` (30/2564) | two-world registry | REWRITE → unified `registry/` (kind-tagged) |
| `output/` (13/2294) | 17-key bundle | KEEP+EXTEND (link records) |
| `compute/` (7/1467) | `glm.py` (1150 lines, 11 GLM families) | KEEP; ADD `randnla.py`,`controller.py` |
| `geo/` (11/995) | tiny `adjacency.py` | KEEP; GROW → SpatialWeightGraph |
| `core/`, `source_artifacts/`, `acceptance/`, `dashboard/`, `storage/` | small | KEEP+EXT |

**Three named structural debts:** (1) The PIRS slice-zoo — one conceptual operation fragmented across ~10 manifest-passing `pirs/*` files mirrored by ~10 `workflows/pirs_*`/`hsic_*` wrappers. (2) The two-world registry (DATASUS world vs inference registries vs a lone SIDRA stub, no `kind` tag). (3) Normalizer duplication (`XCUT-02`): `declarative_normalize.py` coexists with 4 hand-written vectorized normalizers.

**Load-bearing assets NOT to rewrite:** `compute/glm.py` (11 GLM families → LDO copula margins); `she/stdfm/torch_solver.py` (masked PyTorch factor solver, spatial-Laplacian penalty → LDO low-rank layer); `she/population/loss.py` (analytic population loss, Layer 2); `efg/{legality,executor,dag,operators}.py` (the legality type system); `acceptance/contracts.py`; `storage/` (parquet/duckdb/arrow); the HSIC stack.

**§2 Target module tree** (new bold packages): `registry/` (unified kind-tagged), `sources/` (adapter plugin), `panel/` (CommonPanel), `denominators/` (population/reconstruction/exposures), `measurement/` (`bridge.py` EmissionBridge, `race.py`), `disease/` (concepts/icd_adapter/graph/embed_build), `geo/spatial_graph.py`, `efg/measured_quantity.py`, `field/` (latent.py, multiresolution.py, assemble.py), `ldo/` (records/margins/lowrank/precision/edges/residual_scan/certify/orchestrator — replaces `pirs/`), `causal/` (orient/quasi/identify — escalation rungs), `compute/{randnla,controller}`, `assets/` (tiers/build/version/store — Foundational Asset Layer), `validation/` (controls/synthetic/holdout), `output/link_records.py`, `interaction/` (interrogate/lens/escalate/steer/inject — "the five verbs"), consolidated `workflows/{build,investigate}.py`.

**§3 Migration map** — every current file's disposition (KEEP/EXT/MOVE→/MERGE→/REWRITE→/DEL), by top-level package.

**§4 Phased plan (Phase 0 → 7), each item with MSD-III ref, Files, Red (test), Green (pseudocode/steps), Done:**

- **Phase 0 — Lock + de-duplicate.** `T0-1` source-reality contract tests (no-admissible-column-all-null, age decode exact, cause-chain positions, SINASC primitives w/o flags, CNES no bed-total, CNPJ gate, state vocab). `T0-2` EFG legality/state-tensor contracts (Q-tensor columns incl. CV/MoranI/temporal_roughness/spatial_entropy; `n_eff == (Σw)²/Σw² · 1/(1+max(0,MoranI))` — Kish-Moran formula; race-axis declaration gate; high-card axis bound). `T0-3` RaceBridge numerics pin. `T0-4` inference baseline + 17-key output contract (guardrail for LDO strangle). `REFACTOR-01` de-duplicate normalizers (resolve XCUT-02).

- **Phase 1 — Platform foundations.** `REG-07` unified kind-tagged registry+validator (with a large **CORRECTION note, 2026-07-06**: registries/ actually holds 21 files not 30; `callables.py` MUST be preserved verbatim — it's already the §II.1 resolver; the two loader stacks `generic`/`semantic` had a *divergent status-admission rule* silently dropping `bridge_grammars`' operators — REG-07 is a decode-validated contract merge, NOT mechanical translation). `SPG-01/02/03` SpatialWeightGraph (`geo/spatial_graph.py`: `view()`, `blocks()`, `assert_not_circular()`). `PANEL-01` CommonPanel + per-cell provenance + month resolution. `SCOPE-01` DataScope × ExecutionStage.

- **Phase 2 — Data plane.** `EFG-OUT-01` measured-quantity objects retiring rate materialization: `MeasuredQuantity(numerator_count, exposure, offset_semantics, structure, provenance, uncertainty)` — the rate becomes a derived view only, never the modeling input. `POP-01` two-layer population tensor:
```python
def solve_population(intent, censuses, totals, flows):
    x0 = layer1_prior_mean(censuses, totals, axes)   # closed-form ILR-interpolated warm start
    if not has_flow_signal(flows) and n_in_window_censuses(censuses) < 2:
        return x0                                    # data-poor: Layer1 IS the optimum
    return run_msd_six_term_solver(x0, censuses, totals, flows)  # warm-started
```
table 2093 (2000-census strata) registered. `RACE-01..07` RaceBridge redesign: `EmissionBridge(C, target_pi_source, uncertainty)` class; `assert not is_identity(C)` — identity emission prohibited as default; per-source `C_SIM/C_SIH/C_SINASC` literature-informed, region-conditioned. `DIS-01/02/03` disease semantic axis (concepts/icd_adapter/graph, per the companion doc above).

- **Phase 3 — Latent-field + multiresolution engine** (the single highest-leverage new build; grounded in SAE/INLA/SPDE/GMRF methodology). `LF-01` `LatentField` class: "A quantity defined on the finest lattice, observed at arbitrary resolution/sparsity via a weighted observation operator. Sparsity == zero weight; nothing is fabricated." `assemble_field(panel_manifest, state_tensor) -> (X, W)`. `MR-01` multiresolution hierarchical shrinkage: `X = Σ_scale component_scale`; adaptive shrinkage prior via graph Laplacians (`L_W`, `L_D`, temporal) — "the literature engine is INLA/SPDE."

- **Phase 4 — The LDO core (strangle PIRS).** Strict build order: `records → margins → precision(K=0) → lowrank → lags → edges → certify → orchestrator`.
  - `LDO-00` `LinkRecord` schema (fields: source_var, target_var, lag_k, edge_type, weight, partial_correlation, response_curve_ref, spatial_field_ref, stability, uncertainty, confounding_factor_refs, projection_status, code_system, topology_role, overlap_jaccard, certification_status, warnings).
  - `LDO-01` copula margins wrapping `compute/glm.py`: `Z = Φ⁻¹(F_j(·))`; extensive var → binomial/Poisson-with-exposure margin.
  - `LDO-02` sparse+spatial+temporal precision (K=0), new `compute/randnla.py` (`randomized_svd`, `hutchinson_logdet`, `jl_sketch`); `fit_precision`: Kronecker-separable `Ω_var ⊗ Σ_space⁻¹ ⊗ Σ_time⁻¹`, never densified, via GMRF whitening + proximal-gradient graphical lasso.
  - `LDO-03` low-rank latent factors wrapping `she/stdfm`: `sparse_minus_lowrank` = "the market-factor/idiosyncratic split you know from finance."
  - `LDO-04` **lag extension — "the capability the whole redesign exists for."** Core test: recover a planted lag-7 A→B edge + attribute a shared wave to `L` not a spurious edge, with no variable hand-specified. `time_extend(X, K)` stacks time-shifted copies; cross-lag blocks `S^{(k,0)}` give directed lag-k edges.
  - `LDO-05` edge readout + stability selection (`stability_select`, threshold 0.7 over 50 subsamples) + residual HSIC + `type_overlap` (Jaccard-based `mechanical_overlap` tagging).
  - `LDO-06` certification + orchestrator + **the slice-zoo deletion**. `run_ldo(panel, intent)` — the whole pipeline in memory, no inter-stage manifests. After this passes, delete ~13 PIRS micro-stage files + ~10 workflow wrappers.

- **Phase 5 — Causal ladder, adaptive controller, validation battery.** `CAUSAL-01` Rung-1 orientation (LiNGAM non-Gaussian direction + collider v-structure detection, "licensed_by=non_gaussian"). `CAUSAL-02` Rung-2 quasi-experimental (ITS/DiD, shock-triggered only); Rung-3 do-calculus is expert-invoked only. `APC-01` Adaptive Precision Controller — "anytime" engine; escalates to exact computation when numerical uncertainty dominates a decision-relevant edge. `VAL-01..04` validation battery: known-positive controls (Zika→microcephaly, sanitation→diarrheal, vaccination→decline), known-negative controls (false-alarm rate), synthetic ground truth (precision/recall/lag-error scoring), temporal holdout + exact-vs-approx cross-check.

- **Phase 6 — Foundational Asset Layer.** `FAL-01` asset tiers + scope-invariance + versioning: `FOUNDATIONAL = {substrate, population_tensor, exposures, spatial_graph, disease_graph, registry, skeleton}`; `resolve_asset` asserts `build_scope == "national_full_history"`, a query only slices, never rebuilds. `FAL-02` incremental update on new data arrival. `DISCO-01` continuous discovery scheduler spending idle compute via APC — "heaviest lift; stage last."

- **Phase 7 — Multi-resolution scanning, bounded exhaustiveness, national scale.** `RES-01` coarse→fine scanning, screening on heterogeneity/dispersion/max not the aggregate mean (catches Simpson's-paradox cases). `EXH-01` coverage manifest (typed unsearched regions + random-audit false-negative rate). `SCALE-01` national tiling/streaming via `storage/duckdb`+`arrow`; refuses with `scale_exceeds_compute_envelope` rather than silently subsampling.

**§4B Cross-cutting data-plane items (surfaced during national bring-up, not originally phased):**
- `NAT-01` National acquisition/combine/compile — ✅ LANDED. Validated: national C25 mortality over 5,571 munis matches INCA figures.
- `STORE-01` Storage lifecycle — ✅ LANDED. `data/` 53GB→26GB; per-chunk 3×→1× serialization; ReproducibilityManifest 430MB→150KB.
- `STORE-02` Lazy scan_parquet views — ⬜ OPEN.
- `POP-02` Population-tensor compute contract — 🟢 M1/M3/M4/M5/M7 landed; GPU+parallel+M6 open. Key finding: the problem was held as ~10 `n_cells` Python **float tuples** (~32B/elem) — full 25-yr national (209M cells) ≈ 50-67GB → OOM. **M7 finding (from adversarial review):** `tuple(float(x) for x in gradient)` was ~99% of a loss eval — the dense math was never the bottleneck, tuple-boxing was. After M7: 2-yr national tensor builds census-exact (2022 total 203,080,756 = IBGE exact; marginal closure to 3.5e-14). GPU now "JUSTIFIED, not marginal": ~15× measured at block scale.
- `FAL-POP` Population tensor as scope-invariant asset — 🟢 data pipeline landed; several sub-items:
  - `FAL-POP-RECON` census undeclared-race reconciliation — ✅ LANDED: 2093's clean partition silently dropped "Sem declaração" (26,775 people/0.95% of AL 2000); fixed by reallocating per local composition, never dropping. AL 2000 anchor now = enumerated total exactly.
  - `FAL-POP-SV` single-vintage re-anchoring — ⬜ OPEN: the anti-discontinuity fix (SIDRA 6579/EstimaPOP mixes projection vintage with census, causing a 2021→2022 ~5% jump); replace with census-anchored cohort-component closure.
  - `FAL-POP-AMC` municipality-boundary harmonization (CARVE) — 🟢 mechanism landed nationally via the Ehrl/Moser AMC crosswalk (5577 munis→3830 groups): a post-census-installed municipality's population is carved out of its authoritative parents' census-year totals, never inferred for the parents.
  - `FAL-POP-PROJ` native projection beyond official anchors — ✅ landed: reuses the Layer-2 solver's cohort-component machinery as free-running forward integration; uncertainty `σ²(h) = σ²_anchor + Σ(component-rate variance)_i`, monotonically growing with horizon h; `fragile` for `1≤h≤H_soft` (~5yr), `unreliable` (dashboard-blocked) beyond.
  - `FAL-POP-VER` version+store+slice-on-query — ✅ LANDED (`PersistentAssetStore`, build-once key over input hashes+mode+code version).
  - `FAL-POP-VAL` demographic-sanity validation — 🟢 closure prong validated nationally; reconstruction prong gated on POP-02 M6.

**§5 The concrete near-term checklist** and **Appendix A dependency graph**: critical path is `T0 → REG-07 → SPG-01 → PANEL-01 → LF-01 → MR-01 → LDO-00..06 → VAL → acceptance`. Decisive proof-of-life: `LDO-04`'s planted-lag synthetic test is "the earliest moment PegaSUS provably does what it was redesigned to do." Program milestone: the Zika/microcephaly acceptance test.

---

# 4. PEGASUS_REFACTOR_MASTER_PLAN.md

**Purpose/status:** Governing refactor plan consolidating 9 parallel package analyses of `src/pegasus` (271 files, 47.6k LOC), cross-referenced against MSD-III and the Operational Implementation Plan. **Every deletion independently re-verified against source** (grep static imports/dotted-path strings/importlib dispatch). Marks conflicts inline as `[PLAN-CONFLICT]`/`[PLAN-ALIGNED]`.

**Verification stamp (3 load-bearing claims re-checked post-synthesis):** (1) `run_investigate` orphans `disease_graph`/`variable_meta`/`exposure` — CONFIRMED via grep. (2) Q-tensor Kish gap — live `compile_attach.py:223` takes plain `n_obs:int`; dead `q_tensor.py:214` correctly does Kish-weighted n_eff — CONFIRMED. (3) PIRS slice-zoo dead — `model_execution`/`hsic_run` appear only as descriptive strings in `stage_plan.py`, never resolved to callables — CONFIRMED.

**Execution status (executed 2026-07-05, baseline 377→345 tests passing):** Net **−4,881 LOC**. §1 dead code DONE (14 modules/471 LOC + PIRS slice-zoo 15 modules/~4,577 LOC + EFG promotion ~680 LOC). §2 megazords ALL 5 DONE (executor, build, pipeline 1322→521, compile god-fn→44 LOC, dag). §3 tree reorg §3c DONE (`pirs/ldo`→`ldo/`; data plane→`denominators/`; `sources/`+`measurement/`); REG-07 deliberately NOT rushed — flagged as a decode-validated contract merge, not mechanical (task #28). §4 two conformance fixes DONE (run_investigate disease wiring; Q-tensor Kish n_eff); greenfield builds DEFERRED per user decision.

**§0 TL;DR — four things that matter:** (1) ~1,340 LOC dead code deletes with zero breakage; another ~7,600 LOC (slice-zoo+promotion) deletes as a coordinated cut with tests. (2) Two live spec-conformance bugs hide behind dead-but-correct code (Kish n_eff; disease_graph/variable_meta/exposure orphaned). (3) Four genuine megazords (`pipeline.py` 1322, `build.py` 1618, `dag.py` 1026, `executor.py` 1251) decompose cleanly. (4) `registries/` scatter: 10/31 files are codegen cruft.

**§1 Confirmed dead code:** §1a delete now (~370-485 LOC, 11-12 files, zero importers/tests/dynamic dispatch) — including `registries/{sidra,composite_decoders,hsic,output,race_axis,residuals,icd,manifest}.py`, `core/run_context.py` (flagged `[PLAN-CONFLICT]`: plan says KEEP+EXT but it's a 0-caller scaffold whose docstring contradicts live `pipeline.py`), `source_artifacts/resolver.py`, `storage/dataset.py`, `she/stdfm/regime.py`. §1b delete-with-pinning-tests (`registries/models.py`, `output/pirs_bundle.py`, etc — some flagged CONFLICT-IN-ANALYSES, verify before cutting). §1c **HOLD — dead today but plan-reserved** (do NOT delete, add `# <TICKET> target, unwired` markers): `storage/{duckdb,arrow}.py` (SCALE-01), `sidra/{stitching,projection,pushforward,category_maps}.py` (PANEL-01), `she/high_dimensional.py`, `she/{cnes_capacity,sih_costs}.py` (flagged PLAN-CONFLICT — their EFG bundle consumer no longer exists, "dead-by-consequence, not plan-intended"). §1d **the PIRS slice-zoo** — ~4,930 LOC/20 files, deleted as one coordinated cut with pinning tests; live inference path is `compile.py→run_investigate→run_ldo (pirs/ldo/*)` reusing only `pirs/{hsic,nulls,fdr}.py`. §1e EFG promotion plumbing (legacy Slice-14/15). §1f bytecode hygiene.

**§2 Megazord decompositions** (behavior-preserving, ordered ascending risk): `efg/executor.py`(1251)→`support/kernels/run.py` + replace string-matched `elif` dispatch with operator→kernel registry dict; `efg/dag.py`(1026) — kill a **redundant duplicate RN-ratio-construction pass** (authoritative registry loop AND a second heuristic pass whose duplicate edges are silently deduped, masking the redundancy); `sidra/population_cube/build.py`(1618)→7 modules, centralizing `_cell_index` FIRST because the offset math `age*x*r + sex*r + race` is **hand-inlined at 4 separate line locations** = "latent divergence bug" risk; `workflows/pipeline.py`(1322)→extract SIDRA acquisition, land STORE-02 lazy-combine in the same pass (do NOT faithfully relocate the eager code); `workflows/compile.py::_run_compile_impl`(~410 LOC)→6 helpers, fold a duplicated extras-dict construction, land the run_investigate wiring fix here.

**§3 Registry + directory-tree consolidation:** `registries/` scatter = 31 files, 2 parallel loader stacks (Stack A `generic.py` tuple-returns; Stack B `semantic.py`+`loader.py` dict-based) — 10/31 are codegen cruft. Fix the `validators.py` hardcoded literal list divergence from `REGISTRY_FILES` now. Target directory tree: four planes (data/inference/orchestration/output); contract-bearing internals relocate WHOLE, never rewritten.

**§4 Architecture gaps ranked by leverage:**
- **4.1 [HIGHEST LEVERAGE]** wire orphaned capabilities into `run_investigate` — DIS-04 disease `L_D` prior, mechanical-overlap Jaccard guard, disease-variable grammar, EFG-OUT-01 exposure offsets are all built-and-tested but never reach a real run.
- **4.2 [HIGH — spec-conformance bug]** consolidate Q-tensor, adopt Kish n_eff: live `_moran_corrected_n_eff` uses `n·(1−I)/(1+I)` with plain observation count, no Kish weighting; dead `q_tensor.py` correctly implements `KishEffectiveN(weights)·1/(1+max(0,I))` per MSD-I §3.12.3 — "the dead module is more correct than the live one."
- **4.3 [HIGH]** write the Zika/microcephaly acceptance test — grep across tests/ for zika|microcephaly returns empty; "the program's definition of done does not exist."
- **4.4 [HIGH]** MR-01 multiresolution shrinkage + real `field/` package — UNBUILT; `pirs/ldo/resolution.py` is coarse→fine *variable restriction*, not the GMRF §III.3 spec.
- **4.5 [HIGH, ~15× measured]** POP-02 remainder — GPU port, blocked-solve parallelism, M6 input-construction memory fix; national 5-race build exceeds 32GB until per-locality build-solve-emit blocking lands.
- **4.6 [MEDIUM]** `compute/randnla.py` + matrix-free LDO precision — UNBUILT; LDO precision is CPU-dense (`eigh` infeasible nationally at 5,571² ≈ 248MB before whitening).
- **4.7 [MEDIUM]** half-built APC + STORE-02.
- **4.8 [BUILT-BUT-ORPHANED]** causal Rung-1 auto-orientation has zero non-test importers; `run_ldo` never calls it.
- **4.9 [BUILT-BUT-PARTIAL]** EFG-OUT-01 measured-quantity emitted as an RN sidecar, not yet the terminal object replacing the rate.

**§5 Sequencing:** Phase A (reclaim) → Phase B (coordinated dead-cuts, gate: full suite green before/after) → Phase C (behavior-preserving decompositions) → Phase D (consolidation, REG-07 gets its own migration test per source) → Phase E (new builds, ranked §4).

**MUST NOT CHANGE:** EFG legality-algebra tier (relocate whole, never rewrite); public symbols `execute_efg_result`, `interpolate_census_composition`, `solve_population_tensor_from_sidra_{strata,anchor}`, `run_ldo`, `run_investigate`, `build_efg`, `validate_output_bundle`, `acceptance.contracts.*`; the MSD-III §III LDO pipeline; the FAL-POP population-tensor line.

---

# 5. PEGASUS_REDESIGN_ROADMAP.md — corrections/enhancements over the MSDs

**Purpose/status:** Synthesis (2026-07-07) of `PEGASUS_MATH_CRITIQUE.md` (165 findings, 16 themes, + a steelman with 20 adversarial verdicts, "mostly UPHELD" + 23 direct findings `A1`-`A23`), `PEGASUS_MODULARIZATION_CRITIQUE.md` (`M1`-`M6`), `PEGASUS_GPU_OPTIMIZATION_CRITIQUE.md` (`G1`-`G6`+50 findings), `PEGASUS_FEATURE_PROPOSALS.md` (`P1`-`P5`). **Governing principle: the MSDs are FALLIBLE theory** — several top findings are cases where the spec itself is the trap. "**No live study runs until Tier-0 is closed** — the current pipeline would produce scientifically invalid results with false precision." Priority tiers: P0 (invalidates a scientific claim) / P1 (materially biases results) / P2 (performance/scale) / X (cross-cutting enabler).

**TIER 0 — Foundational validity (blocks the study):**

- **W1 — the `ObservationReliability` contract, "the single highest-leverage redesign."** Problem: the EFG/§3.12 layer computes rich per-cell reliability state (W, effective-n, fragility) that the LDO consumes almost none of — covariance unweighted, edge SE uses raw cell count, and the named statistics measure the *wrong* quantity vs the spec. Redesign: a typed `ObservationReliability` object required to be consumed by covariance/whitening/SE estimators (weighted `Σw·xᵀx/Σw`; weighted ECDF; Fisher-z SE from effective-n not raw count; fix Kish/fragility/CV/roughness definitions). **Progress logged:** point 1 (weighted covariance) DONE — `weights=None` ⇒ byte-identical to old unweighted fit (verified); point 4 (contract test) DONE. Remaining: weighted ECDF, Fisher-z SE, the spec-divergent-statistic fixes.

- **W2 — noise-model redesign (NB/ZINB margins + structured expected-count offset).** Problem: "the MSD contradicts itself" — MSD-I §6.2 prescribes NB/quasi-Poisson/hurdle for overdispersion, but code hardcodes an equidispersed Poisson margin with a single global rate λ, so between-municipality rate variation (the actual epidemiological object) is pushed into "surprise" as an artefactual national development axis. Redesign: per-variable NB/ZINB margin with data-estimated dispersion; offset = structured expected count `E_i = exp(offset + spatial RE)` (small-area/BYM), not a scalar; carry exposure's own reconstruction uncertainty into the margin (errors-in-variables); integrate out randomized-PIT jitter via MI-combine.

- **W3 — spatial+temporal dependence (one graph, whiten both axes, exchangeable nulls).** Problem: spatial dependence variously ignored/double-corrected/measured with a non-geographic 1-D Moran proxy; permutation null non-exchangeable; **temporal autocorrelation never whitened** though a decay parameter is applied anyway; a single pooled AR(1) imposed across the epidemiological transition. Redesign: one `geo.spatial` module (deletes 6 Moran copies); row-standardized Laplacian + principled missing-cell handling; whiten temporal dependence before the fit; time-varying lag structure across regime boundaries; exchangeable (conditional/toroidal or model-based) spatial null with a hard guard against iid fallback.

- **W4 — calibrate decision boundaries + dependence-aware multiplicity.** Problem: ~15 hand-set constants (λ, κ, screen thresholds 0.15/0.30, stability 0.6, veto 0.5) silently determine which findings survive; FDR fields plumbed but unused; PRDS assumption violated by the spatial panel. Redesign: stability-selection error-control criterion for λ (Meinshausen-Bühlmann/eBIC scaled `√(log p/n_eff)`); estimate κ/τ²/ρ from data; dependence-aware FDR (block/knockoff permutation).

- **W5 — identifiability honesty.** Problem: intercensal demography, the race bridge, gross migration are "prior pushforwards reported as inference"; in-sample HSIC residual double-dipping; a circular denominator estimation (`δ = deaths/anchor`). Redesign: add an external identifying anchor OR demote to explicitly prior-dominated/descriptive with a sensitivity envelope; genuine cross-fitting on disjoint folds.

**TIER 1 — estimator+inference integrity:** W6 (optimizer/covariance-matrix integrity — Higham nearest-correlation, ADMM dual+primal stopping with adaptive ρ, remove `max_iter=12` cap, multiplicative ILR compositional closure); W7 (causal-claim discipline — Meek propagation, autocorrelation-aware LiNGAM, ITS correction; "per P5, this becomes the causal installment's own spec"); W9 (separability escape hatch — add a low-rank non-separable component so lagged spatial epidemic spread is representable; Kronecker stays as scalable backbone).

**TIER 2 — performance+scale (validity-neutral):** W8 GPU (batched ADMM eigh on GPU float64, ~5-15×; GPU HSIC residual scan via RFF/Nyström feature maps, ~10-30× — "reframe: this workload is repeated-small-dense+one huge scan — GPU-favorable"). W10 numerical-method/streaming redesigns.

**Cross-cutting:** W11 consolidation (`geo.spatial`, `core.text`/`core.io`, `measurement.composition`, collapse two reconstruction packages, fix geo→denominators layering) — "the reliability contract (W1) and geo.spatial consolidation (W3) are the two structural anchors." W12 new subsystems: P3 export layer co-designed with W1; P4 per-query denominator declaration.

**One-line thesis:** "the LDO is a sophisticated engine that currently (a) uses the wrong noise model, (b) discards the uncertainty it computes, (c) mishandles the spatial/temporal dependence it exists to study, and (d) gates findings on uncalibrated constants — so its outputs are not yet scientifically trustworthy."

---

# 6. PEGASUS_COMPLETION_ROADMAP.md (2026-07-09)

**Purpose/status:** Settled assessment + solutions + sequenced roadmap. Three reframings: (1) full national×full-temporal (2000-2024) is the **default** operating regime; (2) `data/` needs a persistence contract; (3) RaceBridge's problem is **ecological, not individual**.

**Status section — DELIVERED:** W-RACE-2 ecological estimator (`measurement/race_ecological.py`) with a proof-of-capability test (gradcheck 1e-7, recovers a planted 1.5 rate-ratio the naive crosswalk erases to 0.91). W-RACE-2-wire calibration (`measurement/race_calibration.py`) — validated on real AL data: identifiability 0.0015 < 0.005 threshold → the gate correctly REFUSED, "empirically proving the calibration must be NATIONAL." STORE-ORG workspace GC. **VERIFIED→REDIRECTED (measuring changed the answer):** DP-2 (parallel normalize) has a MEASURED rationale for its current cap-of-2 (>2 only stacks RAM); W-REG-1 judged correct-but-marginal.

**§1 RaceBridge — the centerpiece redesign:**
- **§1.1-1.2** Problem: DATASUS event race labels are **administrative** (often third-party recorded), census population race is **self-declared**; the two diverge systematically in Brazil (admin over-reports branca, under-reports parda/preta). **Key insight, formalized: the distortion is ECOLOGICAL, not individual** — individual reclassification is fundamentally unidentifiable (no ground truth per death); but at the aggregate/cell level it IS identifiable via discrepancy between observed admin-race distribution and what self-declared population + plausible rates predict — "a classical ecological-inference structure."
- **§1.3 The model — hierarchical Poisson ecological-deconvolution:** indices `j`=self-declared (true), `k`=administrative (recorded), `s`=cell. `N_{s,j}` = census pop of race j; `Y_{s,k}` = admin events labeled k; `λ_{s,j}` = true target rate; `C_{k|j} = P(recorded=k|self-declared=j)` confusion matrix.
```
Y_{s,k} ~ Poisson( Σ_j  C_{k|j} · λ_{s,j} · N_{s,j} )
```
Infer the posterior over `λ_{s,j}` (the quantity of interest), `C` the shared misclassification structure.
- **§1.4 Identifiability — the small-C trick formalized:** make `C` shared across cells (one national or region-level `C_r`), small/structured (mostly-diagonal 5×5 stochastic matrix). The many cells with varying census composition `N_{s,j}` identify `C`'s few parameters (King/Goodman ecological-inference mechanism) separately from cell-specific `λ_{s,j}` (pinned by hierarchical shrinkage). "Honest scrutiny: pure ecological estimation of C is fragile" (leans on shared-C homogeneity, sufficient contextual variation) → the **robust design is HYBRID**: literature/expert prior on C + ecological likelihood refinement + wide posterior where data don't identify.
- **§1.5 Why the current design is mis-levelled:** current bridge does per-cell **count reallocation** with a **fixed** `C` (`posterior_self = Σ_k Y_k·W_k,j`, `W ∝ C_k|j·π_s,j`) — frames the problem as individual reallocation (which isn't identifiable), never estimates `C` from the only identifiable ecological signal, produces reallocated counts not a rate posterior, `local-π` is a heuristic not a principled prior.
- **§1.6 Redesign phased:** W-RACE-0 (reframe+honesty, VERIFIED largely done — the guard blocks uncalibrated priors from dashboard-safe runs). W-RACE-1 (~1wk, code-only: propagate uncertainty into the LDO measurement-error term, finish region-conditioned `C_r`, replace `local-π` with census-anchored shrinkage prior). W-RACE-2 (~3-4wk, the real redesign: EM+Laplace first, MCMC later if multimodality bites). W-RACE-3 (optional, full MCMC+region hierarchy).
- **§1.7 The sophisticated form — covariate-dependent confusion `C(x)`.** `C` varies by source system, time (25-yr drift), age/cohort, region, reporting mode. Parameterization preserving the small-entity discipline (must NOT become a K×K×covariate tensor): structured multinomial-logit anchored at identity — `log[P(admin=k|self=j,x)/P(admin=j|self=j,x)] = α_kj + x·β_kj`, with `α` identity-dominant and `β` heavily regularized toward 0, collapsed onto a scalar "whitening propensity" `ρ(x) = logit⁻¹(β₀+β_sys+β_year·t+β_age·a+β_region)`. **New identifiability asset — cross-system consistency:** the systems observe partly the same self-declared population under different reporting; holding census composition fixed, the *difference* in admin-race distributions across systems identifies the system-specific `C`.
- **§1.8 Empirical validation (planted-signal probe, 2026-07-09):** synthetic ecological data with known whitening C and a planted genuine race differential (preta mortality truly 1.5× branca). Results table: (A) high contextual variation → naive 0.91 (erases/inverts) vs model 1.49 (recovers); (B) low contextual variation → degrades to 1.30; (C) strong identity-anchored prior → suppressed to 1.07 (**"an over-strong/mis-anchored prior is harmful"**); (D) two systems (cross-system strongest identifier) → 1.49, best C recovery. "**The current production bridge (fixed identity/synthetic C) is scenario C at infinite prior strength → not merely inert but actively harmful** where real misclassification exists."

**§2 Data layer for full-scale default (promoted to first-class):** DP-1 (byte-safe quick wins) → DP-2 (memory-budgeted 3-4-way normalize parallelism) → DP-3 (**first-class**: end-to-end streaming `scan_parquet→sink_parquet` with explicit memory ceiling — "the difference between 'runs on this machine' and 'OOMs' at the default scale") → DP-4 (combine batching/caching).

**§3 Storage/cache/persistence — contract+cleanup (STORE-ORG):** documented `data/` layout spec: `data/lake/{...}` (content-addressed) vs `data/runs/<intent>/<run_id>/` (immutable bundles) vs `data/assets/<name>/<version>/` (versioned foundational assets). GC pass to delete dev-run detritus. Stage-workspace lifecycle (transient dirs under temp/scratch, cleaned on success).

**§5 Sequenced roadmap:** Phase 1 (full-scale readiness+integrity, pre-live-test) → Phase 2 (live test+measurement upgrades: W-RACE-2, W-REG-1) → Phase 3 (polish/hardening: god-module decomposition, REG-07, output-query P3d/P3e) → Phase 4 (the studies: national C25 + disease-comorbidity at full 2000-2024 scale). "**The single highest-leverage next move: Phase-1 data-plane bounded-memory streaming (DP-3)**."

---

# 7. PEGASUS_FEATURE_PROPOSALS.md

**Purpose/status:** Annexed from a project discussion (handed off 2026-07-07), evaluated against an early LDO build. 5 proposals, each with current status.

- **P1 — SpatialWeightGraph richer/legality-typed adjacency.** Multiple weighting schemes as selectable views: distance-decay `exp(-d/ρ)`, k-NN, gravity `pop_i·pop_j/d²`, flow-based (SIH transfer volumes); gravity/flow are `context_derived` and MUST be rejected as a prior for any tested variable sharing that provenance. **Status: mostly a real gap** — SPG-01 built the typing scaffold (views/blocks/laplacian+circularity guard), but the live LDO consumer (`geo/adjacency.py::structural_cod6_adjacency`) is binary contiguity only — richer schemes not wired into GMRF whitening. Verdict: BUILD as SPG-01 refinement folded into spatial consolidation (`M1`).

- **P2 — Disease-tree "borrow strength" adaptive, pattern-only shrinkage.** Three hard requirements: (1) shrink structure only, never level/rate; (2) estimate `τ²` adaptively per block from data; (3) flag heavily-shrunk estimates. **Status: partially built** — `O6` built `sum_of_scales_disease_operator` (per-scale disease Laplacians {category/block/chapter}) but with **FIXED** per-scale precisions (a caller constant) — satisfies (1), fails (2) and (3). Verdict: BUILD adaptive-τ² (empirical-Bayes/marginal-likelihood) + shrinkage-flag.

- **P3 — Export/Materialization layer (NEW subsystem).** User-controllable exportable datasets carrying per-cell uncertainty+provenance columns, stable schemas, reproducibility manifests. **Status: genuine new gap, high strategic value** — no such layer exists. "**Deep connection to the critique's #1 theme:** the export MUST carry per-cell uncertainty+provenance — exactly what the reliability contract computes-but-discards. The export layer is the natural FORCING FUNCTION for the ObservationReliability contract." Verdict: BUILD AFTER W1/reliability contract exists (see the Output Query Layer doc for the actual spec).

- **P4 — Default exposure/denominator declaration (per-query overridable).** Same count under multiple denominators (proportional-morbidity vs population-based) as first-class variables. **Status: real refinement of O7/REG-07** — O7 added the extensive/intensive gate but no per-query override/multi-denominator mechanism. Verdict: BUILD as REG-07/EFG-OUT-01 refinement co-designed with denominator-uncertainty fix.

- **P5 — Causal-ladder implementation detail (DEFERRED).** Rung-1/Rung-2 build specs — "explicitly deferred to its own installment — do NOT build until spec'd." **Status:** built anyway this session (CAUSAL-01, O8) BUT the redesign-roadmap's Theme-15 found them fragile (LiNGAM on Gaussianized data destroys needed non-Gaussianity; collider without faithfulness/Meek propagation; ITS single-break-only). Verdict: incorporate Theme-15 corrections before further causal build.

**Unifying note:** "The unifying prerequisite for P3 and P4 is the `ObservationReliability` contract — the single highest-leverage redesign."

---

# 8. PEGASUS_DATA_LIFECYCLE.md (crystallized 2026-07-09)

**Purpose/status:** The design law for data entry/build/query, "enforced in code, not convention." Authority: `pegasus.core.data_lifecycle`; this doc is the human-readable companion.

**Object model — three tiers + a query layer:**
```
CANONICAL INPUT LAKE  →  DERIVED (rebuildable)  →  VERSIONED ASSET  →  RUN BUNDLE (per-run)
raw/datasus → processed/datasus (raw cols) → normalized/datasus (SHE cols) →
SIDRA cache/metadata → processed/sidra/facts → assets/population_tensor/v{year}.{seq}
   (build-once, scope-guarded, lazy slice-on-query) → runs/{run_id}/ (17-key: identity=UserIntent+
   ReproducibilityManifest; Tables/efg_tensors/{field_id}.parquet)
discovery: RunCatalog (output/run_catalog)   query: output/query — edge✓ count/raw_field✓ rate✗(scoped)
```
- Canonical input: externally fetched, never auto-GC.
- Derived: rebuildable, safe to drop (`processed`=R-bridge raw-DATASUS-columns output; `normalized`=SHE-canonical decode — names are legacy, behavior correct).
- Asset: versioned/immutable/build-once, sliced never rebuilt per query. "Complete + scope-guarded in code; empty on disk only because no national compile has completed yet."
- Run bundle: the 17-key output under `data/runs` (the only production run root; other dirs are dev/test snapshots never written by `src`).

**Persistence contract table** (`core.data_lifecycle.DATA_LIFECYCLE`): 9 roots each with Role/GC-policy/TTL — e.g. `data/raw`=canonical_input/never; `data/cache`=cache/drop_by_mtime/30d; `data/diagnostics`=metadata/drop_by_mtime/90d; `data/assets`=asset/user_gated; `data/intermediate`=ephemeral/delete_always. `classify(path)` answers any path's role; `is_safe_to_delete` True only for cache/ephemeral; `storage_gc.gc_by_contract` enforces exactly those two.

**Honestly-ranked remaining gaps:** (1) `rate`/`standardized_rate` queries — mapping denominator id → materialized bundle field + cell-key-matched division + age-standardization weights is "the correctness-critical next piece," currently a typed refusal rather than a divide-by-guess. (2) Strays (`data/_peryear_probe`, legacy SIDRA strata).

**Refuted by measurement:** "**Bundle built fully in-RAM is a national-scale RAM cliff**" — FALSE. Measured on a real bundle: `Q_tensor`/`V_fields`/`VariableDictionary`/`Hypotheses` are one row per FIELD/EDGE (~73-86 rows, 0.30 MB total), not per cell — scales with field count (bounded even nationally), not cell count. Large per-cell data (`Tables/efg_tensors/`) is already streamed separately, never accumulated in `bundle_manager`'s `list[dict]`. "No streaming-flush rewrite is needed."

---

# 9. PEGASUS_OUTPUT_QUERY_LAYER.md (FEAT-P3 + FEAT-P4 design spec)

**Purpose/status:** Design (2026-07-08), closes into MSD-III §VIII. Implements two coupled roadmap items. **Revision note (SCOPE PRUNED after user steer):** the query layer does NOT recompute rates — recomputing here would create a *second* rate definition that could drift from the EFG's canonical RN-operator rate ("the two-generators anti-pattern"). Refocused: (a) `rate` = a pure read of the EFG's already-materialized RN rate field, never computed; (b) the real value is a **self-describing hypotheses export** — the edge table enriched with each variable's label/carrier/unit/ICD-context from `VariableDictionary`; (c) multi-denominator (FEAT-P4) is a compile-time declaration + query-time selection, never a query-time recompute.

**§2 Object model — `QueryableQuantity` kinds:**
| kind | source | denominator? | uncertainty |
|---|---|---|---|
| `raw_field` | materialized V_fields tensor | — | Q-state (n_eff, fragility) |
| `count` | extensive EFG field | — | Poisson √count |
| `rate` | count÷resolved denominator | required (P4) | count Poisson ⊕ denom fragility → gamma/Byar CI |
| `standardized_rate` | age-specific counts÷person-time | required+reference pop | Fay-Feuer gamma CI |
| `edge` | `Hypotheses.parquet` LinkRecords | — | uncertainty/stability/fdr_qvalue carried through |

**§3 Multi-denominator declaration (FEAT-P4):** registry `config/registries/health/denominators.yaml`, per quantity key an `admissible` list (each with `id`, `default: true` for exactly one, `strata`, `offset_semantics`). Resolution: explicit query override → validated or typed error (never silent fallback); else the declared default; the resolved id+strata+offset_semantics+its own Q-state fragility written into a provenance manifest so "two runs that pick different denominators are distinguishable from the manifest alone." Strata compatibility: numerator strata must be subset of/aggregable to denominator strata, else the RN kernel's ecological-fallacy guard aggregates up and records `ecological_aggregation`.

**§4 Uncertainty propagation:** crude rate CI = Byar's gamma approximation on the Poisson count, divided by exposure; widened by denominator state-tensor fragility in quadrature on the log-rate scale when the population tensor denominator is itself reconstructed. Standardized rate uses existing Fay-Feuer gamma CI. Provenance manifest (one JSON sidecar per export) records run id/bundle hash/QuerySpec/resolved denominator+fragility/reference population/code_system/projection_status/ecological_aggregation/n_eff/sparsity_of_truth note. "Nothing is exported without it."

**§5 API surface:** new package `output/query/`: `spec.py` (`QuerySpec` pydantic model), `denominators.py`, `engine.py` (`materialize_query(bundle_dir, spec) -> MaterializedDataset`), `export.py` (`write_dataset`), workflow entrypoint + CLI verb `pegasus export`.

**§6 Enforcement (reuses existing guards):** extensive/intensive gate (O7); no silent degrade (typed error + recorded coverage gap); disease multi-label non-additivity gate; spatial/disease legality-class circularity guard reused for denominators too.

**§8 Phased implementation:** P3a denominators registry+resolver — DONE (8 tests). P3b edge query+export vertical slice — DONE. P3c edge enrichment (VariableDictionary join) — DONE. P3d `materialized_field` read (pure read, no recompute) — remains. P3e CLI+workflow entrypoint — remains.

**§9 Acceptance battery:** a rate export names its denominator+CI, and `--denominator` changes both numbers and manifest; standardized-rate reproduces `directly_standardized_rate` bit-for-bit on a fixture; an extensive numerator with no admissible denominator refuses loudly; a multi-label disease concept as numerator refuses.

---

# 10. HANDOFF_2026-07-09_population_build_and_project_state.md

**Purpose/status:** Field notes/debrief from an outgoing agent to a fresh one, explicitly "not settled truth." House rule invoked: "believe the code" when notes and code disagree (`CLAUDE.md` §IX).

**§0 Orientation:** Win condition = a national C25 (pancreatic cancer) mortality study, 2000-2025, full national+temporal scale. Blocker: materializing the **national population tensor** as a persisted build-once asset — peak RAM (~18-20GB) sits at the edge of the machine's ~20.8GB idle-available headroom.

**§1 The memory conundrum — measured trace** (instrumented RSS sampler, safe 3GB-available watchdog):
```
  1.5s  rss=4.1GB   read_strata exit             (18MB parquet -> 4.1GB, ~220x expansion, plain Utf8 not Categorical)
 81.1s  rss=8.6GB   sim_death_priors (skipped)
 81.6s  rss=7.2GB   SOLVE_BLOCKED entry
573.4s  rss=9.0GB   SOLVE_BLOCKED exit             (68 locality-blocks, memory-graceful)
605.3s  rss=17.4GB  WATCHDOG ABORT (avail<3GB), still climbing   <- THE EMIT STAGE
```
Three cost centers identified, and the agent notes being wrong about which dominates until measuring: (1) `_read_population_strata`→4.1GB (categorical strings read as plain Utf8, ~220× expansion); (2) record construction→~8.6GB (an ~11.25M-row Python `list[dict]`, doubled by 2000-census disaggregation — "the code comment itself estimates ~12M-row list[dict] ~6GB at national scale"); (3) **the EMIT→≥17.4GB, dominant, still rising at abort** — the code comment claims the per-locality-block parquet write "never materializes the full ~8GB label frame" and "is byte-identical to a monolithic emit," but **"the measurement contradicts the comment"** — RSS climbs ~8GB during this stage regardless. Candidates unresolved: object/string label arrays via `np.tile`, `to_arrow()` transient doubling, ParquetWriter row-group buffering, or per-block frames not released. "This is the single highest-value thing to nail down."

A confound noted (§1.3): running the full pytest suite concurrently with the build inflated early aborts — but the emit spike is real and reproduces idle-alone too. Lesson recorded in project memory: never run pytest concurrently with a national build on this box.

Open uncertainties flagged for verification against spec (§1.4): whether `sim_informed_denominator` mode with no race-bridge prior is the *correct* national invocation (SIM death priors currently short-circuit to None without one, so race structure comes only from census composition); and that `reconstruct_migration=True` at national scale now *surfaces a skip* (rather than silently no-op) because it exceeds `MAX_DENSE_FLOW_PAIRS=8000` — enabling it needs a sparse backend (`POP-FLOW-02`, open).

**§2 Work done this session (branch `TDD-branch-redo`):**
- The GPU population solver (`torch_solver.py`, POP-02) — "the one clean CUDA win": ports the 8-term population loss+SPG to torch; validated machine-identical to numpy (gradcheck 1e-16 f64/1e-7 f32); ~16× per-block. **But** the national many-block loop intermittently hard-segfaults (~2 of 3 national runs) from a native torch+polars(rayon) transition race.
- Response: a **crash gate** (route national/68-blocks to crash-free CPU, keep GPU for ≤12-block scale) + a **subprocess isolation runner** (`build/isolated.py`) with retry, hard-timeout with Windows process-tree kill (`taskkill /F /T` — plain shell `timeout` cannot kill a child tree on Windows), RAM-floor abort, GPU×2-then-guaranteed-CPU-fallback attempt plan. Validated with 5 focused tests. Caveat: this converts a memory failure into a clean *failure*, it does NOT fix the memory — "the real fix is reducing the emit peak."
- **A measured NEGATIVE result, explicitly flagged so it isn't blindly redone:** the internal survey/issue-ledger claimed "batched ADMM eigh GPU 5-15×" was the #1 LDO GPU win. Profiling before building found: a single CUDA f64 eigh at q=360 is 6.9× a numpy 1-thread eigh, agrees to 2.6e-15 — but eigh is only ~60% of a fit, so a single fit nets only 1.76×; the dominant cost (`stability_select`, 20 refits) already parallelizes ~4.5× across CPU cores, which one GPU can't beat for independent refits, and batching is counterproductive at q=360 (GPU already compute-bound). Realistic net ~1.7-2× with regression risk — chose **not to build it**, per the project's "match effort to measured value" + "report negative results" discipline. Broader hypothesis offered: PegaSUS's heavy numerical ops already individually saturate a single small GPU at national scale, so the "batch many small ops" pattern that makes GPUs shine mostly doesn't apply here — the population iterative solve was the exception and it's done.

**§3 Remaining goals:** (1) materialize the national population tensor (needs emit-stage memory fix, target peak well under ~12GB "so it's safe on a loaded machine" per the user's stated standard). (2) Full contextual compile+investigate at national+temporal scale — the user has a HARD "no cherry-picking" directive: every run uses all systems at full national+temporal scale. (3) The pancreatic C25 national study (win condition) — engine exists, validated on real AL 2022, needs items 1+2. Project-level open items: `POP-FLOW-02` (sparse migration backend), RaceBridge region-conditioned `C` is data-blocked pending PNS/PNAD linkage, FEAT-P3e CLI wrapper, a long DEFERRED tail (causal P5, Zika acceptance test, DIS-06/07, LDO cross-fit).

**§5 Meta-note (explicitly emphasized):** "I spent a lot of today oscillating on decisions the measurements could have settled faster... Lead with the probe" — reinforcing the project's core empirical-verification discipline.

---

## Cross-document glossary (every named concept, one/two lines each)

- **EFG (Epidemiological Field Graph)** — the legality/materialization tier that expands registered concepts into concrete, provenance-tagged fields via typed operators (count/functional/RN-ratio/bridge); its executor/dag/legality modules are explicitly "keep, never rewrite."
- **PIRS** — the current single-outcome GLM+HSIC investigation engine ("the slice-zoo"), fragmented across ~10 manifest-passing files; being strangled and replaced by the LDO.
- **LDO (Latent Dependency Operator engine)** — the redesigned in-memory inference engine (`ldo/`): copula margins → sparse+low-rank precision → lag extension → edge readout/stability selection → causal orientation → certification, replacing PIRS.
- **SHE** — the substrate layer (event/cube ingestion, population tensor, ST-DFM, SIDRA context).
- **CommonPanel** — the compiled municipality×time[×age×sex×race] panel, an explicit phase with a per-cell provenance manifest (observed/projected/reconstructed/bounded — never blank).
- **LDO variable-dependency operator `Ω_var`** — the precision-matrix object over the LDO's variable set `p`, regularized by disease-space Laplacian `L_D` exactly as `Σ_space⁻¹` is built from `L_W`.
- **CTR (Constrained Tensor Reconstruction) kernel** — the unified constrained-optimization family generalizing the population tensor, age-bin disaggregation, synthetic context cubes, and ST-DFM, gated by a certification threshold (holdout_mape, reconstruction_var, stability).
- **SpatialWeightGraph** — one base spatial-weight object with derived views (binary/row_standardized/symmetric/laplacian) and a `legality_class` (structural vs context_derived) preventing circular use as a prior.
- **DiseaseGraph** — the disease-axis analogue of SpatialWeightGraph: hierarchy/membership/embedding views feeding a `laplacian()` = `L_D`, same legality-class circularity guard.
- **Disease Concept Registry** — multi-label, provenance/projection-typed code→concept assertions (CCSR/CCIR/CCC/phecodes/curated) that MUST NOT be silently forced to a partition.
- **σ_C (cause-specific restriction)** — the existing ICD chapter/block restriction operator applied by the EFG executor; becomes one partition-view over the richer multi-label Disease Concept Registry.
- **Concept-family grammar** — registered concepts (`concepts.yaml`) as grammar, not fixed columns; the EFG concept-instantiation planner expands intent+substrate into concrete legal V-fields.
- **MeasuredQuantity** — the terminal EFG output object (numerator_count, exposure, offset_semantics, structure, provenance, uncertainty), retiring pre-divided rate materialization.
- **RaceBridge / EmissionBridge** — the measurement-model layer correcting admin-vs-self-declared race discordance; redesigned from fixed-identity per-cell count reallocation into a hierarchical Poisson ecological-deconvolution model with a shared, small, literature-informed confusion matrix `C` (optionally covariate-dependent `C(x)`).
- **Population tensor (two-layer)** — the demographic denominator: Layer 1 = closed-form ILR-interpolated census composition × closure totals (warm start); Layer 2 = the existing 6-term process solver warm-started from Layer 1, with a data-poor short-circuit returning Layer 1 exactly.
- **ObservationReliability contract** — a typed per-cell weight/effective-n/fragility object the LDO's covariance/whitening/SE estimators are required to consume, rather than silently discard — "the single highest-leverage redesign" per the critique.
- **Q-tensor / n_eff / Kish weighting** — the EFG's per-field state diagnostics (CV, MoranI, temporal_roughness, spatial_entropy); the correct spec formula is Kish-weighted effective n; the live code was found to use an unweighted n_eff (a confirmed spec-conformance bug).
- **ARCH-* work items** — the Architecture Addendum's new-build IDs (registry/CTR/spatial/concept/PIRS-explain/profile/HOF), cross-referenced to compliance finding IDs.
- **MII-DIS-* work items** — the Disease Semantic Axis's TDD work-item family.
- **T0-*/REG-07/SPG-*/PANEL-01/POP-01/POP-02/DIS-*/LF-01/MR-01/LDO-00..06/CAUSAL-*/APC-01/VAL-01..04/FAL-*/RES-01/EXH-01/SCALE-01/NAT-01/STORE-01/02** — the Operational Implementation Plan's phase-gated work-item IDs (T0 pins current behavior; REG-07 unifies the registry; SPG builds SpatialWeightGraph; PANEL-01 builds CommonPanel; POP-01/02 the population tensor math/compute; DIS builds the disease axis; LF-01/MR-01 the latent-field/multiresolution engine; LDO-* builds the inference engine; CAUSAL/APC/VAL the science-and-trust layer; FAL-* the Foundational Asset Layer; RES/EXH/SCALE the national-scale scanning discipline).
- **Foundational Asset Layer (FAL)** — the scope-invariance discipline: foundational assets (population tensor, spatial/disease graphs, registry, skeleton) are built once at national/full-history scope and only ever *sliced* by a query, never rebuilt at reduced scope — "building a scope-invariant asset at reduced scope is a correctness bug."
- **DataScope × ExecutionStage** — two orthogonal run-profile axes: DataScope (core_vital/contextual/full = which substrate exists) and ExecutionStage (validate/compile/investigate = how far the pipeline runs); PIRS/LDO is central to `investigate`, never "optional."
- **W1-W12 / Tier 0/1/2** — the Redesign Roadmap's prioritized validity-fix workstreams (ObservationReliability, NB/ZINB noise model, spatial+temporal whitening, calibrated decision boundaries, identifiability honesty, optimizer integrity, causal discipline, separability, GPU wins, consolidation, new subsystems).
- **P1-P5 (Feature Proposals)** — SpatialWeightGraph richness, disease-tree adaptive shrinkage, Export/Materialization layer, multi-denominator declaration, causal-ladder detail (deferred).
- **W-RACE-0/1/2/3** — the phased RaceBridge redesign (honesty guard done → propagate uncertainty → the hierarchical Poisson ecological model → optional full MCMC).
- **QueryableQuantity / QuerySpec / MaterializedDataset** — the Output Query Layer's typed export object model (raw_field/count/rate/standardized_rate/edge kinds) and its provenance-manifest contract.
- **17-key output bundle** — the standing per-run output contract (`OUTPUT_BUNDLE_FILES`); every key always present, empty keys carry a typed reason, never silently blank.
- **The data_lifecycle contract (canonical input / derived / asset / run bundle tiers)** — the enforced persistence law over `data/`, with per-root GC policy/TTL and a `classify(path)` function.
- **"Strangler-fig" pattern** — the governing refactor discipline: pin with a contract test → build new alongside old → route → migrate callers → delete old only once green — never a big-bang rewrite.
- **CLAUDE.md discipline** ("§IX believe the code," "profile before optimizing," "report negative results," "no cherry-picking," "full data at full scale is the default") — the project's empirical-verification operating law, repeatedly invoked across documents as the reason claims were revised.

All ten documents were read to completion; nothing was edited. File paths for reference (all under `C:\Users\Galaxy\LEVI\PegaSUS`): PEGASUS_ARCHITECTURE_ADDENDUM.md, PEGASUS_DISEASE_SEMANTIC_AXIS.md, PEGASUS_OPERATIONAL_IMPLEMENTATION_PLAN.md, PEGASUS_REFACTOR_MASTER_PLAN.md, PEGASUS_REDESIGN_ROADMAP.md, PEGASUS_COMPLETION_ROADMAP.md, PEGASUS_FEATURE_PROPOSALS.md, PEGASUS_DATA_LIFECYCLE.md, PEGASUS_OUTPUT_QUERY_LAYER.md, HANDOFF_2026-07-09_population_build_and_project_state.md.
