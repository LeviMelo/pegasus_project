# Case fatality, and the folder in a paper's order (2026-10-14)

**Case fatality** (`study._case_fatality`): read from the outcome codes pegasus_data now declares fatal (pegasus_data ADR-0191 there,
73 columns). It is computed on the cases; a notification's is read on its confirmed cases. Output: crude by year, sex
and age band (Clopper-Pearson), adjusted for age and sex (binomial regression, marginal standardisation to the
period's case mix), and the adjusted odds ratio per year. Alagoas, infarction admissions (I21-I22, SIH MORTE),
2014-2023, `--products-only` on aeaee1a plus the working tree, log `data/probes/infarto_cf.log`:

| | estimate | 95 % |
|---|---|---|
| whole period | 16.1 % (1,504 / 9,324) | 15.4-16.9 |
| male / female | 14.9 % / 18.0 % | |
| adjusted 2014 → 2023 | 19.0 % → 14.4 % | |
| adjusted OR per year | 0.958 | 0.940-0.977 |

Women's higher in-hospital fatality and a falling trend are the published pattern for AMI in SUS. The adjustment
barely moves the yearly values: the case mix was stable.

**Paper order.** `report.html`: summary of the estimates, descriptive (rates, trends, municipalities by smoothed
ratio, case fatality), analytic (ecological associations, declared hypotheses, persons), data quality, then
"Exploratory signal detection (hypothesis-generating)", scope, methods, provenance. METHODS.md follows the same
order. The map gains the smoothed-ratio panel, and the B1 departure panel is labelled exploratory. The AAPC of a
standardised series had been labelled "crude rate"; fixed. body() requires case fatality wherever an outcome declares
its fatal codes.
