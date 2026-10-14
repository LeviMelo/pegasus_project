# A code-list field read whole; a birth field rated per live births; the SINASC study (2026-10-14)

**Why.** A study of microcephaly (Q02) among live births in Pernambuco, 2012-2019 (`studies/microcefalia_pe.yml`, the
second audit's SINASC study), found four defects:
- The topic's seeds did not reach SINASC's anomaly list (CODANOMAL), which was readable only as a related field.
- Once reached, every product except the counts read the list's field name (`codes:CODANOMAL`) as a column: the case
  mix (20 columns), seasonality, the references and the placed share.
- The anomaly was rated per 100,000 person-years of every resident.
- The report failed on a folder without ratios (no `comparator` column).

**What.**
- `gateway._code_sql` builds a record's code once, from a column or from a code list exploded into its distinct
  ICD-10 categories (`code_list_counts`' rule). It replaces six copies in the readers; `monthly_counts`, `mark_values`,
  `unplaced` and `event_totals` read lists too.
- `fields.classifier_of` and `fields.codes_of` give a field's classifier and codes to every product. Each product had
  taken `source["classifier"]`, which for a code list is the field's name.
- `code_list_counts` keeps its unallocated events by category. A code-list block's lost events had all been null-coded,
  so no block counted them.
- A field whose events are live births is rated per live births (birth prevalence), with Brazil's, the macro-region's
  and the region-without-the-area's rates per live births beside it.
- estimates.parquet carries its whole schema, typed, whatever the producers emitted.

**Shown.** `data/probes/microcefalia_pe3.log` (commit after d57121a, real root, area PE). The study runs in 147 s and
`body()` meets all 23 parts. The documented event shows in the numbers: Pernambuco had 10-12 microcephaly births a
year in 2012-2014 (0.07-0.08 per 1,000 live births), then 494 in 2015 (3.41, 95 % CI 3.11-3.72) and 259 in 2016.
Brazil's 2015 is 1,758 of 3,017,563 live births (0.58 per 1,000), against 1,608 (0.546) in Marinho et al. 2016
(Epidemiol. Serv. Saúde 25(4)), and the Northeast's 1.54 per 1,000 against their 1.39 (95 % CI 1.31-1.47). Their
figures imply 2.95 million live births, the preliminary 2015 file; the final one holds 3.02 million. The difference fits
that revision; their state tables were not checked. Keys: the readers' code changed, so the window adopted stored
results for every reader but `code_list_counts`, whose output changed. Its 16 adopted entries and 18 SINASC
code-list blocks were removed and recomputed.
