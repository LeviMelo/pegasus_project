# PegaSUS: design v0.2

**2026-10-04.** This proposal carries the design discussion of 3–4 October with the author. The author asked the agent to adjudicate, so **everything here is a proposal until the author accepts it**. The agent's least certain calls are in §16.

**Companion documents:**
- `docs/discussion/2026-10-03-what-was-built.md`: what the earlier engine actually ran;
- `docs/RECOLLECTION.md` and `docs/history/`: the earlier ideas and documents;
- `docs/handoffs/2026-10-04-pegasus_data.md`: what this design asks of pegasus_data.

---

## 1. What PegaSUS is

Brazil's health data are observations of one process: **events happening to people, in places, over time, each event carrying attributes**. Mathematically, that is a **marked point process**.

PegaSUS builds **one hierarchical model of that process for all of Brazil**, "normal Brazil", from all the data, through pegasus_data. It then reads three things from it, for people and for AI agents:
- **where the data depart from it;**
- **what its own structure reveals;**
- **how the departures relate.**

Each such reading is a **lead**: a structure with its size, its certainty, its checks and its replication record. **Leads are not conclusions.** They need not be epidemiologically interpretable when found. People, agents and studies follow them.

**The ambition:** use the entire haystack to learn what normal is, so that the needles (departures) are as sharp as the data allow, at any grain where they are coherent.

**Principles**, each traced to a documented failure of the earlier engine:

| principle | the failure it answers |
|---|---|
| **Expectation first.** Every cell is judged against what it should be given its population, place, time and case-mix. | pooled rank transforms baked gradients into "standardised" data; corr(z, log population) = 0.93 |
| **Model events and their attributes, not correlations of columns.** | one Gaussian covariance over all variables, places and years |
| **Every cell carries its precision.** | unit-variance transforms; weights computed and never used |
| **Declared estimands:** between places, within places over time, between groups, between institutions. | a fixed effect silently turned the scan into a within-place test |
| **Minimum-effect nulls and designed multiplicity arithmetic.** | CKA 0.04 certified at huge n; output size set by permutation floor × BY |
| **Structure priors on levels, never on relations.** | the ICD tree used as a prior on dependence penalised dengue ↔ microcephaly |
| **Strengths are learned, not set.** | κ = 1, λ₂ = 1.0, hand-set loss weights |
| **Observed stays observed.** Modelled quantities are typed, carry uncertainty, and are validated by holding data out. | an interpolation presented as a tensor; context reconstructed and never certified |
| **Nothing is trusted before passing the benchmark** of known positives, known negatives and planted signals, run on real data. | the validation programme written and never run |
| **Nothing is blind:** records, cohorts, places, institutions and recording practice. | — |

---

## 2. Two repositories, one rule

**pegasus_data is the data module of the whole project.** It will be open source, and **every input that reaches PegaSUS comes through it**.

The boundary is drawn by the question each piece answers:

| the piece answers | it lives in | examples |
|---|---|---|
| **What exists, and what does it mean?** | **pegasus_data, observed tier** | sources, decoding, labels, validity windows, roles, event-type declarations, code structures, geography and proximity graphs, aggregations, record identity, linkage |
| **What was there, and how was it recorded?** That is, estimates of the world's state and of the observation process, wanted by any analyst whether or not they use PegaSUS. | **pegasus_data, modelled tier**: typed as modelled, versioned, with uncertainty and validation evidence; never replacing an official series | the population account (§5.1); system completeness; race misclassification (§5.2); SUS-dependent population |
| **What is normal, what departs from it, and what relates?** | **PegaSUS** | the monolith, expectations, surprises, scans, leads, ledger, validation harness, agent tools, studies |

**The test for a doubtful case:** would an epidemiologist who never uses PegaSUS want this as data? If yes, pegasus_data. If it is a judgement about normality, surprise or relation, PegaSUS.

**What this settles:**
- **The population account and the race model sit in pegasus_data's modelled tier.** They are estimates of what the population was and how systems record it.
- **Linkage is already there,** on the same rule.
- **POPSVS stays served as published** beside our estimate, following pegasus_data's rule never to recompute an official series.

---

## 3. The ontology: from columns to the process

### 3.1 Entities and the test

| entity | examples |
|---|---|
| **person** | patient, deceased, mother, baby |
| **event** | death, birth, hospitalisation, notification, treatment-month |
| **institution** | establishment (CNES) |
| **place** | municipality and its hierarchies |
| **time** | the calendar |

Every column states a property of one of them. The test, for each column: **if the same person had a different event, would this value change?**
- **No:** a **person** attribute.
- **Yes, the event sets it:** an **event** attribute, a *mark*.
- **It describes what the event points to:** an **institution** or **place** attribute, reached through the reference.
- **It identifies:** an **identifier**, used only to link.

**Linkage measures the test.** Across the linked records of one person, person attributes agree up to recording error, and event attributes vary.

### 3.2 A role for every column (declared in pegasus_data)

pegasus_data's `roles.yml` already writes `<entity>.<property>` for the columns linkage uses. **It is extended to every column of every dataset PegaSUS reads**, each with three statements:

```
role:        entity.property            e.g. admission.length_of_stay, mother.education, baby.weight
value kind:  category | code tree | number | date | place | institution reference | identifier | text
model role:  stratum | dimension | event type | mark | when | where | institution | link-only | excluded
```

- **A stratum of a rate must be carried by the population account:** age, sex, race, residence. Mother's education or marital status cannot be rate strata, because no population of "married women aged 25" by municipality-year exists. **They are marks:** the composition of events is a field like any other.
- **One record can describe several entities.** SINASC has the mother, the baby, the pregnancy and the birth. An infant's SIM record has the child and the mother.
- **The first draft is generated** from pegasus_data's existing typing (codelists → category, numeric → number, identifier flags → link-only), then reviewed.

**What pegasus_data already provides**, each mapping onto this ontology:

| pegasus_data concept | what it provides |
|---|---|
| roles | entity.property |
| semantic axes | whose place: residence, occurrence, facility |
| grain ("what one row is") | the event kind |
| measures with accumulator states | mark summaries |
| VariableDoc | codes, trees, validity windows |
| personal-identifier flags and join keys | identifiers |

### 3.3 Event types

The record a system publishes is not always the event:
- **an SIH AIH is a billing document,** not a hospitalisation;
- **a SINAN row is a notification,** not a case.

So every event type is **declared** in pegasus_data:

```
EventType = ( dataset,
              grain          what one row is
              kind           death | foetal death | birth | hospitalisation | case | notification | treatment-month …
              classifier(s)  the code columns that partition it, with their role; one primary, others alternative
              status         which rows count
              consolidation  how rows become events )
```

| system | event | primary classifier | alternatives | status / consolidation |
|---|---|---|---|---|
| SIM | death; foetal death (`TIPOBITO`) | final underlying cause | original cause (`CAUSABAS_O`); certificate lines as marks | — |
| SIH | **hospitalisation episode** | principal diagnosis | **procedure performed:** the epidemiology of procedures and surgeries; childbirth is defined by procedure | AIH continuations consolidated (`IDENT`); transfers through linkage |
| SINASC | live birth | none (all marks) | anomalies (`CODANOMAL`) | — |
| SINAN | **case, or notification** (two types) | the disease (one dataset each) | final classification, outcome | confirmed by `CLASSI_FIN` |
| CIHA | as SIH, non-SUS | as SIH | as SIH | as SIH |
| CNES | **not an event:** institution state per month | — | — | — |

**Primary and alternative classifiers are different families of fields over the same events.** Their overlap is measured exactly, so they are never tested against each other as if independent.

**Each classifier has its own observation process.** "The diagnosis that justified the bill" and "the cause selected by rule" are different statements, and their disagreement is information about coding.

### 3.4 Structured variables

Each structured variable declares its **shape**, and the shape becomes the prior of the effects along it: a sparse Gaussian Markov prior in every case.

| shape | examples | prior on effects |
|---|---|---|
| **tree** | ICD-10, SIGTAP (group → subgroup → form → procedure), CBO, CNAE, ATC, ICD-O; geography hierarchies | nested effects: a leaf's effect = the sum along its path |
| **overlapping lists** | CID-BR mortality list, morbidity list, the GBD cause hierarchy, garbage codes, ICSAP, avoidable causes, notifiable diseases | an effect per list, carried by every member (multiple membership) |
| **ordinal** | age, gestational weeks, birth weight, education | random walk |
| **cyclic** | month, week, weekday | cyclic random walk |
| **graph** | proximity graphs (§4) | BYM2 / ICAR |

**How trees are used, given the earlier failure:**
- **Trees pool levels (rates), never relations.** Which codes move together is found, never assumed.
- **Pooling strength is learned per level and per subtree.** Heterogeneous branches (chapter XVIII) keep their codes apart; homogeneous ones pool.
- **Heavy-tailed shrinkage** (horseshoe-type) lets a single code escape its family.
- **Several trees at once:** ICD chapters, the GBD hierarchy, the CID-BR lists. Held-out prediction weights them per chapter, and **turns tree pooling off where it doesn't predict better.**

**Code systems change.**
- Validity windows come from pegasus_data.
- Crosswalks map codes into one stable tree where one exists (ICD-9 → ICD-10).
- Where none exists, the change is a **declared break**, not a lead.

**Code roles.**
- **Primary classifiers** define event types.
- **Secondary diagnoses and certificate lines** are multiple-membership marks.
- **"Any mention" fields** exist in their own right, with their overlap measured.

### 3.5 Fields: what the model and the scans see

**A field is a projection of events onto a lattice:** the counts of an event type, or the summaries of a mark, by place × time × groups (× institution).

```
Field: id, family (its node in a code structure), kind (count | mark summary | share | level),
       lattice, grain, groups (axes inside the field, never separate fields), support (observed cells),
       aggregation law, exposure (counts), signature (the predicate defining its events), provenance
```

- **Admitted by information, not enumeration.** A field enters the scans only if its expected events support a test (§16 O4). A code tree is descended only while children stay above that bar.
- **Overlap is measured exactly** from the signatures: shared events over the smaller field's events. Pairs above 0.05 are never tested against each other as if independent.
- **Comparisons happen at a common support:** the finest support to which both fields lift by their aggregation laws. Context observed in census years is compared in census years, never densified.
- **Context fields** (IBGE, SIDRA, climate) are observed fields at their own support.

---

## 4. Space: three roles, many proximities

**The earlier spatial kernel changed nothing:** residual Moran's I was 0.50 before and 0.50 after. It whitened the covariance between variables while the spatial structure sat in each variable's *mean*; its strength was fixed (κ = 1); and queen contiguity treats a 160,000 km² municipality and a 3 km² one alike.

**Here space has three distinct roles:**

| role | what it does | how it is set |
|---|---|---|
| **expectation** | places inform each other's levels and trends (BYM2) | **learned:** BYM2's mixing parameter estimates how much variation is spatially structured. Near 0, "space doesn't help here" is a reported finding. |
| **null** | neighbouring places are not independent evidence | effective sample size from each field's own spatial autocorrelation (Dutilleul); surrogates with matched variograms |
| **search geometry** | which sets of places count as a cluster | a declared graph |

**Proximity is a family of graphs**, built by pegasus_data. Each model component selects or mixes graphs by held-out fit:

| graph | captures | built from |
|---|---|---|
| contiguity, **weighted by shared border length** | shared borders | geometry |
| population-weighted distance | nearness of where people live | census tracts, geometry |
| travel time | reachability by road and river | road network, to acquire |
| **care flows** | where residents of A go for care | **SIH itself:** residence → hospital municipality, per year, per specialty; SINASC for births; SIM for deaths |
| urban hierarchy | influence of regional centres | IBGE REGIC |
| commuting | daily movement | census |
| health regions, comparable areas | administrative grouping | pegasus_data |

**Which graph explains a field best is itself a lead about it**, for example whether a disease follows commuting or referral.

**Unequal areas are handled two ways:**
- the graph weights (border length, population-weighted distance);
- the population-scaled precision of each place's effect, so a large empty municipality and a dense small one do not borrow equally.

---

## 5. The modelled tier (in pegasus_data)

### 5.1 The population account

**The decision (author, 2026-10-03): our own model**, with POPSVS as one input and as the benchmark to beat.

**The state.** The true resident population, `N(u, t, a, s, r)`: municipality, year, single age, sex, race. It moves by **demographic accounting**:

```
N(u, t+1, a+1, s, r) = N(u, t, a, s, r) · S(u, t, a, s) + M(u, t, a, s, r) + R(u, t, a, s, r)
N(u, t+1, 0,   s, r) = B(u, t, s, r) · S₀(u, t, s)
```

S is survival, M net migration, R race reclassification (summing to zero over r), B births.

**Many sources observe it, each through its own data model** (coverage, completeness, delay, selection). This is the Bayesian demographic account of Bryant & Zhang (2018).

| source | observes | known flaw |
|---|---|---|
| censuses 2000, 2010, 2022 | N by municipality × age × sex × race | coverage error by age and region |
| IBGE municipal totals (annual) | Σ N | the official constraint |
| IBGE state projections, life tables, fertility | S and B by state | priors |
| POPSVS (RIPSA, Duchesne cohort ratios) | N by age × sex | another model's estimate |
| SINASC, SIM | B; deaths | completeness by place and year |
| civil registry (SIDRA) | registered births and deaths | completeness |
| **school census (INEP)** | children by age, sex, **race** (declared by the family) | enrolment coverage |
| **CadÚnico (CECAD)** | about 40% of people, by age, sex, **race** | poorer population only |
| **RAIS** | formal workers by age, sex, **race** | formal jobs only |
| **ANS** | private-plan holders by age, sex | gives the **SUS-dependent population** |
| **TSE electoral roll** | voters 16+ by age band and sex; race self-declared since 2022 | race **79% missing in 2026**, selectively |
| census migration questions | origin–destination flows, 5-year | prior on M |
| WorldPop / GHSL | gridded population, built-up area | physical shocks |

**Outputs,** each a field:
- N with intervals;
- **net migration** by municipality × age × year;
- **race reclassification** by cohort;
- **completeness of SINASC and SIM** by municipality-year;
- **dated shocks**;
- **the SUS-dependent population** (residents − plan holders), the right denominator for SIH and SIA.

**Inference.** A state-space fit on the log scale, hierarchical by intermediate region and state, per state in parallel, with states coupled through migration totals.

**The test.** Predict the 2022 census by municipality × age × sex from data up to 2021, and compare with RIPSA's pre-census estimates. **If ours does not win, it is not used.**

### 5.2 Race measurement

**Code faults are removed first:** default fills and another system's codes, flagged per hospital-month (pegasus_data ADR-0128).

**A structured confusion matrix per setting** σ (system, who records, region, period, age band). On the ordered axis branca – parda – preta:

```
C_σ(k|j) = 1 − λ_σ − δ_σ  (k = j),   λ_σ  (k = j − 1, lightening),   δ_σ  (k = j + 1, darkening)
logit λ_σ = x_σ'β_λ ,  logit δ_σ = x_σ'β_δ        hierarchical priors; literature-centred
```

- **Amarela and indígena:** a retention probability each, with leakage.
- **Missing:** its own column, allowed to depend on true race.

**The likelihood is ecological, adjusted for age and sex:**

```
Y_{u,k}^{sys} ~ NegBin( Σ_j C_σ(k|j) · Σ_{a,s} N(u,t,a,s,j) · m^{sys}_{a,s,t} · θ_j · e^{b_u} , φ )
```

- **Identified by** how recorded shares track census composition across places, plus the race-declaring sources of §5.1.
- **Validated by:**
  - planted misclassification in real counts;
  - **linked pairs**, whose joint classification the model predicts: `P(k₁,k₂) = Σ_j π_j C_σ₁(k₁|j) C_σ₂(k₂|j)`.
- **Disparities are reported as intervals over the posterior of C.**

---

## 6. The monolith: normal Brazil

### 6.1 Intensity

For event type e, place u, time t, persons with attributes x (age, sex, race):

```
λ_e(u, t, x) = N(u, t, x) · exp( η_e(u, t, x) )

η_e(u,t,x) = α_e + f_e(x)                       the normal level of e for each group
           + g_e(u)                              its geography  (graph priors, §4)
           + h_e(t)                              its history: trend, season (ordinal / cyclic priors)
           + Σ low-rank interactions             place × time, e × place, e × age × time … (patterns, §8.3)
           + β_e · context(u, t)                 observed context, where observed
```

- **Effects over e follow the code structures** (§3.4).
- **Interactions are low-rank:** a few patterns combine place, time and cause, so that a model over ~10¹² cells is estimable.
- **Observation enters through the modelled tier:**
  - expected *recorded* counts = expected true counts × completeness;
  - race is mapped through C.
- **SUS systems use the SUS-dependent population;** SIM and SINASC use all residents.

### 6.2 Marks

Every mark (length of stay, cost, ICU days, birth weight, gestational weeks, Apgar, prenatal visits, mother's age, derived intervals) gets the same treatment:

```
mark | e, u, t, x, institution  ~  a distribution whose centre and spread depend on
                                    case-mix + place + time + institution, hierarchically
```

**The families:**
- **counts and durations:** negative binomial, Gamma or log-normal with a hurdle;
- **shares:** beta-binomial;
- **bounded scores:** ordinal.

### 6.3 The tiers of "boring" are nested versions of the monolith

| tier | terms switched on | what remains surprising |
|---|---|---|
| **B0** | group levels × national year | anything a place does differently from Brazil, given its population |
| **B1** | + spatial effects | departures from the region |
| **B2** | + each place's own level and trend | departures from its own history |
| seasonal | + seasons | out-of-season events |

A lead states the tier it departs from. **A north–south gradient is a lead at B0 and boring at B1; both readings are kept.**

### 6.4 Calibration

For every field and tier: the randomised PIT of every observed cell under its predictive distribution, tested for uniformity per field, tier and region. A miscalibrated field is flagged and kept out of pair scans at that tier.

---

## 7. Surprises

For every cell of every field and tier:
- `y`, the observed value;
- `μ`, the expected value;
- `z = Φ⁻¹(PIT)`, the surprise on a common scale. It is computed **after** the expectation: the earlier engine's Gaussianisation, in the right order;
- `w`, the cell's information (for counts, μ / (1 + μ/φ));
- flags: denominator tension, unreliable recording, calibration failure.

**The cube is virtual.**
- Expected values come from the monolith's parameters on demand.
- Observed values are the non-empty cells already in the lake.
- Surprises of empty cells have a closed form.
- **What is stored:** parameters, leads and caches of the scans.

---

## 8. Reading the monolith: the scans

### 8.1 Lenses on one field

| lens | statistic | null |
|---|---|---|
| spatial cluster | expectation-based Poisson/NB scan | predictive simulation + extreme-value tail of the maximum |
| outbreak / change point | Farrington-flexible / Noufaily-type; Bayesian change point | predictive |
| space-time cluster | space-time scan | as above |
| group disparity | heterogeneity of a stratum's SIR against the national pattern | NB likelihood ratio |
| trend divergence | a place's trend against its neighbours' | posterior |
| observation | the same lenses on recording-practice fields | as above |

### 8.2 Subset scanning: the needle finder

**A real signal is rarely one cell.** It is a coherent subset whose small surprises add up: these 7 neighbouring municipalities × these 5 months × women over 60 × these three codes.

- **What it searches:** the subset with the largest combined surprise across all dimensions at once. Places connected in a proximity graph; times contiguous; any subset of groups; codes within a subtree or list.
- **How:** the linear-time subset scanning property (Neill 2012; Neill, McFowland & Zheng 2013; McFowland, Speakman & Neill 2013) finds the best subset per dimension in linear time, alternating over dimensions.
- **Null:** predictive simulation with an extreme-value tail.
- **Recursive:** report the top subset, condition it out, look again.

**This finds signals that are invisible cell by cell.**

### 8.3 Patterns

The monolith's low-rank interactions (non-negative Poisson tensor factorisation against the expectations; CP-APR, Chi & Kolda 2012) are patterns: *these causes rose together, in these places, at these times.*
- COVID is one pattern.
- **A coding change is a mirror pair:** "ill-defined" falls where a specific cause rises.
- **A new disease is a pattern new in time.**

### 8.4 Pairs and dependency maps

On calibrated surprises, at each pair's common support:
- **between places (E_b):** correlation of place effects, with Dutilleul's effective n; and an adjusted version (E_b|Z);
- **within places over time (E_w):** correlation of B2 surprises at lags 0…L, with effective degrees of freedom per place;
- **between institutions (E_i)**;
- **across systems:** the same quantity recorded twice (notifications against admissions).

**Tests:** effects with **minimum-effect nulls**, H₀: |ρ| ≤ δ. Computed as weighted Gram matrices `ZᵀWZ`. Rank correlations first; HSIC on short-listed pairs.

**The dependency map** (phase 3): a sparse + low-rank graphical model on the surprises of one estimand, penalty chosen by stability across replication halves. This is the old LDO's goal, on correctly prepared inputs.

### 8.5 Cohort scans

On linked cohorts: every record attribute against every outcome, with a fixed adjustment set and FDR over the grid. This is the PheWAS shape, at the person level, free of the ecological fallacy.

### 8.6 Explaining away and decomposition (on demand)

- **Explaining away:** add a candidate driver (a context field, a capacity change) to the monolith for one lead, and report how much of its surprise it absorbs.
- **Decomposition:** split a change between two periods into population, place-mix and risk components, and say where the risk change sits.

---

## 9. Error control, replication, leads

**The ledger.** Every test, by the scan or by an agent, is written down before it runs. The scan's hypotheses are enumerated in advance.

**FDR.**
- Within a family: BH on analytic p-values.
- Across families: hierarchical selection (Benjamini–Bogomolov).
- Down code trees: TreeBH.

**Replication tiers:**

| tier | meaning |
|---|---|
| R0 | passes FDR on all the data |
| R1 | same sign and at least half the effect in the other temporal half |
| R2 | the same in a disjoint spatial half (immediate regions split within states) |
| R3 | found again through another system |

**Agents** explore one spatial half, and confirm once on the reserve through a logged tool call.

**The lead:**

```
Lead
  kind (residual | subset | pattern | relation | cohort | observation | structural)
  estimand, tier, fields, support, locus (places, times, groups, codes, institutions)
  effect (estimate, interval), test (statistic, p, q, family, null, calibration)
  replication (R0..R3), robustness (C-robust, denominator tension, recording flags, measured overlap)
  provenance (data versions, model version, ledger id)
  rank = evidence × effect × replication
```

---

## 10. How PegaSUS is used: a survey

**The model is a sky survey's.** The Vera Rubin Observatory subtracts a template (the normal sky) from each night's image and issues alerts. Brokers filter them, scientists query the catalogue, teams follow up.

| survey | PegaSUS |
|---|---|
| the template | the monolith |
| tonight's image | the latest data |
| the difference image | the surprises |
| alerts | leads |
| brokers | agents |
| the catalogue | the atlas and the model |
| follow-up | studies |

**Seven ways of use:**
1. **The alert stream.** Each data update brings new leads, ranked.
2. **Any slice, observed against expected, at question time,** including slices nobody precomputed.
3. **Explaining away.** Does candidate X absorb this lead?
4. **Decomposition.** Why did Y change, and where?
5. **Relations, on demand.** What moves with X, between places or over time?
6. **The data's own health.** Completeness, coding changes and default fills by system, place and hospital.
7. **Hand-off.** A lead becomes a study, with its cohort, fields and checks ready.

**Agents (LLMs in a single loop, with tools and an objective) can drive all seven.**

| tool | does |
|---|---|
| `search_fields`, `describe_field` | the registry |
| `expected(slice)`, `surprise(field, tier, scope)` | the atlas |
| `leads(filters)`, `lead(id)` | the lead register |
| `scan`, `compare`, `subset_scan` | logged tests |
| `explain_away(lead, candidate)`, `decompose(field, periods, scope)` | on demand |
| `cohort`, `records` | through pegasus_data |
| `confirm(claim)` | once, on the reserve, logged |

---

## 11. Computation

**The machine:** 32 GB RAM, 20 logical cores, RTX 4050 (6 GB), about 177 GB free disk.

**Four tricks:**
1. **The model touches only cells where something happened.**

   `log L = Σ_{non-empty} y log λ − Σ_{all} λ`

   The second sum over ~10¹² cells factorises through the model's structure into a contraction of the population tensor (millions of cells) with small factor matrices. Each evaluation costs about `nnz + |P| × rank`.
2. **The model is the compression.** The surprise cube is virtual (§7).
3. **Blocks, warm starts, incremental updates, content-addressed caches.**
   - A two-level fit: a top model of chapter-level effects, then chapters in parallel.
   - Monthly data → warm-started refits of the affected blocks.
4. **Hardware does what it is built for.**
   - Gram matrices and contractions on the GPU (JAX, float32 with float64 accumulation, chunked to 6 GB).
   - Sparse Cholesky (CHOLMOD) for the graph priors.
   - Laplace or variational uncertainty, checked against exact fits on samples across many states.
   - DuckDB aggregation over the lake.

**Scaling:** cost ∝ (non-empty cells + population cells × rank) × iterations, × blocks in parallel.
- **Health regions instead of municipalities:** ÷12 in population cells, and more power per cell.
- **Monthly grain:** ×12. **Race:** ×5. **Full code depth:** more non-empty cells.

**The starting setup:** SIM, SINASC, SIH and SINAN; municipality × year, 2010–2023; 18 ages × 2 sexes; codes to three characters.

| task | estimate |
|---|---|
| population tensor | 2.8 M cells (11 MB) |
| aggregation from the lake | minutes per system |
| monolith, all four systems | under an hour |
| subset scan per field | seconds to a minute |
| pair scans, one estimand, ~2,000 fields | minutes on the GPU |
| memory | a few GB per block |

**All figures are estimates,** measured first in phase 1 on one family.

**Storage:** pegasus_data's operational changes (handoff §1) bring the starting setup from roughly 35–45 GB to 12–18 GB.

---

## 12. Data scope

**Phase 1–2 systems:** SIM, SINASC, SIH (diagnoses and procedures), SINAN, CIHA when useful. Context: IBGE and SIDRA, as observed.

**Excluded:**
- **SIA PA and BI** (406 GB of production accounting).
- **CNES** at first (institution lattice in phase 3).

**Later, as care-pathway sources:** SIA's APAC families, small and person-level: oncology (AQ, AR), dialysis (ATD), specialised medicines (AM), psychosocial care (PS).

---

## 13. Validation harness, built first

**Known positives,** each with its lens, tier and locus:
- microcephaly 2015–16, Northeast;
- arbovirus → microcephaly at 6–9 months;
- COVID excess deaths, including Manaus in January 2021;
- dengue epidemics and seasonality;
- leptospirosis after the 2024 Rio Grande do Sul floods;
- the endemic geography of Chagas disease and schistosomiasis;
- infant mortality ↔ income and sanitation (between places);
- diarrhoea ↔ sewerage (between places);
- winter respiratory admissions.

**Known negatives:**
- random partitions of one system's records;
- a field against itself shifted by years;
- unrelated events on the same denominator.

**Planted signals:** known effects injected into real counts give each lens's power curve, and set δ.

**Null surrogates:** the whole pipeline run on data simulated from the expectations, which gives the false-lead rate.

**Gate:** a lens enters production only after it recovers its positives, holds its false-lead rate on surrogates, and publishes its power curve.

---

## 14. Build order

| phase | PegaSUS | needs from pegasus_data | gate |
|---|---|---|---|
| 0 | the harness | — | reproduces itself |
| 1 | the monolith for SIM, SINASC, SIH (annual); surprises; lenses; subset scanning | roles and event types for those systems; code structures; contiguity and distance graphs; aggregation API; POPSVS (until the population account exists) | the univariate positives; false-lead rate; measured compute |
| 2 | pair scans; the ledger; FDR; replication; explaining away; decomposition; SINAN | care-flow graph; the population account v1 with its 2022 test | the pair positives; negatives; power curves |
| 3 | patterns; dependency maps; agent tools; institution lattice; cohort scans; monthly grain | race measurement; new population sources; CNES fields; APAC families | each with its own positives |

**First measurements, once set up:**
- does ICD tree pooling improve held-out prediction, chapter by chapter (SIM 2021–2023)?
- which proximity graph best explains between-municipality variation for a few causes?

---

## 15. The fate of the earlier concepts

Most of the earlier ideas survive. What dies is mostly the machinery that implemented them.

| earlier concept | now |
|---|---|
| Problem 1: typed measures, aggregation laws, measured quantity (count + exposure) | field kinds; pegasus_data's accumulator states; **the measured quantity is the monolith's only input** |
| Radon–Nikodym rate | λ = N · exp(η): a parameter, not a division |
| legality | role rules (a stratum only if the population carries it); race only through C |
| EFG as a variable generator; composites; utility score; semantic entropy | replaced by the registry and admission by information; the monolith's interactions cover combinations |
| canonical core | every standard indicator is a slice of the monolith |
| node life cycle, institutional signature, "anomaly sub-graph as an audit of DATASUS" | **promoted:** observation leads, measurement models, calibration flags |
| state tensor Q(v) | each cell's information weight; calibration per field |
| Problem 3: data sovereignty | observed stays observed |
| one common support; ST-DFM; regimes | dropped: comparisons at their own support; context as observed |
| the CTR kernel (constrained latent reconstruction) | lives where it belongs: the population account |
| population tensor | the Bayesian demographic account, multi-source, tested against 2022 |
| race bridge | structured C, validated by linkage |
| disease semantic axis, L_D | structure priors for every structured variable, **on levels only** |
| HSIC scanner, copula/PIT | PIT after expectation; HSIC on a short list |
| LDO (sparse + low-rank, lags, multiresolution shrinkage) | low-rank patterns in the monolith; graph and tree priors; lagged pair scans; the dependency map on surprises |
| block permutations, FDR families, stability | analytic nulls with calibration; hierarchical FDR; replication tiers |
| causal ladder | explaining away, decomposition, agents, studies |
| bounded exhaustiveness, coverage manifest | admission by information; the ledger; subset scanning (no Simpson cancellation) |
| information ceiling | admission thresholds and power curves |
| living skeleton; the five verbs | the survey; interrogate = slices, lens = scans, escalate = explain and study, steer = the agent's objective, inject = sources and candidates |
| finding ontology | the lens catalogue |
| north star | the principles |
| validation battery; Zika acceptance test | the harness, phase 0 |
| compute levers (Kronecker, randomised SVD, GPU everywhere) | replaced by never building dense objects |
| the prime directive | kept verbatim |

---

## 16. The agent's least certain calls

| | call | the alternative |
|---|---|---|
| O1 | annual grain first; monthly for dense families in phase 3 | monthly earlier |
| O2 | the dependency map waits for phase 3 | earlier, since it is the old engine's core wish |
| O3 | spatial confirmation reserve | temporal (but COVID years distort it) |
| O4 | admission ≥ 1,000 events and ≥ 5% of units; δ = 0.1 | placeholders until the power curves exist |
| O5 | cohort scans in phase 3 | earlier, given pegasus_data's linkage |
| O6 | the population account and race model live in pegasus_data's modelled tier | in PegaSUS (§2 gives the rule) |
