## ADR-0002: The architecture of PegaSUS

**Date:** 2026-10-04. **Status:** active. **Accepted by the author**, after the design discussion of 3–4 October.

**Context.**
- The 2026 engine specified its goals well and failed in its mathematics and machinery. The record is in `docs/discussion/2026-10-03-what-was-built.md`:
  - pooled Gaussianisation that baked gradients into its data (corr(z, log population) = 0.93);
  - one covariance over all places and 25 years;
  - a taxonomy used as a prior on relations;
  - fixed strengths;
  - weights computed and never used;
  - an output size set by multiplicity arithmetic;
  - a validation programme never run on real data.
- The reasoning behind each choice below is in `docs/discussion/2026-10-04-design-v0.2.md`.

**Decision.** `ARCHITECTURE.md` is the authority. In brief:
1. **One model:** a marked point process of health events, fitted as one hierarchical model ("the monolith"). Population offsets and observation terms come from pegasus_data's modelled tier. Structure priors per variable shape act on levels only. A learned BYM2 runs over a family of proximity graphs. Interactions are low-rank (ARCHITECTURE §4).
2. **Estimation by a factorised quasi-likelihood** that never forms empty cells, with dispersion by moments, the Laplace approximation checked against exact fits, and a two-level block fit (§5).
3. **Expectation tiers B0–B2s** as nested versions of the monolith. **Surprise is computed after the expectation,** with an information weight per cell (§6).
4. **Scans:**
   - lenses;
   - multidimensional subset scanning, with a Gumbel-tailed null;
   - patterns;
   - pairs under declared estimands, with dependence-aware nulls and minimum-effect tests;
   - dependency maps;
   - explaining away and decomposition;
   - cohort scans (§7).
5. **Error control:** a ledger written before execution; BH within families; Benjamini–Bogomolov across them; TreeBH; LOND for agent claims; replication tiers R0–R3 over temporal, spatial and system splits. **Admission and minimum effects are calibrated on the harness** (§8).
6. **Use as a survey:** leads, on-demand slices and tools; agents confirm on a reserved spatial half (§9).
7. **A validation harness first,** with positives, negatives, planted signals and surrogates, as the gate for every lens (§10).

**The calls left open in the design, settled:**

| call | settled as |
|---|---|
| O1, grain | annual first, monthly for dense families in phase 2 |
| O2, dependency maps | phase 3, after the pair scans that check them are calibrated |
| O3, agents' confirmation reserve | spatial, not temporal |
| O4, admission and δ | calibrated from power curves and negative controls (§8.4); provisional values meanwhile |
| O5, cohort scans | phase 2 |
| O6, population account and race model | pegasus_data's modelled tier |

**Consequences.**
- Phase 0 builds the harness, the gateway, the store and the ledger before any model.
- PegaSUS depends on pegasus_data delivering the handoff `docs/handoffs/2026-10-04-pegasus_data.md`.
