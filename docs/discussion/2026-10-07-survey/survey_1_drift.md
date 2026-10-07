# Survey 1: architectural drift since 830a418 (2026-10-07)

Scope: `git log 830a418..HEAD` in pegasus_project (27 commits, 10:21-19:13, 42 files, +2446/-1156) and 12 commits of pegasus_data
(`pegasus-core-fixes`, 10:25-18:49). Read-only. `scripts/check_docs.py` and `ruff` pass, so the gaps below are invisible to the checkers.
Doc coverage of the 27 commits: ARCHITECTURE.md touched by 3 (e6761f6, 40c2f37, 5ebadda), STATUS.md by 7, RUNBOOK.md by 3,
coverage matrix by 3, EVALUATION.md by 1 (40c2f37), DECISIONS/ADRs by 0. CLAUDE.md 1.3(1) says every new mechanism, field kind, plan key,
default or constant is written into its ARCHITECTURE section (or 13.2) in the same commit; that did not happen for ~25 items below.
Status values: R recorded, S stale (doc says something the code no longer does), M missing.
Doc refs: ARCH = ARCHITECTURE.md; COV = docs/architecture_coverage.md; FFR = docs/plans/2026-10-07-fields-from-roles.md.

Timeline fact: S1 (97445c1 12:34), S2 (12:42, 12:44), S3 (12:45), S4 (12:45), S5 (12:50) landed in 16 minutes, none with a "Live:" line.
ARCH 12 says "Each package lands end to end before the next starts"; S1's own acceptance (FFR "Acceptance": documented positives for a
measure and a composition) is unmet (`harness.POSITIVES` holds none with a `source`), yet S2 to S6 were started.

## A. Fields and readers (S1)

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| `fields.declared` (kinds measure, composition, interval) / `Declared` | 97445c1, 40c2f37 | fields.py:268-324 | FFR status paragraph; COV 4.4 rows | R in FFR; M in ARCH 3.2 (Field.kind is `count\|mark\|share\|level`), 4.4 | none |
| measure readers; domain-admits-0 => count family | 97445c1, 40c2f37 | fields.py:327-346 (rule at :343) | COV row "bounded scores read as counts" | M in ARCH 4.4 (still says Apgar = ordinal cumulative logit) and 13.2 | P11 established method first: bounded score fitted as NB count with no stated departure; CLAUDE 1.3(5) |
| composition -> share fields, reference = most frequent value of last plan year | 97445c1 | fields.py:436-451; gateway.py:811-846 | FFR | M ARCH 4.4 | values chosen from one probe year (a code absent that year is never a field) |
| `interval:<date>` fields (days from event date, +1, sign by median of probe year) | 40c2f37 | fields.py:395-416; gateway.py:717-745 | FFR; COV | M ARCH | data-derived sign OK; uncached year read at every plan run |
| other-classifier trees (`classifier:`), generalised `monolith.assemble` / `block "*"` meaning changed | 40c2f37, a6b8303 | fields.py:419-433; monolith.py:112-116, 360-366 | none | M ARCH 3.2 (Block), 5.6; RUNBOOK still says `*` = "event type without a tree" | one name now means two things; `Session._blocks` discards `*` by hand (tools.py:277) |
| `mentions:<role>` (multi-column code lists via `gateway.code_groups`) | ac65fee | fields.py:376-392; gateway.py:1361 | FFR; RUNBOOK plans row names neither `mentions` nor `flows` | M ARCH, S RUNBOOK | none |
| `away:<place>` care-flow shares | 5ba7c0c | fields.py:349-373; gateway.py:862 | FFR | M ARCH 4.4/4.5 | entity-name heuristic (`r["entity"] != res["entity"]`) decides what is the event's place |
| `linked:` shares (`link:<spec>:<side>`) over `gateway.linked_counts` | 3dfaef2, 40c2f37, d8a637e | fields.py:454-485; gateway.py:1429 | FFR; ARCH 7.8 silent | M ARCH 7.8, 3.1 | Share model treats Σp_match as a binomial count; linkage uncertainty not carried (only `tools.cohort` draws) |
| ShareModel/CountModel reused for `linked`, `away` | 3dfaef2, 5ba7c0c | monolith.py:98-100, 2354-2358 | none | M | none |
| `Method.kinds`; `_ask` refuses a method for a kind; Bonferroni k counts only methods that read the kind | 97445c1 | questions.py:34, 138-160 | questions-and-methods plan silent | M | none |
| `institution` question + `institution_step` method | 97445c1 | questions.py:82-86; tools.py:297-307 | FFR names it; ARCH 11.1 `questions` row does not; plan questions-and-methods silent | S | `Method` has `kinds=("count",)` so it runs on every count field and fails only by caught exception |
| declared `Registry`, readers key (`READER_FIELDS`) in `fitted()` | 40c2f37 | tools.py:1063; 1067-1080 | none | M ARCH 11.3 | none |
| `Session.train` split-home tag names only mark/indicator/link/side | 40c2f37 | tools.py:788-794 | none | M | classifier/mentions/away sessions share `leads_T{last}` and `ledger_T{last}` with the count session |
| family key `qn\|block+measure` omits classifier-only readers | 3dfaef2 | tools.py:415-420 | none | M | a SIM original-cause classifier family becomes `excess\|I`, merging into the primary field's BH family |
| `marks.SPECS` removed; `marks.reader(dataset, event, column)` | 97445c1 | marks.py:31-50 | ARCH 11.1 `marks` row still says "specs (length of stay, cost, death, ICU)" | S | none (this is the intended removal) |
| entry date from roles (`ENTRY_PROPERTIES`), alarms CLI default | b065737 | gateway.py:581-590; cli.py:212 | RUNBOOK alarms row still passes `--report DT_DIGITA` | S | three property names listed in pegasus_core (vocabulary, not columns) |
| `RACE_COLUMN` removed; race from declared race stratum; SIH, SINAN gain race | 5ebadda | gateway.py:491-496, 511 | ARCH 13.1 "adults, SIH and SINAN read no race" | S | cache key unchanged (`gateway`:3/1) while the SINASC race column may now differ (RACACORMAE to the stratum's) |
| infant age mix from decoded age stratum in whole days | aa4c15d | gateway.py:337-366 | STATUS line deleted, nothing else | M | `_recorded_exposure` key stays `v:1` (gateway.py:433) though `_confusion_mixed` output changed 0.700/0.220/0.081 to 0.699/0.219/0.081: a stored table is served stale (ARCH 11.3 "A stale artefact is never served"). Also hard-codes `LIKE 'P%'` and 7/28-day edges in the gateway |
| `survivors_only` removed from `event_counts` | 5ebadda | gateway.py:473-496 | ARCH 7.6 first paragraph and 8.3 still say SIH = "admissions that did not end in death" | S | none |

## B. Gaussian location path (measures, shares, linked, away read by the stage-C methods)

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| `surprise.gaussian`, `field_cell_variance`, `field_lag_covariance`, `field_replicate`; multiscale `peaks` switch for Gaussian | d8a637e | surprise.py:603-632; multiscale.py:116-124, 204-240, 296-306 | none (ARCH 7.0 table has no "location" row; 7.2 mentions a Gaussian mark score only) | M | P16/6.1: a second noise-structure estimator |
| `gaussian_noise`: N1 of a mark = pooled lag-1 AR(1), clipped +-0.95, no gamma frailty/kappa/spatial share | d8a637e | surprise.py:591-600; multiscale.py:230 (`noise = s.noise if gauss`) | none | M | P16 "noise structure measured per field": two mechanisms for one job (count N1 vs this); CLAUDE 4 "replace, never build beside" |
| `LOCATION_EFFECT = 0.1` (minimum relevant effect in units of one event's SD) and `unit_sd` | d8a637e | surprise.py:562-588; tools.py:~323 (`location_rate_ratio`) | none; not in 13.2 | M | P7 / CLAUDE 1.3(5) constants are debts: hand-set, comment cites Cohen 0.2, not measured; ARCH 8.4 requires delta calibrated on negatives. Commit text cites "8 place-year departures, none before" as the justification |
| count family: randomised PIT of place-year sum | d8a637e | surprise.py:522-539 | FFR line | M ARCH | none |
| `cell_excess` relevance for marks (normal tail), effect = exp(y-mu) | d8a637e | departures.py:130-146 | none | M | none |
| method `calibrated` for mark/share/linked leads comes from count-field grids/events | e6761f6, d8a637e | harness.py:975-1026 keyed by method id only | ARCH 10.5 says "per field" | M | P9/P16: no grid or null world ever read a Gaussian field; leads of `excess` on SINASC weight inherit `calibrated` measured elsewhere |
| no documented positive for any measure/composition/link/mention/away field | S1 | harness.py:78-218 | FFR "Acceptance" | M | CLAUDE 1.0(8) real data with known answers; the 8 birth-weight departures are unjudged |

## C. Stage E: ledgering, triage, corroboration, replication

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| `Session._ledgered`: corroboration, later years, spatial_unit, triage written to the ledger before they run | 0052131, 8b427f1, 6562aa9 | tools.py:831-841, 554, 822, 874, 964 | ARCH 9.2 says all tests are ledgered (silent on how); STATUS no | M detail | untested verdicts (p=None) are ledgered as p=1.0 tests (tools.py:~549) and enter the family denominator |
| `spatial_unit` ledger p = binomial/test-half/state-rest p | 8b427f1 | tools.py:866-872 | none | M | none |
| `replication._delta` takes the system (Strata.dataset) | 70a7fbe | replication.py:468-472 | none | M | commit says crashed "on every unit claim" since earlier: verified by 3 SIH claims only |
| `replication.lasting` skips later-years test for spike/transient answers (`PASSING`) | 40c2f37 | replication.py:261-269; tools.py:822 | ARCH 8.3 later-years row says "a one-off event cannot [replicate]" but not that it is skipped | S | hand list of two shapes; skipped leads are "untested", not rescored |
| `corroborate.sources`: any other served ICD-10-coded event type + declared context fields; RULES removed | 40c2f37 | corroborate.py:72-93; tools.py:919-990 | ARCH 8.3.2 paragraph updated; ARCH 8.3 table row still "S2iD, SINAN or SIH"; ARCH 11.1 `corroborate` row stale; COV lines 434 `corroborate.RULES`, 258, 455 stale | S | ARCH 8.2/P5: "any source rejects" with an unbounded number of sources per lead and BH only within source (tools.py:~980-990) inflates R3 |
| overlap with a lead's system via declared link; year without stored link read whole (`LinkNotStored`) | 40c2f37, a6b8303 | corroborate.py:210-216, 350-354; gateway.py:1381-1404 | ARCH 8.3.2 says linked records are removed; STATUS "dormant: linked overlap read on a full update" | S | ARCH 11.4 / CLAUDE 6 "overlapping fields never tested as independent": missing run => overlap unknown but the test is still a verdict (`ok`), only annotated |
| corroboration design (harm statistic, X36 -> S2iD trigger typologies) fixed after reading landslide results | 40c2f37; pegasus_data fa4b274, 2dae11e | corroborate.py:116-137; evaluation 2026-10-07-derived-corroboration | evaluation entry R | R but flawed | ARCH 11.4 "No ... design choice is tuned on a documented event": the evaluation names Serrana 2011, Sao Sebastiao 2023, Rio 2010 and shows "presence does not discriminate, harm does" |
| `institution_triage` (volume follows >= 0.5 => system/bound, else signal) | d6a72f9 | explain.py:247-258; facility.py:337 | ARCH 7.7 triage rule list silent | M | hand threshold `VOLUME_FOLLOWS` (also LATTICE_G 27, RATIO 1.6) is a v0 constant; commit claims fix by the old 4,636 "noise" only, no after-count |
| `Session.alarms` writes a ledger entry and leads (q = 1/recurrence, calibrated False) | e6761f6 | tools.py:340-393 | STATUS one clause; ARCH 11.1 `surveillance` row silent; RUNBOOK alarms row says report column DT_DIGITA | S | `Lead.q` now holds a recurrence, not an FDR level, so rank (9.1) is not comparable |
| joint departures, map pairs, relation_map bands/courses as leads and ledger entries | e6761f6 | tools.py:1220-1240, 1292-1314; relations.py:538-590 | STATUS | R (STATUS) / M (ARCH 9.1 kinds list lacks `answer`; leads.py:32 has it) | one hypothesis per band/course, not per pair |
| `harness.method_records` replaces `METHOD_EVIDENCE`/`method_record`; record schema changed | e6761f6 | harness.py:975-1026; tools.py:440-466 | ARCH 8.4 (:879) cites `tools.method_record`; COV :344 same; ARCH 9.1 `method` = maturity, power, FDR, MDE | S | record no longer carries tier, theta0, evidence text, power or maturity; `calibrated = k/n <= max(q, 1/n)` is vacuous for n=1 (always True) |
| `verdict_positives`: human-confirmed answers join `event_record`'s documented events | a2968c5 | harness.py:876-896, 908 | RUNBOOK dossier row; ARCH 10.1 silent | M | P9 "documented events are a held-out check, never a tuning target": confirmed answers are by construction findings of the methods they then score |
| `report.record_verdict("artefact")` sets `status="explained"` | a2968c5 | report.py:181-197 | RUNBOOK; ARCH 9.1 silent | M | P14 / ARCH 11.4 "Only a tested explanation removes a lead": a person's label removes it |
| dossier (HTML, matplotlib) | a2968c5 | report.py:86-179 | RUNBOOK row | R | matplotlib not declared in pyproject.toml (CLAUDE 7 Dependencies) |
| report ranks by `rank` | e6761f6 | report.py:55,62 | ARCH 9.1 | R | none |
| `Session._expected_total`: fits block `*` (national, all events) inside a reading when missing | a6b8303 | tools.py:626-646 (calls `update.fit_block`) | none | M | CLAUDE 1.3(4) "No hidden expensive default": a triage/survey call launches a national fit; also `tools` imports `update` (:631, :1187, :1414) while `update` imports `tools`: a cycle against ARCH 11.1 "downward only" |
| `PEGASUS_COMPUTE_LINKS=1` (default: stored runs only) | a6b8303 | gateway.py:1381-1404 | not in any .md (grep) | M | the fix itself is aligned with 1.3(4); undocumented env var |

## D. Dependency map and contexts

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| map fields = every fitted field of the plan's systems; `_readers` from fit keys; `READER_KEYS` | 5ebadda | scans/map_inputs.py:76-91, 114-212 | ARCH 7.6 line 780 first sentence still lists "SIM chapters, SIH chapters (survivors), SINASC indicators"; second bullet updated | S | none |
| overlap: same system if categories or the reader tag meet; cross-system only where a `same_event` link has a stored run | 5ebadda | map_inputs.py:145, 159, 196-212 | ARCH 7.6 (updated) | S | `field_cats \| {tag}` (:159) makes every pair of chapters of the SAME measure overlap (shared tag), so they are never tested: probable defect; ARCH 7.6 "unknown overlap is not tested" vs code `ov = 0.0` when no declared link (:208) |
| `CARE_KINDS`, `maps.care()`, `utilization.tensor` removed => `patterns.py` (CP-APR) has no input | 5ebadda | map_inputs.py:~63; utilization.py | STATUS dormant row; ARCH 7.4, 11.1 `scans` row still list patterns/utilization tensor | S | none |
| contexts by declaration: `gateway.context_value`, normal scores, plan `contexts:` | d72a533 | gateway.py:1194-1250; map_inputs.py:42-52 | RUNBOOK plans row; ARCH 7.6 no | S | `from pegasus_data.fields import _years` (gateway.py:1200): a private function across the boundary; `CONTEXT_SD = 0.05` (map_inputs.py:21) is a pre-existing constant |
| `tools.dependency_map(plan=)`, relation leads for admitted pairs | 5ebadda | tools.py:1180-1235 | ARCH 7.6 | S | CLI `map` does not expose `plan`; default path relative to cwd |
| `indicator_counts` and map helpers removed | d72a533 | gateway.py:~1186 | none needed | R | none |

## E. Update, plans, CLI, survey removal (S0)

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| `pipeline` -> `update`; `pegasus-core run` -> `update`; `fit_block` the one fitting path | e6761f6, 98ffbd1 | update.py:79-93; cli.py:40-48 | ARCH 11.1 row says `update` (9.3) but 9.3 never describes it; COV 9.3 R | S | none |
| `Plan` keys: systems.{measures, compositions, links, intervals, classifiers, mentions, flows, disparities}, plan.{contexts, corroborators, confirm_last} | 97445c1..5ba7c0c | update.py:32-76 | RUNBOOK plans row lists all but `mentions`, `flows`; ARCH 9.3 none | S | **`Plan.load` passes arguments positionally in the wrong order** (update.py:69-71 vs dataclass update.py:32-45): `intervals` receives `disparities`, `classifiers` receives `intervals`, `mentions` receives `classifiers`, `flows` receives `mentions`, `disparities` receives `flows`. Executed: s1_sim_mentions -> flows='all', mentions=None; s1_sih_sigtap -> mentions=['PROC_REA'], classifiers=None; s1_sinasc_fields -> classifiers=['interval:DTCADASTRO'], intervals=None; s3_race -> intervals=['O00-O99',...] which raises. Four of nine plans do not do what they say |
| step keys: data version + whole-repo code version; triage key = answers only | e6761f6 | update.py:137-146, 274 | update.py docstring | S | "each reading redone only where its inputs changed" is false in two ways: any commit re-keys every step; changing `corroborators` or the served systems does not re-run corroboration (not in the key) |
| module global `update.resolved` | 089571a | update.py:149 | none | M | hidden state across calls |
| `blocks: [all]` (every chapter of the primary tree) | 089571a | update.py:108-116 | RUNBOOK | R | none |
| v0 lens survey removed: `Session.survey`, `SURVEY_PLAN`, `METHOD_EVIDENCE`, worker pool, `survey --lenses`, prospective survey | e6761f6 | tools.py (deleted ~120 lines), cli.py:87-97 | RUNBOOK survey row still documents `--lenses`; ARCH 7.1 :676 cites `SURVEY_PLAN`; COV :65, :258, :289, :455 | S | CLAUDE 4 "Never lose a question": commit says "the lenses live on as methods of the questions", but `trend_divergence` and `space_time` are in no `QUESTIONS` entry (questions.py:49-100) and `grid`/`events` now read question methods only; the prospective survey (ADR-0012) has no entry point left; 33,111 leads retired wholesale |
| `grid` default methods = every method of the questions | 98ffbd1 | harness.py:495-501, 718-721 | RUNBOOK grid row | R | cost of the default grid grows with every method, not stated |
| new CLI: `cohort`, `disparity`, `dossier`, `verdict`, `update` | S2-S5 | cli.py:40, 260-305 | RUNBOOK rows for update/dossier/verdict only; `cohort`, `disparity` M | S | `pegasus-core fields` does not show `fields.declared` as FFR promised |
| `epi_week` moved to the gateway; `surveillance` re-exports | 98ffbd1 | gateway.py:1348; surveillance.py:33 | ARCH 11.1 `surveillance` row "epidemiological weeks by one rule" | R | none |
| `monolith._regional_flags`/`footprints` removed | e6761f6 | monolith.py:1724-1790 | plan robust-expectation silent on removal | R | none |

## F. Persons, race, use (S2, S3, S5)

| item | commit | code | documented where | status | conflict |
|---|---|---|---|---|---|
| `tools.cohort`: persons from a declared link side, attributes = all declared compositions, outcome = has partner, Rubin over link draws | 3a83ab5 | tools.py:1349-1399; gateway.py:1486 | ARCH 7.8 (Poisson regression, BH, no link draws); COV :281 and :314 say "script-driven / API NB" while COV :159 (same commit) says built; ARCH 9.3 table row `cohort(...)` | S | draws = independent Bernoulli(p_match) per pair; `DELTA_RR` 1.2 and `min_events` 20 provisional constants (scans/cohort.py:30, 102) |
| `tools.disparity`: race by indirect standardisation, conditional binomial vs national disparity, one BH | 8746b3b | tools.py:1402-1466 | ARCH 7.0 table "race disparity" row describes a different (posterior) model; COV :60 no status; STATUS dormant row "race ... next: race as axis of G" | S | P15: for adult SIM fields (O00-O99, X85-Y09, plans/s3_race.yml) recorded race is read against the declared-race exposure; the confusion is measured for infants only (gateway.py `_recorded_exposure` applies it at age 0 only, :424-457); ARCH 4.1/13.2 say adults stay "recorded race". Commit text says "through the measured confusion". One ledger entry for all race x place tests (:1425-1429) |
| linked-share fields / `same_event` consumed from pegasus_data | 3dfaef2, 5ebadda | gateway.py:1372; fields.py:454 | ARCH 7.6 | R | none |

## G. Boundary and layering

| item | commit | code | status | conflict |
|---|---|---|---|---|
| `municipality_names`, `epi_week`, `entry_date`, `code_groups`, `link_specs`, `declared_fields`, `stored_pairs` added to gateway | many | gateway.py:581, 1186, 1341-1404 | ARCH 2 rule 1 holds: no `import pegasus_data` outside gateway.py (grepped) | rule 1 "public API": gateway imports `pegasus_data.fields._years` (:1200), `linkage.store`, `linkage.engine.stored_key/load_links`, `linkage.identity.record_ids`, `linkage.roles.load_roles` |
| module direction | e6761f6, a6b8303 | tools.py:631/1187/1414 import `update`; tools.py:440/1175/1274 import `harness`; report.py:98 imports `tools` | ARCH 11.1 `update` "may import tools, report"; `tools` "may import leads, scans, surprise, gateway, replication, corroborate" | upward/cyclic imports; ARCH 11.1 dependency sentence is also incomplete (omits departures, relations, multiscale, questions, harness, report, update, facility, marks) |
| pyproject | many | pyproject.toml | matplotlib undeclared (report.py:92); `package-data admission_curves.json` names a file that does not exist (retired, ADR-0028) | CLAUDE 7 Dependencies |

## H. pegasus_data (12 commits, branch pegasus-core-fixes)

| item | commit | where | documented | status | conflict |
|---|---|---|---|---|---|
| `ColumnRole.measure` (ADR-0154) | 1514dfb | column_roles.py; roles/CIHA.yml, SIH-RD.yml | ADR-0154 + DECISIONS | R | ADR-0154 accumulated 5 addenda and one withdrawn claim (1e0066a TPROBSON) in one day: an ADR for a step in progress (pegasus_data CLAUDE 7; user rule "ADR only when final") |
| `missing`/`domain` declared for SIH-RD 38 quantities, SINASC, SIM-DO numbers and categories | 13ff093, a80b695, a4df241, fa4b274 | roles/*.yml; scripts/propose_missing.py | ADR addenda, DATA_SOURCES 2.1 | R | domain inferred from TabNet band labels (a tabulation domain, DATA_SOURCES says so) then consumed by pegasus_core as a hard bound (`mark out of bounds`); no EVALUATION entry for the proposals' counts; CONSPRENAT, QTDFIL* left undeclared (correct) |
| `same_event` required on every link | a55482d, 426a195 | links.yml; linkage/engine.py:~88,153; store.py digest | no doc beyond comments | M | `LinkSpec.same_event: bool = False` default coexists with `body["same_event"]` required (KeyError): consumer relies on it (map_inputs.py:~176) |
| context fields declare `over` (54) and disasters `icd10`, `harm` | fa4b274, 2dae11e, 33cd6dc | curation/fields.yml | no ADR/DATA_SOURCES entry for `over`, `harm` | M | `harm` was added to make one evaluation pass |
| SIM `death.causes` | 0c9c95a | roles.yml, roles/SIM-DO.yml | none | M | landed 18:49:08, same minute as pegasus_core ac65fee that reports "Live" numbers from it |
| working tree (not in the 12 commits) | - | `_translate.py`, `persist/reference.py` (+40, dictionary fingerprint stamps), `retrieve.py`, `scripts/propose_missing.py` | none | M | pegasus_core reads pegasus_data editable: results depend on uncommitted code; DECISIONS.md also carries a 360-line CRLF/LF churn in 13ff093 (diff -w: 1 line) |

## I. Commits whose claimed verification is not supported

| commit | claim | what the code path supports |
|---|---|---|
| 40c2f37 | "Live: 13 of 31 landslide leads corroborated (0 before)" | Supported by the evaluation entry (scratch script, 77 leads). But the rule was chosen on those leads; the update path (`s.corroborate(... served ...)`) was not run end to end; linked overlap not read |
| d8a637e | "SINASC birth weight: 8 place-year departures (+5-7 %), none before" | Count of findings, unjudged against any known event; depends on `LOCATION_EFFECT`=0.1 |
| ac65fee | "Live: SIM 2019 death.causes, sepsis 303,072 mentions against 21,517 underlying; lung cancer 30,972 against 29,247" | Plausible magnitudes (sepsis 23 % of 1.3 M deaths; lung cancer +6 %). Reader called directly: the plan route (`plans/s1_sim_mentions.yml`) cannot work (Plan.load order bug). pegasus_data role committed the same minute |
| 75ab6da, e39f540, 089571a (plans) | no run claimed | s1_sim_mentions, s3_race, s1_sinasc_fields, s1_sih_sigtap are broken by the Plan.load bug |
| 5ba7c0c | "Live: SINASC 2019, 32 % away, SP 3.8 %, median municipality 96.6 %" | Plausible; direct reader call; `flows` plan key broken by the same bug (the plan loads `flows` from `mentions`) |
| 5ebadda | "Live: SINASC-only map, place-effect sd 0.17, 0.0135" | Only SINASC; the `same_event` overlap, "not linked to" twins, care-use factors and `_linked` (stored-run requirement) never ran |
| d72a533 | "Live: 20 default contexts on 5,570 places (GDP per head median R$16.9k, SUS beds 1.1 per 1,000)" | Values plausible; checks `context_value` only, not the map |
| 0052131 | "5 corroboration tests ... registered then completed" | 5 tests; ledgering shown |
| 70a7fbe | "3 SIH unit claims audited" | 3 claims; the other estimands untouched |
| aa4c15d | "Mix 0.699/0.219/0.081 against 0.700/0.220/0.081", 513 deaths | Numbers consistent with the code; downstream cache not invalidated (see A) |
| d6a72f9 | "before, all 4,636 of SIH X were 'noise'" | before-count only; no after-distribution; hand threshold behind the new classes |
| a6b8303 | no verification line | rewrites `_expected_total` (national `*` fit) and `_prepare_grid`; not run |
| e6761f6 | "33,111 v0 leads retired ... 117 kept" | store operation; not reproducible from code |
| S2-S5 commits (3dfaef2, 3a83ab5, 8746b3b, 70c1ab9, a2968c5) | none | no run named; built not checked |

## J. Pre-existing stale statements (before today)

ARCH 11.1: `scans` row lists `departures`, `relations` as "to build" (both exist as modules with their own rows); `marks` (SPECS);
`corroborate` ("S2iD, SINAN, SIH"); `fields` (no declarations); `tools` imports; dependency sentence (11.1 end). ARCH 11.3 home layout omits
`maps/`, `update/`, `tools/` (expected_total), `corroborate/`, `ledger_T*`, `leads_T*`. ARCH 7.1:676 (`SURVEY_PLAN`), 8.4:879 (`tools.method_record`),
8.3 table row "S2iD, SINAN or SIH", 7.6 first sentence. ARCH header (line 3) and section map stop at revision 3 though 12 is revision 4 (no ADR for
revision 4; revisions 2 and 3 have ADR-0023, ADR-0029). ARCH 13.1 (dated 2026-10-06): departure models "not built" (O6 mostly done), relation models
"not built" (relations.py, O7), marks "v0 (PESO)", validation "v0 ... a gate" (gate retired, ADR-0028), "race ... SIH and SINAN read no race",
recording as measurement "conserved-level fields not built" (built, 8.6 text), ICD ontology "lists ... not used". ARCH 13.2: no row for any new
constant (LOCATION_EFFECT, VOLUME_FOLLOWS in triage, PASSING, CONTEXT_SD) or for the count-family/Gaussian-location departures.
STATUS: bottom "The roadmap (revision 3)" table (N1, N2, O6 ... "next") and the first paragraph ("next work is N1") contradict revision 4; "Where each
stage stands" E/F rows, A "next SIA/APAC, CIHA" (plans exist), "Planned and dormant" rows for linkage (sides filtered: done), race (disparity v0
built), breadth (S6 plans), institutions (question built). COV: header table counts (216 items) and the "ten most consequential gaps" are the
2026-10-05 ranking (#3 low-rank "not built" though built, ADR-0021; #6 marks "one type"); rows :281, :314 (cohort NB), :308 (kinds), :274 ("65 fields").
RUNBOOK: survey `--lenses`, CLI row lists `fit|fields|surprise|scan|survey|ask|relations|leads|ledger`, alarms `--report DT_DIGITA`.

## K. The 15 most consequential gaps, ranked

1. **`Plan.load` argument order (update.py:69-71 vs :32-45)**: four plans silently or loudly wrong; every "plans' mentions/flows/intervals/classifiers/disparities key" in 5 commit messages and RUNBOOK is unexercised. Fix before any update run (hours of wasted compute otherwise).
2. **The v0 survey removal lost questions** (e6761f6): `trend_divergence` (municipal, region, state; two references), `space_time` and the prospective survey (ADR-0012) have no scheduled entry; `grid` and `events` no longer measure them. Contradicts CLAUDE 4 "Never lose a question" and the commit's own claim.
3. **A second noise/relevance mechanism for Gaussian fields with a hand-set constant**: `gaussian_noise` (AR(1)), `LOCATION_EFFECT = 0.1`, count family via randomised PIT. P16, P7, CLAUDE 1.3(5); undocumented in ARCH 4.4/7.0/13.2; `calibrated` for these leads comes from count-field grids (harness.py:975).
4. **S1 acceptance unmet and S2-S6 started** (ARCH 12 "end to end before the next"): no documented positive for any new field kind; 16 minutes for S1-S5; findings (8 birth-weight departures, sepsis mentions) are unjudged.
5. **Corroboration rewrite**: harm statistic and X36 typologies fixed on the documented landslides (11.4 / P9), "any source rejects" over unbounded sources, and missing link runs read as unlinked (11.4 overlap invariant).
6. **Human verdict `artefact` removes a lead (`status=explained`) and `verdict_positives` score methods on their own confirmed findings** (P14, P9, 11.4).
7. **Race disparity on adults reads recorded race against declared-race exposure** (P15, ARCH 4.1/13.2) while the commit says "through the measured confusion"; plans/s3_race.yml targets exactly O00-O99, X85-Y09; one ledger row for all tests.
8. **Hidden expensive default and layering**: `_expected_total` launches a national `*` fit inside a reading (tools.py:626-646); `tools` <-> `update`, `tools` -> `harness` cycles (CLAUDE 1.3(4); ARCH 11.1).
9. **Documentation debt, quantified**: ~25 mechanisms/keys/kinds absent from ARCH (field kinds in 3.2/4.4, Gaussian path, plan keys in 9.3, new leads kinds/`answer`, `method` record schema, `PEGASUS_COMPUTE_LINKS`, `block "*"`, new CLI commands in RUNBOOK); one evaluation entry for 27 commits; no ADR or header for revision 4.
10. **`method_records.calibrated` is vacuous for small n** (k/n <= max(q, 1/n) is always true at n=1) and the record dropped tier, theta0, power, maturity required by ARCH 9.1/10.5.
11. **Map inputs overlap bug** (map_inputs.py:159, 205): all chapters of one measure are mutually "overlapping"; the map was run live only on SINASC.
12. **Stale cache served**: `_recorded_exposure` key `v:1` after the age-mix change (gateway.py:433); `event_counts` race stratum change under an unchanged key; `Session.train` homes shared across classifier/mentions/away sessions; classifier-only family keys merge BH families (tools.py:415-420).
13. **STATUS and COV contradict ARCH 12**: STATUS still schedules N1/N2/O6; COV rows contradict each other (cohort built vs NB). CLAUDE 1.2 tells the next session to start from these.
14. **Boundary and dependencies**: private `pegasus_data.fields._years` and linkage internals in the gateway; matplotlib undeclared; stale `package-data`; pegasus_data uncommitted work that PegaSUS reads; ADR-0154 amended five times in a day.
15. **`update` step keys**: whole-repo commit as code version (every commit re-keys all steps; "hours") and corroborators/served systems absent from the triage key; module global `resolved`; interval sign probe re-reads a year each run.

Hand-set constants/lists introduced or newly load-bearing today (candidates for ARCH 13.2): `LOCATION_EFFECT` 0.1 (surprise.py:562), `gaussian_noise` clip 0.95 (:597), `VOLUME_FOLLOWS` 0.5 in triage (facility.py:337), `PASSING` (replication.py:261), `ENTRY_PROPERTIES` (gateway.py:581), `NEWBORN`/`CONTEXT_SD` 0.05 (map_inputs.py:21), `method_records` rule max(q,1/n) (harness.py:1022), alarms `q = 1/recurrence` (tools.py:~388), cohort `draws=20`, `DELTA_RR` 1.2, interval `bounds (1, 1e300)` (fields.py:~414).
