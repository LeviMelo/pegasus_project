# PegaSUS — Conceptual Foundations

*A teaching document, written to be studied and argued with. It settles nothing by fiat; it gives you the concepts and vocabulary to hold your own opinions about the architecture. Where your recent message corrected me, those corrections are folded in and credited. Where I am unsure, I say so.*

Companion to the MSD, MSD-II, and the prior notes. This one is deliberately conceptual rather than normative — it is about *what the system is* before *what the code does*.

---

## How to read this

Each Part builds on the previous one. Part I (the ontology) is the foundation everything else rests on; if only one Part sticks, make it that one. I define terms as I introduce them and use running analogies. When something is genuinely hard, I flag it — the friction you feel is real and mostly a sign that the material *is* hard, not that you're behind.

A note on the friction itself, because it matters: you have repeatedly turned out to be *right* on the substance while doubting your framing. You were right that the tensor must model dynamics. You were right that format is interchangeable but ontology isn't. You were right that the hierarchical scanner isn't exhaustive. What you lack is not insight — it's the vocabulary to name what you already sense. This document is mostly vocabulary.

---

# Part I — The ontology: stocks, flows, and fields

Everything downstream — what the EFG is for, why the tensor exists, how context enters, what "epidemiology" even means for us — falls out of getting the ontology right. So we spend real time here.

## 1. Three kinds of quantity

There are exactly three kinds of thing PegaSUS measures. Keep them separate and most confusions dissolve.

**Flows (events).** A flow is an *occurrence*: something that happens to an individual at a moment. A death. A hospitalization. A birth. A dengue notification. Ontologically an event is a *token* — a dated, individual-attributable happening. You do not "measure" an event; you *count* events that fall in a region of space-time. The natural mathematical object is a **point process**: scatter of dots in (space × time × attribute) space, where each dot is one occurrence carrying attributes (age, sex, race, cause). When you "aggregate SIM to municipality-year," you are *integrating the point process over a cell* — counting the dots inside it. The result is a **count**, and a count's honest model is Poisson-like, with a notion of *how much opportunity there was* for events to occur (more on this in Part II).

**Stocks (states).** A stock is a *standing quantity* that exists at every instant: how many people live in municipality *s* right now. Kilometers of sewage network in place. A stock is not an occurrence; it is a *level*. Crucially, **stocks and flows are linked by accounting**: a stock is the running total (the integral) of the flows into and out of it. The population stock goes up by births and in-migration, down by deaths and out-migration. This is not a metaphor — it is a conservation law, and it is *the* reason the demographic tensor exists (§4).

**Fields (context / environment).** A field is a *property of a place-time*, usually slowly varying, usually of the *environment* rather than of individuals: sewage coverage, GDP per capita, urbanization, average rainfall, altitude. A field is the *conditions under which* flows happen — the risk surface. Population is a special stock that also behaves like a field (it has a value everywhere), which is why it sits at the hinge between the two.

The bathtub makes it concrete. The **water level** is a stock. The **faucet and drain** are flows. The **room temperature, the shape of the tub, the water pressure** are fields — the environment that governs how fast the flows run. Epidemiology, in one sentence, is the science of *how the fields and stocks govern the rates of the health-relevant flows.*

## 2. "Event data" vs "contextual data" is exactly stocks/flows vs fields

You asked me to frame your event/context intuition properly. Here it is: **your "event data" is flows; your "contextual data" is fields (plus the population stock).** You had already found the right cut; it just needed names.

- DATASUS (SIM, SIH, SINASC, notifications) is overwhelmingly **flow data** — registries of occurrences. Each row is a token event with attributes.
- SIDRA is overwhelmingly **field data** — surveys and censuses measuring standing properties of places. Each cell is a level, not an occurrence.
- The population tensor is the **stock** that bridges them — and it is built *from* flows (births, deaths, migration) to serve as the *denominator field* for rates.

Why this matters so much: the three kinds have *different natural mathematics, different natural resolutions, and different natural roles in a model*. Flows want count models with exposure. Fields want to be covariates/parameters. Stocks want conservation/accounting. Forcing them all into one mold (e.g., "everything is a time series in one precision operator") is the category error that has been biting you. We return to this in Parts III and V.

## 3. Format is interchangeable; ontology is not — and this is a design gift

Your OLAP insight is sharp and correct, so let me sharpen it further. You noticed you can rewrite SIM into SIDRA's shape: treat "deaths (of persons, count)" as the *measure*, each column (sex, age, cause…) as a *classification axis*, each value as a *category*. True. The cube format is universal; **any tabular source — DATASUS or SIDRA — is expressible as `(measure, classification axes, categories, cell values)`.**

The payoff you half-saw: this means the *registry* can be unified too (Part VII). One schema can type *any* source. But — and this is the crucial "not" — **format-sameness does not erase ontology-difference.** After you rewrite SIM as a cube, its cells are still *counts of occurrences* (flow), while sewage cells are still *levels* (field). The cube format hides the distinction; it does not remove it. So the correct architecture is: **one universal cube-shaped registry format, plus one explicit ontological tag (`kind: flow | stock | field`) that the format itself cannot infer.** The tag is what tells the downstream math whether to treat the quantity as a count-with-exposure, a conserved stock, or a covariate surface.

This is exactly what the codebase is missing (we verified it: DATASUS and SIDRA are two parallel registry worlds, and no `kind` tag exists — the ontology is encoded only as "which world you're in"). Unifying the format and *adding the missing tag* is a large, clean win, and it is the concrete resolution of your thread C.

## 4. The population tensor, finally explained: a stock that is the integral of flows

Now your correction about the tensor lands with full force, and I was wrong to frame it as "beat interpolation." Here is the right framing.

The population is a **stock**. A stock obeys an accounting identity: its change over time *is* the net flow. In continuous form, `dP/dt = births − deaths + in-migration − out-migration`, and across the age axis, aging is just the deterministic flow of a cohort from age *a* to *a+1*. The demographic tensor's six loss terms (aging, birth, death, migration, race, smooth) are **a discretized statement of that conservation law**. The tensor is not curve-fitting a shape between censuses; it is *reconstructing the trajectory of a conserved stock subject to its governing flows*, anchored where we have observations (censuses) and closed to known totals.

Why this makes "interpolation vs optimizer" a non-question, exactly as you said: interpolation models each (age, sex, race) cell as *its own independent curve between two census points*. But the cells are **not independent** — they are coupled by demography. A cohort of 10-year-olds in 2010 *must* become the 22-year-olds of 2022; deaths in a cell *must* leave the stock; migration *must* balance nationally. Interpolation ignores every one of these couplings. It can accidentally match the endpoints while violating demographic accounting in between (e.g., implying cohorts that grow without births, or age structures that can't have flowed from the prior year). The tensor exists precisely to *forbid demographically impossible reconstructions* — to make the intercensal estimate *coherent with the process that generates population*. That is not a performance upgrade over interpolation; it is a different and stronger scientific claim: **"this is a population trajectory that could actually have happened," not merely "a smooth curve through the census dots."**

So: the tensor is mandatory not because it beats interpolation numerically, but because **only a process model produces demographically valid latent states**, and everything downstream (every rate) depends on the denominator being valid, not merely smooth. You were right; I under-argued it. This also tells us *when* other data must be "made dynamic," which is Part III.

---

# Part II — What the EFG is actually for

This is the fear you named most directly: that you built the EFG around a naive goal (turn counts into rates), then watched PIRS tear the rates back apart, and now suspect the whole layer is confused. Let me resolve it, because the resolution is clean and it mostly *vindicates* the EFG while correcting one wrong assumption.

## 5. The rate confusion: normalization belongs in the model, not in a pre-built variable

Your original intuition: "a raw count like *deaths = 4* is not statistically usable; I must turn it into *deaths/population* to compare across places." The intuition is *half right* and the half that's wrong is the important half.

What's right: raw counts **are not comparable across cells**, because a cell with 4 deaths out of 500 people is nothing like 4 deaths out of 500,000. Comparison requires accounting for the *population at risk*. That instinct is correct and it is the soul of epidemiology.

What's wrong: the fix is **not** to pre-compute a rate and hand that to the statistics. Here is why, and this is the key statistical lesson of the whole project, so I'll go slowly.

A count is a *discrete* quantity with a *variance tied to its mean* (Poisson: variance ≈ mean). A rate `r = deaths/pop` is a *ratio*, and turning it into a plain continuous number throws away three things at once:

1. **The variance structure.** A rate of 1/1000 and a rate of 1000/1,000,000 are numerically equal but statistically *worlds apart*: the first is estimated from 1 event (wildly uncertain), the second from 1000 events (precise). As a bare number "0.001," they look identical, and any model treating them as equally reliable Gaussian observations will be badly wrong. The *count* carries this reliability; the *rate* discards it.
2. **The exposure weighting.** To pool information correctly, big-population cells should count more than tiny ones. The count-plus-population form knows the exposure; the bare rate has amnesia about it.
3. **The zero problem.** Small cells produce rates of exactly 0 (no deaths) or huge unstable spikes (1 death in 50 people = 20/1000). These are artifacts of the ratio, not signal. The count form handles zeros naturally; the rate form manufactures noise.

The statistically correct move is the **Poisson (or negative-binomial) model with an offset**:
```
log E[deaths_i] = log(population_i) + α + (structure)_i
```
Read it aloud: "the log of the *expected count* equals the log of the population (a fixed, known *offset*) plus the effects we're estimating." Rearranged, `E[deaths_i]/population_i = exp(α + structure)` — **the rate is what the model *implies*, not what you feed it.** You fit on counts, you carry population as exposure, and the rate falls out as a derived view with correct uncertainty. This is precisely why PIRS/the LDO "deconstructs" your rates: it needs the count as the response and the population as the offset. It was not undoing your work capriciously; it was recovering the components that the rate had prematurely fused.

## 6. The EFG, reconceived: an algebra of measured quantities, not a rate factory

So is the EFG wrong? **No — it is mostly right, but over-committed to one output shape.** Let me separate what the EFG legitimately does from the one thing it should stop doing.

What the EFG is genuinely, indispensably *for* (keep all of this):

- **A type system for epidemiological quantities.** It knows that Deaths and LiveBirths are different carriers; that you may divide deaths by *population* but not by *births*; that you may sum counts over municipalities but not sum a multi-label concept; that a race-stratified numerator needs a race-consistent denominator; that two fields can only be combined if their axes align. This "legality algebra" is real, hard-won, and correct. It is a *compiler's type checker* for epidemiology, and it prevents nonsense constructions that would silently produce garbage science. This is the EFG's true reason to exist.
- **Provenance and measurement-process tracking.** Every field knows its lineage, its support, its reliability (the state tensor), its uncertainty. Indispensable.
- **The construction grammar.** How to build a legal quantity from raw fields via operators (restrict by cause, stratify by age, aggregate over space).

The one thing to change: **the EFG's *terminal output* should not be a finished rate.** It should be a **measured-quantity object** — a bundle of `(numerator count, exposure/denominator, offset semantics, structure, provenance, uncertainty)` — from which a rate is *one possible view*. Today the EFG rushes to materialize `deaths/pop` as a scalar field; then the LDO has to reverse it. The fix is to stop at the components and hand the LDO exactly what it needs: the count, the exposure, and the declared relationship between them.

Put differently: **the EFG's job is to certify and assemble the *ingredients* of a rate with their relationship typed, not to cook the rate.** The rate is cooked inside the model (as `exp(offset + effects)`) where its uncertainty is correct. This is a small conceptual shift with large consequences: it eliminates the deconstruct-reconstruct waste, and it means the EFG and the LDO finally speak the same language (count + exposure), instead of the EFG producing rates the LDO must un-produce.

So your fear is only *one-third* founded: the EFG's *legality and provenance* mission is sound and important; only its *rate-materialization* habit was the naive part, and it's a targeted fix, not a teardown. You built the right type system around a slightly wrong output contract.

---

# Part III — When must static data become dynamic?

You gave the perfect pair of examples: the census (which you *did* dynamize, via the tensor) and single-year sewage or 2018 dengue (which are epidemiologically precious even though undefined across 2000–2025). When is dynamization necessary, and when is it a mistake?

## 7. The rule

Make a quantity dynamic (reconstruct it as a dense time-varying series) **only** when at least one of these holds:

1. **It is a conserved stock feeding an accounting identity.** The population is conserved (aging/births/deaths/migration link years). A conserved stock *cannot* be left static without violating its own conservation law — its intercensal values are *determined by* the flows, so you must reconstruct the trajectory. → Dynamize.
2. **It is the denominator/exposure of a rate.** Because rate = flow/stock and the stock changes yearly, a static denominator would bias every rate in every non-census year. → Dynamize (this is a special case of 1 for population).
3. **It is itself the outcome whose dynamics you're studying.** If the *trajectory* is the object of interest, you need it resolved in time. → Dynamize.

Otherwise — **do not dynamize.** A field like sewage coverage is a slowly varying *parameter of the risk surface*. Its epidemiological job is to *condition the rates of flows*, and it can do that job **at its own native resolution** without being smeared into a fake annual series. Making it dynamic would (a) invent temporal variation that was never measured (false precision — exactly what PegaSUS forbids), and (b) create a near-constant pseudo-series that pollutes any dynamic model (Part V). The 2018 dengue count is similar-but-distinct: it *is* a flow (so it has real temporal meaning), just a sparsely observed one — it enters as a real but temporally-sparse event series, not as something to be densified by fabrication.

## 8. Staleness as typed uncertainty, not fabricated dynamics

The honest way to use a 2017 sewage measurement for a 2020 analysis is not to interpolate a fake 2020 value. It is to **carry the 2017 value as the best available estimate of the standing field, and *increase its uncertainty* the further you are from the measurement year.** The value stays put; the *confidence* decays. This is the difference between *fabricating a trajectory* (dishonest) and *acknowledging a slowly-changing parameter with growing uncertainty* (honest). It also gives the downstream model exactly the right behavior: a stale field can still contribute, but its influence is automatically down-weighted by its inflated uncertainty.

The ontological payoff: **flows and conserved stocks live on the dense dynamic lattice; fields live at their native (often sparse, coarse) resolution and enter as typed, uncertainty-decayed parameters.** This is a clean architectural law, and it directly contradicts the tempting-but-wrong idea "make everything dense like the tensor." The tensor is dense because population is a *conserved stock and a denominator* — the two strongest reasons on the list. Almost nothing else qualifies.

---

# Part IV — What is "epidemiology," and what is the shape of the goal?

Two of your deepest questions: (I) should we privilege health data, given that sewage↔GDP from SIDRA alone is valid science? and (A) if we discovered *all* links, would there be "no epidemiology left"?

## 9. Don't privilege sources; type the links

The clean answer to (I): **do not build a health-data hierarchy into the engine.** The LDO discovers dependencies in the *joint field of flows, stocks, and fields*, whatever their source. What makes a link "epidemiological" is not which source it came from but **what kind of quantities it connects**:

- A link touching at least one **health flow** (deaths, admissions, notifications) is *epidemiological*.
- A link among **fields only** (sewage↔GDP) is *socioeconomic/environmental* — valid, valuable, real science.
- A link touching the **population stock** and a health flow is *demographic-epidemiological* (e.g., age structure ↔ mortality).

So the resolution is a **link-type taxonomy**, not a source hierarchy. Every discovered edge is *labeled* by the ontological kinds it connects. An "epidemiological query" then *filters* the discovered field to health-flow-touching edges — but the engine never *refuses* to find the sewage↔GDP edge, and never pretends that edge is worthless. This is more honest and more general than privileging DATASUS: relevance becomes **emergent** (which fields participate in strong, certified edges) and **query-dependent** (you choose which link-types to surface), never hard-coded. PegaSUS is, at bottom, a *field-science engine*; "epidemiology" is a *view* over its output, defined by link-type, not a restriction baked into the machinery.

## 10. The "no epidemiology left" hypothetical — and the real limit

Your hypothetical is beautiful and worth taking seriously: if PegaSUS exhaustively discovered every link, would the whole thing become one foundational asset with nothing left to query? The answer is *no*, and *why not* tells us what the goal actually is and where the true boundaries lie.

**Reason 1 — the link space is not finite.** "All links" is undefined until you fix: the resolution (geo × time × disease × age × …), the functional form (linear? which nonlinearity?), the *conditioning set* (a dependence between A and B can appear, vanish, or reverse depending on which other variables you condition on — there are exponentially many conditioning sets), the lag structure, and the interaction order (pairwise, triple, …). The space of statistical relationships in a rich field is **combinatorially unbounded**. The LDO computes a *specific, well-defined slice* of it (structured conditional dependencies + residual nonlinear edges at a chosen resolution). "Exhaustive" always means "exhaustive *within a declared class*," never absolutely. This is not a limitation to apologize for; it is the nature of inference in high dimensions.

**Reason 2 — the binding limit is information, not compute.** Here is the deep point, and it reframes the whole "scale" worry. As you refine resolution and expand conditioning sets, the number of *hypotheses* grows faster than the *data* can support. Fine cells become sparse; effective sample size shrinks; eventually you have more questions than independent observations, and any further "discovery" is fitting noise. So there is an **information-theoretic ceiling** on how much epidemiology is *reliably discoverable* from a given corpus — roughly set by the number of effective independent observations — and **no hardware, however large, moves that ceiling.** A supercomputer would let you *compute* more candidate links; it would not make them *true*. This is liberating: it means your laptop is not the fundamental constraint on the *science*; it's a constraint on the *search*, and the search can be made efficient (Part V). The science is bounded by Brazil's data, not by your GPU.

**Reason 3 — associations are not the whole of epidemiology.** Even a complete associational link-graph does not answer the questions scientists actually care about: *mechanism* (does A cause B, or do both follow C?), *mediation* (through what pathway?), *counterfactual/intervention* (what happens if we build sewers?). The link graph is the **substrate** for those questions, not their answer. Discovering A↔B↔C leaves the causal orientation (A→B→C vs A←B→C) undetermined without further assumptions or experiments.

So the shape of the goal, precisely: **PegaSUS's end state is not "epidemiology finished." It is a *living, bounded, typed associational skeleton* — the discovered dependency field — maintained as a foundational asset, refreshed as data and the world change, from which humans and AIs pose higher-order causal and interventional questions.** A "query" is not "compute a link" (that's foundational build); a query is **interrogating, interpreting, and causally escalating the skeleton.** That is the durable division between build and serve, and it dissolves your hypothetical: the skeleton can be (mostly) built, but the *science on top of it* — causal, mechanistic, interventional, and forever renewed by new data — is inexhaustible. There is always epidemiology left, because association is the floor of science, not its ceiling.

---

# Part V — Making national scale fit on your laptop, with validity intact

You're right that I've under-served this, and it's where the real scientific-computing depth lives. The question has two halves you correctly insisted on joining: *can we fit it in 6 GB / 32 GB?* and *can we do so without lying about the numbers?* The answer to both is yes, and the reason both answers are yes is the **same**: the methods that make it fit are, for the most part, *randomized algorithms with provable error bounds* — not heuristics. Let me actually teach the toolkit.

## 11. The structure that saves you: sparsity + separability

Two structural facts turn an impossible object into a tractable one.

**Sparsity.** Almost every operator in the LDO is mostly zeros. The spatial GMRF (from contiguity) has ~6 neighbors per municipality → ~6 nonzeros per row out of 5570. The disease-hierarchy Laplacian is sparse. The variable-precision, under graphical-lasso, is sparse by construction (few direct links per variable). A dense 5570×5570 matrix is 124 MB in float32; its sparse form is ~0.3 MB. You never build the dense one. Tooling: `scipy.sparse` (CSR/CSC), sparse Cholesky via `scikit-sparse`/CHOLMOD, and matrix-free iterative solvers (below).

**Separability (the Kronecker trick — the single biggest lever).** If the covariance factors as a *Kronecker product* `Σ ≈ Σ_var ⊗ Σ_space ⊗ Σ_time`, then every expensive operation *factors across the small pieces*. The intuition: instead of one giant `(p·S·T)²` object (for national-monthly, that's ~`(10^7)² = 10^14` numbers — utterly impossible), you keep three small ones (`p²`, `S²`, `T²`) and combine them on the fly. Matrix–vector products, linear solves, and even log-determinants (`log det(A⊗B) = n·log det A + m·log det B`) all decompose. This is what collapses 10^14 into ~10^6. The whole feasibility argument rests here. Precedent you can lean on: **GPyTorch** is an entire GPU library built around exactly this (structured/Kronecker Gaussian inference with matrix-free operations); its machinery is directly applicable.

The honest caveat, which you should hold onto: **separability is an approximation.** Real structure sometimes couples space and variables in non-separable ways (a link that exists only in dense cities). The backbone is separable; the *residual nonlinear layer* (HSIC on what the backbone can't explain) is there precisely to catch what separability misses. We accept a separable *backbone* for tractability and *audit its residuals* for what it drops. That audit is part of the validity story (§14).

## 12. Randomized numerical linear algebra — provable approximation, not hand-waving

This is the toolkit you were hungry for. The governing idea: **you can replace an exact O(n³) computation with a randomized O(n²k) or O(nnz·k) one that is correct up to a small, *quantifiable* error with high probability.** These are theorems, not tricks.

- **Randomized SVD / low-rank approximation** (Halko–Martinsson–Tropp). To find the rank-*r* latent factors (the low-rank *L* in the LDO), you don't compute the full SVD. You multiply the matrix by a small random Gaussian sketch, orthogonalize, and do a tiny SVD of the result. Cost drops from O(mn·min(m,n)) to O(mn·r). The *error* is bounded: with high probability the approximation is within a small factor of the best possible rank-*r* approximation (the true (r+1)th singular value). **Off-the-shelf:** `sklearn.utils.extmath.randomized_svd`, `torch.svd_lowrank`. This is how you estimate the shared "epidemic wave" factors on a laptop, *with an error bound*.

- **Stochastic log-determinant estimation** (Hutchinson + stochastic Lanczos quadrature). The Gaussian likelihood needs `log det(Σ)`, normally O(n³). You can estimate it from a handful of matrix–vector products with random ±1 probe vectors, using Lanczos quadrature — the same method GPyTorch uses to scale to huge problems. **Validity:** it's an *unbiased* estimator whose variance you *control* by adding probes (more probes → tighter). You can report the estimator's own error bar. **Off-the-shelf:** GPyTorch's `logdet`, or a ~40-line Hutchinson+Lanczos implementation.

- **Sketching for the regressions** (Johnson–Lindenstrauss). The neighborhood-selection regressions (the sparse-precision step) have huge row counts at national-monthly scale. A JL random projection (or a subsampled randomized Hadamard transform) compresses the rows while *provably preserving* the geometry to within `(1±ε)`. You regress on the sketch. **Validity:** the JL lemma is a distortion guarantee, not a hope. **Off-the-shelf:** the sketch is a few lines of NumPy; libraries like `scikit-learn`'s random projections exist.

## 13. Out-of-core, mixed precision, matrix-free solvers, compression

- **Sufficient statistics beat big data.** The national-monthly tensor doesn't fit in 32 GB RAM. But the regressions only need `XᵀX` and `Xᵀy` — objects of size `p²` and `p`, *tiny* regardless of how many rows there are. So you **stream the data once** from memory-mapped columnar storage (Parquet + Arrow, or DuckDB querying Parquet), accumulating the sufficient statistics tile by tile. The data is huge; what you keep in memory is small. This is the classic "the model fits even when the data doesn't" pattern, and your storage layer already supports it.
- **Matrix-free iterative solvers.** Never invert a covariance; *solve* against it with Conjugate Gradient / MINRES, which need only matrix–vector products (and those factor via Kronecker + sparsity). Add a **preconditioner** (incomplete Cholesky, or the Kronecker factors themselves, or a pivoted-Cholesky preconditioner) to make CG converge in a few iterations. Everything stays matrix-free and GPU-friendly.
- **Mixed precision, carefully.** float32 (already your spec) halves memory vs float64 and the RTX 4050 is much faster in float32. For the bulk (matvecs, sketches) this is fine; for the *reductions* — summing millions of terms, log-dets, ill-conditioned solves — accumulate in float64 (or use Kahan summation) to avoid precision bleed. **Honesty flag:** covariance estimation can be ill-conditioned, and there float32 *can* cost you real accuracy; the mitigation is preconditioning plus selective float64 on the sensitive steps, and *checking the condition number* so you know when you're in danger. This is a genuine validity risk I won't paper over.
- **Hierarchical compression (H-matrices / HODLR).** For dense-but-smooth spatial kernels, hierarchical off-diagonal-low-rank formats store an n×n operator in ~O(n log n) with *controllable* accuracy. This is real compression with error control — but it's the most research-grade item here; treat it as a later optimization, not a day-one dependency.

## 14. The validity contract (this is the part that keeps the science honest)

Here is the principle that lets you trade compute for scale *without lying*: **every approximation must become a typed, propagated uncertainty component, and must be validated against exact computation on a subproblem.** Concretely:

1. **Bounded, not heuristic.** Prefer methods with error bounds (randomized SVD, Hutchinson, JL). Their error is a *known distribution*, not a mystery.
2. **Propagate the approximation into the result's uncertainty.** If randomized SVD introduces error ε into a factor, that ε flows into the affected link's uncertainty. The link record's `uncertainty` field then reflects *both* statistical sampling error *and* numerical approximation error. You never present an approximated number as if it were exact — the approximation shows up as widened error bars, consistent with PegaSUS's entire anti-false-precision ethos.
3. **The small-scale exact run is the reference.** A *state*-scale monthly run fits in VRAM and can be done (nearly) exactly. The *national* approximated run must **agree with the exact run where they overlap** (e.g., the Alagoas sub-block of a national run ≈ the standalone exact Alagoas run, within the propagated bounds). This is a continuous, automatable validity check: the exact regime certifies the approximate regime. If they disagree beyond the stated bounds, the approximation is rejected — loudly, not silently.

That triad — bounded methods, propagated approximation-uncertainty, exact-reference cross-check — is how you get national scale on a laptop while keeping results "valid to a reliable and agreeable extent." The trade is made *visible and quantified*, which is the only honest way to make it.

---

# Part VI — The exhaustiveness problem (you're right that coarse-screening isn't complete)

You caught the flaw in "only drill where a coarse link fires": a link can be **invisible at coarse resolution yet real at a finer one.** This is not a minor caveat; it's a deep statistical fact, and pretending otherwise would be exactly the kind of hidden gap PegaSUS is supposed to forbid.

## 15. Why aggregation hides links

Four distinct mechanisms, worth knowing by name:

- **Simpson's paradox / sign reversal.** A relationship can be positive within every subgroup and negative in aggregate (or vice versa), depending on how subgroup sizes correlate with the variables. Aggregating first can *flip* the finding.
- **Cancellation.** A strong positive effect in some regions and a strong negative effect in others *sum to nothing* at the coarse level. The coarse mean sees zero; the truth is two opposite real effects.
- **Threshold/nonlinearity.** An effect that only appears above some exposure level is invisible in the average, which sits below the threshold.
- **Sparsity dilution.** A sharp rare-disease link (say, a specific arbovirus subcode → a specific anomaly) gets swamped when the code is aggregated into a broad chapter with mostly-unrelated conditions.

So a coarse *test of association* has real false negatives, and a naive "drill only where the coarse test fires" pipeline will *systematically miss exactly the localized, heterogeneous, threshold, and rare effects that are often the most epidemiologically interesting.*

## 16. The fix: screen for what aggregation hides, audit the rest, and type the coverage

You cannot be *absolutely* exhaustive (Part IV: information and compute both forbid it). But you can be **honestly bounded-exhaustive**, via three moves:

1. **Screen on sensitivity, not on the aggregate mean.** The coarse pass should not test "is there an average association here?" It should test "is there *any reason to look closer*?" — a statistic *designed to fire on the things aggregation hides*: subgroup **heterogeneity** (variance of the effect across sub-cells), **dispersion**, or the **maximum subgroup signal**, rather than the pooled mean. A cancellation case has zero mean but *high heterogeneity* → a heterogeneity screen fires and triggers the drill-down. This single change (screen on heterogeneity/max, not mean) recovers most of what a mean-based screen would miss, at nearly the same cost. It converts the coarse pass from a *test* (which has false negatives) into a *sensitive filter* (tuned for recall, deliberately over-flagging).

2. **Random deep audits.** Even a sensitive screen misses things. So, on a *random sample* of the branches the screen pruned, run the full fine analysis anyway. This estimates the **false-negative rate** empirically and catches a bounded fraction of what the screen dropped. You trade a little compute for a *statistical guarantee* about your own blind spots — you can then report "we estimate we missed at most X% of fine links, with 95% confidence," which is worlds better than an unquantified silence.

3. **Type the coverage — never a silent gap.** Whatever you *didn't* search is recorded as a typed `unsearched` region of the hypothesis space (at what resolutions / conditioning sets / functional forms coverage was complete, and where it was pruned and why). This is the same anti-silent-absence ethos that governs your data cells, now applied to the *search itself*: a pruned branch is a declared, auditable decision, not an invisible hole. A user can then explicitly request a deeper search of a `unsearched` region.

Honesty flag: the sparsity-of-truth assumption underlies all of this — the bet that *most* fine links are genuinely null, so a sensitive screen + random audit catches most real ones. That bet is usually right in epidemiology, but it *is* an assumption, and it should be stated in the coverage manifest, not hidden. This is one of the genuinely open methodological questions (it belongs on the "least settled" list), but the screen-on-heterogeneity + random-audit + typed-coverage design is a real, defensible answer to a problem I previously waved at.

---

# Part VII — One registry to type them all

We verified the concrete debt: DATASUS and SIDRA are two parallel registry worlds, and the event/field ontology is nowhere named. Parts I and IV tell us the fix.

Because the cube format is universal (§3), a **single registry schema** can type *any* source — DATASUS or SIDRA or a future source — as:
```
source_registry_entry:
  measures:        [ {name, unit, kind: flow|stock|field, carrier?, exposure_semantics?} ]
  classification_axes: [ {name, semantic_axis, categories, aggregation_law: partition|multilabel|hierarchy} ]
  native_resolution:   {geo, time}          # where the source actually lives
  ontological_kind:    flow | stock | field # THE missing tag (§3)
  provenance, projection_status, refresh_cadence
```
The one thing the format cannot infer — `ontological_kind` — is supplied explicitly, and it is what routes each quantity to its correct mathematics (flow → count+exposure; stock → conservation/CTR; field → typed covariate with staleness). Onboarding a new source becomes *one entry in one schema*, and the ergonomics you wanted follow directly: no separate DATASUS-vs-SIDRA machinery, just a new row that declares its measures, axes, native resolution, and kind. This also *unifies* the fragmentation we've been noting (≈40 registry files, two worlds) into one coherent onboarding surface — advancing the refactor goal and the ontology at the same stroke.

---

# Part VIII — What this settles, and what stays open

**Settled (conceptually):**
- The ontology: **flows, stocks, fields** — with events = flows, context = fields, population = the bridging stock. (Part I)
- Why the tensor *must* be a process model: population is a **conserved stock = integral of flows**; interpolation models cells as independent and violates demographic accounting. Your correction was right. (Part I.4)
- What the EFG is *for*: a **legality/provenance algebra** that should output **count+exposure+structure**, not finished rates. Normalization belongs *in the model as an offset*. Your EFG isn't confused — its type system is sound; only its rate-materialization output was naive. (Part II)
- When to dynamize: only **conserved stocks, denominators, or outcomes**; fields stay at native resolution with **staleness as typed uncertainty**. (Part III)
- "Epidemiology" = a **link-type view** (health-flow-touching edges), not a source hierarchy; context-only science is valid and kept. (Part IV.9)
- The goal's shape: a **living associational skeleton** as foundational asset + **causal escalation** as the inexhaustible query layer; the real ceiling is **information, not compute**. (Part IV.10)
- Scale on a laptop *with validity*: **sparsity + Kronecker + randomized NLA (provable bounds) + streaming sufficient statistics + mixed precision + matrix-free solvers**, under a **validity contract** (propagate approximation error; exact state-run certifies approximate national-run). (Part V)
- Exhaustiveness: impossible absolutely, but **bounded-exhaustive** via **heterogeneity-sensitive screens + random deep audits + a typed coverage manifest**. (Part VI)
- One **unified, kind-tagged data registry** for all sources. (Part VII)

**Genuinely open (research or deep-design; equal priority, not to be rushed):**
- Whether separability + the residual-HSIC audit actually capture enough real non-separable structure (empirical question).
- Identifiability of latent-vs-lag-vs-spatial confounding at scale, and the true discriminating power of the certification gate.
- The sparsity-of-truth assumption behind bounded-exhaustiveness — when does it fail, and how badly?
- Numerical validity under float32 for ill-conditioned covariance — where exactly does it bite, and is selective float64 enough?
- The national migration-enclosure constraint's behavior at 5570 municipalities.
- How causal escalation (the query layer) should actually work — orientation, mediation, intervention — atop the associational skeleton.
- Validation against ground truth beyond the handful of known links (Zika→microcephaly): how do we distinguish real discovery from stable spurious structure?

None of these needs closing now. They need to be *named, held, and returned to* — which is what this document is for.

---

*This is a foundation to argue with, not a verdict. Where a claim here doesn't sit right with you, that friction is the most valuable thing in the room — it's where your own model of the system is forming. Push on any Part and we go deeper.*
