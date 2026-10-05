# Dispersion by macro-region and state, on every fitted block (2026-10-05)

**Scenario.** `scripts/measure_dispersion.py` (targets `sim`, `ix-knn6`, `sinasc-xvii`, `sinasc-total`, `sih`, `sih-monthly`, `dengue`, `lept`, `lept-notif`, `bp-*`, `ho-*`); artefacts `data/logs/dispersion_<target>.json` (local). **Regime.** design-v0 after the Laplace evaluation, fits as cached in `pegasus_home/monolith` (2010–2023, contiguity; kNN6 for the IX group nodes), MAP predictive, 2026-10-05. Each (field, tier) is captured once from `surprise._assemble` and four dispersion structures are scored on the same expectations; the verified default (`Expectations.surprise`) reproduces the survey (IX B1 KS 0.0072 / 0.0201; dengue B2s 0.0174 / 0.0279).

**What was counted.** The PIT's KS overall and in the worst macro-region (the §6.2 criterion, ≤ 0.03 and ≤ 0.05), and the aggregate NB log-likelihood.

| tier (fields) | calibrated: block φ / one φ_extra / macro-region / macro-region + state | mean KS | mean worst-region KS |
|---|---|---|---|
| B1 (33) | 18 / 28 / 30 / 30 | .038 / .0125 / .0118 / .0113 | .059 / .034 / .026 / .026 |
| B2 (33) | 22 / 25 / 26 / 27 | .032 / .018 / .0175 / .0174 | .052 / .036 / .033 / .032 |
| B2s (4) | 2 / 4 / 4 / 4 | .067 / .011 / .010 / .010 | .097 / .025 / .015 / .015 |
| B0 (33, fails by design) | 4 / 4 / 5 / 5 | .110 / .045 / .043 / .042 | .220 / .160 / .146 / .146 |

- **Largest gains** (worst-region KS, one value → macro-region): SIH X B1 .082 → .035 (monthly: .040 → .014); SIH XVII B1 .053 → .028; IX B1 .037 → .022; XVIII B1 .047 → .032; dengue B2s .048 → .028. Where one value already calibrated (leptospirosis, most small chapters) nothing moves.
- **The Centro-Oeste failure is region-specific dispersion:** dengue φ_extra B1 by region (N, NE, SE, S, CO) .22 / .21 / .30 / .15 / .37 (one value: .25); B2s .39 / .32 / .44 / .34 / .50. Chapter IX B1 differs five-fold (47 to 245): the component is larger where places are small.
- **State level.** φ_extra by state ranges 5× within the field (dengue B1 .075 to .40). Gain over macro-region: mean KS −.0005, worst −.0006 (B1), −.0008 (B2); one more field calibrated at B2. Log-likelihood over macro-region: +12 to +5,353 nats for 22 parameters (20 of 22 above 22). Cost: dengue B1 3.4 s one value, 4.7 s macro-region, 6.6 s with states.
- **Still failing at B1** (3): dengue (Southeast .081: the states do not rescue it, .081), SINASC total (.049 / .066, no extra component is wanted), SIM XIV (.051). At B2 (6): those plus XVIII (.057), SIH X (overall .040), SINASC XVII (overall .031).
- **The block's φ by region** (`Monolith.dispersion_by`, `nb_loglik` over every cell including the empty ones; fit to the last year shown, scored on the later years, φ from the fit): dengue 2018 φ N/NE/SE/S/CO .21/.22/.29/.23/.39, held-out gain +0.0094 nats per event (+57,000 nats); dengue 2014 +0.0016; IX 2019 φ 5.8–8.4, +0.0002; XVIII +0.0021; X −0.0007. Only dengue's monthly cells gain materially: not adopted.
- **BP** (ten fields, block φ is the shipped behaviour; a field φ_extra is a diagnostic): IX to 2019 .126 / .195 → .086 / .163 with regions (one value .155); dengue to 2018 .162 / .264 under the block's φ, .290 / .500 with one value, .224 / .326 by region; to 2014 .132 / .229, .207 / .300, .180 / .254. None calibrates: BP's miscalibration is level, as the Laplace entry found.

**Verdict.** Dispersion by macro-region (and state) holds beyond dengue and IX: 12 more fields calibrate at B1 than with the block's φ and 2 more than with one φ_extra; the worst-region KS falls by a quarter at B1. It does not repair dengue B1 in the Southeast or BP, which stay as OQ 6's remainder. Adopted: ADR-0006.

**Correction (BP level, 2026-10-05).** "BP's miscalibration is level" and "BP unaffected" above hold for dispersion estimated on BP's own cells. Applying the *training fit's* φ_extra to BP, with a damped place course and regimes, lowers the mean KS from .121 to .060 (annual) and .169 to .056 (dengue): `2026-10-05-bp-level.md`, ADR-0009.
