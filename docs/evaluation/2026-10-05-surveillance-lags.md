# Surveillance feasibility: publication lag and reporting delay

**Scenario.** The publication-lag measurement of ADR-0004 (per system, from pegasus_data's catalog) plus the reporting delays a nowcast needs, read from dates inside the records. Scripts and raw results are in `data/agent_lags/` (`lag_files.py`, `vital_delay.py`, `sinan_delay.py`, `sih_delay.py`, `rev_sizes.py`, `*.json`).

**Regime.** 2026-10-05. Catalog `pegasus_core_data/_catalog` (crawl `50754253bc0c`, 2026-09-28, 208,099 files; identical crawl to the repo home's 12.9 GB catalog). Record dates come from blobs already cached in the two homes; the one download is `SINAN/DADOS/PRELIM/DENGBR26.dbc` (23 MB, third-party mirror, version of 2026-09-29). pegasus_data pegasus-core-fixes.

## What the catalog can and cannot say

- An FTP modification time is the **last write**, not the first appearance. The catalog keeps no mtime history.
- The only older state is `data/backups/catalog-2026-09-28-before-full-crawl.sqlite` (08-30). Comparing it with the current catalog gives, for 4,353 changed files, the previous mtime and size.
- First appearance is observable only for files first seen on 09-28 and absent on 08-23 (SIH 108, SIA 280, CNES-ST 27 files). For them mtime lies between two crawls, so it is the first appearance.
- **Finals are therefore a last-write lag.** SINAN finals were re-dated in one backward sweep (Feb–Jun 2026: DENG 2024 on 02-27, 2023 on 03-17, 2020 on 04-10, 2014 on 06-02). Only 2025 (07-21) is a plausible first publication.

## Publication lag

Days from the end of the data period to the file's mtime. "Rolling" marks systems where the same file is rewritten.

| system | file | lag (days after period end) | posting pattern |
|---|---|---|---|
| SIM | final DO, 2022–2024 | 354, 353, 356 (2018–21: 454–482) | one write each December of Y+1 |
| SIM | PRELIM 2025 / 2026 | 239 (2025, last write 08-28) / file for 2026 last written 07-28 | 2025 rewritten monthly (07-27, 08-28); the 2026 file was **not** rewritten in August or September |
| SINASC | final DN, 2022–2024 | 375, 354, 356 | as SIM |
| SINASC | PRELIM 2025 / 2026 | 238 / last write 07-27 | monthly (07-27, 08-27) for 2025 |
| SINAN DENG, CHIK, ZIKA | final 2025 | 201 (07-21-2026) | years 2024 and earlier re-dated in the sweep above |
| SINAN DENG, CHIK, ZIKA | PRELIM 2026 | mtime 08-11 or 08-17, then 09-22; the mirror held a 09-29 version | 6 weeks apart on the FTP, one week apart FTP to mirror |
| SINAN LEPT | 2025 PRELIM, 2026 PRELIM | last write 07-15 for all years | stale by 75 days at the crawl |
| SIH-RD | competence M, first appearance | **37 d** (Jul 2026 on 09-06); Jun 2026: 25 of 27 states by 08-23 (≤54 d), two states on 09-06 (68 d) | monthly release around the 6th–9th |
| SIA-PA | competence M, first appearance | **43–48 d** (Jun on 08-12, Jul on 09-14 and 09-17) | monthly, two batches |
| CNES-ST | competence M | **13–16 d** median 2018–2026 (range 10–50); Aug 2026 on 09-15 | monthly, not rewritten |

**SIH and SIA have no preliminary/final split. They rewrite a rolling window of the last ~12 competences each month.**
- On 2026-09-06 every SIH file from 2508 to 2607 carries that date. Earlier months were last written at competence + 367–375 d (2021–24), which is when each leaves the window.
- Revision size between the 08-30 and 09-28 states, measured as the change in compressed file size per file (a proxy for records), for SIH-RD:

| age of the competence | median change | 95th percentile |
|---|---|---|
| 3 months | +3.2% | +26% |
| 4 months | +0.4% | +6% |
| 5 months | +0.2% | +1.6% |
| 8 months and older | about 0 | within ±1% |

- For SIA-PA the first rewrite is much larger: median **+26%** per file at 3 months (95th percentile +83%), +2.7% at 4 months.

**Revisions seen in the preliminary and final files (size, 07-27 → 08-28 unless said):**
- SIM PRELIM 2025: 25 of 28 files shrank, median −3.9% (range −7.8% to +2.7%). Cause unknown.
- SINASC PRELIM 2025: 28 of 28 grew, median +0.5%.
- DENGBR26 PRELIM: +4.3% in 6 weeks (08-11 → 09-22).
- **DENGBR21 FINAIS was re-issued on 2026-09-10 at half the size: 1,024,635 → 540,049 rows.** The 484,586 rows with `CLASSI_FIN` 5 (discarded) were removed; every other class is identical. Counts of discarded cases in a final file are not stable.

## What is inside the preliminary files

| file (mtime) | newest record date | gap file to data |
|---|---|---|
| DENGBR26 (mirror 09-29) | notified 09-27, entered 09-28 | **1 day** |
| ZIKABR26 (09-22) | entered 09-18 | 4 days |
| LEPTBR26 (07-15) | entered 07-03 | 12 days |
| DOAP2026, DORR2026 (07-28) | registered 05-25 / 05-20; death 05-21 / 05-16 | **64–69 days** |
| DNAP2026, DNRR2026 (07-27) | registered 05-23 / 05-26 | 62–65 days |

SIM and SINASC preliminary files are cut about two months before they are posted. SINAN's are cut the day before.

## Reporting delay from in-record dates

Closed files, so the far tail is right-truncated by the file's closing date.

**SINAN, days, final files, national.** Onset (`DT_SIN_PRI`) → entry (`DT_DIGITA`); notification (`DT_NOTIFIC`) between.

| file | rows | onset→notif p50/90 | notif→entry p50/90 | onset→entry p50 / 75 / 90 / 95 / 99 | visible at 7 / 14 / 28 / 56 / 84 d |
|---|---|---|---|---|---|
| DENG 2019 | 1.55 M | 3 / 9 | 10 / 70 | 15 / 34 / 78 / 129 / 274 | .24 / .49 / .71 / .85 / .91 |
| DENG 2020 | 0.98 M | 3 / 10 | 6 / 39 | 11 / 24 / 47 / 77 / 168 | .33 / .59 / .80 / .92 / .96 |
| DENG 2021 | 1.02 M | 3 / 10 | 7 / 44 | 12 / 25 / 52 / 89 / 190 | .31 / .57 / .78 / .91 / .95 |
| DENG 2022 | 1.41 M | 3 / 8 | 7 / 52 | 11 / 26 / 61 / 98 / 193 | .34 / .58 / .77 / .89 / .94 |
| DENG 2023 | 1.65 M | 3 / 7 | 5 / 34 | 9 / 18 / 40 / 60 / 142 | .45 / .68 / .84 / .94 / .97 |
| DENG 2024 | 6.56 M | 3 / 7 | 8 / 56 | 12 / 27 / 64 / 105 / 217 | .35 / .57 / .76 / .88 / .93 |
| DENG 2025 | 1.64 M | 3 / 7 | 4 / 34 | 8 / 17 / 42 / 73 / 169 | .47 / .70 / .85 / .93 / .96 |
| CHIK 2021 / 22 / 23 | 0.13 / 0.27 / 0.27 M | 5 / 20, 3 / 12, 3 / 11 | 14 / 99, 11 / 59, 10 / 64 | 22, 16, 15 (p90 117, 68, 74; p99 257, 192, 204) | .17 / .36 / .60 / .76 / .85 (2021); .26 / .48 / .70 / .86 / .92 (2023) |
| LEPT 2021 / 22 / 23 | 9 / 15 / 21 k | 7 / 20, 7 / 19, 6 / 17 | 7 / 42, 6 / 36, 6 / 35 | 18, 15, 14 (p90 59, 51, 49; p99 265, 202, 196) | .15 / .42 / .69 / .89 / .94 (2021); .22 / .50 / .77 / .92 / .96 (2023) |

DENG: the median onset→entry delay stays 8–15 days in seven years and the 90th percentile 40–78 days; the share visible at 14 days ranges .49–.70 and at 28 days .71–.85. The 2024 epidemic (6.6 M rows) has a longer tail than 2023 and 2025, so load matters.

**SIM and SINASC, days, final files.** Registration (`DTCADASTRO`, municipal entry) and original receipt (`DTRECORIGA`, SIM only; first arrival at the national level; exists from 2011). `DTRECEBIM` is not usable: it is the last receipt (SIM GO 2022 median 342 days).

| set | measure | p50 / 75 / 90 / 95 / 99 | visible at 7 / 14 / 28 / 56 / 84 d |
|---|---|---|---|
| SIM, 22 UFs 2022 (665 k deaths) | death→registration | 13 / 26 / 45 / 62 / 145 | .32 / .54 / .78 / .94 / .97 |
| same | death→original receipt | 20 / 35 / 57 / 80 / 198 | .16 / .36 / .66 / .90 / .96 |
| SIM, AP+RR 2011 | death→registration | 27 / 42 / 76 / 156 / ≥400 | .06 / .21 / .53 / .86 / .91 |
| SIM, AP+RR 2013 | death→registration | 28 / 45 / 72 / 126 / 359 | .05 / .19 / .50 / .84 / .92 |
| SIM, AP+RR 2018 | death→registration | 19 / 30 / 52 / 73 / 211 | .12 / .36 / .73 / .92 / .96 |
| SIM, AP+RR 2022 | death→registration | 16 / 27 / 48 / 82 / 273 | .22 / .46 / .76 / .92 / .95 |
| SINASC, 22 UFs 2022 (1.34 M births) | birth→registration | 14 / 32 / 107 / 284 / ≥400 | .31 / .52 / .72 / .86 / .89 |
| SINASC, 22 UFs 2023 (1.33 M) | birth→registration | 12 / 28 / 69 / 214 / ≥400 | .33 / .56 / .75 / .88 / .91 |

Across states the 2022 median death→registration ranges from 6 to 45 days (PA 6, PR 8, TO 8; DF 45, AC 34), so the delay is a property of the place as much as of the year. AP+RR median: 27, 26, 28, 30, 19, 16 days for 2011, 12, 13, 15, 18, 22 (an improving trend, not a stable law).

**SIH-RD, AC+AP+RR, 2011–2023, 1.6 M records.** The competence file holds a stay billed in that month, which is the discharge month (an admission of 2021-12-27 discharged 2022-01-22 sits in competence 2201).
- Share of discharges billed by the competence of the discharge month plus k months:

| k | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| range over 13 years | .43–.64 | .68–.89 | .82–.97 | .990–.9997 |

- By **admission** month, which is what an admission count needs: visible in the competence of that month, .36–.53; with one month more, .64–.86; two, .80–.96; three, .98–.99.
- Days from admission to the end of its competence month: p50 28–42, p90 70–108, p99 119–133. The 3-month billing rule shows as the jump to ~99.8% at k = 3.
- The share billed in the first month was .43–.47 in 2011–15, .52–.64 in 2016–21, .51–.54 in 2022–23: not stationary.

## Conclusion for ADR-0004

**Weeks behind real time on the day a file is posted.** "Frontier" is the newest period with at least ~80% of its eventual events visible without a nowcast. "Nowcast" is the newest period a delay correction could use, at a visible fraction of 35–50%.

| system | channel | newest datum | frontier | with nowcast | sustainable? |
|---|---|---|---|---|---|
| SINAN DENG, CHIK, ZIKA | PRELIM current year | ~0.5–1 | **4–5** | 1–2 | yes, if the file is refreshed weekly (it was between 09-22 and 09-29; 6 weeks between 08-11 and 09-22) |
| SINAN LEPT | PRELIM | 1.7 | 5 | 2 | file 11 weeks stale |
| SIM | PRELIM current year | **9.5** | 12–13 | 10–11 | the 2026 file was 18.6 weeks behind at the crawl (not rewritten since 07-28) |
| SINASC | PRELIM | 9 | 12 | 10 | as SIM |
| SIH-RD | monthly files, no PRELIM | 5.3 (a month's file, billed by discharge) | **14** (month plus 2 competences) | 5.3 (first file, 36–53% visible) | month grain only |
| SIA-PA | monthly files | 6.1–6.9 | not measured | needs the +26% first rewrite | month grain only |
| CNES-ST | monthly files | 2 | 2 | none | stock, not events |
| any, final files | FINAIS / CID10 | 29 (SINAN) to 51 (SIM, SINASC) after year end | | | retrospective only |

**Fraction of eventual counts visible, lag from the event** (final-file delay distributions, pooled 2022 for SIM and SINASC, the seven DENG years for SINAN):

| lag | 1 wk | 2 wk | 4 wk | 8 wk | 12 wk |
|---|---|---|---|---|---|
| DENG, by onset | .24–.47 | .49–.70 | .71–.85 | .85–.94 | .91–.97 |
| SIM, by death, registered | .32 | .54 | .78 | .94 | .97 |
| SIM, by death, at the national level | .16 | .36 | .66 | .90 | .96 |
| SINASC, by birth, registered | .31–.33 | .52–.56 | .72–.75 | .86–.88 | .89–.91 |

A check on the cut file itself, not on the final-file delays: in `DOAP2026` and `DORR2026` pooled, deaths in the last 7 days before the cut stand at 5% of the level of the weeks 8–16 before it, then 38%, 78%, 83%, 89%, 94% and 97% for the weeks before. AP+RR births: 27%, 41%, 57%, 55%, 78%, then 89–99%. In the last week the file is below what the 2022 registration delay predicts (5% against about 20–30%); from the second week back it is in line.

**What this means for the design.**
1. **Arboviruses are the one family where a surveillance alarm is possible with the public files.** The cut is a day old and the delay is ~10 days median. The preliminary file must be snapshotted (its refresh interval has been 1–6 weeks).
2. **SIM and SINASC alarms run ~10 weeks behind at best, and the 2026 preliminary file was posted once.** The monthly refresh is observed for the 2025 file only. A syndromic excess seen in all three systems at once is possible only at the SIM horizon.
3. **SIH and SIA cannot serve a weekly alarm.** They publish by competence month, 5–7 weeks after it, and bill by discharge. The weekly grain of ADR-0004 point 1 holds for SINAN only; SIH enters at the month grain with a billing-delay nowcast (36–53% at the first file).
4. **The delay is not one stable law.** Its median varies by a factor of 2 across years (DENG 8–15 days), by 7 across states (SIM 6–45), and with epidemic load (DENG 2024 against 2023 and 2025). A nowcast needs the delay per place and per year, estimated from the previous year's closed file, and has to carry its own uncertainty. The visible fraction at 1 week, .24–.47 for DENG and .05–.38 for SIM, bounds how much a nowcast can say about the last two weeks.
5. **Revisions are real and of unequal size:** SIA +26% at the first rewrite, SIH +3%, SIM PRELIM −4%, a DENG final losing 47% of its rows. They cannot be measured from the catalog; they need snapshots of the preliminary files (ARCHITECTURE §12 phase 4 already lists this). A weekly snapshot of `DENGBR26`, `DOxx2026`, `DNxx2026` and one SIH and one SIA competence costs a HEAD per file and a download only when the size changes.

## Limits

- File mtimes are last writes. The first-appearance claims rest on 108 SIH, 280 SIA and 27 CNES-ST files first seen on 09-28, and on single-date files.
- SIM and SINASC delays use 22 UFs (SP, MG, RJ, BA, RS excluded) in 2022–23 and AP, RR before that. SIH delays use AC, AP and RR only. The SINAN delays are national.
- The delays are conditional on a record being in the closed file. Records that never reach it are not counted, and DT_DIGITA is taken as the first entry date, which the layout does not say.
- Size changes are a proxy for record changes; the content of the replaced versions is gone.
- Not measured: SIA event dates, SINAN families other than DENG, CHIK, ZIKA, LEPT, whether SIM PRELIM 2025 shrank because records were removed.
