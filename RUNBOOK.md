# RUNBOOK.md

Commands that operate this repository. The interpreter is the `pegasus` environment's (CLAUDE.md §2):

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
```

| task | command | notes |
|---|---|---|
| install, editable | `PYTHONUTF8=1 $PY -m pip install -e . --no-deps` | the environment already holds the dependencies and pegasus_data |
| check the GPU | `$PY -c "import torch; print(torch.cuda.is_available())"` | expects `True` (RTX 4050, CUDA 12.1) |
| lint | `$PY -m ruff check src scripts` | |
| documents consistent | `$PY scripts/check_docs.py` | ADRs, evaluation index, open questions, modules named in ARCHITECTURE, CLAUDE.md = AGENTS.md |
| pegasus_data reachable | `$PY -c "import pegasus_data, pegasus_core; print(pegasus_data.__file__)"` | |
| warm the gateway cache | `PYTHONUTF8=1 $PY scripts/warm_gateway.py SIM.DO death 2010 2023` | one year at a time; downloads through pegasus_data into `PEGASUS_DATA_ROOT` |
| fit blocks, detached | `scripts/fit_blocks.py DATASET EVENT FIRST LAST GRAPH BLOCK...` via `data/logs/fit_blocks.ps1` (`Start-Process`) | `PEGASUS_DEVICE=cuda` for the GPU; the log is UTF-16 (read with `iconv -f UTF-16`) |
| the CLI | `pegasus-core fit|fields|surprise|scan|survey|leads|ledger` | `pegasus-core --help`; years default 2010-2023, graph contiguity |
| a field's calibration | `pegasus-core surprise SIM.DO death I60-I69 --tier B1` | KS overall and per macro-region, and the most surprising cells |
| the survey | `pegasus-core survey SIM.DO death --replicates 100` | every admissible field of every fitted block; leads to the register |
| held-out model choice | `scripts/measure_heldout.py DATASET EVENT TRAIN_FIRST TRAIN_LAST TEST_LAST BLOCK GRAPH/PROFILE...` | e.g. `contiguity/group knn6/group contiguity/category`; one `HELDOUT` line per configuration |
| the harness for a lens | `pegasus-core harness SIM.DO death I60-I69 space_time --graph knn6` | surrogates (own ledger) and, for subset lenses, the power curve; stored under `pegasus_home/harness` |
| a non-default source | `PEGASUS_SOURCE='{"source": "mark", "mark": "PESO", "bounds": [200, 7000]}'` before `fit_blocks.py` | also `{"source": "code_list", "column": "CODANOMAL"}`; block `*` for an event type without a tree |
