# ADR-0034: an event whose row is a group is read in one exposed cell

**Date.** 2026-10-09. **Status.** Active. Answers OPEN_QUESTIONS 14; revises ARCHITECTURE §3.2 (strata).

**Evidence.** OPEN_QUESTIONS 14: SINAN-SDTA's ill, counted as people by sex and band (pegasus_data decision 0156), fit
with φ 0.066. People arrive an outbreak at a time, so a place-year's variance is about 15 μ².
- **The ill.** Excess, step and trend find nothing. The cluster scan finds 180 answers, 165 of them persistent levels.
  It found none before the gamma quantile's small-shape fix, which this run carries.
- **The same outbreaks counted as outbreaks.** They fit with φ 1.04, and excess finds 30, cluster 172 and divergence 1.
- **What follows.** The outbreak is the unit a change in their occurrence is read on, and it has no sex or age.

## Decision

1. **Groups as events.** pegasus_data declares an event whose row is a group with `persons: false`: SDTA's `outbreak`,
   beside its `case`. An event kind `outbreak` is added. A dataset may refuse its file's shared events with
   `shared_event_types: false`: SDTA's rows are not SINAN's person notifications.
2. **Strata per event.** The strata are chosen per event (`gateway._strata(dataset, event)`), as are the age bands
   (`age_edges(source, dataset, event)`).
   - A group event has no sex or age column.
   - Its events stand in one cell (sex 1, band 0).
   - Its place is the municipality of the entity it is: the outbreak's ID_MUNI_RE, not the notification's municipality.
3. **Exposure.** The assembly puts the whole population of the place in that one cell and leaves every other cell
   unexposed. The fit already fixes unexposed cells at zero, as it does for a mother's male cells. So μ = N_place · rate
   × the place and time effects exactly, and the noise is the field's own NB-P on that cell.
4. **The group question.** It tests nothing on a group event: with one exposed cell it has no degrees of freedom.

## Consequences

- SDTA has two fields: outbreaks (the detection unit) and their ill by sex and band (the burden).
- The ill per outbreak (NU_TOT, a measurement with 0 not recorded) is a mark on the outbreak.
- Twelve gateway readers and the model's assembly pass the event to the strata. A dataset whose events are all
  persons reads as before.
