"""CP-APR on the SIH tensor, and the correlates of the PCA factors (step 1 output)."""
import numpy as np, time, glob, pyarrow.parquet as pq, pyarrow.compute as pc
from pegasus_core.scans import maps, utilization, pairs, patterns, map_inputs
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
d = np.load("data/utilization/step1.npz"); S, SD = d["S"], d["SD"]
y, mu, names = utilization.tensor(inp)
sih = [i for i, g in enumerate(inp.groups) if g == "SIH"]
U = len(inp.places)
def wcorr(a, b, w):
    ok = np.isfinite(a) & np.isfinite(b); w = w[ok]; a = a[ok]; b = b[ok]
    ma, mb = (w*a).sum()/w.sum(), (w*b).sum()/w.sum()
    return (w*(a-ma)*(b-mb)).sum()/np.sqrt((w*(a-ma)**2).sum()*(w*(b-mb)**2).sum())
w = mu.sum((1, 2))
print("== CP-APR (place x year x chapter), deviance explained of mu-alone")
side_a = np.isin(inp.places // 100000, [1, 2, 5])
res = {}
for R in (1, 2, 3, 4, 5, 6):
    t = time.time()
    f = patterns.fit(y, mu, R, iterations=400)
    expl = 1 - f.deviance / f.deviance0
    _, st_t = patterns.temporal_stability(y, mu, R, f)
    _, st_s = patterns.spatial_stability(y, mu, R, side_a, f)
    res[R] = f
    print(f"rank {R}: dev0 {f.deviance0:.0f} dev {f.deviance:.0f} explained {expl:.3f}  shares {np.round(f.shares[1:],3)}  stab_time {np.round(st_t,2)} stab_space {np.round(st_s,2)}  ({time.time()-t:.0f}s)", flush=True)
np.savez("data/utilization/cpapr.npz", **{f"A{R}": f.A for R, f in res.items()}, **{f"C{R}": f.C for R, f in res.items()}, **{f"B{R}": f.B for R, f in res.items()})
for R in (1, 2, 3):
    f = res[R]
    print(f"-- rank {R}: place loadings vs PCA scores (weighted by expected admissions), chapter loadings vs PCA loadings")
    for r in range(R):
        la = np.log(np.maximum(f.A[:, r], 1e-9))
        print(f"  comp {r}: corr(log a, PC1..3) =", [round(wcorr(la, S[:, k], w), 2) for k in range(3)], " corr(a, PC1..3)", [round(wcorr(f.A[:, r], S[:, k], w), 2) for k in range(3)], " c-mode vs PC1 loading", round(np.corrcoef(f.C[:, r], d["loadings"][:, 0])[0, 1], 2), "range c", np.round([f.C[:, r].min(), f.C[:, r].max()], 2))
print("c-mode comp0 rank1:", dict(zip([n.split(':')[1] for n in names], np.round(res[1].C[:, 0], 2))))
print("year mode rank1", np.round(res[1].B[:, 0], 2))
