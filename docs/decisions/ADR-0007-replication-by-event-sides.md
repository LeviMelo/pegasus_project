# ADR-0007: Replication is by event sides, a conditional test on side B, and corroboration by an independent field

**Date.** 2026-10-05. **Status.** Active. Supersedes the temporal/spatial/system ladder of ARCHITECTURE §8.3 as first written.

**Evidence.** `docs/evaluation/2026-10-05-replication.md`; the defects are in `docs/evaluation/2026-10-05-lead-triage.md` (R1 asks a one-off event to recur; the spatial halves were chosen after selection on the same data; the splits used the all-years fit; the reserve was never spent).

## What was measured

- **A marginal test of a cell on a held-out half is not a test** when the count's variation is mostly extra-Poisson. Cells simulated NB(μ, n), dealt 50/30 to A and B, selected on A at p < 0.001 and tested on B at 0.05: the marginal test calls 0.28 (μ = 100, n = 100), 0.42 (μ = 20, n = 10), 0.94 (μ = 20, n = 3) and 1.00 (μ ≥ 100, n ≤ 10) of the null cells "replicated", because the two sides share the cell's rate. Conditional on A's count (the rate's gamma posterior; `replication.conditional_p`) the rate is 0.02 to 0.06 everywhere on the grid.
- **Fitting on all the events leaks little into a side's expectation.** Block XV refitted on side A alone: its expected total equals 0.5 × the all-events fit within 1%; in the 200 largest-|z| cells the all-events expectation is 0.5% to 8% above the A-fit's (median ratio 1.00 to 1.08), cell-wise differences 7 to 14% (the half-data fit is noisier). The shared fit is therefore conservative for upward leads and is the default; `split-fit` refits a block on A alone.

## Decision

1. **The events of every cell are dealt to three sides by a fixed seed** (`control.event_sides`): **A** 50% (explores, selects, and the fit where `split-fit` was run), **B** 30% (the survey's one test of what A selected), **R** 20% (the confirmation reserve). Splits of the period and of the places stay as recurrence and as a reported homogeneity check; they are no longer the way a lead is confirmed.
2. **A lead is R1 only if it was selected on A and stands on B.** The survey runs on A (`split-survey`, its own register and ledger, the same admission of fields from all the events); each A lead is tested once on B at its fixed locus, at the lens's minimum effect, **conditional on A's count**; Benjamini–Hochberg over everything A selected. A register lead takes the verdict of the A lead that is the same finding (same field and direction, a place and a year in common).
3. **Tiers.** R1 split; R2 R1 + recurrence in the temporal half the window does not touch; R3 R1 + corroboration. Recurrence and corroboration do not require each other.
4. **Corroboration by an independent field** (`corroborate.py`): the lead's place set and years in S2iD, SINAN or SIH (survivors only: the in-hospital deaths are SIM's records, §8.5), against that field's own null: the same statistic on random place sets of the same size, states and population quintile, same years; p = (1 + #{≥}) / (1 + 4,999); BH within source. Which field corroborates which codes is data (`RULES`). A deficit is not corroborated by a field.
5. **The reserve is side R,** spent only by claims (`Session.confirm`, `confirm_many`): one fixed locus per claim on R, p-values in one LOND stream whose state is read from the ledger (`control.Reserve`, split `event:R`), in an order fixed before R is read.

## What it does not do

- A cell's extra-Poisson heterogeneity is part of the null: where it dominates (expected count above the NB size), B cannot tell a real shift from the cell's own excursion, and the conditional test has little power. Such leads stay R0 for want of evidence, not because they failed.
- Trend leads are tested on B by the lens's own divergence statistic, which shares the per-cell rates of the sides weakly (a slope averages many cells); not simulated.
- Group patterns have no direction and are not split-tested.
- Corroboration shows that another record system saw the same place and time, not that the cause is the one coded: a registry may omit the event (S2iD has no record of Brumadinho 2019).
