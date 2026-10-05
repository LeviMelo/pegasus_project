# Race bridge, first measurement: SINASC against SIM on linked infant deaths

**Scenario.** Recorded race/colour of the same infant in SINASC (birth) and SIM (death). It uses the stored probabilistic links `sim_infant_deaths_to_sinasc` (digest 66ff89371b34):
- 2021: 26,008 pairs, FDR 0.75%;
- 2022: 26,055 pairs, FDR 0.69%.

All 52,063 pairs resolve to a record on both sides. Scripts and results are in `data/agent_race/` (`analyse.py`, `results.json`, `report.md`; the full cross-tabs are in `report.md`).

**Regime.** 2026-10-04, pegasus_data branch pegasus-core-fixes.

**Why it matters.** It is the first measurement for the race misclassification term of pegasus_data's modelled tier (ARCHITECTURE §2, §12 phase 3).

**Decoding.** In both systems the codes are 1 Branca, 2 Preta, 3 Amarela, 4 Parda, 5 Indígena; blank is null. `translate` labelled these wrongly or truncated them in some calls; that defect went to pegasus_data.

**Agreement:**
- 63.1% (95% CI 62.7–63.5);
- 69.0% when neither side is blank (n = 47,252).

By region, all pairs / neither side blank:

| region | agreement |
|---|---|
| North | 71.9 / 76.8% |
| Northeast | 64.5 / 74.2% |
| Southeast | 57.6 / 61.4% |
| South | 73.4 / 76.0% |
| Centre-West | 51.6 / 59.0% |

**Where SIM records each SINASC race:**
- Branca: Branca 74.9%, Parda 19.2%.
- Preta: Preta 20.1%, Parda 54.5%, Branca 17.8%.
- Parda: Parda 66.0%, Branca 24.5%.
- Indígena: Indígena 82.5%.
- Amarela: Amarela 7%.

**Totals:**
- SIM has 19,359 Branca against SINASC's 14,050, and 1,596 Preta against 4,446.
- Blank: SIM 6.8%, SINASC newborn 2.9%, SINASC mother 3.8%.

**The direction reverses by region:**

| region | SINASC Parda → SIM Branca | SINASC Branca → SIM Parda |
|---|---|---|
| South | 67.1% | 5.5% |
| Southeast | 37.3% | 17.5% |
| Centre-West | 32.7% | 30.2% |
| North | 15.1% | 55.9% |
| Northeast | 13.6% | 48.1% |

SIM records toward the region's majority category.

**The SINASC newborn race is the mother's declaration.** RACACOR equals RACACORMAE in 50,078 of 50,078 records where both are known, so comparing SIM with the mother gives the same table (62.5%).

**Not a linkage artefact.** Sex agrees in 98.85% of pairs, and the FDR is under 1%.

**Consequence.** Race is not one variable across systems. A rate by race that takes its numerator from SIM and its denominator from SINASC or the census is biased:
- in a direction that depends on the region;
- by more than most effects the scans look for.

The bridge has to be a modelled object: P(SIM race | declared race, region, …), with uncertainty.
