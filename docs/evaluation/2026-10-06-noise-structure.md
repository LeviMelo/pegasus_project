# N1: the predictive's noise structure

**Regime.** pegasus_core `design-v0`, the commit carrying this entry. Fields: SIM.DO 2010–2023 (I60-I69, I00-I02), SIH-RD J09-J18, SINASC-DN, SINAN-SIFC. Script `data/noise_structure_check.py`; artifact `data/probes/noise_structure.json`.

**What was measured, and why.** Stage B's predictive treated a place's periods as independent. The time negatives that failed on SIH, SINASC and SIFC suggested serial dependence. Before modelling it, its form was measured.

**The residual covariances are not a stationary noise.** The latent lag-k covariances of B1's residuals, relative to the frailty variance and inverted from the count moments, are:

| field (B1) | lag 0 | 1 | 3 | 9 |
|---|---|---|---|---|
| stroke deaths | 2.10 | 0.80 | −0.66 | −2.75 |
| SIH pneumonia | 1.01 | 0.55 | 0.04 | −0.53 |
| SINAN SIFC | 1.92 | 1.11 | −0.26 | −1.47 |

A covariance that turns strongly negative at long lags is the signature of place-specific trends that B1 does not model. These are departures from the reference, which is what a trend model tests. So a single AR(1) fitted to these residuals read ρ ≈ 0.8, and a persistent-share model hit its bounds.

**The model adopted** (`surprise.Noise`, `noise_structure`):
- **Marginal.** Each cell is NB(μ, φ/κ): a gamma frailty with variance κ/φ, times a Poisson.
- **Serial dependence.** The frailties of a place's periods are joined by a Gaussian copula with AR(1) latent correlation ρ.
- **Estimation.** (κ, ρ) come from bias-corrected moments of regression residuals. Each place's standardised series loses its own level and linear trend (the projection M), and E[Σ e_t e_{t+k}] = tr(L_k M Σ M) is matched at lags 0..2.
- **κ joins the predictive's dispersion** before the PIT, so every detector and every world reads one law.
- **Why gamma rather than lognormal.** A first version drew lognormal frailty. At equal variance its right tail is heavier than the NB's, so the cell detectors' null worlds produced findings: 4 of 10 on stroke, 9 of 10 on SIH.

**Recovery on simulated worlds** (3,000 places, 14 periods, place trends present in y and absent from the reference):

| planted (κ, ρ) | (1, 0.4) | (2, 0) | (2, 0.5) | (0.5, 0.2) |
|---|---|---|---|---|
| recovered | (0.99, 0.38) | (2.20, −0.01) | (2.07, 0.42) | (0.51, 0.18) |

**On the real fields** (B1): stroke (3.25, 0.63); SIH (1.25, 0.62); SINASC (3.35, 0.95, at the bound); SIFC (5.27, 0.83).
- **Sparse rheumatic fever (I00-I02)** reaches κ in the hundreds. Its frailty share is 0.2 %, so its 16 % excess variance attributed to an NB2 frailty inflates κ. Whether a sparse field's excess is NB1-like is open.
- **High ρ.** Births per place wander nonlinearly beyond a linear trend. That wander is the departure models' to judge, against their empirical nulls (stage C), not B's noise.

**The time-shift negative is not a null for slow-shape detectors.** Shifting a place's series circularly keeps its trend and turns it into a jump at the wrap. Its failures on change point and trend therefore measured the negative's construction, not the noise model's. N1's acceptance moves to the grid's null worlds, which now draw the field's counts with this noise (`harness.grid_world`), and to the space negative (MSR), which stays valid.

## The estimator on its own worlds (2026-10-07)

**Why.** The multiscale step's null worlds showed that the refit's N1 put ρ at its bound (0.95 against a generating 0.81). Rivals were declared and tested on the grid's stroke null worlds:
- `data/noise_bias_diag.py`, `data/noise_recovery.py`, `data/noise_clip_bound.py`;
- artifacts `data/probes/noise_{bias_diag,recovery,clip_bound}.json`.

| estimator | ρ on null worlds (generating) | δ | measles B05 ρ |
|---|---|---|---|
| κ fixed at central matching, raw residuals clipped at 0.5 % | 0.95, 0.95, 0.95 (0.81) | 0.12–0.22 (0.58) | – |
| lag scale fitted with ρ, δ; same clipping | 0.95, 0.95, 0.95 (0.75) | 0.55–0.65 (0.61) | – |
| the same, unclipped | 0.82 (0.75); about the true mean and φ, 0.765 | – | – |
| normal scores (randomised PIT) clipped at 0.5 % | 0.77, 0.83 (0.66) | 0.58–0.59 | 0.55 |
| **normal scores clipped at the universal threshold** (Φ⁻¹(1 − 1/2N), 4.36 here) | **0.65, 0.69 (0.66)** | 0.59–0.61 | 0.54 (unclipped 0.30) |

**Two biases, each with its own cause:**
- **κ held fixed.** κ is the marginal of residuals about a fit that absorbs part of a persistent frailty. Held fixed, it left lag 1 to be met by ρ at its bound. The lag model now has its own frailty scale; δ recovered.
- **Clipping at 0.5 %.** Clipping heavy-tailed scores at 0.5 % shrinks the lag-0 moment more than the cross-products. The universal threshold leaves null fields untouched and still bounds an epidemic's cells: measles, chikungunya and diarrhoea stay off the bound.

**Adopted** (surprise cache 12). The real fields move to: stroke ρ 0.57, δ 0.64 (was 0.81, 0.58); SIH measles 0.54, 0.26; chikungunya 0.40, 0.46; diarrhoea 0.76, 0.80.
