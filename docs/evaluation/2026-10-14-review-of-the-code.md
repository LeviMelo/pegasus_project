# The whole code reviewed for meaning and wall clock, from a one-state study (2026-10-14)

**Scenario.** "Perfil epidemiológico da mortalidade por infarto em Alagoas" (`studies/infarto_alagoas.yml`: SIM-DO and
SIH-RD, I21–I22, Alagoas, 2014–2023, depth `deep`) took 27 minutes warm and was priced at 83. It was profiled
(cProfile of the scope and the products, the run's own step seconds), and every module of pegasus_data and PegaSUS was
reviewed by area for wrong numbers and wasted time (findings under `data/handoffs/review-*.md`, local).

**Where the 27 minutes went** (warm run, b7ce933 + side filters): scope 10 s (329 s before fd8f4a8), store 3 s, lanes
873 s, of which one linked share 799 s (SIH's national linked counts built for ten years to keep Alagoas's ~800
infarction admissions), products 705 s (compositions 384 s over 268 lake queries of ~0.65 s fixed cost; labels 144 s,
one rebuild per finding; race rates 90 s; maps 142 s cold, Brazil drawn for one state). The estimate's 83 minutes
counted the replicate pass twice and priced linked shares as national items.

**Measured effects of the fixes** (same machine, same data root):
| what | before | after |
| --- | --- | --- |
| scope of the one-state study | 329 s | 10 s |
| SIH 2019 linked counts, one state and a code set | 38.4 s | 3.9 s (same 785 admissions, 98.2 linked) |
| SIH 2019 event counts by residence, diagnosis, sex, age | 62.7 s | 7.4 s (same rows) |
| composition reads of the products | 268 lake queries | 70 |
| per-row lookups on the population tensor | 40 s | vectorised |
| group share intervals (138,612 calls) | 113 s | one call per level-year |

**Wrong numbers found and fixed** (c449198, af8491f, dd10767; pegasus_data 15c1cf7):
- **Area reads.** The Federal District's administrative-region codes (SIH to 2017) were dropped by a prefix filter:
  530010 kept 11,025 of 151,901 admissions of 2017; records without a residence vanished from an area's reads (CIHA
  2019: 13.4 %), now said as Brazil's; Brazil's lost events had been reported as the area's.
- **Places.** The death-verification service and the registry office were read as places of death (354 answers on
  one field): only `where` places are supports, and SINAN's infection and hospital places are `where` in every form.
- **A second coding** of the topic's deaths (CAUSABAS_O) had been asked every question again.
- **Dispersion.** The prospective tier re-estimated its dispersion on unfitted parameters (variance 3.1× the fit's); the
  robust φ was estimated on fractional imputations (Alagoas infarction deaths: 21.1 → 31.3, not 54 → 68); a φ on its
  Poisson bound is its lower 95 % profile limit (2014–2020: ∞ → 12.3).
- **Calibration** at a fixed KS 0.03 failed a calibrated one-state field 32 % of the time; now max(0.03, 1.63/√n).
- **Keys.** Fits and blocks did not see pegasus_data's declarations or their own code; a stale lane could store old code's
  artefacts under the new code's key (now refused, `config.StaleCode`).
- **Cross-field error control** ran on the survivors of each field: 300 null fields admitted a false answer in 99.3 % of
  repetitions; on the fields asked, 1.5 % (nominal 5 %) (90ff9c5). Scan clusters are connected sets (90ff9c5).

- **Rates and trends of the profile.** The standardised rate's standard was the area's own pooled population (the
  codebook said national): it is now Brazil's 2010 population by sex and age band, named, with Fay & Feuer's interval,
  beside rates by sex and by age band. The trend was a crude APC with a normal interval: Alagoas's infarction deaths
  2014-2023 read +4.1 %/year [2.0, 6.3] crude and +1.35 % [-0.7, 3.5] age-sex adjusted (t interval): most of the rise is
  the population's ageing. Standardised 36.9 (2014) and 46.1 (2023) per 100,000; men 62.3, women 46.2 (2023).
- **Keys of the study.** Five study tables and the readers' question and prospective steps were keyed without the
  area or the reader: one area's tables could be served to another, and a second code set skipped its supports
  ("done on these versions"); a later item's later-years pass erased an earlier item's verdicts; the declared q never
  reached the question passes.

**Known answers held:** Alagoas's infarction deaths by year equal the lake's direct count (1,573 in 2019, the same
through the area-filtered readers and the national ones); SIM, SINAN-TOXC and SIH national event counts identical
before and after pegasus_data's event-reading rewrite (1,349,801; 4,583; 12,181,726 in 2019).

**Open.** Fixers' branches of pegasus_data (query path, semantics, linkage and populations, ingest) are merged only after
their central claims are re-measured; the linkage review found the probabilistic placebo cannot reach the date blocks and
verdicts taken from non-held-out validations, so stored runs' "viable" verdicts are upper bounds until re-judged. The
study's cold wall clock after every fix is measured once the branches are in.

**Regime.** PegaSUS scope-v2 at c449198–ebc9dd1 and the commit of this entry; pegasus_data pegasus-core-fixes at 15c1cf7; data root
`C:/Users/Galaxy/pegasus_core_data`; 2026-10-13/14.
