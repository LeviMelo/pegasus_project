# The run register, the `pegasus` command and the window's read models on the real stores (2026-10-15 to 17)

**Purpose.** Check that what ADR-0038 built works on the real workspace, stores and lake, from the command line and
from the window (pegasus_app), and fix what does not. The checks were run on commits `1c68dbe` to `2c3e2ef`, with the
real `pegasus_home` and data root, on 2026-10-15 and 2026-10-17. A separate project held 13 GB of RAM throughout.

**The run register** (`jobs`)
- A two-command run (40 s, then exit 3) ran detached and was followed live in the window. It was recorded `failed`
  with "a command exited with 3"; its items, memory samples and log were shown.
- A stopped run's child process was gone after `stop`, and a run whose process was killed from outside was recorded
  `lost`.
- A study's pricing ran as a `scope` run in 61 s (leptospirosis RS: 2 read, 27 not read, 14.0 min estimated).

**Defects found and fixed in general**

| found on | defect | fix |
|---|---|---|
| a products run of mortalidade_infantil_al | it waited inside pegasus_data's 4 GB free-memory floor, and the window showed it queued with no reason | the wait is made before the slot is taken, each reason an `admission` event: slots held, the floor, or the room beside running jobs |
| the same | a products-only run asked for a lane's 8 GB though it runs no lane | its own last measured peak, else its process and 1 GB (3.0 GB) |
| the same, stopped while admitted | the run deleted the old products at its start, so stopping it left the folder with three files | a run writes `<folder>.partial` and puts it in place whole at its end; the person's files (plots) move with it |
| pricing a finished study | the priced scope overwrote the `scope.yml` the folder's report was made from | a priced scope is written beside the declaration (`NAME.scope.yml`); only runs write the folder |
| a plot of `rates` | a query matching no rows (a stratum named wrong) saved an empty plot | an empty query is refused |
| a map | d3 read GeoJSON's counter-clockwise rings as the globe less each municipality, and the table's `u` (text) never joined the boundaries' `u` (number) | rings rewound for d3, keys compared as text |
| the table browser | sort ties came in the database's order, so a page could repeat or skip rows | ties are broken by every other column |
| lepto_rs_check run detached | a lane run in the study's own process checked its parent (the shell that started the run, gone at once) and stopped before its first item: lanes 0 s, no steps, the body whole only because the store held every fit; the provenance then miscalibrated other studies' estimates (one declaration priced 6.7 and 20.4 min) | a lane checks the study's process, named by it; rerun: both items ran, each step said with its seconds (`step` events) |

**Readings, each against the files.** The Alagoas readings are the folder's existing rows; the folder predates
the label fix, and the rebuild below writes it again.
- Records from the lake only, with labels:
  - SIM-DO 2022, Alagoas residents read from the national partition: 23,122 records, `CONTADOR` hidden;
  - SINASC-DN 2022, Alagoas residents under 1,000 g: 256 records;
  - SIM-DO 2024 refused as the reserve's.
- `study compare`: infant mortality 2014-2023 is 13.5 per 1,000 live births in Alagoas (6,686 deaths) against 12.4 in
  Brazil (347,228).
- Plots rendered by vl-convert:
  - the Alagoas smoothed-SMR map;
  - a rate series. The editor's pile-up warning showed the first version of this series mixed two fields in one line,
    and it was redrawn.
- The lead register: 96 of 169,805 leads are signals replicated at R1 or better.
- The catalog: 165 datasets in 24 systems, 93 with event types.
- The window: opened on WebView2 at 150 % display scale. It is now maximized: unmaximized, the page had 960 CSS px.

**Rebuild of mortalidade_infantil_al** (products only, commit `2c3e2ef`, 2026-10-17):
- admitted at once with 3.0 GB stated, peak 2.39 GB;
- 131 s: scope 29 s, store 5 s, products 97 s, 17 products and none failed;
- 21 of 21 parts of the analytic body met;
- the folder put in place whole, no `.partial` or `.old` left;
- the condition's label written clean ("death: infant death (deceased.age_years < 1)"), where the folder of
  2026-10-15 03:41 held its encoded event name;
- the period's rate unchanged at 13.5 per 1,000 live births.

**A new study through the window's service, end to end** (2026-10-17, commit `ccc7901`): suicide (X60-X84) in
Alagoas, 2019-2023, SIM-DO alone, survey depth.
- It was created by `POST /api/studies`, a key set with the declaration's comments kept, saved, and priced as a run
  (8.2 min, 2 read, 25 not read).
- It was started by `POST /api/runs`. The run outlived the service's restart. Its lane fitted the new code set (41.6 s)
  and asked its questions, and each step was said.
- 20 of 20 parts of the analytic body; peak memory 3.05 GB.
- 5.2 per 100,000 person-years (835 deaths, 95 % 4.8-5.6), one of the country's lowest state rates, as published.

**Every route on every study.** One request to each route the window reads, on every study of the workspace (556
requests). On the first pass:
- the table list failed with a 500 on two folders written before 2026-10-14 (their views read another checkout's
  paths). Each table is now listed with why and the command that writes it again;
- the ledger's summary took 16 s on each call. It is now read once per state of its parts.

After the fixes, none failed. Three calls were slow:
- the register's first read (18 s) and the ledger's (15 s), then kept;
- a national scope's 1.5 MB YAML, 7 s in the pure-Python parser and 0.4 s in the C one, now used.

**Open: the estimate of a new code set's lane.** The window shows each phase against its estimate, and on
suicidio_al the two disagreed:
- the lanes phase was estimated at 1.1 s and took 64 s, because a code set's fit had never been stored (fit 41.6 s,
  questions 19 s);
- the whole run was estimated at 8.2 min and took 3 min 43 s.

The estimator (`study._estimate`, BACKLOG 9.1) under-prices an unstored code-set fit and over-prices the fixed phases.

