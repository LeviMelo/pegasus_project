# O6: the first departure models against their lenses

**Regime.** pegasus_core `design-v0`, the commit carrying this entry. Grid worlds are refitted and carry N1's noise (gamma frailty, AR(1) copula). Script `data/o6_departures_grid.py`; artifacts `data/probes/grid/o6_departures.json` and `o6_departures_<field>.jsonl`; log `data/logs/o6_departures.out`. Each field had place and region plants, spike and step shapes, 2 worlds each, and 10 null worlds, at q = 0.05.

**Why these counts.** A departure model replaces its lens only if, at equal FDR, it matches or beats the lens's power and keeps its null worlds clean. The criterion was declared in the script before the run.

**Cell excess** (`departures.cell_excess`) is Efron's two-group model on the PIT scores:
- **Null.** An empirical null by central matching.
- **Selection.** The tail-area Fdr (BH on the empirical-null p-values, π0-adaptive).
- **Why not the mean-lfdr selection.** Lindsey's spline extrapolates log f linearly in the tails, so lfdr → 0 at the extremes of a null field. SIH had findings in 5 of 10 null worlds that way.

| detected (plants ≥ 30 expected) | stroke cell excess | stroke outbreak | SIH cell excess | SIH outbreak |
|---|---|---|---|---|
| place spike ×2 / ×3 | 0.25 / 0.81 | 0.05 / 0.36 | 0.02 / 0.16 | 0 / 0 |
| region spike ×2 / ×3 | 0.55 / 0.96 | 0.02 / 0.48 | 0.04 / 0.62 | 0 / 0.02 |
| null worlds with findings | 0/10 | 0/10 | 0/10 | 0/10 |
| false share in planted worlds | 0.037 | 0 | 0.004 | 0 |

**Accepted: cell excess takes over the retrospective cell question from the outbreak lens.** The lens stays for what cell excess does not yet do: the prospective alarm on BPA. All power is lower than in the grids before N1, because the worlds now carry the fields' measured serial dependence and extra variance.

**Step** (`departures.step`) is a Bayesian single change point per place:
- **Evidence.** Laplace marginal likelihoods, tempered by the serial correlation.
- **The level-prior defect.** The first version took the level's prior variance from B1's place totals, which B1 fits by construction. The prior collapsed to its floor and pinned the level, so the slope took the step: δ = 0.25 for a planted ×3. It is now vague; as a nuisance in every model, its Occam factor cancels.
- **Power is still low.** Stroke place steps ×3: 0.18, and SIH 0, against change point's 0.05 and 0. A regional step spreads over municipalities that are each tested alone.
- **Not accepted.** The next step is running the departure models over the ladder of supports.

## The multiscale step on null worlds, diagnosed (2026-10-07)

**The measurement.** Stroke deaths (SIM I60–I69, chapter IX), blob plants of step shape, 2 planted worlds and 10 null worlds, worlds drawn with N1. Script `data/o6_footprint_grid.py`, artifact `data/probes/grid/o6_footprint.json`. Findings in 8 of 10 null worlds (0–6 each); false share in planted worlds 0.116; power 0.78 at 1.5×, 1.0 at 2× and 3×. The winsorised lag moments had not fixed it.

**Four rival explanations, declared before the diagnosis** (`data/step_null_diag.py`, artifact `data/probes/step_null_diag.json`, three of the grid's own null worlds):

| rival | what would show it | measured |
|---|---|---|
| (a) N1 misestimated on the world | the refit's (ρ, δ) ≠ the generating (0.81, 0.58) | **yes**: ρ 0.95 (its bound), δ 0.12–0.22 |
| (b) the variance formula misstates the generator | E[D²/W] ≠ 1 with the true μ and noise | no: 0.99–1.04 at every suffix start |
| (c) the refit's mean biased | mean z ≠ 0 | no: within ±0.07 |
| (d) the replicates' tail too thin | — | not needed |

- **Where the variance goes wrong.** With the refit's μ and noise, E[D²/W] runs from 0.36–0.38 for the suffix from 2013 to 0.98–1.00 for the suffix from 2022. The fit absorbs a long suffix's variance and none of a short one's.
- **Where the false findings sit.** All of them are on the last two or three years.
- **The mechanism.** `multiscale.peaks` matched its empirical null (median and MAD) once per scale, pooled over contrasts. That scaled the exact short windows up by the long ones' deficit, about 1.25×.

**Fixes.**
- **The empirical null per scale and contrast.**
- **ρ, δ fitted together with the lag model's own frailty scale.**
  - κ, the marginal of residuals about a fit that absorbs part of a persistent frailty, was held fixed. The lag moments are corrected for that absorption, so the lag-1 moment could be met only by ρ at its bound.
  - κ itself stays from central matching.

**After the per-contrast null** (same grid; script `data/o6_step_null_v2.py`, artifact `data/probes/grid/o6_step_null_v2.json`):

| | pooled null | per scale and contrast |
|---|---|---|
| null worlds with findings | 8/10 (0–6 each) | 2/10 (1 and 2) |
| false share, planted worlds | 0.116 | 0.023 |
| power 1.5×, 2×, 3× (≥ 30 expected) | 0.78, 1.0, 1.0 | 0.44, 1.0, 1.0 |

- **The declared criterion was at most 1 of 10 null worlds**, and it is narrowly missed. P(≥ 2 of 10) is 0.09 at a 5 % rate.
- **Part of the old power at 1.5× was the miscalibration's.**

**With N1 corrected as well** (normal scores clipped at the universal threshold, the lag model's own scale: evaluation 2026-10-06, noise structure; script `data/o6_step_null_v3.py`, artifact `data/probes/grid/o6_step_null_v3.json`):
- null worlds with findings: 1/10 (one finding);
- false share in planted worlds: 0.022;
- power: 0.56 at 1.5×, 1.0 at 2× and 3×.

**The declared criterion is met.**

**Adopted: one empirical null per scale and absorption class** (a = (Σc)²/(T Σc²)). A null per contrast lost COVID-19 in the North: a year-wide excess moved its own year's null (evaluation 2026-10-07, real events, v11–v12). Spikes share a = 1/T and pool over years; each suffix start keeps its own null, so the result above stands.
