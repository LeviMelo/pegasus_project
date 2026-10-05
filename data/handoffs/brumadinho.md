# Brumadinho confirmatory test (agent "brumadinho", 2026-10-05; ledger d5938be360254838) -- IN PROGRESS
## Where it stands
- Step 1 DONE, committed alone (fb55af9): secondary places = the 25 other municipalities of the MG government's "26 municipios considerados atingidos"
  (Agencia Minas 2021-10-18; live host serves an electoral-period notice 503/302, so read from the Wayback copy of the same PDF); data/brumadinho_locus.json/.py; section "Secondary places" in the entry.
- Nothing fitted, no SIH 2019-2020 outcome read. Next: commit scripts (data/brumadinho_bp.py, brumadinho_baseline.py, brumadinho_test.py), then baseline facility shares (2016-2018 only), then fits X and XI (train 2010-01..2018-12), then test.
## Pitfalls
- Rio Doce lessons: BP trains on whole years (here the training is 2010-2018 = whole years, files 2010-2019 read so Dec 2018 late filings count; truncated at t<108); a single-facility burst in training inflates E.
