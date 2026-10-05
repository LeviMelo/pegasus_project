import pickle, numpy as np
from collections import Counter
M = pickle.load(open("data/utilization/maps.pkl", "rb"))
def lcb(r, n): return float(np.tanh(max(np.arctanh(min(abs(r), 1-1e-12)) - 1.645/np.sqrt(max(n-3, 1e-9)), 0))) if np.isfinite(r) else 0.0
s = lambda x: x.replace("ctx:", "c:")
key = lambda e: (e["x"], e["y"])
base = {key(e): e for e in M[0]}
for k in (1, 2):
    cur = {key(e): e for e in M[k]}
    print(f"=== adjust {k}: admitted conditional by family (before -> after), tested")
    fam = Counter(e["family"] for e in M[0])
    b = Counter(e["family"] for e in M[0] if e["admitted_c"]); a = Counter(e["family"] for e in M[k] if e["admitted_c"])
    for f in sorted(fam):
        if b[f] or a[f]: print(f"  {f:18s} {b[f]:3d} -> {a[f]:3d} of {fam[f]}")
    gone = [e for e in M[0] if e["admitted_c"] and not cur[key(e)]["admitted_c"]]
    new = [e for e in M[k] if e["admitted_c"] and not base[key(e)]["admitted_c"]]
    print(f"  vanished {len(gone)}, appeared {len(new)}")
    print("  APPEARED (SIH involved or not):")
    for e in sorted(new, key=lambda e: -lcb(e["rho_c"], e["n_eff_c"])):
        print(f"    {s(e['x']):22s}{s(e['y']):24s} cond {e['rho_c']:+.2f} (n {e['n_eff_c']:.0f}) was {base[key(e)]['rho_c']:+.2f} marg {e['rho']:+.2f} fam {e['family']} {e['status']}")
    sg = Counter(e["family"] for e in gone); print("  vanished by family", dict(sg))
cur = {key(e): e for e in M[2]}
print("=== 20 strongest remaining SIH-involving edges, adjust 2 (conditional layer, lower bound of |rho_c|)")
rem = [e for e in M[2] if ("SIH" in (e["gx"], e["gy"])) and e["family"] != "SIHxSIM" and e["family"] != "SIHxSINASC" and e["gx"] != "SIM" and e["gy"] != "SIM"]
print(len(rem), "admitted SIH-involving conditional edges; by family", dict(Counter(e["family"] for e in rem)))
for e in sorted(rem, key=lambda e: -lcb(e["rho_c"], e["n_eff_c"]))[:25]:
    print(f"  {s(e['x']):12s}{s(e['y']):26s} cond {e['rho_c']:+.2f} (n {e['n_eff_c']:.0f}) lcb {lcb(e['rho_c'], e['n_eff_c']):.2f} | before {base[key(e)]['rho_c']:+.2f} marg {e['rho']:+.2f} {e['status']} p_c {e['p_c']:.3f}{' ADMITTED' if e['admitted_c'] else ''}")
print("=== SIH x SIH: marginal admitted and conditional rho before/after, strongest 12 marginal")
ss = [e for e in M[2] if e["family"] == "SIHxSIH" and e["admitted"]]
print(len(ss), "marginal admitted; conditional admitted before", sum(base[key(e)]["admitted_c"] for e in ss), "after", sum(e["admitted_c"] for e in ss))
print(" median |rho| marginal", np.median([abs(e["rho"]) for e in ss]), "cond before", np.median([abs(base[key(e)]["rho_c"]) for e in ss]), "cond after", np.median([abs(e["rho_c"]) for e in ss]))
allss = [e for e in M[2] if e["family"] == "SIHxSIH"]
print(" all 210: negative rho_c<-0.1:", sum(e["rho_c"] < -0.1 for e in allss), " positive >0.1:", sum(e["rho_c"] > 0.1 for e in allss), " raw p_c<=.05:", sum(e["p_c"] <= .05 for e in allss))
print("=== SIHxSIM, SIHxSINASC best raw")
for fam in ("SIHxSIM", "SIHxSINASC", "SIHxcontext"):
    es = [e for e in M[2] if e["family"] == fam]
    print(fam, len(es), "admitted_c", sum(e["admitted_c"] for e in es), "BY_c", sum(e["by_c"] for e in es))
    for e in sorted(es, key=lambda e: -lcb(e["rho_c"], e["n_eff_c"]))[:6]:
        print(f"   {s(e['x']):12s}{s(e['y']):22s} cond {e['rho_c']:+.2f} (n {e['n_eff_c']:.0f}) lcb {lcb(e['rho_c'], e['n_eff_c']):.2f} p_c {e['p_c']:.3f} before {base[key(e)]['rho_c']:+.2f} marg {e['rho']:+.2f}")
