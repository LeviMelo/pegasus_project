# Handoff: artefact-aware replication (2026-10-05, ADR-0019)

## Goal
Make ADR-0015's tiers stop confirming coding regimes (evaluation 2026-10-05-replicated-claims-read.md: of 57 state national-trend claims
that replicated, 42 "artefacts", 13 unresolved, 1 substantive). Binding addition from the coordinator: every recording explanation carries an
EVIDENCE GRADE (tested / bound / consistent); only a tested one downgrades a claim; bound and consistent stay attached. ADR-0019 (amends
ADR-0015), DECISIONS row, ARCHITECTURE 8.3, evaluation entry + EVALUATION row, check_docs green, commit own paths only, never push,
message ends "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>". Reserve (SIM.DO 2024) untouched (strata read 2010-2023).

## Built (code)
- `scans/explain.py`: `TESTED/BOUND/CONSISTENT`, `Triage.grade/bound` on every triage rule (graded; only tested -> status "explained");
  series tests `glm_poisson`, `loglinear`, `slope_p`, `shape_test` (step vs best of linear/quadratic, STEP_DELTA 6 calibrated), `exchange`
  (rest of a pool moves opposite: a BOUND), `profile_test` (displaced deaths vs node / pool profile in sex x age x place x mechanism: TESTED).
- `replication.py`: `Strata` (direct standardisation, cells), `jurisdiction` (state: other states, binomial; region: halves of states + leave-one-state-out;
  municipality: state remainder), `audit` (national rate, all-cause column, conservation pools, shape, jurisdiction, verdict), `simulate_shape/_exchange/_profile`.
  Removed: spatial_split, test_spatial, test_trend_unit, simulate_spatial (superseded by jurisdiction).
- `tools.py`: `Session.strata`, `Session.spatial_confirm` (now audit), `kinds_of` (national failure confirms nothing), triage status only on tested,
  corroborate eligibility = not tested-explained.
- Scripts: `data/artefact_replication.py` (57 claims -> data/artefact_replication/audit.json), `data/artefact_replication_sim.py` (-> sim.json, done).

## State
- Sim done (sim.json): step false-call on gradual <= 5% at delta 6; transfer false <= 1.3%; profile test ~95% power/size on Dirichlet profiles.
- Audit of the 57: queued under heavy (free RAM was 1.5 GB; heavy waits for 4 GB). Log data/artefact_replication/run.log.
- TODO: read audit.json against the old classes (final.pkl cls), write evaluation entry, ADR-0019, DECISIONS/EVALUATION rows, ARCHITECTURE 8.3,
  ADR-0015 pointer, check_docs, commit.

## Update (end of run)
- Audit of the 57 done (audit.json, table.csv): not_replicated 13, explained 5, rescoped 2, open 15, survives 22 (Y35 GO survives). Evaluation entry
  docs/evaluation/2026-10-05-artefact-aware-replication.md, ADR-0019, DECISIONS/EVALUATION rows, ARCHITECTURE 8.3, ADR-0015 pointer written.
- Re-scope rule (coordinator): `conserved_level` lifts a claim to node + pool and re-tests; only unit claims lifted automatically.
- check_docs: only "ADR numbers not contiguous" (ADR-0017 absent, another agent's) remains.
- PENDING: planted-truth run (`data/artefact_replication_planted.py`, queued under heavy as "artefact-planted", log planted.log, output planted.json);
  when it finishes read planted.json (real trend must not be `explained`; transfer must raise a bound) and add 2 lines to the evaluation entry.
- NOT built: facility residual re-test; family-level scan of cell-level substitution/system leads.
