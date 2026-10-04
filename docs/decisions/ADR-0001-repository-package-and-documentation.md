## ADR-0001: One repository for PegaSUS, package `pegasus_core`, pegasus_data's documentation model

**Date:** 2026-10-04. **Status:** active.

**Context.**
- PegaSUS is restarted from first principles. Its data module, pegasus_data (`../pegasus_data`), will be open source, and every input of PegaSUS comes through it.
- The shared conda environment `pegasus` already holds an editable install named **`pegasus`**: the 2026 engine at `LEVI/PegaSUS/src/pegasus`. A new package with that import name would shadow it, or be shadowed.
- pegasus_data's documentation model has worked: one document per purpose, ADRs with evidence, compact measurements, a mechanical consistency check.

**Decision.**
1. **`pegasus_project` hosts PegaSUS.** The package is **`pegasus_core`**; the distribution is `pegasus-core`; the CLI is `pegasus-core`.
   - Siblings: `pegasus_data` (data), `pegasus_view` (frontend).
2. **The boundary with pegasus_data** is ARCHITECTURE §2:
   - pegasus_data holds the observed and modelled data;
   - PegaSUS holds inference;
   - only `pegasus_core.gateway` imports pegasus_data;
   - missing data capabilities are requested in `docs/handoffs/`.
3. **The documentation model is pegasus_data's,** with the author's weight rules (CLAUDE.md §7):
   - ARCHITECTURE is the authority;
   - ADRs only for final decisions;
   - measurements compact and added to existing entries;
   - STATUS rewritten, not appended;
   - `scripts/check_docs.py` keeps the documents consistent;
   - CLAUDE.md and AGENTS.md are identical.
4. **Design discussions are archived in `docs/discussion/`** once superseded. The earlier PegaSUS documents are frozen in `docs/history/`.

**Consequences.** `import pegasus` in the shared environment still reaches the 2026 engine. Nothing in this repository imports it.
