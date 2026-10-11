# Alarm delays by week of year and by day (BACKLOG 0.3d, 2026-10-11)

**Scenario.** SIM-DO chapter IX deaths. Delays come from the closed 2022 file; 2023's weeks are nowcast as of a
Saturday and a Wednesday, mid-year (2023-07-01, 07-05) and at the boundary (12-27, 12-30). Each week's deaths known
by the as-of day, divided by F, are compared with its eventual count in the 2023 file. That eventual count is the known
answer. Driver: `ctl/delay_eval.py` (session scratchpad). Code: branch `scope-v2` after c7c2390.

**Found.** The old reading leaked the future. It counted an event as known when its delay in whole weeks, measured
from its own onset day, was within the week's age. Events reported up to six days after the as-of day were counted:
week 26 as of 2023-07-01 had 2,310 "known" deaths against 1,114 reported by then. Its apparent accuracy came from the
leak. The comparison below applies the old F to what was really known.

**Change.**
- `gateway.delay_counts` keeps the onset day and the delay in days.
- An event is known when its report date is on or before the as-of day.
- A week's F is the mean over its seven onset days of F at each day's own elapsed days (`Delays.F_week`).
- F is log-linear in the place and the onset's week of year. The place's pmf is shrunk toward the nation's. The week's
  national pmf is shrunk toward the pooled one (Dirichlet, method of moments), and enters as its ratio to the pooled
  pmf (`surveillance.delays`).

**Result.** Error of known/F against the eventual count, over 24 week-estimates (6 weeks × 4 as-of days):

| delay model | mean absolute error | weeks aged 0–1 | week 52 as of 2023-12-30 |
|---|---|---|---|
| pooled, whole weeks (old) | 11.8 % | 26.1 % | −67.0 % |
| days, pooled over the year | 8.3 % | — | −34.4 % |
| days and week of year (shipped) | 7.0 % | 9.3 % | −23.7 % |

**The year's own pace (added the same day).** Weeks aged 3–5 were overestimated by 4–9 % in every model above:
registration was faster in 2023 than in 2022, the closed year the delays come from. `surveillance.current` now reads
the as-of year's own reporting triangle (onsets in the last D = 188 days, delays seen by the as-of day). It reads it in
reverse time for the right truncation (Lawless 1994): g(d) = P(D = d | D ≤ d) among the events with D ≤ d ≤ T. Each
day's hazard is shrunk toward the closed year's, with a beta weight κ ≈ 2,000–3,600 by the method of moments. The
result enters F as a national year ratio beside the week-of-year one. Measured on 48 week-estimates (8 as-of days
through 2023, 6 weeks each, those in 2023; `ctl/delay_eval2.py`, `delay_eval3.py`):

| delay model | mean absolute error | weeks aged 3–5, mean | weeks aged 0–2, MAE |
|---|---|---|---|
| days and week of year | 6.8 % | +5.2 % | 8.0 % |
| … and the year's triangle, whole year's onsets | 5.4 % | +3.0 % | 7.3 % |
| … onsets in the last D days (shipped) | 5.2 % | +2.7 % | 7.3 % |

**Left.** The boundary's first weeks are still nowcast 14–16 % low as of 2023-12-30 (24 % and 18 % before): 2023's
year-end slowed beyond what the year's own triangle had shown. A week of age 0 is sometimes worse with the triangle
(week 43 as of 2023-10-28: +15.7 % against +5.4 %), since its F rests on the shortest delays, where the weekday of
onset and of registration matter and neither is modelled.
A weekday factor was tried and not kept (`ctl/weekday_diag.py`, `weekday_diag2.py`). The model was
p(d | onset weekday) ∝ b(d)·ρ(registering weekday), fitted on 2022 by iterative proportional fitting.

- 98 % of 2022's registrations fall Monday to Friday, and the fit reproduces each onset weekday's short-delay F within
  0.01–0.02.
- Nationally it brings an age-0 week's F closer on 3 of 5 dates (age-0 error 9.8 % against 12 %).
- Summed over places, as the evaluation reads it, the error grew from 5.2 % to 5.7 %, and the age-0 weeks reached
  +25–33 %.

What it would need is the per-place delay with weekday and week of year modelled jointly, not as independent factors.

**Alarms** (`Session.alarms`, SIM IX, R = 260, c = 0.5) after the change:
- as of 2023-07-01: 44 alarms (54 before);
- as of 2023-12-31: 25 (28 before);
- as of Wednesday 2023-07-05: 55.

The alarms left have known counts at or above their thresholds (353060: 40 known, threshold 39).
With the year's triangle (`ctl/alarm_run.py`, SIM-DO 2010–2023) the counts are the same, 44, 25 and 55: those alarms
are already certain from their known counts, so the triangle moves only the nowcasts of weeks below their thresholds.
