# Unrelated topics end to end, and topics defined by a condition (2026-10-15)

**Purpose.** Check that a person can go from a question to a paper's folder on topics the system was not tuned on, and
fix what breaks. The studies were written with the new `pegasus-core search` / `new`:
- leptospirosis in RS (SINAN);
- suicide in RS (SIM, SIH);
- dengue in GO (a national SINAN file for a one-state study);
- tuberculosis in PE;
- infant mortality and low birth weight in AL (record conditions).

Each ran on the working tree over `1c75315`, with the real stores and the adoption window; logs are
`data/probes/chain_*.log`, `lepto_rs_check*.log`.

**Defects found and fixed in general**

| found on | defect | fix |
|---|---|---|
| leptospirosis RS | the joint ecological model on `contexts: auto` held 63 contexts, a temperature and its monthly maximum and minimum among them; every interval was 0 to ∞ | a rank-revealing QR drops the combinations, then the largest variance inflation over 5, one at a time, each named; the pseudo-inverse's inflations had looked finite on a singular design |
| suicide RS | each of sixty single-context negative-binomial fits re-estimated its dispersion; the Newton fallback held the products for half an hour | the dispersion is estimated once from the field's null model, and every regression is a GLM at it; the univariate rows carry a BH q across contexts |
| suicide RS | SIH records self-harm (X60-X84) as a secondary diagnosis: 7 primary records in ten years, so the study read no admission | a code set is also read anywhere on its records, once per record (`code_list_counts(codes=)`), as one field: the multiple-cause reading |
| leptospirosis RS | at survey depth (`triage: false`) the body required recording classes | the findings part follows the declaration's triage |
| dengue GO | a national SINAN file is 2.6 GB against a survey's 2 GB, so every item was deferred and an empty folder was written | `scope` says what to set, and `study` refuses a scope that reads nothing |
| SISAGUA (pegasus_data) | a month-grain context entered a year as one of its months | `context_field` sums a `law: sum` field over a place-year's rows of a usable status |
| infant mortality AL | a declared exposure without its evidence failed the report and METHODS | the condition's exposure carries the declaration as its evidence |

**Case fatality on a notification** (leptospirosis, RS, 2019-2023, confirmed cases):
- 4.8 % (95 % 3.9-5.9), 90 of 1,878, with 184 outcomes not recorded;
- adjusted odds ratio 1.11 a year (p 0.11).

**Record conditions** (pegasus_data pegasus_data ADR-0193; here `topic.seeds.records`, the condition in the event's name).
- Infant deaths in Alagoas, 2014-2023 (deceased.age_years < 1, per live birth): 13.5 per 1,000 live births (13.2-13.9),
  15.3 in 2014 and 13.6 in 2023. The deaths of unknown age are a completeness row.
- Low birth weight in Alagoas: 38,473 births over the period. The case mix:
  - 38 % born at 32-36 weeks, 41 % at 37-41;
  - 52.6 % by caesarean;
  - 4.1 % with no prenatal visit.

**Dengue in Goiás, 2019-2024** (survey):
- every body part met;
- the 2024 epidemic at 4,542 probable cases per 100,000;
- case fatality 0.10 % over the period (853 deaths) and 0.14 % in 2024, adjusted odds ratio 1.12 a year (1.08-1.17).

**Suicide in RS, 2014-2023** (standard): SIM's rate 12.2 per 100,000 person-years, the country's highest, as published.
Its SIH fields failed because the shared lake held SIH for only 4 states while the catalog recorded all 27 (pegasus_data
2026-10-15, lake catalog drift). A year is now free only when every state it publishes is in the lake; the SIH lake is
being rebuilt.

**Mortality after admission** (pegasus_data's cohort link `sih_admissions_to_sim`, pegasus_data ADR-0194): Alagoas,
infarction (I21-I22), 2014-2023, the area's residents admitted in its hospitals.
- 30 days: 18.1 % (17.2-19.0), 1,363 of 7,526; 17.7 % less the link's coincidences.
- One year: 29.4 % (28.3-30.4); 24.9 % less the coincidences.
- In hospital, from SIH's own flag: 16.1 %.
- The code set anywhere on the admission gives the same within 0.3 points.

The folder holds every body part.

**Spatial autocorrelation** of the smoothed ratios (`_spatial_autocorrelation`, esda), leptospirosis in RS:
- global Moran's I 0.32 for the notifications and 0.23 for the cases (p 0.001);
- local Moran clusters at q 0.05, Benjamini-Hochberg across 497 municipalities: 8 high-high and 16 low-low
  (notifications), 4 and 11 (cases).

At 999 permutations no local p fell under 0.001, so BH passed no case cluster; the local test now draws 9,999.

A notifiable agravo's fields are named by their condition code ("notification (A27 Leptospirose)"), and Table 1's
age bands run in age order.

**The gate's toxoplasmosis slice** (RS, deep) failed one lane on the rebuilt lake. SIA-PA has no lake; its
serology is read from an extract of its codes. The institution question read the facility cube of the whole type,
4.5 GB a year, and a lane may not download. Changes:
- `_records` now reads a code set from the extract that holds it, cut to the area in Arrow;
- a question whose quantity is undefined for a field raises `questions.NotDefined` and is recorded as not read:
  - the share of all events where there is no all-event total (a SIGTAP code set);
  - an establishment's whole activity where the lake does not hold the type whole;
- one rule (`gateway.lake_whole_years`) decides a whole lake year for the scope and the readers.

**After the lake's rebuild**, three more paths read past the lake or the extract, and each is fixed in general:
- A linked share's own link was missing from the links its plan reads. Its stale runs (sim_maternal_deaths_to_
  admission, nine years) were neither priced nor computed before the lanes.
- Seasonality read a code set's whole type by month; `monthly_counts(codes=)` now filters where the records are held.
- The institution question needs an establishment's whole activity. Where the lake does not hold the type whole (SIA-PA)
  it is not defined and is said so.

With these, the toxoplasmosis deep slice (RS 2014-2023, eight sources, linked shares, persons) holds all 27 parts of the
analytic body from a products run that may not download. Its first gate run went over its cap (58 min against 28.9) on
the one-time recomputation of the stale link runs, priced from older and faster runs.
