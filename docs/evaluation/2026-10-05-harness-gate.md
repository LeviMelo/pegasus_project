# The lens gate: false leads, negatives, power, §10.5 (2026-10-05)

**Regime:** `scripts/harness_gate.py` (`fl`, `pow`, `cal`; env `GATE_KINDS`) over the Surprise objects of fitted blocks, pickled by `data/harness_gate/extract.py`; artefacts `data/harness_gate/*.json` and store kind `gate_lenses`. Fields: SIM chapter IX 2010–2023 (I10–I15, I20–I25, I60–I69, I05–I09, I26–I28), SINASC 2010–2023 birth weight (mark `PESO`) and Q02 (counts); contiguity graph, 5,570 municipalities, 100 scan replicates, commit c221508 plus the harness code of this entry. Each cell is "worlds with any finding / worlds"; q = 0.05; ub = Wilson 95% upper limit.

## Worlds

- **NB surrogate (§10.4):** y\* ~ NB(μ̂, φ̂) at the lens's own tier (marks: Gaussian), B2 trends refitted.
- **MSR negative (§10.2, ADR-0005):** the field's standardised residuals z, randomised across places by Moran spectral randomisation on the symmetric-normalised **knn8** graph (the lenses test on contiguity), one sign vector shared by all years; y\* is the NB quantile at Φ(z\*).
- **Shift negative:** each place's z series moved by its own k ∈ [2, T−2] years.
- **`_ns`:** the same after replacing z by its normal scores (marginal exactly N(0,1), dependence kept). Added because a real field carries unmodelled shocks (COVID-19 in 2020–21, Zika in Q02): the raw shift keeps them as marginal extremes, and a cellwise lens then reports them. They are findings, not false leads.

## False leads

| lens (tier) | NB surrogate | MSR negative, IX | MSR, SINASC | shift, IX raw / `_ns` |
|---|---|---|---|---|
| outbreak (B2) | 2/350 | 0/250 | Q02 7/50; PESO 0/50 | 54/250 / **0/160** |
| change point (B2) | 0/300 | 1/250 | 0/50 | 50/250 / 28/160 |
| space–time (B1) | 0/350 | 0/250 | **Q02 50/50**; PESO 0/50 | 46/250 / 1/160 |
| spatial cluster (B0), θ0 1.2 | 1/300 | **84/250** | Q02 33/50 | not a negative (time is summed) |
| trend divergence (B2) | 0/300 | 0/250 | 0/50 | 34/250 / 18/160 |
| group disparity (B0) | 1/250 | 3/250 (ub 0.03) | n/a | n/a (the lens sums years) |
| marks, outbreak / space–time (PESO) | 0/50, 0/50 | n/a | 0/50, 0/50 | shift: outbreak 50/50 raw, 0/40 `_ns`; space–time 2/50 |

- **Surrogates:** every lens is at or below q (pooled worst 2/350, ub 0.02).
- **The residual failures of the shifts are the field's own structure.** Change point `_ns` 28/40 is I26–I28 alone: its level shift after 2020 survives any circular shift (the 3 other IX fields 0/120). Trend divergence `_ns` is I10–I15 (5/40) and I26–I28 (13/40).
- **Space–time and outbreak on Q02:** MSR keeps the Zika block's energy (7,529 events, mostly 2015–16, Northeast) as a smooth random field with hot spots in 2015–16. Raising θ0 does not remove it (space–time 21/40 at θ0 2.0; outbreak 1/40 from 1.4). Not a null for this field.
- **Spatial cluster at B0 is the one lens that fails.** The B0 residuals carry the persistent place effects, smooth in space; a random field with that spectrum has clusters.

## θ0 of the spatial cluster (§8.4), MSR negatives, 30 worlds per field

| θ0 | I10–I15 | I20–I25 | I60–I69 | I05–I09 | I26–I28 | pooled | Chagas (B57) clusters / excess captured | schistosomiasis (B65) |
|---|---|---|---|---|---|---|---|---|
| 1.2 | 15 | 22 | 6 | 4 | 3 | 50/150 | 4 / 12,844 of 22,984 | 20 / 3,494 of 3,370 |
| 1.4 | 2 | 9 | 0 | 1 | 0 | 12/150 | 4 / 12,841 | 20 / 3,484 |
| **1.5** | 0 | 5 | 0 | 1 | 0 | **6/150 = 0.04** | 3 / 10,356 | 20 / 3,366 |
| 1.75 | 0 | 2 | 0 | 0 | 0 | 2/150 | **0** | 18 / 3,244 |
| 2.0 | 0 | 1 | 0 | 0 | 0 | 1/150 | **0** | 18 / 3,232 |

- **The per-family rule of ADR-0005 (no family above q) gives θ0 = 2.0**, which loses the Chagas positive.
- **Set to 1.5** (`lenses.SPATIAL_RATE_RATIO`): the pooled rate is 0.04 and both positives stay. The worst family, I20–I25 (ischaemic heart disease), is 5/30.
- No other lens needed calibration on a valid negative: outbreak, change point, space–time (IX, PESO), trend divergence, group disparity and marks held q at their provisional θ0 1.2, ratio 1.2, sd 0.2 and 3%.

## Power (planted signals, §10.3; the lens itself, B2 trends refitted)

Recovery of a planted locus by a finding on its place (and year), pooled over fields; columns are the locus's expected count (marks: Σ w).

| lens, locus | θ | <3 | 3–10 | 10–30 | 30–100 | 100–300 | 300–1000 | ≥1000 |
|---|---|---|---|---|---|---|---|---|
| outbreak, one place-year | 2 | 0.00 | 0.00 | 0.00 | 0.25 | 0.57 | 0.72 | 0.75 |
| | 3 | 0.02 | 0.19 | 0.74 | 0.97 | 1.00 | 1.00 | 1.00 |
| | 5 | 0.20 | 0.89 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| change point, last 3 years | 1.5 | 0.00 | 0.00 | 0.00 | 0.02 | 0.07 | 0.28 | 0.64 |
| | 2 | 0.01 | 0.02 | 0.18 | 0.48 | 0.88 | 0.99 | 0.96 |
| | 3 | 0.03 | 0.26 | 0.87 | 1.00 | 1.00 | 1.00 | 1.00 |
| group disparity, one group over the period | 2 | 0.00 | 0.00 | 0.00 | 0.03 | 0.24 | 0.71 | 0.73 |
| | 3 | 0.00 | 0.03 | 0.33 | 0.84 | 0.93 | 1.00 | 0.93 |
| | 5 | 0.00 | 0.27 | 0.83 | 0.96 | 1.00 | 1.00 | 1.00 |

| lens, locus (immediate region) | θ | <100 | 100–300 | 300–1000 | 1000–3000 | ≥3000 |
|---|---|---|---|---|---|---|
| space–time, region-year | 2 | 0.00 | 0.00 | 0.00 | 1.00 (2) | |
| | 3 | 0.00 | 0.27 | 1.00 (1) | 1.00 (2) | |
| | 5 | 0.08 | 0.73 | 1.00 (1) | 1.00 (2) | |
| spatial cluster (θ0 1.5), region over the period | 3 | 0.22 | 0.00 | 0.00 | 0.25 | 1.00 (5) |
| | 5 | 0.54 | 0.44 | 0.50 | 1.00 | 1.00 (5) |
| trend divergence, ratio over the period | 3 / 5 | 0 / 0 below 300; 0.11–0.25 / 0.2–0.3 at 100–1,000; 1.0 at ≥1,000 (3 places) |

- **Marks** (birth weight, weight ratio θ): outbreak 1.04 → 0.00, 1.08 → 0.44 (0.94 at Σw 10⁴–3·10⁴), 1.15 → 0.71; space–time 1.08 → 0.63, 1.15 → 0.93. A shift below 4% is never found: the 3% minimum effect plus the noise.
- **The admission reference (§8.4, rate ratio 1.5 over a macro-region-year) cannot be met by space–time or spatial cluster as built:** the scanner's neighbourhoods hold at most 30 places, and at 1.5 no locus of the measured sizes is recovered (0.00).
- **Trend divergence is nearly blind** below a threefold change over the period. The ridge prior, learned from the field, shrinks a lone divergent trend; a divergence needs a large place.
- **Spatial cluster** (θ0 1.5; four IX fields, 30 regions per θ): 0 at θ ≤ 2, 0.18 at 3, 0.63 at 5. At θ0 2.0 it was 0.02 at 3 and 0.42 at 5.

## The gate (§10.5)

| lens / estimand | 1. positives | 2. false leads ≤ q | 3. power curve | gate |
|---|---|---|---|---|
| outbreak | dengue epidemics at **BP** (29/37 state-years 2015–16, 59/64 2019–23, precision 0.57; not at B2s); COVID-19 at BP | NB 2/350; MSR 0/250 IX; shift `_ns` 0/160 | published | **PASS** (positives at BP) |
| change point | none declared in §10.1 (see the update below) | NB 0/300; MSR 1/250; shift `_ns` 28/160 (I26–I28) | published | **FAIL**: no positive |
| space–time | microcephaly (Northeast 2015–16, RR 4.4–5.7), COVID-19 Amazonas, leptospirosis RS 2024 (18 municipalities, RR 63; Jaccard as written fails) | NB 0/350; MSR IX 0/250, PESO 0/50; **Q02 50/50 (negative contaminated by the Zika block)** | published; low (0 at θ ≤ 2) | **PASS**, flagged: the Q02 negative |
| spatial cluster | Chagas (B57), schistosomiasis (B65): precision 1.0, Jaccard 0.07–0.16; kept at θ0 1.5 | NB 1/300; MSR 84/250 at θ0 1.2, 6/150 at 1.5 (worst family 5/30) | published | **FAIL**: negatives (family rule needs θ0 2.0, which loses Chagas) |
| trend divergence | none declared | NB 0/300; MSR 0/250; shift `_ns` 18/160 | published; blind below ×3 | **FAIL**: no positive |
| group disparity | none declared | NB 1/250; MSR 3/250 | published | **FAIL**: no positive |
| marks | none declared | NB 0/50 each lens; MSR 0/50 each | published | **FAIL**: no positive |
| E_b, E_b\|Z | infant mortality ↔ sanitation, diarrhoea ↔ no bathroom (2026-10-05 E_b gate) | δ_E 0.03 / 0.05 calibrated on MSR negatives | published, low on smooth latents | **PASS** (that entry) |
| E_w | microcephaly after arbovirus notifications (script only, no entry) | not run | not run | **not gated** |

## What changed in the code

- `lenses.SPATIAL_RATE_RATIO = 1.5` for the spatial cluster; `RATE_RATIO` stays 1.2 for the other cell lenses.
- `harness`: `lens_world`, `negative_scores`, `mark_surrogate`, `group_world`, `cell_power`, `group_power`, `wilson_upper`, `power_curve(mark=)`; `pairs.MoranBasis.randomise(shared=)`.

## Open

- **Positives for change point, trend divergence, group disparity and marks** are absent from §10.1; each lens stays out of production until one is declared and recovered.
- **A null for the B0 scan that carries the field's spatial spectrum** (the maximum statistic under MSR worlds) would replace the θ0 patch for the spatial cluster.
- **The admission reference effect** needs a locus the scanner can reach (§8.4).

## Update: positives declared for the ungated lenses (entry 2026-10-05-lens-positives)

Rows 1 of the gate for the four lenses that had no positive; rows 2 and 3 are the measurements above. A per-place positive is recovered when the recall of the documented places, weighted by their documented excess, is ≥ 0.5 with the sign (the Jaccard is reported).

| lens / estimand | 1. positives | 2. false leads ≤ q | 3. power | gate |
|---|---|---|---|---|
| change point | COVID-19 as a new cause, **BP** (train ≤ 2019): weighted recall 1.00, Jaccard 0.95 (5,562 findings, 5,285 documented places). **B2 in-sample: 1/5,285**; São Paulo's undetermined-cause deaths 2018 and Roraima's births 2018–19 not recovered at B2 | NB 0/300; MSR 1/250; shift `_ns` 28/160 (I26–I28) | published | **PASS at BP**, flagged: one positive, trivially large; B2 is blind to a step older than the last years |
| trend divergence | municipalities installed in 2013, births: 4 of 5 (8.0–13.3 sd, all up), precision 4/13; not found on chapter IX deaths (too few) | NB 0/300; MSR 0/250; shift `_ns` 18/160 | published; blind below ×3 | **PASS**, flagged: a boundary artefact, seen before it was documented |
| group disparity | female homicide in Roraima: 2 of 14 testable places, female share ×2.1 and ×4.3 of the national pattern; Rio Grande do Sul elderly suicide not found (×1.28, below sd 0.2) | NB 1/250; MSR 3/250 | published | **PASS**, flagged: a sex pattern only; sparse places untestable (`min_expected`) |
| marks | none documented (birth-weight effects ≤ 0.1% against the 3% floor) | NB 0/50 each lens; MSR 0/50 each | published | **FAIL**: no positive |
| E_w | cold → respiratory admissions ρ −0.02 to −0.07 (sign right, controls ≈ 0), below δ 0.1; arbovirus → microcephaly not recovered | not run | not run | **not gated** |


## Update 2: positives declared before the run (entry 2026-10-05-lens-positives, second round)

The passes above for trend divergence and group disparity were seen before they were declared and are withdrawn (coordinator review). Positives declared in `harness.POSITIVES` (commit 86d6895) before the lens ran, from the Atlas da Violência UF tables:

| lens / estimand | 1. positives | gate |
|---|---|---|
| change point | COVID-19 as a new cause, BP (declared beforehand): weighted recall 1.00 | **PASS at BP**, flagged (one positive) |
| trend divergence | homicide divergence across UF borders (30 municipalities, ratio ≥ 1.5 over 2010–23): 7 findings, none documented; recall 0. **Redesigned over three scales (third round, lens-positives entry):** `neighbours` 0.048 (fails); `national` (2,289 municipalities, declared after one look) 0.66 at region and state, negatives 0 | **FAIL** for `neighbours`; `national` recovered, flagged: **not gated** |
| group disparity | women's share by UF (10 UFs): weighted recall 0.048; young men's share (5 UFs): 0.003, Jaccard under 0.01 | **FAIL**: not recovered; the reference overstated women's share (9.98% against 8.2% observed), now re-levelled to the observed totals. Over three scales at sd 0.05 recall 0.97 and 0.94, but the spatial negatives reject every sd below 1.0: **FAIL** (negatives) |
| marks | no primary source for a shift of 3% or more; floor recalibrated to 1.5% (PESO negatives); the 2005 Northeast–Southeast gap (2.4%) is B1-absorbed and of another period | **FAIL**: no positive |
| E_w | the dengue–climate run is queued, not declared: exploratory | **not gated** |
