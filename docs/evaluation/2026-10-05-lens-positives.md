# Known positives for the ungated lenses (2026-10-05)

**Regime:** local scripts `data/p2/*.py` (artefacts `data/p2/*.json`; gitignored), fitted blocks of `pegasus_home/monolith` (SIM.DO all chapters 2010–2023 and chapter I 2010–2019; SINASC births 2010–2023 and 2010–2019; SIH-RD chapter X monthly; SINAN-DENG monthly), lenses at the thresholds of the gate entry (q 0.05, θ0 1.2, spatial 1.5), contiguity graph. Recovery is scored with `harness.recovery`; the positives are in `harness.POSITIVES` and ARCHITECTURE §10.1.

**Criterion.** A place-level Jaccard 0.5 cannot be met when the documented excess sits in a few places, so for the per-place lenses a positive is recovered when the **documented-excess-weighted recall of the documented places is ≥ 0.5 with the right sign**; Jaccard and precision are reported beside it.

## Declared and scored

| lens | positive (source) | result | verdict |
|---|---|---|---|
| change point, **BP** | COVID-19 enters the record in 2020 as a new cause (B34.2; WHO emergency ICD-10 use). Chapter I fitted to 2010–2019, 2020–23 scored; documented places: 5,285 municipalities with ≥ 5 deaths | 714,782 deaths against 372 expected; 5,562 findings, windows start 2020–22; weighted recall 1.00, Jaccard 0.95. **At B2 (fit over all years) 1 of 5,285 places**: the in-sample place trend absorbs the step | recovered at BP; trivially large, a single positive |
| trend divergence, B2 | five municipalities installed 2013 ([IBGE](https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/14431-asi-novos-mapas-municipais-do-ibge-mostram-que-brasil-tem-agora-5570-municipios)): births are recorded under the new code only from 2013 | SINASC births: 13 findings, 4 of 5 documented found (Mojuí dos Campos 13.3 sd, Pescaria Brava 9.7, Balneário Rincão 8.7, Paraíso das Águas 8.0), all up; Pinto Bandeira (about 23 births a year) not. Recall 0.80, precision 4/13 (the other nine are undocumented, not known false) | recovered |
| group disparity, B0 | female homicide in Roraima, the highest rate of the UFs (Atlas da Violência 2019 and 2021, read through a [press report](https://www.bemparana.com.br/noticias/brasil/onde-as-taxas-de-homicidios-de-mulheres-sao-mais-altas-no-brasil/); the Atlas tables themselves were not read), X85–Y09 | 18 findings among 3,250 testable places; 2 in Roraima (Alto Alegre, Caracaraí) of 14 testable, female share 0.188 and 0.384 against 0.092 and 0.089 under the national pattern (×2.1, ×4.3); the state as a whole ×1.40, the highest of 27 UFs | recovered (2 places) |

The trend-divergence positive was seen in the lens's first run on births and documented afterwards; the same lens on the five chapter IX fields (B2 pickles) finds none of the five (0.2 to 185 deaths in the whole period: too few), so it is not blind replication.

## Evaluated, not declared

- **São Paulo's violent deaths of undetermined cause, 2018** (Y10–Y34 2,575 → 4,208; the Atlas da Violência 2020 ch. 1, [IPEA](https://repositorio.ipea.gov.br/bitstream/11058/10353/1/AtlasdaViolencia2020_Cap1.pdf): Brazil 12,310, +25.6%; São Paulo 4,255, +62.5%, [Brasil de Fato](https://www.brasildefato.com.br/2020/08/30/por-incompetencia-do-estado-nao-e-possivel-saber-numero-real-de-homicidios-em-sp/)): change point at B2 on the full fit, **0 findings** (B2 expects 4,760 for 2019 against 4,086 observed). The 2010–2019 chapter XX fit meant to put the shift at the end was stopped at outer 32 of 40 (3,800 s per iteration under the shared queue). Its BP version needs a fit to 2017 and was not run.
- **Venezuelan migration, Roraima births** (births in the state 12,112 in 2017, 13,194 in 2018, 15,105 in 2019; mothers born in Venezuela 634, 1,807, 3,174: SESAU-RR [situation report, Nov 2023](https://vigilancia.saude.rr.gov.br/wp-content/uploads/2024/03/relatorio_migracaovenezuelanaemroraima_11.2023.pdf)): change point on births fitted to 2010–2019, Boa Vista 8,163 and 8,936 against 7,890 and 8,081 expected, **0 findings**. The excess is 1.06 times the expectation, under the 1.2 floor.
- **Elderly suicide in Rio Grande do Sul** (Minayo, Meneghel, Cavalcante, Ciênc Saúde Coletiva 2012;17(8):1963–72): group disparity on X60–X84, 474 testable places, **0 findings**; the older-age share in RS is ×1.28 of the national pattern, under the lens's sd 0.2. Suicide of young Indigenous people (São Gabriel da Cachoeira, Tabatinga, Dourados) cannot be tested: no two sex-age groups reach 5 expected events (`min_expected`).
- **Young men's excess of assault deaths** is the national pattern the lens uses as its reference, so it cannot be found by construction.
- **Regional homicide divergence** (North and Northeast +68%, Southeast down, 2007–2017, Atlas da Violência 2019) is shared by neighbouring places: outside the estimand of a lens that contrasts a place with its neighbours.
- **Marks, no positive:** the documented birth-weight effects (preterm births in Brazil, odds +4% in 2020, ("Preterm births prevalence during the COVID-19 pandemic in Brazil", [PMC10477268](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10477268/))) are about 0.1% of the mean weight against the 3% floor. A lead the lenses did produce, not a positive: PESO space–time, 8 municipalities of Alagoas in 2013, mean weight −6.4% (p 6e-5), undocumented.

## E_w

Units are municipalities with INMET stations (489 with ≥ 2 admissions a month); monthly mean-temperature anomaly per calendar month (z), against the B2s surprise of SIH-RD chapter X; the control moves the temperature by five years. Positive: low temperature raises respiratory admissions, RR 1.07 (1.01–1.14) at extreme cold, Brazil 2008–2018 (Requia et al., Environ Res 2023;231:116231, [BORIS](https://boris.unibe.ch/182982)).

| units | ρ lag 0 / 1 / 2 | control lag 0 / 1 / 2 |
|---|---|---|
| all (489) | −0.024 / −0.039 / −0.017 | −0.003 / −0.012 / −0.010 |
| Norte (66) | −0.058 / −0.074 / −0.063 | +0.038 / +0.030 / +0.041 |
| Nordeste (130) | −0.035 / −0.052 / −0.025 | +0.004 / +0.001 / +0.007 |
| Sul (87) | −0.024 / −0.013 / +0.009 | −0.011 / −0.030 / −0.032 |
| winter months only, all | −0.008 / −0.019 / −0.001 | −0.004 / −0.010 / −0.006 |

The sign is right in every pooled row except the South at lag 2, the controls are near zero, and **no ρ reaches δ = 0.1**; at n_eff ≈ 850 the national ρ (−0.039) is 1.1 standard errors from zero. A documented relative risk of 1.07 gives a correlation this small, so the cold effect is **below the minimum effect**: not a positive for E_w at δ 0.1.

**Not run to completion:** monthly temperature and precipitation anomalies → dengue probable cases (B2s), lags 0–4, for which Lowe et al. (Comput Geosci 2011;37:371–381) found precipitation and temperature at 1–3 months significant (`data/p2/ew_dengue.py`, log `data/logs/p2_ew_dengue.log`) was still queued behind the machine's heavy slots when this entry was written. E_w stays **not gated**: arbovirus → microcephaly not recovered (2026-10-05 entry), cold → respiratory below δ.

## Reading

- **B2 cannot show a step older than the last years** (COVID-19, São Paulo 2018, Roraima 2018): the change-point lens is a BP lens, as the outbreak lens is. B2's place trend is fitted in-sample.
- **The trend-divergence lens finds boundary artefacts** and is blind to regional divergence; it belongs to the observation family as much as to the epidemiological one.
- **Group disparity** reads a place's departure from the national sex-age pattern, needs two groups with 5 expected events, and found a documented sex pattern, not an age pattern.
