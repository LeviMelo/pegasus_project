# ADR-0032: a field's own dispersion is NB-P

**Date.** 2026-10-09. **Status.** Active. Revises ARCHITECTURE §5.2 and §6.2 (the surprise's dispersion); answers
OPEN_QUESTIONS 12 at the field's level.

**Evidence.** OPEN_QUESTIONS 12 and evaluation 2026-10-09-weighted-events-and-absent-ages. Births' B1 excess relative
variance falls from 0.016 in cells under 35 births to 0.0027 in the largest decile, while the surprise's dispersion was
0.0037 at every size. A place-year component added to the block's size-free φ went to zero: it cannot lower the
variance of large cells.

## Decision

1. When the block's φ fails the field's calibration (§6.2), the field's own dispersion replaces it:
   1/φ_cell = Var(μ)/μ² + κ·(μ/μ_ref)^(P−2), on the posterior's cells alone (`surprise._assemble`;
   `monolith.place_year_phi(power=True)`).
2. P in [1, 2] is learned on the field by the same trimmed, shrunk likelihood as κ (μ_ref its median cell); P = 2
   is NB2. The first trimming bounds start from the block's cells. The surprise's calibration records P
   (`dispersion_power`).
3. The block's φ still comes first: a field calibrated with it keeps it.

## Consequences

| field | before (PIT KS by size quintile) | after |
|---|---|---|
| births | 0.028–0.057, not calibrated | 0.016–0.024, **calibrated**, P = 1.63 |
| SIM IX | 0.011–0.089 | 0.012–0.085, P = 1.67 |

- Boa Vista's 2019 births move from z 1.92 to 2.83 (relative sd 6.3 % → 4.1 %): 860th of 77,980 cells, still under the
  false-discovery threshold.
- Remaining:
  - the monolith's own likelihood is still NB2 at its leaves (unit B3), where SIM IX's large places misfit;
  - the robust refit's flagging and the prospective component keep NB2;
  - the grid's null worlds are re-read with the next method records.
