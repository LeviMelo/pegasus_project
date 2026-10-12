# ARCHITECTURE.md: PegaSUS

**The ground truth of the project: what PegaSUS is for, the plan it follows, and the theory it rests on.**
Revision 5, 2026-10-10, written with the author after a day-long review of what PegaSUS could and could not do for a
researcher (the reference: a study of toxoplasmosis). It replaces revision 4 (2026-10-07), archived in
`history/ARCHITECTURE-rev4-2026-10-07.md` in the archive outside the repository (`C:/Users/Galaxy/LEVI/archive/pegasus_project_docs_history_2026-10-10.zip`; not read). Code comments that cite "§N" refer to revision 4 until the code they sit
in is next touched.

- **What the code is today** (modules, objects, commands, what works) is in `STATUS.md`, not here.
- **The order of work** is in `BACKLOG.md`.
- **Decisions with their evidence** are ADRs (`DECISIONS.md`); measurements are evaluations (`EVALUATION.md`).
- **When the code and this document disagree,** one of them is wrong: fix it, or record the departure in §12.

| § | contents |
|---|---|
| 1 | purpose, principles, stages, goals and the win condition |
| 2 | the data space: pegasus_data, sources and intake, meaning, the ICD and other code systems, race |
| 3 | studies: the declaration, scope, depths, the study folder, the report, export |
| 4 | topic resolution: from a study's seeds to its scope |
| 5 | fields: the analysable series, their kinds, supports, grains, groups and denominators |
| 6 | expectations: the model, its estimation, tiers, calibration and surprise |
| 7 | questions: the nine components of departure, their methods, relevance and error control |
| 8 | relations and persons |
| 9 | interpretation: recording, replication, corroboration, context, synthesis, data quality |
| 10 | execution: planner, store, cost, machine, interfaces |
| 11 | validation: characterisation, documented events, null worlds, the planted grid, invariants |
| 12 | decisions and departures, hand-set constants |

---

## 1. Purpose and principles

### 1.1 What PegaSUS is

Brazil's health data are observations of one **marked point process**: events (deaths, births, admissions, notified
cases, procedures, dispensations) happening to persons, at places, at times, each carrying attributes (marks), recorded
by systems that each see part of it.

**PegaSUS automates the bulk of an epidemiological study on those data, deeply and extensively.** Given a topic, it:
1. gathers every record that bears on it, across every system, with its meaning attached (pegasus_data);
2. describes it: counts, rates and their standardisation, by place, period and population group;
3. builds, for every analysable series, an **expectation**: what it would have been given population, place, time
   and case-mix;
4. asks every series every **question**: where, when and in whom it departs from expectation, and how;
5. relates series to each other, to determinants (contexts) and along persons' trajectories;
6. separates recording artefacts from phenomena, replicates and corroborates;
7. hands everything back (data, models, findings, relations, figures and a report) for the researcher to take further.

It does not replace the researcher's judgement. It replaces the months of work before judgement is possible, and it
looks where the researcher would not have thought to look. **Findings are statistical objects, not conclusions**; the
interpretation it offers (§9) is evidence, graded, never a verdict.

### 1.2 Principles

P1–P16 answer documented failures (revisions 1–4) and stand. P17–P23 come from revision 5.

| # | principle |
|---|---|
| P1 | **Expectation first.** Every quantity is judged against a model of what it should be given population, place, time and case-mix. No statistic runs on a raw or rank-transformed value. |
| P2 | **Events and their marks are modelled,** not correlations of columns. |
| P3 | **Every cell carries its information** (§6.8) and every statistic uses it. |
| P4 | **Estimands are declared.** Between places, within places over time, between groups, between institutions: separate statistics, separate nulls. |
| P5 | **Effects are tested against a minimum relevant effect,** and the multiplicity of the whole search is designed before it runs. |
| P6 | **Structure priors act on levels, never on relations.** Taxonomies never decide which quantities may co-vary. |
| P7 | **Every strength is learned or measured,** by the marginal likelihood or held-out data. No unmeasured constant is a gate. |
| P8 | **Observed stays observed.** Modelled inputs come from pegasus_data's modelled tier, typed, with uncertainty. |
| P9 | **Validation characterises; it does not license** (§11). No question is excluded for being hard: it is weighted by its power and reported with its minimum detectable effect. Documented events are a held-out check, never a tuning target. |
| P10 | **No dense object larger than the population tensor** is ever built. |
| P11 | **Established method first.** Before a statistic is designed, the field's standard for that estimand is named, then used or beaten by measurement. A threshold is not an answer to a modelling problem. |
| P12 | **Departures and relations are model terms.** A finding is a statement about a term of a model; scans search, models infer (§7.4). |
| P13 | **Structure is exploited, and every object is computed once,** keyed by content and reused (§10.2). Slowness is a defect of the code or its orchestration, never a reason to read less. |
| P14 | **Recording is measured, never used to dissolve.** Recording processes are model terms where the data identify them and graded explanations where they do not; a finding is re-scoped, never removed by an untested explanation (§9.1). |
| P15 | **Race is an axis, not an option,** read through its measured misclassification (§2.6). |
| P16 | **One stage, one computation** (§1.3). Statistical claims in stages B–D; whether a departure is an event in the world is stage E's question. A method is general: it carries no logic specific to one system or field. |
| P17 | **General, never named.** Nothing in the code names a disease, a dataset or a variable. Every field, relation, source and rule is derived from pegasus_data's declarations; a new topic or dataset needs declarations, not code. |
| P18 | **Meaning first.** A wrong label is worse than none; codes are read with their valid meaning for each year; missing is never zero; a source's own definitions and caveats are declarations every study inherits (§2.4). |
| P19 | **One interface, one product.** A researcher writes one declaration (§3.1) and receives one study folder (§3.4). No command sequences, no agents. |
| P20 | **Depth is the only lever.** Every depth produces the same product; deeper runs more fields, components, relations and checks, never a different kind of output (§3.3). |
| P21 | **Everything is handed over.** Every number in the chain is available as a table with readable names and codes; nothing computed is hidden behind a report. |
| P22 | **Artefacts are labelled, never hidden.** A finding explained by recording keeps its row with its graded explanation; below-threshold results are exported, marked. |
| P23 | **References, not copies.** Heavy data live once (lake, store); a study references them and pins them; copies are made only on export (§3.6, §10.2). |

### 1.3 The stages

PegaSUS is one model of the marked point process read in six stages. They are readings of one persistent state, not a
build order. Each answers one question with one kind of computation and is judged by one kind of validity.

| stage | question | computation | judged by | sections |
|---|---|---|---|---|
| **A. Data and meaning** (pegasus_data) | what was recorded, for whom, under which code? | reading, decoding, labelling, linking, populations | correct meaning | §2 |
| **B. Expectation** | what is expected if nothing unusual happens, and how does its noise behave? | a model of every field: mean, dispersion, dependence of the noise over periods and places | statistical: calibration, held-out likelihood, SBC | §5, §6 |
| **C. Departures** | which component of a field departs from its expectation, where, when, in whom, by how much? | departure terms and scans over the nine components | statistical: false discoveries on null worlds, power on the planted grid | §7 |
| **D. Relations** | which fields and determinants move together, at which distances, lags and scales? who goes on to what? | cross-structure of departures; linked persons | statistical: recovery of planted relations, surrogates | §8 |
| **E. Interpretation** | is a statistical finding an event in the world, an artefact of recording, or known? | recording checks and terms, replication, corroboration, context profile | epidemiological | §9 |
| **F. Products** | what does a researcher receive? | the study folder, the report | usefulness | §3 |

**What each stage may not do:** B contains no departure term; C never builds its own null (it reads B's predictive);
D never tests pairs as its search; a threshold never answers a modelling problem; E removes nothing except by a tested
explanation.

### 1.4 Goals, the win condition, non-goals

- **The scale is the point.** Every record the public systems publish, every declared field, every place, period and
  group, read together on one personal computer (§10.5).
- **The reader** is an epidemiologist or analyst at that computer, the author first.
- **The win condition (author, 2026-10-10):** PegaSUS produces an **exhaustive study of toxoplasmosis** (§3.8): every
  dataset that records it, every field its records support, every component asked, its relations to other fields,
  determinants and persons' outcomes, interpreted, delivered as one study folder a researcher can read and reuse. A
  system that can do that for toxoplasmosis by declaration alone can do it for any topic.
- **Not goals:** causal claims (associations carry their adjustment set; causal designs are pointed to, not run);
  identifying persons (identifiers pass through pegasus_data unmodified and flagged, read only for linkage); agents
  (no LLM in the loop; the MCP server is parked, §10.6); a frontend (`../pegasus_view` is not PegaSUS's); an
  ICD-9-era reader (a mapping to ICD-10 is welcome).

---

## 2. The data space

### 2.1 Repositories and boundary

| repository | role | answers |
|---|---|---|
| **pegasus_data** (`../pegasus_data`) | the data module: sources, decoding, the lake, meaning, links, populations, contexts, the modelled tier | *what exists and what it means; what was there and how it was recorded* |
| **pegasus_project** (this repository; package `pegasus_core`) | inference and studies | *what is normal, what departs, what relates, what it means for a study* |

1. **Every input reaches PegaSUS through pegasus_data's public API,** through one module (`gateway`).
2. **A capability that is meaning or data belongs in pegasus_data** and is built there. The test: *would an
   epidemiologist who never uses PegaSUS want this as data?* Sources, intake, code systems, the concept index's tables,
   links and their viability, contexts and source definitions are all pegasus_data's.
3. **PegaSUS never writes into pegasus_data's home.** PegaSUS's data root (`PEGASUS_DATA_ROOT`) is pegasus_data's home
   for PegaSUS's own queries, and PegaSUS pins `PEGASUS_DATA_HOME` to it so no call creates a home elsewhere.

### 2.2 What pegasus_data provides

| object | content |
|---|---|
| **dataset** | one publication series of one system (SIM-DO, SINAN-TOXG, SIH-RD, SIA-AM…), its files, schema generations, years |
| **event type** | what one row is: kind (death, birth, hospitalisation, notification, case, outbreak, authorisation, procedure), grain, classifiers with their role and code structure, status rules, consolidation, weight, duplicates (SINAN's own flag included), grid of persons |
| **typed column (role)** | every column's meaning: `entity.property`, value kind, model role (stratum, dimension, event type, mark, when, where, institution, link-only, excluded), missing codes or why they cannot be decided, years it is filled |
| **code structure** | trees and lists over code systems (ICD-10, SIGTAP, CBO, anomalies, SINAN agravos, CATMAT where served), validity windows, crosswalks, attributes |
| **link** | a declared person or event link between datasets, its runs with p_match per pair, its viability verdict, `same_event` where two systems record one event |
| **population** | person-years by place × year × age × sex (× race), observed (POPSVS) and modelled (population account) with uncertainty; completeness by system |
| **context field** | a property of places over time with unit, grain, support and denominator (SIDRA, INMET, S2ID, ANS, INEP, and the sources of §2.3) |
| **records** | labelled rows with provenance (source path, file hash, row, record key) |
| **the lake** | Parquet partitions per dataset × schema × state × year, built once (`build_lake`), read in seconds |

### 2.3 Sources and intake

**The rule: the most complete source wins.**
- If an aggregator (the Ministry's DEMAS open-data API, `apidadosabertos.saude.gov.br`) serves everything relevant of
  the original source (microdata, every column, every year), it is used.
- Otherwise the original is taken directly where it can be reached, and the aggregator is the fallback.
- Each case is decided by a measured **source assessment**, never assumed.

**The source assessment** (one script, one evaluation entry per source family). For each endpoint or publication:

| measured | how |
|---|---|
| origin | a copy of something already read (SIM, SINASC, CNES, PNI, SIH/SIA production…) or the only public route (SISAGUA, BNAFAR, SIASI, Previne Brasil, SISVAN, ESAVI…) |
| breadth | years, places, granularity (microdata, or aggregates by place and period), columns |
| equality | on one state-year where an origin exists: row counts, totals, column values against the origin as pegasus_data reads it |
| practicalities | paging and rate limits, update lag, stability across requests |
| decision | ingest from origin, from the aggregator, or skip, with the evidence |

**Known sources by family** (status in `STATUS.md`; work in `BACKLOG.md`):
- **DATASUS FTP** (`ftp.datasus.gov.br/dissemin/publicos`): SIM, SINASC, SIH, SIA, SINAN, CNES, CIHA, SISCAN, PNI,
  SISPRENATAL, RESP, e-SUS Notifica; the Dados Abertos CSV/JSON/XML copies of SINAN.
- **DEMAS API** (113 endpoints, 2026-10-10): SISAGUA (water quality: monthly control samples, out-of-standard samples,
  treatment, catchment, population supplied), SISVAN, SIASI (indigenous health: morbidity, pregnancy follow-up, deaths,
  sanitation by DSEI), BNAFAR (medicine stock by facility × month × CATMAT), BPS (prices), Previne Brasil indicators,
  SIAPS primary-care consultations, PNI doses by year, ESAVI, SRAG, CNES microdata, SIM, SINASC, arbovirus aggregates,
  population estimates.
- **ANVISA** open data: SNGPC (retail sales of controlled medicines and antimicrobials).
- **IBGE** (SIDRA, Localidades, meshes), **INMET**, **S2ID**, **ANS**, **INEP**.

**What intake produces for a source,** inside pegasus_data's existing structure (catalog → fetch → decode → lake →
meaning):
- an **event dataset** (records of happenings) gets an event type and typed columns;
- a **context dataset** (properties of places over time) becomes context fields, **time-varying** where the source is
  (SISAGUA's monthly samples are a series, not one number per place);
- a **facility-level resource** (medicine stock) becomes a facility-support context, joinable to the facility lattice;
- a **new spatial support** (the 34 indigenous health districts) joins the ladder of supports with its membership.

**The publication audit.** For every dataset, every publication of it (DBC, CSV, JSON, XML, aggregator, other portals)
is compared by columns, years and totals, and its documentation is read for what the form actually collects. The audit
is a recorded table in pegasus_data, so "is this all there is?" has a measured answer. Example (2026-10-10): SINAN's
toxoplasmosis is published as final DBC 2019–2023, preliminary DBC 2024–2026 and CSV/JSON/XML copies, all with the same
38 columns; the Ministry's Nota Técnica 133/2022 states the notification uses the generic form with no disease-specific
fields. The 38 columns are all there is.

### 2.4 Source definitions and caveats are declarations

A source's own definitions, validity windows and caveats are declared on its event types, so every study counts what
the source counts and states its limits with their source:
- **definitions:** e.g. gestational toxoplasmosis = a notification with O98.6, P37.1 or B58 in a pregnant woman aged
  10–49; congenital = the same codes in a child under one year (Nota Técnica 133/2022);
- **validity:** data valid from the year surveillance was implemented (toxoplasmosis: 2019);
- **finality:** a year is final once frozen (SINAN: three years after notification); preliminary years are marked;
- **known errors:** misclassified codes, acknowledged by the source;
- **duplicates:** the source's own flag and rows equal but for entry metadata (pegasus_data decision 0159).

The study report's limitations section is assembled from these declarations (§3.5).

### 2.5 Code systems and the concept index

**The model is built on code trees.** The ICD-10 tree (chapter → group → category → subcategory, validity windows,
nesting as the release defines) carries the levels, profiles and pooling of the expectation (§6.2). Its attributes
(DATASUS's CID-10 release: dagger/asterisk, sex restriction, acceptability as underlying cause, references, exclusions;
NCHS age and sex edits; external-cause axes of intent and mechanism) give **structural zeros** (a sex- or age-impossible
cell has no exposure; records there are counted as unallocated by reason) and fields across the tree (intent,
mechanism, analytical lists such as CID-BR-10, avoidable causes, ICSAP). Leaves are 3-character categories; the 4th
character is read only where it encodes an axis.

**The concept index (to build in pegasus_data).** For any code, its counterparts in the other code systems, built only
from tables the sources publish:
- SINAN's agravo ↔ ICD-10 mapping;
- SIGTAP's procedure ↔ ICD-10 compatibility table (each procedure lists the ICD codes it may be billed for);
- APAC authorisations, which carry an ICD code and a procedure or medicine on the same record (an empirical
  ICD ↔ medicine/procedure table, with counts);
- CATMAT ↔ SIGTAP medicine crosswalks where published;
- label search over every code system's labels, flagged as the weakest evidence.

**Relations among codes** are documented (sequela of, dagger → asterisk, exclusions, the exchange pools coders trade:
unspecified ↔ specified, R00–R99, undetermined intent, garbage → targets) or **learned from records** (§4.3).

### 2.6 Race

**Race is an axis wherever the population carries it** (the population account: total plus five races, 2000–2030,
municipality × single age × sex, with intervals). **Declared race is the estimand's race:** a rate by race divides
events by the account's persons of that race. **A system's recorded race is read through its confusion with declared
race,** measured wherever a declared link joins its records to a person's own declaration (infant deaths through the
mother's declaration at birth; women 15–49 through their births). Where no link reaches, the confusion is the identity
with a sensitivity band and the estimand is named *recorded-race rate*. SINASC is declared on both sides. The unknown
share is modelled by system, place and year (by facility for SIH). Disparity is a question (§7.2, component 8).

---

## 3. Studies

### 3.1 The declaration

A study is declared in one YAML file:

```yaml
study: toxoplasmosis                  # the study's name
topic:
  seeds:                              # anything that names the subject, in any code system
    icd10: [B58, O98.6, P37.1]
    sinan: [TOXG, TOXC]
    terms: [toxoplasm]                # matched against every code system's labels (weakest evidence)
  include: []                         # fields, datasets or codes forced in (not built: refused, not ignored)
  exclude: []                         # datasets or systems forced out
  only: []                            # the datasets or systems the study is restricted to (empty: all)
period: 2010-2025                     # clipped to each source's validity (§2.4)
where: BR                             # Brazil, or states (RS, 43) and municipalities (431690): every fit is the area's
grain: [year, month]
depth: standard                       # survey | standard | deep | exhaustive (§3.3)
q: 0.05                               # the study's false-discovery rate
hypotheses:                           # optional declared tests (§7.7)
  - {component: transient, where: [4316907], when: 2018-01..2018-06, note: "Santa Maria water outbreak"}
contexts: auto                        # or a list; auto = every applicable context (§4.5)
ratios:                               # optional ratio fields (§5.2): DATASET[:event][:codes], lag in years
  - {numerator: SINAN-TOXC, denominator: SINAN-TOXG}
  - {numerator: SIM-DOFET, denominator: SINASC.DN}
download: 10                          # GB the study may download (default: the depth's)
related: 3                            # how many related codes are read, strongest first, each wherever recorded (0, N or all)
chapters: true                        # the topic's codes inside their fitted chapters, or as code sets (default: beyond a survey)
questions: [excess, group]            # the questions asked of every field (default: all eleven)
readers: [compositions, intervals]    # the field kinds read beyond counts: measures, compositions, intervals, flows, quality, supports, linked
relations: [fields, contexts]         # among the study's fields, with every context, the data-space screen
persons: true                         # the cohort scan over linked persons
replicate: true                       # leads tested once on the later years they were not selected on
nulls: standard                       # quick | standard | precise: every test's replicate null worlds (×0.25, ×1, ×4)
draws: 10                             # plausible link sets the persons step averages linkage uncertainty over
```

Every key has a default except `study` and `topic.seeds`. **How much a study ingests is the declaration's to set**
(author, 2026-10-11): `where`, `only`, `exclude`, `period`, `download`, `related`, `relations`, `contexts`, `chapters`, `questions`,
`readers`, `persons`, `replicate`, `nulls` and `draws` cut a study to the sources, years, fits and questions it needs, and a source whose latest year holds none of the topic's records is left out
before its other years are fetched (`study._probe`). `studies/toxoplasmosis_quick.yml` is the reference study cut to
its own four sources and nine years at deep depth: the debugging loop, minutes not hours. A topic may also be a whole system or the whole data space
("all of SIM" is a study; §3.8).

### 3.2 Scope

`pegasus-core scope <declaration>` resolves the declaration (§4) in seconds and writes `scope.yml`, a readable list of
everything the study would cover, each item with **the reason it was included** and its **expected cost** at the chosen
depth (§10.3):
- the datasets and the codes in each, with record counts;
- the fields, by kind;
- the related codes found in records, with their strength;
- the person paths, with their links' viability;
- the contexts;
- the components and relations that will be run;
- `minutes_by_choice`: the estimated minutes behind each choice the declaration makes (each dataset, the related
  fields read and the next ten with their cost, the persons step, the ratios, the fixed phases), so a person sees
  what a key would save before running.

The researcher edits `include`/`exclude` if something should change. Resolution is deterministic: the same declaration
on the same data version gives the same scope.

### 3.3 Depths

Every depth fills **the same study folder**; a deeper run adds to it and recomputes nothing already done.

| | survey | standard | deep | exhaustive |
|---|---|---|---|---|
| datasets | those holding the seeds' codes | + those of related codes | same | the whole served data space |
| field kinds (§5.2) | counts and ratios of the topic's own fields | + every measure, composition, interval and care flow of the topic's records; quality fields | + linked shares, captures | + every served field screened against the topic (§8.3) |
| supports (§5.3) | municipality → nation | same | + facility, place of infection, special supports (DSEI) | same |
| grains | year | + month | + epidemiological week where dates allow | same |
| components (§7.2) | level, transient, step, trend, spatial coherence | + seasonality, group heterogeneity on every group dimension, relation among the topic's and related fields | + propagation; relation with every context, time-varying ones with lags | same |
| tiers (§6.7) | B0, B1 | + B2, B2s | + BP, BPA (recent periods) | same |
| persons (§8.4) | — | — | sequences, cohort scan, capture–recapture | same |
| interpretation (§9) | recording checks | + corroboration, context profile | + replication (later years, jurisdictions) | same |
| products | the full folder at this depth | same | same | same |

Depth is a budget, not a filter of meaning: a field too sparse for a fine support is lifted to a coarser one at every
depth (§5.4), never dropped.

**A depth is a preset of the declaration's own choices** (`study.PRESETS`; author, 2026-10-12: choices a person
understands, not budgets). Each key the declaration sets overrides its depth's:

| key | survey | standard | deep | exhaustive |
|---|---|---|---|---|
| `readers` | none | measures, compositions, intervals, flows, quality, supports, linked | same | same |
| `related` (codes read, strongest first, each wherever recorded) | 0 | 3 | 8 | 20 |
| `related_questions` (asked of the related codes' fields: they are read to relate them to the topic) | none | none | none | none |
| `relations` | fields | fields | + contexts | + screen |
| `chapters` (the topic's codes inside their chapter's fit) | false | false | false | false |
| `persons` (cohort scan) | false | false | true | true |
| `replicate` (later years) | false | false | true | true |
| `download` (GB) | 2 | 10 | 40 | unbounded |
| `draws` | 1 | 1 | 10 | 20 |

Every related code stays listed with its strength in `scope.yml` whatever `related` reads, and `minutes_by_choice`
there prices each choice before a run (§3.2).

### 3.4 The study folder

**References, not copies (P23).** Heavy objects live once: records in the lake; fields, expectations, model parameters
and the ledger in the store (§10.2). The folder holds the declaration, the resolved scope, a small catalogue of views
onto the referenced objects, and only what the study itself produces. Store entries a study references are **pinned**:
cache eviction never removes them while the study exists. Two studies sharing a field share its storage.

```
toxoplasmosis/
  study.yml                 the declaration as written
  scope.yml                 what it resolved to, with reasons and costs
  study.duckdb              views onto the lake and store objects the study uses (no data copied):
                              records_<dataset>, fields_<field>, populations, contexts_<context>,
                              expectations_<field>, parameters_<field>, ledger
  findings.parquet          one row per finding (schema below)
  stories.parquet           findings grouped into stories
  hypotheses.parquet        the declared tests and their answers
  descriptive.parquet       counts, crude and age-standardised rates with intervals, by place, period, group
  relations.parquet         field–field and field–context cross-structure (§8.1–8.2)
  screen.parquet            (exhaustive) the data-space screen (§8.3)
  persons.parquet           linked-share sequences, cohort scan, capture–recapture (§8.4)
  quality.parquet           completeness, "ignored" shares, recording regimes, capture completeness (§9.7)
  models/<field>.md         model cards: data, tier, fit, calibration, method records (§11.6)
  figures/                  maps, series against expectation, pyramids, lag and distance curves, cohort plots
  report.html               the report (§3.5), opens offline
  provenance.json           data and code versions, store keys referenced
```

**A finding's row** carries:
- *identity:* component, field (name and codes), support, places (names and IBGE codes), period, group;
- *size:* effect with interval and unit, the minimum relevant effect, q-value and family, or "below threshold";
- *how:* the methods that agree, the shape attributed, the tier;
- *evidence:* recording class with each check's grade and evidence, replication by kind (R-ladder, §9.3),
  corroboration by source, the context profile of its places, its story;
- *links:* its figure, its rows in `expectations_<field>`.

Every table uses readable names beside codes (municipality name and IBGE code; ICD label and code).

**The analytic body** (`study.body`; author, 2026-10-12: enough data and statistics for a thorough
epidemiological analysis and a paper, produced reliably across every preset and scope). Every study folder holds, or
says why it does not: the scope with each source's reason; incidence with its denominator and 95 % interval by place and
year for every source read; a series and a map for every field; findings each with its recording class and named
places; relations; the persons' cohorts and the completeness across systems where persons are asked for; the data's
quality; an answer to every declared hypothesis; the report; and no failed step. The gate (`scripts/prelaunch.py
--slices`) checks it on a slice of every preset and of a second condition before any national run.

### 3.5 The report

`report.html`, static, offline, generated from the folder's tables and the declarations:
1. summary: the strongest stories, with their evidence tiers;
2. descriptive epidemiology: counts and rates by place, period, group; maps and series;
3. findings by story, then by component;
4. relations and determinants;
5. persons and outcomes;
6. data quality and completeness;
7. the declared hypotheses and their answers;
8. methods: models, components, error control, each method's validation record (§11.6);
9. limitations: assembled from the sources' declared definitions and caveats (§2.4), the links not viable, the fields
   too sparse, the methods' known weaknesses;
10. provenance.

Long lists are capped with the rest one link away; every effect has its unit; places and codes are named.

### 3.6 Export

`pegasus-core export <study> --to <dir> [--tables …] [--format parquet|csv]` materialises the **whole folder** by
default (views resolved into files, figures and report included), or the chosen tables, for use away from this machine.
It is the only operation that copies data.

### 3.7 Re-runs

- A re-run of the same declaration recomputes nothing whose content key is unchanged (§10.2).
- New data (a newly published year) recomputes what depends on it.
- A deeper depth adds what the depth adds.
- A changed rule (a triage rule, a method) re-applies to the stored state and keeps the old result beside the new
  (P14).

### 3.8 The reference study and the survey of everything

**The reference study is toxoplasmosis at exhaustive depth** (§1.4). Its sources, measured on 2026-10-10:

| need | source | in pegasus_data |
|---|---|---|
| notified cases in pregnancy, congenital cases | SINAN TOXG, TOXC (2019–) | yes; the generic form only (§2.3) |
| admissions, deaths (principal, secondary, any line) | SIH, SIM | yes |
| births, anomalies, mothers' attributes | SINASC | yes |
| serology and procedures | SIA (PA lines by SIGTAP code) | yes |
| medicines dispensed under authorisation | SIA-AM (CID and medicine on one record) | yes |
| medicine stock; retail antimicrobials; prices | BNAFAR, ANVISA SNGPC, BPS | no |
| water quality by municipality and month | SISAGUA | no |
| sanitation, income, rurality, climate | SIDRA, INMET | yes, as contexts |
| prenatal care coverage and quality | Previne Brasil, SIAPS | no |
| indigenous health | SIASI (by DSEI) | no |

**The survey of everything** is the same mechanism with a scope of a whole system or the whole data space: what
`update` with a plan does today becomes a study whose topic is "all of SIM" (§10.1).

---

## 4. Topic resolution

From a study's seeds to its scope. Every step is general (P17) and every inclusion carries its reason.

### 4.1 Codes in every system

The seeds are expanded through the concept index (§2.5): the ICD seeds with their subtree; the SINAN agravos with their
ICD counterparts and the reverse; SIGTAP procedures whose compatibility lists the codes; medicines dispensed under them
(APAC) and their CATMAT counterparts; label matches of the seed terms, flagged weakest.

### 4.2 Datasets holding them, in any role

Every served event type whose records carry one of the codes **in any role**:
- primary classifier (SIH's principal diagnosis, SIM's underlying cause, SINAN's agravo);
- secondary classifiers (SIH's secondary diagnoses);
- mentions (SIM's certificate lines a–d and part II);
- code lists (SINASC's anomalies);
- procedures and medicines (SIA).

Each dataset enters with the number of records each role contributes.

### 4.3 Related codes, learned from records

A code is **related** to the topic when it appears with the topic's codes more often than their separate frequencies
predict:
- **on the same record:** SIM's certificate lines (cerebral toxoplasmosis on an AIDS death: B58 and B20–B24),
  SIH's secondary diagnoses (hydrocephalus admitted with P37.1), SINASC's anomaly lists;
- **on the same person:** across systems through viable links (a birth's anomalies and the infant's later admissions);
- **in the same place and time:** only at exhaustive depth, through the data-space screen (§8.3).

The statistic per pair is observed/expected co-occurrence with its interval (expected from the codes' marginal
frequencies within the same stratum of age, sex and year), with FDR over the pairs tested and a minimum relevant ratio.
Related codes become **related fields** (standard depth and above), and relations among them are asked (§8.1).

### 4.4 Person paths

Paths through **declared links that pass viability** (pegasus_data measures each link's chance-match rate and refuses
non-viable ones): e.g. birth (SINASC) → neonatal admission (SIH) → infant death (SIM); admission → death. A path the
topic needs that has no declared link is reported in the scope with its status. Links are declared and measured in
pegasus_data (e.g. TOXG → SINASC birth and TOXC → SINASC birth need declaring; SINAN's public files carry the birth
year only since the LGPD, so viability will decide where they can work); where none is viable, the association stays
ecological and the report says so.

### 4.5 Contexts

Every context field defined on the study's supports and period. The order in which they appear in the report comes
from their measured relation to the topic's fields (§8.2), never from a list naming them.

### 4.6 The scope

`scope.yml`: the datasets, codes by system, fields by kind, related fields with their strength, person paths with
viability, contexts, the components and relations the depth runs, and the cost estimate. Deterministic given the
declaration and data version.

---

## 5. Fields

### 5.1 Definition

A **field** is one analysable series: a value for every cell `c = (u, t, g)` (place, period, group) of its lattice,
with its denominator and its law for lifting to coarser supports.

```
Field
  id                dataset:event:reader:node   (the reader names non-count kinds)
  kind              count | measure | composition | interval | ratio | linked_share | capture
  source            the declaration it comes from (event type, role, link, pair of fields)
  support           municipality | … | national | facility | place of infection | special support
  grain             year | month | week
  groups            the group dimensions it can be split by (strata and compositions)
  law               sum | ratio_of_sums | weighted_mean | none
  denominator       population variant | births | a population subgroup | another field
  signature         the predicate defining its events (for measured overlap, §8.1)
  provenance        data versions, query
```

**Fields come from declarations (P17).** No field names a variable; a new system or column needs a declaration, not
code.

### 5.2 The seven kinds

| kind | what it is | read as | example (toxoplasmosis) |
|---|---|---|---|
| **count** | events per cell, at every node of a classifier tree (and lists, axes across it) | NB counts (§6.1) | TOXG notifications; admissions with P37.1 as any diagnosis; deaths with B58 on any line |
| **measure** | a measurement over the events (a declared domain) | the cell's location, log-normal or count family (§6.4) | the mother's age at notification; an infant's length of stay; birth weight of exposed births |
| **composition** | the share of events in each category of a categorical column; includes **care flows** (a place column against residence: treated, notified or infected away from home) and **origins** | beta-binomial per category against its expected share (§6.4) | case classification; confirmation criterion; outcome; schooling; occupation; autochthony; infected outside the residence |
| **interval** | days between two declared dates on a record | location of the delay distribution (median, tail) (§6.4) | onset → notification → investigation → closure → entry; birth → congenital notification |
| **ratio** | one field over another on the same support, optionally with a declared lag | the numerator given the denominator (binomial or rate) with the same structure (§6.4) | congenital ÷ gestational; admissions per notified case; deaths per case; serology procedures per birth |
| **linked share** | the share of one side's persons or events reaching an outcome in another system through a viable link | the share with the link's own variance Σ p(1 − p) (§8.4) | the share of births with an anomaly admitted in the first year |
| **capture** | the overlap of two or more systems' records of the same persons | a log-linear multi-system model; the estimate of the total and each system's completeness (§8.4) | TOXC ∩ SIH P37.1 ∩ SIM P37.1 by state and year |

Readers inside the count kind: other classifiers of an event type; code-list columns (`codes:<column>`: SINASC
anomalies, requested procedures); mentions (certificate lines); weighted events (a row that is several events: SIA's
approved quantity, SIH-SP's approved procedures); group events (an outbreak: one exposed cell holding the place's
population).

### 5.3 Supports, grains, groups, denominators

- **Supports:** municipality → IBGE immediate region → health region → IBGE intermediate region → state → macro-region
  → national; the **facility** (the notifying or recording establishment's CNES code: SINAN's `ID_UNIDADE`, SIH's
  `CNES`, SIM's `CODESTAB`); the **place of infection** where a record declares one (SINAN's `COMUNINF`); special
  supports declared with their membership (the indigenous health districts). Built: a count field at every municipality column of the event
  (`support:<column>`), its records without one unallocated by municipality, the exposure the place's residents.
- **Grains:** year, month, epidemiological week (SINAN's own week, never recomputed).
- **Groups:** every stratum (sex, age band, race) and every composition column (schooling, occupation, …) is a group
  dimension a field can be split by (§7.2, component 8). Built for compositions: a value's expectation is the place-year's events at the place's mix
  in its other years (shrunk by empirical Bayes toward its state's and the nation's; the groups are the (year, value) pairs); race
  is read against the place's own population by race; "not recorded" is a value.
- **Denominators:** chosen by the event's population (births for congenital and birth outcomes; women 10–49 or
  pregnancies for gestational; the resident or SUS-dependent population otherwise; another field for ratios), with the
  population's uncertainty where it has one.

### 5.4 Sparse fields are lifted, never dropped

A field too thin at a support (most toxoplasmosis municipality-months) is read where it has information (the immediate
region, the state, the year) and kept at the finer support with its information weight. No field is dropped for lack
of power (ADR-0028); it is weighted and reported with its minimum detectable effect (§7.6).

### 5.5 Quality fields

Every typed column also yields **quality fields**: the share of "ignored" or missing values by place, period and
facility; the share of codes that cannot be an underlying cause; a source's notification start by place. They are
fields like any other: every component applies (a facility that stops recording anomalies is a step in a quality
field), and they feed interpretation (§9.1). Built: one share field per declared column present in every study year, k the blank or declared-missing
values (a code the roles do not declare missing is a value), read on the item's own classifier so quality is the
topic's records' (`fields.quality_sources`).

---

## 6. Expectations

The expectation is stage B: what each field would be given population, place, time and case-mix, with its uncertainty
and the structure of its noise. Counts use the **monolith**, a hierarchical latent Gaussian model fitted per block;
other kinds use models of the same structure.

### 6.1 Observation model for counts

For a leaf e of a classifier structure and cell c = (u, t, g):

```
y_{e,c} ~ NegBin( μ_{e,c}, dispersion )            Var = μ + μ²/φ  (NB2), or NB-P: Var = μ + α μ^P
μ_{e,c} = κ_{s(e),u,t} · N^{(v(e))}_{c} · exp( η_{e,c} )
```

- **N^{(v)}_c**, person-years of the population variant (all residents, or SUS-dependent), from POPSVS or the
  population account; with the account, log N_c ~ N(log N̂_c, s_c²) and the exposure's variance enters the predictive.
- **κ**, completeness of the system where modelled (an exposure modifier, `popsvs+kappa`).
- **Race:** groups g = age × sex × race from 2000 where the population carries race; the *recorded* count by recorded
  race is the declared-race expectation through the measured confusion C(k|j) and the unknown share (§2.6).

### 6.2 Linear predictor

```
η_{e,c} = θ_e                                    level of e, summed along its path in the tree (+ lists)
        + f_{p(e)}(a, s)                         age–sex profile, carried by the profile node p(e)
        + g_e(u)                                 geography, carried down to a declared level
        + h_e(t)                                 history (trend; season for sub-annual grains)
        + Σ_{r=1..R} ψ_{e,r} ω_r(u) τ_r(t)       low-rank place × time interaction of the block (optional)
```

- Every e-indexed effect is a sum along e's path in its structure: `θ_e = Σ_{n∈path(e)} θ_n + Σ_{L∋e} θ_L`.
- **Carriers.** `profile` carries levels and the age–sex profile (the outermost ICD group, the innermost block, or the
  category); `geography` carries history, place and season effects at or above it; carriers below 1 % of a block's
  events pool.
- **Structural zeros:** a category's inadmissible age–sex cells (sex restriction, absolute age limits) have no exposure;
  records there are counted as unallocated by reason.
- **Context fields are not in the default predictor.** A relation between a context and an outcome must stay
  discoverable (§8.2); context enters only in adjusted estimands and in explaining away.

### 6.3 Priors

Every structured effect is a Gaussian Markov random field whose precision is fixed by its shape and scaled by learned
strengths (P6, P7):

| shape | effect | prior |
|---|---|---|
| tree | θ_n | Gaussian per level per top branch (horseshoe built, not adopted: ADR-0025) |
| ordinal (age, time) | f, h | RW2 (RW1 for short series), sum-to-zero |
| cyclic (month, week) | season | cyclic RW2, sum-to-zero |
| graph (places) | g_n | ICAR on the chosen graph + iid (BYM; BYM2 when its parametrisation is adopted) |
| low-rank interaction | ψ, ω, τ | ψ Gaussian, ω ICAR + iid, τ RW1; rank by held-out deviance |

Graphs come from pegasus_data: contiguity weighted by border length (corner touches at a 1 km floor), population
distance kernels, care flows, REGIC, health regions; the selected graph and the spatial share are reported per field.
Intrinsic GMRFs are constrained to sum to zero per connected component; the age–sex profile is centred over both sexes
together.

### 6.4 The other kinds' models

| kind | model |
|---|---|
| measure (positive continuous) | log-normal on accumulator states (n, Σ log m, Σ (log m)²) per cell; a cell's mean log has variance σ²_w/n + σ²_c |
| measure (count-valued, admits zero) | negative binomial on (n, Σm, Σm²) |
| measure (bounded score) | ordinal (cumulative logit) on the histogram |
| composition | beta-binomial per category against the national composition by age and sex, with the place and time structure |
| interval | the delay's median and upper quantile per cell (log-normal or quantile model) with the same structure |
| ratio | the numerator given the denominator: binomial (a share) or Poisson with the denominator field as exposure, same structure. Built: the denominator's events by place-year are the exposure (`gateway.population("events:DS:EV[:codes][@lag]")`), numerator and exposure in one cell with neither sex nor age read (`event_counts(cell=False)`: a foetus has no age); the count model then applies unchanged |
| linked share | binomial with the link's variance added |
| capture | log-linear model over the systems' inclusion patterns, place and period effects hierarchical; the total and each system's completeness with intervals |

The location follows §6.2's structure plus case-mix and an institution effect (shrunk) where the measure has one. All
are fitted by the same solver (§6.6).

### 6.5 Institutions

- **Supply term** (opt-in): the expectation of an annual count block multiplied by `A_ut = renorm(exp(β_v L_vol +
  β_u L_util))`, the indices built from the *other* chapters only (so a real outbreak of the block never enters them),
  soft-thresholded at their counting noise, exponents chosen by likelihood.
- **Institution lattice:** cells (f, t) with the facility's catchment as exposure, `m_ft = Σ_u q_uf μ_ut` (q the
  care-flow kernel). The facility support of §5.3 reads every component there (§7.2); a facility's step is a finding of
  its own (§9.1), never subtracted from the places it serves.

### 6.6 Estimation

- **Factorised likelihood (P10).** The mean structure by penalised Poisson quasi-likelihood: the non-empty cells streamed
  exactly, the total `Λ_e = Σ_{u,t} κ exp(θ_e + g_e(u) + h_e(t) + …) · M_{p(e)}(u,t)` with `M_n(u,t) = Σ_g N_{u,t,g}
  exp(f_n(g))`, one dense contraction of the population tensor per profile node. Cost `O(nnz + |profiles|·|U||T||G| +
  |E|·|U||T|·R)`; the ~10¹² implicit cells are never formed.
- **Dispersion** by maximum likelihood with μ fixed: non-empty cells exactly, empty cells through log p(0), the sum over
  all cells by μ-binning (8,192 log bins with a second-order correction). The field's own dispersion is NB-P (ADR-0032)
  where the block's fails calibration.
- **The robust expectation** (`Monolith.robust`): outlying leaf × place × period cells imputed to their expectation so a
  departure does not pull the expectation toward itself; an excess its siblings' deficit accounts for is moved back to
  them, not removed (ADR-0033).
- **The mean: exact Newton on the assembled block-arrowhead Hessian.** Parameters in three classes: leaf-place
  (diagonal block, eliminated in closed form), place (per-place dense blocks coupled by the graph's sparsity: sparse
  Cholesky, CHOLMOD), global (dense Schur complement). Constraints by contrast bases and conditioning by kriging. Start
  by iterative proportional fitting and moment estimates. Quadratic convergence under a line search.
- **Strengths: the Laplace marginal likelihood.** Newton on log τ with exact global traces and probe-estimated place
  traces, safeguarded as in mgcv (Wood 2011), per-strength step radii, noise-aware; 5–10 outers.
- **Uncertainty: exact Laplace draws** from the factor (multi-RHS solves; leaf-place block in closed form; centrings by
  kriging). The predictive is matched by moments.
- **Blocks and model choice.** A block is a subtree fitted together (an ICD chapter, a SIGTAP group, an event type
  without a tree). Rank, graph and prior choices by held-out deviance on the last years together with LAML; never
  in-sample deviance. A top model across blocks is not built (§12).
- **Fit on demand.** Any block a study needs and the store lacks is fitted when the planner reaches it (§10.1).

### 6.7 Tiers

A tier is the fitted model with a declared subset of terms: a **reference** a component is tested against (§7.2), not
part of the expectation itself. All tiers come from one fit.

| tier | terms | a departure from it means |
|---|---|---|
| **B0** | national levels, profile and history (re-levelled to each year's national total) | the place differs from Brazil, given its population |
| **B1** | B0 + the graph terms (spatial structure) | the place differs from its region |
| **B2** | B1 + a place intercept and slope per field, shrunk to the region (an exact 2 × 2 Newton per place) | the place departs from its own course |
| **B2s** | B2 + season (sub-annual grains) | an out-of-season event |
| **BP** | prospective expectation: fitted on years ≤ t₀, carried forward (annual: damped slope and damped place trends; monthly: the fit's years as regimes, a mixture predictive) | recent periods are unusual given the past |
| **BPA** | prospective alarm baseline: BP with the monthly history a flat recent level past epidemics do not enter | an epidemic now, even one that repeats a past one |

A category the fit never saw has no expectation: its events are counted and alarm at a declared count (ADR-0011).
The low-rank interaction is never part of a tier.

### 6.8 Calibration and surprise

- **Randomised PIT** of each observed cell under its predictive: `u = F(y − 1) + V · p(y)`, V seeded by (field, cell).
  A field is calibrated when its KS distance is ≤ 0.03 overall and ≤ 0.05 in every macro-region. Calibration is
  **measured and reported per field** in its model card; it never gates a field (P9).
- **The field's place-year variance component** where the block's dispersion fails: `1/φ_cell = 1/φ_cells +
  κ (μ/μ_ref)^(P−2)`, P learned per field (NB-P), the component varying by group of places (field → macro-region →
  state), each level's estimate shrunk to its parent by the between-group variance.
- **The noise structure (N1, ADR-0029):** a field's cells are NB(μ, φ/κ), a gamma frailty times a Poisson; the
  frailties of a place's periods are joined by a Gaussian copula with ARMA(1,1) correlation c_k = ρ δ^(k−1), and across
  places by a spatial component on the graph's heat kernel. κ by central matching of the PIT quartiles; ρ, δ from the
  detrended lag moments. It is what replicate fields, multiscale nulls and the step model's correlation read.
- **Surprise:** `z = Φ⁻¹(u)`, information weight `w = μ / (1 + μ/φ)`, flags (denominator tension, unreliable recording,
  calibration, small support). Zero cells in closed form. Subset statistics never average z; they use Σy and Σμ.
- **Known defect (OPEN_QUESTIONS 12, BACKLOG):** in large places the per-cell predictive does not carry the persistent
  frailty's shape; its upper tail runs 2–3× N(0, 1) above z = 3 on births' own null worlds. The fix belongs here,
  in the model, not in a threshold.

---

## 7. Questions

### 7.1 The principle

For every field, the observed series is decomposed, relative to its expectation, into **components**:

```
observed(u, t, g) = expectation(u, t, g) × level_u × trend_u(t) × step_u(t) × season_u(t)
                                         × transient_{u,t} × heterogeneity_{u,g} × noise
```

Two more components are not terms of the product but **arrangements** of the place components over space and time
(spatial coherence; propagation), and the last is the co-variation of a field's departures with another field's or a
context (relation).

**Each question tests exactly one component.** That makes the question set non-redundant by construction. Several
**methods** may estimate one component; their answers are merged by overlapping locus as agreement, never counted as
separate questions. Every question runs on every field kind (§5.2), at every support (§5.3), at every grain, for every
group dimension where it applies: the system is general because the grid is.

### 7.2 The nine components

| # | component | phenomenon | tested against | methods (built ✓, to build ○) |
|---|---|---|---|---|
| 1 | **level** | a place persistently above or below | B0 | ✓ multiscale peaks of the whole period's excess (`excess_level`); ✓ Poisson scan (`spatial_cluster`); ○ BYM2 exceedance |
| 2 | **transient** | a short burst in one place-period | B1 (B2 where the place's course is known) | ✓ two-group model on the PIT scores per size class (`cell_excess`); ✓ multiscale peaks of spike contrasts (`excess`); ✓ NB tail (`outbreak`); ✓ space–time scan |
| 3 | **step** | a lasting shift from some period | B1; B2 for "against its own course" | ✓ multiscale suffix-sum peaks (`excess_step`); ✓ Bayesian change point tempered by N1 (`step`); ✓ trailing windows (`change_point`) |
| 4 | **trend** | the slope bends, or diverges from the neighbours' or the nation's | B1; B2 | ✓ hinge-contrast peaks (`excess_trend`); ✓ divergence from neighbours and from the nation |
| 5 | **seasonality** | the cycle differs by place, or changes over time | B1 with the rest of the field's season (B2s is the expectation holding the place's own) | ✓ `season_departure`: per unit and calendar year an NB harmonic regression against the rest of the field's season, the years combined by a random-effects meta-regression; the departure (`season_level`) and its change over the period (`season_change`) |
| 6 | **spatial coherence** | neighbouring places depart together | B0/B1 residual arrangement | ✓ graph-connected scans; ✓ heat-kernel scales (multiscale) |
| 7 | **propagation** | departures ordered in space through time: emergence, diffusion, extinction | B1 | ✓ first-departure times over the graph, source and Theil–Sen speed against distance under a Moran spectral null (`propagation`); ○ emergence of a field in places where it was absent |
| 8 | **group heterogeneity** | the departure differs across a group dimension | B0 by group | ✓ sex × age (`group_disparity`); ✓ race (`disparity`; and as a group dimension against the place's own population by race); ✓ every composition column as a group dimension (`Session.by_composition`) |
| 9 | **relation** | co-variation with another field or context, over distance, lag, scale and group (§8.1) | each field's own tier | ✓ dependency map (between places), distributed lag, `compare` (scale), `joint`; ✓ time-varying contexts as series with their own predictive, jointly with the field over graph bands and lags (`tools.determinants`); ✓ a study's fields against the contexts between places (`dependency.field_map`); ✓ a study's relations among its fields and the exhaustive data-space screen (`relation_survey`); ✓ one estimator of the time-varying pair relation over distance (graph band), lag and scale (`relations.relation_estimate`: `compare`, `determinants` and `relation_survey` read it; §8.1) |

Prospective use is not a component: it is every component tested against BP/BPA over recent periods (alarms). Each question of the registry names its component, and a method its own where it differs (`questions.components`: the cluster question's Poisson scan answers spatial coherence, its multiscale peaks level); the former questions keep their ids.

### 7.3 What is not a question

| former question or proposal | what it is |
|---|---|
| share (a field's share of all events) | a ratio field (§5.2) |
| institution (a facility's change) | the components on the facility support (§5.3) |
| divergence (from neighbours, from the nation) | trend against another reference |
| prospective (alarms) | every component against BP/BPA |
| delays | an interval field |
| under-notification | a capture field |
| interventions | a step at a declared date (§7.7) |
| who is affected | group heterogeneity on every group dimension |
| burden, standardised rates, forecasts | products (§3.4) |

### 7.4 Methods: departure models infer, scans search

- **Departure models** read the field's expectation (with its uncertainty) as an offset, `y ~ NB(μ̂ exp(δ), φ_field)`,
  δ the component's term, from the field's established method (P11): the two-group model and local fdr (Efron) for
  cells; Bayesian change points for steps; mixture models of unusual trends (BaySTDetect); exceedance probabilities on
  a BYM2 excess for levels (Richardson et al. 2004); place × group interactions for heterogeneity.
- **Space at unknown scale.** Heat kernels `K_s = exp(−sL)` of the place graph give a continuum of neighbourhoods;
  multiscale peak testing (STEM, Schwartzman et al. 2011) over places × scales × temporal contrasts (spike, step from
  τ, trend bending at τ), the peaks' tail by a generalised Pareto, one BH over peaks. A finding carries its scale and
  footprint.
- **Shape attribution** (Chen & Liu 1993): each finding's series decomposed into additive outliers, temporary changes,
  level shifts and ramps under N1's covariance; the finding carries the shape it takes.
- **Subset scans** (search): expectation-based Poisson score `F(S) = Y log(Y/M) + M − Y`, linear-time subset scanning
  over places in graph neighbourhoods, contiguous windows, codes within subtrees, groups; null by replicate fields with
  a Gumbel tail (no Monte-Carlo floor). A subset is a proposal; the departure model reads it.
- **Merging.** The methods of one component are run, their answers merged by overlapping locus; agreement and the
  shape are reported. Each method carries its measured record (§11.6).
- **Size classes for cell tests** (ADR-0035 amended): each class of expected count has its own empirical null
  (δ0, σ0 ≥ 1, π0), one BH over all classes.

### 7.5 Relevance

Every effect is tested against a **minimum relevant effect** (P5), a statement of relevance, not detectability:
- counts: a rate ratio θ0, or the excess θ0 means at the field's mean cell, whichever is smaller per locus (a burden,
  ADR-0031): `θ0' = min(θ0, 1 + (θ0 − 1)·μ̄/m)`;
- locations: a shift in standard deviations of one event's value;
- relations: |ρ| > δ_E, or a cumulative rate ratio.
Values live with their method and are calibrated on null worlds; every result carries its minimum detectable effect
from the power surface (§11.4), so "nothing found" says what could have been missed.

### 7.6 Error control

- **Families.** One family per component × field kind × study (and per support class where scales are tested
  separately). Within a family Benjamini–Hochberg at the study's q (Benjamini–Yekutieli where dependence is not
  positive); down code trees TreeBH; across families Benjamini–Bogomolov selection. Departure models choose their set
  by Bayesian FDR (expected false discovery proportion from posterior probabilities ≤ q).
- **Weights, not exclusion.** Hypotheses are weighted a priori by power (Roeder–Wasserman; IHW where cross-weighting is
  built); no field is excluded for low power.
- **The ledger.** Every test is written before it runs (family, hypothesis, data and model versions) and its result
  appended; the ledger is the denominator of every error rate.
- **Discovery and confirmation.** Discovery controls FDR. A held-back **confirmation reserve** (a reserved period,
  SIM.DO 2024) tests only claims declared in order before it is read, under one LOND stream.
- **Below threshold** results are exported with their effect and q, marked (P22).

### 7.7 Discovery and hypothesis mode

A declared hypothesis (component, places, period, group, direction) is one test with its own error budget, answered
whether or not discovery finds it, reported separately. A step at a declared date is how interventions are asked.

### 7.8 The grid and the depths

The applied grid is components × field kinds × supports × grains × groups (× contexts for relations). §3.3 fixes which
cells run at each depth; §10.4 how the grid is kept affordable.

---

## 8. Relations and persons

### 8.1 The relation component: cross-structure

Two fields X and Y (or a field and a context) are related through the **cross-structure of their departures**, each
from its own expectation (raw counts correlate spuriously through shared population, age structure and national
course):

```
R_{XY}(d, ℓ, s, g) = association of X's departures at (u, t) with Y's at (v, t + ℓ),
                     over place pairs at graph distance d, at spatial scale s, in group g
```

- **d = 0** is the same place; d ≥ 1 neighbours (spillover, downstream water, referral flows); **ℓ** negative or
  positive shows direction; **s** the support ladder or heat-kernel scale (a relation may hold at the state and not the
  municipality, or the reverse); **g** a group dimension; **conditioning** on a context (a relation only where
  sanitation is poor).
- **Significance** from surrogates that keep each field's own spatial and temporal structure and break the link
  between them. The time-varying pair relation (`relations.relation_estimate`) uses the leader's circular shifts, one shift
  common to all places and coefficients (the phase surrogates of Theiler et al. 1992 and Prichard & Theiler 1994 have
  the same variance but a Gaussian tail that a spiky leader does not have), with a Student-t tail from the shifts'
  kurtosis and effective count; between places, Moran spectral randomisation on another graph
  and Dutilleul's modified t.
- **Estimators by form** (the established method per estimand, P11): between places, weighted correlation of place
  effects with Dutilleul's n_eff, and partial correlation given an adjustment set (E_b, E_b|Z); delayed effects,
  distributed-lag terms with a GMRF over lag (DLNM, Gasparrini et al. 2010); shared geography, a shared-component model
  (Knorr-Held & Best 2001); infectious coupling between places or series, endemic–epidemic terms (hhh4); the same
  quantity in two systems, a ratio field (§5.2).
- **Bounding the grid.** The unconditional relation at (d, ℓ, s) is tested over a declared range; group and
  conditional relations only where the unconditional one is found or a hypothesis names them.
- **Overlap.** Two fields sharing events (nested codes, alternative classifiers, "any mention" against underlying
  cause, two systems recording one event) are not tested as independent: their overlap is measured (from records, or
  Σ p_match through a link) and the shared events are removed (the "not linked to" twin) or the pair is not tested.

### 8.2 Determinants: fields against contexts

Every applicable context is related to the topic's fields (§8.1), cross-sectionally (place levels against the
context) and, for time-varying contexts (water quality by month), as series with lags and distances. Contexts enter
jointly, so associations are partial; the expectation already adjusts for age, sex, population and national course;
spatial dependence is in the null. Results are **associations with their adjustment set**, never effects, with
negative-control outcomes and exposures reported beside them where declared. The measured associations order the
contexts in the report and fill each finding's context profile (§9.5).

### 8.3 Joint departures, the dependency map, the data-space screen

- **Joint departures:** places and periods where several of the topic's fields depart together, which is stronger
  evidence than one.
- **The dependency map:** every field of a scope against every other and the contexts, marginal and conditional layers,
  utilisation factors for care-use fields, error control over the map (TreeBH by field-group pair).
- **The data-space screen** (exhaustive depth): every served field's place level and course against the topic's,
  through the map's machinery generalised to the whole data space; what passes becomes a related field and is asked
  §8.1 in full.

### 8.4 Persons

pegasus_data links records of the same person across systems; PegaSUS reads **persons** (entities built over every
viable link run of the scopes holding the year's records) and their **link uncertainty** (plausible link sets drawn
from p_match, combined by Rubin's rules).
- **Linked sequences:** fields along a person path (§4.4): of the births with an anomaly, the share admitted in the
  first year; of the admitted, the share who died.
- **The cohort scan:** every declared attribute of the starting dataset against each outcome, Poisson with person-time,
  adjusted for age, sex, year and a shrunk place effect, minimum-effect test on log RR, BH within the family. An
  outcome may be in another system (through links) **or on the same record** (an anomaly at birth against the mother's
  attributes).
- **Capture–recapture:** where two or more systems record the same persons (a disease's notifications, admissions and
  deaths), the overlap estimates the total and each system's completeness by place and period (log-linear
  multi-system models, heterogeneity by stratum); completeness becomes a field (§5.2) and a quality finding (§9.7).
  Built (`capture`, 2026-10-12): the population and its lists are pegasus_data's declarations (`captures`), one
  definition across systems; the cases are listed by the systems of cases (two lists: Chapman, a lower bound under
  positive dependence), the deaths by every system (three: the log-linear model of least AIC, Chao's interval),
  pooled over the years whose covering runs of every link are usable (`capture.parquet`, the report's completeness
  table). Not yet: strata by place and period, linkage draws, and the links' missed pairs, which raise the estimate.

### 8.5 Congenital anomalies: the pattern, generally

Anomaly code lists (SINASC's `CODANOMAL`, admissions' and deaths' Q codes) are count fields at every node of the
Q-code tree over births (§5.2), so every component applies: persistent prevalence (level), clusters (transient,
spatial coherence), policy effects (step), emergence and spread (propagation), seasonality of conception, maternal
groups (heterogeneity). Their association with infections is the relation component at about a pregnancy's lag and
over space (the Zika → microcephaly pattern); within-record associations (mother's attributes, gestational age) come
from the cohort scan on same-record outcomes; co-occurring anomalies (syndromes) from related codes on the same record
(§4.3); outcomes of affected births from linked sequences; and the recording completeness of the anomaly field by
facility is a quality field, so a hospital that starts recording anomalies does not read as an outbreak.

---

## 9. Interpretation

### 9.1 Recording checks

Every finding is read against recording explanations in order. Each explanation carries a **grade** (ADR-0019):
*tested* (a test separates it from the claim), *bound* (it accounts for at most a stated share under a stated
assumption), *consistent* (the aggregates cannot exclude it). Only a tested explanation changes a finding's class, and
nothing is deleted (P14, P22).

1. **Denominator:** a municipality created mid-period; years with no records of any kind in a place with person-years;
   population breaks beyond the nation's.
2. **Code substitution:** the excess is matched by a deficit of sibling codes or of the exchange pools (unspecified
   codes, R00–R99, undetermined intent) in the same place and time; tested by the displaced events' profile against
   the code's own. A code-level explanation **re-scopes** the finding to its conserved level (the ICD family plus its
   pools), where it is re-tested.
3. **Recording regime:** a whole state or system changes at once (a new form, a state starting to notify, a code
   introduced); measured by the quality fields (§5.5) and the source's declared start dates.
4. **Concentration:** one facility carries the departure. **This is a finding class, not an artefact** (*institutional*):
   it is read with the facility's CNES facts (type, opening, services, beds) and its other activity (volume steps in
   other chapters), so the researcher sees whether a new referral centre, a hospital outbreak, a laboratory starting a
   test or a coding change is behind it.
5. **Sparsity:** too few events for the effect to mean anything.

Whatever remains is **signal**: unexplained by the data at hand, not confirmed. Every class records the rule version
that produced it; a changed rule re-applies to the stored state, keeping the old class beside the new.

### 9.2 Recording as measurement

Where the data identify a recording process it is a model term, not an explanation after the fact: completeness κ
(SIM, SINASC) as an exposure modifier; race misclassification through measured confusion; a jurisdiction's coding
regime as a confusion between siblings and pools by state and era (to build; garbage-code redistribution as a
sensitivity tier, not the default); a facility's coding or volume on the institution lattice.

### 9.3 Replication: the R-ladder

A finding is confirmed only by **units that took no part in selecting it** (ADR-0015). Splitting a cell's own events
cannot do it (the halves share the cell's frailty; ADR-0007 withdrawn); the event split is kept only to size an effect
honestly after selection.

| unit | test |
|---|---|
| **later years** | selected on years ≤ t, refitted without the later years (BP), the same locus tested after, re-levelled to each state-year's course; a one-off event cannot recur by nature and is "not applicable", not failed |
| **other jurisdictions** | a state claim must hold in other states; a region claim in a random half of its states and without its most influential one; a municipality claim not carried by its state (ADR-0019) |
| **another record system** | corroboration (§9.4) |

R0 passes error control; R_k holds k of the three confirmations. They count independent evidence; they are not a
ladder of strength.

### 9.4 Corroboration

**The same codes in an independent system.** Sources are declared, never named: every other served event type whose
records carry ICD-10 codes covering the finding's codes, less the records a declared link pairs with the finding's
system (Σ p_match); every context field declaring an ICD-10 correspondence (disasters). The statistic is computed on the
finding's places and years in that source; the null is the same statistic on random place sets of the same size, in
the same states, matched on population, over the same years (connected sets for clusters). BH within each source.
**Related fields** (§4.3) add *consistency* evidence, labelled weaker: a gestational excess followed by a congenital
one is consistency, not corroboration.

### 9.5 Context profile

Every finding carries its places' profile: each context's value and national percentile in the finding's period, and
the contexts' measured associations with the field (§8.2).

### 9.6 Synthesis

Findings are grouped into **stories** by place, period and the fields involved; a story is the unit the report leads
with. Stories and findings are ranked by evidence (class, replication, corroboration), effect and burden, never by p
alone. Artefact classes sort after signal; nothing is hidden.

### 9.7 Data quality is a finding

Completeness of every variable (missing and "ignored" shares) by place, period and facility; each system's completeness
from capture–recapture; recording regimes detected; codes that cannot be an underlying cause; the quality fields'
departures. They are reported as findings of their own and feed §9.1.

### 9.8 Verdicts

A researcher may annotate a finding (confirmed, artefact, unknown, with a note). An artefact verdict moves it down the
ranking; a confirmed one joins the documented events that measure the methods (§11.2). Verdicts are optional; nothing
requires them.

---

## 10. Execution

### 10.1 The planner

`pegasus-core study` turns a scope into a **task graph**: reads → fields → fits → expectations and surprises →
components → relations and persons → interpretation → products. Each task has a **content key** (its inputs' keys, the
data version, the source of the code it runs), so nothing is computed twice and a re-run computes only what changed.
It schedules tasks on the machine's CPU, GPU and memory under the job slot, resumes after a kill at the next missing
task, and replaces `update` and its plans.

### 10.2 The store

- **Content-addressed artefacts** under `PEGASUS_HOME` (`<kind>/<hash>/` with a manifest: key, code and data versions,
  time written). A stale artefact is never served: keys hash the syntax trees of the functions an artefact runs
  (`config.code_key`).
- **Pinning:** entries a study references are pinned while the study exists.
- **Eviction:** reads stamp their entry; `gc` evicts the least recently read *cache* entries (gateway reads, assembled
  blocks) to a budget; fits, results and registers are never evicted; pinned entries never.
- **The lake** (records) lives in pegasus_data's home under PegaSUS's data root, built once per dataset-year;
  downloaded source files are pruned once their partitions are verified.
- **Modelled products** are stored compactly (floats in byte-stream-split encoding; pegasus_data
  `reencode-modelled`).

### 10.3 Cost model and depth budgets

Measured throughput per task kind (seconds per field read, fit by block size, component pass per field, relation per
pair, link per side-year) gives each scope a cost estimate before it runs (§3.2). Depth (§3.3) is the explicit budget;
the estimate tells the researcher what a depth costs.

### 10.4 Keeping the grid affordable without dropping anything

1. **One fit serves many questions:** a field family's expectation is fitted once and read by every component,
   support and group.
2. **Vectorised component passes:** fields of one family are passed as arrays together, not one by one.
3. **Lift, don't multiply:** sparse fields are read at coarser supports (§5.4).
4. **Screen, then examine:** a fast pass over all cells proposes candidates; expensive methods (scans with replicates,
   multiscale peaks) run on candidates, with error control carried across the two stages.
5. **Group and conditional relations only where an unconditional one is found** (§8.1).

### 10.5 The machine

32 GB RAM (about 20 usable), 20 logical cores, an RTX 4050 (6 GB, CUDA 12.1), a constrained disk. numpy and scipy;
CHOLMOD (scikit-sparse) for sparse Cholesky; PyTorch (CUDA) for contractions and batched dense algebra; numba; pyarrow,
duckdb. float32 on the GPU with float64 accumulation; float64 factorisations; every random draw seeded from (object,
cell, purpose). A heavy computation takes the machine-wide job slot and the GPU slot and states its threads; a run
refuses to start under its free-disk and free-memory floors.

### 10.6 Interfaces

- **`pegasus-core scope | study | export`** (§3), and the same as a Python API (`pegasus_core.study(path)`). The other
  commands of today (`fit`, `ask`, `surprise`, `survey`, `update`, …) become internal steps or developer tools
  (`STATUS.md`).
- **No agents.** The MCP server (`mcp_server`) is parked; it is not part of the product.

---

## 11. Validation

### 11.1 Characterisation, not permission (P9)

Validation measures operating characteristics; it never decides whether a method may run. Two kinds, never mixed:
**statistical characterisation** of stages B–D (calibration, SBC, power on a planted grid, false discoveries on null
worlds) and **epidemiological checks** of stage E (documented events, replication, corroboration). Real data first: a
world drawn from the model's own law measures internal consistency and cannot reveal that the model is wrong; real
fields, documented events and real-data negative controls judge discovery, and planted grids calibrate.

### 11.2 Documented events

Declared before they are scored (estimand, tier, locus, criterion), held out from tuning; a miss is a defect report
diagnosed to its stage. Among them: microcephaly in the Northeast 2015–16; arbovirus → microcephaly at a pregnancy's
lag; COVID-19 excess deaths 2020–21 (Amazonas, January 2021); dengue epidemics by state; leptospirosis after the 2024
Rio Grande do Sul floods; Chagas and schistosomiasis endemic areas; infant mortality against income and sanitation;
winter respiratory seasonality in the South; the first autochthonous chikungunya (Amapá 2014); and for the reference
study, the Santa Maria (RS) waterborne toxoplasmosis outbreak of 2018. Confirmed researcher verdicts join them (§9.8).

### 11.3 Negatives and null worlds

- **Negatives keep a field's own dependence and remove the relation:** Moran spectral randomisation on the
  symmetric-normalised adjacency of another graph; within-place time shifts.
- **Null worlds** are drawn from the fit **for the tier the method reads**: B1 worlds (every place's fitted level) for
  methods against B1 and above; B0 worlds (no place effects, `grid_world(spatial=False)`) for methods against B0;
  methods whose input no world draws (the facility cube) are marked not judged (OPEN_QUESTIONS 16). A world refits; its
  findings are the false-discovery rate per method.

### 11.4 The planted grid

For a field and locus, plant `y' = y + Poisson((θ − 1) μ_S)` over a designed grid: locus (cell, place-window, cluster,
region, state, macro-region) × shape (spike, step, trend change, seasonal shift, group-specific excess, lagged response)
× size (θ 1.1–3) × duration × sparsity (quantile bins of real fields). Fields are real; worlds are refitted (a refit
absorbs part of every plant); a plant is detected when a finding lies half inside it. Outputs per method: a power
surface on log(θ − 1) and log expected events, the minimum detectable effect at 80 % power, the absorbed share, false
leads per world, the bias of the estimated effect. Leads are sized with their locus held out.

### 11.5 The model's own checks

Simulation-based calibration (Talts et al. 2018); the Laplace fit against MCMC on sampled fields and states;
held-out deviance and calibration of the forecasting tiers.

### 11.6 Method records and model cards

Every method carries its record: maturity, power at the finding's size and support, false-discovery rate on null
worlds, documented-event record; every field its model card (data, tier, fit diagnostics, calibration). Both travel
with findings into the study folder (§3.4) and the report's methods section.

### 11.7 Invariants

```
Every input comes through gateway.
No statistic runs on a value without its expectation and its information weight.
Context is never in a default tier.
Taxonomic structure never enters a relation's prior.
Every test is in the ledger before it runs.
Every p-value has a null that preserves the field's dependence; none has a Monte-Carlo floor.
An effect is tested against its minimum relevant effect, not zero.
Pairs with measured overlap above 0.05 are never tested as independent.
No array larger than the population tensor × profile nodes is materialised.
A modelled input carries its model version; an artefact carries its data and code versions.
Every random draw is seeded from (object, cell, purpose).
No field or question is excluded for low power; it is weighted and reported with its minimum detectable effect.
No constant, rule or design choice is tuned on a documented event.
Only a tested explanation removes a finding; a changed rule is re-applied to the stored state.
Nothing in the code names a disease, dataset or variable; it is declared.
A study references heavy data; only export copies it.
A solver change is measured on the benchmark before it is adopted.
```

Statistical code is verified by the harness on real data and by measured comparisons, not by unit tests written beside
it.

---

## 12. Decisions and departures

### 12.1 Revisions

| rev | date | ADR | what changed |
|---|---|---|---|
| 1 | 2026-10-04 | ADR-0002 | the architecture accepted |
| 2 | 2026-10-06 | ADR-0023 | solver, departures and relations, validation as characterisation |
| 3 | 2026-10-06 | ADR-0029 | six stages, one computation each; noise in the expectation |
| 4 | 2026-10-07 | ADR-0030 | whole-system roadmap; fields from declarations |
| 5 | 2026-10-10 | ADR-0036 | studies (declaration, depths, folder), topic resolution, seven field kinds, nine components, relation as cross-structure, interpretation revised (institutional findings), references not copies, intake rule, no agents; the roadmap moved to `BACKLOG.md`, the code map to `STATUS.md` |

### 12.2 Departures

*Where built code knowingly departs from this document. The unbuilt parts of revision 5 are not departures; they are
`BACKLOG.md`.*

| § | the document says | the code does | why |
|---|---|---|---|
| 6.3 | BYM2 with a learned mixing | BYM: separate strengths for the scaled ICAR and iid parts | the two strengths form a ridge; BYM2's parametrisation measured, not yet adopted |
| 6.3 | horseshoe on tree levels | Gaussian per level by default; horseshoe built, opt-in | held out equal to 2·10⁻⁵ per event (ADR-0025) |
| 6.2 | geography carried to a declared level | groups carry ICAR + iid; categories an iid leaf-place deviation | the category-level deviation is real (IX sd ≈ 0.47) |
| 6.2, 6.6 | the low-rank interaction on every leaf, all scales learned | active leaves only, ψ and τ strengths fixed, annual grain, no draws, rank chosen by script | identifiability and cost; the cross-block factor needs the top model |
| 6.6 | a top model across blocks | not built | — |
| 6.1 | groups g = age × sex × race; κ and the SUS share in μ | race-stratified blocks; κ and SUS as opt-in exposure modifiers | the race axis of G needs the profile's random walk over G |
| 7.2 (5) | seasonality tested against B2s | tested against B1 with the harmonic the same estimator finds on the rest of the field, per year | B1's season is the robust baseline (epidemic cells trimmed), the data's national cycle is not; against B1 itself 10-26 % of random groups of dengue municipalities departed at p < 0.05 (evaluation 2026-10-10 seasonality). Debts: τ² between years scalar (no phase-amplitude asymmetry), clusters are calendar years, a change is a linear drift of the yearly departure |
| 6.1 | the population's uncertainty in the predictive | the default exposure is POPSVS (none) | no account beats POPSVS on deviance (ADR-0010) |
| 6.8 | the cell predictive carries the persistent frailty's shape | it does not in large places | OPEN_QUESTIONS 12; BACKLOG |
| 7.6 | weights learned by IHW | a priori Roeder–Wasserman weights, built and applied to one method | within-field gain measured at about 10 % of power |
| 7.6 | TreeBH | TreeBH with Simes aggregation | the exact combination is a refinement |
| 8.1 | one cross-structure estimator | the time-varying pair relation is one estimator (`relations.relation_estimate`, BACKLOG 3.5); the between-place level correlation E_b, E_b\|Z (a different estimand), the distributed-lag effect size (`Session.relation`) and the joint-departure locus (`joint`) stay separate | each answers a question the estimator does not; distance is read as the graph frequency, not as a spatial lag between places |
| 2.5 | meaning from pegasus_data | `gateway` parses raw date text and maps SIH-RD's Federal District region codes 2008–2017 | pegasus_data now derives both; the switch changes every gateway cache key and waits for a re-warm |
| 8.1 | the relation estimator's null | a Student-t on the leader's circular shifts clear of the tested lags (as many shifts either side as the lags), all shifts where fewer than `NULL_MIN_EFFECTIVE` = 10 are effective; one shift for all places and coefficients | measured on time-reversed and place-permuted real fields (evaluation 2026-10-11-relation-estimator): nominal for time reversal, 2-5 times nominal below p = .001 for rows under place permutation; remedy: shifts per block of coherent coefficients, learned |
| 10.2 | artefact keys hash pegasus_data's data versions | keys carry pegasus_data's package version (plus resource hashes) | pegasus_data exposes no publication-level data version yet |

### 12.3 Hand-set constants

*Each is a debt to learn from data or integrate over; each closes when replaced.*

| constant | where | value | state |
|---|---|---|---|
| minimum relevant effects θ0 | `scans/lenses.py` (`MINIMUM_EFFECT_BY`) | 1.1–2.0 by method and system | calibrated on null worlds (ADR-0026); relevance per estimand to be stated with the reader |
| location effect | `surprise.LOCATION_EFFECT` | 0.1 sd | hand-set |
| facility rules | `scans/explain` (`FAC_K`, `FAC_SHARE`), `facility.VOLUME_FOLLOWS` | 3, 70 %, 0.5 | v0 thresholds, to become measured models |
| size classes | `departures.CLASS_CELLS`, `MAX_CLASSES` | 5,000, 10 | ADR-0035 |
| context sd in the map | `dependency.CONTEXT_SD` | 0.05 | hand-set |
| care kinds | `dependency.CARE_KINDS` | hospitalisation, authorisation | to become a declaration |
| entry-date properties | `gateway.ENTRY_PROPERTIES` | entry_date, registration_date, processing_month | to become a declared role |
| passing courses | `replication.PASSING` | spike, transient | by definition; attribution error not carried |
| dispersion group minimum | `monolith.MIN_DISPERSION_CELLS` | 200 | hand-set |
| job slots | `PEGASUS_HEAVY_SLOTS` | 1 | measured (2026-10-06) |
| download budget per depth | `study.DOWNLOAD_BUDGET_GB` | 2, 10, 40 GB, unbounded | hand-set; to become the cost model's budget (BACKLOG 9.1) |
| population of a race's expected share | `tools.RACE_POPULATION` | account-6 (race slices, 1991–2030) | hand-set; the account version a study pins |
