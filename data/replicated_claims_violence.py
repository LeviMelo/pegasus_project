"""Step 6: the violence family pooled (aggression + undetermined intent + legal intervention), per unit, direct standardisation."""
import os, sys, json
os.chdir("C:/Users/Galaxy/LEVI/projects/pegasus_project"); sys.path.insert(0, "data")
import numpy as np
import replicated_claims as rc
from pegasus_core import leads
from pathlib import Path
reg = leads.Register(Path("pegasus_home/leads_T2019")); mine = {(x.fields[0].split(":")[-1], x.locus["unit"]): x for x in reg.current() if x.locus.get("scale") == "state"}
fam = {"X85-Y09": rc.rng("X85", "Y09"), "X85-Y34": rc.rng("X85", "Y34"), "X85-Y36": rc.rng("X85", "Y36"), "Y10-Y34": rc.rng("Y10", "Y34")}
out = {}
for key, uf in (("X95", "35"), ("Y00", "35"), ("X93", "50"), ("Y35", "52"), ("Y10-Y34", "43")):
    x = mine[(key, uf)]; pl = x.locus["places"]
    out[f"{key} {uf}"] = {nm: round(rc.slope(*rc.oe(pl, c, "popsvs"))[0], 3) for nm, c in fam.items()}
    out[f"{key} {uf}"]["node"] = round(rc.slope(*rc.oe(pl, rc.cats(key), "popsvs"))[0], 3)
for k, v in out.items(): print(k, v)
json.dump(out, open("data/replicated_claims/violence.json", "w"), indent=1)
