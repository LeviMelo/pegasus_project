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
