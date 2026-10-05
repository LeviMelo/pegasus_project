# Census coverage 2000/2010/2022: the raw 2022 Census is the undercount; POPSVS is IBGE's corrected projection

**Question.** Which 2022 population is right? Our vital account (`data/vital_account.py`) gives:

| source | 2022 |
|---|---|
| Census | 203.08M |
| vital projection from Census 2010 | 209.08M |
| POPSVS | 210.86M |

The census-minus-vital residual concentrates at ages 25–39 (men −2.0M, women −1.27M) and 0–4 (−1.04M). The author's hypothesis was that POPSVS is wrong. It was tested against the alternative that the raw census is low.

**Regime.** 2026-10-05: primary sources, plus SINASC and SIM through pegasus_data. A research agent; its text is filed here.

## Sources

| figure | 2022 | coverage-adjusted | source |
|---|---|---|---|
| Census raw (SIDRA 9514) | 203,080,756 | no | 195,101,203 enumerated + 7,979,553 imputed (occupied households without interview, 4.23%): [PES report](https://biblioteca.ibge.gov.br/visualizacao/livros/liv102110.pdf) |
| PES 2022 (post-enumeration survey) | net error 8.3% (omission 12.2%, wrongful inclusion 3.3%) | measures it | about 10% at 0–4, 10–11% at 20–34, 3–5% at 60+; from 3.8% (PB) to 15.5% (RJ). Same report |
| IBGE Projeções, Revisão 2024 | 210,862,983 | yes (+3.9%) | demographic reconciliation of 2000/2010/2022 with PES: [notes](https://biblioteca.ibge.gov.br/visualizacao/livros/liv102111.pdf) |
| IBGE estimates (TCU) 2024 / 2025 | 212.6M / 213.4M | yes | [note](https://biblioteca.ibge.gov.br/visualizacao/livros/liv102112.pdf) |
| POPSVS / TabNet popsvs2024br | 210,862,983 | yes | IBGE's projection distributed to municipality × age × sex: [OPGH note](https://observatoriohospitalar.fiocruz.br/sites/default/files/biblioteca/Nota%20t%C3%A9cnica%20n%C2%BA1_2025_%20OPGH%20atualiza%20o%20c%C3%A1lculo%20dos%20seus%20indicadores%20com%20base%20nas%20novas%20estimativas%20populacionais.pdf) |

## Tests

**Births, 2022.** SINASC births from August 2017 to July 2022 number 13.91M; less infant and child deaths, about 13.73M survive.

| 0–4 count | value | against the surviving births |
|---|---|---|
| Census | 12.705M | 92.5% complete |
| PES-corrected | 13.58M | within 1.1% |
| POPSVS | 13.82M | |

Emigration cannot explain a deficit of under-fives.

**Ages 25–39:**

| count | value |
|---|---|
| Census | 47.12M |
| PES-corrected | 49.94M |
| POPSVS | 49.56M |
| vital | 50.37M |

PES explains about 87% of the census-minus-vital gap.

**2010.**
- Births test: the census is 0.963 of the surviving births, before any correction for SINASC completeness.
- IBGE reconciles 190.76M to 194.7M: +2.2% overall, +7.4% at ages 0–9.
- No person-level PES rates are published.

**2000.**
- The coverage survey reports only a gross omission of 7.87%, with no age detail: [IBGE 2003](https://biblioteca.ibge.gov.br/visualizacao/livros/liv1402.pdf).
- IBGE reconciles 169.87M to 174.7M (+3.0%).
- SINASC was too incomplete in the 1990s for the births test.

**POPSVS 2000 and 2010** are IBGE-reconciled too, not raw.

**Intercensal growth.** Raw census differences understate 2010–22 growth by about 3.8M against the reconciled figures, so a raw residual reads coverage error as migration.

## Verdict

**The hypothesis fails.** The raw 2022 Census is the undercounted series. POPSVS equals IBGE's coverage-corrected projection.

**The weak spots of POPSVS:**
- at ages 60+ it sits 0.25M below the raw census, because IBGE carries 2010 forward there;
- its municipal splits use PES rates by municipality size class.

## Decisions

These bind the population account front.

- **Observed:** raw census counts, keeping the enumerated/imputed split, and vital events.
- **Modelled:** POPSVS, the IBGE projections and estimates, and the vital account. POPSVS is not an independent check on the vital account; both rest on births and deaths.
- **Coverage:** a latent term per census × age × sex, with priors from PES 2022 and IBGE's 2000/2010 reconciliation as sensitivity.
- **2022 hold-out truth:** the PES-corrected census. The raw census and IBGE's reconciliation are reported as sensitivities. Never POPSVS.
