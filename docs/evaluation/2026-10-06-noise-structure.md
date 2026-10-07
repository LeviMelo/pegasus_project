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
