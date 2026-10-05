# The E_b gate: the between-places null, δ_E, power and the known positives (2026-10-05)

**Regime:** `scripts/gate_eb.py` (negatives, δ_E, planted-latent power, known positives), SIM infant mortality and diarrhoea place effects (shrunk) against six census contexts, 5,570 municipalities, graph `contiguity01`, input `data/agent_context/prep.npz`. Calibration run `gate_eb5` (300 negatives per cell, 80 power replicates; `data/logs/gate_eb5.log`); final-constants check `gate_eb6` (100/20; `data/logs/gate_eb6.log`). Null comparison against independent Gaussian-field surrogates (exponential+nugget and Matérn-3/2 fitted to each field's correlogram), `data/agent_pairs/`. Decision: ADR-0005.

## The null (12 outcome-context cells; ratio = predicted sd / true sd of ρ; size = share with p ≤ 0.05 at δ = 0)

| method | ratio | size |
|---|---|---|
| Dutilleul n_eff (the former null) | 0.89 | 0.076 |
| MSR, raw border-length weight matrix | 0.28 | 0.70 |
| MSR, binary contiguity W | 0.45 | 0.51 |
| MSR, dense kernel 50 / 150 / 400 km | 0.55 / 0.78 / 0.92 | 0.42 / 0.15 / 0.065 |
| **MSR, symmetric-normalised contiguity** | **0.99** | **0.047** |
| MSR, normalised weighted contiguity / knn8 / kernel 150 | 1.00 / 0.93 / 0.95 | 0.06 / 0.065 / 0.049 |

The raw-W eigenvectors localise on hubs (the top 10 hold 0.4% of literacy's energy), so sign flips lose long-range structure. Rejected: CAR (Leroux) GLS (size 0.76, spatial confounding); GP-exponential GLS (sd ratio 1.03, size 0.10 at δ = 0, but the estimand changes, DIA-sanitation slopes collapse to ~0, and each outcome needs a ~2 min REML Cholesky): reported as a measured alternative. A weights bug was fixed on the way: randomising the *weighted* field understates σ 2–5× (0.019 against 0.092; ESS of √(w_X w_Y) is 385 of 5,570); production randomises the unweighted residual and applies the weights after.

## δ_E (§8.4): the smallest grid value at which no family exceeds 0.05

Rate of p ≤ 0.05 at δ = 0 / 0.03: IM|census .049/.010, IM|outcome .097/.047, DIA|census .056/.010, DIA|outcome .083/.047, census|census .067/.030. **δ_E = 0.03 for E_b; 0.05 for E_b|Z** (worst family at 0.03: 0.053). The 100-draw check gave 0.02 / 0.03 (Monte-Carlo noise); the 300-draw figures are the constants. Validation of the production code on 200 draws (size at δ = 0 / 0.02 / 0.05): DIA|census .056/.018/.004; IM|census .038/.007/0; with Z, ratio 1.09–1.32 and size .06–.08; census as outcome (unweighted smooth fields, the hardest class, 60 cells) .115/.062/.025, worst cell 0.24.

## Power (planted shared latent; observed ρ is attenuated ~0.5× by shrinkage, true 0.3 → 0.16)

| true ρ | 0.15 | 0.3 | 0.45 | 0.6 |
|---|---|---|---|---|
| smooth latent (literacy spectrum, n_eff 6–25) | 0 | 0 | 0.30 | 0.65 |
| local latent (IM spectrum) | 0.20 | 0.90 | 0.85 | 1.0 |

(gate_eb6, 20 replicates; gate_eb5 at 80: smooth 0.30 / 0.54 at 0.45 / 0.6; local 0.65 / 0.84 / 1.0 at 0.3 / 0.45 / 0.6.) Dutilleul and normalised MSR are equal within noise at held size: **MSR buys a correct null, not power.**

## Known positives at the final constants (ρ / n_eff / p at δ_E; E_b|Z adjusts for log GDP per capita)

| outcome | context | ρ | n_eff | p | | adjusted ρ | n_eff | p |
|---|---|---|---|---|---|---|---|---|
| IM | sewer | −.21 | 76 | .059 | | −.15 | 90 | .18 |
| IM | water | −.21 | 172 | **.008** | | −.15 | 284 | **.049** |
| IM | no bathroom | +.24 | 108 | **.014** | | +.18 | 233 | **.021** |
| IM | waste | −.26 | 68 | **.030** | | −.17 | 131 | .094 |
| IM | literacy | −.24 | 32 | .121 | | −.12 | 279 | .12 |
| IM | log GDP | −.24 | 50 | .073 | | | | |
| DIA | sewer | −.19 | 110 | .052 | | −.12 | 171 | .17 |
| DIA | water | −.15 | 213 | **.036** | | −.09 | 493 | .19 |
| DIA | no bathroom | +.27 | 127 | **.003** | | +.22 | 450 | **.0001** |
| DIA | waste | −.21 | 85 | .052 | | −.12 | 314 | .11 |
| DIA | literacy | −.28 | 28 | .103 | | −.19 | 156 | **.043** |
| DIA | log GDP | −.21 | 45 | .122 | | | | |

Signs 12/12 as before. **Admitted at δ_E (p ≤ 0.05): 5 of 12 unadjusted pairs** (IM water, no bathroom, waste; DIA water, no bathroom; DIA sewer and waste miss at .052), and 4 adjusted at 0.05 (IM water, IM no bathroom, DIA no bathroom, DIA literacy; IM water at .0487 is on the edge). Under the former null at δ = 0.1, 2 of 12. The pairs that stay out (literacy, GDP, n_eff 28–110) are limited power on smooth fields, not a defect.

## Not shown

E_i (basis on the care-flow graph) is untested; E_w keeps its provisional δ = 0.1; the surrogate checks are Gaussian fields fitted to two outcomes' correlograms, not a measure of the unknown truth; false-lead rates computed earlier with raw-matrix MSR are invalid (ADR-0005) and not yet re-run.
