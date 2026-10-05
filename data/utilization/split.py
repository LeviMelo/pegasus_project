import numpy as np
from pegasus_core.scans import maps, patterns
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
L = maps.factors(inp, 3)[2]["loadings"]
side = np.isin(inp.places // 100000, [1, 2, 5])
for name, m in (("N+NE+CO", side), ("SE+S", ~side)):
    w = maps.MapInputs(inp.places[m], inp.names, inp.groups, inp.labels, inp.B[m], inp.SD[m], inp.overlap, inp.meta)
    i = maps.factors(w, 3)[2]; Lh = i["loadings"]
    print(name, "eig share", np.round(i["eigenvalues"][:3] / len(i["eigenvalues"]), 3), "congruence per factor (full vs half):", np.round(np.abs(np.diag(patterns.congruence(L, Lh))), 2))
