# Recollection: what the earlier attempts wanted, found and got wrong

**Written 2026-09-30, before the redesign.** This is an inventory for the
design discussion. It adopts nothing. The author's instruction: PegaSUS is
redesigned from first principles; the earlier versions are not to be stitched
into an architecture.

**How it was gathered.**
- **Read in full for this document, marked [read]:**
  - `plan_pegasus.md` (April), §1–3, §11–13, §16–30;
  - `DISCOVERY_ENGINE_NORTH_STAR.md`;
  - `FINDING_ONTOLOGY.md`;
  - brepi's `epi-db-research` skill.
- **Surveyed by read-only agents, marked [survey]:**
  - both repositories;
  - `LDO_DECONFOUNDING_DESIGN.md`;
  - the GPU and modularisation critiques.
- **Extracted by agents, not yet read by me:** the two math critiques
  (`docs/digests/`). They are the deepest statistical material (OPEN_QUESTIONS
  Q13).

---

## 1. The attempts, in order

| when | where | what it was | size |
|---|---|---|---|
| 2026-04-03 → 04-19 | `C:\Users\Galaxy\LEVI\projects\PegaSUS` (`plan_pegasus.md`, `plan_pegasus_data.md`) | The theory: a "disease-agnostic, code-aware, support-aware, hierarchical epidemiological discovery engine", and a data substrate (FTP scan → families → profiling → a compact translation grammar; SIDRA metadata) | 6 commits, 146 MB |
| April–May | `projects/miniPegaSUS`, `projects/datasus_compendium_builder` | Catalogue attempts: a DATASUS+SIDRA "data substrate compendium"; a one-shot FTP compendium builder (SQLite), whose output brepi later used | — |
| 2026-05-31 → 07-13 | `C:\Users\Galaxy\LEVI\PegaSUS` | The engine: DATASUS via an R `microdatasus` bridge, SIDRA client, a population tensor, the "EFG" compiler, the "LDO" dependence engine (sparse + low-rank precision, HSIC, LiNGAM), six finding lenses, and ~30 self-critique documents | 558 commits, 298 modules, 191 test files; halted the day its governing "north star" was written |
| 2026-07 → 09 | `C:\Users\Galaxy\Downloads\pesquisa_leptospirose_hemomais_g1\brepi` | A study workbench: leptospirosis (now in peer review at RESS, RESS-2026-1462) and GLP-1 dispensing (manuscript drafted); non-DATASUS adapters; R modelling engines; an operating discipline for study work | 81 commits, ~14 GB with data |
| 2026-06 → | `projects/front_pegasus` | A frontend prototype (simulated values) | — |
| 2026-08 → | `projects/pegasus_data` | The data gateway: whole DATASUS tree catalogued, decoded, labelled with validity windows, record linkage, HTTP API | live |

---

## 2. What the author wanted, in their own framings over time

- **April [read]:** "a governed search problem over a latent high-dimensional
  state space". PegaSUS acts as a "lazy hierarchical materializer" that never
  builds the full municipality × year × everything table: it compiles typed
  observables and "descends only where signal survives" (`plan_pegasus.md`
  §1, §3).
- **July [read]:** "a deterministic epidemiological discovery engine". Its job
  is to reveal "fine-grained, in-data, scope-typed, bias-instrumented
  association *leads*" for a human to investigate. It is explicitly "not an
  inference engine that produces epidemiological conclusions"
  (`DISCOVERY_ENGINE_NORTH_STAR.md` §1).
- **brepi [survey]:** a quick harness for studies done directly with an agent,
  where the operating discipline mattered more than the code.
- **Now (2026-09-30, to the author's own words):**
  - "reduce epidemiology to a statistical problem": given data aggregated on
    a geo × time table, find and reveal all kinds of "ecological links";
  - AI agents that investigate the data in a loop until they conclude, and
    collect the result in a report, single-threaded;
  - pegasus_data as the general gateway (DATASUS, IBGE/SIDRA, DEMAS and
    others).

**What changed between framings.**
- **April and "now":** find links.
- **July:** retreated to leads, after meeting the identification wall (§3.1).
- **brepi:** produced finished, reviewed studies without any engine.

The redesign has to decide what PegaSUS produces: links, leads, studies, or a
path from one to the next (OPEN_QUESTIONS Q1).

---

## 3. Problems the earlier attempts named

### 3.1 Statistical and epistemic

| problem | where named | what was found |
|---|---|---|
| **The identification wall.** Observational dependence identifies a skeleton, not causal direction or confounding; a Markov-equivalence class gives identical correlations. "A bigger, more general LDO can never buy Level 2 or Level 3." | north star §2 [read] | Stated as settled. It is why the April ambition, "make it general and bias evaporates", was renounced. |
| **Three levels:** dependence (automatable), effect estimation (a contrast of `E[Y∣X,Z]`, automatable as triage), causal effect (not automatable) | north star §2 [read] | A clean vocabulary for what a machine may claim. |
| **Grain:** the ecological fallacy and MAUP. DATASUS is individual-record microdata, projected down to a panel "by mistake". | north star §4 [read]; LDO residual coarsening "inflates cross-variable dependence (MAUP)" [survey] | The largest bias lever is the individual or linked grain, not a more general aggregate model. pegasus_data now provides both: records via `query()`, linked cohorts via `link()`. |
| **Multiplicity and forking paths.** Per-producer FDR existed; global control did not. A cascade of follow-up tests is "a false-story generator". | north star §6 [read]; `plan_pegasus.md` §20 (ICD descent multiplies tests) [read] | Remedies proposed, not built: pre-specified gatekeeping (Bretz–Maurer), hierarchical FDR, TreeBH for code trees. |
| **Common-size effects and broad confounding** | April §18.2, §22.1-A [read]; deconfounding design [survey] | Raw counts rediscover population size; typed rates were necessary. See §5 for what was measured. |
| **Spatial and temporal dependence:** effective sample size | [survey] | n_eff was deflated by Moran's I, but six divergent Moran implementations made the correction depend on the code path (modularisation critique M1). |
| **Small-area instability, sparse denominators** | April §13.3, §22.1-E [read] | Naive refinement "chases noisy small children"; it needs shrinkage and penalties. |
| **Support role** (residence vs occurrence) | April §6, §22.1-C [read] | "Changes patterns substantially" for admissions and deaths. |
| **Contextual clone vs latent lift:** a coarse value copied to fine units is not a disaggregated estimate | April §11, §22.1-D [read] | Four operators: extensive pushforward, intensive (exposure-weighted) aggregation, contextual clone, latent lift with uncertainty. |
| **Annotation vs partition:** repeated code slots are not partitions | April §22.1-B [read] | Diagnoses in several positions must not be summed as if exclusive. |
| **Measurement error in recorded attributes** (race: administrative vs self-declared) | north star §7 [read]; `measurement/race_ecological.py` [survey] | A hierarchical-Poisson deconvolution was built and validated, never wired. At the linked grain the disagreement becomes observable. |
| **Mixed data types** (counts, rates, proportions, thresholds, continuous context) | April §18.4 [read] | A Gaussian graph is inadequate; mixed or semiparametric exponential-family graphical models were suggested. |
| **Honest outputs:** what an engine should attach to a signal | north star §5 [read] | E-values, negative controls, collider and mediator refusal, reliability, scale sensitivity. |

### 3.2 Engineering (the May–July engine)

- **Memory walls, found one at a time** (`ARCHITECTURAL_DEBT.md` AD-2)
  [survey]. The national combine needed ~25 GB, the profiler 22.7 GB and the
  panel assembly 21.8 GB. The HSIC kernel cache would have needed ~48–107 GB,
  so it was coarsened to ≤702 cells, which degraded the analysis rather than
  fixing it.
- **Dense operators where the true one is sparse or low-rank** [survey]:
  - a P×P migration Hessian, capped at 8,000 pairs;
  - n×n kernels;
  - ~19,000 dense eigendecompositions per national run, cold-started ~20 times.
  
  Lesson from the critique: an OOM cap means the operator has the wrong
  shape.
- **The GPU was never used** [survey]. The installed torch was CPU-only, so
  every GPU path silently ran on the CPU. The hardware: an RTX 4050 laptop GPU
  with 6 GB, and 32 GB of RAM.
- **Canonical versus live** [survey]. The tested "canonical" implementation
  was often orphaned while an untested inline copy ran (Moran's I, the n_eff
  state classifier). A per-cell reliability tensor was built and threaded
  everywhere, and the estimator ignored it (CONTRACT-01). 215 of 676 `__all__`
  symbols had no caller.
- **Unwired work** [survey]: built but not connected — race correction,
  effect modification until late, the DiD rung, three population solvers.
- **Fragile acquisition** [survey]. An R-subprocess bridge
  (`microdatasus`) could not survive the agent's background execution on
  Windows; the national SIM fetch had to run in a manual terminal.
- **Agglutination across sessions** [survey]. brepi's GLP-1 study rebuilt its
  own spatial, negative-binomial, HTTP and path helpers beside the shared
  ones.

---

## 4. Ideas worth knowing (none adopted)

| idea | origin | state |
|---|---|---|
| Typed observables, a support algebra (four operators), a code algebra (roll-up, descent, linked code search) | April §8–12 [read] | theory; synthetic POCs "survived" (§22) |
| Code-role ontology: a code's role (cause, diagnosis, anomaly) is part of its identity | April §7 [read] | theory |
| An active frontier and a refinement grammar (support × code × subgroup × clinical × measure × lag), with a search objective trading stability, localisation and specificity against complexity, uncertainty and multiplicity | April §17–21 [read] | theory |
| Sparse + low-rank precision (latent confounders as the low-rank part), mixed graphical models, count autoregression (PARX), multivariate and graph scan statistics, tree FDR | April §18–20, §23 [read] | literature map; sparse + low-rank was built (LDO) |
| The finding ontology: WHERE (clusters, gradient, range), WHEN (trend, change point, outbreak, seasonality), WHO (concentration, disparity), HOW IT MOVES (emergence, diffusion, space-time interaction), WHAT CO-OCCURS (dependence, co-location, lead-lag, spillover), CONTEXT (effect modification), WHY (orientation, exposure-response) | `FINDING_ONTOLOGY.md` §2 [read] | six lenses built and run on Alagoas (114+ findings) |
| A finding as a departure from a type-appropriate null; `⟨structure, grain, instrumentation⟩` | ontology §1, north star §3 [read] | proposed |
| Fusion of findings into phenomena, triggered follow-up, a synthesis graph, with gatekeeping built alongside | north star §6 [read] | speculative |
| The argument chain (claim, evidence, strength, objection, answer), plausibility gate, threat ledger, thread-following rule, statistical grammar, definition of done, one thesis with one methodological "moat" | brepi skill [read] | used to produce a paper now in peer review |
| Claim ledger and result assertions: the manuscript's numbers are checked against the result files | brepi `audit_claims.py`, `RESULT_ASSERTIONS.yaml` [survey] | used |
| Transform after aggregate (never sum a rate or a transform) | brepi `panel/aggregate.py` [survey] | used; caught a real bug |
| Versioned geography as transfer algebra (extensive, intensive, rate operators with conservation) | brepi `geo/transfer.py`, ADR-001 [survey] | used |
| Denominators by raking census seeds to official margins; a population tensor solved from census + vital events + migration | brepi `denominators/` [survey]; PegaSUS `denominators/` (146M-row tensor) [survey] | both built |
| Modelling engines: DLNM, BYM2/INLA space-time, staggered DiD, ascertainment models, declarative robustness batteries, a fit-execution harness with time and memory budgets | brepi `R/02–13` [survey] | used in the leptospirosis paper |
| "Source-coding conventions are data, not truth" (COBRADE filing choices changed the 2024 RS flood from 467 to 47 municipalities) | brepi `DATA.md` [survey] | lesson |

---

## 5. Things that were measured, not argued

- **The spurious national dependence "near-clique"** (~7,000–9,000 edges among
  ~136 variables) was mostly a degenerate-sampling bug [survey]:
  - complete-case variable selection collapsed the sample to ~145 cells;
  - the resulting singleton fixed-effect groups pinned the normalized HSIC at
    1.0.
- **The effect-size floor was the strongest single lever** (696 → 84 edges).
  The deconfounding projections added nothing beyond two-way fixed effects on
  real data (a negative result).
- **The highest-scoring links were mechanical, not epidemiological:** shared
  denominators, nested disease definitions (Dengue ⊂ Arbovirus), duplicated
  strata. Credibility was non-monotone in effect size. After provenance-aware
  pruning, SP cross-domain data gave 62 edges, 22 certified, judged
  epidemiological.
- **Synthetic proofs of concept (April §22) [read]:**
  - typed measures were necessary;
  - support role mattered;
  - the compilation layers survived a realistic syphilis + Zika scenario;
  - "the global scanner is still the bottleneck".
- **brepi facts [survey]:**
  - PNSB's "declared leptospirosis" contradicts SINAN: 111 of 197
    municipalities reported zero cases.
  - SNGPC dispensing is located at the pharmacy, not the patient.
  - The raked 2022 denominator runs 3.9% above the census count, deliberately.

---

## 6. What was actually delivered

| deliverable | from | state |
|---|---|---|
| Leptospirosis in Brazil, 2007–2025: case fatality varies 6.3-fold across territories mostly through ascertainment | brepi | in peer review, RESS-2026-1462 |
| GLP-1 dispensing, municipal correlates (SNGPC) | brepi | manuscript drafted |
| Pancreatic cancer (C25), national | PegaSUS `studies/pancreatic_c25_national/` | report |
| Alagoas findings run (114+ typed findings) | PegaSUS | engineering validation |
| SIAC Mulher 2026 abstracts | this repository, `studies/siac_mulher_2026/` | in progress |

Every delivered study came from an analyst and an agent with a discipline,
not from an engine.

---

## 7. Data sources seen across the attempts

| source | used by | where it exists today |
|---|---|---|
| DATASUS (all systems), record linkage | all | pegasus_data (the whole tree, labels, linkage) |
| IBGE population | PegaSUS (tensor), brepi (raking), pegasus_data (IBGE series) | three methods in three repositories |
| SIDRA (census, PAM/PPM, PNSB, favela block, GDP, sanitation) | PegaSUS (`sidra/`, 94-table compendium), brepi (`sources/sidra`, `SIDRA_COMPENDIUM.md`) | not in pegasus_data |
| DEMAS / OpenDataSUS | pegasus_data (partly) | pegasus_data |
| Climate: BR-DWGD, ERA5-Land, ENSO | brepi | brepi only |
| Disasters (S2iD / Atlas, COBRADE) | brepi | brepi only |
| ANS, REGIC, SNGPC | brepi (GLP-1) | brepi only |
| MapBiomas, ANA, CEMADEN | brepi (planned, not acquired) | none |

---

## 8. How the way of working went wrong, in the attempts' own words

- **Planning.** Architecture was planned before the purpose was settled. The
  north star corrected the purpose on the last day of work.
- **Scope.** The scope was decided up front: brepi's four-paper design was
  scrapped for one thesis (2026-08-14).
- **The engine.** Optimising it came before knowing whether its outputs were
  epidemiology: 30 self-critiques, GPU plans on a CPU-only install.
- **Duplication.** The same function was reimplemented across sessions and
  modules, with no rule that the existing one be found first.
- **Testing and documentation.** Tests passed while the live path diverged
  from the tested one. Documents multiplied: about 40 loose Markdown files at
  the root of the May–July repository.

pegasus_data's own discipline (live verification, one document per purpose,
ADRs with evidence, replace rather than build beside) was written in response
to these.
