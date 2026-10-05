# ARCHITECTURE.md: PegaSUS

**The authority on what PegaSUS is, its mathematics and its code.** Accepted by the author on 2026-10-04 (ADR-0002). It supersedes the design drafts (`docs/discussion/2026-10-04-design-v0.2.md` holds the reasoning behind each choice). When code and this document disagree, one of them is wrong: fix it, or record the departure in §13.

Section map:

| § | contents |
|---|---|
| 1 | purpose and principles |
| 2 | the repositories and their boundary |
| 3 | objects |
| 4 | the monolith: model |
| 5 | the monolith: estimation and computation |
| 6 | expectation tiers, calibration, surprise |
| 7 | scans |
| 8 | error control, replication, admission |
| 9 | leads, the ledger, use |
| 10 | the validation harness |
| 11 | code: package, artefacts, invariants |
| 12 | phases and gates |
| 13 | departures |

---

## 1. Purpose and principles

Brazil's health data are observations of one **marked point process**: events (deaths, births, hospitalisations, notified cases) happening to persons, at places, at times, each carrying attributes (marks).

PegaSUS:
- **fits one hierarchical model of that process,** the **monolith**, "normal Brazil", from all the data it reads through pegasus_data;
- **reads leads from it:** where the data depart from it (§7.1–7.3), what its own structure shows (§7.4), how departures relate (§7.5–7.6);
- **serves those readings** to people and to AI agents (§9).

Leads are statistical objects, not conclusions.

**Principles.** Each answers a documented failure of the 2026 engine (`docs/discussion/2026-10-03-what-was-built.md`).

| # | principle |
|---|---|
| P1 | **Expectation first.** Every quantity is judged against a model of what it should be given population, place, time and case-mix. No statistic runs on a raw or pooled-rank-transformed value. |
| P2 | **Events and their marks are modelled, not correlations of columns.** |
| P3 | **Every cell carries its information** (§6.3), and every statistic uses it. |
| P4 | **Estimands are declared.** Between places, within places over time, between groups, between institutions: separate statistics, separate nulls. |
| P5 | **Effects are tested against a minimum relevant effect,** and the multiplicity of the whole search is designed before it runs. |
| P6 | **Structure priors act on levels, never on relations.** Taxonomies never decide which quantities may co-vary. |
| P7 | **Every strength is learned or measured.** No unmeasured constant is a gate. |
| P8 | **Observed stays observed.** Modelled inputs come from pegasus_data's modelled tier, typed, with uncertainty. |
| P9 | **Nothing is trusted before the harness** (§10) has scored it on real data. |
| P10 | **No dense object larger than the population tensor** is ever built (§5). |

---

## 2. Repositories and boundary

| repository | role | answers |
|---|---|---|
| **pegasus_data** (`../pegasus_data`, open source) | the data module of the whole project | *what exists and what it means* (observed tier); *what was there and how it was recorded* (modelled tier: population account, system completeness, race misclassification, SUS-dependent population) |
| **pegasus_project** (this repository; package `pegasus_core`) | inference | *what is normal, what departs from it, what relates* |
| **pegasus_view** (`../pegasus_view`) | the frontend | presentation of pegasus_data and, later, of leads |

**Rules:**
1. **Every input reaches PegaSUS through pegasus_data's public API.** One module (`pegasus_core.gateway`) imports pegasus_data. Nothing else does.
2. **A capability that is meaning or data belongs in pegasus_data,** and is requested there (`docs/handoffs/`), never re-implemented here. The test for a doubtful case: *would an epidemiologist who never uses PegaSUS want this as data?*
3. **PegaSUS never writes into pegasus_data's home.** It has its own home (§11.3).

---

## 3. Objects

### 3.1 From pegasus_data (consumed)

| object | what PegaSUS uses |
|---|---|
| **role** | `entity.property`, value kind, and model role (stratum, dimension, event type, mark, when, where, institution, link-only, excluded) of every column |
| **event type** | (dataset, grain, kind, classifiers with role, status, consolidation) |
| **structure** | a shape over a variable's values: tree (parent table), list (membership table), ordinal, cyclic, with validity windows and crosswalks |
| **graph** | a proximity graph over places or institutions: edges (from, to, weight, kind, vintage) |
| **population** | person-years N by place × year × age × sex (× race), with uncertainty; the SUS-dependent variant; completeness by system, place and year |
| **aggregates** | sparse non-empty cells of counts per event type and lattice; mark accumulator states (n, Σm, Σm², Σlog m, Σ(log m)², histogram on declared bins) |
| **records and linked persons** | for cohort scans and agents |

### 3.2 Defined here

**Lattice cell.** `c = (u, t, g)`:
- u, a place (municipality, comparable area or health region);
- t, a time (year, or month for dense families);
- g, a group: age band × sex (× race).

The **population tensor** P = U × T × G holds N_c.

**Field.** A projection of events onto a lattice:

```
Field
  id, family          node of the event type in its classifier structure
  kind                count | mark (with its summary) | share | level (context)
  event_type, classifier_role
  lattice, grain, groups
  support             observed cells (non-empty cells for counts; observed cells for context)
  law                 sum | ratio_of_sums | weighted_mean(weight) | none
  exposure            population variant (all residents | SUS-dependent) and completeness term
  signature           the predicate defining its events (for measured overlap, §8.5)
  provenance          pegasus_data data version, query
```

**Block.** A subtree of a classifier structure fitted together: an ICD-10 chapter, a SIGTAP group.

**Monolith.** The parameters of §4 for all blocks, with their posterior summaries. Versioned (§11.3).

**Tier.** A nested version of the monolith (§6.1).

**Surprise.** For a field, tier and cell: (y, μ, z, w, flags) (§6.3).

**Scan, test, hypothesis.** A statistic over surprises or parameters, with its null, family and estimand (§7–8).

**Ledger entry.** A test recorded **before** it runs (§9.2).

**Lead.** A test result admitted by error control, with its replication, robustness and provenance (§9.1).

---

## 4. The monolith: model

### 4.1 Observation model for counts

For event type e (a leaf of its classifier structure) and cell c = (u, t, g):

```
y_{e,c} ~ NegBin( mean μ_{e,c}, dispersion φ_b )            Var = μ + μ²/φ_b ,  b = block of e
μ_{e,c} = κ_{s(e),u,t} · N^{(v(e))}_{c} · exp( η_{e,c} )
```

| symbol | meaning | source |
|---|---|---|
| **N^{(v)}_c** | person-years of population variant v: all residents (SIM, SINASC, SINAN) or SUS-dependent (SIH, SIA) | pegasus_data. Phase 1: POPSVS with the variant's correction where available. |
| **κ_{s,u,t}** | completeness of system s (1 where unmodelled) | pegasus_data modelled tier |
| **groups with race** | the expected *recorded* count by recorded race k is `μ^{rec}_{e,(u,t,a,s,k)} = Σ_j C_σ(k|j) · μ_{e,(u,t,a,s,j)}`, with C_σ the setting's confusion matrix | pegasus_data modelled tier |

### 4.2 Linear predictor

```
η_{e,c} = θ_e                                   level of e
        + f_{p(e)}(a, s)                          age–sex profile, carried by the profile node p(e)
        + g_e(u)                                  geography
        + h_e(t)                                  history (trend; season for sub-annual grains)
        + Σ_{r=1..R_b} ψ_{e,r} ω_{b,r}(u) τ_{b,r}(t)   low-rank place × time interaction of the block
```

- **Structured effects along e.** Every e-indexed effect is a sum along e's path in its structure, plus the lists e belongs to:

  ```
  θ_e    = Σ_{n ∈ path(e)} θ_n + Σ_{L ∋ e} θ_L
  g_e(u) = Σ_{n ∈ path(e), ℓ(n) ≤ ℓ_g} g_n(u)        (geography carried down to a declared level ℓ_g)
  h_e(t) = Σ_{n ∈ path(e), ℓ(n) ≤ ℓ_h} h_n(t)
  ```

- **Profile nodes.** p(e) is the ancestor of e at the profile level ℓ_f (default: ICD block; SIGTAP subgroup). Age–sex profiles below that level are not separately estimated: **age-specific geography is a lead** (the group lens, §7.1), not a model term.
- **Context fields are not in the default predictor.** A relation between a context field and an outcome must stay discoverable (§7.5), not absorbed as "boring". Context enters only in adjusted estimands (E_b|Z) and in explaining away (§7.7).

### 4.3 Priors: one per shape (P6, P7)

Every structured effect is a **Gaussian Markov random field** whose precision is fixed by its shape, scaled by learned variances.

| shape | effect | precision / prior |
|---|---|---|
| **tree** (node n, level ℓ, top branch b) | θ_n | `θ_n ~ N(0, σ²_{ℓ,b} λ_n²)`, `λ_n ~ C⁺(0,1)` (horseshoe), `σ_{ℓ,b} ~ N⁺(0, s_ℓ)`. **One variance per level per top branch:** a heterogeneous chapter learns large leaf variance and pools little. |
| **tree, functional** | g_n(·), h_n(·), f_n(·) | the function's own GMRF (rows below), scaled by `σ²_{ℓ,b}` |
| **list** L | θ_L | `N(0, σ²_list,L)` |
| **ordinal** (age, time) | f, h | RW2 (random walk of order 2); RW1 for short series. Sum-to-zero. |
| **cyclic** (month, week) | season | cyclic RW2. Sum-to-zero. |
| **graph** (places) | g_n | **BYM2:** `g = σ (√ρ · s_scaled + √(1−ρ) · v)`. s is ICAR on the chosen graph, scaled to unit generalised variance (Riebler et al. 2016); v is iid. ρ is the **learned** share of spatially structured variation. |
| **low-rank interaction** | ψ, ω, τ | ω on the graph's ICAR, τ RW1, ψ Gaussian. Rank R_b chosen by held-out deviance (§5.4). |

- **Graph choice.** Each block's geography may use one graph, or a mixture (one BYM2 term per graph, each with its own σ). The graph family comes from pegasus_data: contiguity weighted by border length, population-weighted distance, care flows, REGIC, health regions. **The selected graph and ρ are reported per field:** they are findings.
- **Identifiability.** Every GMRF is constrained to sum to zero over its index. Tree levels are centred within siblings. The interaction loadings are orthogonalised against the main effects.
- **Unequal places.** BYM2's unstructured part carries population-scaled precision. Graph weights use border length and population-weighted distance, never bare adjacency. A corner touch (border length 0; 514 edges in 2022) keeps its edge at a 1 km floor.

### 4.4 Marks

For a mark m of event type e (length of stay, cost, birth weight, gestational weeks, Apgar, interval between dates), observed through accumulator states per cell × institution:

| mark type | model |
|---|---|
| positive continuous | log-normal: `log m ~ N(ν, ς²)`. The likelihood needs only (n, Σlog m, Σ(log m)²) per cell (pegasus_data's `logmoments`). A cell's mean log has variance σ²_w/n + σ²_c: σ²_w within cells from the log-moments, σ²_c a cell-level component by moments, re-estimated each outer iteration. There are no empty cells and no factorised total. |
| count-valued (prenatal visits, ICU days) | negative binomial on (n, Σm, Σm²) by moments, or on the histogram |
| bounded score (Apgar) | ordinal (cumulative logit) on the histogram |
| binary share (death in hospital, caesarean) | beta-binomial |

The location ν follows the structure of §4.2, plus **case-mix** (the event type's classifier and declared case-mix roles) and an institution effect (shrunk) where the mark has an institution.

---

## 5. The monolith: estimation and computation

### 5.1 The factorised likelihood (P10)

**The mean structure is fitted by penalised Poisson quasi-likelihood:** consistent for μ under overdispersion. **Dispersion is estimated afterwards** (§5.2).

For one block, with interactions confined to the place × time plane:

```
ℓ(β) = Σ_{(e,c): y>0} y_{e,c} log μ_{e,c}  −  Σ_{e} Λ_e  −  penalty(β)

Λ_e = Σ_{u,t} κ_{s,u,t} · exp( θ_e + g_e(u) + h_e(t) + Σ_r ψ_{e,r} ω_r(u) τ_r(t) ) · M_{p(e)}(u,t)

M_n(u,t) = Σ_g N_{u,t,g} · exp( f_n(g) )         one dense contraction of the population tensor per profile node
```

**Cost per evaluation:**

```
O( nnz_b  +  |profile nodes_b| · |U||T||G|  +  |E_b| · |U||T| · R_b )
```

The ~10¹² implicit cells are never formed. The first term streams the non-empty cells from pegasus_data's aggregates. The other two are dense operations on arrays no larger than the population tensor, run on the GPU.

### 5.2 Dispersion

φ_b is estimated by **maximum likelihood with μ fixed** at the mean's fit:

```
ℓ(φ) = Σ_{y>0} log NB(y | μ, φ)  −  φ · [ Σ_{all c} log(1 + μ_c/φ)  −  Σ_{y>0} log(1 + μ_c/φ) ]
```

- **Non-empty cells enter exactly.**
- **Empty cells enter through log p(0) = −φ log(1 + μ/φ).** The sum over every cell is streamed one leaf at a time: a [U, T, G] slab, the size of the population tensor (P10). One evaluation over chapter IX's 216 M implicit cells takes about a second; the one-dimensional optimum needs about 14.
- **This text replaces a Pearson moment equation, measured wrong on chapter IX 2010–2023** (2026-10-04). Cells with tiny μ and y ≥ 1 dominate the Pearson sum, which gave φ = 0.013. A power-series expansion of the empty cells' term also fails: empty cells hold 1.95 M of the 4.99 M expected events, so μ/φ is not small there. The ML estimate is φ = 5.98.
- **A field whose PIT is miscalibrated** (§6.2) with the block's φ gets a field-level place-year component (§6.2).

### 5.3 Optimisation and uncertainty

- **Optimiser.** MAP by L-BFGS with automatic differentiation (PyTorch). Block coordinate descent over: main effects, interaction factors, variance parameters (re-estimated by their conditional modes).
- **Warm starts.** From the previous version's parameters on every data update.
- **Uncertainty.** The Laplace approximation at the mode, with Hessian–vector products. Marginal standard errors of linear predictors come by sparse selected inversion of the GMRF blocks and Hutchinson–Lanczos estimates for the dense low-rank part.
- **Posterior predictive for a cell.** NB with μ inflated by `exp(Var(η_c)/2)`, and its variance augmented accordingly.
- **The approximation is checked, not assumed.** On a random sample of fields and states (never only the densest slice), the Laplace fit is compared with an exact MCMC or INLA fit. Agreement criteria and results are evaluation entries.

### 5.4 Blocks, model choice, two-level fit

1. **Top model.** All blocks' top-level nodes (chapters) with shared population and graph terms. It gives the chapter-level effects and the hyperparameter priors.
2. **Block models.** Each block with the top-level effects as an offset, in parallel on CPU cores, each using the GPU in turn.
3. **Model choice: held-out deviance on the last two years, never in-sample.** The choices are:
   - rank R_b;
   - graph selection or mixture;
   - which trees and lists pool (tree pooling is turned off per chapter where it does not improve held-out deviance).

### 5.5 Hardware and stack

**Target machine:** 32 GB RAM, 20 logical cores, NVIDIA RTX 4050 laptop GPU (6 GB, CUDA 12.1), about 177 GB free disk. The decision record is ADR-0003.

| need | library |
|---|---|
| arrays, sparse algebra, sparse factorisation (GMRF) | numpy, scipy (`scipy.sparse`, SuperLU, CHOLMOD via scikit-sparse where installable) |
| automatic differentiation, GPU contractions and GEMM | **PyTorch 2.5 (CUDA)**. JAX's GPU builds do not run natively on Windows. |
| columnar I/O, aggregation | pyarrow, duckdb, polars |
| scan loops (sorting, LTSS) | numba |
| reference GLMs for checks | statsmodels |
| CLI and configuration | typer, rich, pydantic |

**Numerics:**
- float32 on the GPU with float64 accumulation for sums over cells;
- float64 on CPU for the GMRF solves;
- every random draw seeded from (field id, cell, purpose), so every surprise is reproducible.

**Memory:**
- no array larger than the population tensor × the profile nodes of one block;
- GPU work is chunked to 4 GB;
- the non-empty cells stream in batches from Parquet.

**Budgets** are measured in phase 1 and recorded as evaluation entries. **The starting setup:** SIM, SINASC, SIH and SINAN, municipality × year, 2010–2023, 18 ages × 2 sexes, codes to three characters, population tensor 2.8 M cells. Its estimates, to be confirmed:

| task | estimate |
|---|---|
| all blocks of the four systems | under an hour |
| subset scan | seconds to a minute per field |
| pair scans for one estimand | minutes |

---

## 6. Expectation tiers, calibration, surprise

### 6.1 Tiers

**A tier is the monolith with a declared subset of terms.**

| tier | terms | what remains surprising |
|---|---|---|
| **B0** | θ, f, h restricted to the national level (ℓ_g ignored) | how a place differs from Brazil, given its population |
| **B1** | B0 + g (graph terms) | departures from the region |
| **B2** | B1 + a place-level random intercept and slope per field: `α_{u} + β_{u}(t − t̄)`, shrunk to the region | departures from a place's own course |
| **B2s** | B2 + season (sub-annual grains) | out-of-season events |
| **BP** | prospective: the years after t₀ against the fit on years ≤ t₀, histories extrapolated (the RW2 forecast mean), every place and category effect as learned before t₀ | departures from the past: epidemics, new practices |

- **Tiers are computed from one fit:** B0 and B1 by dropping terms, B2 by a cheap per-field refit of `(α_u, β_u)` with the rest as offset.
- **B0 is re-levelled to the national total of each year.** Dropping centred log-scale place effects also drops E[exp(s + v)] > 1. Without the re-levelling, B0 fell 11% short on chapter IX.
- **B2 is an exact 2 × 2 Newton per place** under NB working weights, with τ_α and τ_β by Fellner–Schall. Where B1 already carries the field's place effects, τ_α runs to its bound and only the trends β_u remain (measured on chapter IX).
- **The interaction ψωτ is never part of a tier.** It is read as patterns (§7.4).
- **Surveillance lenses read BP.** A fit over the whole period learns an epidemic as normal.
  - The year effects absorb the national waves.
  - A category that exists only during the epidemic gets its place effects from the epidemic itself.
  - **Measured on COVID-19 in SIM** (B34.2): 213,152 deaths observed in 2020 against 212,821 expected at B1. The space–time lens found nothing at B1.
- **BP's handling of calibration and new categories:**
  - its calibration is recorded but never flagged, and its dispersion is the block's;
  - a category without a past has no expectation in BP, so the excess is read at its group or chapter.

### 6.2 Calibration

For each field and tier, the **randomised PIT** of each observed cell under its posterior predictive:

```
u_c = F(y_c − 1) + V_c · p(y_c),   V_c ~ U(0,1) seeded by (field, cell)
```

**Uniformity** is tested by KS and by the PIT histogram per field, per tier and per macro-region.

**The criterion is a minimum relevant departure (P5), not a p-value.** With 10⁵ cells, any departure is significant.
- A field is calibrated when its PIT's KS distance is ≤ 0.03 overall and ≤ 0.05 in every macro-region.
- A macro-region's 5,000–25,000 cells reach KS ≈ 0.02 by sampling alone.

**A miscalibrated field** gets a field-level **place-year variance component**: Var(Y_ut) = μ + μ²/φ_agg + μ²/φ_extra, with φ_extra by maximum likelihood on the field's aggregate cells.
- **Why it is needed:** cells within a place-year share variation that the expectation does not model, and summing them adds it coherently. The independent-cell φ_agg misses it.
- **What was measured** on chapter IX B1 (2026-10-04): a U-shaped PIT, with both tails at about 0.13 against 0.10. The component flattened it, bringing KS from 0.035 to 0.010.

**If the field is still miscalibrated, it is flagged.** A flagged field stays visible in lenses with its flag, and is excluded from pair scans and dependency maps at that tier.

**B0 is expected to fail calibration.** It ignores geography by design and serves the spatial-cluster lens, never pairs.

### 6.3 Surprise

```
z_c = Φ⁻¹(u_c)                  surprise on a common scale; computed after the expectation, never before
w_c = μ_c / (1 + μ_c/φ)          information about log μ_c carried by the cell (Fisher information)
flags_c                          denominator tension | unreliable recording (pegasus_data) | calibration | small support
```

- **Zero cells have a closed form:** `u = V · p(0)`.
- **Aggregation over a subset** never averages z. Subset statistics use Σy and Σμ (§7.2).
- **The surprise cube is virtual:** computed from parameters and non-empty cells on demand, and cached only for scanned fields and tiers.

---

## 7. Scans

Every scan is a **ledger entry** (§9.2) with a declared estimand, tier, family and null.

### 7.1 Lenses: one field

| lens | statistic | null |
|---|---|---|
| spatial cluster | expectation-based Poisson scan over graph-connected place sets (§7.2 restricted to places) | §7.2 |
| outbreak, change point | outbreak: each cell's upper tail under the B2/B2s predictive (the PIT), with BH. Change point: per place, the exact NB tail of each trailing window, with Bonferroni over the windows, then BH across places | the predictive, exact; simulated nulls failed on sparse fields (evaluation 2026-10-04) |
| space-time cluster | §7.2 over place × time | §7.2 |
| group disparity | per place: likelihood-ratio heterogeneity of the groups' SIRs against the national group pattern (B0 by group) | χ² against an NB-adjusted reference distribution |
| trend divergence | `β_u − mean_{N(u)} β` from B2, in posterior standard deviations | the posterior |
| observation | the same lenses on recording-practice fields (ill-defined share, secondary-diagnosis coding, race reliability, notification delay) | as above |

### 7.2 Subset scanning

**The score.** For a subset S of cells, with `Y = Σ_S y` and `M = Σ_S μ`, the expectation-based Poisson score (Neill 2012):

```
F(S) = Y log(Y/M) + M − Y    if Y > M,   else 0
```

**For marks,** the Gaussian expectation-based score `F(S) = (Σ_S w r)² / (2 Σ_S w)` on weighted residuals r of the mean log mark, scanned in both directions (p × 2). It keeps the same linear-time property.

**The search.** The space is a product: places (connected in a graph) × contiguous times × any subset of groups × codes within a subtree or list.
- **Linear-time subset scanning (LTSS).** For F, the best subset of a *free* dimension, given the others fixed, is among the top-k cells ranked by the priority `y/μ`. That is O(n log n).
- **Places use LTSS within graph neighbourhoods.** For each centre, its k nearest neighbours by graph distance.
- **Times are enumerated** as contiguous windows.
- **Codes are scanned within each subtree,** by LTSS among its leaves.
- **Dimensions are optimised by alternation** with random restarts (multidimensional subset scan; Neill, McFowland & Zheng 2013).

**The null.**
- R replicate datasets `y* ~ NB(μ, φ)` over the scanned support (R = 200 by default); the maximum score per replicate.
- **A Gumbel fit to the maxima** gives p-values below 1/(R+1) (Abrams, Kleinman & Kulldorff 2010). **There is no Monte-Carlo floor** (the 2026 failure).

**Recursion.** After the top subset is reported, its cells are conditioned out (μ set to y), and the scan is repeated until the next score's p exceeds the family threshold.

### 7.3 Many dimensions at once

Subset scanning across fields: the field is a dimension (a subset of fields within one family). This finds the same subset of places and times departing across several related causes.

### 7.4 Patterns (structural leads)

**Inside the monolith,** the block's interaction factors (ψ_r, ω_r, τ_r) are patterns. Each is reported with:
- its loadings;
- its share of deviance;
- its stability across the replication halves (Tucker congruence ≥ 0.9).

**Across blocks,** non-negative Poisson tensor factorisation of observed against expected (CP-APR, Chi & Kolda 2012, with the monolith's μ as offset):

```
minimise Σ_c [ μ_c m_c − y_c log(μ_c m_c) ]  over  m_c = Σ_r λ_r a_r(u) b_r(t) c_r(field) ≥ 0
```

**Each component is a multiplicative departure shared by places, times and fields.** A coding substitution appears as a component positive on one code and a matching one negative on another, in the same places and times.

### 7.5 Pairs

**Fields X and Y are compared at their common support** (the finest support both lift to by their laws).

| estimand | statistic | null |
|---|---|---|
| **E_b, between places** | weighted correlation ρ̂ over units of place effects b̂(u) (the posterior mean of a field-specific place intercept over B0, shrunk), pair weight `√(w_X w_Y)` with `w = 1/se²`, each field centred by its own weighted mean | **Dutilleul's modified t:** `n_eff = 1 + n² / tr(R̂_X R̂_Y)`, with R̂ from each field's spatial correlogram on the graph's distance classes |
| **E_b\|Z, adjusted** | partial correlation given a declared adjustment set Z (urbanisation, income, macro-region) | same, with n_eff − dim(Z) |
| **E_w, within places, lag ℓ** | `ρ̂_ℓ = Σ_{u,t} w z^X_{u,t} z^Y_{u,t+ℓ} / norm`, pooled over places, on B2 surprises | per place, `n_eff,u = T_u (1−φ̂_X φ̂_Y)/(1+φ̂_X φ̂_Y)` (AR(1)); summed over places; divided by the design effect `1 + (U−1) ρ̄_space` for cross-place correlation at equal t |
| **E_i, between institutions** | as E_b on the institution lattice | as E_b, on the care-flow graph |
| **across systems** | the same quantity in two systems (notifications against admissions): E_w on the log ratio | as E_w |

**Minimum-effect test (P5):**

```
H0: |ρ| ≤ δ_E
z = (atanh|ρ̂| − atanh δ_E) · √(n_eff − 3),   p = 1 − Φ(z)
```

δ_E is set by §8.4.

**Computation.** For one estimand and support class, all pairs come from one Gram matrix `AᵀA` (GPU), with `a_f = √w_f ⊙ (x_f − x̄_f)`, plus per-field n_eff ingredients. Lags shift A.

**Why the weights factorise.** A pair weight that factorises is what lets one Gram matrix serve every pair. The geometric mean √(w_X w_Y) is that weight. The form written here first, `(1/se_X² + 1/se_Y²)⁻¹`, was a variance rather than a weight: it gave the noisiest units the most weight.

**Dutilleul for every pair at once.** Each field's correlogram r_f(k) is computed over 20 distance classes of equal pair counts (great-circle distance between population centres, GPU). Then:

```
tr(R_X R_Y) = n + Σ_k n_k r_X(k) r_Y(k)
```

This is the same Gram form, so n_eff comes for every pair at once.

**Nonlinear dependence:** rank (Spearman) versions in v1. HSIC only on pairs short-listed by another statistic, with a calibrated null and a CKA effect floor.

### 7.6 Dependency maps (phase 3)

For one estimand and support class:
- a sparse + low-rank Gaussian graphical model on the weighted correlation matrix of calibrated surprises (Chandrasekaran, Parrilo & Willsky 2012);
- penalties chosen by stability across the replication halves (StARS);
- **edges reported only if they also pass §7.5's pair test.**

### 7.7 On demand

**Explaining away.** For a lead with support S and a candidate driver x(u,t) (a context field, a capacity change):
1. refit the lead's field locally (B-tier of the lead) with x added;
2. report the coefficient with its interval, and the **absorbed share**:

```
A = 1 − D'_S / D_S,     D_S = 2 Σ_{c∈S} [ y log(y/μ) − (y − μ) ]
```

D'_S is the same with the augmented μ'.

**Decomposition.** The change in expected events between two periods, split into population size, age–sex composition, place mix and risk (η). Each by counterfactual substitution of one component at a time, averaged over all orders (Shapley; exact for these four components). The risk part is reported by place and by group.

### 7.8 Cohort scans (phase 2)

On linked cohorts from pegasus_data (person-level records): every attribute × every outcome.
- **Model:** Poisson regression with person-time offset, adjusted for age, sex, year and a place random intercept.
- **Test:** a minimum-effect test on log RR (`|log RR| ≤ log δ_RR`, default δ_RR = 1.2 until calibrated).
- **Multiplicity:** BH across the grid within a family.

---

## 8. Error control, replication, admission

### 8.1 Families

A **family** is (lens or estimand, tier, field family or pair of field families, support class).

### 8.2 FDR

- **Within a family:** Benjamini–Hochberg at q = 0.05. Benjamini–Yekutieli where p-values within a family are not positively dependent.
- **Across families:** Benjamini–Bogomolov selective inference. Families are selected by their Simes p-value at level q; then within each selected family BH at `q · |selected| / |families|`.
- **Down code trees:** TreeBH (Bogomolov et al. 2021) when a lens tests the nodes of a classifier tree.
- **Agents.** Exploratory tests are logged but carry no claim. Claims pass through `confirm` (§9.3), whose stream is controlled by online FDR (LOND).

### 8.3 Splits and replication

| split | definition |
|---|---|
| **temporal halves** | the period split at its midpoint year |
| **spatial halves** | IBGE immediate geographic regions (510) randomly halved within each state, fixed seed. **Half B is the agents' confirmation reserve.** |
| **systems** | the same estimand through another system |

| tier | requirement |
|---|---|
| R0 | passes §8.2 on all data |
| R1 | same sign and ≥ half the effect in the other temporal half (p < 0.05, one-sided) |
| R2 | the same in the other spatial half |
| R3 | the same through another system |

### 8.4 Admission and minimum effects (calibrated, not set)

**Admission.** A field enters a lens or pair scan if the harness's power curve for that lens (§10.3) gives power ≥ 0.5 for its reference effect:

| scan | reference effect |
|---|---|
| lenses | rate ratio 1.5 over one macro-region-year |
| pairs | ρ = 0.3 |

Until the curves exist, the provisional rule: at least 1,000 events over the window and events in at least 5% of units. **A code tree is descended only while children stay admissible.**

**Minimum effect δ_E per estimand.** The smallest δ for which the false-lead rate on the harness's **negative controls** stays ≤ q. Negative controls keep each field's own dependence and remove the relation (§10.2).

This is the empirical-calibration idea of observational-health research networks, applied to the search itself. **Provisional δ = 0.1 until calibrated.**

**Every lens tests against its minimum effect.** Provisional values, in `scans/lenses.py`:

| lens | H0 (boundary) | provisional |
|---|---|---|
| outbreak, change point, space–time, spatial cluster | rate ≤ θ0 × expected; the null's replicates are drawn at θ0μ | θ0 = 1.2 |
| trend divergence | \|β_u − β̄_N(u)\| ≤ δ, with δ a ratio of 1.2 between the period's first and last year | 1.2 |
| group disparity | the groups' log-SIRs spread with sd ≤ 0.2: G² against non-central χ²(df, 0.2²·Σμ) | 0.2 |
| marks (all lenses) | \|mean log departure\| ≤ 0.03 | 3% |

**Measured on IX** (evaluation 2026-10-04). Testing against zero flooded the survey with trivially small departures, because tens of thousands of deaths make anything significant:
- hypertension (I10–I15): trend divergence fell from 116 to 38 places, group disparity from 121 to 7;
- the strongest signals survived, São Borja among them.

### 8.5 Mechanical overlap

```
overlap(X, Y) = |events(X) ∩ events(Y)| / min(|events(X)|, |events(Y)|)
```

It is computed from records by pegasus_data. Pairs with overlap > 0.05 are not tested for dependence: they are nested codes, alternative classifiers, or "any mention" against underlying cause. They may be tested on their non-shared events.

---

## 9. Leads, the ledger, use

### 9.1 The lead

```
Lead
  id, kind            residual | subset | pattern | relation | cohort | observation | structural
  estimand, tier, fields, support, locus (places, times, groups, codes, institutions)
  effect              estimate, interval, scale (rate ratio | ρ | log RR | share absorbed)
  test                statistic, p, q, family, null, calibration status
  replication         R0..R3, with each replication's effect
  robustness          C-robust (race), denominator tension, recording flags, overlap
  provenance          data versions (pegasus_data), monolith version, code version, ledger id
  rank                evidence × effect × replication; never p alone
```

### 9.2 The ledger

**An append-only table.** One row per test, written before execution:
- id, actor (scan | agent | person), family, hypothesis spec, split, data and model versions;
- the result appended on completion.

**The ledger is the denominator of every error rate.** No test runs outside it.

### 9.3 Use

**PegaSUS runs as a survey.** Each data update triggers:
1. a warm-started refit of affected blocks;
2. surprises for the new periods;
3. the scheduled scans;
4. lead updates.

**The interfaces, as a Python API first, then a CLI, then agent tools:**

| interface | does |
|---|---|
| `leads(filters)`, `lead(id)` | the lead register and its update stream |
| `expected(slice)`, `surprise(field, tier, scope)` | any slice, observed against expected, computed on demand |
| `scan(field, lens, tier, scope)`, `compare(x, y, estimand, tier, scope)`, `subset_scan(...)` | ledgered tests |
| `explain_away(lead, candidate)`, `decompose(field, periods, scope)` | §7.7 |
| `fields(query)`, `field(id)` | the registry |
| `cohort(...)`, `records(...)` | through pegasus_data |
| `confirm(claim)` | one run on the confirmation reserve, ledgered, under LOND |

**Agents** (an LLM in a single loop, with these tools and an objective) see the exploration half only, except through `confirm`. The tool layer is exposed over MCP in phase 3.

---

## 10. The validation harness (phase 0)

### 10.1 Known positives

Each with its lens, tier, locus and pass criterion (locus overlap ≥ 0.5 Jaccard; effect sign):

| signal | lens / estimand | locus |
|---|---|---|
| microcephaly and congenital anomalies | space-time, B2 | Northeast, 2015–16 |
| arbovirus notifications → microcephaly births | E_w, lag 6–9 months (monthly) | Northeast, 2015–16 |
| COVID-19 excess deaths | space–time and outbreak, **BP** (train ≤ 2019) on groups and chapters (SIM codes COVID-19 as B34.2) | national, 2020–21; Amazonas, January 2021 |
| dengue epidemics; seasonality | outbreak, B2s | by state |
| leptospirosis after the floods | space-time | Rio Grande do Sul, May–July 2024 |
| Chagas disease, schistosomiasis | spatial cluster, B0 | known endemic areas |
| infant mortality ↔ income, sanitation | E_b | national |
| diarrhoea admissions ↔ sewerage | E_b (census years) | national |
| winter respiratory admissions | B2s outbreak | South, Southeast |

### 10.2 Known negatives

Each negative keeps a field's own dependence and removes the relation:

- **Between places:** Moran spectral randomisation (Wagner & Dray 2015). The field's coordinates in the graph's Moran eigenvectors get random signs, which keeps its spatial autocorrelation spectrum exactly.
- **Within places:** the field's series shifted by k ≥ 2 years within each place.

**Withdrawn from this list:** "random partitions of one system's events into two fields". Both halves inherit the same place risk, so they correlate by construction. That makes them a positive for power, not a negative.

### 10.3 Planted signals

For a field and locus S, inject `y' = y + Poisson((θ − 1) · μ_S)` with a known θ. For pairs, inject a shared latent field into both fields' intensities. Recovery against θ gives each lens's **power curve**, which feeds §8.4.

### 10.4 Null surrogates

The full pipeline is run on `y* ~ NB(μ̂, φ̂)`, independent across fields. **The leads found are the false-lead rate per lens.**

### 10.5 Gate

A lens or estimand runs in production only after it:
1. recovers its positives;
2. holds its false-lead rate on surrogates at or below q;
3. has a published power curve.

Harness results are evaluation entries.

---

## 11. Code

### 11.1 Package `pegasus_core`

The package is named `pegasus_core` because the name `pegasus` is taken by the 2026 engine's editable install in the shared environment (ADR-0001).

**Modules are created when built.** This map is the contract each one fulfils.

| module | responsibility | may import |
|---|---|---|
| `gateway` | the **only** importer of pegasus_data: roles, event types, structures, graphs, population, aggregates, records; returns Arrow; records data versions | pegasus_data |
| `config` | homes, versions, seeds | — |
| `fields` | field specs, registry, admission (§8.4), common-support lifting, overlap requests | gateway |
| `structures` | GMRF precisions per shape (tree, list, RW1/RW2, cyclic, ICAR/BYM2 scaling), constraints | numpy, scipy |
| `graphs` | named proximity graphs over places (contiguity weighted by border length, distance kernels, kNN), from pegasus_data through `gateway` | gateway, structures |
| `monolith` | model spec (§4), factorised likelihood (§5.1), dispersion (§5.2), fit and Laplace (§5.3), blocks and model choice (§5.4), marks (§4.4), prediction for any slice | structures, fields |
| `surprise` | tiers (§6.1), PIT and calibration (§6.2), the virtual cube (§6.3) | monolith |
| `scans` | a subpackage: `lenses` (§7.1), `subset` (§7.2–7.3), `patterns` (§7.4), `pairs` (§7.5), `explain` (§7.7), `cohort` (§7.8); maps (§7.6) in phase 3 | surprise, monolith, fields |
| `control` | the ledger (§9.2), families and FDR (§8.2), splits and replication (§8.3), LOND | store |
| `leads` | the lead object, ranking, register | control, scans |
| `harness` | positives, negatives, planted signals, surrogates, power curves, the gate (§10) | all of the above |
| `store` | content-addressed artefacts (§11.3) | pyarrow |
| `tools` | the agent and person interface (§9.3); MCP server in phase 3 | leads, scans, surprise, gateway |
| `cli` | the `pegasus-core` command | tools |

**Dependency direction is downward only:** `tools → leads → scans → surprise → monolith → structures/fields → gateway`. No cycles. The harness sits beside the stack and may import all of it.

### 11.2 Interfaces

- **Python API first;** the CLI wraps it, and the tools wrap the API.
- **Arrow tables at module boundaries;** numpy and torch inside.
- **No module reads files outside the store and the gateway.**

### 11.3 Artefacts and homes

**PegaSUS's home.** `PEGASUS_HOME`, default `<repo>/pegasus_home/` (gitignored), never inside pegasus_data's home.

```
pegasus_home/
  monolith/<block>/<version>/params.safetensors, manifest.json    (spec hash, data versions, fit diagnostics)
  surprise/<field>/<tier>/<version>.parquet                         (cached scanned fields only)
  leads/leads.parquet                                               (versioned rows)
  ledger/ledger.parquet                                             (append-only)
  harness/<run>/…                                                   (results behind evaluation entries)
  cache/                                                            (gateway aggregates, keyed by query and data version)
```

**Every artefact's key** hashes (pegasus_data data versions, spec, code version). **A stale artefact is never served.**

### 11.4 Invariants (enforced in code, checked by the harness)

```
Every input comes through gateway.
No statistic runs on a value without its expectation and its information weight.
Context is never in a default tier.
Taxonomic structure never enters a relation's prior.
Every test is in the ledger before it runs.
Every p-value has a null that preserves the field's dependence (§7.2, §7.5); none has a Monte-Carlo floor.
An effect is tested against its minimum relevant effect, not zero.
A miscalibrated field never enters a pair scan at the tier where it failed.
Pairs with measured overlap above 0.05 are never tested as independent.
No array larger than the population tensor × profile nodes is materialised.
A modelled input carries its model version; an artefact carries its data versions.
Every random draw is seeded from (object, cell, purpose).
```

### 11.5 Verification

**Statistical code is verified by the harness on real data** (§10) and by measured comparisons (exact against approximate fits, old against new code on identical data). It is not verified by unit tests written alongside the code, which pass by construction (CLAUDE.md §5).

---

## 12. Phases and gates

| phase | builds | needs from pegasus_data (`docs/handoffs/`) | gate |
|---|---|---|---|
| **0** | harness (§10); `gateway`; `store`; `control` (ledger) | aggregates; event types for SIM, SINASC, SIH | the harness runs end to end on surrogates |
| **1** | `fields`; `structures`; `monolith` (annual; SIM, SINASC, SIH); `surprise`; lenses; subset scanning | roles and event types; code structures; contiguity and distance graphs; POPSVS | univariate positives recovered; false-lead rates; measured compute budgets; **first measurements:** tree pooling by chapter, graph choice |
| **2** | pairs (E_b, E_w, E_b\|Z); FDR across families; replication; explaining away; decomposition; cohort scans; SINAN; sub-annual grain for dense families | care-flow graph; population account v1 (2022 hold-out); linked cohorts | pair positives; negatives; calibrated δ and admission |
| **3** | patterns across blocks; dependency maps; tools over MCP; institution lattice; agents | race measurement; new population sources; CNES fields; APAC families | each with its own positives |

---

## 13. Departures

*Where the code knowingly departs from this document, with the reason. Each row closes when the code catches up.*

| § | the document says | the code does | why |
|---|---|---|---|
| 4.3 | horseshoe on tree levels, one variance per level per top branch | iid Gaussian per level, τ by Fellner–Schall, per block (= per top branch) | the horseshoe needs sampling or a reweighted penalty; the iid level is its first step |
| 4.3 | BYM2 with a learned mixing ρ | BYM: separate τ for the scaled ICAR and the iid part; ρ reported from the two τ's | the same model reparametrised, its τ's learned by the same updates as every other effect; the priors differ |
| 4.2 | geography carried down to a declared level ℓ_g | groups carry ICAR + iid; categories carry an iid `v_cat[e, u]`, centred within the group | the category-level place deviation is real (chapter IX: sd ≈ 0.47), and the coding-substitution leads read it |
| 4.2, 5.4 | the low-rank interaction ψωτ | not yet built | main effects and tiers first; patterns across blocks (CP-APR) read the interaction meanwhile |
| 5.3 | Laplace uncertainty; the predictive inflated by Var(η) | MAP only; the predictive is NB(μ̂, φ) | the B2 per-place refit carries its own posterior sd; full Laplace is OQ-2 |
| 5.3 | Fellner–Schall on the full Hessian | Fellner–Schall with the Poisson Fisher diagonal per effect (block-diagonal), damped to ×10 per iteration; a τ above 10⁵ counts as converged | the exact trace per effect is affordable, the cross-effect terms are not |
| 6.1 | B2s | raises: the monolith is annual | O1: annual first, then monthly |
| 7.2 | groups as a free dimension of every subset scan | the scanner takes any free dimensions; the lenses pass places × time | the per-group surprise is not yet wired into the lenses |
| 8.2 | TreeBH (Bogomolov et al. 2021) | TreeBH with Simes aggregation at each node | the exact combination is a later refinement |
| 11.3 | artefact keys hash pegasus_data's data versions | keys carry pegasus_data's package version, plus the sha256 of the shipped resource for artefacts derived from one (code structures, graphs); the commit is recorded in each manifest | pegasus_data exposes no publication-level data versions yet, and its commit changes with every edit |
