# Location fields: one noise structure, null worlds, and the first declared positives (S1.1–S1.3)

**Regime.** Commits 1134e4e and the S1 commit after it; pegasus_data 0.1.0a1; contiguity graph; 2026-10-07/08.

**Null worlds of a measure** (`scripts/location_null.py SIH-RD hospitalisation X J09-J18 DIAS_PERM --worlds 20`, `data/probes/location_null/`). Each world draws the field from its own predictive with N1 and runs every B1 location method at relevance 0 and at `LOCATION_EFFECT`. Counted: worlds with any finding (the false-discovery rate under the complete null).

| method | before the lift fix | after |
|---|---|---|
| cell excess | 6 of 20 (every false finding at the immediate region, p = 0) | 0 of 20 |
| multiscale excess | 1 of 20 | — |
| step, trend | 0 of 20 | — |

- The cause: `surprise.lift` summed a location's cell means as if they were counts. A location's coarser unit is now the precision-weighted mean of its cells.
- On the observed field, cell excess then reports 434 departures (398 at the municipality, 35 at the region, 1 at the state).
- `LOCATION_EFFECT` changed no finding in any world. It is a relevance statement, not a calibration.

**The declared positives (S1.2)** (`harness.event_record` on the three Fundão declarations, committed before the run).

| declaration | cell excess | multiscale excess |
|---|---|---|
| gestation shorter in 2016 (SEMAGESTAC, down) | missed (680 findings elsewhere) | missed (146) |
| 32–36-week share up in 2016 (GESTACAO 4) | missed (1476) | missed (1020) |
| birth weight, the negative control | no finding at the locus | no finding at the locus |

At the locus (Mariana, Barra Longa, Rio Doce, Santa Cruz do Escalvado):
- **Gestation:** shorter by about 0.25 % on the log scale (about 0.7 days), pooled z −0.9 in 2016. Mariana alone has z −1.9 to −2.1 in each of 2015, 2016 and 2017.
- **Preterm share:** no rise in 2016 (pooled z −1.0).

The study's 1.86 days is a difference in differences over its own exposure set. At this locus the departure is several times smaller, and it lasts, so B1's place level absorbs part of it. **S1.2 is not met.** The next declarations need documented positives large enough to clear the search's multiplicity at their scale.

**Coverage (S1.3)** (`pegasus-core coverage`). Every column pegasus_data declares is either read by a field or carries a reason:

| system | columns | read | with a reason |
|---|---|---|---|
| SIH-RD | 127 | 98 | 29 |
| SIM.DO | 100 | 63 | 37 |
| SINASC-DN | 83 | 45 | 38 |
| SINAN-DENG | 196 | 39 | 157 |

The reasons that are gaps:
- missing codes not declared: 116 dengue columns. A five-year proposal was written, then reverted, because its codes are labelled in some years' codelists and not in others (2021: 7 unsupported codes; 2023: 49).
- code-tree marks no field reads (the cause on an admission, the requested procedure).
- a person's own places (birthplace) that no field reads.
