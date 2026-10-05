# ADR-0013: The dependency map is two pair-test layers controlled over the whole map, δ_E 0.03 and δ_E|Z 0.1

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-dependency-map.md`: 65 fields, 2,059 pairs per layer, Moran-surrogate negatives in 40 worlds (two seeds): no admitted false edge at δ_E|Z 0.1; at 0.05 the conditional layer admitted one in 8 of 20 worlds.

## Decision

1. **The map is the §7.5 pair test applied to all pairs**, in a marginal layer (E_b) and a conditional layer (E_b|Z, Z the other declared contexts, n_eff − dim Z), not a graphical model. Direct / explained / suppressed is read from the two layers (ARCHITECTURE §7.6).
2. **δ_E 0.03 marginal, δ_E|Z 0.1 conditional** (`maps.DELTA_Z`), the conditional one calibrated on the map's own negatives (`harness.map_delta`); single-pair scans keep 0.05.
3. **Error control per layer over the whole map:** TreeBH (family → pair, family = estimand × field-group pair) at q 0.05, BY as the stricter alternative. Pairs whose overlap exceeds 0.05 or is unknown are not tested.
4. **A map is validated on its negatives** (Moran surrogates generated on another graph than the one that tests) before its edges are read.

## Limits

20 worlds per seed resolve only rates above about 0.05 per world; n_eff − dim Z was not compared with no subtraction; SIH×SIH edges are one shared hospital-use dimension and carry no disease claim.
