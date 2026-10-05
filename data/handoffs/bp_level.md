# Handoff: BP level problem (branch design-v0)
Tool calls so far ~38. Background: fits (data/logs/bp_level_fits.sh annual|dengue, logs data/logs/bp_level_fits_*.log): SIM IX/X/I/XVIII at t0 2014,2016,2018 (+2021 X,I,XVIII); dengue monthly t0 2016, 2020. Existing fits: SIM 2019 (+IX 2021), dengue 2014, 2018.
Harness: scripts/measure_bp_level.py annual|dengue ORIGINS -> data/logs/bp_level_<kind>_<origins>.json (under scripts/heavy.py; logs data/logs/bp_level_*_*.log).
Code touched: surprise.refit_place (X_new arg: forecast of the course + var), monolith.extrapolate_effects (annual 'level','damped8','damped5').
## Findings (exploration, IX 2019 / dengue 2018)
- IX 2019: oracle national x year ratio takes KS .126->.101 only; macro x year .094; ORACLE PLACE RATIO .013 (ll -79.5k -> -67.6k): miscentring is PLACE-LEVEL drift, not the national h.
- BP used the block's phi only; the field's in-sample phi_extra (macro/state hierarchy, estimated on the TRAINING fit's B1 cells, no leakage) applied to BP: IX KS .126->.107 (ll +3k); dengue 2018 ll -2.89M -> -1.02M, KS .162->.122.
- Place B2 trends extrapolated (damped .5 + coef var): IX .107 -> .082 (ll -76.5k -> -74.6k). Not for monthly dengue (damp 1 gives obs/exp .2).
- Dengue 2018: climatology mixture over the fit's years (each fit year's h block as a member, equal weights) KS .073 (ll -777k), obs/exp 1.33 (from 2.84); remaining miss: Sul (obs/exp 6.6: dengue spread to the south, place-level drift).
## TODO
run harness all origins, choose, implement in monolith.extrapolate/surprise.prospective (mixture PIT, in-sample extra), ARCHITECTURE 6.1/6.2/13, ADR-0007 if settled, DECISIONS row, EVALUATION entry+row, OQ6, check_docs, commit own paths only (not leads/explain/tools/cli).

## Update (~70 calls)
- Implemented (uncommitted): src/pegasus_core/prospective.py (insample_extra, course, mixture_pit), monolith.extrapolate_members (+ annual histories level/damped8/damped5, 'climatology' for monthly), surprise.Expectations.prospective rewritten (mixture of NBs; other agent also has uncommitted edits in surprise.py: exposure/population hunks -> commit only my hunks with git apply --cached). Verified XVIII 2019: KS .035/.049.
- Dengue results (token: KS/worst/ll): 2018: level36 block .162/.264/-2.89M; +extra .122/.242/-1.02M; climatology .073/.178/-0.777M. 2014: .177/.264/-1.79M; +extra .048/.074/-0.660M; climatology .039/.060/-0.614M.
- Annual 2014 (test 2015-19): linear h overextrapolates at 5y horizon; level/damped better in several; place course + coef var helps most. Running grid H x d (scripts/measure_bp_level.py annual 2014 2019, pooled by scripts/bp_level_table.py). Fits SIM 2016 (then 2018, 2021) and dengue 2016/2020 still running/queued: data/logs/bp_level_fits_*.log.
- Chapter I at 2019 = COVID (B34 category born): KS .53 whatever; report separately.
- TODO: drop Expectations(forecast=) + laplace.forecast_variance/increments + extrapolate_effects(increments) if the mixture replaces them (measure_laplace.py uses forecast=); fix extrapolate_members docstring numbers; docs.

## DONE (commit d3281f9)
BP level front finished. See docs/evaluation/2026-10-05-bp-level.md and ADR-0007. Not run: SIM origins 2018/2021 (COVID break), dengue origins 2016/2020 (queue). surprise.py/monolith.py commit includes another agent exposure/population hunks (needed by prospective). Fit chains killed.

## Follow-up front (ADR-0011 pre-assigned; ~35 calls)
- Launched fits (data/logs/bp_level_fits2.sh sim18|sim21|deng20; logs bp_level_fits2_*.log). Rolling-origin harness gained --lean (earlier BP vs adopted only) and per-region KS: `measure_bp_level.py annual 2018` etc., table by `bp_level_table.py --origins`.
- Outbreak lens on new BP DONE (data/dengue_outbreak_bp2.py, data/logs/dengue_outbreak_bp2.json): state-year recall/precision (>=300/1e5): 2015-16 old 0.78/0.78; level36 on new code 0.49/0.90; new BP (climatology) 0.22/0.80. 2019-23 old level36 0.906/0.637; level36 new code 0.81/0.75; new BP 0.48/0.84 (state-month KS .331 -> .146). The calibrated mixture is a worse epidemic alarm (past epidemics are regimes).
- Chapter I 2019: B34 is NOT an unseen category in the fit (802 training deaths, expected 340, observed 714,782). Real unseen leaves: A67,B04 (mpox, 14 deaths),B35,B96. Experiment: data/p5/unseen_category.py -> data/logs/unseen_category.json.

## PAUSED (coordinator request) - state and next steps
Done and committed: dengue origins 2016/2020 (regimes best at 4 origins), SIM 2018, outbreak lens on new BP (dengue note), unseen category (ADR-0011 implemented in surprise.prospective, checked live), docs.
Next: (1) SIM origin 2021 (COVID break, report separately): fits X, I, XVIII <=2021 done (IX existed); a `measure_bp_level.py annual 2021 --lean` run was queued under heavy (log data/logs/bp_level_annual_2021.log, artefact data/logs/bp_level_annual_2021.json); if it did not finish, rerun it, then `bp_level_table.py annual --origins 2021` and replace the "Not run: SIM origin 2021" paragraph of docs/evaluation/2026-10-05-bp-level.md and OQ 6. (2) check_docs shows 2 problems from other agents (ADR-0015 gap, facility module), not mine.

## Alarm baseline front (commit 5f2a000, ADR-0012; renumbered from 0016 by the coordinator)
Done: SIM origin 2021 measured (docs/evaluation/2026-10-05-bp-level.md; mean KS .088 without chapter I, I .89, X .31; separate), `prospective(purpose="expectation"|"alarm")` (tiers BP/BPA), `Session.survey(prospective=t0)`/`scan(train_last=)`, PROSPECTIVE_TIERS, dengue outbreak lens under both (data/logs/dengue_outbreak_alarm.json; expectation reproduces the earlier run exactly), ARCHITECTURE 6.1/7.1, DECISIONS row, OQ 6.
Open: leads from a prospective survey are not yet explained/replicated (explain_lead/triage read lead.tier without train_last and raise); the recurrence-interval alarm design is phase 4 (ADR-0004); ARCHITECTURE.md hunks of other agents left unstaged; check_docs only complains of the ADR 0013-0014 gap (reserved).
