# A study folder's estimates as one schema (plan, 2026-10-14)

**Why.** Two blind audits wrote a paper from the Alagoas folder. What they tripped on was rarely a missing number:
one column meant a rate, a share or a ratio depending on another column; the whole period was told from a year by a
null; an interval's method was in the codebook or nowhere; 15,127 and 15,126 were both "the deaths"; four APCs of
one series. The folder has 22 tables, eleven of which (descriptive, places, seasons, codes, groups, quality,
measures, trends, associated, contexts, related) hold one kind of object, an estimate, each with its own columns,
grown one audit gap at a time in `study._write_products` (about 3,000 lines). A twelfth gap would add a twelfth table.

**The object.** An estimate is a value with its interval about a population in a place and a time:

| part | columns | rule |
|---|---|---|
| what | `field`, `label`, `dataset` | the field read (its id names reader and codes) |
| measure | `measure` (count, crude_rate, standardised_rate, rate_ratio, smr, proportion, mean, sd, quantile, seasonal_index, apc, aapc, correlation, ...), `model` (crude, age-sex adjusted, joinpoint segment, ...) | one vocabulary, each term defined once in the codebook |
| value | `value`, `low`, `high`, `interval` (garwood, fay-feuer, clopper-pearson, t, delta, permutation, exact-poisson, ...), `p`, `q` | an interval always names its method; none when there is none |
| scale | `numerator`, `denominator`, `denominator_kind` (person-years, residents, events, live births, records), `per` (1, 1e3, 1e5), `unit` | a rate has all of them; a count has none but `unit` |
| where | `geography` (national, macro-region, state, area, health macro-region, health region, municipality), `place` (code), `place_name`, `role` (subject, reference, comparator) | one level vocabulary across tables |
| when | `period_kind` (year, period, month, segment), `first`, `last` (YYYY or YYYYMM), | a year is first = last; never a null standing for "the whole" |
| who | `stratum` (sex, age band, race, a code, a composition value, or a combination as `sex=female; age=60-64`) | parsed, not prose |
| against | `comparator` (Brazil, the region without the area, the standard), `standard` | a ratio names what it divides by |

**What stays its own table.** Records that are not estimates: findings (leads with their provenance), hypotheses, the
link runs, persons' cohort contrasts (estimates too: they move once the schema holds RRs), capture, sources, figures,
the standard's weights, the model's cell expectations. The codebook is generated from the schema's vocabularies.

**How.** One constructor (`_estimate(...)`) builds every row and refuses an incomplete one (a rate without its
denominator, an interval without its method); each producer emits through it; the eleven tables are replaced by
`estimates.parquet`, with study.duckdb views giving the old shapes (rates by year, places, seasons) as queries over it,
so nothing is copied twice. `body()` and the report read the one table. Done when: the Alagoas folder and a slice of
another source (SINAN, SINASC) produce it whole, a third blind audit finds no column it cannot interpret, and
`study.py`'s products are shorter than now.
