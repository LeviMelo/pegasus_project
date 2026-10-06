# ADR-0022: Admission is read from the harness's power curves, not set; a miscalibrated field stays out of pair scans

**Date.** 2026-10-05. **Status.** Active until O3 of ARCHITECTURE §12; **amended by ADR-0023** (2026-10-06). Exclusion by power is replaced by weighting by power (IHW), and the power curves become inputs of the weights and of each result's minimum detectable effect. Items 2, 4 and 5 stand. Closes the admission half of gap 9 of `docs/architecture_coverage.md`; ARCHITECTURE §8.4, §11.4.

**Evidence.** `docs/evaluation/2026-10-05-admission.md`: the lenses' power for a rate ratio of 1.5 over one macro-region and window, measured with the production lenses on six fitted fields thinned to five sizes.

## Decision

1. **A lens scans a field when its measured power for the reference effect is at least 0.5 at the field's expected count** (`fields.admission`, curves in `src/pegasus_core/admission_curves.json` from `scripts/measure_admission.py`). The count is that of the locus in the field's median macro-region: a region-year (outbreak, space-time), the last three years (change point), the whole period (spatial cluster). The former rule (1,000 events and 5 % of units) is removed.
2. **Detection of a macro-region-year means a finding lying at least half inside it** (`harness.region_power`). `power_curve`'s "half the locus recovered" measures the scanner's 30-place neighbourhood, not whether the lens sees the effect, and gave 0.00 at 1.5 for every size.
3. **A lens that cannot reach 0.5 at 1.5 at any count is admitted at the smallest ratio it can** (`fields.reference_theta`): outbreak, space-time and spatial cluster at 2.0, change point at 1.5. Admitting nothing would silently end three production lenses; the ratio used is part of the verdict text. Trend divergence and group disparity have no locus of this kind (trend is blind below x3, §10.3): they scan the fields any lens admits. `Session.survey` skips a lens that does not admit the field.
4. **Pairs: a health field enters the dependency map when the power of E_b at δ_E to see a shared latent of ρ = 0.3 is at least 0.5** (`harness.pair_power`, the field's own refitted place effect against a partner of its spectrum, 30 replicates; `map_inputs.build`). Map inputs are stored under key v2.
5. **§11.4 is enforced** (`maps.exclude_miscalibrated`, `pairs.within(excluded=)`): a field whose calibration failed §6.2 never enters a pair scan, and the KS that excluded it is kept in the inputs' `meta`. For the map the tier is **B1**: the place effects are over B0, which fails by design and cannot be the tier, and B1 is the first tier whose field dispersion the place effects' Poisson sd depends on. SINASC indicators and contexts have no count expectation and stay.

## Limits

- The curves come from five chapter-IX fields and Q02; the count axis is extended by thinning (a thinned negative binomial keeps its size φ). The dispersion of rarer real fields may differ.
- Space-time's curve at 2.0 is flat near 0.4-0.5 from 500 to 17,000 events (a scan with neighbourhoods of at most 30 places); its critical count (6,700) is a pooled-adjacent-violators reading of that plateau.
- The power of the trend and group lenses at a macro-region-scale effect is not measured; they inherit the cell lenses' admission.
- θ0 calibration below 1.2, the map re-run and the coverage count are in the evaluation entry's status; θ0 stays at 1.2 (spatial cluster 1.5) until the entry records them.
