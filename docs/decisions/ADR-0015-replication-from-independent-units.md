# ADR-0015: Replication comes from independent units: later years, other places, another record system

**Date.** 2026-10-05. **Status.** Active. Supersedes ADR-0007.

**Evidence.** The finding is OPEN_QUESTIONS 7 / `docs/evaluation/2026-10-05-replication.md` (commit 9fc46be): the sides of a cell's events are thinned from one cell and share its frailty, so under NB variation the marginal test on B calls 0.28-1.00 of null cells replicated and the test conditional on A has power 0.07-0.21 at three times the boundary. The size and power of the three tiers below on NB worlds are **not yet measured** (`replication.simulate_*` are written and smoke-tested only; handoff `data/handoffs/replication.md`).

## Decision

1. **Tiers are counts of independent confirmations** (`control.KINDS`, `replication_tier`): R0 passes §8.2; R_k holds k of
   - **temporal**: selected by a survey on the years up to t (`Session.train(t).survey`), the fit refitted without the later years, the same places tested on the later years' sum (BP, `Expectations.prospective(course=False)`), re-levelled to each state-year's observed course so a shock that touches every place (COVID-19) does not count (`relevel`), one-sided at the lens's minimum effect, BH over what was tested. Persistent and recurring departures replicate; a one-off event does not, by nature.
   - **spatial**: for a claim about a predeclared unit (a state's or region's trend), the lens on one random half of its municipalities (immediate regions halved, a buffer of graph neighbours removed: ADR-0005) must reach 0.05 and the other half gives the p-value. Clusters and municipalities were chosen among the places and are not spatially tested.
   - **corroborated**: another record system (S2iD, SINAN, SIH) against its own place-set null (unchanged). A one-off event reaches R1 only this way.
2. **The reserve is a reserved period**, not events: `control.RESERVED_PERIODS` = SIM.DO 2024 (final file of Dec 2025, after every fit and survey on 2010-2023). `monolith.assemble` and `Session` refuse it (`ReservedPeriod`); only `Session.confirm_many` opens it (`reserve_open`), testing a persistence claim against the fit on 2010-2023 under one LOND stream (`control.Reserve`, split `period:reserve`). Preliminary years stay out until final. **The top-15 spend remains unspent** (`Reserve.state()` = (0, 0)); one-off signals cannot recur and should not use the stream.
3. **The event split is kept for sizes only** (`SIDES` = A 50 / E 50; `Session.honest_sizes`). Given a cell's rate the sides are independent Poisson counts, so the rate ratio read on E, with its exact Poisson interval, is unbiased for the locus's realised rate whatever A selected. It includes the cell's frailty; it is not evidence of recurrence. A's events are the same as before (the old B and R together are E).
4. `Session.triage`'s in-sample temporal/spatial splits are descriptions and no longer tier.

## Limits

- A lead from the all-years register cannot be tiered temporally unless a survey on the years up to t re-finds it (`retier` matches by field, direction, place and window); the later-years tier is therefore run per origin t.
- Corroboration still draws scattered null place sets; a contiguous cluster shares its neighbours' shocks in the other field (OPEN_QUESTIONS 7).
