"""map_negatives (same random stream) that also prints the health-involving admitted conditional edges of each world."""
import sys, numpy as np
from pegasus_core import config
from pegasus_core.scans import maps, pairs
k, ho = int(sys.argv[1]), sys.argv[2] == "ho"
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
rng = np.random.default_rng(config.seed(sys.argv[3] if len(sys.argv) > 3 else "map-negatives-val", "health" if ho else "all"))
fields = [i for i, g in enumerate(inp.groups) if not (ho and g == "context")]
for w in range(20):
    B = inp.B.copy(); sub = B[:, fields]; miss = ~np.isfinite(sub)
    B[:, fields] = np.where(miss, np.nan, gen.randomise(np.where(miss, 0.0, sub), rng))
    world = maps.MapInputs(inp.places, inp.names, inp.groups, inp.labels, B, inp.SD, inp.overlap, inp.meta)
    m = maps.dependency_map(world, basis, None, "neg", adjust=k)
    for e in m.edges.to_pylist():
        if (e["admitted_c"] and (ho is False or "context" != e["family"][-7:] or e["gx"] != "context" or e["gy"] != "context")) and not (e["gx"] == "context" and e["gy"] == "context" and ho):
            print(f"world {w} {e['x']} ~ {e['y']} fam {e['family']} rho_c {e['rho_c']:+.2f} n {e['n_eff_c']:.0f} p_c {e['p_c']:.2e} marg {e['rho']:+.2f}", flush=True)
    print("world", w, "done", m.controlled["conditional"], flush=True)
