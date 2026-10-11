# Performance: where a study spends its time, and what was changed (2026-10-11)

Regime: branch `scope-v2`; the shared store and data root; an RTX 4050 laptop GPU (6 GB), 20 logical cores and 31.6 GB
RAM. numpy and scipy run on MKL. Profiles were taken with py-spy (sampling, raw stacks) on the running survey study and
on single calls. Drivers are in the session scratchpad (`ctl/`).

## Measured

| where | evidence | change | result |
|---|---|---|---|
| NB-P dispersion (`_dispersion_power`) | 72.5% of 3,280 samples of the running study: a nested scalar search (P outside, log φ inside), each step a CPU pass over every non-empty cell | (log φ0, P) jointly by L-BFGS-B with autograd's exact gradient over the same binned likelihood (`monolith._nbp_profile`) | SIH A00–A09 (573,280 cells): 6.1 s → 1.6 s, −loglik 0.03 lower (P 1.9168 against 1.9175); TOXG identical; DOFET P37.1 the same likelihood on a flat profile |
| Composition counts | the survey run spent over an hour in SIH's group question, re-reading each year's 11.5 M admissions once per column (12.3 s a read; all columns at once 26 s, but free memory went to zero) | up to four columns from one read (`gateway.COMPOSITION_BATCH`) | identical tables on TOXG 2019's eight columns |
| Query split (pegasus_data `render_groups`) | 19% of one `pg.query` (SIH 2016): a full filter per competence month | one stable sort and contiguous slices (`_partition`) | 1.29 s → 0.72 s, identical groups (pegasus_data branch `perf`) |
| `pg.query` overhead | 4.5–4.7 s a year against 2.8 s for the same columns read raw by DuckDB; the curation YAML is parsed once per process (the first query 4.7 s, the next 2.6–3.2 s) | none: about 1 s a year | — |
| Model device | fits defaulted to the CPU; the GPU served only the relation map | `config.device(cells)`: CUDA when the block's estimate (400 B a cell + 200 MB, measured 246 B) fits 60% of the card's free memory, else CPU; `PEGASUS_DEVICE` overrides | fits: TOXG 5.6 → 3.2 s, SIH A00–A09 4.6 → 3.3 s, φ and P equal to 13 digits; TOXG's question pass 156 → 141 s with the same answers (48 excess, 2 cluster, 107 group, 1 divergence, the same p) |
| Items run one after another | a study's items are independent until its products | lanes (`study._run_items`): a dataset's items in one lane (they share fits and caches), lanes in parallel processes while available memory exceeds `PEGASUS_LANE_FREE_GB` (6), at most one on the GPU, cores shared; a lane that dies is rerun in the parent | TOXG, TOXC and DOFET P37.1: 164.5 s wall against 330.3 s of item time (2.0×); warm, 48.9 against 109.8 s (2.2×) |
| Scope pricing (`study._cost`) | 79 % of 2 min of a scope's resolution: `pg.explore` per item, each a query of the 254 MB catalog, though a scope holds many items per dataset | the catalog's sizes once per dataset and process (`study._volumes`); the lake's coverage still read each time | 1.0–1.5 s a call, then 0 |
| Co-occurrence (`gateway.cooccurrence`), measured and left | assumed: a regular expression over every record (SIH 11.5 M a year) | tried: the categories' prevalence from `code_list_counts`, the regex on seed records only | SIH 2015, dengue seeds: 13.9 s against 12.4 s, the record read dominating; counts shifted 0.09 % (unplaced records). Reverted: the scope's tens of minutes were the catalog calls |
| Place-year dispersion (`place_year_phi`) | 53 % of TOXG's question pass: a profile over P with a κ search at each P, every step `stats.nbinom.cdf` twice over every cell (35 % self) | (log κ, P) jointly by L-BFGS-B; the truncation mass by the regularised incomplete beta directly (exact: 0.0 difference), threaded over the process's cores (`_betainc`: 2 M cells 0.60 s on one thread, 0.19 on four) | TOXG surprise 13.4 → 8.4 s with identical estimates; SIH A00–A09 22.1 → 15.0 s, φ within 0.2 % (cells beyond |z| 3: 940 against 937, at the old profile's own tolerance in P); threads 1.2–1.4× more under load |
| The incomplete beta on the GPU (CuPy) | the NB mass's `betainc` is what remains of the place-year dispersion (30 % of TOXG's question pass) | `cupyx.scipy.special` with the trimmed likelihood's cells resident on the GPU for the whole search, where the process computes on CUDA and the cells number 100,000 or more (`place_year_phi`) | 2 M cells beside busy lanes: 0.16–0.23 s on the GPU against 0.33–0.39 s on eight CPU threads (idle: 0.80 s on one thread), values equal to 2e-13. Shipped per call, the transfers ate the gain (SIH surprise 22.1 against 20.6 s). Resident, SIH A00–A09's yearly surprise is level with the CPU, alternating 17.6/16.8 and 14.3/14.1 s, with z within 1e-8. Its place-year cells (56,000) are under the threshold; a monthly field's (670,000) are not |
| Robust refits never reused (`robust_stored`) | looked up under its tag (v 11) but saved under `robust`'s own stamp (v 9): every session recomputed every block's robust refit (a SIH chapter's is about 15 min) | saved under the key it is looked up by | SIH A00–A09's model with its refit: 26.4 s the first time, 9.4 s the next, the same φ and P |
| Group question on a code set (`Session.by_composition`) | a cold SIH item (pneumonia J12–J18, 2014–2023) still in its group question after an hour: a Python pass per row of each composition table | the rows filtered in Arrow; a code set's own codes kept (see below) | SIH A00–A09, one column: 12.5 s; its composition total 2,086,422 = the field's events |

**Lane admission by measured peaks.** In the survey, admission on free memory alone let lanes grow past it: SIH's lanes peaked at 13.5 and 14.2 GB after being admitted with 9 GB free, and the machine fell to 2.3 GB free. Each lane now records its peak per item (`peak_gb` in provenance). A dataset is admitted by its largest measured peak, or 12 GB when unmeasured (`PEGASUS_LANE_DEFAULT_GB`), against the available memory less what the running lanes may still take. Three small items peaked at 2.46–2.54 GB.

**Link runs before the lanes.** The survey stalled for half an hour: a lane was computing national link runs for
corroboration (`update._ensure_links`; CIHA's deaths to SIM 2023–2025 took 152–723 s each, and SIH's 2024–2025 took 394–444 s), with
11.4 GB held. That lane's group waited behind them, and two lanes reading one link would both have computed it. A study
now makes every item's lakes and link runs once, serially, before the lanes start (`study._prepare_store`, recorded as
`store` in provenance). Its scope lists the runs the store lacks (`link_runs_to_compute`), priced by the measured wall
time that pegasus_data now writes into each run's report (`seconds`).

**Where the survey's five hours went** (`study_toxo_survey9`, 17,850 s; item times overlap across lanes):
- **National link runs inside the lanes, about 2.5 h.** `ciha_deaths_to_sim` 2023–2025 ran twice, in two lanes at once
  (about 3,300 s). `sih_deaths_to_sim` 2024–2025 took 840 s, and `sinan_toxc_to_sih_admission` 2025 took 4,600 s.
  Fixed by the store step above.
- **Paging.** Three lanes held 42 GB on 31.6 GB, and the pagefile grew to 47 GB. Fixed by pausing lanes under
  pressure.
- **Whole chapters fitted for one code.** B58's node is read inside ICD chapter I, so a survey fitted every infectious
  disease, in every place and year, for SIH, SIM, CIHA and SIA-ATD. CIHA I took 1,017 s and ATD I 1,606 s. SIM I and
  SIH I ran an hour and more each before failing, and are uncounted. A survey now reads the topic's nodes as a code set
  of their own; the chapter's context is standard depth's.

## Found on the way

- **A code set's group question counted every event of its dataset.** A code-set field's node is `*`, and the filter
  kept every code. SIH A00–A09's composition would have summed to all admissions, not its 2,086,422. The code set's
  codes are now kept by prefix, as its counts read them. The totals now equal the field's events (SIH A00–A09
  2,086,422; TOXG 86,268). Every group answer of a code-set item before this commit is wrong.
- **Foetal deaths have no age.** DOFET's compositions unallocate every row on age, so its group question reads
  nothing. It should say it does not apply.
- **Robust refits.** A fresh robust refit's index tensors are of the imputed cells (SIH A00–A09: 573,280), while its
  `data` is reset to the real block's (565,938). A cell-level likelihood paired the two. It now reads `fit_data`. No
  production path had called it after the reset.
- **Corroboration read years a source does not publish.** A source whose link was not stored that year fell back to its
  unlinked events, and that read raised `NothingPublished` for TOXC before 2019. SIM-DO's O98.6 and P37.1 items failed
  on it. Unpublished years are now skipped before either read.
- **Lanes pinned to the CPU still computed on the GPU.** The multiscale kernels, the scans and the relation map's
  factors each chose CUDA whenever a card existed, ignoring `PEGASUS_DEVICE`, so every lane's excess question shared the
  card with the lane that held it. On TOXG, warm and with the GPU lane busy, 55 % of the excess question sat in
  `multiscale.peaks`, its hot lines synchronisation points. They now follow `config.array_device()`: the lane's pin,
  else the card. Beside the survey's GPU lane, TOXG's excess question took 209–213 s on the CPU and 287–455 s on the
  card, with the same 44 answers and p-values.
- **The robust refit's dense arrays.** A survey lane in SIM-DO chapter I's robust refit held 23 GB committed with
  0.7 GB resident: it was paging. `robust` built each leaf's expectation as a list and then stacked it; it took the NB
  tail and `_impute`'s excess and deficit over the whole [leaf, place, period] block, several temporaries of it at once.
  These are now filled in place, with the tail computed on the cells above their expectation only. Results are
  identical on TOXG (1 leaf), SIH A00–A09 (one code set) and SIM-DO XVI 2015–2019 (59 leaves): the same flags, φ, the
  same 1,923.5 recoded deaths and the same μ hash. On XVI the arrays are 13 MB and the peak is unchanged (1.5 GB
  traced, 0.68 GB of it the refit's arrowhead solver). Chapter I's are of the order of 0.7 GB each; its peak has not
  been measured yet.
- **A block's years held whole before summing.** `assemble` concatenated every year's counts by every code before
  summing them into cells. SIH's share denominator, all admissions as one field over 16 years, held 18.9 GB and paused
  the survey's other lanes. Each year is now summed into its cells first. Cells are identical (SIH 2018–2019: 393,027
  cells and 23,998,365 admissions, the same hash; TOXG the same); the two-year peak fell from 1.88 to 0.81 GB.
- **Recodings spread over every sibling cell.** `_impute` gives each sibling leaf its share of a flagged excess
  (ADR-0033) over every sex-age group. That grew SIM-DO XVI 2015–2019 from 66,574 entries to 3,280,913: 97 % of them
  under 0.01 deaths, 0.2 % of the mass. SIH chapter I's run out of host memory at 160 M entries. Each share now goes
  whole into the leaf's most expected group, exact at leaf, place and period. On XVI: 210,120 entries, robust refit
  62 → 34 s, φ unchanged, 1,620 against 1,621 cells flagged, μ within 1.2e-4 at the median (p99 7.7e-4, max 0.34 %),
  leaf totals within 0.8 %. Drawing the shares as whole counts (stochastic EM) was tried and rejected: 125,000 entries,
  but a rare leaf's total moved by up to 61 %.
- **A lane crash.** The first lane run lost all three workers abruptly, while another process held the GPU. The rerun
  was clean, and a dead lane's items now run again in the parent.

## Not done

- Reading records as Arrow tables (322 MB for four SIH columns a year) where DuckDB could aggregate on the Parquet
  directly.
- Memory per item measured against its cells, for admission by estimate rather than by the free memory now.
- The robust refit and question pass profiled on a cold item: the run was started and not yet read.

**Disk (later the same day).** A lake build kept each downloaded file beside its Parquet. The data root's disk fell to
19 GB free, against the 40 GB a deep study may download. `gateway.ensure_lake` now builds with `release=True`, which
deletes the build's files once verified partitions hold them (pegasus_data's one release rule; a rebuild fetches them
again). `prune` over the root freed 10.4 GB, to 28 GB free.

**Compositions of a code set (evening).** The quick deep study's SIH lane spent its time building compositions for
SIH's 35 group columns × 9 years, each a table of about 6.9 M cells, to keep B58's. `composition_counts(codes=)` now
reads only the code set's records (pegasus_data `query(rows=)`), and so do `by_composition` and the share reader of a
code-set field. SIH 2017, schooling, B58: 971 rows in 2.9 s against 6,717,778 in 16.5 s, the same counts and the same
unrecorded cells.

