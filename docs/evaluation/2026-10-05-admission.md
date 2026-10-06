# Admission by power curve (2026-10-05)

**Regime.** `scripts/measure_admission.py <lens>` (artefacts `data/harness_gate/admission_curve_*.json`, merged into `src/pegasus_core/admission_curves.json`), commit db4a4f7 plus the ADR-0022 code; fields `data/harness_gate/*.pkl` (chapter IX I05-I09, I10-I15, I20-I25, I26-I28, I60-I69; Q02 births), each thinned to 1, 0.3, 0.1, 0.03, 0.01 of its expectation, contiguity graph, 100 scan replicates. A rate ratio θ planted over one macro-region and window (every region meets every window once; five regions per background); **detected** = a production finding at least half inside the locus. Power by the locus's expected count, 165-320 loci per bin at the middle bins.

## What the reference effect needs (power ≥ 0.5)

| lens (tier) | locus read | power at 1.5 | at 2.0 | at 3.0 | admitted at | critical count |
|---|---|---|---|---|---|---|
| outbreak (B2) | median region, one year | 0.455 at 44,000, 0.25 at 17,000, 0 below 1,700 | 0.35 at 520, 0.67 at 1,700 | 0.78 at 180 | **2.0** | 920 |
| change point (B2) | median region, last 3 years | **0.67 at 18,000**, 0.26 at 5,800, 0.05 at 1,700 | 0.54 at 580 | 0.95 at 170 | **1.5** | 11,300 |
| space-time (B1) | median region, one year | 0.47 at 45,000, 0.16 at 17,000, ≤ 0.03 below 5,700 | 0.42-0.49 from 1,800 to 5,700, 0.57 at 17,000 | 0.76 at 180 | **2.0** | 6,700 |
| spatial cluster (B0) | median region, whole period | **0 at every count to 214,000** | 0.64 at 2,000, 0.93 at 214,000 | 0.92 at 200 | **2.0** | 1,200 |

- **Three of the four lenses cannot see a rate ratio of 1.5 anywhere** (the published curves at place-year loci said the same: 0.00 at 1.5). Applying §8.4 to the letter would have admitted no field to outbreak, space-time or spatial cluster; ADR-0022 admits them at the smallest ratio they reach 0.5 at, and the verdict text carries the ratio.
- **Change point is the strictest in counts** (11,300 deaths in the median region's last three years, about 60,000 over 14 years): the rate-ratio-1.5 step needs a common cause.
- The critical counts are per macro-region locus; the former rule (1,000 events nationally) admitted fields whose median region-year holds about 10 events, where the curves are 0.
- Trend divergence and group disparity were not given a curve at a macro-region-scale effect; they scan what any cell lens admits.

## Pairs and calibration (code done, runs pending)

`map_inputs.build` admits a health field when `harness.pair_power` at ρ = 0.3 is ≥ 0.5; `maps.exclude_miscalibrated` removes SIM and SIH chapters failing §6.2 at B1 (the SIH readout already lists XV at .067/.092 and I at .032/.043 as failing B1; SIM is unread); `pairs.within` drops an E_w surprise failing at its tier. **Not yet measured:** the map re-run (`pegasus-core map`, v2 inputs) and its count of fields removed, the scan coverage (`measure_admission.py coverage`), and the per-lens θ0 below 1.2 (`GATE_LOW=1 scripts/harness_gate.py cal`, grid 1.0-1.2, MSR and time-normal-scores negatives, 30 worlds, five IX fields). All three are queued behind `scripts/heavy.py` (machine at 0.3 GB free memory, all six slots held); `data/handoffs/admission.md` has the commands. θ0 stays 1.2 (spatial cluster 1.5) until they are read.
