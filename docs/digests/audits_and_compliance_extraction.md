Full read-only extraction of the 11 requested PegaSUS documents (all read in full; nothing edited). Organized per-document, then two consolidated lists at the end. "Stated" = document's own claim; "Inferred" = my synthesis/labeling across docs.

═══════════════════════════════════════════════════════════════
## 1. PEGASUS_LDO_COMPLETENESS_AUDIT.md (336 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** Generated 2026-07-06, "70-agent adversarially-verified review" of PEGASUS_MSD_III.md vs the LDO/EFG implementation. This is the **LDO build ledger** — each row is a normative MSD-III clause with a Status column tracking whether the live national `run_ldo` path satisfies it. Updated through a 2026-07-07 20-agent adversarial re-verification (O1–O19).

**Named components (LDO internals):**
- **LDO** = Latent Dependency Operator — the final inference stage; fits sparse+low-rank Gaussian precision Ω=S−L then a residual HSIC scan, emits typed `LinkRecord`s.
- **CPW decomposition** — Chandrasekaran–Parrilo–Willsky sparse+low-rank precision split Ω=S−L (graphical-lasso ℓ1 sparse S + nuclear-norm low-rank L), via LVGLASSO/ADMM.
- **L_W** — spatial GMRF operator κI+L_W (Σ_space⁻¹), whitening metric.
- **L_D** — disease-structure Laplacian (DiseaseGraph.laplacian()), meant as a prior-regularizer quadratic (γ/2)·tr(SᵀL_DS).
- **L_time** — temporal-smoothness Laplacian quadratic (5th of the "five simultaneous structural assumptions" in §III.4(5), alongside L_W, L_D).
- **spatial_field_ref** — LinkRecord field carrying a per-edge spatially-varying-coefficient (BYM/ICAR) field.
- **Adaptive Precision Controller (§V.5)** — anytime budgeted scheduler (`compute/controller.py`, Budget/Quantity/`adaptive_precision_run`) setting every approximation dial by value-of-computation; self-corrects (escalate numerically-dominated decision-relevant edges to exact).
- **CoverageManifest (§VIII.2(3))** — typed record of searched vs. unsearched regions + stated sparsity-of-truth assumption; "never a silent gap."
- **Causal ladder (Part IV)** — Rung-0 (time precedence) → Rung-1 (LiNGAM orientation + collider/v-structure) → Rung-2 (ITS/DiD/negative-control quasi-experimental escalation) → Rung-3 (do-calculus, expert-invoked only, never autonomous).
- **Kronecker joint operator (§V.2)** — Ω_var⊗Σ_space⁻¹⊗Σ_time⁻¹ factored matvec/logdet/solve, avoiding the (p·S·T)² dense object.
- **Stochastic log-det (§V.3)** — Hutchinson + stochastic Lanczos quadrature (SLQ), anytime/probe-controlled.
- **Mixed precision (§V.1/§V.4)** — float32 bulk, float64 reductions/logdets; condition-number monitor escalates to float64.
- **Exact-certifies-approximate (§V.6(3))** — a state-scale exact CPW run must agree with the national approximate run within propagated bounds; disagreement rejects loudly.

**Progress log — work packages (WP1–WP8) all marked DONE** by commit, closing the corresponding gaps:
- WP1 (temporal + disease-L_D quadratics, `f774e28`) — BLO-1, MAJ-2/4/5/6
- WP4 (HSIC completeness: structured null, FDR regime, descriptive gate, MR continuation, `0af97c3`) — BLO-2/3, MAJ-7/8
- WP5 (causal ladder: collider orientation, Rung-2 ITS, `4f3bca7`) — MAJ-9/10, MIN-4/5
- WP6 (honesty layer: numerical-error propagation, certification conjunction, coverage manifest, exact-certifies-approx, `1445679`) — BLO-4/7, MAJ-11/13/18/21/22/23, MIN-1/2/6
- WP3 (count-with-exposure end-to-end incl. EFG sidecar transport, `f7573fb`) — BLO-9/10, MAJ-19
- WP7 (adaptive precision controller, `c1761cc`) — BLO-8, MAJ-24/25
- WP8 (§V.3 SLQ `95ca4be`; §V.1 mixed precision `a4731f6`; §V.2 Kronecker `ff90e86`) — MAJ-14/15/16/17, MIN-7/8/9/10
- WP2 (§VIII.2 sensitivity screen + random deep audit `080ddf1`; §III.3 spatial BYM field `3370e67`) — BLO-5/6, MAJ-1/3, MIN-3

**⚠ Important self-correction inside the document (2026-07-07):** the initial "all closed" claim after WP1–WP8 was an **overstatement** — a 20-agent adversarial re-verification found only 9/45 gaps cleanly resolved, ~9 partial/unresolved, and 2 §III.8 conjuncts never audited. Root cause: the national run used `resolution='year'` (~139k cells), under the old 300k `use_mr` gate, so the whole §VIII.2/§V.6 multiresolution shell never fired on the actual flagship run. The subsequent **O1–O19 remediation wave** (commits `458c986`…`6030edc`) is stated to have closed all 19 items — 17 as tested builds, 2 (O15/O16) as documented scope boundaries (O15: out-of-core streaming beyond RAM is a ceiling; O16: JL neighborhood-sketch is "architecturally N/A" since the LDO fits the joint CPW precision, not per-node regressions).

**Requirement IDs enumerated with status** (all individually tagged `_Status: PENDING_` at time of listing — i.e., this ledger's per-item status lines were NOT updated even though the progress log / gap-resolution index above claims them closed; the doc explicitly says "the per-gap Status lines remain the original review state" — so status must be read from the commit map, not the inline `_Status_` tag):
- **BLO-1** [missing→DONE via WP1 f774e28] §III.4(5) temporal-smoothness Laplacian quadratic (γ/2)tr(SᵀL_timeS), tying adjacent lag positions.
- **BLO-2** [present_divergent→DONE WP4] §6.8/§6.9 HSIC null must be the panel-support-keyed STRUCTURED null (spatial-block+cyclic-time-shift for annual muni; season-preserving moving-block circular shift for monthly), not iid/wrong-support permutation.
- **BLO-3** [present_divergent→DONE WP4] §III.6 residual nonlinear audit must actually run (coarsen/tile rather than silently refuse) on national scale.
- **BLO-4** [missing→DONE WP6] §V.6(3)/§IX.3 exact-certifies-approximate runner.
- **BLO-5** [orphaned→DONE WP2 080ddf1] §VIII.2(1) sensitivity screen (subgroup heterogeneity, not pooled mean) as the coarse→fine filter.
- **BLO-6** [missing→DONE WP2] §VIII.2(2) random deep audits measuring empirical false-negative rate on pruned branches.
- **BLO-7** [orphaned→DONE WP6] §VIII.2(3) typed CoverageManifest emitted on the live path.
- **BLO-8** [orphaned→DONE WP7] §V.5 Adaptive Precision Controller wired live (was built, zero callers).
- **BLO-9** [orphaned→DONE WP3] §II.3 EFG terminal output must be a MeasuredQuantity {count,exposure,offset_semantics,structure,provenance,uncertainty}, not a materialized rate.
- **BLO-10** [orphaned→DONE WP3] §II.3/§I.2/§III.5 count+exposure margin: log E[count]=log(exposure)+effects modeled directly, not gaussianized off a pre-divided rate.
- **MAJ-1** [present_divergent→DONE WP2 3370e67] §III.4(5)/§III.3 spatial BYM/ICAR varying-coefficient field distinct from the whitening metric; populate `spatial_field_ref`.
- **MAJ-2** [present_divergent→DONE WP1] §III.4(5) disease Laplacian L_D as smoothness quadratic (was only adaptive-ℓ1 discount).
- **MAJ-3** [present_divergent→DONE WP2/O5] §III.7/§XI stability selection must perturb full Place×Time lattice + tuning, not spatial-only.
- **MAJ-4** [missing→DONE, via edges.py stability wiring per WP-era commits] §III.7/§XI latent_shared edges must also pass stability selection (not just contemporaneous/lagged).
- **MAJ-5** [missing→DONE WP2/O6] §III.3 multiresolution hierarchical shrinkage on disease axis (chapter+block+category+leaf sum-of-scales).
- **MAJ-6** [orphaned→DONE WP1] §II.6/§5.2 DiseaseGraph.laplacian() (L_D) must actually enter the LVGLASSO S-step.
- **MAJ-7** [present_divergent→DONE WP4] §6.8 FDR method must be resolved by panel-support regime (BY for annual/monthly panels; BH cross-sectional; Storey-q facility stock), not hardcoded BH.
- **MAJ-8** [present_divergent→DONE WP4] §6.8 descriptive-only gate must be the disjunction (spatial_blocks<5 OR temporal_blocks<5), not spatial-only.
- **MAJ-9** [stubbed→DONE WP5] §IV Rung-1 collider/v-structure detection (`is_collider` existed but was never called on unshielded triples).
- **MAJ-10** [orphaned→DONE WP5] §IV Rung-2 quasi-experimental escalation (ITS/DiD/negative-control) triggered by detected structural breaks.
- **MAJ-11** [present_divergent→DONE WP6] §V.6(2) numerical-approximation error must widen edge uncertainty (randomized-SVD/logdet error), never present approximate as exact.
- **MAJ-12** [orphaned→DONE WP2] §VIII.1/§III.3/§V.1 coarse→fine multiresolution as the live discovery strategy (resolution.py covered "<20%" of it at audit time).
- **MAJ-13** [missing→DONE WP6] §V.6(2) — duplicate/companion of MAJ-11 (fold numerical error into LinkRecord.uncertainty in quadrature with statistical uncertainty via shared `Quantity.total_uncertainty`).
- **MAJ-14** [missing→DONE WP8 95ca4be] §V.3 stochastic log-determinant (Hutchinson+SLQ) as an anytime evaluator feeding §V.5/§V.6 (explicitly NOT a replacement for the ADMM prox eigh — "category error" to swap).
- **MAJ-15** [present_divergent→DONE WP8 a4731f6] §V.1/§V.4 mixed precision + condition-number escalation; also fixes `estimate_ldo_bytes` under-counting peak memory ~2×.
- **MAJ-16** [present_divergent→DONE WP8 ff90e86] §V.2 Kronecker-factored joint operator (matvec/logdet/solve) replacing dense-eigh-on-lag-stacked-features.
- **MAJ-17** [present_divergent→DONE WP8] §V.1 compute-envelope refusal must be truthful (byte model must match actual dtype used, else the guard can green-light an OOM).
- **MAJ-18** [missing→DONE WP6] §V.6(3) exact-certifies-approximate as a live gate on the investigate path (duplicate of BLO-4, more detailed FIX).
- **MAJ-19** [orphaned→DONE WP3] §III.5/§I.2/§II.3 copula margins: extensive quantities must use count-with-exposure (Poisson-offset) margin, never a pre-divided rate.
- **MAJ-20** [orphaned→DONE, RES-01 21c42d3] §III.3/§I.5/§VIII/§XI.3 multiresolution coarse→fine readout wired into `run_investigate` (was calling flat `run_ldo`).
- **MAJ-21** [present_divergent→DONE WP6] §III.7/§III.8/§V.6(2) promotion must be a true conjunction: stability AND propagated uncertainty for lagged/contemporaneous edges.
- **MAJ-22** [orphaned→DONE WP6] §III.8 standing abort: an edge promoted without stability/uncertainty must hard-fail (not soft-downgrade only).
- **MAJ-23** [present_divergent→DONE, ties to MAJ-1] §III.7 output payload must populate `spatial_field_ref` per certified edge.
- **MAJ-24** [present_divergent→DONE WP7, "state-tensor uncertainty into W (n_eff)"] §3.12/§3.12.3 Q-tensor must be the single live producer of state (n_eff, Moran's-I-deflated Kish weighting, provenance risk).
- **MAJ-25** [stubbed→DONE WP7] §II.3 MeasuredQuantity.uncertainty must carry the full §3.12 state tensor (14 components), consumed by the LDO as observation weight, not a lone scalar.
- **MIN-1** [missing→DONE WP6, o3 121d3f6] §V.6(3)/Appendix F.3 two-run CPW reconciliation (exact state-scale vs approximate national).
- **MIN-2** [missing→DONE WP6, O13 6bd06a6-family] §V.6 whitening-operator error propagation (Lanczos-sqrt approx error → edge uncertainty).
- **MIN-3** [present_divergent→DONE O5 d3920d9] §III.7 stability subsampling must perturb BOTH Place and Time (was spatial-only) plus tuning jitter.
- **MIN-4** [missing→DONE MIN-4 via WP5, "compliance by prohibition"] §IV Rung-3 do-calculus, expert-invoked-only entrypoint (optional, non-autonomous).
- **MIN-5** [present_divergent→DONE WP5] §IV every causal claim must carry typed `rung`+`assumptions` fields on LinkRecord.
- **MIN-6** [orphaned→DONE WP6] §III standing abort must be an actual live post-certification gate call (`assert_ldo_edge_promotion_allowed`), not "true by construction, unchecked."
- **MIN-7** [missing→DONE WP8, "reclassified as intentionally-exact"] §V.3 stochastic logdet — resolved by declaring the LDO's dense eigh intentionally exact (bounded p) rather than needing the stochastic estimator, while still adding §V.6(2) error propagation.
- **MIN-8** [missing→OPEN per O16 "architecturally N/A"] §V.3 JL sketching for neighborhood regressions — ruled not applicable since the LDO fits the joint CPW precision, not per-node neighborhood regressions.
- **MIN-9** [missing→O15, documented ceiling] §V.4 streaming sufficient statistics (out-of-core scan_parquet) — the moment algebra is already streamable and fits at national scale; the true out-of-core (beyond-RAM) extension is a stated, undone ceiling.
- **MIN-10** [present_divergent→DONE WP8] §III.4(3)/§V.2/Appendix F(2) Kronecker/separable structure — FIX text is truncated/empty in the source document (ends mid-sentence at line 336; this is a defect in the source file itself, not a read error).

**Subsystem verdict table (gaps/reqs ratios, at time of the original 70-agent audit, before WP1–8/O1–19 closed them):** CPW decomposition 1/11 mathematically complete; spatial GMRF 3/9; lag+temporal-smoothness+stability 4/9; disease L_D 3/5 NOT complete; residual HSIC audit 5/8 partial; causal escalation 5/8 partial; certification/bounded-exhaustiveness 8/14 NOT complete; Computation&Scale 10/12 NOT complete (Adaptive Precision Controller orphaned); LDO orchestration+output 6/17; EFG legality/MQ 4/6.

**Final status summary in doc:** "All 8 work packages landed... 356 tests green... sole remaining research ceiling: full SPDE/INLA latent-Gaussian multiresolution field (the per-edge BYM varying-coefficient shipped in WP2 is its realized carrier)." Net after O1–19: "17 as landed tested builds, 2 (O15/O16) as a genuine bounded implementation plus an honest §V scope boundary."

═══════════════════════════════════════════════════════════════
## 2. PEGASUS_COMPLIANCE_AND_REMEDIATION.md (531 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "Master Compliance & Remediation Report" — working contract for bringing `/src` into compliance with the MSD. Derived from a line-level read of the MSD (6,823 lines) + `/src` (227 files, ~35k LOC) + 42-file registries tree. Undated internally but part of the same review era (references 2026-07 commits elsewhere in the corpus).

**Central thesis — the "two-tier structure":** a *contract/scaffolding tier* (decoders, registries, legality predicate, population objective, HSIC/null machinery, certification thresholds, 17-key validator) that is rigorous/faithful to the MSD, sitting above a *production/numeric tier* (vectorized normalizers actually wired in, GLM family/spatial coverage, race-bridge numerics, SIDRA-context path) that is a **reduced MVP**. "The system validates far more than it computes."

**Severity legend:** S0 Contract breach (silently wrong science) · S1 Capability gap (mandated capability absent/stubbed) · S2 Fidelity gap (weaker than MSD, mislabeled/approximate) · S3 Hygiene (no scientific impact).

**Genuinely strong / COMPLIANT (kept as-is):**
- Composite decoders (`datasus/decoders.py`) — faithful §2.4.0.1–.5.
- Population tensor objective (`she/population/loss.py`) — "Best-in-codebase," analytic loss+sparse gradients for every §2.8.4–2.8.9 term.
- EFG legality predicate (`efg/legality.py`) — full seven-part structural predicate + §3.8.8 declaration gate.
- Race declaration gate (`efg/declaration.py`) — blocks the §4.3 illegal direct division (§10 abort).
- HSIC scanner+nulls+FDR+cross-fitting (`pirs/hsic.py`,`nulls.py`,`fdr.py`,`crossfit.py`) — faithful §6.5–6.9.
- ST-DFM certification (`she/stdfm/certification.py`) — faithful §2.10.4.
- Output 17-key validator (`output/validate.py`,`schemas.py`) — faithful §8 contract.
- EFG physical executor (`efg/executor.py`) — real Polars materialization, σ_C restriction, ecological-fallacy guard, cross-join prohibition.
- SIDRA regime classifier (`sidra/regime.py`) — faithful §2.9.

**Headline S0/S1 problems (finding IDs):**
1. **`SHE-NORM-01` (S0, "the most important fix in the report")** — the four production `normalize_*_events` functions (SIM/SIH/SINASC/CNES) re-implement decoder logic inline (bypassing `datasus/decoders.py` and the registry-driven `declarative_normalize.py`) and null out most of the §2.4 canonical schema: SIM cause_chain_norm/associated_conditions_norm/observer marks; SIH secondary_icd_set/ICU marks/movement geography/CNPJ; SINASC continuous birth_weight/APGAR/parity/gestation/typed anomaly_icd. Also collapses §2.3's five distinct missingness states (Unknown/Missing/Invalid/Unparseable/NotRecorded) to a binary "unknown." Downstream this makes `V_M05/M06`, `V_H06/07`, `V_C07/10/11/12/13`, and the FacilityFlow bridge uncomputable. Remediation: Path A (preferred) — extend `source_fields.yaml` with raw→canonical routing (raw_fields/route/decoder per canonical field) and make `declarative_normalize.py` the single record-level normalizer; Path B (fallback) — make the vectorized `_events` functions decoder-backed and complete.
2. **`SHE-CNES-01/02/03` (S0)** — CNES emits forbidden generic `capacity_total_observed` (sums QTLEIT*+QTINST* — exactly what §2.4.4 forbids, mixing bed and infrastructure indices) and skips `filter_cnpj` at ingest (§2.4.0.5 gate unenforced) and does `fill_null(0)` before summing (§2.3 missing≠zero violation).
3. **`SHE-SINASC-01` (S0)** — SINASC SHE layer bakes EFG-level outcome indicators (`low_birth_weight_flag` etc.) instead of emitting primitives (§2.4.3 vs §3.10.4 layering violation); the proximate cause of several `V_C` fields being uncomputable.
4. **`PIRS-SPAT-01` (S1)** — §6.3 spatial effect modes (`ICAR`/`UF_FE`/`municipality_FE`) are "entirely absent" anywhere in the codebase; the GLM is non-spatial, biasing SEs on spatial outcomes.
5. **`SIDRA-CTX-01` (S1)** — SIDRA context + ST-DFM machinery exists (regime/stitch/project/pushforward/cert modules faithful) but is inert end-to-end: acquired to disk, never routed into EFG context nodes; ST-DFM explicitly skipped in `compile.py`.
6. **`RACE-01` (S2)** — race bridge runs only the fast-mode fixed-W approximation: applies the prior matrix C directly as crosswalk W instead of computing the Bayesian local-π posterior crosswalk (§4.5.3); no posterior simulation (§4.6); partial-ID bounds are a heuristic ±width band, not the true inf/sup over the credible set (§4.7); `race_bridge_cv` measures the wrong quantity (cross-category spread instead of bootstrap dispersion), feeding downgrade/promotion gates incorrectly.
7. **`SHE-POP-02` (S1)** — large-scale population solvers: only `projected_gradient_small`/`sparse_block_coordinate` active; `sim_informed_sparse_admm_scaffold_v1` is a `legacy_warning_scaffold`; no real state-space smoother; `primal-dual_sparse` (§2.8.12) absent from the code entirely.
8. **`REG-*` cluster (S3)** — four orphaned alias-stub registries (`{aggregation,carrier,provenance,unit}_registry.yaml`) kept alive only because the validator (`REG-VALIDATOR-01`) points at the dead names instead of the live short-name files; stale SIDRA filename tuple referencing 3 nonexistent files; scaffold `output_schema.yaml`; 2-entry model registry vs 8-family real GLM.
9. **Cross-cutting `XCUT-05` — the MSD itself has no "valid partial run" concept**, so the code resolves the tension silently (context inert, ST-DFM skipped, but the 17-key bundle still "validates" structurally).

**Designed resolution — the Run Profile contract (§3.2, the report's own architectural proposal, not yet built):**
`RunProfile ∈ {core_vital, contextual, full}`. `core_vital` = SIM/SIH/SINASC + independent denominator only (B_reconstructed/B_latent/B_cross-sectional MAY be empty, ST-DFM/SIDRA not required). `contextual` = core_vital + SIDRA compendium routed through regime→stitch→projection→bounded pushforward (+ ST-DFM where gated). `full` = contextual + full §2.8 demographic tensor over (s,t,a,x,r) + race bridge over real census strata. Makes the 17-key bundle **profile-aware**: all 17 keys must still exist (hard abort unchanged), but a `PROFILE_NONEMPTY` map states which keys must be non-empty per profile, and any empty-but-legal key must carry an explicit `empty_by_profile` reason row in Warnings — "the crucial anti-silence guarantee."

**Secondary internal MSD tension (§3.3):** §2.8.2 defaults denominators to independent (λ_D=0), but §2.6.5 (perinatal) and §3.10.4 (V_C01–V_C14) presuppose lagged-birth denominators the default never reconciles with. Resolution proposed: fold V_C04/V_C05/lagged maternal-child bridge into `contextual`-or-higher, emitting `quarantined_descriptive` under `core_vital`.

**Consolidated compliance matrix** (§11) maps every finding ID to MSD section, contract-tier status, production-tier status, severity — full table reproduced in the source; key line: "Run-profile contract | 1.2/8.1/9/10 | Absent (tension) | Resolved silently | S0 (process)."

**Prioritized remediation roadmap (§12):** Phase 0 (registry hygiene + Run Profile contract, small/high-leverage) → Phase 1 (`SHE-NORM-01` Path A — "highest-impact fix in the report" — + SINASC/CNES/decoder fixes + Q-tensor completion) → Phase 2 (spatial effect modes, GLM families, race-bridge correctness steps 1–2) → Phase 3 (light up `contextual`: SIDRA context wiring + high-card axis bound + race posterior simulation/partial-ID) → Phase 4 (light up `full`: ADMM/state-space solver, full demographic tensor + real race bridge).

**MSD amendments required (§13, spec-side, not code):** add §1.5 Run Profiles; reconcile §2.8.2 denominator default with maternal-child preconditions; either build or delete the §2.8.12 `primal-dual_sparse`/state-space-smoother bands; state facility-stock uses BY (not Storey-q) if unimplemented; restate §8.1 as "all 17 keys present; profile-required keys non-empty; empty keys carry an explicit reason."

═══════════════════════════════════════════════════════════════
## 3. PEGASUS_ARCHITECTURE_AUDIT.md (223 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "Architectural / Mathematical / Computational-Compliance Audit," whole-codebase vs MSD-III (esp. Part V), multi-agent adversarially-verified (8 dimensions, 41 agents). Generated 2026-07-06. 21 findings total, 20 survived verification, 1 refuted.

**Remediation progress section** (landed, test-gated, "full suite 352 green" at time of writing): CPW S/L collapse fix (incoherence gate, `06acb2f`); residual-scan precision misalignment fix (`95cbfa4`); anticonservative iid-HSIC-null fix (structured within-UF permutation, `1847294`); unconverged-ADMM certification gate (`0f0c324`); planted-factor identifiability fix (`4cd7388`); spatial GMRF whitening wired; causal LiNGAM orientation wired into `run_ldo`; §V.3 randomized SVD for low-rank factors; Kronecker (#2) reframed as inapplicable to the LDO's bounded sample-based design (never builds the (pST)² object §V.2 targets); disease-axis gaps (#11/#13) reconciled via documentation. **Dead-code correction:** the audit's own dead-code list was found unreliable on verification — 3 of its "clean deletes" (`she/sih_costs.py`, `she/cnes_capacity.py`, `sources/sidra/projection.py`) are governed PANEL-01 KEEPs with explicit "do not reap" banners, and its import-detector missed `from pkg import module` form. Only `dashboard/hsic_readonly.py` + an empty `studies/` dir were safely removed.

**Key reframe:** the annexed Pylance dump is stale/noise (cited "zombie trees" already deleted). "The real damage is in the LDO mathematical core... MSD-III Part V is ~30-40% wired — the building blocks exist as modules but are not connected to the live estimator."

**Ranked findings (top severities, with file:line evidence):**
1. **[CRITICAL] CPW sparse+low-rank decomposition has no stable λ2 operating point.** Files: `ldo/lowrank.py:59,93`; `workflows/investigate.py:151`. Evidence: at default λ2=0.1, S comes back purely diagonal, direct_edges empty, a true direct edge misclassified as latent_shared; at λ2≥0.2 L collapses to rank 0. "NO single λ2 recovers both structures." Fix: identifiability-curve (stability-path/CV) selection of (λ1,λ2), not a fixed scalar; gate with a synthetic sparse+low-rank recovery acceptance test.
2. **[HIGH] `pegasus.causal` (LiNGAM+collider) built and test-covered but never wired** into investigate — "a completed milestone that is inert at runtime." Zero runtime importers.
3. **[HIGH] LDO residual scan feeds a misaligned/undersized precision block** — `orchestrator.py:151` slices `S[:p,:p]` assuming the first p kept features are the p base variables in order; when low-coverage lag-0 variables are dropped this misattributes edges, and when q<p it crashes into a swallowed try/except that silently disables the scan. "Runs by default in every real investigate... exercised by zero tests."
4. **[HIGH] Spatial GMRF prior κI+L_W absent from the live estimator** — whitening code (`precision.py`) has zero runtime callers; `kappa` threaded through but never referenced in the body.
5. **[HIGH] Residual HSIC scan uses iid permutation null on spatiotemporally autocorrelated residuals** — anticonservative; the structured-null registry (`nulls.py`) exists and is bypassed.
6. **[HIGH] Kronecker/spatial separability (§V.2) absent from the live LDO path** — dense eigh on (p(K+1))²; `grep kron` zero hits.
7–20: dead maternal-child/SINASC output cluster; disease/variable_grammar bypassed by investigate's own generator; off-dispatch workflow entrypoints; lag-0 dual-emit (contemporaneous AND latent_shared for same pair); unconverged ADMM emitting certified edges; §V.3 randomized NLA entirely unimplemented; stale Pylance "zombie tree" claims; `pegasus.pirs` test-pinned dead code; various low-severity dead-code/type-noise items.

**Remediation roadmap synthesis (5 workstreams):** A — LDO core math integrity (CRITICAL, keystone: fix λ2, then whitening/null/precision-alignment/edge-dedup/convergence-gate — cheap once the split is trustworthy). B — §V Computation & Scale (Kronecker/randNLA/GPU-solver disconnection — "largely aspirational-over-orphaned"). C — plan-vs-code truth reconciliation (wire CAUSAL-01 or mark deferred; reconcile disease-grammar duplication). D — dead-code de-engorgement (~2,970 LOC, but several "orphans" are governed KEEPs — nuanced, not bulk-deletable). E — lint debt (trivial, do last).

**Bottom line stated by the doc:** "Part V is... perhaps 30-40% wired." Top priority: "Fix the S/L split and wire the spatial whitening first."
*(Note: this audit's findings are chronologically prior to and largely superseded by the LDO_COMPLETENESS_AUDIT's WP1–WP8/O1–O19 build wave, which the Issue Ledger confirms closed the LDO layer.)*

═══════════════════════════════════════════════════════════════
## 4. PEGASUS_ISSUE_LEDGER.md (238 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "Master Issue Ledger" — cross-cutting status tracker for every issue/feature/objective across all non-LDO modules and dev cycles (LDO detail lives in doc #1). Built 2026-07-08 by six read-only inventory agents, cross-checked against live code.

**Headline finding:** "the codebase is well ahead of its own docs" — most doc-listed findings from the Compliance/Architecture audits (docs #2/#3) turned out already DONE or DEFENSIBLE on live-code re-verification; "Trust the Status column here, not the source docs."

**Status legend:** OPEN / OPEN? (unverified lead) / WIP / DONE `<commit>` / VERIFIED-DONE (audited, already satisfied) / LIKELY-DONE (not re-verified this cycle) / DEFERRED `<why>` / SUPERSEDED `<by>` / DEFENSIBLE (flagged but correct-as-is).

**Burn-down conclusion (2026-07-08):** "The EFG-LDO architectural-integrity gate — the user's stated prerequisite before any study — is MET." Verified already-satisfied without new builds: MATH-12, MATH-05/06, KS-01, SIDRA-CTX-01/02, STORE-02, STOR-03/05/06, ARCH-REG-02, SCOPE-01, PANEL-01, EFG-DECL-02, the whole LDO layer.

**★ Genuinely-open priority set at time of writing:** Output Query Layer (FEAT-P3+P4) mostly DONE, only P3e CLI remainder; SIDRA-CTX-01 DEFENSIBLE/DONE; disease variable-grammar + Zika acceptance DEFERRED (grammar intentionally unwired — σ_C restriction is canonical); population-build memory perf VERIFIED-DONE; RaceBridge region-conditioning DEFERRED (data-blocked — needs empirical region-specific confusion matrix not in-repo, not fabricatable).

**Notable resolved GPU claim:** "GPU-01..08, LDO-NUM-01, LDO-DESIGN-01/02 — MEASURED → NOT WORTH IT (2026-07-09)." Profiled the ADMM eigh port: single CUDA f64 eigh is 6.9x faster than numpy, but eigh is only ~60% of a fit (pairwise_correlation + whitening dominate), the dominant cost (`stability_select`, 20 refits) already parallelizes ~4.5x across CPU cores (a single GPU can't beat that for independent refits), and batching is *counterproductive* at the relevant matrix size — net realistic gain ~1.7-2x with regression risk, refuting the survey's claimed 5-15x. Flags task-list item "#54 W8 GPU done" as a **false-completion** (no `torch_admm.py` exists; live code is numpy `eigh`).

**RaceBridge status (§Measurement/race):** redesign (per-source C, literature prior, never identity, uncertainty) LIKELY-DONE except region-conditioning, DEFERRED (data-blocked).

**Disease axis (§Disease semantic axis):** DIS-04 (L_D prior) DONE `f774e28`; DIS-06 (variable-grammar wiring) DEFERRED-by-design (its own docstring warns against being a second live generator); DIS-07 (label embeddings) DEFERRED-inconclusive per user direction; ZIKA-ACCPT DEFERRED (Q02↔A92 DiseaseGraph edge weight is 0.0 — weak/absent coupling, discoverability uncertain).

**Storage/compute:** STOR-01/02/07 DONE (raw.rds decoupled, manifest reference-only); STORE-02 lazy `scan_parquet` VERIFIED-DONE; GPU items above; DISCO-01 (continuous-discovery scheduler) OPEN, future feature.

**Modularity/architecture:** several god-modules OPEN (`compile.py` 1036 LOC, `executor/kernels.py` 838 LOC); T1.2 (DATASUS per-chunk fail-closed completeness gate) DONE `56f0bdc`; EFG-QT (canonical Q-state wiring) DONE `11fce28`, which also surfaced and fixed a live crash (`EFG-QT-residual` `cfda05d` — a non-enum `"warning"` state literal was an active `FieldState` ValueError crash on `sim_informed_denominator` mode, hidden because tests only exercised `official_sidra_anchor`).

═══════════════════════════════════════════════════════════════
## 5. PEGASUS_STORAGE_OPTIMIZATION_PLAN.md (188 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** Storage/data-lifecycle design + remediation. Header notes "✅ IMPLEMENTED (2026-07-05)" for Tiers 1–2; original analysis below is dated by trigger event: `data/` reached 53 GB on a single national all-source acquisition. Bottom line stated: ~70–80% of `data/` is redundant/reclaimable; target end state ~8–12 GB.

**Measured state (2026-07-05):** `raw/datasus/` 26 GB, `processed/datasus/` 14 GB, `sidra/` 2.3 GB, `cache/sidra/` 2.1 GB, `actual_state_panels/` 1.7 GB (stale dev outputs), `normalized/` 1.4 GB, `runs/` 0.7 GB (incl. a 450 MB manifest bug), `diagnostics/` 0.44 GB. Per-system DATASUS: SIH-RD 32 GB (dominant, and least relevant to the pancreatic-cancer/mortality win-condition since that comes from SIM), SINASC 5 GB, SIM-DO 4 GB, CNES ~0.

**Root inefficiency — per-chunk triple storage:** one SIH chunk stores the same ~250K rows three times: `raw.rds` (R-native, 6.15 MB, **never read back** — `readRDS` appears nowhere in the codebase), `microdatasus_processed.parquet` (6.43 MB, legacy semantic labels, superseded by the in-house codebook), `processed.parquet` (6.37 MB, raw-coded — the ONLY artifact the normalizer reads). The source `.dbc` is already deleted post-parse, so the 26 GB "raw" tier is two *re-serializations* of data that already exists as `processed.parquet`.

**Root inefficiencies enumerated (I1–I8):** I1 `raw.rds` written, never read (~13 GB reclaimable) · I2 `microdatasus_processed.parquet` legacy, unconsumed (~13 GB) · I3 SNAPPY codec instead of ZSTD on the kept artifact (~4–5 GB of 14, codec-only, columns retained) · I4 downstream re-materialization at each pipeline stage · I5 44K ancillary debug files (heartbeat/stdout/stderr, ~180MB NTFS slack + inode cost) · I6 SIDRA response-cache duplicates facts (~2 GB) · I7 stale dev outputs (~2 GB) · I8 `ReproducibilityManifest` inlines raw float tensors instead of referencing parquet (450 MB/run bug, ~11 GB at full-window scale).

**Target architecture (stated principle):** "one compact, portable, content-addressed copy per (system, UF, year[, month]); everything else is a view or a hash." Raw is ephemeral (keep only `raw_sha256`, not bytes); one consumed artifact per chunk at **full raw fidelity — all DBF columns retained, only codec changes** (columns are explicitly never pruned, since a future concept binding must not force a re-fetch); downstream layers become lazy `scan_parquet` Hive-partitioned views, materialized only when genuinely needed; ancillary logs retained only on failure; run bundles reference tensors by path/hash, never inline; SIDRA cache treated as an accelerator, droppable once facts materialize.

**Work items, tiered by ROI/risk:**
- Tier 1 (−28 GB, low risk): W1 GC redundant raw layer + decouple cache-hit check off `raw_path` onto `processed.parquet`+`manifest.json`; W2 prune debug ancillaries on success; W3 GC stale dev outputs; W4 fix run-bundle inline-tensor bloat.
- Tier 2 (−8 GB, prevents regrowth): W5 stop writing `raw.rds` at the R source; W6 SNAPPY→ZSTD+dictionary on `processed.parquet` (lossless, 14→~9-10 GB); W6b retire `microdatasus_processed.parquet` at the source (~−13 GB).
- Tier 3 (architecture, bounded scaling): W7 Hive-partitioned canonical lake (lazy scan, no re-materialization); W8 SIDRA cache dedup/expiry.

**Estimated end state table:** Total 53 GB → 23 GB (Tier 1) → 13 GB (Tier 2) → 10 GB (Tier 3). Framed as "the per-(system,UF,year) footprint drops ~3×, so a full 2000–2024 national acquisition lands in the low tens of GB instead of 100+ GB."

**§7 — DATASUS translation architecture (why the cuts are safe):** two coexisting paths — Path A (microdatasus, being retired: downloads raw DBF, then a *lossy* semantic `process_*()` step to `microdatasus_processed.parquet` that nothing in the Python pipeline consumes except a dev audit `schema_compare.py`) vs Path B (in-house codebook, the strategic/production authority: normalizers read the raw-coded `processed.parquet` directly and apply the codebook vectorially with explicit MSD §2.3 missingness states, never microdatasus's silent NA collapse). Consequence: "the raw→canonical injection is already lossless w.r.t. variables" — translation is already in-house; only the *fetch transport* still depends on microdatasus/R.

**§8 — SIDRA lifecycle (S1–S4 inefficiencies):** raw JSON payload stored twice (client cache + extract raw dump, ~2 GB); dumps pretty-printed (20-30% larger than compact JSON, and JSON itself is 3-5× a parquet of the same facts); facts materialized in 3 re-copied layers; per-UF workdir explosion (27 workdirs × ~94 tables) at national scale creating thousands of tiny files.

**Header note confirms actual implementation:** Tiers 1-2 shipped (commits `83914ac` DATASUS v4 bridge, `6245664` SIDRA slim dumps, `61746bb` manifest fix) — `data/` measured 53 GB → 26 GB, "no column or row of source data was dropped," national compile + pop-tensor re-validated post-migration. Tier-3 (W7 Hive views) explicitly left optional/remaining.

═══════════════════════════════════════════════════════════════
## 6. PEGASUS_MODULES_REMEDIATION.md (40 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "PegaSUS Modules Remediation Roadmap (non-LDO)" — generated 2026-07-07 by a 25-agent discovery workflow, 93 raw findings collapsed via 14 adversarial verifiers. Explicitly scoped: "Ranked by leverage toward the win condition: the full-range 2000–2024 national all-source compile+investigate running end-to-end on a 34 GB-RAM / 6 GB-VRAM box, correctly." LDO/EFG-math work is out of scope here (done elsewhere).

**Verification outcomes — findings that were REJECTED as over-stated:** "DATASUS fetch has no retry" (false — the R script retries 4× with `Sys.sleep(min(2·attempt,8))` backoff); "eager combine fallback OOM" (the empty-group path is unreachable); "on-success GC orphaned" (the debug-file pruning `_prune_success_ancillary` already runs inline on success/cached, though the separate `storage_gc.py` module functions are indeed orphaned).

**CONFIRMED findings:** datasus_combined re-materialization; the throwaway intermediate never deleted; M2 float32 solver never built; `tensor_values` full-array retention; SIDRA warm-cache absent; SIDRA sprawl (S3/S4); SIDRA UF fan-out hardcoded to 6; `DatasusConfig` diverging across 3 layers; microdatasus-retirement incomplete; transient-chunk completeness-gate gap.

**Tier-1 blockers/correctness table (11 items T1.1–T1.11):** T1.1 window-blind national cache (BLOCKER — a 2000-2024 request silently reuses a stale 2000-2020 cached national file); T1.2 no fail-closed completeness gate over per-chunk failed/timeout chunks (MAJOR, lower risk given confirmed retry); T1.3 national race-prior hardcoded `None` at `pipeline.py:475` (MAJOR); T1.4 EFG stage workspace never cleaned, duplicating the full national tensor payload per run (BLOCKER); T1.6 `datasus_combined` re-materialization because `combined_hash` folds in `fetched_at`, creating a new 26→50 GB copy per identical re-run (BLOCKER, CONFIRMED); T1.8 M2 float32 denominator solve never built despite config declaring it (MAJOR); T1.9 `_candidate_pairs` O(N²) national migration blowup (5570² per year before guard no-ops) (MAJOR); T1.10 `tensor_values`/`migration_values` full arrays retained on the result dataclass just to call `len()` (MAJOR, CONFIRMED as aliased not copied); T1.11 `DatasusConfig` default divergence across 3 layers (8/4/16 workers, 300/900s heartbeat) (MAJOR, CONFIRMED).

**Tier 2/3:** W7 lazy Hive views (subsumes T1.6 + SIDRA sprawl); SIDRA warm-cache/TTL/zstd; Q-tensor state re-classification; GPU wiring gaps (STDFM `prefer_cuda` hardcoded False); dead `normalize/records.py` (~439 LOC, 0 callers); two divergent DATASUS entrypoints; assorted drift/dead-code cleanup items.

**Progress log — landed this wave:** T1.1 window-safe national cache (`64b20d6`); T1.4 EFG stage-workspace deletion (`e999d3a`); T1.9 O(N²)→O(N·k) migration candidate pairs + T1.11 config unification (`80456ce`); M2 partial — population-problem inputs stored float32 (`ac17ac0`, ~8 GB national RAM reclaimed, lossless since solver still runs f64). **Remaining, in stated order:** T1.6 content-addressing → T1.3 race-prior wiring → T1.2 completeness gate → T1.10 result-array retention → Tier-2 W7 + GPU wiring → Tier-3 dead-code cluster.

═══════════════════════════════════════════════════════════════
## 7. PEGASUS_REPO_HEALTH_ASSESSMENT.md (142 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "PegaSUS Repo-Health Assessment (2026-07-08)" — five parallel read-only audits (registries, dead/orphaned code, wiring/integration, performance, architectural coherence), cross-reconciled, plus a second-wave four-deep-dive redesign synthesis (2026-07-09).

**Verdict:** "Healthy and coherent; the remaining work is bounded and known." Architecture cleanly mirrors MSD-III (correct layering SHE→EFG→LDO, no cycles; one centralized output contract; one measured-quantity type). Dead code ~2% and mostly marked forward-scaffolds. Core acquire→normalize→SHE→EFG→denominators→LDO→output path wired end-to-end. Performance: "good baseline with no algorithmic bloat." **"No blocker to a reduced-statewide live test."**

**Per-dimension summary:** Architecture SOUND (one benign layering note: `geo/migration_affinity`→`denominators` public-type dependency; god-modules are real debt). Dead code MINIMAL ~2% — only one genuinely-dead unmarked module (`efg/empirical_compression.py`, 187 LOC); six inert modules are marked PANEL-01/SCALE-01 scaffolds (intentional, keep); **but** the whole `pirs/` package (354 LOC) is orphaned (missed by the per-module dead-code scan, caught by the wiring audit). Wiring 90% solid — gaps are untyped `dict[str,Any]` handoffs (`domain_summaries` EFG→compile; `Q_tensor` rows executor→investigate with a silent 0.0 fallback) and one truthfulness flag. Registries FRAGMENTED in the health domain specifically (the user's stated concern, confirmed). Performance GOOD baseline, no GPU-gating issue, two byte-safe structural wins remain.

**Tiered remediation:** Tier 1 (pre-live-test integrity, small): `maternal_child_linkage` hardcoded `True` in RunConfig regardless of actual run scope (truthfulness fix); delete `efg/empirical_compression.py` (DONE, 520 tests still collect); `pirs/` package deletion DEFERRED (2 test files still import it, one being a contract guardrail — migrate tests first). Tier 2 (health-registry typing/de-orphaning, "the user's ask"): `icd_curated_groups.yaml` orphaned vs hardcoded chapters/blocks; `cnes_capacity`/`sih_cost` registries shadowed by hardcoded enums (two sources of truth); `icd_catalog.yaml`/`icd_quality_groups.yaml` are "Macro-Slice 27A" stubs only validator-referenced; type `diagnostic_topology`+`clinical_event_definitions`; sweep other registry domains. Tier 3 (typed contracts): `Q_tensor` silent-0.0-fallback risk; `domain_summaries` typed contract. Tier 4 (byte-safe perf): vectorize `covariance.py` nested lag-loop (~15-25% LDO speedup); batch-align fields in `panel.py` (~10-20%). Tier 5 (gated refactors): decompose god-modules (`compile.py` 1036, `efg/dag.py` 1026, `efg/executor.py` 1251, `kernels.py` 838 LOC); REG-07 registry consolidation (deliberately deferred — "decode-validation is a silent-corruption risk if rushed").

**Deep-dive redesign synthesis (2026-07-09), four workstreams:**
- **A. RaceBridge (centerpiece):** wiring fear unfounded — both the embedded population-solver path and the autonomous EFG `Bridge_R` field are live. **Core gap: the confusion matrix C is an identity/synthetic placeholder** — the Bayes crosswalk math (W∝C·π_local) + bootstrap are structurally correct but with identity C they quantify only sampling variability, not real admin↔self-declared reclassification bias. Also: national-only C (region_scope infra exists, unpopulated); heuristic local-π instead of principled shrinkage; **the bridge's own computed uncertainty (CV/credible bounds) is dropped, never propagated into rates/LDO.** Proposed workstreams W-RACE-1 (code-only: propagate uncertainty, complete region-conditioning path, census-anchored shrinkage prior) → W-RACE-2 (acquire a real region-conditioned C_s from published misclassification studies/PNS-PNAD linkage) → W-RACE-3 (eventual full hierarchical latent-class Bayesian model).
- **B. Data plane:** solid, not a rewrite target — micro-optimize (parallel normalize beyond the hardcoded 2-way cap, +25-40% wall-clock; byte-safe quick wins). Out-of-core (DuckDB) deferred to full 2000-2024 scale only.
- **C. Registries:** ~70% of the way to "add data = registry edit." Correction noted in the doc itself: "there is NO `declarative_normalize.py`— the declarative engine is `records.py::normalize_record`+`callables.py::resolve_callable`" (a factual correction to an earlier claim elsewhere in the corpus). Blocker to full registry-only extension: vectorized batch transforms/categorical codebooks/SIDRA extraction policies are still per-system code. W-REG-1 (10-15 days) proposes a declarative `vectorized_transform` op-spec. Feasibility ceiling stated: "~90% registry-only achievable (~6 wk); 100% impossible (computations are code)."
- **D. Per-module:** structured logging for silent exception fallbacks; mtime cache-invalidation for ICD/concept lru_caches; spatial-graph Laplacian view caching; a silent denominator fallback in the query engine explicitly **rejected** as contradicting the no-silent-degrade principle.

**Live-test go/no-go: "GO for reduced-statewide."** Recommended staging: `core_vital` scope, `validate` stage first, then `investigate`(LDO) stage. Pre-flight: land Tier-1 truthfulness fix + safe deletions, and ideally the Q-tensor contract fix "so a live run's provenance is honest and its reliability weights aren't silently defaulted."

═══════════════════════════════════════════════════════════════
## 8. docs/architecture/LDO_RESIDUAL_ARTIFACT_HANDOFF.md (130 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** A handoff note from "Claude (Opus 4.8)" to "GPT-5.6 (Sol)," dated 2026-07-11, re: an LDO residual-scan near-clique artifact discovered on the national pancreatic-cancer (ICD C25) study run. **This is a live-annotated document — it contains two RESOLVED headers added later (2026-07-12) that record what actually happened after the handoff, so it doubles as both the open question and its answer.**

**Context:** the LDO's final stage is a residual HSIC scan for nonlinear edges, on top of the sparse+low-rank Ω=S−L linear backbone. Task: get the national LDO stage to complete, then assess trustworthiness of output.

**Engineering fixes that made it run (settled, committed, not in question):** `f26f525` residual-scan was memory-bandwidth-bound (O(P·n²) random-access kernel-permutation copy) → fixed via low-rank kernel factoring + batched matmul, bit-exact, 16-30× faster; `953dd99` output-writer crash (polars inferred a float column as Null from the first 100 all-None rows) → fixed with an explicit schema; `a078106` pair cap raised from 15k to 150k for full national coverage. Result: national LDO completes in ~26 min, peak RSS 18.5 GB.

**The real problem — output is largely an artifact.** Of 7,483 total edges, 7,197 are `nonlinear_residual`, forming a near-clique among 132 of 348 variables at median degree ≈118/131 (≈83% of all pairs). Effect sizes tiny (HSIC median 0.006-0.009, 90% below 0.05) yet pass BY-FDR — i.e., statistically real (systematic) but negligibly small. 113/132 clique nodes are same-source DATASUS disease-count variables. The `mechanical_overlap` guard emitted **0 edges** (inert — keys only on ICD-code overlap, not shared source event-volume).

**The author's own diagnostic mistake (explicitly flagged for scrutiny, a case study in the "correct-but-wrong-layer" failure mode named in CLAUDE.md):** initially diagnosed a "low-rank global-factor leak" — the residual scan was fed sparse `S` instead of full `Ω=S−L`. Built a synthetic, confirmed the mechanism in isolation (block residual correlation 0.72→0.04 after fix), shipped the fix (`bcdd0dd`), re-ran national — **the clique barely moved (7,197→7,290 edges).** Explicit lesson stated: "a synthetic that reproduces the symptom can validate the wrong mechanism; the real quantity to measure is the national residual, not a proxy." The Ω fix was kept as a legitimate correctness fix but does not explain the artifact.

**Refined candidate mechanisms handed off (unresolved at handoff time):** (A) no effect-size floor — significance (q≤0.1) alone gates promotion, so an arbitrarily tiny HSIC "passes" at large effective-n; (B) ecological averaging at national grain — a 0.40·RAM memory guard forces spatial-block×year group-averaged residuals, and aggregation inflates cross-variable dependence (MAUP); (C) the executed null does not preserve residual temporal autocorrelation — code documents it should use `spatial_block_cyclic_time_shift` but actually runs a free within-block year-shuffle, anti-conservative for any pair sharing a temporal trend; (D) which dependence is tested is chosen non-reproducibly by the 40%-RAM memory guard (different grain on different machines).

**RESOLUTION (2026-07-12, commit `deddf68`, added as a header note):** GPT-5.6/Codex determined the artifact was **spatial nuisance** — the residual conditions on Ω across variables but not on the panel's municipality/time structure, so co-located pairs beat the null. Confirmed per-mechanism on a controlled synthetic (confounder-pair p: 0.001→0.76 under the fix). Fixes: two-way FE nuisance projection, spatial-block cross-fit of Ω, refuse-don't-average, normalized-HSIC effect size, corrected low-rank memory model — committed. **One validated caveat:** the municipality FE also erases genuine cross-sectional determinants (p 0.001→0.87 for a real cross-sectional signal), so the residual scan now tests a *within-municipality temporal* estimand only; cross-sectional signal must come from the linear backbone. A cross-sectional-preserving alternative was proposed but **not adopted** (risk-averse choice, explicitly stated).

**FULL RESOLUTION (2026-07-12, second header):** Four further fixes closed the artifact completely: `1369193` normalized-HSIC (CKA) effect-size floor (default 0.05); `5fbb582` fixed a degenerate complete-case sampling bug (the scan maximized variable count, collapsing n via singleton fixed-effect groups until CKA saturated to 1.0 for every pair — "the true source of the flat clique" — replaced with a coverage-ordered cliff rule + degeneracy guard); `56d106b` mechanical-overlap typing for shared-numerator pairs (a count and its own derived rate); `7b1a943` excluded population denominator/exposure seeds from the analytical outcome set (they were driving co-scaling CKA≈1.0). **Validated result on real data:** production clique 1711→825→78-139 real edges; a 43-variable cross-domain slice → 62 edges/22 certified, described as "all textbook epidemiology" (infant-mortality cluster, birth-outcome web, socioeconomic↔fatality), 31 LiNGAM-oriented, 7 mechanical correctly demoted.

**Outstanding caveat flagged at the end:** the national deliverable file (`data/runs/national_c25_full_ad2/Hypotheses.parquet`, built 07-11 12:14) **predates every fix** — its 9,180 nonlinear_residual edges (all "selected," 0 FDR-significant) are the pre-fix clique. Refreshing it requires a targeted LDO rerun on the existing panel, "intentionally not launched autonomously (lengthy full-scale runs are deprioritized)."

═══════════════════════════════════════════════════════════════
## 9. docs/ICD_LIBRARY_REVIEW.md (197 lines)
═══════════════════════════════════════════════════════════════
**Purpose/date:** "ICD-Code Technical Backbone Review — Disease Semantic Axis." Reviews the two ICD libraries under `src/pegasus/disease/` (`icd_adapter.py`, `concept_registry.py`, `graph.py`): `simple-icd-10` (hierarchy backbone) and `icd-mappings` (grouper backbone). Explicitly empirically verified against the installed `pegasus` conda env versions, not just docs.

**`simple-icd-10` (installed v2.1.1):** ships **WHO ICD-10, 2019 edition** (12,542 nodes, offline XML, deterministic). Full hierarchy toolkit (ancestors/descendants/parent/children/leaf/nearest-common-ancestor/is_chapter etc.) — "no API gap." Limitations: WHO edition, not ICD-10-CM and not Brazilian CID-10; no Portuguese descriptions; pinned to 2019, no multi-release support.

**`icd-mappings` (installed v0.6.2):** grouper mappers `icd9`, `block`, `chapter`, `ccsr`, `ccir`, `ccc_category`, `ccc_subcategory`. **Discrepancy found:** the code (`concept_registry._GROUPERS`) references a `"cci"` target in one probe path, but the installed library exposes `ccir` (Chronic Condition Indicator *Refined*), not `cci` — a bare `cci` target would raise. The live registry config actually uses `ccir` correctly; only stray comments/probe-path references to `cci` are wrong and should be scrubbed. Its internal code table is broader than WHO-2019 and includes the dengue codes — the identified lever for remediation.

**THE GAP (§3, central finding):** Brazilian CID-10 (DATASUS V2008) arbovirus block is A90-A99, starting at **A90 (Dengue clássico) and A91 (Dengue hemorrágico)**. WHO-2019's block node is literally `A92-A99` — **A90 and A91 do not exist as nodes at all** in the shipped library (dengue was folded into A97 in the WHO edition). Empirically verified table: A90/A91 → `is_valid_item`=False in simple-icd-10 but resolve correctly to block `A90-A99` via icd-mappings; similarly U06 (a Zika emergency-use code in some vintages) is absent from WHO-2019's U-block but resolves via icd-mappings to `U00-U49`. By contrast A92.0 (Chikungunya), A92.5/A92.8 (Zika), A95 (yellow fever), Q02 (microcephaly) are all present and correct in WHO-2019. "This is not a broad catalogue failure — it is a handful of load-bearing codes."

**How the axis handles it today (already partly designed-for):** the adapter does NOT silently break — `code_info` types A90/A91/U06 as `status=source_system_specific`, correctly resolves the *chapter* via a hand-maintained `_CID10_CHAPTERS` range table, and never coerces to a WHO subcode (the §II.13.2 guard). Downstream `projection_status` is degraded rather than silently dropped.

**What is nonetheless lost:** because A90/A91/U06 are absent from the WHO tree, `get_ancestors`→(), `get_descendants`→(), `is_leaf`→False, and `code_info.block` is `None`. This degrades two things: (1) `DiseaseGraph._structural_weight` — dengue↔dengue/other-arbovirus edges lose the correct 0.5 "same block" tier (falling back to 0.25 chapter-only weight for dengue↔chikungunya), so **"the L_D prior over the arbovirus cluster is weaker than it should be for exactly the diseases Brazil cares most about"**; (2) nearest-common-ancestor/distance calculations return `None` for dengue nodes, so hierarchy distance is unavailable.

**Alternatives assessed and rejected:** `simple-icd-10-cm` (US ICD-10-CM tree) would fix A90/A91 but "silently change every ancestor/leaf/NCA result to the US clinical tree — a far larger behavioral blast radius than the hole it fixes." `rmnldwg/icd` multi-release has a different API surface, no pt-BR. WHO ICD API is authoritative but requires network+OAuth, violating the offline/deterministic design. "None of the offline libraries ships Brazilian CID-10 with Portuguese descriptions" — the only pt-BR authority is DATASUS itself or the networked WHO API, so CID-10 authority already correctly lives in the repo's own `_CID10_CHAPTERS` table.

**Recommendation (§5): do not switch the backbone.** Keep `simple-icd-10` and layer a narrow deterministic fallback sourced from the already-installed `icd-mappings` dependency. Concrete steps in priority order: (1) fill `block` for WHO-absent codes via `icd-mappings` in `icd_adapter.code_info` when `status==source_system_specific` — "the single highest-value fix, and it adds no dependency"; (2) add an explicit `who_absent_cid10` YAML table enumerating known gaps (A90, A91, U06 + any surfaced by a catalogue diff) with CID-10 block + pt-BR label, making the gap declared and testable; (3) optional synthesized block-level pseudo-ancestor for NCA/distance repair (low priority); (4) add a guard test diffing the WHO-2019 catalogue against DATASUS's actual category set, pinning A90/A91/A92.0/A92.5/A92.8/A95/U06/Q02 as the named acceptance set; (5) scrub stray `cci`→`ccir` references.

═══════════════════════════════════════════════════════════════
## 10. DOCS.md (69 lines)
═══════════════════════════════════════════════════════════════
**Purpose:** "PegaSUS Documentation Index & Lineage" — the single source of truth for which doc governs what, since the planning docs are described as "strata" deposited over time.

**Precedence rules when docs disagree:** (1) file/module disposition → `PEGASUS_REFACTOR_MASTER_PLAN.md` wins (only plan verified against the live tree); (2) registry/REG-07 direction → `PEGASUS_MSD_III.md` §II.1 wins over the Operational Implementation Plan's REG-07 framing (called "wrong" — REG-07 is a decode-validated contract merge, not mechanical); (3) run-legality/mandatory-chain semantics → MSD-III §VII.2 supersedes MSD-I §9's absolute "closed mandatory chain" language; (4) otherwise the newest doc governs, older strata are reference-only.

**Governing specs (current):** `PEGASUS_MSD_III.md` (the architecture spec of record — §II.1 registry, §III LDO, §V compute/scale, §VII run legality, §XI phases/acceptance); `PEGASUS_OPERATIONAL_IMPLEMENTATION_PLAN.md` (the TDD/build plan, subordinate to MSD-III and the master plan; "its file-count/DEL claims are unreliable"); `PEGASUS_REFACTOR_MASTER_PLAN.md` (refactor plan of record, source-verified, carries `[PLAN-CONFLICT]` reconciliations).

**Foundational/code-referenced (kept, cited by code):** `PEGASUS_MSD_I.md` (7015 lines, foundational data-plane spec, §9 superseded by MSD-III §VII.2); `PEGASUS_MSD_II.md` (cited in ≥5 code modules as registry authority / SpatialWeightGraph source); `PEGASUS_DISEASE_SEMANTIC_AXIS.md` (the disease-axis spec, §II.13, current); `PEGASUS_ARCHITECTURE_ADDENDUM.md` (superseded by MSD-III but kept only because MSD-II cross-references its "four pillars" — treat as historical).

**Reference material (not plans):** `PEGASUS_COMPLIANCE_AND_REMEDIATION.md` — explicitly labeled "**Not a plan of record**," a finding-ID dictionary retained by MSD-III §0.1 reference; `PEGASUS_COMPLETION_ROADMAP.md` — "**the settled completion roadmap (2026-07-09)**...the forward plan of record" (full-scale-default reframe, RaceBridge ecological redesign, data-layer first-class, storage contract, phased plan); `PEGASUS_REPO_HEALTH_ASSESSMENT.md`; `PEGASUS_OUTPUT_QUERY_LAYER.md`; `docs/ICD_LIBRARY_REVIEW.md`; data-source field references (`DATASUS_DESC.md` etc.); `README.md`.

**Active subordinate plans that "close into MSD-III when their work lands":** `PEGASUS_COMPUTE_BUILD_OPTIMIZATION_PLAN.md`→§V (POP-02 GPU/blocked build); `PEGASUS_STORAGE_OPTIMIZATION_PLAN.md`→§V (STORE-02 lazy views); `PEGASUS_OUTPUT_QUERY_LAYER.md`→§VIII (FEAT-P3/P4).

**Deleted (git history preserves, do NOT resurrect as guidance):** 13 five-line Jun-6 doc stubs describing a "dead slice-bundle architecture" mentioning old PIRS/EFG; `docs/production_boundaries.md` + `pegasus_codebase_contract.yaml` (old boundary-audit tooling, "now exterminated"); `TDD_old.md` (3264 lines, superseded); ephemeral `HANDOFF.md`; `_review/*` Jun-25/26 remediation snapshots absorbed into MSD-III. **Also removed:** `scripts/dev/**` (~57.5k LOC of "chatbot-era one-shot updater codemods" that mutate/lint a *past* state of src — explicitly noted "re-running corrupts current code"); only 6 real tools remain at `scripts/` root. Explicit rule stated: **"No functional source belongs under `scripts/` — ever."**

═══════════════════════════════════════════════════════════════
## 11. CLAUDE.md — "Working principles — data-intensive, mathematically-heavy projects" (245 lines)
═══════════════════════════════════════════════════════════════
**Note:** this file, read from `C:\Users\Galaxy\LEVI\PegaSUS\CLAUDE.md`, is a *general operating-discipline document*, not PegaSUS-specific narrative — it is written as domain-agnostic principles with PegaSUS-illustrative parentheticals. Governing idea stated up front: **"claims — in specs, docs, prior code, or your own reasoning — are hypotheses until measured. Earn every conclusion."** Numbered by roman-numeral section (not by a single flat numbering); reproduced below with each section's principles listed.

**I. Specifications and documentation are fallible hypotheses.**
1. Empirically validate prescriptions before implementing them, especially math/performance — build the smallest probe measuring the actual claimed quantity.
2. A correct prescription can fail three distinct ways, each needing a different fix: (a) naive implementation (right idea, wrong constants — slower/unstable); (b) correct-but-marginal in the actual operating regime; (c) correct-but-wrong-layer (real effect, but belongs to a different model component than the one touched). *[This is the exact taxonomy the LDO handoff document (#8) explicitly invokes for its own λ2/spatial-whitening misdiagnosis.]*
3. Respect source provenance but hold even the top authority as fallible — prefer newest/most-rigorously-reviewed among conflicting sources, then still test it.

**II. Validate mathematics by measurement and inspection — not by test suites.**
4. A green test suite does not establish mathematical correctness (synthetic tests can pass on wrong math — inverted sign, wrong DOF, a leak).
5. Prefer throwaway probes over committed test batteries for validating math; keep one focused proof-of-capability test per feature, not a battery.
6. Isolate one numeric change at a time; when a change breaks a recovery check, diagnose why before reverting — the break is information.

**III. Diagnose the mathematical structure before engineering a fix.**
7. Locate where a phenomenon lives in the model (sparse vs low-rank vs whitening vs factor/covariate), then fix it there — "no amount of elaboration on the wrong component will move it." Establish structure (rank/range/locality/stationarity) empirically first.
8. Match effort to empirically-established value; stop polishing a marginal candidate.
9. Distinguish "the safe default is adequate" (provable, keep it) from "the default is a lazy shortcut" — document evidence either way.

**IV. Statistical honesty under dependence.**
10. Deflate effective sample size (n_eff) for serial/spatial dependence, propagated into every SE/power gate/threshold, using the correct estimand-specific design-effect formula.
11. Use dependence-robust multiplicity control (FDR) when tests are correlated; a computed-but-unused q-value protects nothing — actually enforce it.
12. Cross-fit or gate in-sample scoring (double-dipping); at minimum flag/refuse certification when p/n is large enough for bias to bite.
13. Guard against leakage/circularity in engineered features — a quantity derived from X must never be a prior/weight/denominator for an estimate about X; enforce at point of use, not by convention.

**V. Parameters, defaults, and safety of changes.**
14. Auto-determine deep mathematical parameters from data/problem dimensions rather than static constants, unless the knob serves a genuine functional purpose (compute budget/depth) — and validate the auto-determination's own robustness.
15. Prefer monotone-safe changes (can only tighten/widen, never fabricate signal); invasive changes that move point estimates need explicit recovery validation before adoption.
16. Never silently cap/truncate/degrade — always emit the fact of a bound (top-N, no-retry, sampling, fallback).

**VI. Tools, data, and acquisition.**
17. Search for and use established, maintained libraries/datasets; don't hand-roll substitutes or declare a task blocked for lack of data without searching first. *[Directly realized in the ICD library review (#9): keep the maintained `simple-icd-10`+`icd-mappings` pair rather than hand-rolling a CID-10 table or switching backbones.]*
18. Acquired capability compounds even when the triggering hypothesis fails — evaluate on downstream optionality.

**VII. Process discipline.**
19. Enforce reliable kill switches on long-running work; know which timeout mechanism actually kills a process tree on your platform; run full validation once after a complete batch, not per intermediate build.
20. Guard diagnostic probes as strictly as production runs — bounded scope + resident-memory-ceiling watchdog (RSS/working-set, not commit-charge or instantaneous "available"); a two-tier ceiling (sustained-soft + instant-hard).
21. Actively watch long-running work — check early, then periodically; a monitor armed only on terminal signals can't distinguish running/hung/wrong-output.
22. Reconnoiter current code before building; verify doc/memory claims against live code — "docs and notes are point-in-time; code moves." *[Directly realized by the Issue Ledger (#4): "the codebase is well ahead of its own docs."]*
23. Commit in small, single-purpose units with evidence in the message.
24. Report faithfully, including negative/surprising results — never overstate or hide a refutation. *[Directly realized by the LDO handoff (#8): explicitly flagging its own wrong-layer misdiagnosis for independent scrutiny rather than shipping a second guess.]*

**VIII. Performance and scale are empirical.**
25. Profile the real workload before optimizing — attack the dominant cost (often surprising), not the assumed one.
26. Localize where a slowdown lives (per-iteration cost vs iteration count vs memory thrash vs wrong stage) before engineering a fix; validate a "faster" fix against the correct reference optimum, not just speed.
27. Validate at/near the real operating scale — behavior (convergence, conditioning, memory) inverts across scale; a miniature that "passes" proves little.
28. Distrust a resource-virtue label until measured (a "memory-bounded" solver can use more memory than the dense path it replaces). *[Directly realized in the Issue Ledger's GPU finding (#4): the "GPU-accelerated" claim was measured and found not worth it, and a "done" GPU milestone was found to be a false-completion.]*
29. Select among strategies via a fast head-to-head bake-off at two sizes (to see scaling), not by iterating one candidate against the full workload.
30. A sample must carry the property the bottleneck scales in (cardinality/skew/fan-out), not merely row count.
31. Before concluding a tool is slow, isolate which call shape is slow — the pathology is usually in how it was invoked, not the engine.

**IX. The code is usually ahead of its record — verify current state, including your own past claims.**
32. Treat every status claim as stale-by-default; establish current state before acting. *[This is the explicit stated basis for the Issue Ledger (#4)'s entire methodology.]*
33. A five-minute probe routinely overturns authoritative-sounding claims — run it before building.
34. Audit your own prior claims with the same skepticism applied to others' — re-verify and correct promptly without narrative-protection. *[Realized twice in this corpus: the LDO_COMPLETENESS_AUDIT's own "all closed" claim was later found overstated by re-verification (§ "CORRECTION" in doc #1); the LDO handoff's author explicitly flagged and retracted their own λ2/spatial-whitening diagnosis.]*
35. Existence in code ≠ use in the live path — orphaned-but-callable is not wired-live; confirm via actual call chain + runtime telemetry. *[This exact pattern — a built, tested, zero-caller module — recurs across docs #1, #3, #4 (LiNGAM orientation, Adaptive Precision Controller, spatial GMRF whitening, `pirs/` package, `variable_grammar.py`, all independently found "orphaned."]*
36. A stage never reached at real scale has an unverified "works" status; reaching it for the first time is itself a finding (expect new failures; check real-data preconditions).

**X. Escalate a recurring patch into the abstraction it implies.**
37. A localized fix sensed to recur is a symptom of a missing abstraction — name the class, not the instance; duplication (the same synonym list copied and drifting) is the tell.
38. Prefer wiring an existing semantic layer through to its consumers over re-encoding it ad hoc — let hardcoded parallel lists be deleted, not kept in sync.
39. Separate the canonical concept from its surface representation with one explicit queryable mapping, rather than conflating canonical-name and source-column-name in one field.

**XI. You have no clock — bound effort by design risk, not by time/length/context.**
40. The only real limits are design fragility (blast radius) and uncertainty (verifiability) — never token count, code length, or elapsed turns.
41. Cycle/phase boundaries are architectural milestones (a hypothesis resolved, a design secured), not chronological ones.
42. A milestone is a point to secure and reassess, not a license to stop — only a user-only decision, a hard external gate, or true completion justifies pausing.
43. Manage long-conversation context loss by externalizing state (commits, docs, memories) continuously, not by stopping early.

═══════════════════════════════════════════════════════════════
## CONSOLIDATED LIST (a) — every MSD requirement mentioned, with status
═══════════════════════════════════════════════════════════════
(Grouped by source document; "status" reflects that document's own final verdict, which is not always the same across documents when the same requirement recurs — the Issue Ledger's live-code-verified status should be trusted as most current per its own stated precedence rule.)

**From LDO_COMPLETENESS_AUDIT (all ultimately DONE per commit map, though the file's individual `_Status_` tags were left stale as "PENDING"):**
BLO-1 (temporal-smoothness L_time) DONE · BLO-2 (structured HSIC null) DONE · BLO-3 (residual audit must run at national scale) DONE · BLO-4 (exact-certifies-approximate) DONE · BLO-5 (§VIII.2(1) sensitivity screen) DONE · BLO-6 (§VIII.2(2) random deep audits) DONE · BLO-7 (§VIII.2(3) CoverageManifest) DONE · BLO-8 (Adaptive Precision Controller wiring) DONE · BLO-9 (EFG MeasuredQuantity, not a rate) DONE · BLO-10 (count+exposure margin) DONE · MAJ-1 through MAJ-25 all DONE (spatial BYM field, disease L_D, stability lattice, latent_shared stability, disease multiresolution, DiseaseGraph.laplacian() wiring, panel-support FDR, disjunctive descriptive gate, collider detection, Rung-2 escalation, numerical-error propagation ×2, multiresolution coarse→fine, exact-certifies-approximate ×2, exposure margin end-to-end, MR wiring into investigate, promotion conjunction, standing abort, spatial_field_ref population, Q-tensor canonical producer, MeasuredQuantity state tensor) · MIN-1/2/3/4/5/6/7 DONE · MIN-8 ruled architecturally N/A (OPEN by ruling) · MIN-9 partially DONE with a documented out-of-core ceiling remaining OPEN · MIN-10 DONE (source FIX text itself truncated in the document).

**From COMPLIANCE_AND_REMEDIATION (status as of that document, largely superseded/DONE per later Issue Ledger verification):**
SHE-DEC-01 COMPLIANT · SHE-DEC-02/03 (S2) OPEN at doc time · SHE-NORM-01 (S0, "central defect") OPEN at doc time, headline fix · SHE-CNES-01/02/03 (S0) OPEN at doc time · SHE-SINASC-01 (S0) OPEN at doc time · SHE-POP-01 COMPLIANT · SHE-POP-02 (S1, ADMM scaffold) OPEN at doc time · SIDRA-CTX-01/02 (S1) OPEN at doc time → later VERIFIED-DONE/DEFENSIBLE per Issue Ledger · EFG-LEG-01 COMPLIANT · EFG-DECL-01 COMPLIANT, EFG-DECL-02 (S2) OPEN at doc time → later VERIFIED-DONE per Issue Ledger · EFG-EXEC-01 COMPLIANT · EFG-CMP-01 COMPLIANT · EFG-Q-01 (S2, missing CV/Moran/roughness/entropy) OPEN at doc time · EFG-REG-01 (S1, pending SHE-NORM-01) OPEN · RACE-01 (S2, fixed-W only) OPEN at doc time, later LIKELY-DONE except region-conditioning per Issue Ledger · PIRS-HSIC-01 COMPLIANT · PIRS-FAM-01 (S1, missing simplex/beta-binom families) OPEN · PIRS-SPAT-01 (S1, "entirely absent") OPEN, definitive gap · PIRS-REG-01 (S3) OPEN · PIRS-FDR-02 (S3) OPEN · OUT-01 COMPLIANT, OUT-02/03 OPEN → OUT-03 later LIKELY-DONE per Issue Ledger · REG-DEAD-01/VALIDATOR-01/STALE-LIST-01/SCAFFOLD-01/EOL-01 (S3) all OPEN · Run Profile contract (§3.2, S0 process) — a *proposed*, not-yet-built design, OPEN.

**From ARCHITECTURE_AUDIT (20 verified findings, status as of that doc; substantially superseded by later LDO build waves per Issue Ledger's "the whole LDO layer" VERIFIED-DONE):**
#1 CPW λ2 no stable operating point CRITICAL, later fixed via WP1-era stability-path work · #2 causal orientation orphaned HIGH, later fixed WP5 · #3 residual-scan precision misalignment HIGH, later fixed · #4 spatial GMRF absent HIGH, later fixed WP2 · #5 iid HSIC null anticonservative HIGH, later fixed WP4 · #6 Kronecker separability absent HIGH, later fixed WP8 · #7-#9 dead-code/bypass findings MEDIUM · #10 lag-0 dual-emit PLAUSIBLE, later fixed · #11 unconverged-ADMM-certifies CONFIRMED, later fixed WP6 · #12 randomized NLA unimplemented CONFIRMED, later fixed WP8 · #13-20 low-severity dead-code/lint/stale findings, several REFUTED or DEFENSIBLE on verification.

**From ISSUE_LEDGER (the most current status per the corpus's own precedence rule — "trust the Status column here"):**
FEAT-P3+P4 DONE (P3a-d) except P3e CLI remainder OPEN · SIDRA-CTX-01 DEFENSIBLE/DONE · FEAT-P4 folded into #1 · DIS-06/ZIKA-ACCPT DEFERRED · POP-02 M6 VERIFIED-DONE · RACE-01 region-conditioning DEFERRED (data-blocked) · STOR-05 VERIFIED-DONE · PERF-02 VERIFIED-DONE + hardened · GPU-01..08/LDO-NUM-01/LDO-DESIGN-01/02 MEASURED→NOT-WORTH-IT · DISCO-01 OPEN (future) · MOD-02/WF-11/WF-01/WF-02/LDO-B08 (W11 consolidation cluster) WIP · MOD-01/EFG-03/MATH-22 (Moran's I duplication) DEFENSIBLE · LDO-B03/B04 (HSIC "fork") DEFENSIBLE/false-lead · T1.2 DONE · T1.3 DEFENSIBLE-BY-DESIGN · EFG-QT/DIRECT-QT-01 DONE · EFG-QT-residual DONE (also an active crash fix) · WF-07/EFG-08/EFG-09/EFG-07/MOD-03/WF-08/09 (god-modules) OPEN/OPEN? · T1.8/POP-02-M2 (float32 solver) OPEN · REG-07-LOADER OPEN · MOD-HELD VERIFIED test-only, deletion deferred · ARCH-REG-02/SCOPE-01/PANEL-01 all VERIFIED-DONE.

**From MODULES_REMEDIATION:** T1.1 window-blind cache DONE `64b20d6` · T1.2 completeness gate OPEN (remaining) · T1.3 race-prior wiring OPEN (remaining) · T1.4 EFG workspace cleanup DONE `e999d3a` · T1.6 datasus_combined re-materialization OPEN (biggest remaining storage lever) · T1.8 M2 float32 solve PARTIAL (`ac17ac0`, inputs only; full solve working-set still OPEN) · T1.9 migration O(N²) DONE `80456ce` · T1.10 result-array retention OPEN (remaining) · T1.11 DatasusConfig drift DONE `80456ce`.

**From STORAGE_OPTIMIZATION_PLAN:** W1-W4 (Tier 1) DONE per header · W5/W6/W6b (Tier 2) DONE per header (`83914ac` DATASUS v4 bridge, ZSTD codec, microdatasus retirement) · W7 (Hive-partitioned lazy views, Tier 3) OPEN/optional, explicitly deferred · W8 (SIDRA cache dedup) OPEN, folded into SIDRA sprawl fixes tracked elsewhere.

═══════════════════════════════════════════════════════════════
## CONSOLIDATED LIST (b) — every named component/concept, one-line definition
═══════════════════════════════════════════════════════════════
- **MSD (Master System Document, I/II/III)** — the layered architecture spec of record; MSD-III is current/authoritative, MSD-I/II retained as foundational/cited-by-code.
- **LDO (Latent Dependency Operator)** — the final inference stage; fits a sparse+low-rank Gaussian precision then a residual HSIC scan, emitting typed `LinkRecord` hypotheses.
- **EFG (Epidemiological/Entity-Field Graph)** — the legality-governed graph of typed, provenance-tracked epidemiological fields materialized from SHE substrate.
- **SHE (Substrate Harmonization Engine)** — the layer that decodes raw DATASUS/SIDRA sources into typed canonical primitives with explicit missingness states.
- **CPW decomposition** — Chandrasekaran–Parrilo–Willsky sparse (S) + low-rank (L) split of a precision matrix Ω=S−L, separating direct edges from shared latent factors.
- **L_W** — the spatial GMRF operator κI+L_W (Σ_space⁻¹), used to whiten spatial autocorrelation before/within the precision fit.
- **L_D** — the disease-hierarchy Laplacian (from DiseaseGraph), a prior-regularizer quadratic smoothing precision rows across structurally-related diseases.
- **L_time** — the temporal-smoothness Laplacian tying adjacent lag positions.
- **spatial_field_ref** — a LinkRecord field pointing to a per-edge, spatially-varying (BYM/ICAR) coefficient field answering "where is this link strongest."
- **Adaptive Precision Controller (§V.5)** — an anytime, budget-driven scheduler that sets every approximation dial by value-of-computation and self-corrects by escalating numerically-dominated decision-relevant edges to exact computation.
- **CoverageManifest (§VIII.2(3))** — a typed record distinguishing searched vs. deliberately-unsearched regions, with the sparsity-of-truth assumption stated explicitly.
- **Causal ladder (Rung 0-3)** — a typed hierarchy of causal-claim strength: time-precedence → LiNGAM/collider orientation → quasi-experimental (ITS/DiD/negative-control) escalation → expert-only interventional identification.
- **Kronecker joint operator (§V.2)** — a factored representation Ω_var⊗Σ_space⁻¹⊗Σ_time⁻¹ avoiding the dense (p·S·T)² object.
- **Stochastic log-determinant (§V.3)** — Hutchinson+stochastic-Lanczos-quadrature anytime estimator of a log-determinant, variance controlled by probe count.
- **Run Profile** — a proposed (not-yet-built, per COMPLIANCE_AND_REMEDIATION §3.2) capability tier (`core_vital`/`contextual`/`full`) making partial runs formally, not tacitly, valid.
- **17-key output bundle** — the fixed, MSD §8.1-mandated set of output files every valid run must produce (Hypotheses, V_fields, E_DAG, Q_tensor, etc.).
- **Q_tensor / Q-state** — the 14-component per-field state-diagnostic tensor (n_eff, CV, Moran's I, missingness, provenance risk, etc.) driving verified/fragile/quarantined classification.
- **MeasuredQuantity** — the EFG's terminal typed output object {numerator_count, exposure/denominator, offset_semantics, structure, provenance, uncertainty}, replacing a materialized rate.
- **RaceBridge (Bridge_R)** — the Bayesian ecological race/color reclassification bridge (§4), converting admin-declared race counts toward self-declared composition via a confusion matrix C.
- **ST-DFM** — Spatio-Temporal Dynamic Factor Model, for gated latent-context reconstruction from SIDRA (§2.10).
- **SIDRA context pipeline** — regime-classify → stitch → project → bounded-pushforward, routing IBGE/SIDRA compendium facts into EFG context nodes.
- **HSIC (Hilbert-Schmidt Independence Criterion)** — the residual nonlinear-dependence scanner (§6.7), with a panel-support-keyed structured permutation null and FDR control.
- **DiseaseGraph** — the CID-10 hierarchy-derived structural graph over disease concepts, source of L_D.
- **simple-icd-10 / icd-mappings** — the two ICD library dependencies underlying the disease semantic axis (WHO-2019 hierarchy backbone + broader-coverage grouper, respectively).
- **who_absent_cid10 table (proposed)** — a small declared-gap registry for CID-10 codes (A90, A91, U06) absent from the WHO-2019 tree, filling block/label via `icd-mappings`.
- **PANEL-01** — the CommonPanel data structure/contract wiring compiled substrate into the LDO's tensor assembly; also the name of a "governed keep, do not reap" marker convention used on several intentionally-parked modules.
- **W7 (Hive-partitioned lazy views)** — the proposed storage architecture replacing per-run re-materialization with lazy `scan_parquet` views over a partitioned lake.
- **Run-bundle manifest / ReproducibilityManifest** — the per-run provenance record; historically inlined large tensors as raw floats (a fixed bug), now references parquet paths/hashes.
- **CAUSAL-01** — the task/milestone name for LiNGAM orientation + collider detection; a documented case of a "completed" milestone that was code-complete but unwired until later fixed.
- **`pirs/` package** — a legacy/orphaned inference-support package superseded by `ldo/hsic.py`; retained only because two tests (one a contract guardrail) still import it.
- **REG-07** — the registry-consolidation initiative (unifying duplicate decode-validation stacks); deliberately deferred as a "silent-corruption risk if rushed."
- **W-RACE-1/2/3** — the phased RaceBridge remediation workstreams: code-only uncertainty propagation → real region-conditioned confusion-matrix acquisition → full hierarchical Bayesian model.
- **W-REG-1/2/3** — the phased registry-operationalization workstreams toward "add a new DATASUS system = a registry edit."

═══════════════════════════════════════════════════════════════
No files were edited; this is a pure read-only extraction per the task's constraints. All eleven documents were read to completion (including files whose length exceeded a single tool-call page, which were paged in fully via offset reads).
