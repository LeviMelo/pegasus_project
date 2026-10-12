# The deep paths, first run end to end (2026-10-11)

**Scenario.** `studies/toxoplasmosis_smoke.yml`: the reference study cut by its declaration to congenital
toxoplasmosis's own records. Seeds P37.1 and TOXC; sources SINAN-TOXC, SIH-RD and SIM-DO; 2015–2023; depth deep;
code sets; questions excess and group; compositions only; one context (SISAGUA E. coli); the Santa Maria hypothesis.
Run worktree `pegasus_project_run` at 2ebc272; shared store and data root. Log
`pegasus_project/data/probes/study_toxo_smoke4.log`; folder `studies/toxoplasmosis_smoke` (2.3 MB).

**Ran.** 9 steps, 0 failed, 466 findings (signal 67, system 46, noise 311). Every deep path ran: later-year
replication, related codes (B58 found beside P37.1 and read in SIH and SIM), linked shares, persons, determinants with
contexts and the place-level map (28 field–context rows), 1,468 relation rows, the hypothesis.

**Known answer.** Linked persons, TOXC cohort 2021 → SIM death certificate. Cases whose SINAN outcome is death from
the disease (EVOLUCAO 2) have one 240 times as often as surviving cases (63–906, q 1e-13), and death from another
cause (3) 99 times. The two systems agree on who died.

**Cost.** 32.1 min against an estimate of 7.2 (scope 0.5, store 0.2, lanes 12.3, products 19.2). The estimate prices
no products phase: persons (national quality per scope, 10 draws × 3 years) and the relations. `_phase_record` now
carries the products overhead into the next estimate.

**Defects found by the four runs before it, all fixed:**
- an effect unit (km per month) the questions produce and `Lead` refused;
- triage on a fit loaded on demand (`_per_year` unset);
- a group answer without years failing replication;
- the place-level map on one field read twice;
- persons merged from every link of the year (now the study's own; seeded draws, identical persons, about 3× faster);
- a group answer shown with its place's totals (Santa Maria 2019: effect 0.0057 beside 118 observed, 20 expected).

**Left.**
- The hypothesis is not testable on TOXC (it starts in 2019), and SIH P37.1 gives no support. SIM-DOFET, the source
  that answers it, is read by the full study.
- The products phase prices nothing in advance.
