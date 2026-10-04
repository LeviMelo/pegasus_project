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
  - `scans`: the lenses, subset scanning with a Gumbel null, pairs (E_b, E_b|Z, E_w with Dutilleul and AR(1) n_eff), CP-APR patterns, explaining away, Shapley decomposition, cohort scans.
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

**Next:**
1. **Held-out deviance** (fit 2010–2021, score 2022–2023). It serves two first measurements: contiguity against kNN, and tree pooling.
2. **The first survey across the fitted chapters**, and E_b|Z with the ill-defined share.
3. **The harness** on surrogates and planted signals: false-lead rates and power curves per lens.
4. **SINASC and SIH** through the gateway.

**Unblocked:** ICD-10 U07/U09/U10 now exist (pegasus_data 70b56fc), so chapter XXII (COVID-19) can be fitted.
