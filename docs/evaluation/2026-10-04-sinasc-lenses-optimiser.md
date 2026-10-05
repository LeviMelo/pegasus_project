# SINASC through the model; the optimiser; the change-point null; the first lead examined (2026-10-04)

**Regime:**
- **Data:** SIM.DO 2010–2023 and SINASC-DN 2010–2023 through `gateway` (pegasus_data 0.1.0a1; branch `pegasus-core-fixes` 70b56fc for the ICD tree and graphs).
- **Graph:** contiguity unless stated.
- **Artefacts:**
  - in `pegasus_home/`: `monolith/` and `harness/ledger`;
  - in `data/logs/`: `fit_blocks.log`, `fit_sinasc.log`, `positive_microcephaly.log`, `survey_ix.log`;
  - the scripts `data/profile_*.py`, `data/check_change_point.py` and `data/lead_sao_borja.py`.
- **Commit:** this entry's own.

## SINASC: births, anomalies, birth weight

**Totals:** SINASC totals through the gateway equal the published ones (2015: 3,017,668; 2020: 2,730,145; allocated plus unallocated).

**Births (one leaf, exposure = women by age):** 39.66 M events, 31 s, φ = 22.1.
- The male cells carry no exposure. A division by zero in the initialisation had set them to NaN, which is now fixed.

**Anomalies:** chapter XVII from CODANOMAL, one count per distinct category a birth carries.
- 411,955 category-events in 87 categories, φ = 5.8.
- **Microcephaly (Q02) at B1:**
  - 2015: 1,758 observed against 765 expected; 2016: 2,276 against 876;
  - Northeast 2015–16: 2,371 against 610;
  - every other year: 150–560 observed.

**Birth weight (PESO, mark model, log-normal):**
- 39.64 M weights;
- unallocated: 20,447 missing, 1,667 outside 200–7,000 g;
- mean 3,153 g, geometric mean 3,088 g (2022).

## Two rank errors in Fellner–Schall, and the optimiser

**The rank errors:**
- **Across rows:** centring was not subtracted from the effective ranks. v_cat was overstated by U·n_groups, and the group-level effects by a factor n_groups/(n_groups − 1).
- **A centred iid:** it claimed rank n, not n − 1. On a single-group block that gave th_grp a rank of 1 on an effect that is identically zero, and the births fit died on a singular factor.
- **Fixed:** chapter IX's objective moved from 3.0555 M to 3.0419 M.

**The optimiser (open question 6 (resolved)):** L-BFGS uses all 300 inner iterations it is given, about 160 s.

| from | none | diagonal preconditioner | block preconditioner (Cholesky of D + τQ) |
|---|---|---|---|
| perturbed fit (optimum 0.61204) | 0.61212 | 0.61212 | 0.61208 |
| scratch | — | 0.882 | 0.773 (+108 s factorising) |

- **Adopted meanwhile:** a third of the inner iterations while the τ's move by more than 10%.
- **The result:** chapter IX contiguity converged in 15–25 outers, about 3× faster per outer early on.

## The change-point null

The survey of IX flagged 25 small places for rheumatic heart disease (I00–I02). The null fit was the cause:

| null | I00–I02 | I05–I09 | I60–I69 | I21 |
|---|---|---|---|---|
| Gumbel by moments, all replicate maxima | 25 | — | — | — |
| Gumbel on the positive maxima, times 1 − π0 | 2 | 7 | 0 | 0 |
| **exact NB tail per window, Bonferroni over windows** | **1** | **1** | **0** | **0** |

- **Why the simulated nulls failed:** most replicate maxima are zero in small places, and the fitted tail was far too thin. For example, p = 4e-9 was given to 2 deaths against 0.03 expected.
- **The exact test:**
  - it needs no simulation and has no floor;
  - it runs in under 1 s per field;
  - its two hits are Bom Jesus (RN), 7 against 0.4 in 2014–23, and São Mamede (PB), 6 against 0.2 in 2022–23.

## The first lead examined: São Borja (RS, 431800), chapter IX

**What the counts show:**
- **Acute MI (I21):** 28–53 a year in 2010–2017, then 99 in 2018, and 97–134 through 2023. The six contiguous neighbours stay flat at 27–53.
- **Trends at B2:** I21 +0.50 ± 0.04 (neighbours −0.04); stroke (I60–I69) −0.19 ± 0.04 (stroke counts fell from 94 to 32); chapter IX as a whole +0.095 ± 0.023 (neighbours ≈ 0).
- **Not pure substitution:** the MI gain (about +60 a year) exceeds the stroke loss (about −30). This points to a 2018 change in what is certified and where.

**Status:** unexplained and unreplicated. The candidate drivers are a cardiology service, death verification and residence coding, through explain-away once CNES enters.

**The neighbours show a second pattern:** I63 rose from 1–5 to 14–24 a year from 2019, while I64 fell. That is a regional shift from unspecified to ischaemic stroke coding.

## The first known positive: microcephaly (§10.1)

**Script:** `data/positive_microcephaly.py`.

**Q02 subsets from the space–time lens** (100 replicates, Gumbel; 20 subsets at B1 and 20 at B2), the same loci at both tiers:

| locus | years | observed / expected | RR (B2) |
|---|---|---|---|
| Pernambuco, 28 places | 2015–16 | 419 / 94 | 4.4 |
| Bahia, 22 places | 2015–16 | 347 / 76 | 4.6 |
| Rio de Janeiro, 16 places | 2016 | 162 / 35 | 4.6 |
| PI, CE, PE, 21 places | 2015–16 | 100 / 18 | 5.7 |
| São Paulo, 17 places | 2016–17 | 136 / 34 | 4.0 |

**The pass criterion is met:** the locus lies in the Northeast in 2015–16, the sign is positive, and the result holds at B2 as well. The lens's surrogate false-lead rate is still pending.

## Held-out graph choice, chapter IX

Fit on 2010–2021, scored on 2022–23. The kNN6 and contiguity rows are from `scripts/measure_heldout.py`.

| graph | deviance per event |
|---|---|
| kNN6 | 2.21759 |
| contiguity | 2.21785 |

- **So far the graph barely matters out of sample.**
- **The trend extrapolation over-predicts** (850 k expected against 788 k observed): the training period ends in the COVID years.

## Marks: subset scans

**The score:** a Gaussian expectation-based score F = (Σw r)²/(2Σw) on weighted residuals of the mean log mark. It keeps the linear-time subset structure, scans two tails, and multiplies p by 2 for the two directions.

**Birth weight at B1:**
- KS 0.023, worst region 0.033: calibrated.
- 40 subsets, the strongest about 2% heavier in Northeast clusters in 2010–13.
- These are not read as leads until δ for marks is calibrated (P5).

## Performance: what was slow, and what fixed it

**Measured on contiguity IX** (`data/check_suffstat.py`, `data/profile_eval.py`, `data/check_gpu_null.py`):

| step | before | after | how |
|---|---|---|---|
| objective + gradient | 457 ms | **71 ms** | Σ y·η over 2.4 M cells is linear in the effects, so it becomes ⟨x, Y_x⟩ with the sufficient statistics Y_x computed once; iid penalties skip the sparse product. Objective identical to 12 digits, gradient to 1e-12 |
| one outer iteration (mean + τ) | ~90 s | **~18 s** | the above, plus a third of the inner iterations while the τ's move |
| null of a space–time scan, 100 replicates | 248 s (NumPy) | **2.5 s** | the replicates batched on the GPU (float32), drawn on the device. Null maxima agree: two-sample KS p = 0.99, medians 67.1 and 64.9 |
| harness, 20 surrogates of one field | hours | minutes | one null per field, cached and shared by its surrogates |

**What remains:** the observed scan itself (NumPy, about 2.5 s per recursion step), and L-BFGS's iteration count (open question 6 (resolved)).

## COVID-19: the positive fails retrospectively, and why

**SIM codes COVID-19 as B34.2:** 212,706 of the 2020 records have it as underlying cause, against 0 with U07. U07.1 appears in the cause lines of 173,561.

**At B1 over 2010–2023, B34 matches its expectation:** 213,152 observed against 212,821 expected in 2020; Amazonas 5,942 against 4,722.
- The space–time lens finds nothing at B1, and at B2 only Rio de Janeiro 2020 (RR 1.54, p 0.03).
- The year effects absorb the waves.
- The category's place effects are learned from the epidemic itself.

**Consequence:** the prospective tier BP (ARCHITECTURE §6.1) is for surveillance lenses. Its run is pending the 2010–2019 fits.

## Certification quality does not explain E_b among cardiovascular causes

**Script:** `data/eb_given_illdefined.py`.

**The ill-defined (chapter XVIII) place effect over B0:**
- its sd across places is 0.64;
- it correlates negatively with specific diagnoses (I20–I25 −0.38, I21 −0.33, I63 −0.35) and positively with vague ones (I64 +0.17, I50 +0.15, I10 +0.15).

**Adjusting for it barely changes E_b:**

| | pairs passing BH (δ = 0.1) | I61–I67 ρ |
|---|---|---|
| E_b | 29 of 180 | 0.406 |
| E_b given the ill-defined effect | 20 of 180 | 0.405 |

**A hypothesis for the surviving pairs:** I61, I71, I26, I80–I89 and I70–I79 are all diagnosed by imaging, so the common factor may be diagnostic capacity. To be tested with E_b|Z on CNES equipment.

## COVID-19 recovered prospectively (tier BP, train 2010–2019)

**Script:** `data/positive_covid_prospective.py`; 2010–2019 fits of I, X, IX, XVIII.

**Chapter I** (it includes B34.2):

| | 2020 observed / expected | 2021 observed / expected |
|---|---|---|
| Brazil | 267,139 / 58,900 | 486,462 / 61,667 |
| Amazonas | 6,972 / 1,037 | 10,334 / 1,074 |

- **The space–time lens** returns 20 subsets in 2020–21. Among them is AM+RR+PA at RR 9.0, beside SP, RJ, PR+SC, CE, MG+GO+DF and RS.
- **The pass criterion is met:** Amazonas in 2020–21, positive.
- **B25–B34 alone** is not a usable field: its expectation is near zero (173 deaths in 2020), because B34 has no past.
- **Respiratory deaths fell below the forecast:**
  - influenza and pneumonia (J09–J18): 68,186 against 87,706 expected in 2020, and 68,106 against 90,842 in 2021;
  - the respiratory chapter X: −12% in 2020 and −18% in 2021.

  This is consistent with deaths certified as COVID instead of pneumonia, and with influenza suppressed by distancing. The count lenses are one-sided, so the deficit came from the descriptive totals: two-sided lenses are the next step.

## The harness, first gate numbers (I60–I69, contiguity, minimum-effect lenses)

**False leads on 20 NB surrogates:** space–time 0/20, outbreak 0/20, change point 0/20.

**Power is low for a doubled single region-year.** A first version of the power curve bypassed the lens and scored by Jaccard. Rewritten to run the lens, it gives 2.5% at θ = 2.
- A São Paulo region (expected 9,535) and a Bahia region (1,656) are found at θ = 2 (p 1e-36 and 5e-5).
- An Amapá region (193) is not.
- Power depends on the expected count in the locus, so it is now reported by θ × expected count.

## Newton–CG replaces L-BFGS (open question 6 (resolved) resolved)

**Script:** `data/profile_newton.py`, chapter IX, τ fixed, from a perturbed start 14.0 above the optimum (scaled objective):

| | after ~3 s | after ~40 s |
|---|---|---|
| L-BFGS | gap 1.56 | diverged (NaN) |
| Newton–CG | gap 9.5e-4 | gap 5e-6 |

**Full refit (Newton–CG, sufficient statistics):** IX 229 s, X 154 s, I 525 s. The dispersions equal the earlier fits (6.00, 5.81, 6.72).

