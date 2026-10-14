# A study folder as a paper's only source (2026-10-14)

**Why.** The author: the folder goes to researchers, or a model, who write the paper from it alone, at every depth; it
was "categorically insufficient". Audited against a paper's sections (table 1, rates and their comparison, trends,
maps, completeness, methods, linkage), the folder lacked: whole-period rows (only years, to be summed by hand); any
table per municipality; completeness as numbers; anything to compare an area's rates with; trends with their own
columns (an APC sat in the `rate` columns, said only by the text of `per`); a methods text; a linkage table; and
descriptive's column `group` is an SQL reserved word.

**Regime.** `scratchpad/run/smoke_products.py` driving the products of `studies/infarto_alagoas.yml` (Alagoas, SIM-DO
I21-I22, 2014-2023) on the working tree after ec45de0, pegasus_data 7593925; the SIM-DO block refitted (11 s), the
products 57 s warm. Output read table by table.

| check | read | against |
|---|---|---|
| area deaths, 2019 | 1,573 (49.0 /100k; standardised 46.5) | Alagoas ~1,500 I21 deaths a year (TabNet order) |
| Brazil reference, 2019 | 95,652 I21-I22 deaths (46.0 /100k) | ~95,000 AMI deaths a year in Brazil |
| reference before the fix | 1,221,011 (every death) | a code-set field is node `*`: the code set had not been applied |
| indirect expected, 10 years | 15,126 = observed 15,126 | by construction |
| ill-defined causes, all AL deaths 2019 | 940 / 20,287 = 4.6 % | AL ~20,000 deaths a year |
| age-sex adjusted APC | AL +1.35 % (-0.73, 3.46); Northeast -1.99 % (-2.78, -1.20); Brazil -2.23 % (-2.87, -1.59) | crude AL +4.11 %: ageing read as risk |
| linkage, sih_deaths_to_sim | 10 runs, false-match 0.84-1.00 % (upper bound ≤ 1.03 %), independent agreement 93.7-99.1 % | 2019-2023 were runs of 2026-10-10, served as current |

**Found beside.** `gateway.link_report` read a run's report file with no currency check: runs made before the linkage
fixes counted as stored (not remade by a study, their verdicts read). Now pegasus_data's `linkage.store.report`, the
rule `load` applies. A test asserted two such stale verdicts; it now accepts "not stored".

**Kept as found.** Variables that never apply to these deaths (the mother's education, death relative to childbirth)
read 100 % not recorded in quality.parquet: true, and left for the reader to filter; pegasus_data declares no
applicability to filter on. SIM and SIH declared no `source_notes`, so the methods' limitations section was empty for
them, and adding notes would have re-keyed every count (`gateway._declared_key` hashed the whole declaration). Since
then (same day): the notes are declared with their documents (pegasus_data 2e24cc0) and the key ignores documentation
(7f93a06).

**The whole study, read.** `studies/infarto_alagoas.yml` (deep) on PegaSUS 8498322, pegasus_data 7593925, after the
relink: 8.6 min (scope 29 s, store 10 s, lanes 319 s, products 158 s; 26.6 min the day before), every `body` part met
but the codebook (`records_with_code`, fixed in bf582f4). Read beside the smoke: SIH's in-hospital case fatality of the
topic's admissions (MORTE = 1 in groups.parquet) 16.1 % (15.4, 16.9) over 2014-2023; the linked share of those
admissions paired with a SIM-DO death record fell below it in several years (2016: 20.1 % against 22.6 % dying in
hospital), so the link misses some in-hospital deaths (sensitivity near 85-90 %, not yet a column); the linked shares
had carried the count fields' labels (fixed in bf582f4). Seasonality: deaths peak in June-July (index 1.10, 1.05-1.16).
Gaps found and queued: the topic's own measures (length of stay, cost) were not read for a code set (a deep study read
supports only); `by` and `where` are SQL reserved words in groups and associated; climate is declared as sums and
readings that no context entry can divide; three census fields named their denominator in prose only (pegasus_data
bfbdafe).

**The topic's own measures, ages and shares** (`scratchpad/run/smoke_products.py` on HEAD 7f93a06 plus the queued study
patches, from a scratch export; SIH-RD and SIM-DO I21-I22, Alagoas 2014-2023). Admissions: age 62.3 (sd 12.3; men 61.2,
women 63.9); length of stay (DIAS_PERM) mean 9.1 days, median 6 (IQR 3-12), the admission-to-discharge interval one day
more as defined; ICU days mean 1.8; AIH value (VAL_TOT) mean R$ 3,034, median R$ 1,116. Proportional: 41.7 % (41.1, 42.4)
of the area's ischaemic-heart-disease admissions (I20-I25), 7.0 % of chapter IX's, 0.56 % of all. A first version counted
every value out of domain: `NOT IN (NULL)` is never true, so a measure with no declared missing code read none; read
before commit.

**What the linked share is** (corrected the same day). `sih_deaths_to_sim` pairs only admissions that ended in death
(its left side is `admission.death = 1`) with their certificates: the cohort of Alagoas's 2022 I21-I22 admissions (the
code-set cohort, `scratchpad/run2/cohort_debug.py`) found 159 linked deaths, all among the 168 with MORTE = 1 and none
among the 996 discharged alive. So "12-20 % of admissions paired with a SIM-DO death record" above is in-hospital
mortality as the link finds it, not death after admission, and the link's sensitivity for in-hospital deaths there is
159/168 = 94.6 % (nationally its `linked_share`, 0.89-0.92 a year). The cohort scan had read MORTE as an attribute of
that outcome (its fit diverged: log RR 27.7, sd 6,969, p 0.5); a column a link's side filters on is no longer one.
