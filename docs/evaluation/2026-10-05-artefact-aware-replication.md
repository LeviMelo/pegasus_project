# Artefact-aware replication: the 57 claims re-run, and the tests on negative-binomial worlds (2026-10-05)

**Regime:** ADR-0019; code of the commit of this entry (`replication.audit`, `jurisdiction`, `conserved_level`, `explain.shape_test/exchange/partners/profile_test`). Claims: the 57 R2 state claims of `2026-10-05-replicated-claims-read.md` (register `pegasus_home/leads_T2019`). Events SIM.DO 2010-2023 by 4-character code, sex, age (never 2024), person-years POPSVS. Scripts: `data/artefact_replication.py` (-> `data/artefact_replication/audit.json`), `data/artefact_replication_table.py` (-> `table.csv`), `data/artefact_replication_sim.py` (-> `sim.json`, `sim.log`), `data/artefact_replication_planted.py`.

## The 57 claims through the audit

Verdicts (`replication.audit`; only a *tested* explanation can take a claim out, and it is then **re-scoped** to the level where the total is conserved, dropped only if nothing remains there):

| verdict | claims | what it is |
|---|---|---|
| not_replicated | 13 | the slope against the year's observed national rate fails to reach the minimum divergence with half its size |
| explained | 5 | a tested explanation (the displaced deaths profile as the node's, not the pool's) accounts for at least half and nothing stands at the conserved level: I10 ES, I67 TO, I67 SC, I67 RS, V49 MA |
| rescoped | 2 | tested explanation at the code level, a conserved level stands: I64 ES (node + R00-R99, b -0.17, x0.58 over the period, multi-state) and R00-R09 GO (R group, b -0.32, x0.36) |
| open | 15 | bound or consistent explanations remain attached (R-chapter subject, bounds not tested by a profile) |
| survives | 22 | no explanation raised, or all excluded by a test; includes Y35 and Y35-Y36 GO (R00-R99 and undetermined intent both excluded by the profile test: the displaced deaths are not node-like) |

Against the old reading's classes (42 A, 13 U, 2 S): of the 42 "A", 13 fail the observed national rate, 4 are explained (tested), 1 is re-scoped, 12 stay open and 11 survive; the 2 S survive; of the 13 U, 1 is explained (I67 SC), 3 are open and 9 survive. So 17 of 42 are removed or re-scoped by a test or by the observed national rate, and **25 of the 42 remain alive with their explanation attached only as a bound or a consistency**: the aggregates cannot exclude them, which is the coordinator's correction made operational. The São Paulo X95 "60% moved to undetermined intent" is not even a bound here: the undetermined-intent pool does not move against the node by half at 3 standard errors (`survives`).

Scope: 29 claims hold in other states (re-scoped to the nation or a group of states, `multi-state`), 28 are one jurisdiction's and get no spatial confirmation. Shape: 1 step (W78 SC), 26 gradual, 30 indeterminate; the old "step" claims (I67 TO and RS, Y40-Y84 and Y83 CE) are not called steps (a log-quadratic course fits them). The unit's all-cause slope is in every record (`all_cause`, -0.027 to +0.046); its share of the claim is under 0.5 for all 57.

**Re-scoped family-level claims.** Each claim whose pool moved (and was not excluded by a test) was lifted to node + pool and re-tested (`conserved_level`, in `table.csv`). Two stand with their code-level shift reported beside them (I64 ES, R00-R09 GO), and both are dominated by the R group's own fall (node share of deaths 0.75 and 0.12): they are statements about certification, not about stroke epidemiology. The ICD-block lifts (stroke I60-I69, hypertension I10-I15, other-cerebrovascular families of the five "explained" claims) are flat (|b| at most 0.03, p above 0.9): no family-level divergence is hidden behind those five. Lifts of claims that fail the national rate (I63 PR, W18 RN) are in the table and not counted.

## The tests on worlds (`sim.json`)

- **Shape** (delta 6): called a step on gradual courses (null, linear, accelerating; level 30-2000, NB size 10-50, effect 0.1-0.6) in 0 to 4.8% of series (mostly under 2%); power for a one-year step of x1.8 (effect 0.3) 0.62-0.85 at size 50 (0.19-0.22 at size 10), for x6.5 (effect 0.6) 0.66-0.99.
- **Conservation** (`pool_exchange`, 3 / 10 / 60 codes, node level 30-1000): a real gradual rise among stable codes raises a bound in 0 to 21% of worlds (about 5% at level 200 or more; high at level 30 where counts are noise); a transfer is found with probability 0.95 or more at level 1000 and effect 0.3, 0.6-0.8 at level 200, at most 0.35 at effect 0.1 or level 30 (a transfer larger than its partners' level is not simulable). A false bound is harmless to the verdict: it downgrades only if the profile test then says *supports*.
- **Profile test** (12-200 cells, 50-5000 displaced deaths, Dirichlet profiles of concentration 0.5-50): recoded deaths are called *supports* in 0.93-0.98 (0.82 at 200 deaths with near-identical profiles); independent changes are never called *supports* (*excluded* 0.92-0.96, *open* 0.03-0.13). Real profiles are less distinct (stroke subtypes differ little in sex and age): the grade then stays *bound*.
- **Planted real trend on the real strata** (`artefact_replication_planted.py`: a x3.5 gradual rise in K80 MG, N20 SP, L89 PR, M54 CE, and the same gain taken from the block): queued under the heavy queue; the result, if it finished, is `data/artefact_replication/planted.json`. Not claimed here.

## Limits

Thresholds (`STEP_DELTA` 6, `EXCHANGE_SHARE` 0.5, `EXCHANGE_Z` 3, `PROFILE_MIN` 20) come from the worlds, not from the 57 labels. One change followed a first run on the 57: whole-pool conservation with a lack-of-fit dispersion missed an obvious exchange (I63/I64 ES) and was replaced by the second-difference dispersion plus partner codes before the table above. The facility class is graded in triage (tested) but its residual is not re-tested by this build; cell-level leads classed substitution or system are not lifted automatically, only unit claims are (`Session.spatial_confirm`). Direct standardisation uses the nation, which contains the unit.
