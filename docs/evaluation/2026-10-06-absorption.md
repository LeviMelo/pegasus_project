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

**At fixed strengths or re-learned** (`data/o5_absorption_tau.py`): the Northeast step and the PE state-year at θ = 2 were refitted both ways, at the fit's strengths (7–12 s) and by the full production fit with every strength re-learned (34–42 s). The share absorbed is the same to the third decimal: 0.63 and 0.183. The history's strength did loosen (log τ_h −1.36 for the step, −0.17 for the state-year), but the mean barely moved. So the grid's worlds are refitted at fixed strengths.

**Held-out sizing** (`tools.Session.held_out`, `Monolith.without`): an NB world was drawn from SIM IX 2010–2023 with two plants and refitted. The plants were a Northeast step ×2 over 2020–23 and a Paraná ×1.5 in 2018.

| locus | in-sample ratio | held-out ratio |
|---|---|---|
| Northeast step ×2 | 1.31 | 2.01 |
| Paraná ×1.5 (observed noise included) | 1.53 | 1.64 |
| São Paulo 2018, no plant | 1.05 | 1.07 |

Each call took 7–9 s. Holding the locus out recovers the planted size.

The held-out p-value is not yet usable: it sums independent cells, so a 7 % excess over 87,000 deaths reads p ≈ 0. It needs the place-year dispersion φ_extra that the surprise tiers carry before it can be read.
