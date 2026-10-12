# A study of one state (2026-10-12)

**Scenario.** `studies/toxoplasmosis_rs.yml`: the smoke study's declaration with `where: RS` (497 of 5,570 places).
Seeds P37.1 and TOXC; SINAN-TOXC, SIH-RD, SIM-DO; 2015–2023; deep; code sets; questions excess and group; readers
compositions and linked; two related codes; the Santa Maria hypothesis. Run worktree at 8652ee0 (rs5), shared store;
log `pegasus_project/data/probes/study_toxo_rs5.log`.

**Ran.** 293 s, no step failed (scope 18, store 2, lanes 15 on fits rs4 had stored, products 259: hypotheses 117,
persons 101, field tables 23, groups 17). 10 findings, 724 relation rows, 18 hypothesis rows. Estimate 20.9 min: the
products overhead was carried from the national smoke study, scaled by items.

**Defects found on the way (rs1–rs4), fixed with a fast test each.** The model loaded Brazil's parameters (the
assemble key lacked the area); the graph and the evidence grid were Brazil's while the blocks were the area's (triage
indexed place 4,799 of 497); the register and ledger were shared with national studies (now `leads_area_43`).

**Read.** TOXC's group finding in Santa Maria in 2019, the year after the outbreak, is triaged signal. The hypothesis
(2018) cannot be tested on TOXC, which starts in 2019; SIH's B58 admissions at their place of care were 9 against 4.1
expected (p 0.03), not supported after Holm over the sources. The 2021 cohort reaches 3 SIM deaths in every draw;
2022 and 2023 reach none, because SINAN-TOXC → SIM is "not viable" in 2022 (chance pairs up to 28.9 %) and reserved in
2023. The persons table had reported those zeros as outcomes; it now names the missing link, and it records each
cohort's tested contrasts when none is at q.
