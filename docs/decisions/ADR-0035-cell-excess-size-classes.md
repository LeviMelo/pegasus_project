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
