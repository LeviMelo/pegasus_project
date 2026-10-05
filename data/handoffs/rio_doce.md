# Rio Doce confirmatory test (agent "rio doce", 2026-10-05; ledger 49f1626af33f4867)
## State
- DONE: locus fixed and committed alone (f5438d7): 41 municipalities of the IBAMA Laudo Tecnico Preliminar 2015 (data/rio_doce_locus.json).
- Training "through 2015-10" is not what BP does (whole years): data/rio_doce_bp.py truncates the training assembly to 70 months (key "through": 201510,
  files 2010-2016); test assembly files 2015-2017. Fits (X, XI monthly) run via heavy.py -> data/logs/rio_doce_fit.log (waited for 4 GB free RAM at start).
- data/rio_doce_test.py (operational definitions in its docstring) -> data/logs/rio_doce_result.json. Run after both BLOCK lines appear in the fit log.
- facility.py is untracked: not used; facility shares computed directly from the CNES column in rio_doce_test.py.
## Next
1. test run (heavy.py), read the numbers; 2. ledger complete(49f1626af33f4867, p, effect, result); 3. "Result" section in the declaration entry;
4. commit own paths only (docs entry, data scripts with git add -f, no push).
