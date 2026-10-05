# Replication from independent units: size, power and the SIM register re-tiered (2026-10-05)

**Regime:** ADR-0015 (this entry measures it; supersedes the sizes of `2026-10-05-replication.md`, whose event-side tests ADR-0015 withdrew). Code of the commit of this entry (`replication.simulate_*`, `corroborate._null_sets`, `Session.train/temporal_confirm/spatial_confirm/corroborate/retier`). Simulations: `data/replication_power.py`, `repl_spatial.py`, `repl_spatial2.py`, `repl_corroborate*.py`, `repl_placebo.py`, `repl_reserve_power.py` → `data/perf/out/replication_power.json`. Real data: SIM.DO death 2010–2023, contiguity graph, `data/retier_register.py`, `data/spatial_T2019.py` → `data/perf/out/retier_register.json`, `spatial_T2019.json`; survey on the years ≤ 2019 (`pegasus-core temporal-survey`, blocks I, IX, X, XVIII, XX; XX fitted for this entry). The reserve (SIM.DO 2024) was **not read**: the LOND stream is unspent, `Reserve.state()` = (0, 0).

## Size and power on negative-binomial worlds

Cells of mean μ per year, NB size n (frailty independent over years, or AR(1) ρ = 0.5), 10 training years and 4 later; selected on a scan of 1–3 year windows at p < 0.001 against 1.2 × the mean; tested on the sum of the later years (`test_prospective`'s tail). 200,000 cells per row, 3 draws for the null. "Known": the expectation is the true mean (a fit that sees only the training years but is exact). "Own mean": the cell's training mean, which contains the excursion that selected it (the pessimistic bound; the real BP fit pools over places and ages and lies between).

| later-years tier, share of selected cells replicated at 0.05 | known | own mean |
|---|---|---|
| null, ρ = 0 (μ 5–500, n 3 / 10 / ∞) | 0.000–0.014 | 0.000–0.002 |
| null, ρ = 0.5 | 0.025–0.071 (n = 3: 0.06–0.07) | ≤ 0.005 |
| persistent × 2 / × 4 (from year 4), μ = 50, n = 10 | 0.92 / 1.00 | 0.05 / 0.18 |
| persistent × 2 / × 4, n = 3 | 0.57 / 0.99 | 0.02 / 0.14 |
| recurring × 2 / × 4 (years 3, 6, 9, 12: one recurrence in the later years), n = 10 | 0.09 / 0.68 | 0.00 / 0.01 |
| one-off × 4 (year 4) | 0.00–0.05 (serial correlation only) | 0.00 |

The tier is conservative under independent variation and slightly liberal (≤ 0.07) when the frailty is serially correlated and the expectation is exact (the NB tail assumes independent years). A departure already inside the training window is absorbed by a refit that sees it, so persistence is detected mainly as a level the fit did not know; a one-off never replicates (the design). On real data 15% of the training leads stand (below).

- **Sizes (side E).** 2,000,000 cells per row, selected on side A at p < 0.001: the mean rate ratio on all events is 1.3 to 8.5 for a true realised 1.0 to 7.9; on A it is inflated the same way; **on E it equals the realised ratio** (1.00 vs 1.00 for Poisson; 3.31 vs 3.26, μ = 5, n = 3; 2.04 vs 2.04, μ = 20, n = 10). The exact 90% interval covers the realised rate at 0.915–0.958 (6 settings, 550–1,900 selected cells).
- **Other places (unit trends).** 14 × 14 lattice, 300–400 units per row. At the boundary (trend = δ) 312 units selected on a half, 5.8% replicate on the other (buffered 5.3%, unbuffered 6.2%); at 3δ power 0.99+ (0.95 at the worst). With year-by-year shocks smooth over the graph no row departs from 0.05 (7–25 units selected per row). **With a random log-linear slope smooth over the graph (neighbours share a trend) the halves share it and the tier is not a test against it:** replication of selected units 0.02–0.47 buffered, 0.17–0.66 unbuffered (slope sd 2–8 δ, smoothing 2–8 steps; table in the JSON). The buffer halves the excess; it cannot remove a field wider than the unit. A trend field of that size is a regional trend, which is also what the claim says.
- **Another record system.** 30 × 30 lattice, a one-off ×θ in a cluster of 6 or 12 places for 2 years, the other field NB (n 3–10) with shocks smooth over 3 steps. Scattered null sets (the old `_null_sets`): size 0.06–0.12 once the shocks reach 0.3; **connected null sets grown on the graph (now the default)**: 0.01–0.06; power at ×1.5 falls 0.73 → 0.59 (k = 6), 0.81 → 0.66 (k = 12), without shared shocks (or weak ones, sd 0.15) the two nulls coincide (size 0.03–0.07, power 0.83–0.95 at ×1.5, 1.00 at ×2 and above). **Placebo windows on real SIH** (5 categories × clusters of 3/6/12 × random 2-year windows, 8,996 placebos): scattered 0.061, connected **0.049** at the 0.05 level.
- **A permutation p cannot clear Benjamini–Hochberg when the tests outnumber the replicates.** With 4,999 replicates the floor is 2·10⁻⁴ and BH over 863 SIH tests needs 6·10⁻⁵: no lead could be corroborated whatever the data. `Session.corroborate` now redraws the leads with p < 0.01 at 99,999 replicates (chunked).
- **The reserve (one year, 2024).** Same worlds, 14 training years, 1 later; persistent departure from the start of the period, level 0.05 before the stream: known expectation ×1.5 / ×2 / ×4 = 0.09–0.19 / 0.26–0.53 / 0.84–0.98 (μ 5–500, n 10; Poisson 0.14–1.00 / 0.42–1.00 / 0.99–1.00), own mean 0.02–0.03 / 0.05–0.06 / 0.01–0.02; null 0.00–0.01.

## The SIM register re-tiered

Survey on the years ≤ 2019 of blocks I, IX, X, XVIII, XX (1,439 leads selected; **333 register leads match one that stands on 2020–2023**: BH over everything tested, re-levelled by state and year). 7,496 triaged leads, tier by class (R1 = temporal; no lead holds two):

| class | R0 | R1 | no counterpart / block not surveyed / tested, not standing / stands |
|---|---|---|---|
| signal | 1,921 | 94 | 1,029 / 470 / 422 / 94 |
| system artefact | 3,883 | 162 | 3,063 / 403 / 417 / 162 |
| substitution | 674 | 72 | 341 / 193 / 140 / 72 |
| noise | 685 | 5 | 363 / 233 / 89 / 5 |

By lens: trend 170 stand (of 435 tested), space-time 151 (664), outbreak 12 (300); change point 0 (2). Group disparity has no later-years test. 4,796 leads have no training counterpart (windows inside 2020–23, COVID-19 and after, or not found on the earlier years), 1,299 lie in blocks not surveyed, 1,068 were tested and did not stand. 7,163 leads hold no confirmation, 333 hold one, none two or three.

- **Other places.** The register has no unit claim to split: all 3,355 SIM trend leads of the survey are neighbour-referenced, none a national-trend claim at region or state. The tier was run on the 446 national-trend claims of the ≤ 2019 survey instead: 349 testable, 261 reach 0.05 on their first half, 159 stand on the second (all states; **no region does**: 84 regions, 20 stand temporally, none spatially — a region's municipalities are too few to halve with a buffer); with the later years, **57 claims hold both (R2)**, 74 only the later years, 102 only the places, 213 neither.
- **Another record system.** Signal leads tested: SIH 863, SINAN 85, S2iD 24 (the rest have no rule, or are deficits). Raw p < 0.05: 56 (43 expected by chance), 16 (4), 3 (1.2). After BH within source (SIH redrawn at 99,999 replicates where p < 0.01) **none is corroborated** (smallest q: SINAN 0.089, S2iD 0.186, SIH 0.61). Corroboration is unproductive for SIM signals as built: the SIH survivors and the SINAN notifications of the places rarely move with the deaths beyond what places of the same state do.
- **The 15 top signals (triage entry).** Tiers: **#10 J09 Rio Brilhante+ 2016 is R1** (13 deaths against 3.5 expected in 2020–23, p 0.009, q 0.048, borderline; not corroborated by SIH). The rest are R0: #1, #2 (A92 Fortaleza/Maracanaú 2017), #6–#8, #11–#15 have no training counterpart (windows in the later years, or an outbreak the ≤ 2019 survey did not select) and their corroboration fails (SINAN p 0.36/0.33; S2iD 0.45, 1.0; SIH 0.88, 0.51, 0.85, 0.88; #14 is a trend with no window to corroborate); #3, #4 (Brumadinho: 35 deaths against 126 expected afterwards), #5, #9 were tested on the later years and did not stand, as one-offs do not (the S2iD records of Rio 2010: 3 places, p 0.008, q 0.19 after the 24 S2iD tests; Brumadinho 2019 is not in S2iD); #15a has no independent field, #15b is a deficit. **No one-off event reaches any tier**; the only route is a corroboration whose power is limited by the few places of a lead (S2iD) and by the multiplicity of the source.

## What a reserve spend would test (not done)

SIM.DO 2024 against the fit on 2010–2023, re-levelled by state; `gateway.population([2024])` exists for the default source (popsvs, 212.6 M persons). It can only test that a departure **persists or recurs**; the 333 temporal leads and the unit trends (362 states, 111 temporal-standing in ≤ 2019) are the candidates. LOND at q = 0.05 with the stream unspent gives levels 0.0315, 0.0063, 0.0026, 0.0015, 0.0009 … (0.046 spent by 15 claims) unless a claim is rejected and raises the next: **it affords one or two decisive claims and a handful of weak ones**. With one year the power at the first level is 0.1–0.5 for a ×1.5–2 departure with an exact expectation and about 0.05 when the fit has absorbed it. The order must be fixed before 2024 is read (the strongest persistent state-level trends first); the top-15 spend is not worth it (twelve are one-offs, which cannot recur).

## Verdict

Measured: the later-years tier holds its size and has the power only to see departures the fit did not know; the sides' size E is unbiased; the spatial tier holds its size against year-to-year shocks and not against a smooth trend field; the connected corroboration null is calibrated on real SIH and the scattered one is 20% liberal. The register: 4.4% R1, none R2 or R3; the unit-claim set: 57 of 446 R2. Not measured: the ADR-0005 negatives (`harness.lens_world` space/time) through the whole survey-and-test chain on a real Surprise; the sizes (`honest_sizes`) on real leads; the reserve.
