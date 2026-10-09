# ADR-0033: the robust expectation moves recodings instead of removing them

**Date.** 2026-10-09. **Status.** Active. Revises ARCHITECTURE §5.2 (the robust refit's imputation); answers
OPEN_QUESTIONS 13.

**Evidence.** OPEN_QUESTIONS 13 and evaluation 2026-10-09-weighted-events-and-absent-ages, OQ 13 section.
- **The bias.** With NB-P in place, SIM IX's largest places sat above their expectation: O/E 1.028 at the 90th–99th
  percentiles of size, 0.998 below the median. The PIT's KS rose with size, to 0.085 in the largest quintile.
- **The cause: the robust refit.** It imputed every flagged leaf × place × period to its expectation. Examples:
  - a city certifying a group's deaths under one code, such as Fortaleza's hypertension as I10 at about five times
    its expectation in 2010–2014;
  - Belo Horizonte's I11, Brasília's I51, and I42 in Nova Iguaçu and Duque de Caxias.
- **Why only large places.** Each such leaf is flagged every year, and imputing it removes deaths the place really
  had. A large place's level is its own data, so the removal lowered exactly the large places' expectation. 55 % of
  the top decile's flagged excess was matched by a deficit among the same place's other leaves, against 21 % below
  the median.

## Decision

1. A recoding leaves the matching deficit among the block's other leaves in the same place and period; an epidemic
   adds deaths and leaves none.
2. The flagged excess that the unflagged leaves' deficit accounts for, min(Σ excess, Σ deficit) per place and period,
   is added back to those leaves (`Monolith._impute`), and only the rest is removed as a departure:
   - across leaves, in proportion to each leaf's deficit;
   - within a leaf, in proportion to its expectation over the sex–age groups.
3. The pool is the block, not the leaf's group, because recodings cross groups (I10 against I50). Measured on SIM IX
   2010–2023, B1:

| pool | O/E below median | 90–99 % | top 1 % | whole | PIT KS by size quintile |
|---|---|---|---|---|---|
| none (v9) | 0.9976 | 1.0276 | 1.0232 | 1.0178 | 0.012, 0.026, 0.041, 0.048, 0.085 |
| group | 0.9945 | 1.0158 | 1.0150 | 1.0102 | 0.006, 0.019, 0.032, 0.039, 0.055 |
| **block** | 0.9787 | 1.0058 | 1.0102 | 1.001 | 0.018, 0.007, 0.010, 0.012, 0.018 |

   - The block calibrates best in four quintiles, and its worst KS is the lowest of the three.
   - Its whole O/E is 1.001.
   - The O/E gradient with size remains, about 3 points as before: smallest places 2 % low, the largest 1 % high.
     The noise covers it at every size.
4. The robust fit's key is `v: 11`, so every stored robust fit is refitted.

## Consequences

- **What was the imputation, and what remains.** SIM IX's miscalibration by size was the imputation. A size term in the
  expectation (unit B4) is not needed for calibration. The remaining O/E gradient is an open question of the
  expectation's form (OPEN_QUESTIONS 13).
- What a recoding hides stays visible: the moved events are counted (`Monolith.recoded`), and the flagged leaf keeps its
  departure, read against an expectation that no longer absorbs it.
