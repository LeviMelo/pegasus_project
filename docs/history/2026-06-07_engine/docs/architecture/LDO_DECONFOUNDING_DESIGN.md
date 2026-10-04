# LDO residual-scan deconfounding — design & research synthesis

**Status:** research program in progress (2026-07-12). This document is the durable synthesis of a
7-dimension literature reconnaissance + real-data diagnosis of the LDO residual near-clique, and the
architecture we are building to resolve it. It supersedes the "unidentifiable, handoff to GPT-5.6"
framing in [`LDO_RESIDUAL_ARTIFACT_HANDOFF.md`](LDO_RESIDUAL_ARTIFACT_HANDOFF.md) and the §8 pessimism
in [`modules/ldo.md`](modules/ldo.md).

Read [`modules/ldo.md`](modules/ldo.md) first for the code+math map of the estimator; this document is
the *forward plan* for its residual layer.

---

## 1. The problem

At national scale the LDO residual nonlinear-edge scan (`scan_residual_nonlinear_edges`, HSIC on
joint-model residuals) produces a **near-clique**: ~7,000–9,180 `nonlinear_residual` edges among ~136
covered variables — almost everything depends on almost everything. This is an **artifact**, not
epidemiology. The stale national output (`national_c25_full_ad2`, 9,180 edges) predates Codex's
nuisance projection (deddf68); the live-code clique size on a real slice is being measured now
(Phase 1). Composition of the stale clique: 40 counts, 25 proportions, 17 rates, 16 log-ratios, 8
money (BRL), 8 SIDRA people, etc.; 50% of edges touch ≥1 count, only 8.5% are count–count.

## 2. The converged diagnosis — it is CONFOUNDING, not compute/kernel/threshold

Seven independent literature dimensions converged on one diagnosis: the near-clique is a
**confounding** problem with several distinct mechanisms, each with its own home in the stack. It is
**not** primarily a kernel defect, an OOM problem, or an FDR-threshold problem (no uniform FDR
threshold — BH, the ~12× stricter BY, or a smaller α — can separate a confounder clique from a genuine
hub, because they differ in *structure*, not per-edge p-magnitude).

The mechanisms:

| # | Mechanism | Where it lives | Current handling |
|---|-----------|----------------|------------------|
| M1 | **Ratio-standard / shared-denominator (Kronmal)** — two quantities sharing the population denominator correlate ~0.5 by *arithmetic* even when numerators are independent. MEAN-driven. | Margin (counts & same-denominator rates) | Partially: count\|exposure margin on RN rate vars only (74 refs after the wiring fix); raw counts untouched |
| M2 | **Interactive (multiplicative) latent factor** — `e_ic(t) ≈ λ_i(c)·F(t)`: municipalities respond to a national factor (population/urbanicity/SES gradient) with heterogeneous loadings. | Residual cell field (space×time) | **Not handled.** Additive two-way FE removes only `α_i + γ_t`; the variable-level low-rank `L` is cross-variable, not cross-cell. |
| M3 | **Full-rank RSR over-projection** — the current municipality FE is the degenerate rank-S Restricted Spatial Regression (Reich-Hodges-Zadnik), which *erases* cross-sectional contrasts. | Nuisance projection | Present but blunt (removes real signal) |
| M4 | **Small-area heteroskedasticity** — rate variance ∝ 1/exposure; population-driven variance co-modulates across variables. | Margin / test weighting | Partially (EB shrinkage in count margin) |
| M5 | **Permutation p-floor** — `1/(B+1)` pins thousands of pairs at the same minimal p; FDR degenerates (the "6,974-edge cliff"). | Null | Not handled |
| M6 | **Wrong multiplicity denominator** — `M_eff ≪ p(p-1)/2` under the clique. | FDR | Not handled |

## 3. The identifiability resolution — overturning the "unidentifiable" dead-end

An earlier analysis concluded the cross-sectional confounding was *unidentifiable* (a broad shared
confounder is mathematically indistinguishable from a broad genuine determinant, because a data-driven
SVD orders them by magnitude and interleaves them). **That is a real theorem** (D'Amour/Ogburn
multi-cause critique; the Deconfounder is not point-identified) — but the conclusion "therefore we
cannot fix it" was **wrong**. The mature deconfounding literature (CATE, RUV, SVA-with-controls, GCM,
FarmTest) escapes it exactly one way, and PegaSUS is unusually well-positioned to use it:

- **Inject external information about which directions are nuisance.** The dominant confounder
  (**municipality population/size**) is **OBSERVED** (SIDRA population tensor + `measured_quantity_refs`
  exposures + SIDRA socioeconomic block). Conditioning on an *observed* confounder is identifiable —
  this is *not* the latent-factor unidentifiability. Blind SVD is the wrong tool; **supervised
  regress-out of the named confounders** is the right one.
- **CPW incoherence for the unsupervised remainder.** Where a latent factor must still be estimated,
  separate confounder from signal by **loading BREADTH (incoherence), not singular-value magnitude** —
  a confounder is low-rank AND dense/incoherent; a genuine determinant is sparse/concentrated. This is
  the *same* sparse+low-rank incoherence (Chandrasekaran-Parrilo-Willsky) the LDO already trusts on its
  linear layer `Ω = S − L`. The trim transform (Ćevid) and Bai IFE defactoring realize it.

Both spatial-confounding (Guan et al.) and genomics (RUV) reached the identical resolution
independently: the two accepted escapes are (a) an unconfoundedness-at-high-frequency assumption, or
(b) conditioning on the known confounders. We use (b) as primary, (a)/CPW as the safety net.

**Decisive computational fact:** every deconfounder here operates on the `p×n` residual matrix
(~150 MB at n≈140k, p≈136) or the `p×p` Gram (~0.15 MB) — roughly **1000× below** the `n×n` HSIC kernel
wall (157 GB). Deconfounding is *essentially free* relative to the real constraint, GPU-trivial, and
RAM-adaptive by a single rank knob. The fix belongs **upstream** of the expensive kernel (§III: fix the
phenomenon where it lives), so the O(n²)/low-rank HSIC only ever sees residuals already purged of
population and factor structure.

## 4. The architecture — a multi-layer deconfounding stack

Each layer is cheap, attacks one mechanism, and composes monotonically. Ordered by where it sits:

### Layer A — Margin: mean-conditioning, not division (attacks M1, M4)
- **Correct-offset count\|exposure with the SEMANTICALLY CORRECT denominator per variable** (population
  for mortality, births for perinatal, admissions for in-hospital) via `measured_quantity_refs` (the
  wiring fix, commit 524ea00, now resolves 74 refs). Extends to raw counts by pairing each with its
  observed exposure (`exposure_field_by_variable`) — *condition on* population, never divide by it.
- Optionally **analytic Pearson residuals** (Lause-Kobak-Berens / sctransform) as a closed-form
  O(np) mean-AND-exposure-conditioning residual (the genomics answer to shared-depth co-expression ≈
  shared-population co-morbidity). Monotone-safe alternative to the PIT margin for counts.
- **Not** plain VST (Anscombe/Freeman-Tukey/asinh) *alone*: it stabilizes variance but leaves the
  shared-denominator MEAN confounding — powerless against M1.

### Layer B — Residual deconfounding (the core new step; attacks M2)
Inserted in `residual_scan.py` immediately after `joint_model_residuals` and BEFORE the HSIC reprs.
Two composed operations on `E` (p×n):
1. **Supervised regress-out of the observed confounders** `Z` = {log-population (+ cubic/spline),
   spatial low-rank basis, year effects, optionally SIDRA structural block} — a GCM/RCoT-style ridge
   residualization `E ← E − (E Zᵀ)(ZZᵀ)⁻¹ Z`. Identifiable (Z observed), O(npq), no factor count.
   **Cross-fit across the existing spatial-block 2-fold split** (Neyman-orthogonal, reuses deddf68's
   folds).
2. **Unsupervised trim / IFE defactoring of the residual remainder** — subtract the leading DENSE
   PCs of `E` (Bai 2009 interactive fixed effects), rank by **Ahn-Horenstein eigenvalue-ratio** on the
   p×p Gram, **filtered by CPW loading breadth** so a concentrated cross-sectional determinant is
   protected. Ćevid **trim transform** (cap top singular values at the median) is the tuning-free,
   no-k default. Nuclear-norm SoftImpute (Athey 2021) is the convex, monotone-safe fallback when r is
   ambiguous — the exact residual-layer analogue of the LDO's `λ₂·tr(L)` trace penalty.

`remove_common_trend` (k=1) and the two-way FE (deddf68) are the additive, rank-≤2 special cases of
exactly this machinery; Layer B is the data-driven-rank interactive generalization.

### Layer C — Spatial: reduced-rank, not full-rank (attacks M3)
Replace the degenerate full-rank municipality FE with a **reduced-rank spatial+ / Moran-basis
projection** (Dupont-Wood-Augustin 2022; Hughes-Haran 2013) at rank r ~ 0.1·S: remove only the smooth,
low-frequency, positively-autocorrelated spatial driver; retain fine-scale cross-sectional
determinants. Machinery is one `scipy.sparse.linalg.eigsh` on the existing `build_spatial_precision_sparse`
Laplacian. GMRF/CAR `Q^{1/2}` whitening (matrix-free, monotone-safe) is the conservative baseline.
**Caveat (decisive):** raw RSR projection with a naive permutation null is anti-conservative
(Khan-Calder 2022) — the HSIC null MUST be recomputed on the projected/cross-fit residuals.

### Layer D — Null + effect size: escape the p-floor (attacks M5)
Replace/augment the permutation null with a **permutation-free spectral / Gamma moment-matched analytic
null** (free by-product of the low-rank feature covariances) to restore continuous p-values, and gate on
a **normalized-HSIC (CKA) effect-size floor** τ_effect — a monotone-safe rule that directly kills the
median-HSIC≈0.006 diffuse clique while sparing a strong real dependence. Optionally an Efron empirical
null fitted to the bulk of the pairwise statistics.

### Layer E — Multiplicity: honest denominator + hub-aware (attacks M6)
Use **M_eff (Li-Ji eigenvalue)** as the FDR denominator instead of `p(p-1)/2`; report `M_eff/p` as a
first-class clique-severity diagnostic. Add **hub-aware p-filter (Barber-Ramdas) across {edge, node}
layers** so a genuine hub survives the node layer while a diffuse everything-vs-everything clique is
trimmed by structure. Use the **correlation-specific n_eff** (xDF / Pyper-Peterman product-of-ACFs —
the AR(1) `(1−φ_aφ_b)/(1+φ_aφ_b)` in `edges.py` is the correct special case) to size permutation blocks
and per-edge SEs. Keep BY as the monotone-conservative backstop (necessary, not sufficient).

### Layer F — Engine: scalable feature-map HSIC (already ~done)
Keep the low-rank factored kernel `‖AₓᵀA_y‖²_F` (f26f525); optionally swap the kernel-eigen build for
**RFF (GPU matmul path) or Nyström (accuracy-per-byte, spatial-block-stratified landmarks)** so the
`n×n` kernel is never formed. Fix the stale `estimate_residual_scan_bytes` 2n² model → `n·r·8`
(RAM-adaptive rank from budget). This layer is about scale, not confounding.

## 5. Priority (from the synthesis)

**Tier-1 must-build** (each attacks a distinct dominant channel, all RAM-trivial upstream of the kernel):
1. **Kronmal exposure-conditioning margin** (Layer A) — analytic Pearson residuals + correct semantic
   offset. The single highest-leverage, cheapest fix; kills the dominant MEAN-driven shared-denominator
   channel. *Precondition:* `measured_quantity_refs` must route the correct exposure per variable — audit
   coverage.
2. **Regress-out conditional test (GCM + RCoT) on named Z** (Layer B/F) — the identifiable escape;
   condition the residual/feature-map on observed {log-pop, urbanicity, SES}. GCM = O(n) triage, RCoT =
   nonlinear.
3. **Feature-map HSIC engine (Nyström/RFF) + permutation-free spectral null** (Layer D/F) — removes the
   n² wall AND the 1/(B+1) p-floor cliff in one move; enables RCoT.
4. **Breadth-filtered IFE/low-rank defactoring** (Layer B) — the escape that needs *no naming* and
   preserves concentrated cross-sectional signal (CPW breadth); Ahn-Horenstein rank, SoftImpute default.
5. **Normalized-HSIC (CKA) effect-size floor + Gamma moment-matched null** (Layer D) — monotone-safe;
   kills the median-HSIC≈0.006 diffuse clique.

**Tier-2 strong:** correlation-specific n_eff (xDF) + autocorrelation-preserving block permutation;
hub-aware p-filter + M_eff denominator; factor-adjusted testing (FarmTest/PFA) + Efron empirical null;
spatial+ reduced-rank spatial-DML; RUV-4/CATE negative-control anchored subspace.
**Tier-3 optional:** SplitKCI certification; weighted (heteroskedastic-robust) HSIC; standalone Trim;
compositional (clr) handling for share/proportion variables.

## 6. Bake-off plan (Phase 4)

Race candidates on TWO real slices (SP/MG `35`/`31`, then national) so scaling is visible, each
carrying the confounding property. Harness: `scratchpad/bakeoff_deconfound.py`. **Plant THREE ground
truths into each slice:**
- (a) known **nonlinear conditional dependences that MUST survive** (power);
- (b) pure **confounder-null pairs** (independent numerators sharing the population denominator) that
  **MUST die** (specificity — reproduces the controlled 0.001→0.76 collapse);
- (c) a **concentrated, genuine cross-sectional determinant** (poverty→one disease) that **MUST survive**
  — this is the discriminator that separates the breadth-filter (keeps it) from muni-FE/Trim (kill it).

**Candidates, isolating one change at a time:** `C0` baseline (current marginal HSIC + muni-FE +
year-shuffle null) → reproduce the clique; `C1` Kronmal margin alone; `C2` RCoT regress-out on Z +
feature-map engine + spectral null; `C3` GCM regress-out on Z; `C4` breadth-filtered IFE defactoring;
`C5` effect-size floor + Gamma null on top of C0; `C6` full stack (C1+C4+C2+C5 + n_eff/p-filter/M_eff).

**Metrics per candidate/slice:** (1) clique collapse — edge count, max/median node degree, M_eff/p;
(2) planted-edge power + confounder-null false-positive rate + concentrated-determinant survival;
(3) null calibration — p-value QQ-uniformity on a null panel, no floor pile-up; (4) compute + peak RSS
at both sizes (no n×n, 0 pairs coarsened, scaling slope); (5) cross-candidate agreement — do C2 (named-Z)
and C4 (breadth-defactor) converge on the same surviving edges? Promote only the winner (or the C6
combination that dominates) to a single full-scale national run.

**The decisive open question the bake-off answers:** which escape dominates — external-info conditioning
(RCoT/GCM on named Z) or breadth-filtered IFE defactoring — and whether both are needed or one suffices.

## 7. Empirical anchors (filled as runs land)

- **Wiring fix (M1, done):** `measured_quantity_refs` returned 0 on the national run (stale
  `__efg_stage_workspace` sidecar path); fallback to the final tensor dir → **74 refs**. count\|exposure
  drives corr(Z, log-exposure) 0.93 → −0.05 column-by-column with each variable's own denominator.
  Commit 524ea00.
- **Phase 1 (current-code clique on SP slice, 2026-07-12):** the CURRENT live pipeline (backbone
  Ω=S−L + Codex's two-way FE projection + structured within-block×bucket null + BY) on real SP data
  (57 kept vars, n=1599 complete-case cells) produces **clique = 1093/1953 pairs (56%)** — the
  near-clique is fully alive; the additive FE projection does NOT collapse it. A planted pure-confounder
  pair (two independent series sharing only population) is **falsely certified** (CKA 0.47, q 0.05),
  while genuine nonlinear edges are correctly detected (CKA 0.74/0.76). Confirms M1–M3 are unaddressed.
- **Phase 3 (factor diagnosis, 2026-07-12):** loading-breadth participation ratio of the residual
  matrix — **E0 pre-FE:** leading factor 33–49% of variance, **PR 0.34–0.37 (BROAD confounder)**; **E_base
  post-FE:** leading factor PR drops to **0.02** and *no* factor exceeds the 0.15 breadth threshold. The
  additive two-way FE projection **already removes the broad cross-sectional confounder.** So a
  supervised regress-out on (time-invariant) population and an unsupervised breadth-filtered IFE strip
  have *nothing broad left to remove* on this data.
- **Phase 4 (bake-off, 2026-07-12; real SP data, exact-mode HSIC, BY-FDR):** the verdict, isolating one
  change at a time:
  | candidate | clq@0 | clq@0.1 (CKA floor) | confounder-pair | genuine edges |
  |---|---|---|---|---|
  | C0 pre-FE | 1100 | 793 | alive (0.45) | survive (0.78/0.77) |
  | C0 post-FE (current) | **616** | **102** | alive (0.45) | survive |
  | C2 regress-out obs Z | 538 | 98 | **DIES (0.01)** | survive (c attenuated 0.77→0.57) |
  | C4 breadth-IFE | 616 | 102 | alive | survive (**0 factors — redundant with FE**) |
  | NULL-calibration | **0** | 0 | — | — |

  **Findings that redirect the plan:** (1) the permutation null + BY-FDR is **well-calibrated** —
  NULLcalib yields 0 edges on an independence-destroyed panel, so the clique is *real* weak dependence,
  not a null artifact; (2) the FE projection removes the broad confounder (1100→616); (3) post-FE the
  clique is dominated by **negligible-effect** edges (CKA median 0.041) — an **effect-size floor
  (CKA≥0.1) is the single biggest lever, 616→102 (6×)**, monotone-safe, one-line; (4) **breadth-IFE is
  REDUNDANT** with the existing FE (0 factors post-FE) — drop it from tier-1; (5) **regress-out of
  observed confounders is still needed for specificity** — it is the *only* candidate that kills the
  shared-denominator confounder pair — but should condition on the **time-varying** population per cell
  (my probe used the muni-mean, redundant with FE) to bite on the real bulk. **Winning stack: FE
  (present) + CKA effect-size floor (new, headline) + regress-out time-varying observed confounders
  (new, specificity).**

## 7a. MAJOR finding — the near-clique is substantially a DEGENERATE-SAMPLING bug (2026-07-12)

Running the *real* `run_ldo` end-to-end (not the harness) surfaced a latent bug the green tests missed
(they use dense synthetic panels where it never triggers): **every** `nonlinear_residual` edge came
back with CKA = 1.0. Root cause, traced step by step:

1. The residual scan's complete-case trimming kept the **largest** variable set with ≥`_MIN_N_EFF`=100
   jointly-observed cells — i.e. it *maximised variable count*.
2. On a real heterogeneous-coverage panel a few sparse variables collapse the intersection: a 54→59
   variable step dropped the shared sample **n from 1599 to 145 cells**.
3. Those 145 cells are spread thinly across municipalities/years, so most (municipality) and
   (block×time) FE groups are **singletons**, which `_project_panel_nuisance` demeans to **exactly 0**
   → the projected residual is a **97% point mass** (unique-value fraction 0.02).
4. A point-mass variable's median-heuristic RBF bandwidth collapses → the centered kernel ≈ identity →
   HSIC(X,Y) ≈ √(HSIC(X,X)·HSIC(Y,Y)) for *every* pair → **CKA saturates to 1.0** → the scan emits an
   everything-vs-everything near-clique of meaningless effect sizes.

So the production residual near-clique is **largely a sampling/degeneracy artifact, not confounding**.
The effect-size floor (7b) cannot help while CKA is pinned at 1.0. **FIX (committed):** select the
variable subset that maximises `n_vars × complete_case_n` (sample-quality-aware, not count-greedy) via
incremental masking — on the SP slice this keeps 35 well-covered vars at **n=13547, unique-fraction
1.0** (non-degenerate), and CKA becomes meaningful again (e.g. 0.97 for two SINASC per-birth counts
that genuinely share the births scale — a real Kronmal channel). Plus a **degeneracy guard**: refuse
with a typed skip if the projected residual is still a point mass (median unique-fraction < 0.05),
recorded in `residual_scan_error` rather than emitting garbage. Dropped variables are reported
(`residual_scan_vars_dropped_for_coverage`). On dense panels the product is maximised at the full set →
no behaviour change. This is the highest-impact fix of the session — it is a prerequisite for the whole
residual layer (effect floor, confounding analysis) to mean anything on real data.

## 7b. Implementation status (Phase 5)

- **DONE — Effect-size floor (Layer D), committed.** `scan_residual_nonlinear_edges` now gates edges on
  a normalized-HSIC (CKA) floor (`run_ldo(residual_effect_floor=)`, default 0.05); the weight already
  carries the CKA. Monotone-safe, drop count recorded. Validated: real SP data 696→84 edges at CKA≥0.1
  (n=1599) / 1100→102 (n=366); unit test `test_ldo_effect_size_floor.py`. This is the single biggest lever.
- **NEGATIVE RESULT — the deconfounding-projection layers are largely REDUNDANT with the existing FE.**
  On real data the additive two-way FE projection (deddf68) already strips the broad confounder
  (participation ratio 0.34→0.02), so: (a) breadth-filtered IFE finds **0 factors** post-FE; (b)
  muni-level regress-out on observed population is **byte-identical** to the FE baseline (696→696). The
  synthesis ranked these tier-1, but the empirics show FE + the effect floor capture their value at a
  fraction of the complexity. Do NOT build them speculatively.
- **DEFERRED / unresolved — time-varying confounder regress-out.** The within-muni population TREND
  survives FE (which removes only the muni mean), so conditioning on per-(muni,year) population *could*
  remove residual within-muni confounding the floor doesn't. Untestable here: the population tensor's
  per-(muni,year) keys align with only **9%** of panel cells at year grain (a data-alignment gap, not a
  math gap). Prerequisite: reconcile the population tensor's geo/year keys to the panel before this can
  be measured.
- **NEXT principled step (not yet built) — raw-count Kronmal margin (Layer A).** The 40 raw extensive
  counts (SIM/SIH/SINASC direct counts) have NO `measured_quantity_ref` (they are not RN ratios), so
  they never get a count|exposure margin — the shared-population/denominator (ratio-standard) channel is
  addressed only for the 74 RN rates. Fix: route each raw count to its CORRECT semantic exposure
  (population / births / admissions) via `exposure_field_by_variable`, conditioning on the denominator
  at the margin. Requires a per-variable denominator registry (§O7 / §X shared-normalizer abstraction).
  Its incremental value beyond FE+floor is unmeasured — validate before building.

## 7c. Cross-scope validation + the provenance-aware pruning finding (2026-07-12)

The fixes were validated on real SP data across THREE disease scopes (not just C25), each on the fixed
`run_ldo` (cliff-rule trimming + degeneracy guard + effect floor):

| scope | residual_err | CKA p50/p90/p99 | clique @CKA≥0/0.05/0.1 |
|---|---|---|---|
| perinatal (SINASC+SIM) | None (non-degenerate) | 0.017 / 0.158 / 0.997 | 498 / 163 / 76 |
| arbovirus (Dengue/Zika/Chik) | None | 0.012 / 0.149 / 0.999 | 153 / 29 / 19 |

**The fixes GENERALIZE** — non-degenerate samples, distributed CKA, floor collapses the clique in every
scope. But the cross-scope data exposes the NEXT target: **the top of the CKA distribution is dominated
by MECHANICAL relationships, not epidemiological determinants.** The highest-CKA (≈1.0) surviving edges
are, in every scope:
- **denominator/exposure leakage** — the 4 `population_tensor_solver_independent_denominator_{total,
  age_group,sex,race}` are collinear DENOMINATORs that leak into the analytical *outcome* set
  (`analytical_variable_ids` keeps any non-structural role), so they form CKA=1.0 self-pairs AND are a
  §IV circularity (a count|exposure denominator also tested as an outcome);
- **duplicate-named strata variables** — 18 names appear on ≥2 distinct field_ids (same measurement over
  icd_chapter/block/… strata) → collinear mechanical edges + ambiguous output;
- **nested definitions** — `Dengue ⊂ Arbovirus` (CKA 0.74), Zika/Chikungunya ⊂ Arbovirus;
- **shared-denominator counts** — SINASC per-birth counts (`deceased_children ↔ prior_pregnancy` = 1.0)
  all share the births scale (the Kronmal channel).

**The reframing for edge pruning (§7d / task PRUNE):** effect size ALONE is a poor discriminator because
the MOST-dependent edges are the LEAST interesting (mechanical). The credibility of a residual edge is
NOT monotone in CKA — it is high in a MIDDLE band (a genuine determinant), low at CKA≈0 (noise) AND low
at CKA≈1 (mechanical/duplicate/nested/shared-denominator). The discriminator that separates mechanical
from genuine is PROVENANCE (the EFG lineage: shared carrier/source/denominator, nesting, duplication),
not magnitude. So the composite is **provenance-aware**: gate/demote mechanical edges via lineage, then
rank the survivors by (effect-size band × stability × causal orientation × holdout persistence).

Highest-leverage, monotone-safe first increments: (a) exclude pure denominator/exposure variables
(population strata) from the analytical OUTCOME set (fixes the CKA=1.0 population pairs + the §IV
circularity); (b) extend the mechanical-overlap guard (§5.3, currently disease-code Jaccard only) to
LINEAGE overlap (shared denominator, nesting, duplication) so those edges are typed `mechanical_overlap`
(descriptive, never a discovery); (c) a near-duplicate guard (CKA≈1.0 + shared lineage). All demote-only
(monotone-safe). Then the graded credibility tier.

## 7d. Spatial-kernel reopening — the kernel is marginal, the FE projection owns the spatial channel (2026-07-12)

The spatial-kernel choice (raw queen contiguity, default) was reopened given the residual-layer
developments. Measured residual spatial autocorrelation (Moran's I on the SP muni graph, pooled over
variable-years) at each stage, under contiguity vs a distance-kNN Gaussian kernel:

| stage | Moran \|median\| (contiguity) | (knn_distance) |
|---|---|---|
| raw Gaussianized Z | 0.50 | 0.50 |
| backbone residual, POST-whitening, PRE-FE | **0.50** | 0.48 |
| residual POST two-way FE projection | **0.10** | 0.10 |

Two findings: (1) **the GMRF whitening (`κI + L_sym`) does NOT reduce the residual's spatial
autocorrelation** — `e = ΩZ/diag(Ω)` is computed on the *unwhitened* Z; the whitening only removes
spatial autocorrelation from the *correlation estimate* feeding the graphical lasso (making the backbone
partial-correlation edges spatially honest), not from the residual field. (2) **the spatial channel of
the residual layer is owned by the two-way FE projection** (0.50 → 0.10) + the within-spatial-block
structured null, NOT the GMRF kernel; and **contiguity vs distance-kNN are indistinguishable at every
stage.** So the kernel choice is genuinely marginal for the residual layer — keeping raw contiguity is a
justified conclusion (§III "the safe default is adequate"), not negligence. The remaining residual Moran
≈ 0.10 post-FE is real (a reason the structured null must permute within spatial blocks) and is the
opening for the tier-2 **reduced-rank spatial+** (§4 Layer C) — remove the smooth low-rank spatial driver
while keeping fine cross-sectional signal — should a future need to sharpen the residual spatial handling
arise. Not built now (its incremental value over FE+null is unmeasured; the kernel swap it would replace
is marginal).

## 7e. Provenance-aware pruning — shipped increments + validation (2026-07-12)

Two monotone-safe (demote-only) pruning increments landed and validated on real SP data:

- **Denominator/exposure exclusion** (commit, `field_selection`): a variable carrying
  `population_denominator_seed` is the exposure, not an outcome — excluded from the LDO variable set
  (national analytical set 306→301; the 4 collinear population-strata CKA=1.0 self-pairs gone; §IV
  circularity closed).
- **Mechanical-overlap guard extended** (`edges.py` + `orchestrator`): a CONTAINMENT criterion
  (`|A∩B|/min(|A|,|B|) ≥ 0.9`) catches code-set NESTING even at low Jaccard, and the guard now runs on
  `nonlinear_residual` edges (re-applied after the residual scan). **Validated live on arbovirus:** 4
  Dengue⊂Arbovirus *count* edges correctly demoted to `mechanical_overlap` (`nested_codes`); combined
  with the exclusion + effect floor the clique fell to **65** residual edges (from 153), **8** at
  CKA≥0.1.

**Known remaining gap (next increment):** the DERIVED variables (RN rate/share of Dengue vs Arbovirus)
still surface at CKA 0.73 because they carry NO code_set — `disease_variable_meta` reads codes from
`support.restrict_conditions` (present on the σ_C count numerator, absent on the RN rate), and
`V_fields` persists only `lineage_hash`, not `parent_ids`. Clean fix = propagate the numerator's code_set
to its derived RN field (a rate's codes ARE its numerator's codes) — an **EFG-side change**: persist
`lineage.parent_ids` in `V_fields` (see [`modules/efg.md`](modules/efg.md) §1 content-addressed lineage),
then `disease_variable_meta` inherits the parent's code_set. This is the §X "wire the declared semantics
through to consumers" move.

**Still to build (the larger design):** a graded **edge-credibility tier** for residual edges — they are
currently certified on q-value alone (`certify.py`), lacking the stability/effect-size-band/causal-rung
composite that backbone edges get. Credibility is non-monotone in CKA (§7c): the tier should combine
effect-size band × cross-fit fold agreement × (holdout persistence, causal orientation where available),
NOT rank by raw CKA.

## 7f. Epidemiological-substance validation — the output is meaningful (2026-07-12)

Ran the full LDO on a real cross-domain SP slice (43 vars: mortality rates × birth outcomes ×
healthcare cost × data-quality × SIDRA socioeconomic) with the complete stack (degeneracy fix + effect
floor + all three mechanical guards + LiNGAM). Result: **62 edges, 22 certified, the clique gone**, and
the certified edges are textbook epidemiology, NOT artifacts:
- **infant-mortality cluster** — neonatal ↔ postneonatal ↔ infant mortality co-vary (0.32/0.24) — a
  genuine ecological pattern;
- **birth-outcome web** — prematurity ↔ low-birth-weight ↔ cesarean ↔ congenital anomaly ↔ infant death;
- **health-system** — total billing cost ↔ inpatient fatality; socioeconomic ↔ inpatient fatality;
- **socioeconomic covariate structure** among SIDRA context variables;
- 31 edges causally oriented (LiNGAM), one rung-2 (ITS-escalated).
Mechanical artifacts correctly DEMOTED: `PostNeonatalDeaths ↔ its own rate` (shared numerator),
`ChapterMortality ↔ CuratedCauseMortality` / `SIMCrudeMortality ↔ ChapterMortality` (same `Deaths`
numerator, different stratification). **The three mechanical-guard classes now cover the artifact
taxonomy:** denominator/exposure leakage (excluded), disease-code nesting (containment), and
shared-numerator count↔rate (carrier). On the graded credibility TIER: the LDO already emits, per edge, all the discernment signals — effect
size (`weight`=CKA / partial-corr), causal rung (LiNGAM), `stability`, `fdr_qvalue`, and mechanical
typing (`edge_type`+warnings) — and the three mechanical-guard classes + the effect floor do the
pruning. Baking a fixed strong/moderate/weak TIER into the LDO would impose arbitrary effect-size
thresholds (§V "do not expose deep parameters as static constants"); the banding belongs in the Output
Query Layer (which consumes the raw signals), so the LDO stays threshold-free. This is a justified
"the safe default is adequate" conclusion (§III), not a gap — the output is substantive, pruned, and
carries every signal a consumer needs to rank.

**#84 CONCLUDED.** The edge-pruning architecture is complete: effect-size floor + denominator-exposure
exclusion + the three-class mechanical-overlap guard (code-nesting / shared-numerator / denominator) +
LiNGAM causal orientation — validated to produce a substantive epidemiological graph on real data.

## 8. References (by layer)

- **Deconfounding:** Ćevid, Bühlmann, Meinshausen — spectral deconfounding / trim transform. Wang,
  Zhao, Hastie, Owen 2017 — CATE. Gagnon-Bartsch & Speed — RUV-4. Leek & Storey — SVA. Sun-Zhang-Owen —
  LEAPP. Zheng-Ke — BEMA (factor count).
- **Interactive fixed effects:** Bai 2009. Pesaran 2006 — CCE. Athey et al. 2021 — matrix completion.
  Ahn-Horenstein 2013 — eigenvalue-ratio rank. Chandrasekaran-Parrilo-Willsky — sparse+low-rank.
- **Conditional independence:** Shah & Peters 2020 — GCM. Strobl et al. — RCIT/RCoT. Zhang et al. 2011 —
  KCI. Pogodin et al. 2024 — SplitKCI.
- **Spatial confounding:** Reich-Hodges-Zadnik 2006 — RSR. Hodges & Reich 2010. Hughes & Haran 2013.
  Dupont, Wood & Augustin 2022 — spatial+. Guan et al. 2023 — spectral. Khan & Calder 2022 —
  anti-conservative null warning.
- **Counts/rates:** Kronmal 1993 — ratio-standard fallacy. Lause-Kobak-Berens — analytic Pearson
  residuals. Dunn & Smyth — randomized quantile residuals. Clayton-Kaldor / BYM — EB rate shrinkage.
- **Multiplicity:** Benjamini-Yekutieli. Fan-Han-Gu — FarmTest / PFA. Efron — empirical null.
  Barber-Ramdas — p-filter. Li-Ji — effective number of tests. Afyouni-Smith — xDF.
- **Scalable HSIC:** Rahimi-Recht — RFF. Williams-Seeger — Nyström. Zhang et al. — block HSIC.
