# The gateway's readers on one template, shown equal on real reads; the store's dead weight removed (2026-10-14)

**Why.** The gateway review (structure 1-2): nine readers each assembled their key by hand (six without the area, two
without the declaration, one without its code), built the same cell frame, the same reason a cell is in no count, and
the same get -> compute -> put, with nothing stopping two lanes from computing one national table at once.

**What.** `gateway._reader_key` (code, places, declaration, data, lake files, area, then the reader's parts),
`_cells` (records to cells: u, sex, age, weight, the reader's own columns), `_reason`, `_unallocated`, and
`store.cached` (all of a reader's parts stored together; one process computes under a lock beside the entry, the others
wait and read). On it: code_list_counts, monthly_counts, away_counts, linked_counts, cooccurrence, unplaced,
mark_quantiles, mark_values, mark_moments, mark_facility_moments, delay_counts, composition_facility, event_counts'
store, the composition reader's reason. Keys completed: code_list_counts, cooccurrence and unplaced had no lake files,
composition_facility no code. Not done: facility_cube (facility.py), the composition batch's own frame, splitting
gateway.py. gateway.py 2,996 -> 2,987 lines: the template is a structure, not yet a reduction.

**Shown equal.** `scratchpad/reader_eq/run.py` and `run2.py`: 18 reader calls (SIM-DO, SIHSUS-RD, SINAN-LEPT; Alagoas
and Brazil; counts, months, compositions, code lists, away, links, co-occurrence, marks, delays, facility cube of 2.3
million rows) on the code before (d0cd2d7) and after, each cold on its own scratch home: 33 of 33 tables equal but one,
mark_moments' log sums, which differ by at most 1.1e-15 relative (DuckDB's parallel float summation order; the NaN cells
the same). Time per call unchanged (the slowest, mark moments of 7.4 million cells, 24 s).

**The store.** `pegasus-core keys gc`: 182,828 entries no code computes a key for any more (every code value outside the
window of the current and adoptable keys), 33.9 GB, removed; 37,980 live entries (2.8 GB) and 10,347 whose key holds no
code value kept.
