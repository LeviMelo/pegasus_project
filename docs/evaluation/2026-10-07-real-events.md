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
