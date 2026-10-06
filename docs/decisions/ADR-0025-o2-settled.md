# ADR-0025: O2 settled — the interaction's rank, the tree prior and the exposure modifiers

**Date.** 2026-10-06. **Status.** Active. Amends ADR-0020 (the modifiers stay opt-in, now measured) and ADR-0021 (the rank). Race groups and SINAN wave 1, the rest of O2, are not settled here.

**Evidence.** All runs held out 2022–23 after fitting 2010–2021 under ADR-0024's defaults, scored by the negative binomial log-likelihood per event (`scripts/bench.py`, `data/o2/*.log`; evaluation 2026-10-06, solver v1, sections O2).

## Decision

1. **The low-rank interaction stays off by default.** Its rank is a per-block choice, until the model-choice loop (O10) makes it.

   | block | gain over rank 0 | best rank | time against rank 0 |
   |---|---|---|---|
   | SIM IX | +0.0153 per death | 4 | 5–9× |
   | SIH-RD X | +0.0012 per admission | 1 | 7× |

   On SIH-RD X, rank 3 loses 0.0002 against rank 0.
2. **The tree prior stays the iid Gaussian per level.** The horseshoe's held-out score equals the Gaussian's to 2·10⁻⁵ per event on SIM I, SIM XVII and SIH-RD IX, at 15–40 % more time. The block carrier of ADR-0024 already gives each innermost group its own level; the horseshoe was meant to deliver that shrinkage.
3. **Completeness κ and the SUS-dependent share stay opt-in exposure modifiers** (`popsvs+kappa`, `popsvs+sus`). Held out, each gains or loses at most 0.0034 per event, with no consistent sign. Place effects absorb a UF-year completeness and a municipal share that is constant in time.

   | modifier | gain held out per event |
   |---|---|
   | κ on SIM | IX +0.0001, X +0.0011, XX +0.0002, IV −0.0004, I −0.0034 |
   | SUS on SIH-RD | II −0.0002, IX −0.0005, X −0.0020, XV +0.0002 |

   ARCHITECTURE §4.1's case for κ stands for a series whose completeness changes within a place over time. The 2010–2023 SIM series is not such a series at this grain.

## Limits

- One held-out window, 2022–23, after COVID. The damped forecast carries the courses.
- The SUS share exists for 2021–23 only. Before then it is its cell mean (ADR-0020), so its time course is never tested.
