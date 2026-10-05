"""Power of the adjusted conditional layer: a field made of a real SIH signal that is NOT utilization is still found;
one made of the utilization factor is not."""
import numpy as np
from pegasus_core import config
from pegasus_core.scans import maps, pairs
inp = maps.MapInputs.load({"what": "map_inputs", "years": [2015,2016,2017,2018,2019], "v": 1})
basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
S, SD, info = maps.factors(inp, 2)
rng = np.random.default_rng(config.seed("planted-util"))
z = lambda v: (v - v.mean()) / v.std()
ix = inp.names.index
tgt = {"SIM:XII": "SIH:IX", "SIM:XIII": "SIH:X", "SIM:IV": "SIH:XIV"}
for kind in ("specific", "utilization"):
    B = inp.B.copy()
    for sim, sih in tgt.items():
        Z = np.column_stack([np.ones(len(S)), inp.design(), S])
        b = inp.B[:, ix(sih)]
        resid = b - Z @ np.linalg.lstsq(Z, b, rcond=None)[0]
        sig = z(resid) if kind == "specific" else z(S[:, 0])
        noise = z(gen.randomise(inp.B[:, ix(sim)], rng))
        B[:, ix(sim)] = 0.6 * sig + 0.8 * noise
    world = maps.MapInputs(inp.places, inp.names, inp.groups, inp.labels, B, inp.SD, inp.overlap, inp.meta)
    for k in (0, 2):
        m = maps.dependency_map(world, basis, None, "planted", adjust=k)
        print(kind, "adjust", k)
        for sim, sih in tgt.items():
            e = [r for r in m.edges.to_pylist() if {r["x"], r["y"]} == {sim, sih}][0]
            print(f"   {sim} ~ {sih}: marginal {e['rho']:+.2f} (n {e['n_eff']:.0f}, adm {e['admitted']}) conditional {e['rho_c']:+.2f} (n {e['n_eff_c']:.0f}, adm {e['admitted_c']})", flush=True)
