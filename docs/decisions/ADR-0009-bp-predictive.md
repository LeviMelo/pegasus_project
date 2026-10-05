# ADR-0009: BP's predictive is a mixture over the history's regimes, with the training fit's place-year component and the place's damped course

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-bp-level.md` (`scripts/measure_bp_level.py`; three annual origins, two monthly); the origin is OQ 6 and the Laplace and dispersion entries (BP stayed miscentred under every dispersion structure fitted on its own cells).

## Decision

1. **φ_extra applies to BP,** estimated on the *training fit's* B1 cells (macro-region and state hierarchy, ADR-0006), so no departure the tier shows leaks into it. BP formerly kept the block's φ alone.
2. **Annual grain:** h carries the RW2's last slope damped by 0.5 per year, and each place carries its own B2 trend over the fit, damped by 0.5, its coefficients' posterior variance added to the predictive.
3. **Monthly grain:** h is not extrapolated; every year of the fit is a regime (its twelve months of h), equal weights, and a cell's predictive is the mixture of NBs (`prospective.mixture_pit`). The flat baselines (`level36`, `median`, `robust`) stay as `history=` options, for a point alarm baseline (ADR-0004).
4. **The forecast-variance heuristic is removed** (`laplace.forecast_variance`, `forecast_increments`, `Expectations(forecast=)`): a national random-walk spread added 385 nats of 1.4 M in the annual score, and the regime mixture carries the monthly level uncertainty. Laplace draws and exposure variance still add to each member's dispersion.

## Why

Oracle decompositions put the miss in the place's level (a per-place multiplier restores KS 0.013) and, for dengue, in the epidemic regime. Held-out log score over the rolling origins: annual −1.52 M → −1.37 M (mean KS .121 → .060); dengue −4.68 M → −1.39 M (mean KS .169 → .056, obs/expected 2.2 → 1.2). The h forecast itself is second-order for deaths (linear, damped and flat within 700 nats).

## Consequences

BP's `Surprise.mu` is the mixture's mean and `phi` its matched dispersion; lens code reading BP is unchanged in form. The monthly mean is higher than level36's (epidemic years are normal ones): the outbreak lens's recall and precision of evaluation 2026-10-05 (baseline history) were measured on the point baseline and are not re-measured here. BP still misses §6.2 in the worst region; OQ 6 keeps the regional drift (dengue's spread into the Sul) and categories born after the fit (B34). The COVID break (training ≤ 2019 against ≤ 2021) and dengue origins 2016 and 2020 were not run.
