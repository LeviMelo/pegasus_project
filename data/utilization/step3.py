"""Correlates of the utilization factors under ADR-0005's E_b null (marginal, and given the other contexts)."""
import numpy as np, glob, pyarrow.parquet as pq, pyarrow.compute as pc, duckdb
from pegasus_core.scans import maps, utilization, pairs, map_inputs
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
d = np.load("data/utilization/step1.npz"); S, SD = d["S"], d["SD"]; K = 2
basis = pairs.MoranBasis(inp.places)
U = len(inp.places); ix = {int(u): i for i, u in enumerate(inp.places)}
# care-flow extras: self-sufficiency (resident admissions treated in the home municipality) and import share
files = [f"C:/Users/Galaxy/LEVI/projects/pegasus_data/data/probes/care_flow/sih_rd_{y}.parquet" for y in range(2015, 2020)]
con = duckdb.connect()
rows = con.execute("""SELECT cast(\"from\" as bigint)//10 AS f, cast(\"to\" as bigint)//10 AS t, sum(weight) w FROM read_parquet(?) GROUP BY ALL""", [files]).fetchall()
res = np.zeros(U); home = np.zeros(U); treated = np.zeros(U); own_treated = np.zeros(U)
for f, t, w in rows:
    if f in ix: res[ix[f]] += w
    if t in ix: treated[ix[t]] += w
    if f == t and f in ix: home[ix[f]] = w
self_suff = np.where(res > 0, home / np.maximum(res, 1), np.nan)
import_share = np.where(treated > 0, 1 - home / np.maximum(treated, 1), np.nan)   # share of treated admissions that are from elsewhere
z = lambda v: (v - np.nanmean(v)) / np.nanstd(v)
extras = {"care:self_sufficiency": z(np.arcsin(np.sqrt(self_suff))), "care:import_share": z(np.arcsin(np.sqrt(np.where(treated > 0, import_share, np.nan)))),
          "care:treated_per_resident_log": z(np.log((treated + 1) / np.maximum(res, 1) ) )}
print("care-flow coverage", {k: int(np.isfinite(v).sum()) for k, v in extras.items()})
# total admissions place effect (all chapters pooled) from the tensor
y, mu, names = utilization.tensor(inp)

from pegasus_core.scans import map_inputs
b, sd, tau = map_inputs.place_effect(y.sum((1, 2)), mu.sum((1, 2)))
eff = {f"util{k+1}": (S[:, k], SD[:, k]) for k in range(K)} | {"total_admission_rate": (b, sd)}
ctx = inp.context_index()
for i in ctx: eff[inp.names[i]] = (inp.B[:, i], inp.SD[:, i])
for n, v in extras.items(): eff[n] = (np.where(np.isfinite(v), v, np.nan), np.where(np.isfinite(v), 0.05, np.nan))
names, R, N = pairs.statistics(eff, basis)
def lcb(r, n): return np.tanh(max(np.arctanh(min(abs(r), 1-1e-12)) - 1.645/np.sqrt(max(n-3, 1e-9)), 0))
print("== marginal rho (n_eff), E_b null; * = H0 |rho|<=0.03 rejected at 5% single test")
heads = [f"util{k+1}" for k in range(K)] + ["total_admission_rate"]
others = [n for n in names if n not in heads]
print(f"{'':32s}" + "".join(f"{h:>18s}" for h in heads))
for o in others:
    line = f"{o:32s}"
    for h in heads:
        i, j = names.index(h), names.index(o)
        p = pairs.minimum_effect_p(np.array([R[i, j]]), np.array([N[i, j]]), 0.03)[0]
        line += f"{R[i,j]:+7.2f} ({N[i,j]:5.0f}){'*' if p<.05 else ' '}  "
    print(line)
print("== given the other contexts (n_eff - dim Z)")
print(f"{'':32s}" + "".join(f"{h:>18s}" for h in heads))
cn = [inp.names[i] for i in ctx]
for k in [n for n in others]:
    if k in cn:
        Z = inp.design((inp.names.index(k),)); sub = {h: eff[h] for h in heads} | {k: eff[k]}
        nm, Rc, Nc = pairs.statistics(sub, basis, Z, against=k); q = Z.shape[1]
    else:
        Z = inp.design(); sub = {h: eff[h] for h in heads} | {k: eff[k]}
        nm, Rc, Nc = pairs.statistics(sub, basis, Z, against=k); q = Z.shape[1]
    line = f"{k:32s}"
    for h in heads:
        i, j = nm.index(h), nm.index(k); n = max(Nc[i, j]-q, 3.01)
        p = pairs.minimum_effect_p(np.array([Rc[i, j]]), np.array([n]), 0.1)[0]
        line += f"{Rc[i,j]:+7.2f} ({n:5.0f}){'*' if p<.05 else ' '}  "
    print(line)
