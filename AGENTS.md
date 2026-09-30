# CLAUDE.md — pegasus_project

`AGENTS.md` is a byte-for-byte copy of this file.

1. **PegaSUS is being redesigned from first principles with the author.** The
   earlier attempts (`docs/RECOLLECTION.md`) are an inventory of ideas and
   lessons, never an architecture to assemble. Until the design is settled,
   record choices as open questions (`OPEN_QUESTIONS.md`), not decisions.
2. **Data comes through `../pegasus_data`**, with its interpreter
   `C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe` and `PYTHONUTF8=1`.
   Nothing here downloads from DATASUS directly.
3. **Studies live under `studies/<name>/`,** each with its scripts, results and
   a journal that holds the claims and the numbers behind them. Every number in
   a text carries its measure, interval and denominator, and names the data
   version it came from.
4. **Check a fact before stating it;** mark what was measured and what was
   inferred. A number that looks implausible is a bug report until shown
   otherwise.
5. **Never act outward as the author** (push, publish, submit) without explicit
   authorisation. Commit on branches; the author merges and pushes.
