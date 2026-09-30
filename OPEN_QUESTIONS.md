# Open questions for the redesign

Nothing below is decided. Each question lists what the earlier attempts
offer (`docs/RECOLLECTION.md`, section numbers "R§") as material, not as an
answer.

| # | question | material |
|---|---|---|
| Q1 | **What does PegaSUS produce?** Links (April, May and now), a living associational skeleton served to humans and agents (MSD-III), leads (north star), finished studies (what got delivered), or a path from lead to study? | R§2, R§3, R§4.14, R§9; assessment §5, §11.4 |
| Q2 | **What is an "ecological link", precisely?** The LinkRecord's edge types, the finding ontology's shapes, or an estimand + null + grain + verdict? | R§4.10, R§4.15; assessment §2.3 |
| Q3 | **Where does the machine stop and the scientist start?** The causal ladder's rungs; the north star's three levels. | R§4.11, R§4.15 |
| Q4 | **The agent loop.** Its tools, its state (journal, ledgers), its stopping rule, what it may claim, how its work is checked. Single-threaded, per the author. What of `epi-db-research` becomes enforced rather than advisory? | R§8.1; PHAROS |
| Q5 | **Multiplicity under an agent.** Every test logged and counted? Data splitting, online FDR, pre-registered confirmation? | R§4.15; assessment §6 |
| Q6 | **Grain.** Records, linked cohorts, panels: which question goes to which grain, and how is that declared? | R§4.15, R§8.2; assessment §11.5 |
| Q7 | **The boundary with pegasus_data.** Is it the single gateway for every source (SIDRA, climate, disasters, ANS, REGIC, SNGPC)? Does Problem 3 (regimes, sovereignty, the population process model) live there? Which population method? | R§4.4–4.6, R§8 |
| Q8 | **Statistical engines.** Python only, or R (INLA, DLNM) where it is better? Fit budgets on this machine (32 GB RAM, 6 GB laptop GPU)? | R§4.12; brepi `R/` |
| Q9 | **The benchmark.** MSD-III Part IX specified known positives, known negatives, synthetic truth and holdout; only the synthetic half was built. Which known answers, run live on real data, must a capability pass before anything is built on it? | R§5; assessment §9 |
| Q10 | **What evidence counts as "done"** for a lead and for a study? | brepi definition of done; R§4.15 |
| Q11 | **How are results checked against their files** (claims ↔ numbers)? | brepi claim ledger and result assertions |
| Q12 | **brepi's future.** It stays as is while the leptospirosis paper is in review. What happens to its adapters and engines afterwards? | R§8.1 |
| Q13 | **Problem 2's statistical foundation.** Every form broke on the same data properties (overdispersion, zeros, small areas, dependence in space and time, non-stationarity, multiplicity) and on single global objects. What model family is the default: NB with varying baselines and BYM2 shrinkage, as the critique recommends? How is heterogeneity across regions and periods represented rather than pooled away? | R§4.9–4.10, R§6.2; assessment §11.1–11.2; the two critique digests (read) |
| Q14 | **Is the Problem 1 / 2 / 3 decomposition kept?** It is the author's own and the most durable idea in the corpus. Keeping the decomposition is not keeping the code. | R§4.2, R§4.4, R§4.9; assessment §11.1 |
| Q15 | **Sizing to information.** If the discoverable set is bounded by effective observations (the information ceiling), how is the search sized to it, and is exhaustiveness still a goal? | R§4.13, R§4.14; assessment §11.3 |
