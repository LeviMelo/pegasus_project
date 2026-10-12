# The slice gate, and Santa Maria found (2026-10-12)

**Scenario.** `studies/toxoplasmosis_slice.yml` through `scripts/prelaunch.py --slice`: the fast tests (55), then the
study within twice its estimate, then `pegasus-core audit`. Rio Grande do Sul, 2014–2021; seeds B58, P37.1, TOXC and
"toxoplasm"; SINAN-TOXC, SIH-RD, SIM-DO and SIA-PA (its serology read from the extract); deep preset (every reader,
later years, persons, capture), one related code, `nulls: quick`, two link draws, SISAGUA's E. coli as the context, the
Santa Maria hypothesis. Run from `pegasus_project_dev` at d1dc655 (slice3), shared store; log
`pegasus_project/data/probes/slice3.log`.

**Why a slice.** Thirteen national deep runs (deep7–deep19, 2–3 h each) had been the debugging loop, each finding one
defect in an end-to-end path the unit-level tests never reached; the slice reaches every path in minutes. slice1 began
a second SIA-PA extract (2,746 files) and slice2 failed one item on a reader past the store; both were fixed with a test
before slice3.

**Ran.** 9.0 min against an estimate of 24.7 (scope 35 s, store 20 s); no step failed. 203 findings (24 signal, 73
system, 100 noise), 832 relation rows (208 with the context, over lags), cohorts 2019–2021 with nothing at q, capture of
cases reported without a total (links "use with caution": 41 children on both lists, 490 notified only, 336 admitted
only), of deaths not computed (SIH's toxoplasmosis admissions to SIM not viable in 2019–2021, chance pairs up to 51 %).

**Known answer.** The Santa Maria hypothesis (January–June 2018) is supported by SIA serology at the municipality of
testing: 29,237 tests against 20,834 expected, 1.40×, Holm p 2.9e-8. Discovery finds it unasked: a 2018 excess of
serology at the place of testing over Santa Maria and its region (25 municipalities, 1.40×, q 2e-8), triaged signal; the
congenital notifications cluster there in 2019–2021 (13.9×, signal). The other sources cannot test it: TOXC starts in
2019, SIH and SIM hold too few events, and serology by residence is 97 % unallocated.

**Audit.** Items 3, 5, 7, 8, 9 and 10 met; 1 partial for the sources the slice leaves out by design (TOXG, SINASC); 2 and
6 partial (ratios not declared; institutional findings none); 4 waiting on the screen (slice4).
