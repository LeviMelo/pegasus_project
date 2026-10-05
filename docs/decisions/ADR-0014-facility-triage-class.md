# ADR-0014: Facility is a triage class: a lead carried by at most three recording institutions, with a mechanism

**Date.** 2026-10-05. **Status.** Active. Constants provisional.

**Evidence.** `docs/evaluation/2026-10-05-lead-triage.md`, section "Facility class". On the SIM.DO register the class takes 84 of 2,015 signals (4.2 %), on the SIH-RD chapter X register 3,219 of 9,469 (34 %, 94 % of them trends, 77 % by a volume step); the J31 space-time lead of 2015 in the Rio Doce valley is one CNES code's 255 of 255 admissions.

## Decision

1. **A lead is `facility` when** at most `FAC_K` = 3 facilities carry at least 70 % of its change, that concentration exceeds their share of the block's base-year events (binomial p < 1e-3; waived when they are the whole place), **and** a mechanism shows in their own behaviour: the same facilities' residents of other places show the same step in the lead-code share (z >= 3), or their volume without the lead's events stepped x1.6. It takes only from `signal`, after `noise`; the other classes keep priority.
2. **The class means "attributable to one institution", not "artefact".** A referral hospital receives real events and coding alike, so the lead keeps `info["facility"]` (facilities, shares, volumes, the outside step) and is not discarded; an outbreak read through one hospital is still read.
3. **Concentration without a mechanism stays signal** (`place_specific` if others do not move). Where the facility is the place (a sole provider with stable volume and no other residents), the data cannot separate hospital from place and the lead stays a signal with the flag.
4. The facility cube (residence x facility x 3-character code x year) is the single source (`facility.py`, gateway cache); SIM's `CODESTAB` is empty for 27-29 % of deaths, so SIM reads are partial.

## Limits

- 34 % of SIH signals is high: CNES opening, closing and recoding in small municipalities dominate. The volume threshold (x1.6) is untuned; changing a constant changes counts, not the rule.
- Group patterns have no direction and no facility read.
- The regional-epidemic case (a dengue year reaching a hospital's other catchments) passes the catchment test as a coding step; the class cannot tell it from institutional coding (hence point 2).
