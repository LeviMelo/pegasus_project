# Questions and their methods

**Status:** design (author's proposal, 2026-10-07). It formalises what the documented-events table does by hand: a question per row, several methods per column, each method with its record.

## Why

- **Flat names.** Stage C and D register methods by name (`outbreak`, `cell_excess`, `excess`, `step`, …), and nothing says which of them answer the same question.
- **What follows.** The survey cannot ask what the methods for one question say together. Retiring a method means editing lists. Today's rule "never lose a question" is enforced by hand.
- **The answer.** A question is the fixed object; its methods are interchangeable answers, each with a measured record. An investigation can branch into many methods towards one question without losing control of what is claimed.

## The objects

```
Question   id, estimand (in words and as its departure term, ARCHITECTURE §7.0), stage (C, D or E), reference tier,
           locus type (cell, area, area × window, field pair, lead), effect scale, minimum relevant effect,
           the combination rule, declared once
Method     id, the question it answers, a callable, its assumptions (independence of places, Gaussian peaks, …),
           the data regimes it suits (sparse or dense, annual or monthly), its record (below)
Record     calibration on null worlds (false discoveries at q), recall on the documented events (§10.1, which
           event, where, at which scale), real negative controls (time reversal, place permutation), cost.
           Measured, never set by hand.
```

The first questions:

| question | stage | methods today |
|---|---|---|
| excess in a place and period | C | `cell_excess` (two-group; the ladder), `excess` (multiscale spike), `outbreak` (the v0 lens, prospective) |
| a lasting level change | C | `excess_step` (multiscale), `step` (Bayesian change point), `change_point` (the v0 lens) |
| a course bending away | C | `excess_trend` (multiscale), `trend_divergence` (the v0 lens) |
| fields moving together, with a lead | D | `spectral_factor_model`, the per-band factor models, `distributed_lag` (pairwise confirmation) |
| why a lead exists | E | rival explanations per lead: supply, recording, coding, reference (O8) |

## Rules

1. **The combination is declared before data.**
   - Per locus, the methods' p-values combine by the Cauchy combination test (Liu & Xie 2020, valid under arbitrary dependence between the methods).
   - Loci are matched across methods by place × period overlap.
   - Multiplicity is counted per question, never per method, so adding a method cannot buy findings.
2. **Disagreement is reported.**
   - Each lead carries which methods found it and at which scale.
   - A regional finding without a cell finding, or the reverse, is a statement about the departure's scale.
3. **Roles come from records.** Which methods run in a data regime, and which is primary, is read from the records. No constant is tuned to make an event appear; the events stay held out of tuning (§10.0).
4. **Retirement follows CLAUDE.md "never lose a question".** A method leaves when its question's other methods cover every use it had, by record.

## Build order

1. `questions.py`: the registry, with the records filled from `data/real_events.py` and the grid's null worlds.
2. `Session.ask(question, node)` runs a question's methods and combines them. The survey asks questions, not lenses.
3. Leads carry the question, the methods' agreement and the combined evidence.
