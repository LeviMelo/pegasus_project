# SIH-RD hospital admissions: the fitted blocks read out (2026-10-05)

**Regime:** SIH-RD `hospitalisation` 2010-2023, contiguity, HEAD 9ee7774 (ADR-0006 regional dispersion; the working tree carried other agents' uncommitted `surprise.py`/`control.py` edits). Blocks fitted when read: annual VIII, IX, X, XI, XV, XVII, XIX; monthly X (admission month, 16,690,840 events). Year = processing (competence) year, as TabNet; national totals matched TabNet (chapters mean 0.00 %, max +0.02 %). Oct-Dec 2023 are deficient (filing lag ~3 months).
Scripts (`data/`, gitignored): `sih_winter2.py`, `sih_readout.py`, `sih_survey.py`, `sih_triage_top.py`; logs `data/logs/sih_winter2.{log,json}`, `sih_readout_cal*.jsonl`, `sih_readout_survey_X.log`, `sih_readout_triage.log`.

## 1. Known positive: winter respiratory admissions, South and Southeast (§10.1)

Monthly chapter X, share of the year x12 (1 = flat), mean over years:

| region | observed peak (amp) | B1 expected | B2s expected | Jun-Aug share: obs / B1 / B2s |
|---|---|---|---|---|
| Sul | Jul (1.80) | May (1.51) | Jun (1.71) | 1.227 / 1.094 / 1.199 |
| Sudeste | May (1.55) | May (1.53) | May (1.55) | 1.101 / 1.096 / 1.102 |
| Nordeste, Norte, Centro-Oeste | May / May / Mar (1.49-1.52) | May | May (1.45-1.50) | 1.04 / 1.00 / 1.03 vs B2s 1.05 / 1.02 / 1.05 |

- **Season recovered, sign right.** B1 carries one national season, so it misses the Sul's later and larger winter; B2s takes the regional shape (profile correlation with observed 0.986-0.998 against 0.84-0.997 at B1). The Jaccard of the (region, month) sets with share >= 1.10 in Sul + Sudeste is **1.00 at B2s against 0.56 at B1** (thresholds 1.05/1.15: 0.90/0.83 against 0.73/0.80). Amplitude ordering: Sul 1.80 > Sudeste 1.55 > Norte, Nordeste, Centro-Oeste about 1.5. The South peaks in Jul, the other regions in Mar-May.
- **As the outbreak lens, the criterion as written fails, by design.** B2s outbreak cells: 73 nationwide, 40 in S/SE, **6 of them in Jun-Aug** (15 % against 25 % by chance); B1 8 of 44, B2 9 of 40. The lens does not flag the recurring winter, because the expectation already holds it. S/SE hits concentrate in 2015 (9), 2016 (5) and 2021 (12), not in winters. A municipality-month outbreak cell cannot overlap a regional season at Jaccard 0.5; the criterion is the seasonal one above.
- **Calibration, monthly X under ADR-0006** (KS overall / worst macro-region): B0 0.085 / 0.294 (Sul), B1 0.010 / 0.012, B2 0.014 / 0.018, B2s 0.014 / 0.019. All three non-B0 tiers calibrated. The regional dispersion cut the S/SE outbreak cells (B2s 146 to 73 nationwide) with the same winters flagged as before.

## 2. Calibration per block (KS overall / worst macro-region; criterion 0.03 / 0.05)

| block | B0 | B1 | B2 | groups calibrated B1 / B2 (of n) |
|---|---|---|---|---|
| VIII | .032 / .119 | .012 / .022 | .027 / .050 | 4 / 4 (4) |
| IX | .052 / .331 | .014 / .031 | .027 / **.052** | 10 / 6 (10) |
| X | .100 / .387 | .023 / .033 | **.040** / .049 | 10 / 3 (10) |
| XI | .104 / .353 | .018 / .034 | .030 / .044 | 10 / 4 (10) |
| XV | .065 / .283 | **.067 / .092** | **.092 / .104** | 5 / 0 (8) |
| XVII | .056 / .258 | .012 / .023 | .019 / .038 | 11 / 11 (11) |
| XIX | .039 / .201 | .017 / .022 | .029 / .040 | 20 / 16 (21) |

- **B0** never calibrates (worst region 0.12-0.39, the South worst in X, IX, XI, XIX): expected, it has no place effects. **B1 calibrates in every block but XV** (chapters 6 of 7; groups 70 of 74). **B2 calibrates in 4 of 7 chapters** (VIII, XI, XVII, XIX; X misses overall by .010, IX in a region by .002, XV fails) and in 44 of 74 groups; it over-expects by 0.4-3.2 % in total (X: 16.998 M against 16.769 M observed; VIII 3.2 %).
- **XV (pregnancy, childbirth) is miscalibrated at every tier**, worst in O80-O84 (delivery; B1 KS .084) and O10-O16. Its admissions are births, whose count in a place follows the hospital's catchment rather than residents' risk. A fitted-model defect, not a regional one (all five regions fail, .071-.104).
- Remaining blocks (annual I-VII, XII-XIV, XVI, XVIII, XX, XXI; monthly other chapters) were still fitting (the driver `sih_pipeline2.ps1` was on I); `data/sih_calibrate.py` runs them after the fits.

## 3. Survey of chapter X (50 replicates, 2,062 s) and its triage

Register held no SIH leads; surveyed X here. **22,628 leads**: trend_divergence 15,477, group_disparity 5,928, outbreak 615, space_time 601, change_point 7. `pegasus-core triage SIH-RD hospitalisation` (replication on):

| class | leads | trend | group | outbreak | space-time |
|---|---|---|---|---|---|
| signal (unexplained) | 10,142 | 6,302 | 3,152 | 358 | 327 |
| system | 7,250 | 4,770 | 2,183 | 119 | 175 |
| noise | 3,093 | 2,374 | 593 | 122 | 4 |
| substitution | 2,143 | 2,031 | 0 | 16 | 95 |

System reasons: coding practice 4,869, denominator 1,289, recording 1,029, model 63. **All 22,628 stay R0**: 0 R1, R2, R3. Trend leads fail the half-period test (`ok` False), the group leads are untested, the window leads fail the other-half test by construction (one-off events), as the SIM survey found for outbreaks.

Top plausible signals (class signal, ranked), all unconfirmed, and mostly one municipality at a time:
1. trend J40-J47, São Gonçalo/RJ, divergence -27.6 (217 admissions per year in the window against 6,297 in the base; the siblings 3,490 against 5,745): a collapse of one code group in one city, most likely coding or a hospital's behaviour.
2. trend X, Cristópolis/BA (+22.4), and J12, same place (+19.3): a place-level rise in respiratory admissions; no reading yet.
3. group_disparity J11 influenza, Ilhéus/BA; J45 asthma, Vitória da Conquista/BA; J12 João Pessoa/PB: one city's age-sex pattern differs from its peers.
4. space_time J31 (rhinitis, nasopharyngitis), 27 municipalities of MG, 2015: 255 against 16 expected, base 0, siblings 158 to 1,156 and the spatial test passes (R1 spatial ok, temporal not). Geography reads as the Rio Doce valley (Governador Valadares and its neighbours), the year of the Fundão dam failure: a hypothesis, not tested (annual grain).
5. space_time J14 and J13 (Haemophilus and Streptococcus pneumonia), SC and MG groups, 2020-2023: 0 admissions against 183 and 226 expected while the siblings stay at 1,700-2,000 and the nation falls about half. The code stops being used locally: a coding artefact the triage does not catch because the siblings do not rise.
6. outbreak J42 (chronic bronchitis), Pinhão/PR, 2016: 228 against 23 expected, base 1, siblings flat: a coding event in one hospital.

**What this says about the readout:** the signals the triage leaves open are unexplained only; reading them, 3 of 6 look like coding behaviour of a hospital or an area (J40-J47, J14/J13, J42), none is a confirmed epidemiological event. The two largest groups of leads (trend divergence and group disparity at municipal grain, 20,900 of 22,628) never replicate; the SIM entry's lesson holds here too, only more strongly.

## Defects and gaps
- XV does not calibrate at any tier (§2); X and IX B2 miss the 0.03/0.05 criterion by a hair, with a +0.7-1.4 % over-expectation.
- Triage leaves `substitution` blind to a locally vanished code whose siblings do not rise (lead 5), and the replication tier stays R0 for all trend leads.
- The monthly X and annual X blocks hold 16.69 M and 16.77 M events (competence month against competence year, plus 2009-dated late filings in neither).
- Blocks I-VII and XII-XXI had not finished fitting; their calibration and surveys are pending in the driver.
