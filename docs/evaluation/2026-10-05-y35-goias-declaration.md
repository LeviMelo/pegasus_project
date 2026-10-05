# Declared: legal-intervention deaths (Y35) in Goiás, real rise or recoding

**Status.** Declared 2026-10-05, before the discriminating data were read. Ledger id `3d787b765f614065`; spec at `data/y35_goias_declaration.json`.

**Origin.**
- In SIM, Y35 in Goiás rose from 0–3 deaths a year (to 2015) to 45 (2017) and 142 (2019).
- FBSP reports 265 police killings in Goiás in 2017 and 425 in 2018.
- The author notes that a physician rarely certifies legal intervention as the underlying cause.

**Competing hypotheses and what each predicts in data not yet read.** The data are: pooled firearm deaths of every intent (X93–X95, Y22–Y24, X72–X74, W32–W34, Y35), the certifier field, the place of occurrence, the victims' profile, SIH firearm admissions, 2012–2021.

| hypothesis | predicts |
|---|---|
| **real** (police lethality rose) | pooled firearm deaths rise beyond the national course; Y35 rises without a matching fall in assault and undetermined firearm deaths; victims' profile matches police-killing profiles; SIM Y35 follows FBSP's yearly counts in direction |
| **recode** (Y35 relabels other firearm deaths) | the pooled total is conserved; X93–X95 + Y22–Y24 fall by about the Y35 rise, in the same years; a dated certifier or IML change; the same victims' profile as the deaths replaced |
| **coverage** | SIM Y35 below FBSP, with a rising ratio |

**Rule.**
- Each prediction is scored separately.
- The verdict names which hypothesis the data support, with its evidence grade (tested / bound / consistent).
- No hypothesis is dropped without a discriminating test.
- FBSP counts are read from the Anuário's primary tables.

## Result

**Run.** 2026-10-05; code `data/y35_goias_{sim,sih,labels,analysis,sih_analysis}.py`, `data/y35_goias/fbsp.json`; outputs `data/y35_goias/{analysis.out,results.json}`; handoff `data/handoffs/y35_goias.md`. SIM.DO 2012-2021 was read through `pegasus_data` with explicit select lists (residence = `CODMUNRES`; the reserve, SIM.DO 2024, was not read). Y35 is the 3-character category (all subcodes), Y35.0 (firearm) in brackets. The declaration's 142 for 2019 is 146 here (residence) and 157 by occurrence; the filter behind 142 was not reconstructed.

**Yearly table.** Deaths by residence in Goiás; pooled = X93-95 + Y22-24 + X72-74 + W32-34 + Y35 as declared; FBSP = police-killing count of the latest edition carrying the year, police on and off duty; n/o = not obtained.

| year | X93-95 | Y22-24 | X72-74 | W32-34 | Y35 (Y35.0) | pooled GO | pooled BR | Y35 BR | FBSP GO | Y35/FBSP GO | FBSP BR | Y35/FBSP BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2012 | 1955 | 21 | 22 | 5 | 0 (0) | 2003 | 43124 | 708 | n/o | | n/o | |
| 2013 | 2138 | 12 | 41 | 5 | 3 (3) | 2199 | 43196 | 592 | n/o | | 2212 | 0.27 |
| 2014 | 2054 | 2 | 37 | 8 | 1 (1) | 2102 | 45861 | 793 | n/o | | 3146 | 0.25 |
| 2015 | 2161 | 5 | 35 | 6 | 2 (2) | 2209 | 44937 | 942 | 141 | 0.01 | 3330 | 0.28 |
| 2016 | 2143 | 9 | 42 | 11 | 9 (9) | 2214 | 48152 | 1374 | 209 | 0.04 | 4220 | 0.33 |
| 2017 | 2057 | 7 | 33 | 5 | 45 (37) | 2147 | 51465 | 1854 | 265 | 0.17 | 5179 | 0.36 |
| 2018 | 1860 | 7 | 36 | 6 | 76 (69) | 1985 | 45781 | 2042 | 429 | 0.18 | 6175 | 0.33 |
| 2019 | 1457 | 8 | 41 | 9 | 146 (128) | 1661 | 35579 | 1470 | 533 | 0.27 | 6351 | 0.23 |
| 2020 | 1391 | 5 | 35 | 7 | 164 (127) | 1602 | 38589 | 2188 | 631 | 0.26 | 6413 | 0.34 |
| 2021 | 1012 | 9 | 52 | 4 | 167 (155) | 1244 | 37502 | 2285 | 564 | 0.30 | 6493 | 0.35 |

**FBSP source.** Anuário Brasileiro de Segurança Pública, table "Mortes decorrentes de intervenções policiais, segundo corporação e situação", Goiás row, read from the PDFs by word position (`pdftotext -layout` misaligns the state rows of these tables). URLs are under `https://forumseguranca.org.br/wp-content/uploads/`; pages are PDF pages; editions revise earlier years (first and latest values in `fbsp.json`).
- 2015-16: `2017/12/ANUARIO_11_2017.pdf` p.13.
- 2017-18: ano 13 (2019) p.63, with the breakdown 3+237+1+24 and 0+416+1+8 on p.52. The file read is a mirror, `static.poder360.com.br/2019/09/forumseguranca-Anuario-2019-FINAL-v3.pdf`; the forumseguranca path guessed returned 404.
- 2018-19: `2020/10/anuario-14-2020-v1-interativo.pdf` p.83. 2019-20: `2021/07/anuario-2021-completo-v6-bx.pdf` p.57. 2020-21: `2022/06/anuario-2022.pdf` p.75. 2021-22: `2023/07/anuario-2023.pdf` p.59. 2022-23: `2024/07/anuario-2024.pdf` p.57.
- Brazil 2013-14: "Gráfico 19", printed p.59 of the 2021 edition. FBSP's MVI for Goiás: 2012-18 ano 13 p.16; 2019-20 ed. 2021 p.58; 2021 ed. 2022 p.76.
- **Not obtained: Goiás 2012-2014.** Guessed URLs of the 2015 and 2016 editions returned 404, and the search of `publicacoes.forumseguranca.org.br` lists only the 2010 edition. The coverage ratio before 2015 is untested.

**Labels.** Decoded with `pegasus_data.translate`: ATESTANTE 1 attending physician ("Sim"), 2 substitute, 3 IML, 4 SVO, 5 other, 9 unknown; FONTE 1 Boletim de Ocorrência, 2 hospital, 3 family, 4 other. **Two of its labels contradict the shipped layout (`pegasus_data/sources/SIM_Mortalidade_Geral_Estrutura.pdf`) and the data, and the layout's were used.** Cross-tab against the cause, Brazil 2012-21: CIRCOBITO code 3 holds 97% of X93-95, code 2 95% of X72-74, code 1 45% of W32-34 and code 4 89% of Y35, so 1 = accident, 2 = suicide, 3 = homicide, 4 = other (translate: 1 = homicide, 3 = accident). LOCOCOR code 4 holds 49% of assaults, 3 = home (55% of suicides), 1 = hospital, 2 = other health facility (translate: 2 = public road, 4 = other). Defect for `pegasus_data` (codelist `TIPOVIOL` for CIRCOBITO; the LOCOCOR list). The translate vintage fallback (no codelist window covers 2018) applies to all fields.

### Score of each prediction

| # | prediction | result | grade |
|---|---|---|---|
| real-1 | pooled firearm deaths rise beyond the national course | **No.** Pooled 2,214 (2016), 1,661 (2019), 1,244 (2021). Goiás's share of the rest of Brazil's pooled: 0.0500 (2012-16), 0.0456 (2017-19). Index to 2012-16: Goiás 0.997 against rest 1.147 in 2017; 0.57 against 0.84 in 2021. A weak discriminator: about 500 more police killings fit a fall of the total if other deaths fall more (FBSP MVI less police killings: -41% 2015-19). | tested |
| real-2 | Y35 rises without a matching fall of X93-95 + Y22-24 | **No: there is a fall, and it is larger than the rise.** Against Goiás's 2012-16 share of the rest of Brazil, the deficit of X93-95 + Y22-24 is 321 / 228 / 151 / 345 / 676 (2017-21) against a Y35 excess of 42 / 73 / 143 / 161 / 164: 1,721 against 583. | fall tested; its size bound (rests on the national-course counterfactual) |
| real-3 | Y35 victims match police-killing profiles | **Yes** on sex, age, race: 99-100% male, median age 22-23, 78-79% aged 12-29, 79-81% brown or black among known race (FBSP Brazil 2022, ano 17 p.65-66: 76% aged 12-29, 83% black). **No** on place: 30-42% on the public road (LOCOCOR 4) against FBSP's 68%, but 22-32% died in hospital, and LOCOCOR is the place of death, FBSP's the place of the event. | consistent (national benchmark, other year) |
| real-4 | SIM Y35 follows FBSP in direction | **Yes.** Goiás 2015-21: Pearson 0.98, Spearman 0.96 (n = 7). FBSP 141 to 631 (2015-20, 4.5x); Y35 2 to 164. | tested (two trending series: weak) |
| recode-1 | pooled total flat while Y35 rises | **No.** It fell 44% (2016-21) against 21% in the rest of Brazil; only 2017 is flat (0.997) while the rest of Brazil rose 15%. | tested |
| recode-2 | X93-95 + Y22-24 fall by about the Y35 rise, same years | **At most a third.** Equal only in 2019 (151 against 143); 2-8 times larger in the other years. 2017-21 deficit 1,721 (bootstrap sd 128) against a Y35 excess of 583, p(D = E) < 1e-4. If every extra Y35 death were a relabelled X95/Y24 death, recode would explain 34% of the fall. Across 26 UFs the fall of X93-95 + Y22-24 does not go with the Y35 rise (slope +1.9, se 0.8; recode implies -1); Goiás ranks 5th of 26 on the Y35 rise and 6th on the fall. | bound (an upper bound); across-UF slope tested but weak |
| recode-3 | a dated certifier / IML change | **No.** IML (ATESTANTE 3) certifies 95.5% (2012) and 97.3% (2017, 2021) of Goiás X93-95 and 95.6-99.3% of Y35; the attending physician (code 1) certifies none of the Y35 and 0.2-0.7% of X93-95. Rest of Brazil: 92-95%, also flat. "A physician rarely certifies it" is true, but Goiás's IML already signed nearly every violent death in 2012. Not tested: the IML unit, the CRM. | tested |
| recode-4 | Y35 profile identical to the X93-95/Y22-24 replaced | **No** against ordinary firearm homicide: median age 22-23 against 25-26, aged 12-29 78% against 62-63%, male 99-100% against 93-96%; total-variation distance of the age distributions 0.15-0.18. It cannot discriminate the variant "police killings coded X95 move to Y35": they are young men either way. | tested (general variant); not identified (police variant) |
| coverage-1 | SIM Y35 below FBSP with a rising ratio | **Yes.** Goiás 0.01 (2015), 0.04, 0.17, 0.18, 0.27, 0.26, 0.30 (2021); by occurrence 0.37 in 2021; Brazil flat at 0.23-0.36. Goiás began two orders below the national ratio and ended at it. | tested (2015-21) |

### Decomposition and consistency checks

- Y35 = c x FBSP. From 2015 to 2020 the rise is +162: 7 if only FBSP rose, at the 2015 fraction (c = 0.014); 35 if only the fraction rose, at the 2015 FBSP level; 120 from both together. From 2016: 18, 45, 92. Neither factor alone produces it. Grade: consistent (FBSP counts taken as the true number).
- Non-police violent deaths (SIM X85-Y34 against FBSP MVI less police killings): SIM exceeds FBSP by 196 (2015), 352, 569, 578, 589, 735, 650 (2021). Police killings outside Y35 (FBSP less SIM Y35) are 139, 200, 220, 353, 387, 467, 397. Both rise together, as they would if most police killings sit in X95. SIM's all violent deaths over FBSP's MVI is steady (1.02-1.14). Grade: consistent (the offset is assumed constant).

### Verdict

**Both a real rise and a coding catch-up; not a recode of ordinary firearm deaths into Y35.**
1. **Real rise: supported.** FBSP's police counts rose 4.5x (141 to 631) and SIM Y35 follows. Tested for direction; bound for size, since FBSP's Goiás series is the state's own and may have changed how it records, which this test cannot see.
2. **Coverage / coding: supported and large.** In 2015 about 98% of Goiás's police killings sat outside Y35; in 2021 about 70% still did. Most of the Y35 rise is the Y35 share moving to the national level together with the real rise. Tested for the ratio; consistent for the decomposition.
3. **Recode of other firearm deaths into Y35: rejected as the main account.** Tested on the pooled total, the profile and the certifier; bound at 34% of the fall of X93-95 + Y22-24. It is not excluded as a minor contribution in 2019, the one year the sizes match.
4. Pooled firearm deaths fell in Goiás; the Y35 rise is a rise of a category, not of firearm mortality.

**Honesty note.** Police-killing recording in SIM is a documented problem. In São Paulo city 2014-15, linking SIM to the state police (SSP-SP) records, 53% of lethal police-violence deaths sat under other underlying causes in SIM, and SIM under-reported them by 53.2% (capture-recapture): Ryngelblum M, USP master's thesis 2021 (DOI 10.11606/d.5.2021.tde-22092021-161219) and its Cad. Saúde Pública 2021;37(10):e00317020. The figures come from the abstract summary; the full text returned 403 to this client. Goiás's 2015 ratio of 0.01 is far beyond that. These tests cannot say which X95 deaths were police killings; only a record link (SIM to police occurrence reports) can.

**Open.** SIM-to-police-record linkage; FBSP Goiás 2012-14; the IML unit or CRM behind the 2017 jump; whether SSP-GO changed its own classification around 2016-17.

**SIH firearm admissions: not completed (a gap, not an absence).** `data/y35_goias_sih.py` reads SIH-RD (hospital UF = GO; `IDENT` = 1; firearm codes in `DIAG_PRINC`, `DIAGSEC1-9`, `CID_ASSO`, `CID_MORTE`; the external cause sits in `DIAGSEC` from 2014 only, `DIAG_SECUN` being dead, so 2012-13 cannot show it). One year ran: 2014, 359,979 admissions, 1,034 with a firearm code, peak 0.32 GB. Every later attempt (a single year, eleven in parallel, a wrapped queue) stalled for more than 40 minutes on the machine's shared decode queue before reading a record, with the CPU idle (diagnosis: admission wait, not a failure of the source). The SIH prediction (Y35 admissions rising with FBSP, an intent mix unchanged) is therefore **unscored**.
