# Architecture review (2026-10-06)

**Why.** The author's critique of 2026-10-06, after the debrief of that day:

- the gate reads as "a question is only legitimate if you already know the answer";
- the computation never used the methods the problem obviously needs;
- the lag test was crude;
- much of the architecture is pedestrian for a project this complex.

Development was paused to revise the theory first. This note is the diagnosis, layer by layer, with the evidence. The revised design is ARCHITECTURE.md (revision 2, ADR-0023); the order of work is `docs/plans/2026-10-06-overhaul.md`.

## What holds

These survive the review and are kept:

- **The core is a latent Gaussian model of counts.** NB counts, a GMRF per structured effect, a factorised likelihood that never forms the 10¹² cells. That is the right class of model. Its failures are in how it is solved and read, not in what it is.
- **Expectation first (P1), information weights (P3), declared estimands (P4), the minimum relevant effect (P5).**
- **The ledger as the denominator of every error rate.**
- **Replication on independent units** (ADR-0015).
- **Graded recording explanations, and re-scoping instead of dissolving** (ADR-0019).
- **The gateway boundary to pegasus_data.**
- **Calibration as a necessary check.** It is not a proof.

## What is wrong

### 1. Estimation treats a structured problem as a black box

**What the code does.** A Newton–CG solves each step on autodiff Hessian–vector products with a diagonal preconditioner. The variances move by a Fellner–Schall fixed point. Uncertainty comes from perturbation draws.

**Evidence: chapter IX, 2010–2021** (552,046 parameters, three cold outers, profiled 2026-10-06).
- Of 30 Newton steps, the first ten take 1–3 CG iterations. From step 14 on, every step hits the 50-iteration cap and gains less than 10⁻³. The tail of each mean fit is spent not converging.
- One Hessian–vector product costs 0.15–0.5 s, depending on the machine's load. One forward pass of the total costs 0.017 s.
- Fellner–Schall converges linearly: 12–40 outers per fit, each repeating the mean fit.
- On a 277-death block (chapter VII), 85% of the time is Hessian–vector products over the full lattice.

**Why it is slow.**
- **The Hessian has a known shape, and nothing uses it.** It is block-arrowhead:
  - each place's own effects (its level, group and leaf deviations) couple only with each other;
  - places couple only through the map graph's sparse precision;
  - a few hundred global effects (age, time, tree) couple to everything.
- Such a matrix is factored exactly and directly, as INLA and TMB do:
  - eliminate the per-place blocks in closed form or by batched dense Cholesky;
  - one sparse Cholesky on the graph;
  - a dense Schur complement on the globals.
- **The same factor gives what the rest of the fit needs:** exact traces for the variance updates (selected inversion, Takahashi), and exact marginal variances.
- **The variances can be fitted by the established method.** Maximise the Laplace approximate marginal likelihood in log τ by Newton or BFGS (Wood 2011; Wood & Fasiolo 2017), not by a damped fixed point.
- **The BYM parametrisation makes the ill-conditioning worse.** The geography uses a separate τ for the ICAR and iid parts (ARCHITECTURE §13). The two variances form a ridge, which is the problem BYM2 was introduced to remove (Riebler et al. 2016). The ridge is visible in the `move_tol` stopping rule written to step around it.

### 2. Detection is residual hunting with a constant per lens

**What the code does.** The monolith fits "normal". Lenses then scan the PIT surprises, each with its own null and its own provisional constant (θ0 = 1.2 or 1.5, δ_E = 0.1, FAC_K = 3, FAC_SHARE = 70%, ×1.6, z ≥ 3, sd 0.2…).

**The consequences:**
- The expectation absorbs part of the signal. B2 learns a place's trend; an epidemic needs BP.
- Every lens needs its own calibration campaign.
- Every constant needs a harness run to justify it.

**The literature has model-based versions of most of these estimands:**

| estimand | model-based method |
|---|---|
| unusual place trends | BaySTDetect (Li et al. 2012): a mixture of common and place-specific trends, with posterior probabilities and FDR |
| cell excess | two-group models and local fdr (Efron 2004) |
| clusters | disease mapping with exceedance probabilities; the Bayesian spatial scan (Neill et al. 2006) |
| outbreak baselines | Farrington / Noufaily (2013), the surveillance benchmark |
| change points | Bayesian change-point components |

Read this way, **a lead is a posterior statement about a model term**: how large, how sure, against which minimum effect. It is not a tail probability of a residual statistic under a lens-specific null. Scan statistics stay useful as *search*, cheap proposals of supports, not as the inference.

### 3. Validation became permission

**What the code does.**
- A lens runs only after it recovers declared real events (§10.5).
- A field is scanned only where the lens's power exceeds 0.5 at a reference effect (ADR-0022).

**What is wrong:**
- **The ground truth is thin.** One to three documented events per lens decide pass or fail; that verdict is mostly noise.
- **Design constants were tuned on the same events.** The history rule was chosen on dengue 2019–23; the national trend reference because the positives were state-level. That is fitting the method to its test set.
- **Exclusion is the wrong response to low power.** FDR already controls the false discoveries of weak hypotheses. Their real cost, a small dilution of the others' power, is answered by weighting hypotheses by power (weighted BH; independent hypothesis weighting, Ignatiadis et al. 2016), not by not asking.
- **The established form of validation characterises:**
  - simulation-based calibration of the model (Talts et al. 2018);
  - a designed grid of planted signals giving each method's operating surface;
  - false-discovery rates measured on null worlds;
  - documented events as a held-out check of face validity, never a tuning target.

### 4. Relations are correlations of residuals

**E_w** is one weighted correlation per lag, pooled over places. It failed the microcephaly positive twice:
- at the region-month grain, a flat ρ ≈ 0.12 over lags 0–6;
- prewhitened at the state grain, a lag-0 coincidence (ρ 0.20) and no 5–9 month lead.

That is the expected behaviour of a screen asked to carry an estimand. An exposure–lag–response relation is estimated, not screened:
- **Distributed-lag terms** in the outcome's rate, smooth over lag (Gasparrini et al. 2010). The lag curve becomes a model output with its uncertainty, and season and trend are handled by the outcome's own model.
- **Shared-component models** for two outcomes' common geography (Knorr-Held & Best 2001).
- **Endemic–epidemic models** for coupling between infectious series (Held, Höhle & Hofmann 2005; `hhh4`).
- **Negative-control outcomes and exposures** (Lipsitch et al. 2010) as the standard guard against shared confounding.

**E_b** (place effects with Dutilleul's n_eff and Moran negatives) is a sound ecological screen and stays one.

### 5. Recording artefacts were handled by post-hoc rules

**Triage classes** (system, substitution, facility, noise) were rules with thresholds applied after the fact.

**The rule change did not reach the stored state.** Before the explanations were graded (ADR-0019), those rules had marked **14,813 of 33,228 register leads "explained"**: 41%, none with a tested verdict. A typical reason was "the code's national level moves ×0.24". The graded rule was introduced on 2026-10-05; the stored verdicts were reopened only on 2026-10-06.

**The model can carry much of this itself:**
- every lead read at its conserved level (the ICD family, plus R00–R99, plus undetermined intent), fitted as standard fields, not computed on demand;
- recording processes as measurement terms where the data identify them. Race confusion is built. Completeness κ was measured negligible once place terms are in (2026-10-06). Coding regimes by jurisdiction and era remain.

### 6. The process produced first versions and left them standing

- **Each component was built to run end to end, measured once, and left** while the next gap was opened. Parallel agents multiplied the first versions; nobody returned to make them good.
- **The default answer to a problem was a new check** (a gate, a threshold, a class) rather than the field's established method.
- **Speed had no budget and no benchmark.** Fits of 20–90 minutes and surveys of hours were accepted. Every measurement queued behind every other.
- **Small failures cost hours.** A missing `PYTHONUTF8`, `bash` resolving to WSL, a calibration override in a script.

## The revision in one table

| v1 mechanism | v2 | ARCHITECTURE |
|---|---|---|
| Newton–CG on autodiff HVPs, diagonal preconditioner | exact Newton on the assembled arrowhead Hessian (per-place elimination, graph Cholesky, Schur on globals) | §5.3 |
| Fellner–Schall fixed point, 12–40 outers | the Laplace marginal likelihood maximised in log τ (Newton/BFGS, exact gradients by selected inversion) | §5.4 |
| BYM (two τ, a ridge) | BYM2 (σ, ρ) | §4.3 |
| perturbation draws for marginals | selected inversion from the same factor; draws from the factor where joint quantities are needed | §5.5 |
| lenses with per-lens nulls and constants | departure models (posterior on a model term against the minimum effect), scans as search | §7 |
| E_w correlations by lag | distributed-lag terms; shared-component models; endemic–epidemic coupling; E_b stays as a screen | §7.5 |
| gate and admission by exclusion | characterisation (SBC, planted grid, null worlds); weighting by power (IHW); known events held out | §8.4, §10 |
| triage classes as rules | conserved-level fields as standard; recording as measurement terms; graded explanations only; rule changes re-run on stored state | §8.6 |
| no performance target | budgets per component and a benchmark run on every solver change | §5.8 |
| first versions | maturity levels stated per component; established method first | §1 |
