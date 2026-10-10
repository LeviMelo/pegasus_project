# Weighted events, and absent ages counted as 80+ (2026-10-09)

**Regime.** Branch `design-v0`, with pegasus_data at d8ece14 (its decision 0155). The local data home was used. The SIA trial ran
`gateway.event_counts` and `monthly_counts` for 2023 on AC 2023-01 only: `pg.query` and `count_events` were patched to
that partition and the store was stubbed, so no partial result was cached under a national key. The script is
`try_weight.py`, kept in the session scratchpad and not shipped.

**Absent ages were counted as 80+.** The gateway capped age as `least(floor(TRY_CAST(age)), 80)`. DuckDB's `least()`
skips NULLs, so `least(NULL, 80)` is 80 (DuckDB 1.5.5). From e065bd1 (2026-10-04) on, every event whose age stratum
was empty or unparsable was counted at 80+ instead of being unallocated as `age`.
- SIM.DO 2022: 2,337 such deaths, against 495,283 deaths at 80+, a 0.47% inflation of that band.
- SINASC.DN 2022: 26 births (mothers' ages).
- SIA BI AC 2023-01: 1,490 procedures, TPIDADEPAC 9.

`_age_sql` now keeps an absent age absent. It also nulls the codes the age stratum's roles declare missing, such as
PA_IDADE 998 and 999, which would otherwise be capped at 80.

`event_counts` and `linked_counts` were keyed by code, so they re-key themselves. `monthly_counts`, `mark_moments`,
`composition_counts`, `away_counts`, `code_list_counts` and `delay_counts` were not, and now are (ARCHITECTURE §11.3):
their stored results recompute on next use.

**Weighted events (pegasus_data decision 0155).** `_records` attaches a weighted event's weight, and every event count sums
it (`wt`). SIA PA 2023-01 in AC:
- `event_counts` and `monthly_counts` allocate 146,228 procedures and leave 1,046,221 unallocated by municipality
  (the consolidated BPA records none);
- the sum is pegasus_data's 1,192,449.
- BI allocates 79,876 and leaves 1,490 unallocated by age.
- `mark_moments` refuses PA ("a mark's moments is per record"), and so do linked counts.

`_when` accepts the property `competence` (SIA's month of care), and `_date_sql` reads YYYYMM as the month's first
day.

Not run: a national SIA year. PA is about a billion approved procedures in some 400 million rows a year, a
multi-hour read.

**S1.6, relevance as burden (ADR-0031).** `data/probes/s1_5/roraima.py`, re-run with the burden floor, writes
`roraima_burden.json` and `.log`; the fits are the stored ones (SINASC-DN `*`, SIH-RD XV), re-assembled once after the
age fix. Boa Vista is still missed by every method, and so are Pacaraima and the delivery admissions; the Macapá
control is clean. Read on the B1 cells (field mean 507 births a cell):
- 2018: 8,163 observed, 7,813 expected, ratio 1.045, floor 1.0065, relevance p 0.27.
- 2019: 8,936 observed, 7,956 expected, ratio 1.123, floor 1.0064, relevance p 0.035.

Relevance no longer stops it. The excess is 1.9 noise sd (place-year noise 6.3 % of the cell), and 3,460 of 77,980
cells have z ≥ 1.92. The expectation already carries half the arrivals: POPSVS's population rose, and B1's course
followed.

**S2.4(d)(e), persons' quality and completeness through any route.**
- `gateway.person_quality(year)` gives each person link's edges, refusals and triangles (pegasus_data
  `entities.triangles`). The cohort reading logs it, and each cohort lead carries it in its provenance. 2021: SIH
  deaths 1,826/1,826 routed pairs agree; maternal deaths 1,826/1,829.
- `link_sensitivity` counts an infant death found through any route of the scope's persons (pegasus_data
  `side_counts(persons=)`). In 2021 this adds nothing yet (25,592.5 of 31,674): the newborn-admission runs, the
  other route, are being computed (`pegasus-core links plans/s2_infant_cohorts.yml`, from 2026-10-09).

**The location rounds under the amendment** (`data/probes/s1_5/locations_burden.py`, `.json`, `.log`; SINASC's and
SIM's stored share and mark fits). First pass, with the burden shift: São Paulo's caesarean law matched by the excess
at one municipality (Sagres, effect 0.108, p 2.4·10⁻⁵; Murutinga do Sul 0.131), and the other four rounds missed. Second
pass, with the event criterion amended (ADR-0031 amendment): all five missed, the Fundão birth-weight control clean.
The criterion's change applies to every positive; the earlier rounds are re-read after S6.0.

**Noise by size (OPEN_QUESTIONS 12, ADR-0032).** `data/probes/dispersion_by_size.py`, `nbp_test.py`, `nbp_check.py`
(births `*` and SIM IX, B1, 2010–2023, stored fits). Excess relative variance by μ decile against the assumed 1/φ:
births 0.016 → 0.0027 against 0.0037 flat; SIM IX about 0.02 → 0.009 against 0.010–0.014. Fitted alone on the cells, NB-P
beats NB2 by 1,413 nats (births, P 1.58) and 305 (IX, P 1.69).

Through the surprise's own path (the old values read from the cache under the old code):
- births: not calibrated, KS by quintile 0.029, 0.032, 0.028, 0.029, 0.057 → calibrated, 0.020, 0.020, 0.016, 0.024,
  0.018 (P 1.626);
- IX: 0.011, 0.026, 0.041, 0.048, 0.089 → 0.012, 0.026, 0.041, 0.048, 0.085 (P 1.672).

Roraima re-scored under it (`roraima_nbp.json`): still missed. Boa Vista 2019 z 1.92 → 2.83, 860th of 77,980 cells.

**S2.4 done: the 2021 birth cohort through persons, with two outcomes.** `pegasus-core cohort SINASC-DN birth baby 2021
--outcome SIM-DO:deceased --outcome SIH-RD:patient --draws 10` (`data/probes/s2_4_cohort_2021.log`). It read
2,677,101 births over the persons of the scopes 2021 and 2022, after `pegasus-core links` stored the newborn-admission
runs 2014–2022 (42,373 to 67,625 pairs a year, about 14 minutes each).

- **Per draw:** 26,114–26,164 babies with an infant death and 73,173–73,252 with a newborn admission.
- **Contrasts:** 262 over 24 attributes, with the known gradients on both outcomes: gestation under 22 weeks RR 162
  for death; prenatal visits; anomalies 22.5; plurality 4.5; Robson groups 10–14; mother's schooling 0.44–0.52 for
  admission.
- **What the persons rest on** (logged per scope, carried by each lead):

  | scope | link | edges kept | refused | agreement with other routes |
  |---|---|---|---|---|
  | 2021 | newborn admissions | 62,218 | 63 | 2,692 / 2,770 (97.2 %) |
  | 2021 | infant deaths | 25,195 | 14 | 2,692 / 2,770 (97.2 %) |
  | 2021 | SIH deaths | 700,193 | 1 | 4,518 / 4,523 |
  | 2022 | newborn admissions | 65,697 | 68 | 2,715 / 2,809 |
  | 2022 | infant deaths | 25,211 | 22 | 2,715 / 2,809 |

- **Completeness through any route:** 2021's infant deaths paired 25,766.5 of 31,674, against 25,592.5 for the
  direct link. 174 deaths are found only through an admission and its certificate.
- **Not viable nationally, so persons skip it:** the women's-death link, padded four years back (12,961,822 mothers
  in 2012), matches by chance at 92 %, as the race bridge found outside municipalities under 2,000 mothers.
- **Running:** the CIHA links, which failed on a name resolution fixed in pegasus_data f8c4a88.


**OQ 13: SIM IX's large places above their expectation, and the robust refit (ADR-0033).** Probes:
`data/probes/recoding_pool.py`, with logs `recoding_pool_block.log` and `recoding_pool_v11.log`. Readings are on SIM IX
2010–2023 under B1, with O/E taken over 2010–2019 by quantile of place size.
- **The baseline (v9).** O/E is 0.998 below the median and 1.028 at the 90th–99th percentiles, 1.018 overall. The PIT
  KS by size quintile runs from 0.012 to 0.085.
- **The cause: recodings flagged and removed.**
  - The robust refit flagged persistent recodings and imputed them away: Fortaleza's I10 at about 5× its expectation
    every year, Belo Horizonte's I11, Brasília's I51, and I42 in Nova Iguaçu and Duque de Caxias.
  - The same place's other leaves showed the matching deficit for 55 % of the top decile's flagged excess, against
    21 % below the median.
- **Moving the excess back to the deficits (v10, v11).** With the leaf's group as the pool:
  - IX calibrates: KS 0.006–0.055, whole O/E 1.010.
  - With the block as the pool, KS is 0.007–0.018 and whole O/E 1.001, so the block was kept.
  - O/E still runs from 0.979 below the median to 1.010 in the top 1 %, inside the noise, and OQ 13 stays open on it.

**Gateway keys carried pegasus_data's package version, not its declarations.** A change to SDTA's grid rule left
`event_counts` serving the old counts: the key held `config.data_version()`, the package version, which no curation
or code edit changes.
- Every gateway artefact read from events (11 keys) now adds `_declared_key`: a hash of the event type's declaration,
  the strata, the roles of the columns that make rows events, and pegasus_data's `semantics/event_types.py`.
- Re-read, SDTA 2023 counts 19,879 people (pegasus_data evaluation 2026-10-09-outbreak-grid-and-fill).

**The gamma quantile at small shapes returned NaN.** `surprise.gamma_quantile_at_normal`, at shape 0.005, returned
NaN for 7,918 of 2,000,000 normals, all with ε between −1.97 and −1.90. There the quantile, (p·Γ(a+1))^(1/a), falls
below the smallest double (about e^−710), and the Halley steps on log x fail instead of returning 0.
- **Where it surfaced.** SINAN-SDTA's people-count field (φ 0.066) drew NaN frailties into the cluster scan's CUDA
  Poisson draws, and the scan's assertions fired.
- **The fix.** The quantile is now 0 wherever the lower-tail term underflows, and any other non-finite value raises.
- **The check.** The frailty's mean is 0.999, 1.004 and 1.017 at shapes 0.066, 0.005 and 0.001; 1 is right.

**SINAN-SDTA through `update` (`plans/s6_sinan_sdta.yml`, 2015–2023, log `data/probes/s6_sinan_sdta.log`).**
- **The fit.** It converges with φ 0.066 and P 1.67. The robust refit flags nothing.
- **What the questions find.** Excess, step, trend, cluster and divergence find nothing. *Corrected the same day:* that
  cluster scan drew NaN frailties (the gamma quantile below), and rerun with the fix it finds 180, 165 of them
  persistent levels. The group question finds 15
  disparities, single-year spikes in one band and sex at Araguari, Carpina, Osasco and others: one outbreak in one age
  group. Triage reads them as noise.
- **What this measures.** People counted in clusters are read at a noise that hides departures (OPEN_QUESTIONS 14).
- **The grid's lens loop.** It skips a lens the field cannot take when the lens raises LookupError, as it already did
  for ValueError: births have no classifier, so no facility cube. The B3 grid had stopped on that.

**The grid never scored the two divergence methods.** The grid passed each method's name to `scan` as a lens.
`divergence_neighbours` and `divergence_national` both run `trend_divergence` with their own settings, so both raised
KeyError, which the grid logged as a lens the field cannot take.
- The grid now runs each method's own lens with its settings, as `questions.py` does, and records rows by method.
- A KeyError is raised, never read as "lens does not apply".
- Both methods run through `scan` on SDTA's ill. `scripts/throughput.py` reads a stamped `update` log into seconds
  per question and fit (S0.8): SDTA's ill take 281 s a field.

**SDTA's outbreaks as the unit (ADR-0034).** Worktree `group-events`, with pegasus_data's branch of the same name; log
`data/probes/s6_sinan_sdta_groups.log`.
- **The outbreak field.** One exposed cell holds the place's whole population (Brazil 2019: 207.9 M). It fits with
  φ 1.045 and P 2.0; the robust refit raises φ to 1.44 and flags 42 place-periods (446 outbreaks against 21 expected).
- **What it finds.** Excess finds 30 (the ill: 0), cluster 172 (162 persistent levels), divergence 1; group finds none,
  having no degrees of freedom.
- **The counts.** 771 outbreaks in 2019 and 1,161 in 2023 (one with no municipality), each in sex 1, band 0.


**One notifying unit behind a state's outbreaks.** SDTA's largest outbreak lead, Maranhão 2023 (217 municipalities,
ratio 56), is 37 outbreaks in 4 places, against 1–2 a year before. 32 of them were notified by one unit, CNES 9005064
in municipality 210340.
- **Why triage missed it.** It had skipped the facility read for every field with no classifier ("no facility
  classifier"). The facility cube now reads such fields at the code `*`.
- **What the read can and cannot say.** It records the concentration, but its mechanism tests compare a code's share
  within its block, and a single-code field has no mix. So it cannot tell one notifier's surge from a real wave
  handled by one unit. The concentration stays evidence, not a verdict.
- **What it was (the same day).** Neither: the 32 rows are one outbreak of 32 ill entered again and again. 19 are
  identical but for entry metadata, and 13 differ in a fact (onset 23 or 25 March). pegasus_data's decision 0159 keeps
  one of the identical rows; the near-copies stay, which copy is right being unknown.

**Raw reads in PegaSUS's data root decode the DBC files again in every process.** One CIHA state-month (SP 2013-06,
689,806 records) takes 30.6 s in a new process, 22.4 s in another and 6.8 s within the same one.
- **What this costs.** A link year reads 324 such files and takes 33–70 min.
- **What was started.** A CIHA lake, 2015–2022 without labels, is being built into `pegasus_core_data`. An SIH-RD lake,
  2010–2023, follows it: the S6.0 SIH survey re-reads every year after today's key changes.

**A column was read over years it did not fill.** `update` offered every modelled measure, composition and interval
over the plan's years, whatever the column's own span. A later form's column read as a collapse before it existed:
dengue's 2014 warning signs on a 2010–2023 plan, SIH's VAL_SH_FED and VAL_UCI, SINASC's DTDECLARAC interval.
- `update._declared` now reads a column only where it fills every year of the plan: its span, less pegasus_data's
  `unfilled:` years.
- It names every column it leaves ("not read: filled 2014-2026 only").
- Dengue on 2010–2023 keeps 33 compositions and leaves 43 from its 2014 form, which a plan on their years reads.
- `fields.declared` gives a column empty in some of the readings' years its reason.

**S1.5's fifth round under ADR-0033 (births only).** `data/probes/s1_5/roraima_births.py`, result in
`roraima_births_v11.json`. Every method was rerun on the births field (B1, NB-P, the robust v11 expectation).
- **Boa Vista and Pacaraima 2018–2019.** Still missed by cell excess (482 findings in the field), excess (100),
  outbreak (65) and space–time (3).
- **The control.** The Macapá negative control stays clean.
- **Why.** Boa Vista's 11–16 % rise, about 1,000 births a year, stands at about 3 noise sd. The false-discovery family
  of 77,980 place-years asks for more. Relevance no longer stops it (ADR-0031); the family's size does
  (OPEN_QUESTIONS 15).
- **Still to score.** The delivery-admission declaration waits for the SIH lake.

**OQ 15: the outbreak lens's weights, and what a capital's excess needs.** Probe `data/probes/oq15_weights.py`, on births
B1.
- **The weight.** Boa Vista's 2019 cell (8,936 births against 7,956 expected, p 3.9e-3) had a Roeder–Wasserman weight of
  0.0005 at the one reference effect of 1.5×: at 1.5× the cell is a sure detection.
- **The change.** The weights are now averaged over nine reference effects, log-uniform from 1.05 to 2×. They average
  1, so the weighted BH keeps FDR ≤ q, and Boa Vista's weight is 1.0.
- **The field's rejections.** 81 unweighted, 65 at 1.5×, 75 averaged.
- **What it does not change.** Boa Vista is still missed: BH's threshold over 77,980 place-years is about 5e-5 (OPEN_QUESTIONS 15).

**A positive's reach.** `harness.locus_reach` tests the locus itself as one aggregate (its places and years, NB variance).
`event_record` reports it beside every method's verdict, so a miss that a family could reach (a method's defect) is told
from one beyond any search.
- **Roraima's births, 2018–2019.**
  - Boa Vista: 17,099 births against 15,768 expected, z 2.82, p 2.4e-3. It clears q alone, not the q/m of a family of
    77,980 cells.
  - Pacaraima: z 0.77; the B1 expectation took its rise. It clears neither.
  - The Macapá control: z −1.29.
- **What this means for S1.5.** Both positives were beyond reach; the next declarations are chosen with their reach
  computed first.
