# History: the documents of the earlier PegaSUS

**Frozen copies, gathered 2026-10-04.** These are read for reasoning, never as instructions. `RECOLLECTION.md` (this folder) is their inventory, and `2026-10-discussion/2026-10-03-what-was-built.md` says what the engine actually ran.

| folder | period | what | copied from |
|---|---|---|---|
| `2026-04_plans/` | April | the first theory and the data-substrate plan | `LEVI/projects/PegaSUS/` |
| `2026-05_formalisation/` | 25–30 May | the public framing and PIBITI grant (`PegaSUS*.docx`, `Planos_*`); the five formalisation dialogues and the memorandum thesis; miniPegaSUS v0.9 | `Downloads/` |
| `2026-06-07_engine/` | 31 May – 13 July | the engine repository's documents: MSD (12 June), MSD-I/II/III, the Architecture Addendum, Conceptual Foundations, Disease Semantic Axis, the plans, the audits, the math critique and its steelman, the roadmaps, the handoff, the north star, the finding ontology, the module maps | `LEVI/PegaSUS/`, `LEVI/PegaSUS_MSD.md`, `Downloads/PEGASUS_CONCEPTUAL_FOUNDATIONS.md` |

**Not here:**
- **The engine's code**, which stays in `LEVI/PegaSUS`.
- **The frontend plan** (`PLAN_front_pegasus.md`), which belongs to `pegasus_view`.
- **pegasus_data's own history**, which stays in `pegasus_data/docs/history`, where its code cites it.

---

## Moved here on 2026-10-10 (documentation restructure)

On 2026-10-10 the active documents were reduced to `ARCHITECTURE.md` (ground truth, plan, theory), `STATUS.md` (the map of the code), `BACKLOG.md` (the ordered work), the indexes `DECISIONS.md` and `EVALUATION.md` with their folders, `OPEN_QUESTIONS.md`, `RUNBOOK.md` and `GLOSSARY.md`. What the new documents superseded is here, moved with `git mv`, unedited (the paths inside them are those of their time). Read for reasoning, never as instructions.

| now at | was | why it is history |
|---|---|---|
| `ARCHITECTURE-rev4-2026-10-07.md` | `ARCHITECTURE.md` | revision 4, replaced by the rewritten `ARCHITECTURE.md` (its module map moved to `STATUS.md`) |
| `STATUS-2026-10-07.md` | `STATUS.md` | the state of 2026-10-07, replaced by the code map; its register "Architecture learned from results" and its dormant-items table are read here |
| `2026-10-discussion/` | `docs/discussion/` | the design reasoning of 2026-09-30 to 2026-10-07 (assessment, what the 2026 engine built, design v0.2, the revision reviews, the whole-system review and survey) |
| `2026-10-discussion/architecture_coverage.md` | `docs/architecture_coverage.md` | the audit of 2026-10-05, superseded by `STATUS.md` and the new architecture |
| `2026-10-plans/` | `docs/plans/` | the package designs (O1-O7, fields from roles, questions and methods, robust expectation) and the work plan of 2026-10-07 (units S0-S7, P1-P3, B3-B5 with their done tables), superseded by `BACKLOG.md` |
| `2026-10-handoffs/` | `docs/handoffs/` | requests from PegaSUS to pegasus_data, 2026-10-04 to 06 (all taken up there) |
| `2026-10-handoffs/data/` | `data/handoffs/*.md` | per-front hand-off notes of the 2026-10-05 fronts (the gitignored `data/` scripts they describe stay in `data/`; its build logs `cnes_*.log/json` stay in `data/handoffs/`) |
| `digests/` | `docs/digests/` | extractions of the April-July 2026 engine's documents, with `RECOLLECTION.md` |
| `RECOLLECTION.md` | `docs/RECOLLECTION.md` | the inventory of the earlier PegaSUS attempts (April-July); an inventory of history, not a live memory |
