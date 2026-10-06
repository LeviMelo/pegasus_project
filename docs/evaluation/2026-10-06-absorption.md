# How much of a departure the fit absorbs (O5's first measurement)

**Regime.** Pegasus_core `design-v0` at 1f5da4b; SIM.DO chapter IX fitted 2010–2021 under ADR-0024's defaults. Script `data/o5_absorption.py`; artefact `data/probes/o5_absorption_ix.json`; 2026-10-06.

**What and why.** The v0 power curves (`harness.power_curve`, `region_power`) plant y' = y + Poisson((θ − 1)μ) into a null world and read it against the *same* μ. A departure in the data the model is fitted to is instead partly taken up by the model's own effects. So the curves measure power against a fit that never saw the signal. To measure this, each signal was planted at the leaf level into the real counts and the mean was refitted at the fit's strengths (warm start, as `scripts/sbc.py` does: 8–22 s a refit). The figure read is the share of the locus's log excess that the refit took: 1 − log(Y′/μ_refit) / log(Y′/μ_fit).

The prediction was declared in the script before running: a national year is absorbed wholly, a place-year hardly at all, and a regional step to the series' end largely.

| locus (θ = 1.5 / 2) | expected deaths | absorbed |
|---|---|---|
| one place-year, ~100 deaths a year | 102 | 0.09 / 0.11 |
| one place-year, São Paulo | 24,000 | 0.18 / 0.21 |
| a cluster (Campinas and neighbours), one year | 4,100 | 0.11 / 0.13 |
| one block-group in a state-year (stroke, PE) | 4,900 | 0.16 / 0.18 |
| a state-year (PE) | 17,500 | 0.16 / 0.18 |
| São Paulo, three years | 71,500 | 0.37 / 0.41 |
| a macro-region-year (Northeast) | 92,500 | 0.37 / 0.42 |
| a state step to the end (PE, 2018–21) | 71,200 | 0.45 / 0.48 |
| a macro-region step to the end | 378,000 | 0.57 / 0.63 |
| a state trend change (PE, log-linear 2016–21) | 107,000 | 0.59 / 0.60 |
| the whole country, one year | 357,000 | 1.00 / 1.00 |

**Reading.**
- What a refit absorbs grows with the locus's share of a component's support. Its place effect spans twelve years and takes 9–21 % of one year. Its history spans the country: a macro-region-year holding 26 % of the deaths loses 40 %. Its trend absorbs steps and trend changes that run to the series' end: 45–63 %.
- Two consequences:
  - **Power curves planted into a fixed μ overstate power**, most for the lasting and regional loci that matter. ADR-0022's admission curves (macro-region × window, fixed μ) are among them.
  - **In-sample surprise sees a lasting regional departure at about half its size.** This is the masking that Farrington's reweighting and Noufaily et al. (2013) correct in outbreak baselines by down-weighting past excesses.
- For O5 and O6:
  - the grid's worlds are refitted, at fixed strengths (seconds a world);
  - a lead's effect is re-estimated with its locus held out of the fit (exposure masked) before it is sized;
  - small disjoint loci can share a world; a large locus has its own.
