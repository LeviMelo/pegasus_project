# Ratio, interval and quality fields (2026-10-10)

Regime: branch `design-v0` (this commit), PegaSUS's data root, store as of the survey-depth toxoplasmosis run.
What was counted: each new field kind on real records, against a figure known independently, because a wrong rate
or delay here reads as a finding downstream.

**Ratio fields (BACKLOG 2.2).** A ratio is the numerator's count with the denominator's events as exposure
(`gateway.population("events:DS:EV[:codes][@lag]")`), both in one cell with neither sex nor age read
(`event_counts(cell=False)`).

| field | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| SINAN-TOXC per SINAN-TOXG notification | | 0.31 | 0.31 | 0.32 | 0.34 | 0.41 | 0.45 |
| SIM-DOFET per 1,000 SINASC births | 10.4 | 10.2 | 10.6 | 10.9 | 10.7 | 10.4 | |

The foetal death rate is Brazil's known level (about 10 per 1,000). DOFET 2019 accounts for every record of the
file (28,983 allocated, 122 outside a municipality: 29,105, the count pegasus_data's 2026-10-10 evaluation made). A
TOXC event in a municipality-year with no TOXG notification is unallocated ("no population in the cell": 1,988 of
26,375 over 2019–2024).

Two defects found on the way:
- **Warm starts across exposure units.** The ratio's first fit started from TOXC's person-year fit, so b0 began about
  15 log units off. It stayed at μ ≈ 1e-66 (objective 4.16e6, 26,208 events "against 0 expected"). A cold fit
  reproduced the 26,208 events (φ 3.8). `warm_start` now relates fits of the same exposure unit only.
- **A code set's share** was taken against the code set's own fit as the total. That gave 4,185 "share departures"
  from CIH-CR's 3 P37.1 admissions. The total is now the unrestricted reader's, and a ratio asks no share.

**Interval fields (2.3).** The descriptive table reports the records' median and 90th percentile
(`gateway.mark_quantiles`), not exp(mean log). The delays are not log-normal: same-day prenatal notifications sit
beside a long tail.

| TOXG, days from onset | 2019 median / p90 | 2023 median / p90 | the moments' exp(mean log), 2019 |
|---|---|---|---|
| to notification | 5 / 205 | 5 / 79 | 8.1 |
| to closure | 103 / 364 | 36 / 272 | 61.2 |

**Quality fields (2.5).** Each declared column present in every study year gives the share of its blank or
declared-missing values (`share_moments(quality=True)`). TOXG has 25 such columns. Schooling is ignored in 26.8%
(2019) to 31.8% (2021); the 2019 share is exactly the 2,260 records coded 9.

**Roles by year.** `gateway._strata(dataset, event, year)` reads the column a role has in that year's layout. It
reads the latest layout's column when no year is given, which fixed SIM-DOFET, DOINF and DOEXT's residence.
