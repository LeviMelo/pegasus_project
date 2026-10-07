# Review C: ARCHITECTURE.md against the code (pegasus_project, src/pegasus_core), 2026-10-07

Method: every item read against the code (grep and reads of tools.py, monolith.py, solver.py, surprise.py, departures.py,
multiscale.py, relations.py, questions.py, pipeline.py, harness.py, leads.py, control.py, replication.py, cli.py,
mcp_server.py, gateway.py, fields.py, marks.py), not against docs/architecture_coverage.md.
States: INT = integrated (built, reachable through Session/CLI, feeds the next stage); STA = standalone (built, only scripts
or feeds nothing); PAR = partial; ABS = absent. "Reach" notes say how an item is reached. The reachable chain that actually
produces the register: `pegasus-core run` -> pipeline.fit_block (count blocks, default model) -> Session.survey_questions ->
Lead(kind="answer") -> Session.triage -> relation_survey (kind="relation") -> report.write.

## §1 Purpose and principles (P1-P16, §1.1 stages)

| item | state | evidence |
|---|---|---|
| fit one model of "normal Brazil" from all the data | PAR | count blocks of SIM, SIH, SINASC, SINAN only: pipeline.fit_block; plans/default.yml; no SIA, CIHA, CNES events |
| serve to people and agents | PAR | cli.py (28 commands), mcp_server.py (9 tools, no scan/compare/ask/decompose); no UI |
| phase 4 prospective surveillance | PAR | tools.Session.alarms, surveillance.py (epi_week, delays, nowcast, alarm); not in pipeline, no weekly fit, no register |
| P1 expectation first | INT | every lens reads Surprise (surprise.py); share_excess, joint_excess read mu too |
| P2 events and marks modelled | PAR | counts INT; marks only via scripts/fit_marks.py -> marks.fit_chapter (not in CLI, Session or pipeline) |
| P4 estimands declared | PAR | questions.QUESTIONS (6 estimands); E_i, across-system, race, adjusted estimands absent |
| P5 minimum relevant effect | PAR | lenses.minimum_effect / MINIMUM_EFFECT_BY (a constant table, ADR-0026, the per-system table §8.4 says to withdraw); departures.excess uses relevance_z; cell_excess relevance; Bayesian step P(rr>theta0) |
| P7 every strength learned/measured | PAR | tau by LAML (solver); but explain.py constants THETA, DRIFT, SURGE, POP_BREAK, RATE_BREAK, ABSORB, FAC_K, FAC_SHARE, FAC_VOLUME, MIN_EXCESS, NEW_CATEGORY_ALARM=5, KS 0.03 remain hand-set |
| P8 observed stays observed, modelled typed with uncertainty | PAR | gateway.population (account-2/3/4 sigma); default is POPSVS, no uncertainty |
| P9 validation characterises | PAR | harness.grid/surface/event_record built; not attached to leads (see §10) |
| P11 established method first | PAR | per-question: Efron two-group, STEM, Chen-Liu, factor analysis; BaySTDetect, BYM2 exceedance, DLNM-as-search absent |
| P12 departures are model terms; posterior statements | PAR | only departures.step is posterior (bayes_select, Newton 2004). cell_excess = empirical-null BH + lfdr; excess/excess_trend = STEM peak p-values; no model term delta in an NB offset model; leads carry interval=None |
| P13 structure exploited; speed budgeted | INT/PAR | solver.StructuredNewton, Supernodal Cholesky; scripts/bench.py is not a CLI command; benchmark "on every change" is by practice |
| P14 recording measured, never dissolve | PAR | kappa, +confusion built; conserved-level fields exist (fields.Registry.conserved) but are read by nothing (see §8.6); coding-regime term ABS |
| P15 race is an axis | PAR | race-stratified blocks only (gateway.population(race=), monolith.assemble race=); no race axis in G, none in departures/relations/pipeline/CLI |
| P16 one stage one computation | PAR | monolith.robust and tiers B2 inside stage B still carry detection-adjacent logic; harness holds both statistical and epidemiological checks; thresholds per system survive (lenses.MINIMUM_EFFECT_BY, explain constants) |
| §1.1 stages A-F each have one object | PAR | A gateway; B surprise/monolith; C departures/multiscale/questions + v0 lenses; D relations; E explain/replication/corroborate; F report/leads. v0 lenses still dispatched beside the questions (tools.Session.scan) |

## §2 Repositories and boundary

| item | state | evidence |
|---|---|---|
| rule 1: gateway is the only importer of pegasus_data | PAR (violated) | cli.py:234 (`from pegasus_data import geography`, joint command) and report.py:19 (geography.municipalities) import pegasus_data directly; matrix says "fixed" |
| rule 2: meaning belongs in pegasus_data | PAR | gateway._date_sql / _residence_sql (the §13 interim); marks/casemix reading in gateway._mark_frame own SQL |

## §3 Objects

| item | state | evidence |
|---|---|---|
| structure: tree | INT | gateway.code_structure("ICD10"), fields.Registry |
| structure: list | PAR | fields.Registry.list_fields / LIST[...] across-block fields via surprise._surprise_across; not walked by Session.fields, so never surveyed; no list term in the model |
| graph | PAR | graphs.graph: contiguity, contiguity01, distanceH, knnK, careflow. No health-region, REGIC graph; no graph mixture; one graph per block |
| population: POPSVS, account-2/3/4/6, hybrid | INT | gateway.population, monolith.default_population |
| population: SUS-dependent variant | PAR | gateway.sus_share, `+sus` modifier; opt-in, 2021-23 share held for earlier years |
| completeness by system | PAR | gateway.completeness, `+kappa`; opt-in, SIM/SINASC UF-year only |
| aggregates incl. mark accumulator states | PAR | gateway.event_counts, mark_moments, share_moments; computed by own DuckDB SQL, not pegasus_data's logmoments aggregate |
| records and linked persons | PAR | tools.records (module function over private gateway._records); scans/cohort.py by scripts only; link_draws not wired |
| lattice cell (u, t, g), age = 33 classes (single years 0-19) | PAR | monolith.BlockData; ages are POPSVS's 18 bands (gateway.age_edges, monolith line 260); the 33-class single-age lattice of §3.2 ABS; race axis ABS |
| institution cell (f, t) with catchment | PAR | facility.institution_lattice, Session.institutions; SIH annual only; no pair estimand |
| Field (kind, law, exposure, signature, provenance) | PAR | fields.Field has id, kind, law, support, signature; no exposure, no provenance members; kind is always "count" except share/mark fields built outside Registry |
| scan/test/hypothesis; ledger entry written before run | PAR | control.Ledger.register before every lens and departure; NOT for relations.relation_map, tools.compare, tools.relation_survey, Session.relation, Session.explain_away/decompose (no ledger call anywhere in relations.py) |
| lead | PAR | leads.Lead; KINDS = residual, subset, pattern, relation, cohort, observation, structural, answer; produced: residual, subset (tools._lead), answer (survey_questions), relation (relation_survey) only |

### §3.3 ICD ontology

| item | state | evidence |
|---|---|---|
| tree to category, nested groups | INT | fields.Registry, monolith._carrier |
| code attributes (sex restriction, age limits, underlying-cause eligibility) | INT | monolith._admissible via gateway.code_attributes; group_cells -> structural zeros in Monolith (_emask/_smask) |
| seven concept lists: as fields | PAR | Registry.list_fields; on demand only (see §3 list) |
| list effects theta_L in the predictor | ABS | no list component in Monolith.components |
| external-cause axes (intent, mechanism) | INT | fields._external_cause_axes; Registry.walk includes XX axis members, so surveyed |
| conserved-level fields CONS[...] | STA | fields.Registry.conserved; reachable by node name; not walked, not read by lenses, triage or leads |
| typed relations (sequela, dagger-asterisk, exchange pools) as data | ABS | pools hard-coded: Registry.conserved (R00-R99, Y10-Y34), replication.conserved_level, corroborate.RULES |
| ICD-9 tree and bridge | ABS | no ICD-9 anywhere in src |
| ICD-O, procedure-diagnosis compatibility, notifiable-disease map | ABS | |

### §3.4 Race

| item | state | evidence |
|---|---|---|
| race as axis of G / race terms in eta / disparity estimand | ABS | grep "race" finds it only in gateway.py and monolith.py (assemble args) |
| race-stratified blocks, births by mother's race, infant deaths with C(k|j) exposure | PAR (v0) | gateway.population(race=), `+confusion`, _recorded_exposure, declared_ratios; python-only (Session(source={"race":..})), no CLI, not in pipeline |
| women's matrix, SIH/SINAN/adult race recording, unknown share m | ABS | |
| 2000 undeclared imputation, flat band spreading (pegasus_data side) | outside this repo | |

## §4 Monolith: model

| item | state | evidence |
|---|---|---|
| 4.1 kappa completeness, N^(SUS) | PAR | gateway `+kappa`/`+sus` source strings; opt-in; not factors of mu; config.population_source / PEGASUS_POPULATION |
| 4.2 theta_e, f_p(a,s), g_e(u), h_e(t) | INT | components th_grp, th_cat, f_all, f_grp, s_/v_ place, h_all, h_grp (monolith.__init__) |
| 4.2 low-rank interaction psi omega tau | PAR | Monolith(rank=R), _enable_interaction, solver.ix_sweep; off by default, no Laplace draws; Session(rank=) python-only; pipeline.fit_block and CLI fit never set rank; no model-choice loop |
| 4.2 race terms | ABS | |
| 4.3 tree prior (horseshoe) | PAR | `prior="horseshoe"` (_update_horseshoe), not default; one sigma per level per top branch is not the structure (per carrier group iid) |
| 4.3 BYM2, learned rho, PC priors | ABS | grep BYM2/PC finds nothing in code; BYM with two taus (s_*, v_*) |
| 4.3 graph mixture; graph and rho reported per field | ABS / PAR | no mixture; spatial_share in manifest per block |
| 4.3 population-scaled iid precision | ABS | structures.iid unweighted |
| 4.4 log-normal mark | PAR | monolith.MarkModel; reached by scripts/fit_marks.py |
| 4.4 count mark (NB moments) | PAR | monolith.CountModel (_CellMark), same reach |
| 4.4 binary share (beta-binomial) | PAR | monolith.ShareModel, same reach |
| 4.4 bounded score (cumulative logit, Apgar) | ABS | |
| 4.4 case-mix and institution effect | PAR | marks._shrink_facilities, gateway._mark_frame (procedure group); marks.SPECS = los, cost, death, icu (SIH) only; PESO by hand |
| 4.5 supply term | PAR | facility.attach_supply, Session(supply=True), annual only, applied after fit |
| 4.5 institution lattice | PAR | facility.institution_lattice, Session.institutions; no crossed effects in likelihood |

## §5 Estimation and computation

| item | state | evidence |
|---|---|---|
| 5.2 phi_extra hierarchy (field, macro, state) | INT | surprise.DISPERSION_LEVELS, place_year_phi |
| 5.3 exact structured Newton (arrowhead, kriging, Schur) | INT | solver.StructuredNewton.assemble/factor/solve_full, fit_mean; v0 Newton-CG gone from the default path |
| 5.3 interaction and marks on v1 | INT within Monolith | solver.ix_sweep, _mark_factors |
| 5.4 LAML strengths | INT | Monolith._score_taus, solver.scoring/traces; selected inversion not adopted (documented) |
| 5.5 exact Laplace draws | STA | laplace.Posterior, solver.draws; only Expectations(laplace=S); Session never passes laplace, CLI none |
| 5.5 N2 nested-level sweeps | PAR | Posterior.sample(sweeps=), _level_sweep; in progress |
| 5.5 marginal variances by selected inversion | ABS | (documented as not built) |
| 5.6 top model (all chapters, shared terms) | ABS | grep finds no code |
| 5.6 model-choice loop (rank, graph, prior) by held-out/LAML | STA | monolith.heldout + scripts/measure_heldout.py only |
| 5.8 benchmark and budgets | STA | scripts/bench.py (+ many bench_*.log); not a CLI command |
| exact reference (MCMC/HMC) | ABS | OPEN_QUESTIONS only |

## §6 Tiers, calibration, surprise

| item | state | evidence |
|---|---|---|
| B2 (exact 2x2 Newton), B2s | INT | surprise.refit_place*, tier B2s needs month grain |
| BP, BPA | INT | Expectations.prospective, prospective.py; Session.train/survey(prospective=); questions/survey_questions retrospective only |
| N1 noise structure (gamma frailty, ARMA(1,1) copula, spatial share) | INT | surprise.Noise, noise_structure, with_noise; read by departures, multiscale, relations.innovations |
| noise dependence across causes | ABS | Noise covers periods and places only (stage B text says causes too; D handles it) |
| randomised PIT, KS criteria, per-field place-year component | INT | surprise.randomised_pit/calibration/place_year_phi |
| flag a miscalibrated field, exclude from pair scans | PAR | tools.relation_survey and tools.dependency_map exclude; scans/pairs.within does not; lens leads carry calibrated flag |
| surprise flags (denominator, recording, small support) | PAR | surprise.py: DENOMINATOR, CALIBRATION, NO_INFORMATION, NEW_CATEGORY; RECORDING declared "not yet served", no small-support flag |

## §7 Scans

| item | state | evidence |
|---|---|---|
| 7.0 cell excess (two-group, Efron) | INT | departures.cell_excess, questions "excess" |
| 7.0 excess at unknown scale (STEM multiscale) | INT | departures.excess, multiscale.peaks/GraphSpectrum, questions excess/step/trend/cluster |
| 7.0 shape attribution (Chen-Liu) | INT | departures.attribute, questions._shape |
| 7.0 step (Bayesian change point, Bayesian FDR) | INT | departures.step, _step_posteriors, bayes_select; question "step"; the only true posterior-based model |
| 7.0 trend: BaySTDetect mixture | ABS | question "trend" has only the multiscale hinge (excess_trend) |
| 7.0 spatial cluster: BYM2 exceedance | ABS | question "cluster" = excess_level (STEM) + v0 spatial_cluster |
| 7.0 group disparity: shrunk place x group interaction | ABS | question "group" = v0 lenses.group_disparity (per-unit G2) |
| 7.0 race disparity | ABS | |
| 7.0 observation fields | INT | departures.share_excess, question "share", Session.scan("share_excess") |
| 7.0 posterior of effect with interval, P(effect > min), expected FDP <= q | PAR | only step reports posteriors; findings carry effect point + p; Lead.interval=None for answers (tools.survey_questions) |
| 7.0 ladder of supports | INT | departures._ladder, scans/scales.py |
| 7.1 v0 lenses (outbreak, change_point, space_time, spatial_cluster, trend_divergence, group_disparity) | INT | scans/lenses.py via Session.scan/survey; SURVEY_PLAN; hand-set minimum_effect table |
| 7.2 subset scan: score, LTSS, alternation, Gumbel null, recursion | INT | scans/subset.py (Scanner, null, scan); lenses use it |
| 7.3 scan across fields | PAR | departures.joint_excess, tools.joint, CLI `joint`; ledgered but findings not admitted to the register, not in pipeline |
| 7.4 interaction patterns (psi, omega, tau) read as leads | ABS | no code reads Monolith ix factors as leads |
| 7.4 CP-APR across blocks, stability | STA | scans/patterns.py (fit, stability); no caller in tools/cli/harness (only data/patterns_across.py) |
| 7.5 E_b, E_b|Z, Dutilleul/MSR | PAR | scans/pairs.between via maps.dependency_map (CLI `map`); result to pegasus_home/maps and ledger, never the register |
| 7.5 E_w lag | STA | scans/pairs.within; scripts/data only |
| 7.5 E_i | ABS | |
| 7.5 across systems log-ratio field | ABS | |
| 7.5 rank/HSIC versions | PAR/ABS | pairs.statistics(rank=True) exists, never reported; HSIC absent |
| 7.5 joint relation model (factors + lags + one FDR) | INT | relations.innovations/bands/lagged/factor_model/relation_table/relation_map -> tools.relation_survey (Lead kind "relation") -> pipeline "relations"; `pegasus-core relations` |
| 7.5 direct vs shared driver (graphical lasso, StARS) | INT | relations.direct_relations inside relation_map |
| 7.5 national/macro-regional course relations | INT | relations.course_relations |
| 7.5 distributed-lag term (DLNM-style, RW2) | PAR | relations.distributed_lag, Session.relation, CLI `relation` (with reverse negative control); not feeding the register |
| 7.5 shared-component (BYM2) model; endemic-epidemic (hhh4) | ABS | |
| 7.5 negative-control outcomes/exposures as guards on every relation | PAR | only `reverse=` on Session.relation; relation_map has none |
| 7.5 overlap rule (0.05) in stage D | ABS | relation_survey/relation_map never call fields.testable/overlap (fields.overlap has no caller in src outside map_inputs); nested ICD groups (levels=("group",)) enter the same factor model |
| 7.6 dependency map (two layers, TreeBH, utilization factors, negatives) | PAR | scans/maps.py, tools.dependency_map, CLI `map`, harness.map_negatives; standalone from register; sparse+low-rank graphical model replaced by relations.direct_relations |
| 7.7 triage classes, rule versions, facility | INT | Session.triage (reads answers, since 2026-10-07), explain.triage/RULES, facility.Facilities; CLI `triage`, pipeline |
| 7.7 triage thresholds replaced by measured models | ABS | constants in explain.py (THETA, DRIFT, SURGE, FAC_K ...) |
| 7.8 cohort scans | STA | scans/cohort.py (scan, fit_one); no Session.cohort, no CLI, no pipeline |

## §8 Error control, replication, weighting, recording

| item | state | evidence |
|---|---|---|
| 8.2 Benjamini-Bogomolov across families | INT | control.bogomolov in survey, survey_questions |
| 8.2 Bayesian FDR | PAR | departures.bayes_select only in step |
| 8.2 LOND on confirm | PAR | control.LOND/Reserve, Session.confirm(_many), mcp confirm_claim (--allow-confirm); never spent on a real claim (per matrix; reserve guard present) |
| 8.2 weights by power (IHW) | ABS | control.optimal_weights = Roeder-Wasserman prior weights; applied only in lenses.outbreak |
| 8.3 temporal (later years) | PAR | Session.train/temporal_confirm, CLI `temporal-survey`; not in pipeline |
| 8.3 spatial (other jurisdictions) | PAR | Session.spatial_confirm -> replication.audit; accepts only trend_divergence unit claims (tools.py: `estimand == "trend_divergence" and scale`); no CLI; not for question answers |
| 8.3 corroboration (S2iD, SINAN, SIH) | PAR | Session.corroborate, corroborate.RULES; no CLI, not in pipeline |
| 8.3 evidence grades tested/bound/consistent | INT | explain.GRADES in triage and replication.audit |
| 8.3 event split for sizes | PAR | Session.honest_sizes, CLI split-survey |
| 8.3 reserved period + LOND stream | PAR | control.RESERVED_PERIODS/ReservedPeriod/Reserve; guard in Session.__post_init__ |
| what pipeline's triage does for replication | PAR | Session._replicate = half-splits of the evidence (the form ADR-0015 withdrew), not the independent-unit tests |
| 8.4 minimum detectable effect on every result | PAR | harness.surface computes mde; no lead carries it |
| 8.4 minimum effect as P(effect>min) only | PAR | lenses.MINIMUM_EFFECT_BY per-system table still gates leads |
| 8.6.1 conserved-level fields standard, lead read at both levels | STA | Registry.conserved only; Lead has no `conserved` member |
| 8.6.2 kappa, race confusion, coding-regime term, facility term | PAR | kappa/confusion opt-in; coding-regime term ABS; facility = triage + supply term |
| 8.6.3 graded explanations / re-scope to conserved level | PAR | replication.conserved_level/audit rescope (unit trend claims only); triage v0 classes for answers |
| 8.6.4 changed rule re-applied to stored state | INT | explain.RULES hash; Session.triage(stale=True); verdict `superseded` |

## §9 Leads, ledger, use

| item | state | evidence |
|---|---|---|
| Lead fields: effect + interval | PAR | leads.Lead.interval is None for every lens and answer lead (tools._lead, survey_questions) |
| Lead: replication R0-R3 | PAR | control.replication_tier(kinds_of(x)); pipeline produces halves-based kinds only |
| Lead: robustness / triage class + grade + rule version | INT | Lead.robustness["triage"] |
| Lead: conserved reading | ABS | no field |
| Lead: method record (maturity, power, FDR on null worlds, MDE) | PAR | tools.method_record = hard-coded METHOD_EVIDENCE table (tier, theta0, calibrated, evidence text); no maturity, power or MDE; kind="answer" leads get no method record at all (survey_questions) and `calibrated=True` is asserted |
| Lead: provenance | INT | Lead.provenance code_version, data_version |
| Lead kinds pattern, cohort, observation, structural | ABS | KINDS declared; nothing constructs them |
| rank = evidence x effect x replication | PAR | Lead.rank = -log10(q) * |effect| * (1+tier): certainty not interval-based, relevance absent |
| 9.3 survey per data update | PAR | pipeline.run is incremental by data/code version, started by hand (CLI `run`); no trigger; fits count blocks only, no rank/month/marks/prospective; surveillance not in it |
| API expected(slice), surprise(field,tier,scope) | PAR | Session.expected/surprise take node and tier, no scope; mcp get_expectation takes places/years |
| API scan, subset_scan | PAR | Session.scan (any lens); no `subset_scan` entry; space_time/spatial_cluster are lenses |
| API compare | PAR | tools.compare, a module function (not Session), unledgered, CLI `compare` |
| API explain_away, decompose | STA | Session methods only |
| API records | PAR | tools.records (module function, private gateway._records) |
| API confirm | INT | Session.confirm(_many), mcp confirm_claim |
| API train, temporal_confirm, spatial_confirm, corroborate, honest_sizes, retier | INT in Python; CLI only for train/temporal/honest (split-*, temporal-survey) |
| MCP exposure | PAR | mcp_server.py: list_blocks, list_fields, get_expectation, search_leads, explain_lead, place_story, method_status, ledger_status, confirm_claim, 3 doc resources; none of ask, scan, compare, relations, decompose, alarms, records; "paused" |
| agents (LLM loop) | ABS | |

## §10 Validation

| item | state | evidence |
|---|---|---|
| 10.1 documented events held out | INT | harness.POSITIVES (30 declarations), harness.event_record, CLI `events`; scripts data/real_events*.py |
| 10.2 Moran spectral negatives, series shifts | INT | harness.negative_scores/lens_world/pair_negatives, MoranBasis |
| 10.3 designed grid (loci x shapes x sizes x duration x sparsity), refitted worlds | PAR | harness.grid/grid_design/grid_world/surface, CLI `grid`; shapes spike, step, trend, group only (GRID_SHAPES); seasonal shift and lagged response ABS; default GRID_LENSES lists only v0 lenses (new methods need `lens_names=`); relation planting only in data/o7_factor_*.py |
| 10.3 posterior calibration (90 % exceedance), bias of effect | ABS | harness.absorbed measures absorption only |
| 10.3 power surface -> MDE and weights on results | PAR | harness.surface; not read by tools/leads/control |
| 10.5 no gate; every lead carries record | PAR | gate gone; record is the static METHOD_EVIDENCE table; answers lack it |
| 10.6.1 SBC | STA | scripts/sbc.py, sbc_chain.py |
| 10.6.3 held-out deviance, forecasting-tier calibration | STA | monolith.heldout, scripts/measure_heldout.py |

## §11 Code

| item | state | evidence |
|---|---|---|
| module map (every module listed exists) | INT | all of config, fields, structures, graphs, monolith, solver, marks, laplace, surprise, prospective, relations, questions, report, pipeline, surveillance, multiscale, departures, control, replication, facility, corroborate, leads, harness, store, tools, mcp_server, cli, gateway present. departures/relations sit at top level, not under scans/ as the text says (the table lists both) |
| dependency direction downward, no cycles | PAR | tools imports everything; harness imports tools; departures imports scans.lenses lazily; scans/subset_old.py is a local-excluded dead copy (.git/info/exclude), referenced only by data/perf |
| artefacts and homes | INT | store.py, config.home(); key carries package version (documented departure) |
| inv 1 gateway only | PAR | cli.py:234, report.py:19 |
| inv 5 test in ledger before run | PAR | violated by relation_map/relation_survey/compare/Session.relation |
| inv 6 null preserves dependence, no MC floor | PAR | N1 + STEM nulls; v0 B0 spatial cluster / group nulls known to fail |
| inv 7 minimum effect not zero | PAR | |
| inv 8 miscalibrated never in a pair scan | PAR | enforced in relation_survey and dependency_map, not pairs.within |
| inv 9 overlap > 0.05 never tested | PAR | enforced in maps only; stage D bypasses it |
| inv 13 no question excluded for power | INT | Session.fields scans every field with an event |
| inv 14 no tuning on documented events | PAR | scripts/data real_events_v9..v12 iterate on the events (the doc's own note); lens thresholds table |
| inv 15 only tested explanation removes a lead | INT | Session.triage status logic |

## §12 Roadmap packages (state in code)

| package | state | evidence |
|---|---|---|
| O1 solver | INT | solver.py default for all models |
| O2 settle (rank, tree prior, kappa/SUS) | PAR | each built and opt-in; defaults unchanged; no model-choice loop |
| O4 ICD | PAR | see §3.3 |
| N1 noise | INT | surprise.Noise |
| N2 uncertainty | PAR | Posterior.sample(sweeps); not reachable from Session |
| O6 departures | PAR | cell excess, STEM spike/step/trend, shape attribution, Bayesian step, share, joint, questions registry INT; trend (BaySTDetect), cluster, group departure models ABS |
| O5 characterise | PAR | grid, negatives, SBC script built; weights, seasonal and lagged plants, posterior calibration open |
| O7 relations | PAR | joint band factor model + lags + direct + courses INT; shared-component, endemic-epidemic, distributed-lag-as-confirmation wiring ABS; planted-relation tests are data/ scripts |
| O8 interpretation | PAR | rule versions, triage reading answers INT; recording terms, coding regimes, conserved readings, independent-unit replication for answers ABS |
| O3 race and ages | PAR (v0) | race-stratified blocks; axis, single ages ABS |
| O9 breadth | PAR | SINAN agravos and SINASC in plans/default.yml; SIA/APAC, CIHA, SIGTAP, SIH marks nationally, SIH-SIM link ABS |
| O10 use and surveillance | PAR | report.py, pipeline.py, surveillance.py exist; ranking by relevance, dossier, trigger, weekly alarms ABS |

## §13 Maturity table and departures: code vs table

- §13.1 says "departure models: not built" (§7.0 row) and "relation models: not built": both stale. Code has cell_excess, excess (STEM), step, share_excess, joint_excess, attribute; and relations.py (factor model, direct, courses).
- §13.1 "validation: v0 ... power curves of four lenses, a gate": stale; grid replaces them.
- §13.2 row 4.2/5.4 "no top-model sharing" stands. Row 11.4 (pair scan exclusion) is now partly closed (relation_survey, dependency_map).
- Missing from §13.2 (code departs from the text, unrecorded): ledger skipped in stage D; overlap rule skipped in stage D; question-answer leads without method record/interval; the 33-class single-age lattice (§3.2) not built; list effects; Lead.conserved; per-system minimum-effect table (§8.4 says withdrawn when N1 lands, still in lenses.MINIMUM_EFFECT_BY); Dutilleul in §7.5 text vs MSR/Moran implementation (pairs.MoranBasis).

# The 15 largest structural gaps, ranked by centrality to the purpose

1. §7.0/P12 Stage C is not a model: only the step is a posterior model; cell excess and STEM are empirical-null/p-value procedures, trend (BaySTDetect), cluster (BYM2 exceedance) and group interaction departure models are absent, so leads are not posterior statements with interval and P(effect > minimum) (answers carry interval=None).
2. §8.3/§8.6/§9.1 Stage E is thin for the leads the pipeline now makes: question answers are triaged by v0 threshold rules and half-split replication (the ADR-0015-withdrawn form); independent-unit tests (spatial_confirm is trend-only, corroborate, temporal_confirm, reserve) and the conserved-level re-scope are not wired to answers or to `run`.
3. §9.1/§10.5 Every lead should carry its method's measured record (power, MDE, FDR on null worlds, maturity): the grid computes it (harness.surface) but leads get a hand-written table, and `answer` leads (the production leads) get none, with calibrated=True asserted.
4. §3.4/§4.1/§4.2/O3 Race is not an axis: no race in G, no race terms, no disparity estimand, no recorded-race model beyond v0 infant/birth blocks; "Brazil's inequalities are the first thing a reading must show" is unmet at every stage.
5. §5.6 No top model / cross-block sharing and no model-choice loop (held-out/LAML exists only as scripts); consequently §4.2's interaction (rank) is off everywhere, the cross-block factor of §7.5 has no top model to absorb, and rank/graph/prior are never chosen by the system.
6. §8.6/§3.3 Recording as measurement: conserved-level fields exist but nothing reads them beside leads (Lead has no `conserved`); coding regimes, exchange pools as typed data, list effects theta_L and ICD-9 bridge are absent, so artefact-versus-event (the stage-E question) rests on v0 constants.
7. §7.5 Stage D bypasses invariants: no ledger entry (relation_map, compare, relation_survey, Session.relation) and no overlap rule, nested ICD groups included; plus shared-component and endemic-epidemic models, per-relation negative controls, and E_i are absent.
8. §9.3 Use: the "survey per data update" is a manual `run` that fits count blocks only (no marks, month grain, rank, prospective, surveillance, replication tests, laplace) and writes a Markdown table; no trigger, no dossier, no verdicts; MCP omits scan/ask/compare/relations/decompose and is paused.
9. §4.4/§3.1/§3.2 Fields from roles: only counts (and hand-named marks) become fields; marks (los, cost, icu, death, PESO) fit only through scripts, bounded-score marks absent, SIA/APAC, CIHA, SIGTAP, CNES events never read, Field has no exposure/provenance.
10. §10.3 The bench cannot yet price stage C/D: no posterior-calibration or bias outputs, no seasonal or lagged plants, default GRID_LENSES excludes the new departure methods, relation planting lives in data/ scripts, weights across fields (IHW) absent.
11. §5.5/N2 Posterior uncertainty of levels is not accepted and not reachable: exact Laplace draws and level sweeps exist (laplace.Posterior) but Session/CLI/pipeline never request them; selected inversion, MCMC reference (§10.6.2) absent; SBC is a script.
12. §3.2 Lattice: ages are POPSVS's 18 bands, not the 33 classes with single years 0-19; the account's single ages are summed back; paediatric epidemiology and the race x age profile of §4.2 cannot exist on it.
13. §4.3/§5.3 BYM2 with PC priors, graph mixtures, population-scaled iid, horseshoe-by-branch: the model's spatial prior is two-tau BYM (the ridge the solver steps around), one graph per block; care-flow graph exists but no mixture or per-field selection reported.
14. §7.4/§7.8/§7.3 Lead kinds pattern, cohort, structural, observation never produced: psi omega tau patterns unread, CP-APR and cohort scans are scripts, joint scan across fields does not enter the register.
15. §2/§11.4 Boundary and invariant leaks: cli.py:234 and report.py:19 import pegasus_data; tools.records calls private gateway._records; per-system minimum-effect table (lenses.MINIMUM_EFFECT_BY) and explain.py constants persist against P7/P16 though §8.4 says they are withdrawn when N1 lands.

# Coverage matrix errors (docs/architecture_coverage.md, dated 2026-10-05 with later patches)

Stale or wrong against the code:
1. Row "4.2 low-rank interaction Σψωτ: NB" and gap #3 "not built": built (monolith.Monolith(rank=), _enable_interaction, solver.ix_sweep, ADR-0021). Same for "4.3 horseshoe NB / gap 4" (`prior="horseshoe"`), "7.4 interaction-factor patterns NB: no interaction", "6.1 interaction never part of a tier: moot", "§13 row 4.2 low-rank not built".
2. Rows 5.3/5.4 "truncated Newton-CG, Fellner-Schall BM; §13: Poisson-Fisher diagonal" and "5.3 Laplace by perturbation draws": the code is v1 exact Newton + LAML + exact draws (solver.py, laplace.py); v0 is gone.
3. Row "6.2 flagged field excluded from pairs and maps: NB, maps never read it": tools.dependency_map calls maps.exclude_miscalibrated and relation_survey excludes miscalibrated fields; only pairs.within lacks it. Row inv. 8 "BU" is right, the 6.2 row contradicts it.
4. Row "§2 rule 1: fixed 2026-10-05": cli.py:234 and report.py:19 now import pegasus_data (new leaks); tools.records uses private gateway._records.
5. Row "§3 records ... no API: cohort() and records() absent" and "§9 API compare, subset_scan: NB": tools.compare and tools.records exist (module functions); cohort still absent; "subset_scan" has no such name.
6. Row "phase 2 needs: care-flow graph NB; graphs.py has no care-flow kind": graphs.py has `careflow` (graphs._careflow). The Data coverage table's "care flows no" is also stale.
7. Row "7.1 observation lens" and "7.3 BU" are right, but "9.1 kinds: relation ... NB" is stale (relation and answer kinds are produced); the true gap is pattern/cohort/observation/structural.
8. Row "7.5 Dutilleul SS (ADR-0005)" vs ARCHITECTURE §7.5 still prescribing Dutilleul's modified t: the matrix is right about the code; the architecture text is stale (not a matrix error, but the pair is inconsistent).
9. Counts table (116 BM / 12 BU / 46 P / 41 NB / 1 SS = 216) and "§13 Departures (all 17 rows open)": ARCHITECTURE §13.2 now has 19 rows; counts predate revisions 2-3 and N1/O6/O7.
10. "Data coverage" and gap #10: SINAN is no longer "DENG and LEPT only" (SINAN agravos fitted 2026-10-07, plans/default.yml lists SINAN-SIFC); "read-only 4 systems" stale; SINASC "XVII monthly 2010-14" etc. not rechecked.
11. "Scan coverage" / "Default survey" tables describe SURVEY_PLAN admission counts under a retired rule (self-flagged), and gap #9 (admission rule ADR-0022) is superseded by ADR-0028; yet it remains in "The ten most consequential gaps" as live. Gaps 1-4 as ranked (kappa/SUS, race as blocks, interaction, horseshoe) are not the current top; the matrix's own revision-3 list ranks N2 first, but N2 is not a structural gap (it is accepted-in-progress) while stage-E/F integration gaps are absent from the ranking.
12. Missing from the matrix entirely: unledgered stage D, the overlap rule skipped in stage D, answer leads without method record or interval, spatial_confirm limited to trend_divergence, pipeline replication being half-splits, Session never passing laplace, marks/rank/month absent from pipeline, `Registry.conserved` unread, `Lead` having no `conserved`.
14. Row "5.5 numerics: the fit is float64 throughout (document says float32 on GPU)" is still true but the §5.7 text now says "v0 runs float64"; the matrix labels it BM while the float32 path is ABS.
