# Recollection: what PegaSUS was, in its own documents

**Rewritten 2026-09-30.** The first version, written the same morning, recorded
the April plan and the July north star and missed almost everything between
them: the May formalisation, the three Master System Documents, the
Conceptual Foundations, the mathematics of every subsystem, and the July
reckoning. The author pointed this out ("You have not recollect any of the
actual major concepts and investments of pegasus"). This version replaces it.

**It is an inventory, not a design.** PegaSUS will be redesigned from first
principles (author, 2026-09-30); nothing here is adopted by being recorded.
Where a document's claim was later shown wrong, both are given.

**Sources.** Read in full for this document, or extracted in full by agents
whose digests are in `docs/digests/` (their source lists are in each file):

| corpus | where | read as |
|---|---|---|
| `plan_pegasus.md`, `plan_pegasus_data.md` (April) | `LEVI/projects/PegaSUS/` | read |
| `PegaSUS.docx`, `PegaSUS_PIBITI.docx`, `Planos_PegaSUS_PIBITI.docx` (25 May) | `Downloads/` | read |
| the formalisation dialogues and the memorandum (28–30 May) | `Downloads/` | digest `may_formalization_extraction.md` |
| `miniPegaSUS_v0.9.md` (30 May) | `Downloads/` | structure read; content via the digest |
| `PegaSUS_MSD.md` (12 June, 6,789 lines) | `LEVI/` | structure read |
| MSD-I (7,015 lines), MSD-II, MSD-III, Addendum, Disease Semantic Axis, the plans, roadmaps, handoffs | `LEVI/PegaSUS/` | digests `plans_and_addenda_extraction.md`, `audits_and_compliance_extraction.md`; MSD-III §0, III, IV, IX, XI.4, XII read directly |
| `PEGASUS_CONCEPTUAL_FOUNDATIONS.md` (3 July) | `Downloads/` | read |
| the math critique (1,505 lines, 165 findings) and its steelman (1,288 lines) | `LEVI/PegaSUS/` | digests `math_critique_extraction.md`, `math_critique_steelman_extraction.md` |
| north star, finding ontology, deconfounding design, residual-artefact handoff (11–13 July) | `LEVI/PegaSUS/docs/architecture/` | read or digested |
| brepi | `Downloads/pesquisa_leptospirose_hemomais_g1/brepi` | surveyed |

Section references in this file (§x.y, MSD-I §2.8, …) point into those
documents, not into this one, unless they say "here".

---

## 1. The lineage at a glance

| dates | artefact | what it was | size |
|---|---|---|---|
| 3–19 Apr | `projects/PegaSUS`: `plan_pegasus.md`, `plan_pegasus_data.md` | The first theory: a "governed search problem over a latent high-dimensional state space"; a data substrate plan (FTP scan → families → profiling → translation grammar) | 6 commits |
| Apr–May | `projects/miniPegaSUS`, `projects/datasus_compendium_builder` | Catalogue attempts (a DATASUS+SIDRA compendium; a one-shot FTP compendium in SQLite, later used by brepi) | — |
| 25 May | `PegaSUS.docx`, the PIBITI grant and work plans | The public framing: a "radar epidemiológico computacional" in five layers; the dengue case study for the grant | 3 documents |
| 28–30 May | five conversations with Gemini and GPT; the memorandum thesis v0.1; the miniPegaSUS discussion | The formalisation: Problems 1, 2 and 3; measure algebra; the HSIC scanner; data sovereignty; the intent object | ~5 documents |
| 30 May | `miniPegaSUS_v0.9.md` | A production contract (743 lines) for a bounded version | 1 document |
| 31 May → 13 Jul | `LEVI/PegaSUS` (the engine) | 558 commits, ~300 modules, ~190 test files, ~40 root documents | code + docs |
| 12 Jun | `PegaSUS_MSD.md` | The first Master System Document (SHE, EFG, race bridge, PIRS) | 6,789 lines |
| 26 Jun | Compliance & Remediation report | "The system validates far more than it computes" | 530 lines |
| 30 Jun – 4 Jul | MSD-I (7,015 lines), Architecture Addendum, MSD-II, Conceptual Foundations, MSD-III, Disease Semantic Axis, Operational Implementation Plan | The mature specification: the LDO replaces PIRS | ~10,000 lines |
| 5–9 Jul | Refactor master plan, architecture and completeness audits, math/GPU/modularisation critiques, redesign and completion roadmaps, issue ledger, handoffs | The reckoning | ~20 documents |
| 11–13 Jul | National C25 run; residual-artefact handoff; deconfounding design; finding ontology; north star | Diagnosis of the national output; the retreat from "links" to "leads"; the project halts | 5 documents |
| Jul → Sep | brepi | Studies done with an agent and a discipline, no engine; the leptospirosis paper (in review, RESS-2026-1462) | 81 commits |
| Aug → | pegasus_data | The data gateway (brief of 23 Aug) | live |

---

## 2. The pivots, in order

Each pivot is a change of mind recorded in the documents, with what caused it.

1. **Search engine → typed compiler (April).** April framed PegaSUS as a lazy
   hierarchical materialiser that "descends only where signal survives". Its
   own synthetic proofs of concept (§22) concluded that the typed-observable
   and compilation layers held and "the global scanner is still the
   bottleneck".
2. **Tables → typed measures (May).** `PegaSUS.docx`: a rate is the density of
   an event measure against an exposure measure (Radon–Nikodym), not a
   division of two columns; residence and occurrence are different maps.
3. **Architecture chat → a mathematical question (28 May).** The author
   rejected Gemini's first answers three times as architecture, vagueness and
   "alphabet soup", and forced the question down to: "what beyond linear
   correlation captures nonlinear dependence?", then posed the two founding
   questions (variable generation; tracking every kind of relation).
4. **"Causal ecological network" → "typed graph of conditional nonlinear
   association hypotheses" (GPT's review).** The single most reinforced
   correction of the whole corpus. Every later document repeats it.
5. **Problem 3 is born (GPT's review, then the author).** The copula's
   weakness on ties and zeros led the author to name latent reconstruction as
   its own problem, executed first: pipeline order 3 → 1 → 2.
6. **Reconstruction → data sovereignty (Gemini 2).** The author rejected any
   framing that remodels official data: "official data is an immutable
   physical constraint; the math exists solely to estimate the unobserved
   spaces". DATASUS itself is not reconstructed.
7. **One universal reconstruction model → table-class engines (Gemini 2).**
   The author called the dynamic factor model as a universal solution
   "superficial, lazy and pedestrian". Result: an Interpolation Horizon rule
   and bespoke engines per table class (§4.4 here).
8. **Recipe registry → autonomous DAG from seeds (miniPegaSUS).** The author
   rejected a user-authored recipe registry as a "dissonant, useless,
   emasculated system": stratification by age, sex and race is always
   generated; the user states scope and intent, never formulas.
9. **HSIC as engine → multivariate model first, HSIC on residuals
   (miniPegaSUS, then MSD-II/III).** In the mini branch the negative-binomial
   GLM became Problem 2's primary engine; in MSD-II/III a single joint
   precision model (the LDO) replaced the per-outcome scanner (PIRS), and HSIC
   became "the residual detector, not the engine".
10. **Rates as variables → measured-quantity objects (Conceptual
    Foundations).** The EFG should emit count + exposure + offset semantics,
    not finished rates, because "normalization belongs in the model, not in a
    pre-built variable".
11. **Interpolation → a process model for population (Conceptual
    Foundations).** Population is a conserved stock, the integral of flows;
    interpolating each cell independently can produce demographically
    impossible trajectories.
12. **Everything dense → only stocks, denominators and outcomes are made
    dynamic (Conceptual Foundations, MSD-III §III.2).** Fields stay at native
    resolution; their staleness becomes growing uncertainty.
13. **Source hierarchy → link-type taxonomy (Conceptual Foundations §9).**
    "Epidemiology" is a view over the discovered structure (edges touching a
    health flow), not a restriction on the engine.
14. **Coarse screening → bounded exhaustiveness (Conceptual Foundations §15–16,
    MSD-III Part VIII).** Screen on heterogeneity, audit pruned branches at
    random, record unsearched regions.
15. **Specification as authority → "the MSDs are fallible theory" (Redesign
    Roadmap, 7 July).** After the math critique: "No live study runs until
    Tier-0 is closed".
16. **Race correction per record → ecological deconvolution (Completion
    Roadmap, 9 July).** Individual reclassification is unidentifiable; the
    aggregate discrepancy is identifiable.
17. **"All closed" → 9 of 45 (LDO completeness audit, 6–7 July).** A 20-agent
    re-verification overturned the build wave's own completion claim.
18. **GPU hope → measured (9 July).** The batched GPU eigensolver was
    profiled before building: realistic gain ~1.7–2×, not built.
19. **Discovery engine → lead engine (north star, 13 July).** "Not an
    inference engine that produces epidemiological conclusions". The project
    stopped the same day.
20. **Engine → studies → gateway (August–September).** brepi produced
    finished studies without an engine; pegasus_data took over the data plane.

---

## 3. The founding questions, as the author put them

- 28 May, verbatim: "1. we want a general algebraic framework to deduce and
  infer actual epidemiological quantities... 2. we have now the actual end
  goal: given all this data and variables, how can we actually track the many
  kinds of statistical relationships that may arise..."
- The same day: "can we, by means of category theory, measure algebra and
  general mathematics, reliably reconstruct and synthetize epidemiological
  variables, indicators and other constructs in a systematic, reliable way with
  minimal manual input and configuration?"
- On automation (miniPegaSUS): the system must not require the user to
  "babysit the architecture and defined entire type dictionaries, mathematical
  routines and statistical recipes"; the DAG "can be seriously weaponized to
  automate epidemiological analyses".
- The memorandum's own conclusion: PegaSUS "relocates human judgment to the
  correct layer: substrate definition, type legality, concept harmonization,
  and admissibility... not a black-box AI epidemiologist. It is a
  mathematically disciplined ecological field engine."
- MSD-III §0.2: "PegaSUS is an engine that automates epidemiological
  discovery." It is "not a causal oracle, a query-per-analysis tool, or a
  health-data-only system".
- North star §1 (13 July): "a deterministic epidemiological discovery engine"
  whose job is to reveal "fine-grained, in-data, scope-typed,
  bias-instrumented association *leads*".
- Now (30 September, the author): "reduce epidemiology to a statistical
  problem"; find and reveal "ecological links" in data aggregated on
  geography × time; AI agents investigating in a single-threaded loop;
  pegasus_data as the general gateway.

---

## 4. The mathematics, by object

Each subsection gives the object, how it evolved, what was built, and what
was found wrong with it.

### 4.1 The lattice and the typed field

- **Lattice.** `L = S × T (× A)`: places, times and strata (age, sex, race,
  code class). The memorandum's map chain: raw `𝓡` → admissible base fields
  `𝓑` (Problem 3) → typed variable universe `𝓥` (Problem 1) → association
  graph `𝓖` (Problem 2).
- **Geography modes (MSD-I).** Native, AMC (minimum comparable areas, frozen
  across municipal splits and merges), a gene-allocation mode and a hybrid.
  The AMC crosswalk used nationally was Ehrl/Moser: 5,577 municipalities →
  3,830 groups (Operational Plan, FAL-POP-AMC).
- **Type signature.** Grew from Gemini's two-field tuple (topology ∈
  {extensive, intensive}, domain ∈ a small integer taxonomy) to the
  memorandum's seven parts: kind, carrier, unit, support, aggregation law,
  role, provenance. MSD-I made it node metadata `Γ(v)` with carrier and unit
  ontologies, aggregation laws and a provenance algebra.
- **Ontological kind (Conceptual Foundations).** Every quantity is a
  **flow** (events: a point process integrated over a cell gives a count), a
  **stock** (a level linked to flows by accounting: population) or a
  **field** (a property of place-time: sanitation, income). "Format is
  interchangeable; ontology is not": any source is expressible as a cube
  `(measure, axes, categories, values)`, but the cube cannot tell a count from
  a level, so `kind` must be declared. It was the tag the code never had
  (DATASUS and SIDRA lived in two registry worlds).
- **Three axis kinds (Disease Semantic Axis §2).** Support (geography, time),
  stratification (age, sex, race), and variable identity (ICD code,
  procedure). Treating ICD as a support axis was called a type error.

### 4.2 Problem 1: the measure algebra and the variable DAG

- **Measures.** Additive cubes are finite measures over the σ-algebra of
  lattice cells: event measures `ν` (deaths, admissions) and reference
  measures `μ` (population, area). Only additive cubes are measures;
  percentages, medians and rates are statistical functionals with other
  aggregation laws (GPT's correction; became base measures vs base densities).
- **Operators.**
  - Restriction `ν|_B` (a slice: a cause, a cohort).
  - Pushforward `π_*ν` (roll-up; valid only on measures).
  - Pullback `π*` (broadcast a coarse field to a fine support). It cannot
    manufacture a fine denominator without a supplied allocation kernel;
    that is Problem 3's job.
  - Radon–Nikodym density `dν/dμ` (the rate). Exists iff `ν ≪ μ`. Absolute
    continuity is a definability condition ("no events where exposure is
    zero"), never a causal claim. Direction: events over exposure (Gemini had
    it reversed; GPT's highest-severity correction). Align first, divide
    second: push both to a common support before dividing.
  - Pointwise composition of intensive quantities (composite indices).
  - Marked point-process functionals `Ψ` (mean, median, proportion of a
    record mark: age, birth weight, length of stay, reporting delay). Legal on
    metric, ordinal and binary marks; illegal on identifiers and codes.
  - MSD-I's registry added `σ_C` (cause restriction), `Std_W` (direct
    standardisation), `Bridge` (the measurement bridges) and more.
- **Legality.** A dimensional/denominator-compatibility predicate: congenital
  anomalies over live births, not total population; deaths over GDP
  non-canonical. MSD-I §3.8: a seven-part structural legality predicate `Δ`
  plus a declaration gate (a race-stratified numerator needs a
  race-consistent denominator declared before division).
- **The DAG.** Gemini called it a Measure DAG with measure nodes and density
  nodes. GPT recast it as a typed, depth-bounded term algebra, acyclic by
  construction, not a causal graph. MSD-I named it the EFG (Epidemiological
  Field Graph), seeded by a core registry (`V_M` mortality, `V_H`
  hospitalisation, `V_B` births, `V_C` maternal-child, `V_K` capacity, `V_O`
  observer process, `V_X` context).
- **Canonical core vs exploratory space.** Standard indicators (incidence by
  age, sex and race) are generated always and are immune to pruning; the
  combinatorial rest is explored and pruned. It recurs in every document.
- **Node life cycle.** The author forced a tri-state (alive, quarantined,
  pruned) instead of keep/delete, so that an outbreak is never deleted as
  noise. Three defences:
  - relative, inherited-variance bounds instead of absolute thresholds;
  - an institutional-signature check (administrative failures hit every
    measure of a facility at once; epidemics are carrier-specific);
  - a spatial-coherence bailout by Moran's I (epidemics cluster; glitches look
    like white noise).
  
  Quarantined nodes form an "anomaly sub-graph", itself an audit of DATASUS
  reporting. A quarantine is global over a field's support, never a hole
  punched for one city. miniPegaSUS added a *forced* state: the user may force
  an unstable stratum (indigenous-specific rates), and the warning stays in
  the output.
- **Equivalence collapse** of near-duplicate variables: deferred to the end,
  once, right before the scanner (the author: "marginal X might behave
  completely differently than its parent"), and non-destructive (GPT).
- **Semantic entropy.** A soft penalty on composite variables that mix many
  domains.
- **Generation policy.** Deterministic grammar for a wide, interpretable
  dictionary, then a stochastic sparsifier. Pure representation learning was
  rejected: "you cannot write legislation based on a learned latent vector".
- **miniPegaSUS's intent object.** `ℐ = (geography, period, health realms,
  mandatory seeds, per-source priority weights w, context policy, compute
  budget, objective, force policy)`. Expansion utility:
  `U_ℐ(v) = α₁·canonicality + α₂·relevance + α₃·source priority +
  α₄·cross-system bridge value + α₅·statistical support − α₆·complexity −
  α₇·compute cost`; a node expands if `U_ℐ(v) ≥ θ_budget` or it is forced or
  seeded. MSD-I §3.14 fixed a utility score with weights
  `α = (10, 5, 3, 4, 2, 1.5, 0.5)`.
- **Cross-system bridges.** The DAG's "core operational role" (author): weave
  variables across SIM, SIH, SINASC, CNES and SIDRA. MSD-I specified eleven
  bridge grammars.
- **The reconception (Conceptual Foundations §5–6, MSD-III §II.3).** A
  count's variance is tied to its mean; a pre-divided rate loses the variance
  structure, the exposure weighting and the handling of zeros. The right
  model is `log E[deaths] = log(population) + α + structure`, where the rate
  is implied, not fed. So the EFG's terminal output became a
  `MeasuredQuantity(numerator_count, exposure, offset_semantics, structure,
  provenance, uncertainty)`. What the EFG is *for*: a type checker for
  epidemiological quantities, provenance, and a construction grammar.
- **Known defect (math critique ALGEBRA-CLOSURE-DIV-01).** The algebra was not
  closed: a rate could never again be a numerator or denominator, so the SMR
  (a ratio of ratios) was unconstructible, and no interaction operator
  existed.

### 4.3 The state tensor Q(v): what a field knows about its own reliability

- **Conception (Gemini, May).** Spatial Shannon entropy, CV, global Moran's I,
  temporal total variation. Delta-method prediction of a child node's CV from
  its parents' before computing it; support-intersection entropy for
  sparsity. Both were used as halting conditions.
- **The author's correction.** No domain expectations ("macro data can't be
  volatile" is bias smuggled in); purely statistical noise bounds.
- **MSD-I §3.12.** Fourteen components, including:
  - `n_eff = Kish(w) · 1/(1 + max(0, Moran's I))`;
  - denominator fragility (share of cells with expected count below
    `μ_min = 50`);
  - CV, spatial entropy, temporal roughness (second difference);
  - zero inflation, missingness, provenance risk.
  
  Classification: verified, fragile, quarantined (thresholds: `n_eff` 100/30,
  fragility 0.05/0.20, missingness 0.10, risk 0.5).
- **What the critique found.**
  - The live `n_eff` used the rate *values* as Kish weights, so the smallest,
    noisiest cells dominated (NEFF-KISH-WEIGHT-01, ranked the first critical
    finding: "fix first").
  - Moran's I in one path used the 1-D order of tensor cells instead of
    geography, and elsewhere raw counts (population density, not risk).
  - The `1/(1+I)` deflation has no derivation and double-counts what the
    GMRF whitening models.
  - Fragility measured missing-denominator share; `μ_min = 50` appeared
    nowhere in the code.
  - "CV" measured cross-cell heterogeneity, not sampling CV.
  - The canonical classifier was orphaned while an inline copy ran.
  - The seven thresholds were uncalibrated cliffs.
- **The deeper finding.** The whole reliability layer was computed and then
  ignored by the estimators: the "ObservationReliability contract" gap, which
  the redesign roadmap called "the single highest-leverage redesign" (§6.2
  here).

### 4.4 Problem 3: reconstruction under sovereignty

- **Sovereignty.** Official values are never overwritten. Reconstruction fills
  what is unobserved and is typed as such (`B_official`, `B_harmonized`,
  `B_reconstructed`, `B_latent`, `B_cross-sectional`).
- **Scope, per the author.** DATASUS is record data and needs no latent
  reconstruction, except for boundary changes (AMC) and under-reporting,
  which the author assigned to scanner conditioning, not imputation. The
  burden is temporal missingness in SIDRA ("Spatially everything can be safely
  presumed to share the same geospatial lattice... our problem is strictly on
  the time axis"). Raking closes at the municipality, not at state margins.
  Monte Carlo resampling of the reconstruction was rejected as
  over-engineering.
- **The Interpolation Horizon rule (Gemini 2).**
  - A series bounded by two anchors may be interpolated.
  - A series open at one end is locked cross-sectional.
  - A single-year table is a static constraint only.
- **The Reconstruction Regime Classifier (memorandum §3; MSD-I §2.9).** Every
  table is assigned one of eight regimes: direct official, harmonise only,
  constrained denominator reconstruction, bounded interpolation,
  discrete-state reconstruction, cross-sectional only, synthetic high-risk
  flagged, do not reconstruct.
- **Engines per table class (Gemini 2):**
  1. Demography: cohort-component (Leslie) aging with census anchors, forced
     by real births and deaths, migration as the residual between projected
     and enumerated census endpoints.
  2. Money: deflation by IPCA, a unit harmonisation, not inference.
  3. Infrastructure (water, sewerage): a hidden Markov / Markov-jump model
     with discrete states, because a network is not "30% built".
  4. Vital-statistics delay: right-truncation nowcasting from
     DIFDATA/DTRECEBIM, without inflating raw counts.
  5. Continuous sociological series: a spatio-temporal dynamic factor model
     (ST-DFM: `X_{s,t} = Λ F_{s,t} + ε`, VAR(1) factors, graph-Laplacian
     penalty on `F`, EM + Kalman smoothing), bounded by the last census.
- **ST-DFM certification (MSD-I §2.10).** Holdout MAPE, reconstruction
  variance and stability thresholds; later generalised as the CTR gate
  (§4.6 here).
- **Civil–health divergence and longitudinal stitching (MSD-I §2.11–2.12).**
  Classification projection `Π` between category vintages; bounded
  pushforward.

### 4.5 The population tensor

The most-invested single object of the lineage.

- **Object.** `P(s, t, a, x, r)`: municipality × year × age × sex × race.
- **Why a process model (Conceptual Foundations §4).** "A cohort of
  10-year-olds in 2010 *must* become the 22-year-olds of 2022"; the tensor
  forbids "demographically impossible reconstructions" and claims "a
  population trajectory that could actually have happened".
- **Loss (MSD-I §2.8).** Six terms plus closure:
  - census anchors;
  - aging (a linear cohort operator);
  - births entering age 0;
  - deaths (independent, or SIM-informed);
  - migration;
  - race composition by isometric log-ratio (ILR), because racial
    self-identification is compositional, not biological;
  - age/time smoothness (second differences).
  
  Closure to official totals (EstimaPop). Solvers: projected gradient, sparse
  block coordinate; an ADMM scaffold and a primal-dual solver specified but
  not built.
- **Two layers (Operational Plan POP-01).** Layer 1 is a closed-form
  ILR-interpolated warm start. Layer 2 is the six-term solver, which returns
  Layer 1 unchanged when the data carry no flow signal.
- **Measured.**
  - National 2022 total 203,080,756, equal to IBGE's, with marginal closure
    to 3.5e-14.
  - 99% of a loss evaluation was Python tuple boxing, not the dense math
    (finding M7).
  - The census "Sem declaração" race category had been silently dropped
    (26,775 people, 0.95% of Alagoas 2000); it was reallocated.
  - The GPU solver was bit-identical to NumPy and ~16× faster per block, but
    segfaulted in ~2 of 3 national runs (a torch–polars thread race).
  - The national build aborted at 17.4 GB during the *emit* stage, which a
    code comment claimed never materialised the frame ("the measurement
    contradicts the comment").
- **What the critique found.**
  - POP-IDENT-01, ranked the second critical finding: about 1,212 unknowns
    per locality-year pinned by one closure constraint. In non-informative
    windows the result *is* the prior, reported with a flat 0.02 uncertainty.
  - Loss weights were hand-set (anchor 10, aging 1, migration 0.1, race 0,
    smoothness 0.05).
  - Missing mortality was treated as immortality.
  - Migration was unidentified from net marginals and scaled by a
    hard-coded 1%/year gravity rate.
  - Closure by additive simplex projection instead of multiplicative raking.
  - `max_iterations = 12`.
  - Linear share interpolation where the docstring claimed cohort-component
    dynamics.
  - Tuning was scored on census-year cells, the one place that needs no
    reconstruction.
  - Recommended instead: raking closure, Rogers–Castro migration schedules,
    cohort-component interpolation, leave-one-census-out tuning.

### 4.6 The Constrained Tensor Reconstruction (CTR) kernel

- **Insight (Architecture Addendum §4).** The population tensor, age-bin
  disaggregation, synthetic context cubes and the ST-DFM are one constrained
  optimisation over a non-negative latent tensor: "the population solver is
  already 90% of a general CTR kernel".
- **Contract.** `CTRProblem(latent_shape, observations (A, y, w), anchors,
  nonnegativity, penalties, dynamics, marginals, composition)`.
- **Certification gate:**
  - holdout MAPE ≤ 0.15 (verified) or ≤ 0.35 (fragile);
  - reconstruction variance ≤ 0.25 or ≤ 0.40;
  - constraint residual within tolerance;
  - stability ≥ 0.85.
  
  Output enters only as `B_reconstructed`/`B_latent`, unsafe for dashboards
  until verified.

### 4.7 Measurement bridges: race

- **Problem.** DATASUS records race administratively, often by a third party;
  the census records self-declaration. The two diverge systematically
  (administrative records over-report white, under-report brown and black).
  Dividing one by the other is illegal without a bridge (MSD-I §4, the
  declaration gate).
- **MSD-I design.** Emission matrix `C` (P(recorded k | self-declared j)),
  posterior crosswalk `W ∝ C·π_local`, partial-identification bounds,
  forbidden labels.
- **What ran.** A fixed `C` equal to the identity or a fixture, with a uniform
  `π` fallback because the entry point never passed the local target shares
  (RACE-IDENTIFY-07). Missing race was spread 1/5 to each category,
  fabricating indigenous and Asian-Brazilian deaths (RACE-DECISION-09).
- **Redesign (Completion Roadmap §1).** The distortion is ecological, not
  individual:
  - `Y_{s,k} ~ Poisson(Σ_j C_{k|j} · λ_{s,j} · N_{s,j})`, with a shared,
    small, identity-anchored `C` identified by variation in census
    composition across cells (the King/Goodman ecological-inference
    mechanism);
  - a hybrid design: a literature prior, refined by the ecological
    likelihood;
  - a covariate-dependent form `C(x)` collapsed onto a scalar "whitening
    propensity";
  - cross-system consistency as an extra identifier.
- **Measured (planted-signal probe, 9 July).** True black mortality 1.5× white:
  - naive crosswalk: 0.91 (the differential erased and inverted);
  - model with high contextual variation: 1.49;
  - low variation: 1.30;
  - strong identity prior: 1.07;
  - two systems: 1.49.
  
  Conclusion stated: the production bridge "is not merely inert but actively
  harmful". On real Alagoas data the calibration gate refused (identifiability
  0.0015 < 0.005): calibration must be national. Region-specific `C` was
  marked data-blocked.

### 4.8 The disease semantic axis

- **Parsing (MSD-I §2.5).**
  - A six-state ICD parse.
  - A diagnostic topology: underlying cause vs mention vs associated, the SIM
    cause chain LINHAA–D as ordered, LINHAII as an unordered set.
  - A traversal gate: descend the code tree by support, not by signal.
  - Curated groups as partitions with an `OTHER` residual.
- **The axis (Disease Semantic Axis, July).** Disease becomes "the primary
  organizing axis of the LDO's variable set":
  - a Disease Concept Registry with multi-label, provenance-typed assertions
    (`exact | parent_projection | approximate | unmappable |
    source_system_specific`);
  - an ICD adapter (`simple-icd-10`, with Brazilian CID-10 authoritative;
    never coerced silently to ICD-10-CM);
  - a DiseaseGraph mirroring the spatial graph, with a `laplacian()` `L_D`;
  - embeddings (Qwen3) as a build-time search prior only, never an edge.
- **The mathematics.** `L_D` regularises `Ω_var` as the spatial Laplacian
  regularises `Σ_space⁻¹`:
  - hierarchy as a fused penalty `λ_H Σ ‖Ω_i· − Ω_j·‖²`;
  - embeddings as smoothness `λ_D tr(Ω_var L_D Ω_varᵀ)`;
  - in reconstruction, hierarchy as a hard additivity constraint.
  
  Shared-code overlap (Jaccard) must be modelled or tagged
  `mechanical_overlap`: concepts sharing codes are correlated by construction.
  The search policy: coarse pass at chapter/concept level, then expand along
  the DiseaseGraph around certified edges.
- **Found.**
  - WHO ICD-10 2019 has no A90/A91 (dengue) or U06 (Zika emergency code); a
    gap table was added (ICD library review).
  - The tree-distance prior gave dengue (A90) ↔ microcephaly (Q02) affinity 0
    and anti-coupled the flagship target (LDO-DIS-TREE-01); the issue ledger
    recorded the Q02↔A92 edge weight as 0.0.
  - The multi-label grammar was never wired, so comorbidity and the
    multi-cause chain were destroyed at ingestion (LDO-DIS-MULTICAUSE-04).
  - CCSR/CCIR are US ICD-10-CM groupers returning only the primary category.
  - Disease counts entered the LDO without exposure offsets.

### 4.9 Problem 2, first form: the kernel scanner (May)

- **HSIC.** `HSIC ∝ tr(K_X H K_Y H)`, with Gaussian Gram matrices and
  centring `H = I − 11ᵀ/n`; it detects an inverted U that Pearson misses. KSG
  mutual information was demoted because k-NN boxes degrade as the
  conditioning set grows, while HSIC's Gram trick does not (GPT: "HSIC is
  computationally elegant; it is not magic").
- **Copula normalisation** (Sklar): `U = F_X(X)`, `V = F_Y(Y)`. Flagged for
  ties, zero inflation and discrete counts; this is where Problem 3 started.
- **Conditioning.** Kernel residualisation against a nuisance kernel:
  `P_Z = I − K_Z(K_Z + εI)⁻¹K_Z`, score `tr(P_Z K_U P_Z · P_Z K_V P_Z)`.
  - `K_Z` is a single joint space-time kernel. A Hadamard (product) form
    blinds the scanner to delayed spatial diffusion (an outbreak that takes a
    year to travel), so it was changed to a Kronecker sum; GPT framed this as a
    bias–variance trade-off, not good vs bad.
  - The spatial kernel is static ("quenched"); Woodbury low-rank dynamic
    updates were rejected as unjustified.
- **Beyond pairs.** The author objected that a bivariate scanner is "a
  substantial roadblock". Answer: PC-HSIC, a cheap bivariate skeleton, then
  conditioning only on triangles. Its result is "graph deconfounding", not
  proof that an edge is spurious.
- **Nulls.** Structured block permutations (circular time shifts, spatial
  blocks, season-preserving shifts), a regime per panel type, FDR within
  hypothesis families, stability over block folds. An edge needs five things
  together: score, null significance, FDR, support, stability.
- **Division of labour.** The DAG watches each variable's own state
  (first-order anomalies); the scanner handles two or more variables. Higher
  interactions are pre-collapsed into composite variables by the DAG so the
  scanner stays pairwise.
- **The memorandum's principal claim.** Relative to a specified (substrate,
  type system, expression depth, transformation family, null model), the
  engine enumerates the legal fields and scans the admissible relations:
  "The system does not exhaust reality. It exhausts the hypotheses expressible
  inside" the class. It closed with ten open problems, the first being that
  the regime classification of all tables was not done.
- **miniPegaSUS's Problem 2.** A negative-binomial GLM with a log-population
  offset and fixed/random effects is primary; a group penalty derived from the
  domain taxonomy handles many covariates; HSIC runs only on residuals, for a
  bounded candidate set `𝒩(Y) = Expand(Y) = {x : d_Γ(x, Y) ≤ ε}` around an
  outcome. All pairs remained an "advanced mode".
- **PIRS (MSD-I §6).** The first implementation: per-outcome GLM model
  selection, spatial modes (ICAR, UF fixed effects, municipality fixed
  effects: "entirely absent" from the code per the compliance report),
  cross-fitted residuals, HSIC (exact, Nyström, random Fourier features), a
  null/FDR registry. It fragmented into a "slice zoo" of about ten
  manifest-passing modules and was deleted in July (~4,900 lines).

### 4.10 Problem 2, mature form: the LDO

The name varies: MSD-II/III say *Lattice Dependency Operator*; later documents
say *Latent Dependency Operator*.

- **Object (MSD-III §III.1).** Variables `X_1..X_p` over `S × T`, a tensor
  `X ∈ ℝ^{p×S×T}`. One structured estimate of the precision (inverse
  covariance), fitted **once**; every link is a query against it.
- **Latent field (§III.2).** Every variable is latent on the finest lattice,
  observed through a weighted observation operator. Sparsity is zero weight;
  "fabricates nothing". A variable seen once informs the cross-section and
  nothing about dynamics.
- **Multiresolution shrinkage (§III.3).** A sum of components across scales
  on every hierarchical axis (national + regional + state + municipal; chapter
  + block + category + leaf), each shrunk toward its parent. This is small-area
  estimation / BYM, with INLA/SPDE as the named engine. The coarse→fine scan is
  a posterior readout, not a prune.
- **Five structural assumptions (§III.4):**
  1. sparse (graphical lasso);
  2. low-rank shared drivers: `precision = S − L` (Chandrasekaran–Parrilo–Willsky),
     "identical in form to market-factor/idiosyncratic risk models";
  3. separable: `Ω_var ⊗ Σ_space⁻¹ ⊗ Σ_time⁻¹`;
  4. lagged: time-shifted copies, whose cross-lag entries are directed links
     and whose profile is the distributed-lag response ("the engine
     *discovers* the delay, e.g. Zika's 6–9 months");
  5. prior-regularised by `L_W` (spatial GMRF), `L_D` (disease) and temporal
     smoothness.
- **Margins (§III.5).** Rank/PIT onto a Gaussian scale; extensive quantities
  use a count-with-exposure margin (the denominator principle).
- **Residual audit (§III.6).** HSIC on the residual field, "the residual
  detector, not the engine"; it flags candidates for promotion to named terms.
- **Estimation and output (§III.7).** Penalised pseudo-likelihood (ℓ1 +
  nuclear norm + quadratic priors) by proximal gradient / ADMM; stability
  selection for multiplicity. The link record:
  `LinkRecord{source, target, lag_k, edge_type ∈ {contemporaneous,
  lagged_directed, latent_shared, nonlinear_residual, mechanical_overlap},
  weight, partial_correlation, response_curve_ref, spatial_field_ref,
  stability, uncertainty, confounding_factor_refs, projection_status,
  code_system, topology_role, overlap_jaccard, certification_status,
  warnings}`.
- **Certification (§III.8).** Holdout stability, regularisation-path
  agreement, latent-vs-lag separability diagnostics, `n_eff` and fragility
  gates. Standing aborts: a context-derived prior sharing provenance with the
  tested variables; overlap unaccounted; promotion without stability or
  uncertainty. "The LDO **produces causal hypotheses; it does not certify
  causation.**"
- **Build ledger.** The architecture audit (6 July) found Part V "~30–40%
  wired", with no stable `λ2` operating point for the S/L split. Work
  packages WP1–WP8 were declared "all closed"; the 20-agent re-verification
  found 9 of 45 gaps cleanly resolved, because the flagship national run at
  yearly resolution fell under the gate that switched multiresolution on, so
  the whole shell never ran. Remediation O1–O19 followed.

### 4.11 Causal escalation (MSD-III Part IV)

- **Rung 0:** the LDO skeleton, directed only by time. Bivariate Granger is
  "subsumed".
- **Rung 1:** orientation without experiments, only where assumptions are
  machine-checkable: v-structures (PC/GES/FCI) and non-Gaussian orientation
  (LiNGAM, additive noise).
- **Rung 2:** quasi-experiments triggered by detected structure: interrupted
  time series, difference-in-differences, negative-control outcomes.
- **Rung 3:** do-calculus, expert-invoked only.
- Every causal claim carries its rung and assumptions.
- **Found.**
  - ITS ran on the spatial mean of the Gaussianised latent, so effect sizes
    had no units (LDO-CAUSAL-ITS-GAUSS-01).
  - Pooling municipalities makes data non-Gaussian by aggregation alone, which
    "licenses" LiNGAM spuriously.
  - Colliders rest on faithfulness.
  - Conflicting v-structures were resolved last-write-wins.
  - No multiplicity control in the causal layer.
  - Rungs recorded "which estimator ran", not "which assumptions were
    verified".
  - The feature proposals had said *do not build until specified*; it was
    built anyway.

### 4.12 Compute and scale

- **Envelope.** RTX 4050 laptop GPU (6 GB), 32 GB RAM (MSD-II §II.10,
  MSD-III §V.1).
- **Levers (Conceptual Foundations §11–13, MSD-III Part V):**
  - sparsity;
  - Kronecker separability (`log det(A⊗B) = n log det A + m log det B`),
    GPyTorch as precedent;
  - randomised SVD (Halko–Martinsson–Tropp);
  - stochastic log-determinants (Hutchinson + Lanczos quadrature);
  - JL sketching;
  - streamed sufficient statistics (`XᵀX`, `Xᵀy`);
  - matrix-free preconditioned CG;
  - mixed precision with float64 reductions;
  - H-matrices as a later option;
  - the Adaptive Precision Controller: an anytime scheduler that spends
    compute where it changes conclusions.
- **The validity contract (Conceptual Foundations §14, MSD-III §V.6):**
  bounded methods only; approximation error propagated into link uncertainty;
  an exact state-scale run certifies the approximate national run where they
  overlap, and disagreement rejects loudly.
- **Measured.**
  - The GPU barely served the engine. An agent survey found the installed
    torch CPU-only, so GPU paths silently ran on the CPU. The one CUDA win
    (the population solver, 9 July) crashed nationally. A "W8 GPU done" task
    was a false completion.
  - Batched GPU eigensolvers profiled at ~1.7–2× net (eigh 6.9× alone, but
    ~60% of a fit; stability refits already parallel ~4.5× on CPU); not
    built.
  - The residual scan was memory-bandwidth bound; fixed by kernel factoring,
    16–30× faster, bit-exact.
  - National LDO: ~26 minutes, peak 18.5 GB.
  - Storage 53 → 26 GB by dropping triple serialisation.
  - The critique showed the exact-certifies-approximate check compared the
    same slice (method fidelity, not scope validity), and on the 700
    densest localities.

### 4.13 Bounded exhaustiveness (Conceptual Foundations Part VI, MSD-III Part VIII)

- **Why aggregation hides links.** Simpson's reversal, cancellation of
  opposite regional effects, thresholds, and dilution of a rare code in its
  chapter.
- **Remedy:**
  1. screen on heterogeneity, dispersion or the maximum subgroup signal, not
     the pooled mean;
  2. run full analyses on a random sample of pruned branches to estimate the
     false-negative rate;
  3. record unsearched regions in a typed coverage manifest, with the
     sparsity-of-truth assumption stated.
- **Found.**
  - The thresholds (0.15 / 0.30) were uncalibrated: with T = 15 years the
    null standard deviation of a per-unit correlation is ~0.28.
  - The coarse step mean-pooled across a state, reintroducing the Simpson
    blind spot before the screen could see it.
  - The false-negative audit was a bare point estimate on the pairs least
    likely to hold an edge.
  - The dispersion screen had no callers.
  - Conformal selection or knockoffs were recommended to turn the claim into
    a guarantee.

### 4.14 The shape of the goal (Conceptual Foundations Part IV, MSD-III §0.4, Part XII)

- **"No epidemiology left?"** No:
  - the link space is unbounded until resolution, functional form,
    conditioning set, lag and interaction order are fixed;
  - the binding limit is **information, not compute** ("A supercomputer
    would let you *compute* more candidate links; it would not make them
    *true*");
  - association is the floor of science, not its ceiling.
- **End state.** "A *living, bounded, typed associational skeleton*"
  maintained as a foundational asset, which humans and agents interrogate and
  escalate causally.
- **The Foundational Asset Layer (MSD-III Part VI).** Population tensor,
  graphs, registry and skeleton are built once at national, full-history scope
  and only sliced by queries. "Building a scope-invariant asset at reduced
  scope is a correctness bug."
- **Interaction model (MSD-III Part VII).** Five verbs: interrogate, lens,
  escalate, steer, inject.
- **Three permanent limits (MSD-III §0.4):** the information ceiling;
  association is not causation; some misclassification is unidentified
  without external data.
- **The prime directive (MSD-I §12, MSD-III §0.3):** "never replace
  mathematical legality with convenience, missingness with silence, source
  structure with scalar fiction, or measurement uncertainty with false
  precision". Its development-phase corollary: "works" is the bar; populate
  mechanisms with real, uncertainty-typed content rather than honest no-ops.

### 4.15 The north star and the finding ontology (13 July)

- **The identification wall.** Observational dependence identifies a
  skeleton, not direction or confounding: "a bigger, more general LDO can
  never buy Level 2 or Level 3".
- **Three levels:** dependence (automatable); effect estimation (a contrast of
  `E[Y|X,Z]`, automatable as triage); causal effect (not automatable).
- **Grain.** DATASUS is individual records, projected to a panel "by
  mistake"; the individual or linked grain is the largest bias lever.
- **Multiplicity.** A cascade of follow-up tests is a "false-story
  generator". Proposed: pre-specified gatekeeping (Bretz–Maurer),
  hierarchical FDR, TreeBH.
- **Honest outputs.** E-values, negative controls, collider and mediator
  refusal, reliability, scale sensitivity.
- **LLM agents** rejected for decision-making, because a fixed plan makes the
  number of tests countable.
- **Finding ontology.** A finding is a departure from a type-appropriate
  null, carrying `⟨structure, grain, instrumentation⟩`. Shapes:
  - WHERE: clusters, gradient, range;
  - WHEN: trend, change point, outbreak, seasonality;
  - WHO: concentration, disparity;
  - HOW IT MOVES: emergence, diffusion, space-time interaction;
  - WHAT CO-OCCURS: dependence, co-location, lead-lag, spillover;
  - CONTEXT: effect modification;
  - WHY: orientation, exposure-response.
  
  Six lenses were built and run on Alagoas (114+ findings).

---

## 5. Validation: designed, partly built, never run on real data

This corrects the first recollection and the first assessment, which said no
ground truth was ever considered. It was designed in detail; the real-data
part was never executed.

| what | where specified | state |
|---|---|---|
| **Program acceptance test:** monthly Alagoas, no forced selectors; must emit a `lagged_directed` link from arbovirus admissions to microcephaly, `lag_k` peaked at 6–9 months, with the 2015–16 wave as a confounding factor, stability and uncertainty. "Until it passes, MSD-III's goal is not met." | MSD-II (Zika capability, LDO-04), MSD-III §XI.4 and Appendix D | **Never written.** `tests/acceptance/` is empty. The issue ledger marks ZIKA-ACCPT *deferred*; the refactor plan says "the program's definition of done does not exist". A unit test pins only the ICD codes involved (A90/A91/U06 resolution, same-block coupling). |
| **Known-positive controls:** Zika → microcephaly, sanitation → diarrhoeal disease, vaccination → disease decline | MSD-III §IX.1, Operational Plan VAL-01 | Not built on real data |
| **Known-negative controls** and the measured false-alarm rate | MSD-III §IX.1 | Not run. A synthetic test of the Rung-2 negative-control veto exists. |
| **Synthetic ground truth:** planted edges, lags, factors; separability adequacy; certification power | MSD-III §IX.2 | **Partly built.** Planted-lag recovery (`test_ldo_lag_recovery.py`), sparse + low-rank recovery, exact-certifies-approximate and the race planted-signal probe exist. The critique found the planted-factor test used k = 3 variables at loading 0.577, above the gate that silently drops factors spread over more than ~11 variables (LDO-INCOH-07). |
| **Temporal holdout** | MSD-III §IX.3 | Built. The critique found a margin leak (training years ranked against the full axis) and no null for the persistence rate (~50% by chance). |
| **Exact vs approximate** | MSD-III §V.6, §IX.3 | Built; checks method fidelity on one dense slice, not scope validity |
| **The standing battery:** "recovers known truths; measured false-alarm rate X%; synthetic-recovery accuracy Y%; holds out-of-sample" | MSD-III §IX.4 | The sentence was never filled in |
| **PIBITI validation:** manual calculation, semantic review, retrospective comparison with bulletins | grant, May | The grant's scope; not the engine's |

The precise statement: the validation program was specified as normative and
the synthetic half was partly built. No capability was ever scored against a
known real-world answer, and the error rates the battery was to report were
never measured.

---

## 6. The reckoning (5–13 July), consolidated

### 6.1 Engineering findings

- **"The system validates far more than it computes"** (Compliance report,
  26 June). A rigorous contract tier sat over a reduced production tier:
  - the production normalisers bypassed the decoders and nulled most of the
    canonical schema (SHE-NORM-01);
  - CNES summed beds with equipment and filled missing with zero;
  - SIDRA context was acquired and never routed;
  - spatial modes were "entirely absent".
- **Orphans.** Built, tested, zero callers: LiNGAM orientation, the Adaptive
  Precision Controller, spatial whitening, the variable grammar, the `pirs/`
  package. "Existence in code ≠ use in the live path" (working principle 35).
- **Dead code is more correct than live code.** The dead `q_tensor.py`
  implemented Kish-weighted `n_eff` correctly; the live path did not.
- **The refactor** (5 July): −4,881 lines; four god-modules decomposed;
  duplicated rate construction removed from `dag.py`; the cell-index offset
  arithmetic was inlined in four places.
- **Memory walls, one at a time.** National combine ~25 GB, profiler 22.7 GB,
  panel 21.8 GB, HSIC kernels 48–107 GB (coarsened), population emit
  17.4 GB+. The lesson recorded: an out-of-memory cap means the operator has
  the wrong shape.
- **Acquisition.** The R `microdatasus` subprocess could not survive
  background execution on Windows; national SIM was fetched by hand.

### 6.2 The math critique, in one paragraph per theme

165 findings in 24 themes (critique), 20 adjudicated in full by the steelman,
which upheld 5 outright or with sharpening and found most others "mechanism
real, severity overstated". Its recurring conclusion: "the fix already exists
in the repo and is merely unwired".

- **Noise model.** A Poisson margin with one national rate `λ = Σx/ΣE` for
  every cell, although MSD-I §6.2 mandates NB/ZINB. `compute/glm.py` had
  NB, hurdle and Dunn–Smyth residuals, never imported by the LDO.
- **Reliability not consumed.** The weights `W` were propagated everywhere and
  used in no moment of the primary estimator; SEs used the raw cell count.
- **Temporal dependence.** Never whitened; the estimated `φ̂` went to
  telemetry. Stacked lag windows duplicate K of K+1 entries between adjacent
  columns. Stability selection over contiguous windows *confirms* trend
  artefacts.
- **Stationarity.** One covariance pooled over 2000–2024, dominated by the
  late, high-variance regime; no change-point logic.
- **Lagged edges.** Conditional-Granger, not causal. Pairwise lagged
  co-trends escape the low-rank part (the three-variable support gate) and
  become direct edges.
- **Smoothing on the discovery.** `γ_t = 0.1` is a random-walk prior on the
  very curve reported as discovered; the honest default `γ_t = 0` was
  overridden by the orchestrator.
- **Annual resolution.** Link records had no time unit; sub-annual delays
  alias into undirected lag 0.
- **HSIC.** In-sample residuals (double dipping), against MSD-I's own
  cross-fitting mandate. An intra-state shuffle executed while the provenance
  named the structured null. At national scale, mean-pooled residuals made
  HSIC ≈ linear correlation. A permutation floor combined with BY inflation
  made nonlinearity uncertifiable at national variable counts.
- **Multiplicity.** Stability selection without the Meinshausen–Bühlmann
  construction (0.7 subsamples, two thresholds); FDR fields plumbed and
  unused.
- **Small areas.** Direct standardisation at municipal scale where MSD-III
  §III.3 prescribes BYM/INLA. Age-unknown deaths mapped into the 0–4 stratum,
  which carries the heaviest WHO weight.
- **Recommended toolkit.** NB/ZINB margins with varying baselines; BYM2/INLA
  shrinkage before the copula; weighted moments; λ paths (StARS/eBIC);
  cross-fitted HSIC; spatial-block cyclic nulls; BY or knockoffs;
  conformal edge uncertainty; Poisson/NB ITS with Bai–Perron breaks; calibrated
  negative controls; raking; cohort-component interpolation.

The redesign roadmap's one-line thesis: "the LDO is a sophisticated engine
that currently (a) uses the wrong noise model, (b) discards the uncertainty it
computes, (c) mishandles the spatial/temporal dependence it exists to study,
and (d) gates findings on uncalibrated constants".

### 6.3 The national run and its artefact (11–12 July)

- National pancreatic cancer (C25): 7,483 edges, of which 7,197
  `nonlinear_residual`, a near-clique over 132 of 348 variables with median
  HSIC 0.006–0.009. The `mechanical_overlap` guard emitted 0.
- **First diagnosis wrong.** A "low-rank leak" was confirmed on a synthetic
  and fixed; the national clique barely moved (7,197 → 7,290). Lesson written
  down: "a synthetic that reproduces the symptom can validate the wrong
  mechanism".
- **Resolution** (GPT-5.6, then four fixes):
  - two-way fixed-effect nuisance projection;
  - a CKA effect-size floor of 0.05;
  - a degenerate complete-case sampling bug (singleton fixed-effect groups
    pinned CKA at 1.0: "the true source of the flat clique");
  - mechanical-overlap typing for a count and its own rate;
  - excluding denominators from the outcome set.
  
  Clique 1,711 → 825 → 78–139 real edges. A 43-variable cross-domain slice
  gave 62 edges, 22 certified, "all textbook epidemiology".
- **Caveats recorded.**
  - The municipality fixed effect erases cross-sectional signal, so the
    residual scan now tests only within-municipality temporal dependence.
  - The effect-size floor was the strongest lever (696 → 84 edges); the
    deconfounding projections added nothing beyond two-way fixed effects on
    real data.
  - Credibility was non-monotone in effect size: the top links were
    mechanical.
  - The national deliverable file predates every fix and was never refreshed.

---

## 7. How the work was run: the working principles

`LEVI/PegaSUS/CLAUDE.md` (8 July, 43 principles in 11 sections) was written
from these failures. Its governing sentence: "claims — in specs, docs, prior
code, or your own reasoning — are hypotheses until measured".

The ones the record shows were earned the hard way:
- **A correct prescription fails three ways:** naive implementation,
  correct-but-marginal, correct-but-wrong-layer (the low-rank-leak
  misdiagnosis).
- **A green suite does not establish mathematical correctness;** validate by
  probe and inspection.
- **Locate the phenomenon in the model before fixing it.**
- **Deflate `n_eff` with the right estimand-specific formula;** a computed but
  unused q-value protects nothing.
- **Never silently cap, truncate or degrade.**
- **Profile before optimising;** distrust resource-virtue labels until
  measured (the GPU).
- **Existence in code ≠ use in the live path;** the code is ahead of its
  record; audit your own claims (the "all closed" reversal).
- **A recurring patch implies a missing abstraction.**

The documentation index (`DOCS.md`) had to rank documents by precedence
because "the planning docs are strata deposited over time"; 57,500 lines of
"chatbot-era one-shot updater codemods" were deleted from `scripts/dev/`.

pegasus_data's discipline (live verification, one document per purpose, ADRs
with evidence, replace rather than build beside) descends from these.

---

## 8. The other half of the lineage: brepi and pegasus_data

### 8.1 brepi (July → September)

- **A study workbench:**
  - leptospirosis in Brazil 2007–2025 (case fatality varies 6.3-fold across
    territories, mostly through ascertainment; in peer review, RESS-2026-1462);
  - GLP-1 dispensing (SNGPC; manuscript drafted).
- **The discipline (`epi-db-research` skill):**
  - the argument chain (claim, evidence, strength, objection, answer);
  - a plausibility gate, a threat ledger, a thread-following rule;
  - a statistical grammar and a definition of done;
  - one thesis with one methodological "moat";
  - the manuscript's numbers checked against result files (`audit_claims.py`,
    `RESULT_ASSERTIONS.yaml`).
- **Algebra re-derived independently:**
  - transform after aggregate (never sum a rate);
  - versioned geography as a transfer algebra with extensive, intensive and
    rate operators with conservation.
  
  This matches April's support algebra and the May measure algebra.
- **Engines:** R (INLA/BYM2 space-time, DLNM, staggered DiD, ascertainment
  models, robustness batteries, a fit harness with time and memory budgets).
- **Non-DATASUS adapters:** SIDRA, climate (BR-DWGD, ERA5-Land, ENSO),
  disasters (S2iD/Atlas, COBRADE), ANS, REGIC, SNGPC.
- **Facts learned:**
  - COBRADE filing choices moved the 2024 RS flood from 467 to 47
    municipalities;
  - PNSB's declared leptospirosis contradicts SINAN (111 of 197
    municipalities with zero cases);
  - SNGPC dispensing is located at the pharmacy;
  - the raked 2022 denominator runs 3.9% above the census, deliberately.
- **Failure mode:** studies grew private copies of shared helpers.

### 8.2 pegasus_data (August →)

The whole DATASUS tree catalogued, decoded and labelled with validity
windows; record-level queries; probabilistic record linkage with measured
error. On 30 September:
- births linked to delivery admissions: 1.5 million, 0.47–0.53% chance links;
- in-hospital deaths linked to death certificates: 545,135 of 605,542, 0.23%.

It realises the individual and linked grain the north star called the
largest bias lever. It does not yet hold SIDRA, a population method, climate
or disasters.

---

## 9. What was delivered, across the lineage

| deliverable | from | state |
|---|---|---|
| Leptospirosis in Brazil, 2007–2025 | brepi | in peer review |
| GLP-1 dispensing, municipal correlates | brepi | manuscript drafted |
| National pancreatic cancer (C25) mortality run | PegaSUS | engine output; the national C25 counts matched INCA figures; the dependency file predates the artefact fixes |
| Alagoas findings run (114+ typed findings) | PegaSUS | engineering validation |
| National population tensor (2-year, census-exact) | PegaSUS | built; the 25-year national build never completed |
| SIAC Mulher 2026 abstracts (three) | pegasus_project, on pegasus_data | written 30 September |
| The data gateway | pegasus_data | live |

The studies came from an analyst and an agent working with a discipline.
The engine produced a validated data plane, a population asset and a large
body of mathematics, but no finding that was scored against a known answer.

---

## 10. Where each idea stands (for the design discussion)

No verdicts, only the state each idea was left in.

| idea | specified | built | measured on real data |
|---|---|---|---|
| Typed measures, legality, RN rates | May, MSD-I §3 | yes (EFG legality: "keep, never rewrite") | the compliance report rated it compliant |
| Measured-quantity output (count + exposure) | Conceptual Foundations, MSD-III §II.3 | partly (a sidecar, not the terminal object) | — |
| Canonical core, forced strata, quarantine | May, MSD-I §3.13 | yes | classifier orphaned until July |
| State tensor Q(v) | May, MSD-I §3.12 | yes | formulas wrong in the live path |
| Reconstruction regimes, sovereignty | May, MSD-I §2.9 | classifier yes; context never routed until late | — |
| Population tensor | May, MSD-I §2.8 | yes | 2-year national census-exact; identifiability critique unanswered |
| CTR kernel | Addendum | partly | — |
| Race ecological deconvolution | Completion Roadmap | estimator yes, not wired | synthetic only; AL refused |
| Disease axis, `L_D` | Disease Semantic Axis | yes | anti-couples the flagship target |
| HSIC scanner | May, MSD-I §6 | yes | national artefact; fixed to within-municipality temporal only |
| LDO (sparse + low-rank + lags) | MSD-II/III | yes, after WP1–8 and O1–19 | 22 certified edges on a 43-variable slice |
| Causal ladder | MSD-III Part IV | yes | critique: rungs unlicensed |
| Bounded exhaustiveness | Conceptual Foundations, MSD-III VIII | yes | thresholds uncalibrated |
| Validation battery | MSD-III Part IX | synthetic half | never on real data |
| Finding lenses | north star, ontology | six lenses | Alagoas run |
| brepi discipline | brepi | yes | produced a paper in review |
