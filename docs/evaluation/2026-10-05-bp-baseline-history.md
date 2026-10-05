# The outbreak-robust BP baseline, measured on dengue 2019–2023 (2026-10-05)

**Regime:** `data/dengue_baseline.py` (artefact `data/logs/dengue_baseline.json`): SINAN-DENG probable cases, monthly, block fitted on 2010–2018 (contiguity), 2019–23 scored by BP under four forecasts of the history h (`monolith.extrapolate`), then the state-level outbreak lens with the state-month φ_extra of the 2010–14 lens run (3.63). Truth: the 64 state-years of 27 states with incidence ≥ 300 per 100,000. Closes ADR-0004 item 2.

| history of h | flagged state-years | recall (≥ 300) | precision | recall (≥ 150) | state-month KS | municipal KS | expected 2019–23 (observed 6.08 M) |
|---|---|---|---|---|---|---|---|
| level (last 12 months, the old default) | 103 | 0.922 | 0.573 | 0.871 | 0.471 | 0.310 | 1.69 M |
| **level36 (last 36 months)** | 91 | **0.906** | **0.637** | 0.817 | 0.392 | 0.290 | 2.14 M |
| median of the whole fit | 73 | 0.812 | 0.712 | 0.656 | 0.255 | 0.242 | 3.38 M |
| robust (Farrington-style reweighting) | 73 | 0.812 | 0.712 | 0.656 | 0.256 | 0.243 | 3.38 M |

- **Robust and median give the same answer.** Past epidemic months get weight 1/r², so the iterated mean lands on the median (expected 3.376 M against 3.384 M). A longer memory by itself (level36) raises precision by 6.4 points for 1.6 points of recall (six epidemic state-years missed against five).
- **Why robust loses recall:** it forecasts the endemic level, which in 2010–18 is high for the states that had a big epidemic in the fit (2013, 2015–16). The 12 epidemic state-years it misses include Goiás 2019 (incidence 1,720), Mato Grosso do Sul 2023 (1,571), Goiás 2020 (885), Mato Grosso and São Paulo 2023 (756, 734). The 2019–23 epidemic years come after an epidemic the model has been told to treat as an outlier, so the baseline is already high where the next one lands.
- **The precision figure is a lower bound.** The 21 state-years flagged by the robust baseline and not epidemic (≥ 300) include incidences 212–267 (Pernambuco 2020, Roraima and Sergipe 2019, Piauí 2019, Alagoas and Santa Catarina 2021) at 4–45 times the expected: surges above a tiny baseline that the fixed 300 threshold does not count as epidemics. Precision against incidence ≥ 150 is higher; it was not recomputed here.
- **Calibration** improves monotonically with the baseline (state-month KS 0.47 -> 0.26), as it must: a higher baseline puts more of the 2019–23 mass in the body of the predictive. This is not evidence that robust is the better alarm.

## Decision

The monthly default of BP is **level36**: it keeps recall (0.92 -> 0.91) and raises precision (0.57 -> 0.64), F1 0.707 -> 0.748. The robust form is available (`history="robust"`), and is the choice when false alarms cost more than a missed state epidemic (F1 0.759, the same as level36 within noise). The tuning rests on one disease and one 2019–23 period; the leptospirosis and microcephaly positives use the new default, and BP on another family should be checked against its own truth before the history is trusted. ARCHITECTURE §13 row 6.1 and `monolith.extrapolate` are updated.
