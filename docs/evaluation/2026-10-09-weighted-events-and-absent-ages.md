# Weighted events, and absent ages counted as 80+ (2026-10-09)

**Regime.** Branch `design-v0`, with pegasus_data at d8ece14 (its decision 0155). The local data home was used. The SIA trial ran
`gateway.event_counts` and `monthly_counts` for 2023 on AC 2023-01 only: `pg.query` and `count_events` were patched to
that partition and the store was stubbed, so no partial result was cached under a national key. The script is
`try_weight.py`, kept in the session scratchpad and not shipped.

**Absent ages were counted as 80+.** The gateway capped age as `least(floor(TRY_CAST(age)), 80)`. DuckDB's `least()`
skips NULLs, so `least(NULL, 80)` is 80 (DuckDB 1.5.5). From e065bd1 (2026-10-04) on, every event whose age stratum
was empty or unparsable was counted at 80+ instead of being unallocated as `age`.
- SIM.DO 2022: 2,337 such deaths, against 495,283 deaths at 80+, a 0.47% inflation of that band.
- SINASC.DN 2022: 26 births (mothers' ages).
- SIA BI AC 2023-01: 1,490 procedures, TPIDADEPAC 9.

`_age_sql` now keeps an absent age absent. It also nulls the codes the age stratum's roles declare missing, such as
PA_IDADE 998 and 999, which would otherwise be capped at 80.

`event_counts` and `linked_counts` were keyed by code, so they re-key themselves. `monthly_counts`, `mark_moments`,
`composition_counts`, `away_counts`, `code_list_counts` and `delay_counts` were not, and now are (ARCHITECTURE §11.3):
their stored results recompute on next use.

**Weighted events (pegasus_data decision 0155).** `_records` attaches a weighted event's weight, and every event count sums
it (`wt`). SIA PA 2023-01 in AC:
- `event_counts` and `monthly_counts` allocate 146,228 procedures and leave 1,046,221 unallocated by municipality
  (the consolidated BPA records none);
- the sum is pegasus_data's 1,192,449.
- BI allocates 79,876 and leaves 1,490 unallocated by age.
- `mark_moments` refuses PA ("a mark's moments is per record"), and so do linked counts.

`_when` accepts the property `competence` (SIA's month of care), and `_date_sql` reads YYYYMM as the month's first
day.

Not run: a national SIA year. PA is about a billion approved procedures in some 400 million rows a year, a
multi-hour read.
