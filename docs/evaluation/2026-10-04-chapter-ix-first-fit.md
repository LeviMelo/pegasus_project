# Chapter IX, the first fit read end to end (2026-10-04)

## Regime

- **Data:** SIM.DO deaths 2010–2023 by residence × sex × age × CAUSABAS, through `gateway` (pegasus_data 0.1.0a1 @ 0f4fe46+dirty), and POPSVS.
- **Model:** monolith block IX:
  - 77 categories, 10 groups, 5,570 places;
  - 2,449,785 non-empty cells, 4,990,893 events;
  - unallocated: 4,591 unknown residence, 447 unknown sex.
- **Graph:** knn6.
- **Fit:** CPU, 15 outer iterations, 1,394 s.
- **Artefacts:**
  - the fit, under `pegasus_home/monolith/`, keyed with `graph=knn6`;
  - the scripts `data/live_surprise.py`, `data/live_lenses.py` and `data/live_pairs.py`;
  - their tests, in `pegasus_home/ledger/`.
- **Commit:** this entry's own.

## Counted, and why

**Calibration of the predictive (PIT) is the gate for everything downstream** (ARCHITECTURE §6.2): a miscalibrated surprise produces false leads at every lens. Totals were checked against observed counts.

**The dispersion:**

| estimator | φ |
|---|---|
| Pearson moments | 0.013 |
| moments with a power series for empty cells | diverges |
| exact ML, empty cells streamed by leaf | **5.98** (+63,912 log-lik over Poisson; 13 s) |

The empty cells hold 1.95 M of the 4.99 M expected events (§5.2 rewritten).

**The PIT, KS overall / worst macro-region, after the fixes below:**

| field | B0 | B1 | B2 |
|---|---|---|---|
| IX | 0.031 / 0.152 | 0.010 / 0.033 | 0.011 / 0.030 |
| I20–I25 | 0.035 / 0.142 | 0.007 / 0.038 | 0.015 / 0.038 |
| I60–I69 | 0.024 / 0.097 | 0.013 / 0.029 | 0.011 / 0.025 |
| I64 | 0.078 / 0.193 | 0.011 / 0.028 | 0.020 / 0.039 |
| I10–I15 | 0.048 / 0.139 | 0.008 / 0.016 | 0.018 / 0.023 |

**The fixes the reading forced:**
- **B0's total was 11% short** (Jensen). It is now re-levelled per year.
- **B1's PIT was U-shaped,** with tails at about 0.13. A place-year variance component by ML fixed it: KS 0.035 → 0.010 (§6.2).
- **B2:** τ_α → bound, because B1 already holds the place effects; the trend sd is about 0.08 per year-sd.

**The lenses on B2** (BH within each field):
- **I60–I69:**
  - 1 outbreak cell: 251160 in 2016, 21 deaths against 4.5 expected;
  - 2 change points;
  - 3 trend divergences.
  - **The space–time scan:** none (50 replicates, Gumbel; 70 s).
- **I20–I25:** 93 trend divergences.
- **Municipality 431800 diverges in opposite directions:** stroke −4.6 sd, ischaemic heart disease +8.4 sd. This is the pattern of a coding shift. It is open, not yet explained.

**Pairs:**
- **E_b over B0** (20 fields, 180 testable pairs, δ = 0.1): 29 pass BH.
  - Every relation found is positive among cardiovascular causes, e.g. I61–I67 at ρ = 0.41 with n_eff = 599.
  - **The likely common cause is death-certification quality.** E_b|Z with the ill-defined share (block XVIII) is the estimand that tests it.
- **E_w at lag 0 on B2:** 0 of 145.
- **Distance classes:** equal-count classes made the first class 0–242 km. They are replaced by fixed classes from 15 to 3,000 km, under which r(<15 km) reaches 0.43 and n_eff falls by 10–30%.

## Not yet measured

- held-out deviance (tree pooling; contiguity against kNN);
- power curves and surrogate false-lead rates;
- the other chapters (fitting, contiguity).
