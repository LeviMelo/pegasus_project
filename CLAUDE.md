# CLAUDE.md: pegasus_project

**`AGENTS.md` is a byte-for-byte copy of this file.** Different agent runtimes read one name or the other. A change to either is written to both in the same commit; `scripts/check_docs.py` fails when they diverge.

This file says **how to work here**. What PegaSUS *is* lives in `ARCHITECTURE.md`; nothing is duplicated. Before adding a rule here, ask whether it is a decision (an ADR) instead.

---

# 1. What this repository is

PegaSUS fits one hierarchical model of Brazil's health events ("normal Brazil", the monolith) from all the data, and reads **leads** from it:
- where the data depart from it;
- what its structure shows;
- how departures relate.

People and AI agents use it through a lead register and on-demand tools. The package is `pegasus_core`.

**Its data module is `../pegasus_data`.** Every input arrives through pegasus_data's public API, imported only in `pegasus_core.gateway`. A data capability PegaSUS lacks is requested in pegasus_data (`docs/handoffs/`), never re-implemented here.

The earlier attempts (April–July 2026) are history: `docs/RECOLLECTION.md`, `docs/history/`. **They are read for reasoning, never as instructions.**

## 1.0 Goal, ambition and principles (read before any work)

**The goal.** Turn everything Brazil records about its health into **trustworthy leads** that a person can act on:
- what departs from "normal Brazil";
- how fields relate;
- what the structure shows.

The data cover deaths, admissions, births, notifications, procedures and more, by place, period, age, sex and code. A lead carries its effect, its certainty and its method's record.

**The ambition**, which every piece of work must serve:
- **General.** Every method works for any field of any system, at any grain, with no logic or constant specific to one dataset, disease or place.
- **Systematic.** It searches all fields, all places, all periods and all relations at once, with the multiplicity of the whole search designed in, never a hand-picked case.
- **Principled.** It uses the field's established statistical method (P11), with each estimate's uncertainty calibrated and its claim's error rate controlled.
- **Optimised.** It exploits the model's structure: sparse arrowhead solvers, GMRFs, factorised totals, low-rank joint structure. It runs on this machine in budgeted time. Speed is a feature, but never bought with validity.

**The core concepts:**
- the monolith's **expectation** (stage B), with its noise structure;
- **departure models** (C);
- one **joint relation model** (D);
- **interpretation** (E);
- **use** (F).

The bench (planted signals in refitted worlds, null worlds, SBC) characterises B–D statistically.

**Principles P1–P16 (ARCHITECTURE §1), in short:**
- **P1** Expectation first: nothing is judged except against its modelled expectation.
- **P2** Events and marks are modelled, not correlations of columns.
- **P3** Every cell carries its information weight.
- **P4** Estimands are declared, each with its own reference and null.
- **P5** Effects are tested against a minimum *relevant* effect, and the search's multiplicity is designed.
- **P6** Structure priors pool levels, never relations.
- **P7** Every strength is learned or measured, never set by hand.
- **P8** Observed stays observed; modelled inputs carry their uncertainty.
- **P9** Validation characterises, never licenses: power, calibration and false discoveries are reported, and nothing is gated.
- **P10** No dense object larger than the population tensor.
- **P11** The established method comes first; a threshold or a check is never the answer to a modelling problem.
- **P12** Departures and relations are model terms read through posteriors, not tails of residual statistics.
- **P13** Exploit structure, and budget speed with a benchmark.
- **P14** Recording is measured: leads are re-scoped, never dissolved by untested explanations.
- **P15** Race is an axis, read through its misclassification.
- **P16** One stage, one computation: statistical validity in B–D, epidemiological only in E; a failed null is fixed in B, per field, never by per-system thresholds.

**How work derailed (2026-10-06, 2026-10-07), and the check that prevents it.** On 2026-10-06 a day went into tuning v0 residual lenses with per-system thresholds, comparing variants by trial, and testing relations pairwise. On 2026-10-07 a dozen mechanisms landed while the canonical documents went stale, six-hour runs were launched without a look at the budgets, and untested work was called done. Each step was locally reasonable and globally against the principles. Before and after any change, answer:
1. **Which stage is this?** Does it stay inside that stage?
2. **Is it general?** Would it work, unchanged, on a system I have not looked at? If it needs a per-system constant, the cause is in another stage, usually B.
3. **What is the established method** for this estimand? Am I building it, or patching a v0?
4. **Am I fixing the cause, or a symptom?** A failed null is a model defect; lead volume is a ranking question; "is it real?" is stage E's.
5. **Does it follow the roadmap's order** (STATUS, ARCHITECTURE §12)? Am I improving something the architecture has already demoted?
6. **Is the computation structured and budgeted** (P13)? Does it scale to all fields at once?
7. **Can it be made better?** (author, 2026-10-07; ask it at every design step and again before calling anything done.)
   - Is there a more general, more principled, more robust formulation of this, more aligned with P1–P16?
   - What did I fix by hand that the data or the model could choose: a partition, a scale grid, a shape list, a lag range, a graph? Each is a candidate to be learned or integrated over.
   - What would the strongest critic of this method say first?
   - Write the most general formulation down before simplifying, and name each simplification as a debt with its remedy.
   - The fixed ladder of administrative supports (2026-10-06) was built under time pressure and accepted until the author challenged it. That question should have been asked first.
8. **Is it judged on real data with known answers?** (author, 2026-10-07.)
   - A synthetic world built from the model's own law, scanned by a method that assumes that law, measures internal consistency only: a synthetic problem has a synthetic solution by construction.
   - Synthetic worlds serve calibration (false discoveries need known truth) and nothing more.
   - Discovery is judged on real fields:
     - documented events, found where, when and at what scale they happened (`data/real_events.py`);
     - positive controls (one disease in two systems);
     - real-data negative controls (time reversal, place permutation).
   - Every method is also judged by reading its strongest real findings as epidemiology.
   - Of 2026-10-06/07's measurements most were synthetic; the meaningful ones were the real relation map, SIH's local family and stroke's spatial noise.

9. **Locate it.** Name the ARCHITECTURE section the change touches. A new or changed mechanism, object, field kind, plan key, default or constant is written into that section (or §13.2 as a departure) **in the same commit**. Documentation that tracks the code is part of the change, not a later chore.
10. **Read before asserting.** Describe a subsystem only after reading its code, its ADRs and its evaluations (race, on 2026-10-07, was summarised from memory and misstated).
11. **Cost before running.** Estimate a run's work (fields × methods × years × replicates; fits, reads, links, downloads) against §5.8. Check on one field or one year first. Run at full scale only when a reading the author needs requires it, never to confirm what the code and an inspection settle. Heavy jobs go through `scripts/heavy.py` and `data/chain.py`, never another queue.
12. **No hidden expensive default.** A national linkage, a refit of other blocks, a re-decode: nothing heavy starts implicitly. It is requested, and its cost is visible.
13. **Constants are debts.** A constant that decides what is reported (a minimum effect, a list, a threshold) is recorded in §13.2 with how it will be measured (P7), never left as a silent gate.
14. **Say what was checked.** "Built" means the code exists; "checked on X" names what ran; "done" means the acceptance criterion is met. Never commit unverified work described as working.
15. **Ask before reshaping use.** A change to what the system computes by default, how it is used (§9.3) or a stage's boundary is discussed with the author first.

If any answer is wrong, stop, re-plan, and write it down before coding.

## 1.1 The six stages (ARCHITECTURE §1.1, revision 3, ADR-0029)

PegaSUS is **one model of the marked point process, read in six stages**, one computation each: readings of one persistent state (the fits, the ledger, the register), **not a pipeline and not a build order** (author, 2026-10-07). Every piece of work starts by naming the stage it belongs to.

| stage | question | judged by |
|---|---|---|
| **A. Data and meaning** (pegasus_data) | what was recorded, for whom, under which code? | correct meaning |
| **B. Expectation** (the monolith) | what is expected, and how does its noise behave, including its serial dependence? | statistical calibration (PIT, held-out, SBC) |
| **C. Departures** | is there a departure of a declared shape against a declared reference, and how large? departure terms in the model, read through their posterior | statistical: the grid and null worlds |
| **D. Relations** | which fields move together, and which leads which? one joint model of all fields' departures | statistical: planted relations, null worlds |
| **E. Interpretation** | is a statistical lead a real event, a recording artefact, or already known? | **epidemiological**: recording, replication, corroboration |
| **F. Use** | what does a person read first? | usefulness: ranking, reports, surveillance |

- **Statistical validity lives in B–D;** whether a departure is real is decided in E and nowhere earlier.
- **A method is general.** It carries no logic or constant specific to one data system.
- **A mis-stated null is a defect of B's noise model,** fixed there and measured per field, never patched with thresholds in C.
- **Lead volume is F's ranking question,** never a reason to move a test.

The 2026-10-06 course correction that set this out is `docs/discussion/2026-10-06-course-correction.md`.

## 1.2 Start of every session, and after every context summary

Read, in this order:
1. `STATUS.md` (where each stage stands, and what is next);
2. ARCHITECTURE §1.1 (the stages), §12 (the roadmap S0–S7 and its order) and §5.7–5.8 (the machine, the job runner, the performance budgets);
3. the plan of the package at hand (`docs/plans/`, the newest that covers it);
4. `docs/architecture_coverage.md` for the item at hand.

**A context summary is not the plan.** After one, re-read these before the next change: on 2026-10-07 work resumed from a summary, and the speed plan, the job runner and the budgets were never consulted.

Steer by the roadmap's order and the coverage matrix, not by the latest result.

---

# 2. Run it

**The runtime is the shared conda environment `pegasus`.** It holds pegasus_data (editable) and this package (editable). Use its interpreter explicitly:
- `python` on PATH is a bare interpreter without either package;
- conda **base** imports an unrelated older project.

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
PYTHONUTF8=1 $PY -m pip install -e . --no-deps    # once; dependencies are already in the env
$PY -m ruff check src scripts
$PY scripts/check_docs.py
```

- **Encoding.** Set `PYTHONUTF8=1`: labels are Portuguese.
- **The GPU** is an RTX 4050 laptop part with 6 GB (CUDA 12.1, through PyTorch). Chunk GPU work to 4 GB.
- **Homes.**
  - PegaSUS writes only under `PEGASUS_HOME` (default `pegasus_home/`, gitignored).
  - It reads pegasus_data's home through pegasus_data, never directly.
- **Long runs detach.** The Bash tool caps background work at ten minutes, so start longer jobs with PowerShell `Start-Process` running `scripts/heavy.py` (§4), logging beside them. Check that the process started, and watch it with a filter that catches failure as well as success.

---

# 3. What binds

1. **A correct statistical claim.** A false lead is worse than none: it is followed, and it costs a study. Every other budget yields to this one.
2. **Information.** The data hold a finite amount of evidence. Searching more cannot create more. Size every search to it (ARCHITECTURE §8.4).
3. **Wall clock and memory on this machine** (32 GB RAM, 6 GB GPU). Correct but unusably slow is not finished. **No dense object larger than the population tensor** (ARCHITECTURE P10).
4. **The FTP server and disk** are pegasus_data's constraints. PegaSUS never forces a large download implicitly. Downloads and installs the project needs are approved in advance (author, 2026-10-05), but each is explicit and its size known before it starts.
5. **Scope** (author, 2026-10-06): the ICD-9 era (SIM before 1996) is low priority; an ICD-9 → ICD-10 mapping is welcome, an ICD-9-era reader is not planned.

---

# 4. Autonomy

- **Decide what is the agent's; ask what is the author's.** Do not hand the author a menu of obvious choices, and do not present them as "decisions" (author, 2026-10-07).

  | the agent decides, records and proceeds | the author decides (bring a recommendation) |
  |---|---|
  | methods, estimators, numerical choices, fixes, refactors, the documentation | goals, the reader, what a finished reading is |
  | an ADR once a decision is final | use and cost: how a reading is chosen, bounded and shown (ARCHITECTURE §9.3) |
  | the order of work inside a package | interfaces, serving, agents and MCP (S7; author, 2026-10-05 and 2026-10-07) |
  | | scope, priorities, the roadmap's packages; a big stage's design before it is built |
  | | anything outward: push, publish, contact |
- **Never act outward as the author.** Pushing, publishing, submitting and contacting anyone need explicit authorisation, each time.
- **Replace, never build beside.** Before adding a mechanism, find the one that does the job (ARCHITECTURE §11.1). Two mechanisms for one job is a defect.
- **Never lose a question** (author, 2026-10-06). A method is retired only when its successor answers every question it answered (retrospective and prospective, every support, every shape), measured on the grid. Until then both run, and the docs say "takes over question X", never "replaces" or "drops". A method that answers wrongly is fixed or kept with its record; a question is never withdrawn because a method for it failed.
- **Carry the whole request.** Each instruction is done, or reported as not done with the reason.
- **Never idle on a wait; work fronts in parallel** (author, 2026-10-03, repeated 2026-10-06). While a fit, a scan or an agent runs, advance a task that does not depend on it: other code, documentation of finished work, analysis of results at hand. Launching a job and then waiting on it is the failure this rule names.
  - **Parallel is my work, not the heavy jobs.** Heavy fits run one at a time through `scripts/heavy.py` (a sequence through `data/chain.py` under one slot), within RAM: six concurrent fits paged the machine at 50,000 pages/s and every one of them crawled (2026-10-06).
  - Launch detached, check it started, set a watcher that catches completion and failure, then turn to the next front at once.
- **Subagents** (author, 2026-10-07): none for development; core work stays in the main session. Read-only audits and surveys only, on Sonnet, few (one to three at once), each with one bounded deliverable written to a file, no polling in the brief.
- **Keep pegasus_data and pegasus_view working.**
  - pegasus_data is developed from this session too (branch `pegasus-core-fixes`), under its own CLAUDE.md: a declaration PegaSUS reads is made there, with its evidence, never guessed here.
  - pegasus_view's contract with pegasus_data is pegasus_data's to keep; PegaSUS never touches pegasus_view.

---

# 5. Measure, do not assert

- **The harness is the test suite** (ARCHITECTURE §10): known positives, known negatives, planted signals and null surrogates, on real data.
  - A statistical capability is verified by running the harness cases it affects, and by **comparing on identical data**: old code against new; approximate against exact fits, on samples across scopes, never only the densest slice.
  - **No unit tests written alongside the change:** they pass by construction.
- **Read the output, not the exit code.** Look at the leads, maps and numbers. **A number that looks implausible is a bug report until shown otherwise.**
- **No ritual validation** (author, 2026-10-05). Reconcile against an independent figure (TabNet, an official total) only where a number is suspicious or meaning is at stake, never as a routine step. **Not everything is confirmed by a run** (author, 2026-10-07): what inspection of the code and a small check settle is not run at national scale.
- **Findings drive architecture** (author, 2026-10-06). On every result ask whether it changes a design assumption; if so it goes to ARCHITECTURE (or §13.2) in the same commit. A promising lead is declared in the ledger (locus, window, criteria, negative control) before its confirmatory look.
- **A synthetic that reproduces a symptom can validate the wrong mechanism.** Confirm every fix on the real object, and rerun the headline result after it.
- **Locate a phenomenon in the model before fixing it.** A recurring patch means a missing abstraction.
- **Check a fact before stating it:** a count, a date, what a document or a paper says.
- **Profile before optimising.** Record budgets as measured, never as hoped.

---

# 6. Statistical non-negotiables

Cheap to violate, expensive to discover. The reasons are in ARCHITECTURE §1 and §11.4.

```text
No statistic on a value without its expectation and its information weight.
Expectation first; any Gaussianisation (PIT) comes after it, never before.
The estimand is declared: between places, within places over time, between groups, between institutions.
Effects are tested against a minimum relevant effect, never against zero alone.
Every test is in the ledger before it runs; the ledger is the denominator of every error rate.
Every null preserves the dependence of what it tests; no p-value has a Monte-Carlo floor.
Taxonomies pool levels, never relations.
Every strength (variance, rank, graph, threshold) is learned or calibrated, never set by hand.
Context is never part of a default expectation tier.
A miscalibrated field never enters a pair scan at the tier where it failed.
Overlapping fields (measured shared events) are never tested as independent.
Observed stays observed; modelled inputs carry their model version and uncertainty.
Every random draw is seeded; every artefact carries its data and code versions.
A lead is a statistical object, not a conclusion; nothing claims causation.
One stage, one computation: no object fuses expectation, departure, relation, interpretation or use.
No method carries logic or constants specific to one data system.
No field names a variable: every field comes from a pegasus_data declaration (author, 2026-10-07; ARCHITECTURE §3.2).
A null that fails is fixed in the expectation's noise model, measured per field, never by a threshold.
Statistical claims (stages B-D) never decide whether a departure is real; that is stage E's.
Relevance lives in the departure posterior or the ranking, never in a calibration patch.
Relations are found jointly across all fields; pairwise tests only confirm.
```

---

# 7. Code, documentation, commits

**Code.**
- Python 3.11.
- `ruff` is clean.
- Modules follow ARCHITECTURE §11.1 and import downward only.
- A module is created when it is built: no stubs.
- New capability goes in `src/pegasus_core`, behind the Python API, then the CLI.
- Scripts are for maintenance and measurement only.

**Dependencies.**
- Install what the job needs into the `pegasus` environment and declare it in `pyproject.toml`.
- **Never hand-roll a weaker substitute** to avoid a library.
- Ask the author only for a heavy or licence-restricted dependency.

**Documentation is light and ships with the change, in the same commit.**

| change | where it is written |
|---|---|
| a **final decision** | `docs/decisions/ADR-NNNN-<slug>.md` + a row in `DECISIONS.md`. **Never for a step in progress or one later withdrawn.** |
| a **measurement** or harness run | a few lines, added to an existing `docs/evaluation/` entry where one fits, else a new dated entry + a row in `EVALUATION.md`. A table only when it carries the numbers. |
| a module boundary or persistent object | `ARCHITECTURE.md` (§13 for knowing departures) |
| the state of the work | `STATUS.md` (rewritten, not appended) |
| a new command | `RUNBOOK.md` |
| an open question | `OPEN_QUESTIONS.md`. A resolved row moves to `docs/history/open_questions_resolved.md`, whole and annotated. |
| what PegaSUS needs from pegasus_data | made in pegasus_data under its CLAUDE.md, or `docs/handoffs/` |

**One owner per kind of fact** (survey 2026-10-07). A fact is written once, in its owner; every other document points to it. Memory is a cache of these documents, never the only home of a rule.

| fact | owner |
|---|---|
| what PegaSUS is: goals, principles, objects, module map, departures and hand-set constants | `ARCHITECTURE.md` |
| how to work, and every rule the author states (dated, "author") | this file; commands in `RUNBOOK.md` |
| where the work stands, what is next, the dormant register | `STATUS.md` |
| each architecture item's status | `docs/architecture_coverage.md` |
| a final decision | an ADR and its `DECISIONS.md` row |
| a measurement | one evaluation entry |
| the plan of one package | `docs/plans/<date>-<package>.md`, its status one of design, building, implemented, superseded |

- **No documentation-only commits** (author, 2026-10-07): documentation ships in the commit of the change it describes. A commit that changes a module, a constant or a default updates its owner in the same commit.
- **A documented number found wrong is corrected where it was written,** saying so there.
- **The documentation must not outweigh the code it describes.**
- `scripts/check_docs.py` stays green.

**An evaluation entry names:**
- the harness case or script, and its artefact under `pegasus_home/` or `data/`;
- what was counted, and why it is the thing that matters;
- the regime: commit, data versions, date.

**Studies** live under `studies/<name>/`, each with its scripts, results and a journal holding the claims and the numbers behind them. Every number in a text carries its measure, interval and denominator, and names the data version it came from.

**Commits.**
- Batch related work into one commit, not one per increment.
- Work on a branch; the author merges and pushes.

---

# 8. The repository

| path | what |
|---|---|
| `src/pegasus_core/` | the package |
| `scripts/` | maintenance and measurement scripts (`check_docs.py`) |
| `studies/` | studies done with PegaSUS and pegasus_data |
| `assets/brand/` | logo (`pegasus-logo.png`), wordmark, mark |
| `docs/decisions/`, `docs/evaluation/` | ADRs and measurements, indexed by `DECISIONS.md` and `EVALUATION.md` |
| `docs/plans/` | each package's design and acceptance (the order of work is ARCHITECTURE §12), the speed plan and budgets (`2026-10-06-optimization.md`) |
| `docs/architecture_coverage.md` | every ARCHITECTURE item against the code and the evidence, and the gaps ranked |
| `docs/handoffs/` | requests to pegasus_data |
| `docs/discussion/` | design reasoning, dated, frozen once superseded |
| `docs/history/`, `docs/digests/`, `docs/RECOLLECTION.md` | the earlier PegaSUS documents, extractions of them, and resolved questions; frozen, read for reasoning only |

**Gitignored:** `pegasus_home/`, `data/`.

---

# 9. Where to look

| need | read |
|---|---|
| where the work stands, stage by stage, and what is next | `STATUS.md` |
| what PegaSUS is: the six stages (§1.1), principles P1–P16, mathematics, code, roadmap (§12), maturity and departures (§13) | `ARCHITECTURE.md` |
| the order of work | ARCHITECTURE §12 (S0–S7); each package's plan in `docs/plans/` (the 2026-10-07 plans; `2026-10-06-overhaul.md` is the earlier packages' record) |
| the solver's speed design and timings | `docs/plans/2026-10-06-optimization.md` |
| the joint relation model's design (O7) | `docs/plans/2026-10-06-o7-joint-relations.md` |
| how much of the architecture is built and measured, item by item; the gaps ranked | `docs/architecture_coverage.md` |
| accepted decisions | `DECISIONS.md` (an index; one file per ADR under `docs/decisions/`) |
| measurements, harness and grid runs | `EVALUATION.md` (an index; entries under `docs/evaluation/`) |
| open questions | `OPEN_QUESTIONS.md` |
| commands | `RUNBOOK.md` |
| terms | `GLOSSARY.md` |
| why revision 3 (the stages; what was fused; what changed) | `docs/discussion/2026-10-06-course-correction.md` |
| why revision 2 (the overhaul) | `docs/discussion/2026-10-06-architecture-review.md` |
| why each original design choice was made | `docs/discussion/2026-10-04-design-v0.2.md` |
| what the earlier engine actually did | `docs/discussion/2026-10-03-what-was-built.md` |
| what PegaSUS asked of pegasus_data | `docs/handoffs/` |
| studies done with PegaSUS | `studies/` |
| the earlier ideas | `docs/RECOLLECTION.md`, `docs/history/`, `docs/digests/` |
| data, meaning, sources | `../pegasus_data`: its `README.md`, `ARCHITECTURE.md`, `DATA_SOURCES.md` |

**Read an index, then the entries a task needs; never a whole folder.**
