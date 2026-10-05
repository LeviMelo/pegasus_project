# Lead triage: the SIM survey's 7,496 leads by class, and what replicates (2026-10-05)

**Regime:**
- **Mechanism:** `scans/explain.triage` reads the lead's cells (counts of the field, its siblings, the ill-defined chapter, all causes, person-years); `Session.triage` builds the arrays and runs the replication; `pegasus-core triage SIM.DO death`. The class goes to `lead.robustness["triage"]`; artefacts become status `explained`.
- **Run:** `data/triage_survey.py SIM.DO death --write`, 467 fields, 24 min, register of 2026-10-05 (all R0 before). Readouts `data/triage_readout.py`, `data/triage_known.py`; logs `data/logs/triage_*.log`.
- **Rules (provisional constants in `explain.py`):** read in this order, the first that fires decides.
  1. *denominator*: a year with no death of any cause at 5,000+ person-years; an all-cause death rate (without the lead's own events) breaking by more than ×1.6 beyond the nation's, at 20,000+ person-years; person-years missing or jumping by ×1.25.
  2. *substitution*: the siblings under the field's parent move opposite and undo at least 75% of the change, at z ≥ 3 against their own year-to-year noise (robust sd of first differences).
  3. *system, certification*: the lead is chapter XVIII, or the ill-defined chapter moves opposite by the same rule.
  4. *system, recording*: the code's national level (median of its first and last three years) moves by more than ×3, unless the lead is a one- or two-year excess at which the nation peaks too; or a deficit against an expectation that learned a surge (a place's peak year ≥ 5 × its median).
  5. *system, coding practice*: a residual category ("outros", "não especificado" by the label's own words) trending, or with a different age–sex pattern.
  6. *noise*: fewer than 10 events from the expectation, or an effect within ×1.5 at under 30 events; a group pattern whose log-SIR sd is under 0.3 (the minimum effect is 0.2).
  7. otherwise *signal*: **unexplained by the data at hand, not confirmed.**
- **Replication (§8.3), a split of the evidence, not a refit:** B1 expectations of the all-years fit. R1: for a window lead the effect in the temporal half it does not touch; for a trend, the divergence from the neighbours in both halves. R2: both spatial halves of a subset's places (`control.spatial_halves`). Same sign, at least half the effect, one-sided NB p < 0.05 (`control.replicates`, `replication_tier`).

## Classes

| class | leads | trend | space–time | outbreak | change point | group |
|---|---|---|---|---|---|---|
| system | 4,045 (54%) | 2,662 | 745 | 125 | 11 | 502 |
| signal (unexplained) | 2,015 (27%) | 229 | 1,133 | 419 | 5 | 229 |
| substitution | 746 (10%) | 365 | 358 | 22 | 1 | 0 |
| noise | 690 (9%) | 99 | 53 | 195 | 11 | 332 |

- **System, by reason:** certification 3,001, recording 493, coding practice 390, denominator 103, expectation learned a surge 58. **XVIII is 2,599 leads: 2,462 system, 137 substitution (R98 → R99, R95–R99 siblings).**
- **By chapter (signal / all):** XX 600/1,291; X 372/818; IX 348/897; I 225/592; IV 99/343; II 86/331; V 66/110; VI 61/134. Chapter II is 36% noise (119/331); XX has the most signal because its events are discrete disasters, outbreaks and age–sex patterns.
- **Denominator:** the population series is smooth (no person-year break and no zero year in 5,570 places), so a created municipality shows only in the death series: 3 places with an empty year, 26 of 1,794 large places with a rate break above ×1.6. 103 leads sit on them.

## Read against the hand reading (the survey entry)

| lead | triage | verdict |
|---|---|---|
| Curitiba XVIII, R95–R99; Olindina R98 | system, certification | agrees |
| I46 Fortaleza 2010–13, J12 2010–17 (RR 0.01), I46 trend | system, recording (×5.5, ×8.2) | agrees |
| I63 / I64 in the stroke stories | substitution 17 of 50 (I63) and 22 of 39 (I64); 16 I63 leads stay signal, 14 noise | partly: where the other I60–I69 codes do not fall by the same amount in the same years, the substitution is not seen |
| J12 2020–21, Rio metro (752 vs 4; J18 −624) | substitution; the same in Maranhão, Pará, Roraima (J12 up, siblings flat): signal | agrees; COVID certified as J12 is a coding path, flagged only where J18 falls |
| A92 Fortaleza 2017, Brumadinho X36 2019, B34 Mossoró 2016, dengue 2015 | signal | agrees (each failed first versions of the rules: see below) |
| A48 Varginha 2017 (A48.3, one city's certification) | signal | **misses**: the 4-character subcode and the certifier are not in the block arrays |
| I46 Rio metro 2022–23 (I42 → I46) | signal | **misses**: the I42 decline is outside the parent group's z test |

- **Three first versions were wrong and were read out before the final run:** the siblings of X36 (heat and cold years) undid 61% of Brumadinho's rise by chance, so the share is 75% and z is against the siblings' own noise; A92 was "recording" because chikungunya emerged nationally, so a one- or two-year excess at which the nation peaks is an event; the death-rate break flagged Brumadinho because of the 133 deaths themselves, so the lead's own events are removed.
- **Not caught:** São Borja I21 (112 against 20 a year, ill-defined share 8.0% → 1.8%, siblings flat) stays signal, as in the earlier evaluations; and many trend and deficit signals are **one city's code collapsing to nearly zero** (Ribeirão Preto I50 56 → 2.5 a year, Mogi das Cruzes J69, Campo Grande chapter V 44 → 2, 23 places of Santa Catarina I80 2 against 132 expected): the data at hand do not separate a local coding change from a real change.

## Replication

- **R0 7,394 (98.6%), R1 79, R2 23, R3 none.** Signal: R0 1,982, R1 29, R2 4.
- **Temporal (R1):** 62 of 3,355 trend leads (both halves diverge the same way), 32 of 2,088 space–time, 8 of 761 outbreaks, 0 of 13 change points. R1 asks for recurrence, so **a one-off event fails it by construction**: Brumadinho, Fortaleza 2017, X00 (a building fire, 12 places, 2013), the Rio 2010 and Recife 2022 landslides (X36) all stay R0. For events the usable evidence is the other kind below.
- **Spatial (R2), 1,767 of 2,214 space–time subsets pass both halves, 930 of them signals.** This is **homogeneity of a cluster selected on the same data, not independent replication**; it separates a cluster of 12 places that all moved (X00, X36 Recife, J09 2016 in Mato Grosso do Sul and Paraná) from one place carrying it. Independent replication needs the confirmation reserve (half B, `confirm`) and a refit on the other years: **not done**.
- **Tier ladder:** R2 requires R1 in `replication_tier` (§8.3 as written), so those spatially homogeneous one-off events cannot reach R2. Open: report spatial homogeneity beside the tier, or reorder the ladder for one-off events.

## The top plausible signals, one line each (events, not group patterns)

Observed against expected from the lens; "base" is the median of the other years in the same places.

| # | lead | evidence |
|---|---|---|
| 1 | A92 Fortaleza 2017 | 159 against 14.3 (base 0); the nation peaks (1 → 130 a year); ill-defined share 3.8% against 4.0%; one-off (R1 no) |
| 2 | A92 Maracanaú, Caucaia and 13 more, 2017 | 210 against 16.1; both spatial halves; the same epidemic |
| 3 | A90–A99 Fortaleza 2017; Maranguape and 16 more | 184 against 29.9; 241 against 37.4 |
| 4 | X36 Brumadinho 2019 | 133 against 11.9 (base 0); 16-place cluster 231 against 15.8; siblings 1,126 against 1,266; spatial yes |
| 5 | X36 Magé, São Gonçalo, Niterói 2010 | 176 against 13.5 (base 0); ill share 9.3% against 7.4% |
| 6 | X36 Recife and Camaragibe 2022 | 106 against 6.7; 8 places; spatial yes |
| 7 | X00 São Gabriel, Cacequi and 10 more, 2013 | 202 against 14.9 (base 2); siblings flat; spatial yes |
| 8 | B34 Mossoró 2016 | 29 against 0.3 (base 1), all B34.9; ill share 8.7% against 3.3% |
| 9 | A90 Cosmópolis and 15 more, 2015 | 83 against 8.9; Marília 34 against 3.5; the dengue year of São Paulo's interior |
| 10 | J09 Rio Brilhante, Caarapó and 13 more, 2016 | 28 against 0.8; Dois Vizinhos 30 against 2.0; an influenza season |
| 11 | J12 Bacabeira (MA) and 24 more, 2020–21 | 522 against 67.9; J18-group siblings flat (616 against 573): COVID certified as viral pneumonia, not displaced from J18 |
| 12 | J98 São Paulo, 12 places, 2020 | 8,424 against 1,930 (base 292); J98 is "other respiratory disorders": a certification route for COVID |
| 13 | J16 Uruará, Altamira and 18 more, 2017–19 | 263 against 47.9; ill-defined share 10.5%; unclear |
| 14 | I21 São Borja (trend) | 112 against 20 a year; ill share 8.0% → 1.8% (a part, not the whole); R0 |
| 15 | V49 and I80, Ceará and Santa Catarina, 2020–23 (deficits) | 17 against 324 and 2 against 132; a local code collapse; national levels flat |

Items 1–10 are what the survey should find; they carry no tier above R0 for the reason above. 11–15 are **unexplained, and 12 and 15 probably recording**.

## Consequences

- The register now says which of 7,496 leads to read: **2,015 signals** (1,133 space–time, 419 outbreaks, 229 trends, 229 patterns, 5 change points), of which the discrete events (items 1–10) are the ones with an external reading.
- Open: subcode and certifier concentration (A48 Varginha), a test for a code collapsing in one place against its chapter, an independent replication through the reserve, and the group-disparity effect (the "worst group", survey defect 1), which the triage replaces by the sd of log SIR.

## Facility class (2026-10-05, HEAD 8584d6a)

**Rule, run:** `explain.triage` step 7 (ARCHITECTURE §7.7); cubes by residence x facility x code x year, SIM.DO and SIH-RD 2010-2023 (`facility.py`); `data/facility_triage.py DATASET EVENT` (no `--write`: the register is unchanged), JSON `data/logs/facility_triage_<DATASET>.json`, readouts `data/facility_readout.py`, `data/facility_chapters.py`. SIM names a facility for 71-73 % of deaths, SIH for every admission. "Before" is the same run's signal plus facility (the rule only takes from signal); the stored classes drifted from a fresh run by 1,100 SIH leads (714 signal and 329 noise now *system*: other rules changed since the survey), so the stored counts are not the baseline.

| register | leads | signal before | facility | signal after | system / substitution / noise |
|---|---|---|---|---|---|
| SIM.DO (467 fields) | 7,496 | 2,015 | 84 (4.2 % of signals) | 1,931 | 4,045 / 746 / 690 |
| SIH-RD chapter X (67 fields, 21 min) | 22,628 | 9,469 | 3,219 (34 %) | 6,250 | 8,242 / 2,142 / 2,775 |

- **SIM by chapter (facility / signal before):** X 31/372, I 15/225, XX 13/600, IX 13/348, VI 7/61, XVI 2/23, IV, XV, XVII 1 each. 41 space-time, 29 outbreak, 14 trend; 46 by catchment, 38 by volume. Examples: A48 Varginha 2017 (3 facilities, 85 %, other places' residents z 6.7); J12 Itaperuna region 2020-21 (one facility, 84 % against 12 % of the block).
- **SIH by estimand:** 3,030 trends, 116 outbreaks, 71 space-time, 2 change points; **2,488 by a volume step** (opened, closed, entered or left the data; for example São Gonçalo/RJ, two CNES codes from 9,023 a year to 0) and 731 by catchment; 1,273 have the facilities as the place's sole provider (>= 85 % of its base events). The trends are CNES churn in small municipalities: the rule fires on a third of the SIH signals and is a statement about the hospital register, not about disease.
- **Not decided by the rule:** 1,301 leads concentrated but place-specific stay signal. **The 15 strongest trend and event signals left** (Miguel Alves/PI J45, Alegrete/RS J15 3 to 232 admissions a year, Coribe/BA J00-J06, Olindina/BA, Igaporã/BA J12 118 to 0, Ipixuna do Pará J96, São Félix do Xingu/PA J40-J47, among them) are **one hospital carrying 95-100 % of the change with a stable volume** and no residents of other places to test it against (fewer than 30 events): facility and place coincide in a sole-provider municipality, and the data cannot separate the hospital's coding from the place. They stay signals; the next check is the neighbouring municipalities' own hospital. All 15 leads of highest raw rank are group patterns (sd of log SIR across age-sex groups), which have no change direction and so no facility read; they are not ranked against events.

**J31 in the Rio Doce valley, 2015 (lead `fa41cad3c98d27c4`, 27 municipalities; facility shares only).** Class *facility*. In 2015 the 27 places had 255 J31 admissions (0 to 8 a year in the other years, 8 in 2014); **one hospital, CNES 2118629 (Governador Valadares), recorded all 255 (share of the change 1.00; 2.7 % of the block's base events)**, from residents of all 27 places (Governador Valadares itself 136, others 6 to 10 each). The same hospital recorded 398 of Brazil's 544 J31 admissions in 2015 (66 facilities with any; next 15), from residents of 70 places, against 21 in 2014 and 1 in 2016; its J31 share of the chapter went 0.9 % to 20 % (inside) and 3.2 % to 17 % (residents of other places, z 5.7), and its volume rose 1,439 to 4,050 a year without the J31 events (6,767 admissions in 2015, 3,754 in 2014, 1,984 in 2016). So the burst is one hospital's, across places and residents alike, not spread over facilities; the facility class does not say whether that hospital coded differently or served a real event.
