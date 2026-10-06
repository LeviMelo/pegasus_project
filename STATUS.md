# Status

**2026-10-06. Development is paused for ARCHITECTURE revision 2** (ADR-0023), on the author's instruction after the review `docs/discussion/2026-10-06-architecture-review.md`. It resumes with work package O1 (the structured solver) of `docs/plans/2026-10-06-overhaul.md`. What follows describes the v0 engine that the revision builds on.

**2026-10-04.** Every module of ARCHITECTURE §11.1 existed. The first block (ICD chapter IX, SIM 2010–2023) was fitted and read end to end: surprises at B0, B1 and B2, lenses, pairs (evaluation 2026-10-04).

**Coverage of the architecture** (2026-10-05): [docs/architecture_coverage.md](docs/architecture_coverage.md) maps every ARCHITECTURE item to built / measured / partial / not built / superseded, with the data and scan coverage and the ten gaps that matter most. It reads the code and the evaluations, not this file; re-run it when a status changes.

**Built:**
- **The data path:**
  - `gateway`: population, event counts, structures, graphs, regions, overlap; it reconciles exactly with the official SIM totals;
  - `store`, `config`.
- **The model:**
  - `structures`, `graphs`;
  - `monolith`: the factorised likelihood, Fellner–Schall, φ by exact ML;
  - `fields`: registry, admission, overlap, lifting.
- **Reading the model:**
  - `surprise`: tiers B0, B1 and B2, randomised PIT, calibration, place-year φ;
  - `scans`: the lenses, subset scanning with a Gumbel null, pairs (E_b, E_b|Z with MSR on the normalised graph, E_w with AR(1) n_eff), CP-APR patterns, explaining away, Shapley decomposition, cohort scans.
- **Inference and use:**
  - `control`: the ledger, BH/BY/Simes, Benjamini–Bogomolov, TreeBH, LOND, splits, replication tiers;
  - `leads`;
  - `harness`: positives, planted signals and power curves, NB surrogates, MSR and shift negatives, the gate;
  - `tools` (Session, survey, confirm);
  - `cli` (`pegasus-core`).
- **Known departures** are listed in ARCHITECTURE §13.

**Fitted (contiguity, v0 solver):**
- **SIM:** 19 chapters (I–XVIII, XX), XVII refitted under the `hybrid` exposure on 2026-10-06.
- **SIH-RD:** 20 chapters, annual. The fits on ≤ 2019 for replication are running.
- **SINASC:** births; anomalies (XVII, from CODANOMAL); birth weight (mark model).
- **SINAN:** DENG and LEPT; wave 1 (eleven families) being fitted.

**The first lead examined:** São Borja (RS), acute MI ×2 in 2018 against flat neighbours (evaluation 2026-10-04, SINASC entry).

**pegasus_data is developed from this session too** (since 2026-10-04): branch `pegasus-core-fixes` (ICD-10 COVID categories, border lengths, `logmoments`, pegasus_data's ADR on GBD).

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
| SBC on sparse SIM VII: effects calibrate, count-scale sums do not; the Laplace draws imply 4–10× the observed deaths (a Gaussian at the mode of zero-count levels has a right tail the exact posterior lacks) | the Laplace layer is not used for count-scale functionals in sparse blocks until its marginals are skew-corrected; production surprises stay mode-centred | OPEN_QUESTIONS 2; SBC evaluation |

**The overhaul (2026-10-06).** The order of work is ARCHITECTURE §12. The detail, acceptance and running jobs are in `docs/plans/2026-10-06-overhaul.md`:

| package | what | state |
|---|---|---|
| O0 | the revision: review, principles (P11–P15), the ICD ontology and race (§3.3–3.4), §5, §7.0, §7.5, §8.4, §8.6, §10, §12, §13 (ADR-0021, ADR-0023) | done |
| O1 | the solver: assembled arrowhead Hessian, sparse Cholesky, Schur, BYM2, LAML, selected inversion, the benchmark (`bench`, O1) | **in progress** (2026-10-06): `solver.py` built and verified on IX (exact Newton, quadratic convergence, 24 units below v0's optimum); strengths by Newton on log τ, safeguarded by the LAML itself (mgcv) and shrunk by their probe noise; **the age–sex profile now centred over both sexes** (a model defect: no component carried the sex level; held-out deviance 2.21828 → 2.21703); a start from IPF (leaf + group × year + group × age–sex), backfitted place deviations and moment-estimated strengths; φ from a binned likelihood; cold IX 59 s, 6 outers (v0 501 s calm), XV 50 s, SIH-RD X monthly 2010–14 119 s; v1 is the default for count blocks; monthly grain verified; `scripts/bench.py`, `heavy.py` threads and GPU slot. the interaction (leaf-specific features, alternating Newton for ψ, τ, ω) and the mark and share models on v1; supernodal factor and solves; every SIM and SIH block refitted under ADR-0024 (pass 3, started 2026-10-06 13:09: SIM 2010–2023, SIH 2010–2023, SIM 2010–2019; `data/refit3_chain.py`), then O2's rank and prior runs on the same defaults (`data/o2b_chain.py`). Open: the rank choice on v1 (IX rank 1 held out −1.6284 against v0's −1.6297; rank 3 running), the 20 s budget (IX 37 s under ADR-0024; small geography carriers pooled, the strengths stop at one LAML unit), the BYM ridge's outers (BYM2 coordinates measured, not adopted), the rank choice across blocks (O2). The NB mean fit is not adopted (OPEN_QUESTIONS 8 resolved). v0 retired; exact Laplace draws; the horseshoe on exact variances. **The lead registers predate the refits** and are regenerated when O5–O6 redesign the lenses (evaluation 2026-10-06, solver v1) |
| O2 | settle on the fast stack: the interaction's rank, the horseshoe, the SUS exposure and race groups, SINAN wave 1 | **mostly settled** (ADR-0025, 2026-10-06): the interaction is off by default, with its rank chosen per block (IX rank 4 +0.015 per death); the tree prior stays Gaussian; κ and the SUS share stay opt-in. Open: race groups (with O3), SINAN wave 1 on v1 |
| O3 | race and ages: pegasus_data's tensor fixes (2000 undeclared imputed from microdata, bands, sample vs full count, 1991, single ages 0–19 validated), G = 33 ages × sex × race, the recording model, disparities | |
| O4 | the ICD ontology: pegasus_data's `icd_ontology` (attributes, age rules, ICD-9 bridge, lists, external-cause axes, relations); subcategory leaves, lists, structural zeros, conserved levels from the relations | **in progress** (2026-10-06, ADR-0024): the nested tree; attributes and external-cause axes in pegasus_data; **admissibility built** (sex by RESTRSEXO and NCHS Table G, Table G's absolute age limits, SIM underlying-cause eligibility; excluded records counted by reason); profiles by block with history and geography by group; chapter XX's intent and mechanism fields. The courses' annual forecast is the damped trend (OPEN_QUESTIONS 9, resolved). pegasus_data serves the ICD-9 → ICD-10 bridge (NCHS 1996; 99.45 % of SIM RS 1995's causes covered). Pre-1996 SIM is of limited importance (author, 2026-10-06): the bridge stays as a mapping, and no ICD-9-era reader is planned. Open: recording-quality fields from the conditional edits and CBPOUCOUTEIS, lists as effects, the relation graph; the refits under ADR-0024 |
| O5 | characterise: the planted grid, null worlds, constants re-made, IHW weights, the gate retired | **started** (2026-10-06): a refit absorbs 9–63 % of a planted departure by locus (evaluation, absorption), so the grid's worlds are refitted; `harness.grid` built (plants by kind × shape × θ, NB worlds from the fit, a warm refit at fixed strengths, the production lenses, the logistic power surface) |
| O6 | departure models | |
| O7 | relation models: distributed lag, shared component, endemic–epidemic | |
| O8 | recording: graded re-triage of the stored register (running), rule versions, conserved-level fields, coding regimes | started |
| O9 | breadth: SINAN, SIH marks, SIA/APAC, CIHA, the SIH↔SIM link | |
| O10 | top model, model choice, prospective surveillance | |

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
