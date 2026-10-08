# One field's question pass: objects computed once (S0.2)

**Regime.** `scripts/profile_field.py SIH-RD hospitalisation X J09-J18 --years 2010-2023` (contiguity, robust B1, sandbox ledger), before at aa6bd90, after on the S0.2 commit; pegasus_data 0.1.0a1; this machine on AC power; 2026-10-07. Profiles in `data/probes/profile/` (`before_`, `after_`, `after3_` logs).

**What was counted, and why.** Seconds per question for one field, and the answers each question returns. The time shows the cost of a reading; the answer counts show the speed-up did not change what is found.

| question | before (s) | after (s) | answers before → after |
|---|---|---|---|
| excess | 97.2 | 58.1 | 229 → 228 |
| step | 43.9 | 7.8 | 23 → 23 |
| trend | 43.2 | 7.2 | 28 → 27 |
| cluster | 69.7 | 30.7 | 29 → 28 |
| share | 620.9 | 33.2 | 1048 → 1048 |
| institution | 37.2 | 14.5 | 1500 → 1500 |
| group | 11.0 | 2.4 | 799 → 799 |
| **total** | **922.9** | **153.7** | |

- The before run fitted the national `*` model silently (74 s, `_expected_total`); it is stored now, so share's drop includes it once. The rest:
  - the evidence grid vectorised (identical arrays; 2.9 s against 37.9 s for two years);
  - the beta-binomial tails compiled (exact against mpmath where scipy's `sf` floors at about 1e-9);
  - the spatial noise computed once per surprise and in single precision (ω and s* equal to double on three SIH fields; 2.5 s against 21–26 s);
  - the spectrum and the scale ladder kept per graph;
  - variances, lag covariances, spatial roots and replicate fields kept per surprise.
- Excess, trend and cluster each moved by one answer. All three shapes now read one set of replicate fields per field and tier, drawn from a seed without the shape: another Monte Carlo draw of the same null.
- **Not met:** §5.8's target of under 2 min. The remaining time is computed once per field: the surprise's noise fit (`place_year_phi`, nbinom cdf 21 s), the peaks' GPU passes (37 s for 4 calls) and the institution pairs (14 s). This is unit S0.7 of the work plan.
