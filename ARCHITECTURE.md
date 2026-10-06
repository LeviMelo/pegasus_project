# ARCHITECTURE.md: PegaSUS

**The authority on what PegaSUS is, its mathematics and its code.** Accepted by the author on 2026-10-04 (ADR-0002). **Revision 2, 2026-10-06 (ADR-0023),** on the author's instruction after the review `docs/discussion/2026-10-06-architecture-review.md`. It replaces how the model is solved (§5), how departures and relations are read (§7), how methods are validated (§8.4, §10), and the roadmap (§12). The model itself (§4) and the boundary with pegasus_data (§2) stand. The design drafts are in `docs/discussion/2026-10-04-design-v0.2.md`. When code and this document disagree, one of them is wrong: fix it, or record the departure in §13.

**Maturity.** Each component is at one of three levels, stated where it is described and summarised in §13:
- **v0**, a first version that runs;
- **v1**, the field's established method for the estimand, implemented;
- **v2**, v1 measured against its alternatives on this data.

A v0 is never the end state.

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
| 8 | error control, replication, weighting by power, recording as measurement |
| 9 | leads, the ledger, use |
| 10 | validation: characterisation, not permission |
| 11 | code: package, artefacts, invariants |
| 12 | roadmap: the overhaul's work packages |
| 13 | maturity by component; departures |

---

## 1. Purpose and principles

Brazil's health data are observations of one **marked point process**: events (deaths, births, hospitalisations, notified cases) happening to persons, at places, at times, each carrying attributes (marks).

PegaSUS:
- **fits one hierarchical model of that process,** the **monolith**, "normal Brazil", from all the data it reads through pegasus_data;
- **reads leads from it:** where the data depart from it (§7.1–7.3), what its own structure shows (§7.4), how departures relate (§7.5–7.6);
- **serves those readings** to people and to AI agents (§9).

Later (phase 4, ADR-0004), the same model and lenses run **prospectively**, as surveillance across every diagnosis code and system.

**Who it happens to.** Departures and relations are read by age, sex **and race**. Brazil's health inequalities are among the first things a reading of its data must show. Race is an axis of the lattice from 2000 (§3.4), read through how each system records it (§4.1). Every estimand has its race-specific and its disparity form (§4.2, §7.0).

Leads are statistical objects, not conclusions.

**Principles.** P1–P10 answer documented failures of the 2026 engine (`docs/discussion/2026-10-03-what-was-built.md`). P9 is rewritten, and P11–P14 added, after the 2026-10-06 review of this engine's own first versions.

| # | principle |
|---|---|
| P1 | **Expectation first.** Every quantity is judged against a model of what it should be given population, place, time and case-mix. No statistic runs on a raw or pooled-rank-transformed value. |
| P2 | **Events and their marks are modelled, not correlations of columns.** |
| P3 | **Every cell carries its information** (§6.3), and every statistic uses it. |
| P4 | **Estimands are declared.** Between places, within places over time, between groups, between institutions: separate statistics, separate nulls. |
| P5 | **Effects are tested against a minimum relevant effect,** and the multiplicity of the whole search is designed before it runs. |
| P6 | **Structure priors act on levels, never on relations.** Taxonomies never decide which quantities may co-vary. |
| P7 | **Every strength is learned or measured.** Strengths are learned by the marginal likelihood (§5.4) or held-out data, never by a heuristic fixed point. No unmeasured constant is a gate. |
| P8 | **Observed stays observed.** Modelled inputs come from pegasus_data's modelled tier, typed, with uncertainty. |
| P9 | **Validation characterises; it does not license.** Every method carries its measured operating characteristics: calibration, power over a designed grid of planted signals, and false discoveries on null worlds (§10). No question is excluded for being hard: it is weighted by its power and reported with its minimum detectable effect (§8.4). Documented events are a held-out check, never a tuning target. |
| P10 | **No dense object larger than the population tensor** is ever built (§5). |
| P11 | **Established method first.** Before a statistic is designed, the field's standard for that estimand is named. It is then used, or beaten by measurement. A check, gate or threshold is not an answer to a modelling problem. |
| P12 | **Departures and relations are model terms.** A lead is a posterior statement about a term of the model (its size, its certainty, its minimum relevant effect), not the tail of a residual statistic under a method-specific null. Scans search; models infer (§7). |
| P13 | **Structure is exploited, and speed is budgeted.** Computation follows the model's sparsity: an arrowhead Hessian, GMRF precisions, factorised totals (§5.3). Every component has a time budget, and a benchmark is run on every change to the solver (§5.8). |
| P14 | **Recording is measured, never used to dissolve.** Recording processes are model terms where the data identify them, and graded explanations where they do not. A lead is re-scoped to its conserved level, never removed by an untested explanation. A changed rule is re-applied to the stored state (§8.6). |
| P15 | **Race is an axis, not an option.** Where the population carries race, the lattice does. Recorded race is read through its measured misclassification and missingness, never taken as the declared race, and never dropped because it is hard. |

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
| **population** | person-years N by place × year × age × sex (× race), with uncertainty; the SUS-dependent variant; completeness by system, place and year. Sources behind `gateway.population(source=)`: `popsvs` (IBGE's projection as the MoH distributes it, modelled, single years of age, no uncertainty), `account-2` (pegasus_data's `population-account-2`, municipality × sex × five-year band × year 2010–2023, 80 % intervals read as σ of log N) and `account-3` / `account-4` (the complete tensor, 5,570 municipalities, single ages, race, 2000–2023 / 2000–2030, summed onto POPSVS's 18 bands, σ an upper bound; ADR-0010 amended). The source fixes the age bands (18 for POPSVS and account-3/4, 17 for account-2, whose 0–4 holds ages 0 and 1–4); the cache keys carry the source and the model version. `hybrid` (POPSVS + the account-6 age 0) is the default for a newborn-exposure field, one with at least half its events at age 0 (`monolith.default_population`; SIM chapter XVI), `popsvs` for the rest; `PEGASUS_POPULATION` overrides |
| **aggregates** | sparse non-empty cells of counts per event type and lattice; mark accumulator states (n, Σm, Σm², Σlog m, Σ(log m)², histogram on declared bins) |
| **records and linked persons** | for cohort scans and agents |

### 3.2 Defined here

**Lattice cell.** `c = (u, t, g)`:
- u, a place (municipality, comparable area or health region);
- t, a time (year, or month for dense families);
- g, a group: age × sex × race (§3.4). Ages are single years 0–19, five-year bands 20–79, and 80+ (33 classes; the tensor carries single ages, and pediatric epidemiology needs them). Race from 2000, the year the population tensor's race begins; race `total` before.

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

### 3.3 The ICD ontology (revision 2; O4)

**The model is built on the ICD.** Its tree carries the levels, its profiles and its pooling. The ICD is therefore an ontology PegaSUS consumes, not a code column.

**It is a pegasus_data product** (§2, rule 2): versioned, typed, read through `gateway`.

**What exists (2026-10-06):**
- **The tree.** pegasus_data ships the ICD-10 tree (chapter → group → category → subcategory; 14,563 nodes, with validity windows).
- **Seven concept lists:** CID-BR-10, the tabulation lists 2 and 4, avoidable causes for ages 0–4 and 5–74, ICSAP conditions and groups.
- **What PegaSUS uses:** the tree down to the 3-character category, and nothing else.
- **Harvested, not built:** DATASUS's own CID-10 release (`sources/cid10csv_v2008.zip`: chapters, groups, categories, 12,451 subcategories, and ICD-O). It carries per code:
  - `CLASSIF`: dagger or asterisk;
  - `RESTRSEXO`: the sex restriction;
  - `CAUSAOBITO`: acceptable as an underlying cause of death;
  - `REFER` and `EXCLUIDOS`: cross-references and exclusions.

**The ontology, by component:**

| component | content | source | what PegaSUS does with it |
|---|---|---|---|
| **hierarchy** | WHO ICD-10 with the Brazilian additions (U codes), validity per year | `code_trees` (shipped) | tree effects (§4.2); leaves at the 3-character **category**. The 4th character is not a modelled level: certifiers and services rarely use it informatively, and a subcategory lattice multiplies the leaves for little epidemiology (author, 2026-10-06). It is read only where it encodes an axis: the place of occurrence of W00–Y34 |
| **code attributes** | dagger/asterisk, sex restriction, acceptability as underlying cause, references, exclusions | the DATASUS CID-10 release (2008 harvested; the current release to fetch) | **structural zeros**: a sex-restricted code has no exposure in the other sex; an asterisk code is never an underlying cause; unacceptable underlying causes become recording-quality fields (§8.6) |
| **age plausibility** | age limits per code (perinatal, obstetric, congenital, senility) | the critique tables of SIM and SIH; SIGTAP's CID table | structural zeros by age; impossible records flagged, never dropped |
| **ICD-9 and its bridge** | the ICD-9 tree (SIM 1979–1995) and an ICD-9 → ICD-10 map with comparability ratios | to locate (pegasus_data open question 69) | the SIM series from 1979 in one tree, with the bridge's uncertainty |
| **ICD-O** | morphology of neoplasms | in the DATASUS release | oncology fields (SIH, APAC) |
| **analytical lists** | the seven shipped; to add: WHO mortality list 1, the SIH morbidity list (`LISTA10`, pegasus_data open question 69), garbage codes by level (GBD, licence checked), the work-related disease list (LDRT, Portaria 2.309/2020), notifiable diseases ↔ ICD | list tables | list effects θ_L (§4.2, not built); fields that cross the tree |
| **external-cause axes** | intent × mechanism (WHO / CDC external-cause matrix); place of occurrence by the 4th character of W00–Y34 | derived from the tree and the matrix | intent and mechanism fields across chapter XX (homicide, suicide, accident, undetermined, whatever the code) |
| **relations** (a typed graph) | *sequela of* (I69 → I60–I67, B90–B94, T90–T98, Y85–Y89); dagger → asterisk; exclusions; **exchange pools**, the codes coders trade (unspecified ↔ specified, R00–R99, Y10–Y34, C76–C80, garbage → targets); procedure ↔ diagnosis (SIGTAP compatibility); notifiable disease ↔ ICD (SINAN) | documented relations from the release and the WHO rules; exchange pools from the literature and from this data's measured exchanges | the conserved levels of §8.6 (no longer a list inside triage code); corroboration rules (§8.3, no longer `corroborate.RULES`); the coding-regime term and redistribution sensitivity |

### 3.4 Race (revision 2; O3)

**Race is an axis of the lattice** wherever the population carries it. It is read through how each system records it.

**Declared race: the population tensor.** pegasus_data's `population-account-3/4` (pegasus_data decision 0151) gives total plus five races, 2000–2030, municipality × single age × sex, with intervals.

*Its census inputs:*
- **2010 and 2022:** the full count by single age (SIDRA 9606).
- **2000:** the sample by IBGE's bands (SIDRA 2093: five-year bands to 29, ten-year bands 30–79, then 80+).
- **Between censuses:** cohort composition, the log race shares linear along each birth cohort, with a state reclassification rate per year. Calibrated out of sample on 2010.
- **Each census year has exactly one source:** 2010's sample in table 2093 is never mixed with its full count.

*Known limits, to fix in pegasus_data (O3).* The tensor is the denominator of every rate, so its race split must be as defensible as its totals.
1. **2000's "sem declaração": allocate, never drop, never a denominator of its own.**
   - **Today:** 1.207 M people (0.71 % of the sample) are dropped, so the undeclared are split like the declared. The 2010 and 2022 full counts leave 6,608 and 11,119 people outside the five races.
   - **The fix: impute each undeclared person's race** from the census microdata of the same year (IBGE's public 2000 sample), with a model of race given age, sex, municipality, education, urban residence and **the declared races of the other members of the household**, which predicts it best.
     - The fit is on the declared people and is applied to the undeclared.
     - Several imputations carry its uncertainty into the race intervals.
   - **The official totals are untouched:** only the split among races changes.
   - **Where only tables exist** (the 2010 and 2022 residuals), the undeclared are split by their municipality × sex × age cell's declared shares.
   - **Sensitivity:** a bound for race-dependent non-response (all undeclared of the most affected cells to each race in turn) is reported in the manifest.
2. **2000's bands spread flat over their ages**, including the ten-year bands 30–79. The prior is the same cohorts' single-age shape in the 2010 full count (the 2000 band 30–39 is the 2010 cohort 40–49), constrained to the band's total. Its error is measured on 2010 by aggregating 9606 to the 2093 bands.
3. **2000 is a sample and 2010–2022 are full counts.** In 2010 the sample's white count is 90.62 M against the full count's 91.05 M. 2010 publishes both, so the correction is measured there by race × band × state and applied to 2000, its spread entering the interval.
4. **1991–1999 carry the total only.** The 1991 census's race is read and carried through the backcast; SIM records race from 1996.

**Ages.**
- **The tensor's single ages 0–79 are the vital cohort-component account's own path** (SINASC births, adjusted for registration completeness, and SIM deaths by single age, settled on the censuses; pegasus_data decision 0151). The within-band share error is measured at the census closings (a² 0.0015 over all ages).
- **PegaSUS kept only POPSVS's bands (0, 1–4, 5–9 …) and discarded them.** Revision 2 reads single years 0–19 (§3.2).
- **The tensor is validated at those ages** (O3), by single age 0–19 against the 2010 and 2022 censuses, and the 2007 Contagem where it counts.
- **Children's migration** is tied to the account's schedule for adults aged 20–39, the ages of their mothers.

**Recorded race in the events:**
- SIM `RACACOR` (from 1996);
- SINASC `RACACORMAE` (the mother's declaration) and the newborn's `RACACOR` (equal to the mother's in 50,078 of 50,078 linked records);
- SIH `RACA_COR`, flagged per hospital and month, never relabelled (pegasus_data decision 0128);
- SINAN `CS_RACA`;
- SIA/APAC.

**How the recording is measured:**
- confusion matrices of recorded against declared race: infant deaths, anchored on the mother's declaration at birth (pegasus_data decision 0143); women aged 15–49, measured through their births (pegasus_data decision 0149);
- the share recorded as unknown, by system, place and year (and by facility for SIH).
- Other adults' confusion is not measured; §4.1 gives how they are read.

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
| **κ_{s,u,t}** | completeness of system s (1 where unmodelled) | pegasus_data `system_completeness` (SIM, SINASC by UF × year 2000–2023, 80 % intervals); an exposure modifier of the source string, `popsvs+kappa`: N ← κ_{UF(u),t} N, σ in quadrature (`gateway.population`, ADR-0020) |
| **race** (revision 2, §3.4; O3) | **groups g = age × sex × race** (2000 on). The *recorded* count by recorded race k ∈ {five races, unknown} is `μ^{rec}_{e,(u,t,a,s,k)} = (1 − m_{s,u,t}) Σ_j C_{s,σ}(k\|j) μ_{e,(u,t,a,s,j)}` for a race, and `m_{s,u,t} Σ_j μ_{e,(u,t,a,s,j)}` for unknown. `C_{s,σ}` is the measured confusion of system s in setting σ: infant deaths, women 15–49. Where no confusion is measured (other adults, SIH, SINAN), C is the identity, with a sensitivity band from the nearest measured matrix, and the estimand is named *recorded-race*. `m` is the unknown share (a smooth field over place and year, by facility for SIH), assumed not to depend on race; the sensitivity of that assumption is reported | pegasus_data modelled tier (`race_confusion_infant`, `race_confusion_women`). v0 built: race-stratified blocks (`race=` in the source arguments, ADR-0020), births by the mother's declared race, infant deaths with the exposure `Σ_j C(k\|j) r_j N_j` (`+confusion`); none measured, and the women's matrix is not wired |

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
- **The low-rank interaction (`Monolith(rank=R)`, annual grain, ADR-0021).** Σ_r ψ[r,e] ω[r,u] τ[r,t] acts on the *active* leaves, those holding at least 0.1 % of the block's events (the others have ψ = 0), so the cube is |E_active|·U·T. ψ ~ N(0, 1) is fixed and centred within each group's active leaves, which makes the term orthogonal to the effects the leaves of a group share; ω = scaled ICAR + iid, both centred over the places, with learned strengths (the amplitude lives there); τ = RW1 scaled like the other shapes plus a unit prior on its level, strength fixed. The strengths of ψ and τ are fixed so the three factors' scales are not a ridge. A fit runs the base model, then starts the interaction from a weighted alternating least squares of the base fit's working-residual cube (a zero start is a saddle), then iterates the same Newton–CG and Fellner–Schall (the Gauss–Newton diagonals of the three factors replace the first-derivative mass). Forecast: ω and ψ as fitted, τ flat at its last value (the RW1 mean). Laplace draws are not built for it. The interaction is *within the block*: it carries a place–time pattern shared by some leaves with different loadings; a place level shared by whole chapters is the block's main place effect and cannot be separated here (evaluation 2026-10-05, low-rank).
- **Race terms (revision 2, O3).** η gains, for declared race j:
  - a race effect per tree node, shrunk along the tree like θ;
  - a race × age deviation of the profile (RW2 per race, shrunk to the common profile);
  - a race × place contrast at a coarse scale (BYM2 over states or immediate regions: municipal race-specific counts are too sparse);
  - a race × time contrast (RW1).

  A **disparity** is the exponentiated race contrast, a rate ratio with its posterior, by place, period, age and node. The cells grow fivefold. The race contrasts join the place and global classes of §5.3, so the solver's structure is unchanged.
- **The ICD ontology in the predictor (revision 2, O4; §3.3).**
  - List effects θ_L are carried by every member code (CID-BR-10, avoidable causes, ICSAP, garbage levels).
  - Sex- and age-impossible cells are structural zeros of the exposure, not low rates.
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
- **Identifiability.** Every intrinsic GMRF (ICAR, RW) is constrained to sum to zero over each connected component of its index. Proper iid place effects (v_all, v_grp, v_cat) are not: their own prior identifies them, which is INLA's convention, and it removes 87 of IX's 117 constraints across places (2026-10-06). Tree levels are centred within siblings. The interaction loadings are orthogonalised against the main effects.
- **The age–sex profile is centred over both sexes together** (f_all over its 2 × bands; f_grp per group over both sexes, then across groups). The sex difference lies in the RW2's null space and is informed by the data. Until 2026-10-06 each sex was centred separately, so no component carried the sex level. IX's youngest bands were fitted at 0.57–0.77× observed in one sex and 1.4–3.0× in the other; held-out deviance per death went from 2.21828 to 2.21699 with the correction (evaluation 2026-10-06, solver v1).
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
- **The search for φ bins the cells once** (`_nb_loglik_binned`): the non-empty cells exactly, the sum over every cell from one pass that bins μ by its log (8,192 bins, count, Σμ, Σμ² with a second-order correction). It agrees with the exact streamed likelihood to 10⁻⁶ log-likelihood units and gives the same φ. On IX it takes about 4 s against 14 (2026-10-06).
- **The block's own φ stays one value per block.** `nb_loglik` scores any φ (a scalar or one per place) over every cell, and `dispersion_by` fits one per group of places. Per macro-region, held out, it gained 0.009 nats per event on dengue (fit to 2018), 0.0002 on chapter IX and −0.0007 on chapter X (ADR-0006), so it is not adopted.

### 5.3 The mean: structured Newton (v1 for every model since 2026-10-06: counts, the low-rank interaction, marks and shares; v0 retired the same day; evaluation 2026-10-06, solver v1)

**The v0 solver** is truncated Newton–CG on autodiff Hessian–vector products (double backward through the factorised total), with a diagonal preconditioner, Eisenstat–Walker forcing and an Armijo line search; L-BFGS before it diverged (evaluation 2026-10-04). Warm starts, `mean_tol` and Anderson acceleration of the outer loop are ADR-0017.
- **Measured** on chapter IX 2010–2021 (552,046 parameters; 2026-10-06): the first ten Newton steps take 1–3 CG iterations each; from the fourteenth, every step hits the 50-iteration cap and gains less than 10⁻³.
- One Hessian–vector product costs 0.15–0.5 s, against 0.017 s for one evaluation of the total.
- The conditioning is the coupling between effects that explain the same cells. A diagonal or per-effect block-Jacobi preconditioner cannot see it (block-Jacobi measured no better, evaluation 2026-10-05).

**The v1 solver: exact Newton on the assembled Hessian.** The parameters of a block fall into three classes:

| class | members | size (chapter IX annual) |
|---|---|---|
| **leaf-place** v | v_cat[e, u] | E·U = 428,890 |
| **place** ℓ_u | s_all[u], v_all[u], s_grp[·, u], v_grp[·, u], the interaction's ω[·, u] | (2 + 2K + 2R) per place; 122,540 at R = 0 |
| **global** γ | b0, θ_grp, θ_cat, f_all, f_grp, h_all, h_grp, season, the interaction's ψ and τ | 616 |

With W the working weights (μ for the Poisson quasi-likelihood of counts; the mark and share models' own), the data part of the Hessian is JᵀWJ, every entry a sum of W over the cells two parameters share.

**The structure:**
- a leaf-place parameter shares cells only with its own place's ℓ_u and with the globals of its leaf and group, so H_vv is **diagonal**;
- two places share no cell, so the data part of H_ℓℓ is **block-diagonal by place**, and places couple only through the graph precision τQ of the ICAR terms;
- the globals couple to everything, and there are few of them.

H is **block-arrowhead**. Every block is a contraction of the factorised μ = LP[e,u] · PT[k,u,t,g] (§5.1): the same factors, summed over different index pairs. No cell array is formed (P10).

**The solve, in order:**
1. **Eliminate v in closed form.** The diagonal Schur complement onto (ℓ, γ) is a sum of outer products over (e, u), accumulated by contraction.
2. **Factor the place system:** per-place dense blocks of size 2 + 2K + 2R, coupled by the graph's sparsity. Sparse Cholesky with a fill-reducing ordering (CHOLMOD through scikit-sparse; SuperLU where CHOLMOD is absent).
3. **Schur complement onto γ:** dense, a few hundred to a few thousand, factored densely.
4. **Back-substitute.** The Newton step is exact, and the iteration converges quadratically under the line search.

**The start** (`Monolith._initialise`, 0.3 s on IX; evaluation 2026-10-06, solver v1):
- **The mean.** The Poisson maximum likelihood of leaf + group × year + group × age–sex, by iterative proportional fitting (the ML of a log-linear model), written into the centred parametrisation. Then one backfitting pass gives each (leaf, place) its penalised Poisson deviation, split into the place, group-place and leaf-place parts.
- **The level, profile and course strengths** start at Fellner–Schall's value for a well-identified effect, rank / x̂ᵀQx̂.
- **The place strengths** start at Marshall's (1991) moment estimate of the between-unit variance at each level, shared equally by the ICAR and iid parts. A level whose variance cannot be told from its Poisson part starts shrunk (τ = 10³).
- **Measured on IX:** the first start (each margin against the flat rate, then centred) began at an objective of 4.3·10⁸ against the optimum's 2.6·10⁶. From the main effects alone, the first Newton step moved a leaf-place deviation by 66 and later steps undid it. At τ = 1 everywhere, the first outer pulled the leaf levels to their group's and moved s_grp by 14.

**Constraints.** Constraints local to a place (groups' deviations summing to zero, leaves centred within groups) and to the globals (h_grp over groups) are imposed by contrast bases inside the blocks. The few constraints across places (ICAR sum-to-zero per connected component) are imposed by conditioning by kriging on the factor (Rue & Held 2005, §2.3.3).

**When γ is large** (the monthly grain: h_grp over 168 months), the factor of the place system with an approximate Schur complement becomes the preconditioner of a CG on the exact assembled product. A handful of iterations is expected, against the v0's 50-iteration cap. This is measured, not assumed (§5.8).

**The interaction and the marks on v1** (2026-10-06; evaluation 2026-10-06, solver v1).
- **Leaf-specific features.** The assembly and the solve carry them exactly. With the low-rank interaction on, an active leaf's place-time factor is its group's times exp(I), so its coupling to the shared effects is its group's features plus a deviation δφ. The leaf-place elimination then gains, per (group, place), the cross term φ·G1ᵀ + G1·φᵀ and the active–active term Σ (LP²/d)·δφ·δφᵀ − H1·H1ᵀ/s. On IX rank 3 with the interaction held fixed: gradient equal to autodiff to 10⁻¹⁴, solves to 10⁻⁶.
- **The interaction's own factors** (ψ, τ, ω = os + ov) by alternating exact Newton steps (`solver.ix_sweep`; the fit of Goodman's row–column association models). Given the other two, η is linear in each factor, so each step is a Poisson Newton step with that factor's prior. ψ and τ are small dense systems; ω is a sparse 2R·U system (CHOLMOD, with the centrings by kriging). The ω strengths take a Newton step on log τ from that system's own traces (`ix_strengths`).
- **The mark and share models** (log-normal, beta-binomial share, count) exist only on non-empty cells, each with its family's Fisher weight. They are the same structure with a zero shared factor and every leaf active (`StructuredNewton._mark_factors`). Gradients equal autodiff to 10⁻¹⁵, and Newton converges quadratically. Birth weight 2010–2023 fits in 9 s against v0's 21 s.
- **Age–sex cells with no exposure** in the whole block (a mother's male cells) are fixed at zero, and the profiles are centred over the exposed cells. Under the centring over both sexes, the unexposed sex's level was a flat direction tied to b0.

**BYM2.** The geography is reparametrised as BYM2: one σ and a mixing ρ (Riebler et al. 2016, §4.3). The v0's two separate τ's for the ICAR and iid parts form a ridge, which is the ill-conditioning the `move_tol` stopping rule steps around.

### 5.4 Strengths: the Laplace marginal likelihood (v1 built 2026-10-06: Newton on log τ with exact traces)

**v0:** Fellner–Schall fixed point, damped to ×10 per outer, with the Poisson Fisher diagonal per effect, Anderson-accelerated. It converges linearly: 12–40 outers per fit, each repeating the mean fit.

**v1:** the log strengths ρ_j = log τ_j (and the interaction's, and BYM2's σ and ρ) maximise the Laplace approximate marginal likelihood:

```
LAML(ρ) = ℓ(x̂) − ½ x̂ᵀQ_ρx̂ + ½ log|Q_ρ|₊ − ½ log|H_ρ|,   H_ρ = JᵀWJ + Q_ρ
∂LAML/∂ρ_j = ½ [ rank_j − τ_j x̂ᵀQ_j x̂ − τ_j tr(H⁻¹Q_j) ]   (+ the term from W's dependence on x̂, Wood 2011)
```

- **Fellner–Schall's fixed point is this gradient's root.** The v1 reaches the same optimum by Newton or BFGS in ρ: Wood (2011) for the outer Newton, Wood & Fasiolo (2017) for the relation to the fixed point. 5–10 outer iterations are expected.
- **Every quantity comes from the factor of §5.3:**
  - log|H| from its diagonal;
  - tr(H⁻¹Q_j) by selected inversion (Takahashi recursions on the sparse factor; the Schur part densely), which replaces the probes and per-row dense solves of `_trace_inv_times`.
- **As built (2026-10-06):**
  - Newton on ρ with the observed negative Hessian of LAML (W's derivative dropped): ½δ_ij τ_j(tr_j + q_j) − ½τ_iτ_j tr(ΣQ_iΣQ_j) − τ_iτ_j xᵀQ_iΣQ_jx.
  - Floored on each component's own scale, with Fellner–Schall's step where it agrees in sign and goes further.
  - It stops when the step's predicted LAML gain is below 0.1 (the BYM ridge is flat).
  - **Safeguarded as in mgcv** (Wood 2011, §3). The LAML itself is evaluated at every new mean: −objective + ½Σ rank_j ρ_j − ½ log|H| on the constrained subspace (the leaf-place blocks under their centring, the arrowhead, the kriging term). A step that lowered it by more than 2 units is halved from where it started. The step's target omits W's derivative, which on IX sits 1–4 % of τ from the LAML's own optimum; the tolerance absorbs that. Two reads are compared only when both are within 10 units of the mean's mode, and never across a moving interaction or a mark model's re-estimated dispersion; three failed halvings return to the best strengths found.
  - **Each strength has its own step radius**, adapted as Rprop's (halved on a reversal, ×1.2 while the direction holds, ×100 at most). A step that is not an ascent direction after clipping is replaced by the diagonal Newton step.
  - **Noise-aware.** The place traces are probe estimates, so each gradient component is shrunk toward zero by twice its standard error. On IX the noise reached ±13 for v_all and kept the predicted gain above the stop for a dozen outers.
  - The factor the strengths read is built at the converged mean. After chord steps the last factor belonged to a point up to four steps back, which put the LAML's derivative off by 10²–10³.
  - The globals' traces and their pairs in tr(ΣQ_iΣQ_j) are exact, from the globals' covariance block. The place components use 16 probes solved exactly with the factor: one Σz per probe gives their traces, and ΣQ_jz for the place j only gives every pair that involves them.
  - Selected inversion was measured and not adopted at this size: a numba Takahashi recursion took 44 s against about 2 s for 32 exactly solved probes, which agree with it to 10⁻³ (evaluation 2026-10-06, solver v1). A supernodal selected inversion would change that.
  - On IX: 6 outers cold, against 12–40 for v0; VII converges in 5, where the unsafeguarded step oscillated for 40.
  - **Open:** a strength heading for its boundary (IX's v_grp, an iid part that the ICAR part absorbs) climbs ×100 per outer, three outers in all. Sending it to the boundary in one step was measured and rejected, and PC priors on the place strengths did not stop it (evaluation 2026-10-06, solver v1). It stops at `SHRUNK` = 10³ (sd < 0.03). BYM2's mixing parameter is the reparametrisation that removes the ridge.
- **LAML is also a model-choice criterion** (§5.6), beside held-out deviance.
- **The dispersion φ** stays maximum likelihood with μ fixed (§5.2). A joint estimate inside LAML is a measured option.

### 5.5 Uncertainty (v1 built 2026-10-06: exact Laplace draws)

**v1** (`laplace.Posterior`, `solver.StructuredNewton.draws`; off by default, `Expectations(laplace=S)`): draws from the Laplace posterior N(θ̂, H⁻¹) on the centred subspace. They are exact, not perturb-and-MAP:
- H carries the negative binomial's expected information w = φμ/(φ + μ) for counts (each leaf's slab streamed once, its sums kept as the leaf's own features) and the family's Fisher weights for a mark model;
- the place and global coordinates come from their marginal precision, factored as MMᵀ: x = M⁻ᵀz, all draws in one multi-RHS solve;
- the leaf-place block is drawn given them in closed form, v = Z(D^½z − Bx);
- the centrings by conditioning by kriging;
- with the low-rank interaction, the draws are of the other effects, the interaction at its MAP.

Over 2,000 draws on IX, the variance of random projections equals the exact aᵀH⁻¹a within its Monte-Carlo error (ratios 0.96–1.04 against ±0.03), and the centrings hold to 10⁻¹⁰ (evaluation 2026-10-06, solver v1). The per-cell variance has relative error √(2/S). The predictive is matched by moments: 1/φ_eff = (E[Σμ²]/φ + Var(Σμ))/m².

**v0** (replaced): perturb-and-MAP draws (Papandreou–Yuille), each solved by CG with a block-Jacobi preconditioner (40–90 iterations per draw). It moved in-sample calibration by ≤ 0.01 KS (evaluation 2026-10-05, Laplace).

**Not built:** marginal variances of every effect by selected inversion (draws give them with error √(2/S)).

**Centring of the predictive.** In-sample tiers are centred on the MAP's μ, and BP on the posterior mean. BP adds the history's forecast error.

**The approximation is checked, not assumed** (OQ-2): against MCMC on sampled fields and states (§10.1).

### 5.6 Blocks, model choice, two-level fit

1. **Top model (not built).** All blocks' top-level nodes (chapters), with shared population and graph terms. It gives the chapter-level effects and the hyperparameter priors.
2. **Block models.** Each block with the top-level effects as an offset.
3. **Model choice.** Held-out deviance on the last two years, together with LAML (§5.4); never in-sample deviance. The choices:
   - rank R_b;
   - graph selection or mixture;
   - the tree prior (Gaussian or horseshoe, §4.3);
   - which trees and lists pool.

   Held-out deviance decides for the forecasting tiers. LAML decides where the held-out years cannot (a pattern absent from the last two years).

### 5.7 Hardware and stack

**Target machine:** 32 GB RAM (about 20 GB usable), 20 logical cores, NVIDIA RTX 4050 laptop GPU (6 GB, CUDA 12.1), about 177 GB free disk. The decision record is ADR-0003.

| need | library |
|---|---|
| arrays, sparse algebra | numpy, scipy |
| **sparse Cholesky, selected inversion** | **CHOLMOD via scikit-sparse** (installed into the environment; SuperLU fallback); per-place dense blocks by batched `torch.linalg.cholesky` on the GPU |
| automatic differentiation, GPU contractions and GEMM | **PyTorch 2.5 (CUDA)**; JAX's GPU builds do not run natively on Windows. Autodiff checks the assembled Hessian; it is not the solver's engine |
| fused kernels where a contraction is not enough | numba (CPU). CuPy was tried for the Schur products: in float64 this GPU took 0.15–0.26 s where the CPU took 0.08 s, so it was dropped (2026-10-06). `torch.compile` does not run on this machine: no Triton and no compiler toolchain, tested 2026-10-06 |
| columnar I/O, aggregation | pyarrow, duckdb, polars |
| scan loops (sorting, LTSS) | numba |
| reference GLMs for checks | statsmodels |
| CLI and configuration | typer, rich, pydantic |

**Numerics:**
- float32 on the GPU with float64 accumulation for sums over cells. The v0 runs float64 everywhere (`Monolith.dtype`), and mostly on the CPU: on the GPU, float32 cuts the total from 2.1 to 0.7 ms on IX (2026-10-06);
- float64 for the factorisations;
- every random draw seeded from (field id, cell, purpose), so every surprise is reproducible.

**Memory:**
- no array larger than the population tensor × the profile nodes of one block;
- GPU work chunked to 4 GB;
- the non-empty cells stream in batches from Parquet.

**Jobs** (`scripts/heavy.py`). A heavy job gets the machine's cores and states its share (`--threads`, set for its BLAS, OpenMP and numba); a GPU job takes the single GPU slot (`--gpu`). Few fat jobs are preferred to many thin ones: six fits of 2–4 threads competing for 2 GB of free memory each ran several times slower than alone (2026-10-06). Surveys have their own pool. A chain of jobs runs through `data/chain.py`, never `bash`, which on this machine resolves to WSL's and cannot see the C: paths.

### 5.8 Performance budgets and the benchmark

**Speed is a requirement (P13).** The benchmark (`bench`, to build in O1) fits a fixed set of blocks cold and warm and records seconds, outers, Newton steps, inner iterations, peak memory and the optimum reached. It runs on every change to the solver, and its result is an evaluation entry.

The measurements, the design of every fast path and the order of work are in `docs/plans/2026-10-06-optimization.md`.

| benchmark block | v0 measured (calm machine, 2026-10-06, unless noted) | target, cold / warm |
|---|---|---|
| SIM.DO VII 2010–2021 (277 deaths) | about 10 s per outer under load, 25-outer cap | 2 s / 1 s |
| SIM.DO IX 2010–2021 annual (2.07 M non-empty cells, 552 k parameters) | v0 calm: 501 s cold, 17 outers, 7,768 CG iterations (664–1,683 s under load). **v1: 59 s cold (6 outers, 9 Newton steps; IPF and moment start, safeguarded strengths, binned φ)** (evaluation 2026-10-06, solver v1) | 20 s / 5 s |
| IX with race × single child ages (G 36 → 330) | — | 90 s / 20 s |
| SIH-RD X 2010–2023 annual | about 1 h | 2 min / 30 s |
| SINAN-DENG 2010–2023 monthly | 145–160 s per outer (SIH X monthly, comparable) | 2 min / 30 s |
| all 19 SIM chapters; all 20 SIH chapters | hours | 10 min; 30 min |
| survey of one chapter | 65 s (III, 21 fields) to hours | < 2 min |

**Budgets are design targets.** The first v1 measurement either meets them or revises them, with the reason.

**The optimum is the acceptance criterion.** v1 must reach the v0's optimum on the same data: objective within one log-likelihood unit, τ's within the convergence tolerance, the same calibration.

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

### 7.0 Two layers: departure models infer, scans search (revision 2)

**Detection has two layers (P12):**
- **Departure models (§7.0, v1, to build) are the inference.** A lead is a posterior statement about a model term.
- **Scans (§7.1–7.4, v0, built) are the search.** They propose supports cheaply, and the departure models read those supports.

Until a departure model exists for an estimand, its v0 lens stands as the inference, and its leads say so (`method_maturity`).

**The departure model of a field.** The monolith's expectation, with its uncertainty, is the offset:

```
y_{u,t} ~ NB( μ̂_{u,t} · exp(δ_{u,t}),  φ_field )        δ = the estimand's departure term
```

Each estimand declares its own δ, taken from the field's established method (P11):

| estimand | departure term δ | established method | replaces |
|---|---|---|---|
| **unusual trend** of a place | a two-component mixture per place: the common course, or a place-specific course; the posterior probability of "unusual" | BaySTDetect (Li, Best, Hansell et al. 2012) | trend divergence's posterior-sd contrast and its δ grid |
| **cell excess** (outbreak) | a sparse excess per cell (horseshoe or spike-and-slab), or the two-group model on the PIT scores; the local false discovery rate per cell | Efron (2004, 2010); for prospective baselines, Farrington / Noufaily (2013) as the benchmark | the outbreak lens's BH on PIT tails at θ0 |
| **step** (change point) | a step per place with a discrete location and a shrunk size; the posterior over (location, size) | Bayesian change-point components (product partitions or a step basis with a shrinkage prior) | trailing-window NB tails with Bonferroni |
| **spatial cluster** | a BYM2 excess over B0 (or the field's place effect); exceedance probabilities P(RR_u > θ0 \| y), for irregular shapes a Bayesian spatial scan | disease mapping (Richardson et al. 2004 exceedance rule); Neill, Moore & Cooper (2006) | the B0 Poisson scan with its MSR-calibrated θ0 |
| **group disparity** | a place × group interaction, shrunk within the place and over the graph; the exceedance of the minimum effect | the hierarchical interaction of the monolith's own priors | the per-unit G² against a non-central χ² |
| **race disparity** (O3) | the race contrast's departure, by place and period, from its own national course; for each pair of races, the exceedance of a minimum rate ratio | the race terms of §4.2, read through the recording model of §4.1 | nothing: v0 read no race |
| **observation** fields | the same terms on recording-practice fields | as above | |

**What a departure model reports:**
- the **posterior of the effect** (rate ratio, slope ratio, step size), with its interval;
- the **posterior probability that it exceeds the minimum relevant effect (P5)**, which keeps its role as the region of practical equivalence, calibrated on null worlds (§8.4);
- **the set of reported departures, chosen so that its expected false discovery proportion**, computed from those posterior probabilities, is at most q (Bayesian FDR; Newton et al. 2004; Müller, Parmigiani & Rice 2006).

**Scale.** Departure models are fitted per field on its aggregate cells (place × period), not on the 10¹² implicit cells. They reuse the solver of §5.3, so they cost a fraction of the block's fit. Scales (§7.1) are the same models on lifted cells (`surprise.lift`).

### 7.1 Lenses (v0): one field, now the screens

| lens | statistic | null |
|---|---|---|
| spatial cluster | expectation-based Poisson scan over graph-connected place sets (§7.2 restricted to places) | §7.2 |
| outbreak, change point | outbreak: each cell's upper tail under the B2/B2s predictive (the PIT; prospectively under BPA, the alarm baseline, §6.1), with BH. Change point: per place, the exact NB tail of each trailing window, with Bonferroni over the windows, then BH across places | the predictive, exact; simulated nulls failed on sparse fields (evaluation 2026-10-04) |
| space-time cluster | §7.2 over place × time | §7.2 |
| group disparity | per unit of each scale: likelihood-ratio heterogeneity of the groups' SIRs against the national **observed** group pattern (B0 by group, re-levelled to the observed national total of each year and group), each group's deviance divided by its NB variance factor | non-central χ²(df, sd²·Σμ/k) |
| trend divergence | per unit of each scale: `β_u − mean_{N(u)} β` from B2 (reference `neighbours`) or `β_u` (reference `national`, B1 carrying the national course), in posterior standard deviations | the posterior (a coarser unit: Student t, sd inflated by its dispersion around a cubic course) |
| observation | the same lenses on recording-practice fields (ill-defined share, secondary-diagnosis coding, race reliability, notification delay) | as above |

**Scales (`scans/scales.py`).** A per-place lens reads a **scale**: municipality, IBGE immediate region (about 510 units) or state (27). A trend shared by a whole state cancels between a municipality and its neighbours and is a divergence only at the state; a sex-age pattern too thin to show in a municipality shows in the state. Every unit of every scale is tested in one family, with BH **within each scale at q / (number of scales)** (FDR ≤ q overall; one BH over all units charged the 27 states at the price of the 5,570 municipalities). The unit's B2 trend is the same Newton as the municipality's (`surprise.refit_place` on Σy against the offset Σμ, vague prior), and its locus is its member municipalities. Two trend estimands are declared (P4): against the neighbours and against the national course.

**The survey runs every lens on every field (revision 2).** The gate is retired (§10.5). Admission becomes weighting by power (§8.4).
- Lenses that failed their checks are run, and their characteristics travel with their leads:
  - the trend against the neighbours (recovered no positive);
  - the national trend at the municipality (failed the time-shift negatives);
  - group disparity (failed its negatives).
- `gate="failed"` becomes `method_status`, which a lead's rank reads. It is no longer a reason not to look.
- A region or state lead's trend replication is not defined (it reads a municipality's contrast with its neighbours): `untested`.
- v0 history: the survey ran only the gated combinations (`tools.SURVEY_PLAN`; evaluation 2026-10-05-lens-positives).

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

**Revision 2.** A subset is a **proposal**. The departure model of its estimand (§7.0) reads the proposed support, and the lead carries that posterior. The scan's Gumbel p stays as the search's own stopping rule.

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

### 7.5 Pairs (screens) and relation models

**Fields X and Y are compared at their common support** (the finest support both lift to by their laws).

| estimand | statistic | null |
|---|---|---|
| **E_b, between places** | weighted correlation ρ̂ over units of place effects b̂(u) (the posterior mean of a field-specific place intercept over B0, shrunk), pair weight `√(w_X w_Y)` with `w = 1/se²`, each field centred by its own weighted mean | **Dutilleul's modified t:** `n_eff = 1 + n² / tr(R̂_X R̂_Y)`, with R̂ from each field's spatial correlogram on the graph's distance classes |
| **E_b\|Z, adjusted** | partial correlation given a declared adjustment set Z (urbanisation, income, macro-region) | same, with n_eff − dim(Z) |
| **E_w, within places, lag ℓ** (v0; a screen only, revision 2: failed the arbovirus → microcephaly positive at the region-month grain and, prewhitened, at the state grain) | `ρ̂_ℓ = Σ_{u,t} w z^X_{u,t} z^Y_{u,t+ℓ} / norm`, pooled over places, on B2 surprises | per place, `n_eff,u = T_u (1−φ̂_X φ̂_Y)/(1+φ̂_X φ̂_Y)` (AR(1)); summed over places; divided by the design effect `1 + (U−1) ρ̄_space` for cross-place correlation at equal t |
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

**Relation models (revision 2; v1, to build).** A pair screen proposes; a relation model estimates. Each relation estimand has its established model, fitted with the solver of §5.3:

| relation | model | estimand reported |
|---|---|---|
| **an exposure leads an outcome by a delay** (arbovirus → microcephaly; cold → respiratory admissions; a disaster → admissions) | a **distributed-lag term** in the outcome's rate: `log μ_Y(u,t) += Σ_{ℓ=0..L} β(ℓ) · x(u, t−ℓ)`, with β(ℓ) a GMRF over lag (RW2, strength learned) and x the exposure's excess or rate at the grain where it is measured, lifted to the outcome's places. Heterogeneity across macro-regions as a hierarchical β. The outcome keeps its own season, trend and place course, so shared seasonality is not read as a lead. | **the lag–response curve with its uncertainty**, its cumulative effect, and the window where it departs from zero (Gasparrini, Armstrong & Kenward 2010, DLNM) |
| **two outcomes share their geography** | a **shared-component model**: both fields' place effects carry a common BYM2 component, scaled per field, plus their own | the shared share of each field's spatial variance, with its interval (Knorr-Held & Best 2001); multivariate extension as MCAR (Gelfand & Vounatsou 2003) |
| **infectious series drive one another** (between places, between notified diseases) | an **endemic–epidemic** term: the expected count includes the lagged counts of other places or series, weighted by the graph (care flows, contiguity) | the epidemic coupling coefficients (Held, Höhle & Hofmann 2005; Meyer, Held & Höhle 2017, `hhh4`) |
| **the same quantity in two systems** | the log ratio of the two systems' counts as a field with its own departure model (§7.0) | a recording or completeness departure |

**Guards that every relation model carries:**
- **Negative-control outcomes** that share the confounding and not the mechanism (Q90 for microcephaly), and **negative-control exposures** (the exposure's own future: a lead of the outcome over the exposure). Both are standard (Lipsitch, Tchetgen Tchetgen & Cohen 2010) and are reported beside the estimate.
- **The declared adjustment set** (§7.5, E_b|Z).
- **The relation is an association** between expectations' departures or rates, not a causal effect. Causal language needs a design (§7.8 cohorts, natural experiments) that the lead points to.

**The screens that propose relations:**
- E_b over all pairs (the Gram matrix);
- a prewhitened cross-correlation at a coarse grain for lagged pairs (`pairs.within(prewhiten=p)` on lifted surprises). It is a screen only; it failed the microcephaly positive at the state grain (evaluation 2026-10-05, re-test 2026-10-06).


### 7.6 Dependency maps (phase 3)

A map is a graph over many fields at once, built from the §7.5 pair test (`scans/maps.py`, inputs in `scans/map_inputs.py`, `pegasus-core map`). Fields are place effects (shrunk Poisson intercepts over the indirectly standardised expectation) of SIM chapters, SIH chapters (admissions that did not end in death: the in-hospital deaths are SIM records, §8.5), SINASC indicators and context fields (census, SIDRA, CNES, ANS, INEP).
- **Marginal layer:** E_b for every testable pair at δ_E.
- **Conditional layer:** E_b|Z for every testable pair, Z the other declared context fields, n_eff − dim(Z). Present in both layers is direct; marginal only, explained by the context; conditional only, suppressed by it.
- **Utilization factors (`maps.dependency_map(adjust=k)`, `maps.factors`):** the first k principal factors of the SIH chapters' place effects (weighted correlation, k = 2 by parallel analysis against Moran surrogates), re-extracted from the map's own fields so that a negative world re-extracts them from its surrogates, join Z for every pair with an SIH member. An SIH chapter is an admission rate per resident and a place's shared level of hospital use enters all of them, so SIH relations are read net of it (evaluation 2026-10-05, utilization); the model-side fix is the low-rank interaction (§4.2).
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

**Triage (`explain.triage`, `Session.triage`).** A lead is read against what the data at hand can say about it, in order. The first rule that fires gives its class (`lead.robustness["triage"]`):
- *system*: the denominator broke; the code's national level moved; the ill-defined chapter moved opposite; a residual category trending.
- *substitution*: siblings under the same parent undo the change.
- *noise*: too few events, or too small an effect.
- *facility*.
- otherwise *signal*, which means **unexplained by the data at hand, not confirmed**.

**Revision 2 (P14).**
- **A class is an explanation with a grade (ADR-0019), and only a *tested* explanation marks a lead `explained`.** A code-level class re-scopes the lead to its conserved level (§8.6).
- **The thresholds of these rules are v0 constants.** They are FAC_K = 3, FAC_SHARE = 70 %, ×1.6, z ≥ 3. Each is replaced by a measured model as §8.6 builds it.
- **The stored state was re-run.** 14,813 leads marked `explained` before the grading existed were reopened on 2026-10-06, with their old verdict kept (`triage.superseded`); their graded re-triage is a work package (§12).

Evaluation 2026-10-05, lead triage.

**Facility (`facility`).** The event cube by residence × recording facility × 3-character code × year (SIH-RD `CNES`, SIM-DO `CODESTAB`; one gateway-cached table per year). A lead is `facility` when at most `FAC_K` = 3 facilities carry at least `FAC_SHARE` = 70 % of its change (window against base years), that concentration is not what the facilities' size would carry (one-sided binomial p < 10^-3 against their share of the block's base-year events, unless they are the whole place), and a mechanism shows in the facilities' own behaviour: the same facilities' residents of *other* places show the same step in the lead-code share of the block (z >= 3, at least half the inside log ratio), or the facilities' volume without the lead's events stepped by x1.6. Concentrated but the others do not move: `place_specific`, the lead stays a signal. The class says the change is attributable to one institution's recording or volume; it does not say whether the institution coded differently or served a real event (a referral hospital receives both). SIM names a facility for 71-73 % of deaths only, so the read is partial there.

### 7.8 Cohort scans (phase 2)

On linked cohorts from pegasus_data (person-level records): every attribute × every outcome.
- **Model:** Poisson regression with person-time offset, adjusted for age, sex, year and a place random intercept.
- **Test:** a minimum-effect test on log RR (`|log RR| ≤ log δ_RR`, default δ_RR = 1.2 until calibrated).
- **Multiplicity:** BH across the grid within a family.

---

## 8. Error control, replication, weighting, recording

### 8.1 Families

A **family** is (lens or estimand, tier, field family or pair of field families, support class).

### 8.2 FDR

- **Within a family:** Benjamini–Hochberg at q = 0.05. Benjamini–Yekutieli where p-values within a family are not positively dependent.
- **Across families:** Benjamini–Bogomolov selective inference. Families are selected by their Simes p-value at level q; then within each selected family BH at `q · |selected| / |families|`.
- **Down code trees:** TreeBH (Bogomolov et al. 2021) when a lens tests the nodes of a classifier tree.
- **Departure and relation models (§7.0, §7.5; revision 2).** The reported set is chosen so that its expected false discovery proportion, computed from the posterior probabilities of exceeding the minimum effect, is at most q (Bayesian FDR; Newton et al. 2004). Across families, the same Benjamini–Bogomolov selection applies, with each family's evidence summarised by its smallest local fdr.
- **Weights (§8.4).** The frequentist families are weighted by power (IHW), not pruned by it.
- **Agents.** Exploratory tests are logged but carry no claim. Claims pass through `confirm` (§9.3) on the reserve (§8.3), whose stream is controlled by online FDR (LOND).

### 8.3 Replication (ADR-0015)

A lead is selected on data and confirmed only by **units that took no part in the selection**. Splitting a cell's own events cannot do it: the sides share the cell's frailty, so under extra-Poisson variation the excursion that selected the cell shows on the other side (ADR-0007, withdrawn; OPEN_QUESTIONS 7).

| independent unit | test |
|---|---|
| **later years** (`temporal`) | selected by a survey on the years up to t (`Session.train`); the fit refitted without the later years (BP, the place's course not carried forward); the same places tested on the later years' sum, re-levelled to each state-year's observed course (`replication.relevel`), one-sided at the lens's minimum effect; BH over what was tested. A persistent or recurring departure replicates; a one-off event cannot. |
| **other places** (`spatial`, ADR-0019) | for a claim about a predeclared unit: the other *jurisdictions*, the unit that sets the coding regime (`replication.jurisdiction`). A state claim must hold in other states (more of them diverging the same way than chance, binomial over the states with 30+ events), else its scope is one jurisdiction and it is not confirmed; a region claim in a random half of its states and without its most influential state; a municipality claim must not be carried by its state's other municipalities. (ADR-0015 halved the unit's own municipalities, which share a regime.) A cluster is untested. |
| **another record system** (`corroborated`, §8.3.2) | the lead's places and years in S2iD, SINAN or SIH against that field's own place-set null |

**Reading a unit claim against how deaths are recorded (ADR-0019, `replication.audit`, `Session.spatial_confirm`).** A coding regime recurs in time and holds across a jurisdiction's municipalities, so the tiers alone confirm it as readily as a mortality change. Every unit claim is therefore also read on direct standardisation (the year's observed national rate by sex x age, `replication.Strata`), and **every recording explanation carries an evidence grade** (`explain.GRADES`): *tested* (a test separates it from the claim), *bound* (it accounts for at most a stated share, under a stated assumption), *consistent* (the aggregates cannot exclude it). Only a tested explanation downgrades a claim; the others stay attached to it. The readings: (1) the claim's slope against the observed national rate must hold with half its size (else `not_replicated`, and it confirms nothing: `kinds_of`); (2) the unit's all-cause slope, a mandatory column, and its share of the claim (bound); (3) conservation inside the ICD family: the rest of the node's block, R00-R99 and (external causes) undetermined intent Y10-Y34 moving the other way (`explain.exchange`: a *bound*), made *tested* by the profile of the displaced deaths in sex, age, place of occurrence and mechanism against the node's and the pool's (`explain.profile_test`); (4) shape: a one-year step against the better of a linear and a quadratic course (`explain.shape_test`; a step is classed administrative, grade consistent); (5) the jurisdiction split above. Verdicts: `not_replicated`, `explained` (a tested explanation accounts for half or more), `open` (explanations remain), `survives`. `explain.triage` grades its own classes the same way and marks a lead `explained` only when the grade is tested.

**Tiers.** R0 passes §8.2 on all data; R_k holds k of the three confirmations. They count independent evidence and are not a ladder; a lead's kinds are listed by `explain_lead`.

**Corroboration (§8.3.2).** The place set and years of a lead, in a field that shares none of its records: SIM deaths against S2iD (disasters), SINAN (notifications) or SIH (admissions that did not end in death: the in-hospital deaths are the SIM records, §8.5, and their share is recorded). **The null is the corroborating field's own:** the same statistic (places with a registered disaster; the log ratio of the window's count to the places' median year) on random place sets of the same size, in the same states, over the same years (a lead's touching places are one cluster, replaced by a connected set grown on the graph: a cluster shares its neighbours' shocks; its isolated places by a place of the same population quintile); p = (1 + #{null >= observed}) / (1 + B), B = 4,999, redrawn at 99,999 where p < 0.01 (a floor of 1 / (B + 1) would otherwise stop BH over hundreds of tests from ever rejecting). BH within each source. A deficit is not corroborated by a field. The rules (which field for which codes) are data (`corroborate.RULES`). The null sets are scattered; a contiguous cluster shares its neighbours' shocks (OPEN_QUESTIONS 7).

**The event split** (`control.SIDES`, A 50 / E 50; `Session.honest_sizes`) is kept for sizes only: given a cell's rate its sides are independent Poisson counts, so the rate ratio read on E, with its exact Poisson interval, is unbiased for the locus's realised rate whatever A selected. It includes the cell's frailty and is no evidence of recurrence.

**The confirmation reserve is a reserved period** (`control.RESERVED_PERIODS`: SIM.DO 2024, final after every fit and survey on 2010-2023). `monolith.assemble` and `Session` refuse it (`ReservedPeriod`); only `confirm_many` opens it (`reserve_open`). A claim (a persistence claim: fixed places and direction) is tested once on it against the fit on the session's years, and its p-value enters one LOND stream (§8.2) whose state is read back from the ledger (`control.Reserve`, split `period:reserve`); the order of the claims is fixed before the reserve is read. Preliminary years are added only when final.

### 8.4 Weighting by power, and minimum effects (revision 2)

**No field is excluded for low power (P9).**
- **v0 (ADR-0022):** a field entered a lens only where the lens's power at a reference effect reached 0.5.
- **The objection:** FDR already controls the false discoveries of weak hypotheses. Their only cost is a dilution of the others' power, and weighting answers that.

**v1 (to build): weighted multiple testing.**
- Each hypothesis carries a weight from a covariate that is independent of its p-value under the null: the expected count of its locus, the power curve read at it, the field's sparsity.
- The weights are learned by **independent hypothesis weighting** (Ignatiadis, Klaus, Zaugg & Huber 2016), with cross-weighting so that the data choosing a weight never test the hypothesis it weights. FDR control holds.
- For the departure models (§7.0), the posterior probabilities already carry the power: a field with little information has wide posteriors and rarely crosses the minimum effect. Their FDR is the Bayesian one of §8.2.
- **Every reported result carries its minimum detectable effect**, read from the power surface (§10.2). A "nothing found" in a sparse field says how large an effect it could have missed.

**The v0 curves stay as measurements.** `harness.region_power`, `admission_curves.json` and `harness.pair_power` are inputs of the weights and of the minimum detectable effect, not gates. They come from the production lens run on planted loci.
- **The detection criterion:** a finding lying at least half inside the planted macro-region-year. A macro-region-year is far larger than one cell or the scanner's 30-place neighbourhood.
- **Their limit:** five chapter-IX fields and Q02, thinned to five sizes. The designed grid of §10.2 replaces them.

**Minimum effect δ_E per estimand.** The smallest δ for which the false-lead rate on the **negative controls and null worlds** stays ≤ q (§10.2–10.4). It is the empirical-calibration idea of observational-health research networks, applied to the search itself. It is the region of practical equivalence of the departure models (§7.0) and of the pair screens.
- **Calibrated so far:** δ_E = 0.03 for E_b, 0.05 for E_b|Z (ADR-0005), 0.1 for E_b|Z in maps (ADR-0013); the spatial cluster's θ0 = 1.5 (evaluation 2026-10-05, lens gate); marks 1.5 % (PESO negatives).
- **Provisional elsewhere:** θ0 = 1.2 for outbreak, change point and space–time; trend divergence 1.5 at the municipality, 1.2 at region and state; group disparity sd 0.2, **not calibratable** on the spatial negatives (MSR holds only from sd 1.0 at the state). Values live in `scans/lenses.py`.
- **The minimum effect is a statement of relevance, not of detectability.** A field that cannot see it is weighted, not dropped.

**Why minimum effects at all** (evaluation 2026-10-04, chapter IX). Testing against zero flooded the survey with trivially small departures, because tens of thousands of deaths make anything significant:
- hypertension (I10–I15): trend divergence fell from 116 to 38 places, group disparity from 121 to 7;
- the strongest signals survived, São Borja among them.

### 8.5 Mechanical overlap

```
overlap(X, Y) = |events(X) ∩ events(Y)| / min(|events(X)|, |events(Y)|)
```

It is computed from records by pegasus_data. Pairs with overlap > 0.05 are not tested for dependence: they are nested codes, alternative classifiers, or "any mention" against underlying cause. They may be tested on their non-shared events.

---

### 8.6 Recording as measurement (revision 2, P14)

**A departure in a recorded count is a change in events, in how they were recorded, or both.** v0 separated them after the fact, with triage rules and thresholds (§7.7). Revision 2 moves as much as the data identify into the model, and grades the rest.

1. **Conserved-level fields are standard (to build).**
   - For every node, the field of its conserved level is fitted and surveyed beside it: the ICD family, plus R00–R99, plus (for external causes) undetermined intent Y10–Y34, the pools a coding change exchanges with. These are list structures across blocks (§3.1).
   - A lead is reported at its own level and at its conserved level. A coding exchange shows as a node lead with no conserved-level lead, which is the *tested* reading of ADR-0019's exchange, available for every lead instead of on demand.
2. **Recording processes are measurement terms where the data identify them:**

   | process | term | state |
   |---|---|---|
   | completeness κ of SIM/SINASC (UF × year) | exposure modifier | built; opt-in (2026-10-06: absorbed by the place terms at B1/B2/BP; B0 changed by −4,149 to +14,709 negative log score, mixed in sign) |
   | race misclassification | confusion matrix on the expected recorded counts (§4.1) | built for infants and births; adults stay recorded race |
   | coding regimes of a jurisdiction and era | a confusion between sibling codes and the conserved pools, by state and period, estimated from the exchanges of item 1; garbage-code redistribution (GBD style, Naghavi et al. 2010) as a sensitivity tier, not the default | to build |
   | a facility's coding or volume | the institution lattice (§4.5) and E_i | first stage built |

3. **Graded explanations, never dissolution (ADR-0019).**
   - Only a *tested* explanation marks a lead `explained`; *bound* and *consistent* explanations stay attached.
   - A code-level explanation **re-scopes** the lead to its conserved level, and the lead is re-tested there.
4. **A changed rule is re-applied to the stored state.**
   - Every stored verdict carries the version of the rule that produced it.
   - When a rule changes, the verdicts of the old version are reopened and re-run.
   - The 2026-10-06 audit found 14,813 leads removed under a rule that predated grading.

*(§8.4–§8.5 were lost in commit 4c0397a and restored from 4c0397a^ on 2026-10-05. Later changes to the values they name live in the evaluations: the marks floor of 1.5% (lens positives, redesign section); δ_E for E_b|Z in maps 0.1 (ADR-0013).)*

## 9. Leads, the ledger, use

### 9.1 The lead

```
Lead
  id, kind            residual | subset | pattern | relation | cohort | observation | structural
  estimand, tier, fields, support, locus (places, times, groups, codes, institutions)
  effect              estimate, interval, scale (rate ratio | ρ | log RR | share absorbed)
  test                statistic, p, q, family, null, calibration status
  replication         R0..R3, with each replication's effect
  robustness          C-robust (race), denominator tension, recording flags, overlap, triage class with its grade and rule version (§7.7, §8.6)
  conserved           the same reading at the lead's conserved level (§8.6)
  method              the method's maturity and status, its power at the lead's size and support, its false-discovery rate on null worlds, the minimum detectable effect (§10.5)
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

## 10. Validation: characterisation, not permission (revision 2)

### 10.0 What validation is for (P9)

**Validation measures a method's operating characteristics.** It does not decide whether the method may run.
- **The model:** whether the fit recovers what generated the data, and whether its predictive is calibrated (§10.6, §6.2).
- **A detector or relation method:** its power over a designed grid of planted signals (§10.3), and its false discoveries on null worlds (§10.2, §10.4).
- **Documented real events (§10.1)** are a held-out check of face validity. **They are never used to tune a constant, a rule or a design choice.**
  - Tuning happens on the planted grid.
  - The v0 history (θ0, the alarm history rule chosen on dengue 2019–23, the trend reference chosen because the positives were state-level) is recorded where it happened.
  - Those choices are re-made on the grid in work package O5 (§12).

### 10.1 Documented events (held out)

Each event is declared before it is scored, with its estimand, tier, locus and criterion (locus overlap ≥ 0.5 Jaccard; effect sign). A failure is a finding about the method, recorded with its reasons; it does not take the method out of the survey.

| signal | lens / estimand | locus |
|---|---|---|
| microcephaly and congenital anomalies | space-time, B2 | Northeast, 2015–16 |
| arbovirus notifications → microcephaly births | a distributed-lag term on Q02 births (§7.5), the lag curve's mass at 5–9 months; v0: E_w, lag 6–9 months (monthly) | Northeast, 2015–16. **v0 not recovered twice:** E_w at region-month (ρ ≈ 0.12 flat over lags 0–6) and prewhitened at state-month (lag 0, ρ 0.20; declared in `21c771e`, evaluation 2026-10-05 and its 2026-10-06 re-test) |
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

### 10.3 Planted signals: a designed grid

For a field and locus S, inject `y' = y + Poisson((θ − 1) · μ_S)` with a known θ. For pairs, inject a shared latent field into both fields' intensities. For a lagged relation, inject into the outcome a distributed-lag response to the exposure's own series.

**v0:** power curves of four lenses on five chapter-IX fields and Q02, at one locus type (a macro-region-year), thinned to five sizes (ADR-0022).

**v1 (to build): a designed grid.** Each method is characterised over:

| axis | levels |
|---|---|
| locus | one cell; one place over a window; a graph-connected cluster; an immediate region; a state; a macro-region |
| shape | spike; step; trend change; seasonal shift; group-specific excess; a lagged response to another field |
| size | rate ratio 1.1, 1.2, 1.5, 2, 3 (lag responses: cumulative RR) |
| duration | 1 period; 3; whole remaining series |
| field sparsity | expected events per place-year in five quantile bins of the real fields |

- **Fields are real.** The backgrounds are fitted fields of every system: SIM, SIH, SINASC, SINAN, monthly and annual.
- **The outputs:**
  - each method's **power surface**;
  - the **calibration of its posterior probabilities** (departure models): do 90 % exceedances hold 90 % of the time;
  - its **bias in the estimated effect**.
- The surface gives every result its minimum detectable effect, and the weights of §8.4.

### 10.4 Null surrogates

The full pipeline is run on `y* ~ NB(μ̂, φ̂)`, independent across fields. **The leads found are the false-lead rate per lens.**

### 10.5 No gate: what replaces it

**v0:** a lens ran in production only after it recovered its positives, held its false-lead rate on surrogates, and had a published power curve.

**Revision 2:** every method runs, and every lead carries its method's record:
- maturity (v0, v1, v2);
- its measured power at the lead's size and support;
- its false-discovery rate on null worlds;
- its documented-event record.

A method that fails its null worlds (false discoveries above q at its minimum effect) is not silenced. Its minimum effect is recalibrated until it holds, and the recalibration is an evaluation entry.

### 10.6 The model's own checks

1. **Simulation-based calibration** (Talts et al. 2018). Data simulated from a fitted block's posterior are refitted, and the ranks of the true parameters among the posterior's draws must be uniform. This checks the Laplace approximation and the solver together.
2. **Exact against approximate.** On sampled fields and states (never only the densest slice), the Laplace fit is compared with MCMC (OQ-2).
3. **Held-out deviance and calibration of the forecasting tiers** (§5.6, §6.2).

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
| `monolith` | model spec (§4), factorised likelihood (§5.1), dispersion (§5.2), the fit's outer loop (§5.4), blocks and model choice (§5.6), marks' likelihoods (§4.4), prediction for any slice | structures, fields, solver |
| `solver` (O1, built for every model) | the assembled block-arrowhead Hessian with leaf-specific features (the interaction's active leaves, the mark models' cells), per-place elimination, the graph's supernodal sparse Cholesky and solves, the Schur complement on the globals, constraints by contrast bases and kriging, LAML and its gradient, the interaction's joint step, exact Laplace draws (§5.3–5.5) | structures (scikit-sparse, numba, torch) |
| `marks` | the mark models' fitting per chapter: specs (length of stay, cost, death, ICU), empirical-Bayes facility effects, the mark lead's facility triage (§4.4) | monolith, facility |
| `laplace` | the Laplace posterior of a fitted count block (§5.3): information from pairwise marginals, perturbation draws, predictive moments, the history's forecast error, full-Hessian Fellner–Schall | monolith |
| `surprise` | tiers (§6.1), PIT and calibration (§6.2), the virtual cube (§6.3) | monolith, laplace, prospective |
| `prospective` | BP's predictive (§6.1): the training fit's φ_extra, the place course, the mixture PIT | monolith, laplace, surprise |
| `scans` | a subpackage: `lenses` (§7.1), `subset` (§7.2–7.3), `patterns` (§7.4), `pairs` (§7.5), `maps`, `map_inputs` and `utilization` (§7.6), `explain` (§7.7), `cohort` (§7.8); `departures` (§7.0, to build) and `relations` (§7.5's relation models, to build) | surprise, monolith, fields, solver |
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
  blockdata/<hash>/arrays.npz, manifest.json                        (an assembled BlockData; key = arguments, data version, population key and content hash, hash of the assembly and gateway source)
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
No question is excluded for low power; it is weighted and reported with its minimum detectable effect.
No constant, rule or design choice is tuned on a documented event.
Only a tested explanation removes a lead; a changed rule is re-applied to the stored state.
A solver change is measured on the benchmark before it is adopted.
```

### 11.5 Verification

**Statistical code is verified by the harness on real data** (§10) and by measured comparisons (exact against approximate fits, old against new code on identical data). It is not verified by unit tests written alongside the code, which pass by construction (CLAUDE.md §5).

---

## 12. Roadmap: the overhaul (revision 2)

**Phases 0–3 of 2026-10-04** (harness, monolith, lenses, pairs, replication, maps, institutions' first stage) were built as v0 by 2026-10-05. Phase 4, prospective surveillance (ADR-0004), stands as the goal (O10).

**The overhaul's work packages** run in this order: speed first, because every later measurement waits on it. Each package ends with its measurement, its evaluation entry and its decision. Details, acceptance and the running state are in `docs/plans/2026-10-06-overhaul.md`.

| package | builds | accepted when |
|---|---|---|
| **O0** | this revision: review, principles P9 and P11–P15, the ICD ontology (§3.3) and race (§3.4), §5, §7.0, §7.5 relation models, §8.4, §8.6, §10, this roadmap (ADR-0023) | written (2026-10-06) |
| **O1, solver** | `solver`: the assembled arrowhead Hessian (checked against autodiff), elimination, sparse Cholesky, Schur complement, constraints; BYM2; LAML in log τ; selected inversion; the benchmark (`bench`, O1) | the v0 optimum is reached on the four benchmark blocks, and the §5.8 budgets are met or revised with the reason |
| **O2, settle** | refit the fitted blocks on the new solver; decide what waited on slow fits: the interaction's rank (ADR-0021), the tree prior (horseshoe), the SUS exposure and race groups (ADR-0020), the SINAN wave-1 families | each decision has its held-out measurement |
| **O3, race and ages** | pegasus_data: the 2000 undeclared imputed from the census microdata with household context (totals untouched), the within-band prior from 2010's cohorts, the sample-to-full-count correction measured on 2010, the 1991 race, single ages 0–19 validated; PegaSUS: G = 33 ages × 2 sexes × 5 races, the recording model of §4.1, the race terms of §4.2, the race-disparity departure | births, infant deaths and one adult chapter fitted with race and single child ages; recorded against expected by race calibrated at B1; disparities with intervals checked against published rates (held out) |
| **O4, ICD ontology** | pegasus_data: the ontology product of §3.3 (attributes from the DATASUS release, age plausibility, ICD-9 and its bridge, the lists to add, external-cause axes, the relation graph); PegaSUS: list effects θ_L, structural zeros, intent and mechanism fields, conserved levels and corroboration rules read from the relations | the ontology served through `gateway`; one chapter refitted with lists and zeros, held-out deviance against the fit without them |
| **O5, characterise** | the designed grid of planted signals (§10.3) and null worlds over real fields of every system; v0 constants re-made on the grid; IHW weights (§8.4); the gate retired in code, the method record on every lead | every v0 lens has its power surface and null-world FDR; no documented event tunes anything |
| **O6, departures** | departure models (§7.0): unusual trend (BaySTDetect), cell excess (local fdr / shrinkage), step, cluster exceedance, group interaction; Bayesian FDR | each beats or matches its v0 lens on the grid at equal FDR, else the lens stays the inference and the reason is recorded |
| **O7, relations** | the distributed-lag term in the monolith; the shared-component model; the endemic–epidemic term for infectious families; negative controls | the arbovirus → microcephaly lag recovered (declared before the run), cold → respiratory admissions estimated with its interval, null worlds held |
| **O8, recording** | conserved-level fields as standard; the graded re-triage of the stored register (running, 2026-10-06); rule versions on verdicts; the coding-regime term | no lead removed by an untested explanation; every lead read at its conserved level |
| **O9, breadth** | on the fast stack: SINAN families beyond wave 1, SIH marks (§4.4), SIA/APAC, CIHA, the SIH↔SIM link's products | each new system calibrated at B1 and surveyed |
| **O10, top model and surveillance** | the top model and the model-choice loop (§5.6); phase 4 (ADR-0004), with alarm baselines benchmarked against Farrington/Noufaily and published alerts (InfoDengue) | timeliness, false alarms and hits against the benchmark |

**What pegasus_data must supply** for each package is requested in `docs/handoffs/`, as before (§2, rule 2).

---

## 13. Departures and maturity

### 13.1 Maturity by component (2026-10-06)

| component | § | maturity | raised by |
|---|---|---|---|
| model (§4): levels, profiles, geography, history, season | 4 | v1 (the established LGM), BYM instead of BYM2 | O1 |
| tree prior: Gaussian per level; horseshoe built as `prior="horseshoe"` | 4.3 | v1 built; v2 pending: held-out on XVII shows no difference (2026-10-06), I and IX running | O2 |
| low-rank interaction ψωτ | 4.2 | v1 built (ADR-0021); rank not chosen: held-out deviance on IX falls monotonically R0 → R3 (2.2185, 2.1938, 2.1840, 2.1799) | O2 |
| marks | 4.4 | v0 (PESO); SIH marks built, not run nationally | O9 |
| mean solver | 5.3 | v1, **the default for every model** since 2026-10-06 (exact Newton; IX cold 59 s against v0's 501 s, a better optimum and held-out; monthly grain, the interaction, marks and shares verified against autodiff); v0 retired (the horseshoe reads exact Laplace variances) | O1 |
| strengths | 5.4 | v1 built (Newton on log τ, exact traces); held-out equal to v0 on IX | O1 |
| uncertainty | 5.5 | v1: exact Laplace draws from the factor (off by default); selected inversion not built | O1 |
| tiers, PIT calibration, φ_extra hierarchy | 6 | v1 | — |
| lenses and their nulls | 7.1–7.2 | v0, now screens | O5, O6 |
| departure models | 7.0 | not built | O6 |
| E_b and E_b\|Z pair screens, maps | 7.5–7.6 | v1 as screens (Dutilleul n_eff, MSR negatives) | — |
| E_w | 7.5 | v0, screen only, failed its positive twice | O7 |
| relation models (distributed lag, shared component, endemic–epidemic) | 7.5 | not built | O7 |
| triage | 7.7 | v0 rules with thresholds; graded, re-scoping (ADR-0019) | O8 |
| replication on independent units | 8.3 | v1 (ADR-0015, ADR-0019) | — |
| admission | 8.4 | v0 exclusion by power (ADR-0022), to be replaced by weighting | O5 |
| recording as measurement | 8.6 | κ and race built; conserved-level fields and coding regimes not built | O8 |
| validation | 10 | v0 (positives, negatives, power curves of four lenses, a gate) | O5 |
| race as an axis, the recording model, disparities | 3.4, 4.1, 4.2 | v0 race-stratified blocks for births and infant deaths, unmeasured; adults, SIH and SINAN read no race | O3 |
| the ICD ontology | 3.3 | the tree to the category; lists, attributes, ICD-9, relations not used | O4 |
| top model, model-choice loop | 5.6 | not built | O10 |

### 13.2 Departures

*Where the code knowingly departs from this document, with the reason. Each row closes when the code catches up.*

| § | the document says | the code does | why |
|---|---|---|---|
| 4.3 | horseshoe on tree levels, one variance per level per top branch | the default stays iid Gaussian per level; the horseshoe is built as `prior="horseshoe"` (a reweighted penalty, the closed mean-field fixed point of the half-Cauchy's auxiliary form, 2026-10-06) | the default changes only if held-out deviance favours it (O2); on XVII it made no difference (leaf-total deviance 949.3 against 949.8) |
| 4.3 | BYM2 with a learned mixing ρ | BYM: separate τ for the scaled ICAR and the iid part; ρ reported from the two τ's | the two τ's form a ridge that stalls the solver (§5.3); BYM2 comes with the v1 solver (O1) |
| 4.2 | geography carried down to a declared level ℓ_g | groups carry ICAR + iid; categories carry an iid `v_cat[e, u]`, centred within the group | the category-level place deviation is real (chapter IX: sd ≈ 0.47), and the coding-substitution leads read it |
| 4.2, 5.4 | the low-rank interaction ψωτ for every leaf, ψ, ω, τ all learned scales | built (ADR-0021) on the active leaves (≥ 0.1 % of the block's events), ψ and τ strengths fixed, ω ICAR + iid, annual grain, no Laplace draws, no top-model sharing of ω across blocks; the rank is chosen per block by held-out deviance on a script, not by a model-choice loop | the cube's cost is E·U·T per Hessian-vector product; fixing two of the three scales identifies the product; the cross-block shared factor needs the top model (§5.4), not built |
| 5.2 | every strength is learned (P7), the dispersion by place group included | φ_extra is a hierarchy (field, macro-region, state); the block's φ is one value per block | the block's φ by macro-region gained 0.009 nats per event held out on dengue and −0.0007 to +0.002 on chapters IX, X and XVIII (ADR-0006) |
| 5.3–5.5 | exact Newton on the assembled Hessian; LAML for the strengths; selected inversion for uncertainty | v1 for every model: exact Newton, safeguarded Newton on log τ with exact global traces and probes, exact Laplace draws; selected inversion measured and not adopted (probes); v0 retired | — |
| 6.1 | B2s on every field; BP is a mixture over the history's regimes, not the RW2 forecast | the monthly grain (season: cyclic RW2 over 12) is built for event counts; B2s refits trend + one harmonic per place; marks and code lists stay annual. BP at the annual grain damps the last slope (0.5 per year) and adds each place's damped B2 trend; at the monthly grain h is not extrapolated but drawn from the fit's years (a flat level36 baseline reached obs/expected 2.2 on dengue, the climatology 1.2; the outbreak-robust and level36 point baselines of evaluation 2026-10-05, baseline history, remain as `history=`) | the last two months' slope is noise at that grain; an epidemic series has no level to extrapolate; places drift apart (evaluation 2026-10-05, BP level) |
| 10.1, 7.5 | lagged relations are estimated by distributed-lag terms; marks recover a documented event | E_w only (a screen): cold → respiratory admissions (RR 1.07, Requia et al. 2023) gives ρ −0.02 to −0.07 at the monthly municipal grain; arbovirus → microcephaly not recovered at region or, prewhitened, at state grain; marks: none declared | the relation models are O7; no citable mark shift ≥ 4 % |
| 7.2 | groups as a free dimension of every subset scan | the scanner takes any free dimensions; the cell lenses pass places × time. Group disparity is a per-unit G² over the groups (not a subset scan of them), at the municipality, region and state scales (`scans/scales.py`); the trend lens reads the same scales | a subset scan over groups × places needs the per-group surprise in the scanner; the G² at three scales answered the documented departures (evaluation 2026-10-05-lens-positives). `Session.survey` runs the gated combinations (§7.1); a multi-municipality locus is a story of its own, its trend replication untested, and the group lens runs only `--ungated` |
| 8.2 | TreeBH (Bogomolov et al. 2021) | TreeBH with Simes aggregation at each node | the exact combination is a later refinement |
| 11.3 | artefact keys hash pegasus_data's data versions | keys carry pegasus_data's package version, plus the sha256 of the shipped resource for artefacts derived from one (code structures, graphs); the commit is recorded in each manifest | pegasus_data exposes no publication-level data versions yet, and its commit changes with every edit |
| 3.1, 4.1 | the population carries uncertainty and N enters the predictive with it | `account-2` and `account-3/4` carry it (σ of log N from the 80 % interval; `Monolith.exposure_variance`, ρ = 0), but the default source is POPSVS, which has none | no account is better than POPSVS on chapter IX or births deviance (account-3: births B1 +0.4 %, held-out KS .096 against .059; its births loss sits in 2020–2023 in places of 25–1000 births a year), and its exposure variance double counts the φ already estimated with μ fixed (evaluation 2026-10-05, exposure; ADR-0010). Closes when φ is estimated with the exposure variance in |
| 2.1 | meaning comes from pegasus_data | `gateway._date_sql` parses raw date text (YYYYMMDD, DDMMYYYY), and `_residence_sql` maps the Federal District's administrative-region codes in SIH-RD 2008–2017 to 530010 | interim; pegasus_data now derives `<COL>_date` and `MUNIC_RES_municipio` (pegasus_data c893b69, 1f88401). Binding the roles to them changes every gateway cache key, so the switch waits for the next re-warm |
| 8.4 | every field scanned, hypotheses weighted by power (IHW) | v0: admission by exclusion where power < 0.5 at the reference effect (`fields.admission`, `admission_curves.json`, `harness.pair_power`); the survey runs only the gated lens combinations (`tools.SURVEY_PLAN`) | O5 replaces both |
| 11.4 | a miscalibrated field never enters a pair scan at the tier where it failed | the map reads B1 for SIM and SIH chapters (the place effects are over B0, which fails by design); SINASC indicators and contexts have no tier | ADR-0022 |
| 8.4, 10.2 | δ is the smallest value at which no family's false-lead rate on the negatives exceeds q; single-field lenses have negatives that keep the field's dependence | spatial cluster θ0 = 1.5 (pooled negatives 0.04, worst family 5/30), where the family rule gives 2.0; single-field negatives are MSR of the residuals on a knn8 graph and a per-place shift, with a normal-scores variant | θ0 2.0 loses the Chagas positive; the B0 residuals carry smooth place effects, which a Poisson scan reads as clusters. Closes with a B0 scan null that carries the field's spatial spectrum |
| 7.6 | a sparse + low-rank Gaussian graphical model, penalties by StARS, edges also passing the pair test | pairwise E_b and E_b\|Z given the declared contexts, no joint model; run 2026-10-05 (ADR-0013): delta_E|Z 0.1, 0 false edges in 40 surrogate worlds | each pair carries its own spatial n_eff, which a joint likelihood has no place for; the conditional layer conditions on declared contexts as the low-rank part would |
| 4.5 | the facility effect is part of the model: a place × facility supply term estimated with the monolith, and crossed place and facility effects at the node level | the supply term is a multiplier of the fitted expectation, with two exponents chosen by likelihood after the fit on the same cells (opt-in); the facility's own handling of a node (coding) is not subtracted, only read on the lattice | the independent evidence (other chapters) removes 11 % of the facility class and 6.5 % of the signals (evaluation 2026-10-05, institutions); what the facility does with the block's own codes cannot be subtracted without absorbing an outbreak that one hospital serves. A refit with the term inside the likelihood, and crossed effects where places share facilities, are the next stage |
| 4.1 | κ and N^{(SUS)} are factors of μ; groups g = age × sex × race | κ and the SUS share are exposure modifiers of the source string (`popsvs+kappa`, `+sus`), opt-in; race groups are race-stratified blocks (own θ, f, g, h per race), not a race axis of G; infant deaths by recorded race use the exposure Σ_j C(k\|j) r_j N_j with r_j fitted on the recorded counts, valid when declared races share one shape; SUS before 2021 is the 2021-23 cell mean with a measured random-walk σ | η's age-sex profile is a random walk over G and is another front's ground; a race axis needs it; the SUS product holds 2021-23 only (ADR-0020) |
