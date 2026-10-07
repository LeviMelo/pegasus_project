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
| the solver | v1 for every model (counts, the low-rank interaction, marks, shares); v0 retired 2026-10-06 | exact Newton on the assembled Hessian and Newton on log τ (ARCHITECTURE §5.3–5.4); `PEGASUS_SCORING_PROBES` (16) and `PEGASUS_LAML_TOL` (0.1) tune the strengths |
| the solver benchmark | `PYTHONUTF8=1 $PY scripts/bench.py --blocks SIM.DO:IX,SIM.DO:VII [--warm] [--heldout 2023] [--rank R] [--grain month] [--mean-tol T] [--profile block\|group\|category] [--geography group\|chapter\|block] [--likelihood poisson\|nb] [--prior gaussian\|horseshoe] [--tag T]` | fits without saving; one JSON row per block to `data/bench/<date>.jsonl` (seconds, outers, Newton steps, φ, τ's, per-outer timings, held-out deviance and NB log-likelihood) |
| simulation-based calibration (§10.6) | `PYTHONUTF8=1 $PY scripts/sbc.py SIM.DO death XIII 2010 2021 --replicates 100 --draws 99` | truths drawn from the fitted block's Laplace posterior, Poisson counts simulated, the mean refitted at the same strengths; the ranks of the tracked quantities among the refit's draws and their χ² to `data/probes/sbc/` |
| the CLI | `pegasus-core fit|fields|surprise|scan|survey|ask|relations|leads|ledger` | `pegasus-core --help`; years default 2010-2023, graph contiguity |
| a field's calibration | `pegasus-core surprise SIM.DO death I60-I69 --tier B1` | KS overall and per macro-region, and the most surprising cells |
| the survey | `pegasus-core survey SIM.DO death --blocks I --levels group` | every field with an event: each stage-C question (excess, step, trend) through all its methods (`questions`), error control per question and block, the answers to the register as kind `answer`. Cost: about 15 min per SIH field of seven questions (survey 3, 2026-10-07); no setting chooses fields, methods or replicates |
| one question | `pegasus-core ask SIM.DO death excess A95` | one field through every method of a question: the answers merged by overlapping loci, which methods agree, each finding's shape (Chen & Liu), the answers of another shape counted apart |
| relations | `pegasus-core relations SIM.DO:death:I,IX SIH-RD:hospitalisation:I` | stage D across systems (`tools.relation_survey`): group fields with ≥ 2,000 events, N1 innovations by graph band, lags 0–2, factor model, one BH; relations to the register as kind `relation`; bands with fewer cells than lagged fields are logged as unanswered |
| several fields at once | `pegasus-core joint SIM.DO:death:A90-A99 SIH-RD:hospitalisation:A90-A99 "SINAN-DENG:notification:*"` | places and periods where a set of fields departs together (`departures.joint_excess`, the fast subset scan over fields) |
| documented events | `pegasus-core events` | `harness.event_record`: every method of every built question against `harness.POSITIVES` (declared before their runs); a positive whose question is not built, whose locus a script derives or whose dataset is not served is listed with that status; the record to the store |
| the report | `pegasus-core report --out reports/leads.md` | the register as a person reads it (`report`): answers per question and block with named municipalities, methods, shapes, triage and tier; relations and the scales left unanswered |
| the dossier | `pegasus-core dossier --out reports/dossier.html`; `pegasus-core verdict LEAD_ID confirmed --note …` | the leads by rank, one section each (claim, series against expectation, methods, triage, corroboration, method record); a person's verdict written back, confirmed answers judged as documented events |
| the update | `pegasus-core update plans/default.yml` | brings the fits, the register and the report up to the plan (`update`); each reading redone only where its data or code changed; `--force` redoes all. A full update is hours |
| the plans | `plans/*.yml` | `default` (SIM, SIH, SINASC, SINAN-SIFC; corroborators; the map's contexts); `s1_*` fields from declarations (a measure of SIH chapter X, SIH's procedures by SIGTAP, SINASC's measures and an interval, SIM's mentions); `s6_*` breadth (SIM-DOFET, SIA APAC, CIHA). A system's keys: `blocks` (or `[all]`), `levels`, `measures`, `compositions`, `intervals`, `links`, `classifiers`, `disparities`; a plan's: `confirm_last`, `corroborators`, `contexts`. Run long ones detached, one heavy job at a time |
| alarms (phase 4) | `pegasus-core alarms SINAN-DENG notification '*' 2024-03-15 --report DT_DIGITA` | the place-weeks of the last 8 weeks whose nowcast exceeds the alarm baseline at a 260-week recurrence (`surveillance`); delays from the closed year before |
| held-out model choice | `scripts/measure_heldout.py DATASET EVENT TRAIN_FIRST TRAIN_LAST TEST_LAST BLOCK GRAPH/PROFILE...` | e.g. `contiguity/group knn6/group contiguity/category`; one `HELDOUT` line per configuration |
| a lagged relation (§7.5) | `pegasus-core relation SINASC-DN birth Q02 SINAN-DENG:notification SINAN-CHIK:notification SINAN-ZIKA:notification --grain month --within 2` | the distributed-lag curve of the exposure (log of 1 + events per 1,000 residents) on the field's B1 rate, at immediate regions; `--reverse` is the negative control |
| the planted grid for a field | `pegasus-core grid SIM.DO death I60-I69 --years 2010-2023 --out data/probes/grid/I60-I69.json` | refitted planted and null worlds read by the production lenses (sandbox ledger), each lens's power surface; stored under `pegasus_home/harness` (kind `grid`) |
| a non-default source | `PEGASUS_SOURCE='<a reader>'` before `fit_blocks.py`, the reader a declared field's (`fields.measure_source`, `share_sources`, `interval_source`, `mentions_source`, `flow_source`, `link_source`, `classifier_sources`) | block `*` for an event type without a tree |
| a heavy job | `python scripts/heavy.py --label NAME [--gpu] [--threads N] -- <command>`; a sequence: `python data/chain.py LOG1 "cmd" LOG2 "cmd"` under one `heavy.py` slot | the machine-wide queue (slots, free memory, the one GPU; ARCHITECTURE §5.7); detach with PowerShell `Start-Process` beyond the Bash tool's ten minutes |

**Tools over MCP (paused, ADR-0008):**

| task | command | notes |
|---|---|---|
| serve the tools over MCP (paused, ADR-0008) | `$PY -m pip install -e .[mcp]` once, then `pegasus-core mcp` (stdio, read-only) | not registered with any client; `--allow-confirm` lets `confirm_claim` spend the reserve |
| exercise the MCP server | `$PY scripts/mcp_demo.py [--spend]` | a real stdio client against `pegasus_home`; `--spend` uses a copy of the ledger |

**The environment** (2026-10-06). The v1 solver needs CHOLMOD (scikit-sparse) and numba:
- `conda install -n pegasus -c conda-forge scikit-sparse --no-deps` plus its SuiteSparse libraries, with `--no-deps` as well. **Never let conda solve it in:** the solver swapped the CUDA PyTorch for a CPU build and removed geopandas, shapely and pillow.
- PyTorch with CUDA: `$PY -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121`.
- The pip PyTorch bundles its own `torch/lib/libiomp5md.dll`, which collides with conda's `intel-openmp` (MKL, numpy): "OMP: Error #15", then a fatal error inside numpy's LAPACK. It is renamed `libiomp5md.dll.bak`, so PyTorch uses the conda runtime.
- CuPy is not needed: in float64 the CPU beats this GPU on the solver's products (2026-10-06).
