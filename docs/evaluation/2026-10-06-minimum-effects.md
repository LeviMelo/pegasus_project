# Minimum effects θ0 re-made on the grid (O5)

**Regime.** Pegasus_core `design-v0` at 7f5f529 and after; 2010–2023 stored fits under ADR-0024; 2026-10-06.

**Runs and artefacts.**
- Model worlds: `pegasus-core grid --minimum-effects` (`data/queue_grid_calib.py`) → `data/probes/grid/calib_*.jsonl`, read by `data/read_grid_calib.py`.
- Real-structure negatives: `data/theta0_negatives.py` → `data/probes/grid/theta0_negatives_*.json`.

**Fields.**
- SIM I60-I69 (stroke, dense);
- SIM I00-I02 (rheumatic fever, sparse);
- SIH-RD J09-J18 (pneumonia admissions).

**What and why.** v0 set each lens's minimum effect θ0 by hand or on one field. It was 1.2 for the cell lenses and 1.5 for spatial cluster, and 1.5 / 1.2 / 1.2 for trend divergence by scale. ARCHITECTURE §10.5 re-makes θ0 as the smallest value whose null worlds keep false discoveries at or below q = 0.05. Two kinds of null are needed:
- **Model worlds:** NB from the fit, refitted, with no plant. Twenty per field.
- **Negatives that keep the real residuals' dependence:** Moran spectral randomisation in space, and a time shift. Twenty each, on normal scores so that a single real shock cell does not count. With raw scores, outbreak fired once in every time-shifted stroke world: one heavy-tailed cell carried along.

**Null worlds with any finding (of 20).**

| lens | model worlds, θ0 1.0 / 1.1 / 1.2 | space negatives | time negatives |
|---|---|---|---|
| outbreak | SIM 0 / 0 / 0; SIH 3 / 0 / 0 | 0 except SIH at 1.0 (1) | 0 |
| change point | 0 / 0 / 0 | 0 except SIH at 1.0 (1) | stroke 6 / 0 / 0; SIH 10 / 0 / 0; **rheumatic fever 13 / 12 / 12** |
| space-time | SIM 0 / 0 / 0; SIH 1 / 0 / 0 | stroke 2 / 0 / 0; SIH 4 / 0 / 0 | **rheumatic fever 18 / 18 / 18** |
| trend divergence (θ0 1.1 / 1.2 / 1.5) | 0 / 0 / 0 | 0 | **SIH 20 / 20 / 19, 50 / 26 / 4 findings per world** |
| spatial cluster (θ0 1.0 / 1.2 / 1.5 / 2.0) | stroke 20 / 2 / 0 / 0; rheumatic fever 3 / 1 / 0 / 0; SIH 20 / 20 / 20 / 0 | — | — |

**Power gained at the lower θ0** (stroke; planted loci of 100 or more expected deaths; share detected at θ = 2):

| lens | locus | θ0 1.2 | θ0 1.1 | θ0 1.0 |
|---|---|---|---|---|
| outbreak | place-year | 0.38 | 0.72 | 0.88 |
| outbreak | region-year | 0.32 | 0.50 | 0.82 |
| outbreak | state-year at θ = 1.5 | 0.00 | 0.25 | 0.75 |

The change point lens stays nearly blind at any θ0 (a place step ×3: 0.11 at 1.2, 0.42 at 1.0). Its tier is tested apart (`data/queue_grid_tiers.py`). Rheumatic fever detects nothing at θ = 2 at any locus: its power surface, not its θ0, is what the field says.

**Reading.**
- On model worlds and space negatives, θ0 = 1.1 holds on all three fields for outbreak, change point, space-time and trend divergence. Spatial cluster needs 1.5 on SIM and 2.0 on SIH, whose B0 holds the hospital-use geography of ADR-0018. Decided in ADR-0026.
- The time negatives that fail do so at every θ0, so no minimum effect is the cause:
  - change point and space-time on the sparse field;
  - trend divergence on SIH.

  Those fields carry slow, persistent place-level departures that the model does not hold, and they survive a time shift. That is misspecification, and a missing model term (the place × time interaction, O6's departure models) has to answer it, not a threshold.
- Until then, SIH trend-divergence leads have no calibrated false-discovery rate. That covers the 18,575 of the stored register, which predate the refits anyway.
