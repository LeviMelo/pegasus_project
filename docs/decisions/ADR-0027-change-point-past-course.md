# ADR-0027: The change point lens reads each place against its own past course

**Date.** 2026-10-06. **Status.** Active. O6's first departure baseline, for the change point estimand.

**Evidence.** `docs/evaluation/2026-10-06-minimum-effects.md` (tiers and baselines); `data/change_point_past.py` → `data/probes/grid/change_point_past_*.json`. The checks, on SIM I60-I69, SIM I00-I02 and SIH-RD J09-J18:
- model null worlds, 10 per field;
- space- and time-scrambled normal-score negatives, 20 each;
- planted place and state steps, 2 worlds each.

## Decision

1. **The baseline.** The change point lens reads the B1 tier (was B2). Each window [t, T) is set against the place's own course, fitted on the years before t and extrapolated over the window (`lenses._past_course`, Farrington 1996's baseline with its trend):
   - a negative binomial regression on the tier's mean, with a level and a slope;
   - each with a normal prior whose spread is the field's between-place spread, estimated by moments net of the NB noise;
   - the window total's predictive is NB, its variance the cells' plus the extrapolation's (delta method).

   A persistent place deviation or trend is thus the baseline, and the step under test never enters it.
2. **Why not a tier as it is.**

   | baseline | place step ×3 found (stroke / SIH) | where it fails |
   |---|---|---|
   | B2, which refits each place's trend over the whole series | 0.11 / 0.07 | it takes the step into the trend |
   | B1 as it is | 0.95 on stroke | SIH: steps in every space-scrambled world (20 per world), from SIH's persistent place courses |
   | level only, Poisson noise | — | SIH model worlds 2/10 and space negatives 20/20 |
   | B0 with the past course | — | the dispersion fitted at B0 counts place variation as noise: SIH power ≈ 0 |

3. **What the adopted baseline does.**
   - Stroke: clean on the model worlds (0/10) and both negatives (0/20). A place step ×3 is found 0.47 of the time and a state step ×2 always.
   - SIH: clean on the model worlds and time negatives; space negatives 3/20. A place step ×3 is found 0.40 of the time.

## Limits

- Sparse fields: the time negatives fail on I00-I02 under every baseline (10–17/20). Such a field's change-point leads have no calibrated false-discovery rate.
- SIH's space negatives at 3/20 sit above q on 20 worlds. They are reported as such until a larger run settles them.
- The extrapolated slope costs power against B1 as it is: a place step ×2 is found 0.16 of the time, against 0.70. That is the price of a baseline that never saw the step.
