# `alarms` at a year boundary: the cause is the flat nowcast prior, not the week

**Scenario.** `pegasus-core alarms SIM.DO death IX <AS_OF>` (BACKLOG 0.3b), SIM IX, fit 2010-2022 (stored), as-of 2023-06-30/07-01 (mid-year) and 2023-12-31 (a Sunday, epidemiological week 1 of 2024). Drivers in the session scratchpad (`alarms/d4.py`, `d5.py`); no artefact under `data/`. Regime: 2026-10-10, commit de15d10 plus this change, SIM delays from the 2022 and 2023 files.

**Causes found (code and delay tables read).**
1. **A flat prior on the week's total** (`surveillance.nowcast`: events to come NegBin(y + 1, F)). SIM's F(0) = 0.28 (2022 file: 28% of deaths are registered within 7 days of the death), so one death known reads as 1 + 2 × 0.72/0.28 = 6.1 expected: every young week with 1-3 deaths known alarmed against a threshold of 4-5. Not specific to the boundary: with the node filter below, the flat prior alarms 6.9% of the evaluated place-weeks mid-year and 5.1% at the boundary.
2. **The year boundary's bookkeeping.** Week 1 of 2024 was read from the 2023 file alone (31 December: 3,814 deaths of a week of ~28,000) and compared with a whole-week baseline; the filter `year == epidemiological year of AS_OF` dropped the seven weeks of 2023 before it, so the "last 8 weeks" were one; the baseline was read at the as-of's calendar year for every week.
3. **The week in progress.** A week still running was nowcast as if complete (the retrospective file held its future events, a leak; a prospective file would hold a fraction).
4. **Not boundary-specific, and not fixable in the files this unit may edit:** `gateway.delay_counts` counts every event of the event type, so for a field below the type (IX of `death`) the known counts and the delays are those of all causes against a chapter-IX baseline. All-cause known counts are about 3.5 times the baseline (national weekly IX baseline 8,000, deaths known about 28,000): 5,509 alarms of 27,938 evaluated place-weeks (19.7%) mid-year and 4,696 of 26,142 (18.0%) at the boundary even with fixes 1-3.

**Fix.** `surveillance.py`: the nowcast takes the week's alarm baseline NB(μ, φ) as the prior on its total (gamma-Poisson with binomial thinning, events to come NegBin(φ + y, (φ/μ + F)/(φ/μ + 1)); F = 1 returns the known count, F → 0 the baseline); `window` gives the weeks that have ended by AS_OF by position, across epidemiological years; `Delays.F` takes arrays. `Session.alarms` (tools.py): reads the files holding the window (both across a year, and a straddling week from both parts), fits the baseline per epidemiological year of the week (train through the year before it), refuses a window in the confirmation reserve (`control.check_reserved`; SIM 2024 is reserved, so a week of 2024 cannot be watched until it is spent). Under the baseline as the truth the posterior probability of exceeding the threshold averages to the prior's, so a place with no departure alarms with probability at most 1/(c·R) (2/260 at c = 0.5, R = 260), whatever its delay.

**Numbers** (place-weeks with at least one known death; alarms are the place-weeks with P(exceed) ≥ 0.5).

| reading | mid-year 2023-07-01 | boundary 2023-12-31 |
|---|---|---|
| before (flat prior, week-1 bookkeeping, all-cause), 2023-06-30 / 2023-12-31 | 10,016 alarms in 8 weeks | 177, all in week 1 (known 1-3, nowcast 10-30) |
| window and prior fixed, all-cause counts (cause 4 left) | 5,509 / 27,938 (19.7%) | 4,696 / 26,142 (18.0%) |
| flat prior, node-restricted counts (prototype of the gateway fix, ICD chapter I) | 1,045 / 15,224 (6.9%) | 699 / 13,686 (5.1%) |
| **baseline prior, node-restricted counts** | **54 / 15,224 (0.35%)** | **31 / 13,686 (0.23%)** |

Two more boundaries, with the baseline prior and node-restricted counts: as-of 2023-01-07 (weeks 46 of 2022 to 1 of 2023, two files, two per-year baselines, the 2021 fit made on demand in 22 min) 41 / 13,804 (0.30%); as-of 2021-01-02 (week 53 of 2020 straddling the 2020 and 2021 files, read from both) 35 / 12,320 (0.28%).

With the node restriction and the baseline prior all four dates alarm at a tenth of the 0.77% bound; the alarms left have known counts at or above the threshold (e.g. 120040: 20 known, threshold 20, baseline 8.3 in week 49). The boundary is no longer different. The node-restricted rows used a prototype in the driver (`delay_counts` filtered on the classifier column starting with the chapter's letter), not the shipped code.

**Debts.** (a) Registration slows at the turn of the year: the share of deaths registered within the week of death is 0.25-0.29 in most weeks but 0.21 in week 51 and 0.17 (2023) / 0.12 (2024) in week 52, against F(0) = 0.28 from the closed year pooled over its weeks; boundary weeks are nowcast too high by it (a week-of-year delay, shrunk to the pooled, is the remedy). (b) Delays are whole weeks, so a Wednesday as-of discards four days of reporting. (c) The gateway restriction of cause 4 (BACKLOG 0.3c).

**Shipped (0.3c).** `gateway.delay_counts(codes=)` now restricts the known events to the field's leaves, as the
prototype did. The rerun of `d5.py` gives 54 of 15,224 (0.35%) as-of 2023-07-01 and 28 of 13,686 (0.20%) as-of
2023-12-31. A year a source does not publish now raises pegasus_data's `NothingPublished` in `event_counts`;
corroboration skips it, where it used to fail on a schema with no columns (SINAN-TOXG in 2010).
