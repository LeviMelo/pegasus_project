# Course correction (2026-10-06, evening)

Written after the author's critique of the day's work:
- detectors are generic tools and should not carry case-specific logic;
- statistical validity and epidemiological validity are different questions;
- relations were being approached pairwise;
- the architecture fuses scientifically different computations into single objects.

The critique is right. This note does three things:
1. lays out PegaSUS's flow as distinct computations;
2. shows where the code fuses them;
3. says what the day got wrong against the principles, and what changes.

It is a proposal for the author to read and correct before any restructuring.

## 1. The flow, one computation per stage

Each stage answers one question, with its own kind of validity.

| stage | question | computation | its validity is | output |
|---|---|---|---|---|
| **A. Data and meaning** (pegasus_data) | what was recorded, for whom, under which code? | reading, decoding, populations | correct meaning | counts by place × period × age–sex × code; populations |
| **B. The expectation model** (the monolith) | what would we expect, and how much would it vary, if nothing unusual happened? | a probabilistic model of every count: its mean **and its noise, including how noise is shared across years, places and causes** | statistical: calibration of the predictive (PIT, SBC, held-out likelihood) | a *joint predictive distribution* per field |
| **C. Departures** | is there a departure of a declared shape (a cell excess, a step, a trend, a cluster, a group interaction), and how big is it? | **departure terms added to the model** (P12), each with its posterior; reported where the posterior says the effect exceeds the minimum relevant effect, with the expected false-discovery proportion held at q | statistical: on worlds drawn from B with and without planted departures, the reported sets keep their false discoveries at q, and power is measured (the grid) | statistical leads: shape, support, effect with interval, P(effect > minimum) |
| **D. Relations** | do fields move together, and does one lead another? | **a joint model of all fields' departures from their expectations**: shared latent factors across fields, places and time, and the dynamics among them; a pairwise lag test only confirms a link the joint model proposes or that was declared | statistical: recovery of planted relations, null worlds | relation leads: which fields share which factor, with lags and intervals |
| **E. Interpretation** | is a statistical lead an event in the world, an artefact of recording, or known? | recording terms and their graded explanations (P14), replication on independent units, corroboration by independent systems | **epidemiological**, not statistical | a lead's class, its replication tier and its corroboration |
| **F. Use** | what does a person read first? | ranking by effect, certainty and relevance; reports, the register, serving | usefulness | the reading list |

**The boundary that matters.** Stages B to D make statistical claims only: "under the model, this departure is larger than its noise, by this much, with this certainty." A false lead at those stages is a *statistical* error: the stated certainty is wrong, because the null was mis-stated. Whether the departure is a real event is decided at stage E, and nowhere earlier.

## 2. Where the code fuses stages

| object today | computations fused in it | consequence |
|---|---|---|
| **the expectation tiers** (B0, B1, B2, BP) | the model's predictive (B) fused with *the reference a departure is measured against* (C's estimand): B2 refits a trend per place inside the "expectation" | a step or trend is partly absorbed by the very baseline it is tested against; the noise the model never described (serial correlation) is handled nowhere |
| **a lens** | a search over shapes (a scan), a null distribution built from B's *marginal* noise, a multiplicity rule, a minimum effect, and a detection unit | each lens carries its own null, and when the null was wrong I patched the lens (per-system θ0, tier swaps) instead of the model |
| **θ0** (the minimum effect) | a statement of relevance (stage F's, or P5's region of practical equivalence) and a calibration patch for a mis-stated null (stage B's defect) | ADR-0026's per-system table encodes B's missing noise structure as C's thresholds |
| **the harness** | statistical characterisation (worlds, the grid, SBC) and epidemiological positives (documented events) | "validation" meant two different things; documented events tuned constants in v0 |
| **triage** | recording terms (E), replication (E), and rules that decided whether a lead "counts" | a rule change silently removed leads (fixed by rule versions, but the fusion remains) |
| **the lead's rank** | statistical strength and effect size and relevance | a reader cannot tell why a lead is first |

## 3. What the day got wrong

- **I tuned residual statistics instead of building departure models.**
  - P12 says departures are model terms. §7.0 lists each estimand's established departure model (BaySTDetect for trends, Efron's two-group model for cell excess, Bayesian change points for steps, BYM2 exceedance for clusters).
  - O6 was to build those. Instead I made the v0 lenses better residual tests: tiers, past baselines, θ0 per system.
  - Each step was measured, but the object being improved is the one the architecture had already demoted to a screen.
- **I answered a modelling problem with thresholds (P11).**
  - The negatives failed because B's predictive treats years as independent. The residuals' lag-1 autocorrelation within places measures it: 0.03 on stroke, 0.23 on ill-defined causes, 0.27 on births, 0.39 on SIH pneumonia (`data/probes/residual_autocorr.json`).
  - The fix is a term in B, so every departure model inherits the right noise. The per-system θ0 table is the wrong fix, and goes.
  - The sparse field's failure (rheumatic fever, autocorrelation −0.02) has another cause: the normal-score negative manufactures spikes in near-zero cells. It is a defect of the negative, not of the field.
- **I put relevance into the test, and then judged the test by lead volume.** Raising the trend's θ0 because a survey produced 41,700 leads mixes stage F's question ("which leads matter?") into stage C's ("is there a departure?").
- **I approached relations pairwise.** `relations.distributed_lag` is a sound confirmatory test of one declared link, but it is not stage D. Stage D is a joint model, whose cost grows with the number of shared factors, not with the square of the number of fields.

## 4. What stands

- **Stage B's machinery:** the solver (exact Newton on the arrowhead, LAML strengths), the ICD structure and admissibility (ADR-0024), the O2 choices (ADR-0025).
- **The grid** as stage C's statistical characterisation: worlds drawn from B, refitted, planted departures, null worlds. It measures a departure model as well as it measured the lenses.
- **The absorption finding** (a refit takes 9–63 % of a departure) and **held-out sizing** (`Monolith.without`). Both are stage C facts. They also argue that departures belong *inside* the model as terms, where the fit cannot absorb what a term carries.
- **SBC** as stage B's calibration check, and its finding: the joint mode misplaces the intercept under data-poor random effects. That is an open stage-B problem (OPEN_QUESTIONS 2).
- Rule versions on verdicts, the method record and the retired gate: stage E and F plumbing.

## 5. What changes

1. **B carries its noise structure.** A residual place × period term with temporal correlation (AR(1) over periods within place, its strength and correlation learned by the marginal likelihood), or the equivalent in the predictive. Every field's predictive then states its own serial correlation, measured from its data, never set per system. ADR-0026's per-system table and the trend relevance floor are withdrawn with it.
2. **C becomes departure models (O6, as §7.0 specifies).** Each estimand gets a departure term in the field's model, read through its posterior, with the Bayesian FDR of §8.2:
   - cell excess: the two-group model;
   - steps: a Bayesian change-point term;
   - trends: BaySTDetect;
   - clusters: BYM2 exceedance;
   - group interaction.

   The lenses stay as cheap screens that propose supports, and they make no claims. The tiers become what they are: **references** an estimand is measured against (national, the place's level, the place's past), declared per estimand, not a property of "the expectation".
3. **Relevance moves to where P5 puts it.** It is the minimum relevant effect inside the departure model's posterior, P(effect > minimum): a statement about the effect, not a patch on a null. Lead volume is stage F's ranking problem.
4. **D is designed as a joint model before more is built.** All fields' departures (from C) are modelled together:
   - a low-rank set of latent space–time factors shared across fields, the cross-block generalisation of the place × time interaction (the "top model", §5.6);
   - sparse lagged dependence among the factors.

   The pairwise lag test remains the confirmatory tool. A design note comes first, for the author.
5. **The documents are re-cut to the stages.**
   - ARCHITECTURE §6–§8 are reorganised so each object does one stage's computation.
   - ADR-0026 (per-system θ0) and ADR-0027 (lens baselines) are marked as superseded by the stage-B noise term and the stage-C departure models once those land.
   - The harness separates statistical characterisation (B, C, D) from documented events (E).

## 6. What the first steps are

1. Measure, then build: the residual AR(1) term in B, its strength and correlation by LAML. Accepted if the negatives that failed by serial correlation pass with no per-system constant, and held-out likelihood does not fall.
2. The first departure model, cell excess (Efron's two-group model on the predictive scores, with the local fdr), characterised on the existing grid against the outbreak lens at equal FDR.
3. The stage-D design note.
