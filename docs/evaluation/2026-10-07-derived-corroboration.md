# Corroboration from declared sources, on documented disasters (2026-10-07)

**What.** `corroborate.sources` replaces the hand-written `RULES`: every other served ICD-10-coded event type, less its
records linked to the lead's system by a declared link, and pegasus_data's disasters field through its declared ICD-10
correspondence and harm columns. Run on the register's 77 SIM leads at X36 (landslides) and A92 (chikungunya) that
stage E had read as signals; nothing written to the register (scratch `corr_live.py`, pegasus_core at a2968c5 plus this
change, data home `pegasus_data_home`).

**Why it matters.** A one-off disaster cannot recur in later years; corroboration is its only independent confirmation.
Before this change no landslide lead was corroborated, Brumadinho, Petrópolis and the 2011 Serrana included.

| X36 leads (31) | before | places with a registered event | people the registry reports harmed |
|---|---|---|---|
| corroborated (BH within source) | 0 | 0 | 13 |

- **The correspondence was wrong, the data said so.** S2iD types an event by its trigger: Petrópolis 2022, Recife and
  Jaboatão 2022, São Sebastião 2023 as Chuvas Intensas; Petrópolis, Nova Friburgo, Teresópolis 2011 as Enxurradas.
  X36 now takes the triggers (pegasus_data `fields.yml`).
- **Presence of an event does not discriminate**: rain is registered statewide (Recife 2022 p 0.58). The registry's
  reported harm does: 2 % of events report a death; Serrana 2011 3,084 harmed (q 0.026), São Sebastião 2023 57
  (q 0.030), Rio 2010 107 (q 0.043), Santa Catarina 2020 57 (q 0.008). Recife 2022 (115, q 0.08) and Niterói 2010
  alone (q 0.09) fall short of BH.
- **Brumadinho 2019 is absent from S2iD** (no record for 310900 in 2019; 34 dam collapses in all): untestable there.
- **Chikungunya (A92) corroborates nothing** (22 tested): the epidemic years are statewide, and the null draws places of
  the same state and years, so SINAN notifications at the lead's places are no more unusual than the state's. The test
  is specific to place, not to the epidemic; a state-level epidemic needs a state-level lead.
