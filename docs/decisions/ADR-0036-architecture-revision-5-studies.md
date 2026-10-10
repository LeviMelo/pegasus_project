# ADR-0036: Architecture revision 5 — studies, declared and exhaustive

**Date.** 2026-10-10. **Status.** Active. Replaces ARCHITECTURE revision 4 (archived as
`history/ARCHITECTURE-rev4-2026-10-07.md`); supersedes ADR-0030's order of work (packages S0–S7), now `BACKLOG.md`.

**Evidence.**
- **A live assessment of the running system** (`data/assessment/2026-10-10-capability-assessment.md`, a Sonnet agent
  exercising every user-facing feature on real data):
  - the data layer works and is fast;
  - the modelling machinery runs;
  - the researcher's value chain mostly does not. The lead register's top ranks are artefacts, only four datasets were
    ever surveyed into it, the output needed a developer to read, `alarms` was broken, and nothing was exported.
- **A day-long review with the author,** carried through one reference case (a researcher's study of toxoplasmosis).
  It showed:
  - investigation needed hand-written plans and command sequences;
  - "exhaustive" meant only what a plan named;
  - the question registry mixed field kinds, supports, references and modes with phenomena;
  - relations were three unrelated tools;
  - a facility-concentrated excess was treated as an artefact although it is often real;
  - the models and expectations were computed but never handed over;
  - large public sources (the DEMAS API's 113 endpoints, ANVISA's medicine data) were outside the data space.
- **What the toxoplasmosis sources hold, measured:** every SINAN publication of TOXG/TOXC carries the same 38 columns.
  The Ministry's Nota Técnica 133/2022 states the notification form has no disease-specific fields, so the clinical
  depth of a study has to come from other systems.

## Decision

1. **The product is a study.** A researcher writes one declaration (topic seeds, period, place, grain, depth,
   hypotheses) and receives one study folder: data views, descriptive tables, model cards, expectations, findings,
   stories, relations, persons, quality, figures, a report, provenance (ARCHITECTURE §3). No command sequences, no
   agents; the MCP server is parked.
2. **Depth is the only lever** (survey, standard, deep, exhaustive). Every depth fills the same folder.
3. **The scope is resolved from the seeds, generally** (§4):
   - the concept index across code systems, built from tables the sources publish;
   - every dataset holding the codes in any role;
   - related codes learned from co-occurrence on records and persons;
   - person paths through viable links;
   - every applicable context.
4. **Seven field kinds** (§5): count, measure, composition (care flows included), interval, ratio, linked share,
   capture. Plus quality fields, the facility and place-of-infection supports, and every composition column as a group
   dimension.
5. **Nine components, one question each** (§7):
   - the list: level, transient, step, trend, seasonality, spatial coherence, propagation, group heterogeneity,
     relation;
   - each is paired with the tier it is tested against;
   - methods estimating one component are merged, never counted twice;
   - share, institution, divergence and prospective are re-cut as a field kind, a support, a reference and a mode.
6. **Relation is the cross-structure of two fields' departures** over distance, lag, scale and group, with surrogates
   that keep each field's own structure (§8.1). It replaces `compare`, `relation`, `joint` and the map's pair test as
   separate tools.
7. **Interpretation:**
   - a facility-concentrated departure is an *institutional finding*, read with the facility's facts, not an artefact;
   - every finding carries a context profile;
   - stories are the report's unit;
   - data quality is a finding (§9).
8. **References, not copies.** A study references the lake and store and pins what it uses; only `export` copies,
   the whole folder by default (§3.4, §3.6).
9. **Intake: the most complete source wins.** An aggregator is used where it serves the original's full breadth;
   otherwise the original is taken directly, with the aggregator as fallback, decided by a measured source assessment.
   A publication audit records, for every dataset, that what is served is all that exists (§2.3).
10. **Source definitions and caveats are declarations** that every study inherits (§2.4).
11. **The documentation roles change:**
    - ARCHITECTURE.md is the ground truth, plan and theory;
    - STATUS.md is the map of the code;
    - BACKLOG.md is the ordered work across both repositories;
    - superseded plans and discussions are archived under `history/`.
12. **The win condition** (author): an exhaustive study of toxoplasmosis from one declaration, accepted by the
    criteria in BACKLOG.md.

## Consequences

- Most of revision 5 is unbuilt; BACKLOG.md orders it. Phase 1 puts the interface and the product over today's
  machinery first.
- pegasus_data grows with it:
  - the source assessments, the publication audit and source definitions;
  - SISAGUA, medicines, SIASI, primary care and the remaining DEMAS families;
  - the concept index;
  - new links and the DSEI support.
- The lead register and `update` plans become a study's internals; `report`, `dossier` and `verdict` are replaced by
  the study report.
- Code comments citing revision 4's sections stay valid against the archived document until the code is touched.
