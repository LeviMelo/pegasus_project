# ADR-0012: The prospective tier has two objects: the calibrated expectation (BP) and the alarm baseline (BPA)

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-dengue-monthly.md` (dated note, "alarm baseline"; `data/dengue_outbreak_bp2.py`, artefact `data/logs/dengue_outbreak_alarm.json`), `2026-10-05-bp-baseline-history.md`, `2026-10-05-bp-level.md`.

## Decision

1. `Expectations.prospective(node, t0, purpose="expectation" | "alarm")` returns two different objects, tier **BP** and tier **BPA** (`surprise.PURPOSE_TIER`).
   - **Expectation (BP, ADR-0009):** the regime mixture, calibrated; it serves surprises, the calibration check (§6.2) and every lens that reads departures from "normal Brazil", past epidemics included.
   - **Alarm baseline (BPA):** the history is `monolith.regime_history(..., purpose="alarm")`, at the monthly grain the flat `level36` (the mean of the last 36 months of h), with the same training-fit φ_extra, Laplace and exposure variance. No past epidemic regime enters it, so an epidemic that repeats one stays a departure. Its calibration is recorded, never claimed. At the annual grain there are no regimes to leave out and BPA is BP's single member under another tier name.
2. **The outbreak lens reads BPA in a prospective survey, every other prospective lens BP** (`tools.PROSPECTIVE_TIERS`; `Session.survey(prospective=t0)`, `Session.scan(..., train_last=t0)`). The retrospective plan (`SURVEY_PLAN`, `LENS_TIERS`) is unchanged: B2 for the outbreak lens.
3. The ledger families differ by tier name (`outbreak|BPA|block`): an alarm and a surprise are never one family.

## Why

Measured on dengue, state-years with incidence >= 300 per 100,000 (recall / precision), same code, same fits:

| origin (test years) | expectation (BP) | alarm baseline (BPA) |
|---|---|---|
| 2014 (2015-16) | 0.22 / 0.80 | 0.49 / 0.90 |
| 2018 (2019-23) | 0.48 / 0.84 | 0.81 / 0.75 |

The regimes predictive is the better calibrated (state-month KS .146 against .331 at 2018; held-out log score ADR-0009) and the weaker alarm, for one reason: the fit's years are its regimes, and an epidemic that repeats one is inside the predictive (observed/expected 1.3 against 2.8). The two jobs ask opposite things of the baseline: calibration wants the history's whole range, detection wants what is normal when nothing is happening. A single object tuned to both would be mediocre at each (ADR-0004 item 2 anticipated it: the alarm baseline downweights past epidemics, the descriptive tiers keep them). The flat level with the training fit's φ_extra recovers 0.81 of the 2019-23 epidemic state-years; the median and a Farrington-style robust level did worse (0.81 / 0.71 without φ_extra against 0.91 / 0.64 for the last 36 months; `bp-baseline-history`).

## Consequences

- Nothing about the expectation changes: its numbers at both origins reproduce to the digit (state-month KS, municipal KS, recall, precision).
- **What is not decided: the alarm design.** BPA feeds the outbreak lens, whose test is BH over one search at a rate ratio of 1.5 (§7.1). ADR-0004's false-alarm rate per place over time (a recurrence interval), the nowcast and the weekly grain remain phase 4; the alarm's recall and precision here are those of a retrospective epidemic-year recovery, not of a deployed alarm. Level36 is the best of the flat levels measured, not shown optimal; the monthly grain only.
- Leads from a prospective survey carry tier BPA or BP and are not yet explained or replicated (`explain_lead`, `triage` re-read the lead's tier without a train_last and raise).
