# O7 on real fields: the first relation map

**Regime.** pegasus_core `design-v0`, the commit carrying this entry. 65 group-level fields with at least 2,000 events, 2010–2023, B1 expectations:
- SIM chapters I, IX and X;
- SIH chapters I and X;
- SINASC, all births;
- SINAN SIFC.

The pipeline is `relations.innovations` → `bands` (9 graph-frequency bands) → `lagged` (0–2) → `factor_model` (K ≤ 16, ARD) → `relation_table`, with one BH at q = 0.05 over 93,600 pair × lag × band tests. Scripts `data/o7_real_relations.py` and `data/o7_real_relations_supply.py`; artifacts `data/probes/o7_real_relations.json` and `o7_real_relations_supply.json`. Each run takes 82 s on the CPU.

**Why these counts.** First, what is reported and in which families. Then a competing explanation tested for the largest family, declared before the second run.

| run | reported | SIH ↔ SIH | across systems |
|---|---|---|---|
| B1 | 128 | 113 | 15 |
| B1 with SIH's supply term | 82 | 67 | 15 |

**Across systems: known positive controls, found.**
- Dengue deaths with dengue admissions (A90–A99): about 49-place scale, ρ 0.35, z 15.
- HIV deaths with HIV admissions (B20–B24).
- Pneumonia deaths with pneumonia admissions (J09–J18), and COPD/asthma deaths with admissions (J40–J47).
- Congenital-syphilis notifications (SIFC) with syphilis admissions (A50–A64).
- SIM respiratory deaths with SIH diarrhoeal and other-infection admissions remain to be read.

**Within SIH: a family of local, simultaneous co-movements.** Diarrhoea, pneumonia, COPD, upper-respiratory and other-infection admissions move together at 5–50-place scales, at lag 0. The rival explanation is that a hospital's supply or billing shifts move all its groups at once. It explains 41 % of the family (113 → 67). The rest is an open stage-E question: residual supply the term does not hold, shared coding practice, or shared local epidemics.

The relations are statistical (P16), and none is yet interpreted.

## The negative control: SIH's places permuted (later the same night)

**Regime.**
- The same 65 fields and pipeline, on N1 surprise cache 12.
- Script `data/o7_relations_control.py`, declared before the first run and revised between runs as noted in its docstring.
- Logs `data/logs/o7_relations_control{,2,3,4}.out`; artifacts `data/probes/o7_relations_control{,_sample,_merged}.json`.
- One fixed permutation of the places is applied to every SIH field, so every SIH × other-system relation is false while SIH's own structure is kept.

**Criterion.** False cross-system relations at most q = 5 % of everything reported.

| run | observed: reported, SIH cross | permuted: reported, SIH cross | permuted, bands above λ 0.002: SIH-cross share |
|---|---|---|---|
| factor model z (as published above) | 185, 17 | 691, 46 (42 in the national band) | 4/203 = **2.0 %** |
| sample correlation, Dutilleul n_eff | 2,285, 863 | 1,717, 409 | 91/737 = 12 % |
| factor model, low bands merged to ≥ 195 cells | 466, 150 | 1,523, 383 (377 in the merged low band) | 6/226 = 2.7 % |

**What it shows.**
- **Above the national scale the factor model's relations are calibrated**: 2.0 % false cross-system relations under permutation.
- **The national band is not.** It has 5 eigenvectors × 12 periods, 60 cells against 195 lagged fields, so the factor model is not identified there. Its z (ρ√n) treats a fitted implied correlation as a sample one: 42 false cross-system relations against 1 observed.
- **Merging the low bands to n ≥ p makes it worse.** A factor model needs far more cells than variables.
- **A direct test fails everywhere.** The band coefficients are not white in time, and the factor model's shrinkage is what kept the other bands calibrated. The direct test was removed.
- **The permutation is no null for the national band in any case.** It keeps every field's national course.

**Adopted.**
- A band with fewer cells than lagged fields is not fitted, and is logged as unanswered (`relations.bands`, `min_cells`).
- The relations of national and macro-regional scales are OPEN_QUESTIONS 9, with the method they need: national series at degrees of freedom ~ T, under a null that breaks the national course.
- The first map's 12 national-band relations are withdrawn. Its 173 others stand, with this record.
