import sys, json, numpy as np
from pegasus_core import harness
from pegasus_core.scans import maps, pairs
k = int(sys.argv[1])
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
for ho in (False, True):
    neg = harness.map_negatives(inp, basis, gen, 20, ho, seed=("map-negatives-val",), adjust=k)
    W = neg["worlds"]
    print("adjust", k, "health_only", ho, flush=True)
    for key in ("marginal:treebh", "marginal:by", "conditional:treebh", "conditional:by", "conditional:raw"):
        v = [w[key] for w in W]; print(" ", key, "mean", sum(v)/len(v), "max", max(v), "worlds>0", sum(x > 0 for x in v), flush=True)
    d = harness.map_delta(neg, "conditional")
    print("  delta_c", d["delta"], {f: round(v, 3) for f, v in d["rate_by_delta_and_family"][0.1].items()}, flush=True)
