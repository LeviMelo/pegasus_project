# Stage C on documented events: the baseline

**Regime.** pegasus_core `design-v0` at 87e10b3 plus the uncommitted robust field dispersion (which did not engage). SIM and SIH 2010–2023, B1. Script `data/real_events.py` (events and criterion declared before the run); artifact `data/probes/real_events.json`; log `data/logs/real_events.out`.

**Why this is the measurement that matters.** Every synthetic grid of 2026-10-06/07 drew its worlds from the model it tested, so it could not show that the model itself was wrong. These events are known independently of the model.

The criterion: a finding whose years overlap the event's and at least half of whose places lie in its area.

| event | multiscale spike | multiscale step | ladder cell excess | outbreak lens |
|---|---|---|---|---|
| yellow fever deaths, MG/ES/SP/RJ 2017–18 (SIM A95) | missed | an unrelated SP step from 2013 | ES 2017, 38× | one MG town, 11× |
| measles admissions, RR/AM 2018–19 (SIH B05) | missed | missed | missed | missed |
| chikungunya and other arboviral fevers, Northeast 2016–17 (SIH A92) | missed | missed | missed | missed |
| Brumadinho 2019 (SIM V01–X59) | the town, 5.1× | the town, from 2019 | the town, 7.4× | the town, 7.4× |
| COVID-19 in the North 2020–21, relative to Brazil (SIM B25–B34) | missed | missed | missed | missed |

**Diagnosis (stage B), measured on the fields themselves:**
- **One dispersion per chapter.**
  - The monolith fits one φ per chapter. Chapter I's is about 0.1–0.14, set by its epidemic diseases: 180 yellow-fever deaths against 16 expected in the four states are no surprise under it.
  - The calibration check passes trivially (KS 0.002), so the field-level remedy never engages.
- **No time course per category.**
  - A category has a level and place deviations, and follows its ICD group's time course; dengue drives A90–A99's.
  - The Poisson fit sets the category's level with the epidemic years included. Measles is expected at 200–300 admissions every year against 33–83 observed outside 2018–19 (891 and 833). Yellow fever is expected at about 32 deaths a year against 0–8 outside 2017–18 (195 and 257).
- **Chapter XX is fine.** It holds no epidemics, so its dispersion is honest, and Brumadinho is found by every method.

**Consequence.** Stage B is refitted robustly before any detector is judged further: plan `docs/plans/2026-10-07-robust-expectation.md`. It is accepted on these events, with no constant tuned to them.

## After the stage-B fix (same script, same criterion, same methods)

**Regime.** Robust stage B by default (`Monolith.robust`, v1: two rounds of trimming at the predictive's upper 0.5 % quantile, imputation by the expectation, refit; no category courses yet). The detectors carry the night's fixes:
- the noise estimated on the background only (`surprise.background`);
- the spatial share penalised when unidentified;
- the multiscale score as the probit of a gamma tail probability (`multiscale.tail_z`; a standardised difference gave one death against 0.0001 expected a score of 100);
- a separate cache key for the robust fit, and the surprise cache at version 3.

Artifact `data/probes/real_events.json`; the baseline is kept as `real_events_baseline.json`.

| event | multiscale spike | multiscale step | ladder cell excess | outbreak lens |
|---|---|---|---|---|
| yellow fever 2017–18 | RJ/SP 2018, 16-place scale, 343× | (a step 2013–23: shape misattributed) | ES 2017, 92× | SP town 2018, 39× |
| measles 2018–19 | AM 2018, 818× | AM 2016–23, 4-place scale | AM 2018, 471× | AM 2018, 491× |
| chikungunya 2016–17 | BA 2017, 120× | MA from 2017, 29× | MA 2016, 122× | MA 2016, 122× |
| Brumadinho 2019 | the town, 7.4× | (a step 2017–23) | the town, 13.4× | the town, 13.4× |
| COVID-19 North 2020–21 | PA 2020, 1.35× | (a step 2015–23) | PA 2020, 1.36× | AM 2020, 3.3× |

**What changed, by measurement.**
- **Ordinary-year expectations now track their observed level:** measles 70–90 admissions a year against 33–83 (was 200–300); yellow fever 4–7 deaths against 0–8 (was about 32).
- **Every event is found by three methods at least.** The multiscale model reports each at its own scale.
- **The step model's matches of spike events are shape misattributions.** The overlap criterion cannot tell a step from a spike; it is to be tightened to the event's window.

**Still open.**
- **Volume.** Epidemic fields now report hundreds of departures: chikungunya admissions 999 cells, COVID-19 966 multiscale peaks. Under a robust expectation that is statistically right (every place chikungunya reached departs from its pre-chikungunya background). Ranking and summarising them is stage F's.
- **Category courses (plan step 4).** A category that dominates its group (COVID-19 in B25–B34) leaves its siblings mis-expected. It is being fitted by alternation to the joint optimum and is measured next.

## Robust stage B v9 with the N1 noise re-estimated (v9c, later the same night)

**Regime.** Robust stage B v9 (trimming only, no category courses). N1's κ by central matching of the randomised PIT's quartiles (`surprise._central_kappa`), and ρ, δ from winsorised lag moments (±`TRIM_Z`); surprise cache 10. The same script and criterion: `data/real_events_v9c.py`, artifact `data/probes/real_events_v9c.json`, log `data/logs/real_events_v9c.out`. Between v9 and v9c the untrimmed κ had been inflated by measles itself (κ = 1000, measles missed by the multiscale spike); central matching gives κ ≈ 20 for B05, 71 for A92, 0.9 for diarrhoea and 2.8 for stroke.

| event | multiscale spike | multiscale step | ladder cell excess | outbreak lens |
|---|---|---|---|---|
| yellow fever 2017–18 | SP 2018, 2-place scale, 460× | (MG 2013–23) | ES 2017, region, 92× | SP town 2018, 39× |
| measles 2018–19 | Manaus 2018, 818×, p 3×10⁻⁴³ | (AM 2013–23) | AM 2018, region, 471× | AM 2018, 491× |
| chikungunya 2016–17 | MA 2016, 173× | MA from 2017, 51× | MA 2017, region, 62× | MA 2017, 94× |
| Brumadinho 2019 | the town, 4-place scale, 4.1× | (2016–23) | the town, 13.4× | the town, 13.4× |
| COVID-19 North 2020–21 | AM 2020, 2.6× | (PA 2017–23) | PA 2020, 3.8× | PA 2020, 3.8× |

**Reading.** Every event is found by the three spike-type methods, each at its own scale. The multiscale step's matches, in brackets, start years before their events: its suffix sums fire on a one- or two-year epidemic inside their window. The overlap criterion counted them, wrongly. Chikungunya's step from 2017 is the one that may be real (the virus settled endemic in the Northeast after 2016); its shape is attributed below.

## Each finding's course in time attributed (v10)

**Regime.** As v9c, with `departures.attribute` on every multiscale and Bayesian-step finding. That is Chen & Liu's (1993) iterative intervention analysis (additive outlier, temporary change, level shift, ramp; GLS under N1's covariance of the kernel-weighted series; critical |z| 3). A step method's match now counts only when its finding is attributed a step. Script `data/real_events_v10.py`, artifact `data/probes/real_events_v10.json`.

- **The spike-type methods are unchanged.** Every event is found by the multiscale spike, cell excess and the outbreak lens, and every matched multiscale spike is attributed a spike in the event's year (yellow fever 2018, z 225; measles Manaus 2018, z 596; chikungunya MA 2016; Brumadinho 2019, z 31; Manaus 2020, z 10).
- **The multiscale step now matches no event.**
  - Its bracketed matches of v9c are each attributed a spike in the event's year: MG 2018, Manaus 2018, Brumadinho 2019.
  - Of its top five findings per field, one is attributed a step: PA accidental deaths from 2020, z 10.
  - The step question (`questions.ask`) returns the others apart, under `other_shape`, as answers to the excess question.
- **Chikungunya.** No step in MA is attributed. The strongest MA findings are spikes in 2016 and 2022, with a transient from 2021: recurrent epidemics, not one lasting change of level.

## N1 corrected, and the empirical null by absorption class (v11, v12)

**Regime.**
- N1 on normal scores clipped at the universal threshold, with its own lag scale (surprise cache 12; evaluation 2026-10-06, noise structure).
- Scripts `data/real_events_v11.py` and `_v12.py`; artifacts `data/probes/real_events_v1{1,2}.json`.

**v11, the empirical null per contrast** (it fixed the multiscale step's null worlds):
- COVID-19 in the North was **missed** by the multiscale spike;
- measles' best match fell from p 10⁻⁴³ to 10⁻⁷.
- **The cause.** A spike's contrast is one year, so the year-wide COVID-19 excess of 2020 moved that year's own median and MAD, and the null took it in. This is the empirical null's known weakness against broad signals (Efron 2010).

**v12, one null per scale and absorption class.** The class is a = (Σc)²/(T Σc²), the share of a contrast the fit's place level takes in.
- Every spike has a = 1/T, so spikes pool over the years. Each suffix start is its own class, so the step's null-world calibration is unchanged (1/10).
- **The spike-type methods find all five events again:**
  - yellow fever: SP 2018, 460×;
  - measles: Manaus 2018, 818×, p 8×10⁻⁴⁵;
  - chikungunya: BA 2017, 120×;
  - Brumadinho 2019: 4.1×;
  - COVID-19: Manaus 2020, 2.6×, p 9×10⁻⁵.
- **The multiscale step matches only chikungunya**, by a step in MA from 2022 (z 44): a later regime, not the 2016–17 epidemic. Matching a step to a spike event is a misreading either way. The criterion for step methods is to test the attributed start against the event's years.
