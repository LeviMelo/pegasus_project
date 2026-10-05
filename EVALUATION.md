# EVALUATION.md

The index of measurements: harness runs, budgets, comparisons. One file per entry under `docs/evaluation/`.

- **Nothing is declared working on the basis of a plausible-looking output.** Read the leads, maps and numbers, and count against an independent figure (CLAUDE.md §5).
- **An entry names:**
  - the harness case or script, and its artefact;
  - what was counted, and why it is the thing that matters;
  - the regime: commit, data versions, date.
- **A small finding goes into an existing entry** where one fits.

| date | entry | regime |
|---|---|---|
| 2026-10-04 | [Chapter IX, the first fit read end to end](docs/evaluation/2026-10-04-chapter-ix-first-fit.md): φ by ML (5.98, not 0.013), calibration B0/B1/B2, lenses, pairs | SIM.DO 2010–2023, knn6, pegasus_data 0.1.0a1 |
| 2026-10-04 | [SINASC through the model; the optimiser; the change-point null; São Borja examined](docs/evaluation/2026-10-04-sinasc-lenses-optimiser.md) | SIM and SINASC 2010–2023, contiguity, pegasus_data 70b56fc |
| 2026-10-04 | [E_b known positives against census context](docs/evaluation/2026-10-04-eb-census-positives.md): 12/12 signs, 2/12 admitted at δ 0.1 (Dutilleul n_eff 24–211); the E_b gate not passed | SIM, SINASC, Census 2022, 5,570 municipalities, 00936a9 |
| 2026-10-04 | [Race bridge, first measurement](docs/evaluation/2026-10-04-race-bridge-infant.md): SINASC vs SIM race on 52,063 linked infant deaths, 63% agreement, the direction reversing by region | links sim_infant_deaths_to_sinasc 2021–22 |
| 2026-10-05 | [Dengue at the monthly grain](docs/evaluation/2026-10-05-dengue-monthly.md): counts equal TabNet in 8 of 10 files; φ 0.235; season ×13 (Sul ×102); B2s calibrated (KS 0.011); epidemics recovered at BP (29/37 state-years), not at B2s; BP 2019–23 pending | SINAN-DENG 2010–2023, contiguity, pegasus_data 22a4b67 |
