# Replication by event sides: the null check, the shared fit, and what S2iD says (2026-10-05)

**Regime:** `control.event_sides` (A 50 / B 30 / R 20), `replication.py`, `corroborate.py`, commit of this entry; SIM.DO death 2010–2023, contiguity graph; `data/measure_fit_sharing.py` (XV), `replication.control_inflation` (simulation, seed `split-null-v1`), S2iD (46,489 events, 2010–2024, `pegasus_data` field `disasters`). The register re-tiering and the reserve demonstration are **not run yet** (see the end).

## What was counted, and why it matters

- **Does a test on a held-out half of the events replicate under the model's own null?** 400,000 simulated cells per row, NB(μ, n), events dealt 50/30 to A and B, cells selected on A at p < 0.001 against A's expectation, tested on B at 0.05. Nominal 0.05. This is the rate at which an A-selected chance cell would be called "replicated".

| μ (all events) | n (NB size) | marginal test on B | conditional on A's count |
|---|---|---|---|
| 5 / 100 | ∞ (Poisson) | 0.03 / 0.06 | same |
| 20 | 100 | 0.10 | 0.04 |
| 100 | 100 | 0.28 | 0.04 |
| 100 | 10 | 0.97 | 0.05 |
| 20 | 3 | 0.94 | 0.05 |
| 5 | 1 | 0.91 | 0.04 |
| 500 | 10 | 1.00 | 0.06 |

The sides share a cell's rate, and the model counts its extra-Poisson variation as noise, so an excursion selected on A shows in B. **A marginal test on B calls nearly every null cell replicated once μ exceeds n.** The conditional test (the rate's gamma posterior given A's count) holds 0.02 to 0.06 on the whole grid (25 rows, 130–430 selected cells each). It is the test used (ADR-0007); its price is power where the extra-Poisson part dominates.

- **Does fitting on all the events leak into a side's expectation?** Block XV (obstetric deaths, 26,696 events) refitted on side A alone (1,215 s under load; 114 s alone): the A-fit's total equals the side's events (13,277, the score equation) and 0.5 × the all-events fit within 0.5% (13,277 vs 13,349); in each field's 200 largest-|z| cells the all-events expectation is 0.2% to 8% above the A-fit's (median ratio 1.00 to 1.08), cell-wise relative differences 7 to 14% (the half-data fit is noisier). The all-events fit absorbs a little of a cell's own events, so a shared-fit test is slightly conservative for an upward lead. Not measured on a block with discrete disasters (XX refit queued: `data/logs/splitfit_XX.log`); the default is the shared fit, `split-fit` the A-only refit.

- **What does S2iD say about the one-off events?** Looked up directly in the cached registry (46,489 events):
  - **Rio 2010 (X36): corroborated in kind** — Niterói (330330) 48 deaths and São Gonçalo (330490) 16 deaths in "Movimento de Massa", 2010.
  - **Brumadinho 2019 (X36): not in S2iD.** Municipality 310900 has events in 2012, 2016, 2018 (an infectious-disease emergency), 2020–23, none in 2019; the registry holds 6 dam-collapse records in 2019 and none in Brumadinho. The expected corroboration by S2iD will not be found: the registry omits the event the deaths record.
  - **X00 Rio Grande do Sul 2013** (the Santa Maria nightclub fire; victims' residences): S2iD has no urban-fire typology, only wildfire, and the fire was in one municipality while the deaths are by residence in a dozen: not corroborable by this field.
  - Fortaleza A92 2017 depends on SINAN chikungunya (not published before 2015; cache warm queued, `data/logs/warm_chik.log`).

## Aggregate-scale trend leads on side B

The survey's region/state leads (trend against the national course) were `untested` in replication. `replication.test_trend_unit` tests them on B: the unit's places as one NB series, the slope refitted on B's events, one-sided against the scale's minimum divergence, **conditional on A** (each cell's boundary course becomes its expectation given A's count; ADR-0007). Check (`data/null_aggregate.py`, logs `data/logs/null_aggregate_sel*.log`): a unit of 20 cells x 14 years, A selects at p < 0.5 against the boundary (to have a null population), 400 draws each; share of selected units called replicated on B at 0.05, true course exactly at the boundary (+delta, -delta):

| cell mean, NB size | conditional | marginal |
|---|---|---|
| 100, 10 | 0.037, 0.021 | 0.032, 0.042 |
| 100, Poisson | 0.026, 0.026 | 0.026, 0.026 |
| 1000, 10 | 0.036, 0.026 | 0.067, 0.041 |
| 1000, Poisson | 0.030, 0.030 | 0.030, 0.030 |

Power, true course 3 delta (A selects at 0.05): conditional 1.00 for Poisson cells, 0.21 (mean 100) and 0.07 (mean 1000) for size 10; marginal 1.00. Conditioning on A's yearly counts leaves little for B to add when the cells' NB size is small at high counts, the price the cells' test pays too. The marginal is valid in this simulation only because the cells' extra-Poisson noise is drawn independently per year; a rate that drifts persistently would inflate it, so the conditional test is the one used.

The run on a real block (SIM.DO death 2010-2023, chapter III: survey on A in a scratch register, `split_confirm`, `data/replicate_aggregate.py`, output `data/perf/out/replicate_aggregate_III.json`, log `data/logs/replicate_aggregate.log`) was queued behind the heavy slots and had not been admitted when this was written; its counts are to be added here. Also found: the top-15 run (`data/logs/top15.log`) died at the SIH step (a `Decimal` in the arrow rows, fixed in `corroborate.py`) before the reserve step; the LOND stream is unspent (`Reserve.state()` = (0, 0)), so the run is still to be made once.

## Not run

State at 11:06 on 2026-10-05, still on the heavy queue or running: the survey on side A (`pegasus-core split-survey SIM.DO death`, admitted 09:19, at the C-chapter codes, `leads_A` not yet written), the tier counts of the 7,496 leads (`data/replicate_register.py --write`, needs the survey), and the 15 signals (`data/top15.py`, admitted 10:02, waiting on the SINAN-CHIK 2015-2023 fetch shared with the warm job). Finished: SIH odd years (side B warm), the side-A refit of block XX (3,774 s; its comparison with the shared fit, `data/measure_fit_sharing.py XX`, is queued). The 15 signals were selected on all the events, R included, so that run shows the mechanism and LOND consumption, not an independent confirmation. The tier counts, the 15 signals and the reserve table belong here when they exist; the handoff (`data/handoffs/replication.md`) lists the commands.
