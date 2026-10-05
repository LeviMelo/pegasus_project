# The SIM survey read out: 7,496 leads, and what the top of the list is (2026-10-05)

**Regime:**
- **Run:** `pegasus-core survey SIM.DO death --replicates 100`, 22:36 to 02:28 (3 h 52 min), 19 fitted chapters, contiguity, B0/B1/B2 per lens, Bogomolov across families. Leads in `pegasus_home/leads`; log `data/logs/survey_sim.log`.
- **Scripts:** `data/readout_survey.py`, `readout_survey_summary.py`, `readout_lead_check.py`. Logs `data/logs/readout_survey*.log`, `readout_lead_check.log`.
- **Raw check:** the gateway's event counts (pegasus_data records, 2010–2023), year by year, the lead's code in its places against its siblings, its parent and Brazil. Labels from the ICD-10 tree and `pg.translate`.

## What was admitted

| lens | leads | | chapter | leads |
|---|---|---|---|---|
| trend divergence | 3,355 | | XVIII (ill-defined) | 2,599 |
| space-time | 2,289 | | XX (external) | 1,291 |
| group disparity | 1,063 | | IX | 897 |
| outbreak | 761 | | X | 818 |
| change point | 28 | | I | 592 |

- **35% of all leads, and 68% of the trend-divergence leads (2,271 of 3,355), are in chapter XVIII.** They describe how deaths are certified, not how people die.
- **Stories:** 3,866 places or subsets. São Paulo has 122 leads, Rio de Janeiro 67, Fortaleza 50. **122 stories (3.2%) carry a substitution flag:** R95–R99 50, I60–I69 19, XX 11, I30–I52 7, E10–E14 7.
- **No lead is replicated:** all 7,496 are R0.
- **Space-time leads stop at 20 per field and lens** (the recursion cap): 934 of 2,289 point down.

## The top ten by rank, read against the records

| # | lead | raw reading | class |
|---|---|---|---|
| 1, 3 | Curitiba, XVIII and R95–R99, trend +17.8 and +16.0 sd | ill-defined deaths 87 → 299 (2010 → 2023) while Brazil is flat and neighbours fall; all causes 9.9k → 11.9k | **artefact** (certification) |
| 2 | X59 São Paulo, group disparity | 4,722 deaths: ages 80+ at 2.0–2.5 × the national pattern, adults 20–59 at 0.3–0.5 ×. The "worst group" shown (F 10–14, 1 against 10) is not what drives it | **artefact** (X59 in São Paulo is mostly the elderly; elsewhere it is adults) |
| 4 | W84 Rio, group disparity | 80+ at 1.1–1.4 ×, infants 0.6 × | **unclear** (certification of the old; no external check made) |
| 5, 7, 9 | R99, R95–R99, XVIII São Paulo, group disparity | R99: men 15–39 at 2.3–4.2 ×, women 80+ at 0.35 ×; young deaths go to the death-verification service and stay unspecified | **artefact** (certification) |
| 6 | X95 Salvador, group disparity | firearm assault, young men 15–24 at 1.1–1.2 ×, men 40+ at 0.5–0.7 × | **plausible**, small |
| 8 | J81 São Paulo, group disparity | pulmonary oedema NEC in men 15–24 at 3.0 × | **artefact** (same mechanism as R99) |
| 10 | J12 Magé, Duque de Caxias and 26 more places, 2020–21, RR 7.3 | J12 877 in 2020 against 4 a year before; J18 falls (6,155 → 4,618) in the same places | **signal through a coding artefact**: COVID certified as viral pneumonia |

**Reading the top of the list:** the rank (−log10 q × |log effect|) is saturated by q underflow (10 leads have q < 1e-200, 8 of them group disparity), and the group-disparity lens ranks first the big cities where a small difference in age pattern is enormous in G².

## Other leads read, because the top ten were not enough

| lead | raw reading | class |
|---|---|---|
| A92 Fortaleza 2017, 159 against 14 | A92.0 (chikungunya): 24 in 2016, 146 in 2017, 5 in 2018; the Fortaleza epidemic | **plausible signal** |
| X36 Brumadinho 2019, 133 against 12 | X36 is 0 in 2010–18, 133 in 2019 (Brazil 317); the tailings dam failure of January 2019 | **plausible signal** (a disaster, found without being told) |
| B34 Mossoró 2016, 29 against 0.3 | all B34.9; Brazil 232 in 2016 against about 55 a year | **plausible**, aetiology unclear (an unspecified viral illness; arbovirus the likely cause) |
| A48 Varginha 2017, 85 against 6 | A48.3 (toxic shock syndrome) 84 of Brazil's 422 that year, 4 in 2018 | **artefact** (one city's certification) |
| R98 Olindina (BA), trend +12 sd | R98 0, 1, 1, 9, 31 … 44, 18, 1, 0 (2010–23); Brazil R98 25,178 → 6,672 | **artefact** (the code's use is disappearing nationally) |
| I46 Fortaleza and Rio metro, 2010–13, RR 0.01 | I46 is 0 in 2010 and 641 in 2011, 3,501 in 2023 (Brazil) | **model artefact**: the expectation borrows the later years of a code that did not exist as a cause in 2010 |
| I46 Rio metro 2022–23, RR 4.4 | I46 62 (2017) → 836 (2023) while I42 1,033 → 420 | **artefact** (cardiomyopathy → cardiac arrest, a substitution) |
| J12 2010–13 and 2014–17, RR 0.01–0.03 | J12 is 0–6 a year there until the 2020 surge of 877 | **model artefact**: the code's place effects are learned from the epidemic (the weakness named in the COVID entry) |
| outbreaks of A90–A99 (2015 10 places, 2016 12, 2017 21, 2018 14), J09 2016 (15 places), J12 2020–21 (27 and 24 places) | many places in one year | **plausible signals**: the dengue and chikungunya years, an influenza season (J09 2016), COVID |

**Change points (28 leads)** are mostly small places (27 of 28 have 3–33 observed events; the exception is Araçatuba I26–I28, 144 against 76). Two read: Amajari (RR), protozoan diseases B50–B64: 0 until 2019, 2, 2, 11, 11 (2020–23) against 4,177 in Brazil and falling, **plausible** (malaria, not checked externally); G37 in General Sampaio (CE): 4, 2, 1 deaths in 2011–13 and none in the ten years after, reported as a window "2011–2023" that includes the quiet years, so the effect is understated and the lead is **unclear** (small numbers, a local certifier).

## Substitutions

- **Stroke:** Brazil's I63 rises 4,157 → 12,635 while I64 falls 44,865 → 33,749 (2010 → 2023); the 19 flagged stories in I60–I69 are places adopting the specified code at different times. Not a change in mortality.
- **Diabetes:** E10 1,966 → 7,229 and E11 4,002 → 16,593 while E14 stays near 50,000: type specification is the "signal" in the E10–E14 stories.
- **R95–R99:** R98 falls 25,178 → 6,672 and R99 rises 35,070 → 60,544 (2021), so most of the 50 flagged stories are the retirement of R98.

## What this says about the instrument

- **The survey finds what it should:** the dengue years, chikungunya in Fortaleza, the 2016 influenza season, COVID (as J12 and B34.2), Brumadinho. Of the 16 rows read above: 5 plausible signals (X95 Salvador, A92, X36, B34, the epidemic years), 1 signal through a coding path (J12 2020–21), 1 unclear (W84), and 9 artefacts of certification or of the fit.
- **What it cannot yet separate is recording from mortality.** The observation lens (§7.1) exists in principle; XVIII is not routed to it.
- **Defects found, not fixed here (the files are other fronts'):**
  1. **Group-disparity "worst group"** is the group with the most extreme SIR among those with μ ≥ 5, not the group contributing most to G². The shown group (effect 0.03) is usually unrelated to the signal. `scans/lenses.py:227` also raises `divide by zero in log` when a group has no deaths.
  2. **The rank saturates at q = 0**; ties among the top group-disparity leads are broken by nothing.
  3. **The register is written once at the end of the survey.** A crash after 3 h 52 min would lose all of it. Write per chapter.
  4. **Down-direction subsets are leads** (934 of 2,289 space-time), but a deficit in a code that was introduced or retired is a model artefact, not a finding. A lead that points down and sits in a code with a national trend of more than a factor of 3 should be flagged `recording`.
  5. **No tier BP** (prospective expectations) is applied, so epidemic years inflate the expectation of the years before them (J12, I46).

## Next

- Route XVIII and R-code leads to the observation lens, and flag leads whose code changes nationally by more than 3× over the window.
- Replicate (R1, R2) the outbreak and space-time leads with a plausible reading, starting with the dengue years.
