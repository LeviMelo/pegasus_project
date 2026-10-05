# Known positive: leptospirosis after the Rio Grande do Sul floods, May–July 2024 (2026-10-05)

**Regime:** SINAN LEPT through `gateway.monthly_counts` (month of first symptoms, municipality of residence), block fitted on 2010–2023 (contiguity; `data/fit_monthly.py`), 2024 scored by the prospective tier BP (`data/positive_lept.py`, artefacts `data/logs/positive_lept_{notification,case}.json`). Space-time lens: 30 nearest places, windows ≤ 4 months, 200 replicates. Commit: this entry's own.

**What exists.** The FTP holds `LEPTBR24.dbc` under `SINAN/DADOS/FINAIS` (final, modified 2026-07-15) and the open-data `LEPTBR24.csv.zip` (modified 2026-01-29); `LEPTBR25.dbc` is `PRELIM`. pegasus_data read the open-data CSV: **27,510 notifications for 2024** (26,884 allocated in the scored months; 4,054 confirmed cases of 4,178 in the file). The final DBC was not read, so its count against the CSV's is untested. Nothing was substituted: the positive is scored on 2024.

**The fit** (2010–2023, 236,362 notifications): φ = 0.80 (cases 0.62), national season ×1.9 (January–March peak, August trough). BP calibration on 2024: KS 0.014 (cases 0.005).

## Result

Rio Grande do Sul, observed against the BP forecast (notifications):

| month | RS observed | RS expected |
|---|---|---|
| Apr 2024 | 169 | 159 |
| **May** | **3,518** | **133** |
| **Jun** | **2,353** | **121** |
| **Jul** | **449** | **111** |
| Aug | 155 | 103 |

Rest of Brazil, May–July: 1,646 / 1,260 / 1,148 against 1,504 / 1,370 / 1,254: no excess. The flood signal is RS only.

- **Space-time lens, notifications:** the first finding is **18 RS municipalities, May–June 2024: 4,290 observed against 67.7 expected, rate ratio 62.9** (against the 1.2 minimum effect), p below 10⁻³⁰⁰ (the Gumbel null underflows); two further RS clusters in May–June (RR 14.8, 12.7), one in July (RR 13.2). All nine findings inside May–July lie wholly in RS.
- **Confirmed cases:** the same locus: 16 RS municipalities, May–June, 546 observed against 12.9 expected (RR 40.9); RS May 598 against 32, June 270 against 31.
- **The criterion (cell Jaccard ≥ 0.5 with RS × May–July) is not met as written:** 0.117 (cases 0.096). The findings cover 171 municipalities (107 in RS) of the 497, and the locus holds 1,491 cells, most with no excess. **The excess is captured:** the findings' cells inside the locus hold 5,697 of the locus's 5,954 excess notifications (95.7%; cases 818 of 859). For a sparse count outcome the Jaccard of cells measures how many empty cells the locus lists, not whether the lens found the event; I would score such positives by captured excess, and by the share of findings inside the locus (9 of 9 in May–July).
- **Other findings in 2024:** 20 upward findings in all (9 inside RS × May–July) and 8 downward. Of the others, the largest (windows in January–May, RR 5.6–37, none in RS) are in the North, Rio de Janeiro, Espírito Santo and São Paulo, against the 2023 baseline; the rest were not examined.

## What this shows

The BP tier plus the space-time lens recovers an event of a size no seasonal model would absorb (RR 63 over 18 municipalities), with the right place and months, at the municipality grain where φ = 0.8 makes single cells uninformative: the lens works because it sums cells.
