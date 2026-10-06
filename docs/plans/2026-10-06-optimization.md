# Speed: review and plan (2026-10-06)

**Requirement (author, 2026-10-06):** blazing speed, and no resumption of development on unoptimised mathematics or code. This file is the design of work package O1 (ARCHITECTURE §5.3–5.8, §12) and of the speed work spread over the other packages. Every number below is measured unless it is marked as a target.

## 1. Where the time goes now

**The machine:** 20 logical cores (14 physical), 33.9 GB RAM, RTX 4050 Laptop (6 GB, CUDA 12.1).

**Measured on a calm machine** on 2026-10-06. Block: SIM.DO IX 2010–2021, with U = 5,570 places, T = 12, G = 36, E = 77 leaves, K = 10 groups, 2.07 M non-empty cells, 552,046 parameters. One call each:

| device, precision | total Λ | Hessian–vector product (autodiff double backward) |
|---|---|---|
| CPU float64, 8 threads | 2.8 ms | 26.7 ms |
| GPU float64 | 2.1 ms | 18.9 ms |
| GPU float32 | 0.7 ms | 13.1 ms |

**Measured in production.**

| quantity | value | source |
|---|---|---|
| CG iterations (= Hessian–vector products) in one IX fit | 6,004 | rank sweep, R = 2 |
| Newton steps at the 50-iteration CG cap | 16 of 30, each gaining < 10⁻³ | profile, 2026-10-06 |
| outers per fit (Fellner–Schall) | 12–40 | fit logs |
| the same product under the 2026-10-05/06 load (six jobs, 2–4 threads each, 2 GB free) | 150–500 ms, 5–20× the calm figure | profiles |
| cold IX fits under that load | 664–1,683 s; warm 191 s | exposure fits |
| SIH chapter fit | about 1 h | logs |
| one SIM chapter survey (III, 21 fields) | 384 s, then 65 s after the 2026-10-05 changes; still Python-bound (scalar optimiser, per-place refits) | evaluation 2026-10-05, survey throughput |
| expectation tiers on IX | B0 13 s, B1 3 s, B2 2 s, BP 15 s per node | exposure evaluation |
| assembling a block | 10.6 s (103 s before 2026-10-05); cached 0.6–1.0 s | survey throughput |
| SIH role tables rebuilt from compressed files | hours (the linkage, 2026-10-05) | linkage handoff |

**Reading the numbers.** A fit's cost is roughly

```
outers × [ Newton steps × ( CG iterations × HVP + line search × Λ ) + strength update ]
```

Today that is about 6,000 Hessian–vector products. That makes 160 s calm and 15–30 min under load. Three factors multiply:

1. **Too many iterations:** a diagonal preconditioner on an ill-conditioned problem, and a linearly converging fixed point outside it.
2. **Too much per iteration:** a product costs about 20 forward passes of the total. On the GPU in float32 the forward pass is 0.7 ms and the product 13 ms, so the product is **overhead-bound**: autograd's graph and many small kernels, not arithmetic.
3. **A machine competing with itself:** 5–20× from contention alone.

**The tools.**
- **Precision:** float64 everywhere (`Monolith.dtype`). On this GPU, float64 arithmetic runs at about 1/64 of float32's rate. Memory-bound passes pay twice the bytes.
- **Device:** most fits ran on the CPU. `fit_blocks` defaults to the CPU; the SINAN driver forces it.
- **`torch.compile` does not run here** (no Triton, no compiler toolchain on this Windows install; tested 2026-10-06).
- **Available on conda-forge for this environment:** scikit-sparse 0.5.0 (CHOLMOD, SuiteSparse 7.10) and CuPy 14.

## 2. Principles

1. **Iterations first, then cost per iteration, then constants.** A direct solve that removes 6,000 products beats any kernel tuning.
2. **No autograd in the hot path.**
   - The objective is Poisson in η, so its gradient is Jᵀ(y − μ) (sufficient statistics minus marginals) and its Hessian is JᵀWJ.
   - Both are **contractions of the factorised μ**, written once by hand and checked against autodiff.
3. **Eliminate in closed form everything the structure makes diagonal.** Factor only what is coupled.
4. **Only the contractions grow with the lattice; the factorisations do not.** Race and finer ages multiply G (§6). The design keeps that growth in passes that are linear in the lattice.
5. **float32 for the lattice's contractions on the GPU, float64 for accumulations and factorisations.** Every change of precision is checked against the float64 optimum.
6. **The machine is scheduled, not shared.** One GPU job at a time. CPU jobs get explicit thread counts summing to the cores. Memory is reserved. A heavy job never starts beside another heavy job unless both fit.
7. **Measured, or it does not count.** The benchmark (§7) runs on every change to these paths. A change that slows a benchmark block by more than 10 % is rejected unless its reason is recorded.

## 3. The model's structure, written for the solver

**For one block,** with k = k(e) a leaf's group:

```
LP[e,u]      = exp(b0 + θ_grp[k] + θ_cat[e] + v[e,u])                                    E × U
PT[k,u,t,g]  = exp(h_all[t] + h_grp[k,t] + s_all[u] + v_all[u] + s_grp[k,u] + v_grp[k,u])
               · N[u,t,g] · exp(f_all[g] + f_grp[k,g])                                   K × U × T × G (never formed)
μ[e,u,t,g]   = LP[e,u] · PT[k,u,t,g]
```

**Every gradient and Hessian entry is a sum of μ** over the cells two parameters share. The marginals needed, all from GEMMs and contractions of N with the exponentiated factors:

| array | definition | size (IX) | what reads it |
|---|---|---|---|
| P[k,u,t] | Σ_g PT | 668 k | v–h couplings; total |
| m[e,u] | LP · Σ_t P | 429 k | the v diagonal; v–place couplings; θ |
| M[k,u] | Σ_{e∈k} m | 56 k | place-block diagonal |
| A[k,u,t] | (Σ_{e∈k} LP) · P | 668 k | place–h couplings |
| B[k,u,g] | (Σ_{e∈k} LP) · Σ_t PT | 2.0 M | place–f couplings |
| C[k,t,g] | Σ_u (Σ_{e∈k} LP) · PT | 4.3 k | h–f couplings |

- **Total cost:** O(K·U·T·G) for B and C, O(E·U·T) for the rest. That is the cost of one evaluation of Λ: a few ms.
- **f is diagonal in g, and h in t.** A cell has one age-sex group and one period, so f[g] and f[g'] share no cell, and neither do h[t] and h[t'].

## 4. The v1 solver

### 4.1 Exact Newton on the block-arrowhead Hessian

The classes of ARCHITECTURE §5.3: leaf-place **v** (E·U), place **ℓ_u** (2 + 2K per place, plus R for the interaction's ω), and global **γ** (b0, θ, f, h, season, the interaction's ψ and τ).

1. **Eliminate v in closed form.** H_vv is diagonal: d[e,u] = m[e,u] + τ_v. Each v[e,u] couples only to its own place's variables of its own group and to its leaf's and group's globals. So the Schur complement's update is a sum over (e, u) of rank-one terms whose vectors are rows of LP·P and LP·Σ_t PT.

   **Collapsing the update.** Every update collapses to a weight per (k, u):

   ```
   q[k,u] = Σ_{e∈k} LP[e,u]² / d[e,u]
   ```

   times the same factor arrays. For example, the h–h update is `einsum('ku,kut,kus->kts', q, P, P)`.

   The cost is O(K·U·(T + G)²): about 10⁸ operations for IX, milliseconds on the GPU. **No E·U × γ matrix is ever formed.**
2. **The place system.**
   - After elimination, each place's block (2 + 2K + R) has arrowhead structure itself: the "all" variables over the group variables, diagonal in k.
   - Places couple only through τ·Q_ICAR on s_all and s_grp: K + 1 copies of the 5,570-node municipal graph, tied together within each place.
   - **Sparse Cholesky by CHOLMOD:**
     - the symbolic analysis (ordering, supernodes) is done **once per block**, because the pattern does not change across Newton steps or outers;
     - each step does only the numeric factorisation.
3. **The globals by Schur complement.**

   ```
   S_γ = H_γγ − H_γℓ H_ℓℓ⁻¹ H_ℓγ
   ```

   - The solve with H_ℓℓ takes |γ| right-hand sides at once (BLAS-3 triangular solves with the supernodal factor), on the GPU where they fit.
   - S_γ is dense (616 for IX annual), factored densely on the GPU.
   - **Alternative, kept if measured faster:** CG on S_γ with the place factor inside, preconditioned by S_γ's diagonal plus its low-rank part. This is the option for large γ (§6).
4. **Back-substitution** gives the exact Newton step, under the existing Armijo line search.
   - **Quadratic convergence:** 3–6 steps from a cold start, 1–2 from a warm one (target, O1.0).
5. **Constraints.**
   - Local ones (group deviations summing to zero, leaves centred in their group) by contrast bases inside the place blocks.
   - The few across places (ICAR sum-to-zero per component) by conditioning by kriging on the factor.
   - The singular directions (b0 against s_all, BYM's two parts) disappear with BYM2 and the contrasts. A ridge of 10⁻⁸ is the only numerical guard.

### 4.2 The strengths: LAML with exact derivatives

- ρ_j = log τ_j by **BFGS (or Newton) on the Laplace approximate marginal likelihood**, from the previous fit's ρ.
  - The value: ℓ(x̂) − ½x̂ᵀQx̂ + ½log|Q|₊ − ½log|H|.
  - log|H| comes free from the factors: the place factor's diagonal, the Schur part's Cholesky, and Σ log d for the eliminated v.
- **Gradient:** ½[rank_j − τ_j x̂ᵀQ_jx̂ − τ_j tr(H⁻¹Q_j)]. The traces come by **selected inversion**:
  - **v-block:** diag(H⁻¹)_vv = 1/d + (the place and global entries of H⁻¹ on each v's couplings)/d². This needs only the inverse's entries on the place blocks and the global block.
  - **Place system:** the Takahashi recursion on CHOLMOD's factor converted to simplicial LDLᵀ, written in numba. Or an existing selected-inversion routine if one installs: to check in O1.0.
  - **Global block:** dense.
  - **Fallback, if selected inversion is not ready:** Hutchinson probes **solved exactly with the factor**, at two triangular solves each instead of a CG.
- **Target:** 5–10 outers, against 12–40. A converged fit's ρ starts every related fit (warm), as today.

### 4.3 What is removed

Once v1 reaches the v0 optimum on the benchmark:
- the CG loop;
- `_trace_inv_times`;
- the Anderson mix on the fixed point;
- the `move_tol` ridge workaround;
- the double-backward Hessian–vector product (kept only as a test oracle in the benchmark script).

## 5. The rest of the pipeline

| stage | today | v1 | target |
|---|---|---|---|
| **gateway, assembly** | 10.6 s per block; cached 0.6–1.0 s; SIH role tables rebuilt from compressed files in hours | the lake (Parquet) and pegasus_data's aggregate cubes materialised once in the core data home for SIM, SIH, SINASC and SINAN; BlockData stored float32 | < 2 s per block cold from the lake; never a decode in an analysis |
| **dispersion φ** | about 14 evaluations of about 1 s, streamed per leaf | a 1-D Newton on the GPU over the same slabs, float32 with float64 sums; the empty cells' term from the factorised marginals | < 1 s |
| **tiers** | B0 13 s, B1 3 s, B2 2 s, BP 15 s per node under load (2026-10-05); calm, 0.8–1.2 s per node, half in the field's place-year φ (32 scalar searches) and the KS tests (2026-10-06) | **every node of a block at once**: the node-level μ is a sparse aggregation matrix [nodes × leaves] times the leaf cube; B2 is a 2 × 2 Newton per (node, place), vectorised; BP from the same factor's draws | a block's tiers for all nodes < 10 s |
| **PIT, surprises** | per field, NB CDFs on the CPU | vectorised over all nodes and cells (scipy's C kernels, or the GPU's regularised incomplete beta); seeded draws in batch | a chapter < 5 s |
| **scans (screens)** | 2.5–3.7 s per field; Python-bound; R = 200 replicates for nulls | one null set per field shared by its lenses; the scalar optimiser and `refit_place` vectorised across fields; nulls only for screens, since departure models (O6) infer from posteriors | a chapter survey < 2 min; all SIM < 30 min |
| **departure models (O6)** | none | fitted on aggregate cells with the same solver; the per-place mixtures vectorised | a field < 1 s |
| **pairs, maps** | Gram matrix on the GPU (built) | unchanged | as is |
| **replication, triage** | facility cubes re-read per lead | cubes cached per block, the per-lead reads vectorised | the re-triage of the 33 k-lead register < 30 min |

## 6. Race and finer ages: keeping the growth linear

**The growth.** Revision 2 adds race (5) and finer child ages (single years 0–19, ARCHITECTURE §3.4). So G grows from 36 to about 33 ages × 2 sexes × 5 races = 330, about 9×.

| what | how it grows | IX estimate |
|---|---|---|
| the contractions of §3 (total, gradient, Hessian blocks) | linear in G | about 25 ms on the CPU in float64, about 6 ms on the GPU in float32 (from §1) |
| the place system | unchanged: race and age enter the place blocks only through race × place contrasts at a **coarse** scale, which join the globals | — |
| the global block | f_grp becomes K × G = 3,300, plus f_all and the race contrasts: γ grows from 616 to about 4,000 | O1.0 decides |

**How γ is kept cheap, by priority:**
1. **The profile as a Kronecker GMRF.** f = age RW2 (irregular spacing) ⊗ sex ⊗ race, with race × age deviations on a coarser age grid. Fewer free parameters for the same lattice.
2. **The Schur complement by CG** (§4.1, step 3), preconditioned by the block-diagonal of S_γ: f is diagonal in g within the data part, so S_γ's f-block is diagonal plus low rank.
3. **The dense Schur on the GPU** (4,000² float64 is 128 MB): about 21 GFLOP per factorisation. That is about 0.1 s on this GPU in float32-with-refinement, or a few seconds in float64. Use the first only if refinement holds the optimum.

## 7. The benchmark

**`bench`** (O1.0 builds it first, before the solver). It is a script: fixed blocks, cold and warm, written to `data/bench/<date>-<commit>.json`, and summarised in an evaluation entry when a solver path changes.

| block | why |
|---|---|
| SIM.DO VII 2010–2021 (277 deaths) | tiny: fixed costs |
| SIM.DO IX 2010–2021 annual | the reference |
| SIM.DO IX with race × fine ages (after O3; until then a synthetic G = 330 lattice with IX's events spread by the tensor's race and age shares) | the growth of §6 |
| SIH-RD X 2010–2023 annual | large E and K |
| SINAN-DENG 2010–2023 monthly | large T, the monthly γ |
| SINAN-TUBE 2010–2023 | it hit the 25-outer cap in v0 (2026-10-06) |

- **Recorded per block:** wall time; outers; Newton steps; factorisations; time in assembly, factorisation, solves, line search, LAML; peak RAM and GPU memory; the objective and every τ at the optimum.
- **Acceptance of v1:**
  - the v0 optimum (objective within one log-likelihood unit, τ's within tolerance);
  - the same calibration (KS within 0.005);
  - the same leads on the chapter III survey.

**Targets.** They replace ARCHITECTURE §5.8's first budgets, calm machine, cold / warm:

| block | target |
|---|---|
| VII | 2 s / 1 s |
| IX annual | 20 s / 5 s |
| IX race × fine ages | 90 s / 20 s |
| SIH-RD X annual | 2 min / 30 s |
| DENG monthly | 2 min / 30 s |
| all 19 SIM chapters | 10 min |
| all 20 SIH chapters | 30 min |

O1.0 measures the parts (assembly, factorisation, Schur, LAML iterations) on the real IX pattern and either confirms these targets or revises them with the reason.

## 8. Order of work in O1

| step | what | done when | status (2026-10-06, evaluation solver v1) |
|---|---|---|---|
| O1.0 | **Spike and benchmark:** install scikit-sparse (CHOLMOD) and CuPy; `bench`; build the IX place system's real sparsity pattern; time CHOLMOD's symbolic and numeric factorisation, the multi-RHS Schur, and a dense 4,000² factorisation; check the arithmetic of §3 against autodiff | numbers recorded; targets confirmed or revised | done: CHOLMOD supernodal; CuPy measured and dropped (the CPU wins in float64) |
| O1.1 | the analytic gradient and the assembled Hessian (§3), float32 contractions with float64 accumulation | equal to autodiff to 10⁻⁸ relative (float64) and 10⁻⁵ (mixed) on VII, IX, DENG | done in float64 (gradient to 10⁻¹⁴); float32 not adopted |
| O1.2 | elimination, place factorisation, Schur, exact Newton; BYM2; contrasts and kriging | IX optimum equals v0's; Newton steps ≤ 6 cold | done but BYM2: the IX optimum is below v0's; IX cold 6 outers, 9 Newton steps |
| O1.3 | LAML with selected inversion (or the exact-solve Hutchinson fallback) | τ's equal to v0's converged ones; outers ≤ 10 | done with Hutchinson probes (selected inversion measured, not adopted); safeguarded Newton on log τ; IX 6 outers |
| O1.4 | uncertainty from the factor; removal of the v0 path (§4.3) | Laplace marginals equal to v0's draws within their Monte-Carlo error | done: exact Laplace draws (projections within Monte-Carlo error of aᵀH⁻¹a); v0 retired |
| O1.5 | the pipeline of §5: lake materialisation, all-node tiers, vectorised PIT, φ on the GPU | chapter tiers < 10 s; chapter survey < 2 min | φ binned (4 s against 14); the rest open |
| O1.6 | scheduling (§2.6): `heavy.py` with a GPU slot of one, thread counts, memory reservations | no measured contention between two concurrent jobs | `heavy.py` thread counts and the GPU slot built; contention not measured |

Each step's measurement goes into one evaluation entry for O1, written when O1 closes (documentation weight: one entry, not six).

## 8b. Measured so far (2026-10-06, evaluation 2026-10-06, solver v1)

| block, cold | v0 | v1 | held-out deviance per event (v0 / v1) |
|---|---|---|---|
| SIM.DO IX 2010–2021 | 664–1,683 s under load (12–40 outers) | **154 s, 6 outers** (about 5.6 s mean fit and 9.4 s strengths per outer) | 2.21851 / 2.21828 |
| SIM.DO VII 2010–2021 (277 deaths) | — | 395 s, 17 outers; h_all and v_all run to their bounds | — / 18.2 |

**What VII shows.** A block with very few events pays the full lattice's fixed cost (E·U leaf-place parameters, every probe over them), and its weakly identified strengths bounce off the ×10 clip. Two model changes are measured before adoption, by held-out deviance:
1. **Leaf-place terms only where identifiable: measured and rejected.** v_cat restricted to leaves with ≥ 0.1 % of the block's events and ≥ 100 events kept 42 of IX's 77 leaves (99.4 % of deaths). Held-out deviance went 2.21828 → 2.21934 (worse by about 840 units over 788 k deaths), and the time 169 → 160 s: the rare codes' place deviations predict, and the per-outer cost is the probes, not E·U. On VII (none qualify) held-out went 18.21 → 19.95. The option was removed.
2. **A weak prior on log τ.** N(0, 3²) on each ρ, which barely moves the identified strengths and keeps the flat ones from wandering.

**IX under ADR-0024** (block profiles, group geography): 37 s cold on a calm machine, 5 outers, 11 Newton steps (from 59–71 s by the group carrier). Profiled at 4 threads beside a fit (72 s):

| part | share |
|---|---|
| factorisations (9) | 43 % |
| – their rank-k update | 1.5 s each |
| – B's construction | 1.1 s each (0.3 s of it the write in factor order) |
| the strengths' probe solves | 25 % |
| the arrowhead's dense Y products | 16 % |
| the closing dispersion | 8 % |

B's construction became a column copy (the feature map has weight-1 entries only; the Newton step is unchanged to 10⁻⁹). The supernodal solves had rescanned the process's libraries through `threadpool_limits` at every call (36 ms each, 2 s per fit); one cached controller removes it. The next levers are the factorisation count (9 for 11 steps) and the probes.

**IX at the day's end** (every default of ADR-0024; 10 threads beside one O2 fit): 35.1 s cold.
- 4 outers end at 27 s: the mean 7.7, 4.5, 2.5 and 2.5 s; the strengths 2.4 s each. The closing mean and φ take the last 8 s, the binned dispersion pass 3 s of them.
- The closing mean now runs to the fit's own tolerance (1 unit, not 0.001): 37.6 → 35.1 s, held-out unchanged (−1.63304).
- The 20 s target needs the core's ~2 s Newton step and 2.4 s strengths update halved, which is to be profiled on a calm machine.
- Scoring probes 16 → 8 on blocks of 100 k events or more (`data/probes_*.log`): IX 48 → 31 s and XX 197 → 186 s, held-out equal to 1e-5. VII kept at 16: with 8 its held-out fell by 0.17 per death.
- The interaction's Hessian terms (`_active_terms`) by per-group sums and BLAS Gram products: 1.38 → 0.29 s a call. Rank-1 IX takes 178 s (36 Newton steps); a chord start after its sweeps was slower (228 s) and was dropped.

**SIH-RD 2010–2023 refits under ADR-0024** (warm-started, beside three to five other jobs; `data/logs/refit3_sih_2023.log`):
- 16 chapters took 1,013 s; most took 8–80 s, I 133 s and XIX 282 s (23 groups, none under the pooling share);
- all 20 SIH chapters are within the 30-minute target, on a loaded machine.

## 9. Risks and their fallbacks

- **Selected inversion in Python.** No maintained Python binding exposes it. The fallback is Hutchinson probes with exact factor solves: the LAML gradient's noise is then √(2/S) of the trace, and BFGS tolerates it with S = 30.
- **CHOLMOD on Windows** is a conda-forge build (SuiteSparse 7.10). If it misbehaves, the fallbacks are SuperLU (scipy) on the same pattern, slower by a measured factor, or CuPy's cuSOLVER.
- **float32 contractions.** The sums over 10⁸ cells lose precision. Accumulation stays float64 (pairwise or chunked); the benchmark's optimum check catches any drift.
- **The interaction ψωτ** is not linear in its factors. Its Gauss–Newton blocks enter as in v0: ω joins the place blocks, ψ and τ the globals. Its rank's cost is measured in the benchmark as R grows.
