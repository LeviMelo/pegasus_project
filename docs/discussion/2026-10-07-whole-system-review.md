# Whole-system review and a new roadmap (2026-10-07)

**Status:** a proposal for the author, written at their instruction after three days of development produced, in their words, "a mess of a system, poorly integrated, with fancy models".

**How it was made.** Four independent audits, read-only, against the code rather than the existing status documents:
- (A) pegasus_core's integration;
- (B) pegasus_data's capabilities against what PegaSUS consumes;
- (C) ARCHITECTURE.md item by item;
- (D) the evidence base and where the effort went.

Their full reports are kept beside this note (`docs/discussion/2026-10-07-review/`). This note is the synthesis, and the plan that follows from it.

---

## 1. What PegaSUS is meant to be

ARCHITECTURE §1: Brazil's health data are observations of **one marked point process**. Events happen to **persons**, at **places** and **times**, each carrying **marks**, recorded by **institutions** under codes. They are read by age, sex **and race**.

PegaSUS fits one hierarchical model of that process, reads leads from it (departures, structure, relations), interprets them, and serves the readings to people and agents.

## 2. What exists

**What is modelled.** One slice of that process: **counts** by municipality × year × age band × sex, per ICD chapter. They come from SIM, SIH, SINASC and the SINAN agravos.

**That slice is deep.**
- The solver: exact Newton on the arrowhead Hessian, with LAML strengths.
- Robust fitting, a measured noise structure, multiscale departure tests, shape attribution, a band factor model for relations.
- Three calibration audits, each of which found and fixed a real defect.

**Everything else the architecture names is absent, standalone, or a stub.**

| the architecture's object | state (audits C, A, B) |
|---|---|
| **persons** (record linkage, §3.1, §7.8) | pegasus_data links SIH→SIM (91 % of in-hospital deaths at ≤ 1 % false matches), infant deaths→SINASC, women's deaths→mothers, CIHA, for 2021–23. pegasus_core never imports a link table. `scans/cohort.py` waits for draws that nothing supplies |
| **marks** (§4.4, P2) | pegasus_data types 1,540 columns, ~90 % marks or dimensions; PegaSUS reads none. `marks.py` is reached only from a script |
| **race** (§3.4, P15) | not an axis of G; no race terms, no disparity estimand |
| **institutions** (§4.5) | a triage read and an opt-in supply term; no institution term in the likelihood; the lattice is script-reached |
| **the lattice's ages** (§3.2) | POPSVS's 18 bands, not the 33 classes with single years 0–19 |
| **the top model and model choice** (§5.6) | absent; the low-rank interaction is built and off everywhere |
| **departures as model terms** (P12, §7.0) | only the Bayesian step gives posteriors. The others are p-value procedures, and answers carry no interval |
| **lead kinds** (§9.1) | answer and relation only. Pattern, cohort, observation and structural are declared, never produced |
| **method records on leads** (§9.1, §10.5) | a hand-written table for v0 lenses. Answers assert `calibrated=True` with no record. The grid and the event record write results nothing reads |
| **the ledger** (§9.2: no test outside it) | stage D writes no ledger entry |
| **stage E** (§8.3, §8.6) | the default path replicates by splitting the same data, which ADR-0015 withdrew. The independent-unit tests (temporal, spatial, corroboration) run only on v0 leads, from scripts. The conserved level is read by nothing |
| **use** (§9.3) | a Markdown table sorted by q (the §9.1 rank is ignored); no dossier, no human verdict, no data-update trigger. MCP lacks the new verbs |
| **breadth** (O9) | CIHA, SIM foetal deaths, SIA/APAC, SIGTAP, aggregates, climate, availability, care flows, 29 of 35 CNES supply fields: served, unread |

**Integration debt** (audit A):
- two stage-C surveys write one register;
- two stage-D mechanisms (`dependency_map` and `relation_map`);
- surveillance, `joint`, `compare` and `relation` print rows and register nothing;
- 31 scripts build models outside the package;
- `data/` holds six near-identical copies of one evaluation;
- layering inversions (the gateway imports surveillance; the monolith imports multiscale);
- pegasus_data imported outside the gateway;
- 14 lead-register and 13 ledger variants in the home.

## 3. Where the effort went

From audit D: 239 commits over four days.

| share | of what |
|---|---|
| 37 % | documentation-only commits |
| 33 % | stage B, of the code-bearing commits |
| 11 % | stage C |
| 3 % | stage D |

Synthetic harness work grew from 5 % of commits on 10-05 to 28 % on 10-07.

The real-data findings are, almost entirely, recoveries of events already known, and catalogues of recording artefacts. Neither is new knowledge about health. The one substantive new finding is Y35 in Goiás.

Several declared real-data positives failed and were not pursued: Rio Doce; Brumadinho in SIH; the family-health strategy against infant mortality; the trend across state borders (0 of 30); group disparity (recall 0.05).

## 4. Why it happened

1. **The roadmap is depth-first by stage.** §12 orders N1 → N2 → O6 → O7 → O8, "with O3 and O9 alongside". A stage-by-stage order on a system whose purpose lives in the whole means the downstream stages, and every axis of the process except counts, wait behind the polishing of the upstream ones. Each stage can always be made more correct, so the wait never ends.
2. **I chose work from the latest number.** A miscalibrated statistic is always more urgent than an unread section of the architecture. The coverage matrix existed and went stale. The author corrected this on 10-05, and again on 10-07 twice, and it recurred.
3. **"Validation" became the work.** Each method was perfected against its own null before the system existed to use it. Documented events were rerun six times on one method family.
4. **The architecture's own wording invites it.** §1.1 calls PegaSUS "a pipeline of six stages", and I built it as one: a chain of batch steps over counts. It is one model of a marked point process, with persistent state, read many ways.

## 5. The new approach: system first, then depth

**The rule.** Every object of §1 (persons, places, times, marks, institutions, codes, race) enters the system **end to end** at v0/v1 before any method is deepened. End to end means:
- declared fields come from pegasus_data;
- a fitted expectation;
- the questions asked of it;
- leads in the one register, ledgered, with their method record;
- stage E's independent tests;
- a reading a person can act on.

A component counts as done only when it reaches the reader. Depth is added afterwards, where a reading shows it is needed, and is time-boxed.

**What stops.**
- No calibration work on a method until the component it serves is integrated end to end.
- No synthetic study without a real-data integration point waiting on it.
- No reruns of the same documented events to tune a method.
- No documentation-only commits: the docs ship with the change.

## 6. The roadmap

Each work package lands end to end before the next one starts. Inside a package, parallel fronts are fine.

| # | package | delivers, end to end | done when |
|---|---|---|---|
| **S0** | **Consolidate** (integration debt, no new capability) | one lead writer per kind; v0 lenses only as methods inside questions; one stage-D mechanism (`relation_map`; `dependency_map`'s context fields become relation fields); every test ledgered (stage D included); method records computed from the grid and the event record and attached to every lead; the gateway the only import of pegasus_data; dead code and the `data/` duplicates removed; one register and one ledger in the home; the runner renamed and reframed as §9.3's update of persistent state | `scripts/codehealth.py` and a reachability check pass; every lead in the register has a method record |
| **S1** | **Fields from declarations** (`docs/plans/2026-10-07-fields-from-roles.md`) | the field registry built from pegasus_data's event types and roles: counts per classifier node, marks by declared scale, compositions from dimensions, the institution lattice from institution roles; pegasus_data declares what is missing (a number's scale, order); `marks.py` integrated as the mark expectation | for SIM, SIH, SINASC and SINAN, every declared column is a field or names why not; one chapter's marks and compositions are asked the questions and read in the report |
| **S2** | **Persons** (linkage, §7.8) | the gateway reads pegasus_data's link tables and draws; `cohort()` in the API; outcome-after-event fields from declared links (death after admission, infant death after birth, death after notification); cohort leads; person-level corroboration in stage E | one cohort scan and one outcome-after-event field in the register with linkage uncertainty (Rubin across draws) |
| **S3** | **Race** (§3.4, O3) | race in G where the account carries it (SIM, SINASC, SINAN); recorded race through the measured confusion; the disparity estimand as a question | births and infant deaths fitted with race; disparity answers in the report |
| **S4** | **Interpretation that is independent** (§8.3, §8.6) | the default stage E runs the independent-unit tests (later years, other places, other systems: joint, relations, linkage) on every lead kind; the conserved level read; the in-sample split removed | every reported lead carries independent replication or says why none is possible |
| **S5** | **The reader** (§9) | the dossier per lead, ranked by §9.1's rank: claim, the locus's series against its expectation, graded rival explanations, independent corroboration; a human verdict written back; verdicts feed the documented events | the author reads the first dossier and records verdicts |
| **S6** | **Breadth** (O9) | CIHA, SIM foetal deaths, SIA/APAC, SIGTAP as SIH's second classifier, all SINAN agravos, the lake aggregates as the count path, climate and care flows as context, availability guarding fields; each through S1's registry, so no system-specific code | each system's fields in the register |
| **S7** | **Surveillance and serving** (phase 4, phase 3) | alarms as leads in the register; MCP verbs for questions, relations, cohorts and dossiers (planned with the author) | — |
| **D** | **Depth, only where readings demand it** | departure models with posteriors (P12) where intervals are needed by S5; N2's SBC; the top model; BYM2; 33 age classes; the interaction read for patterns | each item has a reading that needed it |

**Order and size.**
- S0 first, short: days, not a week. Every later package lands on it.
- S1 and S2 are the two largest missing objects of §1, and the reason the system looks reduced.
- S5 comes early enough that the author reads the system's output as it grows, not at the end.

## 7. What changes in the documents

- **ARCHITECTURE §1.1:** "a pipeline of six stages" becomes "six stages, each a reading of the one model, held as persistent state". The stages keep their validity boundaries (P16). They stop being a build order.
- **ARCHITECTURE §12:** the roadmap above replaces the N1 → N2 → O6 → O7 → O8 order. Finished items keep their record.
- **STATUS:** the stage table gives way to a package table (S0–S7, D), each with its done-when, and the "planned and dormant" register.
- **docs/architecture_coverage.md:** re-derived from the audits. The audits found nine errors in it.

## 8. Decisions for the author

1. The approach (§5): system first, end to end, depth on demand.
2. The order (§6): in particular whether persons (S2) should come before fields from declarations (S1), and where race (S3) sits.
3. S0's removals: the v0 survey as a separate path, `dependency_map`, and the runner's framing.
4. Whether the agents and MCP layer (phase 3) moves earlier than S7.
