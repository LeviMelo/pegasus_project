# Handoff to pegasus_data: SINAN CHAG and ESQU event types

**2026-10-05.** From the PegaSUS front "SINAN known positives" to pegasus_data.

**Asked:** event types and roles for `SINAN-CHAG` (acute Chagas disease, 2007–2025 published) and `SINAN-ESQU` (schistosomiasis, 2007–2026), as for the 15 SINAN families already served (`curation/roles/SINAN-*.yml`). `pg.event_types("SINAN-CHAG")` and `("SINAN-ESQU")` currently raise "no event types declared"; both datasets decode (`pg.availability` reports 26 and 20 published years).

**Needed by the gateway:** a `notification` event type (one row, one notification), the onset date (`DT_SIN_PRI`), the notification date, municipality of residence (`ID_MN_RESI`), sex, age; for ESQU the form's case classification if it carries one.

**Why:** ARCHITECTURE §10.1 lists Chagas disease and schistosomiasis as spatial-cluster positives at B0. Until these exist the positives are run on their deaths in SIM (B57, B65; evaluation 2026-10-05), which measure the chronic disease (Chagas) and its severe end (schistosomiasis), not notifications. Acute Chagas notifications are an Amazon (Pará) oral-transmission signal and would be a second, different locus; ESQU notifications are the Ministry's own endemic-area record.
