# O7: the joint factor model on a planted world

**Regime.** pegasus_core `design-v0`, the commit carrying this entry. Script `data/o7_factor_synthetic.py`; artifact `data/probes/o7_factor_synthetic.json`.

**The world.** 30 fields of Poisson counts over the 5,570 municipalities and 14 periods, with gamma expected counts (mean 20). Three planted space–time factors (graph-diffused regional bumps × temporal bumps) are loaded by fields 0–4, 5–9 and 10–11; the other 18 fields load on nothing.

**What is counted.** Each pair's relation z (`Factors.relations`): the implied correlation of the two fields' departures times √n_eff. It is compared between planted and null pairs, alongside the factors the ARD keeps.

**Two fits rejected first.**
- **Alternating MAP with GMRF factors.** It made every field load on every factor (null pairs' shared correlation up to 0.83): without the factors' posterior covariance, a factor absorbs the fields' own noise.
- **Loading z-scores.** They are conditional on the scores and too small to test by: null fields read z ≈ 12.

**The EM of probabilistic factor analysis with ARD** (Rubin & Thayer 1982; Bishop 1999), on departures lifted by sums to each rung of the ladder of supports:

| support | cells (eff.) | factors kept | planted pairs, median z | null pairs, max \|z\| |
|---|---|---|---|---|
| municipality | 59,687 | 0 | – | – |
| immediate region (510) | 5,262 | 3 | 3.64 | 1.37 |
| intermediate region (133) | 1,342 | 3 | 4.78 | 1.77 |
| UF (27) | 265 | 3 | 6.55 | 2.82 |

**Reading.** The ARD finds K = 3 wherever the signal is visible; at the municipal grain the localised factors drown. Relations are therefore read over the ladder, with one FDR across supports. A fit takes 1–4 s for 30 fields on the GPU. Still to come: lagged loadings and the null bench (independent fields drawn with N1 noise).

## 2026-10-07: graph-frequency bands and innovations replace the ladder

**Correction.** The ladder above reads relations at administrative units fixed in advance, so its result depends on the zoning (the modifiable areal unit problem). With leads included it was also wrong: stacking each field with its own past (lags 0–2), the same world with **no** planted factor reported **2,405** relations. Scripts `data/o7_factor_lagged.py` (the ladder) and `data/o7_factor_bands.py` (the replacement); artifacts `data/probes/o7_factor_lagged.json` and `o7_factor_bands.json`.

The world is the one above, plus field 12 following factor 0 by two periods, with N1 noise (gamma frailty, AR(1) copula ρ 0.6). Three causes of false relations, each removed in turn:

| change | null world: relations reported | planted world: false |
|---|---|---|
| ladder, log-ratio departures | 2,405 | 2,275 |
| graph bands, log-ratio departures | 2,482 (in the lowest band: Jensen's bias of the log ratio is shared by all fields) | 2,282 |
| bands, relative excess (y − μ)/(μ + ½) | 584 (the finest band: lagged copies of a serially correlated field) | 688 |
| bands, AR(2) prewhitening pooled per field | 35 (a big place's correlation differs from a small one's) | 52 |
| **bands, innovations whitened by N1 per place** | **0** | **0** |

**Planted world with the final pipeline:**
- The lead of fields 2–4 to field 12 is reported in the band of about 220 places, at lags 1 and 2. The true lag is 2; the temporal bumps are smooth.
- 8 of the 21 same-lag planted pairs are reported. Power is moderate, and every report is correct.
