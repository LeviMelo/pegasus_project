# DECISIONS.md

The index of accepted decisions. One file per decision under `docs/decisions/`.

- **A decision is recorded only when final,** with its evidence.
- **A later decision supersedes by its own record,** and the earlier record's status changes.

| ADR | date | decision | status | relation |
|---|---|---|---|---|
| [ADR-0001](docs/decisions/ADR-0001-repository-package-and-documentation.md) | 2026-10-04 | `pegasus_project` hosts PegaSUS as package `pegasus_core`; pegasus_data is the only data path; pegasus_data's documentation model, with the author's weight rules | active | — |
| [ADR-0002](docs/decisions/ADR-0002-the-architecture.md) | 2026-10-04 | The architecture: one hierarchical model of the marked point process (the monolith), expectation tiers, surprises, scans, error control with a ledger and replication, use as a survey, a validation harness first; the design's open calls settled | active | ARCHITECTURE.md |
| [ADR-0003](docs/decisions/ADR-0003-compute-stack.md) | 2026-10-04 | PyTorch on CUDA, scipy sparse, Arrow/DuckDB/polars, numba; no dense object larger than the population tensor | active | part of ADR-0002 |
| [ADR-0004](docs/decisions/ADR-0004-prospective-surveillance.md) | 2026-10-04 | Prospective surveillance (weekly grain, nowcast from in-record delays, false-alarm-rate alarms, syndromic scans across systems, benchmarked against published alerts) is phase 4 | active | ARCHITECTURE §1, §12 |
| [ADR-0005](docs/decisions/ADR-0005-between-places-null-and-negatives.md) | 2026-10-05 | Between places, the null and the negatives are MSR on the symmetric-normalised graph (Dutilleul measured liberal: size 0.076; raw-matrix MSR null sd 3.5× too small); δ_E = 0.03 (E_b), 0.05 (E_b\|Z) | active | ARCHITECTURE §7.5, §8.4, §10.2 |
| [ADR-0006](docs/decisions/ADR-0006-dispersion-by-region.md) | 2026-10-05 | The place-year dispersion component φ_extra is a hierarchy (field, macro-region, state), each level shrunk to its parent; B1 calibrates 30 of 33 fields (28 with one value, 18 with the block's φ); the block's own φ stays one value; BP keeps it | active | ARCHITECTURE §5.2, §6.2 |
| [ADR-0007](docs/decisions/ADR-0007-replication-by-event-sides.md) | 2026-10-05 | Replication is by event sides A/B/R (50/30/20), R1 = selected on A and standing on a test on B conditional on A's count (a marginal test calls 28-100% of null cells replicated where extra-Poisson variation dominates), R2 recurrence, R3 corroboration by an independent field against that field's own null; the reserve is side R, spent by claims under LOND | active | refines ARCHITECTURE §8.3 |
| [ADR-0008](docs/decisions/ADR-0008-tools-over-mcp.md) | 2026-10-05 | The tools served over MCP (official SDK, optional extra `mcp`, stdio): eight reading tools; one write, `confirm_claim`, guarded three ways | built, paused (use and integration to be planned with the author) | ARCHITECTURE §9.3, §11.1, §12 |
| [ADR-0009](docs/decisions/ADR-0009-bp-predictive.md) | 2026-10-05 | BP's predictive is a mixture over the history's regimes (annual: damped slope; monthly: the fit's years), with the training fit's φ_extra and each place's damped B2 trend; held-out log score annual −1.52 M → −1.37 M, dengue −4.68 M → −1.39 M | active | ARCHITECTURE §6.1, §6.2, §13 |
| [ADR-0010](docs/decisions/ADR-0010-exposure-source.md) | 2026-10-05 | The gateway reads the population from a source parameter (popsvs default, account-2 with its sd of log N, bands 18 vs 17, uncovered cells unallocated, keys carry source and model); account-2 is not better on IX or births deviance, and exposure variance double counts phi: POPSVS stays the default | active | ARCHITECTURE §3.1, §4.1, §13 |
