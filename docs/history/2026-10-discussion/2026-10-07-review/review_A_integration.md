# Integration audit: pegasus_core (2026-10-07, read-only)

Method: AST import graph of src/pegasus_core (top-level and lazy imports), grep of Session/CLI call sites, AST scan of scripts/, data/*.py for `pegasus_core` imports, and reading of ARCHITECTURE §1.1, §7, §9, §11.1, §13. "Session" = tools.py `Session` plus module functions in tools.py. "pipeline" = `pegasus-core run` (pipeline.py). Consumers are real importers or readers of outputs, not mentions in docs.

Verdict in one line: stages B and the C-methods-through-`questions` chain are wired end to end (fit -> Session.scan -> questions -> register -> triage -> report). Stage C v0, stage D v1 screens, stage E independent-unit replication, stage F alarms/joint/compare, marks, patterns and cohort are separate islands. The register is the only join, and half of what writes to it is not read by what reports from it.

## 1. Modules

Status key: integrated = on the fit->report path or consumed by a stage that is; standalone = reachable but its output feeds nothing; duplicate = a second mechanism for a job done by another; dead = not imported by src, CLI or MCP.

| module | purpose | § | reachable from | consumed by | status |
|---|---|---|---|---|---|
| config | homes, versions, seeds | 11.3 | everything | all | integrated |
| store | content-addressed Parquet/npz artefacts | 11.3 | all | gateway, monolith, surprise, graphs, replication, corroborate, maps, pipeline, harness, tools | integrated |
| gateway | the one door to pegasus_data (A) | 2, 11.1 | Session | fields, monolith, surprise, graphs, facility, replication, scans.scales, surveillance | integrated (not the only importer: cli.py:234, report.py:19 import pegasus_data) |
| fields | field registry, tree walk | 3.2 | Session.fields, CLI fields | tools, surprise, map_inputs | integrated |
| structures | GMRF precisions | 4 | monolith | monolith, graphs | integrated |
| graphs | place graphs | 3.2 | Session.edges, pipeline.fit_block | monolith, replication, lenses, pairs, tools | integrated |
| monolith | the model, assemble, Monolith.fit, robust | 4-5 | CLI `fit`, `run` (pipeline.fit_block), Session | surprise, replication, laplace, prospective, marks, tools | integrated |
| solver | block-arrowhead Newton, LAML, draws | 5.3-5.5 | monolith | monolith, laplace | integrated |
| laplace | Laplace posterior of a count block | 5.3 | monolith/surprise | surprise, prospective | integrated |
| prospective | BP predictive (mixture PIT) | 6.1 | surprise | surprise | integrated |
| surprise | tiers, PIT, calibration, N1 noise, virtual cube (B->C interface) | 6 | Session.surprise, CLI surprise | all of C, D, E | integrated (hub) |
| multiscale | heat kernels, STEM peak testing | 7.0 | Session.spectrum | departures, relations; monolith.py:1941 (stage B reaches into C) | integrated |
| departures | departure models: cell_excess, excess*, step, share_excess, joint_excess, attribute | 7.0 | Session.scan, tools.joint, questions | questions (via scan), tools | integrated for scan methods; `joint_excess` standalone |
| questions | question -> methods registry, merge into answers | 7.0, plan 2026-10-07 | Session.ask/survey_questions, CLI ask/survey, pipeline | tools, harness.event_record | integrated (current stage C front) |
| scans.lenses | v0 lenses: outbreak, change_point, space_time, spatial_cluster, trend_divergence, group_disparity | 7.1 | Session.scan/survey, CLI survey --lenses, grid, MCP confirm | tools, questions (as 4 of its methods), replication, harness, marks | duplicate (v0, still half of the methods) |
| scans.subset | subset scanner and its null (N1-aware) | 7.2 | via lenses | lenses, harness | integrated |
| scans.subset_old | stale copy of subset.py before the noise/cache edits | 7.2 | nothing | nothing (subset_old <- []) | dead |
| scans.scales | municipality/region/state partitions | 7.1 | Session.scales | lenses, departures ladder | integrated |
| scans.explain | triage rules, explain_away, decompose | 7.7 | Session.triage/explain_away/decompose | tools, replication, facility | integrated (rules still keyed to v0 estimand names, see B6) |
| scans.patterns | CP-APR structural patterns | 7.4 | nothing in src/CLI/MCP; 1 data script | nobody | dead |
| scans.cohort | cohort scan | 7.8 | nothing in src/CLI/MCP; data/cohort_infant, readout_cohort* | nobody | standalone |
| scans.pairs | E_b/E_w pair screens, Moran basis | 7.5 | tools.dependency_map, CLI `map`; scripts | maps, harness, utilization | duplicate (stage D v1 screen) |
| scans.maps / map_inputs / utilization | dependency map of SIM, SIH, SINASC and contexts | 7.6 | tools.dependency_map, CLI `map` | tools, harness; output stored (kind maps), read by nobody | duplicate + standalone |
| relations | stage D: factor model per band, directness, course relations, distributed lag | 7.5 | tools.relation_survey, tools.compare, Session.relation; CLI relations/relation/compare, pipeline | tools | integrated (relation_survey), standalone (compare/relation print only) |
| replication | independent-unit tests, sizes, `test_prospective`, THETA | 8.3 | Session.side/train/temporal_confirm/confirm; CLI split-*, temporal-survey; MCP confirm | tools, explain-adjacent | integrated for v0 leads only |
| corroborate | S2iD/SINAN/SIH independent fields, place-set null | 8.3 | Session.corroborate only | tools | standalone (no CLI, MCP, pipeline caller; only data/repl_corroborate*.py) |
| facility | event cube by facility, supply term | 4.5, 7.7 | Session.triage, surprise(supply) | surprise, marks, tools | integrated |
| marks | SIH mark models (LOS, cost, death, ICU), facility effects, mark triage | 4.4 | scripts/fit_marks.py only | nothing in src | dead for the package (script-only) |
| control | ledger, FDR/BH/Bogomolov, splits, LOND, reserve | 8, 9.2 | every scan | nearly all | integrated |
| leads | Lead, Register, stories, ranking | 9.1 | Session, CLI leads/stories, MCP | tools, report, replication, mcp | integrated |
| report | stage F Markdown from the register | 9.3 | CLI report, pipeline | cli, pipeline | integrated, but reads only kinds "answer" and "relation" |
| pipeline | one plan: fit, questions, relations, triage, report | 9.3 | CLI run, fit | cli | integrated (the only end-to-end route) |
| surveillance | epi weeks, nowcast, alarms | 12 phase 4 | Session.alarms, CLI alarms | gateway (lazy), tools | standalone (prints; no leads, not in pipeline/report) |
| harness | planted worlds, grid, positives, event_record | 10 | CLI grid/events, Session indirectly | cli, scans.map_inputs, tools(depmap) | standalone (writes store kind harness, read by nobody in src) |
| mcp_server | tools over MCP | 9.3 | CLI mcp, pegasus-mcp | cli | integrated but narrow (known pause); exposes no ask/report/relations/alarms |
| cli | the `pegasus-core` command | 9.3 | entry point | nothing | integrated |
| tools | Session API | 9.3 | CLI, MCP, scripts | cli, mcp, pipeline, harness | integrated (1291 lines, hosts two survey mechanisms) |

## 2. Integration breaks, ranked

1. **Two stage-C surveys write to one register, and only one is read by stage F.** `Session.survey` (SURVEY_PLAN of v0 lenses, tools.py:476-546, kinds residual/subset) and `Session.survey_questions` (kind answer, tools.py:428-474) both call `register.add`; `report.report` keeps only `kind == "answer"` and `"relation"` (report.py:48, 56), so every v0 lead, including all replication work attached to them, never reaches the reading list.
2. **The independent-unit replication of §8.3 is not part of the pipeline.** `pipeline.run` stage E is `Session.triage(register=answers)` (pipeline.py:142) whose replication is `_replicate`, the in-sample halves of the same data (tools.py:752-760, "splits of the evidence, not refits"), the very scheme replication.py's docstring says cannot replicate (shared frailty); `temporal_confirm`, `spatial_confirm`, `honest_sizes`, `corroborate`, `retier` are reachable only via CLI temporal-survey/split-* on v0 leads or scripts (tools.py:822-965; corroborate has no caller in cli.py/mcp_server.py/pipeline.py).
3. **Method records do not flow into leads.** Answer leads are built with `calibrated=True` and no `method=` (tools.py:466-471), while `METHOD_EVIDENCE`/`method_record` (tools.py:63-98) are hand-typed strings for v0 lenses only; the harness grid and `event_record` write results to the store (harness.py:825) that no module reads back, so §9.1's "method: power, FDR on null worlds, minimum detectable effect" is never filled for the current methods and `uncalibrated()` never demotes an answer (leads.py:143).
4. **The characterisation harness measures the old methods by default.** CLI `grid` defaults to the six v0 lenses (cli.py:157-158, harness.py:494 GRID_LENSES) while pipeline answers come from cell_excess/excess/excess_step/step/excess_trend/excess_level; the new methods are characterised only by data/o6_*grid scripts and `event_record` (a positives-only record, `pegasus-core events`).
5. **Two stage-D mechanisms; the old one is a dead end.** `tools.dependency_map` (scans.maps/pairs/map_inputs, CLI `map`, tools.py:1156-1192) and `relations.relation_map` (CLI relations/compare/pipeline) both answer "which fields move together"; the map's edges go to store kind `maps` (tools.py:1191) and are never read, never become leads, and are absent from the pipeline and report.
6. **Stage E rules still speak the v0 vocabulary.** `explain.triage` applies its residual-category coding-practice rule only to estimands `trend_divergence`/`change_point` (explain.py:336) and `replication.THETA` knows only v0 lens names (replication.py:156-157), but answer leads carry estimand = question id ("excess", "step", "trend", ...), so those rules silently skip every answer.
7. **The reserve-period claim route cannot confirm the current methods.** MCP `confirm_claim` accepts only `lens in replication.THETA` (mcp_server.py:264; THETA = outbreak, change_point, space_time, spatial_cluster, trend_divergence), i.e. none of the departure models or questions.
8. **Fitting has two entry points with different settings.** `pipeline.fit_block`/CLI `fit` call `model.fit(log=...)` with defaults (pipeline.py:70-72); the production path is scripts/fit_blocks.py with `warm="auto"`, `outer=40`, `mean_tol=1.0`, `PEGASUS_SOURCE` (marks, code lists), grain and device (fit_blocks.py:26-34); 31 data/scripts files construct `monolith.Monolith(...)` themselves. `pegasus-core run` cannot reproduce a monthly or mark fit.
9. **SIH marks (§4.4) exist only as a script.** `marks.py` (268 lines) is imported by no module in src and no CLI/MCP command; only scripts/fit_marks.py reaches it, so mark leads never enter the register.
10. **Stage D/F outputs that are not leads.** `tools.joint` (tools.py:1247), `tools.compare` (1262), `Session.relation` (246), `Session.alarms` (378) return rows to the CLI and stop; none is registered, ranked, triaged or reported, so a person's `joint`/`compare`/`alarms` result has no life in the register.
11. **Lead kinds declared but never produced.** `leads.KINDS` has pattern, cohort, observation, structural (leads.py:30) but only answer, residual, subset, relation are ever constructed (tools.py:466, 549, 1233); `scans.patterns` and `scans.cohort` are therefore unconnected to §9.1 and to Session (STATUS lists both as dormant).
12. **Ranking differs between the register and the report.** `Lead.rank` = -log10(q)*|log effect|*(1+tier) (leads.py:81) is what the register sorts by, but `report.report` sorts each family by `x.q` (report.py:50), so stage F does not use the §9.1 rank (effect and replication are ignored).
13. **Layering inverted in places that ARCHITECTURE §11.1 forbids.** gateway lazily imports surveillance (gateway.py:1159) while surveillance imports gateway; stage-B `Monolith.robust` imports `multiscale` (monolith.py:1941, off by default, `footprints=()`), `place_year_phi` from surprise (monolith.py:1729) while surprise imports monolith; `scans.map_inputs` imports harness (map_inputs.py:183); cli.py:234 and report.py:19 import pegasus_data outside gateway.
14. **A stale code copy ships in the package.** scans/subset_old.py (430 lines) is a pre-edit copy of subset.py (no neighbourhood cache, no `noise=`), imported by nobody.
15. **Persistent-object layout has drifted from §11.3.** The register and ledger are directories of part files (leads.py:94-107, control.py:44), not `leads.parquet`/`ledger.parquet`; pegasus_home holds ~14 `leads*` and ~13 `ledger*` variants (scripts' private homes), plus unreferenced objects (`triage_block/`, `readout_sim_agg.parquet`, `vital_account_2022.npz`, `cohort_infant_2021*.json`, `monolith_centring1_2026-10-06/`) written only by data/ scripts.

## 3. Duplicates (both named, current marked)

| job | old / alternative | current | note |
|---|---|---|---|
| detect departures | v0 lenses `outbreak`, `change_point`, `space_time`, `spatial_cluster`, `trend_divergence`, `group_disparity` (scans/lenses.py) | departure models `cell_excess`, `excess*`, `step`, `share_excess` (departures.py) | `questions.QUESTIONS` lists both side by side as "methods" (cluster and group questions are v0-only; `space_time` and `trend_divergence` are in no question, so the pipeline never runs them) |
| pass over all fields | `Session.survey` (SURVEY_PLAN, thread pool, prospective mode, scales) | `Session.survey_questions` (serial, per question, answers) | survey_questions is current for retrospective; survey is the only route for prospective (`prospective=t0`), split/temporal replication (CLI split-survey, temporal-survey) and scripts (7 data scripts) |
| grouping and reading leads | `leads.stories` + CLI `stories` + MCP `place_story` | `report.report` + CLI `report` | stories group v0 leads by place; report groups answers by family; different keys, different sort |
| relations | `tools.dependency_map` over `scans.pairs/maps/map_inputs/utilization` (E_b, E_b\|Z) | `relations.relation_map` via `relation_survey`/`compare` | relations is current; the map is a screen kept by ADR-0013/0022 |
| relation of an exposure | `Session.relation` (relations.distributed_lag) | `relations.relation_map` | arguably complementary (pairwise confirmation, §7.5), but two CLI verbs `relation` and `relations`/`compare` |
| fit a block | `pipeline.fit_block` (CLI fit, run) | `scripts/fit_blocks.py` | script is the one actually used for production fits |
| subset scanner | scans/subset_old.py | scans/subset.py | subset_old unreferenced |
| replication | `Session._replicate` (in-sample halves, tiers R1-R2 via triage) | `replication.py` independent units (temporal/spatial/corroborate) | only the first is in the pipeline |
| validation on documented events | data/real_events*.py (v9, v9b, v9c, v10, v11, v12: six near-identical copies with a hand-typed EVENTS list) | `harness.event_record` over `harness.POSITIVES` (CLI `events`) | event_record is current; the scripts re-declare the five events instead of reading POSITIVES |
| reading the register | data/read_survey_questions.py (hand-rolled Markdown) | `report.report` | script predates/duplicates the report |
| triage + report run | data/triage_answers_v1.py | `pipeline.run` stage E-F | same two calls, plus a Counter |
| per-dataset survey | data/{sih_survey,sih_full_survey,survey_v1_sim,survey_v1b_sim,sinan_run,...}.py | `pegasus-core run` / `survey` | 7 scripts call `.survey(` directly |

## 4. Stranded in data/ and scripts/

data/ has 210 `.py` files (31 build `Monolith` directly; none import `pipeline` except by plan files in plans/default.yml). The 20 most recent (mtime 2026-10-07 05:05-08:34) group as:

| group | files | what they do | belongs in the package as |
|---|---|---|---|
| N1 noise diagnostics | noise_recovery, noise_bias_diag, noise_clip_bound, step_null_diag | declare rival explanations and test N1's (kappa, rho, delta) recovery and the step method's null failures on refitted worlds | a `harness` recovery check (SBC-like: `scripts/sbc.py` is the sibling) run by CLI; their findings are already absorbed into `surprise.noise_structure` |
| multiscale step null/footprint grids | o6_step_null_v2, o6_step_null_v3, o6_footprint_grid | planted/null worlds through `harness.grid` for `excess_step` with a declared criterion (<= 1 of 10 null worlds with findings) | `pegasus-core grid --lenses excess_step` (CLI default lacks the new methods; a `--criterion` on the null worlds) |
| real-event scoring | real_events_v9b, v9c, v10, v11, v12, shape_attribution_real, event_record_sim | stage C methods against documented events; v10-12 add shape attribution; event_record_sim is the 10-line caller of `harness.event_record` | already `harness.event_record` / `pegasus-core events`; v9-v12 are superseded copies; shape attribution on real series is a missing `events` column |
| questions survey and its reading | survey_questions_v1, read_survey_questions, triage_answers_v1 | `Session.survey_questions` on SIM I, IX, X, XX and SIH I, X; hand-written Markdown reader; triage + report | `pipeline.run` + `report.write` (CLI run/report); the reader duplicates report.py |
| stage D on SINAN | o7_relations_control, o7_sinan_relations, o9_sinan_families | negative control and positive controls (same disease across SIM/SIH/SINAN), fitting every SINAN agravo as block "*" | `pipeline.run` with the SINAN plan; o9 loops `monolith.Monolith` over agravos directly instead of using `pipeline.fit_block` for a list of agravos (a `--all-agravos` plan entry); the control is a `harness` negative for `relation_map` |

scripts/ (17 files): `fit_blocks.py` (production fits; should be `pipeline.fit_block` with source/grain/device/warm), `fit_marks.py` (marks; should be `pegasus-core fit --mark` or a `marks` command), `sbc.py`, `measure_*.py`, `gate_eb.py`, `declare_positives.py` (derives loci the harness cannot, `harness._area` returns None for these), `heavy.py` (detach/launch), `warm_gateway.py`, `mcp_demo.py`. Of these only `check_docs.py` and the `measure_*` files are legitimately scripts; the rest are capability that the CLAUDE.md rule says belongs in src behind the CLI.

## 5. Persistent objects: who writes, who reads

| object (under pegasus_home/) | written by | read by |
|---|---|---|
| `monolith/<key>` (params npz, manifest) | `Monolith.save` (monolith.py:1989, 2035); scripts/fit_blocks.py, pipeline.fit_block | `Monolith.load`, `Expectations`, replication.py:97, `tools.fitted`, mcp_server.py:106; warm-start search monolith.py:1044 |
| `blockdata/<hash>` | `monolith.assemble` (monolith.py:179) | same function |
| `structures/` | monolith.py:2611 | monolith.py:2606 |
| `graphs/` | graphs.py:66, scans.pairs.py:97 (two writers, different keys) | graphs.py:38, pairs.py:94 |
| `gateway/` (aggregates, delay_counts, facility cube) | gateway.py (about 30 sites), facility.py:62 | gateway.py, facility.py |
| `surprise/` (field x tier tables) | surprise.Expectations (surprise.py:376, 425) | surprise.py:367 |
| `calibration/` | tools.calibration_of (tools.py:191) | tools.py:187 (map, MCP) |
| `leads/` (part files) | Session.survey, survey_questions, triage, side/temporal/spatial/honest_sizes, relation_survey (default Register, ignores `split_home`) | CLI leads/stories/report, MCP, pipeline triage selection, report.py, replication, triage |
| `ledger/` (part files) | every scan via control.Ledger (`register_many`/`complete_many`, cohort.py, pairs.py, lenses, departures) | `ledger_status`, `Reserve`/LOND state (control.py:324-387), CLI ledger, MCP |
| `ledger_A/` and `split_sides/` | Session.side("A"), replication.py:63 (event sides) | replication.py:51, Session.honest_sizes |
| `corroborate/` | corroborate.py:96-130 | corroborate.py:88-120 |
| `maps/` (MapInputs, utilization tensor, `map_edges`) | maps.py:73, utilization.py:38, tools.py:1191 | maps.py:79, utilization.py:26; `map_edges` never |
| `harness/` (grid, event_record, depmap, gate_eb results; `harness/grid_ledger`) | harness.record (harness.py:825), scripts/gate_eb.py | nobody in src (docs/evaluation entries are written by hand from these) |
| `pipeline/` (done markers) | pipeline._mark | pipeline._done |
| unreferenced: `triage_block/`, `readout_sim_agg.parquet`, `vital_account_2022.npz`, `cohort_infant_2021*.json`, `monolith_centring1_2026-10-06/`, ~14 `leads*`/~13 `ledger*` variants | data/ scripts (cohort_infant, vital_account, readout_*, triage_*) with their own homes | the same scripts |

## 6. Straight reading

- The architecture's spine (A -> B -> surprise -> questions -> register -> triage -> report) is real and runs through `pipeline.run`. Everything else was built on that spine as a branch and never reattached.
- The recurring pattern is "built new beside old": v0 lenses (kept as methods and as the prospective/replication route), the pair/map screens beside relations, `survey` beside `survey_questions`, `stories` beside `report`, in-sample triage replication beside independent-unit replication. In each case the old half still carries a capability the new half lacks (prospective mode, replication tiers, confirm, calibration records), which is why neither can be retired. The fix is to move that capability onto the current object, not to add a third path.
- `tools.py` is the junction (1291 lines, 3 sets of verbs); `monolith.py` (2613) and `solver.py` (1809) are large but internally coherent B code.
