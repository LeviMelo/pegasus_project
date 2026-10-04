# DECISIONS.md

The index of accepted decisions. One file per decision under `docs/decisions/`.

- **A decision is recorded only when final,** with its evidence.
- **A later decision supersedes by its own record,** and the earlier record's status changes.

| ADR | date | decision | status | relation |
|---|---|---|---|---|
| [ADR-0001](docs/decisions/ADR-0001-repository-package-and-documentation.md) | 2026-10-04 | `pegasus_project` hosts PegaSUS as package `pegasus_core`; pegasus_data is the only data path; pegasus_data's documentation model, with the author's weight rules | active | — |
| [ADR-0002](docs/decisions/ADR-0002-the-architecture.md) | 2026-10-04 | The architecture: one hierarchical model of the marked point process (the monolith), expectation tiers, surprises, scans, error control with a ledger and replication, use as a survey, a validation harness first; the design's open calls settled | active | ARCHITECTURE.md |
| [ADR-0003](docs/decisions/ADR-0003-compute-stack.md) | 2026-10-04 | PyTorch on CUDA, scipy sparse, Arrow/DuckDB/polars, numba; no dense object larger than the population tensor | active | part of ADR-0002 |
