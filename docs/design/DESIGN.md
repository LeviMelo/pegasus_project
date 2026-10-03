# PegaSUS: design proposal v0

**2026-10-03, revised the same day (v0.1):** own demographic model (§4.1); subset scanning, pattern decomposition and dependency maps (§7.4–7.6). A complete proposal, written so the author can react to something concrete. The author asked the agent to adjudicate. **Everything here is a proposal until the author accepts it**; the choices the agent was least sure of are listed in §13.

**Inputs:**
- the discussion of 2026-10-03;
- `docs/discussion/2026-10-03-what-was-built.md`, what the earlier engine actually did;
- `docs/RECOLLECTION.md`, the ideas and their history.

---

## 1. What PegaSUS is

**PegaSUS scans all of Brazil's health, demographic, institutional and context data for leads, with a known error rate.**

- **A lead** is a structure in the data that departs from a declared expectation beyond a calibrated null, has an effect size worth knowing, and comes with a record of whether it replicates.
- **Leads are not conclusions.** They need not be epidemiologically interpretable when found.
- **Two kinds of explorer use the same substrate:**
  - the **systematic scan**, deterministic and exhaustive over what it enumerates;
  - **agents** (LLMs in a single loop, with tools and an objective), which go where no enumeration reaches.

**Principles**, each traced to a documented failure:

| principle | the failure it answers |
|---|---|
| **The expectation comes first.** Every cell is compared with what it should be given its population, place and time. Sophistication goes into that expectation. | pooled rank transforms baked gradients into "standardised" data; corr(z, log population) = 0.93 |
| **The estimand is declared.** Between places, within places over time, between strata, between institutions: separate scans, separate nulls, never switched silently. | a fixed effect turned the residual scan into a within-place test without anyone deciding it |
| **Every cell carries its precision.** A cell with 2 deaths and one with 2,000 never weigh the same. | unit-variance transforms; weights computed and unused |
| **Effect sizes against minimum-effect nulls.** At national n, "different from zero" is not a lead. | CKA 0.04 certified; the effect floor was the strongest lever |
| **The multiplicity arithmetic is designed, not discovered.** Analytic p-values with calibrated tails; every test counted. | the output size was set by permutation floor × BY |
| **Observed data stay observed.** Sparse context is used where observed. Modelled quantities (denominators, race composition) are labelled, carry uncertainty, and are validated by holding data out. | an interpolation presented as a tensor; reconstructed context never certified; a flat 0.02 uncertainty |
| **Nothing is trusted before it passes the benchmark** of known positives, known negatives and planted signals, run on real data. | the validation programme written and never run |
| **Nothing is blind.** Records, linked cohorts, places, institutions and recording practice are all scannable. | — |

---

## 2. Layers

```
                ┌──────────────────────────────────────────────────────────┐
 agents, people │  L8 tools      search · describe · map · scan · compare · confirm · records
                ├──────────────────────────────────────────────────────────┤
                │  L7 leads      typed leads, tiers, rank, provenance         ◄─ L6 ledger + error control
                │  L5 scans      lenses (one field) · pair scans (two fields) · cohort scans
                │  L4 surprise   per field, per cell: y, μ, z, w at each expectation tier
                │  L3 expectation per field: a model of what each cell should be
                │  L2 denominators & measurement: population at risk; race composition;
                │                 race misclassification; recording-reliability flags
                │  L1 fields     registry of every field: kind, lattice, support, law,
                │                 exposure, construction signature, provenance
                ├──────────────────────────────────────────────────────────┤
 pegasus_data   │  L0 gateway    records · aggregates · labels · linkage · POPSVS · census ·
                │                 IBGE context · CNES · geography lattices
                └──────────────────────────────────────────────────────────┘
 across all:  V  validation harness: known positives, known negatives, planted signals, null surrogates
```

**The boundary with pegasus_data:**
- **pegasus_data holds observed data and its meaning.** It never models.
- **PegaSUS holds every model:** race composition, misclassification, expectations; and every result: surprises, scans, leads, ledger.
- **PegaSUS reads only through pegasus_data's API.**

---

## 3. L1: fields

### 3.1 The object

```
Field
  id, name, family            # family = a node in a hierarchy (ICD tree, CNES type, SIDRA theme)
  kind      count | total | share(num, den) | level | published_rate
  lattice   municipality | comparable_area | health_region | state | institution | …
  grain     day | week | month | year
  strata    axes inside the field: age × sex (× race)   — strata are axes, not separate fields
  support   the observed (unit, time, stratum) cells; missing cells stay missing
  law       sum | ratio_of_sums | weighted_mean(weight field) | none
  exposure  the person-time field it is measured against (counts), with its strata
  signature the predicate that defines its events (record-derived fields)
  provenance pegasus_data query, data version, code version
```

### 3.2 Where fields come from

| source | generator | lattice |
|---|---|---|
| **Event records** (SIM, SIH, SINASC, SINAN, SIA, CIHA) | system × event × condition × code role (underlying cause, any mention, principal or secondary diagnosis) × place role (residence or occurrence). Conditions descend a code hierarchy (chapter → block → three characters) **only while the expected count supports it** (§3.3). | municipality, institution |
| **Linked cohorts** | cohort outcomes aggregated per place-time: births followed by neonatal death, admissions followed by death within 30 days, readmission | municipality, institution |
| **CNES** | capacity (beds by type, equipment, staff, accreditations), per establishment-month; summed to places | institution, municipality |
| **Recording practice** | share of ill-defined causes, of secondary diagnoses coded, race-recording reliability, notification timeliness | institution, municipality |
| **IBGE and SIDRA context** | as observed, at their own support and years | as published |
| **Climate, environment** | as published | as published |

### 3.3 Sizing by information, not enumeration

- **A record-derived field is admitted only if its expected events support a test.** The default rule is at least 1,000 events over the scan window *and* events in at least 5% of units. A code-tree branch stops descending where its children would fall below that.
- **Strata never multiply fields.** Age, sex and race are axes inside a field: expectations use them, and the stratum lens scans them.
- **Expected size:** a few thousand record fields, plus a few hundred context fields. That is about 10⁷ pairs per estimand, enumerable and countable.

### 3.4 Construction signatures and mechanical overlap

Every record-derived field carries the predicate defining its events. Its overlap with another field can therefore be **measured exactly** from the records:

```
overlap(F, G) = |events(F) ∩ events(G)| / min(|events(F)|, |events(G)|)
```

The same applies to parent and child codes, a count and its own share, and one death counted under two causes. Pairs above 0.05 are never tested for dependence. They may be tested *conditionally*, on the events not shared.

### 3.5 The support lattice

- **Spatial units are partially ordered:** municipality ⊂ immediate region ⊂ intermediate region ⊂ state ⊂ macro-region ⊂ Brazil; municipality ⊂ health region ⊂ state; institution → municipality. Comparable-area lattices (pegasus_data ADR-0126) absorb boundary changes.
- **Time:** day ⊂ week ⊂ month ⊂ year.
- **Two fields are compared on their common support:** the finest support to which both can be lifted by their aggregation laws. A field with law `none` cannot be lifted.
- **Census-year context compares at census years.** It is never densified for a test.

---

## 4. L2: denominators and measurement

### 4.1 Population at risk: our own demographic account

**Decision (author, 2026-10-03): PegaSUS builds its own population model.** POPSVS is one of its inputs, and the benchmark it must beat.

**The model.** The true resident population is a hidden state, `N(u, t, a, s, r)`: municipality, year, single age, sex, race. It moves by **demographic accounting**:

```
N(u, t+1, a+1, s, r) = N(u, t, a, s, r) · S(u, t, a, s) + M(u, t, a, s, r) + R(u, t, a, s, r)
N(u, t+1, 0,   s, r) = B(u, t, s, r) · S₀(u, t, s)
```

- S is survival.
- M is net migration.
- R is race reclassification between categories, which sums to zero over r.
- B is births.

**Many sources observe it, each through its own data model** (coverage, completeness, delay, noise). This is the "Bayesian demographic account" of Bryant & Zhang, *Bayesian Demographic Estimation and Forecasting* (2018).

| source | observes | data model |
|---|---|---|
| censuses 2000, 2010, 2022 | N, by municipality × age × sex × race | coverage error by age, sex and region |
| IBGE annual municipal totals | Σ N | small noise; the official constraint |
| IBGE state projections, life tables, fertility | S and B by state | priors |
| POPSVS (RIPSA) | N by age × sex | another model's estimate: an informative observation, not truth |
| SINASC | B, by mother's residence × age × race | completeness by state and year |
| SIM | deaths, so S | completeness by state, age and year |
| electoral roll (TSE), every two years | adults by municipality × age × sex | registration lag; transfers reveal adult migration |
| school census (INEP) | children by municipality × age | enrolment coverage |
| CadÚnico | persons by municipality × age × sex × race | covers the poorer population; race declared |
| primary-care registrations (SISAB) | persons by municipality | coverage varies by team |
| formal employment (RAIS/CAGED) | workers by municipality × age × sex × race | an economic-shock signal |
| census migration questions | origin–destination flows, 5-year | prior on M |

**Availability.** These sources are not yet behind pegasus_data except the censuses, POPSVS and IBGE totals. Each one is acquired behind the gateway first.

**Inference.** A Bayesian state-space fit on the log scale, hierarchical by intermediate region and state. It runs per state in parallel; states are coupled through migration totals.

**Outputs, each a field in its own right:**
- the posterior of N per cell, with its interval;
- **net migration** by municipality × age × year, which shows where people went and when;
- **reclassification** by cohort ("browning");
- **the completeness of SINASC and SIM** by municipality-year;
- **shocks** between censuses: a municipality whose sources disagree with smooth growth (a mine closing, a dam failing, a frontier opening).

**The test that shows we do better.**
- Predict the **2022 census** by municipality × age × sex from data up to 2021 only.
- Compare with RIPSA's pre-census estimates for 2021–2022 (its 2000–2021 series).
- The error, by municipality size and age, becomes the uncertainty model.

### 4.2 Race misclassification

**Settings.** σ = (system, who records, region, period). Code faults are removed before modelling: a hospital-month whose race field is a default fill or another system's codes (pegasus_data ADR-0128 flags them).

**A structured confusion matrix.** No one misclassifies at random.
- **On the ordered axis branca (1) – parda (2) – preta (3):**
  ```
  C_σ(k | j) = 1 − λ_σ − δ_σ    if k = j   (boundary rows renormalised)
               λ_σ               if k = j − 1   (lightening)
               δ_σ               if k = j + 1   (darkening)
  ```
- **Amarela and indígena:** a retention probability each, with leakage to parda or branca.
- **Missing:** its own column, with p_miss,σ(j) allowed to depend on j.
- **The propensities depend on the setting:**
  ```
  logit λ_σ = x_σ' β_λ ,  logit δ_σ = x_σ' β_δ      (x = system, recorder class, region, period, age band)
  ```
  The coefficients get hierarchical priors, and priors centred on published comparisons of self- and other-classification. That is a few dozen parameters, against 20 free ones per setting.

**The likelihood: ecological, age and sex adjusted.**

```
Y_{u,k}^{sys} ~ NegBin( Σ_j C_σ(k|j) · Σ_{a,s} P(u,t,a,s,j) · m^{sys}_{a,s,t} · θ^{sys}_j · e^{b_u} ,  φ )
```

- m is the system's national age × sex rate.
- θ_j are the race rate ratios, the quantities of interest.
- b_u are shrunk place effects.

**Identification** comes from how recorded shares track census composition across places. θ and C are partly confounded, so disparities are reported as **intervals over the posterior of C**, not as point corrections.

**Validation:**
1. **Planted misclassification.** Apply a known C to real SIM counts, then recover it.
2. **Linked pairs.** Where the same person appears in two systems, the model predicts their joint classification, `P(k₁, k₂) = Σ_j π_j C_σ₁(k₁|j) C_σ₂(k₂|j)`. The observed cross-table tests the model. Linkage validates; it is not the estimator.

**How it is used.** Race-stratified expectations are computed **in the recorded space**: `μ_{u,k} = Σ_j C(k|j) μ_{u,j}`. Recorded counts are compared with expected recorded counts, and a race lead must survive the plausible range of C ("C-robust").

---

## 5. L3: expectations

### 5.1 The tiers: what counts as boring

Each count field gets a **ladder of expectations**. Each tier declares more structure boring, and every lead states which tier it departs from. For a cell (u, t, g) with exposure N:

| tier | log μ | what remains surprising |
|---|---|---|
| **B0 composition** | log N_{utg} + log r_{g,t} (national rate by stratum and year) | everything a place does differently from Brazil, given its population and the year |
| **B1 smooth space** | B0 + s_u, a BYM2 spatial effect (smooth + unstructured), shrunk | non-smooth spatial anomalies; departures in time |
| **B2 own place** | B0 + α_u + β_u (t − t̄), level and trend per place, shrunk to their region | departures of a place from its own course: outbreaks, breaks, co-movements |
| **seasonal** (sub-annual grains) | the tier + a seasonal profile per region, shrunk | out-of-season events |

**Your "north–south gradient" question is answered by the ladder, not by a choice.** A gradient is a lead at B0 and boring at B1. Both readings are kept.

### 5.2 Model family and estimation

- **Counts:** negative binomial with field-specific dispersion φ, estimated per field. Zero-heavy fields use a hurdle. Shares: beta-binomial. Levels: Gaussian or Student-t on their natural scale.
- **v0 estimation, Python:**
  - B0 in closed form;
  - B1 as a sparse Gaussian Markov random field (the BYM2 precision on the adjacency graph), solved by sparse Cholesky with hyperparameters set per field family;
  - B2 as Poisson–gamma / normal empirical Bayes with hierarchical shrinkage.
- **Reference check:** the same models in R-INLA on a random sample of fields, across scopes (not only the densest slice), as a measured agreement.
- **Libraries:** numpy, scipy, scikit-sparse (CHOLMOD), glum or statsmodels, duckdb/polars; R-INLA as the reference.

### 5.3 Calibration of each expectation

- For every field and tier: the **randomised PIT** of each observed cell under its predictive distribution, then a uniformity test per field, per tier, and per region.
- **A field whose predictive distribution is miscalibrated is flagged** and excluded from pair scans at that tier. It stays visible in the lenses with the flag.

---

## 6. L4: the surprise cube

**One table per field family**, one row per cell × tier:

```
field_id, unit, time, stratum, tier, y, mu, z, w, flags
```

- `z` = Φ⁻¹(PIT), the surprise on a common scale. **It is computed after the expectation, never before it.** That is Gaussianisation in the right order.
- `w` = the cell's information, μ / (1 + μ/φ) for counts, carried into every statistic.
- `flags`:
  - denominator tension (§4.1);
  - unreliable recording (§4.2);
  - calibration failure (§5.3).
- **Size:** 5,570 municipalities × 25 years × a few thousand fields × 3 tiers is about 10⁹ rows of a few floats. That is tens of GB of Parquet, partitioned and scanned by family. Monthly grain only for families with enough counts.
- **This is also what agents see first:** for any field, where and when it is surprising.

---

## 7. L5: scans

### 7.1 Lenses: one field

| lens | statistic | tier | null |
|---|---|---|---|
| **spatial cluster** | Kulldorff Poisson/NB scan of y against μ | B0, B1 | simulation from the predictive, max statistic with an extreme-value tail fit (no Monte-Carlo floor) |
| **outbreak / change point** | surveillance-grade algorithms on each place's series (Farrington-flexible / Noufaily-type for counts; Bayesian change point) | B2, seasonal | the predictive distribution |
| **space-time cluster** | space-time scan | B2 | simulation, extreme-value tail |
| **stratum disparity** | per place, heterogeneity of stratum SIRs against the national stratum pattern | B0 by stratum | NB likelihood ratio |
| **trend divergence** | β_u against its neighbours' | B2 | posterior of β |
| **observation** | the same lenses on recording-practice fields | any | as above |

### 7.2 Pair scans: two fields, at their common support

**Between places (E_b).** The correlation, across units, of the two fields' **place effects**: time-aggregated log SIR at B0, shrunk, weighted.
- **Null:** spatial autocorrelation shrinks the effective sample, so p-values use Dutilleul's modified t (Clifford–Richardson–Hémon effective n from both fields' spatial structure).
- **Calibration:** checked on variogram-matched surrogate maps for a random subset of pairs.
- **Adjusted version (E_b|Z):** partial correlation given a fixed declared set (urbanisation, income, region), stated with the lead.

**Within places over time (E_w).** The pooled correlation of B2 surprises z, lags 0…L, across places.
- **Null:** analytic, with each place's autocorrelation deflating its effective degrees of freedom.
- **Calibration:** checked by circular time shifts per place on a subset.

**Between institutions (E_i):** the same, on the institution lattice.

**Effect sizes** are reported as the correlation and as the implied rate ratio per standard deviation of the other field.

**Minimum-effect null:** H₀: |ρ| ≤ δ (default δ = 0.1, set per estimand by the benchmark's power curves). This is tested with a shifted Fisher z, so negligible dependence is never "significant".

**Compute:** for one estimand, one support class and p fields, the statistic is one weighted Gram matrix `ZᵀWZ`. With p in the low thousands and about 10⁵ cells, that is minutes. Lags multiply it by L + 1.

**Nonlinearity:** rank correlations in v0. Kernel dependence (HSIC) only on short-listed pairs, with its own calibrated null.

### 7.3 Cohort scans: the record grain (v1)

On linked cohorts, every record attribute (diagnosis nodes, procedures, the mother's attributes) is scanned against every cohort outcome:
- Poisson or logistic regression, with a fixed adjustment set (age, sex, year, place effect);
- FDR over the grid;
- the same lead object.

This is the PheWAS shape. It is free of the ecological fallacy by construction.

### 7.4 Subset scanning: the needle finder

The surprise cube has many dimensions: place, time, age, sex, race, code (a tree), institution. A real signal is rarely one cell. It is usually a **coherent subset** whose small surprises add up: these 7 municipalities × these 5 months × women over 60 × these three codes.

**Subset scanning searches for the subset whose combined surprise is largest:**
- **Statistic:** an expectation-based score over a subset of cells, Poisson or NB log-likelihood ratio of observed against expected, each cell weighted by its precision.
- **Search:** over subsets constrained along each dimension:
  - places connected or within a radius;
  - times contiguous;
  - strata any subset;
  - codes along the tree.
- **It is efficient:** the linear-time subset scanning property (Neill 2012; Neill, McFowland & Zheng 2013 for several streams and dimensions; McFowland, Speakman & Neill 2013) finds the best subset of each dimension in linear time. Alternating over dimensions reaches the joint optimum.
- **It finds signals no single-cell test can:** each cell's excess is within its noise, but 100 such cells together are not.
- **Null:** simulation from the predictive with an extreme-value fit of the maximum, so there is no Monte-Carlo floor.
- **Recursive:** after the top subset is reported, it is conditioned out and the next is sought.

### 7.5 Pattern decomposition

A non-negative Poisson tensor factorisation (CP-APR; Chi & Kolda 2012) is fitted to the **counts against their expectations** over place × time × condition (× stratum). Each component is a pattern: *these conditions rose together in these places at these times.*

- **COVID** appears as one component.
- **A coding change** appears as a pair of components: a cause falling exactly where another rises.
- **A new epidemic** appears as a component that is new in time.

Components are leads of the kind "co-occurrence pattern", with stability checked across halves of the data.

### 7.6 Dependency maps

On the **calibrated** surprises of one estimand, a sparse plus low-rank Gaussian graphical model maps which fields move together **after** their expectations, with the shared factors kept apart. The old LDO goal is kept; its failures are not:
- inputs are calibrated per cell, not pooled ranks;
- each cell carries its precision weight;
- one map per estimand;
- the penalty is chosen by stability across the replication halves, not by hand.

This is phase 3, once the pair scans are calibrated, so the map can be checked against them.

---

## 8. L6: error control and replication

**The ledger.** Every test the system or an agent runs is written down **before** it runs, with its family. The systematic scan's hypotheses are enumerated from the registry before execution, so m is known in advance.

**Families and FDR.**
- Families are lens or estimand × tier × field-family pair.
- **Within a family:** Benjamini–Hochberg on analytic p-values.
- **Across families:** hierarchical selection (family-level first, Benjamini–Bogomolov). TreeBH where fields are nested in a code tree.

**Replication tiers,** recorded on every lead:

| tier | meaning |
|---|---|
| R0 | passes FDR on the full data |
| R1 | same sign and at least half the effect in the other temporal half (2008–2015 / 2016–2023 by default) |
| R2 | same in a disjoint spatial half (immediate regions split at random within each state) |
| R3 | the same estimand found through another system (SIM and SIH; SINAN and SIH) |

**The confirmation reserve, for agents.** One spatial half (§13, O3) is invisible to exploration tools. An agent's claim is confirmed on it once, through a logged tool call.

---

## 9. L7: leads

```
Lead
  id, kind (lens | pair | cohort), estimand, tier
  fields, support, locus (units, times, strata)
  effect (estimate, interval), test (statistic, p, q, family, null, calibration status)
  replication (R0..R3 with effects), robustness (C-robust, denominator tension, recording flags)
  overlap (measured), provenance (data versions, code version, ledger id)
  rank   = evidence × effect × replication, never p alone
```

---

## 10. L8: tools for agents and people

Thin, composable, logged:

| tool | does |
|---|---|
| `search_fields(text, filters)`, `describe_field(id)` | the registry: meaning, support, provenance |
| `surprise(field, tier, scope)` | the surprise cube: maps and series |
| `leads(filters)`, `lead(id)` | the lead store |
| `scan(field, lens, tier, scope)` | runs a lens (ledger entry) |
| `compare(field_a, field_b, estimand, tier, scope)` | runs a pair test (ledger entry) |
| `cohort(definition)`, `records(query)` | the record grain, through pegasus_data |
| `confirm(lead_or_claim)` | one run on the reserve; logged; once per claim |

Exploration tools read only the exploration half. The systematic scan reads everything, under FDR.

---

## 11. V: the validation harness, built first

**Known positives.** Each has the lens, tier and locus where it must appear:

| signal | lens / estimand | where |
|---|---|---|
| microcephaly and congenital anomalies, 2015–16 | space-time cluster, B2 | Northeast |
| arbovirus → microcephaly births, lag 6–9 months | E_w, monthly | Northeast, 2015–16 |
| COVID-19 excess deaths; Manaus, January 2021 | outbreak, space-time, B2 | national; Amazonas |
| dengue epidemic years and seasonality | outbreak, seasonal | many states |
| leptospirosis after the 2024 Rio Grande do Sul floods | space-time cluster | RS, May–July 2024 |
| Chagas and schistosomiasis geography | spatial cluster, B0 | known endemic areas |
| infant mortality ↔ income and sanitation | E_b | national |
| diarrhoeal admissions ↔ sewerage coverage | E_b, census years | national |
| respiratory admissions in winter | seasonal | South and Southeast |

**Known negatives.**
- Random partitions of one system's records into two fields: only shared structure can link them.
- A field against its own values shifted by years.
- Fields of unrelated events on the same denominator.

**Planted signals.** A known effect exp(β·x) is injected into real fields' counts (by thinning or adding draws), with a chosen locus. Recovery against β gives each lens's **power curve** and sets δ.

**Null surrogates.** The whole pipeline is run on data simulated from the expectations, with no cross-dependence. The leads found are the **false-lead rate**.

**Gate.** A lens or estimand enters production only when it:
1. recovers its listed positives at its declared tier;
2. keeps the false-lead rate on surrogates at or below its target;
3. reports its power curve.

---

## 12. Build order

| phase | builds | its gate |
|---|---|---|
| 0 | the harness (§11): positives, negatives, spike-in, surrogates | the harness reproduces itself |
| 1 | registry (record fields from SIM, SINASC, SIH; annual); the demographic account (§4.1) with its 2022 hold-out test against RIPSA; expectations B0–B2; the surprise cube; the six lenses; subset scanning (§7.4) | the positives that are univariate; false-lead rate on surrogates |
| 2 | pair scans E_b and E_w; ledger, FDR, replication; measured overlap | the pair positives; the negatives; power curves |
| 3 | race misclassification (§4.2); pattern decomposition (§7.5); dependency maps (§7.6); agent tools; institution lattice; cohort scans; monthly grain for dense families; new demographic sources (TSE, INEP, CadÚnico) | each with its own positives |

---

## 13. What is left out, and the choices most open to change

**Deliberately excluded from v0, with the evidence:**
- **A joint model fitted on raw fields.** Its penalty had no stable value, and its time and space structure were never fitted. The dependency map (§7.6) is fitted on calibrated surprises instead.
- **HSIC as the primary statistic.** It was dominated by haze, degenerate samples and permutation arithmetic.
- **Dense reconstruction of context for scanning.**
- **Automated causal escalation.**
- **GPU work.** The Gram matrix and sparse solves fit this machine.

**The agent's least certain calls:**
- **O1, grain.** Year first; month only for families with dense counts (arboviruses, respiratory, births). Should month come first?
- **O2, the joint model.** Excluded in v0. Is a single model of all fields still part of the vision, beyond what the pair scans give?
- **O3, the confirmation reserve.** A spatial half (immediate regions within states) rather than a temporal one. A temporal reserve would sit on the COVID years, which distort everything.
- **O4, thresholds.** 1,000 events and 5% of units for field admission; δ = 0.1 for pair effects. Both are placeholders until the power curves exist.
- **O5, the record-grain scan.** Phase 3 here. It may deserve to come earlier, given pegasus_data's linkage.
