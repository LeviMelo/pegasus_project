# Brumadinho confirmatory test (agent "brumadinho", 2026-10-05; ledger d5938be360254838) -- IN PROGRESS
## Done (committed)
- Step 1 (fb55af9): secondary places = 25 other municipalities of the MG government's "26 municipios considerados atingidos" (Agencia Minas 2021-10-18; read via Wayback copy because the live host serves an electoral notice); data/brumadinho_locus.json.
- Step 2 (3413ce1, 0fa8f40, 00b0ebc): data/brumadinho_bp.py (train 2010-01..2018-12, T0 108), brumadinho_baseline.py, brumadinho_test.py; operational definitions in the entry.
- Step 3: baseline shares reported in the entry (Brumadinho J20-J22: 16 admissions, hospital 2124289 69%; my own mechanical burst rule fired on n=11, judged an artefact, disclosed; test proceeds).
## Running
- Fit X then XI: data/logs/brumadinho_fit.log (heavy.py, cuda; ~100 s per outer, 40 max). Done when `BLOCK X`, `BLOCK XI`.
## Remains
- `PYTHONUTF8=1 python scripts/heavy.py --label "brumadinho test" -- python data/brumadinho_test.py` -> data/logs/brumadinho_result.json; read criteria; Result section in the entry; ledger complete("d5938be360254838", p, effect, result) (see rio doce handoff); commit own paths (git add -f data/), never push.
- The test reads SIH-RD 2019-2020 (present: availability shows 1992-2026 decoded).
