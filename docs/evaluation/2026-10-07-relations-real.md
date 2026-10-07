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
