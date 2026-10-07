# O7 design: relations as one joint model (stage D)

**Status:** implemented (`relations.py`, `pegasus-core relations`; ARCHITECTURE §7.5); this file is the design record. Was: design for the author's review before the build (ARCHITECTURE §7.5, ADR-0029). It replaces pairwise relation search with one joint model of all fields' departures.

## The question and why not pairs

Which fields move together over places and time, and which lead which?
- With F fields, the pairwise search is F² × L lag tests. For F ≈ 2,000 (every ICD block of every system), that is ~4·10⁶ × L, with the multiplicity this implies.
- Shared drivers (season, utilisation, epidemics, coding regimes) make most pairs correlate spuriously.

The established answer is a **latent factor model**: a few shared space–time signals, each field loading on them, possibly with a delay. Two literatures supply it:
- spatial dynamic factor analysis (Lopes, Salazar & Gamerman 2008);
- shared-component and multivariate disease mapping (Knorr-Held & Best 2001; Gelfand & Vounatsou 2003, MCAR).

Relations are then read from the loadings, and the cost grows with the number of factors K, not with F².

## The model

**Data from the stages before.**
- For every field f, its departures from the expectation (stage B) at place u and period t: the log ratio r_{f,u,t} = log((y + ½)/(μ + ½)).
- Its sampling variance v_{f,u,t} comes from B's predictive, noise structure included (N1).
- Fields at a monthly grain enter at their own grain; annual fields enter at the annual grain, with monthly factors summed to years.

**Structure.**

```
r_{f,u,t} = Σ_k Σ_{ℓ=0..L} λ_{f,k,ℓ} · F_{k,u,t−ℓ} + ε_{f,u,t},   ε ~ N(0, v_{f,u,t} + σ_f²)
F_k        : a space–time field, ICAR over the graph × RW1/AR(1) over time (a separable GMRF), unit scale
λ_{f,k,ℓ}  : loadings over lags, a horseshoe prior (most are zero), RW2 smoothing across ℓ within (f, k)
```

- **A relation** is two fields loading on one factor.
  - Both at lag 0: they move together (shared geography and timing).
  - One at lag 0 and the other at lag ℓ > 0: the second follows the first by ℓ periods. That is the distributed-lag link, now found inside the joint structure.
- **Interpretation stays out** (P16). A shared factor is a statistical relation. Whether it is causal, a shared driver or a shared recording artefact is stage E's question, read with negative controls (time-reversed lags, unrelated outcomes).

## Estimation

- **Alternating Laplace**, as the place × time interaction ψωτ is already fitted:
  - given the loadings, the factors are a sparse GMRF problem (precision: graph × time, plus the loadings' data term), solved by the sparse Cholesky of O1;
  - given the factors, each field's loadings are a small penalised regression, independent across fields, so they run in parallel.
- **K is chosen** by the marginal likelihood and held-out departures, growing K until the evidence stops rising.
- **Scale.** K·U·T factor unknowns: K = 20, U = 5,570, T = 14 gives 1.6 M, sparse. For a monthly T = 168, the factors run at the regional grain (≈ 500 immediate regions). Loadings are F·K·(L+1) scalars. Each sweep costs one factor solve per k and F small regressions.
- **Departure-aware.** The data are B's departures, so seasonality, trends and place levels are already the expectation's, and a factor cannot be a shared season.

## Output and control

- **Relation leads:** a pair (or group) of fields, the factor, the lags, and each loading's posterior inclusion probability.
- **Reporting:** with the Bayesian FDR of §8.2 over all loadings.
- **The pairwise confirmation** (`relations.distributed_lag`) re-estimates a reported lag curve on the two fields directly, and the declared positives are checked:
  - arbovirus notifications → microcephaly births (lags 5–9);
  - cold → respiratory admissions.

## Characterisation (the bench)

- **Planted relation worlds:** a factor injected into chosen fields with chosen loadings and lags (ARCHITECTURE §10.3's lagged plant).
- **Null worlds:** fields drawn independently from their predictives with N1 noise.
- **Measured:** recovery of planted loadings and lags; false relations per world; the dependence on K.

## Build order

1. The departures matrix: r and v for every field of the fitted blocks (SIM, SIH, SINASC, SINAN), at annual and monthly grains, from B's predictive.
2. The factor model with lag-0 loadings only. Check recovery on planted worlds, then the real map at small K.
3. Lagged loadings, the horseshoe, then the Bayesian FDR.
4. The declared positives as confirmations, then the bench.
