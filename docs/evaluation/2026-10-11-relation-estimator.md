# The relation estimator (BACKLOG 3.5, 2026-10-11)

**Regime.** Branch `relation-estimator` (from `scope-v2` 429317b), shared store, data 0.1.0a1. B1 monthly fits of SINAN
notification fields (2012-2019; TOXG, TOXC 2019-2025) and SINASC's Q02 (`code_list` CODANOMAL). Commands:
`pegasus-core compare SINAN-TOXG:notification:'*' SINAN-TOXC:notification:'*' --years 2019-2025 --grain month --lags 12`;
`tools.relate` with `window=(201401, 201712)`, `macro=[2]`, `profiles=True` for Q02 against CHIK; controls
`scripts/relation_controls.py 12` (artefact `data/probes/relation_estimator/controls_L{6,12}.json`).

**What replaced what.** One estimator (`relations.relation_estimate`) for the time-varying pair relation: a follower's
innovations at t against a leader's at t-ℓ, projected on supports (nine graph-frequency bands, the macro-regional and the
national course, information-weighted), a null of the leader's circular shifts (one shift for all places: the leader's
spectrum, spatial and nonlinear structure kept), one BH, the partial and direct read of what is reported, and a lag
profile per pair and support. It replaces the band factor model, `relation_table`, `course_relations`,
`direct_relations`, `lagged`, `bands`, `spectral_factor_model` and `scans.pairs.within` (E_w); `compare`, `determinants`
and `relation_survey` read it with their row schemas. `Session.relation` (distributed lag) stays: it gives the effect in
rate-ratio units, which a correlation does not. `joint` stays: it localises co-departures, which no support-level
statistic does.

**What the first null got wrong.** The first null was the leader's phase surrogates with the statistic's variance in
closed form (checked against 20,000 draws: 2,484 closed against 2,474 drawn). On place-permuted copies of real fields
it called pairs related 2-4 times too often below p = 0.001 (0.21 % of 16,380 tests against 0.1 %; 3 of 4 families
reported a false relation). A leader whose energy sits in a few periods (an epidemic) has a shift null of kurtosis 6-10
where the surrogates' is 2.6. The null became the Student-t on the shifts' variance, with the smaller of the
kurtosis's and the effective-size degrees of freedom, over the shifts clear of the tested lags (a relation lifts its own
neighbourhood: 43-76 % of the closed-form sd in the fine bands). Where fewer than 10 effective clear shifts exist (T = 48,
L = 12: 11, smooth) the clear shifts called 119 of 225 rows related on two epidemic waves; all shifts are then the null.

## Negative controls (real fields, 8 fields, T = 72 months, `scripts/relation_controls.py`)

Each real field against a copy of every other, time-reversed or place-permuted; the national support is dropped for
permutations (a permutation keeps the nation's course).

| lags | control | row tests | p < .05 | p < .01 | p < .001 | reported | profile tests, p < .05, reported |
|---|---|---|---|---|---|---|---|
| 12 | time reversed | 11,550 | 4.9 % | 0.78 % | 0.04 % | 0 | 924, 1.5 %, 0 |
| 12 | place permuted ×3 | 10,500 each | 5.9-6.7 % | 1.2-1.3 % | 0.17-0.34 % | 18, 8, 7 | 840 each, 3.3-5.2 %, 0 |
| 6 | time reversed | 6,006 | 5.1 % | 0.88 % | 0.03 % | 0 | 924, 4.0 %, 0 |
| 6 | place permuted ×3 | 5,460 each | 5.6-6.9 % | 1.0-1.5 % | 0.07-0.37 % | 6, 1, 0 | 840 each, 3.9-5.6 %, 0 |

Time reversal is at nominal. Place permutation is not: the rows' tail is 2-5 times nominal below p = 0.001, and the
reported ones sit mostly in the lowest bands, where a permuted copy still carries the nation's course (SINAN fields
share a notification-system course). The profiles (one test per pair and support) hold at nominal and report nothing.
**Planted lag** (LEPT against a copy of itself leading it by 3 months, diluted with another field to correlation a;
11 supports): lag 3 is the smallest p and reported at 10, 9-10, 8 and 5 supports for a = 1, 0.5, 0.25, 0.1.

## 1. SINAN-TOXG → SINAN-TOXC (monthly 2019-2025, T = 84, lags 0-12, 11 supports)

**Result: the lag shows in the profile at the fine scales, and no row or profile reaches q.** Of 275 rows 0 reported;
of 22 profiles 0 (smallest p 0.034).
- At 20-49 places (λ 0.1-0.5), TOXC follows TOXG at lags 1-8 (mean ρ 0.029-0.032, rows z 2.0-3.0, largest at lag 4 in the
  49-place band, p 0.003) and not beyond lag 9 (mean ρ ≤ 0.005): the nine-month gestation.
- The reverse direction (TOXG following TOXC) has ρ ≈ 0.001 at lags ≥ 1 in the same bands, and ρ 0.05 (z 2.6-3.1) at
  lag 0: the same-month co-notification, which is the only relation common to both orders.
- At the coarse supports both orders are positive (cumulative ρ 0.13-0.24, p ≥ 0.09): a shared slow course, no lead.
- The annual grain (T = 7) has no power (0 of 55 rows).
Stage of the miss: the null's power, not the data model. One pair of 84-month series gives the smallest row p 0.003,
against a BH threshold of 0.0002 for 275 tests.

## 2. Arbovirus → microcephaly (SINASC Q02, Northeast, window 2014-2017, lags 0-12; Zika 2015-2017, lags 0-8)

DENG fails B1's calibration (KS 0.025) and, by invariant 8, is left out (its earlier, unscreened rows are not
reported). **No row or profile reaches q (0 of 225 rows, 0 of 18 profiles; with Zika 0 of 459, 0 of 54).** The profiles
all peak where the documented lag lies:
- Q02 ← CHIK: ρ rises from 0 at lag 1 to 0.47 at lags 5-7 (NE course, z 2.0), 0.57 at lags 6-7 in the ~492-place band
  (z 2.7), 0.35 at lag 6 in the ~333-place band (z 2.7); cumulative p 0.045-0.078 at the coarse supports, peak lags 5-8.
- Q02 ← ZIKA (2015 retrospective notifications and 2016): ρ 0.97 at lag 7 in the NE course (z 2.5), 0.70 at lag 7
  at ~492 places (z 2.8); peak lag 6-7 at six supports, cumulative p 0.056-0.22.
- The reverse (CHIK or ZIKA following Q02) shows no lead.
The earlier tests, a per-lag E_w correlation and a prewhitened one, saw a plateau at lags 0-6 and a lag-0 coincidence;
this one sees a peak at 6-7 months on both arboviral series, as the 6-9 month window predicts. It is not significant:
one epidemic wave in 36-48 months is a few effective observations, and the shift null cannot say more (z 2.5-2.8
against a threshold near 3.7). Reported as a miss at its stage (the null's power on short single-wave series), with the
peak as the finding.

## Debts

- The tail is a moment-matched Student-t, not exact; place permutation shows it 2-5 times nominal below p = 0.001 for rows.
  Remedy: shifts per block of coherent coefficients, learned from the leader's spatial coherence (a common shift is the
  coarsest null that keeps the structure; independent shifts per place the finest).
- `NULL_MIN_EFFECTIVE` = 10 and the guard of as many shifts either side as the tested lags are hand-set.
- Distance is read as the graph frequency; a leader's effect on neighbouring places (a spatial lag) is not estimated.
- The bands weigh places equally (the courses weigh by information).
- `Session.relation` has no null; the shift null of its exposure is the one to attach.
