# The ecological model and the smoothed municipal ratios (2026-10-14)

Three paper audits found a study's contexts collected per municipality and related to nothing, so a design declared
"ecological" estimated no association. They also found a map's crude standardised ratios dominated by small places.
Both are now estimates in the folder (`study._ecological`, `study._places`); METHODS gains an "Ecological analysis"
section and the smoothing's paragraph; `body()` requires both (`places` needs `smoothed_smr`; `associations`
where contexts exist).

**Regime.** `studies/infarto_alagoas.yml`, `--products-only` on the working tree over f4fead5, with the adopted key
window, the real stores; log `data/probes/infarto_eb.log`; 250 s.

**Ecological model.** For each count field: NB2 with an offset of the events expected at the area's own age-sex rates,
contexts per SD, cluster-robust by health region. Three fields (SIH I21-I22, SIM CAUSABAS, SIM CAUSABAS_O), 11
contexts: 66 associations with intervals, each context alone and jointly. The joint models name the variance inflation
over 5 of the two collinear ICU-bed contexts (alone they go one way; jointly 1.31 against 0.76). Moran's I of the joint
residuals: SIH 0.059 (p 0.11), SIM 0.024 (p 0.27), CAUSABAS_O 0.084 (p 0.055). Little spatial dependence is left.

**Smoothed ratios.** Marshall's (1991) global empirical Bayes: a moment-estimated gamma prior per year and over the
period, with a 95 % gamma posterior interval. 3,366 rows over the 3 fields. The shrinkage follows the noise:

| municipality | events | SMR (exact CI) | smoothed (CI) |
|---|---|---|---|
| 270620, SIH | 30 | 2.26 (1.52-3.22) | 1.55 (1.14-2.02) |
| 270640, SIH | 168 | 2.25 (1.93-2.62) | 2.02 (1.74-2.32) |
| 270330, SIM | 195 | 2.32 (2.01-2.67) | 2.15 (1.86-2.45) |

`body()`: 24 of 24 parts met.
