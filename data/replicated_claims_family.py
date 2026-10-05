"""Step 5: does the claim's family diverge when the node's own substitutes are kept inside? beta (per sd-year, direct standardisation
as step 2) of the whole ICD block incl. the node, of the chapter incl. the node, and of transport without V87/V89/V99."""
import json, sys
import numpy as np
sys.argv = sys.argv[:1]
import replicated_claims as rc
rows = json.load(open("data/replicated_claims/claims.json"))
import pandas as pd
from pegasus_core import leads
from pathlib import Path
from pegasus_core.tools import kinds_of
reg = leads.Register(Path("pegasus_home/leads_T2019"))
mine = {x.id: x for x in reg.current()}
CH = {"I": ("I00", "I99"), "J": ("J00", "J99"), "R": ("R00", "R99"), "V": ("V01", "Y98"), "W": ("V01", "Y98"), "X": ("V01", "Y98"), "Y": ("V01", "Y98")}
out = []
for r in rows:
    x = mine[r["id"]]; places = x.locus["places"]; node = r["node"]; own = rc.cats(node)
    blk = rc.block_of(node); fam = rc.cats(blk) if blk and "-" in blk else own
    chap = rc.rng(*CH[own[0][0]])
    d = {"id": r["id"], "node": node, "uf": r["uf"]}
    d["beta_block_incl"] = rc.slope(*rc.oe(places, sorted(set(fam) | set(own)), "popsvs"))[0]
    d["beta_chapter_incl"] = rc.slope(*rc.oe(places, chap, "popsvs"))[0]
    if own[0][0] == "V" and node in ("V87", "V89", "V99", "V09", "V22", "V29", "V49"):
        spec = [c for c in rc.rng("V01", "V99") if c not in ("V87", "V89", "V99")]
        d["beta_V_specific"] = rc.slope(*rc.oe(places, spec, "popsvs"))[0]
        d["beta_V_all"] = rc.slope(*rc.oe(places, rc.rng("V01", "V99"), "popsvs"))[0]
    out.append(d)
df = pd.DataFrame(out)
df.to_pickle("data/replicated_claims/family.pkl")
print(df.round(3).to_string())
