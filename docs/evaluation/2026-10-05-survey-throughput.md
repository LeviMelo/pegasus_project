# Survey throughput: 384 s to 65 s on SIM.DO chapter III, the same 28 leads (2026-10-05)

**Regime:**
- **Run:** `Session.survey(["III"], replicates=50)` on SIM.DO death 2010-2023, contiguity, 21 fields, via `data/perf/survey_profile.py` (scratch ledger and register).
- **Baseline:** HEAD 83fde72 in a worktree (no cProfile) and a cProfile run of the working tree.
- **Machine:** shared, GPU at 100% from other agents' fits, 1-4 GB free RAM. Timings carry that noise (the same GPU null took 95 s and 245 s in two runs of the same code).
- **Artefacts:** `data/perf/out/`.

## Where the time went (cProfile, 549 s)

| item | seconds | cause |
|---|---|---|
| model load (`monolith.assemble`) | 103 | a Python list comprehension per event row (millions) |
| `Session.edges()` | 113 | loaded a second model, the first fitted block (`I`), only to read the places; also its RAM. This was the 389 s step before `trend_divergence` in the SIH X survey |
| B2 expectation | 3 x 21 builds | outbreak, change point and trend divergence each rebuilt it (`place_year_phi` 1 s, `refit_place` 1.2 s) |
| GPU null (42 nulls) | 95 to 245 | cumsum over the 14-year axis was 46% of device time; `(Yw*P).sum` allocated [R,C,K,W] |
| `neighbourhoods` | 17 | Python BFS over 5,570 places, redone per field |

## Changes

- **Loading:**
  - Codes are decided once per distinct code (pyarrow dictionary) and indices come from `searchsorted`.
  - `BlockData` is identical to the old code's (XVI, 185,576 cells: N, e, u, t, g, y, unallocated, key); assemble 103 s to 10.6 s.
- **Session:**
  - `edges()` uses a loaded model and is cached.
  - `surprise()` is memoised for the length of one field's lenses.
  - `survey(workers=)` scans fields on threads over the one model, merged in field order (`survey_workers()`, `PEGASUS_SURVEY_WORKERS`; +0.1 GB per thread).
- **Scans:**
  - Window sums are one product with the windows' indicator, place sums a batched matmul (kernel 0.57 s to 0.09-0.25 s per chunk of 8, `best` equal to 2e-6).
  - The neighbourhoods are cached.
  - The null is drawn only when the observed best score is positive (a zero score has p = 1 under any null).
- **`place_year_phi`:** the gamma terms are computed on cells with y > 0 only (2-3x on sparse fields, relative difference below 1e-9).

## Result (wall, peak RSS)

| run | wall | peak RSS |
|---|---|---|
| HEAD, serial | 384 s | 1.82 GB |
| this change, 1 thread | 89.7 s | 1.59 GB |
| this change, 4 threads | 64.7 s | 2.00 GB |

- **Leads:** 28 in each; the same loci in the same order; p and q within 4.7e-6 (relative) of the baseline's (float32 order in the null); 1 thread and 4 threads give identical leads.
- **Threads give 1.5x, not 4x:** the remaining per-field work is Python-bound (the scalar optimiser, `refit_place`) and 8 threads were no faster (110 s, noisy).
- **Startup is 12 s:** model load 7 s, then the macro-regions of the 5,570 places (14 s of `geography.memberships`, once per process; pegasus_data).

**Extrapolation:**
- The SIM survey (726 fields, 19 chapters) took 232 min, 19 s per field. At 2.5-3.7 s per field plus 19 loads it is about 45-60 min.
- The SIH X survey saves its second model load (about 6 min) and 2 GB.
- Both are estimates from one small chapter: larger chapters have denser fields and larger models.
