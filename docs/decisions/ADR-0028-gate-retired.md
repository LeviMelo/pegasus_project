# ADR-0028: The gate is retired: every field is scanned, and every lead carries its method's record

**Date.** 2026-10-06. **Status.** Active. O5 step 5. Supersedes ADR-0022's lens admission (its pair rules stand) and v0's survey gate (`SURVEY_PLAN`'s passing and failing combinations, `Lead.gate`).

**Evidence.**
- ARCHITECTURE §8.4 and §10.5 (revision 2).
- The grid of ADR-0026/0027, which measured each lens's calibration field by field.
- The survey smoke test on SIM VII 2010–2023: 27 fields (the gate had admitted far fewer), 46 s on 4 workers, 19 leads with their records; old register rows load with their v0 gate inside the record.
- On chapter IX: 88 fields, 76 with at least 10 deaths, against 44 admitted, at about 7 s a field through every lens.

## Decision

1. **Every field with an event is scanned** (`Session.fields`). A lens's BH runs within each field's run, and the survey's families pool findings, so a weak field dilutes no other. Its cost is compute: roughly twice the gate's on IX.
2. **Every combination of `SURVEY_PLAN` runs.** v0 ran the "failing" ones only on request (`--ungated`); that flag is gone.
3. **Every lead carries `method`**:
   - its tier and minimum effect;
   - whether its false-discovery rate is calibrated where it ran;
   - the evidence (`tools.method_record`, `METHOD_EVIDENCE`).

   Uncalibrated today:
   - trend divergence on SIH (time negatives fail at every θ0, ADR-0026);
   - the neighbours estimand (no documented positive recovered);
   - group disparity (fails its spatial negatives).

   Their leads are kept and ranked after the others. Nothing is silenced.
4. **What is removed:**
   - the admission machinery (`fields.admission`, its curves, `admission_curves.json`, `measure_admission.py`);
   - the v0 gate (`harness.power_curve`, `region_power`, `trend_power`, `cell_power`, `group_power`, `harness_gate.py`, `tools.gate_status`);
   - the MCP tool `gate_status`, which becomes `method_status`. The MCP server stays paused (OPEN_QUESTIONS 4); only the retired tool's name changed.

## Amendment (2026-10-06): the outbreak lens weights its cells

The outbreak lens's BH is weighted by default (`outbreak(weighted=True)`). Each cell's Roeder–Wasserman weight comes from its standardised effect at a rate ratio of 1.5, from its own μ and dispersion. On the grid (3 worlds and 10 null worlds per field), the null worlds stayed clean and the detections rose by 0.01–0.03:

| field | place-year doublings | region-year doublings | place-year triplings |
|---|---|---|---|
| stroke | 0.48 → 0.51 | 0.59 → 0.62 | 0.94 → 0.95 |
| SIH pneumonia | 0.16 → 0.18 | 0.70 → 0.70 | 0.72 → 0.74 |

## Limits

- The weights of §8.4 act in the outbreak lens only. Across fields, and in the other lenses, whose hypotheses are units and windows, they are not applied.
- The method records hold what the grid has measured: three SIM/SIH fields annual, with SINASC and SINAN running. A lens on a system not yet gridded carries the default record.
