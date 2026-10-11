# The topic's medicines (2026-10-11)

**Regime.** PegaSUS on branch `scope-v2`, pegasus_data on branch `perf2`, data root `pegasus_core_data` (SNGPC
industrialised sales 2019–2021 in the lake). Drivers are inline commands in the session.

**What was missing.** Acceptance item 1 asks for "BNAFAR/SNGPC for those medicines", but nothing tied the topic to a
medicine. The concept index finds none from records. Of 16,563,831 SIA AM authorisations (2025), none carries B58,
O98.6 or P37.1. SNGPC's ICD-10 field is filled on 0.39 % of 2021's lines, and once with B58.

**The declaration.** pegasus_data's `curation/treatments.yml` records the medicines an official document gives for a
condition, and `pg.treatments` and the concept index return them. For toxoplasmosis the document is Nota Técnica
163/2018-CGAFME/DAF/SCTIE/MS, item 6:
- spiramycin before the 30th week;
- pyrimethamine, sulfadiazine and folinic acid after it.

Each substance names the declared fields that count it, with an exact row filter and its denominator. PegaSUS's scope
lists them under `medicines`. Their reads become rated context entries (`study._medicines`) that the relation layers
and context profiles use.

**Read on the records.** Data by substance:

| substance | SNGPC 2021 sale lines | BNAFAR stock |
|---|---|---|
| spiramycin | 7,438 (boxes) | yes (2025-03 on) |
| oral sulfadiazine | 291 | yes |
| pyrimethamine | 8 | yes |
| silver sulfadiazine (burn cream) | 218,715 | — |

Silver sulfadiazine is kept out by the exact name. National spiramycin sales were 30,502 boxes in 2019, 29,419 in 2020
and 24,633 in 2021. The Ministry buys these medicines and the states dispense them (RENAME 2017's strategic
component), so retail sees little of them.

**Two defects found.**
- A filtered context left a municipality with no matching rows unknown. Spiramycin's mean per resident was taken over
  the 2,097 places that sold any; the field holds 5,152 that year, 3,055 of which sold none. Those are now 0, and the
  mean fell 4.5-fold, from 5.9e-4 to 1.3e-4. A place the field has no rows for stays unknown.
- Two strata of one field took one name in the field map (`ctx:<field>`), and the map's matrices lost a row
  (IndexError). They are now named by `gateway.context_name`.

A series no longer counts declared years the lake holds nothing of: SNGPC is declared for 2014–2026 and built for
2019–2021.

**Result.** TOXG's place effects 2019–2025 against the three retail rates 2019–2021 (`dependency.field_map`, Moran
null):

| medicine | ρ | n_eff | p | admitted |
|---|---|---|---|---|
| spiramycin | −0.009 | 2,289 | 0.84 | no |
| pyrimethamine | −0.074 | 596 | 0.14 | no |
| sulfadiazine | −0.024 | 1,221 | 0.58 | no |

Retail sales do not follow the notifications, as the dispensing route predicts. BNAFAR's stock, the SUS route, is a
snapshot from 2025-03 on and is not yet read as a series.
