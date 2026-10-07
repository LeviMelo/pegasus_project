# ADR-0029: Architecture revision 3 — six stages, one computation each

**Date.** 2026-10-06. **Status.** Active. Revises ARCHITECTURE (§1.1, P16, §6.1, §7.0, §7.5, §8.4, §10, §12). Marks ADR-0026 and ADR-0027 for supersession as N1 and O6 land.

**Evidence and reasoning.** `docs/discussion/2026-10-06-course-correction.md` (the review), written after the author's critique of that day's work:
- detectors are general and system-agnostic;
- statistical validity is not epidemiological validity;
- relations are a joint, systematic problem;
- the architecture had fused scientifically different computations.

## Measurements behind it

- **Residual lag-1 autocorrelation within places** under the B1 predictive (`data/residual_autocorr.py`, `data/probes/residual_autocorr.json`):

  | field | autocorrelation |
  |---|---|
  | stroke deaths | 0.03 |
  | ill-defined causes | 0.23 |
  | births | 0.27 |
  | congenital syphilis | 0.11 |
  | SIH pneumonia | 0.39 |

  The fields whose time-shifted negatives failed are the serially correlated ones. The exception is the sparse field, where the normal-score negative itself manufactures spikes.
- B2 as a detection reference took in what it was testing: a place step ×3 found 0.11 of the time against B2, and 0.95 against B1 (evaluation 2026-10-06, minimum effects).
- The first v1 survey (41,700 leads, trend divergence the bulk) showed lead volume being managed by moving test thresholds, which is a stage-F question.

## Decision

1. **PegaSUS is six stages, one computation each** (ARCHITECTURE §1.1):
   - A data and meaning;
   - B expectation, with its noise structure;
   - C departures;
   - D relations;
   - E interpretation;
   - F use.

   Stages B–D make statistical claims only; E alone is epidemiological. Every object belongs to one stage (P16).
2. **The expectation carries its noise structure.** A mis-stated null is fixed in stage B, measured per field (N1), never by a threshold per data system. ADR-0026's per-system table (`lenses.MINIMUM_EFFECT_BY`) and the trend relevance floor go when N1 lands.
3. **Detection is departure models** (§7.0, O6). The v0 lenses are screens, and the tiers are references declared per estimand. ADR-0027's past course survives as the step model's reference; its lens settings go with O6.
4. **The minimum relevant effect is relevance only**, inside the departure posterior. Lead volume belongs to ranking (stage F).
5. **Relations are one joint model of all fields' departures** (§7.5, O7): shared latent space–time factors and sparse lagged dependence. Pairwise lag tests only confirm. A design note precedes the build.
6. **Validation is split.** Statistical characterisation (stages B–D) and epidemiological checks (stage E) are never mixed.
7. **The roadmap is re-cut** (§12). New first packages: N1 (noise structure) and N2 (marginal uncertainty, from the SBC finding). O6 comes before O7, and O8 gathers interpretation. Order: N1 → N2 → O6 → O7 → O8, with O3 and O9 alongside, then O10. Leads are regenerated after O6.

## What stands

- The solver and model.
- ADR-0024 (ICD) and ADR-0025 (O2).
- The grid as stage B–D characterisation.
- The absorption finding and held-out sizing.
- SBC.
- ADR-0028 (the gate retired, method records, weighted BH).
- Rule versions.
- `relations.distributed_lag` as the confirmation tool.

## Limits

- The stage boundaries are the author's to correct.
- O7's joint model is a direction, not yet a design.
