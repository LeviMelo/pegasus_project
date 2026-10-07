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
