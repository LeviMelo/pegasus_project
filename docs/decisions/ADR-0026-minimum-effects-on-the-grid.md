# ADR-0026: The lenses' minimum effects re-made on the grid

**Date.** 2026-10-06. **Status.** Active. Replaces v0's hand-set θ0 (ADR-0005's 1.2; the harness gate's 1.5 for spatial cluster and 1.5 for municipal trends). This is O5 step 3, for the count lenses on annual fields.

**Evidence.** `docs/evaluation/2026-10-06-minimum-effects.md`, on SIM I60-I69, SIM I00-I02 and SIH-RD J09-J18, with two kinds of null:
- refitted model worlds (`harness.grid`, 20 per field);
- negatives that keep the real residuals' dependence: space-scrambled and time-shifted normal scores, 20 each.

## Decision

1. **The rule.** A lens's θ0 is the smallest value at which, on every calibrated field, the model worlds and the space negatives keep the share of worlds with any finding at or below q = 0.05.
2. **The values.**

   | lens | θ0 | was |
   |---|---|---|
   | outbreak, change point, space-time | 1.1 | 1.2 |
   | trend divergence, every scale | 1.1 | 1.5 municipal, 1.2 coarser |
   | spatial cluster, SIM | 1.5 | 1.5 |
   | spatial cluster, SIH-RD | 2.0 | 1.5 (its B0 holds SIH's hospital-use geography, ADR-0018) |

   Outbreak at 1.0 fails SIH's model worlds (3/20) and space negatives (1/20), so 1.1 is the floor. The gain at 1.1 on stroke: outbreak detects 0.72 of place-year doublings (0.38 at 1.2) and 0.50 of region-year doublings (0.32).
3. **Time-shift negatives that fail at every θ0 are not a minimum-effect question.** Where they fail, the field carries persistent place-level departures that the model does not hold, and no threshold removes them:
   - change point and space-time on sparse SIM I00-I02 (12–18 of 20 worlds at any θ0);
   - trend divergence on SIH-RD (20 of 20 even at 1.5).

   Leads of those lenses on such fields have no calibrated false-discovery rate. A model term has to answer this (the place × time interaction, O6's departure models), not a threshold.

## Limits

- Three fields, annual grain. SINASC, SINAN, the monthly grain and the mark lenses keep their v0 values until their grids run.
- ADR-0022's admission curves were measured at the old θ0. A lower θ0 only raises power, so the curves now admit fewer fields than they should, until O5's weights replace admission.
- The group disparity sd stays at 0.2: none of these grids planted group shapes.
