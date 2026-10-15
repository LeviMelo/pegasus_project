# The folder audited by writing the paper from it (2026-10-14)

**Why.** The author: the folder goes to researchers, or a model, who write the paper from it alone. Instead of a
checklist, an agent was given only `studies/infarto_alagoas/` (`data/handoffs/paper-audit-brief.md`: no code, no
project document, no web) and asked to draft the methods, Table 1, Table 2, the figure data, the results and the
limitations of "Acute myocardial infarction in Alagoas, 2014-2023", then to rank every place it could not do something.
It reproduced the crude and adjusted APCs exactly and found every count additive across geography and strata; it
ranked 18 gaps. This is what they were and what was done.

**Regime.** Audit on the folder of PegaSUS acef164 (pegasus_data 0325b7c). Fixes run as the whole study
(`studies/infarto_alagoas.yml`, deep) on the working tree after b4acc59, pegasus_data 0325b7c: 12.5 min (lanes 261 s:
the question passes recomputed; products 415 s, persons and link readings re-keyed by b4acc59); output read table by
table; after the further fixes below, two reruns of 3.9 and 3.4 min (warm), no product failed, no column undocumented.

**Wrong, not missing** (meaning first):

| what the folder said | what it was | fix |
|---|---|---|
| `expectations_sim_do`: y and mu negative, phi empty | three SIM-DO fields (counts, CAUSABAS_O, linked share) wrote one file name; the last, the linked share's logits, kept | one `expectations.parquet` keyed by `field`, with each field's `scale`; a share's `n`, observed and expected share |
| quality: 1,504 "events placed (residence, sex and age)", descriptive 1,503 (2016) | counted by residence alone (`cell=False`): one certificate of municipality 270670 has no sex or age | counted by the rates' own cells |
| README: the linked share is "the link's sensitivity" | 14.2 % of every admission; the link pairs only those that ended in death | the topic's own sensitivity: 88.0 % (86.3-89.6) of the 1,504 admissions that ended in death |
| SIH race and schooling 0 % not recorded | RACA_COR 99 (5,251) and INSTRU 0 (all 9,324) are not declared missing; RACA_COR has no codelist | pegasus_data (data5, in progress); meanwhile a column with one value on every record is flagged (GESTRISCO "Sim", INSTRU, VINCPREV and four more) |
| two SIM fields with one label, two figures alike | CAUSABAS_O, the coding CAUSABAS recodes, was not named | the label names a non-primary classifier |
| the low-income context absent | its filter lists two income bands, compared as one string; and the filter is applied by pegasus_data when it builds a field from a SIDRA series, so PegaSUS applied it twice | a list is `IN (...)`; a series field's filter is pegasus_data's alone |
| air temperature and rainfall for 8 and 9 of Alagoas's 102 municipalities (found by the first run of contexts.parquet) | a context field's stored reading was keyed by its name and years: INMET's stations, read before the fields were rebuilt from BR-DWGD, were still served; the climate relations of the morning's run were INMET's | the key holds the field's declaration and its lake files (path, size, time) and the code |

**Added.** Rates: each sex's rate standardised on the standard's ages of that sex; Brazil's and the macro-region's rates
by sex, age band and sex within band; every standardised rate's ratio to Brazil's with its interval (Alagoas
1.244, 1.224-1.264; women 1.343, men 1.178); the standard's weights (standard.parquet). Trends: the adjusted model's
dispersion; joinpoint regression (Kim et al. 2000, NCI defaults, 4,499 permutations) of the crude and the standardised
rate with segment APCs and the AAPC: no joinpoint in Alagoas (p 0.11-0.13), one in Brazil's standardised admissions at
2020 (2.6 % a year to 2020, 6.6 % after, p 0.048). Seasonality by quasi-Poisson regression on year and month: deaths
peak about 12 August (20 July to 4 September; the monthly index highest in June and July), peak-to-trough 1.15
(1.09-1.21), F p 0.001; admissions about 4 September (10 August to 28 September), 1.34 (1.18-1.52) (first written
here as mid-July and early August: the peak in months from 1 January was read a month early, which the second audit
caught; it is now a day of the year and a date); the date column
named (DTOBITO, DT_INTER) and the year said to be the publications'. Places: each municipality against Brazil's age-sex
rates (SMR, exact interval, two-sided p and BH q), the internal ratio's p and q, the macro-region; the boundaries as
municipalities.geojson. Completeness: SIM's coverage of the state's deaths by year (pegasus_data system_completeness:
93.3 % in 2014 to 95.8 % in 2023), Brazil's events in no reference rate. A same-event link's share on the other side:
27.7 % (26.7-28.8) of Alagoas's AMI deaths in hospital have an SUS admission ending in death. The topic by code
(codes.parquet: I21.9, unspecified, is 97.4 % of the deaths and 72.8 % of the admissions); the age from the records
(the counts' ages stop at 80: the deaths' mean age 67.1 read capped, 68.9 read whole, median 70, 90th percentile 87);
every context per municipality and year (contexts.parquet: each of the eleven on all 102 municipalities); what each
figure shows (figures.parquet).

**Checked, kept.** SIH's alternation (703, 913, 675, 814, 950 AIHs a year in Alagoas's files) and the 2022 jump in
length of stay (mean 7.0 to 12.2 days, median 4 to 8) are in the records by publication year and by admission date
alike, and every year holds its twelve monthly files: features of the source, said, not gaps. Macro-region 2703 holding
regions 7-10 is Alagoas's second (Arapiraca's): correct.

**With pegasus_data's rounds 5 and 6** (merged 71873d6, pegasus_data ADR-0180, pegasus_data ADR-0181). GESTRISCO was coded the wrong way round:
SISAIH01's layout asks it of sterilisation AIHs only, 0 Sim, 1 Não, while TabWin's table binds 1 Sim; the records side
with the layout, so its 1 on every AIH is the default fill, declared not recorded. RACA_COR's 99, INSTRU's 0 and four
more columns' "ignored" codes are declared missing: race is recorded on 43.0 % of the AIHs (was "100 %"); SIH's race
codes read "(undecoded)" because PegaSUS asked for them as one digit, SIM's width (fixed here). sources.parquet lists
every file read (SIH-RD 2014-2023: 3,240 files, every state's twelve monthly files, each with its digest, rows, server
date and status); METHODS quotes what one row is and the known biases of each source, and the population's producer,
vintage (IBGE's Revisão 2024, after the 2022 Census), reference date and method: Alagoas's near-flat 2022-23 is its
natural increase offset by an implied net out-migration of about 0.7 % a year. The area is also compared with its
region without it (the Northeast without Alagoas), its ratio's interval from two independent variances.

**Left.** Open: case fatality at 30 days (needs a person link of every admission to later deaths); ill-defined and
garbage-code shares (pegasus_data round 7, in progress: a declared, cited list) and costs in constant reais (the same
round: IPCA); persons for 2014-2020 and 2023 (link runs not stored); procedures (SIGTAP) not read.
