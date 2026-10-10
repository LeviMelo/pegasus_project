<p align="center"><img src="assets/brand/pegasus-logo.png" alt="PegaSUS" width="560"></p>

# PegaSUS

**PegaSUS reads Brazil's public health data as one process:** events happening to people, in places, over time. It fits one hierarchical model of that process for the whole country, "normal Brazil", and from it finds **leads**:
- where the data depart from what they should be;
- what the model's own structure reveals;
- how the departures relate.

Each lead carries its size, its certainty, its checks and its replication record. People and AI agents follow leads into studies.

It reads all its data through **[pegasus_data](../pegasus_data)**, the project's data module: DATASUS decoded and labelled, linked records, populations and context.

**State:** architecture revision 5 (2026-10-10): the win condition is an exhaustive study of one topic from one declaration (ARCHITECTURE §1.4). The code as it is: `STATUS.md`; the ordered work: `BACKLOG.md`.

| document | what it holds |
|---|---|
| `ARCHITECTURE.md` | **the ground truth, the plan and the theory:** purpose and principles, the data space, studies, fields, expectations, questions, relations, interpretation, execution, validation, departures |
| `STATUS.md` | **the map of the code:** modules, stores, commands, interfaces, what works and what is broken |
| `BACKLOG.md` | the ordered work, unit by unit, with its done-when |
| `CLAUDE.md` / `AGENTS.md` | how to work in this repository: disciplines, documentation policy |
| `DECISIONS.md`, `EVALUATION.md` | decisions and measurements, indexed |
| `OPEN_QUESTIONS.md` | what is still open |
| `GLOSSARY.md`, `RUNBOOK.md` | terms; commands |
| `studies/` | studies done with pegasus_data (SIAC Mulher 2026) |

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
PYTHONUTF8=1 $PY -m pip install -e . --no-deps
$PY scripts/check_docs.py
```
