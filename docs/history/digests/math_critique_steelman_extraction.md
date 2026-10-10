Extraction complete. Document: PEGASUS_MATH_CRITIQUE_STEELMAN.md (1288 lines). It has two distinct parts:

**Part A (lines 1–870):** 20 critique IDs get FULL adversarial verdicts (mathematical derivation, code citations, corrected framing). These are all in the "LDO-" prefix family (margins, PSD, whitening, ADMM, incoherence, separability, lag-related).

**Part B (lines 872–1288):** A "Thematic Index" listing **all 165 findings** (every ID that exists across the full critique corpus, not just this doc's 20 detailed ones) in 24 cross-cutting themes, each with only a **one-line restated claim** and a shared theme-level "cross-cutting recommendation" — NOT individual verdicts. Then a final "Ranked list of CRITICAL findings" (20 items) with one-line blast-radius justifications, partially overlapping the 20 detailed verdicts.

I list every ID below. For the 20 with full verdicts I give detailed summaries; for the remaining ~145 I give the ID + one-line claim as stated in the thematic index (no verdict was independently rendered for these in this document — flagging this clearly so the cross-referencing agent doesn't expect one).

---

## PART A: IDs with full adversarial VERDICTS (20 total)

### LDO-MARG-01 [CRITICAL] — Poisson-offset margin hardcodes equidispersion, contradicting MSD-I's own NB/ZINB mandate
**VERDICT: UPHELD.**
- Spec citations (MSD-I §6.2 lines 6270-6272; MSD-III §III.5 line 222) confirmed accurate — they mandate a data-aware NB/ZINB family; `count_exposure_gaussianize` (margins.py:88-115) hardcodes Poisson only, single pooled rate `lam = x.sum()/total_e`, no dispersion estimate, no ZI gate.
- PIT math confirmed correct: under true overdispersion fed through Poisson CDF, `u_i` over-disperses relative to uniform → `Z` gets heavy tails concentrated in high-exposure/high-count cells → the CPW sparse/low-rank split can misattribute this as `latent_shared` or spurious dense edges.
- Decisive point: the fix already exists and is simply unwired — `compute/glm.py` has `_estimate_nb_theta` (line 207), NB CDF pairs, `_hurdle_cdf_bounds`+`randomized_quantile_residuals` (line 302, Dunn–Smyth), and `select_count_family` (line 313, the §6.2 router) — but grep confirms LDO never imports `compute.glm`. Also `dispersion_screen` exists in `ldo/exhaustiveness.py:39` and is unused.
- Sharpening: the OTHER margin branch (`randomized_pit_gaussianize`, empirical rank) is dispersion-agnostic and unaffected — the defect is scoped to the count-exposure Poisson branch specifically (extensive counts w/ population denominators — includes the flagship pancreatic-C25 outcome).
- Fix: route `count_exposure_gaussianize` through the existing NB/hurdle machinery; must condition θ estimate on exposure structure (Pearson-residual dispersion of x against μ=λ·E, not raw var/mean of x).
- Key files: `ldo/margins.py:88-115`; `compute/glm.py:207,280,302,313`; `ldo/exhaustiveness.py:39`; `ldo/orchestrator.py:464`.

### LDO-MARG-02 [CRITICAL] — Single global rate lambda pushes real spatial/temporal rate variation into the latent 'surprise' scale
**VERDICT: PARTIAL** (mechanism real; severity overstated — two downstream layers absorb most of it, but a residual concern is genuine).
- Code fact confirmed: `margins.py:111` flat scalar `lam = x.sum()/total_e`, no stratum/spatial RE. Produces a naive-SMR-style residual `Z_i ≈ (x_i−λE_i)/√(λE_i)`, injecting a coherent municipal-development gradient into every high-rate outcome's latent scale.
- REFUTED at CRITICAL severity ("dominant discovered structure/genuine determinant edges shrunk"): two wired layers intercept it — (1) spatial GMRF whitening (`precision.py:87-98`, `covariance.py:151-198`) removes smooth spatial common-mode BEFORE edges are read (docstring: edges are "net of space"); (2) CPW sparse+low-rank split (`lowrank.py`) routes any surviving coherent cross-outcome mode into typed `latent_shared`, not into direct edges S — `covariance.py:5` explicitly names this exact collapse as the thing the design fights.
- UPHELD as genuine PARTIAL-severity defect: whitening uses a FIXED prior κI+L_W (κ=1.0 default, not fitted) so it's a mis-specified prior not the true shrunk posterior; high-frequency (non-smooth) spatial structure survives and loads onto L, inflating the latent factor; and variance mis-scaling from the wrong μ (heteroscedastic residual variance) is not undone by whitening at all.
- Fix (endorsed, minimal form): per-stratum (health-region/state) rate offset in the margin — cheaper than full EM-style copula-margin refinement which would breach the Layer-0/Layer-1 separation.
- Key files: `ldo/margins.py:111`; `ldo/precision.py:87-129`; `ldo/lowrank.py:269-302`; `ldo/covariance.py:1-8,151-198`; `PEGASUS_MSD_III.md` §III.3,III.4,III.5.

### LDO-MARG-03 [HIGH] — Randomized-PIT jitter drawn once and frozen; stability selection treats one stochastic realization as data
**VERDICT: PARTIAL** (mechanism real, severity overstated → downgrade HIGH to MEDIUM).
- Confirmed: single frozen draw (`gaussianize_field` called once, `orchestrator.py:71`; `rng.uniform` fires once, `margins.py:60,113`); `stability_select` slices the frozen `field.Z` (`edges.py:45`); U never integrated out anywhere.
- Distributional-validity point correct: Dunn–Smyth PIT is standard normal only marginally over U; freezing U makes it a fixed nuisance common to every subsample/refit.
- Overreach: "majority of latent values are pure jitter frozen into structure" overstates impact — zero-cell jitter is exchangeable noise within a shared tie-band (independent U-draws across variables), so it inflates the noise floor / attenuates toward null rather than manufacturing structured false-positive edges. Also mitigated by: rare-event routing to count-exposure margin (cell-specific tie bands), and `_MIN_N_EFF=100` gate (edges.py:23) capping the sparsest edges to descriptive.
- The propagated `edge_uncertainty` (edges.py:173-176) omits the auxiliary-randomization SE entirely — a legitimate finding.
- Fix: wrap in R≥20 outer loop over independent margin seeds, pool MI-style (Rubin's rules) for the point estimate and add between-realization variance to `edge_uncertainty`; cheaper approximation = deterministic mid-P quantile PIT for point estimate + diagnostic band from a few draws.
- Key files: `ldo/margins.py:42-64,88-115,118-144`; `ldo/orchestrator.py:71,173-176`; `ldo/edges.py:41-48,23,168,202`.

### LDO-MARG-04 [HIGH] — Empirical CDF computed on full national sample then subsampled — information leak across stability folds
**VERDICT: PARTIAL** — one prong REFUTED (Prong A: spatial stability selection), one prong UPHELD (Prong B: temporal holdout — the real bug).
- Prong A (spatial stability): REFUTED as material threat. Meinshausen–Bühlmann stability selection was never premised on independent folds (overlapping-subsample theory); the shared global CDF converges at DKW rate O_p(n^-1/2) with large national n, contributing negligible EXTRA fold-coupling beyond the 0.3-fraction direct sample sharing already inherent to the resampling scheme.
- Prong B (temporal holdout, `holdout.py:98-144`): UPHELD, genuine leak. Training-year Z values are ranked against the FULL time axis including held-out years — textbook target leakage. Inflates the reported `persistence_rate`, the exact quantity the certifier reads, defeating the entire epistemic purpose of the holdout (§III.8/§IX.3).
- Fix: do NOT re-gaussianize per spatial fold (would reduce stability-selection validity for no benefit). DO fix temporal_holdout: re-estimate margin on training window only, apply that CDF to test window (requires threading raw pre-Gaussian values into `temporal_holdout`).
- Severity retargeted: MEDIUM, and re-labeled "temporal-holdout margin leak" not "stability PIT leak."
- Key files: `ldo/margins.py:56-62`; `ldo/orchestrator.py:139-142,246`; `validation/holdout.py:81-144`; `ldo/edges.py:61-148`.

### LDO-MARG-05 [HIGH] — Per-cell reliability weights W are computed and propagated but NEVER used in the margin or the precision estimator
**VERDICT: UPHELD** (with one evidence correction that sharpens it).
- Confirmed: `W` assembled with rich provenance-graded scale (`_STATE_WEIGHT`, assemble.py:51-60), propagated through `GaussianField` (margins.py:34), sliced through every op — but both estimator paths (`whitened_lagged_correlation` covariance.py:151-220; `pairwise_correlation` covariance.py:48-109) use only a binary 0/1 finiteness mask, never W. Genuine MSD §III.2 violation ("estimation is by weighted likelihood").
- Evidence correction: critique claimed W is "never in a moment" — false. Two DOWNSTREAM/ancillary paths DO use it: `spatial_field.py:42-61` (BYM varying-coefficient) and `resolution.py:72-81` (coarsening). This doesn't rescue the design — it means weighting is applied inconsistently (honored in secondary paths, ignored in the primary edge estimator), arguably worse since coarse-pass and fine-pass edges are now weighted under different measures.
- The only W-derived quantity reaching the primary fit, `field_weights`, is a per-variable scalar (can't distinguish observed vs. broadcast cells within a variable) and even it only scales W, which the estimator then ignores.
- Fix: enter `w_ab=√(w_a·w_b)` into moments in BOTH `pairwise_correlation` AND `whitened_lagged_correlation` (the default path — a fix touching only the former leaves the primary national path unweighted); derive Kish effective n for the `_MIN_N_EFF`/SE gates (edges.py `_n_eff` currently raw cell count).
- Key files: `ldo/covariance.py:48-109,151-220`; `ldo/assemble.py:51-60`; `ldo/margins.py:34`; `ldo/edges.py:151-152`; `ldo/lags.py:109-117`; `PEGASUS_MSD_III.md` §III.2 line 197.

### LDO-MARG-06 [HIGH] — Gaussianization discards count-scale variance the denominator principle exists to preserve
**VERDICT: PARTIAL** (leaning UPHELD on diagnosis; framing over-claims, mechanism misattributed).
- Confirmed: PIT provably equalizes marginal variance across all cells regardless of μ (a 2-death cell and a 2000-death cell both get exactly N(0,1) Z). W never reaches the estimator (same finding as MARG-05).
- Overreach corrected: "count information ANNIHILATED" is too strong. The count-exposure margin DOES inject magnitude info into the location/mean of Z via quantization granularity — small μ → coarse PMF steps → wide randomization band → Z dominated by injected uniform noise (diffuse/noisy by construction); large μ → narrow band → Z tracks deviation tightly. So heteroscedasticity survives as reduced information content (added latent noise) for low-count cells, not full annihilation.
- Sharpened fix: carry a per-cell Fisher weight `w_i ∝ μ_i` into moment accumulation (closes MARG-05 and MARG-06 with one weld) rather than adding a parallel variance-stabilized (Anscombe) representation, which would reintroduce a materialized transform the denominator principle forbids.
- Key files: `ldo/margins.py:88-115,118-144`; `ldo/covariance.py:48-109,151-220`; `ldo/lags.py:108-139`; `ldo/edges.py:46`.

### LDO-MARG-07 [HIGH] — Gaussian copula imposes tail-independence that epidemic threshold/clustering dependence violates
**VERDICT: PARTIAL** (leaning UPHELD on mechanism; "attenuated toward bulk" harm claim overstated) → severity downgraded HIGH→MEDIUM.
- Confirmed: rank/PIT margin + graphical_lasso on Gaussian scale is definitionally a Gaussian copula (λ_U=0 for all ρ<1, radially symmetric/monotone). HSIC is detector-not-engine: flagged pairs are appended as separate `nonlinear_residual` records, never promoted into a term that re-enters Ω_var estimation — the primary graph stays pure Gaussian-copula. The varying-coefficient term (`spatial_field.py`) is linear effect-modification fit post-hoc on already-selected edges, not a threshold/joint-tail primitive.
- Overreach: the edge weight tracks whole-support rank/PIT concordance (Spearman-type), not linear Pearson — so it is NOT "attenuated toward the bulk" for general dependence; the true blind spot is narrower: contemporaneous, tail-concentrated joint-extreme co-occurrence with weak bulk concordance. The flagship Zika/arbovirus edges are LAGGED (via lags.py cross-lag precision) and therefore among the BEST-served cases, not the worst. Co-absence asymmetry is already mitigated: randomized PIT on zero-inflated counts spreads tied zero-mass uniformly across its CDF band, preventing spurious co-absence concordance.
- Fix: not a global t-copula (symmetric, poor fit for mixed national panel). Instead: per-certified-edge tail-dependence diagnostic (λ̂_U from empirical copula at high quantiles); escalate HSIC-flagged pairs into an explicit threshold/interaction basis that re-enters the precision fit (the real structural gap); document contemporaneous Gaussian-copula weights as lower bounds for tail-concentrated pairs.
- Key files: `ldo/margins.py`; `ldo/precision.py`; `ldo/residual_scan.py`; `ldo/spatial_field.py`; `ldo/orchestrator.py:195-332`; `PEGASUS_MSD_III.md` §III.5,§III.6.

### LDO-MARG-08 [HIGH] — Exposure denominator treated as a known constant despite being a reconstructed uncertain tensor
**VERDICT: UPHELD** (with a refinement that sharpens it).
- Confirmed: `count_exposure_gaussianize` treats `e` as error-free; §II.4 (lines 149,151) marks the population tensor as explicitly reconstructed/uncertainty-typed with per-cell error growing with anchor distance — that uncertainty is dropped. Exposure enters `assemble.py` as bare point values (no `sigma_E` channel).
- Correction to critique's algebra: the correct compound-variance deflation term is `μ²·σ²_logE` (Poisson-lognormal form), not `λ²·Var(E)` as an additive term — meaning deflation is WORST for HIGH-count cells on uncertain denominators, not uniform.
- Serious half: `lam` is a single POOLED MLE, so Z measures deviation from the national-average rate implied by each cell's denominator; a mis-vintaged regional IBGE projection (e.g. 2022 census enumerating ~10M fewer than 2021 projection) shifts every μ_i in that region coherently — a spatially-coherent shift in Z that the GMRF whitener cannot distinguish from genuine spatial dependence, actively manufacturing the spurious spatial trend §II.4 exists to prevent.
- W (reliability weight) encodes provenance state coarsely but is never consumed inside margin variance — confirmed true residual gap, not a documented-and-deferred one.
- Fix (critique's option (a) endorsed, sharpened): transport per-cell `sigma_logE` and replace Poisson PIT with Poisson-lognormal PIT. Note: variance deflation alone fixes false-precision but does NOT remove the spatial bias in the mean of Z — only option (b) (resampling E from its posterior) or an explicit spatially-correlated Var(E) term neutralizes the GMRF misread.
- Key files: `ldo/margins.py:88-115,133-134`; `ldo/assemble.py:50-60,174-207`; `PEGASUS_MSD_III.md` §II.4 lines 147-151, §III.5 line 222.

### LDO-PSD-01 [HIGH] — Pairwise-complete correlation is provably indefinite; the MSD treats it as a valid covariance
**VERDICT: PARTIAL** (leaning REFUTED on core claim; UPHELD on one narrow diagnostic gap).
- Premise correct: raw pairwise-complete matrix (covariance.py:83-100) is generically indefinite (Wothke 1993/Lounici 2014 apply — not the Gram matrix of any single dataset).
- Central factual claim REFUTED: "MSD treats it as a valid covariance / feeds indefinite C into log-likelihood" is false — critique's own evidence pointer stops 5 lines short of the operative code. Both entry points return `_nearest_correlation(C)` (covariance.py:105,216), which eigen-clips to a STRICTLY POSITIVE floor (1e-3, not 0), producing a genuinely PD matrix; `lowrank.py:168` adds a further +1e-4·I ridge before the ADMM logdet. The objective (`-logdet(Θ)+tr(ΘC)`) never sees a negative eigenvalue — it is the standard, bounded, jointly-convex graphical-lasso likelihood.
- UPHELD sliver: the recommendation's diagnostic ask — "report pre-projection min eigenvalue and Frobenius distance moved by projection, abort if large" — is genuinely missing. No gate notices if the raw matrix was badly indefinite and the projection moved it far from any real covariance.
- Fix (narrowed, not a re-architecture): make `_nearest_correlation` return `(projected, min_eig_pre, frob_shift_rel)`, surface both, add a §II.6.4-style abort when indefiniteness/shift exceeds threshold.
- Key files: `ldo/covariance.py` (`_nearest_correlation` L38-45; return sites L105,L216); `ldo/lowrank.py` L168; `ldo/lags.py` L137; `PEGASUS_MSD_II.md` §II.6.2 L247.

### LDO-NCORR-02 [HIGH] — '_nearest_correlation' is eigen-clip+rescale, NOT the metric-nearest correlation matrix (Higham)
**VERDICT: PARTIAL** (leaning REFUTED on the two "dangerous" defects; UPHELD only on naming/hygiene) → severity LOW, not HIGH.
- Defect (1) "rescale can reintroduce indefiniteness": REFUTED. The rescale `R=D⁻¹·psd·D⁻¹` is a symmetric congruence by an invertible diagonal; by Sylvester's law of inertia, congruence preserves inertia exactly — since eigen-clip floors at 1e-3>0, psd is strictly PD, so R is strictly PD. No indefiniteness risk exists.
- Defect (2) "absolute floor biases small eigenvalues/distorts edges": PARTIAL/mostly overstated. The input is already a correlation matrix (unit diagonal, trace=q, O(1)-scale eigenvalues), so the "absolute" 1e-3 floor is EFFECTIVELY a relative floor (~1e-3/λ_max, condition-number cap ~10³·q) — the critique's premise that it's applied to "raw" eigenvalues misreads the input. Downstream, edges are actually governed by explicit graphical-lasso `alpha` / ADMM `lambda1,lambda2` penalties plus an additional +1e-4·I, not by this clip — so the distortion is real but second-order, not the "ad-hoc spectral surgery concentrating distortion on edges" claimed.
- What IS correct and worth fixing: the naming/docstring overclaims "nearest correlation (Higham)" when it's a single eigen-clip+rescale step, not Higham's alternating-projection algorithm.
- Fix: make the floor relative (`rel_floor * max(vals.max(),1.0)`), record min eigenvalue/projection move. Swapping in true Higham iteration is optional polish (real cost per stability resample, no validity gain since output is already valid PD).
- Key files: `ldo/covariance.py:38-45,96-101,212-214`; `ldo/precision.py:121-125`; `ldo/lags.py:137`.

### LDO-TIME-03 [CRITICAL] — Temporal autocorrelation is never whitened before the fit; Σ_time⁻¹ is post-hoc telemetry only
**VERDICT: UPHELD** (with two sharpenings and one qualification the critique understates).
- All factual claims confirmed: only space is whitened (`lags.py:109-114`, `Q_space=κI+L_W`); `Σ_time⁻¹` via `KroneckerPrecision` (kron.py) is instantiated once inside a try/except purely for §V.6 telemetry (orchestrator.py:385-407) and explicitly documented (kron.py:26-31) as "deliberately NOT swapped into the CPW ADMM R-step"; `n_eff` is raw iid cell count (edges.py:151-176) with no √(1-φ²) or AR-adjusted DOF deflation despite φ̂ already being estimated at orchestrator.py:391-399 and then discarded.
- Sharpenings: (1) stacked-window design is worse than plain AR — adjacent sample columns (s,t) and (s,t+1) share K of K+1 lag entries by construction (deterministic near-duplication, not just stochastic correlation); (2) stability selection does NOT rescue this — `stability_select` perturbs CONTIGUOUS time windows, so it will CONFIRM (not filter) a trend-driven spurious edge as "stable."
- Qualification: the low-rank L component gives PARTIAL protection for cross-series trend co-movement (a common secular trend across variables is rank-1, can be soaked into latent_shared) — but does NOT fix effective-n inflation or within-series autocorrelation (the self-driven distributed-lag discovery, e.g. Zika's own lag structure).
- Fix: minimum viable — wire the already-computed φ̂ into `n_eff_ac = n_eff·(1-φ̂)/(1+φ̂)`, propagate into `stat_se`/`_MIN_N_EFF`; stability layer should use block/circular-block time resampling not contiguous windows; report should not present Kronecker log-det as characterizing the fit's operator.
- Key files: `ldo/lags.py:109-141`; `ldo/covariance.py:151-220`; `ldo/kron.py`; `ldo/orchestrator.py:380-407`; `ldo/edges.py:61-176`.

### LDO-WHITEN-04 [HIGH] — (κI+L_W)^{1/2} whitening imputes missing cells to 0 and uses the unnormalized degree Laplacian
**VERDICT: PARTIAL** (leaning UPHELD) — problem (1) UPHELD as the more serious; problem (2) PARTIAL/overstated.
- Confirmed: `Zc=np.where(isfinite(Z),Z,0.0)` (covariance.py:176); unnormalized `L_W=D−A` (precision.py:73,77, `κ+degree` diagonal, `-1` off-diagonal); κ fixed at 1.0, never fit (orchestrator.py:101).
- Problem (1) mean-imputation: UPHELD, sharper than stated. Because L_W is a difference operator, a missing neighbor set to 0 injects `(z_s−0)=z_s` as if the neighbor equaled the global mean — manufacturing a spurious gradient at every observed/missing boundary. Since DATASUS missingness is spatially clustered and outcome-correlated (worse where burden is high/access is low), this bias is systematic and outcome-correlated — the worst kind. Caveat: blast radius confined to the spatial-whitening step specifically (pairwise-complete correlation elsewhere is genuinely missing-aware).
- Problem (2) degree-confounded whitening: PARTIAL/overstated. The claimed consequence ("distorts partial correlations non-uniformly per edge") does not follow — the whitener applies identically to numerator AND both denominator terms of the correlation ratio, so a common per-node reweighting largely CANCELS in the ratio; it reweights WHICH municipalities dominate the national estimate (a representativeness distortion), not which edges appear.
- Fix: (a) restrict L_W to the observed sub-graph per time-slice instead of impute-0 (removes boundary-gradient bias exactly); (b) scale structured precision to unit generalized marginal variance (BYM2/Riebler-Sørbye) — repo's `spatial_field.py` BYM/ICAR machinery already exists as a donor, just unwired into the whitener.
- Key files: `ldo/covariance.py:176,194,203`; `ldo/precision.py:73,77,93`; `ldo/lags.py:104-106`; `ldo/spatial_field.py`.

### LDO-ADMM-06 [HIGH] — ADMM stopping test uses only the primal residual — can certify convergence at a non-stationary iterate
**VERDICT: PARTIAL** (leaning UPHELD on mechanism, downgraded on consequence) → reclassify HIGH→MEDIUM.
- Correct: stopping test (`lowrank.py:229`) checks only primal residual `r=R−(S−L)`; the dual residual `s=−ρ(M^{k+1}−M^k)` is never formed anywhere — textbook false-convergence mode (R settled while M still moving). Unnormalized `tol=1e-5` is scale-dependent (confirmed, worth fixing regardless).
- Overreach: "no adaptive ρ" is true but is a performance/robustness gap not a correctness bug (ADMM converges for any fixed ρ>0 on this convex problem) — critique conflates "slower" with "wrong."
- Mitigation the critique understates: the §V.6 gate only uses `converged` to DOWNGRADE edges when False — a false-positive on `converged` merely fails to add protection, it doesn't manufacture a `selected` certification on its own. Promotion to `selected` independently requires stability-across-resamples AND propagated uncertainty (§III.8) — a premature-stop-induced unstable S/L split would generically fail the stability conjunct too. So it's defense-in-depth erosion, not a single-point failure.
- One sharpening the critique misses: the incoherence gate (`min_factor_support`) and mutual-exclusion rule operate on S and L SEPARATELY at readout, not on M=S−L — so a dual residual on Δ(S−L) alone wouldn't fully catch S/L mass trading within a settled M; a rigorous certificate should also track Δ‖S‖/Δ‖L‖.
- Fix: add dual residual + scale-normalized ε=√n·ε_abs+ε_rel·max(...) tolerances at lowrank.py:224-231; add split-drift monitoring.
- Key files: `ldo/lowrank.py:206-231,258-295`; `ldo/certify.py:38-40`; `ldo/orchestrator.py:289-294`; `tests/unit/test_ldo_convergence_gate.py`.

### LDO-INCOH-07 [HIGH] — min_factor_support=3 and loading_threshold=0.3 are magic proxies for the CPW incoherence condition
**VERDICT: PARTIAL** — concern real and HIGH, but critique misdiagnoses the failure MECHANISM.
- Correct: the readout gate (`lowrank.py:270-282`) operates on post-ADMM output L, not on the true CPW incoherence condition (Chandrasekaran-Parrilo-Willsky 2012 tangent-space transversality on the TRUE (S*,L*)). The docstring (lowrank.py:147-156) overclaims by naming the gate "the CPW incoherence identifiability condition at readout." Thresholds are fixed constants, not scaled with p.
- Empirically wrong mechanism: critique claimed a weak-dense confounder gets "shattered into dozens of spurious S edges." Author ran a synthetic test (25 vars, factor loading 20) — CPW correctly absorbs the confounder into L with EXACTLY ZERO spurious S edges across confounder strengths 0.28-0.45 (no shattering; CPW works as designed).
- The REAL failure (worse, and validates HIGH severity via a different, cleaner mechanism): L2-normalized eigenvector loading of a factor spread over k variables ≈1/√k. The 0.3 gate admits a factor only while k≲11 — beyond ~11 variables the factor is dropped from the REPORT ENTIRELY regardless of strength (confirmed empirically: loadings stay ~0.24 as strength raised 0.28→0.45). A 20-variable epidemiological wave gets ZERO latent_shared edges — a false negative (silent suppression), not spurious edges.
- Fix: drop "incoherence" naming from the docstring; replace absolute `loading_threshold=0.3` with a participation-ratio/energy-concentration criterion (the current gate's logic is INVERTED for large factors — high spread, the mark of a real driver, drives every per-variable loading down and fails the gate); scale `min_factor_support` with p; add a k=20 dense-weak confounder to the planted-structure test (currently only tests k=3, loading 0.577, comfortably above 0.3 — so the test's green status is not evidence of correctness for the failing regime).
- Key files: `ldo/lowrank.py:121,147-156,269-295`; `tests/synthetic/test_ldo_sparse_lowrank_recovery.py`.

### LDO-SEP-08 [HIGH] — Separability Ω_var⊗Σ_space⁻¹⊗Σ_time⁻¹ forbids space-varying and lag-varying dependence
**VERDICT: PARTIAL** — headline mechanism real but misreads the estimator architecture → severity HIGH→MEDIUM.
- Critique wrong: the separable Kronecker operator is NOT the estimator backbone — `KroneckerPrecision` (kron.py) is used in exactly one place, feeding §V.6 telemetry only (orchestrator.py:387-403), explicitly documented as "deliberately NOT swapped into the CPW ADMM R-step." The actual estimator whitens by a shared spatial METRIC (nuisance autocorrelation) not a shared spatial SIGNAL covariance — a much weaker, defensible assumption than "every disease's spatial range is identical," which the critique's airborne-vs-vector-borne example targets incorrectly.
- Critique wrong: the "cancellation → fictitious homogeneous Brazil" risk is directly, non-post-hoc defended against — `exhaustiveness.heterogeneity_screen` explicitly scores on std of subgroup effects and its docstring names exactly this failure ("pooled mean ~0 because subgroup effects have opposite signs still scores high here"); it's wired live into the multiresolution scan plus a random deep audit measuring false-negative rate.
- Real residue: the estimator still fits ONE global Ω_var — region-varying dependency STRENGTH is recovered only per-edge, post-hoc (`spatial_field.py` BYM readout), gated by whether the edge cleared the national threshold first — so a strong-in-one-region/weak-elsewhere coupling below national threshold can be missed entirely. Sign-flip heterogeneity is inferable from `_heterogeneity_summary`'s beta_min/beta_max but not surfaced as an explicit flag. No region-stratified Ω_var homogeneity test exists.
- Fix priority: (cheap) sign-heterogeneity flag in `_heterogeneity_summary`; (larger) region-stratified Ω_var homogeneity LRT as a §V.6 conjunct; low-rank non-separable correction (`kron_cg_solve` accepts a `correction=` arg but nothing constructs one) is lower priority since Kronecker isn't promoted to the estimator anyway.
- Key files: `ldo/kron.py`; `ldo/lags.py:108-141`; `ldo/covariance.py:151-198`; `ldo/exhaustiveness.py:25-62`; `ldo/spatial_field.py:64-174`.

### LDO-MARGIN-10 [HIGH] — Count-with-exposure margin Poisson-offset; overdispersed → biased correlations
**VERDICT: UPHELD** (with one technical sharpening, one scope correction).
- Confirmed no dispersion parameter, no NB margin, no PIT-uniformity/KS gate anywhere; `dispersion_screen` is a coarse heterogeneity filter that doesn't feed back into the margin. Path confirmed reached in production (orchestrator.py:70-73).
- Corroborated independently by the project's own PEGASUS_MATH_CRITIQUE.md, which logs this as TWO findings: pooled-λ ranked CRITICAL (DIRECT-MARG-01) and overdispersion ranked HIGH (DIRECT-MARG-02) — this steelman agrees that ordering is right: even a perfectly dispersion-calibrated NB margin with a single pooled mean would STILL inject the spatial-mean/trend surface as spurious dependence, so the NB fix alone is necessary but not sufficient; the varying-rate GLM (secondary rec in the critique) should be promoted to primary.
- Spec check confirmed: MSD-III §III.5 and MSD-I §6.2 license NB/ZINB; this is spec-under-implementation.
- Fix: primary = varying baseline (`log μ = log E + s(space) + f(time)` or EB-shrunk rate); secondary = NB-with-offset dispersion α (seedable from existing `dispersion_screen`); add a KS/χ² uniformity gate on u per variable before covariance step (none exists).
- Key files: `ldo/margins.py:88-115,133-134`; `ldo/exhaustiveness.py:39`; `PEGASUS_MSD_III.md` §III.5; `PEGASUS_MSD_I.md` §6.2.

### LDO-LAG-CONF-01 [CRITICAL] — Lag-extended precision identifies conditional-Granger association, not directed effects; low-rank L cannot absorb lagged common trends
**VERDICT: PARTIAL, leaning UPHELD.**
- Correct/load-bearing: margin is fit on LEVELS with no detrending/differencing anywhere upstream of covariance — a shared 2000-2024 monotone trend with a phase offset between two variables produces exactly the peaked cross-lag curve the pipeline reads as a "discovered" distributed-lag response. `edge_type='lagged_directed'` naming over-claims relative to the taxonomy's own admission (§IV, Rung 0 = "directed only by time") that this is conditional-Granger, not causal.
- Imprecise: "L cannot absorb lagged common trends" is HALF wrong — `fit_sparse_plus_lowrank` is fed the FULL lag-extended correlation (not just lag-0 block), so L CAN in principle represent a lag-shifted rank-1 factor. The real failure is a separation/identifiability issue: `min_factor_support≥3` (lowrank.py:270-282) deliberately routes any rank-1 component supported on FEWER than 3 variables into S as a direct edge — so a PAIRWISE lagged co-trend (exactly the phase-offset case named) is actively excluded from L by the very gate that fixes the S/L collapse elsewhere, and handed to S as a spurious `lagged_directed` edge. Many-variable common trends WOULD be caught by L; pairwise trends bypass it.
- Also: temporal holdout does NOT save this — a persistent trend artifact persists into the holdout tail precisely because it's persistent.
- Fix: add a per-variable trend/spline covariate to the margin (or fit on innovations/detrended series) — §II.6.1 already promises a covariates hook the code doesn't consume, a genuine spec-vs-code gap; add an explicit common-trend null; rename `lagged_directed`→`granger_predictive` at Rung 0, reserve causal language for Rung 2+ (already-built machinery in `causal/quasi.py`).
- Key files: `ldo/margins.py`; `ldo/lags.py:5-13,136-183`; `ldo/lowrank.py:270-282`; `ldo/orchestrator.py:239-246`; `causal/quasi.py`.

### LDO-LAG-STAT-02 [CRITICAL] — A SINGLE response curve is pooled over 2000-2024, assuming time-invariant lag structure across a major epidemiological transition
**VERDICT: UPHELD** (with two sharpenings and one narrowing).
- Confirmed: both estimators (`whitened_lagged_correlation`, `pairwise_correlation`) accumulate ONE Gram matrix / moment set over ALL time slices — mathematically a time-pooled MLE covariance, valid only under an i.i.d./identically-distributed-across-t assumption. MSD §II.6.1's `Σ_time⁻¹` is a within-series smoothing prior, NOT a regime-invariance claim — the MSD is genuinely silent on stationarity. No stationarity/changepoint/CUSUM/regime-split logic exists anywhere in the LDO.
- Sharpened mechanism: pooling is not "the average curve" — since covariance is a second moment, the HIGHEST-VARIANCE regime (late-window, given rising counts/SUS-capture completeness) dominates the pooled off-diagonals, so the pooled curve is effectively the LATE-regime curve mislabeled as covering the whole window.
- Compounding factor confirmed: no detrending anywhere (`margins.py` does a single global rank-PIT over all (s,t)); a monotone completeness ramp (SIM/SINASC ~80%→95%+) enters as a shared trend, reinforcing LDO-LAG-CONF-01's spurious-edge mechanism.
- Narrowing (1): `temporal_holdout` is a partial mitigation but doesn't cover the failure — its train window ITSELF still pools ~24 years, its tail is 1 year (too short for a regime diagnostic), and it compares only SIGN persistence, not curve shape (a lag-1-to-lag-4 peak shift within a persisting edge passes undetected).
- Narrowing (2): the low-rank L may actively absorb a 2015 arbovirus surge into `latent_shared` and discard it rather than merely smearing it — arguably worse for detectability, not better.
- Fix: add a stationarity diagnostic re-fitting Ω_var on pre/post temporal-midpoint (or CUSUM changepoint), downgrade edges whose response CURVE (not just sign) diverges across halves — mirrors the existing `regularization_path_agreement` conjunct idiom; report divergence as a first-class finding (it IS the epi-transition signal); model completeness as a time-varying margin offset.
- Key files: `ldo/covariance.py:83-86,191-203`; `ldo/lags.py:62-66`; `ldo/margins.py`; `PEGASUS_MSD_II.md` §II.6.1 line 239; `ldo/certgates.py`.

### LDO-LAG-SMOOTH-03 [HIGH] — Temporal-smoothness prior biases the discovered response curve toward smoothness that may not exist
**VERDICT: UPHELD** (with two sharpenings, one over-reach corrected).
- Mechanism confirmed exactly: `build_smoothness_operator` (lowrank.py:336-337) penalty `(γ_t/2)·Σ‖S[:,a·p+var]−S[:,(a±1)·p+var]‖²` directly shrinks the difference between adjacent-lag columns of the precision that IS the reported response curve (`lags.py:160-161`) — this is a Gaussian random-walk prior on the lag profile whose posterior mean is a smoothing spline, demonstrably broadening a delta-like true response and pulling the argmax interior. MSD-II §II.6.3 line 254 explicitly calls this profile "the discovered distributed-lag response curve" — so a prior of unstated strength sits directly on the headline scientific output.
- Two decisive, unmitigated facts making this genuinely HIGH: (1) γ_t (default 0.1, orchestrator.py:118) is NEVER perturbed in certification — `regularization_path_agreement` perturbs only λ1; stability selection perturbs the lattice, not γ_t — so no gate ever checks whether peak_lag moves under different smoothing strength; (2) `fit_lagged_links`'s low-level default IS γ_t=0.0 (honest, no-smoothing) but the orchestrator OVERRIDES it to 0.1 (orchestrator.py:118 vs lags.py:82) — the honest discovery path exists and is discarded at the wiring layer.
- Correction to critique's framing: "opaque indirect deformation" is understated — under the separable Gaussian model the response curve literally IS a slice of the precision, so this is a LITERAL random-walk prior on the reported curve, not an indirect one — this strengthens (not weakens) the case for a fused-lasso/TV regularizer (allows sharp jumps, matches piecewise-smooth incubation kernels).
- Escalation from MEDIUM (as logged in PEGASUS_MATH_CRITIQUE.md as DIRECT-TEMP-01) to HIGH here is justified because completed certification work (task #48) added λ- and time-perturbation axes but specifically did NOT add a γ_t axis.
- Fix: add γ_t to `regularization_path_agreement`, report peak_lag stability across {0,γ_t,2γ_t}; default discovery runs to γ_t=0, report smoothing as a labeled robustness variant; replace L2 chain-Laplacian with fused-lasso/TV.
- Key files: `ldo/lowrank.py:188-220,306-347`; `ldo/lags.py:82,124-133,158-183`; `ldo/orchestrator.py:118`; `ldo/certgates.py:35-57`; `ldo/edges.py:70-90`.

### LDO-LAG-ANNUAL-04 [HIGH] — Lag-0 contemporaneous vs lag-k directed not cleanly separable under annual aggregation; default K=8 means 8 YEARS
**VERDICT: PARTIAL** — core aliasing physics CORRECT and unmitigated; two sub-claims (adaptive-K, "structurally impossible") REFUTED as code misreads.
- Correct/upheld: lag-0 aliasing physics is real — `lags.py:163-169` excludes lag 0 from directed peaking, emitting it only as undirected `contemporaneous`; any true sub-annual delay is thus forced into that undirected bucket — a correct consequence of the sampling interval, not a bug. The genuine, sharp finding: `LinkRecord` carries `lag_k` with NO time-unit field (a curve indexed in years is byte-indistinguishable from months); the `contemporaneous` record carries no aliasing warning at all — a real HIGH-severity honesty defect (unit-ambiguous evidence object, silent about aliasing).
- Refuted (3): "adaptive-K spends the budget on implausible 6-8-year delays" misreads the mechanism — the engine reads off the empirical peak (peak-reading, not prior-loading); if the true signal is at lag 0, it simply won't find a large lag-k correlation, and threshold/stability gates drop spurious high-lag edges. The real cost of large K is compute, not fabricated multi-year delays.
- Refuted (4): "Zika structurally impossible at default resolution" overstated — `resolution="year"` is a dataclass DEFAULT, not hard-wired; monthly grain is fully plumbed (`assemble.py:67`, `nulls.py:41-48`, `residual_scan.py:189-206` all key on "month" in resolution) and is in fact the MSD's own mandated acceptance-test resolution for Alagoas (MSD-III:476, MSD-II:578). Caveat that strengthens the critique: no acceptance test exists yet (`grep zika tests/` empty) — monthly path is plumbed but unproven.
- Fix: stamp resolution/time-unit onto every LinkRecord; add a warning tag `lag0_delay_unresolved_at_{resolution}` on contemporaneous records; optional soft warning when resolution="year" and a selected lag ≥3 (chronic-exposure review flag). Reject the critique's blunt "refuse annual K>3" recommendation — would wrongly block legitimate cancer-latency studies (the pancreatic C25 annual study).
- Key files: `ldo/lags.py:73,163-169,186-194`; `ldo/margins.py:35`; `ldo/records.py:20-49`; `ldo/edges.py:47,205-219`; `ldo/orchestrator.py:80-94`.

---

## PART B: Remaining ~145 IDs — thematic-index one-liners only (NO individual verdict rendered in this document)

These appear ONLY in the lossless "Thematic Index" (lines 872-1260, 24 themes) as a restated one-line claim, grouped with a shared theme-level cross-cutting recommendation — not individually adjudicated. Grouped by theme as the document presents them:

**Theme 1 (count noise model), also containing MARG-01/06/MARGIN-10 above:** LDO-LAG-GAUSSCOUNT-09 (Gaussian-copula partial-corr on sparse overdispersed counts, no NB dispersion, ties break PIT monotonicity), LDO-HSIC-12 (Gaussian-graphical residuals impose linear precision on overdispersed counts; HSIC audits wrong residual), LDO-CAUSAL-COUNT-DIST-13 (causal ladder uses Gaussian-OLS where Poisson/NB mandatory), LDO-CAUSAL-ITS-GAUSS-01 (ITS segmented regression on Gaussianized Z destroys level/slope semantics — also appears in the CRITICAL ranked list, #8), LDO-DIS-SPARSE-07 (rank-PIT-to-Gaussian invalid for rare/sparse disease counts), POP-GAUSS-07 (Gaussian loss on population counts wrong noise model), ASTD-POISSON-03 (Fay-Feuer CI assumes Poisson; real counts overdispersed), LDO-EXH-11 (dispersion_screen defined but never wired into drill decision), LDO-CERT-ENH-NB-15 (recommends NB/small-area-shrunk margins pre-certification).

**Theme 2 (exposure/denominator as known constant), also containing MARG-08 above:** MQ-EXPOSURE-VARIANCE-01, LDO-DIS-DIAG-DENOM-12, LDO-EXH-08, MORAN-VALUE-NOT-RATE-STD-01, RN-N-EVENTS-RATE-01, ASTD-CI-PROP-15.

**Theme 3 (identifiability — prior IS posterior), also containing LDO-INCOH-07, LDO-LAG-CONF-01 above:** POP-IDENT-01 (ranked CRITICAL #2 — intercensal demographic tensor under-determined), RACE-IDENTIFY-07 (ranked CRITICAL #13 — race bridge is deterministic pushforward), POP-GRAV-05, LDO-DIS-IDENT-03, ALGEBRA-CLOSURE-DIV-01.

**Theme 4 (uncalibrated magic-number thresholds):** LDO-MARG-13, LDO-KAPPA-05, LDO-LAMBDA-09, LDO-RANDSVD-13, LDO-EXH-01 (ranked CRITICAL #15), LDO-EXH-06, LDO-CAUSAL-NC-BINOM-04, LDO-CAUSAL-COLLIDER-THRESH-08, LDO-CERT-STABTHRESH-06, LDO-CERT-PATHGRID-09, STATE-GATE-THRESHOLDS-01, LDO-DIS-MAGIC-06, POP-MIGBOUND-06, DIVERGENCE-EPSILON-01.

**Theme 5 (multiple-testing/FDR under dependence):** LDO-LAG-MULTTEST-12, LDO-EXH-07, LDO-HSIC-05, LDO-HSIC-06, LDO-CAUSAL-MHT-14, LDO-CERT-MULTITEST-07, LDO-DIS-STAB-14.

**Theme 6 (spatial-autocorrelation mishandling/double-correction), also containing LDO-WHITEN-04 above:** MORAN-DOUBLECORRECT-01, LDO-LAG-KAPPA-11, LDO-HSIC-02 (ranked CRITICAL #7), LDO-HSIC-11, MORAN-ORDERING-PROXY-01, LDO-CAUSAL-ITS-AGG-02, ECOFALLACY-GUARD-01.

**Theme 7 (temporal autocorrelation/stationarity), also containing LDO-TIME-03, LDO-LAG-STAT-02, LDO-LAG-ANNUAL-04 above:** LDO-AR1-14, LDO-LAG-OVERLAP-05, LDO-CAUSAL-ITS-AUTOCORR-03, LDO-CAUSAL-ITS-SINGLEBREAK-10, POP-SMOOTH-08.

**Theme 8 (PSD/covariance integrity), also containing LDO-PSD-01, LDO-NCORR-02 above:** LDO-LAG-NEARCORR-07, LDO-GLASSO-11.

**Theme 9 (Kronecker separability), also containing LDO-SEP-08 above:** LDO-LAG-KRONSEP-10, POP-SEP-10.

**Theme 10 (optimizer/convergence integrity), also containing LDO-ADMM-06 above:** LDO-SMOOTH-12, POP-ITER-02, POP-CLOSURE-03.

**Theme 11 (copula/rank-PIT margin defects), also containing LDO-MARG-07 above:** LDO-MARG-09, LDO-MARG-10 [note: this reused ID number conflicts with LDO-MARGIN-10 above — thematic index lists a distinct "LDO-MARG-10: inverse_gaussianize biased off-by-one nearest-rank quantile" as separate from "LDO-MARGIN-10: count-with-exposure Poisson-offset" which got the full verdict — these are two different findings with confusingly similar IDs, flag for the cross-referencing agent], LDO-MARG-12, LDO-CERT-COPULA-08.

**Theme 12 (frozen randomness/seed bias), also containing LDO-MARG-03 above:** LDO-HSIC-09, RACE-BOOT-10.

**Theme 13 (data leakage/double-dipping), also containing LDO-MARG-04 above:** LDO-HSIC-01 (ranked CRITICAL #6), LDO-CERT-SLICE-SCOPE-04 (ranked CRITICAL #12), POP-DEATHRATE-09, LDO-CAUSAL-NC-NEFF-12.

**Theme 14 (weights defined-but-unused), also containing LDO-MARG-05 above:** LDO-MARG-11, LDO-LAG-NEFF-13, NEFF-KISH-WEIGHT-01 (ranked CRITICAL #1 — "fix first," poisons all downstream precision/gating), KISH-ABS-NEGATIVE-01, DENOMFRAG-SPEC-DIVERGE-01, CV-COUNT-VS-SAMPLE-01, TEMPROUGH-SPEC-01, LDO-NEFF-15.

**Theme 15 (causal-claim overreach):** LDO-CAUSAL-RUNG-SEMANTICS-11, LDO-CAUSAL-FAITHFUL-07, LDO-CAUSAL-COLLIDER-CONFLICT-09, LDO-CAUSAL-LINGAM-POOL-05, LDO-CAUSAL-LINGAM-LINEAR-06, LDO-CAUSAL-DID-ORPHAN-15, LDO-HSIC-15.

**Theme 16 (certification-layer statistical validity):** LDO-CERT-FISHERZ-01 (ranked CRITICAL #11), LDO-CERT-UNITS-02, LDO-CERT-LATENTBAND-03, LDO-CERT-SLICE-BIAS-05, LDO-CERT-HOLDOUT-NULL-10, LDO-CERT-CONJ-CONFIRM-11, LDO-CERT-BAND-ZERO-12, LDO-CERT-SVDERR-13, LDO-CERT-ENH-CONFORMAL-14, LDO-EXH-13.

**Theme 17 (exhaustiveness/coverage-guarantee weaknesses):** LDO-EXH-02 (ranked CRITICAL #17), LDO-EXH-03 (ranked CRITICAL #18), LDO-EXH-04 (ranked CRITICAL #16), LDO-EXH-05, LDO-EXH-09 (also Theme 19), LDO-EXH-10, LDO-EXH-12, LDO-EXH-14.

**Theme 18 (HSIC residual-scan specifics):** LDO-HSIC-03, LDO-HSIC-04, LDO-HSIC-07, LDO-HSIC-08 (also Theme 19), LDO-HSIC-10, LDO-HSIC-13, LDO-HSIC-14.

**Theme 19 (boundary-change/geography harmonization):** LDO-EXH-09, LDO-HSIC-08 (both cross-ref'd from 17/18), LDO-DIS-BOUNDARY-13, POP-DISC-04, INTERP-NEGMIG-13.

**Theme 20 (age-standardization/small-area measurement):** ASTD-SAE-02 (ranked CRITICAL #14), ASTD-AGEMISS-01, ASTD-STDPOP-04, ASTD-OPENEND-05, ASTD-NUMSTAB-06.

**Theme 21 (race bridge/demographic reconstruction internals):** RACE-PRIOR-08, RACE-DECISION-09, INTERP-COHORT-11, INTERP-GEOM-12, POP-GEOM-13, POP-AGGREG-11, POP-BIRTH-15, POP-VALTUNE-14.

**Theme 22 (numerically explosive ILR/structural-zero handling):** POP-RACEILR-12, RACE-ILR-14.

**Theme 23 (disease-axis prior construction, L_D):** LDO-DIS-TREE-01, LDO-DIS-SCALES-02, LDO-DIS-MULTICAUSE-04, LDO-DIS-MAXWEIGHT-05, LDO-DIS-CHAPTER-08, LDO-DIS-RANGE-09, LDO-DIS-OVERLAP-10, LDO-DIS-PROV-11.

**Theme 24 (GPU-acceleratable/dense-scaling heavy math):** LDO-DIS-QUAD-DENSE-15, LDO-RANDSVD-13 (also Theme 4), LDO-CERT-SVDERR-13 (also Theme 16).

---

## Ranked list of 20 CRITICAL findings (document's own closing section, lines 1261-1288)

Stated by the document as "the input flags 20 CRITICAL findings," ranked by blast radius (not independently re-verdicted here beyond what's already covered above):
1. NEFF-KISH-WEIGHT-01 — n_eff uses rate values not denominators; poisons every rate field's effective sample size downstream. "Fix first."
2. POP-IDENT-01 — intercensal demographic tensor under-determined; the denominator every rate divides by is fabricated.
3. LDO-MARG-01 (full verdict above: UPHELD)
4. LDO-MARG-02 (full verdict above: PARTIAL)
5. LDO-TIME-03 (full verdict above: UPHELD)
6. LDO-HSIC-01 — residual scan double-dips on in-sample residuals; anticonservative by construction.
7. LDO-HSIC-02 — restricted permutation non-exchangeable on spatial panel; nulls stay anticonservative even after double-dip fix.
8. LDO-CAUSAL-ITS-GAUSS-01 — ITS on Gaussianized Z destroys level/slope semantics; causal claims measure nothing interpretable.
9. LDO-LAG-CONF-01 (full verdict above: PARTIAL leaning UPHELD)
10. LDO-LAG-STAT-02 (full verdict above: UPHELD)
11. LDO-CERT-FISHERZ-01 — wrong SE for whitened partial correlations; certification uncertainty miscalibrated at its core.
12. LDO-CERT-SLICE-SCOPE-04 — exact-certifies-approximate on same slice certifies the method, not the claimed national scope.
13. RACE-IDENTIFY-07 — deterministic linear pushforward; self-declared-race counts not actually inferred.
14. ASTD-SAE-02 — direct standardization indefensible at municipal scale; SAE/BYM prescribed by MSD, ignored.
15. LDO-EXH-01 — screen thresholds 0.15/0.30 arbitrary, no false-negative guarantee.
16. LDO-EXH-04 — coarse→fine naive refit reintroduces the Simpson/cancellation blind spot §VIII.2 claims to avoid.
17. LDO-EXH-02 — per-unit correlation over T=26 dominated by sampling noise, misread as heterogeneity.
18. LDO-EXH-03 — FNR is a bare point estimate with mismatched denominator; recall asserted not bounded.
19. (document notes items 19 is a self-referential aside pointing back to LDO-HSIC-01/02 and LDO-LAG-STAT-02, already listed — no new ID)
20. LDO-MARGIN-10 (full verdict above: UPHELD) — "a specific, high-severity instance of the Theme-1 pattern already led by LDO-MARG-01."

---

## Overarching / meta conclusions stated by the document

The document has no separate prose "meta-conclusions" preamble — its overarching pattern emerges from the aggregate of the 20 detailed verdicts and the theme cross-cutting recommendations. Patterns explicitly stated or clearly recurring across multiple verdicts:

1. **Recurring verdict shape: "mechanism real, severity/consequence overstated."** Of the 20 fully-adjudicated findings: 4 UPHELD outright (MARG-01, MARG-05, TIME-03, LAG-STAT-02, MARGIN-10 — actually 5), 1 UPHELD-with-sharpening (LAG-SMOOTH-03), and the remaining ~14 are PARTIAL, nearly always with the same shape: the code-level fact and the core mathematical mechanism are confirmed correct, but the critique's claimed DOWNSTREAM CONSEQUENCE (e.g., "spurious edges," "unbounded objective," "reintroduced indefiniteness," "attenuation toward bulk") is shown to be blocked, mitigated, or simply mis-derived by an existing downstream safeguard the critique didn't fully trace.

2. **"The codebase has more defense-in-depth than the critique assumes" — a recurring specific pattern.** Named explicitly and repeatedly: spatial GMRF whitening + CPW sparse/low-rank S vs. L role-split (MARG-02, SEP-08) keeps coherent common-mode contamination out of direct edges and into a typed `latent_shared` bucket instead; the §V.6 convergence gate only ever downgrades (never promotes) so a false-positive `converged` flag alone can't manufacture a certified edge (ADMM-06); independent stability + uncertainty conjuncts gate `selected` status regardless of one weaker guard (ADMM-06, MARG-02); `_MIN_N_EFF=100` caps sparsest edges to descriptive regardless of margin randomization noise (MARG-03); `_nearest_correlation`'s strictly-positive eigen-floor plus Sylvester's law of inertia genuinely guarantees PD output (PSD-01, NCORR-02, refuting two "dangerous" claims outright).

3. **"The fix already exists in the repo and is merely unwired" — the single most common concrete finding across UPHELD/PARTIAL verdicts.** Explicitly stated for: MARG-01 (full NB/hurdle/dispersion-router machinery in `compute/glm.py` never imported by LDO), MARG-08/MARGIN-10 (`dispersion_screen` computed and discarded), WHITEN-04 (BYM/ICAR scaled-precision machinery in `spatial_field.py` not wired into the whitener), TIME-03 (φ̂ already estimated at orchestrator.py:391-399 then thrown into telemetry instead of the SE), LAG-SMOOTH-03 (the honest γ_t=0 no-smoothing default exists in the low-level API but is overridden to 0.1 at the orchestrator layer), MARG-05/MARG-06 (W is propagated everywhere but the one weld into the moment computation was never made).

4. **A distinct, recurring failure of the critique's own mechanism-tracing.** In at least 3 cases the document finds the critique's STATED harm mechanism is empirically or mathematically backwards, even while the underlying concern is real: LDO-INCOH-07 (claimed "shattering into spurious S edges" — empirically tested and found FALSE; actual failure is silent total suppression of large factors via a 1/√k loading-threshold interaction); LDO-LAG-CONF-01 (claimed "L cannot represent a lag-shifted factor" — false, it can in principle; actual failure is the `min_factor_support≥3` gate specifically excluding low-support/pairwise trends from L); LDO-NCORR-02 defect 1 (claimed the rescale step reintroduces indefiniteness — refuted outright via Sylvester's law of inertia).

5. **Severity is very frequently downgraded on reassessment**, and the document is explicit and numeric about this in nearly every PARTIAL verdict: MARG-03 HIGH→MEDIUM, MARG-04 HIGH→MEDIUM (retargeted from stability-selection to temporal-holdout), MARG-07 HIGH→MEDIUM, NCORR-02 HIGH→LOW, ADMM-06 HIGH→MEDIUM, SEP-08 HIGH→MEDIUM. No case in the 20 fully-adjudicated findings has severity escalated above what the critique stated, except LAG-SMOOTH-03 (already escalated by the critique itself from a prior MEDIUM finding, and the steelman endorses keeping it HIGH).

6. **Corroboration by an independent source.** Two findings (MARGIN-10, and by reference MARG-01/MARG-02) are cross-checked against the project's own separate audit document, `PEGASUS_MATH_CRITIQUE.md`, which logs the same defects under different IDs (DIRECT-MARG-01/02) — used as independent evidence that a finding is real rather than a misread of the code.

7. **Recommended fixes are consistently reframed as narrower/cheaper "wiring" tasks rather than the critique's broader recommended re-architectures** — e.g., PSD-01 explicitly rejects re-architecting the estimator in favor of adding a diagnostic/abort; NCORR-02 rejects swapping in full Higham iteration as unnecessary cost for no validity gain; SEP-08 deprioritizes the low-rank non-separable correction since the Kronecker operator isn't even the estimator.

No separate "lessons about the critique process as a whole" section is stated as prose at the document's start or end — the file opens directly into the first verdict (LDO-MARG-01) and closes directly with the ranked CRITICAL list (item 20), with the thematic index's per-theme "cross-cutting recommendation" lines serving as the closest thing to summary/meta content, and these are theme-specific engineering recommendations rather than reflections on critique methodology.
