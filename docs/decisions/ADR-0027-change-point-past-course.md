# ADR-0027: The change point reads each place against its own past course; the outbreak lens reads B1

**Date.** 2026-10-06. **Status.** Active. O6's first departure baselines: the change point and the outbreak estimands.

**Evidence.** `docs/evaluation/2026-10-06-minimum-effects.md` (tiers and baselines); `data/lens_course.py` → `data/probes/grid/change_point_past_*.json`. The checks, on SIM I60-I69, SIM I00-I02 and SIH-RD J09-J18:
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

4. **The outbreak lens** reads B1 as it is (was B2). Prospective tiers keep their alarm baseline. A course fitted on every other year adds nothing once the level is pinned: B1 alone gives the same numbers. A level freed to the model's place-effect prior failed SIH's time negatives (18/20): see the evaluation, level prior.
   - Calibrated: model worlds 0/10 and both negatives at most 1/20 on all three fields (`data/lens_course.py B1 outbreak`).
   - Place spikes at 30 or more expected events, ×2 / ×3, against B2 at θ0 1.1: stroke 0.44 / 0.92 against 0.36 / 0.81; SIH 0.15 / 0.73 against 0.07 / 0.55.
   - State-years: SIH 0.50 at ×1.5 and 1.0 at ×2 against 0.25 and 0.75. Stroke reads 0.5 against 1.0 at ×2, on 4 plants a size, which is noise at that count.

## Limits

- Sparse fields: the time negatives fail on I00-I02 under every baseline (10–17/20). Such a field's change-point leads have no calibrated false-discovery rate.
- SIH's space negatives at 3/20 sit above q on 20 worlds. They are reported as such until a larger run settles them.
- The extrapolated slope costs power against B1 as it is: a place step ×2 is found 0.16 of the time, against 0.70. That is the price of a baseline that never saw the step.
