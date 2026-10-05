# ADR-0017: Institutions, first stage: an opt-in supply term from independent evidence, and facility steps on a lattice of (facility, year) cells

**Date.** 2026-10-05. **Status.** Active. Constants provisional; the supply term is opt-in.

**Evidence.** `docs/evaluation/2026-10-05-institutions.md` (SIH-RD chapter X, annual, 2010-2023, 5,570 places, 16.77 M admissions; the survey under today's plan, 50 replicates).

## Decision

1. **Two objects, because only part of a facility's behaviour can leave a place's expectation without hiding real events.** A facility's volume reaches its residents' counts in every chapter, so other chapters are independent evidence of it. A facility's handling of the block's own codes (coding, a service, a real event it served) is not independent: a referral hospital receives real events and coding alike (ADR-0014 item 2), and subtracting it from the places it serves would absorb an outbreak that one hospital serves.
2. **The supply term (`facility.attach_supply`, `Session(supply=True)`, `Monolith.supply`).** The expectation of an annual count block is multiplied by `A_ut = renorm(exp(b_v L_vol + b_u L_util))`.
   - `L_vol` = log Σ_f w_uf r_ft (w_uf: share of the place's block events recorded at f; r_ft: the facility's other-chapter volume as a share of the nation's, over its own mean). `L_util` = log of the place's own other-chapter admissions over its mean rate times the nation's course.
   - **Other chapters means not the block and not I, X, XXII** (`EPIDEMIC_PREFIXES`): dengue and COVID admissions never enter a supply index.
   - Each log index is **soft-thresholded at two standard deviations of its counting noise** (`_deadband`; the inflation read off the places). Without it a sole-provider town's index is its own counts: z sd 0.96 to 1.06.
   - `renorm` keeps every place's and every year's expected total. The exponents are chosen on a grid {0, .25, ..., 1} by the negative binomial likelihood of the place-year cells under the block's B1; the term is applied after the fit, in every tier (`Monolith.expected`, `expected_by_group`). With the deadband the grid chose 1 and 1.
3. **Annual grain only.** The cube is annual; an annual factor on monthly cells raised the outbreak lens's B1 cells from 83 to 139 (a step inside a year lands in the wrong months). `Expectations` skips monthly blocks.
4. **The institution lattice (`facility.institution_lattice`, `Session.institutions`).** Cells (facility, year) with the facility's catchment as exposure: `m_ft = Σ_u q_uf μ_ut`, q the share of the place's other-chapter events recorded at f. A facility's best window of years is found by the Poisson likelihood ratio, scaled by the dispersion of the facilities' residuals (`LATTICE_G` 27, step at least x1.6, `LATTICE_MIN_EXPECTED` 30). A step is **volume** when the facility's other-chapter volume moved with it (at least half the log step), **specific** otherwise. A specific step is read as a lead of the institution (E_i), never subtracted from the places.
5. **The supply term is not the default, and the lattice is not yet a lens.** Neither enters `Session.survey` or the register until the next stage (below).

## What was measured (today's survey plan, chapter X)

| | baseline | supply term |
|---|---|---|
| leads | 4,321 | 4,200 |
| facility class | 507 | 452 (-11 %) |
| signal | 974 | 911 (-6.5 %) |
| calibrated fields B1 / B2 (of 67) | 67 / 51 | 67 / 51 (chapter KS .0227 -> .0191, .0398 -> .0374) |

- The facility share of signal-or-facility is 34 % either way. 421 of the 507 facility leads and 857 of the 974 signals persist.
- Dengue (A90, A91) and the COVID-era J12, J18, J96 state-years keep their obs/exp (state-year correlation .90-.999; dengue state-years at 2x or more: 22 of 22 and 14 of 14 stay at B2, and 22 of 25 at A90 B1, the other 3 falling just under 2x). The seasonal profile (monthly, Jaccard 1.00 for Sul and Sudeste) is untouched.
- Sole-provider places (1,191): z sd .959 to .983; 112 of 113 sole-provider signals persist; only a stepped subset (141) gains at B2 (|z|>3 3.3 % to 2.8 %). They do not become readable.
- The lattice finds 1,744 steps among 5,666 facilities (1,336 volume, 408 specific); its false-step rate under its own null is 0.0002 and 0.011 at twice the dispersion.

## Limits and what remains

- **The term removes a minority** because most facility-class leads are a facility's handling of a node (J45, J15, J13 ...), which other chapters cannot see. A larger pass-through (the grid at 1 with the raw indices) added leads (5,065) and noise.
- **The term is chosen on the cells it is applied to** and applied after the fit. A fit with the term inside the likelihood is the next step (ARCHITECTURE §13, row 4.5).
- **Crossed place x facility effects at the node level** (a facility's handling of a node estimated from all the places it serves, places from all their facilities) is what could separate a hospital from a place where places share facilities; sole providers stay inseparable by any model.
- **The lattice is a function, not a lens:** no multiplicity across 57 nodes (14,102 node-level steps in 3,880 facilities, too many to be leads), no replication, no pair. The calibrated detector, its place in the ledger and the E_i pair come next.
- SIM-DO names a facility for 71-73 % of deaths only; nothing here is measured on SIM.
