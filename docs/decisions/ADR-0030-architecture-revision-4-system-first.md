# ADR-0030: Architecture revision 4 — the whole system first

**Date.** 2026-10-07. **Status.** Active. Revises ARCHITECTURE §1.2 (goals, new), §12 (the roadmap), §3.2 and §4.4 (fields from declarations), §9.3 (the state computed once), §11.1 and §13. Supersedes the order of work of ADR-0029 (N1 → N2 → O6 → O7 → O8); its six stages stand.

**Evidence.** `docs/discussion/2026-10-07-whole-system-review.md`: the stage-ordered overhaul deepened the counts through stages B–D while persons, marks, race, institutions and use stayed absent or stranded. The author adopted it the same day (proceed as devised; agents and MCP stay at S7). The evening's survey (`docs/discussion/2026-10-07-survey.md`) measured how far the code had moved from the documents and brought §11.1 and §13 to it.

## Decision

1. **Packages S0–S7, each end to end before the next** (ARCHITECTURE §12): declared fields, a fitted expectation, the questions, ledgered leads with their method record, stage E's independent tests, and a reading. Depth (D) only where a reading needs it.
2. **Fields come from pegasus_data's declarations** (§3.2): no field names a variable; a new system or column needs a declaration, not code.
3. **No new capability before S1's acceptance on real data** (documented positives for a measure and a composition) and the survey's open defects (its §2) are fixed or recorded in §13.2.
4. **The full survey is the default reading** (§1.2, §9.3). Speed comes from computing each object of the state once, keyed by content, under one orchestrator (`docs/plans/2026-10-07-work-plan.md` §2), never from reading less. Amended the same day: a first draft left use and cost to an author's ruling and proposed bounding readings by budget; the author rejected both (the agent decides; slowness is a defect of the code).
5. **Work proceeds in units** with contracts and definitions of done (`docs/plans/2026-10-07-work-plan.md`), one at a time.
