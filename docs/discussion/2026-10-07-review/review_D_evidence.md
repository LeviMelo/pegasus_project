# Review D: evidence audit of pegasus_project (2026-10-04 to 2026-10-07)

Read-only. Sources: EVALUATION.md (49 files under docs/evaluation/, ~63 index rows), `git log --since=2026-10-04` (239 commits), STATUS.md register. Classes: (a) real data vs independently known answer; (b) real data, descriptive/model-checking (held-out calibration counts as b); (c) synthetic (planted/null worlds, surrogates, SBC); (d) engineering. Where an entry mixes classes, the primary one is given, then the secondary.

## 1. Classification of every evaluation entry (49)

| entry | class | what it established |
|---|---|---|
| 10-04 chapter-ix-first-fit | b | phi by ML (5.98 not 0.013); B0/B1/B2 calibration on SIM IX; first lenses/pairs read |
| 10-04 sinasc-lenses-optimiser | b (+c, d) | SINASC through the model; optimiser; change-point null; Sao Borja examined |
| 10-04 eb-census-positives | a | 12/12 signs of E_b vs census context recovered, only 2/12 admitted at delta 0.1 (power) |
| 10-04 race-bridge-infant | b | SINASC vs SIM race on 52,063 linked infant deaths: 63% agreement, direction reverses by region |
| 10-05 admission | c | power for planted RR over a region/window on thinned real fields; 1.5 not reached for 3 lenses |
| 10-05 artefact-aware-replication | b (+c) | 57 state claims re-audited: 22 survive, 15 open, 13 not replicated, 5 explained, 2 re-scoped; NB-world check of trend-vs-step |
| 10-05 bp-baseline-history | a | dengue 2019-23 vs 64 state-years with incidence >=300: level36 recall 0.91 / precision 0.64 (tuned on that same truth) |
| 10-05 bp-level | b | BP miss is place level + epidemic regime; held-out log score +9% (annual), +70% (dengue) |
| 10-05 brumadinho-declaration | a | declared test of J20-J22 admissions after the 2019 dam: FAIL (O 3, E 4.37); secondary places a post-hoc lead only |
| 10-05 census-coverage | a | raw 2022 Census undercounts (PES net 8.3%; ages 0-4 92.5% vs births); POPSVS = IBGE-corrected projection |
| 10-05 cnes-supply-pairs | a | declared first: Roemer's law recovered (rho +0.26); ESF vs infant mortality FAILS its sign; sanitation survives in 2/3 pairs |
| 10-05 dengue-monthly | a (+b) | counts equal TabNet in 8/10 files; epidemics recovered at BP (2015-16 29/37; 2019-23 59/64), not at B2s; phi 0.235 |
| 10-05 dependency-map | b (+c) | 65 fields, 2,059 pairs: SIH x SIH one hospital-use dimension; SIM XVI x Apgar recovered; no SIH x SIM/SINASC edge; delta calibrated on surrogates |
| 10-05 dispersion-by-region | b | B1 calibrated 18/28/30 of 33 fields (block / one phi_extra / by region) |
| 10-05 exposure-41 | b | UF x year residual follows log completeness (slope 2.3, CI 1.1-3.9), NLL -0.12% |
| 10-05 exposure | b | population-account-2/3/6 vs POPSVS: none beats POPSVS except account age 0 on chapter XVI; POPSVS stays default |
| 10-05 fit-throughput | d | warm start 36 -> 7 outers; cycling at SHRUNK boundary found |
| 10-05 harness-gate | c | false leads on NB surrogates <= q; MSR negatives; power per lens; only 3 lenses pass; spatial cluster fails |
| 10-05 institutions | b | facility-supply term removes 11% of facility class, 6.5% of signals; lattice finds 1,744 facility steps in 5,666 facilities |
| 10-05 laplace-uncertainty | d (+b) | CG draws 1,000 -> ~40 iterations; parameter uncertainty <=10% of overdispersion; BP IX KS 0.126 -> 0.056 |
| 10-05 lead-triage | b | 7,496 SIM leads: 4,045 system artefact, 2,015 signal, 746 substitution, 690 noise; 98.6% stay R0 |
| 10-05 lens-positives | a | round 1: COVID at BP recovered, 4/5 installed municipalities; round 2 declared first: UF-border trend 0/30, group disparity recall 0.05/0.003, marks no positive; earlier passes withdrawn |
| 10-05 mcp-tools | d | first MCP build exercised live; paused |
| 10-05 pairs-gate | c (+a) | MSR on normalised graph is the between-places null (size 0.047); delta_E 0.03/0.05; 5/12 sanitation/literacy/GDP pairs admitted |
| 10-05 positive-arbovirus-microcephaly | a | Q02 births 25x forecast in NE 2015-16, onset lag 6-7 months; E_w at immediate-region grain NOT recovered (rho 0.12 plateau) |
| 10-05 positive-chagas-schistosomiasis | a | B57/B65 deaths: B0 ratios put Ministry's endemic states first (Goias 5.6, Alagoas 7.7); Jaccard criterion fails, precision 1.0 |
| 10-05 positive-leptospirosis-rs | a | RS floods 2024: 18 municipalities, May-June, RR 63, 95.7% of excess captured; Jaccard as written fails |
| 10-05 replicated-claims-read | b | the 57 claims read against coding/completeness/denominator: 42 artefacts, 13 unresolved, 1 substantive (Y35 Goias) (later revised, see artefact-aware) |
| 10-05 replication | c | marginal test on held-out half is anti-conservative (0.28-1.00 of null cells "replicated"); conditional test 0.02-0.06; S2iD has Rio 2010 not Brumadinho |
| 10-05 replication-independent-units | c (+b) | later-years tier size <=0.014, power 0.9-1.0 / 0.05-0.18 if absorbed; real SIM register: 333 R1, none R2/R3, no signal corroborated |
| 10-05 rio-doce-declaration | a | declared test of J30-J31 admissions on 41 municipalities after Fundao: FAIL (O 1, E 35.9); the lead was a pre-rupture single-facility burst |
| 10-05 sih-full-readout | b | B1 calibrates in 17/19 chapters (B2 5/19); XV fails because dispersion does not fall with place size |
| 10-05 sih-readout | a (+b) | winter respiratory season recovered at B2s (Sul July peak, Jaccard 1.00 vs 0.56); calibration 6/7 chapters; chapter X: 22,628 leads, all R0 |
| 10-05 sim-survey-readout | b (+a) | 7,496 leads, 35% in ch. XVIII; top ten mostly artefacts; Brumadinho, dengue years, Fortaleza chikungunya found unprompted |
| 10-05 surveillance-lags | b | publication lags per system (SINAN 1 day, SIM/SINASC 9 wk, SIH 5 wk); revisions SIA +26%, DENG final -47% rows |
| 10-05 survey-throughput | d | SIM III survey 384 s -> 90 s (65 s on 4 threads), same 28 leads |
| 10-05 utilization | b (+c) | SIH place effects carry two factors (general use 33%, referral/specialty 17%); with them in Z 88/89 SIH x SIH edges drop, no SIH x SIM/SINASC edge |
| 10-05 y35-goias-declaration | a | declared competing predictions, scored against FBSP: both a real rise (FBSP 141 -> 631) and a coding catch-up (Y35/FBSP 0.01 -> 0.30); recode-as-main-account rejected |
| 10-06 absorption | c | refit absorbs 9-21% of a place-year, ~40% of a region-year, 45-63% of regional step/trend, all of a national year |
| 10-06 departure-models | c | cell excess beats outbreak lens on planted worlds; multiscale step's null worlds fail until empirical null per contrast |
| 10-06 factor-model-synthetic | c | EM factor analysis with ARD recovers K=3/3 and separates planted from null at regional supports; nothing at municipal grain |
| 10-06 icd-structure | b | sex/age admissibility, group geography: held-out gain per death (II -2.547 -> -2.383; XX -3.340 -> -3.230) |
| 10-06 minimum-effects | c | theta0 1.1 holds for 4 lenses on refitted model worlds; time-shift negatives fail for sparse SIM change point/space-time and SIH trends |
| 10-06 noise-structure | c (+b) | N1: NB with AR(1) copula, recovered on simulation; lognormal frailty rejected; estimator bound bug found on its own worlds (fixed 10-07) |
| 10-06 sbc | c | Laplace draws imply 4-10x observed deaths on sparse VII, and the sums fail on dense XIII; production (mode-centred) unaffected |
| 10-06 solver-v1 | d | exact Newton + strengths: IX cold 282 s -> 67 s, held-out deviance equal to v0 or better; sex-level defect found |
| 10-07 real-events | a | five documented events: before stage-B fix every method found Brumadinho only, yellow fever by two; after robust stage B all five found by three spike methods. States that no synthetic grid could show this |
| 10-07 relations-real | a (+b) | 65 fields: 128 relations (173 stand after withdrawing national band); cross-system positive controls found; permuted-SIH negative control 2.0% false above national scale |
| 10-07 robust-expectation | a | variants scored against yellow fever 2017-18 and ordinary-year tracking; v7 adopted |

Tally (primary class): a 16, b 17, c 11, d 5 = 49. By day: 10-04 4 (3 b, 1 a); 10-05 34 (a 13, b 12, c 5, d 4); 10-06 8 (c 6, d 1, b 1, a 0); 10-07 3 (all a).
Reading: 10-05 was the real-data day, 10-06 was the synthetic day (6 of 8 entries, zero real-data-known-answer entries), and 10-07 turned back to real events after `real-events` showed the synthetic grids could not see a stage-B defect. The 10-07 entry says so itself ("Every synthetic grid of 2026-10-06/07 drew its worlds from the model it tested").

Caveats on class (a): (i) several criteria were adjusted or failed as written (Jaccard criterion fails for leptospirosis, Chagas, SIH winter; two lens-positive passes were withdrawn after declaring positives beforehand). (ii) bp-baseline-history tunes level36 on the same 2019-23 dengue truth it is scored on. (iii) `real-events` after-fix runs were iterated several times (v9, v9b, v9c, v10, v11, v12) on the same five events, so a pass there is partly tuned to them; the entry states "no constant tuned to them" but variants were chosen by those events. (iv) census-coverage and the 2022 hold-out truth are official figures, the strongest (a) evidence in the set.

## 2. Effort split (239 commits)

Method: files per commit mapped to area; primary area = area with most code files touched (src/, scripts/, data/); commits with no code file = docs-only. Area map: A gateway/fields/config/graphs/store/exposure scripts; B monolith/solver/laplace/structures/surprise/prospective/bench/fit scripts/N1; C departures/multiscale/lenses/subset/maps/marks/control; D relations/pairs/utilization/gate_eb; E leads/replication/explain/corroborate/facility/questions plus event-test data scripts (rio_doce, brumadinho, y35, replicated claims, artefact_replication); F tools/cli/report/mcp/pipeline/surveillance/heavy.py; H harness.py/sbc/harness_gate/measure_admission/declare_positives. Caveat: most `data/` experiment scripts (o5_*, o6_*, o7_*, real_events*, noise_*, theta0_*, grid queues) are gitignored, so commit file lists undercount the synthetic and real-event scripts; I rely partly on subject lines and on which evaluation file a commit carries.

Primary area per day:

| day | A data | B expect/solver | C departures | D relations | E interp/triage/repl | F use/CLI | H harness/valid. | docs-only | total |
|---|---|---|---|---|---|---|---|---|---|
| 10-04 | 2 | 1 | 3 | 0 | 1 | 1 | 2 | 6 | 16 |
| 10-05 | 8 | 16 | 1 | 2 | 23 | 11 | 7 | 55 | 123 |
| 10-06 | 4 | 31 | 6 | 2 | 3 | 4 | 5 | 27 | 82 |
| 10-07 | 0 | 2 | 7 | 1 | 1 | 6 | 0 | 1 | 18 |
| all | 14 (6%) | 50 (21%) | 17 (7%) | 5 (2%) | 28 (12%) | 22 (9%) | 14 (6%) | 89 (37%) | 239 |

Commits touching an area at all (non-exclusive): B 72, F 53, E 46, C 38, H 30, A 27, D 17.
Of the 150 code-bearing commits: B 33%, E 19%, F 15%, C 11%, A 9%, H 9%, D 3%.
Reading: stage B (expectation/solver) is the largest sink (peak 10-06, 31 commits, the solver v1 rounds, ICD structure, interaction rank O2). Stage D (relations) is the smallest (5 primary commits) yet was declared the architecture's core aim (P16, six stages) and shows its first real map only on 10-07. Docs-only commits (89) are 37% of all commits, mostly STATUS/ARCHITECTURE/handoff/plan edits (STATUS.md 76, ARCHITECTURE.md 93, EVALUATION.md 60 touches), against a user rule "commit less often, docs must not outweigh code": the 10-05 count (55 docs-only of 123) is the clearest breach.

Share of commits touching synthetic harness/grid/SBC/null-world code or results:
- Mechanical (touches harness.py, sbc.py, harness_gate, measure_admission, admission_curves, planted/_sim scripts, or a synthetic-class evaluation file): 41/239 = 17%.
- Plus subject lines naming grid/SBC/surrogate/null worlds/negatives/power/planted: 60/239 = 25% (upper bound; includes false hits such as "negative-control status" in a real-data entry).
- Judgement list (primary content synthetic; 29 commits): 10-04: b98c623, 9393daf; 10-05: fa55690, 7d047ac, 4b51292, a253922, c9720d2, a44bd8e; 10-06: fdd0b7e, 337d526, a256d9e, 386411c, 140b590, e53a281, 21a6906, c12c01c, 8d42bf8, 23d4fda, ecdd473, 5e6c303, 010a481, 8faae4e, 39c535f, 55a193c; 10-07: a22a820, 87e10b3, fcbfd76, e22dec7, 4ec03b3. = 12% of all commits, 19% of code-bearing commits. By day: 10-04 2/16, 10-05 6/123 (5%), 10-06 16/82 (20%), 10-07 5/18 (28%).
- Best single estimate: roughly one commit in six to eight (12-17%) is primarily synthetic; one in four is touched by it. The cost is concentrated in 10-06/10-07 where it is 20-28% of commits. Pure `harness.py` file touches (27) overstate it: that module also holds declared real-data positives.

Related counts: heavy.py (machine job queue, 6 commits) and scripts/bench.py (12) are infrastructure; the "declared before testing" commits (about 12: Rio Doce, Brumadinho, Y35, CNES, lens positives, SINAN positives, microcephaly lag) are the project's discipline for real-data evidence and are a small share of effort.

## 3. What the project actually KNOWS about Brazil's health from real data

Honest framing: it mostly re-finds known events and mostly catalogues recording artefacts. Almost nothing is a new epidemiological discovery. Findings that depend on the real data, with entry:

Events recovered (all previously known; method validation, not discovery):
- Brumadinho dam 2019, 7.4-13.4x in the town: found unprompted in the survey and by 3 methods (sim-survey-readout; real-events).
- Dengue epidemic state-years: 2015-16 (29/37) and 2019-23 (59/64, precision 0.57-0.64) at BP (dengue-monthly; bp-baseline-history). Fortaleza chikungunya and COVID certified as viral pneumonia J12 (RR 7.3, 28 places, 2020-21, J18 falling) in sim-survey-readout.
- Leptospirosis, RS floods 2024: 18 municipalities, May-June, RR 63 (positive-leptospirosis-rs).
- Chagas/schistosomiasis: Ministry's endemic states ranked first on deaths (positive-chagas-schistosomiasis).
- Microcephaly Q02 25x its forecast in the Northeast 2015-16, 6-7 months after the arbovirus peak (positive-arbovirus-microcephaly): a reading of curves, the formal lagged test failed at immediate-region grain.
- Winter respiratory season, Sul July peak (sih-readout).
- COVID-19 as a change point at BP (lens-positives).
- Yellow fever 2017-18, measles 2018-19, chikungunya 2016-17, Brumadinho, COVID North: all five found only after robust stage B (real-events, robust-expectation).

Relations found:
- Roemer's law: SIH admissions with SUS beds, E_b rho +0.264 / +0.252 given Z (cnes-supply-pairs).
- Cross-system relations (dengue, HIV, pneumonia, COPD deaths with admissions; congenital syphilis with syphilis admissions), calibrated above the national scale (2.0% false under permutation) (relations-real).
- Sanitation survives primary-care adjustment in 2 of 3 declared pairs; 5 of 12 sanitation/literacy/GDP pairs admitted (cnes-supply-pairs; pairs-gate).
- SIM XVI x Apgar recovered in the dependency map (dependency-map).
- SIH is essentially one hospital-use dimension plus a referral/specialty axis, unrelated to mortality or births at place level (dependency-map; utilization).

Declared tests that failed (negative real findings):
- Rio Doce/Fundao J30-J31 admissions: no excess (O 1 vs E 35.9); the earlier lead was a single pre-rupture facility (rio-doce-declaration).
- Brumadinho J20-J22 admissions: O 3 vs E 4.37 (brumadinho-declaration).
- ESF coverage with infant mortality: wrong sign (cnes-supply-pairs).
- Homicide trend divergence across UF borders: 0 of 30; group disparity weighted recall 0.048/0.003; marks: no citable positive (lens-positives).
- Immediate-region lagged dengue to microcephaly (positive-arbovirus-microcephaly); SIM I x sanitation edge (dependency-map).
- The facility-supply term explains none of the 15 unexplained SIM leads (cnes-supply-pairs).

Artefacts identified (the largest body of real-data knowledge):
- SIM: 35% of all leads and 68% of trend leads sit in chapter XVIII (certification); São Paulo X59 is mostly the elderly; young deaths go to unspecified R99 via the death-verification service (sim-survey-readout).
- Of 7,496 SIM leads, 4,045 are system artefacts, 746 substitution; 42 of 57 replicated state trends were first called artefacts (21 composition inside an ICD family, 9 R-chapter, 8 national-course misfits, 4 one-year steps), later revised to 22 survive / 15 open / 13 not replicated / 5 explained (replicated-claims-read; artefact-aware-replication; lead-triage).
- SIH: a third of chapter X signal (3,219 of 9,469) is facility behaviour, 77% volume steps (CNES opening/closing/recoding); J31 Rio Doce 2015 is one CNES facility with 398 of Brazil's 544 (lead-triage; institutions).
- Y35 legal-intervention deaths in Goias: a real rise (FBSP 141 to 631) plus a coding catch-up (Y35/FBSP 0.01 to 0.30); recode rejected as the main account. This is the one substantive health finding that survived scrutiny (y35-goias-declaration).
- Race: SINASC and SIM agree on 63% (69% non-blank) of 52,063 linked infants, direction reversing by region (race-bridge-infant).
- Denominators: raw 2022 Census undercounts (PES net 8.3%, ages 0-4 at 92.5% against births); POPSVS is IBGE's corrected projection; the DATASUS-derived population account does not beat POPSVS (census-coverage; exposure).
- Completeness: UF x year SIM residual follows log completeness, concentrated in North/Northeast (exposure-41).
- Surveillance timing: preliminary data lag 1 day (SINAN) to 9 weeks (SIM/SINASC); revisions of +26% (SIA) and -47% rows (DENG final) (surveillance-lags).
- Model-validity facts: chapter I's single dispersion (phi about 0.1) and per-category levels fitted with their epidemic years hid yellow fever, measles, chikungunya and COVID North (real-events); SIH chapter XV's dispersion does not fall with place size (sih-full-readout); SIH time-shift negatives always produce trend findings (minimum-effects); Laplace draws imply 4-10x observed deaths on sparse chapters (sbc).

Bottom line: the evidence base is solid about the data's recording behaviour and about whether the pipeline can rediscover documented events (it can, after stage B was repaired on 10-07). It holds no new claim about disease burden, causation or health-system performance in Brazil beyond the Y35 Goias reading and confirmations of known relations. No relation has been interpreted (relations-real: "none is yet interpreted"), and of the 7,496 SIM leads none is R2/R3 and no SIM signal is corroborated (replication-independent-units; only J09 Rio Brilhante of the top 15 is R1).
