# SIH-RD, all chapters: calibration, the XV diagnosis, and the survey/replication run (2026-10-05)

**Regime:** SIH-RD `hospitalisation` annual 2010-2023, contiguity, 19 fitted chapter blocks (I-XV, XVII-XIX, XXI; XVI refitted, below), ADR-0006 regional dispersion, population per ADR-0010. Scripts (`data/`, gitignored): `sih_readout.py --groups` (calibration; `data/logs/sih_full_cal.jsonl`, read by `sih_full_cal_read.py`), `sih_xv_diag.py` (`data/logs/sih_xv_diag.log`), `sih_full_survey.py`, `sih_full_repl.py`, `sih_full_read.py`, chain `sih_chain.ps1`, `sih_fit2019.ps1`. Code changed: `corroborate.py` (SIM source for SIH leads, below).

## 1. Calibration, 19 chapters (KS overall / worst macro-region; criterion 0.03 / 0.05)

| tier | chapters calibrated | groups calibrated (of 198) | what fails |
|---|---|---|---|
| B0 | 0 of 19 (worst region .12-.40, the South worst in 9) | 40 | no place effects: expected |
| B1 | **17 of 19** | **182** | XV (.067 / .092); I by .002 (.032 / .043) |
| B2 | 5 of 19 (VIII, XI, XIV, XVII, XIX) | 114 | overall: I .037, II .035, III .032, IV .039, V .035, VI .033, VII .041, X .040, XII .044, XIII .032, XVIII .037, XXI .046, XV .092; region only: IX .052 |

- The worst region at B1 is the North for 9 of 19 chapters (Centro-Oeste 5, Nordeste 4, Sul 1) and at B2 for 15 of 19 (few, small places). B2 over-expects by 0.4-3.2 % in total (VII +2.4 %, IV +2.1 %, XXI +2.0 %, VIII +3.2 %), which the second-stage shrinkage does not remove. **B1 is the calibrated tier of SIH; B2 fails the 0.03 / 0.05 criterion in 14 of 19 chapters** (13 overall, IX by region), so leads that need B2 inherit a null that is slightly too wide.
- XVI (perinatal): its stored fit predates the hybrid newborn exposure (ADR-0010 amendment, `3e5c9fb`); `Session` looked for a block keyed `population: hybrid` and `survey` raised `LookupError`. Refitted (`fit_sih_XVI_hybrid.log`, 40 outers); calibration of XVI is in `data/logs/sih_full_cal_XVI.log` once the queue runs it.

## 2. Why XV (pregnancy, childbirth) fails: the variance function, not the catchment

Chapter XV is 32.9 M admissions (14 years x about 2.35 M). At B1: PIT deciles hump in the middle (0.75 ... 1.46 ... 0.60), z sd 0.95, expected total exact (y/mu 0.998 every year). Reading the residuals (`sih_xv_diag.log`):

- **z sd falls with place size**: 1.16 (smallest fifth, 367 admissions per place over 14 years) to 1.01, 0.93, 0.85, **0.73** (largest fifth, 22,973). A negative binomial with one dispersion per field over-states the variance of large places, where deliveries are close to deterministic given the population and fertility; the same ordering holds at B2 (1.08 to 0.69). Calibrated chapters do not show it (XVII: 1.00-1.06, 0.96 in the largest fifth).
- **It sits in delivery, not in complications**: O80-O84 (normal delivery, 19.5 M) KS .084 / .114, whereas O60-O75 (labour complications, 3.3 M) KS .023 / .036 with z sd 1.0 at every size.
- **Not a catchment (supply) effect**: the correlation of a place's z with its neighbours' is **positive**, +0.34 (a hospital serving its neighbours would make it negative), and the supply term of ADR-0016 changes nothing (B1 KS .067 to .064, B2 .092 to .087; O80-O84 .084 to .081).
- A residual with a time shape remains: z sd by year is U-shaped (1.09 at 2010, 0.82 in 2015-2019, 1.06 in 2023) and a place's mean z over 2010-2016 is correlated -0.93 with its mean over 2017-2023 at B1 (-0.38 at B2): places drift in delivery admissions (births falling faster in some regions, deliveries moving between hospitals) beyond a level plus a national course.

Verdict: a **fitted-model defect in the dispersion** (variance should grow slower than mu squared for delivery), plus place-level drift that B2's slope only half absorbs. XV leads are not trustworthy at any tier until the dispersion depends on size (ARCHITECTURE §13); the survey keeps XV in but its leads are read as suspect.

## 3. Corroboration of SIH leads (code)

`corroborate.rule_for` knew SIM-lead rules only; for a lead of SIH-RD the rule `sih` would have corroborated an SIH lead with SIH itself. `SIH_RULES` now give SINAN (dengue A90/A91, chikungunya A92) and **SIM deaths outside hospital** (`corroborate.sim_year`, `Fields.sim`: SIM.DO by residence, 3-character cause, LOCOCOR = 1 or not). An in-hospital death is the same person as an admission that ended in death (ARCHITECTURE §8.5), so those are excluded and the share recorded as the overlap bound. SIM 2015: 1,264,175 deaths, 848,842 in hospital (67 %).

## 4. Survey, triage and replication tiers: running, not read

The gated plan (`SURVEY_PLAN`, 50 replicates) was too slow for one process (about 25 s per field under the machine's load, an estimated 1,200 fields), so it runs as `base1` (I-VIII, XII-XIV, XVII, XVIII, XXI), `base2` (IX, X, XI, XV, XIX), `base3` (XVI) and `supply` (`Session(supply=True)`: X, IX, XI, XIX, XV), each followed by the facility triage and the same-array replication, with its own register under `pegasus_home/`. The fits on 2010-2019 for the ADR-0015 training survey (`sih_fit2019.ps1`: X, IX done; the rest in the queue) and the chain `sih_chain.ps1` (train survey <= 2019, temporal, spatial, corroboration, then `sih_full_read.py`) are detached. **No lead count, class or tier is claimed here**; they are appended to this entry when `data/logs/sih_chain.log` reads `CHAIN DONE` (handoff `data/handoffs/sih.md`). The reserve (SIM.DO 2024) is not read.
