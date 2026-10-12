<p align="center"><img src="assets/brand/pegasus-logo.png" alt="PegaSUS" width="560"></p>

# PegaSUS

**PegaSUS reads Brazil's public health data as one process:** events happening to people, in places, over time. It fits one hierarchical model of that process for the whole country, "normal Brazil", and from it finds **leads**:
- where the data depart from what they should be;
- what the model's own structure reveals;
- how the departures relate.

Each lead carries its size, its certainty, its checks and its replication record. People and AI agents follow leads into studies.

It reads all its data through **[pegasus_data](../pegasus_data)**, the project's data module: DATASUS decoded and labelled, linked records, populations and context.

**State:** architecture revision 5 (2026-10-10): the win condition is an exhaustive study of one topic from one declaration (ARCHITECTURE §1.4). The code as it is: `STATUS.md`; the ordered work: `BACKLOG.md`.

## Run a study

A study is one declaration (`studies/*.yml`; every key in ARCHITECTURE §3.1). A depth (`survey`, `standard`, `deep`,
`exhaustive`) presets the choices below, and any of them can be set by hand to make a study smaller or larger:

```yaml
study: toxoplasmosis_rs
topic: {seeds: {icd10: [P37.1], sinan: [TOXC]}, only: [SINAN-TOXC, SIH-RD, SIM-DO]}  # what, and which sources
period: 2015-2023
where: RS                 # Brazil, states or municipalities: fits, graphs and leads are the area's
depth: deep
related: 1                # how many related codes to read beside the topic's own, strongest first
readers: [compositions, linked]   # which kinds of fields beyond counts
questions: [excess, group]        # which questions to ask of every field
relations: [fields]       # relations among the fields; add contexts, screen
persons: true             # the cohort scan and capture-recapture over linked persons
replicate: true           # test the leads on the later years they were not selected on
nulls: quick              # the tests' null worlds: quick, standard or precise
```

```bash
pegasus-core scope studies/toxoplasmosis_rs.yml   # what it would read, why, and the minutes behind each choice
pegasus-core study studies/toxoplasmosis_rs.yml   # run it; the folder lands beside the declaration
pegasus-core audit studies/toxoplasmosis_rs       # the folder against the win condition's acceptance items
```

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
