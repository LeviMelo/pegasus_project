<p align="center"><img src="assets/brand/pegasus-logo.png" alt="PegaSUS" width="560"></p>

# PegaSUS

**PegaSUS reads Brazil's public health data as one process:** events happening to people, in places, over time. It fits one hierarchical model of that process for the whole country, "normal Brazil", and from it finds **leads**:
- where the data depart from what they should be;
- what the model's own structure reveals;
- how the departures relate.

Each lead carries its size, its certainty, its checks and its replication record. People and AI agents follow leads into studies.

It reads all its data through **[pegasus_data](../pegasus_data)**, the project's data module: DATASUS decoded and labelled, linked records, populations and context.

**State:**
- architecture accepted (2026-10-04); **revision 2** (2026-10-06, ADR-0023): established methods first, model-based detection and relations, validation that characterises, a structured solver with time budgets;
- a v0 engine is built and fitted on SIM, SIH, SINASC and SINAN (`STATUS.md`);
- **development resumes with the overhaul** (`docs/plans/2026-10-06-overhaul.md`), starting with the solver.

| document | what it holds |
|---|---|
| `ARCHITECTURE.md` | **the authority:** objects, mathematics, scans, error control, code, phases |
| `CLAUDE.md` / `AGENTS.md` | how to work in this repository: disciplines, documentation policy |
| `STATUS.md` | the state of the work |
| `DECISIONS.md`, `EVALUATION.md` | decisions and measurements, indexed |
| `OPEN_QUESTIONS.md` | what is still open |
| `GLOSSARY.md`, `RUNBOOK.md` | terms; commands |
| `docs/handoffs/` | what PegaSUS needs from pegasus_data |
| `docs/discussion/` | the reasoning behind the design, and what the 2026 engine actually did |
| `docs/RECOLLECTION.md`, `docs/history/` | the earlier attempts and their documents |
| `studies/` | studies done with pegasus_data (SIAC Mulher 2026) |

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
PYTHONUTF8=1 $PY -m pip install -e . --no-deps
$PY scripts/check_docs.py
```
