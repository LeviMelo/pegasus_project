# The persons step of a study (BACKLOG 6.3, acceptance item 5; 2026-10-11)

**What.** At deep and exhaustive depth, `study._persons` runs the cohort scan (`tools.cohort`) for every read source
whose records are the topic's persons:
- an agravo's own notifications;
- a source read through a declared code list holding the topic's related codes (SINASC's CODANOMAL).

Such a source must also be a person on a usable declared link. Its persons of the latest `PERSON_YEARS` (3) years are
scanned against every person kind they reach, and against the topic's codes on their own record. Results go to
`persons.parquet` and the report's section 3d. A source without such links, or without attributes, is said.

**Run** (`ctl/persons_test.py`, the survey's scope read at deep depth, 2 draws, shared store). SINAN-TOXC 2025: 7,279
cases; 751 and 739 of them (the two draws) reach an SIH admission, and 2 a death certificate (through SIH, the direct
TOXC → SIM run not being stored for 2025). The scan made 16 contrasts over 7 attributes and 2 outcomes, none at q,
in 120 s.

**Found.** Two defects.
- **Persons failed on deterministic runs.** pegasus_data's union of a scope's runs read a `bits` column, which
  deterministic runs (TOXC to SIH) do not have. Each pair of such a run now weighs log2((1 − c)/c) bits at precision
  1 − c, where c is the run's own negative-control chance share (8.7 % for TOXC to SIH 2019).
- **The first draft scanned the wrong cohorts.** It took every source with related codes, so every death of a year
  was tested against HIV on its certificate. Cohorts are now only the topic's persons, and same-record outcomes come only
  from declared code lists, never from mentions.
