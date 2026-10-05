import numpy as np, time, json
from pegasus_core.scans import maps, utilization, pairs
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
t=time.time(); y, mu, names = utilization.tensor(inp); print("tensor", y.shape, time.time()-t, y.sum(), mu.sum())
S, SD, info = maps.factors(inp, 6)
ev = info["eigenvalues"]; F=len(ev)
print("fields", F); print("eigenvalues", np.round(ev[:8],2), "share", np.round(ev[:6]/F,3))
gen = pairs.MoranBasis(inp.places, "knn8")
null = utilization.parallel_analysis(inp, gen, 200)
q95, q99 = np.quantile(null, .95, 0), np.quantile(null, .99, 0)
print("null mean", np.round(null.mean(0)[:6],2), "q95", np.round(q95[:6],2), "q99", np.round(q99[:6],2))
print("eig > q99:", [int(i+1) for i in range(F) if ev[i]>q99[i]])
print("rank-k share of off-diag R:", [round(utilization.rank1_share(info["R"], ev, np.linalg.eigh(info["R"])[1][:, ::-1], k),3) for k in range(1,7)])
print("loadings:"); 
for n,l in zip(info["fields"], info["loadings"][:,:3]): print(f"  {n:10s}", np.round(l,2))
np.savez("data/utilization/step1.npz", S=S, SD=SD, ev=ev, null=null, loadings=info["loadings"], R=info["R"])
