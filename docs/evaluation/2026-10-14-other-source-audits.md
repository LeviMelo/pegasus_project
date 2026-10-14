# Two more blind paper audits, on SINASC and SIA; what the system got wrong in general (2026-10-14)

**Regime.** `studies/microcefalia_pe.yml` (SINASC-DN, Q02 on CODANOMAL, Pernambuco 2012-2019, standard depth) and
`studies/dialise_al.yml` (SIASUS-ATD, N18 on AP_CIDCAS, Alagoas 2014-2023), run on ddf6a11. Each folder went to a Sonnet
agent that saw nothing else and wrote the paper (`data/handoffs/paper-audit-sources-brief.md`; drafts and audits in
`data/handoffs/audit_microcefalia/`, `audit_dialise/`).

**SINASC.** The documented event is in the folder: 34.1 (31.1-37.2) per 10,000 live births in 2015 against 0.7-0.8 in
2012-2014, a monthly rise from 12 births in August 2015 to 206 in November. The system's defects:
- the mother's sex and age read as the newborn's strata (every event "female" over women's person-years);
- no live-birth denominators by municipality;
- count rows written twice, and the `rates` view collapsing per-births and per-person-year rows;
- the monthly test of the declared hypothesis failing on a code list;
- a code-list item read at no other place.

**SIA.** The folder counts authorisations, not patients, and never says so in its methods. The two defects that
mislead:
- 2014 holds August to December only and read as a halving into 2015;
- N18 is on 12 % of the authorisations, falling from 31 % to 7 %, so the field's -10 %/year is coding.
The auditor recovered the census's prevalence (474-688 per million) only by hand.

**Fixed (general, not per study).**
- A births field is rated per live births only: its municipalities too, its case mix by the mother's age band, no race
  ratio or sex.
- A perinatal field's per-births rows add no second count, and the `rates` view groups by the denominator's kind.
- A monthly source's year the lake holds fewer than twelve months of is `partial` (the reason stated); trends and
  seasonality leave it out.
- Every ICD-10 source states the share of its events with no code of the tree on its classifier (ATD: 68 % in 2014, 89 %
  in 2023).
- A code-list item gets support readers; `code_list_counts` reads at a support place, and a monthly code-list fit no
  longer fails on its own keywords.
- Data quality is met by the topic's own completeness by year where no quality reader applies.
- Each estimate has an `id`.

Rerun on the fixes, both folders meet every part of `body()`. Recife's monthly test reads 129 microcephaly births in
August 2015 to June 2016 against 1.5 expected; at the place of birth, 424 against 7.8.

**Left to pegasus_data** (fix-data9): SINASC's sex coded 1/2 in some years and letters in others, measures' sentinels
(SINASC's measures; ATD's laboratory values), ATD's evidence measured on ATD. **Next here:** distinct persons where a
source identifies its subject (the SIA folder had no patient count), then a third audit.
