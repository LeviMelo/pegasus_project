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
| Group question on a code set (`Session.by_composition`) | a cold SIH item (pneumonia J12–J18, 2014–2023) still in its group question after an hour: a Python pass per row of each composition table | the rows filtered in Arrow; a code set's own codes kept (see below) | SIH A00–A09, one column: 12.5 s; its composition total 2,086,422 = the field's events |

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
- **A lane crash.** The first lane run lost all three workers abruptly, while another process held the GPU. The rerun
  was clean, and a dead lane's items now run again in the parent.

## Not done

- Reading records as Arrow tables (322 MB for four SIH columns a year) where DuckDB could aggregate on the Parquet
  directly.
- Memory per item measured against its cells, for admission by estimate rather than by the free memory now.
- The robust refit and question pass profiled on a cold item: the run was started and not yet read.
