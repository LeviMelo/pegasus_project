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

## Coordinator review (2026-10-05)

The gate requires positives declared before the lens runs (§10.5). Measured against that rule, this entry's gate table stands as follows.

| lens | gate | reason |
|---|---|---|
| change point | **passes, at BP** | COVID-19 as a new cause code in 2020 was specified before the run |
| trend divergence | **does not pass** | the positive (municipalities installed in 2013, whose births rise from zero) was documented after its hits were seen, and is trivial by construction |
| group disparity | **does not pass** | Roraima female homicide was sourced through a press report, not the Atlas da Violência tables, and recovered in 2 of 14 places |
| marks | fails | no citable shift was found |
| E_w | not gated | the dengue–climate run is pending |

**The §10.1 criterion change** (excess-weighted recall ≥ 0.5 in place of a place-level Jaccard ≥ 0.5 for per-place lenses) is accepted, flagged. Its reason holds: a Jaccard of 0.5 cannot be met by sparse outcomes. It was adopted after seeing results, however, so it is confirmed only when a positive declared beforehand passes under it.

**Next.** Positives declared before running:
- the homicide divergence between the Northeast and the Southeast in the 2000s, from the full chapter XX fit, citing the Atlas da Violência tables;
- group disparity from the Atlas tables;
- a citable birth-weight shift for marks.

## Declared before the run (second round, 2026-10-05)

**Regime.** Positives written into `harness.POSITIVES` and committed (86d6895, with `scripts/declare_positives.py` and `scripts/atlas_uf.json`) before any lens ran on them; scored by `data/p3/score.py` (artefact `data/p3/score.json`) with `harness.recovery`, on the existing SIM.DO chapter XX 2010–2023 contiguity fit (no refit: a chapter XX block is hours under the queue). Sources are the Atlas da Violência UF tables, IPEA/FBSP: 2019 Table 2.1 for 2010–12 ([repositório](https://repositorio.ipea.gov.br/server/api/core/bitstreams/0bba5ec5-f166-4c0a-82d4-271b28c90df0/content)), 2025 Tables 2.1, 2.2, 4.3, 5.1 for 2013–23 ([handle 11058/17165](https://repositorio.ipea.gov.br/handle/11058/17165)). The loci follow from those tables, the contiguity graph and the population alone. Criterion: weighted recall of the documented municipalities ≥ 0.5 with the documented sign (weight: estimated deaths), the §10.1 criterion adopted after the fact; the original Jaccard 0.5 is reported.

| lens | declared positive | result | verdict |
|---|---|---|---|
| trend divergence, B2 | a municipality's documented divergence is its UF's log-rate slope (2010–23) less its neighbours' UFs' mean; 30 municipalities with a ratio ≥ 1.5 over the period (16 up, 14 down). The first choice, a doubling, left 3 places and was widened before any run | 7 findings in the whole field (BA 2, MG 2, PB 2, PI 1); **none in the 30**. Weighted recall 0, Jaccard 0 | **fails** both criteria |
| group disparity, B0 | women's share of homicide victims 2013–23 against Brazil's (7.9%), UFs with ratio ≥ 1.25 or ≤ 0.8: RR 1.66, SC 1.54, MS 1.43, SP 1.38, RS 1.27, RO 1.26; AP 0.64, SE 0.64, RN 0.78, AL 0.78 (1,943 municipalities) | 15 findings (BA 5, PA 4, RR 2, AM, CE, AL, SE 1 each); 4 in documented UFs, all with the right sign (RR 2, AL, SE). Weighted recall **0.048**, Jaccard 0.002, precision 1.0 | **fails** |
| group disparity, B0 | men aged 15–29's share 2013–23 against Brazil's (49.2%): RO 0.71, RR 0.79, SP 0.75, MS 0.74; AP 1.27 (807 municipalities) | the same 15 findings; 2 in documented UFs (RR), right sign. Weighted recall **0.003**, Jaccard 0.002 | **fails** |
| marks | none declared: no primary source gives a shift of mean log mark ≥ 3% at a place and time. Searched: drought and birth weight in Rio Grande do Norte (grams, under 1%), Zika (acts on the count of births), the Mariana and Brumadinho dams (low-weight odds, no mean shift), COVID-19 preterm births (about 0.1% of the mean). The only mark fitted is PESO | not run | **fails**: no positive |

**Reading.**
- Group disparity finds the places that are very different from the reference (Roraima, Bahia, Pará), not the documented UF-level departures. The reference is the model's B0 expectation, and **it overstates women's share**: the national expected share of women is 9.98% against 8.2% observed (2013–23), young men 48.2% against 48.9%. The lens divides the excess by a genomic-control factor of 1.83. São Paulo city, 8,843 deaths, sits at 0.92 of the reference for women while the state sits at 1.38 of Brazil's observed share. The sex pattern the Atlas documents is therefore partly a difference between the observed and the model's national pattern, and the lens is blind to departures from the observed one. A lead (re-level the B0 group pattern to the observed national group totals), not a change made here.
- Trend divergence has no finding in the documented belts. The documented divergences are a ratio of 1.5 to 2 between neighbouring states over 13 years, in the range where the power curve is blind (below ×3); its 7 findings (BA, MG, PB, PI) were not scored against borders.
- The §10.1 criterion of weighted recall stays confirmed by one declared positive only (change point at BP, 1.00); on the declared positives of this round it does not change a verdict (the Jaccard is also under 0.01).
- The earlier passes of these two lenses (installed municipalities, Roraima female homicide) were seen before they were declared. They are withdrawn from the gate, as the review says, and not replaced by a pass.

## E_w dengue (exploratory only)

`data/p2/ew_dengue.py` (dengue against temperature and precipitation anomalies, lags 0 to 4; heavy label `ew-dengue`) was queued at 09:52 and had not been admitted when this section was written (`data/logs/p2_ew_dengue.log` holds the queue line only). It was **not declared in `harness.POSITIVES`** before it was queued; any result of it is exploratory and cannot gate E_w. E_w stays not gated.
