# GLOSSARY.md

Terms as PegaSUS uses them. The definitions are in ARCHITECTURE; this is the short form.

| term | meaning | ARCHITECTURE |
|---|---|---|
| **marked point process** | the object the data observe: events at places and times, to persons, each carrying attributes (marks) | §1 |
| **monolith** | the one hierarchical model of event intensities and marks for all of Brazil: "normal Brazil" | §4 |
| **event type** | what a record counts as (death, hospitalisation episode, confirmed case…), declared in pegasus_data with its classifiers, status and consolidation | §3.1 |
| **classifier** | a code column that partitions events (underlying cause, principal diagnosis, procedure); primary or alternative | §3.1 |
| **field** | a projection of events onto a lattice: counts of an event type, or summaries of a mark | §3.2 |
| **cell** | one place × time × group of a lattice | §3.2 |
| **population tensor** | person-years by place × year × age × sex (× race), from pegasus_data; the offset of every count | §3.2, §4.1 |
| **block** | a subtree of a classifier structure fitted together (an ICD chapter) | §3.2, §5.4 |
| **profile node** | the ancestor at which an age–sex profile is estimated | §4.2 |
| **structure / shape** | how a variable's values relate: tree, list, ordinal, cyclic, graph; it fixes the prior of effects along it | §4.3 |
| **proximity graph** | a weighted graph over places (contiguity by border length, distance, care flows, REGIC…), served by pegasus_data | §4.3 |
| **BYM2** | the spatial prior: a scaled ICAR part plus an iid part, mixed by a learned ρ | §4.3 |
| **tier (B0, B1, B2, B2s)** | a nested version of the monolith declaring what is boring: composition; plus region; plus own course; plus season. Since revision 3 a tier is a stage-C **reference** a departure is measured against, not part of the expectation | §6.1 |
| **surprise** | (y, μ, z, w, flags) for a cell: observed, expected, z = Φ⁻¹(randomised PIT), information weight | §6.3 |
| **information weight** | w = μ / (1 + μ/φ), the Fisher information about log μ a cell carries | §6.3 |
| **lens** | a scan of one field (cluster, outbreak, disparity, trend, observation); since revision 3 a screen only, its claims replaced by departure models | §7.1 |
| **subset scan** | the search for the subset of cells, across dimensions, whose combined surprise is largest | §7.2 |
| **pattern** | a low-rank component of departures shared by places, times and fields | §7.4 |
| **estimand (E_b, E_b\|Z, E_w, E_i)** | the declared question of a pair test: between places, adjusted, within places over time, between institutions | §7.5 |
| **minimum effect δ** | the effect below which a relation is not a lead; calibrated on negative controls | §8.4 |
| **family** | the unit of FDR control: lens or estimand × tier × field families × support | §8.1 |
| **ledger** | the append-only record of every test, written before it runs | §9.2 |
| **replication tier (R0–R3)** | all data; the other temporal half; the other spatial half; another system | §8.3 |
| **confirmation reserve** | the spatial half agents cannot explore; claims are confirmed on it once | §8.3, §9.3 |
| **lead** | a test result admitted by error control, with replication, robustness and provenance | §9.1 |
| **harness** | known positives, known negatives, planted signals and null surrogates on real data. The gate was retired (ADR-0028); since revision 3 the statistical part is the **bench** and documented events belong to stage E | §10 |
| **gateway** | the one module that imports pegasus_data | §2, §11.1 |
| **modelled tier** | pegasus_data's estimated products (population account, completeness, race misclassification), typed and versioned | §2 |
| **maturity** | v0 a first version that runs; v1 the field's established method for the estimand; v2 v1 measured against its alternatives on this data | §1, §13.1 |
| **block-arrowhead Hessian** | the shape of a block's Hessian: diagonal in the leaf-place effects, block-diagonal by place plus the graph's sparsity, dense only in the few hundred globals; what the v1 solver factors exactly | §5.3 |
| **LAML** | the Laplace approximate marginal likelihood of the strengths τ; maximised in log τ, its root is Fellner–Schall's fixed point | §5.4 |
| **selected inversion** | the entries of H⁻¹ on the factor's sparsity pattern (Takahashi recursions): exact marginal variances and the traces LAML needs | §5.4–5.5 |
| **departure model** | a field's model with the monolith's expectation as offset and an estimand-specific departure term δ; a lead is a posterior statement about δ | §7.0 |
| **screen** | a cheap search (a lens, a subset scan, a pair correlation) that proposes supports or pairs for a model to read | §7.0, §7.5 |
| **distributed-lag term** | an exposure's lagged values in an outcome's rate with a smooth coefficient over lag: the lag–response curve as an estimate | §7.5 |
| **shared-component model** | two outcomes' place effects with a common spatial component; its share of each field's variance is the relation | §7.5 |
| **IHW** | independent hypothesis weighting: hypotheses weighted by a covariate of their power, FDR kept; replaces exclusion by power | §8.4 |
| **conserved level** | the pool a coding change exchanges deaths with: the ICD family, R00–R99 and undetermined intent; every lead is read there too | §8.6 |
| **stage** | one of PegaSUS's six computations: A data, B expectation, C departures, D relations, E interpretation, F use; every object belongs to one (P16) | §1.1 |
| **statistical vs epidemiological validity** | whether a method's stated certainty holds (stages B–D) against whether a lead is a real event (stage E) | §1.1, §10 |
| **noise structure** | the expectation's description of how counts vary beyond their mean: dispersion, and the dependence of a place's deviations across periods (N1) | §6.1, §12 |
| **reference** | what a departure is measured against (Brazil, the region, the place's own past), declared per estimand; the tiers' role since revision 3 | §6.1, §7.0 |
| **departure model** | a departure term of a declared shape (cell excess, step, trend, cluster, group interaction) added to the model and read through its posterior; the stage-C inference | §7.0 |
| **joint relation model** | stage D: all fields' departures modelled together through shared latent space–time factors and sparse lagged dependence; pairwise lag tests only confirm | §7.5 |
| **the bench** | the statistical characterisation of stages B–D: the grid of planted signals in refitted worlds, null worlds, negatives, SBC | §10 |
| **absorption** | the share of a departure a refit takes into the expectation (9–63 % by locus); why departures are model terms and leads are sized held out | §10.3 |
