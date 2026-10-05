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
| 2026-10-05 | [Dengue at the monthly grain](docs/evaluation/2026-10-05-dengue-monthly.md): counts equal TabNet in 8 of 10 files; φ 0.235; season ×13 (Sul ×102); B2s calibrated (KS 0.011); epidemics recovered at BP (2015–16: 29/37 state-years; 2019–23: 59/64, precision 0.57), not at B2s; φ implies detection by clusters and BP | SINAN-DENG 2010–2023, contiguity, pegasus_data 22a4b67 |
| 2026-10-05 | [Surveillance lags](docs/evaluation/2026-10-05-surveillance-lags.md): SINAN preliminary cut 1 day old, delay p50 8–15 d; SIM and SINASC preliminary cut 9 weeks before posting; SIH 5 weeks by competence month; revisions seen (SIA +26%, DENG final −47% rows) | catalog crawl 2026-09-28 and backup 08-30, cached blobs, pegasus_data pegasus-core-fixes |
| 2026-10-05 | [Census coverage 2000/2010/2022](docs/evaluation/2026-10-05-census-coverage.md): the raw 2022 Census undercounts (PES net 8.3%; ages 0–4 92.5% complete against births); POPSVS = IBGE's corrected projection; the 2022 hold-out truth is the PES-corrected census | IBGE PES, projections; SINASC, SIM |
| 2026-10-05 | [The E_b gate](docs/evaluation/2026-10-05-pairs-gate.md): MSR on the normalised graph is the between-places null (sd ratio 0.99, size 0.047; Dutilleul 0.076, raw-W MSR 0.70); δ_E 0.03 (E_b), 0.05 (E_b\|Z); 5 of 12 sanitation/literacy/GDP pairs admitted; power on smooth latents low | SIM, 5,570 municipalities, Census 2022, contiguity, pegasus_core design-v0 |
| 2026-10-05 | [Known positive: leptospirosis, Rio Grande do Sul floods 2024](docs/evaluation/2026-10-05-positive-leptospirosis-rs.md): BP + space-time recover 18 RS municipalities, May–June, RR 63; 95.7% of the excess captured; the Jaccard criterion as written fails | SINAN-LEPT 2010–2024 monthly, contiguity |
| 2026-10-05 | [Known positives: Chagas and schistosomiasis](docs/evaluation/2026-10-05-positive-chagas-schistosomiasis.md): on SIM deaths (B57, B65) the B0 ratios put the Ministry's endemic states first (Goiás 5.6; Alagoas 7.7); Jaccard criterion fails, precision 1.0 | SIM.DO 2010–2023, chapter I, contiguity |
| 2026-10-05 | [The SIM survey read out](docs/evaluation/2026-10-05-sim-survey-readout.md): 7,496 leads; 35% in chapter XVIII (certification); the top ten read against records are mostly artefacts; Brumadinho, the dengue years and chikungunya in Fortaleza found unprompted; five defects listed | SIM.DO 2010–2023, 19 chapters, contiguity, 100 replicates |
| 2026-10-05 | [The BP baseline history, dengue 2019–23](docs/evaluation/2026-10-05-bp-baseline-history.md): last 12 months recall 0.92 / precision 0.57; last 36 months 0.91 / 0.64 (new monthly default); median and Farrington-style robust 0.81 / 0.71 (miss the big epidemics of states that had one in the fit) | SINAN-DENG 2010–18 fit, 2019–23 scored, state lens |
| 2026-10-05 | [Known positive: arbovirus notifications and microcephaly, Northeast 2015–16](docs/evaluation/2026-10-05-positive-arbovirus-microcephaly.md): Q02 25× its forecast, onset-to-onset lag 6–7 months on the regional total; E_w at the immediate-region grain not recovered (ρ 0.12 plateau over lags 0–6, none admitted; control flat) | SINAN-DENG, SINASC 2010–17 monthly, immediate regions |
| 2026-10-05 | [The Laplace uncertainty layer](docs/evaluation/2026-10-05-laplace-uncertainty.md): block-Jacobi CG cuts a draw from 1,000 capped iterations to about 40 (50 on full IX); parameter uncertainty is at most 10 % of the overdispersion and moves in-sample KS by ≤ 0.01; BP IX 0.126 → 0.056 with the history's forecast error; BP dengue stays 2.0–2.8× off (not a variance problem); the Centro-Oeste failure is regional dispersion (φ_extra per region calibrates B2s); a B2 Σμ² inconsistency corrected | SIM.DO IX knn6/contiguity, SINAN-DENG monthly, GPU, 32 draws |
