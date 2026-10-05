# Known positive: arbovirus notifications and microcephaly births, Northeast 2015–16 (2026-10-05)

**Regime:** `data/positive_ew_microcephaly.py` (artefact `data/logs/positive_ew_microcephaly.json`; the first run, without the 2015-only variant, is `…_run1.json`). Tier BP, models fitted on 2010–14 (SINAN-DENG probable cases, monthly; SINASC births by month of birth, block XVII, `CODANOMAL` code list; contiguity), 2015–17 scored against the forecast (history level36, ADR-0004 default). Surprises lifted from municipalities to immediate regions (510 units, 154 in the Northeast) with a unit-month variance component by ML (dengue φ_extra 2.8). E_w (`scans/pairs.py`, within places) at lags 0–12 months, minimum effect δ = 0.05. Control outcome: Down syndrome (Q90).

**The signal.** Zika became notifiable in 2016, after the microcephaly peak, so it cannot lead the outcome; its file does hold 2015 notifications in the Northeast (24 in January, 1,263 in April, 10,790 in July, retrospective probable cases), but the national notification regime was set up in 2016, so they are not a surveillance series. The arbovirus signal is therefore **dengue probable cases** (the dengue-like illness that carried the 2015 Northeast Zika epidemic), with chikungunya and Zika tabulated beside it. **This measures arbovirus transmission in general, not Zika**: a dengue or chikungunya epidemic with no Zika in it looks the same to this test.

## Result

**The positive is present in the Northeast series.** Q02 births in the Northeast: **2,371 in 2015–16 against 94 expected** (25×); nationwide 4,595 against 510 in 2015–17. The outcome and the control behave as they should: Q90 stays at its forecast (3,126 observed, 2,867 expected nationally).

| Northeast, monthly | Mar 2015 | May 2015 | Sep 2015 | Oct 2015 | Dec 2015 | Mar 2016 |
|---|---|---|---|---|---|---|
| dengue probable, observed / expected | 44,882 / 24,835 | 54,065 / 19,504 (peak excess +34.6 k) | 9,995 / 2,499 | 10,964 / 2,577 | 25,257 / 4,373 | 72,529 / 24,940 |
| Q02 births, observed / expected | 5 / 4.3 | 9 / 4.2 | 50 / 3.9 | 197 / 3.7 | 510 / 3.5 | 159 / 4.3 |

Dengue-like excess starts in March 2015 and peaks in May; Q02 starts in September–October and peaks in December: **6–7 months from onset to onset, 7 months peak to peak**, inside the 6–9 month window. This is a reading of two curves, not a test.

**The E_w test does not recover it.** Dengue → Q02 surprise correlation, Northeast units:

| lag (months) | 0 | 2 | 4 | 6 | 7 | 8 | 9 | 12 |
|---|---|---|---|---|---|---|---|---|
| ρ, 2015–17 | 0.123 | 0.120 | 0.123 | 0.115 | 0.098 | 0.067 | 0.027 | −0.037 |
| ρ, signal 2015 only | 0.104 | 0.110 | 0.119 | 0.116 | 0.091 | 0.051 | 0.000 | −0.062 |
| ρ, Q90 control, 2015–17 | −0.010 | 0.010 | 0.029 | 0.004 | 0.000 | 0.004 | −0.004 | −0.002 |

n_eff is 60–100 on the Northeast units. **No lag is admitted** (p 0.42–0.80 against δ = 0.05 for lags 0–9), and the profile is a plateau over lags 0–6 (falling after 7), not a peak at 6–9. Over all 510 units ρ is 0.04–0.06 with the same shape. The control is flat at zero, so what the Northeast dengue and Q02 surprises share is real but not lag-specific; removing the 2016 dengue and chikungunya epidemics from the signal (variant "signal 2015 only") changes nothing.

## Why, and what it shows

- **The unit-month grain cannot see a lag in a rare outcome.** The expected Q02 count is 0.03 per unit-month; the surprise z of most cells is noise, and the correlation is carried by a few Pernambuco, Paraíba and Bahia units. The timing reading above is on the Northeast total, where the counts are large.
- **The plateau at lags 0–6 is shared slow variation**: in a 36-month series with one wave in each variable, any lag within the wave's width correlates; E_w, which corrects for autocorrelation through n_eff, finds nothing beyond that.
- **The proxy is partial.** The large 2016 dengue and chikungunya epidemics (Feb–Mar 2016) were not followed by microcephaly (Q02 16–29 per month in August–November 2016 against 3.9 expected), so arboviral transmission as such is not the cause; Zika specifically, with the 2015 epidemic's immunity behind it, is. With the Zika file starting in 2016, that distinction is outside what this data can resolve.
- **Verdict.** BP recovers the outcome (25×) and the proxy's 2015 surge; the lagged E_w at the immediate-region grain does **not** recover the link at the 6–9 month window. I would not count it as a positive of the pairs layer. A test that sums over the Northeast before correlating, or tests the outcome's surprise against the lagged signal at one coarse geographic grain, is the way to a recovery; the ecological timing above is consistent with a first-trimester infection, but it is two curves, not an estimate.
