"""The solver benchmark (ARCHITECTURE §5.8; docs/plans/2026-10-06-optimization.md §7).

    python scripts/bench.py [--solver v0|v1] [--blocks SIM.DO:IX,SIM.DO:VII] [--years 2010-2021] [--warm]

Fits each block from a cold start (or warm from its stored relative) without saving it, and writes one JSON line
per block to data/bench/<date>.jsonl: wall seconds, outers, Newton steps, the final objective, φ, every τ, the
solver's own timings, and the commit. A change to the solver is measured here before it is adopted; a block that
slows by more than 10 % without a recorded reason rejects the change."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import torch

parser = argparse.ArgumentParser()
parser.add_argument("--solver", default=os.environ.get("PEGASUS_SOLVER", "v1"))
parser.add_argument("--blocks", default="SIM.DO:VII,SIM.DO:IX")
parser.add_argument("--years", default="2010-2021")
parser.add_argument("--warm", action="store_true")
parser.add_argument("--outer", type=int, default=40)
parser.add_argument("--threads", type=int, default=0)
parser.add_argument("--accel", action="store_true", help="Anderson acceleration of the strengths (fit(accelerate=True))")
parser.add_argument("--heldout", type=int, default=0, help="score the years after the fit up to this one (monolith.heldout)")
args = parser.parse_args()
os.environ["PEGASUS_SOLVER"] = args.solver
if args.threads:
    torch.set_num_threads(args.threads)

from pegasus_core import graphs, monolith  # noqa: E402

first, last = map(int, args.years.split("-"))
years = range(first, last + 1)
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
out = Path("data/bench") / f"{time.strftime('%Y-%m-%d')}.jsonl"
out.parent.mkdir(parents=True, exist_ok=True)
EVENTS = {"SIM.DO": "death", "SIH-RD": "hospitalisation", "SINASC-DN": "birth"}
for spec in args.blocks.split(","):
    dataset, block = spec.split(":")
    t0 = time.time()
    data = monolith.assemble(dataset, EVENTS.get(dataset, "notification"), block, years)
    t_asm = time.time() - t0
    model = monolith.Monolith(data, graphs.graph(data.places, "contiguity"), "contiguity")
    t1 = time.time()
    model.fit(outer=args.outer, warm="auto" if args.warm else None, mean_tol=1.0, accelerate=args.accel,
              log=lambda line, b=block: print(f"  {b} {line[:400]}", flush=True))
    secs = time.time() - t1
    nw = getattr(model, "_solver_v1", None)
    row = {"block": spec, "years": args.years, "solver": args.solver, "start": "warm" if args.warm else "cold", "accel": args.accel,
           "commit": commit, "seconds": round(secs, 2), "assemble_seconds": round(t_asm, 2),
           "outers": len(model.history), "newton": len(model.newton_log), "cg": model.cg_iterations,
           "objective": float(model.objective()) * model._objective_norm(), "phi": model.phi,
           "converged": model.converged, "stop": model.stop_reason,
           "taus": {k: c.tau for k, c in model.components.items()},
           "solver_timing": {k: round(v, 3) for k, v in (nw.timing.items() if nw else []) if isinstance(v, float) and v < 1e6},
           "parameters": int(sum(p.numel() for p in model.params.values())), "nnz": int(len(data.y))}
    row["history"] = [{"mean_s": round(h.get("mean_seconds", 0), 2), "tau_s": round(h.get("tau_seconds", 0), 2),
                        "newton": h.get("newton"), "change": round(h.get("change", 0), 4)} for h in model.history]
    if args.heldout:
        test = monolith.assemble(dataset, EVENTS.get(dataset, "notification"), block, range(last + 1, args.heldout + 1))
        h = monolith.heldout(model, test)
        row["heldout"] = {"years": [last + 1, args.heldout], "deviance_per_event": h["deviance_per_event"],
                          "nb_loglik_per_event": h["nb_loglik_all"] / h["events"], "events": h["events"]}
    print("BENCH", json.dumps(row), flush=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
