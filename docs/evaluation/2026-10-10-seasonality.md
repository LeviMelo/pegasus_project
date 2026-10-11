# Seasonality (BACKLOG 3.2): dengue's regional phases recovered, toxoplasmosis' monthly fields asked

**Scenario.** `pegasus-core ask SINAN-DENG probable_case seasonality '*' --years 2010-2019 --grain month` and the same on
`SINAN-TOXG notification --years 2019-2024`; `scans.lenses.season_departure` (the question's two methods, `season_level`
and `season_change`). Drivers and artefacts under `data/probes/` (`season_table.py`, `season_null.py`, `season_null2.py`,
`season_lens.py`; `season_deng10.json`, `season_toxg.json`, `season_null*_deng10.log`, `ask_*.log`). Regime: branch
`seasonality` (code of this commit), data 0.1.0a1, monthly fits SINAN-DENG probable_case 2013-2019 (7.09 M events) and
2010-2019 (9.41 M allocated), SINAN-TOXG 2019-2024, 2026-10-10.

**Method** (`scans/lenses.py`). Per unit (municipality, immediate region, state) and complete calendar year, an NB harmonic
regression (cosinor: Nelson et al. 1979; Cornelissen 2014) of the 12 monthly counts, B1's expectation times the harmonic
that the same estimator finds on the **rest of the field** (leave-one-out) as offset, a free level per unit-year, a
Gaussian prior on the harmonic learned across the rows (Fellner-Schall). The years are replicates of the season and are
combined as a multivariate random-effects meta-regression (DerSimonian-Laird moments, Jackson et al. 2010; Hartung-Knapp
scaling, Rover et al. 2015): `season_level` the mean departure vector (sin, cos), `season_change` its difference between the
last and the first year. Test of the minimum relevant effect (H0: ||d|| <= log 1.1, the rate-ratio floor): T = d'V^-1 d/2
against non-central F(2, C - p) at the largest non-centrality H0 allows; BH per scale at q / scales, the two methods at q/2.

**Why not against B1 itself** (the unit's row said B2s). B1's season is the robust baseline (epidemic cells trimmed); the
data's national cycle is not it. Against B1 a place-permutation negative (random groups of municipalities, dengue
2013-2019) departed at p < 0.05 in 10-26 % of groups, with a median ||d|| of 0.13-0.25. Against the rest of the field the
negative is clean (below). B2s stays the expectation tier holding a place's own season (`refit_place_season`, unchanged).

## Dengue: the regional phases are recovered

Documented pattern (Churakov, Villabona-Arenas, Kraemer, Salje & Cauchemez, PLoS NTD 2019;13(4):e0007012): most cases
December-June; a seasonal wave from the western states (Acre, Rondonia) east to the coast (Sao Paulo, Rio de Janeiro) and
last to the Northeast; Roraima and Amapa off the wave. Rio de Janeiro State 2016-2023 concentrated March-June (SEER UNIRIO
article, found by search; not read in full). The national B1 season peaks 3 April (amplitude 1.36 in log rate, a 15-fold
peak-to-trough ratio); the raw monthly shares 2013-2019 peak in March-April (22.3 %, 22.7 %).

State and macro-region seasons against the rest of the field, 2010-2019 (peak of the fitted harmonic; shift in months,
negative earlier; departure ||d|| in log rate with its standard error; p against zero, F(2, 9), uncorrected):

| unit | peak | shift | ||d|| (se) | p |
|---|---|---|---|---|
| AC | 7 Feb | -1.79 | 1.12 (0.19) | 0.0009 |
| RO | 17 Feb | -1.46 | 0.93 (0.14) | 0.0003 |
| MT / MS | 2 Mar / 4 Mar | -0.97 / -0.89 | 0.68 / 0.66 | 0.0019 / 0.0013 |
| PA / AM | 8 Mar / 10 Mar | -0.77 / -0.67 | 0.69 / 0.62 | 0.0019 / 0.017 |
| SP / MG | 24 Mar / 25 Mar | -0.24 / -0.19 | 0.63 / 0.66 (amplitude 1.83 / 1.89 against 1.23 / 1.25) | 0.019 / 0.004 |
| RJ | 3 Apr | +0.10 | 0.07 (0.11) | 0.81 |
| PE / PI / CE / RN | 24-29 Apr | +0.8 to +1.0 | 0.58-0.75 | 0.0008-0.029 |
| PB / SE / AL | 9 / 14 / 20 May | +1.29 / +1.45 / +1.68 | 0.84 / 1.08 / 1.05 | 0.0011 / 0.0004 / 0.0001 |
| RR | 3 Jun (amplitude 0.35) | +2.08 | 1.22 (0.17) | 0.0002 |
| North / Centre-West / South | 26 Feb / 18 Mar / 14 Mar | -1.21 / -0.49 / -0.53 | 0.87 / 0.35 / 0.56 | 0.0004 / 0.016 / 0.012 |
| Southeast / Northeast | 28 Mar / 27 Apr | -0.10 / +1.11 | 0.71 / 0.87 | 0.0009 / 0.0003 |

West earliest (Acre, Rondonia 1.5-1.8 months before the field's 1 April), the Southeast coast near the national peak
(Rio de Janeiro on it), the Northeast last (Paraiba, Sergipe, Alagoas 1.3-1.7 months after), Roraima off the wave with a
flat season (amplitude 0.35), as documented. The seven-year fit (2013-2019) gives the same order (AC -2.2, RO -1.4, ... AL
+1.9, SE +1.9, RR +3.3 months). The lens's findings (`ask`, BH): **5 state answers at 2010-2019** (Alagoas p 1.3e-4,
Roraima 3.3e-4, Rondonia 5.5e-4, Sergipe 6.2e-4, Acre 1.3e-3; rate-ratio effects 2.5-3.4 at the departing month); none
at the municipality or the region, none for `season_change`; **none at 2013-2019** (seven years: best state p 7e-4 against
BH 3e-4): the F(2, C - 1) reference with seven years leaves the 27 states without the power the ten years have. The season
carries a between-year variance (tau^2 0.06-0.3, Q/df about 1): epidemics do not repeat their timing, and a place's
year-to-year scatter is what the test is set against.

**Negatives on the real data** (the lens's statistic, BH at q/6, p_min = p against the minimum effect). Random groups of
municipalities are not exact nulls (their mixes of seasons differ), so two kinds were run on 2010-2019:
- state-stratified (every group holds a random 1/G of each state's municipalities, so it has the nation's mix of seasons),
  G = 4, 8, 27, 20 worlds each: **0 BH rejections in 60 worlds** (level and change), p_min < 0.05 in 0 / 0.6 / 5.4 % of
  units (level) and 0 / 0.6 / 1.1 % (change);
- unstratified random groups, G = 27, 100, 510, 6 worlds each (36 worlds per estimand): **0 BH rejections** with the
  reference used, F(2, C - p). The groups' mixes of seasons differ, so p against zero is inflated (11-37 % at .05 for
  `level`, 1-5 % for `change`) and p_min < 0.05 holds in 4-10 % of the `level` units (the small groups' composition noise,
  above the nominal 5 %); that is why the family is BH over the test of the minimum effect and a rejection needs both.
The second reference F(2, 2(C - p)) (the isotropic scalar's degrees of freedom) was refused: it rejected 18-37 % of the
random groups at .05 for `level` (p_min < 0.05 in 6-15 %) and gave one BH rejection in 36 worlds.

## Toxoplasmosis (SINAN-TOXG notification, 2019-2024, six complete years): asked, nothing departs

The field's season is weak: B1 amplitude 0.088 (peak-to-trough 1.2), peak 17 July (monthly shares: August 9.6 %, December
6.7 %, January 7.9 %). At the state scale every state is within sampling of the rest: smallest p 0.059 (Rio Grande do Sul,
peak 29 Aug, +1.4 months, ||d|| 0.06), next 0.18 (Minas Gerais); standard errors 0.02-0.03 in log rate, so the lens can
only see departures of about 0.1 and larger (the floor), and the macro-regions are within 0.4 months (North 5 Jul to
Northeast 29 Jul). `season_level` and `season_change`: 0 answers at the municipality, the region and the state. The
answer to "TOXG's monthly fields asked" is: asked, and the notification season is the same everywhere (one cycle, peak
July-August), not changing over six years.

## Debts

- tau^2 between years is scalar and the clusters are calendar years: a season that straddles the new year (the North's
  Amazon dry-season dengue) is cut in two; clusters starting at the field's trough would not be.
- The change is a linear drift of the yearly departure; a step is not asked (the other shapes would be the trend question's
  at the monthly grain).
- Ten years leave 27 states with 5 findings where the biggest departures are 3-fold; the test is by construction
  conservative (the non-centrality at the largest eigenvalue, F with C - p degrees of freedom).
- The synthetic calibration (a null world drawn from the predictive with N1's frailty) is not made; the nulls above are the
  real-data permutations. The B3 grid's planted seasonal shift is the next measurement.
- The 2013-2019 monthly fit took 7 minutes (shared store); a surprise at B1 for the national field about 4 minutes more.
