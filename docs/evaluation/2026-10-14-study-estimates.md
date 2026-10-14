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
answers adopted, `PEGASUS_ADOPT`), then the products alone from them (`scratchpad/run/products_only.py`, 291 s, no
product failed). `data/probes/estimates_compare_20261014.txt` counts every number of the ten old tables (the 16:50
run, d0cd2d7) and finds each in estimates.parquet, with nothing new: rates 65,715, municipalities 51,714, codes 1,320,
case mix 251,533, completeness 6,010, measures 5,396, trends 22,820, contexts 12,342. The exceptions:
- the seasons' `per_day` and `share`, left out because each is events over days or over the total;
- the associated causes' `records_with_code`, dropped by the first version and restored as a count.
`body()` meets every part but "every step ran", which a run without lanes cannot. The README documents every column.
