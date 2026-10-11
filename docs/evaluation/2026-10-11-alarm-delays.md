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

**Left.** Weeks aged 3–5 are overestimated by 4–9 % in every model: registration was faster in 2023 than in 2022,
the closed year the delays come from. The remedy is a delay read from the current year's own reporting triangle, with
right truncation (a reverse-time hazard: Lawless 1994). The boundary's first weeks are still nowcast 18–24 % low: 2023's
year-end slowed more than 2022's.

**Alarms** (`Session.alarms`, SIM IX, R = 260, c = 0.5) after the change:
- as of 2023-07-01: 44 alarms (54 before);
- as of 2023-12-31: 25 (28 before);
- as of Wednesday 2023-07-05: 55.

The alarms left have known counts at or above their thresholds (353060: 40 known, threshold 39).
