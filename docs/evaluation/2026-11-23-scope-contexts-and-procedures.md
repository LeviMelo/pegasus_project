# Scope: context candidates decided, procedure seeds (2026-11-23)

**Why.** Ten ABNc studies, written as scripts beside the scope, used almost none of the context pegasus_data holds and
missed length of stay in every cohort; four of them are defined by a SIGTAP procedure, which no seed could name. The
scope now lists every context candidate (pegasus_data `context_candidates`: each SIDRA research and subject with tables
at the municipality in the study's years, each intake source placed by municipality or state) with the declaration's
decision on it (`contexts_considered: {id: {decision: include|exclude, why}}`); the full tables and columns are written
beside it (`NAME.candidates.yml`); `study.body` counts an undecided candidate as a missing part ("contexts considered").
`topic.seeds.sigtap` (and `study new --sigtap`) names procedures at any level of the tree; they go through the existing
procedure path (`_concept_items`: SIGTAP's instruments against each column's, one field per chapter).

**Regime.** Branch `scope-v2` after 29d42e2, pegasus_data 85673778, the one data home, survey depth, 2026-11-23.

| study | read | deferred | not read (each with why) | candidates |
|---|---|---|---|---|
| spina bifida, Q05, Brazil 2015-2023 | 10: SINASC's CODANOMAL (6,658 births), SIH 9,490 AIHs / 7,761 stays, CIHA 1,134, SIM 789 deaths and 118 foetal, SIA AD and SAD | 7 (ANS TISS, SIA PA, SIH-SP, ...) | 18 | 130 undecided |
| neurosurgery, SIGTAP 0403 (132 procedures), Alagoas 2022-2023 | SIH 1,735 AIHs / 1,548 stays, CIHA 472, SIH-SP | 8 (SIA PA, BI, SAD, APAC AM, AN, AB) | 8 APAC and BPA datasets holding none | 80 undecided |

An invalid seed (`sigtap: 99`) is listed in `not_read` with why; a decision without a reason fails `study check`.

**Open.** SIM-DOFET appears both read (118, primary classifier) and in `not_read` ("records hold none"): two readers,
to reconcile. A scope's first record counts for SIH chain every national year's AIHs into stays (minutes, cached).
The window does not render `contexts_considered` yet (a form kind of its own).
