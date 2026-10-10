# ADR-0035: cell excess is tested within size classes, each with its own empirical null

**Date.** 2026-10-09. **Status.** Active. Revises ARCHITECTURE §7 (cell excess); answers part of OPEN_QUESTIONS 15.

**Evidence.** Births B1, 77,980 place-years (`data/probes/oq15_classes.py`).
- **One pooled null.** Efron's two-group null fitted over every cell at once has σ0 0.978.
- **Ten equal-count classes by expected count.** σ0 runs from 1.028 in the smallest (5–35 expected births) to 0.911
  in the largest (836 and up), steadily.
- **What the pooled null did.** It was too narrow for villages, inviting false findings, and too wide for cities, costing
  them power.
- **What separation is for.** Efron (2008, "Simultaneous inference: when should hypothesis testing problems be
  combined?") separates classes whose nulls differ.

## Decision

1. **Classes.** At each support, the testable cells are split into equal-count classes by their expectation, not their
   count, so the classes are fixed before the test. A class holds about 5,000 cells (`CLASS_CELLS`, enough for its own
   empirical null), with at most 10 (`MAX_CLASSES`).
2. **Null and family per class.** Each class has its own two-group fit (δ0, σ0, π0) and its own BH at q. Each finding
   carries its class and that class's null.
3. **Relevance.** The minimum relevant effect is applied as before (ADR-0031).

## Consequences

- **Births.** 455 findings, against 482 pooled, moved toward larger places: the four largest classes give 308.
- **Roraima.** Boa Vista is still missed: one class's family is still thousands of place-years (OPEN_QUESTIONS 15).
- **Still to do.** A null-world check of the classed lens runs after the B3 grid. The guarantee is BH's within each class.

## Amendment (2026-10-10): one family, and a null that never narrows

**Evidence.** Births, null worlds drawn from B1 and refitted (`pegasus-core grid SINASC-DN birth '*' --worlds 0
--null-worlds 20 --lenses cell_excess`). The seeds are the same in every run, so the worlds are paired. A world with any
finding is a false discovery, and q allows 1 in 20.
- **BH per class, as decided above.** 7 of 11 worlds had a finding.
  - Each of up to ten classes spent its own q, so under a complete null the chance of a finding approaches
    1 − 0.95¹⁰ ≈ 0.40.
- **One BH over every class's cells.** 3 of the first 4 worlds still had findings.
- **One BH, and each class's σ0 at least 1.** 2 of 11 worlds, within the binomial noise of q. In worlds 0–3:
  - without the floor: 2, 1, 1 and 0 findings;
  - with it: 0, 1, 1 and 0.
- **What remains is the predictive's.** One world's z (`data/probes/cell_null_tails.py`):
  - the centre is calibrated everywhere: sd 1.005 overall, σ0 0.96–1.03 per class;
  - above 3, the largest classes' tails run 2-3× N(0, 1), and up to 12× above 4;
  - all three cells BH rejects there lie in the two largest classes.
  - That is OPEN_QUESTIONS 12's size-dependent noise, to be fixed in the model.

**Decision.**
1. Each class keeps its own empirical null (δ0, π0, and σ0 for the record), but the p-values are pooled into one BH at
   q over every testable cell (Efron 2008's separate classes; Cai and Sun 2009).
2. The null's width is max(σ0, 1): an empirical null may widen the predictive's N(0, 1), never narrow it.
