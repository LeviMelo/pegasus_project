# Persons, race, corroboration and the first dossier (S2–S5)

**Regime.** The S2–S5 commit; pegasus_data 0.1.0a1 (pegasus-core-fixes f9f1533); PegaSUS's data root; contiguity graph; 2026-10-08.

**The cohort scan (S2.1)** (`pegasus-core cohort SINASC-DN birth sim_infant_deaths_to_sinasc right 2021`, `data/probes/s2_1/`). The 2021 births (2,677,008) are persons. The outcome is an infant death linked to the birth. Every declared composition (23) is an attribute.
- **Cells.** Persons are collapsed to their covariate cells (attribute × age × sex × place: 292k cells). These are the Poisson likelihood's sufficient statistics. The estimates are identical to 8 decimals on synthetic data.
- **The fit.** It was rewritten three times in the run, each measured on synthetic data with identical estimates:
  - The place block of the Hessian is diagonal, so the Newton system is solved by a Schur complement on the fixed columns, and τ's trace has a closed form. The old fit needed a full sparse factorisation and a dense solve per place: 2.5 min per attribute.
  - The fixed design is dense (BLAS products): 2.0 → 1.0 s at 400k cells.
  - It stops on the Newton decrement, not the step. A level without events walks to −∞ by steps that never shrink: 450 Newton steps became 55, 52 s became 4.9 s.
- **The follow-up crosses the year.** A birth of December 2021 whose baby died in January 2022 is paired in run 2022, because the birth side is padded by a year. `gateway.side_pairs` reads every run whose scope holds a side's year (`covering_runs`). Reading one run had undercounted every cohort's late-year deaths.
- **The reading** (runs 2021 and 2022, 20 link draws by Rubin's rules, about 20 min; minimum effect RR 1.2): 123 contrasts over 23 attributes, 66 leads, 7 of them protective. Checked against what is known of infant mortality, not against the system's own assumptions:
  - gestation under 22 weeks RR 162, 22–27 weeks 146, 28–31 weeks 40, 32–36 weeks 5.4, against term;
  - a congenital anomaly 22.5; twins 4.5, triplets 11; breech 5.0;
  - no prenatal visit 6.7 against seven or more; Robson groups 6–10 11–13 against group 5;
  - induced labour 0.56;
  - the mother's schooling: none 1.88, twelve years or more 0.75, against 8–11;
  - indigenous 1.48 against *parda*; married 0.76.
  - Every "not recorded" level carries excess risk (1.4–7).
  - These are associations adjusted for age, sex, year and place, attribute by attribute; none is adjusted for the others.

**The linked share (S2.1).** For the 2021 births, `linked_counts` gives n = 2,677,008 and k = 23,638 expected linked (8.8 per 1,000; run 2021 alone). Σp(1−p) = 124, against a binomial variance of about 23,400. The linkage's own uncertainty is small at this scale and enters each cell's variance (`kv`).

**Race disparities (S3.2)** (`plans/s3_births_perinatal.yml`, `data/probes/s3_2/`). A place's race-j ratio over the reference race's is tested against Brazil's disparity.
- The conditional binomial's reading had left 10,396 open leads on births, of 22,280 place-race pairs tested. Places differ in disparity as they differ in every rate.
- With a beta-binomial whose concentration is set by central matching (the bulk sets the null, as N1's κ), 804 depart. Example: Tefé/AM, indigenous over white 28.6 against Brazil's 2.9.
- SIM chapter XVI (perinatal deaths, recorded race through the infants' confusion): 208 → 0.
- The earlier readings are retired.
- **The women's matrix, tested and not wired** (`gateway.CONFUSIONS`, one mechanism for every measured population). Declared-race ratios by inverting each matrix on the recorded deaths at its reach (2015–2023):
  - infants: *preta* 1.79, indigenous 2.63 against white, as infant mortality is known to run;
  - women of 15–49: *preta* 0.71, *amarela* 0.045, against crude recorded ratios of 1.01 and 0.80 (2022).
  - The cause: São Paulo's matrix records 9 % of the women declared *parda* as *preta* and 28 % as white. Applied to 26.8 million *parda* women, that inflow outweighs the *preta* women's own deaths. The matrix's declared axis is the mother's SINASC declaration; the account's race is the census's.
  - OPEN_QUESTIONS 10.

**Corroboration (S4.1)** (`data/probes/s4_1/corr_check.py`, its JSON; nothing written to the register). 42 SIM leads at X36 (landslides).
- Under one family (each lead's smallest source p × its sources tested, one BH over the leads), 7 are corroborated, all by the disasters field (S2iD's people harmed).
- The SIH source was untested in every year except 2021–2022, because `sih_deaths_to_sim` had no stored run. S2.2 computes the runs a plan reads.

**The first dossier (S5.1)** (`report.dossier`, `data/probes/s5_1/`). The 30 leads ranked highest are SIH chapter X answers. 26 are shares and institution steps at q at the floor. Read against the records (the place's chapter by code and year, the facility, procedure and ages of the window's events), the first eight are recodings at a sole provider:

| lead | window's events | what fell |
|---|---|---|
| Mundo Novo/GO 2012, J64 pneumoconiosis | 65, one facility, ages from 2 | J45 75 → 5, J18 71 → 11 |
| Manicoré/AM 2012, J85.2 lung abscess | 79, one facility, ages 1–9 | J12 294, 200 → 8 (the facility's code moves J12 → J85 → J40 → J06) |
| Carlinda/MT 2013, J66.8 | 11, one facility, ages 1–4 | — |
| Fortaleza dos Nogueiras/MA 2012, J85.0 | 30, one facility | J45 67 → 32 |
| Piên/PR 2014, J66.8 | 21, one facility, only that year | — |
| São João Batista/MA 2012, J80 ARDS | 108, ages 1–9 | J45 253 → 55, back to 128 |
| Igarapé Grande/MA 2015, J98.9 | 233, one facility | J18 215 → 72 |
| Tuntum/MA 2022, J06.8 | 216, one facility, as in 2021 | (the facility admits upper respiratory infections) |

All eight have the verdict *artefact*, by the agent, with the records cited.

Stage E had read the first seven as signals:
- A node that is its own outermost group had no siblings, so the substitution rule never ran. An outermost group's siblings are now the rest of its chapter.
- A sole provider is the place, so the facility rule cannot separate them.

The test that does separate them: **the events carry the age–sex profile of the codes they replaced, not their own code's.**
- `explain.recoded_profile` gives the likelihood ratio of the two profiles.
- Under the code's own profile, P(LR ≥ k) ≤ 1/k (Markov), so LR ≥ 1/FAC_P grades the substitution *tested*.
- A tested explanation now orders a lead after the open ones, in the register, the report and the dossier (`leads.reading_order`).
- Each dossier carries the codes table it was read from.

**The first re-triage** (`pegasus-core triage SIH-RD hospitalisation --stale`, `data/probes/s5_1/retriage_sih.log`; the rules of cc7a9fd).
- The profile test graded 507 SIH leads a tested substitution.
- It graded none of the dossier's seven, because it was asked only where the siblings had absorbed the change. They had not: Manicoré's siblings were 112 against 116, and Igarapé Grande's and Fortaleza dos Nogueiras' rose. A facility's whole volume swings from year to year, so its other codes need not fall against the median year.
- The profile test now stands alone. Under the code's own profile its error is bounded by Markov whatever the siblings did.
- The run re-triaged 43,168 leads, retired ones among them; it now reads only the leads not retired.

**The eight under the standing profile test** (`data/probes/s5_1/check8.py`, nothing written):

| lead | log10 LR (siblings' profile against the code's) | class |
|---|---|---|
| Mundo Novo J64 | 10.2 | tested substitution |
| Manicoré J85 | 24.5 | tested substitution |
| Carlinda J66.8 | 4.8 | tested substitution |
| São João Batista J80 | 73.3 | tested substitution |
| Igarapé Grande J98.9 | 50.5 | tested substitution |
| Tuntum J06.8 | 30.8 | tested substitution |
| Fortaleza dos Nogueiras J85.0 | 2.9 | signal (under 3) |
| Piên J66.8 | −2.0 | signal |

- Piên's 21 admissions are of adults aged 40–78: the profile of the code itself. The test contradicts my verdict *artefact*, which was premature. It is now *unknown*: occupational organic-dust disease in a farming town is a rival reading no record here excludes.
- Fortaleza dos Nogueiras stays *artefact* by the reading (lung gangrene in infants while asthma fell). The test, at 10^2.9, does not reach it.

**The ledger** held 93,272 part files: stage E wrote two per test.
- Merged into one in 196 s (`control.Ledger.compact`, now `update`'s last step).
- Stage E's tests are now registered and completed by batch: a node's leads in triage, a lead's sources in corroboration.

**Link runs (S2.2)** (`pegasus-core links plans/default.yml`, `data/probes/s2_2/`).
- `sih_deaths_to_sim` failed on every year before 2014. pegasus_data's role table asked for all of a role's additional columns (SIH's DIAGSEC1–9), which those years lack. Fixed in pegasus_data 9160d53: it asks only for the columns a year may carry.
- The same defect stopped `sinan_dengue_deaths_to_sim` on SIM's 2010 files, which lack SEMAGESTAC, a role's own column. pegasus_data 8afada1: a column the period lacks makes its role absent (nulls, named) instead of failing the table.
- Run times are about 5 min a year: 2014 gave 404,653 pairs, 2015 429,306.
- `sinan_dengue_deaths_to_sim` 2015 is **not viable**, by the engine's own test (972 deaths, 165,342 candidates; the date-shifted controls reach 39 % of the real pairs in the 23–26-bit bins).
  - It is not a defect of either side's keys: both are complete.
  - Without a birth date (SINAN lost it to the LGPD), death day, residence, sex and age do not single out a person in the large cities where 2015's deaths were.
  - Such a year stays unlinked, and corroboration names it untested, with the reason. S2.2's "no year unlinked" holds only where a link is viable.

**The profile test on local person-years, and the second dossier** (`data/probes/s5_1/retriage3.log`, `reports/dossier.html`).

The test against the code's *national* profile had a confound: a real outbreak in an old or a young town carries the town's ages, like its siblings. Both hypotheses are now rates on the place's own person-years.
- Tested recodings: 2,400 → 2,210 of the 17,890 SIH leads not retired; 3,025 explained in all.
- The re-triage ran in 9 min (45 before): batched ledger, stored facility cube.

The dossier's top 40 under the reading order:
- 5 cohort associations: *confirmed*, the known gradients.
- 17 institution steps that triage reads as capacity, and one share it reads as a system change (Capim Grosso/BA): *artefact*.
- 11 single-institution behaviours, tested: *artefact*.
- Six place signals, read against the records:
  - Massaranduba/PB 2012 *confirmed*: 83 tonsillectomies and adenoidectomies of children at one facility, a surgical drive. A departure of care, not of disease.
  - São Pedro da Água Branca/MA *artefact*: one facility's codes move year to year.
  - Juru/PB, Vitor Meireles/SC, Miguel Alves/PI, Igrapiúna/BA *unknown*: a coding habit or a real exposure or wave, which the records do not settle.
- The capacity and single-institution verdicts rest on stage E's reading, stated in each note; only the six place signals and the first eight were read against records.
- Every verdict carries its evidence. S5.1's condition, a dossier whose top leads have verdicts, is met.
- A re-triage that loaded the register at 09:25 wrote back, at 09:34, the verdict a person had changed at 09:25:57 (Piên's correction). The register now keeps a lead's newest verdict on record whatever state is written (`Register.add`), and reads one lead without parsing the rest: 8 s → 0.6 s.

**The first outcome-after-event field** (`plans/s2_infant_cohorts.yml`, 2010–2022; births followed by an infant death, every birth year read through the runs of that year and the next; `data/probes/s2_1/`).
- The plan computed its missing runs (2010 and 2011, 29,072 and 29,782 pairs) after a third pegasus_data fix (86aa7e4: a padded side's years are read one by one, SINASC 2009 lacking columns 2010 has). It fitted the births' block and the field, and asked its questions: 208 answers on the births' counts, 23 on the field.
- All 23 field answers are deficits (0.07–0.14 of expectation):
  - 20 are linkage holes: SIM recorded 79 deaths at age 0 at those places and years, and the link found 1.
  - 3 are places that recorded no infant death that year.
  - None is an excess. The field reads the link's completeness as much as mortality (OPEN_QUESTIONS 11).
- The field shared its id with the births' count field (`SINASC-DN:birth:*:*`). A field's id now names its reader, `dataset:event:classifier[reader]:node`.
- Triage reads only leads of its session's reader. SIH's 646 length-of-stay answers had been triaged on the count field's evidence, 47 of them *explained* by it. They are open and untriaged again: a measure's triage (`marks.triage_lead`) is not wired.

**S1.5, the fifth round** (`data/probes/s1_5/roraima.py`, declared in cc7a9fd before the run). The Venezuelan arrivals were scored in two systems at the municipality.
- Missed by every method: births at Boa Vista and at Pacaraima in 2018–2019, and SIH's delivery admissions at Boa Vista. The Macapá control is clean.
- The reason is measured. Boa Vista's births rose 27 % from 2017 to 2019 (7,043 → 8,936). The population series (POPSVS) already carried part of the arrivals: women of 15–49 rose 9.5 % (100,293 → 109,833).
- The rate rose 11–16 % (70.2 → 78.1 → 81.4 per 1,000 women, back to 72.1 in 2020): about 1,000 births above the rate's course over two years. That is under the count lenses' minimum relevant effect, a rate ratio of 1.2.
- A ratio threshold treats a capital's 1,000 extra births like a village's handful. Relevance stated as a ratio alone is a debt (ARCHITECTURE §13.2, the minimum relevant effect).

