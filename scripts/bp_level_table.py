"""Pool the rolling origins of `scripts/measure_bp_level.py`: per variant the held-out log score summed over the
(node, origin) pairs, the PIT's KS pooled over them, and the mean per-pair KS.

Usage: python scripts/bp_level_table.py annual|dengue [--nodes A,B] [--origins 2014,2016]"""

import glob
import json
import sys

import numpy as np
from scipy import stats

kind = sys.argv[1]
nodes = origins = None
for i, a in enumerate(sys.argv):
    if a == "--nodes":
        nodes = set(sys.argv[i + 1].split(","))
    if a == "--origins":
        origins = set(sys.argv[i + 1].split(","))
data = {}
for f in sorted(glob.glob(f"data/logs/bp_level_{kind}_*.json")):
    with open(f, encoding="utf-8") as fh:
        data.update(json.load(fh))
pairs = [k for k in data if (nodes is None or k.split("@")[0] in nodes) and (origins is None or k.split("@")[1] in origins)]
names = list(data[pairs[0]])
print(f"{kind}: {len(pairs)} (node, origin) pairs: {', '.join(pairs)}")
print(f"{'variant':44s} {'log score':>12s} {'pooled KS':>9s} {'mean KS':>8s} {'mean worst':>10s} {'obs/exp':>8s}")
for n in names:
    rows = [data[k][n] for k in pairs if n in data[k]]
    u = np.concatenate([np.asarray(r["u"]) for r in rows])
    print(f"{n:44s} {sum(r['ll'] for r in rows):12.0f} {stats.kstest(u, 'uniform').statistic:9.3f} "
          f"{np.mean([r['ks'] for r in rows]):8.3f} {np.mean([r['worst'] for r in rows]):10.3f} "
          f"{np.mean([r['obs_exp'] for r in rows]):8.2f}")
regions = sorted({r for k in pairs for v in data[k].values() for r in v.get("by_region", {})})
if regions:
    print("mean KS per macro-region (1 N, 2 NE, 3 SE, 4 S, 5 CO):", *regions)
    for n in names:
        rows = [data[k][n] for k in pairs if n in data[k] and "by_region" in data[k][n]]
        if rows:
            print(f"{n:44s}", *[f"{np.mean([r['by_region'][g] for r in rows if g in r['by_region']]):.3f}" for g in regions])
