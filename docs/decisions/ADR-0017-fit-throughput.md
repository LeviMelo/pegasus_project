# ADR-0017: A fit starts from its nearest stored relative, its mean stops at one log-likelihood unit per outer, and the assembled cells are cached

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-fit-throughput.md`: SIM.DO XVI 2010-2019, cold with the mean tolerance 36 outers and 5,905 CG iterations, warm 7 and 2,119, the same φ (9.807 / 9.797) and μ to 5e-4 (RMS log); the legacy loop had not converged at 33.

## Decision

1. **Warm start (`Monolith.fit(warm="auto")`).** A fit starts from the best related stored fit: the same dataset, event, block, graph, profile, source and grain, preferring the same exposure and split, then the most years in common. Parameters are carried where shapes agree, histories shifted onto the shared periods, every τ. A start changes where the iteration begins, not what it converges to; a wrong or stale relative costs iterations only. Batch fits (`scripts/fit_blocks.py`, side-A fits) use it; `PEGASUS_FIT_COLD=1` turns it off.
2. **The mean fit of an outer stops at `mean_tol` = 1 log-likelihood unit** (a shift of about one posterior standard deviation in total); the parameters persist across outers and the last fit after the loop runs to the full tolerance. The old tolerance (1e-9 of the scaled objective) was never met inside 30 Newton steps.
3. **Convergence.** Optionally (`move_tol`, 0.5 log-likelihood units in the evaluation; off by default) a fit also stops when two successive τ updates each moved the MAP by less than that: a τ on the edge of identifiability cycled for 120 outers on SINAN-LEPT monthly with the fit unchanged. Anderson acceleration of log τ (depth 4, fixed point unchanged) is also opt-in; with the noisy inner solves of the monthly grain it wandered. The summary records `converged`, `stop_reason` and `outers`; a fit that reaches its cap says "NOT CONVERGED".
4. **`monolith.assemble` is memoised** in the store (kind `blockdata`), keyed by its arguments, the data version, the population key and content hash, and the hash of the assembly and gateway source.

## Not decided

- A block-Jacobi preconditioner for Newton-CG was measured and is no better than the diagonal; not adopted.
- The coupling of the BYM pair (s, v) in the Fellner-Schall update (the slow τ's of SIH X monthly) changes the fixed point; left open.
- Acceleration and the movement stop are opt-in until the monthly runs (evaluation, last section) justify a default.
