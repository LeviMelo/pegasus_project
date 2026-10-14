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
applicability to filter on. SIM and SIH declare no `source_notes`, so the methods' limitations section is empty for
them: a curation gap, and adding notes today re-keys every count (`gateway._declared_key` hashes the whole declaration).
