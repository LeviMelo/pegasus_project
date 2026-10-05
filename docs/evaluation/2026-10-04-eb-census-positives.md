# E_b known positives against census context: signs recovered, admission underpowered

**Scenario.** §10.1 positives "infant mortality ↔ income, sanitation" and "diarrhoea ↔ sewerage", through `scans.pairs.between` (Dutilleul n_eff, H0 |ρ| ≤ δ = 0.1). The scripts are under `data/agent_context/` (`prep.py`, `analyse.py`, `rank_sens.py`; results in `results.json`). Tests are registered in the harness ledger (`pegasus_home/harness/ledger`), not production.

**Regime.** 2026-10-04, pegasus_project 00936a9, 5,570 municipalities.

**Outcomes.** Per-place shrunk log-rate effects (`surprise.refit_place`, Poisson, T = 1):
- **Infant mortality.** SIM deaths at age 0 in 2018–22 (165,628) over SINASC births (13.76M); expected = births × national rate.
- **Diarrhoea.** Deaths A00–A09, 2010–22 (58,535); expected by indirect age-sex-year standardisation.

**Context.** Census 2022 shares (sewer, water, no bathroom, waste collected, literacy 15+) and log GDP per capita 2021. Each is z-scored with a constant sd of 0.05. The context sd cannot change ρ.

| outcome | context | ρ | n_eff | p (δ 0.1) | ρ given log GDP pc | n_eff | p |
|---|---|---|---|---|---|---|---|
| infant mortality | sewer | −0.210 | 98 | 0.136 | −0.147 | 307 | 0.203 |
| infant mortality | water | −0.212 | 211 | 0.048 | −0.148 | 1127 | 0.052 |
| infant mortality | no bathroom | +0.240 | 131 | 0.051 | +0.182 | 599 | 0.020 |
| infant mortality | literacy | −0.242 | 32 | 0.216 | −0.120 | 221 | 0.382 |
| infant mortality | log GDP pc | −0.238 | 52 | 0.159 | | | |
| diarrhoea | sewer | −0.185 | 75 | 0.229 | −0.124 | 266 | 0.345 |
| diarrhoea | no bathroom | +0.268 | 98 | 0.045 | +0.218 | 460 | 0.005 |
| diarrhoea | literacy | −0.276 | 24 | 0.201 | −0.187 | 133 | 0.156 |

(Waste and water for diarrhoea are omitted; they are in `results.json`.)

**Signs.** All 12 signs are as expected, and the 10 adjusted signs are too. Sanitation survives income in sign and at about 70% of its size.

**Shrinkage.** It matters. Infant mortality ↔ sewer goes from a crude ρ of −0.07 to −0.21 once the Poisson noise of small municipalities is removed.

**Admission fails, for want of power.** Only 2 of 12 pairs pass δ = 0.1 at 0.05. Dutilleul n_eff is 24–211 of 5,570, because the context fields are strongly autocorrelated (literacy's correlogram reaches 1.0 at 15–75 km). With a naive n, all 12 would give p < 10⁻⁴.

**Consequence.** By §10.5, E_b has not passed its gate. ρ ≈ 0.2 against δ = 0.1 needs n_eff ≈ 100–200. Two things remain open:
- the provisional δ was never calibrated on negatives (§8.4);
- Dutilleul's n_eff is not yet compared with the Moran spectral randomisation null (§10.2) for power at a held false-lead rate.

Diarrhoea deaths are a weak outcome. §10.1 names admissions (SIH).
