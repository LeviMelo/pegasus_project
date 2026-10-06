# ADR-0023: Architecture revision 2: established methods, model-based detection and relations, validation that characterises, a structured solver with time budgets

**Date.** 2026-10-06. **Status.** Active. It revises ADR-0002's architecture on the author's instruction. It amends ADR-0022 (admission becomes weighting) and the gate of ARCHITECTURE §10.5 (retired). ADR-0015, ADR-0019 and ADR-0021 stand.

**Evidence.**
- The author's critique of 2026-10-06, and the review that answers it: `docs/discussion/2026-10-06-architecture-review.md`.
- The measurements cited there:
  - the chapter IX solver profile: 16 of 30 Newton steps at the CG cap, 0.15–0.5 s per Hessian–vector product against 0.017 s per evaluation of the total;
  - the 277-death block spending 85 % of its time in Hessian–vector products;
  - E_w failing the microcephaly positive twice;
  - 14,813 leads removed under an ungraded rule;
  - κ absorbed at B1/B2/BP.

## Decision

1. **Principles.**
   - P9 is rewritten: validation characterises; it does not license.
   - P11: established method first.
   - P12: departures and relations are model terms.
   - P13: structure is exploited, and speed is budgeted.
   - P14: recording is measured, never used to dissolve.
   - Every component states its maturity (v0, v1, v2); a v0 is never the end state.
2. **Estimation (§5.3–5.8).**
   - Exact Newton on the assembled block-arrowhead Hessian: closed-form elimination of the leaf-place effects, sparse Cholesky of the place system on the graph, a dense Schur complement on the globals.
   - BYM2.
   - The strengths by the Laplace approximate marginal likelihood in log τ.
   - Uncertainty by selected inversion and exact draws from the same factor.
   - A benchmark (`bench`, O1) with time budgets, run on every solver change.
3. **Detection (§7.0).** Departure models infer, from each estimand's established method (BaySTDetect, local fdr / shrinkage, change-point components, exceedance probabilities, hierarchical interactions), with Bayesian FDR. The v0 lenses become screens.
4. **Relations (§7.5).**
   - Distributed-lag terms, shared-component models and endemic–epidemic terms estimate relations, guarded by negative-control outcomes and exposures.
   - E_b stays a screen; E_w is a screen only.
5. **Validation (§8.4, §10).**
   - No field or lens is excluded for low power or a failed check. Hypotheses are weighted by power (IHW), and every result carries its minimum detectable effect and its method's record.
   - Methods are characterised on a designed grid of planted signals and on null worlds; the model by simulation-based calibration and MCMC comparison.
   - Documented events are held out, never used to tune.
6. **Recording (§8.6).**
   - Conserved-level fields are standard.
   - Recording processes are measurement terms where identified.
   - Only tested explanations remove a lead.
   - A changed rule is re-applied to the stored state.
7. **Race and the ICD ontology** (added the same day, on the author's objection that race was missing from the architecture and that the model needs an ICD ontology).
   - **P15:** race is an axis, not an option. G = age × sex × race from 2000. Recorded race is read through its measured misclassification and missingness (§3.4, §4.1). Disparities are estimands (§4.2, §7.0).
   - **The ICD ontology is a pegasus_data product the model consumes (§3.3):** attributes, age plausibility, ICD-9 and its bridge, ICD-O, lists, external-cause axes, relations.
   - Work packages O3 and O4; the later packages renumbered O5–O10.
8. **Roadmap (§12).** Work packages O1–O10, in that order: solver, settle, characterise, departures, relations, recording, breadth, top model and surveillance.

## Alternatives

- **Keep the v0 architecture and tune it.** Rejected by the evidence of the review: its failures come from how it solves and reads the model, which tuning does not touch.
- **Replace the monolith by per-field models only.** Rejected: the shared structure (tree, graph, profiles) is what makes sparse fields estimable; the review found the model sound.

## Consequences

- **Development was paused** on 2026-10-06 for this revision.
- **Running measurements were left to finish**, because their results enter O2: the interaction's rank, the horseshoe, the SUS exposure, the SINAN fits, the graded re-triage.
- **O1 starts the resumed development.**
