# ADR-0004: Prospective surveillance is a registered goal (phase 4)

**Date.** 2026-10-04. **Status.** Active. **Decided by** the author.

## Decision

PegaSUS will also run as a **prospective surveillance system**: early alarms on recent data, for every diagnosis code in every system. It is phase 4 (ARCHITECTURE §12), built on the phases before it, not beside them.

## Why

- **Its startup cost is small.** The expectation tiers, the outbreak and space–time lenses, the null and the monthly grain exist already. They reproduce COVID-19 prospectively (tier BP, trained up to 2019) and recover epidemic years retrospectively.
- **Nobody does it.** Dedicated tools watch one disease. Syndromic surveillance across SIM, SIH and SINAN (excess deaths from ill-defined causes, a rise in admissions for a syndrome, an excess seen in all three systems at once) has no existing tool.
- **Control.** The code is ours to change.

## What it needs (not mathematics)

1. **A weekly grain.**
   - Weeks are derived from dates under one rule for every system; SIM and SIH publish no week.
   - They are reconciled against SINAN's published epidemiological week as a test, so counts match the official bulletins at year boundaries.
   - The season becomes a 52-week cycle.
2. **A baseline robust to past outbreaks.** Past epidemics are downweighted when fitting the alarm baseline, as in Farrington. The descriptive tiers keep them, because for "normal Brazil" they are part of what is normal.
3. **A nowcast.**
   - The reporting delay is estimated from dates inside the records of completed years:
     - SINAN: onset, notification, data entry;
     - SIH: admission and discharge, against the processing month;
     - SIM: death, against registration.
   - The delay is then applied to the recent, incomplete weeks.
   - Snapshots of the preliminary files over time add the revisions: records changed or discarded after they first appear.
4. **An alarm design.** A false-alarm rate per place over time (a recurrence interval), not an FDR over one search. The cluster scan's Gumbel null converts to it directly.
5. **A benchmark.** The harness scores alarms against an existing tool's published alerts (InfoDengue, for arboviruses) and against later-confirmed epidemics: timeliness, false alarms, hits.

## Two measurements decide feasibility first

1. **Leftover variation per family.** The NB φ that remains after the per-place trend and season.
   - It sets a floor on the smallest detectable rate ratio, whatever the count.
   - At φ = 6 nothing under about ×8 is detectable in one cell; at φ = 30, nothing under about ×3.
2. **Publication lag per system,** from pegasus_data's catalog.
