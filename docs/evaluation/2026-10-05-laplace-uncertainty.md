# The Laplace uncertainty layer: cost, accuracy, and what it does to calibration

**Scenario.** `scripts/measure_laplace.py` (modes `ix`, `dengue`, `bp-ix19`, `bp-dengue18`, `bp-dengue14`; 32 draws, GPU), `scripts/measure_laplace_fs.py`, and the small-block checks `data/laplace_exact.py`, `pc_test.py`, `pc_var.py`, `region_phi.py` (local, gitignored). Artefacts in the worktree: `data/logs/laplace_<mode>.json`, `laplace_fs_<mode>.json`, `laplace_exact_ix_50.json`, `region_phi.json`.
**Regime.** Branch `worktree-agent-afb63cec4eed96769` after merging design-v0 (d7f4514), 2026-10-05; fits as cached in `pegasus_home/monolith` (IX SIM.DO 2010-23 knn6; contiguity for BP; dengue monthly). Posterior: NB expected information, perturbation draws, block-Jacobi CG, `Expectations(laplace=32)`.

## The draws

Exact check (50-place IX block, P = 5,588, dense pseudo-inverse): the median |log variance ratio| of a cell's linear predictor is 0.250 / 0.169 / 0.121 / 0.081 at S = 16 / 32 / 64 / 128, against the Monte-Carlo floor √(2/(S−1)) of 0.365 / 0.254 / 0.178 / 0.125; bias ≤ 0.07. A cell-space Hutchinson probe errs 0.223 (K = 16) and 0.112 (K = 64) and costs 186 / 659 s; the inverse diagonal alone (1/diag H) errs 0.56 with bias +0.52.

**Cost.** The diagonal preconditioner hit the 1,000-iteration cap on every solve (τ up to 10⁸ makes smooth ICAR modes 10⁵ times softer than the diagonal says). Block-Jacobi per effect (diag(Σw) + τQ, one sparse LU per batch row, applied as CᵀB⁻¹C), relative tolerance 10⁻³:

| small block, CPU | iterations | s / draw | cell-η error vs converged | draw variance vs fully converged (log ratio, median; p5 / p95) |
|---|---|---|---|---|
| diagonal, at the cap | 1,000 | 7.5 | 3.7e-2 | n/a |
| block, tol 1e-3 | 40 | 0.5–0.7 | 6.5e-2 | +0.001; −0.05 / +0.07 |
| block, tol 1e-2 | 18 | 0.3 | 1.7e-1 | +0.000; −0.19 / +0.24 |

Full models: 50 iterations per draw (IX), 88 (IX, BP fit to 2019), 7.7 (dengue); residual ≤ 10⁻³; GPU peak 0.8–2.1 GB; 32 IX draws take 2–3 minutes on a loaded machine. Default is now `tol = 1e-3`, `precond = "block"`.

## What it changes in calibration

Parameter uncertainty is small beside the overdispersion. μ-weighted CV²(μ) from the draws against the NB's 1/φ (IX 0.167, dengue 4.3): IX B1–B2 0.001–0.017 (exact, small block: 0.0023 against 0.15), dengue B1 0.0014 (0.03 % of 1/φ), BP IX 0.001–0.013.

**Centring.** The posterior mean of μ sits exp(Var η / 2) above the MAP's expectation, which the score equations tie to the data. In-sample it overshoots totals (IX +0.9 %) and worsens KS (IX B1 0.034 → 0.055). In-sample tiers are therefore centred on the MAP's μ with the draws' variance (`center="plugin"`, the default). BP predicts cells the fit has not seen and is shown both ways.

In-sample, block-φ KS overall / worst region (with the field's place-year φ_extra KS moves by ≤ 0.003 everywhere):

| field | tier | MAP | Laplace |
|---|---|---|---|
| IX | B1 / B2 | .034/.051 / .017/.035 | .027/.045 / .012/.025 |
| I20-I25 | B1 / B2 | .032/.059 / .018/.042 | .024/.051 / .017/.031 |
| I60-I69 | B1 / B2 | .013/.029 / .011/.025 | .008/.024 / .018/.030 |
| I64 | B1 / B2 | .025/.038 / .019/.041 | .018/.032 / .019/.036 |
| I10-I15 | B1 / B2 | .044/.050 / .035/.037 | .038/.044 / .024/.027 |
| dengue | B1, B2, B2s | .250/.336, .217/.289, .179/.255 | .249/.335, .216/.287, .177/.252 |

Prospective (BP), block-φ KS overall / worst region. "+ forecast" adds the history's forecast error (annual: the RW2 forecast variance; monthly: the empirical level-change variance, a heuristic):

| BP | MAP | Laplace | + forecast | + forecast, posterior mean |
|---|---|---|---|---|
| IX, to 2019 (obs/exp 1.019) | .126/.195 | .118/.187 | .102/.171 | **.056/.126** (1.002) |
| I20-I25 | .069/.135 | .060/.126 | .051/.120 | .048/.116 |
| I60-I69 | .040/.117 | .033/.113 | .025/.108 | .030/.074 |
| I64 | .113/.154 | .101/.144 | .097/.141 | .111/.155 |
| I10-I15 | .145/.165 | .139/.158 | .135/.153 | .113/.133 |
| dengue, to 2018 (obs/exp 2.8) | .162/.264 | .162/.263 | .132/.207 | .104/.146 (1.95) |
| dengue, to 2014 (obs/exp 2.25) | .132/.229 | .129/.224 | .114/.165 | .112/.189 (2.04) |

Dengue BP uses the monthly default of design-v0 (h held at its last 36 months, `level36`; the forecast variance is measured over the same window). With the field's φ_extra: 0.290 / 0.500 (to 2018) → 0.251 / 0.450; 0.207 / 0.300 (to 2014) → 0.190 / 0.279. With the earlier 12-month baseline the same columns read .179/.298 → .122/.186 (obs/exp 3.6 → 2.45) and .141/.195 → .110/.155 (2.6 → 2.31), and the field-φ KS 0.310 → 0.275 and 0.225 → 0.205.

## Verdict

1. **Parameter uncertainty does not fix the miscalibration.** It is 0.03–10 % of the overdispersion in-sample and moves KS by ≤ 0.01; for BP dengue it moves nothing (0.162 → 0.162).
2. **BP chapter IX (annual): the layer helps, and the history's forecast error does the work.** Parameters alone take KS 0.126 → 0.118; the forecast variance with posterior-mean centring takes it to 0.056 and obs/exp from 1.019 to 1.002. The regional criterion (≤ 0.05) is still missed (worst region 0.126): a regional departure in level.
3. **BP dengue is not a variance problem.** Observed cases are 2.0–2.8 times the forecast (2.6–3.6 with the 12-month baseline); the epidemic years 2015–16 and 2019–23 lie outside any flat-level history. The forecast variance narrows the PIT (0.162 → 0.104 to 2018) but cannot centre it, and the field's own φ_extra stays at 0.25–0.29. What is missing is a temporal effect (epidemic level, climate), not wider intervals.
4. **The Centro-Oeste failure is dispersion structure by region.** φ_extra estimated per macro-region (B1: Centro-Oeste 0.37, Sul 0.15, Nordeste 0.21, one global value 0.25) takes Centro-Oeste's KS at B1 from 0.103 to 0.040 (Sudeste rises 0.068 → 0.082 and becomes the worst region) and calibrates B2s in every region (all ≤ 0.028; overall 0.018). Not adopted; OQ 6.
5. **Fellner–Schall on the full Hessian disagrees with the block-diagonal one for space.** IX, τ now → full Poisson / full NB: s_all 425 → 81 / 72, s_grp 139 → 28 / 26, v_all 158 → 108 / 106, v_cat 4.4 → 4.0, f_grp 2.3 → 2.1; time effects unchanged; v_grp diverges (shrunk to nothing). Dengue: s_all 1.5·10⁶ → 4·10⁷, the rest unchanged. A refit at the NB-FS τ's has not been run, so the effect on calibration is open.

## A correction found on the way

`Expectations.surprise` refit B2/B2s place means (μ → rμ) but kept B1's Σμ², so the aggregate dispersion φμ²/Σμ² was inconsistent (mean cell 1/φ 3.1 at dengue B2 and 22.7 at B2s, against 0.17). Σμ² now scales by r². Dengue, field φ: B2 0.028/0.065 → 0.034/0.066 (no longer under 0.03), B2s 0.011/0.047 → 0.019/0.048 (still calibrated); IX B2 is unchanged to the third decimal. The figures in `2026-10-05-dengue-monthly.md` are the earlier ones (a correction line is added there).
