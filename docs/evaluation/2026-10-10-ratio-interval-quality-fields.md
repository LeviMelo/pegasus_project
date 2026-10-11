# Ratio, interval and quality fields (2026-10-10)

Regime: branch `design-v0` (this commit), PegaSUS's data root, store as of the survey-depth toxoplasmosis run.
What was counted: each new field kind on real records, against a figure known independently, because a wrong rate
or delay here reads as a finding downstream.

**Ratio fields (BACKLOG 2.2).** A ratio is the numerator's count with the denominator's events as exposure
(`gateway.population("events:DS:EV[:codes][@lag]")`), both in one cell with neither sex nor age read
(`event_counts(cell=False)`).

| field | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| SINAN-TOXC per SINAN-TOXG notification | | 0.31 | 0.31 | 0.32 | 0.34 | 0.41 | 0.45 |
| SIM-DOFET per 1,000 SINASC births | 10.4 | 10.2 | 10.6 | 10.9 | 10.7 | 10.4 | |

The foetal death rate is Brazil's known level (about 10 per 1,000). DOFET 2019 accounts for every record of the
file (28,983 allocated, 122 outside a municipality: 29,105, the count pegasus_data's 2026-10-10 evaluation made). A
TOXC event in a municipality-year with no TOXG notification is unallocated ("no population in the cell": 1,988 of
26,375 over 2019–2024).

Two defects found on the way:
- **Warm starts across exposure units.** The ratio's first fit started from TOXC's person-year fit, so b0 began about
  15 log units off. It stayed at μ ≈ 1e-66 (objective 4.16e6, 26,208 events "against 0 expected"). A cold fit
  reproduced the 26,208 events (φ 3.8). `warm_start` now relates fits of the same exposure unit only.
- **A code set's share** was taken against the code set's own fit as the total. That gave 4,185 "share departures"
  from CIH-CR's 3 P37.1 admissions. The total is now the unrestricted reader's, and a ratio asks no share.

**Interval fields (2.3).** The descriptive table reports the records' median and 90th percentile
(`gateway.mark_quantiles`), not exp(mean log). The delays are not log-normal: same-day prenatal notifications sit
beside a long tail.

| TOXG, days from onset | 2019 median / p90 | 2023 median / p90 | the moments' exp(mean log), 2019 |
|---|---|---|---|
| to notification | 5 / 205 | 5 / 79 | 8.1 |
| to closure | 103 / 364 | 36 / 272 | 61.2 |

**Quality fields (2.5).** Each declared column present in every study year gives the share of its blank or
declared-missing values (`share_moments(quality=True)`). TOXG has 25 such columns. Schooling is ignored in 26.8%
(2019) to 31.8% (2021); the 2019 share is exactly the 2,260 records coded 9.

**Roles by year.** `gateway._strata(dataset, event, year)` reads the column a role has in that year's layout. It
reads the latest layout's column when no year is given, which fixed SIM-DOFET, DOINF and DOEXT's residence.

**Groups and supports (2.4, 2.6).** The group question also runs over each composition column
(`Session.by_composition`). A value's expectation is each age–sex cell's B0 expectation times Brazil's share of the
value in that cell, so the national totals are reproduced exactly. TOXG 2019–2024 has 135 departures over 6 columns
(sex × age: none, as a field of pregnant women should). Examples: Espírito Santo's schooling "0" at 21.7 times;
Piauí's autochthony "not recorded" at 2.9 times. The supports read TOXG at its place of infection (recorded for
40,949 of 71,471 cases; São Paulo 1,139, Fortaleza 643, Manaus 482) and at its notifying municipality (Teresina
1,682 against 737 resident cases).

**Triage by reader.** A system read as a code set had its dataset's chapter answers triaged on the code set's
session (CIH-CR, CIHA: `StopIteration` and "codes=['P371'] is a field of its own"). Answers are now triaged by
their own reader and on their own years; `READER_FIELDS` names code sets, quality and supports.

**A ratio's place-years without exposure.** A municipality-year with no denominator event has μ = 0, and the noise
structure divided 0 by 0 ("Residuals are not finite"): such a cell now carries no variance. The study maps draw a
municipality's (O − E)/sd rather than O/E, whose small places were mostly noise.

**Declared denominators (2.2b).** pegasus_data decision 0161: TOXG, TOXC, SIFG and SIFC are read per live birth, SIM-DOFET
per total birth (live births and foetal deaths), by default. TOXG is 2.96 per 1,000 live births in 2019 and 6.44 in
2024 (Rio Grande do Sul 8.32 in 2023); the literature's Uberlândia figure for 2020–2025 is 3.6–5.6. Foetal deaths
are 10.1–10.8 per 1,000 total births. Under an event exposure a composition's expected mix is the year's national one.
Retired answers are no longer triaged or written to a study.

**Race as a group dimension (3.4).** Read against Brazil's mix, race "departed" wherever the population differs: Santa
Catarina's pardos at 0.25. A race is now expected at the place's own population share of it in each age–sex cell
(population-account-6's race slices; under a births exposure, at the events' national age–sex profile), re-levelled
to Brazil's observed totals. TOXG 2019–2024 has 36 departures. Espírito Santo records "amarela" 18.5 times expected,
beside its schooling "0" at 21.7, which points to a recording practice. Roraima notifies indigenous women at 0.24 of
their share. Piauí leaves race unrecorded 2.9 times.

**Gestational → congenital as a relation (3.5, measured).** `tools.compare` (the joint factor model over graph-spectral
bands and lags) on SINAN-TOXG and TOXC, 2019–2024, annual grain: 55 relations. The two move together in the same year
at every scale (ρ 0.18–0.24 over 20 to 443 places, 0.73 macro-regional, 0.98 national), read as a shared driver, not a
lead. That fits a pregnancy shorter than the annual grain and one screening programme behind both notifications. A
lag in months waits for the monthly grain.

**Interpretation on every finding (7.2, 7.4).**
- **Context profile.** Each finding carries the mean of every rated context over its places, as a national
  percentile. Counts without a declared denominator ranked by size alone (every capital at p100), so only rated
  contexts enter, plus the residents once. Examples: a small Piauí municipality has sewer network p1 and households
  without a bathroom p99; Manaus is urban p98 with SUS primary-care units per resident p3.
- **Related fields.** Every other primary field is read at the finding's places and years as O/E with an exact
  interval. TOXC across Rio Grande do Sul in 2019–2020 is 1.36 [1.24, 1.49]; Porto Alegre in 2023 is 0.57 [0.42, 0.75].
- **Institutional findings (7.1).** An establishment's CNES.ST registration is read for the finding's first and last
  year (one national month, 74 s once, then kept in the store). Hospital de Clínicas de Porto Alegre in 2023: a general
  hospital with a SUS link, 526 beds, an obstetric centre and a neonatal unit. A code absent in a year is "not
  registered", never zero.

**Capture model (2.7).** `capture.multiple_systems` fits every log-linear model with main effects and any set of
pairwise dependences and averages N̂ by Akaike weight (Buckland, Burnham & Augustin 1997). It was checked on the
three-list spina bifida data (upstate New York, 1969–1974, Hook, Albright & Cross 1980; 621 cases; from R's conting):
- every model's N̂, deviance and AIC equal R's `glm`;
- the averaged N̂ is 734.8 [660.5, 809.1];
- the lists' completeness is birth certificates 69%, death certificates 28%, rehabilitation 25%, against the authors'
  68%, 27% and 25%.

**Related codes from records (4.2).** `cooccur.related_codes` reads every code a record carries, here the certificate
lines of SIM 2015–2023 deaths with B58 or P37.1. Each category's records with a seed are compared with their expectation
under independence within sex × ten-year age strata (exact Poisson, BH at 0.05). 88 categories are related. HIV
leads: B24 on 7,816 certificates at 27.6 times expected [27.0, 28.2], B20 at 23.1. AIDS's opportunistic infections
follow: pneumocystosis (B59, 16.2), cytomegalovirus (B25, 22.5), CNS tuberculosis (A17, 25.3), candidiasis (B37, 16.3).
That is the known clinical picture of cerebral toxoplasmosis in AIDS. The read takes 7 s once the counts are cached.

**Same-record outcomes in the cohort scan (6.1).** `pegasus-core cohort SINASC-DN birth baby 2021 --outcome
record:IDANOMAL=1 --outcome record:CODANOMAL~Q90` gave 2,677,101 births, 22,959 with an anomaly and 1,125 with Down
syndrome. Of 256 contrasts over 25 attributes, 39 hold at q 0.05:
- preterm gestations carry 3.3–4.3 times the anomaly rate;
- breech presentation 2.6 times;
- an unrecorded sex 85 times (an undetermined sex marks a genital anomaly);
- Down syndrome is raised in Robson groups 7 and 10 (breech; preterm).

The run took 1,056 s, mostly reading the record identities.
