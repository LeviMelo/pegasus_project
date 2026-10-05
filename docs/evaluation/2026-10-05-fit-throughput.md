# Fit throughput: warm starts, a mean fit that stops where it should, a cache of the assembled cells (2026-10-05)

**Regime:**
- **Code:** branch `worktree-agent-a92b69efff4c1c1d7` on design-v0 4e878d3; probes `data/perf/fit_probe.py`, `precond_probe.py`, `compare.py`, `check_blockdata.py`, `check_anderson.py`; JSON and logs in `data/perf/out/`.
- **Machine:** shared, six heavy jobs and the GPU in use by others. **Wall seconds carry that noise; the machine-independent cost is the number of conjugate-gradient iterations (CG, one Hessian-vector product each) and of outer iterations.**
- Nothing was saved to the fit store: every probe fits and discards, so the stored fits stay the references.

## Where a fit spends its time

| finding | evidence |
|---|---|
| The mean is never converged inside an outer | SIM.DO XVI 2010-19 at the stored τ's from a cold start: after 25 Newton steps the objective still falls 14 log-likelihood units per step, CG at its cap of 50 from step 18; the stopping rule (decrease < 1e-9 of the scaled objective, about 1e-4 log-likelihood units) is never met inside `inner` = 30. Every outer then pays 30 steps. |
| A block-Jacobi preconditioner (sparse LU per effect, as in `laplace.py`) does **not** help | same start, 25 steps: diagonal 455 CG iterations (forcing 0.5) reaching objective 355728, block 821 reaching 355782, diagonal at forcing 0.05 796 reaching 355682. The ill-conditioning is the coupling between effects that explain the same cells. Dropped; the code is not kept. |
| The monthly "not converged in 40 outers" is two different things | below |

## Results, SIM.DO XVI death 2010-2019 (185,576 cells)

| run | options | outers | CG iterations | wall s | CPU s | φ | rms Δlog μ vs C |
|---|---|---|---|---|---|---|---|
| A | legacy (cold) | not converged at 33 (max τ change 0.03), stopped at the 30-minute limit | | 1,633+ | | | |
| C | cold, `mean_tol` 1 | 36 | 5,905 | 932 | 2,529 | 9.807 | reference |
| D | C + warm start (from the 2010-2023 fit) | 7 | 2,119 | 359 | 869 | 9.797 | 5.2e-4 |
| E | D + Anderson + MAP-movement stop | 5 | 2,069 | 346 | 825 | 9.798 | 6.4e-4 |

- **Same optimum:** φ within 0.1%, the event-weighted RMS of log(μ_D / μ_C) is 5e-4, the largest τ ratio (active components) 1.63 (a weakly identified spatial one; a flat ridge, the objective is 355,643 against 355,679).
- **Warm start** takes the outers from 36 to 7 and the CG work to 36%. **`mean_tol`** (stop the Newton steps of an outer at one log-likelihood unit; the parameters persist, the final fit runs to full tolerance) is what lets C finish at all: A had not at 33.
- The Anderson mix and the MAP-movement stop save two more outers here. In the cold run C the MAP moved 0.8 units at outer 28 and 0.1 at 32: the movement stop (0.5) would have ended it at about 28.
- Not measured: the popsvs-to-account exposure pair (probes started, killed to relieve the machine) and the train-to-full pair in the train-to-full direction; D is the full-to-train direction. Both use the same code path (`warm_start` shifts the histories by years).

## Monthly convergence

- **SINAN-LEPT case monthly (41,498 cells), legacy, 150 outers:** objective flat at 217,336.1 and the MAP moving 0.31 units per outer from outer 30, yet "max τ change" 1.78 to the end. The fit had converged; **v_all hovered about `SHRUNK` (1e5) and cycled between 4.9e4 and 2.9e5**, where the update (x'Qx → 0) is ill-defined, and `min(new, τ) > SHRUNK` counted it as movement each time. The test is now `max(new, τ) > SHRUNK` (a τ that small has shrunk its effect, sd < 0.003).
- **SIH X monthly 2010-2023 (existing log, 40 outers, 9,263 s, not converged):** slow τ's, not noise. s_all climbs from 3 to 7,100 and is still moving 0.05-0.1 per outer; from outer 18 the BYM pair s_grp / v_grp swaps (s_grp 160 to 25, v_grp 34 to 4.5e4): the block-diagonal Fellner-Schall update sees each of two effects that explain the same place deviation as alone, a positive feedback that runs into the same shrunk boundary. The objective is flat to 1e-6 relative from outer 16 to 28. The full-Hessian update (`laplace.py`) would couple them but moves the fixed point (spatial τ about 5x lower), so it is not used here; open.
- **Anderson on log τ** converges a synthetic Fellner-Schall-like map in 8 iterations against 136 (`check_anderson.py`), and with noisy inner solves it can wander (SINAN-LEPT, first try, outers 9-29: objective jumping 217,4xx to 218,9xx); it is therefore opt-in, with the MAP-movement stop as the criterion that ends a ridge drift.
- Pending at the time of writing: `lept_N` (the `SHRUNK` fix alone), `lept_E` (all options), `sihX_E` (SIH X monthly 2010-2023, GPU, warm start from the 2010-2014 monthly fit, all options): see the last section.

## BlockData cache

`monolith.assemble` is memoised in the store (kind `blockdata`). Verified equal to a fresh assembly field by field, dtype by dtype, with the same monolith store address, on SINAN-LEPT monthly, SIM.DO III, IX under account-3, and a SINASC mark block. A hit reads in 0.6-1.0 s against 5-6 s with a warm gateway; the cold assembly of SIH X monthly (10.7 M cells) was 467 s. Concurrent writers of one address collided on Windows (PermissionError on a shared temporary name); `store` now writes a per-process temporary and tolerates a lost race.

## Projection for the queue's mix

Per fit, from the measured ratios (XVI: 36 to 5-7 outers, CG 5.9k to 2.1k) and not from the multiplicity yet run:
- a variant of a stored fit (train to full, exposure, split, rolling origin) costs about a third of a cold one: 0.35 of the CG work, 5-7 outers instead of 30-40;
- the 3.5-6 minute births block, the 11-28 minute IX annual and the refits of XX behave as XVI: a second and later variant at 0.3-0.4 of the first;
- the SIH X monthly: the legacy 40 outers (2.6 h) become the warm run in the last section.

## Last section: monthly runs with the new code
(filled in below when they finished)
