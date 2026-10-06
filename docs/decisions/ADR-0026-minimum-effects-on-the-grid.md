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

## Amendment (2026-10-06, breadth): SINASC and SINAN

SINASC births and SINAN congenital syphilis (SIFC) were run on the same checks: 10 model worlds each, with planted spikes and steps (`data/queue_grid_breadth.py` → `data/probes/grid/breadth_*.json`), and the space and time negatives (`data/theta0_negatives.py`). Every value lives in one table, `lenses.MINIMUM_EFFECT_BY`, keyed by lens and dataset prefix; the default is 1.1.

| lens | SINASC | SINAN (SIFC) |
|---|---|---|
| outbreak, change point | 1.1 holds | 1.1 holds |
| space-time | 1.1 holds | **1.5** (time negatives 17/20 at 1.1, 4/20 at 1.2, 0/20 at 1.5) |
| trend divergence | **1.5** (time negatives 13/20 at 1.1, 0/20 at 1.5) | **2.0** (10/20 at 1.1, 3/20 at 1.5, 0/20 at 2.0) |
| spatial cluster | 1.5 holds | **2.0** (model worlds 10/10 at 1.5, 0/10 at 2.0) |

On these systems the time negatives fall as θ0 rises, unlike SIH's trends, so a minimum effect calibrates them. Notification practice and birth registration move over time more than the model holds.

What the grid says of power on births: outbreak finds 0.48 of place-year doublings and 0.93 of region-year doublings; change point (ADR-0027) finds 0.59 of place step doublings. SIFC's loci are small, a median of one expected case, and nothing is found even at ×3 on 68 expected cases. That is the field's power, read from its surface, not a defect: the refitted worlds show the planted excess.

The SINAN values rest on one notifiable disease and are applied to every SINAN dataset until others are gridded.

## Amendment (2026-10-06, relevance): θ0 is the larger of a relevance floor and the calibrated floor

ARCHITECTURE §8.4 makes the minimum effect a statement of relevance, not of detectability. Item 2's rule took the smallest calibrated value only. For trend divergence that gave 1.1 over the period: a 10 % divergence across fourteen years, about 0.7 % a year. The first v1 survey (`data/survey_v1_sim.py`) showed what that does: chapter IX produced 5,130 leads, of which 3,257 were trend divergences, and IV produced 2,340, of which 1,560 were.

The trend's relevance floors are v0's, kept for their own reason: 1.5 over the period at the municipality, 1.2 at region and state. The cell lenses keep 1.1, because a 10 % excess in one place-year or window is worth reporting and is where the grid's power gain lies. A lens's θ0 is now max(relevance floor, system floor) (`lenses.minimum_effect`).

## Limits

- Three fields, annual grain. SINASC, SINAN, the monthly grain and the mark lenses keep their v0 values until their grids run.
- ADR-0022's admission curves were measured at the old θ0. A lower θ0 only raises power, so the curves now admit fewer fields than they should, until O5's weights replace admission.
- The group disparity sd stays at 0.2: none of these grids planted group shapes.
