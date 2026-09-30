# Open questions for the redesign

Nothing below is decided. Each question lists what the earlier attempts
offer (`docs/RECOLLECTION.md`) as material, not as an answer.

| # | question | material |
|---|---|---|
| Q1 | **What does PegaSUS produce?** Links (the April and current framing), leads for a human (July), finished studies (what actually got delivered), or a path from lead to study? | RECOLLECTION §2, §6 |
| Q2 | **What is an "ecological link", precisely?** Which structures count: dependence, co-location, lead-lag, concentration, change, effect modification, exposure-response? Against which null? At which grain? | the finding ontology's taxonomy (§4); the north star's three levels and identification wall (§3.1) |
| Q3 | **Where does the machine stop and the scientist start?** Level 1 (dependence) only, Level 2 as triage, or more? | north star §2, §8 |
| Q4 | **The agent loop.** Its tools, its state (journal, ledgers), its stopping rule, what it may claim, and how its work is checked. Single-threaded, per the author. What of the `epi-db-research` discipline becomes enforced rather than advisory? | brepi skill; PHAROS (the author's agent project) |
| Q5 | **Multiplicity under an agent.** An agent that explores is a garden of forking paths. Is every test logged and counted? Is a plan pre-registered before confirmatory claims? Is exploratory work labelled? | north star §6 (gatekeeping) |
| Q6 | **Grain.** Records, linked cohorts, panels: which questions go to which grain, and how is that declared? pegasus_data now serves records and links. | north star §4; pegasus_data `query`, `link` |
| Q7 | **The boundary with pegasus_data.** Is it the single data gateway for every source (SIDRA, climate, disasters, ANS, REGIC, SNGPC)? Where do denominators live, and by which method (IBGE series, raking, a population tensor)? | RECOLLECTION §7 |
| Q8 | **Statistical engines.** Python only, or R (INLA, DLNM) where it is better? How are fits budgeted in time and memory on this machine (32 GB RAM, 6 GB laptop GPU)? | brepi `R/`, `09_exec.R`; the compute critiques |
| Q9 | **Which structures first,** and what proves they work: a planted-signal benchmark, reproducing a published result, or a study a reviewer accepts? | the six built lenses; brepi's studies |
| Q10 | **What evidence counts as "done"** for a lead and for a study? | brepi definition of done; north star instrumentation |
| Q11 | **How are results checked against their files** (claims ↔ numbers)? | brepi claim ledger and result assertions |
| Q12 | **brepi's future.** It stays as is while the leptospirosis paper is in review. What happens to its adapters and engines afterwards? | brepi survey |
| Q13 | **The math critiques, digested.** Both are extracted by read-only agents: `docs/digests/math_critique_extraction.md` (the 387 KB critique, pure extraction) and `docs/digests/math_critique_steelman_extraction.md` (165 finding IDs, 20 with full verdicts). The critique's recurring pattern: uncertainty and reliability were computed but never consumed by the estimators; count data's overdispersion, zeros and autocorrelation broke the assumed models; thresholds were magic numbers. Read both before the design discussion reaches statistics. | the two digests |
