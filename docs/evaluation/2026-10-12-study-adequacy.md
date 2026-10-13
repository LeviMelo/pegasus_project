# A study folder's numbers, read for a paper (2026-10-12)

**Question (author).** Are the numbers in a study folder described and supplied so that a rigorous epidemiological
study can be made from them? Asked of the best folder then (`studies/toxoplasmosis_slice`, RS 2014–2023, deep, run at
d40e66a with uncommitted code), it was read table by table; `study.body` had passed it, checking presence only.

**Found (each a defect of meaning, not of scope).**
- The area's total written as "national, BR", identical to its state rows.
- Congenital toxoplasmosis rated on every notification: discarded and inconclusive included. Nationally in 2019,
  1,642 of 2,858 TOXC notifications are confirmed (CLASSI_FIN 1), and 6,346 of 8,436 TOXG (lake).
- P37.1 deaths per 100,000 person-years of everyone; the "standardised" column equal to the crude one.
- Codes unnamed: SIGTAP procedures, composition values (`CRITERIO 1`), and a term-matched code set summing a
  health-education activity (0101010222) with the antibody tests. In RS the education procedure holds no record
  (serology 598,897 in 2014–2023), so the slice's serology findings stand.
- No finding with an interval (0 of 203); groups as observed against expected with no proportion; persons as notes.
- No column described anywhere but the report's prose.

**Fixed.** The fixes and the checks `body` now makes are listed in ARCHITECTURE §3.4 (the analytic body). In pegasus_data,
SINAN-TOXC and TOXG declare a confirmed-case event (0d8437f).

**Read on the slice's new output** (`studies/slices/toxoplasmosis_deep_slice`, f880982; then f44fcdb).
RS, confirmed cases per 1,000 live births:
- gestational: 3.3 (3.0–3.7) in 2019, 3.8, 4.7, 6.1 and 6.3 (5.9–6.8) in 2023;
- congenital: 1.3 (1.1–1.5), 1.1, 1.7, 1.8 and 1.5 (1.3–1.8).

Notifications run 30–50 % above the confirmed cases in each year. Reading this output found three more defects, now
fixed:
- the persons cohort scanned notifications (257 in 2023), not the 186 confirmed cases;
- a Wald interval gave 0 of 257 deaths as [0, 0];
- that zero came from a link to SIM that was not viable, so no proportion should have been given.

**Cost.** Uncapped, at f880982: 32 min, of which products took 24.

| part | seconds |
|---|---|
| capture | 692 |
| persons | 242 |
| screen | 207 |
| fields' tables, figures, maps | 184 |
| groups | 56 |
| hypotheses | 44 |

Capture is national reads cut to the area, because DATASUS files a record by its place of care; it is now stored.

Three other defects made the earlier gate runs overrun:
- the products' labels read every year of SIM and SIH (20 min);
- the screen fitted 577 national blocks under the area;
- the estimate priced none of either.

**Gate.** `scripts/prelaunch.py`'s slice on `studies/slices/toxoplasmosis_deep.yml` (now reading TOXG too), f44fcdb, shared
store: 25.9 min against an estimate of 36.9, every part of the body met, the adequacy checks included; log
`data/probes/slice_toxo10.log`. The other presets' slices and the second condition are not yet run on this code.

**A known answer that failed, and why.** The leptospirosis slice (RS 2016–2024, deep, a5bc790's parent) declared
Porto Alegre's May 2024 floods. At B1 its notifications in 2024 were 2,119 against 1,309 expected, "not supported"
(Holm p 0.70): B1 is fitted on 2024 itself, so a statewide rise is absorbed by the year's effect. Against the
prospective alarm tier trained on 2016–2023 they are 2,119 against 311 (6.8×, 6.5–7.1), supported (Holm p 0.012); at the
place of notification 5.5×, supported. Confirmed cases at residence, 283 against 66 (4.3×), do not reach q under
Holm. Hypotheses now use BPA (ARCHITECTURE §7.7); at the annual grain a window of months is read as its whole year, and
the answer says so. The same slice found persons and capture writing nothing where the topic has no person link or
capture population; they now say why.
