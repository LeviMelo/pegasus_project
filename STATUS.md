# Status: the map of the code

**2026-10-10.** Branch `design-v0`, HEAD `69efd93` (327 commits since 2026-09-30), plus uncommitted documentation. This file is the map of the codebase as it is: what each module does, what it keeps on disk, how it is driven, what works and what does not. The theory and the plan are in `ARCHITECTURE.md`; the ordered work is in `BACKLOG.md`; decisions, measurements and open questions are in their own files. This file is rewritten, never appended, and holds no plan.

Sources: the code (read 2026-10-10), `scripts/codehealth.py`, `scripts/check_docs.py`, the stores in `pegasus_home/`, and the live capability assessment `data/assessment/2026-10-10-capability-assessment.md` (made while an overnight `update plans/s6_0_sim_all.yml` held the machine; its findings are quoted as measured there, not re-run).

---

## 1. What PegaSUS does today, end to end

`pegasus_core` (40 modules, 22,253 lines; the package `scans` is 9 of them) reads Brazilian health events through `pegasus_data` and turns them into a register of **leads**. For an event type of a system (SIM deaths, SIH admissions, SINASC births, SINAN notifications, SIA procedures, CIHA, ...) it assembles counts by residence municipality x year x sex x age x classifier code (`gateway`, `monolith.assemble`), fits **one hierarchical negative-binomial model per block** (one ICD chapter; `monolith`, `solver`, `laplace`) with a place-year noise structure (`surprise`), turns the fit into expectations at six tiers and a calibrated cell-level surprise (`surprise`), asks every field of the block a fixed set of **questions** (excess, step, trend, cluster, share, institution, group, divergence, prospective) through all the **methods** registered for each (`questions`, `departures`, `scans/`, `multiscale`), controls error over the whole search through a ledger written before any test runs (`control`), and stores what survives as leads (`leads`). A second reading relates fields to each other (`relations`, `dependency`, `scans/maps`), a third interprets leads (triage into signal / noise / substitution / system / facility in `scans/explain` and `facility`; replication on later years and other jurisdictions in `replication`; corroboration in other record systems in `corroborate`), and a fourth presents them (`report`: Markdown report, HTML dossier, person verdicts). Persons linked across systems enter through cohort scans (`scans/cohort`) and linked-share fields. The whole is driven by `update` (a YAML plan brings fits, questions, relations, triage and the report up to date, redoing only what changed), by the `pegasus-core` CLI, by the Python `tools.Session`, and read-only by an MCP server.

State of the store (2026-10-10): 334 stored fits (SIM.DO 149, SIH-RD 85, SINASC-DN 28, 31 SINAN diseases), a ledger of 113,069 tests in 981 families, a register of 63,078 leads (SIH-RD 43,168; SINASC-DN 11,766; SIM.DO 7,746; SINAN-SDTA 398), of which 62,745 are at replication tier R0, 333 at R1, none at R2 or R3. Section 8 says what that means.

---

## 2. The data flow as it runs

```text
pegasus_data (../pegasus_data; lake, roles, event types, links, modelled products, geography)
   |  only `gateway` imports it (two exceptions, section 7)
   v
gateway ---------- counts, populations, marks, shares, links, persons, context fields, graphs -> store kind `gateway`
   |
   v
monolith.assemble -> BlockData (store `blockdata`) -> Monolith.fit  (solver: exact Newton on the arrowhead Hessian,
   |                                       CHOLMOD; LAML strengths)  -> robust refit -> store `monolith`
   |                                       laplace: posterior draws          structures/graphs: precisions, place graph
   v
surprise.Expectations ---- tiers B0 B1 B2 B2s BP BPA, noise structure N1, randomised PIT, calibration  (store `surprise`, `calibration`)
   |
   v
questions.ask  ->  methods:  departures (cell_excess, excess, step, share_excess, joint_excess, attribute)
   |                         scans.lenses (outbreak, change_point, space_time, spatial_cluster, trend_divergence, group_disparity)
   |                         scans.subset (space-time scanner), multiscale (graph heat-kernel peaks), facility (institution step)
   |   every test registered in control.Ledger BEFORE it runs; BH / Bogomolov per family
   v
leads.Register (Parquet parts) -- Lead(kind, estimand, tier, fields, locus, effect, q, replication R0..R3, triage, method record)
   |
   +--> stage E on demand / in `update`:  Session.triage (scans.explain, facility, marks)  ->  replication (later years, other jurisdictions)
   |                                       corroborate (other systems)  ->  verdicts, replication tier
   +--> stage D:  relations.relation_map (N1 innovations in graph bands, factor model)  /  dependency (between-place map, scans.maps, scans.pairs)
   +--> persons:  scans.cohort on gateway.persons / linked_counts
   +--> use:  report.report / report.dossier / report.record_verdict ; tools.find_leads / explain_lead ; mcp_server ; cli
harness: planted worlds, null worlds, known positives -> store `harness` -> questions.method_records -> every lead's method record
update:  the orchestrator over all of the above for a plan (plans/*.yml), under jobs (one heavy-job slot, thread count, GPU slot)
```

Layering (imports go downward; `scripts/codehealth.py` finds 0 import cycles, function-level imports counted):
`cli`, `mcp_server` > `update`, `report`, `dependency`, `harness` > `tools` > {`replication`, `corroborate`, `questions`, `departures`, `relations`, `marks`, `multiscale`, `surveillance`, `scans/*`} > `surprise` > {`monolith`, `laplace`, `solver`, `facility`, `fields`} > {`gateway`, `graphs`, `structures`, `jobs`} > `store`, `config`. `control` and `leads` are used from every layer above `gateway`.

---

## 3. Module map

Lines are of `src/pegasus_core/` on 2026-10-10. "Imports" lists pegasus_core modules only (function-level imports included).

### 3.1 Foundations

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `config` | 319 | homes and roots; versions; seeds; the **code-closure key** (`code_key`: a hash of the AST of the named functions and everything in the package they reach, so an edit re-keys only what it can change) | `home`, `data_root`, `population_root`, `population_source`, `population_pinned`, `code_version`, `code_key`, `code_closure`, `data_version`, `resource_version`, `data_code_version`, `data_package_dir`, `seed`, `supply_exponents`, `FIT_YEARS` (2010-2023) | none (sets `PEGASUS_DATA_HOME` default at import) |
| `store` | 145 | content-addressed artefacts `pegasus_home/<kind>/<sha256[:20] of key>/` = `table.parquet` (zstd) or `arrays.npz` + `manifest.json` (key, code and data versions, written time); `gc` evicts caches | `address`, `put_table`, `get_table`, `put_arrays`, `get_arrays`, `manifest`, `manifests`, `gc`, `CACHE_KINDS` (`gateway`, `blockdata`) | config |
| `structures` | 120 | precision structures of effects (iid, RW, ICAR, kNN) | `Shape`, `iid`, `random_walk`, `icar`, `knn_graph`, `centre` | none |
| `graphs` | 102 | proximity graphs over places through the gateway, stored as arrays (`graphs`) | `edges`, `graph`, `DEFAULT` ("contiguity") | config, facility, gateway, store, structures |
| `jobs` | 116 | the machine: one heavy-job slot (OS file lock, `PEGASUS_HEAVY_SLOTS`), thread count, GPU slot, `run` of command sequences, `parallel_map` | `default_threads`, `slot`, `threads`, `run`, `parallel_map` | gateway |
| `control` | 427 | **error control**: the append-only ledger (Parquet parts `pending` then `result`), BH/BY (weighted), Simes, Bogomolov, tree BH, LOND, replication helpers (halves, `replicates`), the confirmation reserve | `Hypothesis`, `Ledger` (`register`, `complete`, `table`, `compact`, `family`), `bh`, `optimal_weights`, `adjusted`, `simes`, `bogomolov`, `tree_bh`, `LOND`, `temporal_halves`, `spatial_halves`, `replicates`, `event_sides`, `ReservedPeriod`, `Reserve`, `check_reserved`, `replication_tier`, `KINDS` | config |

### 3.2 Data and fields

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `gateway` | 2130 | **the one door to pegasus_data.** Every input is an Arrow table cached in `gateway` keyed by data version and the code it runs; events that cannot be placed are returned as `unallocated`. Populations (POPSVS, population account 2/3/4, hybrid, with modifiers kappa = registration completeness, sus = without private coverage, confusion = race), event counts by residence x sex x age x code, monthly counts, mark moments, composition and share counts, flow (`away`) counts, code-list counts, weights, delay counts, context fields, graphs and memberships, name lookups, stored link pairs and persons, link sensitivity/completeness, cohort records Ratio exposures: `population("events:A:e[;B:e][@lag]")`, another field's events by place-year; `event_counts(cell=False)` (no sex or age read), `support=` (another municipality column as the place), year-specific strata (`_strata(..., year)`), `NothingPublished` for a year not published; `mark_quantiles` (a mark's median and p90 by state); `share_moments(quality=True)`; `delay_counts(codes=)`. | `EventCounts`, `population`, `completeness`, `sus_share`, `declared_ratios`, `event_counts`, `monthly_counts`, `mark_moments`, `composition_counts`, `composition_facility`, `share_moments`, `away_counts`, `mark_facility_moments`, `code_list_counts`, `strata`, `code_tree`, `code_structure`, `code_attributes`, `event_types`, `event_datasets`, `roles`, `context_field`, `context_sum`, `context_value`, `declared_fields`, `proximity_graph`, `municipality_points`, `municipality_names`, `regions`, `epi_week`, `delay_counts`, `ensure_lake`, `published_years`, `link_specs`, `stored_pairs`, `covering_runs`, `side_pairs`, `link_sensitivity`, `link_completeness`, `linked_counts`, `cohort_records`, `persons`, `person_quality`, `person_records`, `person_scopes`, `machine_slot`, `facility_column`, `LinkNotStored` | config, store |
| `fields` | 679 | a **field** is a node of a classifier tree or a declared column read in a declared way; the registry walks a tree; `declared` turns pegasus_data roles into fields (measures, compositions, intervals, linked shares, mentions, flows, code columns, other classifiers) or into a stated reason why not; `coverage` lists every declared column with what reads it `quality_sources` (blank or declared-missing share per column), `support_sources` (the event's municipality columns as supports). | `Field`, `Registry`, `Declared`, `declared`, `measure_source`, `declared_flows`/`flow_source`, `declared_mentions`/`mentions_source`, `declared_codes`/`codes_source`, `interval_source`, `classifier_sources`, `share_sources`, `declared_links`/`link_source`, `coverage`, `coverage_summary`, `overlap`, `testable`, `lift`, `common_support`, `reader_tag` | config, gateway |

### 3.3 Stage B: the expectation

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `monolith` | 2883 | the hierarchical model of a block: `y[e,u,t,g] ~ NegBin(mu, phi)` with levels along the ICD tree, age-sex profiles, histories (RW2), BYM geography per level, optional low-rank place x time interaction (Poisson, annual only), NB-P dispersion, robust refit (trimmed likelihood, recodings moved within the block), per-category courses; mark and share models (log-normal, beta-binomial, count-valued); BP's regime extrapolation; `assemble` builds `BlockData` from the gateway A ratio field's events and exposure in one cell (`events:` population); `default_population` reads an event type's declared exposure (pegasus_data decision 0161); warm starts only within one exposure unit. | `BlockData`, `assemble`, `fit_block` (assemble, fit, store and robust-refit one block: the one fitting path, moved here from `update` on 2026-10-10), `Monolith` (`fit`, `warm_start`, `robust`, `robust_stored`, `refit`, `without`, `expected`, `expected_by_group`, `nb_loglik`, `save`, `load`), `MarkModel`, `ShareModel`, `CountModel`, `model_class`, `place_year_phi`, `extrapolate*`, `regime_history`, `heldout`, `default_population` | config, control, gateway, graphs, jobs, solver, store, structures |
| `solver` | 1809 | the v1 solver: exact Newton on the block-arrowhead Hessian (leaf-place diagonal eliminated, place system by CHOLMOD supernodal factor, dense Schur on globals), LAML strength updates with exact traces, interaction sweeps | `StructuredNewton`, `Arrowhead`, `Supernodal`, `Factors`, `fit_mean`, `ix_sweep`, `ix_strengths` | none |
| `laplace` | 227 | Laplace posterior of a fitted block: exact draws from N(0, H^-1) on the centred subspace, exact conditional sweeps of the nested levels (Poisson only), predictive phi | `Posterior`, `predictive_phi` | config, monolith, solver |
| `surprise` | 1356 | **tiers and calibration.** For a field and a tier (B0 no place effects, B1 the fit, B2 + place trend, B2s + place season at monthly grain, BP prospective expectation, BPA alarm baseline) every cell gets y, mu, aggregate phi, randomised PIT, z, information weight; **N1 noise structure** (AR(1) latent over periods, gamma frailty by Gaussian copula, spatial heat-kernel root); calibration (KS by macro-region); mixture PIT for BP | `Noise`, `Surprise`, `Expectations` (`model`, `field`, `surprise`, `prospective`, `place_effects`, `posterior`), `noise_structure`, `with_noise`, `calibration`, `refit_place*`, `place_course`, `lift`, `replicate_correlated`, `field_replicate`, `randomised_pit`, `mixture_pit`, `TIERS` | config, facility, fields, gateway, jobs, laplace, monolith, store |
| `facility` | 416 | the institution behind an event: the facility cube (residence, facility, code3, year), supply indices and the supply term of a block, the institution lattice (a facility's events against its catchment's expectation) | `facility_cube`, `Facilities`, `Pairs`, `pairs`, `supply_indices`, `fit_supply`, `attach_supply`, `Supply`, `best_window`, `institution_lattice` | config, gateway, scans (explain), store |
| `marks` | 280 | measures of an event type (length of stay, cost, death in hospital, ICU days) fitted with case-mix and an empirical-Bayes facility effect; triage of a mark lead as one institution's | `reader`, `spec`, `fit_chapter`, `shrink_facilities`, `facility_jumps`, `triage_lead`, `FacilityFit`, `save_record` | facility, fields, gateway, graphs, monolith, scans |

### 3.4 Stages C and D: departures, questions, relations

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `questions` | 347 | the **registry of questions and their methods** (section 5.1; `seasonality` is asked at the monthly grain only, `Question.grain`), `ask` (all methods of a question at q/k, union merged into answers by overlapping loci, agreement reported), `method_records` read from the harness store | `Question`, `Method`, `Answer`, `AnswerList`, `QUESTIONS`, `ask`, `agreement`, `summary`, `method_records` | departures, store |
| `departures` | 681 | departure models: Efron two-group `cell_excess` (empirical null, size classes, one BH), multiscale `excess`, Bayesian `step`, `attribute` (intervention-analysis shape of a course), beta-binomial `share_excess`, `joint_excess` over several fields | `two_group`, `bayes_select`, `size_classes`, `cell_excess`, `excess`, `series`, `attribute`, `step`, `betabinom_tails`, `betabinom_central`, `share_excess`, `joint_excess` | config, control, multiscale, scans, surprise |
| `multiscale` | 391 | space at every scale from the place graph: normalised-Laplacian spectrum, heat kernels, peaks of standardised kernel contrasts (gamma tail scores), footprints | `GraphSpectrum`, `spectrum`, `contrasts`, `peaks`, `Peak`, `tail_p`, `tail_z`, `kernel_row`, `footprint` | config, store, surprise |
| `scans/lenses` | 795 | the v0 lenses, kept as methods of questions: outbreak, change point, space-time, spatial cluster, trend divergence (3 scales), group disparity, burden/mean cell tests; **season departure** (monthly grain, 3 scales: yearly NB harmonics against the rest of the field's season, random-effects over the years; the `seasonality` question's two methods, level and change) | `spatial_cluster`, `space_time`, `outbreak`, `change_point`, `group_disparity`, `trend_divergence`, `unit_trends`, `season_departure`, `year_harmonics`, `mean_cell`, `burden_ratio`, `burden_shift`, `minimum_effect`, `Finding` | control, surprise, scans.scales, scans.subset |
| `scans/subset` | 461 | expectation-based Poisson subset scanning over graph-connected neighbourhoods and windows, with Monte Carlo null | `Scanner`, `scan`, `score`, `neighbourhoods`, `windows`, `Null`, `null`, `replicate`, `Subset` | config, surprise |
| `scans/scales` | 63 | the unit a per-place lens reads (municipality, immediate region, state) | `Scale`, `municipality`, `standard` | gateway |
| `relations` | 712 | stage D: N1-whitened innovations in graph-frequency bands, lagged stacking, EM factor model with ARD (`factor_model`), `relation_table` under one BH, directness by the graphical lasso, national/macro-regional course relations with phase surrogates; the penalised distributed-lag curve (`distributed_lag`) as pairwise confirmation | `relation_map`, `factor_model`, `innovations`, `lagged`, `bands`, `relation_table`, `course_relations`, `direct_relations`, `distributed_lag`, `lag_matrix`, `LagCurve`, `Factors`, `SpectralFactors`, `spectral_factor_model` (not wired), `Departures` | control, surprise |
| `dependency` | 271 | the dependency map over a plan's systems: place effects of every fitted field plus context fields, marginal and conditional edges under one control (`scans/maps`) | `dependency_map`, `build`, `place_effect`, `gaussian_effect`, `normal_scores` | config, control, fields, gateway, leads, scans, scans.maps, scans.pairs, store, surprise, tools |
| `scans/maps` | 280 | map inputs and the map: every field against every other between places, two layers (E_b marginal, conditional on contexts), utilization factors | `MapInputs`, `DependencyMap`, `dependency_map`, `exclude_miscalibrated`, `care`, `factors`, `testable` | control, fields, scans.pairs, store |
| `scans/pairs` | 291 | dependence between two fields at their common support: Moran-basis spectral randomisation null, minimum-effect p | `Pair`, `MoranBasis`, `statistics`, `between`, `within`, `minimum_effect_p` | config, control, graphs, store |
| `scans/utilization` | 41 | parallel analysis / rank-1 share of the care-use factor | `parallel_analysis`, `rank1_share` | config, scans.maps, scans.pairs |
| `scans/patterns` | 131 | multiplicative place x time x field patterns (CP-APR factorisation) with stability | `Factorisation`, `fit`, `congruence`, `stability`, `temporal_stability`, `spatial_stability` | config |
| `surveillance` | 162 | prospective surveillance: the weeks that have ended by an as-of date (`window`, across epidemiological years and files), reporting-delay distributions per place (empirical Bayes), nowcast with the week's alarm baseline as the prior on its total, alarm threshold at a declared recurrence (false alarms at most 1/(c·R) by Markov) | `Delays`, `delays`, `window`, `nowcast`, `threshold`, `alarm`, `expected_false_alarms` | gateway |

### 3.5 Stage E: interpretation

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `scans/explain` | 764 | explaining away and decomposition; **triage rules** (versioned by `RULES`, a hash of the module): substitution, system, noise, signal, facility; graded explanations (tested, bound, consistent); share triage; log-linear profile tests | `explain_away`, `decompose`, `triage`, `institution_triage`, `share_triage`, `facility_read`, `recoded_profile`, `profile_test`, `exchange`, `shape_test`, `Explanation`, `Evidence`, `Triage`, `GRADES` | config |
| `replication` | 903 | replication by units that did not select the lead: later years (`test_prospective`, re-levelled to the state's course), other jurisdictions against how deaths are recorded (`audit`, conserved levels, pool exchange), event sides A/E for sizes only (`honest_effect`), `account` of each independent test | `deal`, `prepare`, `SideModel`, `SideExpectations`, `match`, `honest_effect`, `relevel`, `test_prospective`, `test_lead`, `account`, `lasting`, `Strata`, `jurisdiction`, `conserved_level`, `pool_exchange`, `audit`, `simulate_*` (shape, exchange, profile, temporal, sizes), `INDEPENDENT` | config, control, gateway, graphs, leads, monolith, scans (explain, lenses), store, surprise |
| `corroborate` | 380 | corroboration: the same place and years in an independent record system (every served ICD-coded event type, declared context fields such as disasters), one statistic, one family | `Source`, `Corroboration`, `Fields`, `sources`, `corroborate`, `source_year`, `field_events`, `categories_of`, `typologies_for` | config, gateway, store |
| `leads` | 292 | the lead and the register: `Lead` (kind, estimand, tier, fields, locus, effect, scale, q, family, null, replication R0-R3, replications, robustness, provenance, status, method record, train_last/purpose for prospective), rank = -log10 q x |log effect| x (1 + tier), append-only Parquet parts, stories (leads grouped by place), reading order | `Lead`, `Register`, `Story`, `stories`, `reading_order`, `uncalibrated`, `trend_reference`, `family`, `chapter`, `triage_counts`, `KINDS` | config, gateway |
| `scans/cohort` | 169 | cohort scans on linked persons: every declared attribute against each outcome, Schur-complement fit on covariate cells, Rubin combination over link draws | `scan`, `fit_one`, `CohortResult` | control (+ pegasus_data `linkage.uncertainty.combine`) |
| `harness` | 1111 | the validation harness: known positives (`POSITIVES`, 42 declarations), planted signals in refitted worlds (`grid`: kind x shape x theta, power surface, absorbed share), null surrogates, negative controls for pairs and maps, E_b gate, `event_record` of every method against the positives | `Positive`, `POSITIVES`, `grid`, `grid_world`, `grid_design`, `Plant`, `surface`, `absorbed`, `lens_world`, `group_world`, `pair_negatives`, `pair_power`, `map_negatives`, `calibrate_delta`, `dependency_negatives`, `event_record`, `verdict_positives`, `locus_reach`, `record` | config, control, gateway, leads, questions, scans (lenses, maps, pairs, subset), store, surprise, tools |

### 3.6 Use and interfaces

| module | lines | responsibility | main public names | imports |
|---|---|---|---|---|
| `tools` | 1914 | **the Python API.** `Session(dataset, event, years, graph, supply, rank, source, ledger, register)` binds an event type's fitted blocks to the ledger and register: `fields`, `surprise`, `scan`, `ask`, `survey_questions`, `triage`, `corroborate`, `explain_away`, `decompose`, `held_out`, `relation`, `alarms`, `side`/`train`/`temporal_confirm`/`spatial_confirm`/`honest_sizes`/`retier`, `confirm`/`confirm_many` (the reserve); module functions for registry reading and cross-field work `by_composition` and `group_columns`: compositions and the race stratum as group dimensions of the group question (race expected from the population's own race slices); `alarms` with the baseline as the nowcast prior and the field's own events; a code set's share taken of all the type's events. | `Session`, `lens_tier`, `LENS_TIERS`, `PROSPECTIVE_TIERS`, `fitted`, `find_leads`, `explain_lead`, `lead_row`, `kinds_of`, `ledger_status`, `method_status`, `relation_survey`, `joint`, `compare`, `records`, `cohort`, `disparity` | config, control, corroborate, departures, facility, fields, gateway, graphs, leads, marks, monolith, multiscale, questions, relations, replication, scans (cohort, explain, lenses, scales), store, surprise, surveillance |
| `update` | 523 | **the orchestrator.** `Plan` (YAML) -> lake build and link runs as declared steps -> fit every block (`monolith.fit_block`, the one fitting path) -> questions per field -> declared readers (measures, compositions, links, intervals, mentions, flows, classifiers, codes) -> race disparities -> prospective fits and survey -> relations -> triage + corroboration -> later-years confirmation -> report -> ledger compaction; each step keyed by data version, code closure and inputs and skipped when current, so a killed run resumes `system_readers` lists a system's fields beyond its counts (also quality and supports), read by `run` and by `study`; triage per reader and per year, retired answers skipped. | `System`, `Plan`, `monolith_class_load`, `plan_links`, `run`, `EXTRA` | config, control, corroborate, fields, gateway, graphs, monolith, report, store, tools |
| `cooccur` | 50 | **related codes from records** (ARCHITECTURE §4.2): `related_codes` reads the codes on the same records as the seeds (`gateway.cooccurrence`: certificate lines, all diagnoses, anomaly lists), expected under independence within sex × age-band strata, exact Poisson p, BH, lift with its interval; a study lists them in its scope and reads them as fields beyond a survey | `related_codes` | control, gateway |
| `propagation` | 349 | **propagation** (ARCHITECTURE §7.2, component 7): each place's onset (first cell departure), the source by the onset-distance Spearman correlation inside a Moran-spectral null (the source search inside the null), Theil-Sen speed, trend-surface bearing, successive waves in fixed sequence, emergence where the field was absent | `onsets`, `waves` | departures, graphs |
| `capture` | 100 | **capture fields** (ARCHITECTURE §5.2, §6.4): `multiple_systems` fits every log-linear model with main effects and pairwise dependences over k linked systems' inclusion patterns, averages N̂ by Akaike weight (Buckland's unconditional variance), and gives each system's completeness | `multiple_systems`, `Estimate` | statsmodels |
| `study` | 965 | **studies (ARCHITECTURE §3).** `load` validates a declaration (with `ratios:`); `resolve` gives its scope: SINAN agravos named, every event type whose primary ICD-10 classifier holds the seeds' nodes, subcategory seeds as code sets, declared ratios, and (scope v2) the concept index's other ICD classifiers, SINAN agravos by `ID_AGRAVO` and label-named SIGTAP procedures as code sets; each source's years, download cost against the depth's budget, cheapest first, and its records, a source with none dropped; the depth's readers (`DEPTH_READERS`). `run` drives `update` per item and writes the folder: `findings.parquet`, `descriptive.parquet` (counts and rates with exact intervals per exposure; intervals as the records' median and p90; shares with Clopper–Pearson), `groups.parquet` (each composition and race, observed and expected), `hypotheses.parquet`, expectation tables viewed from `study.duckdb`, series and map figures, `report.html`; `export` materialises a folder | `Declaration`, `load`, `resolve`, `Scope`, `Item`, `run`, `export`, `DOWNLOAD_BUDGET_GB`, `DEPTH_READERS` | config, fields, gateway, leads, store, tools, update |
| `report` | 265 | stage F: the register as a Markdown report with named places, an HTML dossier (series figures with matplotlib, codes table, replication rows, verdict slot), a person's verdict written back to the register (a confirmed lead becomes a documented event; an `artefact` verdict annotates, never removes) | `report`, `write`, `dossier`, `record_verdict` | config, gateway, graphs, leads, replication, tools |
| `cli` | 532 | `pegasus-core` (typer): 32 commands (section 6.1); heavy ones run under `jobs.slot` | `app`, `main` | control, dependency, fields, gateway, harness, jobs, leads, mcp_server, monolith, questions, replication, report, store, tools, update |
| `mcp_server` | 362 | PegaSUS over MCP (stdio, optional extra `mcp`): 9 tools and 2 resource families (section 6.2) | `list_blocks`, `list_fields`, `get_expectation`, `search_leads`, `explain_lead`, `place_story`, `method_status`, `ledger_status`, `confirm_claim`, `architecture_map`, `architecture_section`, `evaluation_index`, `evaluation_entry`, `main` | config, control, graphs, leads, replication, store, tools |

`__init__` (12 lines) only carries the package docstring.

---

## 4. Persistent state

### 4.1 Roots and environment

| root | default | role |
|---|---|---|
| `PEGASUS_HOME` | `<repo>/pegasus_home/` (gitignored, 8.3 GB) | everything PegaSUS writes |
| `PEGASUS_DATA_ROOT` | `C:/Users/Galaxy/pegasus_core_data` (`config.data_root`) | pegasus_data's home for PegaSUS's own reads: `_catalog/`, `blobs/`, `lake/` (`CIHA`, `SIHSUS`, `SIM`, `SINAN`, `SINASC`, `demas`, `fields`, `links`, `modelled`, `population`, `roles`, `sidra`), `registries/`, `work/`. `config` also sets `PEGASUS_DATA_HOME` to it at import, because an unrooted pegasus_data call creates a home beside the working directory |
| `PEGASUS_POPULATION_ROOT` | `C:/Users/Galaxy/LEVI/projects/pegasus_data/pegasus_data_home` | read for population series already built there |

| variable | read by | effect |
|---|---|---|
| `PEGASUS_POPULATION` | `config`, `monolith` | exposure source (`popsvs`, `account-2/3/4`, `hybrid`, with `+kappa`, `+sus`, `+confusion`); unset: `monolith.default_population` per field |
| `PEGASUS_SUPPLY` | `config` | `volume:1,utilisation:0.5`: facility-supply exponents given instead of chosen |
| `PEGASUS_THREADS`, `PEGASUS_HEAVY_SLOTS`, `PEGASUS_SLOT_HELD` | `jobs` | thread count; number of heavy-job slots (1); set in a child of a job that holds the slot |
| `PEGASUS_HEAVY_MIN_FREE_GB`, `PEGASUS_HEAVY_WAIT`, `PEGASUS_MIN_FREE_GB`, `PEGASUS_ADMISSION_WAIT`, `PEGASUS_DECODE_SLOTS`, `PEGASUS_DECODE_SLOT_DIR` | `gateway`, `jobs` | pegasus_data's decode admission, set around heavy reads (`machine_slot`) |
| `PEGASUS_COMPUTE_LINKS` | `gateway` | `1`: a link run missing from the store is computed instead of raising `LinkNotStored` |
| `PEGASUS_MCP_LEDGER` | `mcp_server` | ledger directory of the MCP server |
| `PEGASUS_LAML_TOL`, `PEGASUS_OUTER_TOL_FRAC`, `PEGASUS_SCORING_PROBES` | `monolith` | solver tolerances and probes (benchmarks) |

### 4.2 The store, kind by kind (`pegasus_home/<kind>/`)

Entries are `manifest.json` + `table.parquet` or `arrays.npz`; the address hashes the key (what it is, data version, code closure). Counts are directories on 2026-10-10.

| kind | entries | written by | read by | note |
|---|---|---|---|---|
| `gateway` | 1,900 | `gateway`, `facility` | everything above | cache of pegasus_data reads; evictable (`gc`) |
| `blockdata` | 41 | `monolith.assemble` | fits, replication | cache; evictable |
| `monolith` | 334 | `monolith.fit_block` (`Monolith.save`, `robust_stored`) | `surprise.Expectations.model`, `replication`, `update.monolith_class_load` | fits and their robust refits; never evicted |
| `structures` | 8 | `monolith` (shape precisions) | `monolith` | sparse Q |
| `graphs` | 21 | `graphs.graph`, `scans/pairs` | `graphs`, `scans/pairs` | edges, weights; Moran bases |
| `spectrum` | 3 | `multiscale.GraphSpectrum` | `multiscale` | eigenpairs of the place graph |
| `surprise` | 6 | `Expectations.surprise` (when asked to cache) | `Expectations` | cell tables + noise + calibration |
| `calibration` | 11 | `tools.Session.calibration_of` | `tools` | per field, tier |
| `answers` | 21 | `tools.Session.survey_questions` | `tools` | a field's merged answers (pickled rows), so a killed survey resumes at the next field |
| `split_sides` | 20 | `replication.deal` | `replication` | events dealt to sides A/E (fixed seed) |
| `corroborate` | 56 | `corroborate` | `corroborate` | independent fields' events by year |
| `maps` | 4 | `scans/maps`, `dependency` | `scans/maps` | map inputs, edges, SIH tensor |
| `harness` | 122 dirs | `harness.record`, `harness.grid` | `questions.method_records`, `tools.method_status` | grid / gate_lenses / gate / gate_eb / event_record / depmap results |
| `tools` | 6 | `tools` | `tools` | expected totals, evidence grids |
| `update` | 24 | `update._mark` | `update._done` | step-completion markers (questions, fit, triage, lake, prospective, disparity) |
| `ledger/` | 101 parts | `control.Ledger` | `control`, `tools`, `mcp_server` | the main ledger: Parquet part files (`pending`, `result` rows); compacted at the end of `update` |
| `ledger_A/`, `ledger_T<last>[<reader tag>]/` | 10,527 and 2,248 parts | `Session.side("A")`, `Session.train(last)` | same | selecting sessions' own ledgers (side A; training years); **not compacted** |
| `leads/`, `leads_A/`, `leads_T<last>/` | 126, 2, 6 parts | `leads.Register` | `leads`, `report`, `tools`, `mcp_server` | the register; a lead's later states are new rows of the same id |
| `triage_block/` | 41 | nothing in `src/` (the writer was removed) | nothing | legacy |
| `_archive/`, `monolith_centring1_2026-10-06/`, `readout_sim_agg.parquet`, `vital_account_2022.npz`, `cohort_infant_2021*.json` | | superseded registers and `data/` scripts | nothing | legacy / script output; unreferenced by the package |

Other outputs: `reports/` (gitignored: `leads.md`, `dossier.html`, per-plan reports), `data/` (gitignored, 314 entries: ~190 experiment and benchmark scripts, 77 logs, `data/probes/` 153 outputs, `data/assessment/`, `data/real_events.py` and its versions), `studies/siac_mulher_2026/` (scripts, results, journal, abstracts), `.claude/worktrees/agent-a7b38d04f82452c33` (a stale agent worktree) and sibling worktree `../pegasus_project_b4` (branch `b4-size`).

---

## 5. Questions, methods, tiers, plans

### 5.1 The questions registry (`questions.QUESTIONS`)

| question | component (ARCHITECTURE §7.2) | reference tier | methods (`id`) | shapes accepted |
|---|---|---|---|---|
| `excess` | transient | B1 | `cell_excess`, `excess` (multiscale spike), `outbreak` (v0), `space_time` (v0) | spike, transient |
| `step` | step | B1 | `excess_step`, `step` (Bayesian change point), `change_point` (v0) | step |
| `trend` | trend | B1 | `excess_trend` | trend |
| `cluster` | level; `spatial_cluster` spatial coherence | B0 | `excess_level`, `spatial_cluster` (v0) | |
| `propagation` | propagation | B1 | `propagation` (first departures, source, Theil–Sen speed, Moran spectral null) | propagation |
| `share` | transient (ratio field) | B1 | `share_excess` (beta-binomial) | |
| `institution` | step (facility support) | B1 | `institution_step` (v0 lattice) | |
| `group` | group heterogeneity | B0 | `group_disparity` (v0) | |
| `divergence` | trend (against neighbours or nation) | B2 | `divergence_neighbours`, `divergence_national` (lens `trend_divergence`; municipality, region, state) | |
| `seasonality` | seasonality | B1, monthly | `season_level`, `season_change` (lens `season_departure`) | |
| `prospective` | the method's component against BP/BPA | BP / BPA | `outbreak` (BPA), `change_point` (BP), `space_time` (BP) | |

A finding's component is the set of its agreeing methods' (`questions.components`); relation is a study product
(`tools.compare`, `tools.determinants` with time-varying contexts, `relation_survey`).

Methods declare the field kinds they read (`count`, `mark`). Every method of a question runs at q/k (union bound); the Cauchy combination is not yet used. Every method has a stored record (calibration on null worlds, power on planted signals, recall on the documented events); all 16 are maturity `v0` (section 8).

### 5.2 Field kinds `fields` can produce

Counts of a classifier node (ICD-10 chapters/blocks/3-character categories, SIGTAP procedure chapters, other declared code trees); measures (positive log-normal, count-valued, bounded); compositions (a share per category value); intervals (days from the event's own date); linked shares and outcome-after-event fields (declared links); multiple-code `mentions:<role>`; place fields `origin:` and care flows (`away`); code-column fields `codes:<column>`; race-stratified counts (`source={"race": k}`); weighted events (SIA procedures weigh rows; per-record readers refuse them); grid events (SINAN-SDTA outbreak cases by sex x band).

### 5.3 Plans (`plans/*.yml`, 20 files; `update.Plan` keys: `years`, `systems[{dataset, event, blocks, levels, measures, compositions, links, intervals, classifiers, mentions, flows, codes, disparities}]`, `questions`, `relations`, `triage`, `report`, `graph`, and extras `corroborators`, `contexts`, `confirm_last`, `prospective`, `persons`)

| plan | covers |
|---|---|
| `default.yml` | SIM.DO I/IX/X/XX, SIH-RD I/X, SINASC-DN, SINAN-SIFC; corroborators SINAN-DENG, SINAN-CHIK; relations and triage; the dependency map reads its systems |
| `s6_0_sim_all.yml`, `s6_0_sih_all.yml` | every ICD-10 chapter of SIM.DO and SIH-RD, by group, 2010-2023 (the SIM one is the overnight run of 2026-10-10) |
| `s6_sinan.yml` | every SINAN agravo published in all of 2010-2023; `s6_sinan_2013`, `_2015`, `_2019` the later-published agravos; `s6_sinan_sdta` outbreaks and cases of SINAN-SDTA (2015-2023) |
| `s6_sim_dofet.yml`, `s6_ciha.yml` | foetal deaths; CIHA admissions (2012-2023) |
| `s6_sia_apac.yml`, `s6_sia_dialysis.yml`, `s6_1_sia_ps.yml`, `s6_1_sia_sad.yml` | SIA: oncology authorisations (AQ, AR), dialysis (ATD), psychosocial care (PS), home care (SAD); weighted events |
| `s1_sih_x.yml`, `s1_sih_sigtap.yml`, `s1_sim_mentions.yml`, `s1_sinasc_fields.yml` | declared fields: SIH X length of stay, SIH by procedure, SIM by mentioned cause, SINASC measures and interval |
| `s2_infant_cohorts.yml` | births followed by an infant death through declared links (2010-2022), persons |
| `s3_births_perinatal.yml` | race disparities of births and perinatal deaths |

### 5.4 Scripts (`scripts/`)

| script | does |
|---|---|
| `check_docs.py` | mechanical consistency of the documents (section 10) |
| `codehealth.py` | import cycles and unreferenced definitions (runs in about a second) |
| `bench.py` | the solver benchmark (cold and warm fits of reference blocks) |
| `sbc.py` | simulation-based calibration of the mean fit and its Laplace posterior |
| `throughput.py` | seconds per field and question from a plan's stamped log |
| `profile_field.py` | profile of the question pass on one field |
| `warm_gateway.py` | fills the gateway cache for an event type and years |
| `fit_marks.py` | fits and reads one declared measure of SIH |
| `gate_eb.py` | the E_b gate: negative controls, delta_E, planted-latent power, known positives |
| `location_null.py` | null worlds of a location field |
| `measure_bp_level.py`, `bp_level_table.py` | BP's level by rolling origins and its pooled table |
| `measure_dispersion.py`, `measure_exposure.py`, `measure_heldout.py`, `measure_laplace.py`, `measure_laplace_fs.py` | dispersion by region; POPSVS vs population account; held-out model choice; Laplace uncertainty; Fellner-Schall vs full Hessian |
| `declare_positives.py` (+ `atlas_uf.json`) | derives the documented loci of three declared lens positives from the Atlas da Violencia |
| `mcp_demo.py` | exercises the MCP server with a real client |

---

## 6. Interfaces

### 6.1 CLI (`python -m pegasus_core.cli`, entry `pegasus-core`; 32 commands)

| command | what it does |
|---|---|
| `fit DATASET EVENT BLOCKS... [--years --graph --device --source --cold]` | fit blocks (and their robust refit) and store them, under the job slot |
| `update PLAN [--force]` | bring fits, questions, relations, triage, report up to a plan (hours; takes the job slot and the GPU slot) |
| `links PLAN` | compute the stored link runs a plan reads (`update`'s first step alone) |
| `run [--gpu] [--log f]... -- cmd :: cmd` | run heavy commands one after another under the job slot |
| `coverage [DATASET]` | every column pegasus_data declares and what reads it, or why nothing does |
| `fields DATASET EVENT BLOCK` | the admissible fields of a fitted block |
| `surprise DATASET EVENT NODE [--tier]` | a field's calibration and most surprising cells |
| `scan DATASET EVENT NODE LENS` | one v0 lens on one field (ledgered) |
| `ask DATASET EVENT QUESTION NODE` | one question of one field through every method |
| `survey DATASET EVENT` | the scheduled pass: every field x every question |
| `triage DATASET EVENT [--stale]` | classify open leads and replicate them |
| `relations DATASET:EVENT:BLOCK,...` | stage D across systems |
| `relation DATASET EVENT NODE EXPOSURE...` | distributed-lag relation of an exposure to a field |
| `compare X Y`, `joint FIELDS...` | do two fields move together (scale, lag); where several fields depart together |
| `map [--years --negatives --plan]` | the dependency map of a plan's systems and contexts |
| `cohort DATASET EVENT ROLE YEAR --outcome D:ROLE...` | cohort scan on linked persons |
| `disparity DATASET EVENT NODE` | race disparities of a field by indirect standardisation |
| `alarms DATASET EVENT NODE AS_OF` | place-weeks above the alarm baseline (see section 8: broken) |
| `grid DATASET EVENT NODE` | the planted-signal grid on one field (refitted worlds) |
| `events` | every method of every question against the documented positives (over 10 minutes) |
| `leads [--limit --kind]`, `stories`, `ledger [--family]` | read the register, the stories, the ledger |
| `report [--out --limit]`, `dossier [--out --limit]` | Markdown report with named places; HTML dossier |
| `verdict LEAD_ID confirmed\|artefact\|unknown [--note]` | record a person's verdict on a lead |
| `split-fit`, `split-survey`, `temporal-survey DATASET EVENT LAST` | replication machinery: sides A/E; selection on years up to LAST then test on later years |
| `mcp [--allow-confirm]` | serve the tools over MCP on stdio |
| `gc [--budget-gb]` | evict least-recently-read cache entries (`gateway`, `blockdata`) |

### 6.2 MCP (`python -m pegasus_core.cli mcp`, or `pegasus-mcp`)

Nine tools: `list_blocks`, `list_fields`, `get_expectation`, `search_leads`, `explain_lead`, `place_story`, `method_status`, `ledger_status`, `confirm_claim` (a dry run unless the server has `--allow-confirm` and the call has `spend=true` and a named caller). Resources: `pegasus://architecture` and `pegasus://architecture/{number}` (sections of `ARCHITECTURE.md`, parsed from headings `## N. Title` / `### N.M Title`), `pegasus://evaluation` and `pegasus://evaluation/{slug}` (`EVALUATION.md` and its entries). Session tools default to SIM.DO / death / 2010-2023.

### 6.3 Python

`tools.Session(...)` (section 3.6) is the API; every CLI command is a thin layer over it. `update.run(update.Plan.load(path))` is the programmatic form of `update`. The ledger and register are plain objects (`control.Ledger()`, `leads.Register().current()`).

---

## 7. The pegasus_data surface PegaSUS depends on

Installed editable from `../pegasus_data` (pyproject: `pegasus-data`); `config.data_version()` is its package version, `data_code_version()` adds its commit. Calls, by where they are made (all in `gateway` unless noted):

| area | used |
|---|---|
| top-level `pegasus_data` | `event_types`, `roles`, `describe`, `translate`, `query`, `count_events`, `load_field`, `load_population`, `load_settings`, `memberships`, `proximity_graph`, `municipality_point`, `field_overlap`, `code_structure`, `code_attributes`, `build_lake`, `availability`, `link` |
| semantics | `semantics.event_types` (`event_type`, `events_of`, `event_weights`, `load_event_types`), `semantics.curation.read_yaml` (also in `update`), `decode.admission.admitted` |
| geography | `geography.municipalities()`; memberships (`ibge_immediate_region`, `health_region`, `uf`); the shipped proximity graphs (contiguity default) |
| modelled products | `modelled.read_modelled`: `population_account` (pinned `population-account-2`, others by version), `system_completeness-2`, `population_without_private_coverage` (`sus-dependent-2`), `race_confusion_infant-1` (the women's matrix exists and is not wired) |
| linkage | `linkage.engine` (`load_links`, `links_file` also in `update`, `link_method`, `stored_key`, `side_counts`), `linkage.store`, `linkage.roles.load_roles`, `linkage.identity.record_ids`, `linkage.entities` (`build_entities`, `person_pairs`, `triangles`), `linkage.uncertainty.combine` (in `scans/cohort`) |
| private names | `_request.parse_dataset`, `_request.NothingPublished`, `fields._years` |

Declarations PegaSUS reads, never names: **event types** (the unit that is an event, its classifiers with code trees, marks, weights, strata roles: residence, sex, age, race), **roles** per column (`entity.property`, `kind`, `model` = stratum / mark / dimension / when / where / institution / event_type / link_only / excluded, missing codes, domains, first and last year, draft flag, multi-valued token rules, linkage code groups), **links** (`curation/links.yml`: sides, sensitivity side, padding years; stored runs under `lake/links/`), **context fields** (`curation/fields.yml`: SIDRA/IBGE, INMET, S2iD, ANS, INEP, with `over` denominators and ICD-10 typologies for corroboration), the ICD-10 trees, lists and code attributes (sex and age restrictions). Datasets with event types, 74 on 2026-10-09 (SIM-DO, SIM-DOFET, SINASC-DN, SIH-RD/SP, CIHA, SIA families, 56 SINAN forms); not declared (KeyError): CNES (context only), PNI, SISCAN, SISPRENATAL.

Dependency exceptions: `update` and `scans/cohort` import `pegasus_data` directly, and the gateway uses three private names; the package rule is that only the gateway imports it.

---

## 8. What works, what is partial, what is broken

Measured 2026-10-10 in the capability assessment (machine shared with the overnight SIM job) and by reading the code. "Works" means ran and produced plausible output when exercised.

**Works**
- Data access through the gateway: counts, populations (all sources and modifiers), marks, shares, links, persons, context fields; `ensure_lake` makes a CIHA national year read in 12 s; labelled reads 4x faster than before.
- Fitting: the v1 solver, robust refit, NB-P dispersion, recodings moved within the block; SIM.DO (149 manifests: the chapters and their year ranges, with robust refits), SIH-RD (85), SINASC-DN (28), 31 SINAN diseases (2 each, more for dengue, leptospirosis and SDTA). A killed `update` resumes at the next missing object (checked on one SIM chapter).
- The question pass on a stored fit (`ask`, `surprise`, `compare`): one `ask` on SINAN-CHIK found the 2014 Amapa introduction and the 2015 Bahia wave as top answers; SINAN-LEIV 79 s, 102 answers.
- The ledger (113,069 tests registered before they ran), error control by family, triage with versioned rules (system 17,398, signal 15,167, substitution 6,487, noise 6,146, facility 6,017, untriaged 11,863), `explain_lead` (0.7 s), report and dossier generation, verdicts (annotate, never remove).
- Cohort scans on linked persons (205 leads, all SINASC 2021 births to infant death: known risk gradients), race disparity for births and perinatal deaths, the relation map and the dependency map.
- MCP read path: `search_leads`, `explain_lead`, `ledger_status`, `method_status`, `list_blocks`.

**Partial**
- **Interpretation depth.** Replication tiers across the register: R0 62,745, R1 333, R2 0, R3 0; 93 leads are both triaged `signal` and at least R1. "Another system" corroboration returns "not tested: no independent field holds its codes" for many leads.
- **Method records.** All 16 methods are maturity `v0`: planted-signal power low (cell_excess 0.195, excess 0.155, outbreak 0.066, space_time 0.003, spatial_cluster 0.000), documented events recovered 0 of 9 by the excess methods and 0 of 3 by outbreak and space-time (these stored numbers predate ADR-0035's size-class correction and the 2026-10-10 null-world grid, and were not re-derived); null worlds with findings: group_disparity 60 of 125, institution_step 20 of 20, spatial_cluster 14 of 105. Their leads should not be trusted on their own.
- **Breadth.** The register covers SIH-RD, SINASC-DN, SIM.DO and SINAN-SDTA; the other 30 fitted SINAN diseases have fits and no leads; SIA, CIHA, SIM-DOFET and SIH-SP have plans and no fits at the time of the assessment (the SIM all-chapters run was in progress).
- **Readability.** `leads`, `stories`, `ask`, `surprise`, MCP and `place_story` show IBGE and ICD codes; only the Markdown report names municipalities, and it does not expand ICD codes or state the unit of `effect`. `count_events(by=...)` returns raw codes.
- **MCP** is read-only on the register: no `ask`, `surprise`, `compare`, `cohort`, `records` or pegasus_data query; `list_fields(block="IX")` did not return in about 9 minutes under load (it loads a full session, 4.7 GB resident).
- **Disparity** (`group_disparity`, null rate 0.48) and **institution_step** (1.0) raise findings in null worlds.
- **Triage stability.** The same lead (Fernando de Noronha/PE, SINAN-SDTA cluster) is `noise` in `reports/s6_sinan_sdta.md` and `signal` in a newer report; the rule version is stored but not shown beside the label.
- **Unbuilt combinations** (`NotImplementedError`): monthly grain for the low-rank interaction and for anything but event and code-list counts; NB mean fit with the interaction; refit of an interaction model; Laplace level sweeps for NB; Laplace draws across blocks; the prospective tier for non-counts; B2s on annual blocks; the facility supply term at monthly grain; a grouped link side with a filter or "latest" order.
- **Store hygiene.** `ledger_A` (10,527 parts) and `ledger_T2019` (2,248) are not compacted; fitted-block lookup depends on the exact year range of the request.

**Broken** (the survey run of 2026-10-11 on the old code, `study_toxo_survey9`, 5.0 h against an estimate of 46.5 min; rerun on the fixes as `survey10`)
- **CUDA out of memory poisoned processes.** One error in SIM-DO chapter I's lane failed that lane's next item, and one in the products phase failed 30 later steps. Fixed: `config.cuda_failed` moves the process to the CPU and the step is retried there (`config.on_cpu_if_cuda_fails`).
- **Lanes outgrew their admission.** Three lanes held 42 GB committed on 31.6 GB, and SIM-DO chapter I's robust refit alone held 23 GB; all three paged. Fixed: under memory pressure every lane but the largest is paused (`study._run_items`).
- **SIH chapter I's robust refit ran out of host memory** in `_impute`, at `np.unique` over 160 M entries: recodings move the excess to every sibling leaf's sex-age groups. To be measured on `survey10`.
- **No SINAN lead was corroborated.** Corroboration took a lead's codes from its code tree, and a SINAN agravo's is `*`: "no independent field holds its codes" on every TOXC and TOXG lead, Santa Maria's included. Fixed: the agravo's records' condition codes (`categories_of`, `gateway.condition_codes`); codes at their recorded precision, read by prefix (P37.1 had meant all of P37); foetal deaths read without sex and age (DOFET had held none).
- **State-wide departures read as place signals.** Five of the survey's fifteen stories were whole states in one year (TOXG 2019, the system's first year: 853 of Minas Gerais's places at 1.4×; SIH P37.1 in São Paulo 2010, 645 places at 3.2×). Triage now states such a lead at the state (`explain.triage`, state-wide: its places hold 80 % or more of their states' events in the window, over five places or more; graded consistent, never taken out of the running). The Santa Maria region stays a signal.
- **Findings of uncalibrated methods read as signals; method records judged lenses on the wrong null.** The 60 of 125 null worlds against `group_disparity` were B1 worlds, which keep every place's level: its own B0 worlds give none (TOXG 0 of 40, births 0 of 10; `questions.method_records` now judges each lens on its tier's null). Its 107 survey answers were compositions, read against Brazil's mix (OPEN_QUESTIONS 17), which drawn worlds never held: each now says so. (`institution_step`'s stored 20 of 20 is not a calibration either: no world holds facilities, `harness.GRID_NOT_JUDGED`.) Each finding now carries its methods' null-world record (`uncalibrated`, `reliability`); the report states it on the story's line, and a story made only of such findings ranks after the others. Nothing is removed.
- **A study folder opened only from the directory the study ran in**: its views named its own tables by a relative path, so `export` failed. Fixed: absolute paths, and `export` copies the folder's own tables as files (the survey's exported whole: 21 MB, its folder 3.3 MB).
- **SIA-PA and SIA-BI could not be read beyond a survey**: 175 and 156 GB of files against under 180 GB free. A code-set item whose download would not fit half the free disk is now read as an extract of its codes (`study._extract_or_lake`, `_ensure_extract`; pegasus_data `build_extract`), counted through `gateway.event_counts(codes=)` only for years the extract holds whole.
- **Stratum contexts (ANS, INEP) failed when read by name.** Fixed: their declarations name the rows they are read by (`where`).

Fixed before the survey: persons read nothing through link runs stored before 2026-10-10, which named records by row (pegasus_data `store.load` relabels; merged).

Fixed since the 2026-10-10 assessment: `alarms` (BACKLOG 0.3–0.3c: fit on demand, the as-of year, the field's own codes; SIM IX 0.35% mid-year, 0.20% at a year boundary; week-of-year delays remain, 0.3d); the robust refit's dispersion jump (0.2: the field-level dispersion restores calibration, no product affected).
- **`events`** takes more than 10 minutes (not a quick readout).

---

## 9. Stale, dead and orphaned code

`scripts/codehealth.py` (2026-10-10): 40 modules, 0 import cycles, 9 definitions referenced nowhere: `fields.common_support`, `harness.recovery`, `harness.group_world`, `relations.spectral_factor_model`, `scans.patterns.temporal_stability`, `scans.patterns.spatial_stability`, `scans.utilization.parallel_analysis`, `scans.utilization.rank1_share`, `surveillance.expected_false_alarms`. Beyond that list:
- `scans/patterns.py` and `scans/utilization.py` are imported by no production path (only by `data/` scripts); `relations.spectral_factor_model` likewise by `data/o7_*` scripts; the production relation map uses `bands` + `factor_model`.
- `scans/lenses` v0 lenses are live as methods of questions, not dead.
- Store kind `triage_block` and the `_archive/` registers have no reader or writer in `src/`.
- `data/` holds ~190 experiment scripts that import the package; none is on a production path. `data/handoffs/` keeps only two build logs (the notes moved to `history/2026-10-handoffs/data/`).
- `pegasus_project/pegasus_data_home/` (untracked) is a stray pegasus_data home created by an unrooted call before `config` set `PEGASUS_DATA_HOME`.
- Docstrings in `src/` still cite `ARCHITECTURE §N` of revision 4 and `docs/plans/...` (now under `history/2026-10-plans/`).

---

## 10. Mechanical dependencies of the documents on the code

- `scripts/check_docs.py` fails when: an ADR referenced does not exist, ADR numbers are not contiguous or not in `DECISIONS.md`, an evaluation entry is not in `EVALUATION.md` or a `docs/` link does not resolve, an `OQ-N` is not a row of `OPEN_QUESTIONS.md`, a `scripts/*.py` named in a document does not exist, a module under `src/pegasus_core` is not named (in backticks) in this file, or `CLAUDE.md` and `AGENTS.md` differ.
- `mcp_server` reads `ARCHITECTURE.md` section headings (`## N. Title`, `### N.M Title`) and `EVALUATION.md`; the architecture resources return nothing useful if the headings change shape.
- `config.code_key` hashes function source, so editing a function re-keys exactly the stored artefacts that call it; docstrings and comments are excluded from the hash.
