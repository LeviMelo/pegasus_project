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
