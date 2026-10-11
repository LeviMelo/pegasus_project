# BACKLOG.md: the ordered work of PegaSUS and pegasus_data

**This is the work.** Nothing is developed outside it: a new need becomes a unit here first (with its done-when), in the
same commit as the work that revealed it. The design every unit serves is `ARCHITECTURE.md` (revision 5); the code as
it is, `STATUS.md`. The backlog spans both repositories: each unit names where it lands, **[core]** (pegasus_project,
`pegasus_core`) or **[data]** (`../pegasus_data`).

**Rules.**
- **The win condition orders everything** (below). A unit that does not move the reference study forward waits.
- **Each unit lands end to end** (code, its declarations, its documentation, a live check on real data recorded as an
  evaluation) before the next on the same path starts. Units on independent paths run in parallel.
- **Done means its done-when holds on real data,** read, not asserted (CLAUDE.md §5).
- **When a unit lands,** it is marked done here with its commit and evaluation, and `STATUS.md` is updated in the same
  commit. When a unit is found wrong or unnecessary, it is struck with the reason, never silently dropped.
- **Statistical refinement of a built method** (calibration, null worlds) is a unit only when a measured defect blocks a
  study product. Depth on demand, never polish for its own sake.

---

## The win condition

**PegaSUS produces an exhaustive study of toxoplasmosis from one declaration** (ARCHITECTURE §1.4, §3.8):

```yaml
study: toxoplasmosis
topic: {seeds: {icd10: [B58, O98.6, P37.1], sinan: [TOXG, TOXC], terms: [toxoplasm]}}
period: 2010-2025
where: BR
depth: exhaustive
```

**Accepted when** `pegasus-core study toxoplasmosis.yml` delivers a study folder in which:
1. **Scope:** `scope.yml` lists, each with its reason, at least:
   - SINAN TOXG and TOXC;
   - SIH admissions with the codes in any diagnosis;
   - SIM deaths with them on any certificate line;
   - SINASC births with related anomalies;
   - SIA serology procedures and medicines dispensed under the codes;
   - BNAFAR/SNGPC for those medicines;
   - SISAGUA and every applicable context;
   - the related codes found in records (e.g. B20–B24 on certificates, Q03 at birth), with their strength;
   - the person paths with their links' viability.
2. **Fields:** every kind of ARCHITECTURE §5.2 that the sources support is present: counts, measures, compositions
   (incl. infection away from residence), intervals (onset → notification → closure), ratios (congenital ÷ gestational),
   linked shares, a capture of TOXC × SIH × SIM. Quality fields are included.
3. **Components:** all nine (§7.2) are run where they apply, at every support and grain the depth names, with
   per-family error control and the ledger. The declared hypothesis (Santa Maria 2018) is answered.
4. **Relations:** among the topic's and related fields, and with every context. SISAGUA's water quality is related as a
   time-varying context with lags and distances. The data-space screen has run.
5. **Persons:** linked sequences, a cohort scan with same-record and cross-system outcomes, and capture–recapture, where
   links are viable; where not, the report says so.
6. **Interpretation:** every finding carries its recording class with graded evidence, R-ladder replication,
   corroboration by source, a context profile and its story. Institutional findings carry CNES facts.
7. **Products:**
   - findings, descriptive tables, relations, persons and quality tables;
   - model cards and figures;
   - `report.html` readable by an epidemiologist with no developer: names, units, capped lists;
   - `provenance.json`.
8. **Storage and export:** the folder references the lake and store (no copies) and its own files stay small.
   `export` materialises it whole.
9. **Documented event:** the Santa Maria (RS) 2018 waterborne outbreak is found by discovery, not only by hypothesis.
   A miss is diagnosed to its stage.
10. **Cost:** the run completes on this machine within the scope's own cost estimate, and that estimate was produced
    before running.

Intermediate acceptance at each depth (survey, standard, deep) is the milestone of the phases below.

---

## Phase 0: stand on firm ground (now)

| id | unit | repo | done when |
|---|---|---|---|
| 0.1 | Commit revision 5 (ARCHITECTURE, BACKLOG, STATUS, the consolidated docs, CLAUDE/AGENTS) with ADR-0036 | core | committed; `check_docs` green |
| 0.2 | ~~The robust refit's dispersion blow-up~~ **measured 2026-10-10:** SIM chapter III, φ 1.84 → 5.96e5 because the block's φ is re-estimated on imputed counts; the field-level dispersion restores calibration (III B1 KS 0.005, macro-regions ≤ 0.015), so no product is affected; the estimator's bias moves to 8.3 | core | done (no product defect) |
| 0.3 | **`alarms` broken**: (a) SINAN-CHIK `LookupError` (no prospective fit: fit on demand); (b) SIM IX and J09–J18 `ValueError "groups ... have no admissible cell the population holds"` in `monolith._assemble` on the test-period assembly | core | `alarms` runs for one SINAN disease and one SIM chapter, the test-period assembly correct **Done 2026-10-10 (1f94d3d): fit on demand, a session's published years, the as-of year; SIM IX and chikungunya run. Left: 0.3b.** |
| 0.3b | **`alarms` at an epidemiological-week year boundary**: SIM IX at 2023-12-31 (epi week 1 of 2024) alarms in many places with 1–3 deaths known, nowcasts 10–30 and P ≈ 0.9: the delay correction of the year's first week looks wrong (the previous year's delays applied to a week with almost nothing yet known?) | core | an as-of on a year boundary gives the same alarm rate as one mid-year on null data **Done 2026-10-10: the cause was a flat nowcast prior (1 death known at F = 0.28 read as 6) plus week bookkeeping; the baseline is now the prior, weeks cross years and files; SIM IX alarms 0.35% mid-year, 0.23% at 2023-12-31 of evaluated place-weeks. Left: 0.3c (`delay_counts` must count the field's codes, not every cause: 18-20% alarms until it does); SIM 2024 weeks are in the reserve.** |
| 0.3c | **`alarms` counts the field's own events**: `gateway.delay_counts` read every event of the type against the field's baseline (SIM all-cause deaths ~3.5 times IX's) | core | SIM IX alarms at null rates mid-year and at a boundary **Done 2026-10-10: `delay_counts(codes=)` from the field's leaves; 54 of 15,224 place-weeks (0.35%) mid-year, 28 of 13,686 (0.20%) at 2023-12-31, from 19.7% and 18.0%.** |
| 0.3d | **Alarm delays by week of year and day**: the share of SIM deaths registered within the week falls from 0.28 to 0.17 (2023) and 0.12 (2024) in week 52, so boundary weeks are nowcast high; and a mid-week as-of discards up to four days of reporting | core | a week-of-year delay shrunk toward the pooled one, and daily ages, on SIM IX boundary weeks |
| 0.4 | The overnight chain (`night_chain3`: SIM survey, SIH survey, SIA PS/SAD, event records): let it finish or stop it; keep the fits (they serve studies); its register stays as data, not a product | core | decided by what it has produced when 0.1–0.3 are done; recorded in STATUS |
| 0.5 | Retire the stray data homes (`pegasus_project/pegasus_data_home`, `pegasus_project_b4/pegasus_data_home`), the B4 worktree and branch `b4-size`, population-account-1 and -5's files (superseded, unread) — **needs the author's go** (irreversible deletions) | core, data | done or declined by the author **Done 2026-10-10 with the author's go: each verified unread (not a live root, no reader, no uncommitted work); 4.5 GB freed.** |

## Phase 1: a study from one declaration, over what exists (survey depth)

The interface and the product first, over today's machinery, so every later phase adds to a product that works.

| id | unit | repo | done when |
|---|---|---|---|
| 1.1 | **The declaration**: schema (ARCHITECTURE §3.1), validation with readable errors, defaults | core | a malformed declaration says what is wrong; the toxoplasmosis declaration parses **Done (1f94d3d).** |
| 1.2 | **Scope v1**: seeds → ICD subtree and SINAN agravos (through pegasus_data's existing SINAN↔ICD map) → every event type whose *primary* classifier holds them → count fields; contexts = every declared context; written to `scope.yml` with reasons and record counts | core | toxoplasmosis' scope lists TOXG, TOXC, SIH and SIM (primary roles) with counts **Done (1f94d3d), with record counts from the cached counts, download cost per dataset-year against the depth's budget, sources with no records dropped; toxoplasmosis: TOXG 86,268, TOXC 35,425, SIH B58 13,922 / P37.1 16,768 / O98.6 1,356, SIM B58 988 / P37.1 417 / O98.6 46 (2010–2023).** |
| 1.3 | **The planner over existing steps**: a task graph from the scope (reads → fits on demand → surprises → today's questions → triage, replication, corroboration) keyed by content, resuming; replaces `update`'s plan loop for studies | core | the survey-depth toxoplasmosis study runs end to end and a re-run computes nothing |
| 1.4 | **Fit on demand**: any block a study (or `ask`) needs and the store lacks is fitted | core | `ask` on an unfitted SINAN agravo fits and answers **Done (1f94d3d): `monolith.load_or_fit`.** |
| 1.5 | **The study folder**: `study.duckdb` views onto store and lake objects (no copies); store pinning against `gc`; `findings.parquet` from the study's leads with the §3.4 schema (names and codes, units, evidence) | core | the folder opens in DuckDB/R/Python; its own files are under a few MB; `gc` leaves its entries |
| 1.6 | **Descriptive tables**: counts, crude and age-standardised rates with intervals by place, period, group (pegasus_data's `age_standardised_rates` and populations) | core | toxoplasmosis' descriptive table matches a direct recount from the lake |
| 1.7 | **Figures**: maps of rates and findings, series against expectation with intervals, by field | core | figures written for every field with findings **Maps built (`study._map_figure`): the rate by state beside each municipality's standardised departure from B1, the findings' places outlined (pegasus_data `mesh`); with the series, two figures per primary field.** |
| 1.8 | **The report**: `report.html` from the folder (§3.5), stories first, names and units, capped lists, limitations assembled from declarations; replaces `report`/`dossier` | core | an epidemiologist can read the survey-depth toxoplasmosis report without help; it opens in a second **Stories and declared limitations built: findings joined by a shared municipality and overlapping years into stories (the summary's unit, `story` in findings.parquet); methods and limitations assembled from the sources' `source_notes` and `exposure` (definition, preliminary years by the finality rule, known errors, denominators with evidence). Readability to be judged on the run.** |
| 1.9 | **Export**: `pegasus-core export <study> --to <dir>` (whole folder by default; `--tables`, `--format`) | core | the exported folder is self-contained and loads elsewhere |
| 1.10 | **Milestone: survey-depth toxoplasmosis study** | core | acceptance items 1 (primary roles), 3 (built components), 7, 8 at survey depth; evaluation entry |

## Phase 2: fields, every kind the sources support

| id | unit | repo | done when |
|---|---|---|---|
| 2.1 | **Codes in any role**: count fields from secondary diagnoses (SIH), certificate lines (SIM mentions), code lists (SINASC anomalies), procedures and medicines (SIA) for a scope's codes | core (+data where a role is missing) | toxoplasmosis' scope adds SIH any-diagnosis, SIM any-line, SIA procedure and AM-medicine fields **In progress: mentions (SIM certificate lines, SIH all diagnoses) wired into the scope; 4-character seeds read as code-set fields (`assemble(codes=)`, 1f94d3d); SINASC anomaly lists wait for related codes (4.2). 2026-10-10: SIH's every-diagnosis reader was never found for SIHSUS-RD, because the roles and links spell it SIH-RD. Names now compare through pegasus_data's `parse_dataset` (`gateway.dataset_key`), and SIH's links resolve the same way.** |
| 2.2 | **Ratio fields** (numerator over denominator field, optional lag) with their model (§6.4) | core | congenital ÷ gestational by state-year with intervals **Done (see the 2026-10-10 ratio evaluation): declared `ratios:`; TOXC/TOXG 0.31 (2019) to 0.45 (2024); DOFET per SINASC birth 10.2–10.9‰.** |
| 2.3 | **Interval fields** read as delay distributions (median and upper quantile) | core | onset → notification → closure delays per state-year for TOXG **Done: the study's descriptive table gives each interval's median and 90th percentile from the records (`gateway.mark_quantiles`; TOXG onset → notification median 5 days in 2019 and 2023, 2 in 2024); the model stays the log-normal location.** |
| 2.4 | **Composition columns as group dimensions** for every field of a dataset (schooling, occupation, race, …) | core | TOXG split by schooling and occupation with their expectation **Built for composition columns (`Session.by_composition`: the group question over each; `groups.parquet` in the folder; TOXG 2019–2024: 135 departures over 6 columns, e.g. Espírito Santo's schooling 0 at 21.7 times). Occupation waits for code-tree columns (CBO), as `fields.declared` says.** |
| 2.5 | **Quality fields** from every typed column (missing/"ignored" shares; by place, period, facility) | core (+data for "ignored" codes per column) | TOXG/TOXC quality fields in the folder **Built for place and period (`share_moments(quality=True)`, 25 TOXG columns from standard depth; schooling ignored 26.8% in 2019 = the 2,260 records coded 9); the facility waits for 2.6.** |
| 2.2b | **Denominators by the event's population, declared**: births for congenital, birth and foetal outcomes; pregnancies for gestational (an `exposure:` on the event type, read by `monolith.default_population` through 2.2's events exposure) | data + core | SIM-DOFET and SINAN-TOXC read per SINASC birth with no `ratios:` in the declaration **Done: pegasus_data decision 0161 declares them, `default_population` reads them, several event types summed (`events:A;B`); TOXG 2.96 → 6.44 per 1,000 live births (2019–2024), foetal deaths 10.1–10.8 per 1,000 total births.** |
| 2.6 | **Supports**: facility (notifying/recording CNES), place of infection (`COMUNINF`), special supports declared with membership (DSEI) | core + data | TOXG findings at the facility and infection supports **Built: the place supports (`support:<column>`, every municipality column of the event: TOXG's place of infection, recorded for 57%, and notifying municipality, where Teresina notifies 1,682 cases for 737 residents); the facility is the institution question's. The declared special supports (DSEI) wait for 5.7.** **2026-10-10: a code set is read at its supports too, with its own codes (SIA-PA's toxoplasma serology at PA_UFMUN and PA_MUNAT): the consolidated BPA names no patient, so an outbreak's tests show only where they were done.** |
| 2.7 | **Capture fields** (log-linear multi-system model) over linked systems | core | TOXC × SIH P37.1 × SIM P37.1 completeness by state-year (needs 6.2's links) **Model built (`capture.multiple_systems`: every hierarchical log-linear model with pairwise dependences, averaged by Akaike weight with Buckland's unconditional variance); checked on the spina bifida three-list data against R and the published completeness (69/28/25 % against 68/27/25 %). 6.2 measured: TOXC × SIH × SIM cannot be fitted, because SIH → SIM is not viable and SIM names the disease on 726 certificates in five years. Only TOXC × SIH links, and two lists cannot test their own independence: a child admitted is likelier to be notified, so an estimate would be a lower bound.** |
| 2.8 | **Milestone: standard-depth fields** | core | acceptance item 2 except linked shares and capture; evaluation |

## Phase 3: the nine components

| id | unit | repo | done when |
|---|---|---|---|
| 3.1 | **Questions → components**: the registry re-cut into the nine components with their tier pairing (§7.2); share → ratio field, institution → facility support, divergence → trend reference, prospective → BP/BPA over recent periods; methods keep their records | core | every built method answers one component; the old question names map, nothing lost (CLAUDE: never lose a question) **Planned (after the seasonality and propagation branches merge, which add their questions to the same registry): excess → transient (cell_excess, excess, outbreak, space–time); step → step; trend + divergence → trend (B1, and B2 against neighbours/nation); cluster's `excess_level` → level and its `spatial_cluster` → spatial coherence; group → group heterogeneity (sex × age, compositions, race); share → ratio field (its departures asked by the components of that field); institution → the facility support (its steps asked as step at that support); prospective → the BP/BPA mode of every component; seasonality and propagation as they land; relation stays a study product (§8.1). The old names stay as aliases in the registry and in leads' families (never lose a question).** **Done 2026-10-10: each question names its component and a method its own where it differs (`questions.components`); a finding's component is the set of its agreeing methods' (a cluster found by both lenses is level + spatial coherence); the study's separate mapping removed; question ids unchanged.** |
| 3.2 | ~~**Seasonality**: per-place season amplitude and phase against the field's (B2s), and their change~~ **done 2026-10-10** (evaluation [2026-10-10-seasonality](docs/evaluation/2026-10-10-seasonality.md)): the `seasonality` question, methods `season_level` and `season_change` (`scans.lenses.season_departure`, monthly grain, municipality/region/state); the field's season is the rest of the field's, not B1's | core | met: dengue 2010-2019 by state in the documented order (west early, Southeast on the field's peak, Northeast last, Roraima off), 5 state answers; TOXG 2019-2024 asked, nothing departs. Left: a planted seasonal shift on the B3 grid; a synthetic null with N1's noise |
| 3.3 | **Propagation**: first-departure times over the graph, direction and speed of spread; emergence of a field in places where it was absent | core | the 2015–16 microcephaly emergence and the 2014 chikungunya spread from Amapá read as propagation **Built, partly validated (evaluation 2026-10-10-propagation): chikungunya's 2015 North-East spread and a small 2014 Bahian wave found, the Amapá entry not; the 2015 microcephaly emergence found (SINASC Q02 monthly against BP 2012–2014: one wave from Ilha de Itamaracá, PE, onset 2015-11, earliest June–July 2015 in metropolitan Recife and the North-East, 816 of 826 places emerging, p 0.007 under the spectral null).** |
| 3.4 | **Group heterogeneity on every dimension** (generalising `group_disparity` beyond sex × age; race through §2.6) | core | TOXG heterogeneity by schooling and race answered **Done: the group question over every composition and the race stratum (`tools.group_columns`); race expected from the place's own population by race (the account's slices), re-levelled to Brazil's disparity. TOXG 2019–2024: Espírito Santo records race 'amarela' 18.5 times expected, Roraima's indigenous women are notified at 0.24 of their share, Piauí leaves race unrecorded 2.9 times.** |
| 3.5 | **Relation as one cross-structure estimator** (distance × lag × scale; group and conditional where found), surrogates keeping each field's structure; replaces `compare`, `relation`, `joint` and the map's pair test as separate tools | core | gestational → congenital toxoplasmosis lag recovered; arbovirus → microcephaly (documented, missed twice before) re-tested **Measured on the existing joint model: TOXG and TOXC co-move in the same year at every scale (ρ 0.18–0.98), a shared driver; the single estimator replacing `compare`, `relation`, `joint` and the map's pair test is not yet built.** **Contexts joined (2026-10-10): a time-varying context is a series with its own predictive (binomial or Poisson on its declared denominator, place and year effects, quasi-likelihood dispersion, AR(1) whitened: `relations.context_innovations`) entered beside the field in the one relation map (`tools.determinants`, deep depth and above). TOXG 2019–2023 against CNES facility counts: 180 rows, none at q. Controls on SISAGUA 2014–2023 (2026-10-11): the place-level layer (`dependency.field_map`, each topic field's place effect against the contexts, Moran null; the study's determinants run both layers) admits SIH diarrhoea A00–A09 with E. coli presence (ρ 0.15, p 0.001) and total coliforms (0.13, 0.014), and nothing for femur fractures S72 (the negative control). Raw rates agree: the municipalities in the highest quartile of E. coli positivity have 3.8 times the admission rate of the lowest (Spearman 0.17 over 5,362). The time-varying layer finds neither pair year to year (smallest p 0.25 and 0.19). Its power is not characterised; that needs a planted year-to-year signal.** |
| 3.6 | **Hypothesis mode**: declared component tests with their own budget | core | the Santa Maria 2018 hypothesis answered **2026-10-10: each source is tested at its residence and at every place it declares (`study._hypothesis_readers`, `fields.support_sources`, columns of the item's layout years), in the hypothesis's Holm family. Known answer, SIM-DOFET P37.1 underlying cause, Santa Maria 2018: 3 foetal deaths (20 April, 26 April, 2 June) against 0.013 expected at the residence (rate ratio 225, from 46), 3 against 0.48 at the place of occurrence (6.3), both supported. SIA-PA toxoplasma serology by Santa Maria establishments: 960-1,209 a month through 2017 and 1,054-1,158 in January-March 2018, then 3,075 in April and 4,613 in May, 1,943-3,311 for the rest of 2018 and 1,759-2,267 a month through 2019 (a transient, then a step: the follow-up of the exposed), but 2-8 by the patient's residence (the consolidated BPA names no patient), so SIA answers only at its place of care (PA_UFMUN). SIA-PA is not in the lake.** |
| 3.7 | **Milestone: standard-depth study** | core | acceptance items 2–3 at standard depth; evaluation |

## Phase 4: topic resolution

| id | unit | repo | done when |
|---|---|---|---|
| 4.1 | **Concept index**: SINAN↔ICD, SIGTAP procedure↔ICD compatibility, APAC ICD↔procedure/medicine counts, CATMAT↔SIGTAP where published, label search flagged; a public API | data | for B58/O98.6/P37.1 the index returns the SINAN agravos, the compatible procedures, the medicines dispensed under them with counts **In progress (pegasus_data d2f6f3f): `concept_index` gives SINAN agravos by their records' ID_AGRAVO, SIGTAP's compatible procedures, ICD-10 and SIGTAP label search (finds the toxoplasma serology). Left: APAC ICD → procedure/medicine counts (SIA AM, not in the lake yet), CATMAT ↔ SIGTAP, SINAN agravos outside the lake (opt-in download).** |
| 4.2 | **Related codes from records**: co-occurrence on the same record (SIM lines, SIH secondary diagnoses, SINASC anomaly lists) and the same person (viable links), observed/expected with intervals and FDR | core (+data for record-level reads) | B20–B24 found related to B58 on certificates; hydrocephalus to P37.1 in admissions **Built for co-occurrence on the same record (`cooccur.related_codes`, stratified by sex × age band, exact Poisson, BH, lift with interval), listed in the scope and read as fields beyond a survey. SIM 2015–2023 certificates with B58/P37.1: 88 related categories; HIV B24 on 7,816 at 27.6× [27.0, 28.2], B20 23.1×, and AIDS's opportunistic infections (pneumocystosis B59 16.2×, cytomegalovirus B25 22.5×, CNS tuberculosis A17 25.3×). Same-person co-occurrence waits for 6.2's links.** **At deep depth and above a related code is read in every other served source that records it (`study._related_elsewhere`): its ICD-10 classifiers as a code set, and ICD-10 code columns such as SINASC's anomaly list as the code's node, over years already in the lake.** |
| 4.3 | **Scope v2**: seeds → concept index → every dataset holding the codes in any role → related fields → person paths with viability → contexts; reasons and cost per item | core | acceptance item 1 except the not-yet-ingested sources **Person paths built: every declared link touching a read source, with its stored runs' verdicts (`scope.yml` person_paths, the report's scope section). Beyond a survey, a usable path's linked share is read as a field over the years whose covering runs are all usable (`study._linked_items`); a year without one is said, never read as unlinked.** |

## Phase 5: data intake (pegasus_data)

| id | unit | repo | done when |
|---|---|---|---|
| 5.1 | **Source assessment of the DEMAS API** (113 endpoints): origin, breadth, granularity (aggregate or microdata), columns, equality against the origin on one state-year where one exists, paging, lag; decision per endpoint (origin / DEMAS / skip) | data | an evaluation table covering every endpoint, each with evidence |
| 5.2 | **Source assessment of ANVISA open data** (SNGPC and related) | data | same |
| 5.3 | **Publication audit** of every served dataset: every publication's columns, years, totals; what each form collects (its documentation) | data | a recorded table; every dataset's "is this all there is?" answered |
| 5.3b | **SIM-DOFET's residence column in an older schema generation**: counting its events fails with `MissingColumnError: 'MUNIRES' is not present in family SIM_DOFET_55e…` (2026-10-10, the toxoplasmosis scope); the role names a column one generation lacks | data | DOFET counted over every published year |
| 5.4 | **Source definitions and caveats as declarations** (SINAN's technical notes: definitions, validity start, freeze rule, known misclassification), surfaced through the API | data | TOXG/TOXC carry the Nota Técnica 133/2022 definitions and caveats; studies inherit them |
| 5.5 | **SISAGUA** ingested by the assessment's verdict: monthly control and surveillance samples, out-of-standard results, treatment, population supplied, as time-varying contexts by municipality | data | water quality for a municipality-month readable through the API with its meaning |
| 5.6 | **Medicines**: BNAFAR stock (facility × month × CATMAT), SNGPC retail sales, BPS prices, by verdict; CATMAT code structure | data | spiramycin/sulfadiazine/pyrimethamine series by place and month |
| 5.7 | **Indigenous health**: SIASI modules (morbidity, pregnancy follow-up, deaths, sanitation) with the DSEI support and its membership | data | SIASI records readable by DSEI |
| 5.8 | **Primary care and programmes**: Previne Brasil indicators, SIAPS consultations (CIAP/CID), SISVAN | data | readable with meaning |
| 5.9 | **The remaining DEMAS families** by verdict (ESAVI, SRAG, CNES microdata, arbovirus aggregates, PNI doses, …) | data | each ingested or skipped with its evidence |
| 5.10 | **Context fields for every new source**, declared (unit, grain, support, denominator) so studies find them automatically | data | `contexts: auto` picks them up |

## Phase 6: persons

| id | unit | repo | done when |
|---|---|---|---|
| 6.1 | **Same-record outcomes in the cohort scan** (an anomaly at birth against the mother's attributes) | core | SINASC anomalies × mother's attributes answered **Done: `cohort` reads outcomes on the person's own record (`record:COLUMN=values`, `record:COLUMN~codes`), no link needed. SINASC 2021 (2,677,101 births): anomaly recorded on 22,959, Down syndrome (Q90) on 1,125; preterm gestations 3.3–4.3× the anomaly rate, breech presentation 2.6×, sex not recorded 85× (undetermined sex marks genital anomalies); 1,056 s, the record identities' read the bulk.** |
| 6.2 | **New links declared and measured**: TOXG → SINASC birth, TOXC → SINASC birth (SINAN carries the birth year only since the LGPD), notification ↔ admission ↔ death for the topic's codes; viability decides | data | each link run with its viability verdict on real years **Done 2026-10-10 (pegasus_data branch `links`, evaluation 2026-10-10-links-toxoplasmosis): SINAN's birth date rebuilt from the age in days counted back from DT_SIN_PRI (99.7% give ANO_NASC, 91.8% from the notification date). TOXC → SIH admissions with P37.1/B58: 1,444 pairs at 5.75% chance, use with caution. TOXC → SIM: 101 at 6.9%. SIH → SIM, TOXC → SINASC and TOXG → SINASC: not viable. Per year (the runs a linked share reads), TOXC → SIH is usable with caution in every year 2019-2024: 11.3-16.2 % of notifications linked, chance upper bound 7.9-14.5 %.** |
| 6.3 | **Linked sequences in studies** (fields along a scope's person paths) | core | births with anomalies → infant admission → death shares in the toxoplasmosis study |
| 6.4 | **Capture–recapture** as a study product (2.7 + quality) | core | completeness by system, state, year in `quality.parquet` |
| 6.5 | **Milestone: deep-depth study** | core | acceptance items 5 and 6 (persons, replication) |

## Phase 7: interpretation

| id | unit | repo | done when |
|---|---|---|---|
| 7.1 | **Institutional findings**: the facility class becomes a finding class read with CNES facts (type, opening, services, beds) and other-chapter volume | core (+data for CNES facts by facility-year) | a facility-concentrated toxoplasmosis finding shows its facility's facts **Built: a facility-concentrated finding is reported as institutional (its own report section, no longer among recording explanations), with each establishment's CNES.ST registration at the finding's first and last year (`gateway.establishment_facts`: name, type, SUS link, beds, obstetric centre, neonatal unit; absent at the start = opened within it). Hospital de Clínicas de Porto Alegre 2023: general hospital, SUS, 526 beds, obstetric and neonatal. Other-chapter volume is not yet attached.** |
| 7.2 | **Context profile** on every finding | core | every finding row carries it **Built: `context_profile.parquet` (every finding × every rated context: mean over its places in the period, national percentile), the three most extreme named on the row; counts without a declared denominator are left out and size enters once (residents). A small Piauí municipality: sewer network p1, households without a bathroom p99. Strata contexts (ANS, INEP, climate, disasters) need their `where` and are skipped, logged.** |
| 7.3 | **Stories as the report's unit**, ranked by evidence, effect, burden | core | the report leads with stories |
| 7.4 | **Related-field consistency** beside corroboration | core | gestational → congenital consistency shown on stories **Built: `related.parquet`, every other primary field of the study at a finding's places and years, O/E with its exact interval; the row names those whose interval excludes 1. TOXC over Rio Grande do Sul 2019–2020 1.36 [1.24, 1.49]; Porto Alegre 2023 0.57 [0.42, 0.75].** |
| 7.5 | **Quality findings** in the report | core | the data-quality section is filled from 2.5 and 6.4 |

## Phase 8: the model where a study needs it

| id | unit | repo | done when |
|---|---|---|---|
| 8.1 | **The cell predictive in large places** (OPEN_QUESTIONS 12): the persistent place-year frailty's shape in the cell test (a place-year against its own other years under the copula), not a threshold | core | births' cell excess holds q on 20 B1 null worlds; real-data z tails per size class within N(0,1)'s; power no worse |
| 8.2 | **B0 scans under persistent frailty** (OPEN_QUESTIONS 16): spatial_cluster's null carries the field's spatial and temporal persistence | core | spatial_cluster holds q on B0 null worlds |
| 8.3 | Interval, composition and ratio models at v1 (§6.4) where 2.x built a v0 | core | each with calibration in its model card |

## Phase 9: execution and speed

| id | unit | repo | done when |
|---|---|---|---|
| 9.1 | **Cost model** from measured throughput, shown by `scope` | core | estimates within a factor 1.5 of the actual run on the toxoplasmosis study **Built, to be measured: each item's wall clock predicted before the run (`study._estimate`: its own measured seconds from earlier studies' provenance; else the nearest stored fit of its dataset and block scaled by years, or the stores' fit-seconds-on-events relation; plus the median measured question pass), shown by `scope` (`estimated_minutes`); each run records its items' seconds. Fit seconds on events alone scatter by a factor ~7 (log sd 2.1 over 273 fits), so the first runs set the per-source figures.** |
| 9.2 | **Vectorised component passes** across a family's fields | core | per-field component pass at least 5× faster on a SINAN family, same answers **Composition counts batched (2026-10-11): the survey run spent over an hour in SIH's group question, re-reading each year's 11 million admissions once per composition column (12 s a read); up to four uncounted columns now come from one read (`gateway.COMPOSITION_BATCH`), each stored on its own key; identical tables on TOXG 2019's eight columns; all columns at once was 26 s a year but took the free memory to zero.** |
| 9.3 | **Screen, then examine** with error control across the stages | core | same findings at q on the grid, less time |
| 9.4 | Lake and store hygiene as studies grow (pinning, `gc` budgets, prune after verified builds) | core + data | disk stays within its floor during the exhaustive run |

## Phase 10: exhaustive

| id | unit | repo | done when |
|---|---|---|---|
| 10.1 | **The data-space screen** (§8.3) over every served field | core | the toxoplasmosis screen runs; what passes becomes related fields **Built, to be run at exhaustive depth: `study._screen` reads every system the store has fitted over the topic's years with the topic's own in one `relation_survey` (window chosen to maximise systems × years: 76 systems on 2019–2023), keeping the relations that involve a topic field. Fixed on the way: the factor model asked for more factors than stacked series (two fields: K 16 against 6).** |
| 10.2 | **The win condition** | core + data | every acceptance item above holds; evaluation entry; the author reads the report |

---

## Open items carried from the superseded plans

*(Filled from the 2026-10-07 work plan and package plans when they were archived; each either maps to a unit above,
waits as depth on demand, or is struck with its reason.)*

| item | from | maps to |
|---|---|---|
| S0.7: a field's question pass under its speed target (an SIH field 191–231 s; dispersion, κ, v0 nulls and peaks still per field) | work plan 2026-10-07 | 9.2, 9.3 |
| S0.3: per-object RAM declared, not measured | work plan | 9.1 (the cost model measures memory too) |
| S0.8: exhaustive SIM and SIH survey times not measured; the `s6_0_*` logs were to measure it (the chain died 2026-10-10 03:32 with no error, after SIM chapters I–IV) | work plan | 9.1; 0.4 |
| S6.0 / S6.0a: SIM all-chapters (partial: I–IV), SIH all-chapters (never ran), S6 plans re-read after NB-P | work plan | 0.4, then the "survey of everything" as a study (phase 10) |
| S6.1: SIA plans (PS, SAD, APAC, dialysis) not fitted and asked | work plan | 2.1 (SIA through scopes); phase 10 |
| S1.2 / S1.5: missed positives (Fundão, Manaus home deaths, capitals' stays, São Paulo caesarean law, Roraima); proposed next steps: a positive control within the data, one quantity in two systems, declarations of the scale a finding must cover | work plan | 2.2 (ratio fields: one quantity in two systems), 3.1, 11 (documented events); each re-scored when its component lands |
| S1.4: about 40 older-form dengue columns with no label; per-year fill measure (pegasus_data OQ 71); places in non-nesting code systems; SINASC newborn race 2011–2013 | work plan | 5.3 (publication audit), 2.5 (quality fields) |
| P1: datasets without event types (CNES, SISCAN, PNI, undeclared SIA families); 478–938 columns waiting for missing codes; 58 undeclared | work plan | 5.3, 5.9; [data] declarations as phase 4–5 scopes need them |
| S2.2 / S2.4(a): link years incomplete (CIHA runs, newborn-admission years, SIH→SIM 2010–13) | work plan | 6.2 |
| S3: the women's race confusion tested, not wired (OQ 10); no adult confusion on the census axis | work plan | 3.4 (heterogeneity by race) |
| B3 / B5: re-read surveys after NB-P; the cell predictive in large places; B0 null with persistence | work plan | 8.1, 8.2 |
| S5 / S4: re-triage, verdicts, corroboration once link-years are stored | work plan | 7.x, 6.2 |
| S7 / D: surveillance (alarms as findings), serving; top model, N2 marginal uncertainty, BYM2 exceedance, interaction patterns, exact reference fit (OQ 2) | work plan | 0.3 (alarms); prospective as BP/BPA components (3.1); depth items wait as depth on demand; serving struck (no agents) |
| dormant: institutions in the likelihood; one model across chapters; interaction patterns; an epidemic-level component for BP; positives for trend divergence, group disparity, marks; the dengue–climate lag; race in g | old STATUS | depth on demand, each when a study product needs it; the dengue–climate lag → 3.5 |
| optimisation plan §5 (pipeline speed) | 2026-10-06 optimization | 9.2–9.4 |
| overhaul O3 race axis, O4 ICD-9 bridge, O6 cluster/group on departure models, O7 endemic–epidemic and declared confirmations (arbovirus → microcephaly, cold → respiratory), O8 coding-regime term, O10 alarms against Farrington/Noufaily | 2026-10-06 overhaul | O6 → 3.1; O7 → 3.5; O8 → 7.x (recording as measurement); O3 → 3.4; O4, O10 depth on demand |
| questions-and-methods: Cauchy combination to replace the union bound across a component's methods; D and E questions not in `QUESTIONS` | questions plan | 3.1 |
| fields-from-roles: pegasus_data to declare a number's measurement scale and a category's order; positives for a measure and a composition | fields plan | 2.x [data]; documented events for measures and compositions in 11 |
| o7: horseshoe prior and Bayesian FDR on loadings unbuilt (EM + ARD used); `relations.spectral_factor_model` unwired | o7 plan | 3.5 decides what of it the cross-structure estimator keeps; the rest struck or depth |
| the block's φ in the robust refit is estimated on imputed counts (flagged cells set to μ), biased toward Poisson: SIM III 1.84 → 5.96e5; the field-level dispersion restores calibration (III B1 KS 0.005), so no product is affected | 2026-10-10, unit 0.2 | 8.3 (exclude flagged cells from the dispersion likelihood instead of imputing them) |
| the "Architecture learned from results" register of the old STATUS (`history/STATUS-2026-10-07.md`) | old STATUS | read into ARCHITECTURE where still true; the rest is history |
