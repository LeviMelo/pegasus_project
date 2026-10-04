# Status

**2026-10-04.** The architecture is accepted and the repository is set up. No model code exists yet.

**Done:**
- **`ARCHITECTURE.md`:** the authority on objects, mathematics (monolith, estimation, tiers, surprise), scans, error control, use, the harness, code and phases. ADR-0001–0003.
- **Agent rules** (`CLAUDE.md` = `AGENTS.md`), the documentation policy, `scripts/check_docs.py` (green).
- **Package `pegasus_core`,** installed editable in the `pegasus` environment beside pegasus_data. PyTorch reaches the GPU (CUDA 12.1).
- **The handoff to pegasus_data** (`docs/handoffs/2026-10-04-pegasus_data.md`): storage, roles for every column, event types, aggregation with mark accumulators, code structures, proximity graphs, the modelled tier.
- **History:** the earlier documents (`docs/history/`); the redesign questions resolved (`docs/history/open_questions_resolved.md`); the design reasoning archived (`docs/discussion/2026-10-04-design-v0.2.md`).
- **Brand:** the logo, wordmark and mark in `assets/brand/`.

**Next: phase 0** (ARCHITECTURE §12):
1. `gateway`, over pegasus_data's existing aggregates;
2. `store`;
3. the ledger in `control`;
4. the harness: positives, negatives, planted signals, surrogates.

Then phase 1, as pegasus_data delivers roles, event types, structures and graphs. Its first measurements:
- ICD tree pooling, chapter by chapter;
- which proximity graph explains between-municipality variation.
