# survey_3: computational cost and configurability of pegasus_core (read-only audit, 2026-10-07)

Repo HEAD a6b8303 (19:13). Paths are under `src/pegasus_core/` unless stated. Line numbers are from the working tree as read.
Evidence used: `data/logs/prof_questions.pstats` (cProfile, 908 s, one field), `data/logs/s1_sih_x.out`, `pegasus_home/update/*/manifest.json` mtimes, `data/logs/survey_questions_v1.out`, `data/logs/o6_v6.out`, docs/evaluation/*. Nothing was run except `pstats` on the existing profile file.

Scale of the field profiled: `scratchpad/prof.py` = SIH-RD chapter X, group J09-J18, U=5,570 places, T=14, fits stored, `Session.ask` once per question (7 questions, 12 methods). Profile was taken at about 19:08-19:23, i.e. partly before a6b8303 landed (see c.2).

## (a) Entry points

Common to all rows: any read of a count block goes `Expectations.model` (surprise.py:164) -> `Monolith.load` -> `monolith.assemble` -> **`robust_stored`** (surprise.py:170; see c.1). "Fit" below means `update.fit_block` (update.py:79).

| entry | default work | implicit triggers | knobs | hard-coded |
|---|---|---|---|---|
| `fit` (cli.py:30) | one cold/warm fit per block, 2010-2023 | assemble (cache miss 7-10 s, SIH monthly 467 s); warm-start search over stored fits (monolith.py:1052) | blocks, years, graph, device | `outer=40, mean_tol=1.0, warm="auto"` update.py:91 |
| `update PLAN` (cli.py:41 -> update.py:176) | per system: fit missing blocks; **question pass over every field of every block**; then for each declared reader (measure, each composition VALUE, link, interval, mentions, flows, classifier chapters) a separate fit + a separate full question pass (update.py:205-249); disparity per node; relation_survey; triage + corroboration per system; optional `confirm_last` | robust refit of every block touched (c.1); fits of missing blocks (update.py:189-197) and of the train years (`_later_years` update.py:152-173, which also repeats the whole question pass); per-reader `tools.Session` -> its own spectrum (27 s) + scales (8 s); report | plan keys: `years, systems[dataset,event,blocks|all,levels,measures,compositions,links,intervals,classifiers,mentions,flows,disparities], questions, relations, triage, report, graph, corroborators, confirm_last, contexts`; `--force` | everything below; no per-field, per-method, per-replicate or per-step selection; `known` keys update.py:73 |
| `survey` (cli.py:88) = `Session.survey_questions` (tools.py:402) | every field with events (chapter, group, category, members, axes, lists: fields.py:174) x 7 questions x 12 methods; BB per (question, block); register write at the end | memo of B1/B0 surprise per field (tools.py:425); `harness.method_records()` parses every stored grid at the end (tools.py:442) | `--blocks`, `--levels` (CLI); API also `questions`, `q` | q=0.05; all questions; all methods; all fields of a level |
| `ask` (cli.py:100, tools.py:396, questions.py:138) | one question on one field, all its methods at q/k | B1 (and B0 for cluster/group) surprise rebuilt each call when called alone (memo owner, questions.py:144) | question, node, q, limit; API `**kw` forwarded to EVERY method's `scan` (a kw one method lacks becomes a silent "failed" entry, questions.py:176) | -- |
| `scan` (cli.py:77, tools.py:283) | one lens | surprise at the lens's tier; `share_excess` -> `_prepare_grid`+`_expected_total` (tools.py:583, 626); `institution_step` -> unmemoised B1 rebuild (tools.py:141) | lens, tier, API `**kw` per lens (replicates, rate_ratio, scales, footprints) | LENS_TIERS tools.py:42 |
| `surprise` (cli.py:61), `fields` (cli.py:51) | one field's tier / the field list | model load + robust | tier | -- |
| `triage` (cli.py:133, tools.py:495) | every open lead of the dataset: `explain.triage` + `_replicate` + facility tally | `_data(chapter)` assemble, `_facilities` cube, B1 surprise per node, one ledger parquet file per test (control.py:94) | `replicate`, `stale` (CLI); API `facility` | facility on by default |
| `corroborate` (tools.py:919; called only from update.run, update.py:279) | every "signal" lead x every independent field holding its codes: permutation null; leads with p<0.01 redrawn | linked sources read stored link runs only (gateway.py:1388) | API `replicates, refine_p, refine_replicates, only_signals, q`; plan `corroborators` | 4999 / 0.01 / 99999 (tools.py:920-921); pure-Python set growing (corroborate.py:296-320, 20 retries) |
| `temporal-survey` (cli.py:365), `temporal_confirm` (tools.py:797) | train session: full second question pass on years <= last, then `prospective` per node | fits on train years (update.py:166 path); BP load/extrapolate per node | `last`, `level`, `blocks` | level="state" |
| `split-fit`/`split-survey` (cli.py:342/354), `honest_sizes` | side-A fit + full question pass + side-E sizes | fits on side A | blocks | -- |
| `spatial_confirm` (tools.py:851) | `replication.audit` per trend-divergence unit claim (profile draws=4000, explain.py:645) | `Strata.from_gateway` (SIM/SIH strata read, tools.py:842) | `source` | draws 4000 |
| `alarms` (cli.py:213, tools.py:340) | BPA tier for one field + delay counts | `prospective(node, year-1)` fit/load; `gateway.delay_counts` x2 | as_of, recurrence, weeks | -- |
| `relations` (cli.py:119) / `relation_survey` (tools.py:1236); in update.py:258-267 | for each (system, blocks): load every block, B1 surprise of every group-level field with >= 2,000 events, then `relation_map` (9 bands, factor model K=16, 200 EM iterations, 999 phase surrogates) | models of ALL listed blocks incl. robust (c.1); fresh `Session` per entry, no reuse of survey surprises; GPU used without a slot | CLI `min_events, q, years`; plan `relations` bool | lags=2, K=16 relations.py:530; iterations=200 :197; replicates=999 :608; levels from plan |
| `compare` (cli.py:246, tools.py:1317), `joint` (cli.py:228, tools.py:1292) | two / n fields at B1 | model loads, B1 builds | q, lags (API) | K=2; replicates=100 |
| `map` (cli.py:387, tools.py:1180) | dependency map of all fitted fields of `plans/default.yml` + 20 contexts | `map_inputs.build` on first use (stored key v3); `calibration_of` per count field (a B1 build, ~15 s, stored after); two Moran bases | `years`, `negatives` (0), `health_only` | plan path fixed "plans/default.yml" (tools.py:1181); worlds 20/draws 200 in harness.py:273,336 |
| `cohort` (cli.py:261, tools.py:1349) | one link side, one year: all declared compositions as attributes, Rubin over draws | `gateway.cohort_records` -> `stored_pairs` (refuses if no stored run) | link, side, year, draws, q | draws=20; GLM iterations=50, outer=15 (scans/cohort.py:52) |
| `disparity` (cli.py:274, tools.py:1402) | 1 reference + all other races (gateway.RACE) | **fits any missing race block** (tools.py:1429-1432) | node, reference, races (API), q | all races |
| `grid` (cli.py:150, harness.py:704) | 5 kinds x 4 shapes x 4 worlds (+4 null) = 84 worlds; each: `refit` + grid_world draw + **all 12 methods** | `refit` (fit_mean 30 it) per world, B1 build per world | kinds, shapes, lenses, worlds, null_worlds, replicates, minimum_effects, tiers | thetas (5), `ThreadPoolExecutor(8)` harness.py:663; replicates only reach space_time/spatial_cluster |
| `events` (cli.py:200, harness.py:897) | every method of every built question on every documented positive | session + model per dataset, `questions._shape` per matching finding | `years` | all positives (POSITIVES + verdict_positives) |
| `dossier/verdict/report/stories/ledger/leads` | read the register/ledger | `ledger.table()` reads every part file once (thousands of files) | limit, out | -- |
| MCP tools (mcp_server.py:119-262) | read-only; `get_expectation`/`list_fields` build surprises; `confirm_claim` spends the reserve | model load + robust | per tool | -- |
| scripts/ | `fit_blocks.py` (fit_block, env PEGASUS_DEVICE/SOURCE/FIT_COLD), `bench.py` (flags in RUNBOOK), `sbc.py` (replicates 100, draws 99), `warm_gateway.py`, `heavy.py` | -- | argparse/env | -- |

## (b) Hard-coded cost parameters

Documented/measured column: M = measured with a number in docs/evaluation or a code comment, D = documented as a choice, none = neither.

| file:line | parameter | role | doc |
|---|---|---|---|
| update.py:91 | `outer=40, mean_tol=1.0` | every fit | M (fit-throughput) |
| monolith.py:980 | `outer=25, inner=30, tol=0.02` | Monolith.fit defaults | D |
| monolith.py:1021-1022 | outer Newton floor `max(mean_tol, 1000.0)` loglik units; env PEGASUS_OUTER_TOL_FRAC | steps per outer | M (comment: IX 67->59 s) |
| monolith.py:1406 | scoring probes 8 (scale >= 1e5) else 16; env PEGASUS_SCORING_PROBES | strengths' Hutchinson probes | M (comment: VII -0.17/death at 8) |
| monolith.py:1463 | PEGASUS_LAML_TOL default "1.0" | outer stop | M; **RUNBOOK says 0.1** |
| solver.py:921, 979, 1204, 1470 | probes 32 / 16 (chunk 16) / fit_mean iterations 30 / ix probes 32 | solver | M |
| monolith.py:1721 | refit `iterations=30, loglik_tol=1.0` | robust rounds, grid worlds, held-out | M (absorption) |
| monolith.py:1726-1727, 1939 | robust `rounds=2, trim=0.005, min_expected=0.05`, store tag `v: 9` | implicit robust refit | M ("about 15 minutes per chapter on the CPU", evaluation 2026-10-07 robust-expectation) |
| monolith.py:101-109 | `ASSEMBLY=1`, NEWBORN_SHARE .5, GEO_POOL .01 | assembly | D |
| departures.py:159 | excess `footprints=(1..512)` = 10 scales, `replicates=40` | multiscale peaks (spike/step/trend) | none (cost) |
| surprise.py:962 | `spatial_structure` footprints (2..256) = 8; lines 1002-1004: 8 x O(U^3) float64 products | N1 spatial part, inside every peaks call | none; profile: 38 s per call |
| multiscale.py:197, 89, 144, 96 | peaks `replicates=40`; scale bisection 40 steps x `footprint` 22 ms; GPD `exceedances=250`; contrasts min_past=3/min_years=2 (m = 14 spike, 10 step, 11 trend, 1 level) | peaks | none |
| surprise.py:695, 905; departures.py:461 | `place_year_phi rounds=3`; `_central_kappa` 41-point grid + bounded search; `share_excess` 31-point grid + bounded search | per surprise build / per share field | none |
| scans/lenses.py:84, 92, 125 | spatial_cluster / space_time `replicates=200`, `k=30` | `cluster` question | D |
| scans/subset.py:304-305, 437, 401 | `MIN_POSITIVE=20`, `MAX_REPLICATES=2000` (null re-drawn up to 10x), `max_subsets=20`, batch chunk 8 | scan null is adaptive: the declared 200 is a floor | D |
| departures.py:300, 328 | `_laplace_glm iterations=12`; step `min_years=2, min_past=3, prior_change=.05`, one GLM per start x per support | step | none |
| scans/lenses.py:268 | `_past_course iterations=8` per start | change_point | none |
| scans/scales.py:51; tools.py:297 | ladder = municipality + region (~500) + state; `cell_excess` and `step` each call `surprise.lift` per support | supports | D |
| departures.py:234 | `attribute`: 4T candidates, <= 2T add steps, pinv per step | every finding's shape | none |
| tools.py:920-921; corroborate.py:312, 330, 366 | corroborate `replicates=4999`, `refine_p=0.01`, `refine_replicates=99999`; 20 connected-set retries; chunk 2e7 | stage E | D (comment) |
| explain.py:645; replication.py:776 | `profile_test draws=4000`; `simulate_profile draws=300` | spatial_confirm | none |
| relations.py:530, 197, 324, 608 | `lags=2, K=16`; EM `iterations=200`; 9 band edges; `replicates=999` | stage D | none |
| tools.py:1236, 1317, 1292, 1349 | `min_events=2000`; compare K=2; joint `replicates=100`; cohort `draws=20` | stage D / cohort | D |
| harness.py:491-494, 663, 704; cli.py:153 | `GRID_KINDS`(5) x `GRID_SHAPES`(4) x `worlds=4` (+`null_worlds=4`), `GRID_THETAS`(5), `ThreadPoolExecutor(8)` | grid | M (o6_v6.out) |
| harness.py:273, 336; scans/utilization.py:17 | pair_negatives `draws=200`; map_negatives `worlds=20`; parallel_analysis `worlds=200` | depmap negatives | none |
| scripts/heavy.py:34, 60-62 | threads = cpu//2, slots 6, survey slots 2, min free 4 GB | scheduling | D (ARCH 5.7) |
| multiscale.py:36; relations.py (factor_model `dev`) | `cuda` chosen whenever available, no device argument, no GPU slot | GPU use | none |
| gateway.py:507, 564, 1297 | `max_download=8 GiB`, `allow_partial=False` | implicit downloads | none |
| store.py:45 | `np.savez_compressed` for every array artefact | blockdata write 2.5 s each | none |
| control.py:94 | one parquet file per ledger register/complete call | ~2 files per test | M (thousands of files take minutes) |

Environment knobs that exist: PEGASUS_HOME, PEGASUS_DATA_ROOT, PEGASUS_POPULATION(_ROOT), PEGASUS_SUPPLY (config.py), PEGASUS_COMPUTE_LINKS (gateway.py:1381), PEGASUS_OUTER_TOL_FRAC, PEGASUS_SCORING_PROBES, PEGASUS_LAML_TOL (monolith.py), PEGASUS_MCP_LEDGER, scripts: PEGASUS_DEVICE/SOURCE/FIT_COLD, heavy: PEGASUS_HEAVY_*/SURVEY_SLOTS. **Documented but absent:** `--lenses`, `--replicates`, `PEGASUS_SURVEY_WORKERS` (RUNBOOK.md:23, evaluation 2026-10-05 survey-throughput); `survey` has only `--blocks/--levels` (cli.py:88). No code path sets torch/BLAS thread counts; only `heavy.py` does, through env, when someone wraps the job.

## (c) Hidden expensive defaults

1. **Reading a count block runs a robust refit if none is stored.** surprise.py:170 `robust_stored()` (monolith.py:1936): 2 rounds, each a `refit` (fit_mean up to 30 Newton steps) plus `m.expected` for every leaf (monolith.py:1778-ish loop `np.stack([m.expected(...) for e in range(E)])`) and a trimmed-dispersion search. About 15 min per chapter (evaluation 2026-10-07). Triggered by `Session.fields`, `surprise`, `update.run`'s "fitted already?" probe (update.py:189-191), `relation_survey`, `fields`/MCP, harness sessions. It is keyed by the settings tag including `"v": 9` (monolith.py:1939): bumping the tag or the rounds re-runs it for every chapter. `cli fit` does not create it. In `s1_sih_x.out` lines 11-28 six robust fits (E-sized, 5k-49k flagged cells each) ran inside the first group, between its `cluster` and `share` questions: that is the old `_expected_total` summing every chapter's model (see 2).
2. **A share question needed every chapter.** Before a6b8303, `Session._prepare_grid` assembled all 20 SIH chapters and `_expected_total` loaded all 20 models (each robust-refitted): profile `_prepare_grid` 280 s (20 `_data` calls), `_expected_total` 23 s. Now the annual path reads cached `event_counts` and one "*" fit (tools.py:583-660); if "*" is not stored, `update.fit_block(..., "*")` is a silent cold fit inside a question (tools.py:638-640). Monthly and "*"-classifier sessions still take the all-blocks branch (tools.py:610-624).
3. **Assembly cache is keyed on the bytes of gateway.py.** `_assembly_code` (monolith.py:189-196, line 195 `Path(gateway.__file__).read_bytes()`); gateway.py was touched in 31 of 263 commits since 2026-10-04. Each edit orphans all `blockdata` (658 entries, 4.2 GB in pegasus_home); the next read re-assembles (profile: 19 misses, `_assemble` 142 s + `put_arrays` 49 s compressed writes). Model fits are NOT keyed on it (BlockData.key, monolith.py:406), so only time is lost, not fits.
4. **`update` steps are keyed on the git commit.** `_key` (update.py:137-138) includes `config.code_version()` = short HEAD + "+dirty" (config.py:49-51, 87-95). Stored keys in `pegasus_home/update/` carry `a2968c5+dirty`; HEAD is a6b8303, 20+ commits later, so a rerun of `plans/s1_sih_x.yml` redoes the 8 h question step even with no code change that matters. "Redoing only what changed" (update.py module docstring) is "redo everything not done at this exact commit".
5. **All-or-nothing steps.** `survey_questions` writes the register only after the last field (tools.py:464) and `update` marks the step done only after the whole system (update.py:204-210, 241-247). A failure at hour 7 loses the 7 h. No per-field or per-block checkpoint of answers, and `Expectations.surprise(cache=True)` (surprise.py:356, store option) is never used on the survey path.
6. **Every level, every question, no information gate.** `fields()` (tools.py:92) keeps every node with >= 1 event ("no field is left out for low power"); with `levels=None` that is chapter + groups + all categories. Each field pays the 7-question battery (4 multiscale peaks calls) regardless of its events. Only `relation_survey` has a floor (2,000).
7. **Per-reader multiplication in `update.run`.** `measures/compositions/links/intervals/mentions/flows: all` each add readers; compositions add one reader per category VALUE (update.py:210-213), each with own fits for every block and its own 7-question survey (update.py:238-247).
8. **Downloads and decodes behind a gateway read.** `event_counts` on a cache miss calls `pg.count_events(..., max_download=8 GiB, allow_partial=False)` (gateway.py:505-507); same in `_records`, `raw_event_counts`. Key includes data version and `_df_key`; no log line announces a download.
9. **Linkage.** Until a6b8303 a missing linked-field run launched `pg.link(..., method="probabilistic")` ("hours per year", gateway.py:1379-1381); now refused unless `PEGASUS_COMPUTE_LINKS=1`. Callers: `linked_counts`, `cohort_records`, plan `links`, corroboration of linked sources.
10. **GPU without a slot.** `GraphSpectrum` (multiscale.py:36-64, `eigh` of 5570x5570 float64: 27 s per Session), peaks, `spatial_root`, `factor_model` pick CUDA when present; `heavy.py` takes the GPU slot only for `--gpu`/PEGASUS_DEVICE=cuda (heavy.py:30). Float64 on this GPU is ~1/64 of float32 (optimization.md section 1). A survey launched with `update` directly (as `scratchpad/queue.ps1` does) bypasses heavy.py altogether.
11. **Ledger as a file per call** (control.py:88-95): triage of 16,806 leads + corroboration wrote tens of thousands of parquet files; `Ledger.table()` reads them all.
12. **`harness.method_records()`** (tools.py:442, harness.py:975) re-reads and JSON-parses every stored event_record and grid result (110 harness entries) at the end of each `survey_questions` and each `relation_survey`.
13. **Standalone `ask`** resets the surprise memo each call (questions.py:144-150): `s.ask` x 7 rebuilt B1 nine times in the profile (about 15 s each).

## (d) Budget against measured

| component | budget | measured | source |
|---|---|---|---|
| IX annual cold fit | 20 s / 5 s warm (ARCH 5.8, plan 7) | 35.1 s cold at day's end (10 threads beside a fit); 37 s calm; 59-71 s earlier; 154 s v1 first | optimization.md 8b; solver-v1 |
| VII annual | 2 s / 1 s | 92 s (5 outers); 395 s (17 outers) earlier | solver-v1 L123; optimization 8b |
| IX race x fine ages | 90 s / 20 s | not measured | -- |
| SIH-RD X annual | 2 min / 30 s | 71 s (rank 0) | solver-v1 L273 |
| SIH X monthly / DENG monthly 2010-2023 | 2 min / 30 s | SIH X monthly 2010-14: 119 s cold (4 outers); full 14-year v1 run not found; v0 9,263 s not converged | solver-v1 L173; fit-throughput |
| all 20 SIH chapters | 30 min | 1,013 s for 16 chapters warm (I 133 s, XIX 282 s), loaded machine | optimization 8b |
| all 19 SIM chapters | 10 min | not found | -- |
| assemble one block | < 2 s cold from lake | 10.6 s (7.4 s mean in profile incl. misses), cached 0.6-1.0 s; plus `_age0_share` 4 s per block per process | survey-throughput; prof_questions.pstats |
| tiers, one node | all nodes of a block < 10 s; B1 3 s | one B1 `Expectations.surprise` about 15 s (SIH X, U=5570): place_year_phi 9 s, noise_structure 4 s, PIT/shrink rest | pstats (136 s / 9 builds) |
| robust refit | none stated | about 15 min per chapter | evaluation 2026-10-07 robust-expectation |
| survey, one chapter | < 2 min | v0 lenses SIM III 21 fields: 65 s (met) | survey-throughput |
| survey, question pass (3 questions) | < 2 min / chapter | SIM, 41 groups: 5,581 s = 136 s per group; per question mean excess 43 s, step 60 s, trend 33 s; one outlier 770 s | survey_questions_v1.out |
| survey, 7 questions, one field | -- | SIH X J09-J18: 893 s (excess 176, step 105, trend 67, cluster 67, share 427, institution 32, group 20) | prof_questions.pstats |
| survey, SIH X groups (10), 7 questions | -- | 16,790 answers; `questions` step stamped 18:36:39; log file created 10:34, last write 19:01 (8 h 27 m wall, includes the 6 robust fits and per-group share assembly) | s1_sih_x.out; update manifests |
| DIAS_PERM measure on X (10 groups) | -- | 19 min (18:36:39 -> 18:55:40), 16 answers; includes a mark fit if it was missing | update manifests |
| triage 16,806 leads + corroboration 5,512 | re-triage 33k-lead register < 30 min | <= 5.5 min (18:55:40 -> 19:01:11) | update manifest; plan 5 |
| planted grid, one world | -- | SIH J09-J18: 125-137 s per world, 6 lenses, 56 worlds = 2.1 h; SIM I60-I69 (v0 lenses) 21-49 s per world | o6_v6.out; grid_*.log |
| default `grid` CLI (84 worlds x 12 methods) | -- | not run; by the above, hours to tens of hours per field | extrapolation |

Stage E is not the long pole in the one complete run seen: the question pass was 8 h, triage + corroboration under 6 min.

## (e) Hot spots and repeated work, ranked by likely time saved (per field, SIH X scale, from the 893 s profile)

1. **`surprise.spatial_structure` inside every `multiscale.peaks` call: 189 s (21 %), 4 calls, 47 s each** (surprise.py:962; `peaks` calls it at multiscale.py:221, no caching). 152 s is the 8 float64 U x U products at lines 1003-1004. The result depends only on (field, tier, graph). `excess`, `excess_step`, `excess_trend` all read B1, so three of the four calls are identical (about 94 s repeated); `excess_level` reads B0. Also recomputed per call: `spectrum.scales` bisection (40 x 22 ms per footprint: 36 calls, 42.8 s, a function of the graph only, constant across fields), `spectrum.kernel` twice per scale (multiscale.py:231, 288), `spatial_root` (3.4 s per call), 40 replicate fields (3 s).
2. **`share_excess` theta search: 105 s (12 %)** (departures.py:457-463): 51 evaluations of scipy `betabinom.cdf` + `pmf` over all cells with n >= 20 (4.1 M `_cdf_single` Python-level calls, 102 s). Per field, not shareable by memo; cost is the evaluator.
3. **Shares of the old all-chapter assembly: 280 s (31 %)** (c.2): fixed for the annual path by a6b8303; remains for monthly and "*".
4. **Surprise builds: 136 s (15 %) for 9 builds.** The survey memo (tools.py:425) should reduce this to B1 + B0 per field; `Session.institutions` bypasses it (tools.py:141) and costs a third build (about 15 s per field). `lift` (surprise.py:675) is recomputed for `cell_excess` and again for `step`. `by_group` (tools.py:146) is not memoised.
5. **`_shape` per finding: 21.6 s** (2,573 `series` calls, 33.5 k `lag_covariance` calls; questions.py:168 runs before merging, so findings later superseded by a stronger finding of the same method are shaped too). `series` recomputes `field_cell_variance` and every lag covariance over all U x T per call (departures.py:215-232). Scales with finding count (SIH answers: thousands per field).
6. **GraphSpectrum / ladder per Session: 27 s + 8 s** (tools.py:262, 255), paid again by every `tools.Session` that `update.run` creates per reader (update.py:232).
7. **Block (re)assembly:** `assemble` hashes the population content on every call (monolith.py:166-168) and re-reads POPSVS; `_age0_share` 4 s per block per process (monolith.py:116).
8. Outside the question pass: robust refit 15 min per chapter (c.1); update's all-or-nothing/commit-keyed steps (c.4, c.5); `confirm_last` doubles the question pass.

Memoisation present: B1/B0 surprise per field within `survey_questions` (tools.py:425); `Session.edges/scales/spectrum` per session; `_NULLS` for the scan null (scans/lenses.py:65, keyed on a raw array pointer `s.mu.ctypes.data`, never cleared); `_age0_share` lru; neighbourhoods. Absent: spatial_structure, scales(), kernels, series/variance arrays, lift, by_group, any cross-session or on-disk cache of question answers.

## (f) What configurability would touch (observations only)

- **Method records and the BB denominator.** `Answer.p` is times k, where k = number of methods that read the field's kind (questions.py:196, tools.py:430). Dropping a method for cost changes k, the family's p-values and the stored `method_records` basis (calibration was characterised with all methods at q/k; harness.py:975). Lead `method` field and `calibrated` flag are computed from the methods an answer names (tools.py:446-460).
- **Ledger and register.** Each lens registers a hypothesis before running (`ledger.register`, e.g. departures.py:116, 177); a lighter or targeted run still writes one parquet file per call, and `family` strings (`excess:{shape}|{tier}|{block}`) define the BH/BB family, so a subset of fields changes family size. The register is written once at the end (tools.py:464).
- **Replicate counts are part of the null.** `peaks` replicates=40 feeds a GPD tail (`tail_p` needs n >= 4 x 250 null peaks, multiscale.py:150), `corroborate` replicates 4999/99999 set the smallest attainable p (comment tools.py:947-949 ties 99999 to BH over many tests), spatial_cluster adapts 200..2000. Changing them changes attainable p and therefore which leads can be admitted; calibration records were made at these values.
- **Stage E consumes the answers' fields.** `triage` reads `x.provenance["by_method"]` stats, `corroborate` needs `signal` triage, `later_years` needs the all-data answers' ids (update.py:157, 174): a partial survey changes the lead set these see and the keys (`leads=sorted(ids)`, update.py:274).
- **Keys.** The only cached units are fits, blockdata, calibration, gateway tables, and the three update step keys; there is no key for (field, question, method, settings), so any per-field scoping needs a new address kind or it re-runs. The update key carries code version (c.4) and `Plan` fields `questions`/`levels` but not methods or replicate settings.
- **Objects that carry no cost settings today:** `Session` (tools.py:68-84: dataset, event, years, graph, supply, rank, source, ledger, register), `Plan`/`System`, `questions.Question/Method` (frozen dataclasses with assumptions, regimes, kinds; no cost or priority), `Finding`, `Lead.method`.
- **Where defaults enter:** keyword defaults inside departures/multiscale/lenses/corroborate/relations; `Session.scan` passes only `q`, `tier`, `scales`, `**kw` (tools.py:283); the question layer forwards one `**kw` to all methods (questions.py:158-176) so per-method values cannot be expressed through `ask`.
- **Scheduling.** heavy.py is a process wrapper keyed on the command string "survey" (heavy.py:50); `update` is not wrapped by it unless launched through it, and its work units (fit, question pass per system, reader, relation, triage) are not exposed as separate jobs. Other mechanisms exist (see below).

## Job runner (item 6)

- `scripts/heavy.py` (slots/memory/GPU slot, thread env) and `data/chain.py` (sequential logs) are documented (ARCH 5.7, RUNBOOK last row). Neither is imported or invoked by `update.py`, `cli.py` or `tools.py` (grep of src: no reference). Usage is manual: `grep` finds heavy.py only in docstrings/headers of data scripts and in `data/logs/*.ps1`/`*.sh` chains.
- Second mechanisms in the repo: 17 `data/queue_*.py` each with its own `subprocess` loop (e.g. data/queue_1006.py), per-purpose PowerShell/bash chains in data/ and data/logs/ (fit_*.ps1, *_chain.sh), the current `scratchpad/queue.ps1` that runs `python -m pegasus_core.cli update` directly without heavy.py or chain.py, and 210 ad-hoc `data/*.py` experiment scripts. `survey` slot pool detection is by substring (heavy.py:50), which `update` does not match.

## Side findings (bugs and doc drift met on the way)

- **`Plan.load` passes `System` arguments in the wrong order** (update.py:69-71 vs the dataclass fields update.py:40-45): `disparities` is passed in the `intervals` position, `intervals` in `classifiers`, `classifiers` in `mentions`, `mentions` in `flows`, `flows` in `disparities`. By reading, `plans/s3_race.yml` (`disparities`) would be handed to `_declared(..., "interval", ...)` and raise "not modelled interval fields", and `intervals:` in `plans/s1_sinasc_fields.yml` lands in `classifiers` and matches nothing. Not run.
- `update.run` builds the relation spec from the raw `x.blocks` (update.py:259), not the resolved chapters, so `blocks: [all]` with `relations: true` would look for a block named "all".
- RUNBOOK.md:23 and :19 describe knobs that no longer exist or differ (above).
