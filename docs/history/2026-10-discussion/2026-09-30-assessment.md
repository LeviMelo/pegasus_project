# PegaSUS: an assessment, for the redesign discussion

**2026-09-30.** Written after reading:
- the April plan;
- the July north star and finding ontology;
- brepi's operating discipline;
- the agent surveys of both repositories;
- the extractions of the two math critiques.

It argues positions so they can be argued with. It decides nothing (see
`OPEN_QUESTIONS.md`).

**Corrected the same day** after the full recollection (`docs/RECOLLECTION.md`,
rewritten), which covers the May formalisation, MSD-I/II/III and the
Conceptual Foundations that this assessment had not read. Four statements
below were wrong or incomplete. Each is marked **[corrected]** where it
stands, and §11 adds what the fuller record changes.

---

## 1. The short verdict

The earlier attempts failed for one root reason, which showed up in several
forms. **PegaSUS tried to build the answer before it had defined the question
or a way to know whether an answer was right.**
- **April** defined a search space.
- **May** formalised it: a typed measure algebra (Problem 1), a nonlinear
  dependence scanner (Problem 2) and reconstruction under data sovereignty
  (Problem 3).
- **June–July** specified it in three Master System Documents, built it, and
  then spent the last weeks discovering, through thirty self-critiques, that
  it could not tell a finding from an artefact.
- **The north star** is a lucid document, but it arrived on the last day. It
  correctly retreated from "find links" to "reveal leads", and it named the
  identification wall.
- **[corrected]** A way to know whether an answer was right *had* been
  specified: MSD-III Part IX's validation battery and the Zika → microcephaly
  acceptance test (§XI.4). Its synthetic half was partly built. It was never
  run on real data, so the question was defined and left unanswered.

Meanwhile the work that produced value went the other way round: question
first, data second, discipline throughout. That covers brepi's leptospirosis
paper (in review), the GLP-1 manuscript, and today's three SIAC abstracts.
**The attempts' own record says that value came from studies, not from the
engine.**

That is not an argument against the ambition. It argues about its **order**,
and about what the engine is **for**.

---

## 2. What "reduce epidemiology to a statistical problem" can mean

The ambition deserves a precise statement, because its vagueness is what
halted it.

### 2.1 The object

The data are random fields. A variable `Y_v(s, t, g)` is indexed by place
`s`, time `t` and stratum `g` (age, sex, race, code class). Behind the fields
are individual records, and pegasus_data now also gives linked trajectories.

An epidemiological statement is a claim about a **functional of the
distribution that generated them**:
- a rate;
- a contrast of rates between groups;
- a trend;
- a departure from spatial homogeneity;
- a conditional association.

### 2.2 Three kinds of statement, with different fates

| kind | example | can a machine produce it from the data alone? |
|---|---|---|
| **Descriptive**: a functional of the observed distribution | "maternal cardiovascular deaths were 12.0% of maternal deaths, 2014–2023" | **Yes**, given correct definitions, denominators and data-quality handling. This is most of epidemiology's published output, and it is fully automatable. |
| **Associational**: a conditional contrast | "recorded heart disease is associated with 15× the ICU rate, adjusted for age, HDP, twins, region" | **Yes as computation, no as meaning.** The number is identified; what it means depends on a chosen adjustment set, and choosing it takes assumptions. |
| **Causal**: an intervention contrast | "treating X reduces Y by Z" | **No.** Identification rests on assumptions the data cannot verify (the north star's wall, correctly stated). |

"Reducing epidemiology to statistics" is therefore **true for the descriptive
layer, true as computation for the associational layer, and false for the
causal layer**. The earlier engine's discovery half lived in the second row and
kept being pulled toward the third. The fuller record shows its own documents
resisted that pull: "a causal clue, not a causal theorem" (GPT, May), the
causal ladder with typed rungs (MSD-III Part IV), and "association is not
causation" as a permanent limit (MSD-III §0.4).

**[corrected]** I first wrote that the engine neglected the descriptive layer.
It did not, by design. The canonical core generated standard stratified
indicators always and exempted them from pruning. miniPegaSUS made the variable
DAG itself "the central analytic engine": rates, standardised rates, burden
measures, inequality decompositions and anomaly reports, with the state tensor
read as a result in its own right. What went wrong was execution, not intent:
direct standardisation at municipal scale without shrinkage, age-unknown deaths
filed as infants, and rate intervals computed and never propagated.

### 2.3 What an "ecological link" is

Under this framing, a link is not an edge in a graph. **A link is an
estimand, a null, a grain and a verdict:**
- **Estimand:** a functional contrasting an outcome functional across levels
  of an exposure or context functional, e.g. the rate of Y in places or strata
  where X is high against where it is low; the lag-k co-movement of X and Y;
  the co-location of two clusters.
- **Null:** what the functional would be if nothing were there, e.g.
  independence, spatial randomness, a stationary baseline, proportionality to
  population.
- **Grain:** record, linked cohort or area-time cell. The ecological fallacy
  is the statement that the same estimand differs across grains.
- **Verdict:** how far the observed value is from the null, how precisely it
  is known, and how fragile that is to the known failure modes (confounding by
  size, mechanical overlap, recording artefacts, multiplicity).

July's finding ontology (WHERE, WHEN, WHO, HOW IT MOVES, WHAT CO-OCCURS,
CONTEXT) is best read as **a catalogue of estimand shapes**, not as a set of
scanners to run over everything. Each shape is a question template:
- "does Y cluster, and where?";
- "did Y change, and when?";
- "which stratum carries Y beyond its population share?";
- "do X and Y co-locate?";
- "does the X–Y relation vary with Z?".

The difference matters. A scanner runs every template on every variable and
must then control an astronomical multiplicity. A question template is
instantiated for a reason, and the reason carries the prior plausibility that
multiplicity control otherwise has to supply.

### 2.4 Why the "discover everything" engine struggled, in statistical terms

1. **The hypothesis space is combinatorial,** and every stage multiplies it:
   variables × strata × codes × lags × places × lenses. April saw this and
   proposed a search objective `J(A)` with eight weighted terms. The weights
   are arbitrary. Worse, **adaptive descent (go deeper where signal appears)
   invalidates the p-values of what it finds**; this is selective inference,
   and the plan named hierarchical FDR only for code trees.
2. **The strongest signals in administrative data are artefacts:** population
   size, shared denominators, nested definitions, recording practice. The July
   deconfounding work found exactly this. The top-scoring links were
   mechanical, and the clique was a sampling degeneracy. Today's SIAC work
   found the same thing in miniature: the "hub" hospitals for maternal heart
   disease may just be the hospitals that record secondary diagnoses. An
   engine ranking by signal strength ranks artefacts first.
3. **Ground truth was designed but never used on real data.**
   **[corrected]** I first wrote "no ground truth was ever used", which is
   wrong about the design.
   - **Specified.** MSD-III Part IX specified:
     - known-positive controls (Zika → microcephaly, sanitation → diarrhoeal
       disease, vaccination → decline);
     - known-negative controls with a measured false-alarm rate;
     - synthetic ground truth;
     - temporal holdout;
     - exact-versus-approximate checks.
     
     The program acceptance test (§XI.4) required a monthly Alagoas run to
     discover the arbovirus → microcephaly lag of 6–9 months unprompted.
   - **Built.** Synthetic planted-lag and sparse + low-rank recovery tests;
     the race planted-signal probe.
   - **Never done.** The real-data half. `tests/acceptance/` is empty and
     the issue ledger deferred the Zika test.
   
   So sensitivity and false discovery on real data were never measured, and
   the project calibrated itself largely by critique: 165 argued findings, of
   which the steelman adjudicated 20, a few by experiment. The candidate
   benchmark in §9 extends the battery MSD-III already wrote.
4. **The model families did not match the data.**
   - Counts are overdispersed and zero-inflated, and small areas are unstable.
   - The Gaussian copula with a Poisson margin, one global separable
     precision, iid permutation nulls and unweighted moments each broke on
     that data.
   - The critique's recommended remedies are the standard areal-data toolkit:
     negative-binomial margins, BYM2/INLA shrinkage, cross-fitting, proper
     stability selection.
5. **Uncertainty was computed and then ignored.** Reliability weights, n_eff,
   denominator fragility and standardised-rate intervals were all built and
   never consumed. This is an engineering failure with a statistical
   consequence: the system certified findings whose inputs it had itself
   flagged as unreliable.

None of this says discovery is impossible. It says discovery is a
**statistical procedure that must be validated like one**: on planted
signals, known results and negative controls, with its error rates measured
rather than argued.

---

## 3. The attempts, assessed one by one

### April PegaSUS: the theory

**Right:**
- **Typed observables.** A count, a rate, a proportion, a context value, an
  annotation and a latent-lifted estimate are different kinds of thing, with
  different aggregation laws.
- **The support algebra.** Extensive pushforward, exposure-weighted intensive
  aggregation, contextual clone and latent lift is a correct and useful
  formalisation. brepi independently re-derived it as its transfer algebra.
  Two independent derivations of the same algebra are good evidence it is
  real.
- **Code roles and code hierarchies as first-class objects.** A diagnosis
  that is a cause, a comorbidity, an anomaly or an annotation is not the same
  variable. Today's EPI-01 used "any of 11 diagnosis positions"; EPI-02
  separated underlying cause from the certificate lines. Both are code-role
  choices.
- **Naming the enemies.** Common-size effects, support-role artefacts and
  sparse-branch noise.

**Wrong:**
- **Discovery as a search objective.** The weights have no statistical
  meaning, and adaptive refinement breaks inference.
- **The municipality × year lattice as the analysis object.** It threw away
  the record grain from the start.
- **A "global graph engine" as the core.** Its own §22.2 conceded the scanner
  was "the bottleneck" and the conceptual layers were sounder.

### May–July PegaSUS: the engine

**Right:**
- **The data machinery was real.** It was later superseded by pegasus_data.
- **The finding ontology,** read as question shapes.
- **The north star's three levels,** the identification wall, grain as the
  main bias lever, and instrumentation (E-values, negative controls,
  collider refusal).
- **The recognition that a cascade of follow-up tests is a "false-story
  generator"** unless its error is controlled.
- **Several empirical lessons worth keeping:** the effect-size floor as the
  strongest lever, credibility non-monotone in effect size, provenance-aware
  pruning of mechanical links.

**Wrong:**
- **Everything the critiques found:** assumptions violated by count data,
  uncertainty not propagated, magic numbers, certification certifying the
  wrong thing, canonical code orphaned while copies ran.
- **More fundamentally, the order of work.** The engine was scaled
  nationally (memory walls, GPU plans on a CPU-only install) before any
  capability was shown on one state to find a *known real* signal and reject
  a real null. **[corrected]** Synthetic planted signals were recovered; the
  first version of this sentence said they were not. The engine was optimised
  before it was known to be right on real data. That is the same
  error pegasus_data's discipline now forbids: "correct but unusably slow is
  not finished", and equally, fast but unvalidated is not started.

### brepi: the workbench

**Right:**
- **The discipline:** argument chain, plausibility gate, threat ledger,
  thread-following, statistical grammar, one thesis and one moat. It is the
  single most valuable thing in the whole lineage, because it is what
  actually produced accepted science.
- **Claims checked against result files.**
- **The areal modelling engines:** BYM2/INLA, DLNM, DiD, ascertainment.
- **The non-DATASUS adapters** and their hard-won facts: COBRADE filing
  choices, PNSB against SINAN, pharmacy location against residence.

**Wrong:** no shared data layer, and no rule that a tool must be found before
it is rebuilt. Studies grew private copies of helpers. The discipline governed
arguments but not code.

### pegasus_data: the gateway

It is the part of the lineage that is finished in the sense that matters: it
is verified live, documented and trusted.

Two of its recent capabilities change what PegaSUS can be:
- **Record-level queries with meaning attached,** so the individual grain is
  available directly.
- **Record linkage with measured error.** Today: 1.5 million births linked to
  their delivery admissions at 0.5% chance links, and 545,135 in-hospital
  deaths linked to death certificates at 0.23%.

The linked-cohort grain, which the north star marked as speculative, exists.
EPI-01 used it this morning.

---

## 4. Five root causes, and what each implies

| root cause | evidence | what a redesign would need |
|---|---|---|
| **Purpose unsettled while building** | April "links"; July "leads"; now "links" again; the delivered value was studies | Settle what PegaSUS produces and for whom, before any architecture |
| **An external criterion specified, never run** | MSD-III Part IX and the Zika acceptance test written; synthetic half built; no real-data error rate ever measured; 165 argued findings instead | A benchmark of known answers (positive and negative) that every capability must pass, run live, before the capability is scaled or built upon |
| **Scale before correctness** | national OOMs and GPU plans before any single-state validation | State-scale validation first; national only once a capability is known to be right |
| **Aggregation mistaken for the object** | panel-first design; the north star's own correction | Grain chosen per question; records and links available (pegasus_data) |
| **Contracts unenforced** | reliability computed and ignored; canonical code orphaned; helpers duplicated across sessions | Estimators whose signatures require the uncertainty they need; one implementation per concept, found before written |

---

## 5. Possible conceptions of the restart

Three coherent shapes, with their costs. They are options for discussion, not
choices.

### A. A lead engine: discovery first

Question templates are instantiated systematically over the data and emit
leads with their grain and instrumentation. A person, or an agent, picks
leads to study.
- **For:** closest to the original wish; finds what nobody asked about.
- **Against:** multiplicity and artefacts dominate unless validated; the
  value of a lead is only known after someone studies it; hardest to show
  value early.

### B. A study engine: questions first

An agent receives a question, or proposes one, and conducts a study end to
end: definitions, data, descriptive core, one modelling contribution, threat
ledger, report with checked claims. It uses pegasus_data as its only data
access and brepi's discipline as its operating contract.
- **For:** produces value immediately; its outputs can be judged by the
  standards science already uses (reviewers, replication of published
  results); it is what actually worked.
- **Against:** it only finds what it is asked. The "ecological links" wish is
  served only through the agent's own question-generation.

### C. A loop: leads feed studies, studies calibrate leads

The lead engine proposes; the study engine tests; the verdicts are recorded
and become the benchmark that measures the lead engine's precision. Over
time, lenses that produce leads that survive study are trusted more.
- **For:** the only design in which discovery gets an empirical error rate.
  It turns the "false-story generator" risk into a measured quantity.
- **Against:** it needs both halves, and the second half has to exist first.

**My reading:** C is the natural end state, and B is the necessary first
step. B exercises the whole data path and the agent, and it produces what
today's work showed is valuable. It also builds the machinery that C needs to
calibrate A: study protocols, the ledgers and verdicts. A built first has
nothing to measure itself against, which is the history of May–July.

---

## 6. The statistical questions an agent loop reopens

The north star rejected LLM agents for the decision-making on one ground: a
fixed plan makes the number of tests countable, and error control needs that.
You want an agent loop, and the tension is real. There are principled ways
through it:

1. **Separate exploration from confirmation by data splitting.** The agent
   explores freely on one part of the data and must confirm on a part it has
   not seen. The splits that make sense here:
   - **temporal:** explore 2014–2019, confirm 2020–2023;
   - **spatial:** explore on half of the states;
   - **across systems:** a lead from SIH confirmed in SIM.
   
   Exploration then needs no multiplicity control at all, and confirmation
   needs control only over the claims actually carried forward. This is the
   cheapest honest design, and it fits the rich time axis DATASUS has.
2. **Online error control for sequential tests.** An agent's tests arrive as
   a stream, each chosen after seeing earlier results. Online FDR procedures
   are built for exactly that: alpha-investing, LORD and SAFFRON, or
   e-value-based procedures, which stay valid under arbitrary dependence and
   optional stopping. They make "every test logged and counted" a working
   error guarantee rather than a bookkeeping rule.
3. **Pre-registration inside the loop.** Before a confirmatory analysis, the
   agent writes its protocol (estimand, population, adjustment set with its
   reason, threats), and the protocol is frozen before the data are touched.
   This is brepi's scoping rule made mechanical.
4. **Empirical calibration with negative controls.** For each claim, the
   agent also runs outcomes or exposures that should show nothing. The spread
   of those null results calibrates the claim's interval against systematic
   bias, not only sampling error. The critique recommended this, and
   observational health-data research networks such as OHDSI do it routinely.
5. **Models that match the data by default.** For areal counts: negative
   binomial with a population offset, and BYM2 shrinkage for small areas. For
   records: robust Poisson or log-binomial for risks. Exact intervals for
   small counts. Dependence is modelled, not patched with an n_eff factor.
   This is the critique's list, and it is the standard toolkit.

---

## 7. The data gateway, now that it exists

pegasus_data is DATASUS-complete. Everything else the lineage used exists in
two or three half-versions:
- **SIDRA:** in the May–July PegaSUS and in brepi.
- **Population denominators:** IBGE series in pegasus_data, raking in brepi,
  a 146-million-cell tensor in PegaSUS.
- **Climate, disasters, ANS, REGIC, SNGPC:** brepi only.

Whatever PegaSUS becomes, it needs these through one gateway, each verified
live. The order should follow the questions: SIDRA and one population method
first, since every rate needs them.

---

## 8. Compute, honestly

Question-first work is cheap. Today's three studies ran on this laptop in
minutes to an hour, beside a national linkage job using 17 GB. What exhausted
32 GB before was scanning everything: dense p×n² kernels and ~19,000
eigendecompositions.

A design that computes what a question needs, at the grain it needs, fits
this machine. National BYM2 over 5,570 municipalities is a routine INLA fit.
The GPU is not needed for any of it.

---

## 9. What I would propose to settle first, in this order

1. **What PegaSUS produces** (A, B, C or another shape), and for whom.
2. **The benchmark:** a list of known answers PegaSUS must reproduce, and
   negative controls it must not "find". This is the correctness criterion
   the lineage never had. Candidates:
   - the Zika microcephaly signal;
   - COVID excess deaths;
   - the leptospirosis case-fatality gradient (brepi);
   - published Brazilian maternal-mortality figures (as matched in EPI-02
     today);
   - the SIH–SINASC linkage results;
   - and placebos.
3. **The agent's contract:** its tools, its ledgers, when it may claim, and
   how exploration and confirmation are separated.
4. **Only then,** the architecture that serves those three.

---

## 10. Questions for you

1. When you imagine PegaSUS working, what is on your screen: a report
   answering a question you asked, a ranked list of things you did not know to
   ask, or a map of links?
2. Do you accept that an engine's claims should be scored against known
   answers before they are trusted, even if that slows the first year?
3. Are you comfortable with the agent working under data splitting (exploring
   on some years, confirming on others), which limits how much of the data any
   single claim can use?
4. PHAROS: what from its agent design should carry over, and what proved too
   heavy?

---

## 11. What the full record changes (added after the recollection)

1. **The three problems remain the right decomposition, and they fared very
   differently.**
   - **Problem 1 (what the quantities are) is the solid part.** Typed
     measures, Radon–Nikodym rates with legality, the canonical core and the
     measured-quantity output survived every critique. The compliance report
     rated the legality predicate compliant, and brepi re-derived the same
     algebra independently.
   - **Problem 3 (reconstruction under sovereignty) is sound doctrine.** It
     comprises the regime classifier, a process model for population, and
     only stocks, denominators and outcomes made dynamic, with staleness as
     uncertainty. It is mostly a *gateway* concern: denominators and SIDRA
     belong behind pegasus_data, typed by regime.
   - **Problem 2 (finding relations) is where every attempt broke,** in three
     successive forms: the pairwise HSIC scanner, the NB GLM with a residual
     scan, and the joint sparse + low-rank precision. Each broke on the same
     properties of the data, not on its choice of dependence measure:
     overdispersed, zero-inflated counts; small unstable areas; dependence in
     space and time; a 25-year non-stationary window; and multiplicity. The
     critique's remedies are the standard areal-data toolkit.
2. **The recurring mathematical error was a single global object.** One
   national rate for every cell, one covariance pooled over 2000–2024, one
   separable precision for all of Brazil, one frozen randomised PIT. Brazilian
   health data are heterogeneous by region, period and scale, and the areal
   toolkit (negative binomial with varying baselines, BYM2 shrinkage toward a
   parent) exists precisely for that. This is a statistical diagnosis, not an
   engineering one.
3. **The information ceiling (Conceptual Foundations §10; MSD-III §0.4) is the
   corpus's most consequential sentence for the redesign.** If reliably
   discoverable epidemiology is bounded by effective independent
   observations, the discoverable set at fine grain is small. A design should
   be sized to the information, not to the compute. Much of the May–July
   effort (Kronecker operators, randomised NLA, the GPU) went into searching
   more candidates than the data could support.
4. **The shape the author already wrote down is option C.** MSD-III's
   "living skeleton" with five verbs (interrogate, lens, escalate, steer,
   inject) is a build/serve split: the skeleton is the lead engine, and the
   escalation layer is where studies happen. An agent loop is a natural
   occupant of the serve side. What the record adds is the missing step: the
   skeleton was never scored against known answers before being served.
5. **The grain has moved since July.** The whole lineage was panel-first; the
   record-level functionals and bridges were specified but secondary.
   pegasus_data now gives records and linked cohorts with measured linkage
   error. Some "ecological links" can therefore be asked at the individual
   grain, where the ecological fallacy does not arise, and Problem 2's object
   is no longer only a municipality × time panel.
6. **Unchanged:** the order argued in §5 and §9. Settle what PegaSUS produces;
   then the benchmark, which extends MSD-III Part IX, run on real data first;
   then the agent contract; only then the architecture.
