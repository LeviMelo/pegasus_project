# ADR-0018: SIH relations in the dependency map are read net of two utilization factors extracted from the map's own SIH fields

**Date.** 2026-10-05. **Status.** Active (scan side; the model-side fix is the low-rank interaction, ARCHITECTURE §4.2, and supersedes it when built).

**Evidence.** `docs/evaluation/2026-10-05-utilization.md`: parallel analysis against Moran surrogates (two factors above the 99 % null, a third not), CP-APR agreeing on two; the conditional layer with the factors removes 88 of 89 SIH x SIH edges and admits no SIH x SIM or SIH x SINASC edge; a planted SIH-specific relation is kept (3 of 3), a planted utilization relation removed (0 of 3); 2 false edges in 40 surrogate worlds.

## Decision

1. **Hospital use is read as two factors:** the first two principal components of the weighted correlation matrix of the SIH chapters' place effects (`maps.factors`), k = 2 by parallel analysis on Moran surrogates (ADR-0005's null). Factor 1 is general use per resident, factor 2 a referral / specialty axis.
2. **They join Z in the conditional layer for every pair with an SIH member** (`dependency_map(adjust=2)`), with n_eff reduced by their number. The marginal layer, other pairs and delta_Z 0.1 (ADR-0013) are unchanged.
3. **The factors are extracted from the map's own fields,** so a negative world re-extracts them from its surrogates; the false-edge rate is read off those worlds.
4. **A conditional rho of the sign opposite to its marginal, after a factor is removed, is not read as a relation** (the removal induces it).

## Limits

The false-edge rate is 2 in 40 surrogate worlds (0.05 per world, the nominal q), both SIH x SIH with induced sign; the factor is a component of the fields it conditions; power for an SIH-SIM relation of the real size is untested.
