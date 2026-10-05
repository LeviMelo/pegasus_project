# The 57 replicated national-trend claims, read (2026-10-05)

**Regime:** the register `pegasus_home/leads_T2019` (survey of SIM blocks I, IX, X, XVIII, XX on 2010-2019; tier R2 = `kinds_of` holds `temporal` and `spatial`; code of ff56f5f, evaluation `2026-10-05-replication-independent-units.md`). Events: SIM.DO death 2010-2023 by `gateway.event_counts` (the reserve, 2024, not read). Scripts `data/replicated_claims*.py` (cache, per-claim O/E, family pools, violence pools, table), output `data/replicated_claims/`. Populations POPSVS and account-3 (`gateway.population`), SIM completeness `system-completeness-2` (pegasus_data decision 0146). Literature from web searches (summaries only, pages not opened).

**What a claim is.** All 57 are *state* claims (no region): a state's log-linear trend of one ICD node against the national course exceeds 1.2x over 2010-2019 (beta 0.058 per sd-year), and still holds on 2020-23 and on the half of the state's municipalities that did not select it. 53 distinct death sets (J69 is inside J60-J70 CE, Y35 = Y35-Y36 GO, R54 inside R50-R69 PR, Y83 inside Y40-Y84 CE).

## Method (the four rivals, each a number per claim)

- **Independent re-estimate.** Direct standardisation: expected = the year's national rate by sex x 18 age bands x the unit's population; quasi-Poisson slope of O/E on the standardised year, 2010-19. `att` = this slope over the survey's. 44 of 57 keep half or more; 13 do not (the survey's national course, B1, misses a cause whose national rate moves fast).
- **(a) Coding.** The same slope for the node's ICD block *with* the node (`block beta`) and for the chapter; for R00-R99 outside the node; the change of excess deaths (2010-11 to 2018-19) of the siblings and of R against the node's; the series themselves by 3-character code in the unit (`data/replicated_claims_probe.py`).
- **(b) Completeness.** The unit's all-cause slope (`all-cause beta`) and the completeness product's drift of the UF against the nation, 2010 to 2019.
- **(c) Denominator.** The slope again with account-3 in place of POPSVS.
- **(d) Epidemiology.** Cited where a source was found.
- **Classes.** S: survives (a)-(c) and has an independent source. A: a named artefact, with its tag. U: neither shown. Verdicts were set by reading the table and the series, not by a score. Tags: sib sibling substitution; res residual or unspecified code; ill ill-defined to defined; comp composition inside a pooled family; R an R-chapter code (a claim about certification); step abrupt one-year change; off national-course misfit.

## The 57 claims

beta in log rate per sd-year (sd of 2010-19 = 2.87 years), survey / direct (att); "x over 2010-19" = exp(9 beta/2.87) from the direct estimate; obs/exp 2020-23 from the survey's later-years test.

| field | UF | beta survey / direct (att) | x over 2010-19 | obs/exp 2020-23 | all-cause beta | block beta (incl.) | class | evidence |
| I10 Hipertensão essencial (primária) | ES | -0.25 / -0.25 (0.99) | 0.45 | 0.57 | -0.02 | -0.01 | A-sib | I11-I13 +480 of I10 -160 deaths a year; I10-I15 flat (-0.01) |
| I24 Outras doenças isquêmicas agudas d | SC | -0.41 / -0.23 (0.55) | 0.49 | 0.46 | -0.02 | -0.04 | U | R falls .74 to .44 in SC, block falls too (no mirror); real IHD decline vs certification not separable |
| I60 Hemorragia subaracnóide | CE | +0.26 / +0.16 (0.63) | 1.67 | 1.38 | +0.03 | +0.02 | U | gradual from 2010, before CE's R fall (2017); block flat |
| I63 Infarto cerebral | RN | +0.78 / +0.42 (0.54) | 3.73 | 1.98 | +0.05 | +0.02 | U | all-cause SMR in RN .83 to .98; step 2017; block flat |
| I63 Infarto cerebral | ES | +0.92 / +0.78 (0.85) | 11.67 | 3.36 | -0.02 | -0.03 | A-sib | I64 932 (2010) to 84 (2023) as I63 40 to 885; step 2017; I60-I69 flat (-0.03) |
| I63 Infarto cerebral | PR | +0.25 / -0.09 (-0.36) | 0.75 | 1.45 | -0.03 | -0.02 | A-off | att -0.36: no divergence under year-specific national rates |
| I64 Acidente vascular cerebral, não es | ES | -0.25 / -0.15 (0.63) | 0.62 | 0.43 | -0.02 | -0.03 | A-sib | the pair of I63 ES |
| I64 Acidente vascular cerebral, não es | RS | -0.13 / -0.03 (0.24) | 0.91 | 0.65 | -0.01 | -0.03 | A-sib | I63 RS 451 (2016) to 2,229 (2019), I64 2,846 to 1,644; att .24 |
| I67 Outras doenças cerebrovasculares | TO | -0.46 / -0.42 (0.91) | 0.27 | 0.30 | +0.01 | -0.00 | A-step | step 2016 (O/E .6 to .2); sibling change .94 of the node's |
| I67 Outras doenças cerebrovasculares | SC | -0.22 / -0.21 (0.95) | 0.52 | 0.72 | -0.02 | -0.03 | U | gradual 1.2 to .55; R falls; sibling mirror .21 |
| I67 Outras doenças cerebrovasculares | RS | -0.58 / -0.44 (0.76) | 0.25 | 0.11 | -0.01 | -0.03 | A-step | 1,117 to 162 deaths in 2018; I63 RS x4 the same year |
| I69 Seqüelas de doenças cerebrovascula | MA | +0.31 / +0.26 (0.84) | 2.28 | 1.40 | +0.05 | +0.02 | U | MA all-cause SMR +17% relative (2010-19), node x2.3; completeness product +5% only |
| I69 Seqüelas de doenças cerebrovascula | PI | +0.25 / +0.19 (0.78) | 1.84 | 1.51 | +0.02 | +0.01 | A-sib | I69 up while the rest of I60-I69 falls (mirror .68); block flat |
| I70 Aterosclerose | MG | -0.38 / -0.23 (0.60) | 0.49 | 0.50 | -0.01 | -0.08 | U | step 2016-17 (.84 to .42), no mirror in I70-I79; probable code practice |
| I73 Outras doenças vasculares periféri | CE | +0.40 / +0.32 (0.80) | 2.71 | 1.43 | +0.03 | +0.23 | U | CE group: R falls 3,331 to 1,642 (2016-19) |
| I73 Outras doenças vasculares periféri | PE | +0.28 / +0.20 (0.73) | 1.90 | 1.38 | +0.01 | +0.09 | U | gradual x2; PE R falls .82 to .61 in 2017-19 |
| J60-J70 Doenças pulmonares devidas a agent | CE | +0.30 / +0.30 (1.00) | 2.53 | 1.55 | +0.03 | +0.30 | A-ill | CE: J12-J18 +712 of R -1,689 (2016-19), step 2017; respiratory chapter +0.11 |
| J60-J70 Doenças pulmonares devidas a agent | RS | -0.21 / -0.22 (1.02) | 0.51 | 0.69 | -0.01 | -0.22 | A-ill | RS: R excluding the node .66 to .88 of expected while J60-J81 falls |
| J69 Pneumonite devida a sólidos e líqu | CE | +0.35 / +0.33 (0.94) | 2.81 | 1.58 | +0.03 | +0.30 | A-ill | as J60-J70 CE (J69 is 76-93% of J60-J70 there) |
| J81 Edema pulmonar, não especificado d | RS | -0.42 / -0.36 (0.86) | 0.32 | 0.50 | -0.01 | -0.15 | A-ill | as J60-J70 RS; step 2015-17 |
| R00-R09 Sintomas e sinais relativos ao apa | GO | -0.43 / -0.43 (1.00) | 0.26 | 0.47 | -0.01 | -0.43 | A-R | GO R95-R99 1,395 to 710 in 2012; a claim on certification |
| R50-R69 Sintomas e sinais gerais | PR | -0.26 / -0.25 (0.99) | 0.45 | 0.46 | -0.03 | -0.25 | A-R | PR R excl. falls .78 to .42 (certification) |
| R54 Senilidade | PR | -0.30 / -0.30 (1.01) | 0.39 | 0.43 | -0.03 | -0.25 | A-R | inside R50-R69 PR |
| R57 Choque não classificado em outra p | RJ | +0.47 / +0.21 (0.45) | 1.95 | 2.30 | +0.00 | +0.08 | A-R | ill-defined chapter; att .45 |
| R68 Outros sintomas e sinais gerais | CE | -0.31 / -0.13 (0.40) | 0.67 | 0.50 | +0.03 | -0.05 | A-R | ill-defined chapter; att .40 |
| R68 Outros sintomas e sinais gerais | GO | -0.49 / -0.35 (0.70) | 0.34 | 0.38 | -0.01 | -0.28 | A-R | GO 2012 step |
| R96 Outras mortes súbitas de causa des | MA | +0.59 / +0.47 (0.80) | 4.32 | 2.34 | +0.05 | +0.05 | A-R | R98 583 to 298 while R96 35 to 495 and R99 261 to 685: usage shift inside R |
| R98 Morte sem assistência | CE | -0.58 / -0.06 (0.11) | 0.82 | 0.25 | +0.03 | -0.06 | A-R | att .11; R98 is being retired as a code |
| R98 Morte sem assistência | BA | -0.34 / -0.02 (0.05) | 0.95 | 0.25 | +0.02 | +0.05 | A-R | att .05; O/E 3.5 to 5.0 to .8 (humped) |
| V09 Pedestre traumatizado em outros ac | CE | -0.40 / -0.13 (0.33) | 0.66 | 0.43 | +0.03 | +0.02 | A-off | att .33; residual transport code |
| V22 Motociclista traumatizado em colis | CE | +0.41 / +0.32 (0.78) | 2.74 | 1.57 | +0.03 | +0.02 | U | specific code rising x2.7 in CE; family flat; not tested at sub-block level |
| V29 Motociclista traumatizado em outro | BA | +0.14 / +0.18 (1.30) | 1.75 | 1.32 | +0.02 | +0.05 | U | residual motorcyclist code up in BA; family +0.05 |
| V29 Motociclista traumatizado em outro | PR | -0.43 / -0.42 (0.96) | 0.27 | 0.41 | -0.03 | -0.03 | A-res | residual code; V01-V99 of PR diverges -0.03 against -0.42 |
| V49 Ocupante de um automóvel [carro] t | MA | -0.45 / -0.27 (0.61) | 0.42 | 0.53 | +0.05 | +0.07 | A-res | residual code falling while V01-V99 of MA rises (+0.07) |
| V49 Ocupante de um automóvel [carro] t | PR | -0.44 / -0.25 (0.57) | 0.45 | 0.43 | -0.03 | -0.03 | A-res | as V29 PR |
| V87 Acidente de trânsito de tipo espec | SP | -0.60 / -0.62 (1.03) | 0.14 | 0.50 | -0.01 | -0.05 | A-res | V01-V99 of SP -0.05 against -0.62; V87 131 to 22 |
| V89 Acidente com um veículo a motor ou | PR | -0.52 / -0.30 (0.58) | 0.39 | 0.51 | -0.03 | -0.03 | A-res | V89+V99 680 to 123 while V01-V99 -29%; family -0.03 |
| V89 Acidente com um veículo a motor ou | RS | -0.58 / -0.37 (0.63) | 0.32 | 0.62 | -0.01 | +0.02 | A-res | V01-V99 of RS +0.03 against node -0.37 |
| V99 Acidente de transporte não especif | MG | -0.30 / -0.21 (0.72) | 0.51 | 0.45 | -0.01 | -0.01 | A-res | family -0.01 against node -0.21 |
| V99 Acidente de transporte não especif | SP | -0.62 / -0.53 (0.84) | 0.19 | 0.27 | -0.01 | -0.05 | A-res | family -0.05 against node -0.53 |
| W01 Queda no mesmo nível por escorregã | AL | +1.12 / +0.87 (0.77) | 15.04 | 2.23 | +0.00 | +0.11 | U | step 7 to 104 deaths 2016-19, no mirror in W00-W19; probable code practice |
| W18 Outras quedas no mesmo nível | RN | +0.52 / +0.24 (0.47) | 2.15 | 1.79 | +0.05 | +0.10 | A-off | att .47 |
| W18 Outras quedas no mesmo nível | PE | +0.25 / -0.02 (-0.06) | 0.95 | 1.76 | +0.01 | +0.23 | A-off | att -0.06; W19 to W18 swap in 2023 (W19 385 to 135, W18 172 to 554) |
| W19 Queda sem especificação | PE | +0.47 / +0.44 (0.94) | 3.97 | 1.53 | +0.01 | +0.23 | U | x3.3 by 2019 then swapped with W18 in 2023: code is labile |
| W19 Queda sem especificação | RS | +0.35 / +0.30 (0.85) | 2.53 | 1.58 | -0.01 | +0.14 | U | gradual x2.5; siblings of W00-W19 also double |
| W78 Inalação do conteúdo gástrico | SC | +0.82 / +0.39 (0.48) | 3.45 | 1.64 | -0.02 | +0.10 | A-off | att .48; step 2017 |
| X93 Agressão por meio de disparo de ar | MS | +2.13 / +2.14 (1.01) | 809.19 | 4.25 | -0.01 | -0.10 | A-sib | X95 311 to 119 as X93 4 to 89 (2015-19); X85-Y34 of MS -0.09 |
| X95 Agressão por meio de disparo de ou | SP | -0.23 / -0.25 (1.06) | 0.46 | 0.64 | -0.01 | -0.19 | A-comp | pooling Y10-Y34 cuts the family from -0.19 to -0.07: about 60% moved to undetermined intent |
| Y00 Agressão por meio de um objeto con | SP | -0.24 / -0.18 (0.75) | 0.57 | 0.67 | -0.01 | -0.19 | A-comp | as X95 SP |
| Y10-Y34 Eventos (fatos) cuja intenção é in | RS | -0.42 / -0.42 (0.99) | 0.27 | 0.63 | -0.01 | -0.42 | A-comp | RS X85-Y34 pooled +0.03; RS R rising |
| Y21 Afogamento e submersão, intenção n | MG | -0.49 / -0.19 (0.38) | 0.56 | 0.68 | -0.01 | -0.07 | A-off | att .38 |
| Y21 Afogamento e submersão, intenção n | SP | -0.42 / -0.11 (0.27) | 0.70 | 0.62 | -0.01 | +0.06 | A-off | att .27 |
| Y21 Afogamento e submersão, intenção n | GO | -0.53 / -0.24 (0.45) | 0.47 | 0.47 | -0.01 | -0.06 | A-off | att .45 |
| Y35 Intervenção legal | GO | +2.09 / +2.17 (1.04) | 906.99 | 3.51 | -0.01 | +2.17 | S | police registry: GO 265 killings 2017, 425 in 2018 (press quoting the Anuario FBSP), SIM Y35 45 and 76; size recording-confounded |
| Y35-Y36 Intervenções legais e operações de | GO | +2.09 / +2.17 (1.04) | 906.99 | 3.51 | -0.01 | +2.17 | S | same deaths as Y35 GO |
| Y40-Y84 Complicações de assistência médica | CE | -0.94 / -0.93 (1.00) | 0.05 | 0.40 | +0.03 | -0.93 | A-step | O/E 3.3-4.0 in 2010-11 to 1.25 in 2012 |
| Y83 Reação anormal em paciente ou comp | CE | -1.04 / -1.03 (0.99) | 0.04 | 0.37 | +0.03 | -0.93 | A-step | inside Y40-Y84 CE |

## What the four rivals found

- **(a) Coding explains most of the set.** 42 of 57 are artefacts: 21 are composition inside a family (6 sibling substitution, 8 residual or unspecified transport codes, 4 ill-defined to defined, 3 violence pooled with undetermined intent), 9 are R-chapter codes (claims about certification), 4 are one-year administrative steps, 8 are national-course misfits (the claim halves or vanishes under year-specific national rates; five more claims with att below 0.5 sit in other tags). The clearest cases, each readable in the counts: **ES**: I10 falls from 2013, I63 rises 2017-18 as I64 falls, the ICD blocks flat; **RS** 2017-18: I63 451 to 2,229 deaths, I64 and I67 fall, R99 rises 2,048 to 3,356 (2010-19); **MS** 2015-19: X95 311 to 119, X93 4 to 89; **CE** 2016-19: R 3,331 to 1,642 deaths, J12-J18 +712; **CE** 2012: Y40-Y84 at 3-4 times expected in 2010-11, 1.25 in 2012; **GO** 2012: R95-R99 1,395 to 710. Transport: the residual codes V09, V29, V49, V87, V89, V99 fall 0.2-0.6 per sd-year in SP, PR, RS, MG while V01-V99 in the same states diverges by at most 0.05: the claim is the specificity of the certificate, not road deaths.
- **(b) Completeness: none of 57.** The unit's all-cause slope lies in -0.027..+0.046 and carries at most 0.30 of a claim (I63 PR) and 0.22 (I64 RS), under 0.2 for the other 55; the product's drift of the UF against the nation is -3.6..+5.0 % over 2010-19. Two caveats. The claim threshold (1.2x over the period, beta 0.058) lies above these drifts, so a completeness change of this size cannot become a claim by construction (MA and RN all-cause SMR rise 17 and 18 % against the nation, just under it). And the product is an *extension* for every UF after 2011 (`basis extended`), so the check is as good as that extrapolation.
- **(c) Denominator: none of 57.** Account-3 against POPSVS changes a slope by at most 0.012 (median 0.8 % of it; the unit's population ratio to the nation drifts 1.000 to 0.990-1.032). Limit: the two are not independent (both rest on the same census and vital events).
- **(d) Epidemiology.** Cardiovascular mortality fell faster in the South, Southeast and Federal District than in the North and Northeast, and certification improved, with fewer "garbage" codes ([Rev Bras Epidemiol 2017](https://scielosp.org/pdf/rbepid/2017.v20suppl1/116-128/en); pace slowing: [PMC9721214](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9721214/)). That fits the direction of the I24, I67 SC and I70 MG falls and the NE rises of I69 and I73, but those are the codes where certification and mortality cannot be told apart here: they are the 13 U. São Paulo's homicide fall and the northeastern rise are documented ([Unicamp, lethal violence 2000-2017](https://www.eco.unicamp.br/artigos-academicos/growth-of-lethal-violence-in-brazil-2000-2017-a-space-temporal-analysis-of-homicides)); but SP's X95 and Y00 claims shrink from -0.19 to -0.07 per sd-year when undetermined intent (Y10-Y34, 2,575 deaths in 2017, 4,208 in 2018) is pooled: about 60 % of the node's fall is reclassification, the rest (-0.07, about 20 % over the period) is the SP decline. Brazil's road deaths fell about 25 % from 2012 ([Cien Saude Colet](https://www.scielo.br/j/csc/a/ypr9dyzV37fpprKjZS6w8gp/?lang=en)): that is the national course the claims are measured against.

## Verdict

| class | claims | distinct deaths |
|---|---|---|
| S substantive | 2 | 1 (police killings, Goias) |
| A artefact | 42 | 39 |
| U unresolved | 13 | 13 |

- **The one substantive finding.** Y35 legal intervention in Goias: SIM 0-3 deaths a year to 2015, 45 in 2017, 142 in 2019 (observed/expected 3.5 on 2020-23). Press reports quoting the Anuario Brasileiro de Seguranca Publica give 265 police killings in 2017 and 425 in 2018 (search summaries; pages not opened), so the rise is real and SIM records about a sixth of it; the pooled violent-death family (X85-Y36) does not diverge (-0.00), so some of the new Y35 is homicide recoded: the *size* of the SIM slope mixes a real rise with a recording catch-up. Also real, but a residual of claims that are mostly artefact: the SP violent-death decline (-0.07 per sd-year after pooling) and MS (-0.09).
- **What the first independently supported findings say about Brazil.** Mostly a dated map of how each state's death certificates are coded: ES 2013-18 (hypertension, stroke subtype), RS 2017-18 (stroke, I67, rising R99), CE 2012 (Y40-Y84) and 2017 (ill-defined to pneumonia), GO 2012 (ill-defined), MS 2015-19 (firearm specificity), TO 2016 (I67), and the thinning of unspecified transport codes in the South and Southeast. Epidemiological signal is one case (police killings in Goias) plus the SP and MS violence declines.
- **Which artefact classes still pass replication (design inputs).**
  1. *A state's coding regime.* It holds in the later years (a level shift stays) and in the other half of the state's municipalities (one certificate coder serves them). The spatial tier at state scale is not independent of the regime that makes the artefact: halve by coding jurisdiction (neighbouring states), not inside one.
  2. *Composition inside a family* (21 of 57). Replicates in time and place by nature; caught by a conservation test: the claim must survive pooling with its ICD block, the R group and undetermined intent (here the block slope is 0.01-0.05 where the node moves 0.2-0.6).
  3. *Abrupt steps* (4, and part of the U). A level shift persists by construction; needs a shape test (the change in one year against the change over the period).
  4. *The offset's own misfit* (8, and five more in other tags). It lies in both halves and in later years because it lies in the model; a sensitivity against the year's observed national rate (as `relevel` does for the held-out years) removes it.
  5. *Completeness and denominators* produced no claim here; they remain possible above the 1.2x threshold and would show as a co-movement of the unit's all-cause slope, which should be a mandatory column of a unit claim.
- **Not done / limits.** The 13 U are not substantive, only unseparated; certificate-level data (underlying against contributing causes) or the coding software versions by state would separate them, neither read. The direct standardisation uses the nation, which contains the unit; the survey's beta is kept as the claim, mine as the check. Completeness after 2011 is modelled. The reserve was not read and the 2 S need no spend; 54 of 57 keep their direction in 2020-23 under direct standardisation (W18 RN, W18 PE, R98 BA do not, all already A).

## Correction (coordinator, 2026-10-05): "reclassification" here is a bound, not a measurement

**The São Paulo case.** The X95 row's "about 60% moved to undetermined intent" was computed as (−0.19 − (−0.07)) / −0.19:
- the assault family's slope is −0.19;
- the slope after pooling with Y10–Y34 (undetermined intent) is −0.07.

That is an **upper bound**, valid only if every additional undetermined-intent death were a hidden assault. The same aggregate numbers fit a real fall in assaults alongside an independent rise in undetermined deaths, for example from a decline in death investigation.

**What the data show** is that combined violent deaths (assaults plus undetermined intent) still fall in São Paulo. Telling hidden homicides from other undetermined deaths needs individual-level evidence: whether undetermined deaths resemble homicides in weapon, place, age and sex. It was not done here.

**The same caution applies to every "A-comp" / composition label in this entry,** which are of three kinds:

| label | what it says | what it is not |
|---|---|---|
| composition | the family-level trend is flat while a code inside it moves | evidence that individual deaths were relabelled |
| sibling substitution | two codes moving in opposite directions, with a conserved total | proof of who recoded what |
| ill-defined to defined | the R group falling while defined causes rise | a measurement of recoding |

**These labels are recording explanations that the aggregate data CANNOT EXCLUDE.** They are not established recodings. The claim's own effect remains possible.
