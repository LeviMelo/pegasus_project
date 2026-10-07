# Stage B robust to the departures it must expose

**Status:** design, from the first real-data evaluation against documented events (2026-10-07, `data/real_events.py`).

## What real data showed

Yellow fever deaths 2017–18, measles admissions 2018–19 and chikungunya 2016–17 were missed by every stage-C method, or found only by the cruder ones. Brumadinho 2019, in chapter XX, was found. The cause is in stage B, not in the detectors:

- **One dispersion per block.**
  - The monolith fits a single φ for a whole chapter (`Monolith._dispersion`). Chapter I holds dengue and every other epidemic disease, so its φ is about 0.1–0.14. Under that φ, 180 yellow-fever deaths against 16 expected in four states are no surprise.
  - The PIT then passes calibration trivially (KS 0.002), so the field-level dispersion, which is the existing remedy, never engages.
- **Smeared expectations.**
  - With counts so weakly informative, a rare leaf's own year course is shrunk to the chapter's.
  - The epidemic years lift the leaf's level for every year. Measles is expected at 200–300 admissions a year when ordinary years see 33–83; yellow fever at about 32 deaths a year when ordinary years see 0–8.

**The principle.** The expectation's level and its noise must be estimated from the background, never from the departures stage C is meant to report (P16; the empirical-null idea applied to B itself).

## The design

1. **Dispersion over the ICD tree.**
   - log φ_leaf = log φ_block + δ_group + δ_leaf: each group's and leaf's maximum likelihood at fixed μ, shrunk toward its parent by the between-node variance (the pattern of `place_year_phi`).
   - The NB weights and likelihood take φ per cell (`nb_factors`, `nb_loglik` broadcast).
   - Stable leaves keep a large φ; epidemic leaves get their own.
2. **Contamination-robust fitting** (trimmed likelihood: Neykov et al. 2007; robust GLM: Cantoni & Ronchetti 2001).
   - After a fit, the cells beyond the predictive's 0.5 % / 99.5 % quantiles get weight 0.
   - Mean and dispersion are refitted on the rest, for two to three rounds.
   - The trimmed cells are the candidate departures; the expectation is the background's.
   - In-sample reference terms (national year courses) then follow the background, not the epidemic.
3. **Calibration judged on the bulk.**
   - KS on the PITs within [0.005, 0.995], and the field-level dispersion by trimmed likelihood (built: `place_year_phi`).

## Acceptance (real data first)

- The five documented events of `data/real_events.py` are found where and when they happened, with no method-specific constant.
- Measles and yellow-fever expectations in ordinary years approach their observed level.
- Calibration of fields with no documented event does not degrade (stroke, SIH pneumonia): held-out likelihood, KS on the bulk.
- Synthetic worlds only to confirm false-discovery calibration.
