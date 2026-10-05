# Open questions

Unresolved questions only.

- **When one is answered,** the row moves to `docs/history/open_questions_resolved.md`, whole and annotated with its resolution: an ADR, an evaluation, or an ARCHITECTURE section.
- **Questions that are pegasus_data's** live in pegasus_data's own `OPEN_QUESTIONS.md`.

**Status:** `open` · `measuring` · `blocked (on what)`.

| # | question | why it matters | what would answer it | status |
|---|---|---|---|---|
| 1 | **brepi's future.** It stays as is while the leptospirosis paper is in review. What happens to its R engines (INLA, DLNM) and its non-DATASUS adapters (climate, disasters, ANS, REGIC, SNGPC)? | Its adapters belong behind pegasus_data, and its engines may serve as references | the paper's review ending; then a handoff per adapter | open |
| 2 | **Does the Laplace approximation match exact fits** (MCMC or INLA) closely enough, across fields and scopes, for every quantity a lead uses (μ, its interval, the PIT)? | ARCHITECTURE §5.3: an approximation is adopted only after a measured comparison | phase 1 comparison on a random sample of fields and states | open |
| 3 | **The default profile level** (ARCHITECTURE §4.2): an ICD block, or the chapter for sparse blocks? | It sets how age–sex structure is shared, and the cost of §5.1's contraction | held-out deviance by chapter, phase 1 | open |
| 4 | **The agent runtime:** which model and loop drive the tools, and the MCP server's shape | ARCHITECTURE §9.3, phase 3 | a phase-3 design note | open |
| 5 | **A travel-time network** between municipalities (roads, rivers): which source, and whether it beats the care-flow graph | One of the proximity graphs (ARCHITECTURE §4.3) | pegasus_data acquisition; held-out comparison | blocked (pegasus_data) |
