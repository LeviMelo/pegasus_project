# ADR-0006: The place-year dispersion component varies by macro-region and state

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-dispersion-by-region.md` (`scripts/measure_dispersion.py`); the origin is OQ 6 and `docs/evaluation/2026-10-05-laplace-uncertainty.md` (dengue's Centro-Oeste failed at every tier under one φ_extra).

## What was measured

33 fitted fields (SIM chapters, chapter IX and four groups, SINASC, SIH annual and monthly, dengue, leptospirosis) at B0, B1, B2 and B2s, with the block's φ, one φ_extra per field, one per macro-region, and one per macro-region then state (shrunk).

| tier | fields | calibrated: block φ / one φ_extra / + macro-region / + state | mean worst-region KS (same order) |
|---|---|---|---|
| B1 | 33 | 18 / 28 / 30 / 30 | .059 / .034 / .026 / .026 |
| B2 | 33 | 22 / 25 / 26 / 27 | .052 / .036 / .033 / .032 |
| B2s | 4 | 2 / 4 / 4 / 4 | .097 / .025 / .015 / .015 |

- The aggregate log-likelihood rises at every level: macro-region over one value by 8 to 10,710 nats for 4 extra parameters (22 of 22 comparisons), state over macro-region by 12 to 5,353 nats for 22 (20 of 22).
- **The block's own φ, per macro-region,** does not generalise: held out, +0.009 nats per event on dengue (fit to 2018), +0.0002 on chapter IX, +0.002 on XVIII, −0.0007 on X.
- **BP** (prospective) does not benefit: no field of the ten measured calibrates under any variant.

## Decision

1. **φ_extra is a hierarchy: field, macro-region, state.** Each group's log(1/φ_extra) is estimated by maximum likelihood on its own cells and shrunk toward its parent's by the between-group variance the groups show (a random-effects moment estimate on the observed information). The PIT, the information weights and the surprises carry each place's own value (`surprise.place_year_phi`, `DISPERSION_LEVELS`).
2. **The block's φ stays one value per block;** BP keeps it (its calibration is recorded, never flagged).
3. **Surprise tables are re-keyed** (`surprise: 2`): cached tables from the single-value regime are not served.
4. **What it does not fix** (OQ 6, narrowed): dengue B1 in the Southeast (KS 0.081), the SINASC total, and BP's level on epidemic years. These are shape and level departures, not variance.
