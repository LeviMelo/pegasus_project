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

**Record conditions** (pegasus_data ADR-0193; here `topic.seeds.records`, the condition in the event's name).
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
