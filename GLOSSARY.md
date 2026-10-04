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
| **tier (B0, B1, B2, B2s)** | a nested version of the monolith declaring what is boring: composition; plus region; plus own course; plus season | §6.1 |
| **surprise** | (y, μ, z, w, flags) for a cell: observed, expected, z = Φ⁻¹(randomised PIT), information weight | §6.3 |
| **information weight** | w = μ / (1 + μ/φ), the Fisher information about log μ a cell carries | §6.3 |
| **lens** | a scan of one field (cluster, outbreak, disparity, trend, observation) | §7.1 |
| **subset scan** | the search for the subset of cells, across dimensions, whose combined surprise is largest | §7.2 |
| **pattern** | a low-rank component of departures shared by places, times and fields | §7.4 |
| **estimand (E_b, E_b\|Z, E_w, E_i)** | the declared question of a pair test: between places, adjusted, within places over time, between institutions | §7.5 |
| **minimum effect δ** | the effect below which a relation is not a lead; calibrated on negative controls | §8.4 |
| **family** | the unit of FDR control: lens or estimand × tier × field families × support | §8.1 |
| **ledger** | the append-only record of every test, written before it runs | §9.2 |
| **replication tier (R0–R3)** | all data; the other temporal half; the other spatial half; another system | §8.3 |
| **confirmation reserve** | the spatial half agents cannot explore; claims are confirmed on it once | §8.3, §9.3 |
| **lead** | a test result admitted by error control, with replication, robustness and provenance | §9.1 |
| **harness** | known positives, known negatives, planted signals and null surrogates on real data: the gate of every lens | §10 |
| **gateway** | the one module that imports pegasus_data | §2, §11.1 |
| **modelled tier** | pegasus_data's estimated products (population account, completeness, race misclassification), typed and versioned | §2 |
