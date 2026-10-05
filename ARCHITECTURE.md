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

Later (phase 4, ADR-0004), the same model and lenses run **prospectively**, as surveillance across every diagnosis code and system.

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
| **population** | person-years N by place × year × age × sex (× race), with uncertainty; the SUS-dependent variant; completeness by system, place and year. Sources behind `gateway.population(source=)`: `popsvs` (IBGE's projection as the MoH distributes it, modelled, single years of age, no uncertainty), `account-2` (pegasus_data's `population-account-2`, municipality × sex × five-year band × year 2010–2023, 80 % intervals read as σ of log N) and `account-3` / `account-4` (the complete tensor, 5,570 municipalities, single ages, race, 2000–2023 / 2000–2030, summed onto POPSVS's 18 bands, σ an upper bound; ADR-0010 amended). The source fixes the age bands (18 for POPSVS and account-3/4, 17 for account-2, whose 0–4 holds ages 0 and 1–4); the cache keys carry the source and the model version |
| **aggregates** | sparse non-empty cells of counts per event type and lattice; mark accumulator states (n, Σm, Σm², Σlog m, Σ(log m)², histogram on declared bins) |
| **records and linked persons** | for cohort scans and agents |

### 3.2 Defined here

**Lattice cell.** `c = (u, t, g)`:
- u, a place (municipality, comparable area or health region);
- t, a time (year, or month for dense families);
- g, a group: age band × sex (× race).

The **population tensor** P = U × T × G holds N_c.

**Institution cell.** `c = (f, t)`, f a recording facility (CNES for SIH, CODESTAB for SIM) and t a year, with the facility's **catchment** as exposure: the expected events of a block at f are `m_ft = Σ_u q_uf μ_ut`, the place model's expectation spread by the care-flow kernel q (the share of place u's other-chapter events recorded at f). It is the second lattice, read for the estimand *between institutions* (P4, E_i). Built for SIH at the annual grain, one block at a time (§4.5, ADR-0016).

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
| **N^{(v)}_c** | person-years of population variant v: all residents (SIM, SINASC, SINAN) or SUS-dependent (SIH, SIA) | pegasus_data, source `popsvs`, `account-2` or `account-3/4` (§3.1). With the account, log N_c ~ N(log N̂_c, s_c²) and Var(Σ_g μ_g) = Σ μ_g²(e^{s²}−1) + ρ[(Σ μ_g s_g)² − Σ μ_g² s_g²] enters the predictive's variance beside Var(η) (`Monolith.exposure_variance`, `surprise.py`) |
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

### 4.5 Institutions: a supply term, and the lattice

A hospital's volume or coding step reaches a place's residents' counts (SIH names the recording facility of every admission). Two objects, because only one part of it can be taken out of a place's expectation without hiding real events (ADR-0016).

- **Supply term (opt-in, `Session(supply=True)`).** The expectation of an annual count block is multiplied by `A_ut = renorm(exp(β_v L_vol + β_u L_util))`. Both indices come from the *other* chapters only (not the block, not I, X or XXII, which carry epidemics), so a real outbreak of the block never enters them: `L_vol` is the log of Σ_f w_uf r_ft, w_uf the share of the place's block events recorded at facility f and r_ft the facility's other-chapter volume as a share of the nation's over its own mean; `L_util` the log of the place's own other-chapter admissions over what its mean rate and the nation's course give. Each log index is soft-thresholded at two standard deviations of its counting noise (`facility._deadband`), because a sole-provider town's index is its own counts. `renorm` keeps each place's and each year's expected total. The exponents are chosen on a grid by the negative binomial likelihood of the block's place-year cells under its B1 expectation (`facility.fit_supply`), and the term is applied after the fit (§13). At the monthly grain it is off: the cube is annual.
- **Institution lattice (`Session.institutions`, `facility.institution_lattice`).** Cells (f, t) with the facility's catchment as exposure (§3.2). A facility's best window of years (a step or a bump) is found by the Poisson likelihood ratio against its constant ratio of observed to catchment-expected events, scaled by the dispersion of the facilities' own residuals; it is *volume* when the facility's other-chapter volume moved with it, *specific* when it did not (the facility's handling of the block: coding, a service, a real event it served). A specific step is a lead of its own, read as E_i (§7.5), not subtracted from the places it serves: a referral hospital receives real events and coding alike (ADR-0014).

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
- **A field whose PIT is miscalibrated** (§6.2) with the block's φ gets a field-level place-year component (§6.2), which varies by macro-region.
- **The block's own φ stays one value per block.** `nb_loglik` scores any φ (a scalar or one per place) over every cell, and `dispersion_by` fits one per group of places. Per macro-region, held out, it gained 0.009 nats per event on dengue (fit to 2018), 0.0002 on chapter IX and −0.0007 on chapter X (ADR-0006), so it is not adopted.

### 5.3 Optimisation and uncertainty

- **Optimiser.** The mean's MAP comes from truncated Newton–CG given the τ's. The τ's are then updated by Fellner–Schall, and the two alternate.
  - **The Newton step:** CG on exact Hessian–vector products (double backward through the factorised total), diagonal preconditioner, Eisenstat–Walker forcing, Armijo line search.
  - **The likelihood's linear part** Σ y·η comes from sufficient statistics computed once.
  - **L-BFGS was replaced** (open question 6 (resolved), evaluation 2026-10-04). It used every iteration it was given, and from a perturbed start it diverged. Chapter IX now fits in 229 s.
- **Warm starts.** From the previous version's parameters on every data update.
- **Uncertainty.** The Laplace approximation at the mode (`laplace.py`), never forming the Hessian: with the NB expected information w = φμ/(φ+μ), FᵀWF needs only the pairwise marginals of w per leaf (one pass over the slabs), and a Hessian–vector product is three small einsums and one vjp.
  - **Draws, not selected inversion or Hutchinson probes.** Perturb-and-MAP draws (Papandreou–Yuille) solved by CG with a block-Jacobi preconditioner per effect (sparse LU of diag(Σw) + τQ), tolerance 10⁻³: about 40–90 iterations per draw. Their per-cell variance has relative error √(2/S) whatever the correlation; against an exact dense inverse it sits at that floor (evaluation 2026-10-05, Laplace). The diagonal preconditioner capped at 1,000 iterations.
  - **Off by default** (`Expectations(laplace=0)`): it moves in-sample calibration by ≤ 0.01 KS.
- **Posterior predictive.** The aggregate's NB is matched to the draws' moments, 1/φ_eff = (E[Σμ²]/φ + Var(Σμ))/m². In-sample tiers are centred on the MAP's μ (the score equations tie it to the data; the posterior mean overshoots by `exp(Var η/2)`), BP on the posterior mean, and BP adds the history's forecast error (annual: the RW2 forecast variance; monthly: an empirical level-change variance, a heuristic).
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
- the non-empty cells stream in batches from Parquet;
- a survey scans fields on `PEGASUS_SURVEY_WORKERS` threads (default a quarter of the cores, at most 4, cut to free RAM) over one loaded model, the lenses of a field sharing its tiers' expectations; the scan's null runs on the GPU in batches (evaluation 2026-10-05-survey-throughput).

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
| **BP** | prospective, the *expectation*: the years after t₀ against the fit on years ≤ t₀, every place and category effect as learned before t₀; the history h carried forward and each place's own course (annual), or the fit's years as regimes (monthly); a mixture predictive | departures from the past: epidemics, new practices |
| **BPA** | prospective, the *alarm baseline* (ADR-0012): BP with the monthly history a flat level (the last 36 months of h) that past epidemics do not enter; identical to BP at the annual grain | an epidemic, even one that repeats a past one |

- **Tiers are computed from one fit:** B0 and B1 by dropping terms, B2 by a cheap per-field refit of `(α_u, β_u)` with the rest as offset.
- **B0 is re-levelled to the national total of each year.** Dropping centred log-scale place effects also drops E[exp(s + v)] > 1. Without the re-levelling, B0 fell 11% short on chapter IX.
- **B2 is an exact 2 × 2 Newton per place** under NB working weights, with τ_α and τ_β by Fellner–Schall. Where B1 already carries the field's place effects, τ_α runs to its bound and only the trends β_u remain (measured on chapter IX).
- **The interaction ψωτ is never part of a tier.** It is read as patterns (§7.4).
- **Surveillance lenses read BP.** A fit over the whole period learns an epidemic as normal.
  - The year effects absorb the national waves.
  - A category that exists only during the epidemic gets its place effects from the epidemic itself.
  - **Measured on COVID-19 in SIM** (B34.2): 213,152 deaths observed in 2020 against 212,821 expected at B1. The space–time lens found nothing at B1.
- **BP's handling of calibration and new categories:**
  - its calibration is recorded but never flagged;
  - **its predictive is a mixture of NBs** (`prospective.py`, ADR-0009), the cell's φ_agg combined with the *training fit's* φ_extra (estimated on the fit's own B1 cells, so no departure leaks into it);
  - **annual grain:** h is the RW2's last slope damped by 0.5 per year, and each place carries its own B2 trend over the fit, damped by 0.5, with the coefficients' posterior variance;
  - **monthly grain:** the regimes are the fit's own years (each year's twelve months of h, equal weights), the epidemic years of the history being normal ones;
  - **a category the fit never saw has no expectation** (ADR-0011): it leaves the node, its events are counted per year (`extras["new_category"]`, flag `NEW_CATEGORY`) and it alarms at five events in a year. A known category that explodes (B34 in SIM, 802 training deaths against 714,782 later) is not unseen: it is the lens's positive;
  - **two objects (ADR-0012).** `Expectations.prospective(..., purpose="expectation")` is BP, the calibrated predictive of the above, for surprises and the calibration check (§6.2). `purpose="alarm"` is BPA, for epidemic detection: the regimes predictive is calibrated but a weak alarm, since past epidemics are regimes (dengue state epidemic-years, recall/precision 2019–23 0.48/0.84 against 0.81/0.75; 2015–16 0.22/0.80 against 0.49/0.90). BPA keeps the training fit's φ_extra and the variance terms and replaces the monthly regimes by the flat `level36`. A prospective survey (`Session.survey(prospective=t0)`, `tools.PROSPECTIVE_TIERS`) reads BPA for the outbreak lens and BP for the others. The alarm's false-alarm rate per place over time stays phase 4 (ADR-0004 item 4).

### 6.2 Calibration

For each field and tier, the **randomised PIT** of each observed cell under its posterior predictive:

```
u_c = F(y_c − 1) + V_c · p(y_c),   V_c ~ U(0,1) seeded by (field, cell)
```

**Uniformity** is tested by KS and by the PIT histogram per field, per tier and per macro-region.

**The criterion is a minimum relevant departure (P5), not a p-value.** With 10⁵ cells, any departure is significant.
- A field is calibrated when its PIT's KS distance is ≤ 0.03 overall and ≤ 0.05 in every macro-region.
  - The component varies by macro-region (below; ADR-0006): with it 30 of 33 measured fits are calibrated at B1 and 27 at B2, against 28 and 25 for one value, and 18 and 22 for the block's φ alone.
- A macro-region's 5,000–25,000 cells reach KS ≈ 0.02 by sampling alone.

**A miscalibrated field** gets a field-level **place-year variance component**: Var(Y_ut) = μ + μ²/φ_agg + μ²/φ_extra, with φ_extra by maximum likelihood on the field's aggregate cells.
- **It varies by group of places, in a hierarchy:** the field's value, then one per macro-region, then one per state (`surprise.DISPERSION_LEVELS`).
  - Each group's log(1/φ_extra) is estimated by maximum likelihood on its own cells, then shrunk toward its parent's by the between-group variance τ² that the groups show (random-effects moment estimate on the observed information, so a group with little information keeps its parent's value).
  - The PIT, the weights and the surprises carry the place's own value; BP carries the value of the training fit (§6.1).
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
| outbreak, change point | outbreak: each cell's upper tail under the B2/B2s predictive (the PIT; prospectively under BPA, the alarm baseline, §6.1), with BH. Change point: per place, the exact NB tail of each trailing window, with Bonferroni over the windows, then BH across places | the predictive, exact; simulated nulls failed on sparse fields (evaluation 2026-10-04) |
| space-time cluster | §7.2 over place × time | §7.2 |
| group disparity | per unit of each scale: likelihood-ratio heterogeneity of the groups' SIRs against the national **observed** group pattern (B0 by group, re-levelled to the observed national total of each year and group), each group's deviance divided by its NB variance factor | non-central χ²(df, sd²·Σμ/k) |
| trend divergence | per unit of each scale: `β_u − mean_{N(u)} β` from B2 (reference `neighbours`) or `β_u` (reference `national`, B1 carrying the national course), in posterior standard deviations | the posterior (a coarser unit: Student t, sd inflated by its dispersion around a cubic course) |
| observation | the same lenses on recording-practice fields (ill-defined share, secondary-diagnosis coding, race reliability, notification delay) | as above |

**Scales (`scans/scales.py`).** A per-place lens reads a **scale**: municipality, IBGE immediate region (about 510 units) or state (27). A trend shared by a whole state cancels between a municipality and its neighbours and is a divergence only at the state; a sex-age pattern too thin to show in a municipality shows in the state. Every unit of every scale is tested in one family, with BH **within each scale at q / (number of scales)** (FDR ≤ q overall; one BH over all units charged the 27 states at the price of the 5,570 municipalities). The unit's B2 trend is the same Newton as the municipality's (`surprise.refit_place` on Σy against the offset Σμ, vague prior), and its locus is its member municipalities. Two trend estimands are declared (P4): against the neighbours and against the national course.

**The survey runs what the gate allows** (`tools.SURVEY_PLAN`; evaluation 2026-10-05-lens-positives). By default: outbreak, change point and space–time at the municipality, and the trend against the **national course at the region and state scales** (BH at q/2). Not run: the trend against the neighbours (recovers no positive), the national trend at the municipality (fails the time-shift negatives), group disparity (fails its negatives). `survey --ungated` runs them as families of their own (suffix `|ungated`, scales as multiplicity) and their leads carry `gate="failed"`: they sort after every gate-passed lead, a story built only on them has rank 0 and a `gate failed` flag. A region or state lead's trend replication is not defined (it reads a municipality's contrast with its neighbours): `untested`.

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
| **E_i, between institutions** | as E_b on the institution lattice; first stage: a facility's step against its catchment-expected events (§4.5), no pair yet | as E_b, on the care-flow graph |
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

A map is a graph over many fields at once, built from the §7.5 pair test (`scans/maps.py`, inputs in `scans/map_inputs.py`, `pegasus-core map`). Fields are place effects (shrunk Poisson intercepts over the indirectly standardised expectation) of SIM chapters, SIH chapters (admissions that did not end in death: the in-hospital deaths are SIM records, §8.5), SINASC indicators and context fields (census, SIDRA, CNES, ANS, INEP).
- **Marginal layer:** E_b for every testable pair at δ_E.
- **Conditional layer:** E_b|Z for every testable pair, Z the other declared context fields, n_eff − dim(Z). Present in both layers is direct; marginal only, explained by the context; conditional only, suppressed by it.
- **Overlap:** a pair whose measured overlap exceeds 0.05, or is unknown, is not tested (§8.5). SINASC indicators share births, so their pairs are measured from records and mostly excluded.
- **Error control over the whole map, per layer:** families (estimand, field group × field group); TreeBH family → pair with Simes at each node, Benjamini–Yekutieli over the layer as the stricter alternative.
- **Negatives (`harness.map_negatives`):** the map rerun on Moran-randomised surrogates of every field, generated on another graph than the one that tests, optionally with the contexts kept real; every edge found is false. `harness.map_delta` calibrates δ on them.

The sparse + low-rank graphical model with StARS penalties is not built (§13).

### 7.7 On demand

**Explaining away.** For a lead with support S and a candidate driver x(u,t) (a context field, a capacity change):
1. refit the lead's field locally (B-tier of the lead) with x added;
2. report the coefficient with its interval, and the **absorbed share**:

```
A = 1 − D'_S / D_S,     D_S = 2 Σ_{c∈S} [ y log(y/μ) − (y − μ) ]
```

D'_S is the same with the augmented μ'.

**Decomposition.** The change in expected events between two periods, split into population size, age–sex composition, place mix and risk (η). Each by counterfactual substitution of one component at a time, averaged over all orders (Shapley; exact for these four components). The risk part is reported by place and by group.

**Triage (`explain.triage`, `Session.triage`).** A lead is read against what the data at hand can say about it, in order, and the first rule that fires gives its class (`lead.robustness["triage"]`; artefacts become `explained`): *system* (the denominator broke; the code's national level moved; the ill-defined chapter moved opposite; a residual category trending), *substitution* (siblings under the same parent undo the change), *noise* (too few events or too small an effect), *facility*, otherwise *signal*, which means **unexplained by the data at hand, not confirmed**. Evaluation 2026-10-05, lead triage.

**Facility (`facility`).** The event cube by residence × recording facility × 3-character code × year (SIH-RD `CNES`, SIM-DO `CODESTAB`; one gateway-cached table per year). A lead is `facility` when at most `FAC_K` = 3 facilities carry at least `FAC_SHARE` = 70 % of its change (window against base years), that concentration is not what the facilities' size would carry (one-sided binomial p < 10^-3 against their share of the block's base-year events, unless they are the whole place), and a mechanism shows in the facilities' own behaviour: the same facilities' residents of *other* places show the same step in the lead-code share of the block (z >= 3, at least half the inside log ratio), or the facilities' volume without the lead's events stepped by x1.6. Concentrated but the others do not move: `place_specific`, the lead stays a signal. The class says the change is attributable to one institution's recording or volume; it does not say whether the institution coded differently or served a real event (a referral hospital receives both). SIM names a facility for 71-73 % of deaths only, so the read is partial there.

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
- **Agents.** Exploratory tests are logged but carry no claim. Claims pass through `confirm` (§9.3) on the reserve (§8.3), whose stream is controlled by online FDR (LOND).

### 8.3 Replication (ADR-0015)

A lead is selected on data and confirmed only by **units that took no part in the selection**. Splitting a cell's own events cannot do it: the sides share the cell's frailty, so under extra-Poisson variation the excursion that selected the cell shows on the other side (ADR-0007, withdrawn; OPEN_QUESTIONS 7).

| independent unit | test |
|---|---|
| **later years** (`temporal`) | selected by a survey on the years up to t (`Session.train`); the fit refitted without the later years (BP, the place's course not carried forward); the same places tested on the later years' sum, re-levelled to each state-year's observed course (`replication.relevel`), one-sided at the lens's minimum effect; BH over what was tested. A persistent or recurring departure replicates; a one-off event cannot. |
| **other places** (`spatial`) | for a claim about a predeclared unit (a state's or region's trend): the lens on one random half of its municipalities (immediate regions halved) must reach 0.05; the same statistic on the other half, separated by a buffer of graph neighbours (ADR-0005), is the p-value. A cluster or a municipality was chosen among the places: untested. |
| **another record system** (`corroborated`, §8.3.2) | the lead's places and years in S2iD, SINAN or SIH against that field's own place-set null |

**Tiers.** R0 passes §8.2 on all data; R_k holds k of the three confirmations. They count independent evidence and are not a ladder; a lead's kinds are listed by `explain_lead`.

**Corroboration (§8.3.2).** The place set and years of a lead, in a field that shares none of its records: SIM deaths against S2iD (disasters), SINAN (notifications) or SIH (admissions that did not end in death: the in-hospital deaths are the SIM records, §8.5, and their share is recorded). **The null is the corroborating field's own:** the same statistic (places with a registered disaster; the log ratio of the window's count to the places' median year) on random place sets of the same size, in the same states, in the same population quintile, over the same years; p = (1 + #{null >= observed}) / (1 + B), B = 4,999. BH within each source. A deficit is not corroborated by a field. The rules (which field for which codes) are data (`corroborate.RULES`). The null sets are scattered; a contiguous cluster shares its neighbours' shocks (OPEN_QUESTIONS 7).

**The event split** (`control.SIDES`, A 50 / E 50; `Session.honest_sizes`) is kept for sizes only: given a cell's rate its sides are independent Poisson counts, so the rate ratio read on E, with its exact Poisson interval, is unbiased for the locus's realised rate whatever A selected. It includes the cell's frailty and is no evidence of recurrence.

**The confirmation reserve is a reserved period** (`control.RESERVED_PERIODS`: SIM.DO 2024, final after every fit and survey on 2010-2023). `monolith.assemble` and `Session` refuse it (`ReservedPeriod`); only `confirm_many` opens it (`reserve_open`). A claim (a persistence claim: fixed places and direction) is tested once on it against the fit on the session's years, and its p-value enters one LOND stream (§8.2) whose state is read back from the ledger (`control.Reserve`, split `period:reserve`); the order of the claims is fixed before the reserve is read. Preliminary years are added only when final.

## 9. Leads, the ledger, use

### 9.1 The lead

```
Lead
  id, kind            residual | subset | pattern | relation | cohort | observation | structural
  estimand, tier, fields, support, locus (places, times, groups, codes, institutions)
  effect              estimate, interval, scale (rate ratio | ρ | log RR | share absorbed)
  test                statistic, p, q, family, null, calibration status
  replication         R0..R3, with each replication's effect
  robustness          C-robust (race), denominator tension, recording flags, overlap, triage class (§7.7)
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
| `confirm(claim)` | one run on the reserved period (§8.3), ledgered, under LOND |
| `train(t)`, `temporal_confirm(t)`, `spatial_confirm(leads)`, `corroborate(leads)`, `honest_sizes()`, `retier(leads, selected)` | the independent-unit tests, sizes after selection, the tier (§8.3) |

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
| dengue epidemics | outbreak and space–time, **BP** (trained before the epidemic; measured 2026-10-05: B2s absorbs epidemics into each place's fitted history) | by state |
| dengue seasonality | calibration and season amplitude, B2s | by region |
| leptospirosis after the floods | space-time | Rio Grande do Sul, May–July 2024 |
| Chagas disease, schistosomiasis | spatial cluster, B0 | known endemic areas |
| infant mortality ↔ income, sanitation | E_b | national |
| diarrhoea admissions ↔ sewerage | E_b (census years) | national |
| Roemer's law: SUS admissions ↔ SUS beds per capita (CNES December stocks), declared before the run | E_b and E_b\|Z (log GDP pc, urban share) | municipalities, 2015–19. **Recovered:** ρ +0.264 (n_eff 1,365) and +0.252, p < 5e-5 at δ_E; an association between place effects, not evidence that supply induces demand (evaluation 2026-10-05-cnes-supply-pairs) |
| ESF coverage ↔ infant mortality (Aquino 2009, Rasella 2013), declared before the run | E_b\|Z (log GDP pc) | municipalities, 2018–22. **Not recovered:** ρ +0.068 (p 0.32), the sign is wrong; ESF reached the poorest first and the panel designs that find the effect are within-municipality |
| sanitation ↔ infant mortality / diarrhoea survives adjustment for primary care, declared before the run | E_b\|Z (log GDP pc, ESF coverage, agents) | **Met (2 of 3):** IM ↔ no bathroom (+0.166, p 0.012) and DIA ↔ no bathroom (+0.208) stay admitted, IM ↔ water (−0.103, p 0.108) does not |
| winter respiratory admissions: seasonality | the B2s season's peak month and amplitude (calibration and Jaccard over region × month), not the outbreak lens: an expectation that holds the winter cannot flag it (measured 2026-10-05: South peak July, amplitude 1.80 observed against 1.71; Jaccard 1.00 at B2s against 0.56 at B1) | South, Southeast |
| winter respiratory admissions: an anomalous season | the outbreak lens at BP against past winters | South, Southeast; a declared year |
| COVID-19 enters the record in 2020 (a new cause code; train ≤ 2019) | change point, **BP** (B2 absorbs a step older than the last years: in-sample, 1 of 5,285 places) | the 5,285 municipalities with ≥ 5 deaths, 2020–23 |
| homicide divergence across UF borders (Atlas da Violência 2019, 2025 UF tables), declared before the run | trend divergence, B2 (X85–Y09), reference `neighbours` | 30 municipalities with a ratio ≥ 1.5 against their neighbours' UFs over 2010–23; **not recovered** at the municipality (7 findings, none documented) nor over three scales (weighted recall 0.048: only Alagoas; the states' contrasts reach t 3.1–3.5, p 0.006–0.01, above the per-scale BH level). The 2013 installed municipalities, seen before documented, are withdrawn |
| homicide divergence from the national course (same tables; declared in a second commit, after one look at the national lens against the first loci), declared before it was scored | trend divergence, B2, reference `national` | 2,289 municipalities of 14 UFs with a ratio ≥ 1.5 against Brazil's slope; **recovered at region and state scales**: weighted recall 0.66, Jaccard 0.77, precision 0.50 (10 states, 89 regions); the municipality scale alone 0.08 and fails the time-shift negatives (5/30 worlds), so it is left out of the estimand |
| women's and young men's share of homicide victims by UF (Atlas da Violência 2025 Tables 2.2, 4.3, 5.1), declared before the run | group disparity, B0 (X85–Y09) | municipalities of the UFs with a ratio ≥ 1.25 or ≤ 0.8 to Brazil's. With the reference re-levelled to the observed national totals (it had overstated women's share, 9.98% against 8.2%) and the municipality alone: weighted recall 0.05 and 0.03, **not recovered**. Over three scales at sd 0.05 (regions, states): 0.97 and 0.94, but 22 of 27 states depart and the spatial negatives reject any sd below 1.0 (**fails the gate**). Roraima's female homicide, seen before documented, is withdrawn |

**Criterion for per-place lenses.** Cell-sparse outcomes cannot meet a place-level Jaccard 0.5 (the documented excess sits in a few places, the lens resolves others). For change point, trend divergence and group disparity the criterion is the **recall of the documented places weighted by their documented excess ≥ 0.5, with the effect's sign**; the Jaccard and precision are reported (`harness.recovery`). The pass of a positive is judged on the tier the lens runs at; a documented effect below the lens's minimum relevant effect (§8.4) is not a positive for it.

**Marks have no declared positive.** The floor was 3% and the documented Brazilian effects are below it: COVID-19 preterm births about 0.1% of the mean weight; the regional gap in mean birth weight (Northeast 3,287 g, Southeast 3,210 g, 2005, "The epidemiologic paradox of low birth weight in Brazil", Rev Saúde Pública 2010) is 2.4%. The floor is now **1.5%** (calibrated on the PESO negatives, §8.4), which that gap exceeds; it is a level difference between regions, which B1 absorbs, so only a B0 spatial scan of a mark could recover it, and that is ungated, and the source is for 2005 against the fitted 2010–23. A positive is declared when a 2010+ source and the B0 mark scan exist.

### 10.2 Known negatives

Each negative keeps a field's own dependence and removes the relation:

- **Between places:** Moran spectral randomisation (Wagner & Dray 2015) on the **symmetric-normalised** adjacency D^{-1/2}WD^{-1/2}, generated on a different graph from the one the test uses (ADR-0005). The field's coordinates in the Moran eigenvectors get random signs, which keeps its spatial autocorrelation spectrum. On the raw border-weight matrix the top eigenvectors are localised, and the null spread came out 3.5× too small (measured 2026-10-05).
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
| `laplace` | the Laplace posterior of a fitted count block (§5.3): information from pairwise marginals, perturbation draws, predictive moments, the history's forecast error, full-Hessian Fellner–Schall | monolith |
| `surprise` | tiers (§6.1), PIT and calibration (§6.2), the virtual cube (§6.3) | monolith, laplace, prospective |
| `prospective` | BP's predictive (§6.1): the training fit's φ_extra, the place course, the mixture PIT | monolith, laplace, surprise |
| `scans` | a subpackage: `lenses` (§7.1), `subset` (§7.2–7.3), `patterns` (§7.4), `pairs` (§7.5), `maps` and `map_inputs` (§7.6), `explain` (§7.7), `cohort` (§7.8) | surprise, monolith, fields |
| `control` | the ledger (§9.2), families and FDR (§8.2), splits and replication (§8.3), LOND | store |
| `replication` | the later-years and other-places tests, sizes on side E, matching a lead to its selecting finding, size/power simulations (§8.3) | monolith, surprise, scans, leads, control |
| `facility` | the event cube by residence × recording facility × code × year (gateway-cached per year), the per-lead facility tally for the `facility` triage class (§7.7), the supply term of a block's expectation and the institution lattice (§4.5) | gateway, store, config |
| `corroborate` | the independent fields (S2iD, SINAN, SIH) and the place-set null (§8.3) | gateway, store |
| `leads` | the lead object, ranking, register | control, scans |
| `harness` | positives, negatives, planted signals, surrogates, power curves, the gate (§10) | all of the above |
| `store` | content-addressed artefacts (§11.3) | pyarrow |
| `tools` | the agent and person interface (§9.3); MCP server in phase 3 | leads, scans, surprise, gateway, replication, corroborate |
| `mcp_server` | the tools over MCP (§9.3, ADR-0008): read-mostly, `confirm_claim` guarded; optional extra `mcp`. Built and paused: use and integration to be planned with the author | tools, leads, control |
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
| **3** | patterns across blocks; dependency maps; tools over MCP (built, ADR-0008; paused: its use and integration are to be planned with the author); institution lattice (first stage built, ADR-0016: the supply term and the facility steps for SIH; crossed place × facility effects at the node level remain); agents | race measurement; new population sources; CNES fields; APAC families | each with its own positives |
| **4** | prospective surveillance (ADR-0004): weekly grain; an outbreak-robust alarm baseline; a nowcast from in-record delays; alarms controlled by a false-alarm rate; syndromic scans across SIM, SIH and SINAN | dates of notification, entry and processing typed in every family; snapshots of the preliminary files (for revisions) | a benchmark against published alerts (InfoDengue) and confirmed epidemics: timeliness, false alarms, hits |

---

## 13. Departures

*Where the code knowingly departs from this document, with the reason. Each row closes when the code catches up.*

| § | the document says | the code does | why |
|---|---|---|---|
| 4.3 | horseshoe on tree levels, one variance per level per top branch | iid Gaussian per level, τ by Fellner–Schall, per block (= per top branch) | the horseshoe needs sampling or a reweighted penalty; the iid level is its first step |
| 4.3 | BYM2 with a learned mixing ρ | BYM: separate τ for the scaled ICAR and the iid part; ρ reported from the two τ's | the same model reparametrised, its τ's learned by the same updates as every other effect; the priors differ |
| 4.2 | geography carried down to a declared level ℓ_g | groups carry ICAR + iid; categories carry an iid `v_cat[e, u]`, centred within the group | the category-level place deviation is real (chapter IX: sd ≈ 0.47), and the coding-substitution leads read it |
| 4.2, 5.4 | the low-rank interaction ψωτ | not yet built | main effects and tiers first; patterns across blocks (CP-APR) read the interaction meanwhile |
| 5.2 | every strength is learned (P7), the dispersion by place group included | φ_extra is a hierarchy (field, macro-region, state); the block's φ is one value per block | the block's φ by macro-region gained 0.009 nats per event held out on dengue and −0.0007 to +0.002 on chapters IX, X and XVIII (ADR-0006) |
| 5.3 | Laplace uncertainty; marginal sds by selected inversion and Hutchinson–Lanczos | built (`laplace.py`), measured, off by default: perturbation draws on the exact NB information, CG with a block-Jacobi preconditioner; the predictive matched by moments | the draws match the exact inverse at their Monte-Carlo floor; parameter uncertainty is at most 10 % of the overdispersion and does not repair dengue's or BP's miscalibration (evaluation 2026-10-05, Laplace); the check against MCMC/INLA remains OQ-2 |
| 5.3 | Fellner–Schall on the full Hessian | Fellner–Schall with the Poisson Fisher diagonal per effect (block-diagonal), damped to ×10 per iteration; a τ above 10⁵ counts as converged. The full-Hessian update exists (`Posterior.fellner_schall`, from the draws) and is not in the fit | on IX it proposes τ_s 5× lower (425 → 72–81) and τ_s,grp 5× lower; whether a refit there calibrates better is untested |
| 6.1 | B2s on every field; BP is a mixture over the history's regimes, not the RW2 forecast | the monthly grain (season: cyclic RW2 over 12) is built for event counts; B2s refits trend + one harmonic per place; marks and code lists stay annual. BP at the annual grain damps the last slope (0.5 per year) and adds each place's damped B2 trend; at the monthly grain h is not extrapolated but drawn from the fit's years (a flat level36 baseline reached obs/expected 2.2 on dengue, the climatology 1.2; the outbreak-robust and level36 point baselines of evaluation 2026-10-05, baseline history, remain as `history=`) | the last two months' slope is noise at that grain; an epidemic series has no level to extrapolate; places drift apart (evaluation 2026-10-05, BP level) |
| 10.1 | marks and E_w each recover a documented positive | marks: none declared; E_w: the cold → respiratory admissions effect (RR 1.07, Requia et al. 2023) gives ρ −0.02 to −0.07 at monthly municipal grain, below δ 0.1; arbovirus → microcephaly not recovered at region grain | no citable mark shift ≥ 4%; the E_w documented effects are weak at this grain (evaluation 2026-10-05-lens-positives) |
| 7.2 | groups as a free dimension of every subset scan | the scanner takes any free dimensions; the cell lenses pass places × time. Group disparity is a per-unit G² over the groups (not a subset scan of them), at the municipality, region and state scales (`scans/scales.py`); the trend lens reads the same scales | a subset scan over groups × places needs the per-group surprise in the scanner; the G² at three scales answered the documented departures (evaluation 2026-10-05-lens-positives). `Session.survey` runs the gated combinations (§7.1); a multi-municipality locus is a story of its own, its trend replication untested, and the group lens runs only `--ungated` |
| 8.2 | TreeBH (Bogomolov et al. 2021) | TreeBH with Simes aggregation at each node | the exact combination is a later refinement |
| 11.3 | artefact keys hash pegasus_data's data versions | keys carry pegasus_data's package version, plus the sha256 of the shipped resource for artefacts derived from one (code structures, graphs); the commit is recorded in each manifest | pegasus_data exposes no publication-level data versions yet, and its commit changes with every edit |
| 3.1, 4.1 | the population carries uncertainty and N enters the predictive with it | `account-2` and `account-3/4` carry it (σ of log N from the 80 % interval; `Monolith.exposure_variance`, ρ = 0), but the default source is POPSVS, which has none | no account is better than POPSVS on chapter IX or births deviance (account-3: births B1 +0.4 %, held-out KS .096 against .059; its births loss sits in 2020–2023 in places of 25–1000 births a year), and its exposure variance double counts the φ already estimated with μ fixed (evaluation 2026-10-05, exposure; ADR-0010). Closes when φ is estimated with the exposure variance in |
| 2.1 | meaning comes from pegasus_data | `gateway._date_sql` parses raw date text (YYYYMMDD, DDMMYYYY), and `_residence_sql` maps the Federal District's administrative-region codes in SIH-RD 2008–2017 to 530010 | interim; pegasus_data now derives `<COL>_date` and `MUNIC_RES_municipio` (pegasus_data c893b69, 1f88401). Binding the roles to them changes every gateway cache key, so the switch waits for the next re-warm |
| 8.4, 10.2 | δ is the smallest value at which no family's false-lead rate on the negatives exceeds q; single-field lenses have negatives that keep the field's dependence | spatial cluster θ0 = 1.5 (pooled negatives 0.04, worst family 5/30), where the family rule gives 2.0; single-field negatives are MSR of the residuals on a knn8 graph and a per-place shift, with a normal-scores variant | θ0 2.0 loses the Chagas positive; the B0 residuals carry smooth place effects, which a Poisson scan reads as clusters. Closes with a B0 scan null that carries the field's spatial spectrum |
| 7.6 | a sparse + low-rank Gaussian graphical model, penalties by StARS, edges also passing the pair test | pairwise E_b and E_b\|Z given the declared contexts, no joint model; run 2026-10-05 (ADR-0013): delta_E|Z 0.1, 0 false edges in 40 surrogate worlds | each pair carries its own spatial n_eff, which a joint likelihood has no place for; the conditional layer conditions on declared contexts as the low-rank part would |
| 4.5 | the facility effect is part of the model: a place × facility supply term estimated with the monolith, and crossed place and facility effects at the node level | the supply term is a multiplier of the fitted expectation, with two exponents chosen by likelihood after the fit on the same cells (opt-in); the facility's own handling of a node (coding) is not subtracted, only read on the lattice | the independent evidence (other chapters) removes 11 % of the facility class and 6.5 % of the signals (evaluation 2026-10-05, institutions); what the facility does with the block's own codes cannot be subtracted without absorbing an outbreak that one hospital serves. A refit with the term inside the likelihood, and crossed effects where places share facilities, are the next stage |
