"""python data/perf/traj_json.py LABEL [step]: tau trajectory (active components), MAP movement and CG from a probe's JSON."""
import json
import sys
from pathlib import Path

r = json.loads((Path(__file__).parent / "out" / f"{sys.argv[1]}.json").read_text())
step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
h = r["history"]
keys = [k for k, v in h[0]["taus"].items() if v != 1.0 and not k.startswith(("th_",))]
print("outer   objective  change    move   cg    " + " ".join(f"{k:>8}" for k in keys))
for x in h[::step]:
    print(f"{x['iteration']:5d} {x['objective']:11.1f} {x['change']:7.3f} {x.get('move', 0):7.2f} {x.get('cg', 0):6d}  "
          + " ".join(f"{x['taus'][k]:8.3g}" for k in keys))
print({k: r[k] for k in ("outers", "converged", "stop_reason", "cg_iterations", "fit_wall", "fit_cpu")})
