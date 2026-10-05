"""Fit probe (fit throughput front): one block fitted under chosen options, nothing stored in the fit store.

python data/perf/fit_probe.py LABEL DATASET EVENT BLOCK FIRST LAST [--grain month] [--population P] [--outer N]
       [--warm auto] [--accel] [--move-tol X] [--tol X] [--through YYYYMM] [--device cpu|cuda]

Writes data/perf/out/LABEL.json (history: objective, newton steps, seconds, tau trajectory) and LABEL.npz (the
fitted mu[u, t] of the whole block, for `compare`)."""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from pegasus_core import graphs, monolith

OUT = Path(__file__).parent / "out"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("dataset")
    ap.add_argument("event")
    ap.add_argument("block")
    ap.add_argument("first", type=int)
    ap.add_argument("last", type=int)
    ap.add_argument("--grain", default="year")
    ap.add_argument("--population", default=None)
    ap.add_argument("--outer", type=int, default=40)
    ap.add_argument("--tol", type=float, default=0.02)
    ap.add_argument("--warm", default=None)
    ap.add_argument("--accel", action="store_true")
    ap.add_argument("--move-tol", type=float, default=0.0)
    ap.add_argument("--mean-tol", type=float, default=0.0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    data = monolith.assemble(a.dataset, a.event, a.block, range(a.first, a.last + 1), grain=a.grain,
                             population=a.population, cache=not a.no_cache)
    t_assemble = time.time() - t0
    model = monolith.Monolith(data, graphs.graph(data.places, "contiguity"), "contiguity", device=a.device)
    t1 = time.process_time(), time.time()
    warm = a.warm
    if warm == "popsvs":     # the same fit under POPSVS: this model's key without its exposure
        warm = {k: v for k, v in model.key().items() if k not in ("population", "population_model")}
    elif warm and warm.startswith("{"):
        warm = json.loads(warm)
    model.fit(outer=a.outer, tol=a.tol, warm=warm, accelerate=a.accel, move_tol=a.move_tol, mean_tol=a.mean_tol,
              log=lambda line: print(line[:150], flush=True))
    wall, cpu = time.time() - t1[1], time.process_time() - t1[0]
    import psutil
    peak = psutil.Process().memory_info().peak_wset / 2 ** 20
    mu, _ = model.expected(np.arange(len(data.leaves)))
    np.savez(OUT / f"{a.label}.npz", mu=mu, y=model.observed(np.arange(len(data.leaves))))
    s = model.summary()
    res = {"label": a.label, "args": vars(a), "assemble_seconds": t_assemble, "fit_wall": wall, "fit_cpu": cpu, "peak_rss_mb": peak,
           "cg_iterations": model.cg_iterations, "outers": len(model.history), "converged": model.converged, "stop_reason": model.stop_reason,
           "phi": model.phi, "taus": s["taus"], "objective": model.history[-1]["objective"],
           "warm": None if model.warm_info is None else {"from": model.warm_info["from"].get("years"),
                                                           "population": model.warm_info["from"].get("population"),
                                                           "carried": model.warm_info["carried"],
                                                           "shifted": model.warm_info["shifted"]},
           "history": model.history}
    (OUT / f"{a.label}.json").write_text(json.dumps(res, default=float, indent=1), encoding="utf-8")
    print(f"RESULT {a.label}: {res['outers']} outers, wall {wall:.0f}s, cpu {cpu:.0f}s, objective {res['objective']:.1f}, "
          f"phi {model.phi:.3f}, peak {peak:.0f} MB, {model.stop_reason}", flush=True)


if __name__ == "__main__":
    main()
