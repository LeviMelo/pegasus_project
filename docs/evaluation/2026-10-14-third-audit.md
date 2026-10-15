# The third blind audit, on the folder's final schema (Alagoas AMI, 2026-10-14)

**Regime.** `studies/infarto_alagoas` on e899959 (products rewritten from the store), audited by a Sonnet agent that saw
only the folder (`data/handoffs/paper-audit3-brief.md`; draft and `audit.md` in `data/handoffs/audit3_alagoas/`).

**Result.** The arithmetic reproduces exactly: standardised rates, intervals, APCs. 25 gaps, the top ones the sources'
own limits:
- SIM's coverage after 2011 is an extrapolation;
- half the circulatory deaths carry garbage codes;
- admissions are SUS AIHs by processing year;
- the linkage gives shares, not case fatality.

Columns it could not interpret: three, all fixed here. **Fixed in general:**
- trend rows carry their own unit (% a year, joinpoints), the series' rate in `variable`;
- the case mix's `expected` rows state their unit and model;
- a context its scale (`per`, its unit over its denominator);
- each sex's standardised rate on one age standard, the two sexes' ages pooled (male 57.7 and female 35.1 now divide:
  1.64, where the auditor recomputed 1.65);
- a mean's t interval and a median's order-statistic interval;
- a blank measure value is not recorded, no longer outside the domain, and a decimal comma is read;
- the README lists only the measures a folder holds, with no stale `descriptive.parquet`;
- the municipalities view gives the area's ratio its interval and q;
- the geometry is IBGE's intermediate mesh (a municipality's median vertices 12 to 34);
- a run deletes an earlier run's temporary database;
- METHODS says SIM's coverage after 2011 is the source's extension, and that sources.parquet names the server.

Rerun (products only), the folder meets all 23 parts of `body()`. **Left:**
- registration and coding corrections (coverage-corrected rates, garbage redistribution);
- case fatality through the links;
- municipal standardised rates;
- seasonality's last year truncated by processing date.
