# Rio Doce confirmatory test (agent "rio doce", 2026-10-05; ledger 49f1626af33f4867) -- PAUSED by the author
## Where it stands (no result data has been read; the test script has NOT been run)
- Step 1 DONE and committed alone (f5438d7): locus = the 41 municipalities of the IBAMA Laudo Tecnico Preliminar (Nov 2015), sec. 2.4 table;
  IBGE codes in data/rio_doce_locus.json; section "Locus" in docs/evaluation/2026-10-05-rio-doce-declaration.md. (IBAMA URL gives 403 to curl; text read from
  a copy of the same PDF at facfama.edu.br; the 39-municipality TTAC list = this list minus Acaiaca and Ponte Nova, seen only in a secondary summary.)
- Operational definitions + scripts committed before any result (466502c): data/rio_doce_bp.py, data/rio_doce_test.py, "Operational definitions" section of the entry.
- Step 2 (fits) RUNNING DETACHED, not killed: `heavy.py ... data/rio_doce_bp.py fit X XI` -> data/logs/rio_doce_fit.log (cuda, ~60 s per outer, 40 outers max;
  X was at outer 19, max tau change 0.047, ~21 min in). Training = months 2010-01..2015-10 (70 months, store key through=201510; BP trains on whole years so the
  assembly is truncated in the script). Done when the log shows `BLOCK X ...` then `BLOCK XI ...` then `DONE`. If a FAIL line appears the script retries on cpu once.
## Remains
1. When both BLOCK lines exist: `PYTHONUTF8=1 python scripts/heavy.py --label "rio doce test" -- python data/rio_doce_test.py` (writes data/logs/rio_doce_result.json:
   O/E, minimum-effect p (RATE_RATIO 1.2), monthly curve 2015-01..2016-12 for locus and the rest, per municipality, per CNES facility, nodes J30-J31, J31,
   J00-J06, J20-J22, J40-J47 and XI = negative control). The test can refuse (places mismatch between training and test assembly, files 2017 absent): if so, report, do not substitute.
2. Read PASS/FAIL per criterion as defined in the entry (verdict on J30-J31; criterion 2 = >=3 municipalities and >=2 facilities each holding >=5% of the net excess, none >50%;
   criterion 3 = chapter XI ratio < 1.2 or p >= 0.05). Nothing is to be changed after seeing the data.
3. Ledger: control.Ledger().complete("49f1626af33f4867", p, effect(=ratio), result dict). Add a "Result" section to the entry with the honesty notes
   (association in time and place; exposure vs care-seeking/recording change; whole municipalities dilute; training truncation by script).
4. Commit with git add of own paths only (git add -f for data/), message ending "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>". Never push.
## Pitfalls
- facility.py is untracked and not used. heavy.py queued ~2.5 min for 4 GB free RAM.
