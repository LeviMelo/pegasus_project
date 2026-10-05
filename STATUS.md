# Status

**2026-10-04.** Every module of ARCHITECTURE §11.1 exists. The first block (ICD chapter IX, SIM 2010–2023) is fitted and read end to end: surprises at B0, B1 and B2, lenses, pairs (evaluation 2026-10-04).

**Built:**
- **The data path:**
  - `gateway`: population, event counts, structures, graphs, regions, overlap; it reconciles exactly with the official SIM totals;
  - `store`, `config`.
- **The model:**
  - `structures`, `graphs`;
  - `monolith`: the factorised likelihood, Fellner–Schall, φ by exact ML;
  - `fields`: registry, admission, overlap, lifting.
- **Reading the model:**
  - `surprise`: tiers B0, B1 and B2, randomised PIT, calibration, place-year φ;
  - `scans`: the lenses, subset scanning with a Gumbel null, pairs (E_b, E_b|Z with MSR on the normalised graph, E_w with AR(1) n_eff), CP-APR patterns, explaining away, Shapley decomposition, cohort scans.
- **Inference and use:**
  - `control`: the ledger, BH/BY/Simes, Benjamini–Bogomolov, TreeBH, LOND, splits, replication tiers;
  - `leads`;
  - `harness`: positives, planted signals and power curves, NB surrogates, MSR and shift negatives, the gate;
  - `tools` (Session, survey, confirm);
  - `cli` (`pegasus-core`).
- **Known departures** are listed in ARCHITECTURE §13.

**Fitted (contiguity):**
- **SIM:** IX, I, X (II, XX and XVIII are running).
- **SINASC:** births; anomalies (XVII, from CODANOMAL); birth weight (mark model).

**Running:** held-out IX (graph and pooling), the harness on IX fields, the first survey of IX, and the microcephaly positive.

**The first lead examined:** São Borja (RS), acute MI ×2 in 2018 against flat neighbours (evaluation 2026-10-04, SINASC entry).

**pegasus_data is developed from this session too** (since 2026-10-04): branch `pegasus-core-fixes` (ICD-10 COVID categories, border lengths, `logmoments`, pegasus_data's ADR on GBD).

**Fronts (2026-10-04).** Development runs as parallel fronts. Each front is owned end to end by one agent: code, live validation, evaluation entry. This file is where the fronts are coordinated.

| front | ARCHITECTURE | state |
|---|---|---|
| dengue monthly: **done** (evaluation 2026-10-05). Seasonality calibrated (B2s KS 0.011); epidemics by BP: recall 0.78 (2015–16) and 0.92 (2019–23), precision 0.57 against a trough baseline; φ = 0.235 | §6.1, §10.1 | done |
| SINAN positives: leptospirosis RS 2024, Chagas, schistosomiasis, arbovirus → microcephaly E_w; then an outbreak-robust BP | §10.1, ADR-0004 | agent |
| general SIDRA interface: the compendium's ~100 tables, catalog detection, a normalised fact store; it replaces census.py | §3.1 | agent (pegasus_data) |
| census coverage 2000/2010/2022: which tables are adjusted; what is the 2022 truth | §3.1 | agent (research) |
| preliminary-file snapshots, scheduled daily | ADR-0004 | agent (pegasus_data) |
| SIH blocks (fit, survey); the winter respiratory B2s positive | §10.1, §12 phase 1 | agent |
| population account: **shipped** `population-account-1` (pegasus_data decision 0145). Municipal median error 0.057 against vital-only 0.079 on the PES-corrected 2022; 80% intervals cover 0.79–0.81 | §3.1, §12 phase 2 | done |
| SIM survey and infant cohort readout | §7.1–7.8, §9 | agent |
| pegasus_data hygiene: **done**. Dengue representation fallback; SINAN, SIM, SINASC and SIH dates typed; the race labels corrected; Brasília residence codes in SIH 2008–2017 (SIA and CNES windows open in pegasus_data); ANS and INEP fields | §3.1 | done (pegasus_data 53ea78b…80fa8a6) |
| performance and memory: the decode memory fixed (×8), machine-wide admission control; next: catalog growth, label-pack rebuild, streaming aggregation | §5.5 | agent |
| surveillance feasibility: **done** (ADR-0004 updated): weekly alarms feasible for arboviruses only; preliminary-file snapshots must start now | ADR-0004 | done |
| race bridge: **infant bridge shipped** (pegasus_data fcc1444 (its ADR 0143), `race_confusion_infant`). Out of sample, the count error is 6% against 27% for one national matrix. Infant mortality per 1,000, 2022, raw / bridged / truth: Preta 5.5 / 15.8 / 15.1, Branca 14.3 / 10.1 / 9.9; raw rates invert the ordering. Indígena is not bridged. Adults: not identified; next is SIM women 15–49 ↔ SINASC mothers, or a transported sensitivity band. Next for PegaSUS: race in groups g, through the bridge | §2, §4.2, §12 phase 3 | infant done; adult and groups next wave |
| E_b gate: **passed** (evaluation 2026-10-05, ADR-0005): MSR on the normalised graph, δ_E 0.03 / 0.05; sanitation pairs admitted, smooth-field pairs not (low power) | §7.5, §8.4, §10.5 | agent |
| **backlog, in order** (one fresh agent each; ≤ 5 at a time):
1. Laplace uncertainty layer: **done** (evaluation 2026-10-05, Laplace): cheap draws (block-Jacobi, 40–90 CG iterations), off by default; the verdict: parameter uncertainty is not what miscalibrates; next is OQ 6 (φ_extra per region; an epidemic-level effect).
2. SIH readout: winter respiratory B2s, calibration, the survey leads.
3. SINAN: arbovirus → microcephaly E_w; an outbreak-robust BP.
4. The lens gate: **done** (evaluation 2026-10-05, lens gate): false leads ≤ q on surrogates; outbreak, space–time, E_b pass; spatial cluster fails the negatives (θ0 1.5 set); change point, trend divergence, group disparity and marks have no declared positive. Next: declare positives for them.
5. Race in the groups g (infant through the bridge; the adult sensitivity band).
6. The SUS-dependent population (ANS) and completeness by system (modelled tier).
7. Lead triage: the SIM survey's leads, the coding-substitution and artefact classes.
8. The low-rank interaction ψωτ and patterns across blocks (§4.2, §7.4).
9. The horseshoe on tree levels (§4.3).
10. Phase 3: the institution lattice (CNES); APAC families; dependency maps. **Tools over MCP: PAUSED by the author (2026-10-05).** How they are used and integrated is to be planned together; a first build is parked, uncommitted, in data/parked/mcp/.
11. The adult race bridge (SIM women ↔ SINASC mothers).
12. Phase 4: the weekly grain and the nowcast (ADR-0004).
13. pegasus_data: pegasus_data open question 71 (the DF region-code windows); roles bound to the derived columns; the gateway switch at the next re-warm; streaming aggregation.
14. The PegaSUS exposure switch: the gateway's population from `population-account-1` (pegasus_data decision 0145) with its intervals, in place of POPSVS (P8). After the Laplace merge, because every cache key changes.
15. **Population account v2.** The independent check (2000→2010, pegasus_data 581e99e) found no skill over vital-only (median error 0.077 against 0.076) and 80% intervals covering 0.69 (N 0.54, CO 0.55). v1's 2010→2022 advantage (0.057 against 0.079) does not replicate. Needed: migration covariates (economy, the care-flow graph, region-specific widening) and validation on both intervals before PegaSUS adopts it (item 14 waits on this).
16. SIDRA follow-ups: series stitched across census universes (literacy 10+ against 15+); the SIDRA store served to the gateway's context fields; an ingestion check once phaseb/c/d finish.
17. Regenerate pegasus_data's shipped seed (build_resources.py) once all curation is committed: fresh installs still read SIM RACACOR as Bra/Amar/Indig.
18. An epidemic-level effect for BP: dengue's prospective forecast is 2.0–2.8× off whatever its variance (the Laplace evaluation, 2026-10-05). A state-year or regime component in the extrapolation.
20. Regional dispersion: **done** (ADR-0006; evaluation 2026-10-05, dispersion): φ_extra by macro-region and state; B1 calibrates 30 of 33 fields (28 with one value). OQ 6 keeps the epidemic level and dengue's Southeast.
19. Laplace follow-ups: an MCMC/INLA reference; a refit at the full-Hessian Fellner–Schall τ's (spatial τ about 5× lower on IX).
21. Rebuild pegasus_data's registration/system completeness on population-account-2 (pegasus_data decision 0148 notes its births shortfall came from v1).
22. Population account: horizons of 1–3 years from a census untested; the 2022 urban share is 2010's.
23. Positives declared before running, for trend divergence (homicide NE↑ / SE↓ 2000s, full chapter XX fit, Atlas da Violência tables), group disparity (Atlas tables), marks (a citable birth-weight shift); E_w's dengue–climate run. The coordinator's review of 2026-10-05: only change point passes, at BP.
24. Race in the groups g: births by the mother's declared race; infant deaths through `race_confusion_infant`; adult deaths kept as recorded race (the infant matrix does not transport: pegasus_data decision 0149). After the exposure and BP fronts land.
| | queue |

**Next:**
1. **Held-out deviance** (fit 2010–2021, score 2022–2023). It serves two first measurements: contiguity against kNN, and tree pooling.
2. **The first survey across the fitted chapters**, and E_b|Z with the ill-defined share.
3. **The harness** on surrogates and planted signals: false-lead rates and power curves per lens.
4. **SINASC and SIH** through the gateway.

**Unblocked:** ICD-10 U07/U09/U10 now exist (pegasus_data 70b56fc), so chapter XXII (COVID-19) can be fitted.
