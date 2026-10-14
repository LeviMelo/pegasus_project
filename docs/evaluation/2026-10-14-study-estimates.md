# A study folder's estimates as one schema; one rule for what a reader's cells are (2026-10-14)

**Why.** Two blind audits wrote a paper from the Alagoas folder and tripped on reading, not on missing numbers: one
column was a rate, a share or a ratio according to another; a null stood for "the whole period"; an interval's method
was in the codebook or nowhere (docs/plans/study-estimates.md). Separately, the survey asked `share_excess` of every
support reader and logged a failure on each run: the lens refused the reader, the survey did not know it would.

**What.** The ten estimate tables (descriptive, places, seasons, codes, groups, quality, measures, trends, associated,
contexts) are one `estimates.parquet`. Each row is one estimate whose `measure` comes from one vocabulary (`study.MEASURES`,
printed in the README). An interval names its method, a rate names its denominator, kind and scale, and time is
`period_kind`/`first`/`last`. `_estimate_row` refuses an incomplete row and types every column (`ESTIMATE_TEXT`,
`_NUMBER`, `_INT`). A municipality's code beside "BR" in `place` had failed the table on the first full run.
study.duckdb's views `rates` and `municipalities` give the wide shapes, and `body()` reads the one table.
`questions.basis`/`not_read` declare what a reader's cells are and which methods read them: a method's kinds and bases
(`share_excess`: residence and residents) and a question's `quality` flag. One rule replaces the kind check,
`QUALITY_QUESTIONS` and the lens's own refusal; the survey, the harness and the lens apply it alike.

**Shown.** The Alagoas study (SIM-DO and SIH-RD, I21-I22, 2014-2023): the lanes on the full run (the stored fits and
answers adopted, `PEGASUS_ADOPT`), then the products alone from them (`pegasus-core study --products-only` since, 291 s, no
product failed). `data/probes/estimates_compare_20261014.txt` counts every number of the ten old tables (the 16:50
run, d0cd2d7) and finds each in estimates.parquet, with nothing new: rates 65,715, municipalities 51,714, codes 1,320,
case mix 251,533, completeness 6,010, measures 5,396, trends 22,820, contexts 12,342. The exceptions:
- the seasons' `per_day` and `share`, left out because each is events over days or over the total;
- the associated causes' `records_with_code`, dropped by the first version and restored as a count.
`body()` meets every part but "every step ran", which a run without lanes cannot. The README documents every column.

**The producers emit estimates (second commit).** Every producer writes `_estimate_row`s itself; the converter is gone.
The trends, the ratios to Brazil and to the region's rest, the rate figure, the report and the methods read the estimates.
Two study.duckdb views (`RATES_VIEW`, `MUNICIPALITIES_VIEW`) are one SQL each, which the report also reads. study.py
went from 6,752 to about 6,580 lines, including the codebook's entries for the ten tables. Against the converter's
folder (`data/probes/estimates_compare2_20261014.txt`, the same stored fits), every (section, measure) has the same rows and the same
numbers, apart from what was meant to change:
- a variable is named by its column (`variable`) and its source's name (`variable_label`);
- a standardised rate carries its denominator and its `variance`;
- 70 completeness rows that repeated "events placed" under another name, and as national when they were the area's, are
  gone;
- `records_with_code` is restored.
The first version had dropped the race ratios' trends (979 rows), which the old table had written under the unit "per
standardised ratio, race …". They are back, in the ratio's own unit, their joinpoint named for the ratio (its
permutation p re-drawn under the new name). Their fitted values had been multiplied by 100,000, a ratio of 0.33 written
as 32,612; they are on the ratio's scale now.
Fixed on the way: a run deletes the tables an earlier code wrote (the ten had stayed in the folder and in study.duckdb);
a support reader's standardised rate names the place's residents as its denominator; a perinatal series' joinpoint
fitted rates are per 1,000 live births, as its unit says (they had been per 100,000); a topic's ICD-10 seeds reach a
source's declared code lists (SINASC's CODANOMAL had been reachable only as a related field).
