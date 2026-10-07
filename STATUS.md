# Status

**2026-10-07, evening.** Roadmap revision 4 (ARCHITECTURE §12): the whole system end to end, packages S0–S7, each landing end to end before the next. A survey of the day's drift, the author's goals and the cost of readings (`docs/discussion/2026-10-07-survey.md`) found the canonical documents behind the code, the budgets of §5.8 unchecked, and new capability unverified. **Until its defects (§2 there) are fixed and the documentation repaired, no new capability is built**, and nothing heavy runs except a check the author needs.

Words used below: **built** (the code exists), **checked** (what ran, named), **done** (the package's acceptance is met).

## The packages (ARCHITECTURE §12)

| package | state | what is next |
|---|---|---|
| **S0 consolidate** | the v0 lens survey removed, but trend divergence, the space–time lens and the prospective survey were left in no question and no schedule (to restore); stage E's tests ledgered before they run (corroboration, later years, other jurisdictions, triage; checked on SIM and SIH leads); method records read from the harness (vacuous at one measurement); the gateway the only importer (private pegasus_data functions still used); the dependency map rebuilt from declarations (checked on SINASC only) | the survey's open defects; ARCHITECTURE §11.1 and §13 brought to the code |
| **S1 fields from declarations** | built: measures (count family when the domain admits zero), compositions, intervals, linked shares, other classifiers' trees, multiple causes (`mentions`), care flows (`away`), institutions as a question; SIH, SIM, SINASC and SINAN dengue declarations (pegasus_data's decision 0154). Checked: readers on one year each; SIH chapter X with length of stay end to end (16,790 count answers, 79 % from three methods with no measured record; 641 length-of-stay answers). Not done: no documented positive for any new kind | the acceptance on real data: documented positives for a measure and a composition |
| **S2 persons** | built: `cohort()`, linked shares, record identities by pegasus_data's rule, grouped link sides; links read from stored runs only (`PEGASUS_COMPUTE_LINKS=1` to compute). Not run: stored national runs exist for 2021–2022 only | one cohort on a stored year, after S1 |
| **S3 race** | parts exist, not integrated, never run: pegasus_data's population account with race slices (its decision 0151) and the infant and women's confusion products (its decisions 0143, 0149); pegasus_core's race-stratified fits, the recorded-race exposure at age 0 and `tools.disparity` (ADR-0020). Adults read recorded race; the women's matrix is unused | a design for one race path, with the author |
| **S4 independent interpretation** | built: corroboration sources from declarations, later years in `update` (`confirm_last`), passing departures left to corroboration; spatial confirmation repaired (it failed on every unit claim). Open defects: corroboration shaped on documented events, unbounded sources, unlinked years | the survey's defects |
| **S5 reader** | built: `dossier` (HTML), `verdict`. Not used: no dossier produced for the author. Open defects: an `artefact` verdict removes a lead; confirmed verdicts score the methods that found them | the defects, then a first dossier of SIH chapter X |
| **S6 breadth** | plans written (SIM-DOFET, SIA APAC, CIHA; `blocks: [all]`); not run. SINAN: 30 agravos fitted, 17 failed earlier | after S1–S5 |
| **S7 surveillance, serving** | not started; agents and MCP stay here (the author, 2026-10-07) | — |
| **D depth on demand** | the top model, N2, BYM2, interaction patterns, exact reference fit | when a reading needs one |

**Speed (P13, ARCHITECTURE §5.8):** a chapter survey's budget is under 2 min; one SIH field's question pass measured 15 min (share 427 s, excess 176 s, step 105 s, trend 67 s, cluster 67 s, institution 32 s, group 20 s). The optimisation plan's unfinished part (`docs/plans/2026-10-06-optimization.md` §5) is the next speed work.

## Where each stage stands

| stage | state |
|---|---|
| **A. Data** (pegasus_data) | SIM, SIH, SINASC, every SINAN agravo served; declarations of measures, missing codes and domains, link semantics (`same_event`), context denominators (`over`), multiple-cause groups; label lookups kept fresh (pegasus_data 14f6033). SIA/APAC and CIHA declared, not read |
| **B. Expectation** | v1 solver; robust fitting by default; N1 built for counts (a second, simpler noise estimator for measures and shares is a departure to resolve); N2 open (SBC defect of the joint mode on data-poor places) |
| **C. Departures** | the questions registry: excess, step, trend, cluster, share, institution, group; measures read by the multiscale methods since 2026-10-07 (unmeasured) |
| **D. Relations** | `relation_map` (band factor model on N1 innovations), calibrated above the national scale; the dependency map (between-place E_b) rebuilt from declarations |
| **E. Interpretation** | triage with rule versions (institution answers read by their own statistics), replication, corroboration, all ledgered |
| **F. Use** | `report`, `dossier`, `verdict`; no reading delivered to the author yet |

**pegasus_data is developed from this session too** (branch `pegasus-core-fixes`), under its own CLAUDE.md.

**Coverage of the architecture, item by item:** [docs/architecture_coverage.md](docs/architecture_coverage.md) (to be regenerated per package, survey §3).

## Planned and dormant (architecture not advanced, outside the packages above)

| item (ARCHITECTURE) | built | dormant since | next concrete step |
|---|---|---|---|
| institutions in the likelihood (§4.5) | facility triage, mark facility effects | 2026-10-05 | from the declared `institution` roles (same plan) |
| one model across chapters (§5.4) | not built | never started | design note |
| interaction patterns (§7.4) | interaction built, off; `scans/patterns.py` (CP-APR) with no input since the map's SIH tensor went (2026-10-07) | 2026-10-06 | read ψ, ω, τ of one block |
| exact reference fit (OPEN_QUESTIONS 2) | not run | 2026-10-06 | one block by HMC against the Laplace draws |

## Backlog carried from the v0 engine

| item | where |
|---|---|
| an epidemic-level component for BP (dengue's prospective forecast 2.0–2.8× off) | O6 (cell excess; alarm baselines against Farrington/Noufaily) |
| Laplace follow-ups: an MCMC reference; τ's at the full Hessian | O1 (LAML), §10.6 |
| positives declared for trend divergence, group disparity, marks; the dengue–climate lag | O5 (held out), O7 |
| race in the groups g; exposure re-asked on population-account-3/4 | O2 |
| pegasus_data: open question 71 (DF region-code windows); roles bound to the derived columns, with the gateway switch at the next re-warm; streaming aggregation; SIDRA series across census universes; registration completeness rebuilt on population-account-2; account horizons of 1–3 years | requested through `docs/handoffs/`, with the package that needs them |
| tools over MCP: built (ADR-0008), **paused by the author**; use and integration to be planned together | not scheduled |

## Architecture learned from results

Each row: what a measurement showed, and where it now lives (the register the author asked to keep; a row whose design was demoted stays as history of the reasoning).

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
