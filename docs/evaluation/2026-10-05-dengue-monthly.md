# Dengue at the monthly grain: fit, calibration, epidemics (2026-10-05)

**Regime:**
- **Data:** SINAN-DENG `probable_case` (a notification whose CLASSI_FIN is not 5), municipality of residence, **month of first symptoms**, 2010–2023, through `gateway.monthly_counts`. Contiguity graph; pegasus_data on `pegasus-core-fixes`.
- **Scripts (local, `data/` is gitignored):** `fit_dengue_monthly.py`, `dengue_tabnet_reference.py`, `dengue_eval.py` (`recon|fit|calib|lens`); outputs `data/logs/dengue_eval_*.json`, `fit_dengue_*.log`.
- **Code:** monthly `extrapolate` (below), period codes on `Surprise.years`.

## The counts against an independent figure

- **Files.** TabNet "Casos Prováveis" (`denguebbr.def`, DENGBR14–23) against the allocated plus unallocated events of each publication file: **equal for 8 of 10 files** (2014: 543,918; 2015: 1,623,172; 2016: 1,450,084; 2017: 239,395; 2018: 262,611; 2019: 1,546,252; 2021: 540,049; 2022: 1,405,095).
  - **2020:** ours 956,463 against TabNet 975,842 (−2.0%). The FTP file holds 1,495,117 rows, 538,654 of them discarded; TabNet's DBF is another consolidation. A Ministry bulletin figure for 2020 is 987,173 (read in a SciELO article citing the Boletim Epidemiológico 2021, not at the source).
  - **2023:** ours 1,645,956 against TabNet 1,645,350 (+606: the FTP file has no discarded class-5 rows, TabNet's has).
  - TabNet holds no file before DENGBR14. The 2010 and 2013 files read through the DBC fallback: 1,004,314 and 1,455,118.
- **Months.** Onset-year × month matrix of TabNet (summed over the files) against ours, 2014–2023: annual ratios 0.971–1.003 (2020 the low one), monthly ratios 0.95–1.00. One outlier: December 2019, 1.159 (onsets filed in the 2020 file that TabNet's version lacks).
- The Ministry's later-revised series is higher (2015: 1,688,688; 2023: 1,658,816, as reported in a web-search summary of its historical series, not read at the source): the FTP publication files are earlier consolidations, so ours is 3.9% and 0.8% below.

## Fit, 2010–2023 (all Brazil, one leaf)

13,961,701 events, 2,561,393 non-empty cells, 5,570 × 168 months. Unallocated: municipality 11,203, sex 17,759, date outside the period 1,746, unparsable date 14. GPU, 14 outer iterations, 767 s.

| quantity | value |
|---|---|
| φ (NB, municipality-month cells) | 0.235 |
| τ: h (RW2 over 168 months) | 0.0022 (free to follow the waves) |
| τ: season (cyclic RW2) | 2.76 |
| τ: spatial ICAR | 1.5·10⁶ (at the bound): the smooth spatial part vanishes |
| iid place effect | sd 1.68 (log scale) |
| B2s refit τ: α, β, sin, cos | 0.88, 1.54, 1.30, 1.85 |

**Season, national:** peak April, trough September, peak-to-trough ×13.2 (log: 1.42 to −1.16). **By macro-region** (national season plus the weighted B2s harmonic):

| region | peak | trough | peak/trough |
|---|---|---|---|
| Norte | Mar | Aug | ×6.8 |
| Nordeste | Apr | Dec | ×9.3 |
| Centro-Oeste | Apr | Sep | ×13.2 |
| Sudeste | Apr | Sep | ×37 |
| Sul | Apr | Sep | ×102 |

The ICAR collapse says a time-invariant spatial effect does not describe dengue: places differ by epidemic, not by level (the low-rank place × time interaction, not built, would carry it).

## Calibration (randomised PIT, KS; criterion ≤ 0.03 overall, ≤ 0.05 per macro-region)

In-sample on the full fit, 936k municipality-months. Every tier needed the field's own φ.

| tier | KS 2010–23 | worst region | KS 2019–23 | worst region |
|---|---|---|---|---|
| B0 | 0.051 | Centro-Oeste 0.211 | 0.036 | Centro-Oeste 0.294 |
| B1 | 0.033 | Centro-Oeste 0.103 | 0.046 | Centro-Oeste 0.173 |
| B2 | 0.028 | Centro-Oeste 0.065 | 0.033 | Centro-Oeste 0.106 |
| **B2s** | **0.011** (calibrated) | Centro-Oeste 0.047 | 0.015 | Centro-Oeste 0.078 |

- **Season is what calibrates dengue.** B2s flattens the PIT histogram (all deciles 0.094–0.105); B0 to B2 are humped.
- **Centro-Oeste fails first** at every tier; the B2s 2019–23 subset (KS 0.078) fails the regional criterion though the whole period passes.
- **BP, trained to 2014, predicting 2015–2016:** observed 3,065,926 against 1,172,045 expected (×2.6); KS 0.225 (Sul 0.10, Centro-Oeste 0.32). Recorded, never flagged: this tier exists to show the departure.
- **BP, trained to 2018, predicting 2019–2023: not yet run.** The train-2018 fit failed with CUDA out-of-memory (another agent held the GPU) and its restart was blocked; an earlier CPU fit, run beside two others, had reached outer 12 in 1,224 s when it was stopped to move to the GPU.

## The known positive: dengue epidemics by state

State-level outbreak lens (municipalities lifted to 27 states; state-month variance component φ_extra = 3.63 by ML on the in-sample B2s state cells, the same value for every tier). Reference: a state-year is an epidemic when its probable incidence is ≥ 300 per 100,000 person-years (the conventional "high incidence" cut; I could not confirm its source here).

| tier | state-months tested | flagged state-years | epidemic state-years | recall | precision |
|---|---|---|---|---|---|
| **B2s** (fit over 2010–23) | 4,536 | 1 | 173 | 0 | 0 |
| **BP trained to 2014**, 2015–16 | 648 | 37 | 37 | 0.78 | 0.78 |

- **B2s does not recover the epidemics, by construction:** the monthly history h is fitted to the national waves, so the epidemic years are normal there. Its 474 municipal hits (of 935,760 cells) fall in 2017–18 (108 and 85), the troughs after the waves: local flare-ups against a low national level. This is §6.1's statement (surveillance reads BP), now measured; **the §10.1 row "dengue epidemics, B2s" should name BP**, and B2s is for out-of-season events.
- **BP recovers 2015–16:** 13 of 19 epidemic states in 2015 and 16 of 18 in 2016 flagged (29 of 37). The 8 misses (Acre, Rio Grande do Norte, Alagoas, Minas Gerais, Rio de Janeiro ×2, Paraná, Distrito Federal) had incidences 352–847: states whose 2010–14 training already held epidemics. The 8 flags below 300 include Santa Catarina 2015–16 (62 and 70 per 100,000, rate ratio 44 and 63): dengue arriving where the past held almost none, a departure from the past and not an epidemic by incidence.
- **The monthly forecast of h.** The documented linear extrapolation (RW2 forecast mean from the last two periods) is unusable at the monthly grain: h moves ±0.3 per month, and a 60-month horizon would carry the last slope (0.32 per month on the full fit) to a factor of e^19. `extrapolate` now holds the monthly h flat at its last twelve months' mean (annual grain unchanged).

## Pending

- BP trained to 2018 (2019–2023) calibration and state recovery; the space-time lens at B2s; 2024 is outside the data.
