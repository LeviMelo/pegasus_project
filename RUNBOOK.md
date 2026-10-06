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
| the solver | v1 by default for count blocks without the interaction; `PEGASUS_SOLVER=v0` restores the v0 Newton–CG | exact Newton on the assembled Hessian and Newton on log τ (ARCHITECTURE §5.3–5.4); `PEGASUS_STRENGTHS=fs` keeps Fellner–Schall with exact traces, `PEGASUS_SCORING_PROBES` (16) and `PEGASUS_LAML_TOL` (0.1) tune the strengths |
| the solver benchmark | `PYTHONUTF8=1 $PY scripts/bench.py --blocks SIM.DO:IX,SIM.DO:VII [--warm] [--heldout 2023] [--solver v0]` | fits without saving; one JSON row per block to `data/bench/<date>.jsonl` (seconds, outers, Newton steps, φ, τ's, per-outer timings, held-out deviance) |
| the CLI | `pegasus-core fit|fields|surprise|scan|survey|leads|ledger` | `pegasus-core --help`; years default 2010-2023, graph contiguity |
| a field's calibration | `pegasus-core surprise SIM.DO death I60-I69 --tier B1` | KS overall and per macro-region, and the most surprising cells |
| the survey | `pegasus-core survey SIM.DO death --replicates 100` | every admissible field of every fitted block, the gated lens/estimand/scale combinations only (`--ungated` adds the failing ones, their leads marked `gate: failed`); leads to the register. Fields run on `PEGASUS_SURVEY_WORKERS` threads (default: a quarter of the cores, at most 4, cut to the free RAM; 1 is serial) over the one loaded model, +0.1 GB each |
| held-out model choice | `scripts/measure_heldout.py DATASET EVENT TRAIN_FIRST TRAIN_LAST TEST_LAST BLOCK GRAPH/PROFILE...` | e.g. `contiguity/group knn6/group contiguity/category`; one `HELDOUT` line per configuration |
| the harness for a lens | `pegasus-core harness SIM.DO death I60-I69 space_time --graph knn6` | surrogates (own ledger) and, for subset lenses, the power curve; stored under `pegasus_home/harness` |
| a non-default source | `PEGASUS_SOURCE='{"source": "mark", "mark": "PESO", "bounds": [200, 7000]}'` before `fit_blocks.py` | also `{"source": "code_list", "column": "CODANOMAL"}`; block `*` for an event type without a tree |

**Tools over MCP (paused, ADR-0008):**

| task | command | notes |
|---|---|---|
| serve the tools over MCP (paused, ADR-0008) | `$PY -m pip install -e .[mcp]` once, then `pegasus-core mcp` (stdio, read-only) | not registered with any client; `--allow-confirm` lets `confirm_claim` spend the reserve |
| exercise the MCP server | `$PY scripts/mcp_demo.py [--spend]` | a real stdio client against `pegasus_home`; `--spend` uses a copy of the ledger |

**The environment** (2026-10-06). The v1 solver needs CHOLMOD (scikit-sparse), numba and, for the many-column products, CuPy:
- `conda install -n pegasus -c conda-forge scikit-sparse --no-deps` plus its SuiteSparse libraries, with `--no-deps` as well. **Never let conda solve it in:** the solver swapped the CUDA PyTorch for a CPU build and removed geopandas, shapely and pillow.
- PyTorch with CUDA: `$PY -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121`.
- The pip PyTorch bundles its own `torch/lib/libiomp5md.dll`, which collides with conda's `intel-openmp` (MKL, numpy): "OMP: Error #15", then a fatal error inside numpy's LAPACK. It is renamed `libiomp5md.dll.bak`, so PyTorch uses the conda runtime.
- CuPy: `$PY -m pip install cupy-cuda12x`.
