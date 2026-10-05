"""The dependency map with and without the utilization factors in the conditional layer; edges to the store."""
import sys, numpy as np, pickle
from pegasus_core import store
from pegasus_core.scans import maps, pairs
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
basis = pairs.MoranBasis(inp.places)
out = {}
for k in (0, 1, 2):
    m = maps.dependency_map(inp, basis, None, f"util{k}", adjust=k)
    print(k, m.controlled, f"{m.seconds:.0f}s", flush=True)
    out[k] = m.edges.to_pylist()
pickle.dump(out, open("data/utilization/maps.pkl", "wb"))
