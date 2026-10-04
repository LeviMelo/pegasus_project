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
