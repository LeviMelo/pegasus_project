# Survey 2: author's goals/rules vs the canonical documents (read-only, 2026-10-07)

Paths: PP = pegasus_project, PD = pegasus_data. Memory = `~/.claude/projects/...pegasus-data/memory/*.md`.
Note: PP `CLAUDE.md`/`AGENTS.md` have UNCOMMITTED edits (working tree, being made during this audit) that already fix some items below (marked "WT-fixed"); committed HEAD still has the old text. Everything else was read at HEAD of the working tree on 2026-10-07.

Abbreviations: ARCH = PP ARCHITECTURE.md; CL-PP / CL-PD = the two CLAUDE.md; WSR = docs/discussion/2026-10-07-whole-system-review.md; COV = docs/architecture_coverage.md; OVH = docs/plans/2026-10-06-overhaul.md.

---
## (a) Rules and goals

"Canon?" = stated in ARCH / CL-PP / STATUS (the documents a fresh session reads). Y = yes, P = partly, N = memory/discussion only.

### A1. Identity, scope, goals
| # | rule / goal | source | Canon? | contradiction / problem |
|---|---|---|---|---|
| 1 | Goal: turn all Brazilian health records into trustworthy leads a person can act on (departures, structure, relations); a lead is a statistical object, never a conclusion | CL-PP §1.0, ARCH §1 | Y | none. But "a person" is never defined (see c1) |
| 2 | Ambition = general, systematic, principled, optimised | CL-PP §1.0 | P (CL-PP only; ARCH has P1-P16, not the four-word ambition) | none |
| 3 | PegaSUS is NOT a pipeline/ETL chain: one model, persistent state (fits, ledger, register), read many ways; a step-runner is an operational convenience | memory architecture-coverage-matrix (2026-10-07), WSR §4.4 | ARCH §1.1 Y; CL-PP §1.1 WT-fixed (HEAD: "PegaSUS is a pipeline of six stages") | ARCH §10.4 l.1085 "The full pipeline is run"; COV "(the pipeline (§9.3)..."; ARCH §9.3 "PegaSUS runs as a survey. Each data update triggers 1-4" reads as a chain; `update` module OK |
| 4 | Data-agnostic: no logic/constant specific to a system; ALSO never name a variable (PESO, length of stay, Apgar); derive every field from pegasus_data's typed roles (role, kind, model: mark/dimension/institution/stratum); a new system declared in pegasus_data must need no pegasus_core code; a missing role is fixed in pegasus_data curation | memory fields-from-roles ("angry"), stages-not-patches; docs/plans/2026-10-07-fields-from-roles.md | "no system-specific logic": Y (P16, CL-PP §6). "never name variables / roles only": N (plan + STATUS dormant row only) | ARCH §4.4 l.321 lists "length of stay, cost, birth weight, gestational weeks, Apgar"; §11.1 `marks` row "specs (length of stay, cost, death, ICU)"; §13.1 "marks v0 (PESO)"; §10.1 l.885/l.1035 "PESO negatives"; RUNBOOK l.36 `PEGASUS_SOURCE ... "mark": "PESO"`, l.31 "SIH length of stay"; COV §3 "PESO is named by the caller" |
| 5 | Whole system end to end first; depth only where a reading demands it ("architecture over polish"); a component is done only when it reaches the reader; time-box depth; fix a method until "sound enough to build on", record the debt, move on | memory architecture-over-polish, dev-conduct; WSR §5 | ARCH §12 (table only) P; CL-PP §1.2 P | WSR §5 "What stops" (no calibration before integration; no synthetic study without a real-data integration point waiting; no reruns of documented events to tune; no doc-only commits) is in NO canonical doc. STATUS l.3/l.11/l.95 still orders N1 -> N2 -> O6; OVH rule "One package at a time" (stage-ordered) |
| 6 | Steer by the coverage matrix / "planned and dormant" register, not the latest result (failed 3 times) | memory architecture-coverage-matrix | Y (CL-PP §1.2, STATUS register) | the matrix itself is stale (b: COV); the mechanism depends on an artefact nobody maintains |
| 7 | Speed is a requirement (the author's "top concern"): exploit structure, benchmark with time budgets, few fat jobs; "no resumption of development on unoptimised mathematics" | memory established-methods-first; plans/2026-10-06-optimization.md l.3 | Y (P13, ARCH §5.8, CL-PP §1.0/§3.3) | budgets cover fit times only (see c3); §5.8 "benchmark (`bench`, to build in O1)" is stale; the optimization plan's "Requirement (author)" line lives only in the plan |
| 8 | Scope exclusions: pre-1996 SIM (ICD-9 era) low priority: no ICD-9-era reader, no POP 1980-2012 source, no 1979+ harmonised series; ICD-9->10 mapping welcome | memory pre-1996-low-priority | N | ARCH §3.3 l.188 plans "SIM 1979-1995 ICD-9 tree ... the SIM series from 1979 in one tr..."; §3.4 backcast to 1991; COV |
| 9 | Frontend `../pegasus_view`: never touch, never plan, never list as pending ("not to touch this repo at all", 2026-10-05) | memory frontend-out-of-scope | CL-PP WT-fixed ("never touches"); HEAD: "contract ... is pegasus_data's to keep" | **CL-PD §4: "Keep ../pegasus_view working ... a change there is made in both repositories, or not at all"** and §1 "the sibling frontend ../pegasus_view reads"; ARCH §2 table lists pegasus_view role "presentation of ... leads"; COV §2 "pegasus_view presents leads later: NB" |
| 10 | MCP / agent / serving integration is planned WITH the author, never scheduled from the backlog; a paused front is committed, marked paused, never moved out of the tree; agents/MCP stay at S7 | memory plan-interfaces-with-user, dev-conduct | P (ADR-0008 "built, paused"; ARCH §11.1 mcp_server; CL-PP WT §1.3.7 "Ask before reshaping use") | ARCH §9.3 "exposed over MCP in phase 3" (phase 3 label dead); WSR §8.4 "whether MCP moves earlier than S7" left open and recorded nowhere |

### A2. Method and science
| # | rule | source | Canon? | contradiction / problem |
|---|---|---|---|---|
| 11 | Established method first: name the field's method + reference implementation before designing; use it or beat it by measurement; a threshold is never the answer to a modelling problem; maturity v0/v1/v2 stated, v0 never an end state | memory established-methods-first; P11 | Y | ARCH §13.1 maturity table is dated 2026-10-06 and stale (b) |
| 12 | Validation characterises, never gates; no question excluded for low power (weight it); documented events held out | P9, ADR-0028 | Y | ARCH §10 header: epidemiological checks "never tune a statistical constant" vs §10.0 "Real data first ... Discovery is judged first on real fields" and CL-PP check 8 (documented events judge stage-C methods first). Held-out-vs-judged-first is reconciled only by the sentence "a miss is a defect report fixed at its stage" |
| 13 | Real data with known answers, not the mock loop; synthetic worlds only calibrate FDR; report real results first | memory real-data-not-mock-loop | Y (ARCH §10.0, CL-PP check 8, STATUS) | see 12 |
| 14 | No ritual validation: never reconcile against TabNet/official totals as a routine step; verify only a suspicious number, a semantic claim, or a lead vs artefact | memory no-ritual-validation (2026-10-05) | **N** | CL-PP §5 "Count against an independent figure"; CL-PD §5 "count the rows against an independent figure (TabNet, the file's own row count)"; EVALUATION.md l.7 same. No canonical text says when counting against an independent figure is NOT wanted |
| 15 | Stages, not patches: one stage = one computation; statistical validity (B-D) apart from epidemiological (E); a failed null is fixed in B per field, never by per-system thresholds; relations joint, not pairwise | memory stages-not-patches; P16 | Y | none (but ARCH §7.0 still says departure models are "the next work", see b) |
| 16 | Never lose a question: a method retires only when its successor answers every question it answered, shown on the grid; say "takes over question X", never "dropped" | memory never-lose-a-question | Y (CL-PP §4) | in tension with S0 ("v0 survey removed (its 33,111 leads retired)", STATUS l.13), "no v0 left standing", ADR-0028 gate retired. No canonical doc shows the takes-over table for S0's removals (the question registry, plans/2026-10-07-questions-and-methods.md, is the mechanism but is not cited from CL-PP) |
| 17 | Re-scope, never dissolve: a recording explanation lifts a lead to its conserved level and re-tests; grade explanations tested/bound/consistent; only "tested" downgrades; define every term before using it in a report | memory rescope-not-dissolve | P14, §8.6 Y; "define terms" and the three grades' names: N/P | none |
| 18 | Test competing explanations: no semantic claim from a match rate alone; cite a source or test the rival | memory test-competing-explanations | N in PP; PD CL-PP §6 has only "Never guess a code's meaning" | belongs in CL-PD §6 (stage A); absent from both |
| 19 | Findings drive architecture: on every result ask "does this change a design assumption?"; keep the STATUS "Architecture learned from results" register; DECLARE promising leads (locus, window, pass criteria, negative control) in the ledger before the confirmatory look | memory findings-drive-architecture | P (register exists; ledger-before-run is §9.2) | the rule "ask on every report" is in no CLAUDE.md; the register is now 30 rows, many about demoted v0 designs |
| 20 | Always ask "can this be better?"; hand-fixed choices are debts to learn or integrate over; write the most general formulation first | memory always-ask-better | Y (CL-PP check 7, CL-PD §4) | none; duplicated verbatim in two CLAUDE.md |
| 21 | Honest coverage: state what is modelled / only context / never read; never overstate (calibration is necessary, not proof) | memory architecture-coverage-matrix | P (WT §1.3.6 "Say what was checked") | none |

### A3. Working conduct
| # | rule | source | Canon? | contradiction / problem |
|---|---|---|---|---|
| 22 | Decide, don't hand the author a menu; never present obvious choices as "decisions" | CL-PP/CL-PD §4; memory dev-conduct | Y | vs WT CL-PP §1.3.7 "Ask before reshaping use"; memory plan-interfaces ("discuss and plan with me"); stages-not-patches "Before building a big stage, write its design for the author"; WSR §8 "Decisions for the author" (a menu of four). No rule says which calls are the author's (use/interfaces, big-stage design, priority/scope) and which are the agent's |
| 23 | Never act outward as the author: no push, publish, contact; work on a branch, the author merges and pushes | CL-PP §4/§7, CL-PD §4/§7, memory ownership | Y | none (memory names a stale branch `redesign`) |
| 24 | Replace, never build beside; dead code removed | CL-PP §4/§7, CL-PD §4/§7 | Y | WSR §2 documents the opposite state (two stage-C surveys, two stage-D mechanisms, 31 scripts building models, 6 copies of one evaluation in `data/`); S0 is the fix |
| 25 | Never idle on a wait; advance another front; heavy fits one at a time through `scripts/heavy.py`/`data/chain.py`; detach, check it started, watcher for completion AND failure; no polling | CL-PP §4, CL-PD §4; memory coordinate-fronts | Y | RUNBOOK has no entry for `heavy.py`/`chain.py` (grep 0 hits) though CL-PP, WT §1.2/§1.3.3 depend on them; ARCH §5.7 has the only description |
| 26 | Core work is centralised on the main session; agents only for appendicular, crisp-deliverable work, never on files being edited | memory coordinate-fronts | N | CL-PP §4 "Subagents run on the cheaper model for reading, searching and auditing"; CL-PD §4 "background agents" run fronts concurrently |
| 27 | No subagents for development (2026-10-07); audits only if asked; Sonnet for any agent | memory dev-conduct, subagent-model | N (CL-PP: Sonnet only) | CL-PD §4 lets agents run fronts |
| 28 | Agent economics: short-lived, one bounded deliverable, no polling in briefs, handoff file `data/handoffs/<front>.md`, recycle at ~150k context/150 calls | memory agent-token-economics | N | concurrency: coordinate-fronts "At most 1-2 at a time" vs agent-token-economics "About 4-5 at once"; `data/handoffs/` (agent state) vs `docs/handoffs/` (requests to pegasus_data) are two things named "handoffs" |
| 29 | Documentation weight: fewer commits; docs ship inside the code commit; NO doc-only commits; ADR only for a final decision; measurements = few lines added to an existing entry; docs must not outweigh code | memory documentation-weight, dev-conduct; global CLAUDE.md | P: CL-PP §7 and CL-PD §7 have all except "no doc-only commits" | CL-PD §7 contradicts itself: bullet 1 "A measurement is a few lines, added to an existing evaluation where one fits" vs later "A measurement or live run is a new docs/evaluation/YYYY-MM-DD-<slug>.md and a row in EVALUATION.md, including one that changed nothing". WSR §3: 37 % of 239 commits were doc-only. PP canonical docs: ARCH 1271 + COV 490 + STATUS 124 + CL 311 lines against 19.5k lines of code, and each front is asked to update ARCH, STATUS, COV, EVALUATION, DECISIONS |
| 30 | No new unit tests; verify by running the real thing and reading the output; old suite rarely, in background | CL-PP §5, CL-PD §5, ARCH §11.5; memory | Y | none |
| 31 | Install the library the job needs, declare it in pyproject; never hand-roll a weaker substitute; ask only for heavy/licence-restricted | CL-PP §7, CL-PD §7, global | Y | none |
| 32 | Standing approval: downloads, installs, project-serving machine config, stopping/restarting the project's own jobs need no permission | memory downloads-approved | N | CL-PP §3.4 "never forces a large download implicitly"; CL-PD §3.4 "Nothing downloads the whole tree implicitly"; WT §1.3.4 "No hidden expensive default". Compatible only if read: approved but explicit and costed; not written |
| 33 | "Unreachable" is a finding: diagnose (curl -v, browser UA, other endpoints, in-app browser) before declaring a source down; write what was tried | memory diagnose-before-unreachable; global CLAUDE.md | global only | absent from both project CLAUDE.md (belongs in CL-PD §3 FTP/§6) |
| 34 | Use the `pegasus` conda interpreter explicitly | CL-PP §2, CL-PD §2 | Y | none |
| 35 | Read before asserting / check a fact before stating it | CL-PP §5, CL-PD §5, WT §1.3.2 | Y | none |
| 36 | Cost before running; no hidden expensive default; constants that decide what is reported are debts recorded in §13.2; "built" vs "checked on X" vs "done"; changes to default behaviour / use / a stage boundary go to the author first | WT CL-PP §1.3 (new, uncommitted) | WT only | duplicates the derailment check §1 (8 items) with a second 7-item list under another heading (§1.3). Two checklists |
| 37 | A context summary is not the plan: re-read STATUS/ARCH §12/§5.7-5.8/coverage after one | WT CL-PP §1.2 | WT only | none |
| 38 | Correct meaning beats every other budget (PD); a false statistical lead is worse than none (PP); never guess a code's meaning; unmapped code visibly undecoded; labels joined by validity window; etc. | CL-PD §3/§6, CL-PP §3/§6 | Y | none (these two lists are the only well-kept rules) |

### A4. Rule conflicts that need an explicit ruling
1. **pegasus_data ownership.** Memory ownership-and-testing: full control of PD (set in PD sessions, 2026-09-28). CL-PP HEAD §4: "Change pegasus_data directly only when the author asks"; ARCH §2 rule 2 and memory pegasus-redesign: requests go in `docs/handoffs/` (only 3 files, last 2026-10-06). STATUS l.62: "pegasus_data is developed from this session too: branch `pegasus-core-fixes`" (PD ADR-0153/0154 were made from it). WT CL-PP now says "developed from this session too", but ARCH §2 and README were not updated. Ruling needed: handoff only for bulk requests, or direct edits with PD's own CLAUDE.md?
2. **Agents:** 1-2 (coordinate-fronts) vs 4-5 (agent-token-economics) vs none for development (dev-conduct, newest, wins) vs "background agents" (CL-PD).
3. **pegasus_view:** untouchable (memory, WT CL-PP) vs "keep working, change in both repositories" (CL-PD §4).
4. **Menu vs consult** (row 22).
5. **Independent figure** vs no ritual validation (row 14).
6. **Held-out events vs judged-first events** (row 12).
7. **Retire v0 vs never lose a question** (row 16): S0 deletions need the takes-over table.
8. **Doc load**: "docs must not outweigh code" + "no doc-only commits" vs "every mechanism written into ARCH in the same commit" (WT §1.3.1) plus STATUS + COV + EVALUATION + DECISIONS per change. Needs one rule: which single document owns which kind of fact (d4).

---
## (b) Staleness inventory

### STATUS.md (124 lines)
- l.3 "**2026-10-06, evening: ARCHITECTURE revision 3** ... The next work is **N1**, the expectation's noise structure, then N2 -> O6 -> O7 -> O8" vs l.13 "**2026-10-07, roadmap revision 4:** ... S0-S7" and ARCH §12 (S0-S7, D). The file opens with the superseded order.
- Same file contradicts itself on N1: l.11 "next work is N1" vs l.52 "**N1 done**" and l.103 "**built**".
- l.95 "**The roadmap (revision 3, ARCHITECTURE §12).** The order is N1 -> N2 -> O6 -> O7 -> O8, with O3 and O9 alongside, then O10" + table l.97-111 (O0-O10): ARCH §12 no longer has this table. WSR §7 promised "the stage table gives way to a package table (S0-S7, D), each with its done-when": not done; S1-S7 have no state row.
- l.36 fields-from-roles "dormant since 2026-10-07" vs plans/2026-10-07-fields-from-roles.md "Status: building (S1, 2026-10-07)" vs ARCH §12 S1: one item, two states.
- Transient process states in a state document: l.53 "the first question survey ... running", l.54 "(O9, running)", l.52 "SBC running", l.83 "facility triage (running)", l.89 "re-triage running".
- l.62 "pegasus_data is developed from this session too: branch pegasus-core-fixes" vs ARCH §2 rule 2 and CL-PP HEAD §4 (contradiction, a4.1).
- l.64-93 "Architecture learned from results": 30 rows (~half the file), several about designs since demoted (E_w, lenses, theta0, alarm baseline "to be decided with ADR-0004's alarm design", "ADR-0007 under revision" though DECISIONS marks ADR-0007 superseded by ADR-0015, "re-triage running"). CL-PP §7 says STATUS is "rewritten, not appended"; this register is append-only.
- l.122 "tools over MCP ... not scheduled" vs ARCH §12 S7 "serving and agents".
- l.124 "Unblocked: ICD-10 U07/U09/U10 ... chapter XXII can be fitted (O2)" uses a retired label.

### CLAUDE.md / AGENTS.md (PP) (HEAD; WT = uncommitted fix)
- §1.1 HEAD "PegaSUS is a pipeline of six stages" (WT-fixed). §1.1 title still "revision 3" while roadmap is revision 4.
- §1.2 / §8 / §9 HEAD point to `docs/plans/2026-10-06-overhaul.md` (N1, N2, O1-O10) as the order of work (WT-fixed for §1.2, §8, §9 rows); §9 still has "the joint relation model's design (O7)" (O label).
- §1.0 "People and AI agents use it through a lead register and on-demand tools" vs MCP paused (ADR-0008), agents at S7.
- §1 duplicates ARCH (stage table §1.1, P1-P16 summary) although l.5 says "nothing is duplicated"; WT adds a second derailment checklist (§1.3) beside the 8-item one.
- §4 HEAD "Change pegasus_data directly only when the author asks" (WT-fixed, but ARCH §2 not).
- Absent: no-ritual-validation, no-dev-subagents, no-doc-only-commits, plan-interfaces-with-author, fields-from-roles, pre-1996 scope, standing download approval, agent economics.
- AGENTS.md = copy of CL-PP: both are in the modified set; keep them in lockstep (check_docs enforces).

### ARCHITECTURE.md
- Header: "Revision 3, 2026-10-06 (ADR-0029) ... the roadmap (§12)" and section map row 12 "roadmap: the overhaul's work packages"; §12 itself is "revision 4"; no ADR records revision 4 (DECISIONS ends ADR-0029). Revisions 2 and 3 each got one.
- §5.8 l.518 "The benchmark (`bench`, to build in O1)" vs COV "5.8 ... BM (`scripts/bench.py`)" and RUNBOOK l.19; "v0 measured" column mixes eras.
- §7.0 l.617 "its departure models are the next work (O6, after N1)"; "Departure models (§7.0, v1, to build)" vs §11.1 `departures` module ("O6, stage C" built), STATUS "O6 in progress"; §13.1 l.1234 "departure models | 7.0 | not built | O6" and l.1237 "relation models ... not built" while §11.1 lists `relations` (O7, stage D) built and STATUS l.54 "calibrated above the national scale". §11.1 `scans` row still says "`departures` (§7.0, to build)".
- §7.6 heading "Dependency maps (phase 3)": phase labels are dead; S0 removes `dependency_map` (WSR §6).
- §10 header ("Epidemiological checks ... never tune a statistical constant") vs §10.0 "Real data first" (a4.6). §10.0 l.~1000 "Those choices are re-made on the grid in work package O5" (done by ADR-0026, then superseded). §10.4 l.1085 "full pipeline".
- §11.1 `marks` row, §4.4, §13.1, §10.1 name variables (row 4 above). `tools` row "MCP server in phase 3". `mcp_server` row correctly says paused.
- §13.1 "Maturity by component (2026-10-06)": validation "v0 (... a gate)" (gate retired, ADR-0028); triage "v0 rules with thresholds"; "ICD ontology ... ICD-9 ... not used". It is not updated by any S-package.
- §13.2 departures: θ0 table (ADR-0026) described as current while STATUS l.103 says `MINIMUM_EFFECT_BY` "reduced to SIH's spatial cluster" (N1 landed); §7.7 "thresholds ... FAC_K = 3, FAC_SHARE = 70 % are v0 constants" (CL-PP WT §1.3.5 requires them here, with how they will be measured).
- Label zoo: stages A-F, phases 1-4, O0-O10, N1/N2, S0-S7, D, R0-R3, B0-B2s, B-tiers vs R-tiers. No legend maps O-packages to S-packages.
- §9.3 interface list and "Agents ... see the exploration half only" describe the confirmation reserve (ADR-0007/0015) still; fine, but agents are S7.

### docs/architecture_coverage.md (490 lines)
- Header "Audit of 2026-10-05, branch design-v0"; its found-issue note "ARCHITECTURE.md lost §8.4 ... and §8.5 ... in commit 4c0397a" is now false (both sections exist).
- Three stacked rankings: "ten most consequential gaps" (2026-10-05), "gaps re-ranked by the overhaul" (O1...O10, 2026-10-06), "re-ranked by revision 3" (N2, O6...). None by S-package. Gap 3 "low-rank interaction psi-omega-tau is not built" and gap 4 "horseshoe ... not built" contradict the same file's "BM since 2026-10-06"; gap 6 "Marks: only SINASC PESO"; gap 10 "Coverage ... narrow".
- WSR §7 promised "re-derived from the audits (nine errors)": not done. "Counts" table (216 items) predates it.
- §1 rows: "P9 nothing trusted before the harness | P" (P9 rewritten); "mark: PESO only"; "pegasus_view presents leads later NB".

### README.md
- "State: architecture accepted ... **revision 2** ... a v0 engine is built ... **development resumes with the overhaul** ..., starting with the solver." Three revisions behind. Document table omits STATUS's dormant register, `docs/plans/`, `docs/architecture_coverage.md`.

### RUNBOOK.md
- No `scripts/heavy.py` / `data/chain.py` entries (needed by CL-PP §4). l.36 PESO example (row 4). `pegasus-core fit|fields|...` list fine. Runbook says solver "v1 for every model" fine.

### DECISIONS.md / OPEN_QUESTIONS.md / EVALUATION.md
- DECISIONS: nothing for revision 4 / S0-S7 or for the 2026-10-07 mechanisms (fields-from-roles kinds, derived corroboration, link semantics, robust stage B default v9). ADR-0026/0027 "active; superseded as N1 / O6 land" with N1 landed and no status update. Sorting 0015 before 0014 (cosmetic).
- OPEN_QUESTIONS: WSR §8's four decisions for the author (approach, S1 vs S2 order and race position, S0 removals, MCP earlier than S7) are neither answered nor listed. OQ-4 "agent runtime" has no S-label.
- EVALUATION.md l.7 "count against an independent figure" (row 14).

### docs/plans/
- `2026-10-06-overhaul.md`: first paragraph "The current order is N1 -> N2 -> O6 -> O7 -> O8" (superseded by ARCH §12); "Running when development paused (2026-10-06)" job table is dead.
- Status lines inconsistent and stale: `o7-joint-relations` "Status: design for the author's review before the build" (built); `questions-and-methods` "Status: design (author's proposal)" (built, in the registry); `robust-expectation` "Status: design" (robust stage B is the default); `fields-from-roles` Status is a 1,900-character progress log that duplicates STATUS; `optimization` has no status and holds the speed requirement.
- No plan exists for S0, S2 (persons), S3 (race), S4-S7 although ARCH §12 names them (only S1 has one). CL-PD §9 names `linkage.md`/`linkage-theory.md` (PD side; fine).

### docs/discussion/ (frozen) and memory
- `2026-10-07-whole-system-review.md` "Status: a proposal for the author": adopted in ARCH §12 and dev-conduct, but not marked; its §7 document changes are half done (ARCH §12 yes; §1.1 yes; STATUS no; COV no).
- Memory notes stale: ownership-and-testing ("Work on branch `redesign`", "ADR for each decision"), pegasus-redesign-from-scratch ("Phase 0 (the harness) comes next"), established-methods-first ("paused for revision 2 ... plan overhaul.md"), python-env (suite timing), coordinate-fronts ("agents 1-2"), MEMORY.md index fine.

### PD (only what touches this audit)
- CL-PD §4 pegasus_view (row 9); §5 independent figure (row 14); §7 internal contradiction on evaluations (row 29); §4 "background agents".
- PD `STATUS.md`: "Last rewritten 2026-10-04 ... Work continues on branch `linkage`"; repo is on `pegasus-core-fixes` with ADR-0154 and `docs/plans/linkage*.md`; STATUS needs rewrite (not audited further).

---
## (c) Implicit goals never written as goals

1. **Who the reader is.** ARCH §1: "people and AI agents". In practice the author is the only reader (S5: "the author records verdicts"); CL-PD says "a person analysing Brazilian health data". Not stated: the persona (epidemiologist planning a study? the author?), the Portuguese/English split of outputs, what a reader may ask (the question list is code: `questions`, not a document), how a reader is expected to use leads ("follow leads into studies": README only), and what a reader may NOT infer (causation is in §6 rules, but not in a reader-facing statement).
2. **Definition of done for a reading.** WSR §5 defines "done = reaches the reader" and ARCH §12 gives per-package "done when" lines, but there is no general definition of a finished reading (declared field, fitted expectation, question asked, ledgered lead with method record, independent test, dossier) nor of "checked / built / done" outside WT CL-PP §1.3.6.
3. **Cost of a reading.** §5.8 budgets only model fits. Missing: seconds-to-hours budgets for `ask`, `survey`, `relations`, `report`, `dossier`, `update` ("A full update is hours", RUNBOOK l.30); whether an interactive reading (`expected(slice)`, `surprise`) must be seconds; the incrementality goal ("each reading redone only where its data or code changed", `update` docstring/RUNBOOK) is nowhere a stated requirement; no rule that a new default must state its cost (WT §1.3.3 is the first).
4. **Configurability and extension.** Not stated: that new systems/fields/questions arrive by declaration (pegasus_data roles; `plans/*.yml`; the questions registry), that constants are learned not configured (P7), what is configured by environment (`PEGASUS_SOURCE`, `PEGASUS_DEVICE`, `PEGASUS_SCORING_PROBES`) versus plan versus code. The principle "adding a system = zero pegasus_core code" (fields-from-roles) is a memory note and a plan paragraph.
5. **What counts as success of the project.** WSR §3: the real findings so far are recoveries of known events and catalogues of recording artefacts; one new finding (Y35 in Goias). No stated yield criterion (e.g. verdict-confirmed leads that were not already known; what the author would call a discovery); no statement that recovery of documented events is a necessary check, not the product.
6. **Precedence among goals.** CL-PP §3 ranks correctness first, then information, machine, FTP. Not ranked: whole-system breadth vs a method's soundness ("architecture over polish" sets priority, "not standards"), speed vs validity ("never bought with validity" is the only line), author consultation vs autonomy (a4.4).
7. **Stop rule for depth.** "Sound enough to build on" and "time-boxed" have no criterion (a method's record present and calibrated where it ran? one real-data reading?).
8. **Non-goals list.** Scattered: no causation, no pre-1996 reader, no frontend, no MCP before S7, no per-system constants, no ICD-9-era series, no ritual reconciliation. Never in one place.
9. **Relationship to pegasus_data as a product.** PD is open source with other users (ARCH §2); PP may be research code with a paper (brepi). Which repository's discipline governs shared work is the a4.1 conflict.
10. **Machine as a constraint vs a target.** 32 GB / RTX 4050 is a fixed constraint (CL-PP §3.3); whether PegaSUS should also run elsewhere or at larger scale is not said.
11. **Author-in-the-loop cadence.** Verdicts (S5), design notes before big stages, consult before reshaping use: no statement of when the author is asked versus informed.

Missing documents/sections: (i) goals/users/non-goals/done/cost section in ARCH; (ii) a work-label legend (stage vs phase vs O/N vs S); (iii) a standing-rules register of the author (dated, one line each, with the canonical home) so memory is a cache, not the source; (iv) S0, S2-S7 plans; (v) the reading-cost budget table; (vi) the pegasus_data roles contract (which roles/kinds/models pegasus_core reads, and who declares what) as a short ARCH §3.1 subsection; (vii) a recorded ruling on WSR §8's four decisions.

---
## (d) Proposed canonical homes, retirements

### d1. Where each rule lives (one home, others point)
| rule(s) (row #) | home | action |
|---|---|---|
| goal, ambition, user/reader, non-goals, precedence, definition of done, cost of a reading, configurability (1, 2, 5-8, c1-c11) | **ARCH new §1.2 "Goals, users, non-goals, done"** (30-40 lines, directly under §1.1) | write; CL-PP §1.0 shrinks to a pointer + the 4-word ambition |
| not-a-pipeline (3) | ARCH §1.1 (done) | delete the three "pipeline" strings (ARCH §10.4, COV, CL-PP HEAD); keep WT fix |
| data-agnostic + roles-only (4) | **ARCH P17 "Fields come from declarations"** (+ CL-PP §6 one line) | add; purge variable names in §4.4, §11.1 `marks`, §13.1, §10.1, RUNBOOK l.31/l.36 (say "a mark role", "a count-valued role") |
| system first / done-when / what stops (5) | ARCH §12 intro (paste WSR §5 "What stops" as 4 bullets) | add; STATUS drops its own order |
| steer by register not result (6) | CL-PP §1.2 (exists) | keep; make the register current (d2) |
| speed requirement (7) | ARCH P13 + §5.8; reading-cost rows in §5.8 | add budgets for ask/survey/report/update |
| pre-1996 and other scope cuts (8) | ARCH §1.2 non-goals; ARCH §3.3/§3.4 note "not built, low priority (author, 2026-10-06)" | add |
| pegasus_view (9) | CL-PP §4 (WT ok); **CL-PD §4 and §1 must change**; ARCH §2 table drop the "presentation" row or mark out of scope | edit PD and PP in the same commit; COV drop the NB row |
| consult-the-author boundary (10, 22, 36) | CL-PP §4, one table: "agent decides" vs "author decides" (method, defaults of cost-neutral choices, ADR content vs use/interfaces, a stage's boundary, a big stage's design, scope/priorities, anything outward) | write; delete WSR-style menus |
| established methods, validation, real data (11-13) | ARCH P9/P11, §10 (resolve a4.6: say "documented events judge stage-C/D methods first and are never a tuning target; a miss is fixed at its stage") | edit §10 header only |
| no ritual validation (14) | CL-PP §5 and CL-PD §5, replacing "count against an independent figure" with "where a number is suspicious or meaning is at stake" | edit both + EVALUATION.md l.7 |
| test competing explanations (18) | CL-PD §6 (stage A) | add one line |
| findings drive architecture, declare leads before testing (19) | CL-PP §5 (one bullet); register stays in STATUS (d2) | add |
| never lose a question (16) | CL-PP §4 (exists) + point to the question registry as the takes-over table; S0's removals listed there | add pointer |
| agents: Sonnet, no dev agents, centralised core, economics, handoff file path (26-28) | CL-PP §4 "Agents" 4-line block; rename `data/handoffs/` to avoid the clash or say "agent handoffs" | add; resolve 1-2 vs 4-5 (dev-conduct implies 0 for development; audits 1-2) |
| doc weight, no doc-only commits, who-owns-which-fact (29, a4.8) | CL-PP §7 table (extend with "owner of each kind of fact" column) | add the two missing rules to both CLAUDE.md; fix CL-PD §7 contradiction |
| downloads approved vs explicit costed (32), unreachable (33) | CL-PP §3.4 + CL-PD §3.4 / global CLAUDE.md | one sentence each |
| heavy.py / chain.py (25) | RUNBOOK rows | add |
| pegasus_data ownership (a4.1) | ARCH §2 rule 2 + CL-PP §4 + CL-PD | one ruling in all three; STATUS l.62 deleted |
| plan with author for interfaces/MCP (10) | ARCH §9.3 and S7 row; OPEN_QUESTIONS (WSR §8.4) | add |

### d2. Rewrites
- **STATUS.md** to: (1) 5-line state; (2) S0-S7/D package table (state, done-when, next step); (3) the planned-and-dormant register (rows that are S-packages merge into (2)); (4) stage table, one line per stage; (5) "Architecture learned" reduced to rows that still bind a design, rest moved to the ADR/evaluation they cite (they all cite one). Delete l.3-11 and l.95-122 O/N tables; no process states ("running"). Target about 70 lines.
- **ARCH**: header and section map to revision 4; add ADR for revision 4 (short: adopts system-first S0-S7; supersedes the order of ADR-0029's roadmap); §7.0, §13.1 refreshed in the same commit as S0; §13.2 gets the constants named in WT §1.3.5.
- **README** State block rewritten (3 lines).
- **CL-PP** (after WT): merge §1.3 into the §1 derailment check (one list, <= 10 items); drop the stage table and P list in favour of "ARCH §1.1 / §1" (saves ~45 lines); keep §3, §6.
- **COV**: choose one fate. Recommendation: keep it as the single item-level status (it is what the author asked for) but regenerate it per S-package from the code (as WSR §7 said) and delete its three stacked rankings and counts; ARCH §13.1 keeps maturity only. Otherwise the register in STATUS and COV keep diverging.

### d3. Retire / freeze / merge
- Freeze with a banner "record, superseded by ARCH §12": `docs/plans/2026-10-06-overhaul.md` (keep acceptance text of finished O packages), `docs/plans/2026-10-06-o7-joint-relations.md` (Status: built), `2026-10-07-questions-and-methods.md`, `2026-10-07-robust-expectation.md` (both built; Status -> "implemented, see ARCH §x").
- Keep as live: `2026-10-06-optimization.md` (speed plan); move its "Requirement (author)" sentence to ARCH §5.8.
- Standardise plan Status to one of design | building | implemented | superseded + one line; progress logs (fields-from-roles) move to STATUS or git.
- `docs/discussion/2026-10-07-whole-system-review.md`: mark "adopted 2026-10-07 as ARCH §12; open: §8.2 (S1 vs S2 order), §8.4 (MCP earlier)" and move those two to OPEN_QUESTIONS. Freeze the four audit files.
- Memory: after the standing-rules register exists in CL-PP, collapse the duplicates (documentation-weight, ownership-and-testing, dev-conduct, always-ask-better, subagent-model, agent-token-economics, coordinate-fronts) into one-line pointers; fix stale branch/phase statements (ownership, pegasus-redesign, established-methods-first).
- New documents: none beyond the new ARCH §1.2 and plans for S0, S2-S7 as each starts (design for the author before a big stage, per stages-not-patches). A separate GOALS.md is NOT proposed (weight rule).

### d4. Single owner per kind of fact (prevents re-drift)
| fact | owner | never in |
|---|---|---|
| what PegaSUS is, goals, principles, module map, departures | ARCH | STATUS, CLAUDE |
| how to work (rules, conduct, commands to run) | CL-PP/CL-PD (+RUNBOOK for commands) | ARCH, memory (memory = cache) |
| where the work stands, what is next, dormant register | STATUS | ARCH §12 (order only), plans |
| item-by-item built/measured status | COV | STATUS, ARCH §13.1 (maturity v-level only) |
| a final decision | ADR + DECISIONS row | STATUS prose |
| a measurement | one EVALUATION entry | STATUS rows (cite it) |
| a plan of one package | docs/plans/<date>-<pkg>.md | CLAUDE (pointer only) |
| a rule stated by the author | CL-PP/CL-PD with date and "(author)" | memory only |
