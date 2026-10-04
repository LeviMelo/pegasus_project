# `pegasus.ldo` — the Latent Dependency Operator (code + math map)

**What this is.** A faithful map of the LDO module *as implemented* — data flow, the exact mathematics
of each stage, and where each lives in code — so we stop re-deriving it from source. Verified against
live code 2026-07-11 (`file:line` may drift — trust the code, fix the doc, CLAUDE.md §IX). A *mechanics*
map, **not** a spec/contract; where the code diverges from its own docstrings or the MSD spec, this doc
reports the **code**.

> **Companion:** [`../LDO_RESIDUAL_ARTIFACT_HANDOFF.md`](../LDO_RESIDUAL_ARTIFACT_HANDOFF.md) — the open
> investigation into the residual-scan near-clique artifact. §8 (residual scan) and §10 (flags) hold the clues.

Shape symbols: **p** = variables · **S** = spatial units (municipalities) · **T** = time points (years) ·
**K** = max lag · **F** = p·(K+1) lag-extended features · **q** = kept features after coverage filter (q ≤ F) ·
**n** = samples = (T−K)·S · **r** = low-rank factor count.

---

## 0. Orientation — what the LDO computes

Takes a `(year, municipality) × variable` panel and fits a **Gaussian-graphical dependency model** in
two layers, then reads off typed `LinkRecord`s ("determinants"):

1. **Linear backbone** — a **sparse + low-rank precision** `Ω = S − L` over the lag-extended variable set
   (CPW / LVGLASSO, fit by ADMM). `S` (sparse) = *direct* conditional edges; `L` (low-rank, PSD) = *dense/
   global latent* structure. Readouts: contemporaneous (lag-0 partial correlations of `S`), lagged-directed
   (lag-peak of the partial-correlation curve), latent_shared (from `L`).
2. **Residual nonlinear layer** — form a joint-model conditional residual `e = f(Ω, Z)` and run an **HSIC**
   permutation scan on residual pairs under a structured (within spatial-block × temporal-bucket) null with
   FDR, to detect nonlinear dependence the backbone missed → `nonlinear_residual` edges. **This layer
   produces the artifact under investigation.**

Wrapped in **certification** (each edge `selected` vs `descriptive`), a **coverage manifest** (what was not
searched), and an optional **coarse→fine multiresolution** loop.

---

## 1. The spine — call graph in execution order

Entry: **`workflows/investigate.py::run_investigate`** (the sole `investigate`-stage entry; *not* in `ldo/`):

```
run_investigate(run_dir)                                        workflows/investigate.py:240
├─ compile_common_panel                → she.panel.CommonPanel               :263
├─ analytical_variable_ids             → ldo/field_selection.py (drop structural axes)  :271
├─ disease_variable_meta / _disease_graph  (disease-axis prior)              :281
├─ measured_quantity_refs              (count/exposure sidecars)             :291
├─ state_reliability_weights           (Q-tensor reliability W)              :325
├─ use_mr = resolution≠year OR cells>300k OR S>1000                          :310
└─ run_ldo_multiresolution(panel,…) | run_ldo(panel,…)                       :334/:336
```

### `run_ldo` (orchestrator.py:97-598) — single pass, exact order

| # | step | code | notes |
|---|------|------|-------|
| 1 | `_prepare_ldo_inputs` → `(raw, gf)` | :146 | `assemble_ldo_tensor` (CommonPanel→LDOField) then `gaussianize_field`. `raw` kept ONLY for LiNGAM. |
| 2 | **detrend** `gf.Z` (T≥3) | :164-169 | `common_trend`→`remove_common_trend` (default) or `per_muni`→`detrend_latent_field`. Before the fit. |
| 3 | `K = _adaptive_lag_order(K,p,T)` | :172 | `min(K,T-2)`; `p>200→K≤1`, `p>130→K≤2`. Solve O((p(K+1))³). |
| 4 | `assert_within_envelope` | :190 | LOUD refuse if fit exceeds envelope (envelope.py; **fit path only**, not the residual cache). |
| 5 | `select_lambda_stars` [opt] | :194 | StARS λ₁ (lambda_select.py; space-only subsampled). |
| 6 | disease penalty + Laplacian [opt] | :209-240 | per-pair ℓ1 + sum-of-scales Laplacian; τ empirical-Bayes from **raw** values. |
| 7 | **`lagged = fit_lagged_links(gf,K,…)`** | :249 | **★ CORE FIT** → `LaggedFit` (lags.py): S, L, Ω, readouts, `lag0_precision`(S) + `lag0_precision_full`(Ω). |
| 8 | adaptive precision controller [opt] | :257-273 | may **refit exact** (`randomized_factors=False`) if numerical error dominates. |
| 9 | `certify_approximation_on_slice` [p>48,S≥3] | :286 | §V.6 exact-certifies-approximate on a ≤700-locality slice. |
| 10 | `temporal_holdout` [T≥6] | :296 | §IX.3 out-of-time stability. |
| 11 | **`stability = stability_select(gf,K,…)`** | :304 | **★ 12 subsample refits** (edges.py; Place×Time subsampling) → selection frequencies. |
| 12 | `records = to_link_records(lagged,gf,stability)` | :321 | → `list[LinkRecord]` (edges.py). |
| 13 | `annotate_disease_provenance` + `type_mechanical_overlap` [if variable_meta] | :339-343 | **§5.3 code-overlap Jaccard guard — 0 edges on the national run (Flag §10).** |
| 14 | **residual scan** [if `run_residual_scan`] | :345-354 | `lag0 = lagged.lag0_precision_full` (**Ω=S−L**) → `scan_residual_nonlinear_edges` (§8). |
| 15 | convergence gate | :371 | tags `lowrank_unconverged_descriptive_only`. |
| 16 | certgates + `certify_links` | :382-399 | `latent_vs_lag_confounds` + `regularization_path_agreement` → certification gate + FDR (§9). |
| 17 | causal orientation [Rung-1 LiNGAM] | :406 | `orient_links` (causal/orient.py); no-op if `raw is None`. |
| 18 | Rung-2 ITS/DiD [T≥10] | :416 | `escalate_rung2_its` (causal/quasi.py). |
| 19 | spatial varying-coefficient [S>1] | :426 | per-edge BYM field, top-24 edges (spatial_field.py). |
| 20 | Kronecker joint-logdet telemetry | :470-493 | `kronecker_from_ldo(lagged.lag0_precision,…)` — **uses sparse S**; best-effort, never fails run. |
| 21 | coverage manifest + diagnostics | :498-597 | `build_coverage_manifest` (coverage.py). |
| 22 | `return LDORun(records, variables, diagnostics)` | :598 | |

### `run_ldo_multiresolution` (orch:601) → `run_multiresolution_ldo` (resolution.py:191)

`coarsen_field_spatial` (pool by first `level` cod6 digits, level=2≈UF) → coarse `run_ldo` (**residual scan
runs ✅**) → `_sensitivity_screen` recall filter → restrict fine field to candidate vars → fine `run_ldo`
(**residual scan runs ✅**) → merge → `_random_deep_audit` (`run_ldo(run_residual_scan=False)` ❌). **So the
national run runs the residual scan twice (coarse+fine); the audit skips it.**

---

## 2. Core data structures

| type | file | fields (shapes) |
|------|------|-----------------|
| **`LDOField`** | assemble.py:63 | `variables`(p)·`space_ids`(S)·`time_ids`(T)·`X`:(p,S,T) raw·`W`:(p,S,T)∈[0,1]·`exposure`:(p,S,T)\|None·`resolution` |
| **`GaussianField`** | margins.py:29 | `Z`:(p,S,T) latent Gaussian (NaN unobserved)·`W`:(p,S,T)·`count_families`·`margin_calibration`(var→KS p) |
| **`SparseLowRankFit`** | lowrank.py:33 | `S`,`L`,`precision(=S−L)` (q×q)·`factor_loadings`(q×r)·`factor_values`(r,)·`converged`,`numerical_error`,`incoherence`,`well_identified` |
| **`LaggedFit`** | lags.py:37 | `fit:SparseLowRankFit`·`lagged_links`·`latent_shared`·`contemporaneous`·**`lag0_precision`**(p×p)=lag-0 of **S**·**`lag0_precision_full`**(p×p)=lag-0 of **Ω=S−L** |
| **`LinkRecord`** | records.py:20 | 25-field frozen dataclass; `edge_type∈{contemporaneous,lagged_directed,latent_shared,nonlinear_residual,mechanical_overlap}` (full schema §7) |
| **`LDORun`** | orchestrator.py:38 | `link_records`·`variables`·`diagnostics:dict` |

Lag-extended feature matrix (lags.py:49): `(p,S,T)→(p·(K+1),(T−K)·S)`; feature index `f = lag·p + var`,
sample column `c = t_eff·S + s`. Requires `T > K`.

---

## 3. Margins — copula Gaussianization (`margins.py`)

Pushes each variable to a latent Gaussian via its marginal CDF: `Z = Φ⁻¹(F_j(X))`. Output `GaussianField.Z`.

- **`gaussianize_field`** (277-323, live): per variable — if `exposure[j]` has any positive finite cell →
  `count_exposure_gaussianize`; else → `randomized_pit_gaussianize`.
- **`randomized_pit_gaussianize`** (45-96): Dunn–Smyth randomized-quantile (discrete-data-correct). Per obs
  `x`: `u = (#{<x} + U·#{=x})/n`, `U~Unif(0,1)`, `z = Φ⁻¹(u)`, averaged over `n_pit_draws`; reliability-
  weighted variant uses cumulative weights (78-88); `u` clipped `[1e-6,1−1e-6]`; `Φ⁻¹=ndtri`.
- **`count_exposure_gaussianize`** (188-274): Poisson/NB/**ZINB** (auto via `_select_family`, dispersion +
  excess-zeros MoM, 121-150) with expected count `μ_{s,t}=λ_s·E_{s,t}`. `λ_s` = per-municipality
  empirical-Bayes Poisson-Gamma posterior mean (`_per_muni_eb_rate`, 153-185; municipality rate FE, so Z is
  deviation from the muni's OWN expected count, LDO-MARGIN-10) when `S≥3`, else pooled. Randomized-PIT lower-
  CDF form per family; **PIT-uniformity KS gate** (`kstest(u,"uniform")`, 270-272) → `margin_calibration`
  p-value → `margin_miscalibrated_descriptive_only` downgrade downstream.
- **Orphaned:** `inverse_gaussianize` (99-118) — exported, **no live caller** (partial-corr edges are
  scale-invariant, need no back-map).
- **Flag:** reliability `W` is NOT applied inside `count_exposure_gaussianize`'s PIT (only its EB exposure
  baseline); W enters at the covariance stage. `_select_family` mixes per-cell + aggregate moments (heuristic
  MoM, not MLE).

---

## 4. Covariance / spatial whitening (`covariance.py`)

Pairwise-complete correlation (each entry from cells where BOTH variables observed), PSD-repaired, feeding
the precision. `PairwiseCovariance` = `{correlation (q×q PSD), kept, min_overlap, coverage}` (30-35).

- **`pairwise_correlation`** (73-156, non-whitened path, live via lags): reliability-weighted pairwise-
  complete correlation via BLAS moments (`n_ab=Wq@Wqᵀ`, `Sx`, `Sxx`, `Cxy`, then `corr=cov/√(var_a·var_b)`);
  the `1/n` cancels → numerically identical to per-pair `np.corrcoef`. Keep features with `coverage≥30` &
  `nanstd>1e-9`; guard `n_raw≥min_overlap(20)`.
- **`whitened_lagged_correlation`** (198-318, spatial-whiten path, live, default `spatial_whiten=True` when
  S>1): GMRF-whitened variable×lag correlation via the sparse metric `Q`, **matrix-free** — whitened cross-
  cov of two lag features = `featᵢᵀ Q featⱼ`, so no dense S×S whitener / O(S³) sqrt. Accumulates
  `G += Ft@(Q@Ftᵀ)` over `t∈[K,T)`; whitened-mean centering via `H=R@Q^{1/2}·1` (Lanczos `_sqrt_matvec`,
  159-195), `G −= HHᵀ/n_cells`. Non-uniform-weights path (279-301) uses weighted mean `m_v=Σ(W·Z)/ΣW` then
  `√W⊙(Z−m)` (audit-W1 fix). **Missing cells imputed to Gaussian-margin mean 0** (241) — a dense operator
  can't honour per-cell missingness (§III.4).
- **`_nearest_correlation`** (38-70): PSD repair by shrink-to-identity `(1−δ)C+δI` with minimal
  `δ=clip((floor−λ_min)/(1−λ_min),0,1)`, `floor=1e-6·λ_max` (chosen over Higham — measured 14.5 s at q=700).

---

## 5. Sparse + low-rank precision — the LVGLASSO ADMM (`lowrank.py`, `lambda_select.py`, `disease_prior.py`)

**The live precision estimator.** Objective (lowrank.py:9):
`min_{S,L}  −logdet(S − L) + tr((S − L)·C) + λ₁‖S‖₁,off + λ₂·tr(L),  L ⪰ 0`.

**`fit_sparse_plus_lowrank`** (148-370) — ADMM, consensus `R = S − L`:
- Setup: `C = ½(cov+covᵀ)+1e-4·I`. Mixed precision: float32 iterates unless `cond(C)>1e8` → escalate float64
  (`cond_escalated`). `penalty_matrix` (p×p) overrides scalar λ₁ per-pair. Smoothness `G` symmetrized.
- Iteration (248-291):
  1. **R-step** (`_prox_neg_logdet`, 57-68): `R = argmin −logdet R + (ρ/2)‖R−M‖²`, `M=(S−L)−U−C/ρ`; eigenvalue
     map `d=(λ+√(λ²+4/ρ))/2`; **eigh always float64** (§V.1).
  2. **S-step** (`_soft_threshold_offdiag`, 51-54): ℓ1 prox `sign·max(|·|−τ,0)`, diagonal never shrunk. With
     smoothness `G`: proximal-gradient `grad=G·S+ρ(S−(R+L+U))`, step `1/(ρ+λ_max(G))` (§III.4(5); at G=0
     reduces to the plain soft-threshold).
  3. **L-step** (`_psd_project_shifted`, 71-83): `argmin_{L⪰0} λ₂tr(L)+(ρ/2)‖L−M‖²` = eigen-shift-clip,
     `shift=λ₂/ρ`.
  4. **Dual**: `U += R−(S−L)`.
  5. **Convergence**: primal-only `‖R−(S−L)‖/max(1,‖R‖) < tol(1e-5)`. adaptive-ρ default off.
- **Readout** (295-361): direct edges `partial=−S/√(dᵢdⱼ)`, keep `|partial|≥0.05`. Factors via
  `_low_rank_factors` (randomized SVD when `p>2·factor_rank_cap(24)`), keep `vals>max(1e-6,0.02·vals.max())`.
  `latent_shared` = per kept factor, variables with `|loading|≥0.3`, only factors with `≥3` strong variables
  (a concentrated factor is a direct edge, not a shared driver — CPW incoherence gate). **Mutual exclusion**:
  drop any `latent_shared` pair already in `direct_edges` (§III.4.2 one pair, one role). `_cpw_incoherence`
  (114-145) = `spread·(1−deg)·(1−overlap)` diagnostic → `well_identified` if `≥0.35`.

**λ selection — `select_lambda_stars`** (lambda_select.py:41-99, StARS): fixed subsample index sets across
the λ-grid, total instability `ξ=mean_e 2f_e(1−f_e)`, monotonized in density; `λ*` = smallest λ (densest)
with `mono≤β(0.05)`. **Subsampling is space-only** (differs from `stability_select`'s Place×Time — §10).

**Disease prior — `disease_prior.py`** (§III.4(5) `L_D`): `variable_affinity` (34-59) = p×p affinity ∈[0,1]
by **name-matching** variables to disease-graph nodes (weights 1 same category / 0.5 same block / 0.25 same
chapter; unmatched → zero rows). Two uses: (a) `disease_penalty_matrix` = per-pair ℓ1 `λ₁·(1−0.7·affinity)`
floored `0.2λ₁` (related edges survive easier), tiled across lags; (b) `sum_of_scales_disease_operator` =
`Σ τ_level·L_level` quadratic Laplacian, `τ_level` empirical-Bayes James-Stein per block
(`estimate_disease_scale_precisions`).

**Flags:** ADMM `converged=True` = "primal residual small," **not** an optimality certificate (documented
loose `tol=1e-5`, ~2377 iters from the true fixed point; a dual certificate would stop ~100 iters early and
kill recall). `numerical_error` (324-327) under randomized SVD measures the largest sub-2%-floor factor among
the `≤rank_cap` computed eigenvalues, **not** the truncated tail beyond `rank_cap` (never formed) — despite
being named/propagated as "randomized-SVD truncation error" into `latent_shared` uncertainty. Orphaned
Layer-1 cluster in **`precision.py`**: `fit_contemporaneous_precision` (single sklearn graphical_lasso K=0
baseline), dense `build_spatial_precision`, `_matrix_sqrt_psd`, `_whiten_spatial` — exported/tested, **no
live caller** (the live path is `lags→lowrank`); only `build_spatial_precision_sparse` (the sparse GMRF
metric `Q=κI+L_sym`, symmetric-normalized Laplacian) is live.

---

## 6. Lags, detrending, multiresolution (`lags.py`, `temporal.py`, `resolution.py`)

**`fit_lagged_links`** (lags.py:71-282, THE core fit): optional AR(1) `temporal_whiten` → build features (or
GMRF-whitened correlation) → `fit_sparse_plus_lowrank` → readouts.
- **Lagged readout** (208-233): partial-corr curve `partial_full[:p].reshape(p,K+1,p)` indexed
  `[target,lag,source]`; directed peak over lags **1..K only** (lag 0 excluded — an instantaneous directed
  effect only appears on the contemporaneous channel); self-links zeroed; emit where `peak_mag≥edge_threshold`.
- **The two precisions** (270-276): `lag0_precision[base]=S[base]` (**sparse S** → Kronecker readout),
  `lag0_precision_full[base]=fit.precision[base]` (**full Ω=S−L** → residual scan). Both p×p, identity-
  defaulted for dropped low-coverage variables.

**Detrend (`temporal.py`)** — three distinct operators:
- `remove_common_trend` (111-139, `common_trend`, DEFAULT): SVD of the p×T national-mean matrix `Mc`; project
  the **leading k=1** shared temporal factor out of every series (`resid=Zc−⟨Zc,G⟩G`). Surgical — preserves
  variable-specific lags orthogonal to it. **Removes only ONE shared factor** (Flag §10).
- `detrend_latent_field` (81-108, `per_muni`): per-(var,muni) polynomial residualization (degree auto 0/1/2
  by T) — a municipality fixed effect + low-order trend. Can attenuate real long lags.
- `temporal_whiten` (53-78): AR(1) `(z_t−φz_{t−1})/√(1−φ²)`, φ within-unit pooled, clipped ±0.98. Separate
  operator, applied inside `fit_lagged_links` when `temporal_whiten=True`.

**Multiresolution (`resolution.py`)**: `coarsen_field_spatial` (reliability-weighted pooling by cod6 prefix)
→ coarse `run_ldo` → `_sensitivity_screen` (recall filter: subgroup heterogeneity `should_drill_down` OR
pooled `selected|weight≥0.05|stability>0`) → restrict fine field → fine `run_ldo` → merge → `_random_deep_audit`
(FNR of the coarse screen; residual scan off). `_subgroup_effect_vectors` = per-unit within-unit correlation
tensor `einsum("ist,jst→ijs")/(T−1)` (surfaces cancellation/localized signals the pooled aggregate hides).

---

## 7. Edge readout, stability, output, spatial, Kronecker, causal (`edges.py`, `records.py`, `output.py`, `spatial_field.py`, `kron.py`, `stochastic.py`, `causal/orient.py`)

**`stability_select`** (edges.py:61-153, live; caller sets `n_subsamples=12`): refit `fit_lagged_links` on
`n_subsamples` **Place×Time** subsamples (spatial `choice(S, 0.7·S)` without replacement; contiguous temporal
window `L∈[max(K+4,0.4T),T]` when `T≥K+4` — short off-epoch windows break full-span trend-only spurious
edges). `freq[key]=count/runs` over non-failed refits; lag-tolerance merge (`|Δlag|≤1`), capped 1.0. BLAS
pinned to 1 thread/worker.

**`to_link_records`** (edges.py:229-398, live) — edge typing + inference stats:
- `lagged_directed`: `weight=partial_correlation=peak_partial_correlation`, `response_curve_ref`; **certified
  gated on stability** (`stab≥threshold`). `contemporaneous`: `lag_k=0`; **status gated only on `low_power`,
  NOT stability** (stability attached but unused in the readout gate — Flag §10). `latent_shared`:
  `weight=loading`, `partial_correlation=None`, `confounding_factor_refs=("ldo_low_rank_factor",)`.
- **Fisher-z SE (`_uncertainty`, 286-302):** `k_cond=max(q−2,0)` with `q=len(fit.S)` = FULL kept lag-extended
  precision dimension (a GLOBAL conditioning size, not per-edge Markov blanket — intentional). `dof=n_eff−k_cond−3`;
  `dof<1` → refuse a finite SE (`partial_corr_underdetermined`, uncertainty=None). Delta-method r-scale
  `se_r=(1−r²)/√dof`, `uncertainty=hypot(se_r, |r|·numerical_error)`.
- **Per-edge `n_eff` (`_edge_n_eff`, 191-218):** reliability-weighted joint count `Σ min(W_i,W_j)` × spatial
  deflation (`effective_n/n` Moran, per variable) × **Bartlett AR(1) cross-correlation design effect**
  `(1−φ_aφ_b)/(1+φ_aφ_b)` capped at 1. Skipped where already whitened (double-correction guard).
- `type_mechanical_overlap` (409-442, live, gated on `variable_meta` code sets): Jaccard `|A∩B|/|A∪B|≥0.5`
  → re-type `mechanical_overlap` + demote descriptive. `annotate_disease_provenance` (451-478): code_system /
  topology_role (both endpoints agree) / projection_status (worst of two).

**`LinkRecord`** (records.py:20-112) — 25-field frozen dataclass. Key fields: `edge_type`, `lag_k`, `weight`,
`partial_correlation` (None for latent/nonlinear), `stability`, `uncertainty`, `n_eff`, `n_conditioning`
(dof=n_eff−this−3), `null_strategy`, `fdr_method`, `fdr_qvalue`, `overlap_jaccard`, `certification_status`,
`causal_rung` (0 assoc / 1 LiNGAM+collider / 2 quasi-exp / 3 expert-only), `warnings`. `LINK_RECORD_COLUMNS`
fixes the 25-col order.

**`output.py`** (live via investigate.py:347): `link_records_to_table` JSON-encodes the three tuple fields
(`confounding_factor_refs, warnings, causal_assumptions`) to Utf8 and pins an **explicit polars schema**
`_LINK_RECORD_SCHEMA` (25 dtypes) — defeats schema re-inference (the national crash: a `float|None` column
None for the first 100 rows then a float was inferred `Null`, couldn't append). `write_hypotheses` → parquet.

**`kron.py` + `stochastic.py`** — Kronecker joint precision `Ω_var ⊗ Σ_space⁻¹ ⊗ Σ_time⁻¹`, matrix-free.
**Live in the run only as best-effort log-det telemetry** (`kronecker_from_ldo` uses **sparse S**;
`joint_logdet` → sparse Cholesky, or `stochastic_logdet` Hutchinson+SLQ only when S>20000). `matvec`/`solve`/
`to_dense`/`kron_cg_solve`/`stochastic_logdet_dense` are **orphaned** (test-only, no `src` caller).

**`spatial_field.py`** (live when S>1; investigate.py defaults `spatial_field_dir`): per selected edge X→Y,
solve GMRF-penalized within-locality slope field `(diag(A+ridge)+τL_W)β=D`; sum-exact decompose
`β=national+region+state+muni`; sign-heterogeneity flag `min(pos_mass,neg_mass)≥0.10`. Top-24 edges by |weight|.
**Flag:** live call passes `kappa=1.0` (run_ldo default), so `L_W=I+L_graph` (proper-CAR ridge), not the
module's intended pure ICAR `L_graph` at its own `kappa=0.0` default.

**Causal (`causal/orient.py`, applied at orch:406):** pairwise LiNGAM on **raw** values (unidentifiable on
Gaussian) — non-Gaussianity licence (`normaltest α=0.01`), orient toward smaller residual nonlinear-dependence
(sum of squared higher-order cross-moments) if `confidence≥0.05`; collider on unshielded triples
(`|corr(A,B)|<0.1` ∧ `|pcorr(A,B|C)|>0.2`, faithfulness margin 0.02). `_meek_r1`/`apply_meek` **orphaned**
(default off). Magic thresholds hardcoded.

---

## 8. Residual nonlinear HSIC scan (`residual_scan.py`, `hsic.py`, `nulls.py`, `fdr.py`, `multiplicity.py`)

> **UPDATE 2026-07-12 (commit `deddf68`) — this stage was OVERHAULED; §8.1–8.6 below describe the
> PRE-overhaul scan (kept for mechanism history). Current behavior:** the artifact was a **spatial
> nuisance clique** (verified per-mechanism: the confounder pair's p went 0.001→0.76 under the fix) —
> the residual conditions across variables via `Ω` but NOT on the panel's municipality/time structure,
> so every co-located pair beat the null. Fixes: **(a)** a two-way fixed-effect projection (municipality
> + spatial-block×time) removes that nuisance before HSIC; **(b)** spatial-block 2-fold **cross-fitting of
> Ω** (out-of-sample residuals — replaces the `n<10p` heuristic); **(c)** RAM-driven **ecological
> block×year averaging REMOVED** — refuse loudly if the cell-level rep exceeds memory (corrected
> low-rank byte model in `envelope.py` + bounded permutation gather in `hsic.py`); **(d)**
> normalized-HSIC dimensionless effect size (p-value-preserving). **KNOWN LIMITATION (also verified:
> cross-sectional pair p 0.001→0.87):** the municipality FE erases *cross-sectional* determinants, so
> the residual scan now tests a **within-municipality temporal** estimand — cross-sectional signal must
> come from the linear backbone (§5). **A low-rank alternative was explored + validated but NOT
> adopted, and the reason is a fundamental result:** cross-fitting a low-rank shared-municipality
> confounder removal (spatial analog of `remove_common_trend`) IS calibrated (independent pair p=0.79 —
> no manufactured edges) and keeps *specific* cross-sectional determinants (p 0.001). But
> **cross-sectional confounding is UNIDENTIFIABLE from the data alone** — a broad shared-municipality
> factor is mathematically indistinguishable from a broad genuine determinant (poverty → many
> diseases): the SVD interleaves confounders and signals by magnitude (verified — factor-0 = broad
> confounder, factor-1 = the cross-sectional signal), so *any* data-driven removal that kills the broad
> confounder also kills broad cross-sectional *signal*. No automatic rank/factor rule (parallel
> analysis, breadth) cleanly separates them. **The principled fix conditions on the KNOWN confounders**
> (population / urbanization — observed panel variables; registry-driven), extending the linear
> backbone's linear conditioning to the nonlinear residual — a well-scoped future direction. Codex's
> "permutation-resolution cliff" (6,974 edges at the 1/1001 p-floor) is downstream of the same nuisance.
> See [`../LDO_RESIDUAL_ARTIFACT_HANDOFF.md`](../LDO_RESIDUAL_ARTIFACT_HANDOFF.md).

**★ The layer producing the artifact under investigation (see the handoff).** The national live path is:
condition on `Ω=S−L` → memory guard **coarsens to (spatial-block × year) group-AVERAGED residuals** → exact
RBF-HSIC → **within-block year-shuffle** null → BY-FDR at α=0.1 → emit any `q≤0.1` pair as a `nonlinear_residual`
edge (marked `descriptive` at national large-p). Live caller: `scan_residual_nonlinear_edges(gf, lag0_precision_full, seed+2)` (orch:354).

**8.1 Residuals — `joint_model_residuals`** (residual_scan.py:114-117): `e_j = (Ω Z)_j / Ω_jj`, i.e.
`E = (precision @ Z) / clip(diag(precision),1e-12)[:,None]`; shapes `Ω`(p×p), `Z`(p×n)→`E`(p×n). `precision`
is `lag0_precision_full = Ω = S−L` (lags.py:276, lowrank.py:297), sub-indexed to `kept` (:233).

**8.2 Complete-case trim** (:213-244): `observed_full` = cells where ALL p vars jointly observed; if `<100`
and `p>2`, greedily keep the largest coverage-sorted prefix whose complete-case sample ≥100 (drops sparse
context vars). `n_eff = observed.sum()`; `n_eff < _MIN_N_EFF(100)` → raise `ResidualScanUnderpowered` (typed,
recorded, not silent).

**8.3 Coarsening — `_coarsen_residuals`** (:179-200, **the live national grain**): when
`estimate_residual_scan_bytes(p, n_eff) > 0.40·total_RAM` (:269), aggregate cells into `"{block}|{bucket}"`
groups and **average the residual within each** (`E_coarse[:,g] = mean over member cells`, :199) → `E_coarse`
(p×G), G ≈ (#blocks≈`max(5,n_muni/200)` × #years) ≈ a few hundred. `within_block_only=True`. Still over budget
→ `ScaleExceedsEnvelopeError`. **At national fine grain the byte estimate is hundreds of GB, so coarsening
always fires** — the national scan runs on **ecologically group-averaged** residuals, not cell-level.

**8.4 Structured null** (:246-319, `nulls.py`): `regime = select_null_regime(panel_type)` supplies
`permutations` (annual 1000 / monthly 2000 / cross-sec 1000) and `fdr_method` (annual/monthly **BY**,
cross-sec BH, facility Storey-q). Strata: coarse grain → `block` only; fine grain → `block|bucket`. Perms via
`generate_null_indices(strategy="restricted_intra_uf_spatial_swap", support={"uf_strata": strata})` = a **full
within-stratum shuffle** (nulls.py:145-164). **Critically, this is NOT the regime's advertised
autocorrelation-preserving `spatial_block_cyclic_time_shift`** — the live scan always runs the free shuffle and
only consumes the regime's `permutations`+`fdr_method` (residual_scan.py:302-316 documents the divergence;
`null_strategy` on emitted edges names the executed shuffle, so provenance is honest). At coarse grain the
strata are blocks, so the shuffle permutes **years within a block**.

**8.5 HSIC — `hsic.py`** (exact mode live at coarse n): RBF kernel, median-heuristic bandwidth (`_bandwidth`,
2048-pair sampled median for n>~64, x-side seed / y-side seed+1). Statistic = **biased centered-kernel HSIC**
`‖fxᵀ fy‖²_F/(n−1)²` where `fx=_low_rank_factor(centered_kernel)` (eigen-factor `A`, `AAᵀ≈k`, rank `r≈15` at
coarse n; `hsic.py:240-275`). Permutation null `_batched_perm_null` = `‖fxᵀ fy[π]‖²/(n−1)²` batched over perms
(`fy[π]` = cache-friendly row gather — the `f26f527` fix that replaced the bandwidth-bound `ky[np.ix_(π,π)]`
gather). p-value = `(1 + #{null ≥ stat}) / (1 + n_perms)` (residual_scan.py:363, strict `≥`, no epsilon).
Per-variable repr built once (O(p)); pairs scored in a BLAS-pinned ThreadPoolExecutor.

**8.6 Pairs + FDR + emission** (:341-415): `all_pairs = p(p−1)/2`, capped at `_MAX_PAIRS=150_000` (unbiased
subsample + `residual_scan_pairs_capped` warning if exceeded). `qvals = correct_p_values(pvals, regime.fdr_method)`
(fdr.py: BY step-up `q=min(prev, p·m·H(m)·π₀/rank)`). Emit `LinkRecord(edge_type="nonlinear_residual",
weight=stat, uncertainty=q, certification_status="selected" if certifiable else "descriptive")` for every pair
with **`q ≤ alpha(0.1)` — no effect-size / minimum-HSIC floor.** `certifiable = sufficient_blocks (≥5 spatial &
≥5 temporal) AND not insample_biased (n ≥ 10·p)`.

**Orphaned in `hsic.py`:** `run_hsic_scan`, `numpy_kernel_hsic_permutation_test`, `select_hsic_mode`,
`linear_hsic_statistic`, `permutation_p_value` — test/reference only, no live caller (auditing `run_hsic_scan`'s
gates gives a false picture of live behavior). `multiplicity.py` serves the *backbone* FDR (§9), not this path;
residual edges carry their q in `uncertainty`, leave `fdr_qvalue=None`, and are excluded from the panel Fisher-z FDR.

---

## 9. Certification, coverage, compute envelope (`certify.py`, `certgates.py`, `exact_certify.py`, `exhaustiveness.py`, `coverage.py`, `envelope.py`)

**`certify_link`** (certify.py:36-84) — status ∈ {`selected`,`descriptive`}, first match wins:
- Any downgrade warning (`low_n_eff`, `lowrank_unconverged`, `margin_miscalibrated`, `low_regularization_path_agreement*`,
  `possible_latent_lag_confound`) → `descriptive`.
- `mechanical_overlap`/`latent_shared` → `descriptive`. `nonlinear_residual` → `selected` iff `uncertainty is
  not None` (or policy waives). **`lagged_directed`/`contemporaneous` → CONJUNCTION**: `stability≥0.6 AND
  uncertainty is not None`.
- **`_apply_fdr`** (93-121): testable = edges with `n_eff` and `partial_correlation` both set; p-value =
  two-sided Fisher-z (`dof=n_eff−n_conditioning−3`, multiplicity.py:18-29); method = **Benjamini–Yekutieli**
  (default `fdr_dependence="arbitrary"`, valid without PRDS, monotone-conservative). If `fdr_enforce` and a
  `selected` edge is not FDR-rejected → downgrade `descriptive`. **`nonlinear_residual` records set neither
  `partial_correlation` nor `n_eff`, so they are SKIPPED by `_apply_fdr`** — their only FDR is the BY/BH inside
  the residual scan itself (§8). `assert_ldo_edge_promotion_allowed` (124-138) = hard backstop raising if a
  `selected` edge lacks stability/uncertainty.

**`certgates.py`** — the two §III.8 conjuncts folded in as warnings: `regularization_path_agreement`
(refit at λ×{0.5,2.0}; fraction of the 3 grids selecting the edge; `<0.66` → warn) and `latent_vs_lag_confounds`
(a lagged edge whose endpoints form a `latent_shared` pair → `possible_latent_lag_confound`). **Flag:** a
failed λ-grid refit is caught by a bare `try/except → None`, **silently disabling conjunct 3** with no warning
or manifest record (contra §V never-silently-degrade).

**`exact_certify.py`** (§V.6(3), gated `p>48 ∧ S≥3`): compare approximate (randomized-SVD, national) vs exact
(dense eigh, ≤700-locality slice) edge sets on their overlap; disagree iff `|w_a−w_b| > 3·√(σ_a²+σ_b²)`.
**When neither edge carries uncertainty (band=0) this becomes a strict exact-equality test** — fragile to
seed/fp differences; and slice records often lack uncertainty, so band-0 is common.

**Coverage** — TWO distinct `CoverageManifest` classes with the same name: `coverage.py:24`
(resolution/lag-orders/functional-forms searched + typed `UnsearchedRegion`s; built at orch:499) and
`exhaustiveness.py:66` (searched/unsearched pairs + audit FNR; multiresolution path). `build_coverage_manifest`
records the residual-scan functional-form gap but **NOT** the pairs-cap, the spatial-field cap, or the
silently-disabled conjunct-3 — so it is not a complete truncation ledger.

**`envelope.py`** — `assert_within_envelope` (orch:190) guards **only the fit path** (`estimate_ldo_bytes`
= `3S²·8 + S(T−K)·pk·bulk + 3pk²·bulk`) against `0.80·device_VRAM`. The residual cache is guarded separately
inside the scan against `0.40·total_RAM` (residual_scan.py:100). **Significant flag:**
`estimate_residual_scan_bytes` exact-mode charges `2·n²` per variable for "two dense n×n kernels" — but the
live HSIC retains the **low-rank n×r factor** (r≈15), not the n×n kernel, and the null is the batched
row-permute matmul, not the removed `ky[np.ix_(π,π)]` gather. So the byte model is **stale vs the post-f26f527
low-rank path** — it over-estimates by ~n/r and coarsens/refuses far sooner than true memory requires
(monotone-safe: over-estimate → refuse earlier, never green-light an OOM).

---

## 10. Flags — orphaned code, hardcodes, questionable math (for review)

**Factual, not fixed.** ★ = residual-artifact clue for the handoff.

**Wiring — the two precisions**
- `lag0_precision` = sparse **S** (lags.py:275) → Kronecker readout (orch:486). `lag0_precision_full` = full
  **Ω=S−L** (lags.py:276) → residual scan (orch:350). The `bcdd0dd` fix routed the residual scan to Ω.

**★ Residual-artifact clues (from the §8 residual/HSIC map — the sharpest diagnostic surface for the handoff)**
- **A. No effect-size floor** (residual_scan.py:402): an edge is kept purely on `q ≤ α(0.1)`; `weight` is the
  raw HSIC. At large effective n the permutation null is tight, so an arbitrarily tiny residual HSIC is
  "significant" — matches the observed near-clique of median-HSIC≈0.006 edges. Significance ≠ effect size (§IV).
- **B. Ecological averaging is the LIVE national grain** (`_coarsen_residuals`:199): the 40%-RAM memory guard
  forces the national scan onto (block×year) GROUP-AVERAGED residuals (~hundreds of munis per group). Averaging
  inflates cross-variable dependence (MAUP/ecological); HSIC then tests aggregate co-movement, not cell-level.
- **C. The executed null does not preserve residual temporal autocorrelation.** `Ω=S−L` conditions
  *contemporaneously* (lag-0), so residuals retain within-block temporal structure; but the executed null
  shuffles YEARS within a block (`restricted_intra_uf_spatial_swap`, nulls.py:161) — NOT the regime's advertised
  autocorrelation-preserving `spatial_block_cyclic_time_shift`. A free year-shuffle is **anti-conservative** for
  any pair sharing within-block temporal trend/co-movement — the most likely trend-driven near-clique mechanism.
- **D. Which dependence is tested is chosen by 40%-of-RAM** (:100): fine grain (shuffle munis) tests spatial
  dependence; coarse grain (shuffle years) tests temporal co-movement. Non-reproducible across machines.
- **Certification discrepancy to resolve:** the code marks residual edges `descriptive` when
  `insample_biased = n < 10·p` (:288,:399). The §8 map reasons this SHOULD fire at national coarse n (~hundreds)
  with large p — yet the run marked all ~7,200 `nonlinear_residual` edges `selected`. Read the actual coarsened
  `n`, kept `p`, and `certifiable` to see whether the gate fired (a live inconsistency worth pinning).
- **`mechanical_overlap` guard produced 0 edges** (edges.py:409, ICD-code Jaccard via `variable_meta`): verify
  it is *wired* (is `code_set` populated for disease vars at national scale?) and whether it should key on shared
  *carrier/source provenance*, not only code overlap.
- **`nonlinear_residual` edges bypass the panel Fisher-z FDR** (`_apply_fdr` skips them — no `partial_correlation`/
  `n_eff`); their only multiplicity control is the BY inside the scan — which passes a *pervasive* many-small-p
  artifact in bulk (fdr.py flag).

**Orphaned-but-callable** (built ahead of a consumer; no live `src` caller)
- `precision.py`: `fit_contemporaneous_precision`, dense `build_spatial_precision`, `_matrix_sqrt_psd`,
  `_whiten_spatial` (superseded Layer-1 baseline). `margins.inverse_gaussianize`. `kron`:
  `KroneckerPrecision.matvec/.solve/.to_dense`, `kron_cg_solve`. `stochastic.stochastic_logdet_dense`.
  `exhaustiveness.dispersion_screen`. `causal.orient._meek_r1`/`apply_meek` (default off).

**Stale / inconsistent**
- `envelope.estimate_residual_scan_bytes` exact-mode `2n²` model + `+1` "per-perm n×n scoring buffer" both
  describe the pre-`f26f527` dense HSIC; the live path is the low-rank `n×r` factor + batched null (§9).
- Two `CoverageManifest` classes, same name, incompatible fields (coverage.py vs exhaustiveness.py).
- `orchestrator.__all__` omits `run_ldo_multiresolution` (inconsistent with `__init__.__all__`).
  `restrict_variables` drops `count_families`/`margin_calibration` (miscalibration tag can't fire on fine/audit).
- `numerical_error` (lowrank.py:324) does not measure the randomized-SVD truncation it names (§5).

**Hardcoded thresholds / magic constants** (CLAUDE.md §V candidates, not data-derived)
- `_time_key` hardcodes `"year"` (assemble.py:81), ignoring its argument — latent gap for sub-annual grain.
- `remove_common_trend` default **k=1** (temporal.py:111) — removes only one shared temporal factor; multiple
  co-existing secular/reporting trends leave residual shared structure. Not exposed through `run_ldo`.
- StARS λ-selection is **space-only** subsampled (lambda_select.py:65) vs `stability_select`'s Place×Time.
- Certgates `min_path_agreement=0.66`, grid `{0.5,2.0}`; exhaustiveness `het=0.15`/`max=0.3` (duplicated in
  resolution.py); exact-certify slice cap `700`; residual budget `0.40·total_RAM`; spatial-field `kappa=1.0`
  live override vs module `0.0`; causal `indep=0.1`/`dep=0.2`/`margin=0.02`.
- Certgates conjunct-3 silently disabled on refit failure (no warning/manifest record).

**Contemporaneous certification asymmetry:** only `lagged_directed` is stability-gated at readout
(edges.py:342); `contemporaneous`/`latent_shared` ignore stability in the readout gate (may still be
downgraded by `certify_links`).
