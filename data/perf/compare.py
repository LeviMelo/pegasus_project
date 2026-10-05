"""Compare fit probes: python data/perf/compare.py REFERENCE LABEL [LABEL ...]  (reads data/perf/out/*.json, *.npz)

Per label: outers, CG iterations (the machine-independent cost), wall and CPU seconds, convergence, phi, the largest
tau ratio against the reference over the active components, and the event-weighted RMS of log(mu / mu_reference)."""
import json
import sys
from pathlib import Path

import numpy as np

out = Path(__file__).parent / "out"
ref_label, labels = sys.argv[1], sys.argv[2:]
ref, ref_mu = json.loads((out / f"{ref_label}.json").read_text()), np.load(out / f"{ref_label}.npz")["mu"]
print(f"{'label':14} {'outers':>6} {'CG its':>8} {'wall s':>7} {'cpu s':>7} {'phi':>6} {'max tau ratio':>14} {'rms dlog mu':>12}  stop")
for label in [ref_label, *labels]:
    r = json.loads((out / f"{label}.json").read_text())
    mu = np.load(out / f"{label}.npz")["mu"]
    ok = (ref_mu > 0) & (mu > 0)
    rms = np.sqrt(np.sum(ref_mu[ok] * np.log(mu[ok] / ref_mu[ok]) ** 2) / np.sum(ref_mu[ok]))
    ratios = [max(r["taus"][k] / ref["taus"][k], ref["taus"][k] / r["taus"][k]) for k in r["taus"]
              if min(r["taus"][k], ref["taus"][k]) < 1e5 and ref["taus"][k] != 1.0]
    print(f"{label:14} {r['outers']:6d} {r.get('cg_iterations', 0):8d} {r['fit_wall']:7.0f} {r['fit_cpu']:7.0f} {r['phi']:6.3f} "
          f"{max(ratios):14.2f} {rms:12.2e}  {r['stop_reason']}")
