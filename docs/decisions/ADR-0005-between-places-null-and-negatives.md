# ADR-0005: The between-places null and negatives; calibrated δ for E_b

**Date.** 2026-10-05. **Status.** Active.

**Evidence.**
- The pairs-gate measurement (`scripts/gate_eb.py`; handoff `data/handoffs/pairs_gate.md`; its evaluation entry ships with the code).
- `docs/evaluation/2026-10-04-eb-census-positives.md`.

## What was measured

Each method's null spread of ρ was compared with independent Gaussian-field surrogates fitted to each field's own correlogram, across the census-context pairs.

| method | spread against the truth | size at a nominal 0.05 |
|---|---|---|
| Dutilleul n_eff | 0.89 | 0.076: slightly liberal |
| Moran spectral randomisation (MSR) on the raw border-weight matrix | 3.5× too small | far too liberal |
| MSR on the symmetric-normalised adjacency | 0.99 | 0.047 |

The raw matrix's top eigenvectors are localised, so sign flips destroy long-range structure.

## Decision

1. **Between places (E_b, E_b|Z), the p-value comes from MSR on the symmetric-normalised adjacency** (D^{-1/2} W D^{-1/2}). Dutilleul stays only where MSR is unavailable, flagged as liberal.
2. **§10.2's negative controls between places use the same normalised MSR,** generated on a different graph from the one the test uses, so a negative is not circular with its own null.
3. **δ_E is calibrated on those negatives** (§8.4): **0.03 for E_b, 0.05 for E_b|Z.** These replace the provisional 0.1.
4. **What the gate admits.** MSR gives a correct null, not more power. At δ_E, these known positives are admitted:
   - infant mortality ↔ sanitation;
   - diarrhoea ↔ households without a bathroom.

   The spatially smooth literacy and GDP pairs are not: their n_eff is too small. That is honest low power, not a failure of the method.
5. **Consequence.** False-lead rates already computed with raw-matrix MSR negatives are invalid, and are re-run under this ADR.
