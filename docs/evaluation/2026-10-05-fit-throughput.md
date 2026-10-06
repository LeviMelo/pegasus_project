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

- **SINAN-LEPT case monthly (41,498 cells), legacy, 150 outers:** objective flat at 217,336.1 and the MAP moving 0.31 units per outer from outer 30, yet "max τ change" 1.78 to the end. The fit had converged; **v_all (the place iid effect, sd 0.004-0.014) cycled with period 4 between 4.9e3 and 8.2e4**, where its Fellner-Schall update (x'Qx → 0) is ill-defined. A first fix (counting a τ as stationary when either side of an update exceeds `SHRUNK`) did not stop the cycle (it stays below 1e5 on most steps) and was reverted; the fit-level criterion (`move_tol`) is what ends it.
- **SIH X monthly 2010-2023 (existing log, 40 outers, 9,263 s, not converged):** slow τ's, not noise. s_all climbs from 3 to 7,100 and is still moving 0.05-0.1 per outer; from outer 18 the BYM pair s_grp / v_grp swaps (s_grp 160 to 25, v_grp 34 to 4.5e4): the block-diagonal Fellner-Schall update sees each of two effects that explain the same place deviation as alone, a positive feedback that runs into the same shrunk boundary. The objective is flat to 1e-6 relative from outer 16 to 28. The full-Hessian update (`laplace.py`) would couple them but moves the fixed point (spatial τ about 5x lower), so it is not used here; open.
- **Anderson on log τ** converges a synthetic Fellner-Schall-like map in 8 iterations against 136 (`check_anderson.py`), and with noisy inner solves it can wander (SINAN-LEPT, first try, outers 9-29: objective jumping 217,4xx to 218,9xx); it is therefore opt-in, with the MAP-movement stop as the criterion that ends a ridge drift.
- **The movement stop is not yet sound on the cycle.** SINAN-LEPT with `mean_tol` 1 and `move_tol` 0.5 (and the gate "max τ change < 0.5", since removed) still ran 150 outers: the cycling v_all moves the MAP by 0.3 to 2.9 log-likelihood units per outer (out of 2e5), so two consecutive outers under 0.5 are rare. A threshold of about 3 would end it at once, at a cost of up to 3 units of unresolved MAP (a few posterior standard deviations in total over 10^4 parameters); that threshold is not validated and `move_tol` stays opt-in. The cycle itself (a damping or freeze of a τ whose effect is below 0.01) is the clean fix and is **not done**.
- **Not finished when this entry was written** (outputs land in `data/perf/out/`): `lept_M2` (the gate removed), `sihX_M` (SIH X monthly 2010-2023, GPU, warm start from the 2010-2014 monthly fit, `mean_tol` 1, `move_tol` 0.5). Its first outers, 145-160 s each, reached objective 37,227,532 at outer 2, below the legacy fit's final 37,229,757 at outer 39 (different τ's, so only indicative); the earlier run with the Anderson mix (`sihX_E`, killed at the 30-minute background limit after 6 outers) was at 37,227,555 at outer 4 with max τ change 0.16. The legacy fit took 9,263 s for 40 outers.

## BlockData cache

`monolith.assemble` is memoised in the store (kind `blockdata`). Verified equal to a fresh assembly field by field, dtype by dtype, with the same monolith store address, on SINAN-LEPT monthly, SIM.DO III, IX under account-3, and a SINASC mark block. A hit reads in 0.6-1.0 s against 5-6 s with a warm gateway; the cold assembly of SIH X monthly (10.7 M cells) was 467 s. Concurrent writers of one address collided on Windows (PermissionError on a shared temporary name); `store` now writes a per-process temporary and tolerates a lost race.

## Projection for the queue's mix

Per fit, from the measured ratios (XVI: 36 to 5-7 outers, CG 5.9k to 2.1k) and not from the multiplicity yet run:
- a variant of a stored fit (train to full, exposure, split, rolling origin) costs about a third of a cold one: 0.35 of the CG work, 5-7 outers instead of 30-40;
- the 3.5-6 minute births block, the 11-28 minute IX annual and the refits of XX behave as XVI: a second and later variant at 0.3-0.4 of the first;
- the SIH X monthly: a warm start from the 2010-2014 monthly fit begins at the legacy fit's final objective by outer 2 (about 5 min); whether it then stops before the 40-outer cap depends on `sihX_M` (above), so no saving is claimed for it yet.

## Where a small block's time goes (2026-10-06)

cProfile of two outers on SIM.DO VII 2010-2021 (277 deaths, 47 leaves, lattice 5,570 × 12 × 36), CPU, 2 threads, machine shared: 24.6 s, of which Hessian-vector products 15.7 s (102 products, double backward through the factorised total, 0.15 s each against 0.02 s for one forward `total`), Fellner-Schall traces 3.2 s, everything else under 2 s. The cost is the lattice, not the events: a block of 277 deaths pays nearly what one of 150,000 does. Forward-over-reverse (`torch.func.jvp` of the likelihood's gradient, the penalty's τQv analytic, since forward AD has no sparse product) is 0.43 s against 0.51 s per product on the same loaded machine, 15% and not adopted. The objective is Poisson in η, so its Hessian is already Jᵀdiag(μ)J and the double backward computes that product through the same marginal sums as the total; an analytic product would do the same arithmetic, so no large gain is expected from the derivative route. What would cut it is fewer products (a better preconditioner, measured no better in block-Jacobi form above) or a smaller lattice for small blocks (the places with no event in any year of the block carry only the total's term; untested).
