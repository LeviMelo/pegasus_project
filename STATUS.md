# Status

**2026-10-06, evening: ARCHITECTURE revision 3** (ADR-0029). PegaSUS is six stages, one computation each (ARCHITECTURE §1.1):
- A data and meaning;
- B expectation, with its noise structure;
- C departures;
- D relations;
- E interpretation;
- F use.

Stages B–D make statistical claims only; E alone is epidemiological. The next work is **N1**, the expectation's noise structure, then N2 → O6 → O7 → O8 (ARCHITECTURE §12; `docs/plans/2026-10-06-overhaul.md`). The review behind it is `docs/discussion/2026-10-06-course-correction.md`.

**2026-10-07, roadmap revision 4:** the whole system first, end to end (ARCHITECTURE §12, S0–S7; `docs/discussion/2026-10-07-whole-system-review.md`). **S0 in progress:** the v0 survey removed (its 33,111 leads retired); method records from the harness's measurements; stage D ledgered; joint departures, alarms and map pairs are leads; the gateway the only door; the runner reframed as `update`.

**2026-10-07: real data first.** The author found the work stuck in a loop of synthetic benches built from the model's own law; methods are now judged first on documented events (ARCHITECTURE §10, CLAUDE.md design check 8).
- **The real-data baseline** (`data/real_events.py`): of five documented events, measles 2018–19, chikungunya 2016–17 and COVID-19 in the North were missed by every stage-C method. The cause was in stage B: one dispersion per chapter, and categories' levels set with their epidemic years.
- **Robust stage B** is the default (`Monolith.robust`: trimming by EM imputation, flags against a trimmed dispersion). With it, all five events are found by three methods (evaluation 2026-10-07, real events).
- **Category courses (`h_cat`) are built but not the default.** A flexible course absorbs its category's own national epidemic (measles 2018–19); a rigid one cannot follow COVID-19's arrival. The default (v9) is trimming only. Which reference a question takes belongs to the registry (evaluation 2026-10-07, robust expectation).
- **N1 re-estimated:**
  - κ by central matching of the PIT quartiles (measles κ 1000 → 20);
  - ρ, δ from winsorised lag moments with their own frailty scale (ρ was at its bound on its own worlds).
- **A finding's course in time is attributed** (`departures.attribute`, Chen & Liu 1993); the multiscale step's matches of spike events were spikes.
- **The empirical null of the multiscale peaks is per scale and absorption class.** Pooled over every contrast, it put the multiscale step's false findings in 8 of 10 null worlds; per contrast it lost COVID-19 in the North. Now 1 of 10, and all five events found (evaluations 2026-10-06 departure models, 2026-10-07 real events).
- **Built:** the question → methods registry (`questions`, `Session.ask`, `Session.survey_questions`).
- **The space of stages C–D is the graph's own:**
  - multiscale peaks on heat kernels, scored as gamma tail probits;
  - relations in graph-frequency bands on N1-whitened innovations;
  - the spectral-density factor model;
  - the care-flow graph.
  The zoning ladder survives only where its successor has not yet matched it.

**Planned and dormant** (read before choosing any front: an item here is architecture the work has not advanced; 2026-10-07):

| item (ARCHITECTURE) | built | dormant since | next concrete step |
|---|---|---|---|
| fields from pegasus_data's roles: marks, dimensions, institutions (§4.4, §4.5) | measures (count family when the domain admits 0), compositions, intervals (every date against the event's), links and other classifiers' trees (SIGTAP), all from declarations; SIH, SIM and SINASC declared | 2026-10-07 | first end-to-end readings of each kind |
| linkage and cohorts (§7.8, phase 2) | `cohort()`; linked-share fields from declared links | 2026-10-07 | sides filtered or grouped by their spec |
| race and ages (O3, §4.1) | race-aware population accounts | 2026-10-05 | race as an axis of G on births and infant deaths |
| institutions in the likelihood (§4.5) | facility triage, mark facility effects | 2026-10-05 | from the declared `institution` roles (same plan) |
| breadth: SIA/APAC, CIHA, SIGTAP (O9) | SINAN agravos fitted 2026-10-07 | 2026-10-05 | fields from roles first, then the systems |
| one model across chapters (§5.4) | not built | never started | design note |
| interaction patterns (§7.4) | interaction built, off; `scans/patterns.py` (CP-APR) with no input since the map's SIH tensor went (2026-10-07) | 2026-10-06 | read ψ, ω, τ of one block |
| exact reference fit (OPEN_QUESTIONS 2) | not run | 2026-10-06 | one block by HMC against the Laplace draws |
| the readable dossier and human verdicts (stage F) | `dossier` (HTML, series per answer), `verdict`; confirmed answers enter the event record (`harness.verdict_positives`) | 2026-10-07 | the author records verdicts on the first dossiers |
| corroboration's sources (§8.3) | derived from declarations (ICD-10-coded event types, declared links for overlap, the disasters field's ICD-10 correspondence) | 2026-10-07 | the linked overlap read on a full update |

**Where each stage stands:**

| stage | state | what is next |
|---|---|---|
| **A. Data** (pegasus_data) | SIM, SIH, SINASC and every SINAN agravo served; SINAN's notification block declared once for all 58 agravos (pegasus_data, its decision 0153). ICD structure, admissibility, the ICD-9 bridge and code lists | SIA/APAC, CIHA (O9) |
| **B. Expectation** | v1 solver; robust stage B (trimming) by default; **N1 done** (recovers its own worlds); the SINAN agravos fitted as single fields (O9, running) | **N2:** exact conditional sweeps of the levels built (SIM VII's posterior total 9.0 M → 274 against 277); SBC running |
| **C. Departures** | the questions registry (excess, step, trend, cluster, group), each answered by all its methods with agreement and shape (Chen & Liu); multiscale peaks with a null per absorption class; cell excess; every 2026-10-07 documented event found; the first question survey (SIM I, IX, X, XX; SIH I, X) running | cluster and group departure models (BYM2 exceedance, group interaction); the Bayesian step's power |
| **D. Relations** | `relations.relation_map` and `pegasus-core relations` (band factor model on N1 innovations; relations to the register); calibrated above the national scale by SIH place permutation (2.0 %) | national-scale relations (OPEN_QUESTIONS 9); SINAN agravos as cross-system positive controls |
| **E. Interpretation** | triage with rule versions, replication tiers, the facility layer; triage reads question answers; `harness.event_record` scores every method against the declared positives (`pegasus-core events`) | triage of the first question survey; rival explanations per lead (O8) |
| **F. Use** | the register; `pegasus-core report` (answers with named municipalities, methods, shapes, triage; relations; scales unanswered) | the first readable register, after the survey's triage |

**The bench** (O5, statistical characterisation of stages B–D): the grid of planted signals in refitted worlds (`harness.grid`, `pegasus-core grid`), run on SIM dense and sparse, SIH, SINASC, SINAN and monthly dengue; null worlds and negatives; SBC (`scripts/sbc.py`).

**Coverage of the architecture:** [docs/architecture_coverage.md](docs/architecture_coverage.md), item by item.

**pegasus_data is developed from this session too:** branch `pegasus-core-fixes`.

**Architecture learned from results** (each row: what a measurement showed, and where it now lives).

| finding | architectural consequence | where |
|---|---|---|
| parameter uncertainty is ≤ 10% of the overdispersion | the uncertainty layer is not the calibration fix | ADR-0006, Laplace evaluation |
| dispersion differs by region | φ_extra hierarchy (field → macro-region → state) | ADR-0006 |
| BP misses the place's level, not the national one | BP is a mixture over regimes with the place's damped course | ADR-0009 |
| raw-graph MSR is liberal; Dutilleul is slightly liberal | null and negatives on the normalised graph; δ_E calibrated | ADR-0005 |
| replication split after selection measures homogeneity | event sides A/B/R; a conditional test; corroboration as a tier | ADR-0007 |
| trend and disparity positives are state-level; the lenses were municipal | multi-scale lenses; the survey runs gated combinations only | §7.1, 9ee7774 |
| post-hoc positives and criteria | positives declared and committed before running | lens-positives review |
| epidemics and winters sit inside B2s | an epidemic is an outbreak at BP; a season is a calibration positive | §10.1 |
| SIM race ≠ declared race; the infant matrix does not transport | race is a modelled confusion per population; adults stay "recorded race" | pegasus_data decisions 0143, 0149 |
| the raw 2022 Census undercounts; POPSVS is IBGE's corrected projection | coverage is latent per census; POPSVS is modelled | census-coverage evaluation |
| exposure variance double-counts φ | no exposure-variance term by default | ADR-0010 |
| SIH leads are dominated by one hospital's coding | a facility triage class now; the institution lattice is raised in priority | facility triage (running) |
| surveys ran on one core for hours | threaded surveys, a single model load | bef4b70 |
| splitting a cell's events cannot replicate an excess under NB (the sides share the cell's frailty) | replication must use independent units (time, place, system); the event split only sizes effects; the reserve is redesigned | OQ 7; ADR-0007 under revision |
| a calibrated BP (regime mixture) is a weak epidemic alarm: recall 0.48 against 0.81 for level36 with φ_extra (dengue 2019–23) | the EXPECTATION (calibrated, for surprises) and the ALARM BASELINE (for outbreak detection) are distinct objects, as ADR-0004 anticipated | ADR-0009 note; to be decided with ADR-0004's alarm design |
| 34% of SIH chapter X "signals" are one facility's volume or coding step (CNES openings, closures, recoding); J31 in the Rio Doce valley is 100% one hospital | SIH cannot be read without facilities: the institution lattice moves from phase 3 to now; small sole-provider towns stay ambiguous (hospital and place cannot be told apart) | ADR-0014; institution lattice front |
| the dependency map: SIH chapters form one hospital-use dimension, with no edge to SIM mortality or SINASC (ADR-0013) | SIH reflects supply and behaviour more than burden; SIH fields need a utilization factor modelled out (the low-rank interaction ψωτ, §4.2) before their relations are read as disease | ADR-0013; backlog |
| a declared lead (J31, Rio Doce 2015) was one facility's burst BEFORE the rupture; BP training absorbed it and inflated the expectation | BP training must be facility-aware (report a training baseline's facility shares; the institution lattice); exploratory secondary signals are re-declared and tested on independent events | Rio Doce result; Brumadinho declaration |
| replication on independent units (ADR-0015): later years cannot see departures the fit absorbs; other-places halves are invalid for smooth fields; one-offs replicate only by corroboration; no SIM signal is corroborated; 333/7,496 R1, 0 R2/R3; 57 state/region national-trend claims hold in later years AND other places | replication power, not discovery, is now the binding constraint: corroboration needs more independent systems (SIA, SINAN, SIH by facility); the reserve is kept for a pre-declared, high-prior claim | ADR-0015 amendment; replication-independent-units evaluation |
| of 57 replicated state trend claims, the first reading called 42 artefacts (state coding regimes, composition inside an ICD family, abrupt administrative steps), 13 unresolved, 1 finding (Y35 police killings, Goiás); **corrected** by the artefact-aware audit (only a tested explanation removes a claim): 22 survive, 15 open, 13 not replicated, 5 explained, 2 re-scoped | a coding regime replicates in time AND across a state's municipalities: replication must split by jurisdiction, test conservation within the ICD family (+ R group + undetermined intent), reject step shapes, check against the observed national rate, and report the unit's all-cause slope | replicated-claims-read evaluation; artefact-aware replication front |
| SIH place effects are two factors (general hospital use 33%; a referral/specialty axis 17%, against self-sufficiency); removing them takes SIH×SIH edges from 89 to 1, and still no SIH×SIM/SINASC edge appears (ADR-0018) | municipal SIH geography encodes supply and referral, not disease-specific need: SIH relations are read net of the factors; the model-side low-rank term (§4.2) gets rank 2 as its prior | ADR-0018 |
| 14,813 of 33,228 register leads (SIM 5,826, SIH 8,987) were `explained` by triage verdicts that predate grading ("the code's national level moves ×0.24"): a code-level shift had removed the lead instead of re-scoping it | a rule change is applied to the stored state, not only to new runs: every verdict carries its rules' version (`explain.RULES`, the hash of the triage module); a verdict of other rules is stale, `triage --stale` re-runs those leads, and a lead the old rules explained is open again unless the new verdict explains it (the old verdict kept as `triage.superseded`) | coverage matrix (register line); re-triage running |
| a known cross-system link (dengue → microcephaly, Northeast 2015–16) is plain in the regional totals (Q02 25×, a 6–7 month delay) and invisible to E_w at the unit-month grain (ρ ≈ 0.12 flat over lags 0–6, none admitted: expected Q02 0.03 per cell, one wave per series) | a cross-system lagged link must be tested at the grain where the outcome is not rare: an aggregated lagged test (the outcome's surprise against the lagged exposure surprise, summed per region) and a joint space-time scan (an excess in X followed by an excess in Y in the same area); E_w at the unit grain stays for common outcomes | positive-arbovirus-microcephaly evaluation; to build (backlog) |
| a refit absorbs a planted departure in proportion to its share of a component's support: place-year 9–21 %, macro-region-year ~40 %, regional step to the end 45–63 %, national year 100 % (SIM IX) | O5's planted worlds are refitted; a lead's size is re-estimated with its locus masked out of the fit; ADR-0022's fixed-μ admission curves overstate power | ARCHITECTURE §10.3; absorption evaluation |
| SBC on SIM VII (sparse) and XIII (dense): the intercept, the large places and the count-scale sums miscalibrate in both: the joint mode puts data-poor place effects at zero and their mass in the intercept, and Laplace draws centred there inherit it | the Laplace draws are not used for count-scale functionals until levels are estimated marginally (nested Laplace or importance correction); production surprises stay mode-centred | OPEN_QUESTIONS 2; SBC evaluation |
| on SIH, trend divergence finds trends in every time-shifted negative world at any θ0; the rank-1 interaction halves both the real trend leads (1,426 → 636, J09-J18) and the negatives' findings, but not to zero | a SIH trend lead is read net of the interaction, and its remaining place-specific course goes to the facility layer; no threshold calibrates SIH trends | minimum-effects evaluation; ADR-0026 |

**The roadmap (revision 3, ARCHITECTURE §12).** The order is N1 → N2 → O6 → O7 → O8, with O3 and O9 alongside, then O10.

| package | stage | state |
|---|---|---|
| O0 | — | revisions 2 and 3 written (ADR-0023, ADR-0029) |
| O1 solver | B | done |
| O2 settle | B | done (ADR-0025); race (with O3) and SINAN wave 1 open |
| O4 ICD | A–B | mostly done (ADR-0024); lists as effects, recording-quality fields open |
| **N1 noise structure** | B | **built**: NB(μ, φ/κ), an ARMA(1,1) Gaussian copula over periods and a spatial share on the graph, all estimated on the background cells only; `MINIMUM_EFFECT_BY` reduced to SIH's spatial cluster (a reference debt) |
| N2 marginal uncertainty | B | after the O6 acceptance and the regenerated lead register (production reads the mode, which the SBC defect does not touch; it touches the intervals of totals): integrated marginals of the place effects (nested Laplace), entry points `laplace.Posterior.sample`, `solver.StructuredNewton.draws`; accepted when SBC calibrates on VII and XIII |
| **O6 departure models** | C | **in progress**: cell excess accepted for the retrospective cell question (the outbreak lens stays for prospective alarms until cell excess runs on BPA); step built, power low, over the ladder of supports next; trend, cluster, group open |
| O5 bench | B–D checks | grid built, the gate retired (ADR-0028); seasonal and lagged plants, weights across fields open |
| **O7 relations** | D | **in progress**: N1-whitened innovations, graph-frequency bands (no zoning), lagged stacking, EM factor analysis with ARD: clean null and planted worlds; real fields next |
| O8 interpretation | E | rule versions built; recording terms, replication, corroboration, documented events open |
| O3 race and ages | A–B | open |
| O9 breadth | A–B | open |
| O10 use and surveillance | F | last |

**Carried into the overhaul from the v0 backlog** (the rest is done; its history is in git):

| item | package |
|---|---|
| an epidemic-level component for BP (dengue's prospective forecast 2.0–2.8× off) | O6 (cell excess; alarm baselines against Farrington/Noufaily) |
| Laplace follow-ups: an MCMC reference; τ's at the full Hessian | O1 (LAML), §10.6 |
| positives declared for trend divergence, group disparity, marks; the dengue–climate lag | O5 (held out), O7 |
| race in the groups g; exposure re-asked on population-account-3/4 | O2 |
| pegasus_data: open question 71 (DF region-code windows); roles bound to the derived columns, with the gateway switch at the next re-warm; streaming aggregation; SIDRA series across census universes; registration completeness rebuilt on population-account-2; account horizons of 1–3 years | requested through `docs/handoffs/`, with the package that needs them |
| tools over MCP: built (ADR-0008), **paused by the author**; use and integration to be planned together | not scheduled |

**Unblocked:** ICD-10 U07/U09/U10 exist (pegasus_data 70b56fc), so chapter XXII (COVID-19) can be fitted (O2).
