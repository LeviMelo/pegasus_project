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
