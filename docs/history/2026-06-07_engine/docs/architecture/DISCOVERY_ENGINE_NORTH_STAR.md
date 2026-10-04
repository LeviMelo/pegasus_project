# PegaSUS as a Discovery Engine — architectural north star

**Status: governing vision (2026-07-13). Sits ABOVE the tactical docs** (`PIPELINE.md` = current
implementation; `FINDING_ONTOLOGY.md` = the Level-1 ecological finding spec; `LDO_DECONFOUNDING_DESIGN.md`,
`ARCHITECTURAL_DEBT.md`, `MODULE_MAP.md` = component detail). This document does not describe what is built;
it fixes *what PegaSUS is for* and the frame every future redesign should be checked against. It is the
synthesis of a design discussion that (a) corrected the purpose, (b) exposed a statistical ceiling on the
old ambition, and (c) surfaced three orthogonal architectural axes the current system lacks.

**Maturity is marked inline:** `[SETTLED]` (agreed, load-bearing), `[PROPOSED]` (a concrete design
direction, not yet detailed), `[SPECULATIVE]` (a promising idea that still needs a rigorous frame before
it can be trusted), `[OPEN]` (a question we have named but not answered). Do not treat `[SPECULATIVE]` /
`[OPEN]` items as decisions.

---

## 1. The core reframe — reveal leads, do not produce conclusions `[SETTLED]`

PegaSUS is a **deterministic epidemiological discovery engine**. Its job is to **reveal fine-grained,
in-data, scope-typed, bias-instrumented association *leads*** that a human scientist then investigates with
proper methods. It is **not** an inference engine that produces epidemiological *conclusions*, and it is not
"automated epidemiology" in the sense of replacing the analyst.

Consequences that this single sentence forces:

- **Detection-centric is correct, not a shortfall.** A lead ("this outcome clusters in these adjacent
  municipalities over these years"; "this stratum carries disproportionate burden"; "this exposure gradient
  tracks this outcome") does not need an adjusted effect with a confidence interval. It needs to be *true
  enough to be worth a look* and *precise enough to point somewhere*. The earlier self-criticism that "the
  ontology is detection-centric while epidemiology is estimation-centric" applied the wrong yardstick: against
  *production* of epidemiology, estimation is missing; against *revealing*, detection is the deliverable.
- **The handoff boundary is explicit.** PegaSUS says "look here, and here is how fragile the signal is";
  the scientist does the case-control / cohort / adjusted / causal analysis. Anything shaped like a
  *conclusion* is out of scope by construction.
- **Actionable = pursuable *within the data PegaSUS holds*.** `[SETTLED]` A lead is only useful if it is a
  pointer *back into the ingested, processed data* (DATASUS microdata + SIDRA + the population tensor), not a
  lead that would require data we never had. Every finding must be traceable to, and re-sliceable within,
  that universe. This is a hard requirement on the finding envelope (provenance, subjects, locus, the
  variable dictionary, reliability), not a nicety.

---

## 2. The three-level statistical frame — where PegaSUS sits, and the wall it cannot cross `[SETTLED]`

The biostatistical menagerie (RR, OR, HR, SMR, dose-response, interaction, mediation, effect-modification)
is not a bag of unrelated tools; it is facets of one object at three **nested levels**. Naming them fixes
what PegaSUS can and cannot automate.

- **Level 1 — dependence / structure.** "Which variables are conditionally associated, and where / when /
  for whom?" The object is a conditional-independence graph plus unary departures-from-homogeneity. **This
  is PegaSUS's core** (the LDO's dependence graph + the finding ontology). Fully automatable.
- **Level 2 — effect estimation.** "How strong is the X–Y association, on an interpretable scale, adjusted
  for a *chosen* Z, with a CI?" The unifying object is **a contrast of a fitted conditional mean
  `E[Y | X, Z]` under a link** (log→RR, logit→OR, Poisson→rate ratio, Cox→HR, spline→dose-response,
  product→interaction, composition→mediation, offset→SMR). Computationally cheap *per query*; automatable as
  **triage only** (see §6). Its role in PegaSUS is to *rank* leads, never to conclude.
- **Level 3 — causal effect.** "What is the effect of *intervening* on X, and is it identified from this
  data at all?" The unifying object is a target estimand `Ψ(P)` with an efficient influence function
  (g-methods / targeted learning / double-ML). **Out of scope for automation** — see the wall below.

**The identification–estimation split, and the wall.** `[SETTLED]` *Estimation* (compute the target given
that it is a function of the observable distribution) is automatable. *Identification* (is the target a
function of the observable distribution at all, or does it depend on the unseen?) is an **assumptions**
question, and assumptions are not in the data. **Bias lives almost entirely on the identification side.**
Concretely: observational dependence pins down the *skeleton* (who is associated with whom), but a whole
**Markov-equivalence class** of causal graphs (`X→Y`, `X←Y`, `X←U→Y` with U unmeasured) produces the
*identical* observed correlations. No amount of multivariate generality distinguishes them from the data
alone. **This is why a bigger, more general LDO can never buy Level 2 or Level 3** — and why "condition on
everything" (what a graphical model does) is *not* "adjust for the right confounders" (and can be worse:
conditioning on a collider or mediator *opens* a spurious path). The old founding intuition — *make it
general and multivariate and bias evaporates* — founders exactly here, as a theorem, not an engineering gap.

---

## 3. The unifying object of the new architecture: `Finding = ⟨structure, grain, instrumentation⟩` `[PROPOSED]`

The theoretical spine that ties the whole redesign together. A PegaSUS lead is a triple:

- **structure** — *what* epidemiological pattern (the `finding_type`: spatial cluster, temporal outbreak,
  stratum concentration, dependency, dose-response, …). This is the axis `FINDING_ONTOLOGY.md` already
  covers.
- **grain** — *at what inferential level the pattern is valid* (ecological / individual / linked-cohort;
  §4). The ecological fallacy is precisely the statement that the same structure can differ across grains, so
  a finding is only interpretable once its grain is declared.
- **instrumentation** — *how fragile the lead is* (§5): sensitivity to unmeasured confounding, negative-
  control status, data-quality reliability, scale-sensitivity.

The current `Finding` envelope carries only **structure** (+ locus / effect_size / significance /
certification). **The two missing dimensions — grain and instrumentation — are the substance of this
proposal.** They are orthogonal to structure and to each other, and each is a first-class axis below.

---

## 4. Axis A — Scope / grain: PegaSUS is not ecological by nature, only by projection `[PROPOSED]`

**The correction.** DATASUS systems (SIM, SINASC, SIH, SINAN, …) are **individual-level record microdata** —
one row per person-event, carrying DOB/age, sex, race, municipality, dates, ICD codes. **SIDRA alone is
strictly ecological** (geo × time × stratum aggregates). PegaSUS today **projects the microdata down to a
muni×year×stratum panel** and runs everything on that. The aggregation is a *lossy modeling choice*, not a
property of the data — and it was mistaken (by me) for the object itself.

**Three inferential grains, unified by "the exchangeable unit":**

| Grain | Unit | What it answers | Fallacy status |
|---|---|---|---|
| **Ecological** | area × time × stratum cell | area/time/stratum patterns; SIDRA-context associations; rates | subject to the ecological fallacy — a *lead*, not an individual effect |
| **Individual** | the person-record (within one system) | within-system individual associations (e.g. race×cause among deaths, adjusting age/sex) | **ecological fallacy does not apply** |
| **Linked-cohort** | the person-*trajectory* (across systems) | longitudinal exposure→outcome (birth→death, birth→admission) | individual-valid; carries linkage error |

**The load-bearing insight `[SETTLED]`:** the single most powerful bias-avoidance move available to PegaSUS
is **not a more general aggregate engine — it is dropping to the individual grain it already has, where whole
classes of bias (the ecological fallacy above all) dissolve by construction.** Correctness at the right grain
beats generality at the wrong one.

**Record linkage (the linked-cohort tier) `[SPECULATIVE]`.** DOB + sex + race + municipality + maternal
attributes form a quasi-identifier supporting **probabilistic linkage** (Fellegi–Sunter: match weights from
agreement/disagreement on quasi-identifiers; blocking; a threshold) — the canonical example being the
published **SIM–SINASC** linked birth–death cohort. This turns cross-sections into trajectories and makes the
Level-2 apparatus *legitimately* applicable where ecologically it never was. Honest hazards that must be
designed for, not waved away: (a) linkage is **probabilistic**, so **linkage error** (false matches dilute;
missed matches select) is itself a bias that must be modeled or at least instrumented; (b) it must be
**deterministic/reproducible** (fixed blocking + weights + threshold) to satisfy §6. Note: this is the tier
that lets us *directly observe* race misclassification (§7, RaceBridge) — an unidentifiable ecological
deconvolution becomes a partially-observed measurement model.

**Architectural inversion this implies `[PROPOSED]`.** Today the aggregate panel is *primary* and the
individual records are *discarded* after aggregation. The target design makes the **microdata the substrate**
and the **ecological panel a materialized view (a group-by projection) of it**. The EFG becomes a multi-grain
compiler (§7). What is *lost* / irreducible and must be kept honest: DATASUS has numerators but not
denominators, so **rates still require the ecological SIDRA denominator**; SIDRA-context questions are
**irreducibly ecological**; not every question has an individual form. So the three grains **coexist** — the
goal is not to replace ecological with individual, it is to stop pretending only ecological exists.

**Privacy — explicitly out of scope by decision `[SETTLED]`.** The data is already public; re-identification
risk is a matter for MS/DATASUS institutional competence and compliance, upstream of us. Our statistical work,
at our scale, adds no re-identification hazard beyond what publication already incurred. Privacy/LGPD is
therefore **acknowledged but deliberately not an architectural constraint on PegaSUS**, and record linkage is
not gated on it. (Recorded here so the decision is explicit and not silently re-litigated.)

---

## 5. Axis B — Bias-awareness instrumentation: arm the investigator, do not disarm the bias `[PROPOSED]`

Given the §2 wall, the achievable and *correct* goal for a discovery engine is **systematic bias-AWARENESS**,
not bias-eradication: every lead carries a quantified vulnerability to the major bias families, so the human
investigates with eyes open. The systematizable arsenal:

- **Sensitivity / bounds attached to every lead `[PROPOSED]`.** You cannot rule out unmeasured confounding,
  but you can compute *how strong it would have to be* to explain the lead away — **E-values** (VanderWeele)
  for effect-type findings, **Rosenbaum bounds** for rank-based ones, **Manski partial-identification bounds**
  when an honest interval beats a heroic point. One number ("survives confounding up to E-value 2.3") arms
  the user better than a false claim of adjustment.
- **Negative controls `[PROPOSED]`.** Auto-nominate an outcome the exposure should not affect (and an
  exposure that should not affect the outcome); a "signal" on the negative control flags systematic bias.
  Strongly systematizable given a rich variable universe (Lipsitch).
- **Collider / mediator refusal `[PROPOSED]`.** For any Level-2 adjustment, *refuse* to condition on
  variables that are plausibly descendants of the outcome (using the partial orientation we *can* learn +
  known temporal order), and flag collider-risky adjustment sets. A *negative* systematization — safer than
  computing the "right" effect.
- **Reliability & information-bias guards `[PARTLY BUILT]`.** The Q-tensor (n_eff, denominator fragility,
  provenance risk), the reporting-delay findings, the mechanical-overlap guard, the rate floor — differential
  data quality *is* systematizable when you instrument the data-generating process. Extend and surface, don't
  reinvent.
- **Scale-sensitivity (ecological / MAUP) `[PARTLY BUILT]`.** Report scale-dependence explicitly (the
  multiresolution BYM already computes nested scales) rather than committing to one aggregation.

**A latent asset to promote `[SPECULATIVE]`.** The LDO's **low-rank component estimates latent common
drivers** — which are *candidate unmeasured confounders*. "A strong latent factor loads on this edge" is
directly bias-relevant information (a warning that a pairwise dependency may be confounded by the latent
factor). The low-rank part is thus already partial bias instrumentation for the dependency findings; it
should be *read out as such*, not merely used internally.

The output of this axis is a per-finding **instrumentation vector**, the third slot of the §3 triple.

---

## 6. Axis C — Deterministic orchestration + gatekeeping: from a finding dump to a reasoned picture `[SPECULATIVE]`

Today PegaSUS **dumps** findings (a live AL run: 184 dissociated rows across 8 types), many of which are the
*same phenomenon seen through different lenses* (a Zika event is a microcephaly outbreak-year **and** a
space-time cluster **and** a low-Apgar co-location, thrice-counted). Orchestration turns the dump into a
structure, in three deterministic layers of increasing ambition and risk:

1. **Fusion (low risk, high value).** Cluster findings sharing subjects + overlapping locus (variables ×
   municipalities × time-window) into one *phenomenon* node. Pure graph-clustering over the finding set;
   collapses the thrice-counted event into one entity. The obvious first move.
2. **Triggered follow-up (the "agentic-but-deterministic" core).** A finding of a given type *fires a fixed
   rule* spawning a targeted next analysis: a spatial cluster of Y → auto-test which SIDRA exposures
   co-locate *within that cluster*; a temporal outbreak at T → auto-scan coincident change-points; a stratum
   concentration → auto-run the stratified confound-check. This is what a human does on seeing a signal,
   encoded as a fixed decision graph → a *reasoned chain* per phenomenon.
3. **Synthesis graph.** Phenomena + follow-ups as a knowledge structure: nodes = phenomena, edges =
   co-located / co-timed / potentially-confounded-by / potentially-explained-by. A picture, not a table.

**The hazard, named precisely `[SETTLED as a risk]`.** A cascade that spawns tests from tests is
**systematized multiple comparisons — a garden of forking paths with an engine behind it.** Without global
error control the false-discovery rate compounds, and an orchestration *shaped to explain findings will
always find explanations* → a **false-story generator** producing a compelling, coherent, wrong narrative.
This raises the stakes on the gap we already have: **per-producer FDR exists, global multiplicity control
does not**, and a cascade is far more dangerous than a flat dump without it.

**The antidote, and why determinism is the enabling condition `[PROPOSED]`.** A fixed, pre-specified
orchestration graph *is a pre-registered analysis plan*: because every branch is decided in advance, the
total number of tests the cascade will ever run is **countable**, and error can be controlled across the
structured family. The matched, mature tools exist: **graph-based / sequential gatekeeping** (Bretz–Maurer,
α flowing along the DAG so a child test consumes budget only when its parent passes) and **hierarchical FDR**.
So the fragility (cascade multiplicity) has a precise antidote (gatekeeping on the pre-specified graph), and
determinism is not aesthetic — it is what makes honest error control *possible*. **This must be built with
the orchestration, not after it.** The "agentic feel" comes only from data-dependent branching; the
guarantees come from the plan being fixed. Frame it as a **fixed inference program (a compiler pass over the
finding set), not an LLM agent.**

---

## 7. Module-by-module implications

- **EFG → a multi-grain compiler `[PROPOSED]`.** Its "field over muni×year×stratum" abstraction gains a
  sibling: a **record-view over an individual (or linked) record set**, of which the aggregate field is a
  *reduction*. Reorganize so the microdata is the substrate and the ecological panel a materialized
  aggregation (§4 inversion). The largest structural change; sequence it early because everything downstream
  inherits the grain.

- **RaceBridge → a grain-aware race *measurement* layer `[PROPOSED]` (currently mis-framed).** The present
  RaceBridge is an *ecological deconvolution* — a workaround forced by the aggregate grain, where individual
  race is unrecoverable. But race is recorded per DATASUS record; at the **individual** grain the problem is
  **misclassification of a recorded attribute** (a measurement-error model), not ecological deconvolution; at
  the **linked** grain a person's race across systems is *directly comparable*, turning an unidentifiable
  confusion matrix into a **partially-observed** one (you can *see* disagreements). So RaceBridge should be
  re-architected per grain — ecological deconvolution (as now, for SIDRA-denominated rates), individual
  misclassification model, linked within-person consistency — and the linked tier is the one that finally
  *identifies* what the ecological version could only assume. This is why the current implementation "is off
  and will be more so": it solved the aggregate facet of a multi-grain problem.

- **LDO → clarified, pruned, and kept in its lane `[PROPOSED]`.** (a) **Role:** it is the **ecological
  Level-1 dependence** engine — *one* scope and *one* finding type (`dependency`), not the whole output.
  (b) **Forbid edge-as-effect:** its "conditional on everything" is not an adjusted effect (§2); the
  architecture must prevent any reading of an edge as a Level-2 estimate. (c) **Prune the over-built trust
  scaffolding:** a large share of LDO cost went into robustness machinery around a modest, cheap core, and
  some of it measured *marginal/redundant* (deconfounding-projection layers vs existing FE; the HSIC scan as
  an OOM source) — match effort to value (§III). (d) **Do not extend it to the individual grain:** the
  Gaussian graphical model wants a rectangular variable×cell panel; individual records are heterogeneous, so
  individual-grain dependence discovery is a *different* statistical problem (per-pair individual regressions
  / mixed-type graphical models), not a bigger LDO. (e) **Promote the low-rank factors to bias
  instrumentation** (§5).

- **Finding ontology → gains grain + instrumentation, becomes orchestration nodes `[PROPOSED]`.** Extend the
  envelope to the §3 triple; add new *discovery lenses* as finding types (dose-response gradient as a
  *screening* signal; interaction; co-outbreak) — lenses, not inference engines. Findings become nodes in the
  §6 synthesis graph rather than a flat list.

- **Output / query → surface the synthesis, scope-typed and bias-instrumented `[PROPOSED]`.** The
  `kind='finding'` query (built this cycle) is the substrate; it must grow views over *phenomena* (fused) and
  the synthesis graph, filterable by grain and by instrumentation, not only a flat findings table.

- **Intents / config → declare the analysis grain `[PROPOSED]`.** Intents today are grain-blind
  (`geo_mode`, `population_mode`, `race_tensor_mode`, all ecological). They need an explicit **analysis-grain
  / scope** declaration so a run states whether it is ecological, individual, or linked — and so the EFG,
  RaceBridge, and finding scope-typing are driven by one authoritative switch rather than assumed.

---

## 8. Level-2 triage estimation — desired, but fenced `[PROPOSED]`

Level-2 effect estimates are *wanted* (they help rank leads), but they are the sharpest way to drift back into
"producing epidemiology." Non-negotiable fences:

- **Opt-in and clearly labeled** as a screening/triage estimate, never a result.
- **A separate producer**, taking an explicit `(X, Y, Z)` and returning a GLM contrast + a **sensitivity
  bound** (§5) — **never** a reinterpretation of an LDO edge (§2 / §7c).
- **Collider-refusal enforced** on every adjustment set (§5).
- **Gated by the orchestration's error control** (§6) — a triage estimate is a follow-up in the cascade, so
  it consumes gatekeeping budget.
- **Grain-honest**: an ecological Level-2 estimate is labeled ecological (fallacy-exposed); the *legitimate*
  Level-2 lives at the individual/linked grain (§4).

---

## 9. What is settled, what is fragile, and a tentative sequence

**Settled (the frame to check everything against):** discovery-not-production (§1); the three-level split and
the identification wall (§2); the `⟨structure, grain, instrumentation⟩` triple as the spine (§3); individual
grain as the real bias-avoidance lever (§4); bias-awareness-not-eradication (§5); determinism as the
prerequisite for orchestration error control (§6); privacy as out-of-scope-by-decision (§4).

**Still fragile / `[OPEN]` — must be developed before trusting:**
- The **orchestration** (§6) is the most powerful *and* most dangerous idea here; it is unsafe until the
  gatekeeping/hierarchical-FDR layer is designed *with* it. Do not ship a cascade without it.
- **Record linkage** (§4) needs a concrete, reproducible linkage design *and* a linkage-error model before its
  findings can be trusted.
- **Global multiplicity across the whole finding space** is already a live gap; orchestration makes it urgent.
- The **EFG grain-inversion** (§7) is a large refactor with wide blast radius; its interface (record-view vs
  field) needs a proper design pass, not a patch.
- Whether Level-2 triage (§8) is worth its drift-risk at all remains a **product decision**.

**Tentative sequence (dependency-ordered intuition, NOT a roadmap):** (1) add the **grain** dimension to the
finding envelope + intents (cheap, unlocks scope-typing and honesty immediately, even before individual
compute exists); (2) **bias instrumentation** on existing ecological findings (E-value / negative-control /
promote the low-rank factors — additive, high-honesty, low-risk); (3) **fusion** (§6.1) — deterministic,
safe, turns the dump into phenomena; (4) design the **gatekeeping** error model; only then (5) **triggered
follow-up** orchestration; in parallel and larger, (6) the **EFG grain-inversion** enabling the individual
tier, then (7) **linkage** and the linked tier, then (8) grain-aware **RaceBridge**. Earlier items are
additive and safe; later items are structural and must be de-risked first.

---

## 10. Non-goals / boundaries `[SETTLED]`

- **No Level-3 causal claims.** PegaSUS provides structure + instrumentation that *helps* a human do causal
  work; it does not assert causal effects (identification is an assumption we cannot verify).
- **No conclusions, only leads.** Anything shaped like a scientific result is downstream of PegaSUS.
- **The aggregate LDO is not the locus of future power.** Generalizing the covariance model buys a sharper
  dependence picture and nothing on the bias or grain axes; the leverage is in grain, instrumentation, and
  orchestration.
- **Privacy/LGPD is not our architectural concern** (§4) — public data, institutional competence upstream.
- **Findings must stay pursuable within the held data** (§1).

---

*This is a living north star. When a redesign is proposed, check it against §1 (is it revealing leads or
producing conclusions?), §3 (does it respect structure × grain × instrumentation?), and §9 (is its fragility
de-risked before it ships?). Update the maturity markers as `[SPECULATIVE]`/`[OPEN]` items are developed into
`[PROPOSED]`/`[SETTLED]` ones.*
