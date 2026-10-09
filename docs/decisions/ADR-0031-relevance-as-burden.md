# ADR-0031: relevance as a ratio and as a burden

**Date.** 2026-10-09. **Status.** Active. Revises ARCHITECTURE §8.4 (minimum effects); work plan unit S1.6.

**Evidence.** S1.5's fifth round (evaluation 2026-10-08-persons-race-reader): Boa Vista's births rose 11–16 % in
2018–2019, about 1,000 births above the rate's course. That was under the count methods' minimum relevant ratio of 1.1
to 1.2, so it could not be relevant whatever its significance, while a village's handful at the same ratio could.
Evaluation 2026-10-09-weighted-events-and-absent-ages, S1.6 section.

## Decision

1. **One statement of relevance, read two ways.** A count departure is relevant when its ratio clears θ0, or when its
   excess clears the events θ0 means at the field's mean cell, (θ0 − 1)·μ̄. Per locus this is one floor:
   θ0' = min(θ0, 1 + (θ0 − 1)·μ̄/m), with m the locus's expectation per cell and μ̄ the field's mean expectation per
   cell at the same support (`scans.lenses.burden_ratio`).
2. **No new constant.** μ̄ is the field's own. A place of average size or smaller keeps θ0. An aggregate of average
   places keeps θ0, because m is per cell. Only places larger than the field's mean are held to the burden.
3. **Where it applies:** every count test of θ0, namely the cell excess (per cell, at each support), the multiscale
   peaks (per peak, through its kernel and contrast), the step (per unit), the outbreak lens and the space–time scan
   (per cell of the subset's boundary). A finding records the floor it was tested against (`relevant_ratio`).
   Locations (measures, shares) keep the ratio: they have no events to count.

## Consequences

- Boa Vista's floor falls from 1.1 to 1.0064, and its 2019 cell clears relevance (p 0.035). The round is still missed:
  B1 expects 7,956 births there in 2019 (8,936 observed), and the remaining 12 % is 1.9 times the field's place-year
  noise (6.3 %). The binding constraint is now the expectation and its noise, not relevance.
- Capitals' departures become relevant at smaller ratios, so the volume of leads from large places grows. Ranking
  them is stage F's question, not a threshold's (§8.4, revision 3).
