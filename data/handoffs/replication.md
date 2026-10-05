# Handoff: redesign of replication (2026-10-05)

## Goal
ARCHITECTURE 8.3 replication that means something: honest sample splitting (select on A, test on B, fit without B), corroboration
for one-off events (S2iD / SINAN / SIH, own null, overlap per 8.5), the confirmation reserve under LOND, re-tier the 7,496 SIM leads,
report tiers and the 15 top signals; ADR + evaluation entry + EVALUATION row; check_docs; commit own paths only (never monolith.py,
surprise.py, harness registry). Message ends "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>". Never push.

## Design (settled in code, uncommitted)
- control.py: SIDES A .5 / B .3 / R .2, event_sides (multinomial thinning per cell row), Reserve (LOND state read from the ledger,
  split "event:R"), replication_tier(kinds) -> R1 split, R2 +recurs, R3 corroborated (every tier needs split). Spatial halves stay as
  a reported homogeneity flag, not a tier.
- replication.py (new): prepare() = deal events, store sides ("split_sides"), fit block on side A alone (monolith key gets "split":"A");
  SideModel/SideExpectations = B and R read the A fit (expected x fraction ratio, observed own events); test_locus/test_lead; match;
  control_inflation (shared extra-Poisson null check).
- corroborate.py (new): RULES (X36 mass movement/dam, X37, X38, X30, X31, X00 wildfire -> S2iD; A92 -> SINAN-CHIK; A90/A91 -> SINAN-DENG;
  other chapters -> SIH survivors, overlap = SIH deaths share), null = random same-state, same-population-quintile place sets, same years.
- tools.py: Session.side(), split_confirm(), corroborate(), retier(), confirm()/confirm_many() on side R via Reserve; cli split-fit, split-survey.
- lenses.py: trend_scores() factored out of trend_divergence (used by the B test of trend leads).

## State (updated)
- Code done and smoke-tested on block XV (sides A/B/R surprises: events 13,277/8,009/5,410, expected 13,277/7,966/5,311). ruff clean.
- Default regime = SHARED FIT (the all-events fit scaled by the side fraction; `replication.load_base`), because a side-A refit took 20 min
  for XV under load (full fit 2 min unloaded): `split-fit` (A-only refit) exists; XX is queued (data/logs/splitfit_XX.log) for a
  fit-sharing measure. XV measured (data/measure_fit_sharing.py): shared/A median ratio 1.00-1.08 in the top-|z| cells.
- Null check done (replication.control_inflation): marginal B test inflated (0.28-1.00 where mu>=20, size<=10), conditional 0.02-0.06.
  -> B test is CONDITIONAL on A (replication.conditional_p). ADR-0007 and ARCHITECTURE 8.3 written (docs). Evaluation entry NOT yet written.
- S2iD cached (46,489 events). Brumadinho 2019 is NOT in S2iD (expected corroboration absent); Rio 2010 (Niteroi 48 deaths) is.
- Heavy queue is full (other agents): queued in this order: warm sihB (SIH 2011..23 odd years), warm chik (SINAN-CHIK), split-survey SIM A
  (data/logs/split_survey.log; then split_confirm in the same process; writes pegasus_home/leads_A, ledger_A), split-fit XX.
  sihA (even years) done.

## Next
1. When split-survey finishes: `python data/replicate_register.py --write --reserve` (needs SIH odd years + CHIK cached; else run
   with --no-corroborate for the split-only tiers, then again). It prints tier counts, the 15 signals, the reserve LOND demonstration.
2. Write docs/evaluation/2026-10-05-replication.md (+EVALUATION row; numbers: null table above, XV sharing, tier counts, top 15, reserve),
   DECISIONS.md row for ADR-0007, ARCHITECTURE 9.1 text ok, scripts/check_docs.py, commit own paths:
   src/pegasus_core/{control,replication,corroborate,tools,leads,cli}.py, scans/lenses.py, ARCHITECTURE.md, docs/decisions/ADR-0007*,
   docs/evaluation/2026-10-05-replication.md, EVALUATION.md, DECISIONS.md, data/handoffs/replication.md (data/ scripts are gitignored).

## Final state of this front (commit a44bd8e)
Committed: code, ADR-0007, ARCHITECTURE 8.3/11.1, evaluation entry (null check, XV sharing, S2iD findings), rows; check_docs green.
STILL QUEUED in the heavy queue (other agents' jobs ahead; do not start duplicates; find with Get-CimInstance Win32_Process | ? CommandLine -match heavy.py):
 - "top15 replication" -> data/logs/top15.log (+ data/logs/top15.json). SPENDS THE REAL LOND STREAM ONCE (15 claims in the main ledger): do not rerun.
 - "split-survey SIM A" -> data/logs/split_survey.log; writes pegasus_home/leads_A, ledger_A (hours). Then:
   `python data/replicate_register.py --write --reserve` (the --reserve flag would spend another 15 claims: omit it, top15.py did it).
 - "warm sinan chik2" (SINAN-CHIK 2015-2023; earlier years are unpublished and read as zero), "split-fit SIM XX" (fit-sharing measure with data/measure_fit_sharing.py XX).
When they finish: add the tier counts, the 15 signals and the reserve table to docs/evaluation/2026-10-05-replication.md (replace its "Not run"),
update the EVALUATION row, check_docs, commit own paths.

## Status 2026-10-05 11:06 (close-out pass)
Nothing from the queue produced results yet. Running: split-survey SIM A (pid 58032, at CAUSABAS C15, leads_A empty), top15 (pid 54728, admitted 10:02, python child 3564 fetching SINAN-CHIK 2015-2023 together with the warm_chik job pid 57128: if it stalls, check data/logs/top15.log and warm_chik.log; DO NOT start it again). Finished: warm sihB (odd years), split-fit XX (3774 s). Queued: "fit-sharing XX" (data/logs/fitshare_XX.log).
Evaluation entry "Not run" section updated to this state; nothing else to commit until the survey/top15 end. Then: replicate_register.py --write (no --reserve), read data/logs/top15.json, write the results section, EVALUATION row, check_docs, commit.

## Status 2026-10-05 13:50 (aggregate-scale front)
- Part A code done: `replication.test_trend_unit` (B-side test of region/state national-trend leads, conditional on A), `test_lead` routes to it; `Session.split_home` redirects side A's register/ledger (scratch runs). Null/power check done (evaluation entry, section "Aggregate-scale trend leads"; data/null_aggregate.py). 
- Chapter III demonstration: job "replicate aggregate III" is QUEUED/detached (data/logs/replicate_aggregate.log -> data/perf/out/replicate_aggregate_III.json, scratch home in %TEMP%\repl_agg_*). When it ends, add the counts to the evaluation section ("its counts are to be added here").
- Part B NOT done: split_survey.log has no "[heavy] exit 0" (at chapter N, leads_A not final). top15 FAILED (exit 1) at the SIH step (Decimal in corroborate.sih, fixed): the LOND stream is UNSPENT ((0,0), level 0.0315); top15 must be run once more (data/top15.py), after which ./replicate_register.py --write once the survey is done.

## Redesign on independent units (2026-10-05, ADR-0015) - PAUSED, committed
Done: control.py (SIDES A/E, RESERVED_PERIODS SIM.DO [2024], check_reserved/reserve_open guard, Reserve split `period:reserve`, replication_tier = count of KINDS temporal/spatial/corroborated), monolith.assemble guard, replication.py rewritten (honest_effect, relevel, test_prospective, spatial_split/test_spatial/test_trend_unit, simulate_temporal/spatial/sizes), tools.py (train, temporal_confirm, spatial_confirm, honest_sizes, corroborate w/ edges, retier, confirm_many on the reserve, kinds_of), cli temporal-survey, docs (ADR-0015, ADR-0007 superseded, ARCHITECTURE 8.3, OQ 7 narrowed). NOT done / not run:
1. Size & power: loop `replication.simulate_temporal` (level 5/50/500 x size 3/10/inf x rho 0/0.5 x known F/T x kind null/persistent/recurring/oneoff, theta 2-4), `simulate_spatial` (shock 0/0.1, range_ 0/2, buffer T/F, trend 0/3), `simulate_sizes`; also ADR-0005 negatives (harness.lens_world kinds space/time) on a real Surprise; cross-system tier on synthetic Fields (override `Fields.sih`). Write docs/evaluation/2026-10-05-replication-independent-units.md + EVALUATION row (and annotate the old entry as superseded). Smoke so far: null selected 21 -> 0 replicated; persistent x3 0.14 (training mean absorbs) / 1.00 (known mean); one-off 0.0001; sizes: all-events 2.48x, A 2.71x, E 2.25x vs realised 2.25x.
2. Real blocks: fits <= 2019 exist for SIM I, IX, X, XVIII. Run under heavy.py: `pegasus-core temporal-survey SIM.DO death 2019 --blocks X` (and I), then `Session.retier(register, train.register.current())`. COVID is in the held-out years: check relevel by state vs nation on random place sets (size on real data).
3. Corroboration: placebo windows on real SIH to test scattered vs connected null (implement connected grown sets in corroborate._null_sets; Fields.edges is plumbed); then `Session.corroborate(reg)` over the SIM signal leads (SIH odd/even years and SINAN-CHIK are cached) and report tiers per class.
4. Reserve: check `gateway.population([2024])` is available for the default source (popsvs) before any claim; do not read the 2024 events otherwise. The top-15 spend stays HELD; do not spend one-off signals (cannot recur); spend only persistence claims, ordered before reading.
5. The old `split-survey SIM A` job (old code) keeps running; its leads_A is usable by `Session.honest_sizes` (needs A/E dealing: `deal` re-keys store `split_sides` for SIDES A/E).

## Measurement front (2026-10-05, ADR-0015): DONE, committed
Evaluation `docs/evaluation/2026-10-05-replication-independent-units.md` (+ row, OQ 7 narrowed, ADR-0015 evidence/limits amended). Done: size/power on NB worlds for the three tiers (data/replication_power.py etc. -> data/perf/out/replication_power.json); survey <= 2019 on SIM I, IX, X, XVIII, XX (leads_T2019 holds 1,439 leads with prospective + spatial_unit verdicts); register (pegasus_home/leads) re-tiered and written: 333 R1, none R2/R3; corroboration: connected null sets + 99,999-replicate redraw of p < 0.01 (permutation floor blocked BH); `retier` keeps only prospective/honest keys. The reserve is UNSPENT ((0,0)); `gateway.population([2024])` works (popsvs).
Left: ADR-0005 negatives through the whole chain on a real Surprise; honest_sizes on real leads; blocks other than I, IX, X, XVIII, XX on <= 2019 (1,299 leads); the author's reserve spend (see the evaluation, "What a reserve spend would test").
