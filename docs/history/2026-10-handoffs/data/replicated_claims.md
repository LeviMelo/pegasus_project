# Handoff: reading the 57 replicated national-trend claims (2026-10-05)

## Goal
Read the 57 R2 unit claims (SIM survey <= 2019, blocks I IX X XVIII XX; state-scale divergence from the national course holding in later
years AND in other places; evaluation 2026-10-05-replication-independent-units.md, c9720d2) against four rivals: (a) coding practice /
sibling substitution, (b) SIM completeness (ADR-0146), (c) denominator (POPSVS vs account-3), (d) known epidemiology. Classify each
substantive / artefact / unresolved; say what the findings and the surviving artefact classes mean. Evaluation entry + EVALUATION row,
check_docs, commit own paths, message ends "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", never push, reserve (SIM.DO 2024) untouched.

## State
- The 57 claims live in the register pegasus_home/leads_T2019 (tier R2 = kinds_of >= {temporal, spatial}); all 57 are STATE claims (no region).
- data/replicated_claims_cache.py: events (u,year,sex,band,code3,y) 2010-2023 and POPSVS / account-3 by 18 bands -> data/replicated_claims/*.parquet (done).
- data/replicated_claims.py: per claim O/E (indirect standardisation on the national rates of each year), quasi-Poisson slope with both
  populations, sibling / R00-R99 / all-cause excess change 2010-11 -> 2018-19, completeness drift -> data/replicated_claims/claims.json.
- DONE: classified (42 A, 13 U, 2 S = 1 distinct finding); entry docs/evaluation/2026-10-05-replicated-claims-read.md + EVALUATION row; check_docs green; scripts data/replicated_claims*.py (cache, claims, classify, probe, family, violence, table; run in that order, then the entry by hand).
- Open: the 13 U need certificate-level data or coding-software history by state. Was: write docs/evaluation/2026-10-05-replicated-claims-read.md + EVALUATION.md row, check_docs, commit.
