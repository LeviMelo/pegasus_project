# Status

**2026-10-06, evening: ARCHITECTURE revision 3** (ADR-0029). PegaSUS is six stages, one computation each (ARCHITECTURE §1.1):
- A data and meaning;
- B expectation, with its noise structure;
- C departures;
- D relations;
- E interpretation;
- F use.

Stages B–D make statistical claims only; E alone is epidemiological. The next work is **N1**, the expectation's noise structure, then N2 → O6 → O7 → O8 (ARCHITECTURE §12; `docs/plans/2026-10-06-overhaul.md`). The review behind it is `docs/discussion/2026-10-06-course-correction.md`.

**Where each stage stands:**

| stage | state | what is next |
|---|---|---|
| **A. Data** (pegasus_data) | SIM, SIH, SINASC, SINAN served. ICD structure, admissibility, the ICD-9 bridge and code lists are in pegasus_data | breadth (O9) |
| **B. Expectation** | the solver is v1 for every model (exact Newton, LAML; IX 32 s, XX 107 s); ICD carriers and admissibility (ADR-0024); O2 settled (ADR-0025); monthly grain, including code lists | **N1:** the predictive ignores serial correlation (lag-1 within places: 0.03 stroke, 0.23 ill-defined, 0.27 births, 0.39 SIH pneumonia). **N2:** Laplace draws miscalibrate the intercept and count sums (SBC) |
| **C. Departures** | v0 lenses only, now screens. Their 2026-10-06 settings (ADR-0026 θ0, ADR-0027 baselines, weighted outbreak) are interim. Held-out sizing (`Session.held_out`) and the absorption finding stand | **O6:** departure models, after N1 |
| **D. Relations** | `relations.distributed_lag` (confirmation of one link; planted curves recovered, null windows 1/100); `pegasus-core relation`; the arbovirus → microcephaly protocol declared | **O7:** the joint model's design note |
| **E. Interpretation** | triage with rule versions; replication tiers; the facility layer for SIH | O8 |
| **F. Use** | the register with method records (ADR-0028); the v0 register (33,228 leads, pre-refit) and the first v1 survey (41,700 leads, the lenses' baseline) are not reading lists | regenerated after O6 |

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
| **N1 noise structure** | B | **next**: an AR(1) place × period term learned per field; accepted when the failed negatives pass with no per-system constant |
| N2 marginal uncertainty | B | after N1: nested Laplace or importance-corrected draws until SBC calibrates |
| O6 departure models | C | after N1: cell excess, step, trend, cluster, group, each against its lens on the grid |
| O5 bench | B–D checks | grid built, the gate retired (ADR-0028); seasonal and lagged plants, weights across fields open |
| O7 relations | D | design note first; the distributed-lag confirmation built |
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
