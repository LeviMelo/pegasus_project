# Handoff: Y35 in Goiás, declared test (ledger 3d787b765f614065)

## Goal
Run the declared test of docs/evaluation/2026-10-05-y35-goias-declaration.md / data/y35_goias_declaration.json: score each prediction of
real / recode / coverage separately with grade (tested/bound/consistent); no hypothesis dropped without a discriminating test.
Deliver: yearly table (GO, BR) of firearm deaths by intent, pooled, Y35, FBSP counts, SIM/FBSP; certifier (ATESTANTE) of Y35 vs X95/Y24;
victims' profiles; SIH firearm admissions; verdicts; "Result" section in the declaration entry; ledger result row for the id.
Commit own paths only, message ends "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", never push. Reserve (SIM.DO 2024) untouched.

## State
- DONE: SIM 2012-21 (BR), FBSP (GO 2015-23, BR 2013-23; GO 2012-14 not obtained), labels, analysis (data/y35_goias_analysis.py -> analysis.out, results.json), Result section in docs/evaluation/2026-10-05-y35-goias-declaration.md, ledger result row (data/y35_goias_ledger.py; written ONCE, do not rerun), EVALUATION row.
- Verdict: both (real rise in police killings + coding catch-up Y35/FBSP 0.01->0.30); recode of ordinary firearm deaths rejected as main account (<=34% of the fall); no certifier/IML break.
- GAP: SIH firearm admissions unscored. data/y35_goias_sih.py ran for 2014 only (1,034 firearm-coded of 359,979); other years stall >40 min on the shared decode queue (CPU idle). Rerun when the machine is quiet: `python data/y35_goias_sih.py` (peak 0.3 GB/year, no heavy wrapper needed), then `python data/y35_goias_sih_analysis.py`, add the table to the Result section.
- pegasus_data defect found: translate mislabels CIRCOBITO (1/3 swapped: codelist TIPOVIOL) and LOCOCOR (2/4); layout and cross-tab with cause agree with each other, not with translate. Not fixed here (other repo).
- PDFs and parquet under data/y35_goias/ are gitignored (data/); scripts, fbsp.json, results.json, analysis.out are force-added.
