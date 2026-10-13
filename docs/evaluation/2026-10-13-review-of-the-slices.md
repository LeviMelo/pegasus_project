# The RS slices reviewed as a paper's raw material (2026-10-13)

**Scenario.** A read-only review of `studies/slices/toxoplasmosis_deep_slice` and `leptospirosis_deep_slice`
(f44fcdb–7d8c800 outputs), plus direct counts from the lake, independent of the models.

**Wrong numbers found, fixed at f5281d5 and after:**
- **Code sets collapsed.** Every rare code-set field was read collapsed, all its events in one cell (male, age 0).
  - The collapse rule compared the dataset's events lost to a missing sex or age, every code and all of Brazil, with
    the field's own events: 15,670 against 31 SIM B58 deaths in RS.
  - Expectations, standardised rates and findings of SIM, SIH and SIA code sets rested on an exposure of male infants.
  - Fixed: the code set is filtered before the area and the lost events, and its key records how it was read.
- **Case mix.** The sex and age table read those cells: gestational cases were 100 % male at age 0.
- **SIA serology by residence.** It rose 65-fold in RS while tests billed stayed near 5 M a year: residence is placed
  for 0.15 % of tests in 2014 and 9.7 % in 2023. The Santa Maria hypothesis was "supported" (33×) on this artefact,
  while by place of testing it was not. Every rate row now carries `allocated_share`, and hypotheses scale for it.
- **The series' "expected".** It was B1, fitted on the same years, so it matched the totals by construction. It is now
  prospective.
- **O/E against the wrong tier.** Cluster findings (B0, national rates) had their O/E computed against B1: a region at
  13× the national rate read 1.05.
- **SIH race.** RS congenital admissions read amarela 11.6× and parda 0.36× (the documented code 04 defect, pegasus_data open question 66).
  It is declared on the column in pegasus_data and carried on every race row.
- **Trends.** An APC over one event read 9×10¹⁶ %/year; provisional years (SINAN closes over three years) pulled
  slopes down.

**Read and explained.**
- **RS congenital admissions, 66 (2017) → 118 (2018).** Two hospitals began coding P37.1: Hospital Universitário de
  Canoas, 0 → 11 → 50, and Hospital Materno-Infantil Presidente Vargas, 0 → 17 in 2019. Recording, not incidence.
- **National trend** (lake, CLASSI_FIN 1, per 1,000 live births, 2019–2024): gestational 2.23 → 4.91, congenital
  0.58 → 1.52. The rise is not explained by tests or criteria: SUS serology is flat at about 5 M tests a year, and the
  laboratory-confirmed share is stable (97 %, 83 %). Congenital admissions per 1,000 live births rose 4× over
  2010–2024, before SINAN existed (2019), with deaths flat at about 30 a year. Newborn heel-prick IgM begins in 2022.
- **States, 2023.** Congenital rates range from 0.17 (PA) to 5.96 (TO) per 1,000 live births. The confirmed share of
  notifications ranges from 6 % (AC) to 97 % (RR): surveillance practice, before biology.

**Still open.**
- The prospective band of RS's P37.1 admissions is wide (sd 84 around about 127, 2021): one place, Canoas, carries a
  variance of 5,316 (46.9 expected, φ 0.42), the hospital that began coding P37.1 in 2017–2018. That is the data's own
  volatility, not the model's; a band without that institution's step would be a quarter as wide.
- Capture has no total under imperfect linkage (OQ 18).
- Santa Maria 2018 is found only through its declared hypothesis.
- A scan's Gumbel-extrapolated p reaches 1e-83 from 200 replicates.

**Known answers after the fixes.**
- **Porto Alegre, May–July 2024, read in months.** Against the monthly prospective expectation trained on 2016–2023:
  - notifications by residence: 1,890 against 23.7 (80×), supported (Holm p 4e-5);
  - confirmed cases: 246 against 5.2 (47×), supported;
  - by place of infection 31×, by place of notification 62×, both supported;
  - by place of care: 8×, p 0.051.
  The annual reading had given 1.6×, not supported.
- **Santa Maria 2018** stays supported in hospital data: B58 admissions 4.4× by residence, pregnancy admissions 20× by
  place of admission. Serology by residence, adjusted for the share of tests placed, is no longer "supported".

**The semantic review of pegasus_data's toxoplasmosis declarations.**
- **One population.** The capture lists had no common population: SIM's list took P37.1 at any age, and 30 % of 2022's
  certificates were of people aged 2 or more. Now all three lists are children under one (NT 133/2022), and each
  list's death is a death of the condition.
- **Protocol citations.** The class 8 deadlines (300 and 420 days) and the probable case are cited from the protocol:
  confirmed cases are a lower bound.
- **Denominator.** "Per 1,000 live births" is stated as a convention and, for the gestational form, a detection rate.
- **Labels.** TOXC and TOXG have no harvested dictionary; their labels, weighed from DATASUS tables, were checked
  against the protocol and are right. EVOLUCAO 1 ("Vivo" in DATASUS's table, "Cura" on the form) keeps both claims.
